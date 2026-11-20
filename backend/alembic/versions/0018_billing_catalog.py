"""Lot 12A : catalogue commercial versionné, compte de facturation, abonnements (essai, résiliation).

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-20
"""

from pathlib import Path

from app.db.sql_files import run_sql_file

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    run_sql_file(SQL_DIR / "0018_billing_catalog.sql")


def downgrade() -> None:
    raise RuntimeError("Retour arrière non pris en charge : restaurer une sauvegarde.")
