"""ADA Dental Claim Form (2024) — the PDF (ADA-BE-1).

Renders the dict ``claim_form_service.assemble`` produces onto US Letter with
reportlab's canvas (imported lazily, as every other PDF renderer here does).
Two modes, one layout:

* ``form``    — the whole form is drawn: section bands, item boxes, captions
                and the values. For plain paper.
* ``overlay`` — only the values, at the same coordinates, so the practice can
                feed pre-printed ADA stock. ``offset_x`` / ``offset_y`` (pt)
                shift the whole page for printer calibration.

Rule E of the completion instructions: one form holds ten service lines, so a
claim with more lines is rendered as N complete forms, each with its own Item
32 total (the other fees of Item 31a land on the last one) and a
``Page x of y`` footer. A batch call renders many claims into one document.

The layout is a fixed grid (``ROW`` pt per row, two columns) rather than a
pixel copy of the ADA artwork — the data content, item numbering, order and
captions are the ADA's, so a payer reading it by item number finds every value
where the instructions say it is.
"""

from __future__ import annotations

import io
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from app.services.claim_form_service import FORM_VERSION, LINES_PER_PAGE, PERMANENT_TEETH
from app.services.pdf_report import fmt_date, money

PAGE_W, PAGE_H = 612.0, 792.0
MARGIN = 22.0
INNER_W = PAGE_W - 2 * MARGIN
MID = MARGIN + INNER_W / 2
ROW = 15.0
BAND = 11.0
_NAVY = (0.12, 0.23, 0.37)
_GREY = (0.55, 0.55, 0.55)
_LIGHT = (0.93, 0.95, 0.97)


def _rl():  # noqa: ANN202
    try:
        from reportlab.lib.pagesizes import LETTER  # noqa: PLC0415
        from reportlab.pdfbase.pdfmetrics import stringWidth  # noqa: PLC0415
        from reportlab.pdfgen import canvas  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError(
            "PDF rendering requires the 'reportlab' package (pip install -r requirements.txt)."
        ) from exc
    return canvas, LETTER, stringWidth


def _s(value: Any) -> str:  # noqa: ANN401
    if value is None:
        return ""
    if isinstance(value, bool):
        return "X" if value else ""
    if isinstance(value, (date, datetime)):
        return fmt_date(value)
    if isinstance(value, Decimal):
        return money(value)
    return str(value)


def _addr(block: dict[str, Any]) -> tuple[str, str]:
    line1 = " ".join(v for v in (block.get("address_line1"), block.get("address_line2")) if v)
    csz = ", ".join(v for v in (block.get("city"), block.get("state")) if v)
    if block.get("zip"):
        csz = f"{csz} {block['zip']}".strip()
    return line1, csz


def _name(block: dict[str, Any] | None) -> str:
    if not block:
        return ""
    parts = [block.get("last_name") or "", block.get("first_name") or ""]
    text = ", ".join(p for p in parts if p)
    if block.get("middle_initial"):
        text = f"{text} {block['middle_initial']}"
    if block.get("suffix"):
        text = f"{text} {block['suffix']}"
    return text.strip()


