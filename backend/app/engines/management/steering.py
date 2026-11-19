"""Pilotage : agrégats communs aux tableaux de bord financier, budgétaire, de trésorerie et de la masse salariale.

Fonctions pures, en Decimal. Aucune règle comptable n'est codée ici : la classification de chaque compte
(nature, AO / HAO, chiffre d'affaires, trésorerie, personnel, clients, fournisseurs, rubrique) est fournie par le
service à partir du référentiel publié (plan de comptes, structure du compte de résultat, concepts, correspondances).

Conventions :
- montant d'un compte de produit = crédit − débit ; d'une charge = débit − crédit ;
- les écritures d'à-nouveaux sont exclues des flux de la période ; elles ne servent qu'aux soldes d'ouverture ;
- une écriture dont toutes les lignes portent sur des comptes de trésorerie est un transfert interne : elle n'est
  ni un encaissement ni un décaissement ;
- les pourcentages d'un classement sont rapportés au total de la catégorie, pas au total du Top 10 ;
- une donnée absente vaut None, jamais zéro."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal("0.00")
HUNDRED = Decimal(100)


@dataclass(frozen=True)
class Movement:
    account: str
    entry_date: date
    debit: Decimal
    credit: Decimal
    entry_key: str
    is_opening: bool = False
    journal: str | None = None
    number: str | None = None
    piece: str | None = None
    label: str | None = None
    third_party: str | None = None  # identifiant du tiers (natif) ou compte auxiliaire (importé)
    third_party_label: str | None = None
    line_ref: str | None = None
    journal_type: str | None = None  # natif : bank, cash… (sinon None)


@dataclass(frozen=True)
class AccountClass:
    nature: str | None = None  # income | expense | asset | liability | equity | …
    group: str | None = None  # AO | HAO | OTHER (participation, impôt…) pour les comptes de gestion
    revenue: bool = False  # rattaché au chiffre d'affaires
    treasury: bool = False
    personnel: bool = False
    partner: str | None = None  # customer | supplier
    rubric: str | None = None  # code de la ligne du compte de résultat (ou du bilan)
    rubric_label: str | None = None
    label: str | None = None  # intitulé du compte


def pct(part: Decimal | None, total: Decimal | None) -> Decimal | None:
    if part is None or not total:
        return None
    return (part / total * HUNDRED).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def variation(cur: Decimal | None, prev: Decimal | None) -> Decimal | None:
    """(N − N-1) / |N-1| ; non calculée si N-1 est absent ou nul (convention KOFINEX-STD-1)."""
    if cur is None or prev is None or prev == 0:
        return None
    return ((cur - prev) / abs(prev) * HUNDRED).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def signed_pl(net_debit: Decimal, nature: str | None) -> Decimal:
    return -net_debit if nature == "income" else net_debit


# ------------------------------------------------------------------ classification d'après le référentiel
CONCEPT_SETS = {
    "ao": "resultat_activites_ordinaires",
    "hao": "resultat_hao",
    "net": "resultat_net",
    "revenue": "chiffre_affaires",
    "personnel": "charges_personnel",
    "treasury_a": "tresorerie_actif",
    "treasury_p": "tresorerie_passif",
    "customer": "creances_clients",
    "supplier": "dettes_fournisseurs",
}


def _leaves(code: str, structure: dict) -> set[str]:
    d = structure.get(code)
    if d is None:
        return set()
    if d.kind != "total":
        return {code}
    out: set[str] = set()
    for _, c in d.formula:
        out |= _leaves(c, structure)
    return out


def classify(
    accounts: set[str],
    chart: dict[str, tuple[str, str | None]],
    structure: list,
    rules: list,
    concepts: dict[str, dict],
    account_labels: dict[str, str] | None = None,
) -> tuple[dict[str, AccountClass], list[str]]:
    """Classe chaque compte d'après le référentiel : nature et intitulé (plan de comptes, racine la plus longue), lignes
    des états (correspondances, `statements._select`), puis appartenance aux lignes qui composent les concepts du
    référentiel (résultat des activités ordinaires, résultat HAO, résultat net, chiffre d'affaires, charges de personnel,
    trésorerie, créances clients, dettes fournisseurs). Aucun numéro de compte n'est codé ici."""
    from app.engines.accounting.statements import _select
    from app.engines.financial.expressions import references

    reserves: list[str] = []
    sdict = {d.code: d for d in structure}
    sets: dict[str, set[str]] = {}
    for key, concept in CONCEPT_SETS.items():
        ast = concepts.get(concept)
        if ast is None:
            sets[key] = set()
            reserves.append(f"Concept « {concept} » non rattaché dans le référentiel : indicateurs correspondants indisponibles.")
            continue
        sets[key] = set().union(set(), *[_leaves(c, sdict) for kind, c in references(ast) if kind == "line"])
    ao, hao, net = sets["ao"], sets["hao"], sets["net"]
    labels = account_labels or {}

    def chart_of(acc: str):
        for k in range(len(acc), 0, -1):
            if acc[:k] in chart:
                return chart[acc[:k]]
        return (None, None)

    out: dict[str, AccountClass] = {}
    for acc in accounts:
        lab, nat = chart_of(acc)
        try:
            lines = {r.line_code for r in _select(rules, acc)}
        except ValueError:
            lines = set()
            reserves.append(f"Compte {acc} : correspondances ambiguës dans le référentiel.")
        group = "AO" if lines & ao else "HAO" if lines & hao else "OTHER" if lines & net else None
        rubric = sorted(lines & (ao | hao | net)) or sorted(lines)
        out[acc] = AccountClass(
            nature=nat,
            group=group,
            revenue=bool(lines & sets["revenue"]),
            personnel=bool(lines & sets["personnel"]),
            treasury=bool(lines & (sets["treasury_a"] | sets["treasury_p"])),
            partner="customer" if lines & sets["customer"] else "supplier" if lines & sets["supplier"] else None,
            rubric=rubric[0] if rubric else None,
            rubric_label=sdict[rubric[0]].label if rubric and rubric[0] in sdict else None,
            label=labels.get(acc) or lab,
        )
    return out, sorted(set(reserves))


