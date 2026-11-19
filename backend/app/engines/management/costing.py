"""Coûts complets par la méthode des centres d'analyse (sections homogènes).

Étapes :
1. charges incorporables : racines de comptes de la balance (montants exacts), réparties par des clés
   saisies vers des centres ou directement vers des objets de coût (charges directes) ; charges
   supplétives saisies ; les charges de la balance non citées sont les charges non incorporées ;
2. répartition primaire vers les centres ;
3. répartition secondaire des centres auxiliaires, prestations réciproques comprises : système
   linéaire résolu exactement (fractions rationnelles) ;
4. imputation des centres principaux aux objets : par unités d'œuvre (coût de l'UO = total du centre /
   volume d'UO) ou par clés ; l'écart entre le coût du centre et le coût imputé est la différence
   d'imputation (sous- ou suractivité) ;
5. coût de revient par objet, coût unitaire, coût des quantités vendues, marge.
Contrôle : charges incorporées = coûts des objets + différences d'imputation.
Convention : coût des unités vendues = coût unitaire de l'exercice × quantité vendue (pas de stock
initial valorisé) ; le coût de la production non vendue est restitué à part.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, localcontext
from fractions import Fraction

from app.engines.management import HUNDRED, ZERO, ManagementError, div
from app.engines.management.actuals import BalanceRow, balance_amount, prefix_nature


def _d(v, what: str) -> Decimal:
    try:
        d = Decimal(str(v))
    except (ArithmeticError, ValueError, TypeError) as exc:
        raise ManagementError(f"{what} : nombre invalide « {v} ».") from exc
    if not d.is_finite():
        raise ManagementError(f"{what} : nombre invalide « {v} ».")
    return d


def _keys(keys: dict, what: str, allowed: set[str], exclude: str | None = None) -> dict[str, Decimal]:
    if not keys:
        raise ManagementError(f"{what} : aucune clé de répartition.")
    out = {}
    for target, pct in keys.items():
        if target not in allowed:
            raise ManagementError(f"{what} : destination « {target} » inconnue.")
        if target == exclude:
            raise ManagementError(f"{what} : un centre ne peut pas se répartir sur lui-même.")
        p = _d(pct, what)
        if p < 0:
            raise ManagementError(f"{what} : pourcentage négatif.")
        if p:
            out[target] = p
    total = sum(out.values(), ZERO)
    if total != HUNDRED:
        raise ManagementError(f"{what} : les clés totalisent {total} % au lieu de 100 %.")
    return out


def _to_dec(f: Fraction) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 34
        return Decimal(f.numerator) / Decimal(f.denominator)


def solve_reciprocal(primary: dict[str, Decimal], transfers: dict[str, dict[str, Decimal]]) -> dict[str, Decimal]:
    """Totaux des centres auxiliaires : T_a = P_a + Σ_b (k_ba / 100) × T_b, résolu exactement."""
    aux = list(primary)
    n = len(aux)
    idx = {a: i for i, a in enumerate(aux)}
    m = [[Fraction(0)] * (n + 1) for _ in range(n)]
    for a in aux:
        i = idx[a]
        m[i][i] += 1
        m[i][n] = Fraction(primary[a])
        for b, keys in transfers.items():
            if a in keys:
                m[i][idx[b]] -= Fraction(keys[a]) / 100
    for col in range(n):
        piv = next((r for r in range(col, n) if m[r][col] != 0), None)
        if piv is None:
            raise ManagementError("Prestations réciproques : le système n'a pas de solution unique (des centres "
                                  "auxiliaires se renvoient la totalité de leurs charges sans jamais en céder "
                                  "à un centre principal).")
        m[col], m[piv] = m[piv], m[col]
        p = m[col][col]
        m[col] = [x / p for x in m[col]]
        for r in range(n):
            if r != col and m[r][col] != 0:
                f = m[r][col]
                m[r] = [x - f * y for x, y in zip(m[r], m[col], strict=True)]
    return {a: _to_dec(m[idx[a]][n]) for a in aux}


@dataclass
class ObjectResult:
    code: str
    name: str
    quantity: Decimal
    sold_quantity: Decimal
    direct: Decimal = ZERO
    indirect: Decimal = ZERO
    detail: list[dict] = field(default_factory=list)
    revenue: Decimal | None = None

    @property
    def cost(self) -> Decimal:
        return self.direct + self.indirect

    @property
    def unit_cost(self) -> Decimal | None:
        return div(self.cost, self.quantity)

    @property
    def cost_of_sales(self) -> Decimal | None:
        u = self.unit_cost
        return None if u is None else u * self.sold_quantity

    @property
    def margin(self) -> Decimal | None:
        c = self.cost_of_sales
        return None if c is None or self.revenue is None else self.revenue - c


@dataclass
class FullCostResult:
    charges: list[dict]
    total_balance_charges: Decimal
    incorporated_from_balance: Decimal
    supplementary: Decimal
    non_incorporated: Decimal
    centers: list[dict]
    objects: list[ObjectResult]
    imputation_differences: dict[str, Decimal]
    check_difference: Decimal

    @property
    def total_incorporated(self) -> Decimal:
        return self.incorporated_from_balance + self.supplementary

    @property
    def analytical_result(self) -> Decimal | None:
        margins = [o.margin for o in self.objects]
        if any(m is None for m in margins):
            return None
        return sum(margins, ZERO) - sum(self.imputation_differences.values(), ZERO)


def full_cost(params: dict, balance: list[BalanceRow], chart_natures: dict[str, str | None]) -> FullCostResult:
    with localcontext() as ctx:
        ctx.prec = 34
        return _full_cost(params, balance, chart_natures)


def _full_cost(params: dict, balance: list[BalanceRow], chart_natures: dict[str, str | None]) -> FullCostResult:
    centers = params.get("centers") or []
    objects = params.get("objects") or []
    if not objects:
        raise ManagementError("Aucun objet de coût (produit, service, activité).")
    ccodes = [c["code"] for c in centers]
    ocodes = [o["code"] for o in objects]
    if len(set(ccodes)) != len(ccodes) or len(set(ocodes)) != len(ocodes) or set(ccodes) & set(ocodes):
        raise ManagementError("Les codes des centres et des objets doivent être uniques (et distincts entre eux).")
    kind = {c["code"]: c.get("kind") for c in centers}
    if any(k not in ("auxiliary", "main") for k in kind.values()):
        raise ManagementError("Type de centre inconnu (auxiliary ou main).")
    aux = [c for c in ccodes if kind[c] == "auxiliary"]
    main = [c for c in ccodes if kind[c] == "main"]
    targets = set(ccodes) | set(ocodes)

    # 1. charges incorporables
    rows = params.get("charges") or []
    prefixes = [(r["prefix"], tuple(r.get("exclusions") or ())) for r in rows]
    for i, (a, ex_a) in enumerate(prefixes):
        for j, (b, _) in enumerate(prefixes):
            if i != j and b.startswith(a) and not any(b.startswith(x) for x in ex_a):
                raise ManagementError(f"Les racines {a} et {b} se chevauchent : excluez {b} de la ligne {a}.")
    prim: dict[str, Decimal] = {c: ZERO for c in ccodes}
    obj = {o["code"]: ObjectResult(o["code"], o.get("name") or o["code"], _d(o.get("quantity", 0), f"Quantité {o['code']}"),
                                   _d(o.get("sold_quantity", o.get("quantity", 0)), f"Quantité vendue {o['code']}"))
           for o in objects}
    charges_out, from_balance = [], ZERO
    for r in rows:
        nature = prefix_nature(r["prefix"], chart_natures)
        if nature != "charge":
            raise ManagementError(f"Racine {r['prefix']} : seules des charges peuvent être incorporées.")
        amount = balance_amount(balance, r["prefix"], "charge", r.get("exclusions") or ())
        keys = _keys(r.get("keys") or {}, f"Charges {r['prefix']}", targets)
        from_balance += amount
        charges_out.append({"prefix": r["prefix"], "exclusions": r.get("exclusions") or [], "label": r.get("label"),
                            "amount": amount, "keys": keys})
        for t, pct in keys.items():
            share = amount * pct / HUNDRED
            if t in prim:
                prim[t] += share
            else:
                obj[t].direct += share
                obj[t].detail.append({"source": f"compte {r['prefix']}", "amount": share, "type": "direct"})
    supp_total = ZERO
    for s in params.get("supplementary") or []:
        amount = _d(s.get("amount"), f"Charge supplétive « {s.get('label')} »")
        keys = _keys(s.get("keys") or {}, f"Charge supplétive « {s.get('label')} »", targets)
        supp_total += amount
        for t, pct in keys.items():
            share = amount * pct / HUNDRED
            if t in prim:
                prim[t] += share
            else:
                obj[t].direct += share
                obj[t].detail.append({"source": f"supplétive {s.get('label')}", "amount": share, "type": "direct"})

    # 2-3. répartition secondaire (prestations réciproques)
    sec = {s["from"]: s for s in params.get("secondary") or []}
    transfers: dict[str, dict[str, Decimal]] = {}
    for a in aux:
        if a not in sec:
            raise ManagementError(f"Centre auxiliaire {a} : clés de répartition secondaire manquantes.")
        transfers[a] = _keys(sec[a].get("keys") or {}, f"Répartition du centre {a}", set(ccodes), exclude=a)
    for f in sec:
        if f not in aux:
            raise ManagementError(f"Répartition secondaire depuis {f} : seuls les centres auxiliaires se répartissent.")
    aux_total = solve_reciprocal({a: prim[a] for a in aux}, transfers) if aux else {}
    total = dict(prim)
    for a, ta in aux_total.items():
        for t, pct in transfers[a].items():
            if t in main:
                total[t] += ta * pct / HUNDRED

    # 4. imputation des centres principaux
    usage: dict[tuple[str, str], Decimal] = {}
    for u in params.get("usage") or []:
        if u["object"] not in obj or u["center"] not in main:
            raise ManagementError(f"Consommation d'unités d'œuvre : objet {u['object']} ou centre {u['center']} inconnu.")
        usage[(u["object"], u["center"])] = usage.get((u["object"], u["center"]), ZERO) + \
            _d(u.get("quantity"), f"UO {u['object']}/{u['center']}")
    centers_out, diffs = [], {}
    by_code = {c["code"]: c for c in centers}
    for c in ccodes:
        info = {"code": c, "name": by_code[c].get("name") or c, "kind": kind[c], "primary": prim[c]}
        if c in aux:
            info.update(total=aux_total[c], transfers=transfers[c])
            centers_out.append(info)
            continue
        alloc = by_code[c].get("allocation") or {}
        info["total"] = total[c]
        if alloc.get("type") == "work_unit":
            volume = _d(alloc.get("volume"), f"Volume d'UO du centre {c}")
            if volume <= 0:
                raise ManagementError(f"Centre {c} : le volume d'unités d'œuvre doit être positif.")
            cost_uo = div(total[c], volume)
            imputed = ZERO
            for (o, cc), qty in usage.items():
                if cc == c:
                    share = qty * cost_uo
                    obj[o].indirect += share
                    obj[o].detail.append({"source": f"centre {c}", "uo": qty, "amount": share, "type": "indirect"})
                    imputed += share
            info.update(unit=alloc.get("unit"), volume=volume, cost_per_unit=cost_uo, imputed=imputed,
                        used_volume=sum((q for (o, cc), q in usage.items() if cc == c), ZERO))
            diffs[c] = total[c] - imputed
        elif alloc.get("type") == "keys":
            keys = _keys(alloc.get("keys") or {}, f"Imputation du centre {c}", set(ocodes))
            for o, pct in keys.items():
                share = total[c] * pct / HUNDRED
                obj[o].indirect += share
                obj[o].detail.append({"source": f"centre {c}", "amount": share, "type": "indirect"})
            info.update(keys=keys, imputed=total[c])
            diffs[c] = ZERO
        else:
            raise ManagementError(f"Centre principal {c} : choisissez une imputation par unités d'œuvre ou par clés.")
        centers_out.append(info)

    # 5. produits et marges
    for o in objects:
        r = obj[o["code"]]
        if o.get("revenue_prefix"):
            if prefix_nature(o["revenue_prefix"], chart_natures) != "produit":
                raise ManagementError(f"Objet {o['code']} : la racine de chiffre d'affaires doit être un compte de produits.")
            r.revenue = balance_amount(balance, o["revenue_prefix"], "produit")
        elif o.get("revenue") not in (None, ""):
            r.revenue = _d(o["revenue"], f"Chiffre d'affaires {o['code']}")
        if r.sold_quantity > r.quantity:
            raise ManagementError(f"Objet {o['code']} : la quantité vendue dépasse la quantité produite.")
    rev_prefixes = [o["revenue_prefix"] for o in objects if o.get("revenue_prefix")]
    for i, a in enumerate(rev_prefixes):
        for j, b in enumerate(rev_prefixes):
            if i != j and b.startswith(a):
                raise ManagementError(f"Chiffre d'affaires : les racines {a} et {b} se chevauchent.")

    all_charges = sum((r.net_debit for r in balance
                       if _is_charge(r.account, chart_natures)), ZERO)
    total_inc = from_balance + supp_total
    absorbed = sum((o.cost for o in obj.values()), ZERO) + sum(diffs.values(), ZERO)
    return FullCostResult(charges_out, all_charges, from_balance, supp_total, all_charges - from_balance,
                          centers_out, list(obj.values()), diffs, total_inc - absorbed)


def _is_charge(account: str, natures: dict[str, str | None]) -> bool:
    for k in range(len(account), 0, -1):
        n = natures.get(account[:k])
        if n:
            return n == "charge"
    return False
