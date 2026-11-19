"""Années de test libres pour les versions de référentiel créées par les tests d'intégration."""

from __future__ import annotations

import random

from sqlalchemy import text


def free_year(framework_code: str, lo: int, hi: int) -> int:
    """Année de test dans [lo, hi) qu'aucune version du référentiel ne couvre encore.

    Les versions de test portent l'année dans leur libellé (unique par référentiel) et deux versions
    publiées ne peuvent pas se chevaucher : un tirage au hasard collisionnait d'un test à l'autre.
    """
    from app.db.session import engine  # import tardif : ce module est importé (indirectement) par des tests unitaires

    with engine.connect() as conn:
        taken = set(conn.execute(text(
            "SELECT DISTINCT y FROM public.framework_versions v "
            "JOIN public.accounting_frameworks f ON f.id = v.framework_id, "
            "LATERAL generate_series(extract(year FROM v.effective_from)::int, "
            "  extract(year FROM coalesce(v.effective_to - 1, v.effective_from))::int) AS y "
            "WHERE f.code = :code"), {"code": framework_code}).scalars())
    free = [y for y in range(lo, hi) if y not in taken]
    if not free:
        raise RuntimeError(f"Aucune année de test libre pour {framework_code} dans [{lo}, {hi}) : recréer la base (make test-sql).")
    return random.choice(free)
