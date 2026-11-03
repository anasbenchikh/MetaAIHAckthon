"""Devis PDF generation (fpdf2, latin-1 core fonts — French accents OK)."""

from datetime import date
from typing import Any, Dict, List

from fpdf import FPDF

BUSINESS_NAME = "Plombier Express Lyon"
BUSINESS_LINES = [
    "12 rue de la République",
    "69001 Lyon - Tél : 04 00 00 00 00",
    "contact@plombier-express-lyon.fr",
    "SIRET : 000 000 000 00000",
]


def _eur(amount: float) -> str:
    return f"{amount:,.2f} EUR".replace(",", " ")


def _latin1(value: Any) -> Any:
    if isinstance(value, str):
        return value.encode("latin-1", errors="replace").decode("latin-1")
    if isinstance(value, dict):
        return {key: _latin1(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_latin1(item) for item in value]
    return value


def normalize_items(items: Any) -> List[Dict[str, Any]]:
    cleaned: List[Dict[str, Any]] = []
    if not isinstance(items, list):
        return cleaned
    for item in items:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("description") or "?")
        try:
            qty = float(item.get("qty", 1))
        except (TypeError, ValueError):
            qty = 1.0
        try:
            price = float(item.get("price", 0))
        except (TypeError, ValueError):
            price = 0.0
        cleaned.append({"label": label, "qty": qty, "price": price, "total": qty * price})
    return cleaned


def compute_totals(items: List[Dict[str, Any]], tax_rate: float) -> Dict[str, float]:
    subtotal = round(sum(i["total"] for i in items), 2)
    tax = round(subtotal * tax_rate, 2)
    return {"subtotal": subtotal, "tax": tax, "total": round(subtotal + tax, 2)}


def build_quote_pdf(data: Dict[str, Any]) -> bytes:
    data = _latin1(data)
    items = normalize_items(data.get("items"))
    tax_rate = float(data.get("tax_rate", 0.20))
    totals = compute_totals(items, tax_rate)
    number = str(data.get("number") or "DEV-?")
    issued = str(data.get("issued_on") or date.today().isoformat())

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, BUSINESS_NAME, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    for line in BUSINESS_LINES:
        pdf.cell(0, 4.5, line, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, f"DEVIS {number}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Date : {issued}   -   Validité : 30 jours", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Client", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    for line in (
        data.get("name") or "?",
        data.get("address") or "",
        data.get("phone") or "",
    ):
        if line:
            pdf.cell(0, 5.5, str(line), new_x="LMARGIN", new_y="NEXT")
    if data.get("job_type"):
        pdf.cell(0, 5.5, f"Prestation : {data['job_type']}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    widths = (100, 20, 35, 35)
    pdf.set_font("Helvetica", "B", 10)
    for title, width in zip(("Description", "Qté", "P.U. HT", "Total HT"), widths):
        pdf.cell(width, 7, title, border=1)
    pdf.ln()
    pdf.set_font("Helvetica", "", 10)
    for item in items:
        pdf.cell(widths[0], 7, item["label"][:60], border=1)
        pdf.cell(widths[1], 7, f"{item['qty']:g}", border=1)
        pdf.cell(widths[2], 7, _eur(item["price"]), border=1)
        pdf.cell(widths[3], 7, _eur(item["total"]), border=1)
        pdf.ln()
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 11)
    pdf.cell(120, 7, "Sous-total HT", align="R")
    pdf.cell(0, 7, _eur(totals["subtotal"]), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(120, 7, f"TVA {tax_rate * 100:g} %", align="R")
    pdf.cell(0, 7, _eur(totals["tax"]), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(120, 9, "TOTAL TTC", align="R")
    pdf.cell(0, 9, _eur(totals["total"]), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    if data.get("notes"):
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 7, "Notes", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 5.5, str(data["notes"]))
        pdf.ln(2)

    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, "Signature client (mention « Bon pour accord ») :", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(12)
    pdf.set_font("Helvetica", "I", 8)
    pdf.cell(0, 5, "Devis généré par Plombier Express Lyon - Dashboard Sarah", align="C")

    out = pdf.output()
    return bytes(out) if isinstance(out, bytearray) else out
