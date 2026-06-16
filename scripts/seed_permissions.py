"""Seed the rights catalog (and legacy group assignments) from ``data/Groups.txt``.

Resolves docs/users/groups_backend_devreport.md gaps #1 & #2 at the data level:

  1. Parse the legacy Denticon export (13 groups, each with its granted rights, one
     per line, plus an "Overall Available" trailer we ignore — its labels are
     concatenated/truncated).
  2. Seed the GLOBAL ``permissions`` catalog = the de-duplicated union of every
     right label, with a stable slug ``code`` (matches the frontend) and a
     ``category`` (the leading "X - …" segment).
  3. (default) Seed the 13 legacy groups + their right assignments into a tenant,
     mapping to groups that already exist there by name (case-insensitive, with a
     small alias for the "Office Manger" typo). Creates missing groups.

Idempotent: permissions upsert by ``code``; group rights are reconciled to exactly
the legacy set each run. Only the 13 legacy-named groups are touched.

    python -m scripts.seed_permissions                 # catalog + groups into tenant 1
    python -m scripts.seed_permissions --tenant 3      # groups into tenant 3
    python -m scripts.seed_permissions --catalog-only  # only the global catalog
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from sqlalchemy import select

from app.db.models import Permission, UserGroup, UserGroupRight
from app.db.session import SessionLocal

_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "Groups.txt"
_MARKER = "This Group has the following rights"
# Legacy export typos -> the canonical group name already used in the app.
_NAME_ALIASES = {"office manger": "Office Manager"}


def slugify(label: str) -> str:
    """Frontend-compatible code: lowercase, non-alphanumeric runs -> '_'."""
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")


def categorize(label: str) -> str:
    """Leading 'Category - …' segment; 'General' when there is no separator."""
    m = re.split(r"\s[-–]\s", label, maxsplit=1)
    if len(m) == 2:
        return m[0].strip()
    return "General"


def _parse_header(line: str) -> tuple[str, str | None]:
    s = line.strip()
    m = re.match(r"^(?P<name>.*?)\(?(?P<code>\d+)\)?\s*:-\s*$", s)
    if m:
        name = m.group("name").strip().rstrip("(").strip()
        return name, m.group("code")
    return s.rstrip(":- ").strip(), None


def parse_groups_file() -> list[tuple[str, str | None, list[str]]]:
    lines = _DATA_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    marks = [i for i, l in enumerate(lines) if l.strip() == _MARKER]
    overall = next((i for i, l in enumerate(lines) if l.strip().startswith("Overall Avaiable")), len(lines))

    def prev_nonblank(idx: int) -> int:
        j = idx - 1
        while j >= 0 and not lines[j].strip():
            j -= 1
        return j

    groups: list[tuple[str, str | None, list[str]]] = []
    for k, mk in enumerate(marks):
        name, code = _parse_header(lines[prev_nonblank(mk)])
        end = prev_nonblank(marks[k + 1]) if k + 1 < len(marks) else overall
        rights = [l.strip() for l in lines[mk + 1:end] if l.strip()]
        # de-dupe within a group, preserve order
        seen: set[str] = set()
        rights = [r for r in rights if not (r in seen or seen.add(r))]
        groups.append((name, code, rights))
    return groups


def seed_catalog(db, groups) -> dict[str, int]:
    """Upsert the global permissions catalog. Returns {code: permission_id}."""
    labels: dict[str, str] = {}  # code -> label (first label wins)
    for _, _, rights in groups:
        for label in rights:
            labels.setdefault(slugify(label), label)

    existing = {p.code: p for p in db.execute(select(Permission)).scalars()}
    created = updated = 0
    for code, label in labels.items():
        cat = categorize(label)
        row = existing.get(code)
        if row is None:
            db.add(Permission(code=code, label=label, category=cat, is_active=True))
            created += 1
        elif row.label != label or row.category != cat or not row.is_active:
            row.label, row.category, row.is_active = label, cat, True
            updated += 1
    db.commit()
    print(f"catalog: {len(labels)} distinct rights ({created} created, {updated} updated)")
    return {p.code: p.id for p in db.execute(select(Permission)).scalars()}


def seed_groups(db, groups, tenant_id: int, id_by_code: dict[str, int]) -> None:
    existing = {
        g.name.strip().lower(): g
        for g in db.execute(select(UserGroup).where(UserGroup.tenant_id == tenant_id)).scalars()
    }
    for name, code, rights in groups:
        canonical = _NAME_ALIASES.get(name.strip().lower(), name)
        group = existing.get(canonical.strip().lower())
        action = "matched"
        if group is None:
            group = UserGroup(tenant_id=tenant_id, name=canonical, is_active=True)
            db.add(group)
            db.flush()
            existing[canonical.strip().lower()] = group
            action = "created"

        want_ids = {id_by_code[slugify(r)] for r in rights if slugify(r) in id_by_code}
        have = {
            row.permission_id: row
            for row in db.execute(
                select(UserGroupRight).where(UserGroupRight.group_id == group.id)
            ).scalars()
        }
        for pid, row in have.items():
            if pid not in want_ids:
                db.delete(row)
        for pid in want_ids - have.keys():
            db.add(UserGroupRight(tenant_id=tenant_id, group_id=group.id, permission_id=pid))
        db.commit()
        print(f"  [{action}] {canonical!r} (legacy code {code}) -> {len(want_ids)} rights")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tenant", type=int, default=1, help="tenant for legacy group seeding (default 1)")
    ap.add_argument("--catalog-only", action="store_true", help="seed only the global catalog")
    args = ap.parse_args()

    groups = parse_groups_file()
    print(f"parsed {len(groups)} legacy groups from {_DATA_FILE.name}")
    db = SessionLocal()
    try:
        id_by_code = seed_catalog(db, groups)
        if not args.catalog_only:
            print(f"seeding legacy groups into tenant {args.tenant}:")
            seed_groups(db, groups, args.tenant, id_by_code)
    finally:
        db.close()


if __name__ == "__main__":
    main()
