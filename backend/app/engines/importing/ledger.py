"""Lecture et contrôles d'un grand livre (écritures comptables) exporté d'un logiciel comptable.

Formats : tout tableau (Excel, CSV) dont l'utilisateur associe les colonnes. Les en-têtes du fichier des écritures
comptables (FEC : JournalCode, EcritureNum, CompteNum, Debit, Credit…) sont reconnus automatiquement. Aucun
montant n'est deviné : une cellule illisible rend la ligne en erreur, et un grand livre comportant une seule ligne
en erreur ne peut pas être validé.

Contrôles :
- bloquants : lignes illisibles, dates hors de l'exercice, grand livre déséquilibré, écritures déséquilibrées ;
- avertissements (à accepter explicitement) : comptes absents du plan, écarts avec la balance validée.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from app.engines.importing.accounts import parse_account_cell
from app.engines.importing.controls import ChartContext, ControlReport, ControlResult, _fmt
from app.engines.importing.detection import _norm
from app.engines.importing.numbers import AmountError, parse_amount

ZERO = Decimal("0")
MAX_LISTED = 25

FIELDS = (
    "journal_code",
    "journal_label",
    "entry_number",
    "entry_date",
    "document_ref",
    "document_date",
    "account_number",
    "account_label",
    "auxiliary_account",
    "auxiliary_label",
    "label",
    "debit",
    "credit",
    "amount",
    "direction",
    "lettering",
    "lettering_date",
    "validation_date",
    "currency_amount",
    "currency",
)
FIELD_LABELS = {
    "journal_code": "Code journal",
    "journal_label": "Libellé du journal",
    "entry_number": "N° d'écriture",
    "entry_date": "Date d'écriture",
    "document_ref": "Référence de la pièce",
    "document_date": "Date de la pièce",
    "account_number": "N° de compte",
    "account_label": "Libellé du compte",
    "auxiliary_account": "Compte auxiliaire (tiers)",
    "auxiliary_label": "Libellé du tiers",
    "label": "Libellé de l'écriture",
    "debit": "Débit",
    "credit": "Crédit",
    "amount": "Montant (colonne unique)",
    "direction": "Sens (D / C)",
    "lettering": "Lettrage",
    "lettering_date": "Date de lettrage",
    "validation_date": "Date de validation",
    "currency_amount": "Montant en devise",
    "currency": "Devise",
}
DATE_FIELDS = ("entry_date", "document_date", "lettering_date", "validation_date")

# en-têtes du fichier des écritures comptables (FEC), reconnus tels quels
FEC_HEADERS = {
    "journalcode": "journal_code",
    "journallib": "journal_label",
    "ecriturenum": "entry_number",
    "ecrituredate": "entry_date",
    "comptenum": "account_number",
    "comptelib": "account_label",
    "compauxnum": "auxiliary_account",
    "compauxlib": "auxiliary_label",
    "pieceref": "document_ref",
    "piecedate": "document_date",
    "ecriturelib": "label",
    "debit": "debit",
    "credit": "credit",
    "ecriturelet": "lettering",
    "datelet": "lettering_date",
    "validdate": "validation_date",
    "montantdevise": "currency_amount",
    "idevise": "currency",
}
# mots-clés d'en-têtes courants (ordre = priorité)
KEYWORDS: dict[str, tuple[str, ...]] = {
    "journal_code": ("code journal", "journal", "jnl", "jal", "code jal"),
    "journal_label": ("libelle journal", "libelle du journal", "intitule journal", "intitule du journal", "nom journal"),
    "entry_number": (
        "n ecriture",
        "no ecriture",
        "numero ecriture",
        "num ecriture",
        "n mouvement",
        "ecriture",
        "n piece comptable",
    ),
    "entry_date": ("date ecriture", "date comptable", "date d ecriture", "date"),
    "document_ref": ("piece", "n piece", "no piece", "reference", "ref piece", "ref"),
    "document_date": ("date piece", "date de la piece"),
    "account_number": ("compte general", "n compte", "no compte", "numero de compte", "compte", "cpte"),
    "account_label": ("libelle compte", "libelle du compte", "intitule compte", "intitule du compte", "nom du compte"),
    "auxiliary_account": ("compte auxiliaire", "compte tiers", "tiers", "auxiliaire"),
    "auxiliary_label": ("libelle tiers", "libelle du tiers", "nom tiers", "nom du tiers"),
    "label": ("libelle ecriture", "libelle", "intitule", "designation", "description"),
    "debit": ("debit", "mouvement debit", "montant debit"),
    "credit": ("credit", "mouvement credit", "montant credit"),
    "amount": ("montant",),
    "direction": ("sens", "d c"),
    "lettering": ("lettrage", "let"),
    "validation_date": ("date validation", "date de validation"),
}


class LedgerMappingError(ValueError):
    pass


@dataclass
class LedgerOptions:
    decimal_separator: Literal[",", "."] | None = None
    amount_sign: Literal["debit_positive", "credit_positive"] | None = None  # requis pour un montant signé seul
    negative_amounts: Literal["error", "move_to_other_side"] = "error"
    opening_journals: list[str] = field(default_factory=list)  # journaux d'à-nouveaux (choix de l'utilisateur)
    skip_zero_lines: bool = True
    # replace : le fichier remplace le grand livre actif (fichier complet ou correctif) ;
    # complement : le fichier complète le grand livre actif (lignes nouvelles seulement, doublons écartés)
    mode: Literal["replace", "complement"] = "replace"

    @classmethod
    def from_dict(cls, d: dict | None) -> LedgerOptions:
        d = dict(d or {})
        allowed = set(cls.__dataclass_fields__)
        o = cls(**{k: v for k, v in d.items() if k in allowed})
        o.opening_journals = [str(j).strip() for j in (o.opening_journals or []) if str(j).strip()]
        return o


def validate_column_map(cm: dict[str, int], options: LedgerOptions) -> None:
    unknown = set(cm) - set(FIELDS)
    if unknown:
        raise LedgerMappingError(f"Champs inconnus : {', '.join(sorted(unknown))}.")
    if any(not isinstance(v, int) or v < 0 for v in cm.values()):
        raise LedgerMappingError("Les colonnes sont désignées par leur rang (entier positif).")
    if len(set(cm.values())) != len(cm):
        raise LedgerMappingError("Une même colonne est associée à deux champs.")
    for req in ("entry_date", "account_number"):
        if req not in cm:
            raise LedgerMappingError(f"Colonne requise : {FIELD_LABELS[req]}.")
    has_dc = "debit" in cm or "credit" in cm
    if has_dc and "amount" in cm:
        raise LedgerMappingError("Associez soit les colonnes Débit et Crédit, soit une colonne Montant, pas les deux.")
    if has_dc and not ("debit" in cm and "credit" in cm):
        raise LedgerMappingError("Les colonnes Débit et Crédit vont ensemble.")
    if not has_dc and "amount" not in cm:
        raise LedgerMappingError("Associez les colonnes Débit et Crédit, ou une colonne Montant.")
    if "amount" in cm and "direction" not in cm and options.amount_sign is None:
        raise LedgerMappingError("Montant signé sans colonne de sens : précisez si un montant positif est un débit ou un crédit.")
    if "direction" in cm and "amount" not in cm:
        raise LedgerMappingError("La colonne Sens accompagne une colonne Montant.")


# ------------------------------------------------------------------ détection des colonnes
def header_score(cells: list[object]) -> int:
    normed = [_norm(c) for c in cells]
    fec = sum(1 for c in cells if str(c or "").strip().lower() in FEC_HEADERS)
    kw = sum(1 for n in normed if n and any(re.search(rf"(^| ){re.escape(k)}( |$)", n) for ks in KEYWORDS.values() for k in ks))
    return fec * 2 + kw


def detect_header_row(rows: list[list[object]], scan: int = 30) -> int | None:
    best, best_score = None, 2
    for i, r in enumerate(rows[:scan]):
        s = header_score(r)
        if s > best_score:
            best, best_score = i, s
    return best


def suggest_mapping(rows: list[list[object]], header_row: int) -> tuple[dict[str, int], list[str], str]:
    """Association proposée (à confirmer par l'utilisateur), en-têtes lus et format reconnu (« fec » ou « generic »)."""
    headers = [str(c).strip() if c is not None else "" for c in rows[header_row]]
    fec = {FEC_HEADERS[h.lower()]: i for i, h in enumerate(headers) if h.lower() in FEC_HEADERS}
    if {"journal_code", "entry_number", "entry_date", "account_number", "debit", "credit"} <= set(fec):
        return fec, headers, "fec"
    normed = [_norm(h) for h in headers]
    taken: set[int] = set()
    cm: dict[str, int] = {}
    # champs les plus spécifiques d'abord, pour qu'un « libellé du compte » ne devienne pas « libellé »
    order = (
        "journal_label",
        "account_label",
        "auxiliary_label",
        "document_date",
        "validation_date",
        "auxiliary_account",
        "entry_number",
        "journal_code",
        "entry_date",
        "document_ref",
        "account_number",
        "label",
        "debit",
        "credit",
        "direction",
        "lettering",
        "amount",
    )
    for fld in order:
        for kw in KEYWORDS.get(fld, ()):
            hit = next(
                (
                    i
                    for i, n in enumerate(normed)
                    if i not in taken and n and (n == kw or re.search(rf"(^| ){re.escape(kw)}( |$)", n))
                ),
                None,
            )
            if hit is not None:
                cm[fld] = hit
                taken.add(hit)
                break
    if "debit" in cm and "credit" in cm:
        cm.pop("amount", None)
        cm.pop("direction", None)
    return cm, headers, "generic"


# ------------------------------------------------------------------ lecture
@dataclass
class LineIssue:
    code: str
    field: str | None
    message: str


@dataclass
class LedgerLine:
    source_row: int
    status: Literal["valid", "error", "skipped"]
    journal_code: str | None = None
    journal_label: str | None = None
    entry_number: str | None = None
    entry_date: date | None = None
    document_ref: str | None = None
    document_date: date | None = None
    account_number: str | None = None
    account_label: str | None = None
    auxiliary_account: str | None = None
    auxiliary_label: str | None = None
    label: str | None = None
    debit: Decimal = ZERO
    credit: Decimal = ZERO
    lettering: str | None = None
    lettering_date: date | None = None
    validation_date: date | None = None
    currency_amount: Decimal | None = None
    currency: str | None = None
    issues: list[LineIssue] = field(default_factory=list)
    raw: list[object] = field(default_factory=list)

    @property
    def entry_key(self) -> tuple | None:
        if self.entry_number:
            return (self.journal_code or "", self.entry_number)
        if self.document_ref:
            return (self.journal_code or "", str(self.entry_date), self.document_ref)
        return None


@dataclass
class LedgerParse:
    lines: list[LedgerLine]
    entry_key_basis: Literal["entry_number", "document_ref", "none"]

    @property
    def valid(self) -> list[LedgerLine]:
        return [ln for ln in self.lines if ln.status == "valid"]

    @property
    def errors(self) -> list[LedgerLine]:
        return [ln for ln in self.lines if ln.status == "error"]


_DATE_FORMATS = ("%d/%m/%Y", "%Y-%m-%d", "%Y%m%d", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y")


def parse_date(v: object) -> date | None:
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip()
    s = s.split(" ")[0] if re.match(r"^\d{4}-\d{2}-\d{2}[ T]", s) else s.split("T")[0]
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"date illisible « {s} »")


def _text(v: object) -> str | None:
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip()
    return s or None


def build_ledger(rows: list[list[object]], header_row: int, cm: dict[str, int], options: LedgerOptions) -> LedgerParse:
    validate_column_map(cm, options)
    out: list[LedgerLine] = []
    sep = options.decimal_separator

    def cell(r: list[object], f: str) -> object:
        i = cm.get(f)
        return r[i] if i is not None and i < len(r) else None

    def amount(r: list[object], f: str, ln: LedgerLine) -> Decimal | None:
        try:
            return parse_amount(cell(r, f), decimal_separator=sep)
        except AmountError as exc:
            ln.issues.append(LineIssue("AMOUNT", f, f"{FIELD_LABELS[f]} illisible ({exc})"))
            return None

    for idx, r in enumerate(rows[header_row + 1 :], start=header_row + 1):
        if all(c is None or str(c).strip() == "" for c in r):
            continue
        ln = LedgerLine(
            source_row=idx + 1, status="valid", raw=[c if isinstance(c, (str, int, float)) or c is None else str(c) for c in r]
        )
        for f in (
            "journal_code",
            "journal_label",
            "entry_number",
            "document_ref",
            "account_label",
            "auxiliary_account",
            "auxiliary_label",
            "label",
            "lettering",
            "currency",
        ):
            setattr(ln, f, _text(cell(r, f)))
        for f in DATE_FIELDS:
            if f in cm:
                try:
                    setattr(ln, f, parse_date(cell(r, f)))
                except ValueError as exc:
                    ln.issues.append(LineIssue("DATE", f, f"{FIELD_LABELS[f]} : {exc}"))
        if ln.entry_date is None and not any(i.field == "entry_date" for i in ln.issues):
            ln.issues.append(LineIssue("DATE", "entry_date", "Date d'écriture manquante"))
        acc = parse_account_cell(cell(r, "account_number"))
        if acc.number is None:
            ln.issues.append(
                LineIssue("ACCOUNT", "account_number", f"Numéro de compte illisible « {_text(cell(r, 'account_number')) or ''} »")
            )
        else:
            ln.account_number = acc.number
            ln.account_label = ln.account_label or acc.label_remainder
        if "currency_amount" in cm:
            ln.currency_amount = amount(r, "currency_amount", ln)

        if "amount" in cm:
            a = amount(r, "amount", ln)
            if a is not None:
                if "direction" in cm:
                    d = _norm(cell(r, "direction"))
                    side = "debit" if d.startswith("d") else "credit" if d.startswith("c") else None
                    if side is None:
                        ln.issues.append(
                            LineIssue("DIRECTION", "direction", f"Sens illisible « {_text(cell(r, 'direction')) or ''} »")
                        )
                    elif a < 0:
                        ln.issues.append(LineIssue("NEGATIVE", "amount", "Montant négatif avec une colonne de sens"))
                    else:
                        ln.debit, ln.credit = (a, ZERO) if side == "debit" else (ZERO, a)
                else:
                    # convention choisie par l'utilisateur : le signe désigne le côté
                    debit_side = (a >= 0) == (options.amount_sign == "debit_positive")
                    ln.debit, ln.credit = (abs(a), ZERO) if debit_side else (ZERO, abs(a))
        else:
            dv, cv = amount(r, "debit", ln), amount(r, "credit", ln)
            dv, cv = dv or ZERO, cv or ZERO
            for name, v in (("debit", dv), ("credit", cv)):
                if v < 0 and options.negative_amounts == "error":
                    ln.issues.append(LineIssue("NEGATIVE", name, f"{FIELD_LABELS[name]} négatif"))
            if options.negative_amounts == "move_to_other_side":
                dv, cv = (
                    (dv if dv > 0 else ZERO) + (-cv if cv < 0 else ZERO),
                    (cv if cv > 0 else ZERO) + (-dv if dv < 0 else ZERO),
                )
            ln.debit, ln.credit = dv, cv
            if dv > 0 and cv > 0:
                ln.issues.append(LineIssue("BOTH_SIDES", None, "Débit et crédit renseignés sur la même ligne"))

        if ln.issues:
            ln.status = "error"
        elif ln.debit == ZERO and ln.credit == ZERO and options.skip_zero_lines:
            ln.status = "skipped"
        out.append(ln)
    basis = "entry_number" if "entry_number" in cm else "document_ref" if "document_ref" in cm else "none"
    return LedgerParse(out, basis)


# ------------------------------------------------------------------ contrôles
@dataclass
class TBRow:
    account: str
    opening_net: Decimal
    movement_debit: Decimal
    movement_credit: Decimal
    closing_net: Decimal


def run_controls(
    p: LedgerParse,
    fy_start: date,
    fy_end: date,
    options: LedgerOptions,
    *,
    chart: ChartContext | None,
    balance: list[TBRow] | None,
    tolerance: Decimal = ZERO,
) -> ControlReport:
    res: list[ControlResult] = []
    valid = p.valid
    td = sum((ln.debit for ln in valid), ZERO)
    tc = sum((ln.credit for ln in valid), ZERO)

    errs = p.errors
    res.append(
        ControlResult(
            "LINES_READABLE",
            "Lignes lisibles",
            "failed" if errs else "passed",
            "error",
            f"{len(errs)} ligne(s) illisible(s) : corrigez le fichier ou l'association des colonnes."
            if errs
            else f"{len(valid)} lignes lues.",
            {"rows": [{"row": ln.source_row, "issues": [i.message for i in ln.issues]} for ln in errs[:MAX_LISTED]]},
        )
    )
    if not valid:
        res.append(ControlResult("NOT_EMPTY", "Grand livre non vide", "failed", "error", "Aucune ligne exploitable."))
        return ControlReport(res, {"ledger": {"debit": str(td), "credit": str(tc)}}, len(p.lines))

    out = [ln for ln in valid if not (fy_start <= ln.entry_date <= fy_end)]
    res.append(
        ControlResult(
            "DATES_IN_YEAR",
            "Dates comprises dans l'exercice",
            "failed" if out else "passed",
            "error",
            f"{len(out)} écriture(s) datée(s) hors de l'exercice ({fy_start:%d/%m/%Y} – {fy_end:%d/%m/%Y})."
            if out
            else "Toutes les écritures sont datées dans l'exercice.",
            {"rows": [{"row": ln.source_row, "date": str(ln.entry_date)} for ln in out[:MAX_LISTED]]},
        )
    )

    diff = td - tc
    res.append(
        ControlResult(
            "LEDGER_BALANCED",
            "Équilibre du grand livre",
            "failed" if abs(diff) > tolerance else "passed",
            "error",
            f"Total débit {_fmt(td)} − total crédit {_fmt(tc)} = {_fmt(diff)}.",
        )
    )

    if p.entry_key_basis == "none":
        res.append(
            ControlResult(
                "ENTRIES_BALANCED",
                "Équilibre de chaque écriture",
                "skipped",
                "info",
                "Ni numéro d'écriture ni référence de pièce : l'équilibre par écriture ne peut pas être vérifié.",
            )
        )
    else:
        entries: dict[tuple, list[Decimal]] = defaultdict(lambda: [ZERO, ZERO])
        for ln in valid:
            k = ln.entry_key
            if k is not None:
                entries[k][0] += ln.debit
                entries[k][1] += ln.credit
        missing = sum(1 for ln in valid if ln.entry_key is None)
        bad = [(k, d, c) for k, (d, c) in entries.items() if abs(d - c) > tolerance]
        basis = "n° d'écriture" if p.entry_key_basis == "entry_number" else "journal, date et pièce"
        msg = (
            f"{len(bad)} écriture(s) déséquilibrée(s) sur {len(entries)} (regroupement par {basis})."
            if bad
            else f"{len(entries)} écritures équilibrées (regroupement par {basis})."
        )
        if missing:
            msg += f" {missing} ligne(s) sans identifiant d'écriture."
        res.append(
            ControlResult(
                "ENTRIES_BALANCED",
                "Équilibre de chaque écriture",
                "failed" if bad or missing else "passed",
                "error",
                msg,
                {
                    "entries": [
                        {"key": " / ".join(k), "debit": str(d), "credit": str(c), "difference": str(d - c)}
                        for k, d, c in bad[:MAX_LISTED]
                    ]
                },
            )
        )

    if chart is not None:
        unknown = sorted({ln.account_number for ln in valid if chart.match(ln.account_number) is None})
        res.append(
            ControlResult(
                "ACCOUNTS_IN_CHART",
                f"Comptes du plan {chart.framework_code} {chart.version_label}",
                "failed" if unknown else "passed",
                "warning",
                f"{len(unknown)} compte(s) sans compte de rattachement dans le plan."
                if unknown
                else "Tous les comptes se rattachent au plan de comptes.",
                {"accounts": unknown[:MAX_LISTED]},
            )
        )
    else:
        res.append(
            ControlResult(
                "ACCOUNTS_IN_CHART",
                "Comptes du plan",
                "skipped",
                "info",
                "Aucun référentiel publié pour l'exercice : comptes non contrôlés.",
            )
        )

    res.append(reconcile_with_balance(valid, options, balance, tolerance))
    totals = {"ledger": {"debit": str(td), "credit": str(tc), "difference": str(diff)}}
    return ControlReport(res, totals, len(p.lines))


def account_totals(lines: list[LedgerLine], opening_journals: list[str]) -> dict[str, dict[str, Decimal]]:
    out: dict[str, dict[str, Decimal]] = defaultdict(lambda: {"opening": ZERO, "debit": ZERO, "credit": ZERO})
    oj = set(opening_journals)
    for ln in lines:
        t = out[ln.account_number]
        if ln.journal_code in oj:
            t["opening"] += ln.debit - ln.credit
        else:
            t["debit"] += ln.debit
            t["credit"] += ln.credit
    return out


def reconcile_with_balance(
    valid: list[LedgerLine], options: LedgerOptions, balance: list[TBRow] | None, tolerance: Decimal = ZERO
) -> ControlResult:
    """Rapprochement compte par compte avec la balance validée de l'exercice :
    - mouvements du grand livre (hors journaux d'à-nouveaux désignés) = mouvements de la balance ;
    - à-nouveaux du grand livre (journaux désignés) = soldes d'ouverture de la balance, si des journaux sont désignés.
    Un écart est un avertissement à accepter : la balance et le grand livre peuvent provenir d'extractions différentes."""
    if balance is None:
        return ControlResult(
            "TB_RECONCILIATION",
            "Rapprochement avec la balance validée",
            "skipped",
            "info",
            "Aucune balance validée pour l'exercice : rapprochement impossible.",
        )
    led = account_totals(valid, options.opening_journals)
    tb = {r.account: r for r in balance}
    gaps = []
    for acc in sorted(set(led) | set(tb)):
        lt, br = led.get(acc), tb.get(acc)
        ld, lc = (lt["debit"], lt["credit"]) if lt else (ZERO, ZERO)
        bd, bc = (br.movement_debit, br.movement_credit) if br else (ZERO, ZERO)
        row = {"account": acc}
        if abs(ld - bd) > tolerance or abs(lc - bc) > tolerance:
            row.update(ledger_debit=str(ld), balance_debit=str(bd), ledger_credit=str(lc), balance_credit=str(bc))
        if options.opening_journals:
            lo = lt["opening"] if lt else ZERO
            bo = br.opening_net if br else ZERO
            if abs(lo - bo) > tolerance:
                row.update(ledger_opening=str(lo), balance_opening=str(bo))
        if len(row) > 1:
            gaps.append(row)
    scope = "mouvements et à-nouveaux" if options.opening_journals else "mouvements (aucun journal d'à-nouveaux désigné)"
    return ControlResult(
        "TB_RECONCILIATION",
        "Rapprochement avec la balance validée",
        "failed" if gaps else "passed",
        "warning",
        f"{len(gaps)} compte(s) en écart avec la balance ({scope})."
        if gaps
        else f"Grand livre et balance concordent compte par compte ({scope}).",
        {"accounts": gaps[:MAX_LISTED], "count": len(gaps)},
    )


def line_dict(ln: LedgerLine) -> dict:
    d = asdict(ln)
    d["issues"] = [asdict(i) for i in ln.issues]
    return d


# ------------------------------------------------------------------ exploitation
def fiscal_period(fy_start: date, d: date) -> int:
    return (d.year - fy_start.year) * 12 + d.month - fy_start.month + 1


def benford_expected() -> dict[int, Decimal]:
    """Loi de Benford du premier chiffre significatif : P(d) = log10(1 + 1/d) (relation mathématique)."""
    import math

    return {d: Decimal(str(round(math.log10(1 + 1 / d) * 100, 2))) for d in range(1, 10)}


def first_digit(v: Decimal) -> int | None:
    s = str(abs(v)).replace(".", "").lstrip("0")
    return int(s[0]) if s else None


def weekday_label(d: date) -> str:
    return ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")[d.weekday()]


def numbering_gaps(numbers: list[str]) -> list[tuple[int, int]]:
    """Trous dans une suite de numéros entiers (numéros non entiers ignorés) : liste de (du, au) manquants."""
    ints = sorted({int(n) for n in numbers if n and n.isdigit()})
    gaps = []
    for a, b in zip(ints, ints[1:], strict=False):
        if b - a > 1:
            gaps.append((a + 1, b - 1))
    return gaps


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def after(d: date | None, limit: date) -> bool:
    return d is not None and d > limit



# ------------------------------------------------------------------ import complémentaire
def _norm_label(v: str | None) -> str:
    return " ".join(str(v or "").split()).upper()


def fingerprint(ln: LedgerLine) -> tuple:
    """Empreinte d'une ligne pour la détection des doublons entre imports : journal, numéro de pièce comptable, date,
    référence, compte, compte auxiliaire, débit, crédit et libellé (espaces et casse normalisés)."""
    return (ln.journal_code or "", ln.entry_number or "", ln.entry_date, ln.document_ref or "", ln.account_number or "",
            ln.auxiliary_account or "", ln.debit, ln.credit, _norm_label(ln.label))


def complement(existing: list[LedgerLine], incoming: LedgerParse) -> tuple[LedgerParse, dict]:
    """Import complémentaire : le grand livre actif est repris tel quel, puis complété par les lignes nouvelles du fichier.

    - Une ligne du fichier identique (empreinte) à une ligne déjà importée est écartée (« skipped », DUPLICATE_OF_ACTIVE) ;
      les doublons sont comptés ligne à ligne : deux lignes identiques légitimes dans l'import actif n'en écartent que deux.
    - Une écriture du fichier (même clé d'écriture) déjà présente dans l'import actif avec un contenu différent est
      refusée (ENTRY_CONFLICT) : une modification passe par un import de remplacement (fichier correctif complet).
    - Rien n'est additionné aveuglément : le résultat est l'union exacte, contrôlée ensuite comme tout import.
    Les lignes reprises sont renumérotées à partir de 1, les lignes du fichier à la suite (unicité du rang par import)."""
    pool: dict[tuple, int] = {}
    for ln in existing:
        pool[fingerprint(ln)] = pool.get(fingerprint(ln), 0) + 1
    existing_entries: dict[tuple, list[tuple]] = {}
    for ln in existing:
        if ln.entry_key is not None:
            existing_entries.setdefault(ln.entry_key, []).append(fingerprint(ln))
    carried: list[LedgerLine] = []
    for i, ln in enumerate(sorted(existing, key=lambda x: x.source_row), 1):
        carried.append(replace(ln, source_row=i, issues=list(ln.issues)))
    offset = len(carried)
    added = dupes = conflicts = 0
    months: set[str] = set()
    out_new: list[LedgerLine] = []
    remaining = dict(pool)
    # une écriture du fichier est soit entièrement reprise (doublon), soit nouvelle, soit en conflit
    by_entry: dict[tuple | None, list[LedgerLine]] = {}
    for ln in incoming.lines:
        by_entry.setdefault(ln.entry_key if ln.status == "valid" else ("__row__", ln.source_row), []).append(ln)
    for key, lines in by_entry.items():
        valid = [x for x in lines if x.status == "valid"]
        if key is not None and key in existing_entries and valid:
            fps = sorted((fingerprint(x) for x in valid), key=repr)
            if fps != sorted(existing_entries[key], key=repr):
                for x in valid:
                    x.status = "error"
                    x.issues.append(LineIssue("ENTRY_CONFLICT", None, "Écriture déjà importée sous cette référence avec un "
                                              "contenu différent : utilisez un import de remplacement (fichier correctif)."))
                    conflicts += 1
                out_new.extend(lines)
                continue
        for x in lines:
            if x.status == "valid":
                fp = fingerprint(x)
                if remaining.get(fp, 0) > 0:
                    remaining[fp] -= 1
                    x.status = "skipped"
                    x.issues.append(LineIssue("DUPLICATE_OF_ACTIVE", None,
                                              "Ligne déjà présente dans le grand livre actif : écartée."))
                    dupes += 1
                else:
                    added += 1
                    if x.entry_date:
                        months.add(x.entry_date.strftime("%Y-%m"))
            out_new.append(x)
    renumbered = [replace(x, source_row=offset + i) for i, x in enumerate(sorted(out_new, key=lambda y: y.source_row), 1)]
    existing_months = sorted({x.entry_date.strftime("%Y-%m") for x in existing if x.entry_date})
    summary = {"carried": len(carried), "duplicates": dupes, "added": added, "conflicts": conflicts,
               "added_months": sorted(months), "existing_months": existing_months,
               "overlapping_months": sorted(months & set(existing_months))}
    return LedgerParse(carried + renumbered, incoming.entry_key_basis), summary