# ------------------------------------------------------------------ périodes
def fiscal_months(start: date, end: date) -> list[tuple[int, int, int]]:
    """(rang 1..n, année, mois) dans l'ordre réel de l'exercice, même décalé."""
    out, y, m, p = [], start.year, start.month, 1
    while (y, m) <= (end.year, end.month):
        out.append((p, y, m))
        p, m = p + 1, m + 1
        if m == 13:
            y, m = y + 1, 1
    return out


def month_bounds(y: int, m: int) -> tuple[date, date]:
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return date(y, m, 1), date.fromordinal(nxt.toordinal() - 1)


def period_range(
    start: date, end: date, view: str, month: int | None = None, custom: tuple[date, date] | None = None
) -> tuple[date, date]:
    """view : year (exercice), month (le mois de rang `month`), cumulative (début de l'exercice à la fin du mois `month`),
    custom (dates bornées à l'exercice)."""
    months = fiscal_months(start, end)
    if view == "year":
        return start, end
    if view in ("month", "cumulative"):
        if not month or not 1 <= month <= len(months):
            raise ValueError("Mois hors de l'exercice")
        _, y, m = months[month - 1]
        a, b = month_bounds(y, m)
        return (max(a, start) if view == "month" else start), min(b, end)
    if view == "custom" and custom:
        a, b = max(custom[0], start), min(custom[1], end)
        if a > b:
            raise ValueError("Période vide ou hors de l'exercice")
        return a, b
    raise ValueError("Vue de période inconnue")


def equivalent_range(rng: tuple[date, date], fy: tuple[date, date], prev: tuple[date, date]) -> tuple[date, date] | None:
    """Période équivalente de l'exercice précédent : même rang de mois et même jour (borné à la fin du mois),
    pour comparer mois avec mois, cumul avec cumul, année avec année, même si l'exercice est décalé."""
    if rng == fy:
        return prev
    cur, pm = fiscal_months(*fy), fiscal_months(*prev)

    def shift(d: date, is_end: bool) -> date | None:
        idx = next((p for p, y, m in cur if (y, m) == (d.year, d.month)), None)
        if idx is None or idx > len(pm):
            return None
        _, y, m = pm[idx - 1]
        a, b = month_bounds(y, m)
        last_of_month = d == month_bounds(d.year, d.month)[1]
        return b if is_end and last_of_month else min(date(y, m, min(d.day, b.day)), b)

    a, b = shift(rng[0], False), shift(rng[1], True)
    if a is None or b is None:
        return None
    return max(a, prev[0]), min(b, prev[1])


# ------------------------------------------------------------------ agrégats
def in_range(mv: Movement, rng: tuple[date, date]) -> bool:
    return not mv.is_opening and rng[0] <= mv.entry_date <= rng[1]


