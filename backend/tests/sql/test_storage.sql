-- =====================================================================
-- Tests des policies Storage (sql/0003_storage.sql).
-- psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/sql/test_storage.sql
-- =====================================================================
\set QUIET on
BEGIN;

CREATE OR REPLACE FUNCTION pg_temp.ok(cond boolean, label text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  IF cond IS DISTINCT FROM true THEN RAISE EXCEPTION 'ÉCHEC : %', label; END IF;
  RAISE NOTICE 'ok - %', label;
END $$;
CREATE OR REPLACE FUNCTION pg_temp.fails(q text, label text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  BEGIN EXECUTE q; EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'ok - % (refusé : %)', label, SQLERRM; RETURN; END;
  RAISE EXCEPTION 'ÉCHEC : % (aucune erreur levée)', label;
END $$;
CREATE OR REPLACE FUNCTION pg_temp.act_as(uid uuid) RETURNS void LANGUAGE sql AS $$
  SELECT set_config('request.jwt.claims', json_build_object('sub', uid, 'role', 'authenticated')::text, true);
$$;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA pg_temp TO authenticated;

INSERT INTO auth.users (id, email) VALUES
  ('a0000000-0000-0000-0000-00000000000a', 'alice@a.test'),
  ('b0000000-0000-0000-0000-00000000000b', 'bob@b.test'),
  ('c0000000-0000-0000-0000-00000000000c', 'carla@a.test');
INSERT INTO public.accounting_frameworks (id, code, name)
VALUES ('f0000000-0000-0000-0000-0000000000f1', 'TEST_FW', 'Référentiel de test');

SET LOCAL ROLE authenticated;
SELECT pg_temp.act_as('a0000000-0000-0000-0000-00000000000a');
INSERT INTO public.organizations (id, name, slug, created_by)
VALUES ('10000000-0000-0000-0000-00000000000a', 'Org A', 'org-a-st', 'a0000000-0000-0000-0000-00000000000a');
INSERT INTO public.organization_members (organization_id, user_id, role)
VALUES ('10000000-0000-0000-0000-00000000000a', 'c0000000-0000-0000-0000-00000000000c', 'member');
INSERT INTO public.companies (id, organization_id, name, framework_id, created_by) VALUES
  ('20000000-0000-0000-0000-0000000000a1', '10000000-0000-0000-0000-00000000000a', 'A1',
   'f0000000-0000-0000-0000-0000000000f1', 'a0000000-0000-0000-0000-00000000000a');
INSERT INTO public.company_members (organization_id, company_id, user_id, role) VALUES
  ('10000000-0000-0000-0000-00000000000a', '20000000-0000-0000-0000-0000000000a1',
   'c0000000-0000-0000-0000-00000000000c', 'viewer');

INSERT INTO storage.objects (bucket_id, name) VALUES
  ('financial-documents', '10000000-0000-0000-0000-00000000000a/20000000-0000-0000-0000-0000000000a1/balance-2025.xlsx');
SELECT pg_temp.ok(true, 'owner : dépôt d''un document dans son entreprise');

SELECT pg_temp.fails($q$INSERT INTO storage.objects (bucket_id, name)
  VALUES ('financial-documents', 'balance.xlsx')$q$, 'chemin hors convention refusé');
SELECT pg_temp.fails($q$INSERT INTO storage.objects (bucket_id, name)
  VALUES ('financial-documents', '99999999-0000-0000-0000-000000000000/20000000-0000-0000-0000-0000000000a1/x.xlsx')$q$,
  'organisation du chemin incohérente avec l''entreprise : refusé');
WITH u AS (UPDATE storage.objects SET name = name || '.bak' RETURNING 1)
SELECT pg_temp.ok((SELECT count(*) FROM u) = 0, 'document original non modifiable');
WITH d AS (DELETE FROM storage.objects WHERE bucket_id = 'financial-documents' RETURNING 1)
SELECT pg_temp.ok((SELECT count(*) FROM d) = 0, 'document original non supprimable côté client');

INSERT INTO storage.objects (bucket_id, name)
VALUES ('branding', '10000000-0000-0000-0000-00000000000a/logo.png');
SELECT pg_temp.ok(true, 'owner : dépôt du logo');

SELECT pg_temp.act_as('c0000000-0000-0000-0000-00000000000c');
SELECT pg_temp.ok((SELECT count(*) FROM storage.objects WHERE bucket_id = 'financial-documents') = 1,
                  'lecteur attribué : lit les documents de son entreprise');
SELECT pg_temp.fails($q$INSERT INTO storage.objects (bucket_id, name)
  VALUES ('financial-documents', '10000000-0000-0000-0000-00000000000a/20000000-0000-0000-0000-0000000000a1/y.pdf')$q$,
  'lecteur : dépôt refusé');
SELECT pg_temp.fails($q$INSERT INTO storage.objects (bucket_id, name)
  VALUES ('branding', '10000000-0000-0000-0000-00000000000a/autre.png')$q$, 'membre : logo refusé');

SELECT pg_temp.act_as('b0000000-0000-0000-0000-00000000000b');
SELECT pg_temp.ok((SELECT count(*) FROM storage.objects) = 0, 'autre tenant : aucun fichier visible');
SELECT pg_temp.fails($q$INSERT INTO storage.objects (bucket_id, name)
  VALUES ('financial-documents', '10000000-0000-0000-0000-00000000000a/20000000-0000-0000-0000-0000000000a1/z.pdf')$q$,
  'autre tenant : dépôt refusé');

RESET ROLE;
SELECT pg_temp.ok((SELECT bool_and(NOT public) FROM storage.buckets
                    WHERE id IN ('financial-documents','reports','branding')), 'tous les buckets sont privés');

ROLLBACK;
\echo 'Tous les tests Storage sont passés.'
