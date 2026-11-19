"""Socle commun d'audit : méthodologies, missions, équipe, risques, programmes, feuilles, éléments probants, revue, signatures.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-17
"""

from pathlib import Path

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    op.get_bind().exec_driver_sql((SQL_DIR / "0007_audit_foundation.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raise RuntimeError("Retour arrière non pris en charge : restaurer une sauvegarde.")
