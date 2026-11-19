"""Comptabilité générale native (lot 3B, étapes A et B) : journaux, écritures, circuit, lettrage.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-18
"""

from pathlib import Path

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    op.get_bind().exec_driver_sql((SQL_DIR / "0014_native_accounting.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raise RuntimeError("Retour arrière non pris en charge : restaurer une sauvegarde.")
