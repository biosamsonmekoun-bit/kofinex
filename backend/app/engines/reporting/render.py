"""Rendu d'un document neutre en Word (python-docx), Excel (openpyxl) ou PDF (reportlab). Chaque fichier porte en
pied de page l'empreinte des données, la date d'établissement, son auteur et la version du générateur ; les
avertissements (brouillons IA non relus, document de travail) figurent en tête."""

from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime

from app.engines.reporting import document as d

MIME = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def footer_text(meta: dict) -> str:
    return (
        f"KOFINEX · {d.GENERATOR_VERSION} · établi le {d.fmt_date(meta['generated_at'])} par {meta.get('generated_by') or '—'} · "
        f"empreinte des données {meta['data_sha256'][:16]}…"
    )


def _rgb(hex_color: str | None) -> tuple[int, int, int]:
    h = (hex_color or d.DEFAULT_COLOR).lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _cells(block: dict) -> list[list[str]]:
    return [[d.fmt(r.get(c["key"]), c["type"]) for c in block["columns"]] for r in block["rows"]]


def render(doc: dict, fmt: str, meta: dict) -> bytes:
    """meta : generated_at (datetime), generated_by, data_sha256, branding (primary_color)."""
    if fmt == "docx":
        return to_docx(doc, meta)
    if fmt == "xlsx":
        return to_xlsx(doc, meta)
    if fmt == "pdf":
        return to_pdf(doc, meta)
    raise ValueError(f"Format inconnu : {fmt}")


# ------------------------------------------------------------------ Word
def to_docx(doc: dict, meta: dict) -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt, RGBColor

    color = RGBColor(*_rgb((meta.get("branding") or {}).get("primary_color")))
    w = Document()
    st = w.styles["Normal"]
    st.font.name, st.font.size = "Calibri", Pt(10)
    sec = w.sections[0]
    sec.header.paragraphs[0].text = " — ".join(x for x in (doc.get("entity"), doc["title"]) if x)
    sec.footer.paragraphs[0].text = footer_text(meta)
    h = w.add_heading(doc["title"], level=0)
    for r in h.runs:
        r.font.color.rgb = color
    for line in (doc.get("subtitle"), doc.get("entity"), doc.get("period")):
        if line:
            w.add_paragraph(line)
    for n in doc["notices"]:
        p = w.add_paragraph()
        run = p.add_run(("ATTENTION — " if n["level"] == "warning" else "") + n["text"])
        run.bold = True
    for s in doc["sections"]:
        hh = w.add_heading(s["title"], level=1)
        for r in hh.runs:
            r.font.color.rgb = color
        for b in s["blocks"]:
            k = b["kind"]
            if k == "paragraph":
                if b.get("style") == "heading":
                    w.add_heading(b["text"], level=2)
                else:
                    p = w.add_paragraph(b["text"])
                    if b.get("style") == "note":
                        for r in p.runs:
                            r.italic = True
            elif k == "notice":
                w.add_paragraph().add_run(b["text"]).bold = True
            elif k == "fields":
                for label, value in b["items"]:
                    p = w.add_paragraph()
                    p.add_run(f"{label} : ").bold = True
                    p.add_run(str(value))
            elif k == "table":
                if b.get("title"):
                    w.add_paragraph().add_run(b["title"]).bold = True
                t = w.add_table(rows=1, cols=len(b["columns"]))
                t.style = "Table Grid"
                for i, c in enumerate(b["columns"]):
                    cell = t.rows[0].cells[i]
                    cell.text = c["label"]
                    for r in cell.paragraphs[0].runs:
                        r.bold = True
                for row in _cells(b):
                    cells = t.add_row().cells
                    for i, (v, c) in enumerate(zip(row, b["columns"], strict=True)):
                        cells[i].text = v
                        if d.numeric(c["type"]):
                            cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    w.add_heading("Sources", level=1)
    for src in doc["sources"]:
        w.add_paragraph(_source_line(src), style="List Bullet")
    cp = w.core_properties
    cp.title, cp.author, cp.comments = doc["title"], "KOFINEX", f"données {meta['data_sha256']}"
    cp.created = cp.modified = _naive(meta["generated_at"])
    buf = io.BytesIO()
    w.save(buf)
    return _stable_zip(buf.getvalue(), meta["generated_at"])


def _source_line(src: dict) -> str:
    extra = ", ".join(f"{k} {v}" for k, v in src.items() if k not in ("type", "id", "label") and v)
    return (
        f"{src.get('label') or src.get('type')}" + (f" — {src['id']}" if src.get("id") else "") + (f" ({extra})" if extra else "")
    )


