"""Audit financier et comptable : seuils, revue analytique des comptes, sélection d'échantillons, projection
des anomalies, balance ajustée et effets des anomalies sur les états.

Aucun pourcentage de seuil, aucune taille d'échantillon et aucun facteur de confiance n'est fixé ici : ce sont des
choix de l'auditeur (ou des paramètres de sa méthodologie) passés en argument. Le moteur ne fait que des calculs
exacts (Decimal) et des tirages reproductibles (graine conservée).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from decimal import ROUND_HALF_UP, Decimal

from app.engines.accounting.statements import LineDef, MappingRule, TBEntry, build_statements

ZERO = Decimal("0")
CENT = Decimal("0.01")
HUNDRED = Decimal("100")


def money(v: Decimal) -> Decimal:
    """Arrondi au centime, demi supérieur (convention de présentation, pas une règle d'audit)."""
    return v.quantize(CENT, rounding=ROUND_HALF_UP)


# ============================================================ seuils
@dataclass(frozen=True)
class Materiality:
    benchmark_amount: Decimal
    overall_pct: Decimal
    overall: Decimal
    performance_pct: Decimal          # en % du seuil de signification
    performance: Decimal
    trivial_pct: Decimal              # en % du seuil de signification
    trivial: Decimal


def materiality(benchmark_amount: Decimal, overall_pct: Decimal, performance_pct: Decimal,
                trivial_pct: Decimal) -> Materiality:
    if benchmark_amount <= ZERO:
        raise ValueError("Le montant de référence doit être positif (prenez sa valeur absolue et justifiez-le).")
    for name, p in (("seuil de signification", overall_pct), ("seuil de planification", performance_pct),
                    ("seuil des anomalies insignifiantes", trivial_pct)):
        if not (ZERO < p <= HUNDRED):
            raise ValueError(f"Pourcentage du {name} hors de ]0 ; 100].")
    overall = money(benchmark_amount * overall_pct / HUNDRED)
    return Materiality(benchmark_amount, overall_pct, overall, performance_pct,
                       money(overall * performance_pct / HUNDRED), trivial_pct, money(overall * trivial_pct / HUNDRED))


# ============================================================ revue analytique des comptes
@dataclass(frozen=True)
class AccountVariation:
    account: str
    label: str | None
    balance_n: Decimal                # solde net (débit - crédit)
    balance_n1: Decimal | None
    variation: Decimal | None
    variation_pct: Decimal | None     # None si N-1 nul ou absent
    above_threshold: bool


def account_variations(cur: list[TBEntry], prev: list[TBEntry] | None, threshold: Decimal | None) -> list[AccountVariation]:
    """Une ligne par compte non nul en N ou en N-1. Le dépassement compare |variation| (ou |solde N| sans N-1)
    au seuil fourni (en pratique le seuil de planification approuvé)."""
    pmap = {e.account_number: e for e in (prev or [])}
    cmap = {e.account_number: e for e in cur}
    out = []
    for acc in sorted(set(cmap) | set(pmap)):
        c, p = cmap.get(acc), pmap.get(acc)
        bn = c.closing_net if c else ZERO
        bn1 = (p.closing_net if p else ZERO) if prev is not None else None
        if bn == ZERO and not bn1:
            continue
        var = bn - bn1 if bn1 is not None else None
        pct = money(var / abs(bn1) * HUNDRED) if var is not None and bn1 else None
        test = abs(var) if var is not None else abs(bn)
        out.append(AccountVariation(acc, (c or p).account_label, bn, bn1, var, pct,
                                    threshold is not None and test >= threshold))
    return out


def cycle_for(account: str, mappings: list[tuple[str, str]]) -> str | None:
    """Rattachement d'un compte à un cycle : préfixe le plus long parmi (préfixe, cycle) définis par l'auditeur."""
    best = None
    for prefix, cycle in mappings:
        if account.startswith(prefix) and (best is None or len(prefix) > len(best[0])):
            best = (prefix, cycle)
    return best[1] if best else None


# ============================================================ échantillonnage
@dataclass(frozen=True)
class PopItem:
    id: str
    amount: Decimal


@dataclass
class Selection:
    method: str
    item_ids: list[str]
    reasons: dict[str, str]
    parameters: dict = field(default_factory=dict)


def _check_size(n: int, size: int) -> None:
    if size < 1:
        raise ValueError("La taille de l'échantillon doit être d'au moins 1.")
    if size > n:
        raise ValueError(f"Taille demandée ({size}) supérieure à la population ({n} éléments).")


def select_random(items: list[PopItem], size: int, seed: int) -> Selection:
    """Tirage aléatoire simple sans remise, reproductible par la graine."""
    _check_size(len(items), size)
    rng = random.Random(seed)  # noqa: S311 (tirage reproductible, non cryptographique)
    chosen = rng.sample(range(len(items)), size)
    ids = [items[i].id for i in sorted(chosen)]
    return Selection("random", ids, {i: "random" for i in ids}, {"seed": seed, "size": size})


def select_systematic(items: list[PopItem], size: int, seed: int) -> Selection:
    """Sélection systématique : pas = N / taille (rationnel exact), départ aléatoire dans [0 ; pas[."""
    _check_size(len(items), size)
    n = len(items)
    rng = random.Random(seed)  # noqa: S311 (tirage reproductible, non cryptographique)
    # départ en fraction de pas, exprimé sur une grille fine pour rester exact
    start_num = rng.randrange(n)                      # départ = start_num / size  (∈ [0 ; n/size[)
    idx = [(start_num + k * n) // size for k in range(size)]
    ids = [items[i].id for i in idx]
    return Selection("systematic", ids, {i: "interval" for i in ids},
                     {"seed": seed, "size": size, "interval": str(Decimal(n) / Decimal(size)),
                      "start": str(Decimal(start_num) / Decimal(size))})


def select_mus(items: list[PopItem], size: int, seed: int) -> Selection:
    """Sélection en unités monétaires (valeurs absolues) : intervalle J = Σ|montants| / taille, départ aléatoire
    au centime dans ]0 ; J], points de sélection s + kJ. Un élément touché plusieurs fois n'est retenu qu'une fois ;
    tout élément d'un montant ≥ J est retenu."""
    if size < 1:
        raise ValueError("La taille de l'échantillon doit être d'au moins 1.")
    total = sum((abs(i.amount) for i in items), ZERO)
    if total == ZERO:
        raise ValueError("Population de valeur nulle : sélection en unités monétaires impossible.")
    cents = int((total / CENT).to_integral_value())
    interval_c = Decimal(cents) / Decimal(size)
    rng = random.Random(seed)  # noqa: S311 (tirage reproductible, non cryptographique)
    start_c = Decimal(rng.randrange(1, max(int(interval_c), 1) + 1))
    points = [start_c + k * interval_c for k in range(size)]
    ids: list[str] = []
    cum = Decimal(0)
    pi = 0
    for it in items:
        lo, cum = cum, cum + abs(it.amount) / CENT
        hit = False
        while pi < len(points) and lo < points[pi] <= cum:
            hit, pi = True, pi + 1
        if hit:
            ids.append(it.id)
    interval = money(interval_c * CENT)
    reasons = {i: ("key_item" if abs(next(x.amount for x in items if x.id == i)) >= interval else "interval") for i in ids}
    return Selection("mus", ids, reasons, {"seed": seed, "size": size, "interval": str(interval),
                                           "start": str(money(start_c * CENT)), "population_value": str(total)})


def select_key_items(items: list[PopItem], threshold: Decimal) -> Selection:
    if threshold <= ZERO:
        raise ValueError("Le seuil des éléments clés doit être positif.")
    ids = [i.id for i in items if abs(i.amount) >= threshold]
    if not ids:
        raise ValueError("Aucun élément n'atteint le seuil : rien à sélectionner.")
    return Selection("key_items", ids, {i: "key_item" for i in ids}, {"threshold": str(threshold)})


# ============================================================ projection des anomalies
@dataclass(frozen=True)
class TestedItem:
    book: Decimal
    audited: Decimal | None           # None : non encore testé

    @property
    def misstatement(self) -> Decimal:
        return self.book - (self.audited if self.audited is not None else self.book)


@dataclass(frozen=True)
class Projection:
    method: str                       # ratio | mus_tainting | none
    tested: int
    pending: int
    actual: Decimal                   # anomalies constatées dans l'échantillon
    projected: Decimal | None         # anomalie extrapolée à la population (anomalies constatées comprises)
    explanation: str


def project(method: str, population_value: Decimal, items: list[TestedItem], interval: Decimal | None = None) -> Projection:
    """Extrapolation de l'anomalie (estimation ponctuelle, sans limite supérieure : celle-ci exige les facteurs de
    confiance de la méthodologie).
    - aléatoire / systématique : estimation par le ratio, Σ anomalies / Σ valeurs comptables testées × valeur de la
      population ;
    - unités monétaires : pour les éléments < J, taux d'anomalie (anomalie / valeur comptable) × J ; pour les éléments
      ≥ J, l'anomalie constatée ;
    - éléments clés et sélection raisonnée : pas d'extrapolation, seule l'anomalie constatée compte."""
    tested = [i for i in items if i.audited is not None]
    pending = len(items) - len(tested)
    actual = sum((i.misstatement for i in tested), ZERO)
    if method in ("key_items", "judgmental"):
        return Projection("none", len(tested), pending, actual, None,
                          "Sélection non représentative : aucune extrapolation, seule l'anomalie constatée est retenue.")
    if not tested:
        return Projection("none", 0, pending, ZERO, None, "Aucun élément testé.")
    if method == "mus":
        if interval is None or interval <= ZERO:
            raise ValueError("Intervalle de sélection requis pour la projection en unités monétaires.")
        proj = ZERO
        for i in tested:
            if abs(i.book) >= interval or i.book == ZERO:
                proj += i.misstatement
            else:
                proj += i.misstatement / abs(i.book) * interval
        return Projection("mus_tainting", len(tested), pending, actual, money(proj),
                          "Taux d'anomalie de chaque élément × intervalle (éléments < intervalle) ; anomalie constatée "
                          "pour les éléments ≥ intervalle.")
    book = sum((abs(i.book) for i in tested), ZERO)
    if book == ZERO:
        return Projection("none", len(tested), pending, actual, None, "Valeur testée nulle : extrapolation impossible.")
    return Projection("ratio", len(tested), pending, actual, money(actual / book * population_value),
                      "Σ anomalies / Σ valeurs comptables testées × valeur de la population.")


# ============================================================ anomalies et balance ajustée
@dataclass(frozen=True)
class AdjLine:
    account: str
    label: str | None
    debit: Decimal
    credit: Decimal


def check_balanced(lines: list[AdjLine]) -> None:
    if not lines:
        raise ValueError("L'écriture d'ajustement ne comporte aucune ligne.")
    for ln in lines:
        if ln.debit < ZERO or ln.credit < ZERO or (ln.debit == ZERO) == (ln.credit == ZERO):
            raise ValueError(f"Compte {ln.account} : saisissez soit un débit, soit un crédit, positif.")
    d = sum((ln.debit for ln in lines), ZERO)
    c = sum((ln.credit for ln in lines), ZERO)
    if d != c:
        raise ValueError(f"Écriture déséquilibrée : débit {d} ≠ crédit {c}.")


def adjust(entries: list[TBEntry], lines: list[AdjLine]) -> list[TBEntry]:
    """Balance ajustée calculée : chaque ligne s'ajoute aux mouvements, le solde de clôture est recalculé
    (ouverture + mouvements). La balance importée n'est pas modifiée."""
    by = {e.account_number: e for e in entries}
    for ln in lines:
        e = by.get(ln.account) or TBEntry(ln.account, ln.label, ZERO, ZERO, ZERO, ZERO, ZERO, ZERO)
        md, mc = e.movement_debit + ln.debit, e.movement_credit + ln.credit
        net = e.closing_net + ln.debit - ln.credit
        by[ln.account] = replace(e, movement_debit=md, movement_credit=mc,
                                 closing_debit=net if net > ZERO else ZERO, closing_credit=-net if net < ZERO else ZERO)
    return sorted(by.values(), key=lambda e: e.account_number)


@dataclass(frozen=True)
class LineEffect:
    statement_type: str
    code: str
    label: str
    role: str | None
    before: Decimal
    after: Decimal

    @property
    def delta(self) -> Decimal:
        return self.after - self.before


def effects(entries: list[TBEntry], lines: list[AdjLine], structure: list[LineDef],
            rules: list[MappingRule]) -> list[LineEffect]:
    """Effet d'un ensemble d'ajustements sur chaque ligne des états, par le même moteur que les états publiés."""
    before = build_statements(entries, structure, rules).values()
    after = build_statements(adjust(entries, lines), structure, rules).values()
    out = []
    for d in sorted(structure, key=lambda d: (d.statement_type, d.order)):
        b = (before.get(d.code) or {}).get("net") or ZERO
        a = (after.get(d.code) or {}).get("net") or ZERO
        if a != b:
            out.append(LineEffect(d.statement_type, d.code, d.label, d.role, b, a))
    return out


def compare_to_materiality(amount: Decimal, overall: Decimal | None, trivial: Decimal | None) -> str | None:
    """Position d'un montant par rapport aux seuils approuvés (comparaison arithmétique ; la conclusion reste celle
    de l'auditeur)."""
    if overall is None:
        return None
    a = abs(amount)
    if trivial is not None and a < trivial:
        return "below_trivial"
    return "above_overall" if a >= overall else "below_overall"


# ============================================================ population depuis un fichier
@dataclass(frozen=True)
class ParsedItem:
    line_no: int
    reference: str
    item_date: object | None
    label: str | None
    account: str | None
    amount: Decimal


@dataclass
class PopulationParse:
    items: list[ParsedItem]
    issues: list[dict]

    @property
    def ok(self) -> bool:
        return bool(self.items) and not any(i["severity"] == "error" for i in self.issues)


def _parse_date(v: object):
    from datetime import date, datetime
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"date illisible « {s} »")


def parse_population(rows: list[list[object]], header_row: int, columns: dict[str, int | None],
                     decimal_separator: str | None = None) -> PopulationParse:
    """Lignes d'un fichier (après l'en-tête) → éléments de population. Toute ligne non vide dont le montant ou la
    date est illisible est une erreur : la population n'est pas créée partiellement."""
    from app.engines.importing.numbers import AmountError, parse_amount

    if columns.get("amount") is None or columns.get("reference") is None:
        raise ValueError("Colonnes « référence » et « montant » requises.")
    items: list[ParsedItem] = []
    issues: list[dict] = []

    def cell(r: list[object], key: str) -> object:
        idx = columns.get(key)
        return r[idx] if idx is not None and idx < len(r) else None

    for n, r in enumerate(rows[header_row + 1:], start=header_row + 2):
        if all(c is None or str(c).strip() == "" for c in r):
            continue
        ref = cell(r, "reference")
        try:
            amount = parse_amount(cell(r, "amount"), decimal_separator=decimal_separator)
        except AmountError as exc:
            issues.append({"severity": "error", "row": n, "message": f"montant illisible ({exc})"})
            continue
        if amount is None:
            issues.append({"severity": "error", "row": n, "message": "montant vide"})
            continue
        try:
            d = _parse_date(cell(r, "date"))
        except ValueError as exc:
            issues.append({"severity": "error", "row": n, "message": str(exc)})
            continue
        acc = cell(r, "account")
        acc_s = str(acc).strip().split(".")[0] if acc not in (None, "") else None
        if acc_s is not None and not acc_s.isdigit():
            issues.append({"severity": "error", "row": n, "message": f"numéro de compte non numérique « {acc_s} »"})
            continue
        label = cell(r, "label")
        items.append(ParsedItem(len(items) + 1, str(ref).strip() if ref not in (None, "") else f"L{n}", d,
                                str(label).strip() if label not in (None, "") else None, acc_s, amount))
    refs = [i.reference for i in items]
    if len(set(refs)) != len(refs):
        issues.append({"severity": "warning", "row": 0, "message": "références en double dans le fichier"})
    if not items:
        issues.append({"severity": "error", "row": 0, "message": "aucune ligne exploitable"})
    return PopulationParse(items, issues)
