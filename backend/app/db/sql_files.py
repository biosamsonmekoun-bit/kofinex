"""Exécution des fichiers SQL des migrations (`backend/sql/NNNN_*.sql`).

Le fichier est transmis tel quel au curseur psycopg, **sans paramètres** :
psycopg n'interprète alors aucun `%` (par exemple `format('%I', …)` dans les
blocs `DO $$ … $$`) et accepte plusieurs instructions dans un même envoi.
`exec_driver_sql` ne convient pas : SQLAlchemy y transmet un jeu de paramètres
vide, et psycopg lit chaque `%` comme un paramètre.

Le curseur utilise la connexion de la révision Alembic en cours : le fichier
s'exécute dans la même transaction.
"""

from pathlib import Path

from alembic import op


def run_sql_file(path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    driver_connection = op.get_bind().connection.driver_connection
    with driver_connection.cursor() as cursor:
        cursor.execute(sql)
