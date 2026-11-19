"""Environnement Alembic.

Le schéma est défini en SQL (sql/*.sql) car il repose sur des fonctionnalités
PostgreSQL que l'autogénération ne gère pas (RLS, policies, contraintes
d'exclusion, triggers). Les modèles SQLAlchemy reflètent ce schéma mais ne le
pilotent pas : toute évolution passe par une nouvelle révision.
"""

import os

from sqlalchemy import create_engine, pool

from alembic import context

config = context.config


def _url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL n'est pas défini")
    return url


def run_migrations_offline() -> None:
    context.configure(url=_url(), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, transaction_per_migration=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
