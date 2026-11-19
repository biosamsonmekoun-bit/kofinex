"""Reporting : modèles versionnés, documents générés figés, sources validées.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-18
"""

from pathlib import Path

from app.db.sql_files import run_sql_file

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    run_sql_file(SQL_DIR / "0013_reporting.sql")


def downgrade() -> None:
    raise RuntimeError("Retour arrière non pris en charge : restaurer une sauvegarde.")
