"""Schéma initial : tables, contraintes, index, triggers, RLS.

Revision ID: 0001
Revises:
Create Date: 2026-11-17
"""

from pathlib import Path

from app.db.sql_files import run_sql_file

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def _run(filename: str) -> None:
    # run_sql_file : fichier transmis sans paramètres (blocs DO $$ … $$, '%' et ':' littéraux)
    run_sql_file(SQL_DIR / filename)


def upgrade() -> None:
    _run("0001_core_schema.sql")
    _run("0002_rls_policies.sql")


def downgrade() -> None:
    raise RuntimeError(
        "Pas de retour arrière automatique pour le schéma initial : restaurer une sauvegarde."
    )
