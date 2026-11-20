"""Plan de trésorerie : plans, rubriques, prévisions initiale et actualisée (phase 4).

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-20
"""

from pathlib import Path

from app.db.sql_files import run_sql_file

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    run_sql_file(SQL_DIR / "0021_treasury_plan.sql")


def downgrade() -> None:
    raise RuntimeError("Retour arrière non pris en charge : restaurer une sauvegarde.")
