-- =====================================================================
-- SHIM LOCAL — NE PAS EXÉCUTER SUR SUPABASE.
-- Reproduit le minimum fourni par Supabase (schéma auth, auth.uid(),
-- rôles anon / authenticated / service_role) pour le développement et
-- les tests sur un PostgreSQL standard.
-- =====================================================================
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon NOLOGIN NOINHERIT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    CREATE ROLE authenticated NOLOGIN NOINHERIT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    CREATE ROLE service_role NOLOGIN NOINHERIT BYPASSRLS;
  END IF;
END $$;

CREATE SCHEMA IF NOT EXISTS auth;

CREATE TABLE IF NOT EXISTS auth.users (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email       text UNIQUE,
  raw_user_meta_data jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- Même sémantique que Supabase : lit le claim "sub" du JWT de la requête.
CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT nullif(
    coalesce(
      current_setting('request.jwt.claim.sub', true),
      (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')
    ), '')::uuid
$$;

CREATE OR REPLACE FUNCTION auth.jwt() RETURNS jsonb
LANGUAGE sql STABLE AS $$
  SELECT coalesce(nullif(current_setting('request.jwt.claims', true), ''), '{}')::jsonb
$$;

GRANT USAGE ON SCHEMA auth TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION auth.uid(), auth.jwt() TO anon, authenticated, service_role;
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;

-- ---------------------------------------------------------------------
-- Storage (structure minimale compatible avec celle de Supabase)
-- ---------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS storage;

CREATE TABLE IF NOT EXISTS storage.buckets (
  id                 text PRIMARY KEY,
  name               text NOT NULL UNIQUE,
  public             boolean DEFAULT false,
  file_size_limit    bigint,
  allowed_mime_types text[],
  created_at         timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS storage.objects (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  bucket_id  text REFERENCES storage.buckets(id),
  name       text NOT NULL,
  owner      uuid,
  metadata   jsonb,
  created_at timestamptz DEFAULT now(),
  UNIQUE (bucket_id, name)
);
ALTER TABLE storage.objects ENABLE ROW LEVEL SECURITY;

-- Comme Supabase : dossiers du chemin, sans le nom de fichier.
CREATE OR REPLACE FUNCTION storage.foldername(name text) RETURNS text[]
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE _parts text[];
BEGIN
  SELECT string_to_array(name, '/') INTO _parts;
  RETURN _parts[1 : array_length(_parts, 1) - 1];
END $$;

GRANT USAGE ON SCHEMA storage TO anon, authenticated, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON storage.objects TO authenticated, service_role;
GRANT SELECT ON storage.buckets TO authenticated, service_role;
