"""Repair migrated ``letter_templates`` rows (LTR-8, LTR-9).

Two defects came out of the Denticon import and print on real patient-facing
consent forms:

LTR-8 — ``?`` mojibake
    34 of 153 bodies have typographic characters replaced by a literal ``?``
    (``It?s been several months``, ``also known as ?bleaching?``, ``RADIESSE?``).
    The loss is **upstream**: the whole corpus contains zero non-ASCII bytes, so
    the ``?`` is already in ``LETTERS.txt`` and re-running the migration cannot
    recover the original characters. Only a contextual repair can, so the rules
    below are deliberately narrow and everything they cannot prove is left alone
    and reported for a human.

    R1 contraction  ``you?re`` / ``It?s`` / ``don?t``  -> curly apostrophe.
                    A ``?`` between a letter and s/t/re/ve/ll/d/m is never a
                    question mark.
    R2 quote pair   ``as ?bleaching?``                 -> curly quotes.
                    A ``?`` *preceded by whitespace* is never a real question
                    mark (a question mark always hugs the word before it), so it
                    opens a quote; the next ``?`` that is followed by whitespace
                    or punctuation closes it.
    R3 trademark    ``RADIESSE?`` / ``Botox?/Dysport?`` -> (R). Opt-in
                    (``--trademarks``) and only for the brand names listed on the
                    command line, because ``treatment?`` is a legitimate question.

LTR-9 — ``channel`` polluted by a field-offset error
    11 rows hold letter *body text* in ``channel`` (``'policies'``,
    ``'if needed please lea'``). The importer's reader splits on commas, and
    ``LETTERS.txt`` has embedded commas/newlines inside the HTML ``BODY`` column,
    so those rows are shifted. ``--fix-channel`` nulls the junk (keeping only the
    known codes) and reports every affected row so the bodies can be re-imported.

Nothing is written without ``--apply``; the default is a dry-run report.

    python -m scripts.repair_letter_templates                       # report
    python -m scripts.repair_letter_templates --apply               # fix LTR-8
    python -m scripts.repair_letter_templates --fix-channel --apply # + LTR-9
    python -m scripts.repair_letter_templates --trademarks RADIESSE,Botox,Dysport --apply
"""

from __future__ import annotations

import argparse
import re

from sqlalchemy import select

from app.db.models import LetterTemplate
from app.db.session import SessionLocal

# The delivery-channel vocabulary (definitions group ``letter_channel``).
VALID_CHANNELS = {"L", "D", "E", "S"}

# R1: a "?" between a letter and a contraction suffix is a lost apostrophe.
_CONTRACTION = re.compile(r"(?<=[A-Za-z])\?(?=(?:s|t|re|ve|ll|d|m)\b)")
# R2: a "?" preceded by whitespace / an opening bracket opens a quote; the next
# "?" that is followed by whitespace or closing punctuation closes it.
_QUOTE_PAIR = re.compile(r"(?<=[\s(\[>])\?([^?<>]{1,120}?)\?(?=[\s).,;:!\]<]|$)")

APOSTROPHE = "’"
LEFT_QUOTE = "“"
RIGHT_QUOTE = "”"
REGISTERED = "®"


def repair_body(body: str, trademarks: list[str]) -> tuple[str, int]:
    """Apply the three rules. Returns ``(repaired, replacements_made)``.

    Every rule is a same-length substitution, so the count is simply how many
    ``?`` characters disappeared.
    """
    if not body or "?" not in body:
        return body, 0

    fixed = _CONTRACTION.sub(APOSTROPHE, body)
    fixed = _QUOTE_PAIR.sub(lambda m: f"{LEFT_QUOTE}{m.group(1)}{RIGHT_QUOTE}", fixed)
    for brand in trademarks:
        # Only where the "?" directly follows the brand name — "Botox?/Dysport?".
        fixed = re.sub(rf"(?<={re.escape(brand)})\?", REGISTERED, fixed)

    return fixed, body.count("?") - fixed.count("?")


