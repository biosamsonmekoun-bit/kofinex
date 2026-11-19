"""Supabase Storage : buckets privés et policies d'accès par entreprise.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-17
"""

from pathlib import Path

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    op.get_bind().exec_driver_sql((SQL_DIR / "0003_storage.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
          IF to_regclass('storage.objects') IS NOT NULL THEN
            DROP POLICY IF EXISTS financial_documents_read ON storage.objects;
            DROP POLICY IF EXISTS financial_documents_upload ON storage.objects;
            DROP POLICY IF EXISTS reports_read ON storage.objects;
            DROP POLICY IF EXISTS reports_upload ON storage.objects;
            DROP POLICY IF EXISTS branding_read ON storage.objects;
            DROP POLICY IF EXISTS branding_write ON storage.objects;
            DROP POLICY IF EXISTS branding_delete ON storage.objects;
          END IF;
        END $$;
        DROP FUNCTION IF EXISTS authz.storage_object_company(text);
        DROP FUNCTION IF EXISTS authz.try_uuid(text);
    """)
