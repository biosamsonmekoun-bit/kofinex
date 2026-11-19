"""Comptabilité générale native (lot 3B, étapes A et B) : journaux, écritures, circuit, lettrage.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-18
"""

from pathlib import Path

from app.db.sql_files import run_sql_file

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    run_sql_file(SQL_DIR / "0014_native_accounting.sql")


def downgrade() -> None:
    raise RuntimeError("Retour arrière non pris en charge : restaurer une sauvegarde.")