def _clean(text: str) -> str:
    return text.replace("\r", " ").replace("\n", " ")


def _context(body: str, limit: int = 4) -> list[str]:
    return [_clean(m.group(0)) for m in list(re.finditer(r".{0,22}\?.{0,22}", body))[:limit]]


def _diff_snippets(before: str, after: str, limit: int = 8) -> list[tuple[str, str]]:
    """The changed neighbourhoods, so a human can approve a patient-facing edit.

    Safe because every rule is same-length: index i in ``before`` is index i in
    ``after``.
    """
    out: list[tuple[str, str]] = []
    for i, (a, b) in enumerate(zip(before, after)):
        if a == b:
            continue
        lo, hi = max(0, i - 24), min(len(before), i + 24)
        out.append((_clean(before[lo:hi]), _clean(after[lo:hi])))
        if len(out) >= limit:
            break
    return out


def run(
    tenant_id: int | None, *, trademarks: list[str], fix_channel: bool,
    apply: bool, show_diff: bool = False,
) -> None:
    db = SessionLocal()
    try:
        stmt = select(LetterTemplate)
        if tenant_id is not None:
            stmt = stmt.where(LetterTemplate.tenant_id == tenant_id)
        rows = list(db.execute(stmt.order_by(LetterTemplate.id)).scalars().all())

        repaired = leftover = 0
        for row in rows:
            body = row.body_html or ""
            if "?" not in body:
                continue
            fixed, changes = repair_body(body, trademarks)
            if changes:
                repaired += 1
                print(f"  [{row.id}] {row.legacy_id or '-'} {row.name[:48]}: {changes} replacement(s)")
                if show_diff:
                    for was, now in _diff_snippets(body, fixed):
                        print(f"      -  ...{was}...")
                        print(f"      +  ...{now}...")
                if apply:
                    row.body_html = fixed
            if "?" in fixed:
                # Anything the rules could not prove — could be a legitimate
                # question mark, could be a lost character. A human decides.
                leftover += 1
                for snippet in _context(fixed):
                    print(f"      review: ...{snippet}...")

        channel_fixed = 0
        if fix_channel:
            print("\nLTR-9 channel:")
            for row in rows:
                value = (row.channel or "").strip()
                if not value or value in VALID_CHANNELS:
                    continue
                channel_fixed += 1
                size = len(row.body_html or "")
                # The offset that spilled body text into ``channel`` also truncated
                # the body on those rows — call it out, nulling the channel does
                # not recover the letter.
                warn = "  ** body looks TRUNCATED, re-import needed" if size < 200 else ""
                print(f"  [{row.id}] {row.legacy_id or '-'} {row.name[:40]}: "
                      f"channel={value[:40]!r} -> NULL (body_html {size} chars){warn}")
                if apply:
                    row.channel = None

        if apply:
            db.commit()

        verb = "repaired" if apply else "would repair"
        print(f"\n{verb} {repaired} body_html row(s); {leftover} row(s) still contain '?' "
              f"and need a human eye.")
        if fix_channel:
            print(f"{verb} {channel_fixed} channel value(s).")
        if not apply:
            print("Dry run — nothing was written. Re-run with --apply.")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", type=int, default=None, help="Tenant id (default: all)")
    parser.add_argument("--trademarks", default="",
                        help="Comma-separated brand names whose trailing '?' is a lost (R)")
    parser.add_argument("--fix-channel", action="store_true",
                        help="Also null out channel values holding body text (LTR-9)")
    parser.add_argument("--show-diff", action="store_true",
                        help="Print every changed neighbourhood (review before --apply)")
    parser.add_argument("--apply", action="store_true", help="Write the changes (default: dry run)")
    args = parser.parse_args()

    trademarks = [t.strip() for t in args.trademarks.split(",") if t.strip()]
    run(args.tenant, trademarks=trademarks, fix_channel=args.fix_channel,
        apply=args.apply, show_diff=args.show_diff)


if __name__ == "__main__":
    main()
