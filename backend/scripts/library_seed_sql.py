"""Génère le SQL d'insertion de la bibliothèque standard (bases sans Alembic, tests SQL)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engines.financial.library import library_rows  # noqa: E402


def lit(v):
    if v is None:
        return "NULL"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, dict | list):
        v = json.dumps(v)
    return "'" + str(v).replace("'", "''") + "'"


cols = ["code", "version", "name", "category", "expression", "expression_ast", "unit", "rounding_scale",
        "zero_division_policy", "missing_input_policy", "description", "convention_notes", "source_reference",
        "status", "library_version"]
for r in library_rows():
    vals = ", ".join(lit(r[c]) + ("::jsonb" if c == "expression_ast" else "") for c in cols)
    # outil local (base de test) : colonnes fixes, valeurs échappées par lit() ; aucune entrée utilisateur
    print(f"INSERT INTO public.financial_formulas ({', '.join(cols)}, published_at) VALUES ({vals}, now());")  # noqa: S608
