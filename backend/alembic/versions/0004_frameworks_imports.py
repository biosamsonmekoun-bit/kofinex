"""Référentiels versionnés (verrouillage, sources) et importation des balances (lignes de travail).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-17
"""

from pathlib import Path

from app.db.sql_files import run_sql_file

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    run_sql_file(SQL_DIR / "0004_frameworks_imports.sql")


def downgrade() -> None:
    raise RuntimeError("Retour arrière non pris en charge : restaurer une sauvegarde.")
