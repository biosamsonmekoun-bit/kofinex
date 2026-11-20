"""Budget relié au plan comptable : types de budget, rubriques, mode de prévision, contrôle des comptes (phase 3).

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-20
"""

from pathlib import Path

from app.db.sql_files import run_sql_file

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    run_sql_file(SQL_DIR / "0020_budget_chart_link.sql")


def downgrade() -> None:
    raise RuntimeError("Retour arrière non pris en charge : restaurer une sauvegarde.")
