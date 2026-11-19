"""Audit interne : plan annuel, cartographie, constats, recommandations, plans d'action, rapports.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-17
"""

from pathlib import Path

from app.db.sql_files import run_sql_file

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    run_sql_file(SQL_DIR / "0009_internal_audit.sql")


def downgrade() -> None:
    raise RuntimeError("Retour arrière non pris en charge : restaurer une sauvegarde.")
