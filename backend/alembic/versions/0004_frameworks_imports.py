"""Référentiels versionnés (verrouillage, sources) et importation des balances (lignes de travail).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-17
"""

from pathlib import Path

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    op.get_bind().exec_driver_sql((SQL_DIR / "0004_frameworks_imports.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raise RuntimeError("Retour arrière non pris en charge : restaurer une sauvegarde.")
