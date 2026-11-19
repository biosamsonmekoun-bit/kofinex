"""Contrôle de gestion : budgets (scénarios, circuit, gel), centres de coûts, modèles de coûts.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-17
"""

from pathlib import Path

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    op.get_bind().exec_driver_sql((SQL_DIR / "0006_management_control.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raise RuntimeError("Retour arrière non pris en charge : restaurer une sauvegarde.")
