"""Lecture des fichiers en tableaux de cellules (« feuilles »).

* xlsx : openpyxl en lecture seule, valeurs calculées (aucune formule n'est évaluée) ;
* xls  : xlrd si installé, sinon refus explicite ;
* csv  : détection de l'encodage et du séparateur ;
* pdf  : texte natif via pdfplumber ; pages sans texte -> OCR Tesseract (français).
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from app.engines.importing.files import FileRejected, decode_text
from app.engines.importing.layout import Word, words_to_table

logger = logging.getLogger(__name__)

MAX_ROWS = 100_000
MAX_COLS = 60
MAX_PDF_PAGES = 200
MAX_OCR_PAGES = 50
OCR_DPI = 300
MIN_TEXT_CHARS = 40          # en dessous, la page est considérée comme numérisée


@dataclass
class Sheet:
    name: str
    rows: list[list[object]]
    source: str                                   # xlsx | xls | csv | pdf_text | pdf_ocr
    confidence: list[list[float | None]] | None = None   # OCR uniquement
    row_pages: list[int] | None = None                    # PDF uniquement
    warnings: list[str] = field(default_factory=list)
    uncached_formulas: int = 0

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def column_count(self) -> int:
        return max((len(r) for r in self.rows), default=0)


@dataclass
class Extraction:
    sheets: list[Sheet]
    method: str                 # spreadsheet | csv | pdf_text | pdf_ocr | pdf_mixed
    page_count: int | None = None
    ocr_pages: list[int] = field(default_factory=list)


def _cell(v: object) -> object:
    if isinstance(v, str):
        v = v.strip()
        return v or None
    if isinstance(v, datetime | date):
        return v.isoformat()
    return v


def _trim(rows: list[list[object]]) -> list[list[object]]:
    out = []
    for r in rows:
        r = [_cell(v) for v in r[:MAX_COLS]]
        while r and r[-1] is None:
            r.pop()
        out.append(r)
    while out and not out[-1]:
        out.pop()
    return out


# ----------------------------------------------------------------------------- tableurs
def read_xlsx(data: bytes) -> Extraction:
    from openpyxl import load_workbook

    try:
        wb_values = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        wb_formulas = load_workbook(io.BytesIO(data), read_only=True, data_only=False)
    except Exception as exc:  # openpyxl lève des exceptions variées sur un fichier altéré
        raise FileRejected("Impossible de lire le classeur : fichier corrompu ou format non pris en charge.") from exc

    sheets: list[Sheet] = []
    try:
        for ws in wb_values.worksheets:
            wf = wb_formulas[ws.title]
            rows: list[list[object]] = []
            uncached = 0
            for i, (vals, forms) in enumerate(zip(ws.iter_rows(values_only=True), wf.iter_rows(values_only=True),
                                                  strict=False)):
                if i >= MAX_ROWS:
                    break
                row = list(vals)
                for j, (v, f) in enumerate(zip(row, forms, strict=False)):
                    if v is None and isinstance(f, str) and f.startswith("="):
                        uncached += 1
                        row[j] = None
                rows.append(row)
            sheet = Sheet(name=ws.title, rows=_trim(rows), source="xlsx", uncached_formulas=uncached)
            if uncached:
                sheet.warnings.append(
                    f"{uncached} formule(s) sans valeur calculée : ouvrez le fichier dans Excel, "
                    "enregistrez-le, puis déposez-le à nouveau.")
            if ws.max_row and ws.max_row > MAX_ROWS:
                sheet.warnings.append(f"Feuille tronquée à {MAX_ROWS} lignes.")
            sheets.append(sheet)
    finally:
        wb_values.close()
        wb_formulas.close()
    return Extraction(sheets=sheets, method="spreadsheet")


def read_xls(data: bytes) -> Extraction:
    try:
        import xlrd  # type: ignore[import-not-found]
    except ImportError as exc:
        raise FileRejected("Le format .xls (Excel 97-2003) n'est pas disponible sur ce serveur : "
                           "enregistrez le fichier au format .xlsx.") from exc
    try:
        book = xlrd.open_workbook(file_contents=data, on_demand=True)
    except Exception as exc:
        raise FileRejected("Impossible de lire le classeur .xls.") from exc
    sheets = []
    for sh in book.sheets():
        rows = []
        for r in range(min(sh.nrows, MAX_ROWS)):
            row = []
            for c in range(min(sh.ncols, MAX_COLS)):
                cell = sh.cell(r, c)
                if cell.ctype == xlrd.XL_CELL_DATE:
                    row.append(xlrd.xldate.xldate_as_datetime(cell.value, book.datemode))
                elif cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
                    row.append(None)
                elif cell.ctype == xlrd.XL_CELL_ERROR:
                    row.append(None)
                else:
                    row.append(cell.value)
            rows.append(row)
        sheets.append(Sheet(name=sh.name, rows=_trim(rows), source="xls"))
    return Extraction(sheets=sheets, method="spreadsheet")


def read_csv(data: bytes) -> Extraction:
    text, encoding = decode_text(data)
    sample = text[:20000]
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=";,\t|").delimiter
    except csv.Error:
        counts = {d: sample.count(d) for d in ";,\t|"}
        delimiter = max(counts, key=lambda d: counts[d])
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = [row for _, row in zip(range(MAX_ROWS), reader, strict=False)]
    sheet = Sheet(name="CSV", rows=_trim(rows), source="csv")
    sep_label = "tabulation" if delimiter == "\t" else delimiter
    sheet.warnings.append(f"Encodage détecté : {encoding} ; séparateur : « {sep_label} ».")
    return Extraction(sheets=[sheet], method="csv")


# ----------------------------------------------------------------------------- PDF
def read_pdf(data: bytes, *, ocr_lang: str = "fra", allow_ocr: bool = True) -> Extraction:
    import pdfplumber

    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except Exception as exc:
        raise FileRejected("Impossible de lire le PDF.") from exc

    all_rows: list[list[object]] = []
    all_conf: list[list[float | None]] = []
    pages_of_rows: list[int] = []
    ocr_pages: list[int] = []
    text_pages = 0
    warnings: list[str] = []

    with pdf:
        page_count = len(pdf.pages)
        if page_count > MAX_PDF_PAGES:
            raise FileRejected(f"PDF trop long ({page_count} pages, maximum {MAX_PDF_PAGES}).")
        for number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text.strip()) >= MIN_TEXT_CHARS:
                text_pages += 1
                words = [Word(w["text"], float(w["x0"]), float(w["x1"]), float(w["top"]), float(w["bottom"]))
                         for w in page.extract_words(keep_blank_chars=False, use_text_flow=False)]
            else:
                if not allow_ocr:
                    warnings.append(f"Page {number} sans texte (numérisée) : OCR désactivé.")
                    continue
                if len(ocr_pages) >= MAX_OCR_PAGES:
                    warnings.append(f"Page {number} non lue : limite de {MAX_OCR_PAGES} pages OCR atteinte.")
                    continue
                words = _ocr_page(data, number - 1, ocr_lang)
                ocr_pages.append(number)
            table = words_to_table(words)
            # en-têtes répétés en haut de chaque page : on ne garde que le premier
            start = 0
            if all_rows and table.header_index is not None:
                start = table.header_index + 1
            for r, c in zip(table.rows[start:], table.confidence[start:], strict=False):
                all_rows.append(list(r))
                all_conf.append(list(c))
                pages_of_rows.append(number)

    if not all_rows:
        raise FileRejected("Aucun tableau exploitable n'a été trouvé dans le PDF.")
    method = "pdf_ocr" if ocr_pages and not text_pages else "pdf_mixed" if ocr_pages else "pdf_text"
    if ocr_pages:
        warnings.append(f"Reconnaissance optique (OCR) utilisée sur {len(ocr_pages)} page(s) : "
                        "vérifiez attentivement chaque montant avant validation.")
    sheet = Sheet(name="PDF", rows=all_rows, source="pdf_ocr" if ocr_pages else "pdf_text",
                  confidence=all_conf if ocr_pages else None, row_pages=pages_of_rows, warnings=warnings)
    return Extraction(sheets=[sheet], method=method, page_count=page_count, ocr_pages=ocr_pages)


def _ocr_page(data: bytes, index: int, lang: str) -> list[Word]:
    try:
        import pypdfium2 as pdfium
        import pytesseract
    except ImportError as exc:
        raise FileRejected("Le PDF est numérisé mais l'OCR n'est pas installé sur ce serveur.") from exc

    doc = pdfium.PdfDocument(data)
    try:
        image = doc[index].render(scale=OCR_DPI / 72).to_pil().convert("L")
    finally:
        doc.close()
    scale = 72 / OCR_DPI   # coordonnées ramenées en points PDF
    try:
        d = pytesseract.image_to_data(image, lang=lang, config="--psm 6", output_type=pytesseract.Output.DICT)
    except pytesseract.TesseractError as exc:
        raise FileRejected(f"Échec de la reconnaissance optique : {exc}") from exc
    words = []
    for i, txt in enumerate(d["text"]):
        txt = (txt or "").strip()
        conf = float(d["conf"][i])
        if not txt or conf < 0:
            continue
        x0, top = d["left"][i] * scale, d["top"][i] * scale
        words.append(Word(txt, x0, x0 + d["width"][i] * scale, top, top + d["height"][i] * scale, conf))
    return words


# ----------------------------------------------------------------------------- point d'entrée
def extract(fmt: str, data: bytes, *, ocr_lang: str = "fra") -> Extraction:
    if fmt == "xlsx":
        return read_xlsx(data)
    if fmt == "xls":
        return read_xls(data)
    if fmt == "csv":
        return read_csv(data)
    if fmt == "pdf":
        return read_pdf(data, ocr_lang=ocr_lang)
    raise FileRejected(f"Format {fmt} non pris en charge.")


def jsonable(value: object) -> object:
    """Valeur de cellule sérialisable (prévisualisation, données brutes conservées)."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, float):
        return repr(value) if not value.is_integer() else int(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value
