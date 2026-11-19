"""Audit financier : seuils, revue des comptes, échantillons, circularisations, anomalies et ajustements.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-17
"""

from pathlib import Path

from app.db.sql_files import run_sql_file

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    run_sql_file(SQL_DIR / "0008_financial_audit.sql")


def downgrade() -> None:
    raise RuntimeError("Retour arrière non pris en charge : restaurer une sauvegarde.")
