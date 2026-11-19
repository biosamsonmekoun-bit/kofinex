"""Intelligence artificielle : acteur IA, réglages, suggestions, provenance, sorties figées.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-18
"""

from pathlib import Path

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    op.get_bind().exec_driver_sql((SQL_DIR / "0012_ai.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raise RuntimeError("Retour arrière non pris en charge : restaurer une sauvegarde.")