def _stable_zip(data: bytes, at: datetime) -> bytes:
    """Réécrit l'archive OOXML en datant chaque entrée de la génération du rapport (et non de l'horloge au moment de
    l'écriture) : deux rendus des mêmes données et métadonnées donnent exactement les mêmes octets. openpyxl force
    aussi la date de modification des propriétés à l'heure de l'enregistrement : elle est ramenée à la génération."""
    iso = _naive(at).strftime("%Y-%m-%dT%H:%M:%SZ").encode()
    stamp = _naive(at).timetuple()[:6]
    stamp = (max(stamp[0], 1980),) + stamp[1:]
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(out, "w") as dst:
        for info in src.infolist():
            z = zipfile.ZipInfo(info.filename, date_time=stamp)
            z.compress_type, z.external_attr = info.compress_type, info.external_attr
            body = src.read(info.filename)
            if info.filename == "docProps/core.xml":
                body = re.sub(rb"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)", rb"\g<1>" + iso + rb"\g<2>", body)
            dst.writestr(z, body)
    return out.getvalue()


def _naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


# ------------------------------------------------------------------ Excel
def to_xlsx(doc: dict, meta: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    hexc = ((meta.get("branding") or {}).get("primary_color") or d.DEFAULT_COLOR).lstrip("#").upper()
    head_font, head_fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor=hexc)
    wb = Workbook()
    ws = wb.active
    ws.title = "Synthèse"
    ws.append([doc["title"]])
    ws["A1"].font = Font(bold=True, size=14, color=hexc)
    for line in (doc.get("subtitle"), doc.get("entity"), doc.get("period")):
        if line:
            ws.append([line])
    for n in doc["notices"]:
        ws.append([("ATTENTION — " if n["level"] == "warning" else "") + n["text"]])
        ws.cell(ws.max_row, 1).font = Font(bold=True)
    ws.append([])
    used = {"Synthèse", "Sources"}
    n_table = 0
    formats = {"amount": "#,##0.00", "number": "#,##0.##", "percent": '0.0" %"', "ratio": "0.00"}
    for s in doc["sections"]:
        ws.append([s["title"]])
        ws.cell(ws.max_row, 1).font = Font(bold=True, color=hexc)
        for b in s["blocks"]:
            if b["kind"] in ("paragraph", "notice"):
                ws.append([b["text"]])
                ws.cell(ws.max_row, 1).alignment = Alignment(wrap_text=False)
            elif b["kind"] == "fields":
                for label, value in b["items"]:
                    ws.append([label, str(value)])
            elif b["kind"] == "table":
                n_table += 1
                name = _sheet_name(f"{n_table} {b.get('title') or s['title']}", used)
                ws.append([f"→ tableau dans la feuille « {name} »"])
                t = wb.create_sheet(name)
                t.append([c["label"] for c in b["columns"]])
                for c in t[1]:
                    c.font, c.fill = head_font, head_fill
                for r in b["rows"]:
                    vals = []
                    for c in b["columns"]:
                        v = r.get(c["key"])
                        num = d.to_decimal(v) if d.numeric(c["type"]) else None
                        vals.append(float(num) if num is not None else ("" if v is None else str(v)))
                    t.append(vals)
                for j, c in enumerate(b["columns"], 1):
                    if c["type"] in formats:
                        for row in t.iter_rows(min_row=2, min_col=j, max_col=j):
                            row[0].number_format = formats[c["type"]]
                    width = max([len(str(c["label"]))] + [len(str(r.get(c["key"]) or "")) for r in b["rows"][:200]])
                    t.column_dimensions[t.cell(1, j).column_letter].width = min(max(width + 2, 10), 60)
                t.freeze_panes = "A2"
        ws.append([])
    ws.column_dimensions["A"].width = 90
    src = wb.create_sheet("Sources")
    src.append(["Type", "Identifiant", "Libellé", "Détail"])
    for c in src[1]:
        c.font, c.fill = head_font, head_fill
    for s_ in doc["sources"]:
        src.append(
            [
                s_.get("type"),
                s_.get("id") or "",
                s_.get("label") or "",
                ", ".join(f"{k} {v}" for k, v in s_.items() if k not in ("type", "id", "label") and v),
            ]
        )
    src.append([])
    src.append([footer_text(meta)])
    src.append(["Empreinte des données (SHA-256)", meta["data_sha256"]])
    wb.properties.title, wb.properties.creator = doc["title"], "KOFINEX"
    wb.properties.created = wb.properties.modified = _naive(meta["generated_at"])
    buf = io.BytesIO()
    wb.save(buf)
    return _stable_zip(buf.getvalue(), meta["generated_at"])


def _sheet_name(raw: str, used: set[str]) -> str:
    base = re.sub(r"[\[\]:*?/\\]", " ", raw)[:31].strip() or "Tableau"
    name, i = base, 2
    while name in used:
        suffix = f" ({i})"
        name, i = base[: 31 - len(suffix)] + suffix, i + 1
    used.add(name)
    return name


# ------------------------------------------------------------------ PDF
_PDF_MAP = str.maketrans({" ": " ", " ": " ", " ": "  ", "→": "->", "≤": "<=", "≥": ">=", "×": "x", "−": "-"})


