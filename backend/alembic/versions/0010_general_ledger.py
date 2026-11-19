"""Grand livre : imports d'écritures, grand livre actif de l'exercice, populations d'audit tirées des écritures.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-17
"""

from pathlib import Path

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    op.get_bind().exec_driver_sql((SQL_DIR / "0010_general_ledger.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raise RuntimeError("Retour arrière non pris en charge : restaurer une sauvegarde.")
