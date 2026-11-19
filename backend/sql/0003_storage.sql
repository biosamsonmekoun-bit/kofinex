-- =====================================================================
-- KOFINEX — Migration 0003 : Supabase Storage
--
-- Buckets privés + policies sur storage.objects calquées sur les droits
-- d'entreprise. Convention de chemin (imposée) :
--     {organization_id}/{company_id}/{nom_de_fichier}
-- Les documents originaux sont immuables : aucune policy UPDATE, et pas de
-- DELETE côté client (suppression uniquement par le backend, journalisée).
-- Sans schéma storage (PostgreSQL nu, sans shim), la migration est ignorée.
-- =====================================================================

-- Résout l'entreprise désignée par un chemin d'objet, en vérifiant que
-- le 1er segment est bien l'organisation propriétaire de l'entreprise.
CREATE OR REPLACE FUNCTION authz.storage_object_company(p_name text) RETURNS uuid
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public AS $$
DECLARE
  parts   text[] := string_to_array(p_name, '/');
  uuid_re text   := '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$';
  result  uuid;
BEGIN
  IF coalesce(array_length(parts, 1), 0) < 3
     OR parts[1] !~ uuid_re OR parts[2] !~ uuid_re
     OR parts[array_length(parts, 1)] = '' THEN
    RETURN NULL;
  END IF;
  SELECT id INTO result FROM public.companies
   WHERE id = parts[2]::uuid AND organization_id = parts[1]::uuid;
  RETURN result;
END $$;

-- Conversion sans erreur (l'ordre d'évaluation des AND n'est pas garanti en SQL).
CREATE OR REPLACE FUNCTION authz.try_uuid(p text) RETURNS uuid
LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE WHEN p ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN p::uuid END
$$;

REVOKE ALL ON FUNCTION authz.storage_object_company(text), authz.try_uuid(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION authz.storage_object_company(text), authz.try_uuid(text) TO authenticated, service_role;

DO $outer$
BEGIN
  IF to_regclass('storage.buckets') IS NULL OR to_regclass('storage.objects') IS NULL THEN
    RAISE NOTICE 'Schéma storage absent : migration Storage ignorée';
    RETURN;
  END IF;

  INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types) VALUES
    ('financial-documents', 'financial-documents', false, 52428800, ARRAY[
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'application/vnd.ms-excel',
      'text/csv',
      'application/pdf']),
    ('reports', 'reports', false, 104857600, ARRAY[
      'application/pdf',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document']),
    ('branding', 'branding', false, 2097152, ARRAY['image/png', 'image/jpeg', 'image/svg+xml'])
  ON CONFLICT (id) DO UPDATE
    SET public = false,
        file_size_limit = EXCLUDED.file_size_limit,
        allowed_mime_types = EXCLUDED.allowed_mime_types;

  -- ------------------------------------------------ documents financiers
  EXECUTE $p$
    CREATE POLICY financial_documents_read ON storage.objects FOR SELECT TO authenticated
      USING (bucket_id = 'financial-documents'
             AND authz.can_access_company(authz.storage_object_company(name)))$p$;
  EXECUTE $p$
    CREATE POLICY financial_documents_upload ON storage.objects FOR INSERT TO authenticated
      WITH CHECK (bucket_id = 'financial-documents'
                  AND authz.has_company_role(authz.storage_object_company(name), ARRAY['accountant']))$p$;

  -- ------------------------------------------------ rapports générés
  EXECUTE $p$
    CREATE POLICY reports_read ON storage.objects FOR SELECT TO authenticated
      USING (bucket_id = 'reports'
             AND authz.can_access_company(authz.storage_object_company(name)))$p$;
  EXECUTE $p$
    CREATE POLICY reports_upload ON storage.objects FOR INSERT TO authenticated
      WITH CHECK (bucket_id = 'reports'
                  AND authz.has_company_role(authz.storage_object_company(name),
                                             ARRAY['accountant','controller','analyst']))$p$;

  -- ------------------------------------------------ logos (chemin {organization_id}/{fichier})
  EXECUTE $p$
    CREATE POLICY branding_read ON storage.objects FOR SELECT TO authenticated
      USING (bucket_id = 'branding'
             AND coalesce(authz.is_org_member(authz.try_uuid((storage.foldername(name))[1])), false))$p$;
  EXECUTE $p$
    CREATE POLICY branding_write ON storage.objects FOR INSERT TO authenticated
      WITH CHECK (bucket_id = 'branding'
                  AND authz.has_org_role(authz.try_uuid((storage.foldername(name))[1]), ARRAY['owner','admin']))$p$;
  EXECUTE $p$
    CREATE POLICY branding_delete ON storage.objects FOR DELETE TO authenticated
      USING (bucket_id = 'branding'
             AND authz.has_org_role(authz.try_uuid((storage.foldername(name))[1]), ARRAY['owner','admin']))$p$;
END
$outer$;
