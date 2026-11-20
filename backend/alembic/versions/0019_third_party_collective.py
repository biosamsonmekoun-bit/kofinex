"""Plan tiers : rattachement obligatoire des tiers à un compte collectif (correctif du contrôle de gestion, phase 2).

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-20
"""

from pathlib import Path

from app.db.sql_files import run_sql_file

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    run_sql_file(SQL_DIR / "0019_third_party_collective.sql")


def downgrade() -> None:
    raise RuntimeError("Retour arrière non pris en charge : restaurer une sauvegarde.")