def nets(movs: list[Movement], rng: tuple[date, date]) -> dict[str, Decimal]:
    out: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for mv in movs:
        if in_range(mv, rng):
            out[mv.account] += mv.debit - mv.credit
    return dict(out)


@dataclass
class PL:
    produits_ao: Decimal = ZERO
    charges_ao: Decimal = ZERO
    produits_hao: Decimal = ZERO
    charges_hao: Decimal = ZERO
    autres_charges: Decimal = ZERO  # participation, impôt sur le résultat…
    autres_produits: Decimal = ZERO
    chiffre_affaires: Decimal = ZERO
    personnel: Decimal = ZERO
    unclassified: list[str] = field(default_factory=list)  # comptes de gestion hors AO / HAO / autres
    no_nature: list[str] = field(default_factory=list)

    @property
    def marge_ao(self) -> Decimal:
        return self.produits_ao - self.charges_ao

    @property
    def marge_hao(self) -> Decimal:
        return self.produits_hao - self.charges_hao

    @property
    def marge_totale(self) -> Decimal:
        return self.marge_ao + self.marge_hao

    @property
    def total_produits(self) -> Decimal:
        return self.produits_ao + self.produits_hao + self.autres_produits

    @property
    def total_charges(self) -> Decimal:
        return self.charges_ao + self.charges_hao + self.autres_charges

    @property
    def resultat(self) -> Decimal:
        return self.total_produits - self.total_charges


def pl(net: dict[str, Decimal], cls: dict[str, AccountClass]) -> PL:
    out = PL()
    for acc, nd in net.items():
        c = cls.get(acc) or AccountClass()
        if c.nature not in ("income", "expense"):
            if c.nature is None and nd:
                out.no_nature.append(acc)
            continue
        amt = signed_pl(nd, c.nature)
        inc = c.nature == "income"
        if c.group == "AO":
            if inc:
                out.produits_ao += amt
            else:
                out.charges_ao += amt
        elif c.group == "HAO":
            if inc:
                out.produits_hao += amt
            else:
                out.charges_hao += amt
        elif c.group == "OTHER":
            if inc:
                out.autres_produits += amt
            else:
                out.autres_charges += amt
        else:
            out.unclassified.append(acc)
            if inc:
                out.autres_produits += amt
            else:
                out.autres_charges += amt
        if c.revenue:
            out.chiffre_affaires += amt
        if c.personnel:
            out.personnel += amt
    out.unclassified.sort()
    out.no_nature.sort()
    return out


def monthly(
    movs: list[Movement], cls: dict[str, AccountClass], start: date, end: date, rng: tuple[date, date] | None = None
) -> list[dict]:
    """Série mensuelle de l'exercice (limitée à `rng` si fourni) : soldes AO / HAO, chiffre d'affaires, résultat."""
    out = []
    for p, y, m in fiscal_months(start, end):
        a, b = month_bounds(y, m)
        a, b = max(a, start), min(b, end)
        if rng and (b < rng[0] or a > rng[1]):
            continue
        s = pl(nets(movs, (a, b)), cls)
        out.append(
            {
                "period": p,
                "year": y,
                "month": m,
                "produits_ao": s.produits_ao,
                "charges_ao": s.charges_ao,
                "produits_hao": s.produits_hao,
                "charges_hao": s.charges_hao,
                "marge_ao": s.marge_ao,
                "marge_hao": s.marge_hao,
                "marge_totale": s.marge_totale,
                "chiffre_affaires": s.chiffre_affaires,
                "total_charges": s.total_charges,
                "total_produits": s.total_produits,
                "resultat": s.resultat,
                "personnel": s.personnel,
            }
        )
    return out


def top_accounts(net: dict[str, Decimal], cls: dict[str, AccountClass], *, group: str, nature: str, n: int = 10) -> dict:
    """Top des comptes d'une catégorie (AO / HAO, produits / charges). Pourcentage = part du total de la catégorie."""
    items = []
    for acc, nd in net.items():
        c = cls.get(acc)
        if c and c.group == group and c.nature == nature:
            amt = signed_pl(nd, nature)
            if amt:
                items.append({"key": acc, "label": c.label or acc, "rubric": c.rubric_label, "amount": amt})
    total = sum((i["amount"] for i in items), ZERO)
    items.sort(key=lambda i: (-i["amount"], i["key"]))
    for rank, i in enumerate(items, 1):
        i["rank"], i["share"] = rank, pct(i["amount"], total)
    return {"total": total, "items": items[:n], "count": len(items)}


