"""Audit interne : plan annuel, cartographie, constats, recommandations, plans d'action, rapports.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-17
"""

from pathlib import Path

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    op.get_bind().exec_driver_sql((SQL_DIR / "0009_internal_audit.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raise RuntimeError("Retour arrière non pris en charge : restaurer une sauvegarde.")