def _pdf_text(s: str) -> str:
    """Polices standard PDF (WinAnsi) : les caractères hors de ce jeu sont remplacés plutôt que perdus silencieusement."""
    t = str(s).translate(_PDF_MAP)
    t = t.encode("cp1252", errors="replace").decode("cp1252")
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def to_pdf(doc: dict, meta: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    wide = any(b["kind"] == "table" and len(b["columns"]) > 6 for s in doc["sections"] for b in s["blocks"])
    size = landscape(A4) if wide else A4
    brand = colors.HexColor((meta.get("branding") or {}).get("primary_color") or d.DEFAULT_COLOR)
    accent = colors.HexColor(d.ACCENT_COLOR)
    ss = getSampleStyleSheet()
    st = {
        "title": ParagraphStyle("t", parent=ss["Title"], textColor=brand, alignment=0, fontSize=18),
        "h1": ParagraphStyle("h1", parent=ss["Heading2"], textColor=brand, spaceBefore=10),
        "h2": ParagraphStyle("h2", parent=ss["Heading3"]),
        "body": ParagraphStyle("b", parent=ss["BodyText"], fontSize=9, leading=12),
        "note": ParagraphStyle("n", parent=ss["BodyText"], fontSize=8, leading=10, textColor=colors.HexColor("#64748B")),
        "warn": ParagraphStyle(
            "w", parent=ss["BodyText"], fontSize=9, leading=12, textColor=colors.HexColor("#B45309"), fontName="Helvetica-Bold"
        ),
        "cell": ParagraphStyle("c", parent=ss["BodyText"], fontSize=7.5, leading=9),
        "cellr": ParagraphStyle("cr", parent=ss["BodyText"], fontSize=7.5, leading=9, alignment=TA_RIGHT),
        "head": ParagraphStyle(
            "hd", parent=ss["BodyText"], fontSize=7.5, leading=9, textColor=colors.white, fontName="Helvetica-Bold"
        ),
    }
    P = lambda text, style: Paragraph(_pdf_text(text), st[style])  # noqa: E731
    story = [P(doc["title"], "title")]
    for line in (doc.get("subtitle"), doc.get("entity"), doc.get("period")):
        if line:
            story.append(P(line, "body"))
    for n in doc["notices"]:
        story += [
            Spacer(1, 2 * mm),
            P(("ATTENTION — " if n["level"] == "warning" else "") + n["text"], "warn" if n["level"] == "warning" else "body"),
        ]
    avail = size[0] - 30 * mm
    for s in doc["sections"]:
        story.append(P(s["title"], "h1"))
        for b in s["blocks"]:
            k = b["kind"]
            if k == "paragraph":
                story.append(P(b["text"], {"heading": "h2", "note": "note"}.get(b.get("style"), "body")))
            elif k == "notice":
                story.append(P(b["text"], "warn"))
            elif k == "fields":
                story += [Paragraph(f"<b>{_pdf_text(lbl)} :</b> {_pdf_text(v)}", st["body"]) for lbl, v in b["items"]]
            elif k == "table":
                if b.get("title"):
                    story.append(P(b["title"], "h2"))
                cols = b["columns"]
                weights = [3 if c["type"] == "text" else 1.4 for c in cols]
                widths = [avail * wgt / sum(weights) for wgt in weights]
                data = [[P(c["label"], "head") for c in cols]]
                data += [
                    [P(v, "cellr" if d.numeric(c["type"]) else "cell") for v, c in zip(row, cols, strict=True)]
                    for row in _cells(b)
                ]
                t = Table(data, colWidths=widths, repeatRows=1)
                t.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), brand),
                            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                        ]
                    )
                )
                story += [t, Spacer(1, 3 * mm)]
    story.append(P("Sources", "h1"))
    story += [P("• " + _source_line(src), "body") for src in doc["sources"]]
    story += [Spacer(1, 3 * mm), P(f"Empreinte des données (SHA-256) : {meta['data_sha256']}", "note")]
    foot = _pdf_text(footer_text(meta)).replace("&amp;", "&")
    head = _pdf_text(" — ".join(x for x in (doc.get("entity"), doc["title"]) if x)).replace("&amp;", "&")

    def decorate(canvas, docu):
        canvas.saveState()
        canvas.setStrokeColor(accent)
        canvas.setLineWidth(1)
        canvas.line(15 * mm, size[1] - 12 * mm, size[0] - 15 * mm, size[1] - 12 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawString(15 * mm, size[1] - 10 * mm, head[:150])
        canvas.drawString(15 * mm, 8 * mm, foot[:170])
        canvas.drawRightString(size[0] - 15 * mm, 8 * mm, f"page {docu.page}")
        canvas.restoreState()

    buf = io.BytesIO()
    pdf = SimpleDocTemplate(
        buf,
        pagesize=size,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=18 * mm,
        bottomMargin=16 * mm,
        title=_pdf_text(doc["title"]),
        author="KOFINEX",
        subject=f"données {meta['data_sha256']}",
        creator=d.GENERATOR_VERSION,
        invariant=1,
    )
    pdf.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return buf.getvalue()