def top_partners(
    movs: list[Movement], cls: dict[str, AccountClass], rng: tuple[date, date], kind: str, n: int = 10, basis: str = "revenue"
) -> dict:
    """`basis = "invoiced"` (présentation du modèle Excel de référence) : montants facturés, c'est-à-dire débits des comptes
    clients et crédits des comptes fournisseurs (TTC), à-nouveaux et contreparties de règlement exclus (un règlement crédite
    le compte client et débite le compte fournisseur : il n'est pas compté).

    `basis = "revenue"` (par défaut) : clients (kind = customer) : chiffre d'affaires des écritures qui portent sur un
    compte client et un seul tiers ;
    fournisseurs (supplier) : charges des écritures qui portent sur un compte fournisseur et un seul tiers.
    Les règlements, avances et transferts n'ont ni produit ni charge : ils n'entrent pas dans le classement.
    Les avoirs viennent en déduction (sens inverse). Écritures à plusieurs tiers : non attribuées, signalées."""
    if basis == "invoiced":
        return _top_partners_invoiced(movs, cls, rng, kind, n)
    nature = "income" if kind == "customer" else "expense"
    entries: dict[str, list[Movement]] = defaultdict(list)
    for mv in movs:
        if in_range(mv, rng):
            entries[mv.entry_key].append(mv)
    by: dict[str, dict] = {}
    total = unattributed = ZERO
    multi = 0
    for lines in entries.values():
        amount = ZERO
        for mv in lines:
            c = cls.get(mv.account)
            if c and c.nature == nature and (kind == "supplier" or c.revenue):
                amount += signed_pl(mv.debit - mv.credit, nature)
        if not amount:
            continue
        total += amount
        partners = {
            (mv.third_party, mv.third_party_label)
            for mv in lines
            if mv.third_party and (cls.get(mv.account) or AccountClass()).partner == kind
        }
        if len(partners) == 1:
            ((tp, lab),) = partners
            b = by.setdefault(tp, {"key": tp, "label": lab or tp, "amount": ZERO, "entries": 0})
            b["amount"] += amount
            b["entries"] += 1
        else:
            unattributed += amount
            multi += len(partners) > 1
    items = sorted((b for b in by.values() if b["amount"]), key=lambda b: (-b["amount"], b["key"]))
    for rank, i in enumerate(items, 1):
        i["rank"], i["share"] = rank, pct(i["amount"], total)
    return {
        "total": total,
        "attributed": total - unattributed,
        "unattributed": unattributed,
        "coverage": pct(total - unattributed, total),
        "multi_partner_entries": multi,
        "basis": "revenue",
        "items": items[:n],
        "count": len(items),
    }


def _top_partners_invoiced(movs: list[Movement], cls: dict[str, AccountClass], rng: tuple[date, date], kind: str, n: int) -> dict:
    by: dict[str, dict] = {}
    total = unattributed = ZERO
    for mv in movs:
        c = cls.get(mv.account)
        if not (c and c.partner == kind and in_range(mv, rng)):
            continue
        amount = mv.debit if kind == "customer" else mv.credit
        if not amount:
            continue
        total += amount
        if not mv.third_party:
            unattributed += amount
            continue
        b = by.setdefault(
            mv.third_party, {"key": mv.third_party, "label": mv.third_party_label or mv.third_party, "amount": ZERO, "entries": 0}
        )
        b["amount"] += amount
        b["entries"] += 1
    items = sorted((b for b in by.values() if b["amount"]), key=lambda b: (-b["amount"], b["key"]))
    for rank, i in enumerate(items, 1):
        i["rank"], i["share"] = rank, pct(i["amount"], total)
    return {
        "total": total,
        "attributed": total - unattributed,
        "unattributed": unattributed,
        "basis": "invoiced",
        "coverage": pct(total - unattributed, total),
        "multi_partner_entries": 0,
        "items": items[:n],
        "count": len(items),
    }


