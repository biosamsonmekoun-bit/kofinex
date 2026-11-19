"""Contrôle interne : référentiels, domaines, contrôles, matrice, exécutions, tests, évaluations, déficiences.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-18
"""

from pathlib import Path

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    op.get_bind().exec_driver_sql((SQL_DIR / "0011_internal_control.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raise RuntimeError("Retour arrière non pris en charge : restaurer une sauvegarde.")
