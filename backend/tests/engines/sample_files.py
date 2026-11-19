"""Fichiers de balance FICTIFS générés pour les tests (aucune donnée réelle).

Balance équilibrée de 6 comptes : ouverture 12 500 000,00 ; mouvements 16 300 000,50 ;
clôture 17 800 000,50.
"""

from __future__ import annotations

import io
from decimal import Decimal as D

ROWS = [
    # compte, libellé, ouv. D, ouv. C, mvt D, mvt C, clôt. D, clôt. C
    ("101000", "Capital social (test)", "0", "10000000", "0", "0", "0", "10000000"),
    ("401100", "Fournisseurs (test)", "0", "2500000", "3000000", "1800000.50", "0", "1300000.50"),
    ("411100", "Clients (test)", "4000000", "0", "6500000", "5000000", "5500000", "0"),
    ("521100", "Banque (test)", "8500000", "0", "5000000", "3000000", "10500000", "0"),
    ("601100", "Achats (test)", "0", "0", "1800000.50", "0", "1800000.50", "0"),
    ("701100", "Ventes (test)", "0", "0", "0", "6500000", "0", "6500000"),
]
TOTALS = ("12500000", "12500000", "16300000.50", "16300000.50", "17800000.50", "17800000.50")


def fr(amount: str) -> str:
    """12500000.5 -> « 12 500 000,50 » (espace insécable comme séparateur de milliers)."""
    return f"{D(amount):,.2f}".replace(",", " ").replace(".", ",")


def xlsx_two_level_header(with_totals: bool = True) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Balance 2025"
    ws.append(["SOCIÉTÉ DE TEST — BALANCE GÉNÉRALE AU 31/12/2025 (données fictives)"])
    ws.append([])
    ws.append(["", "", "Solde d'ouverture", None, "Mouvements", None, "Solde de clôture", None])
    ws.merge_cells("C3:D3")
    ws.merge_cells("E3:F3")
    ws.merge_cells("G3:H3")
    ws.append(["N° compte", "Intitulé", "Débit", "Crédit", "Débit", "Crédit", "Débit", "Crédit"])
    ws.append(["Classe 1 - Comptes de ressources durables"])
    for r in ROWS:
        ws.append([int(r[0]), r[1], *[float(D(x)) for x in r[2:]]])
    if with_totals:
        ws.append(["TOTAL GÉNÉRAL", None, *[float(D(x)) for x in TOTALS]])
    ws2 = wb.create_sheet("Notes")
    ws2.append(["Feuille sans balance"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def csv_french_cp1252() -> bytes:
    lines = ["Compte;Libellé;Débit;Crédit"]
    for r in ROWS:
        lines.append(f"{r[0]};{r[1]};{fr(r[6]) if D(r[6]) else ''};{fr(r[7]) if D(r[7]) else ''}")
    lines.append(f"Total;;{fr(TOTALS[4])};{fr(TOTALS[5])}")
    return "\r\n".join(lines).replace(" ", " ").encode("cp1252")


def pdf_text() -> bytes:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A4))
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, 560, "BALANCE GENERALE - DONNEES FICTIVES DE TEST")
    c.setFont("Helvetica", 10)
    x_label, x_cols = 120, [420, 520, 620, 720]
    y = 520
    c.drawString(40, y, "Compte")
    c.drawString(x_label, y, "Libelle")
    for x, h in zip(x_cols, ["Mvt Debit", "Mvt Credit", "Solde Debit", "Solde Credit"], strict=True):
        c.drawRightString(x + 60, y, h)
    for r in ROWS:
        y -= 20
        c.drawString(40, y, r[0])
        c.drawString(x_label, y, r[1])
        for x, v in zip(x_cols, (r[4], r[5], r[6], r[7]), strict=True):
            c.drawRightString(x + 60, y, fr(v).replace(" ", " "))
    c.save()
    return buf.getvalue()


def pdf_scanned() -> bytes:
    """Le PDF texte rendu en image (pas de couche texte), comme un document numérisé."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(pdf_text())
    image = doc[0].render(scale=300 / 72).to_pil().convert("RGB")
    doc.close()
    buf = io.BytesIO()
    image.save(buf, format="PDF", resolution=300)
    return buf.getvalue()