def treasury(movs: list[Movement], cls: dict[str, AccountClass], rng: tuple[date, date]) -> dict:
    """Trésorerie : solde initial (à-nouveaux + mouvements antérieurs), encaissements, décaissements (hors transferts
    internes), solde final ; contrôle solde final = initial + encaissements − décaissements ; catégories par
    contrepartie ; détail par compte de trésorerie."""
    entries: dict[str, list[Movement]] = defaultdict(list)
    for mv in movs:
        entries[mv.entry_key].append(mv)
    accounts: dict[str, dict] = {}
    cats_in: dict[str, Decimal] = defaultdict(lambda: ZERO)
    cats_out: dict[str, Decimal] = defaultdict(lambda: ZERO)
    transfers = ZERO
    months: dict[tuple[int, int], dict] = {}

    def acc(a: str, mv: Movement) -> dict:
        return accounts.setdefault(
            a,
            {
                "account": a,
                "label": (cls.get(a) or AccountClass()).label,
                "kind": mv.journal_type,
                "opening": ZERO,
                "receipts": ZERO,
                "payments": ZERO,
                "transfers": ZERO,
            },
        )

    for lines in entries.values():
        tre = [mv for mv in lines if (cls.get(mv.account) or AccountClass()).treasury]
        if not tre:
            continue
        internal = len(tre) == len(lines)
        others = [mv for mv in lines if mv not in tre]
        for mv in tre:
            a = acc(mv.account, mv)
            net = mv.debit - mv.credit
            if mv.is_opening or mv.entry_date < rng[0]:
                a["opening"] += net
                continue
            if mv.entry_date > rng[1]:
                continue
            if internal:
                a["transfers"] += net
                transfers += mv.debit  # montant transféré : compté une fois (côté débit)
                continue
            a["receipts"] += mv.debit
            a["payments"] += mv.credit
            key = (mv.entry_date.year, mv.entry_date.month)
            mo = months.setdefault(key, {"year": key[0], "month": key[1], "receipts": ZERO, "payments": ZERO})
            mo["receipts"] += mv.debit
            mo["payments"] += mv.credit
            cat = _category(others, cls)
            if mv.debit:
                cats_in[cat] += mv.debit
            if mv.credit:
                cats_out[cat] += mv.credit
    rows = sorted(accounts.values(), key=lambda a: a["account"])
    for a in rows:
        a["closing"] = a["opening"] + a["receipts"] - a["payments"] + a["transfers"]
    opening = sum((a["opening"] for a in rows), ZERO)
    receipts = sum((a["receipts"] for a in rows), ZERO)
    payments = sum((a["payments"] for a in rows), ZERO)
    closing = sum((a["closing"] for a in rows), ZERO)
    by_kind: dict[str, dict] = {}
    for a in rows:
        k = by_kind.setdefault(a["kind"] or "unknown", {"opening": ZERO, "closing": ZERO})
        k["opening"] += a["opening"]
        k["closing"] += a["closing"]
    return {
        "opening": opening,
        "receipts": receipts,
        "payments": payments,
        "closing": closing,
        "change": closing - opening,
        "internal_transfers": transfers,
        "check": closing == opening + receipts - payments,
        "accounts": rows,
        "by_kind": by_kind,
        "receipts_by_category": _cats(cats_in),
        "payments_by_category": _cats(cats_out),
        "monthly": [months[k] for k in sorted(months)],
    }


def _category(others: list[Movement], cls: dict[str, AccountClass]) -> str:
    labels = []
    for mv in others:
        c = cls.get(mv.account) or AccountClass()
        if c.partner == "customer":
            labels.append("Règlements clients")
        elif c.partner == "supplier":
            labels.append("Règlements fournisseurs")
        elif c.personnel:
            labels.append("Personnel")
        else:
            labels.append(c.rubric_label or c.label or mv.account)
    labels = sorted(set(labels))
    return labels[0] if len(labels) == 1 else ("Opérations mixtes" if labels else "Sans contrepartie")


def _cats(d: dict[str, Decimal]) -> list[dict]:
    total = sum(d.values(), ZERO)
    return [{"label": k, "amount": v, "share": pct(v, total)} for k, v in sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))]


def payroll(net: dict[str, Decimal], cls: dict[str, AccountClass], revenue: Decimal | None) -> dict:
    """Masse salariale agrégée à partir des comptes de charges de personnel du référentiel (pas de données individuelles)."""
    items = []
    for acc, nd in net.items():
        c = cls.get(acc)
        if c and c.personnel:
            amt = signed_pl(nd, "expense")
            if amt:
                items.append({"account": acc, "label": c.label or acc, "amount": amt})
    total = sum((i["amount"] for i in items), ZERO)
    items.sort(key=lambda i: (-i["amount"], i["account"]))
    for i in items:
        i["share"] = pct(i["amount"], total)
    return {"total": total, "items": items, "ratio_to_revenue": pct(total, revenue) if revenue else None}


