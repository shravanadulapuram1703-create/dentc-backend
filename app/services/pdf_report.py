"""Shared scaffolding for the server-rendered patient reports (PRINT-1).

The frontend's ``src/features/print/patientPdf.ts`` builds every patient-screen
print from the same five primitives — an office / patient header, a navy
section bar, a label/value table, a blue-headed data grid and a wrapped
paragraph — stamped with ``Page x of y``. This module is the reportlab twin of
that file, so a report produced here lays out like the one the browser used to
build, and the four ``*Print.ts`` builders can collapse to ``window.open(url)``.

reportlab is imported lazily (as the statement / contract renderers do) so the
API boots without it; only the report endpoints pay for the import.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

# Palette — the same values as patientPdf.ts (NAVY / BLUE / GRID_LINE …).
_NAVY = (31, 58, 95)
_BLUE = (58, 110, 165)
_GRID = (200, 206, 214)
_LABEL_TEXT = (71, 85, 105)
_LABEL_FILL = (248, 250, 252)
_FOOT_FILL = (241, 245, 249)
_MUTED = (110, 110, 110)
_RED = (220, 38, 38)

MARGIN = 36  # pt, as the FE


def _rl():  # noqa: ANN202
    """Lazy reportlab import so the rest of the API never pays for it."""
    try:
        from reportlab.lib import colors  # noqa: PLC0415
        from reportlab.lib.pagesizes import LETTER, landscape  # noqa: PLC0415
        from reportlab.lib.styles import ParagraphStyle  # noqa: PLC0415
        from reportlab.pdfgen import canvas  # noqa: PLC0415
        from reportlab.platypus import (  # noqa: PLC0415
            BaseDocTemplate,
            Frame,
            FrameBreak,
            KeepTogether,
            NextPageTemplate,
            PageTemplate,
            Paragraph,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError(
            "PDF rendering requires the 'reportlab' package (pip install -r requirements.txt)."
        ) from exc
    return {
        "colors": colors, "LETTER": LETTER, "landscape": landscape,
        "ParagraphStyle": ParagraphStyle, "canvas": canvas,
        "BaseDocTemplate": BaseDocTemplate, "Frame": Frame, "FrameBreak": FrameBreak,
        "KeepTogether": KeepTogether,
        "NextPageTemplate": NextPageTemplate, "PageTemplate": PageTemplate,
        "Paragraph": Paragraph, "Spacer": Spacer, "Table": Table, "TableStyle": TableStyle,
    }


# ── value formatting (the FE's format.ts / accountLedgerModel.ts twins) ───────
def cell(value: Any, dash: str = "-") -> str:  # noqa: ANN401
    """Blank-safe cell text."""
    if value is None:
        return dash
    text = str(value).strip()
    return text or dash


def money(value: Any, dash: str | None = None) -> str:  # noqa: ANN401
    """``$1,234.56`` / ``$-74.00``; ``dash`` (when given) for a blank value."""
    if value is None or value == "":
        return dash if dash is not None else "$0.00"
    try:
        amount = Decimal(str(value))
    except Exception:  # noqa: BLE001
        return str(value)
    sign = "-" if amount < 0 else ""
    return f"${sign}{abs(amount):,.2f}"


def money_or_dash(value: Any) -> str:  # noqa: ANN401
    return money(value, dash="-")


def fmt_date(value: Any) -> str:  # noqa: ANN401
    """``MM/DD/YYYY``; ``-`` when blank. Accepts date/datetime/ISO strings."""
    if value is None or value == "":
        return "-"
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.strftime("%m/%d/%Y")
    text = str(value)
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return f"{text[5:7]}/{text[8:10]}/{text[0:4]}"
    return text


def fmt_time(value: Any) -> str:  # noqa: ANN401
    """``h:mm AM``; ``-`` when blank."""
    if value is None or value == "":
        return "-"
    if isinstance(value, datetime):
        value = value.time()
    if hasattr(value, "strftime"):
        return value.strftime("%I:%M %p").lstrip("0")
    text = str(value)
    try:
        parsed = datetime.strptime(text[:5], "%H:%M")
    except ValueError:
        return text
    return parsed.strftime("%I:%M %p").lstrip("0")


def age_from_dob(dob: date | None, today: date | None = None) -> int | None:
    if dob is None:
        return None
    today = today or date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def sex_word(gender: str | None) -> str:
    g = (gender or "").strip().upper()
    return {"M": "Male", "F": "Female", "O": "Other"}.get(g[:1], g or "-")


def sex_letter(gender: str | None) -> str:
    g = (gender or "").strip().upper()
    return g[:1] if g else "-"


def _rgb(colors, triple):  # noqa: ANN001, ANN202
    r, g, b = triple
    return colors.Color(r / 255, g / 255, b / 255)


# Minimum room (pt) a section bar needs below it — the FE's ``ensureSpace(60)``.
_MIN_KEEP = 60


def _section_class(rl):  # noqa: ANN001, ANN202
    """``KeepTogether`` moves the whole group to a new page whenever it does not
    fit in the space left — which for a 120-row grid leaves the previous page
    nearly blank. This variant breaks only when the group *would* fit on a fresh
    page, or when the bar would otherwise be orphaned at the bottom edge; a
    grid taller than a page just flows and splits like any other table."""
    KeepTogether, FrameBreak = rl["KeepTogether"], rl["FrameBreak"]

    class _Section(KeepTogether):  # type: ignore[misc, valid-type]
        def split(self, aW, aH):  # noqa: N803
            if getattr(self, "_wrapInfo", None) != (aW, aH):
                self.wrap(aW, aH)
            content = self._content[:]
            frame = getattr(self, "_frame", None)
            at_top = bool(getattr(frame, "_atTop", False)) if frame else False
            frame_h = frame._height if frame else aH
            if self._H <= aH or at_top:
                return content
            if self._H <= frame_h or aH < _MIN_KEEP:
                return [FrameBreak(), *content]
            return content

    return _Section


# ── the document ──────────────────────────────────────────────────────────────
@dataclass
class ReportHeader:
    """What ``openPatientPdf()`` draws at the top of every report."""

    title: str
    office_name: str
    office_address: str | None = None
    office_phone: str | None = None
    patient_name: str = ""
    patient_id: int | str = ""
    chart_no: str | None = None
    dob: str | None = None
    extra: list[tuple[str, str]] = field(default_factory=list)
    logo_path: str | None = None
    photo_path: str | None = None
    printed_at: str | None = None
    # LAB-4: an office-wide report (Lab Report / Lab Cost Report) has no
    # patient — skip the "Patient: ... ID: ..." line, keep ``extra``.
    show_patient: bool = True


class PatientReport:
    """A flowable story with the FE's five primitives and a ``Page x of y`` footer."""

    def __init__(self, header: ReportHeader, *, landscape: bool = False) -> None:
        self._rl = _rl()
        rl = self._rl
        self._section = _section_class(rl)
        self.header = header
        self.pagesize = rl["landscape"](rl["LETTER"]) if landscape else rl["LETTER"]
        self.page_width, self.page_height = self.pagesize
        self.width = self.page_width - MARGIN * 2
        self.story: list = []
        self._pending_title: Any = None
        colors = rl["colors"]
        PS = rl["ParagraphStyle"]
        self._styles = {
            "cell": PS("cell", fontName="Helvetica", fontSize=8, leading=9.5),
            "cell_bold": PS("cell_bold", fontName="Helvetica-Bold", fontSize=8, leading=9.5),
            "label": PS("label", fontName="Helvetica-Bold", fontSize=8.5, leading=10,
                        textColor=_rgb(colors, _LABEL_TEXT)),
            "value": PS("value", fontName="Helvetica", fontSize=8.5, leading=10),
            "para": PS("para", fontName="Helvetica", fontSize=8.5, leading=10.5),
            "para_label": PS("para_label", fontName="Helvetica-Bold", fontSize=8.5, leading=11,
                             textColor=_rgb(colors, _LABEL_TEXT)),
            "empty": PS("empty", fontName="Helvetica-Oblique", fontSize=8.5, leading=10.5,
                        textColor=_rgb(colors, _MUTED)),
            "notice": PS("notice", fontName="Helvetica-Oblique", fontSize=8, leading=10,
                         textColor=colors.Color(146 / 255, 64 / 255, 14 / 255)),
            "head": PS("head", fontName="Helvetica-Bold", fontSize=7.5, leading=9,
                       textColor=colors.white),
            "card_title": PS("card_title", fontName="Helvetica-Bold", fontSize=8, leading=10,
                             textColor=_rgb(colors, _NAVY)),
        }
        # Header geometry: the first page carries the full office/patient block;
        # later pages a one-line strip, exactly as the FE continues at y=48.
        self._first_header_height = self._measure_first_header()
        self._later_header_height = 30

    # ── header measurement / drawing ─────────────────────────────────────────
    def _measure_first_header(self) -> int:
        h = self.header
        y = 58
        if h.office_address:
            y += 12
        if h.office_phone:
            y += 12
        y = max(y, 66)  # rule
        y += 14  # patient line
        if h.show_patient:
            y += 13
        y += 13 * len(h.extra)
        if h.logo_path or h.photo_path:
            y = max(y, 96)
        return y + 6

    def _draw_first_header(self, canv, doc) -> None:  # noqa: ANN001
        rl, h = self._rl, self.header
        colors = rl["colors"]
        top = self.page_height
        left = MARGIN
        right = self.page_width - MARGIN

        text_left = left
        if h.logo_path and Path(h.logo_path).is_file():
            try:
                canv.drawImage(h.logo_path, left, top - 80, width=90, height=44,
                               preserveAspectRatio=True, anchor="nw", mask="auto")
                text_left = left + 98
            except Exception:  # noqa: BLE001 - a corrupt logo must not sink the report
                text_left = left

        canv.setFillColor(colors.black)
        canv.setFont("Helvetica-Bold", 14)
        canv.drawString(text_left, top - 44, h.office_name or "Dental Practice")
        canv.setFont("Helvetica", 9)
        canv.setFillColor(colors.Color(80 / 255, 80 / 255, 80 / 255))
        y = 58
        if h.office_address:
            canv.drawString(text_left, top - y, h.office_address)
            y += 12
        if h.office_phone:
            canv.drawString(text_left, top - y, h.office_phone)
            y += 12

        canv.setFillColor(colors.black)
        canv.setFont("Helvetica-Bold", 12)
        canv.drawRightString(right, top - 44, h.title.upper())
        canv.setFont("Helvetica", 9)
        canv.setFillColor(colors.Color(80 / 255, 80 / 255, 80 / 255))
        printed = h.printed_at or datetime.now(timezone.utc).strftime("%m/%d/%Y %I:%M %p UTC")
        canv.drawRightString(right, top - 58, f"Printed {printed}")
        canv.setFillColor(colors.black)

        y = max(y, 66)
        canv.setStrokeColor(_rgb(colors, _NAVY))
        canv.setLineWidth(1)
        canv.line(left, top - y, right, top - y)
        y += 14

        canv.setFont("Helvetica", 9)
        if h.show_patient:
            parts = [f"Patient: {h.patient_name}", f"ID: {h.patient_id}"]
            if h.chart_no:
                parts.append(f"Chart: {h.chart_no}")
            if h.dob:
                parts.append(f"DOB: {h.dob}")
            canv.drawString(left, top - y, "    ".join(parts))
            y += 13
        for label, value in h.extra:
            canv.drawString(left, top - y, f"{label}: {value}")
            y += 13

        if h.photo_path and Path(h.photo_path).is_file():
            try:
                canv.drawImage(h.photo_path, right - 64, top - y - 4, width=64, height=64,
                               preserveAspectRatio=True, anchor="ne", mask="auto")
            except Exception:  # noqa: BLE001
                pass

        self._draw_footer(canv, doc)

    def _draw_later_header(self, canv, doc) -> None:  # noqa: ANN001
        rl, h = self._rl, self.header
        colors = rl["colors"]
        top = self.page_height
        canv.setFont("Helvetica", 8)
        canv.setFillColor(colors.Color(80 / 255, 80 / 255, 80 / 255))
        canv.drawString(MARGIN, top - 22, f"{h.title}  ·  {h.patient_name}  (ID {h.patient_id})")
        canv.drawRightString(self.page_width - MARGIN, top - 22, h.office_name or "")
        canv.setFillColor(colors.black)
        self._draw_footer(canv, doc)

    def _draw_footer(self, canv, doc) -> None:  # noqa: ANN001, ARG002
        # The page total is stamped by the numbered canvas at save time.
        pass

    # ── primitives ───────────────────────────────────────────────────────────
    def _p(self, text: Any, style: str = "cell"):  # noqa: ANN401, ANN202
        return self._rl["Paragraph"](escape(str(text)).replace("\n", "<br/>"), self._styles[style])

    def _emit(self, flowable) -> None:  # noqa: ANN001
        """Append a flowable, gluing a pending section bar to it so a heading is
        never orphaned at the bottom of a page (the FE's ``ensureSpace``)."""
        if self._pending_title is not None:
            bar = self._pending_title
            self._pending_title = None
            self.story.append(self._section([bar, self._rl["Spacer"](1, 2), flowable]))
        else:
            self.story.append(flowable)

    def section_title(self, title: str) -> None:
        """Navy bar with white uppercase text."""
        rl = self._rl
        colors = rl["colors"]
        bar = rl["Table"]([[self._p(title.upper(), "head")]], colWidths=[self.width], rowHeights=[16])
        bar.setStyle(rl["TableStyle"]([
            ("BACKGROUND", (0, 0), (-1, -1), _rgb(colors, _NAVY)),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        if self._pending_title is not None:  # two bars in a row: flush the first
            self.story.append(self._pending_title)
        self.story.append(rl["Spacer"](1, 4))
        self._pending_title = bar

    def key_value_table(self, rows: list[list[str]]) -> None:
        """Label / value pairs — 2-column ``[label, value]`` or 4-column rows."""
        if not rows:
            return
        rl = self._rl
        colors = rl["colors"]
        four = any(len(r) > 2 for r in rows)
        if four:
            label_w, value_w = self.width * 0.17, self.width * 0.33
            col_widths = [label_w, value_w, label_w, value_w]
        else:
            col_widths = [self.width * 0.3, self.width * 0.7]
        data = []
        spans = []
        for i, r in enumerate(rows):
            r = [c if c is not None else "" for c in r]
            if four and len(r) == 2:
                data.append([self._p(r[0], "label"), self._p(r[1], "value"), "", ""])
                spans.append(("SPAN", (1, i), (3, i)))
            elif four:
                data.append([self._p(r[0], "label"), self._p(r[1], "value"),
                             self._p(r[2], "label"), self._p(r[3], "value")])
            else:
                data.append([self._p(r[0], "label"), self._p(r[1], "value")])
        table = rl["Table"](data, colWidths=col_widths, repeatRows=0)
        style = [
            ("GRID", (0, 0), (-1, -1), 0.5, _rgb(colors, _GRID)),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("BACKGROUND", (0, 0), (0, -1), _rgb(colors, _LABEL_FILL)),
        ]
        if four:
            style.append(("BACKGROUND", (2, 0), (2, -1), _rgb(colors, _LABEL_FILL)))
        table.setStyle(rl["TableStyle"](style + spans))
        self._emit(table)
        self.story.append(rl["Spacer"](1, 10))

    def data_table(
        self,
        head: list[str],
        body: list[list[Any]],
        *,
        right: tuple[int, ...] = (),
        center: tuple[int, ...] = (),
        widths: dict[int, float] | None = None,
        font_size: float = 8,
        foot: list[Any] | None = None,
        foot_span: int = 0,
        empty: str = "No records.",
        bold_first_col: bool = False,
    ) -> None:
        """Column grid with a blue header row — one per on-screen DataGrid.

        ``foot`` is an optional bold totals row; ``foot_span`` merges its first
        N cells (the FE's ``colSpan``)."""
        rl = self._rl
        colors = rl["colors"]
        if not body:
            self._emit(self._p(empty, "empty"))
            self.story.append(rl["Spacer"](1, 10))
            return

        n = len(head)
        widths = widths or {}
        fixed = sum(w for i, w in widths.items() if i < n)
        free = [i for i in range(n) if i not in widths]
        share = (self.width - fixed) / len(free) if free else 0
        col_widths = [widths.get(i, share) for i in range(n)]

        PS = rl["ParagraphStyle"]
        cell_style = PS("dt_cell", fontName="Helvetica", fontSize=font_size, leading=font_size + 1.5)
        bold_style = PS("dt_bold", fontName="Helvetica-Bold", fontSize=font_size,
                        leading=font_size + 1.5)
        head_style = PS("dt_head", fontName="Helvetica-Bold", fontSize=max(font_size - 0.5, 6),
                        leading=font_size + 1, textColor=colors.white)
        def wrap(value, style):  # noqa: ANN001, ANN202
            text = "" if value is None else str(value)
            return rl["Paragraph"](escape(text).replace("\n", "<br/>"), style)

        data = [[wrap(h, head_style) for h in head]]
        for row in body:
            cells = []
            for i in range(n):
                v = row[i] if i < len(row) else ""
                cells.append(wrap(v, bold_style if (bold_first_col and i == 0) else cell_style))
            data.append(cells)
        style = [
            ("GRID", (0, 0), (-1, -1), 0.5, _rgb(colors, _GRID)),
            ("BACKGROUND", (0, 0), (-1, 0), _rgb(colors, _BLUE)),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 2.5), ("RIGHTPADDING", (0, 0), (-1, -1), 2.5),
        ]
        if bold_first_col:
            style.append(("BACKGROUND", (0, 1), (0, -1), _rgb(colors, _LABEL_FILL)))
        if foot:
            foot_cells = [wrap(foot[i] if i < len(foot) else "", bold_style) for i in range(n)]
            data.append(foot_cells)
            style.append(("BACKGROUND", (0, -1), (-1, -1), _rgb(colors, _FOOT_FILL)))
            if foot_span > 1:
                style.append(("SPAN", (0, -1), (foot_span - 1, -1)))
        # Paragraph alignment follows the paragraph style, so build aligned twins.
        right_style = PS("dt_right", parent=cell_style, alignment=2)
        center_style = PS("dt_center", parent=cell_style, alignment=1)
        right_bold = PS("dt_right_b", parent=bold_style, alignment=2)
        head_right = PS("dt_head_r", parent=head_style, alignment=2)
        head_center = PS("dt_head_c", parent=head_style, alignment=1)
        last_body = len(data) - (2 if foot else 1)
        for i in right:
            if i >= n:
                continue
            data[0][i] = wrap(head[i], head_right)
            for r in range(1, last_body + 1):
                data[r][i] = wrap(body[r - 1][i] if i < len(body[r - 1]) else "", right_style)
            if foot:
                data[-1][i] = wrap(foot[i] if i < len(foot) else "", right_bold)
        for i in center:
            if i >= n:
                continue
            data[0][i] = wrap(head[i], head_center)
            for r in range(1, last_body + 1):
                data[r][i] = wrap(body[r - 1][i] if i < len(body[r - 1]) else "", center_style)

        table = rl["Table"](data, colWidths=col_widths, repeatRows=1)
        table.hAlign = "LEFT"  # a grid narrower than the page sits under the bar, as on screen
        table.setStyle(rl["TableStyle"](style))
        self._emit(table)
        self.story.append(rl["Spacer"](1, 10))

    def paragraph(self, label: str, text: str | None, *, red: bool = False) -> None:
        """A labelled block of wrapped text (notes, alerts)."""
        rl = self._rl
        colors = rl["colors"]
        body = (text or "").strip() or "-"
        parts = []
        if label:
            parts.append(self._p(label, "para_label"))
        style = self._styles["para"]
        if red:
            style = rl["ParagraphStyle"]("para_red", parent=style, textColor=_rgb(colors, _RED))
        parts.append(rl["Paragraph"](escape(body).replace("\n", "<br/>"), style))
        self._emit(self._section(parts))
        self.story.append(rl["Spacer"](1, 8))

    def notice(self, text: str) -> None:
        """An amber italic line (the FE's truncation banner)."""
        self._emit(self._p(text, "notice"))
        self.story.append(self._rl["Spacer"](1, 4))

    def cards(self, cards: list[tuple[str, list[tuple[str, str]]]]) -> None:
        """N label/value cards side by side (the ledger CONTRACTS tab)."""
        if not cards:
            return
        rl = self._rl
        colors = rl["colors"]
        gap = 12
        card_w = (self.width - gap * (len(cards) - 1)) / len(cards)
        cells = []
        for title, rows in cards:
            inner = rl["Table"](
                [[self._p(k, "label"), self._p(v, "value")] for k, v in rows],
                colWidths=[card_w * 0.55, card_w * 0.45],
            )
            inner.setStyle(rl["TableStyle"]([
                ("GRID", (0, 0), (-1, -1), 0.5, _rgb(colors, _GRID)),
                ("BACKGROUND", (0, 0), (0, -1), _rgb(colors, _LABEL_FILL)),
                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ]))
            cells.append([self._p(title.upper(), "card_title"), inner])
        # Transpose: one outer row of titles, one outer row of inner tables.
        outer = rl["Table"](
            [[c[0] for c in cells], [c[1] for c in cells]],
            colWidths=[card_w] * len(cards),
        )
        outer.hAlign = "LEFT"
        outer.setStyle(rl["TableStyle"]([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), gap),
            ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        self._emit(outer)
        self.story.append(rl["Spacer"](1, 10))

    # ── build ────────────────────────────────────────────────────────────────
    def render(self) -> bytes:
        rl = self._rl
        if self._pending_title is not None:
            self.story.append(self._pending_title)
            self._pending_title = None
        # A trailing spacer that does not fit forces an empty last page.
        while self.story and isinstance(self.story[-1], rl["Spacer"]):
            self.story.pop()
        if not self.story:
            self.story.append(rl["Spacer"](1, 1))

        buf = io.BytesIO()
        first_top = self._first_header_height
        later_top = self._later_header_height
        bottom = 40
        frame_first = rl["Frame"](
            MARGIN, bottom, self.width, self.page_height - bottom - first_top,
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="first",
        )
        frame_later = rl["Frame"](
            MARGIN, bottom, self.width, self.page_height - bottom - later_top,
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="later",
        )
        doc = rl["BaseDocTemplate"](
            buf, pagesize=self.pagesize,
            leftMargin=MARGIN, rightMargin=MARGIN, topMargin=first_top, bottomMargin=bottom,
            title=f"{self.header.title} - {self.header.patient_name}",
            author=self.header.office_name or "",
        )
        doc.addPageTemplates([
            rl["PageTemplate"](id="first", frames=[frame_first], onPage=self._draw_first_header),
            rl["PageTemplate"](id="later", frames=[frame_later], onPage=self._draw_later_header),
        ])
        story = [rl["NextPageTemplate"]("later"), *self.story]

        page_width, margin = self.page_width, MARGIN
        base_canvas = rl["canvas"].Canvas

        class _NumberedCanvas(base_canvas):  # type: ignore[misc, valid-type]
            """Two-pass ``Page x of y`` (the FE stamps it after building)."""

            def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
                super().__init__(*args, **kwargs)
                self._saved_states: list[dict] = []

            def showPage(self) -> None:  # noqa: N802
                self._saved_states.append(dict(self.__dict__))
                self._startPage()

            def save(self) -> None:
                total = len(self._saved_states)
                for state in self._saved_states:
                    self.__dict__.update(state)
                    self.setFont("Helvetica", 7.5)
                    self.setFillGray(0.47)
                    self.drawRightString(page_width - margin, 20, f"Page {self._pageNumber} of {total}")
                    base_canvas.showPage(self)
                base_canvas.save(self)

        doc.build(story, canvasmaker=_NumberedCanvas)
        return buf.getvalue()
