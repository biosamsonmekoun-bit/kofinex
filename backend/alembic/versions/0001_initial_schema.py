"""Schéma initial : tables, contraintes, index, triggers, RLS.

Revision ID: 0001
Revises:
Create Date: 2026-11-17
"""

from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def _run(filename: str) -> None:
    # exec_driver_sql : le fichier contient des blocs DO $$ … $$ et des ':' littéraux
    op.get_bind().exec_driver_sql((SQL_DIR / filename).read_text(encoding="utf-8"))


def upgrade() -> None:
    _run("0001_core_schema.sql")
    _run("0002_rls_policies.sql")


def downgrade() -> None:
    raise RuntimeError(
        "Pas de retour arrière automatique pour le schéma initial : restaurer une sauvegarde."
    )