# ------------------------------------------------------------------ budget : prévision, alertes, classements
@dataclass(frozen=True)
class Thresholds:
    consumption_info_pct: Decimal = Decimal(80)  # consommation d'un budget de charges ≥ ce taux : information
    overrun_warning_pct: Decimal = Decimal(100)  # dépassement : avertissement
    overrun_critical_pct: Decimal = Decimal(110)  # dépassement ≥ ce taux : critique
    pace_gap_points: Decimal = Decimal(15)  # consommation en avance sur le temps écoulé (points)
    under_execution_points: Decimal = Decimal(25)  # sous-exécution par rapport au temps écoulé (points)
    center_variance_pct: Decimal = Decimal(10)  # écart d'un centre, en % de son budget
    change_pct: Decimal = Decimal(10)  # variation N / N-1 jugée significative (analyse)
    concentration_pct: Decimal = Decimal(30)  # part du premier client / fournisseur jugée concentrée


def forecast(row: dict, elapsed: int, total: int) -> dict:
    """Prévision à terminaison d'une ligne budgétaire (extrapolations, jamais présentées comme comptabilisées) :
    - « réalisé + budget restant » : réalisé cumulé à fin du mois écoulé + budget des mois restants ;
    - « tendance » : réalisé cumulé / mois écoulés × mois de l'exercice.
    Sans réalisé mensuel, la prévision n'est pas calculée."""
    by_b, by_a = row.get("budget_by_period") or {}, row.get("actual_by_period")
    if by_a is None or elapsed < 1:
        return {"remaining_budget": None, "trend": None}
    annual = Decimal(str(by_b.get(0, by_b.get("0", 0))))
    monthly_b = {int(k): Decimal(str(v)) for k, v in by_b.items() if int(k) != 0}
    ytd = sum((Decimal(str(v)) for k, v in by_a.items() if 1 <= int(k) <= elapsed), ZERO)
    remain = sum((v for k, v in monthly_b.items() if k > elapsed), ZERO) + annual * Decimal(total - elapsed) / Decimal(total)
    return {
        "actual_to_date": ytd,
        "remaining_budget": (ytd + remain).quantize(Decimal("0.01")),
        "trend": (ytd / Decimal(elapsed) * Decimal(total)).quantize(Decimal("0.01")),
    }


def budget_alerts(rows: list[dict], elapsed: int, total: int, th: Thresholds) -> list[dict]:
    """Alertes budgétaires à seuils paramétrables. Charge : le dépassement est défavorable ; produit : l'insuffisance
    de recettes l'est. Taux de temps écoulé = mois écoulés / mois de l'exercice."""
    time_pct = Decimal(elapsed) / Decimal(total) * HUNDRED if total else None
    out = []

    def add(level, code, title, r, rate, detail):
        out.append(
            {
                "level": level,
                "code": code,
                "title": title,
                "label": r["label"],
                "account_prefix": r.get("account_prefix"),
                "cost_center_id": r.get("cost_center_id"),
                "budget": r["budget"],
                "actual": r["actual"],
                "rate": rate,
                "variance": r.get("variance"),
                "detail": detail,
            }
        )

    for r in rows:
        if r["actual"] is None:
            continue
        b, a = Decimal(str(r["budget"])), Decimal(str(r["actual"]))
        rate = pct(a, b)
        if r["nature"] == "charge":
            if rate is not None and rate >= th.overrun_critical_pct:
                add("critical", "overrun", "Dépassement du budget", r, rate, f"Réalisé à {rate} % du budget.")
            elif rate is not None and rate > th.overrun_warning_pct:
                add("warning", "overrun", "Dépassement du budget", r, rate, f"Réalisé à {rate} % du budget.")
            elif rate is not None and time_pct is not None and rate - time_pct >= th.pace_gap_points and elapsed < total:
                add(
                    "warning",
                    "fast_consumption",
                    "Consommation anormalement rapide",
                    r,
                    rate,
                    f"{rate} % du budget consommé pour {time_pct.quantize(Decimal('0.1'))} % de l'exercice écoulé.",
                )
            elif rate is not None and rate >= th.consumption_info_pct:
                add("info", "consumption", "Budget largement consommé", r, rate, f"{rate} % du budget consommé.")
            elif b > 0 and a == 0 and elapsed == total:
                add("info", "unused", "Budget non consommé", r, rate, "Aucune réalisation sur l'exercice.")
            if (
                (fc := forecast(r, elapsed, total)).get("trend") is not None
                and rate is not None
                and rate <= th.overrun_warning_pct
                and b > 0
                and fc["trend"] > b * th.overrun_warning_pct / HUNDRED
                and elapsed < total
            ):
                add(
                    "warning",
                    "overrun_risk",
                    "Risque de dépassement",
                    r,
                    rate,
                    f"Tendance à terminaison {fc['trend']} pour un budget de {b}.",
                )
        else:
            if rate is not None and time_pct is not None and time_pct - rate >= th.under_execution_points:
                add(
                    "warning",
                    "revenue_shortfall",
                    "Recettes en retrait",
                    r,
                    rate,
                    f"{rate} % du budget de recettes réalisé pour {time_pct.quantize(Decimal('0.1'))} % de l'exercice écoulé.",
                )
        if r.get("cost_center_id") and b and abs(a - b) / abs(b) * HUNDRED >= th.center_variance_pct:
            add(
                "warning" if (a > b) == (r["nature"] == "charge") else "info",
                "center_variance",
                "Écart important sur un centre",
                r,
                rate,
                f"Écart de {a - b} ({pct(a - b, b)} % du budget).",
            )
    order = {"critical": 0, "warning": 1, "info": 2}
    out.sort(key=lambda x: (order[x["level"]], -(abs(Decimal(str(x["variance"]))) if x["variance"] is not None else ZERO)))
    return out


