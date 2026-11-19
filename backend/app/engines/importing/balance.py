"""Transformation d'une feuille en lignes de balance normalisées.

Chaque ligne du fichier produit soit une ligne de balance valide, soit une ligne en erreur
(avec la raison), soit une ligne ignorée (vide, total, intitulé). Rien n'est écarté
silencieusement : chaque décision est tracée dans ``issues``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from app.engines.importing.accounts import is_total_label, parse_account_cell
from app.engines.importing.detection import AMOUNT_FIELDS, FIELDS
from app.engines.importing.numbers import AmountError, infer_decimal_separator, parse_amount
from app.engines.importing.readers import jsonable

ZERO = Decimal("0.00")
LOW_OCR_CONFIDENCE = 80.0

RowStatus = Literal["valid", "error", "skipped", "total"]


@dataclass
class ImportOptions:
    signed_balance_convention: Literal["debit_positive", "credit_positive"] = "debit_positive"
    decimal_separator: Literal[",", "."] | None = None    # None = déduit des données
    negative_amounts: Literal["error", "move_to_other_side"] = "error"
    skip_zero_rows: bool = True
    exclude_aggregate_accounts: bool = False
    balance_tolerance: Decimal = ZERO                     # écart toléré sur les équilibres (0 = strict)

    @classmethod
    def from_dict(cls, d: dict | None) -> ImportOptions:
        d = dict(d or {})
        if "balance_tolerance" in d:
            d["balance_tolerance"] = Decimal(str(d["balance_tolerance"]))
        allowed = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in allowed})


@dataclass
class RowIssue:
    code: str
    message: str
    column: str | None = None
    severity: Literal["error", "warning", "info"] = "error"


@dataclass
class BalanceLine:
    source_row: int                      # numéro de ligne du fichier (1 = première ligne)
    status: RowStatus
    account_number: str | None = None
    account_label: str | None = None
    opening_debit: Decimal | None = None
    opening_credit: Decimal | None = None
    movement_debit: Decimal | None = None
    movement_credit: Decimal | None = None
    closing_debit: Decimal | None = None
    closing_credit: Decimal | None = None
    issues: list[RowIssue] = field(default_factory=list)
    raw: list[object] = field(default_factory=list)
    page: int | None = None
    min_confidence: float | None = None
    closing_computed: bool = False

    def net(self, group: str) -> Decimal:
        return (getattr(self, f"{group}_debit") or ZERO) - (getattr(self, f"{group}_credit") or ZERO)

    @property
    def is_zero(self) -> bool:
        return all((getattr(self, f) or ZERO) == ZERO for f in
                   ("opening_debit", "opening_credit", "movement_debit", "movement_credit",
                    "closing_debit", "closing_credit"))


@dataclass
class DeclaredTotal:
    source_row: int
    label: str
    values: dict[str, Decimal]


@dataclass
class ParseResult:
    lines: list[BalanceLine]
    declared_totals: list[DeclaredTotal]
    mapped_groups: set[str]
    decimal_separator: str | None

    @property
    def valid(self) -> list[BalanceLine]:
        return [line for line in self.lines if line.status == "valid"]

    @property
    def errors(self) -> list[BalanceLine]:
        return [line for line in self.lines if line.status == "error"]


class MappingError(ValueError):
    """Association de colonnes inutilisable."""


def validate_column_map(column_map: dict[str, int]) -> set[str]:
    unknown = set(column_map) - set(FIELDS)
    if unknown:
        raise MappingError(f"Champs inconnus : {', '.join(sorted(unknown))}")
    cols = list(column_map.values())
    if any(not isinstance(c, int) or c < 0 for c in cols):
        raise MappingError("Les colonnes doivent être des index positifs.")
    if len(cols) != len(set(cols)):
        raise MappingError("Une même colonne est associée à plusieurs champs.")
    if not ({"account_number", "account"} & set(column_map)):
        raise MappingError("La colonne du numéro de compte est obligatoire.")

    groups: set[str] = set()
    for g in ("opening", "movement", "closing"):
        has_pair = f"{g}_debit" in column_map or f"{g}_credit" in column_map
        has_signed = f"{g}_balance" in column_map
        if has_pair and has_signed:
            raise MappingError(f"{g} : choisissez soit les colonnes débit/crédit, soit le solde signé.")
        if has_pair and not (f"{g}_debit" in column_map and f"{g}_credit" in column_map) and g != "movement":
            raise MappingError(f"{g} : les colonnes débit ET crédit doivent être associées.")
        if g == "movement" and has_pair and not ("movement_debit" in column_map and "movement_credit" in column_map):
            raise MappingError("Mouvements : les colonnes débit ET crédit doivent être associées.")
        if has_pair or has_signed:
            groups.add(g)
    if "closing" not in groups and not {"opening", "movement"} <= groups:
        raise MappingError("Associez les soldes de clôture, ou à défaut l'ouverture ET les mouvements "
                           "(la clôture sera alors calculée).")
    return groups


def build_balance(rows: list[list[object]], header_row: int, column_map: dict[str, int],
                  options: ImportOptions, *, confidence: list[list[float | None]] | None = None,
                  row_pages: list[int] | None = None) -> ParseResult:
    groups = validate_column_map(column_map)

    sep = options.decimal_separator
    if sep is None:
        samples = [r[c] for r in rows[header_row + 1:header_row + 500]
                   for f, c in column_map.items() if f in AMOUNT_FIELDS and c < len(r)]
        sep = infer_decimal_separator(samples)

    def cell(row: list[object], f: str) -> object:
        c = column_map.get(f)
        return row[c] if c is not None and c < len(row) else None

    lines: list[BalanceLine] = []
    totals: list[DeclaredTotal] = []

    for idx in range(header_row + 1, len(rows)):
        row = rows[idx]
        line = BalanceLine(source_row=idx + 1, status="valid", raw=[jsonable(v) for v in row],
                           page=row_pages[idx] if row_pages and idx < len(row_pages) else None)
        if confidence and idx < len(confidence):
            used = [confidence[idx][c] for c in column_map.values()
                    if c < len(confidence[idx]) and confidence[idx][c] is not None]
            line.min_confidence = min(used) if used else None

        if all(v is None for v in row):
            line.status = "skipped"
            lines.append(line)
            continue

        acc_field = "account_number" if "account_number" in column_map else "account"
        acc = parse_account_cell(cell(row, acc_field))
        label_cell = cell(row, "account_label")
        label = str(label_cell).strip() if label_cell is not None else acc.label_remainder

        if acc.is_total or (acc.number is None and is_total_label(label)):
            values = _parse_amounts(row, column_map, sep, line)
            line.status = "total"
            if values and not line.issues:
                totals.append(DeclaredTotal(idx + 1, str(cell(row, acc_field) or label or "Total"), values))
            line.issues.clear()
            lines.append(line)
            continue

        if acc.number is None:
            # intitulé de section (« Classe 4 - Comptes de tiers »), ligne de titre… : ignorée
            values = _parse_amounts(row, column_map, sep, line)
            if any(v != ZERO for v in values.values()):
                line.status = "error"
                line.issues.append(RowIssue("ACCOUNT_MISSING", "Montants présents sans numéro de compte lisible.",
                                            acc_field))
            else:
                line.status = "skipped"
                line.issues.clear()
            lines.append(line)
            continue

        line.account_number = acc.number
        line.account_label = (label or None) and label[:300]
        values = _parse_amounts(row, column_map, sep, line)
        _assign(line, values, column_map, groups, options)

        if line.min_confidence is not None and line.min_confidence < LOW_OCR_CONFIDENCE:
            line.issues.append(RowIssue("OCR_LOW_CONFIDENCE",
                                        f"Lecture OCR incertaine (confiance {line.min_confidence:.0f} %).",
                                        severity="warning"))
        if any(i.severity == "error" for i in line.issues):
            line.status = "error"
        elif options.skip_zero_rows and line.is_zero:
            line.status = "skipped"
            line.issues.append(RowIssue("ZERO_ROW", "Ligne sans montant ignorée.", severity="info"))
        lines.append(line)

    return ParseResult(lines=lines, declared_totals=totals, mapped_groups=groups, decimal_separator=sep)


def _parse_amounts(row: list[object], column_map: dict[str, int], sep: str | None,
                   line: BalanceLine) -> dict[str, Decimal]:
    values: dict[str, Decimal] = {}
    for f in AMOUNT_FIELDS:
        c = column_map.get(f)
        if c is None or c >= len(row):
            continue
        try:
            v = parse_amount(row[c], decimal_separator=sep)
        except AmountError as exc:
            line.issues.append(RowIssue("AMOUNT_INVALID", str(exc), f))
            continue
        if v is not None:
            values[f] = v
    return values


def _assign(line: BalanceLine, values: dict[str, Decimal], column_map: dict[str, int], groups: set[str],
            opt: ImportOptions) -> None:
    for g in ("opening", "movement", "closing"):
        if g not in groups:
            continue
        if f"{g}_balance" in column_map:          # solde signé
            signed = values.get(f"{g}_balance", ZERO)
            if opt.signed_balance_convention == "credit_positive":
                signed = -signed
            setattr(line, f"{g}_debit", signed if signed > 0 else ZERO)
            setattr(line, f"{g}_credit", -signed if signed < 0 else ZERO)
            continue
        d, c = values.get(f"{g}_debit", ZERO), values.get(f"{g}_credit", ZERO)
        if d < 0 or c < 0:
            if opt.negative_amounts != "move_to_other_side":
                line.issues.append(RowIssue("NEGATIVE_AMOUNT",
                                            f"{g} : montant négatif dans une colonne débit/crédit.", f"{g}_debit"))
                continue
            d, c = max(d, ZERO) + max(-c, ZERO), max(c, ZERO) + max(-d, ZERO)
            line.issues.append(RowIssue("NEGATIVE_MOVED", f"{g} : montant négatif reporté dans la colonne opposée.",
                                        severity="info"))
        setattr(line, f"{g}_debit", d)
        setattr(line, f"{g}_credit", c)

    if "closing" not in groups:
        net = line.net("opening") + line.net("movement")
        line.closing_debit = net if net > 0 else ZERO
        line.closing_credit = -net if net < 0 else ZERO
        line.closing_computed = True
