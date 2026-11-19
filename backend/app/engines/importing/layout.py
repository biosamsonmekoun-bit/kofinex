"""Reconstitution d'un tableau à partir de mots positionnés (PDF texte ou OCR)."""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass

from app.engines.importing.detection import _norm, header_score


@dataclass(frozen=True)
class Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    conf: float | None = None   # confiance OCR 0-100 ; None pour un PDF texte


@dataclass
class Chunk:
    text: str
    x0: float
    x1: float
    conf: float | None

    @property
    def center(self) -> float:
        return (self.x0 + self.x1) / 2


_NUMERIC = re.compile(r"^[(\-−+]?[0-9][0-9 ., ]*[)\-]?$")


def _lines(words: list[Word]) -> list[list[Word]]:
    if not words:
        return []
    heights = [w.bottom - w.top for w in words if w.bottom > w.top] or [10.0]
    tol = statistics.median(heights) * 0.5
    lines: list[list[Word]] = []
    for w in sorted(words, key=lambda w: (w.top, w.x0)):
        if lines and abs(w.top - lines[-1][0].top) <= tol:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(line, key=lambda w: w.x0) for line in lines]


def _chunks(line: list[Word]) -> list[Chunk]:
    out: list[Chunk] = []
    for w in line:
        char_w = (w.x1 - w.x0) / max(len(w.text), 1)
        if out and w.x0 - out[-1].x1 <= 1.6 * char_w:
            prev = out[-1]
            confs = [c for c in (prev.conf, w.conf) if c is not None]
            out[-1] = Chunk(f"{prev.text} {w.text}", prev.x0, w.x1, min(confs) if confs else None)
        else:
            out.append(Chunk(w.text, w.x0, w.x1, w.conf))
    return out


@dataclass
class TableResult:
    rows: list[list[str | None]]
    confidence: list[list[float | None]]
    header_index: int | None


def words_to_table(words: list[Word]) -> TableResult:
    lines = [_chunks(line) for line in _lines(words)]
    if not lines:
        return TableResult([], [], None)

    header_idx = None
    best = 1
    for i, line in enumerate(lines[:40]):
        s = header_score([c.text for c in line])
        if s > best:
            header_idx, best = i, s

    if header_idx is None:
        # sans en-tête : une cellule par bloc de texte, dans l'ordre
        return TableResult([[c.text for c in line] for line in lines],
                           [[c.conf for c in line] for line in lines], None)

    header_chunks = lines[header_idx]
    anchors = [c.center for c in header_chunks]
    # En-tête sur plusieurs lignes (« N° / CPTE / INTITULES » au-dessus de « DEBITEUR … ») : si la
    # plupart des lignes de données commencent nettement à gauche du premier intitulé retenu, on
    # ajoute une colonne de tête pour le compte et le libellé.
    first_x0 = min(c.x0 for c in header_chunks)
    lefts = [line[0] for line in lines[header_idx + 1:] if line and line[0].x1 < first_x0 - 5]
    data_lines = sum(1 for line in lines[header_idx + 1:] if line)
    if data_lines and len(lefts) >= 0.3 * data_lines:
        anchors.insert(0, statistics.median(c.x0 for c in lefts))
        header_chunks = [Chunk("", lefts[0].x0, lefts[0].x1, None), *header_chunks]
    bounds = [(anchors[k] + anchors[k + 1]) / 2 for k in range(len(anchors) - 1)]

    def column_of(chunk: Chunk) -> int:
        # les montants sont alignés à droite : on utilise leur bord droit
        x = chunk.x1 if _NUMERIC.match(chunk.text) else chunk.center
        for k, b in enumerate(bounds):
            if x < b:
                return k
        return len(anchors) - 1

    header_norm = [_norm(c.text) for c in header_chunks]

    def is_side(k: int, side: str) -> bool:
        return 0 <= k < len(header_norm) and header_norm[k].split()[:1] == [side]

    rows: list[list[str | None]] = []
    confs: list[list[float | None]] = []
    for i, line in enumerate(lines):
        cells: list[str | None] = [None] * len(anchors)
        conf: list[float | None] = [None] * len(anchors)
        for ch in line:
            k = column_of(ch)
            # intitulé de groupe (« Solde d'ouverture ») centré au-dessus d'une paire Débit/Crédit :
            # rattaché à la colonne Débit pour être propagé ensuite sur la paire
            if i == header_idx - 1 and is_side(k, "credit") and is_side(k - 1, "debit"):
                k -= 1
            cells[k] = f"{cells[k]} {ch.text}" if cells[k] else ch.text
            if ch.conf is not None:
                conf[k] = ch.conf if conf[k] is None else min(conf[k], ch.conf)
        rows.append(cells)
        confs.append(conf)
    return TableResult(rows, confs, header_idx)
