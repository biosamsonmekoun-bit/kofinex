"""Audit financier : seuils, revue des comptes, échantillons, circularisations, anomalies et ajustements.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-17
"""

from pathlib import Path

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    op.get_bind().exec_driver_sql((SQL_DIR / "0008_financial_audit.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raise RuntimeError("Retour arrière non pris en charge : restaurer une sauvegarde.")
