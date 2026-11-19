"""Moteur financier : structure des états, concepts, bibliothèque de formules, analyses.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-17
"""

import json
from pathlib import Path

import sqlalchemy as sa

from alembic import op
from app.db.sql_files import run_sql_file

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    run_sql_file(SQL_DIR / "0005_financial_engine.sql")
    from app.engines.financial.library import library_rows

    stmt = sa.text("""
        INSERT INTO public.financial_formulas
          (organization_id, framework_id, code, version, name, category, expression, expression_ast, unit,
           rounding_scale, zero_division_policy, missing_input_policy, description, convention_notes,
           source_reference, status, library_version, published_at)
        VALUES (NULL, NULL, :code, :version, :name, :category, :expression, CAST(:expression_ast AS jsonb), :unit,
                :rounding_scale, :zero_division_policy, :missing_input_policy, :description, :convention_notes,
                :source_reference, :status, :library_version, now())
        ON CONFLICT DO NOTHING
    """)
    for row in library_rows():
        op.get_bind().execute(stmt, {**row, "expression_ast": json.dumps(row["expression_ast"])})


def downgrade() -> None:
    raise RuntimeError("Retour arrière non pris en charge : restaurer une sauvegarde.")