def budget_tops(rows: list[dict], n: int = 10) -> dict:
    def var(r):
        return Decimal(str(r["variance"])) if r.get("variance") is not None else None

    acct = [r for r in rows if r["actual"] is not None and var(r) is not None]
    charges = [r for r in acct if r["nature"] == "charge" and not r.get("cost_center_id")]
    produits = [r for r in acct if r["nature"] == "produit" and not r.get("cost_center_id")]
    pick = lambda rs, key, rev=True: sorted(rs, key=key, reverse=rev)[:n]  # noqa: E731
    return {
        "overruns": pick([r for r in charges if var(r) > 0], var),
        "revenue_shortfalls": pick([r for r in produits if var(r) < 0], var, False),
        "savings": pick([r for r in charges if var(r) < 0], var, False),
        "most_consumed": pick(
            [r for r in charges if r.get("realization_pct") is not None], lambda r: Decimal(str(r["realization_pct"]))
        ),
        "centers": pick([r for r in acct if r.get("cost_center_id")], lambda r: abs(var(r))),
    }


def budget_monthly(rows: list[dict], months: list[tuple[int, int, int]], nature: str) -> list[dict]:
    """Tableau mensuel budget / réalisé / écart / taux pour une nature (charge ou produit), lignes par racine de comptes.
    Budget annuel (période 0) réparti également pour la lecture mensuelle (convention affichée)."""
    out = []
    rs = [r for r in rows if r["nature"] == nature and not r.get("cost_center_id")]
    for p, y, m in months:
        b = ZERO
        a: Decimal | None = ZERO
        for r in rs:
            bp = r.get("budget_by_period") or {}
            b += Decimal(str(bp.get(p, bp.get(str(p), 0)))) + Decimal(str(bp.get(0, bp.get("0", 0)))) / Decimal(len(months))
            ap = r.get("actual_by_period")
            if ap is None:
                a = None
            elif a is not None:
                a += Decimal(str(ap.get(p, ap.get(str(p), 0))))
        b = b.quantize(Decimal("0.01"))
        v = (a - b) if a is not None else None
        fav = None if v is None or v == 0 else (v < 0 if nature == "charge" else v > 0)
        out.append(
            {"period": p, "year": y, "month": m, "budget": b, "actual": a, "variance": v, "rate": pct(a, b), "favorable": fav}
        )
    return out