class _Page:
    """One physical page: draws captions/boxes only in form mode, values always."""

    def __init__(self, canv, mode: str, string_width) -> None:  # noqa: ANN001
        self.c = canv
        self.form = mode == "form"
        self.sw = string_width

    # primitives ------------------------------------------------------------
    def band(self, y: float, title: str) -> None:
        if not self.form:
            return
        self.c.setFillColorRGB(*_NAVY)
        self.c.rect(MARGIN, y - BAND, INNER_W, BAND, stroke=0, fill=1)
        self.c.setFillColorRGB(1, 1, 1)
        self.c.setFont("Helvetica-Bold", 7)
        self.c.drawString(MARGIN + 3, y - BAND + 3, title)
        self.c.setFillColorRGB(0, 0, 0)

    def fit(self, text: str, width: float, size: float) -> str:
        if self.sw(text, "Helvetica", size) <= width:
            return text
        while text and self.sw(text + "…", "Helvetica", size) > width:
            text = text[:-1]
        return text + "…" if text else ""

    def field(self, x: float, y: float, w: float, item: str, label: str, value: Any,  # noqa: ANN401
              *, h: float = ROW, checkbox: bool = False, bold: bool = False) -> None:
        """A captioned box whose value sits on the baseline. ``y`` is the top."""
        if self.form:
            self.c.setStrokeColorRGB(*_GREY)
            self.c.setLineWidth(0.4)
            self.c.rect(x, y - h, w, h, stroke=1, fill=0)
            self.c.setFillColorRGB(*_GREY)
            self.c.setFont("Helvetica", 4.6)
            self.c.drawString(x + 1.5, y - 5.2, self.fit(f"{item}. {label}" if item else label, w - 3, 4.6))
            self.c.setFillColorRGB(0, 0, 0)
        if checkbox:
            bx, by = x + 3, y - h + 3
            if self.form:
                self.c.rect(bx, by, 6, 6, stroke=1, fill=0)
            if value:
                self.c.setFont("Helvetica-Bold", 7)
                self.c.drawString(bx + 1, by + 0.8, "X")
            return
        text = _s(value)
        if text:
            self.c.setFont("Helvetica-Bold" if bold else "Helvetica", 7.2)
            self.c.drawString(x + 3, y - h + 3.4, self.fit(text, w - 5, 7.2))

    def text(self, x: float, y: float, text: str, size: float = 7, bold: bool = False) -> None:
        self.c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        self.c.drawString(x, y, text)

    def image(self, x: float, y: float, w: float, h: float, data_url: str | None) -> bool:
        """SIG-16: a captured signature (data-URL JPEG/PNG) fitted into ``w``×``h``
        with the aspect ratio kept. False (nothing drawn) on any decode failure —
        a bad image must not kill a claim print."""
        if not data_url:
            return False
        try:
            import base64
            import io as _io

            from reportlab.lib.utils import ImageReader

            payload = data_url.split(",", 1)[1] if data_url.startswith("data:") else data_url
            reader = ImageReader(_io.BytesIO(base64.b64decode(payload)))
            self.c.drawImage(reader, x, y, width=w, height=h, preserveAspectRatio=True,
                             anchor="sw", mask="auto")
            return True
        except Exception:  # noqa: BLE001
            return False


def _sig_date(slot: dict[str, Any] | None) -> str:
    if not slot or not slot.get("signed_at"):
        return ""
    value = slot["signed_at"]
    return value.strftime("%m/%d/%Y") if hasattr(value, "strftime") else _s(value)[:10]


