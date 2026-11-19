"""Types des états financiers : alignement de financial_statements sur la structure des états (migration 0005).

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-19
"""

from pathlib import Path

from app.db.sql_files import run_sql_file

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    run_sql_file(SQL_DIR / "0017_financial_statement_types.sql")


def downgrade() -> None:
    raise RuntimeError("Retour arrière non pris en charge : restaurer une sauvegarde.")
