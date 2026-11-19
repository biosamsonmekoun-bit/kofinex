"""Contrôle interne : référentiels, domaines, contrôles, matrice, exécutions, tests, évaluations, déficiences.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-18
"""

from pathlib import Path

from app.db.sql_files import run_sql_file

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    run_sql_file(SQL_DIR / "0011_internal_control.sql")


def downgrade() -> None:
    raise RuntimeError("Retour arrière non pris en charge : restaurer une sauvegarde.")
