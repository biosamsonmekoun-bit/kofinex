"""Écarts sur coûts préétablis (standards), élément par élément.

Pour une production réelle Pr :
  quantité préétablie de la production réelle Qs = quantité standard unitaire × Pr ;
  écart global = Qr × Cr − Qs × Cs ;
  écart sur quantité = (Qr − Qs) × Cs ;  écart sur prix (coût unitaire) = (Cr − Cs) × Qr ;
  écart global = écart sur quantité + écart sur prix (vérifié).
Convention de signe : un écart positif est défavorable (le réel coûte plus que le préétabli).
"""

from __future__ import annotations

from decimal import Decimal

from app.engines.management import ZERO, ManagementError
from app.engines.management.costing import _d


def standard_variances(params: dict) -> dict:
    output = _d(params.get("actual_output"), "Production réelle")
    if output <= 0:
        raise ManagementError("La production réelle doit être positive.")
    budget_output = params.get("budgeted_output")
    rows, totals = [], {"standard_cost": ZERO, "actual_cost": ZERO, "quantity": ZERO, "price": ZERO, "total": ZERO}
    for e in params.get("elements") or []:
        name = e.get("label") or "élément"
        qs_u = _d(e.get("standard_quantity_per_unit"), f"{name} : quantité standard")
        cs = _d(e.get("standard_unit_cost"), f"{name} : coût standard")
        qr = _d(e.get("actual_quantity"), f"{name} : quantité réelle")
        cr = _d(e.get("actual_unit_cost"), f"{name} : coût réel")
        qs = qs_u * output
        ev_q = (qr - qs) * cs
        ev_p = (cr - cs) * qr
        total = qr * cr - qs * cs
        if total != ev_q + ev_p:                # identité algébrique : ne peut échouer qu'en cas de bug
            raise ManagementError("Écarts incohérents.")
        rows.append({"label": name, "unit": e.get("unit"), "standard_quantity": qs, "standard_unit_cost": cs,
                     "actual_quantity": qr, "actual_unit_cost": cr, "standard_cost": qs * cs, "actual_cost": qr * cr,
                     "quantity_variance": ev_q, "price_variance": ev_p, "total_variance": total})
        totals["standard_cost"] += qs * cs
        totals["actual_cost"] += qr * cr
        totals["quantity"] += ev_q
        totals["price"] += ev_p
        totals["total"] += total
    if not rows:
        raise ManagementError("Aucun élément de coût.")
    return {"actual_output": output, "budgeted_output": Decimal(str(budget_output)) if budget_output not in (None, "") else None,
            "elements": rows, "totals": totals}
