"""Contrôle de gestion — pilotage : seuils d'alerte budgétaire par entreprise.

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-18
"""

from pathlib import Path

from app.db.sql_files import run_sql_file

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    run_sql_file(SQL_DIR / "0015_management_steering.sql")


def downgrade() -> None:
    raise RuntimeError("Retour arrière non pris en charge : restaurer une sauvegarde.")