def insights(fin: dict, budget_alerts_: list[dict], tre: dict | None, pay: dict | None, th: Thresholds) -> list[dict]:
    """Points d'attention factuels pour la direction, chacun relié à son indicateur, sa valeur, sa référence, l'écart,
    la période et la source. Les seuils sont ceux de l'entreprise. Aucune cause n'est présumée."""
    out: list[dict] = []
    per = fin.get("period") or {}
    src = fin.get("source")

    def add(level, title, indicator, value, ref, detail, action):
        gap = (Decimal(str(value)) - Decimal(str(ref))) if value is not None and ref is not None else None
        out.append(
            {
                "level": level,
                "title": title,
                "indicator": indicator,
                "value": value,
                "reference": ref,
                "gap": gap,
                "period": per,
                "source": src,
                "detail": detail,
                "action": action,
            }
        )

    comp = fin.get("comparison") or {}
    if comp.get("available"):
        k, p, v = fin["kpis"], comp["kpis"], comp["variations"]

        def chg(key):
            return Decimal(str(v[key])) if v.get(key) is not None else None

        if (c := chg("total_charges")) is not None and c >= th.change_pct:
            add(
                "warning",
                "Hausse des charges",
                "total_charges",
                k["total_charges"],
                p["total_charges"],
                f"Charges en hausse de {c} % par rapport à la même période de {comp['fiscal_year']}.",
                "Examiner les comptes de charges dont la hausse est la plus forte (Top 10 des charges).",
            )
        if (c := chg("total_produits")) is not None and c <= -th.change_pct:
            add(
                "warning",
                "Baisse des produits",
                "total_produits",
                k["total_produits"],
                p["total_produits"],
                f"Produits en baisse de {abs(c)} % par rapport à la même période de {comp['fiscal_year']}.",
                "Examiner l'évolution du chiffre d'affaires par client et par compte de produits.",
            )
        if (
            Decimal(str(k["marge_ao"])) < Decimal(str(p["marge_ao"]))
            and (c := chg("marge_ao")) is not None
            and c <= -th.change_pct
        ):
            add(
                "warning",
                "Dégradation de la marge AO",
                "marge_ao",
                k["marge_ao"],
                p["marge_ao"],
                f"Marge AO en recul de {abs(c)} %.",
                "Comparer l'évolution des produits et des charges AO.",
            )
        if (c := chg("personnel")) is not None and c >= th.change_pct:
            add(
                "info",
                "Hausse de la masse salariale",
                "personnel",
                k["personnel"],
                p["personnel"],
                f"Charges de personnel en hausse de {c} %.",
                "Rapprocher de l'évolution du chiffre d'affaires et du budget.",
            )
    for key, label in (("clients", "clients"), ("fournisseurs", "fournisseurs")):
        t = (fin.get("tops") or {}).get(key) or {}
        items = t.get("items") or []
        if items and items[0].get("share") is not None and Decimal(str(items[0]["share"])) >= th.concentration_pct:
            add(
                "info",
                f"Concentration sur un seul {label[:-1]}",
                f"top_{key}",
                items[0]["amount"],
                t.get("total"),
                f"{items[0]['label']} représente {items[0]['share']} % du total.",
                "Évaluer la dépendance et le risque associé.",
            )
        if t.get("available") is False:
            add(
                "info",
                f"Données auxiliaires {label} manquantes",
                f"top_{key}",
                None,
                None,
                t.get("reason"),
                "Renseigner les tiers sur les comptes collectifs ou importer un grand livre avec comptes auxiliaires.",
            )
    if tre and tre.get("available") and Decimal(str(tre["change"])) < 0:
        add(
            "warning" if Decimal(str(tre["closing"])) < 0 else "info",
            "Dégradation de la trésorerie",
            "tresorerie",
            tre["closing"],
            tre["opening"],
            f"Variation de trésorerie de {tre['change']} sur la période.",
            "Examiner les décaissements par catégorie.",
        )
    for a in budget_alerts_[:20]:
        add(
            a["level"],
            a["title"],
            "budget",
            a["actual"],
            a["budget"],
            f"{a['label']} : {a['detail']}",
            "Ouvrir la ligne budgétaire et ses écritures.",
        )
    for r in (fin.get("reliability") or {}).get("reserves") or []:
        add("info", "Fiabilité des données", "qualite", None, None, r, "Compléter ou corriger la source avant de conclure.")
    order = {"critical": 0, "warning": 1, "info": 2}
    out.sort(key=lambda x: order[x["level"]])
    return out


def cumulate(months: list[dict], nature: str) -> list[dict]:
    """Vue cumulée du tableau mensuel budgétaire (Decimal) : budget, réalisé, écart, taux et appréciation cumulés depuis
    le début de l'exercice. Un réalisé mensuel absent rend le cumul absent à partir de ce mois."""
    out, b, a = [], ZERO, ZERO
    for m in months:
        b += Decimal(str(m["budget"]))
        a = None if a is None or m["actual"] is None else a + Decimal(str(m["actual"]))
        v = (a - b) if a is not None else None
        fav = None if v is None or v == 0 else (v < 0 if nature == "charge" else v > 0)
        out.append({**m, "budget": b, "actual": a, "variance": v, "rate": pct(a, b), "favorable": fav})
    return out


def with_changes(months: list[dict], key: str = "resultat") -> list[dict]:
    """Ajoute l'écart avec le mois précédent (`<key>_change`), en Decimal ; absent pour le premier mois."""
    prev = None
    out = []
    for m in months:
        cur = m.get(key)
        out.append({**m, f"{key}_change": (cur - prev) if cur is not None and prev is not None else None})
        prev = cur
    return out
