"""Référentiels comptables pris en charge (identifiants uniquement).

Seuls les deux référentiels sont déclarés ici. Leurs versions, plans de comptes
et tables de correspondance seront chargés en phase 2 à partir des textes
officiels de l'OHADA, avec leur référence de source, puis publiés après
vérification. Aucune règle comptable n'est saisie dans cette migration.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-17
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO public.accounting_frameworks (code, name, description) VALUES
          ('SYSCOHADA_REV', 'SYSCOHADA révisé',
           'Système comptable OHADA annexé à l''Acte uniforme relatif au droit comptable et à l''information financière.'),
          ('SYSCEBNL', 'SYSCEBNL',
           'Système comptable OHADA des entités à but non lucratif.')
        ON CONFLICT (code) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM public.accounting_frameworks WHERE code IN ('SYSCOHADA_REV','SYSCEBNL')")
