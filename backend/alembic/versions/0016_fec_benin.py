"""Comptabilité — Fichier des Écritures Comptables (FEC) DGI Bénin : historique immuable et traçabilité.

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-19
"""

from pathlib import Path

from app.db.sql_files import run_sql_file

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    run_sql_file(SQL_DIR / "0016_fec_benin.sql")


def downgrade() -> None:
    raise RuntimeError("Retour arrière non pris en charge : restaurer une sauvegarde.")