def _draw_form(page: _Page, form: dict[str, Any], lines: list[dict[str, Any]], page_no: int,
               last_page: bool, printed_at: str) -> None:
    c = page.c
    y = PAGE_H - MARGIN
    # ── title ─────────────────────────────────────────────────────────────
    if page.form:
        page.text(MARGIN, y - 10, "ADA Dental Claim Form", 12, bold=True)
        page.text(PAGE_W - MARGIN - 150, y - 10, f"Version {FORM_VERSION} · {form.get('claim_number') or ''}", 6.5)
    y -= 16
    # ── header information ────────────────────────────────────────────────
    page.band(y, "HEADER INFORMATION")
    y -= BAND
    hdr = form["header"]
    tt = hdr["transaction_type"]
    page.field(MARGIN, y, 62, "1", "Type of Transaction", None)
    page.field(MARGIN + 62, y, 96, "", "Statement of Actual Services", tt == "statement", checkbox=True)
    page.field(MARGIN + 158, y, 110, "", "Request for Predetermination", tt == "predetermination", checkbox=True)
    page.field(MARGIN + 268, y, 76, "", "EPSDT / Title XIX", tt == "epsdt", checkbox=True)
    page.field(MARGIN + 344, y, INNER_W - 344, "2", "Predetermination/Preauthorization Number",
               hdr.get("predetermination_number"))
    y -= ROW + 3
    # ── payer / other coverage ────────────────────────────────────────────
    page.band(y, "INSURANCE COMPANY / DENTAL BENEFIT PLAN INFORMATION            OTHER COVERAGE (Items 4–11)")
    y -= BAND
    payer = form["payer"]
    other = form["other_coverage"]
    osub = other.get("subscriber") or {}
    ocar = other.get("carrier") or {}
    lw = INNER_W / 2 - 4
    l1, l2 = _addr(payer)
    page.field(MARGIN, y, lw, "3", "Company / Plan Name, Address, City, State, Zip Code", payer.get("name"), bold=True)
    page.field(MID + 4, y, 70, "4", "Other Dental or Medical Coverage?", None)
    page.field(MID + 74, y, 36, "", "No", not other["has_other_coverage"], checkbox=True)
    page.field(MID + 110, y, 36, "", "Yes", other["has_other_coverage"], checkbox=True)
    page.field(MID + 146, y, lw - 146, "5", "Name of Policyholder/Subscriber in #4", _name(osub))
    y -= ROW
    page.field(MARGIN, y, lw, "", "Address", l1)
    page.field(MID + 4, y, 70, "6", "Date of Birth", osub.get("dob"))
    page.field(MID + 74, y, 36, "7", "Sex", osub.get("sex") if osub else None)
    page.field(MID + 110, y, lw - 110, "8", "Policyholder/Subscriber ID (SSN or ID#)", osub.get("member_id"))
    y -= ROW
    page.field(MARGIN, y, lw * 0.6, "", "City, State, Zip Code", l2)
    page.field(MARGIN + lw * 0.6, y, lw * 0.4, "3a", "Payer ID", payer.get("payer_id"))
    page.field(MID + 4, y, 90, "9", "Plan/Group Number", osub.get("group_number"))
    page.field(MID + 94, y, lw - 94, "10", "Patient's Relationship to Person Named in #5",
               (osub.get("relationship_code") or "").title() if osub else None)
    y -= ROW
    ol1, ol2 = _addr(ocar)
    page.field(MARGIN, y, lw, "", "", None, h=ROW)
    page.field(MID + 4, y, lw - 4, "11", "Other Insurance Company/Dental Benefit Plan Name, Address",
               " · ".join(v for v in (ocar.get("name"), ol1, ol2) if v))
    y -= ROW + 3
    # ── subscriber / patient ──────────────────────────────────────────────
    page.band(y, "POLICYHOLDER / SUBSCRIBER INFORMATION (Items 12–17)                   PATIENT INFORMATION (Items 18–23)")
    y -= BAND
    sub = form["subscriber"]
    pat = form["patient"]
    s1, s2 = _addr(sub)
    p1, p2 = _addr(pat)
    rel = pat["relationship_to_subscriber"]
    page.field(MARGIN, y, lw, "12", "Policyholder/Subscriber Name (Last, First, MI, Suffix), Address",
               _name(sub), bold=True)
    page.field(MID + 4, y, 34, "18", "Rel. to Subscriber", None)
    page.field(MID + 38, y, 34, "", "Self", rel == "self", checkbox=True)
    page.field(MID + 72, y, 36, "", "Spouse", rel == "spouse", checkbox=True)
    page.field(MID + 108, y, 46, "", "Dependent", rel == "dependent", checkbox=True)
    page.field(MID + 154, y, 34, "", "Other", rel == "other", checkbox=True)
    page.field(MID + 188, y, lw - 188, "19", "Reserved For Future Use", None)
    y -= ROW
    page.field(MARGIN, y, lw, "", "Address", s1)
    page.field(MID + 4, y, lw - 4, "20", "Patient Name (Last, First, MI, Suffix), Address", _name(pat), bold=True)
    y -= ROW
    page.field(MARGIN, y, lw, "", "City, State, Zip Code", s2)
    page.field(MID + 4, y, lw - 4, "", "Address", p1)
    y -= ROW
    page.field(MARGIN, y, 80, "13", "Date of Birth", sub.get("dob"))
    page.field(MARGIN + 80, y, 30, "14", "Sex", sub.get("sex"))
    page.field(MARGIN + 110, y, lw - 110, "15", "Policyholder/Subscriber ID (SSN or ID#)", sub.get("member_id"))
    page.field(MID + 4, y, lw - 4, "", "City, State, Zip Code", p2)
    y -= ROW
    page.field(MARGIN, y, lw * 0.45, "16", "Plan/Group Number", sub.get("group_number"))
    page.field(MARGIN + lw * 0.45, y, lw * 0.55, "17", "Employer Name", sub.get("employer_name"))
    page.field(MID + 4, y, 80, "21", "Date of Birth", pat.get("dob"))
    page.field(MID + 84, y, 30, "22", "Sex", pat.get("sex"))
    page.field(MID + 114, y, lw - 114, "23", "Patient ID / Account # (Assigned by Dentist)",
               pat.get("chart_no") or pat.get("patient_id"))
    y -= ROW + 3
    # ── record of services ────────────────────────────────────────────────
    page.band(y, "RECORD OF SERVICES PROVIDED")
    y -= BAND
    cols = [
        ("24", "Procedure Date", 52), ("25", "Area of Oral Cavity", 34), ("26", "Tooth System", 30),
        ("27", "Tooth Number(s) or Letter(s)", 56), ("28", "Tooth Surface", 40), ("29", "Procedure Code", 44),
        ("29a", "Diag. Pointer", 34), ("29b", "Qty", 22), ("30", "Description", 0), ("31", "Fee", 52),
    ]
    fixed = sum(w for _i, _l, w in cols)
    widths = [w or (INNER_W - fixed) for _i, _l, w in cols]
    x = MARGIN
    if page.form:
        c.setFillColorRGB(*_LIGHT)
        c.rect(MARGIN, y - ROW, INNER_W, ROW, stroke=0, fill=1)
        c.setFillColorRGB(0, 0, 0)
    for (item, label, _w), w in zip(cols, widths):
        if page.form:
            c.setStrokeColorRGB(*_GREY)
            c.rect(x, y - ROW, w, ROW, stroke=1, fill=0)
            page.text(x + 2, y - ROW + 8.5, item, 5.5, bold=True)
            page.text(x + 2, y - ROW + 3, page.fit(label, w - 3, 4.6), 4.6)
        x += w
    y -= ROW
    line_h = 13.0
    page_total = Decimal("0")
    for i in range(LINES_PER_PAGE):
        line = lines[i] if i < len(lines) else None
        x = MARGIN
        values = [] if line is None else [
            line.get("date_of_service"), line.get("area_of_oral_cavity"), line.get("tooth_system"),
            line.get("tooth"), line.get("surface"), line.get("procedure_code"), line.get("diagnosis_pointers"),
            f"{int(line.get('quantity') or 1):02d}", line.get("description"), line.get("fee"),
        ]
        if line is not None:
            page_total += Decimal(str(line.get("fee") or 0))
        for n, w in enumerate(widths):
            if page.form:
                c.setStrokeColorRGB(*_GREY)
                c.rect(x, y - line_h, w, line_h, stroke=1, fill=0)
                if n == 0:
                    page.text(x + 1.5, y - line_h + 4, str(i + 1), 4.5)
            if line is not None:
                text = _s(values[n])
                if text:
                    page.text(x + (8 if n == 0 else 3), y - line_h + 4, page.fit(text, w - 6, 7), 7)
            x += w
        y -= line_h
    # ── missing teeth / diagnosis / remarks / totals ──────────────────────
    y -= 3
    missing = set(form["missing_teeth"]["teeth"])
    grid_w = INNER_W * 0.42
    cell_w = grid_w / 16
    page.field(MARGIN, y, grid_w, "33", "Missing Teeth Information (Place an 'X' on each missing tooth)", None,
               h=ROW * 2 + 6)
    top_row = PERMANENT_TEETH[:16]
    bottom_row = list(reversed(PERMANENT_TEETH[16:]))
    for r, row in enumerate((top_row, bottom_row)):
        ty = y - 8 - r * 13
        for k, tooth in enumerate(row):
            tx = MARGIN + 2 + k * cell_w
            if page.form:
                page.text(tx + 1, ty - 4, tooth, 4.2)
            if tooth in missing:
                page.text(tx + 2, ty - 11, "X", 7, bold=True)
    dx = MARGIN + grid_w
    dw = INNER_W - grid_w
    diag = form["diagnosis"]
    page.field(dx, y, 60, "34", "Diagnosis Code List Qualifier", diag.get("qualifier"))
    codes = diag.get("codes") or {}
    cw = (dw - 60 - 110) / 4
    for k, letter in enumerate("ABCD"):
        page.field(dx + 60 + k * cw, y, cw, "34a" if k == 0 else "", f"Diagnosis Code {letter}",
                   codes.get(letter))
    page.field(dx + dw - 110, y, 110, "31a", "Other Fee(s)",
               form["fees"].get("other_fees") if last_page else None)
    y -= ROW
    total = page_total + (Decimal(str(form["fees"].get("other_fees") or 0)) if last_page else Decimal("0"))
    page.field(dx, y, dw - 110, "35", "Remarks", form.get("remarks"), h=ROW + 6)
    page.field(dx + dw - 110, y, 110, "32", "Total Fee", total, h=ROW + 6, bold=True)
    y -= ROW + 6 + 3
    # ── authorizations / ancillary ────────────────────────────────────────
    page.band(y, "AUTHORIZATIONS (Items 36–37)                                            ANCILLARY CLAIM / TREATMENT INFORMATION (Items 38–47)")
    y -= BAND
    auth = form["authorizations"]
    anc = form["ancillary"]
    enc = anc.get("enclosures") or {}
    sigs = auth.get("signatures") or {}
    page.field(MARGIN, y, lw - 40, "36", "Patient/Guardian Signature — release of information", None, h=ROW * 2)
    page.field(MARGIN + lw - 40, y, 40, "", "On File", auth["signature_on_file"], checkbox=True, h=ROW * 2)
    # SIG-16: the captured image (208 × 14 pt) + capture date + guardian name;
    # "Signature on File" only when there is no image to print.
    s36 = sigs.get("item_36") or {}
    if page.image(MARGIN + 3, y - ROW * 2 + 2, min(208, lw - 120), min(14, ROW * 2 - 8), s36.get("signature_data")):
        caption = _sig_date(s36)
        if s36.get("signer_name"):
            caption = f"{s36['signer_name']} ({s36.get('signer_relationship') or 'guardian'})  {caption}"
        page.text(MARGIN + min(208, lw - 120) + 8, y - ROW * 2 + 4, caption, 6)
    elif auth["signature_on_file"]:
        page.text(MARGIN + 3, y - ROW * 2 + 4, "Signature on File", 7, bold=True)
    page.field(MID + 4, y, 66, "38", "Place of Treatment (POS)", anc.get("place_of_treatment"))
    page.field(MID + 70, y, 80, "39", "Enclosures (Y/N)", "Y" if enc.get("attachments_enclosed") else "N")
    page.field(MID + 150, y, lw - 150, "", "Radiographs / Oral Images / Models",
               f"{enc.get('radiographs', 0)} / {enc.get('oral_images', 0)} / {enc.get('models', 0)}")
    y -= ROW
    page.field(MID + 4, y, 96, "39a", "Date of Last SRP", anc.get("date_last_srp"))
    page.field(MID + 100, y, 56, "40", "Ortho Treatment?", None)
    page.field(MID + 156, y, 30, "", "No", not anc["is_ortho"], checkbox=True)
    page.field(MID + 186, y, 30, "", "Yes", anc["is_ortho"], checkbox=True)
    page.field(MID + 216, y, lw - 216, "41", "Date Appliance Placed", anc.get("ortho_appliance_date"))
    y -= ROW
    page.field(MARGIN, y, lw - 40, "37", "Subscriber Signature — assignment of benefits", None, h=ROW * 2)
    page.field(MARGIN + lw - 40, y, 40, "", "Assigned", auth["assignment_of_benefits"], checkbox=True, h=ROW * 2)
    s37 = sigs.get("item_37") or {}
    if page.image(MARGIN + 3, y - ROW * 2 + 2, min(208, lw - 120), min(17, ROW * 2 - 6), s37.get("signature_data")):
        page.text(MARGIN + min(208, lw - 120) + 8, y - ROW * 2 + 4, _sig_date(s37), 6)
    elif auth["assignment_of_benefits"]:
        page.text(MARGIN + 3, y - ROW * 2 + 4, "Signature on File", 7, bold=True)
    page.field(MID + 4, y, 60, "42", "Months of Treatment", anc.get("ortho_months_remaining"))
    page.field(MID + 64, y, 70, "43", "Replacement of Prosthesis?", None)
    page.field(MID + 134, y, 30, "", "No", not anc["prosthesis_replacement"], checkbox=True)
    page.field(MID + 164, y, 30, "", "Yes", anc["prosthesis_replacement"], checkbox=True)
    page.field(MID + 194, y, lw - 194, "44", "Date of Prior Placement", anc.get("prosthesis_prior_date"))
    y -= ROW
    acc = (anc.get("accident_type") or "")
    page.field(MID + 4, y, 60, "45", "Treatment Resulting From", None)
    page.field(MID + 64, y, 60, "", "Occupational", acc == "occupational", checkbox=True)
    page.field(MID + 124, y, 50, "", "Auto accident", acc == "auto", checkbox=True)
    page.field(MID + 174, y, 50, "", "Other accident", acc == "other", checkbox=True)
    page.field(MID + 224, y, 56, "46", "Date of Accident", anc.get("accident_date"))
    page.field(MID + 280, y, lw - 280, "47", "Auto Accident State", anc.get("accident_state"))
    y -= ROW + 3
    # ── billing / treating ────────────────────────────────────────────────
    page.band(y, "BILLING DENTIST OR DENTAL ENTITY (Items 48–52a)                    TREATING DENTIST AND TREATMENT LOCATION (Items 53–58)")
    y -= BAND
    bill = form["billing"]
    tr = form["treating"]
    b1, b2 = _addr(bill)
    t1, t2 = _addr(tr.get("location") or {})
    page.field(MARGIN, y, lw, "48", "Name, Address, City, State, Zip Code", bill.get("name"), bold=True)
    page.field(MID + 4, y, lw - 4, "53", "Treating Dentist (I hereby certify …)",
               tr.get("name"), bold=True)
    y -= ROW
    page.field(MARGIN, y, lw, "", "Address", b1)
    page.field(MID + 4, y, 100, "53a", "Locum Tenens Dentist", None)
    page.field(MID + 104, y, 30, "", "No", not tr["is_locum_tenens"], checkbox=True)
    page.field(MID + 134, y, 30, "", "Yes", tr["is_locum_tenens"], checkbox=True)
    s53 = (form["authorizations"].get("signatures") or {}).get("item_53") or {}
    page.field(MID + 164, y, lw - 164, "", "Signed (Treating Dentist) / Date", None)
    # SIG-16: 78 × 16 pt image, then the printed name + date on the same line.
    if page.image(MID + 167, y - ROW + 1.5, 78, min(16, ROW - 3), s53.get("signature_data")):
        page.text(MID + 167 + 82, y - ROW + 3.4,
                  page.fit(f"{s53.get('printed_name') or tr.get('name') or ''}  {_sig_date(s53)}".strip(),
                           lw - 164 - 88, 6.5), 6.5)
    else:
        page.text(MID + 167, y - ROW + 3.4, "Signature on File", 7.2, bold=True)
    y -= ROW
    page.field(MARGIN, y, lw, "", "City, State, Zip Code", b2)
    page.field(MID + 4, y, (lw - 4) / 2, "54", "NPI", tr.get("npi"))
    page.field(MID + 4 + (lw - 4) / 2, y, (lw - 4) / 2, "55", "License Number", tr.get("license"))
    y -= ROW
    page.field(MARGIN, y, lw / 2, "49", "NPI", bill.get("npi"))
    page.field(MARGIN + lw / 2, y, lw / 2, "50", "License Number", bill.get("license"))
    page.field(MID + 4, y, lw - 4, "56", "Address Where Treatment Was Performed", t1, h=ROW)
    y -= ROW
    page.field(MARGIN, y, lw / 2, "51", "SSN or TIN", bill.get("tax_id"))
    page.field(MARGIN + lw / 2, y, lw / 2, "52", "Phone Number", bill.get("phone"))
    page.field(MID + 4, y, lw - 4, "", "City, State, Zip Code", t2)
    y -= ROW
    page.field(MARGIN, y, lw, "52a", "Additional Provider ID", bill.get("additional_provider_id"))
    page.field(MID + 4, y, 80, "56a", "Provider Specialty Code", tr.get("specialty_code"))
    page.field(MID + 84, y, 100, "57", "Phone Number", tr.get("phone"))
    page.field(MID + 184, y, lw - 184, "58", "Additional Provider ID", tr.get("additional_provider_id"))
    y -= ROW
    # ── footer ────────────────────────────────────────────────────────────
    c.setFillColorRGB(*_GREY)
    c.setFont("Helvetica", 6)
    c.drawString(MARGIN, MARGIN - 8,
                 f"Claim {form.get('claim_number') or form['claim_id']} · Patient {form['patient_id']} · "
                 f"ADA form v{FORM_VERSION} · printed {printed_at}")
    c.drawRightString(PAGE_W - MARGIN, MARGIN - 8, f"Page {page_no} of {form['pages']}")
    c.setFillColorRGB(0, 0, 0)


def render(forms: list[dict[str, Any]], *, mode: str = "form", offset_x: float = 0.0,
           offset_y: float = 0.0, printed_at: datetime | None = None) -> bytes:
    """One PDF for one or many assembled forms (batch = many claims, in order)."""
    if mode not in ("form", "overlay"):
        raise ValueError("mode must be 'form' or 'overlay'")
    canvas_mod, letter, string_width = _rl()
    buf = io.BytesIO()
    c = canvas_mod.Canvas(buf, pagesize=letter)
    stamp = (printed_at or datetime.now(timezone.utc)).strftime("%m/%d/%Y %H:%M UTC")
    for form in forms:
        c.setTitle(f"ADA Dental Claim Form - {form.get('claim_number') or form['claim_id']}")
        lines = form.get("service_lines") or []
        pages = max(1, form.get("pages") or 1)
        for page_no in range(1, pages + 1):
            chunk = lines[(page_no - 1) * LINES_PER_PAGE: page_no * LINES_PER_PAGE]
            c.saveState()
            c.translate(offset_x, offset_y)
            _draw_form(_Page(c, mode, string_width), form, chunk, page_no, page_no == pages, stamp)
            c.restoreState()
            c.showPage()
    c.save()
    return buf.getvalue()
