-- =====================================================================
-- Tests migration 0016 : FEC DGI Bénin — historique immuable, nommage (art. 6), séparateurs (art. 4), versions,
-- auteur, traçabilité vers les écritures validées, RLS (comptables et administrateurs), isolation, acteur IA, stockage.
-- Données FICTIVES.
-- =====================================================================
\set QUIET on
BEGIN;
CREATE OR REPLACE FUNCTION pg_temp.ok(cond boolean, label text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN IF cond IS DISTINCT FROM true THEN RAISE EXCEPTION 'ÉCHEC : %', label; END IF; RAISE NOTICE 'ok - %', label; END $$;
CREATE OR REPLACE FUNCTION pg_temp.fails(q text, label text, pattern text DEFAULT NULL) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  BEGIN EXECUTE q;
  EXCEPTION WHEN OTHERS THEN
    IF pattern IS NOT NULL AND SQLERRM NOT ILIKE '%' || pattern || '%' THEN RAISE EXCEPTION 'ÉCHEC : % (%)', label, SQLERRM; END IF;
    RAISE NOTICE 'ok - % (refusé : %)', label, SQLERRM; RETURN;
  END;
  RAISE EXCEPTION 'ÉCHEC : % (aucune erreur levée)', label;
END $$;
CREATE OR REPLACE FUNCTION pg_temp.act_as(uid uuid) RETURNS void LANGUAGE sql AS $$
  SELECT set_config('request.jwt.claims', json_build_object('sub', uid, 'role', 'authenticated')::text, true);
$$;
-- insertion d'une génération (valeurs par défaut cohérentes ; chaque test en fait varier une)
CREATE OR REPLACE FUNCTION pg_temp.fec(
  p_version int, p_by uuid DEFAULT 'e3000000-0000-0000-0000-00000000000d', p_filename text DEFAULT 'FEC_3201900000001_20251231.txt',
  p_parts jsonb DEFAULT NULL, p_kind text DEFAULT 'working', p_blocking int DEFAULT 0, p_compliance text DEFAULT 'spec_pending',
  p_lines int DEFAULT 2, p_sep text DEFAULT 'tab', p_eol text DEFAULT 'crlf', p_confirmed boolean DEFAULT false,
  p_company uuid DEFAULT '2e000000-0000-0000-0000-00000000000a', p_start date DEFAULT '2025-01-01') RETURNS uuid
LANGUAGE plpgsql AS $$
DECLARE v_id uuid := gen_random_uuid();
  v_root text := '1e000000-0000-0000-0000-00000000000a/' || p_company || '/';
BEGIN
  INSERT INTO public.fec_exports (id, organization_id, company_id, fiscal_year_id, version_no, kind, period_start, period_end, ifu,
    filename, file_format, encoding, field_separator, record_separator, accounting_type, line_count, entry_count, total_debit,
    total_credit, blocking_count, warning_count, compliance, spec_version, spec_confirmed, parts, size_bytes, sha256,
    doc_storage_path, doc_sha256, generator_version, generated_by)
  VALUES (v_id, '1e000000-0000-0000-0000-00000000000a', p_company, '3e000000-0000-0000-0000-00000000000a', p_version, p_kind,
    p_start, '2025-12-31', '3201900000001', p_filename, 'txt', 'iso-8859-15', p_sep, p_eol, 'accrual', p_lines, 1, 100, 100,
    p_blocking, 0, p_compliance, 'test', p_confirmed,
    coalesce(p_parts, jsonb_build_array(jsonb_build_object('part', null, 'filename', p_filename, 'storage_path',
      v_root || v_id || '/' || p_filename, 'size_bytes', 10, 'sha256', repeat('a', 64), 'line_count', p_lines))),
    10, repeat('b', 64), v_root || v_id || '/DOC.txt', repeat('c', 64), 'test', p_by);
  RETURN v_id;
END $$;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA pg_temp TO authenticated;

INSERT INTO auth.users (id, email) VALUES
  ('e3000000-0000-0000-0000-00000000000a', 'own@fec.test'), ('e3000000-0000-0000-0000-00000000000c', 'ctrl@fec.test'),
  ('e3000000-0000-0000-0000-00000000000d', 'acc@fec.test'), ('e3000000-0000-0000-0000-00000000000e', 'acc2@fec.test'),
  ('e3000000-0000-0000-0000-00000000000b', 'out@fex.test');
INSERT INTO public.accounting_frameworks (id, code, name) VALUES ('f3000000-0000-0000-0000-0000000000fa', 'TEST_FEC', 'Test');
SET LOCAL session_replication_role = replica;
INSERT INTO public.profiles (id, email) SELECT id, email FROM auth.users WHERE email LIKE '%@fe_.test' ON CONFLICT DO NOTHING;
INSERT INTO public.organizations (id, name, slug, created_by) VALUES
  ('1e000000-0000-0000-0000-00000000000a', 'Org FEC', 'org-fec', 'e3000000-0000-0000-0000-00000000000a'),
  ('1e000000-0000-0000-0000-00000000000b', 'Org FEX', 'org-fex', 'e3000000-0000-0000-0000-00000000000b');
INSERT INTO public.organization_members (organization_id, user_id, role) VALUES
  ('1e000000-0000-0000-0000-00000000000a', 'e3000000-0000-0000-0000-00000000000a', 'owner'),
  ('1e000000-0000-0000-0000-00000000000a', 'e3000000-0000-0000-0000-00000000000c', 'member'),
  ('1e000000-0000-0000-0000-00000000000a', 'e3000000-0000-0000-0000-00000000000d', 'member'),
  ('1e000000-0000-0000-0000-00000000000a', 'e3000000-0000-0000-0000-00000000000e', 'member'),
  ('1e000000-0000-0000-0000-00000000000b', 'e3000000-0000-0000-0000-00000000000b', 'owner');
INSERT INTO public.companies (id, organization_id, name, framework_id, created_by, tax_id, country_code) VALUES
  ('2e000000-0000-0000-0000-00000000000a', '1e000000-0000-0000-0000-00000000000a', 'Entité FEC', 'f3000000-0000-0000-0000-0000000000fa',
   'e3000000-0000-0000-0000-00000000000a', '3201900000001', 'BJ'),
  ('2e000000-0000-0000-0000-00000000000b', '1e000000-0000-0000-0000-00000000000a', 'Entité FEC 2', 'f3000000-0000-0000-0000-0000000000fa',
   'e3000000-0000-0000-0000-00000000000a', '3201900000002', 'BJ');
INSERT INTO public.company_members (organization_id, company_id, user_id, role) VALUES
  ('1e000000-0000-0000-0000-00000000000a', '2e000000-0000-0000-0000-00000000000a', 'e3000000-0000-0000-0000-00000000000c', 'controller'),
  ('1e000000-0000-0000-0000-00000000000a', '2e000000-0000-0000-0000-00000000000a', 'e3000000-0000-0000-0000-00000000000d', 'accountant'),
  ('1e000000-0000-0000-0000-00000000000a', '2e000000-0000-0000-0000-00000000000b', 'e3000000-0000-0000-0000-00000000000e', 'accountant');
INSERT INTO public.fiscal_years (id, organization_id, company_id, label, start_date, end_date, created_by) VALUES
  ('3e000000-0000-0000-0000-00000000000a', '1e000000-0000-0000-0000-00000000000a', '2e000000-0000-0000-0000-00000000000a', '2025',
   '2025-01-01', '2025-12-31', 'e3000000-0000-0000-0000-00000000000a');
INSERT INTO public.journals (id, organization_id, company_id, code, label, journal_type, number_prefix, created_by) VALUES
  ('4e000000-0000-0000-0000-00000000000a', '1e000000-0000-0000-0000-00000000000a', '2e000000-0000-0000-0000-00000000000a', 'VT',
   'Ventes', 'sales', 'VT', 'e3000000-0000-0000-0000-00000000000a');
INSERT INTO public.journal_entries (id, organization_id, company_id, fiscal_year_id, journal_id, entry_date, piece_ref, piece_date,
  label, status, number, sequence_no, total_debit, total_credit, line_count, created_by, validated_by, validated_at) VALUES
  ('5e000000-0000-0000-0000-00000000000a', '1e000000-0000-0000-0000-00000000000a', '2e000000-0000-0000-0000-00000000000a',
   '3e000000-0000-0000-0000-00000000000a', '4e000000-0000-0000-0000-00000000000a', '2025-03-01', 'F001', '2025-03-01',
   'Facture F001', 'validated', 'VT-000001', 1, 100, 100, 2, 'e3000000-0000-0000-0000-00000000000d',
   'e3000000-0000-0000-0000-00000000000a', '2025-03-01 10:00+00'),
  ('5e000000-0000-0000-0000-00000000000b', '1e000000-0000-0000-0000-00000000000a', '2e000000-0000-0000-0000-00000000000a',
   '3e000000-0000-0000-0000-00000000000a', '4e000000-0000-0000-0000-00000000000a', '2025-03-02', 'F002', '2025-03-02',
   'Facture F002 (brouillon)', 'draft', NULL, NULL, 50, 50, 2, 'e3000000-0000-0000-0000-00000000000d', NULL, NULL);
INSERT INTO public.journal_entry_lines (id, organization_id, company_id, fiscal_year_id, entry_id, line_no, account_number, debit, credit) VALUES
  ('6e000000-0000-0000-0000-00000000000a', '1e000000-0000-0000-0000-00000000000a', '2e000000-0000-0000-0000-00000000000a',
   '3e000000-0000-0000-0000-00000000000a', '5e000000-0000-0000-0000-00000000000a', 1, '411100', 100, 0),
  ('6e000000-0000-0000-0000-00000000000b', '1e000000-0000-0000-0000-00000000000a', '2e000000-0000-0000-0000-00000000000a',
   '3e000000-0000-0000-0000-00000000000a', '5e000000-0000-0000-0000-00000000000a', 2, '701100', 0, 100),
  ('6e000000-0000-0000-0000-00000000000c', '1e000000-0000-0000-0000-00000000000a', '2e000000-0000-0000-0000-00000000000a',
   '3e000000-0000-0000-0000-00000000000a', '5e000000-0000-0000-0000-00000000000b', 1, '411100', 50, 0);
SET LOCAL session_replication_role = origin;
SET LOCAL ROLE authenticated;

-- ------------------------------------------------------------------ droits
SELECT pg_temp.act_as('e3000000-0000-0000-0000-00000000000c');
SELECT pg_temp.fails($q$SELECT pg_temp.fec(1, 'e3000000-0000-0000-0000-00000000000c')$q$, 'contrôleur : génération refusée', 'réservée');

SELECT pg_temp.act_as('e3000000-0000-0000-0000-00000000000d');
SELECT pg_temp.fails($q$SELECT pg_temp.fec(1, 'e3000000-0000-0000-0000-00000000000a')$q$, 'génération au nom d''un autre utilisateur', 'authentifié');
SELECT pg_temp.fails($q$SELECT pg_temp.fec(2)$q$, 'version non consécutive', 'version 1 attendue');
-- ------------------------------------------------------------------ nommage (art. 6) et séparateurs (art. 4)
SELECT pg_temp.fails($q$SELECT pg_temp.fec(1, p_filename => 'FEC_3201900000001_20251130.txt')$q$, 'nom : date autre que la clôture', 'date de clôture');
SELECT pg_temp.fails($q$SELECT pg_temp.fec(1, p_filename => 'FEC_32019 0000001_20251231.txt')$q$, 'nom hors modèle FEC_IFU_AAAAMMJJ (IFU non alphanumérique)', 'check');
SELECT pg_temp.fails($q$SELECT pg_temp.fec(1, p_sep => 'pipe')$q$, 'séparateur autre que la tabulation', 'check');
SELECT pg_temp.fails($q$SELECT pg_temp.fec(1, p_eol => 'tab')$q$, 'fin d''enregistrement non autorisée', 'check');
SELECT pg_temp.fails($q$SELECT pg_temp.fec(1, p_start => '2024-12-01')$q$, 'période hors exercice', 'période');
-- ------------------------------------------------------------------ conformité
SELECT pg_temp.fails($q$SELECT pg_temp.fec(1, p_kind => 'final', p_blocking => 1, p_compliance => 'non_compliant')$q$,
  'définitive avec anomalie bloquante', 'check');
SELECT pg_temp.fails($q$SELECT pg_temp.fec(1, p_blocking => 1, p_compliance => 'spec_pending')$q$, 'anomalie bloquante non déclarée non conforme', 'check');
SELECT pg_temp.fails($q$SELECT pg_temp.fec(1, p_compliance => 'compliant')$q$, '« conforme » sans spécification confirmée', 'check');

SELECT pg_temp.fec(1, p_eol => 'cr') AS v1 \gset
SELECT pg_temp.ok((SELECT version_no = 1 AND generated_by = 'e3000000-0000-0000-0000-00000000000d' AND record_separator = 'cr'
  FROM public.fec_exports WHERE id = :'v1'), 'comptable : version 1 enregistrée (fin d''enregistrement CR admise)');
SELECT pg_temp.fec(2, p_kind => 'working', p_blocking => 3, p_compliance => 'non_compliant') AS v2 \gset
SELECT pg_temp.ok((SELECT count(*) FROM public.fec_exports) = 2, 'nouvelle version sans écraser l''ancienne (fichier de travail non conforme)');
-- fractionnement : FEC_IFU_AAAAMMJJ_1 … _n
SELECT pg_temp.fails($q$SELECT pg_temp.fec(3, p_lines => 2, p_parts => jsonb_build_array(
  jsonb_build_object('part', 1, 'filename', 'FEC_3201900000001_20251231_1.txt', 'storage_path', '1e000000-0000-0000-0000-00000000000a/2e000000-0000-0000-0000-00000000000a/x/a', 'sha256', repeat('a', 64), 'line_count', 1),
  jsonb_build_object('part', 2, 'filename', 'FEC_3201900000001_20251231_3.txt', 'storage_path', '1e000000-0000-0000-0000-00000000000a/2e000000-0000-0000-0000-00000000000a/x/b', 'sha256', repeat('a', 64), 'line_count', 1)))$q$,
  'fractionnement : suffixes non consécutifs', 'nommage');
SELECT pg_temp.fails($q$SELECT pg_temp.fec(3, p_lines => 5, p_parts => jsonb_build_array(
  jsonb_build_object('part', 1, 'filename', 'FEC_3201900000001_20251231_1.txt', 'storage_path', '1e000000-0000-0000-0000-00000000000a/2e000000-0000-0000-0000-00000000000a/x/a', 'sha256', repeat('a', 64), 'line_count', 1),
  jsonb_build_object('part', 2, 'filename', 'FEC_3201900000001_20251231_2.txt', 'storage_path', '1e000000-0000-0000-0000-00000000000a/2e000000-0000-0000-0000-00000000000a/x/b', 'sha256', repeat('a', 64), 'line_count', 1)))$q$,
  'fractionnement : total de lignes incohérent', 'nombre de lignes');
SELECT pg_temp.fails($q$SELECT pg_temp.fec(3, p_parts => jsonb_build_array(
  jsonb_build_object('part', null, 'filename', 'FEC_3201900000001_20251231.txt', 'storage_path', '1e000000-0000-0000-0000-00000000000b/x/a', 'sha256', repeat('a', 64), 'line_count', 2)))$q$,
  'fichier rangé hors de l''entreprise', 'rangement');
SELECT pg_temp.fec(3, p_lines => 2, p_parts => jsonb_build_array(
  jsonb_build_object('part', 1, 'filename', 'FEC_3201900000001_20251231_1.txt', 'storage_path', '1e000000-0000-0000-0000-00000000000a/2e000000-0000-0000-0000-00000000000a/x/a', 'sha256', repeat('a', 64), 'line_count', 1),
  jsonb_build_object('part', 2, 'filename', 'FEC_3201900000001_20251231_2.txt', 'storage_path', '1e000000-0000-0000-0000-00000000000a/2e000000-0000-0000-0000-00000000000a/x/b', 'sha256', repeat('a', 64), 'line_count', 1))) AS v3 \gset
SELECT pg_temp.ok((SELECT jsonb_array_length(parts) = 2 FROM public.fec_exports WHERE id = :'v3'), 'fractionnement _1 et _2 accepté');
-- ------------------------------------------------------------------ immutabilité
SELECT pg_temp.fails($q$UPDATE public.fec_exports SET compliance = 'compliant'$q$, 'utilisateur : modification refusée (droit retiré)', 'permission denied');
SELECT pg_temp.fails($q$DELETE FROM public.fec_export_lines$q$, 'utilisateur : suppression de la traçabilité refusée', 'permission denied');
RESET ROLE;
SELECT pg_temp.act_as('e3000000-0000-0000-0000-00000000000d');
SELECT pg_temp.fails($q$UPDATE public.fec_exports SET compliance = 'non_compliant', blocking_count = 1$q$, 'génération figée, même pour le service', 'figée');
SELECT pg_temp.fails($q$DELETE FROM public.fec_exports$q$, 'suppression refusée', 'figée');
SET LOCAL ROLE authenticated;
-- ------------------------------------------------------------------ traçabilité
INSERT INTO public.fec_export_lines (export_id, row_no, organization_id, company_id, entry_id, entry_line_id) VALUES
  (:'v1', 1, '1e000000-0000-0000-0000-00000000000a', '2e000000-0000-0000-0000-00000000000a', '5e000000-0000-0000-0000-00000000000a', '6e000000-0000-0000-0000-00000000000a'),
  (:'v1', 2, '1e000000-0000-0000-0000-00000000000a', '2e000000-0000-0000-0000-00000000000a', '5e000000-0000-0000-0000-00000000000a', '6e000000-0000-0000-0000-00000000000b');
SELECT pg_temp.ok((SELECT count(*) FROM public.fec_export_lines WHERE export_id = :'v1') = 2, 'traçabilité : lignes du fichier → lignes d''écriture validées');
SELECT pg_temp.fails(format($q$INSERT INTO public.fec_export_lines VALUES ('%s', 3, '1e000000-0000-0000-0000-00000000000a',
  '2e000000-0000-0000-0000-00000000000a', '5e000000-0000-0000-0000-00000000000b', '6e000000-0000-0000-0000-00000000000c')$q$, :'v1'),
  'écriture non validée refusée', 'validées');
SELECT pg_temp.fails(format($q$INSERT INTO public.fec_export_lines VALUES ('%s', 3, '1e000000-0000-0000-0000-00000000000a',
  '2e000000-0000-0000-0000-00000000000a', '5e000000-0000-0000-0000-00000000000a', '6e000000-0000-0000-0000-00000000000a')$q$, :'v1'),
  'doublon d''une ligne d''écriture dans un fichier', 'duplicate');
SELECT pg_temp.fails(format($q$INSERT INTO public.fec_export_lines VALUES ('%s', 3, '1e000000-0000-0000-0000-00000000000a',
  '2e000000-0000-0000-0000-00000000000a', '5e000000-0000-0000-0000-00000000000b', '6e000000-0000-0000-0000-00000000000a')$q$, :'v2'),
  'ligne rattachée à une autre écriture', 'validées');
-- ------------------------------------------------------------------ acteur IA
SELECT set_config('kofinex.actor', 'ai', true);
SELECT pg_temp.fails($q$SELECT pg_temp.fec(4)$q$, 'acteur IA : aucune génération', 'IA');
SELECT set_config('kofinex.actor', '', true);
-- ------------------------------------------------------------------ lecture et isolation
SELECT pg_temp.act_as('e3000000-0000-0000-0000-00000000000a');
SELECT pg_temp.ok((SELECT count(*) FROM public.fec_exports) = 3, 'propriétaire de l''organisation : historique visible');
SELECT pg_temp.ok((SELECT count(*) FROM public.audit_logs WHERE entity_type = 'fec_exports') = 3, 'chaque génération journalisée');
SELECT pg_temp.act_as('e3000000-0000-0000-0000-00000000000c');
SELECT pg_temp.ok((SELECT count(*) FROM public.fec_exports) = 0 AND (SELECT count(*) FROM public.fec_export_lines) = 0,
  'contrôleur de gestion : aucun FEC visible');
SELECT pg_temp.act_as('e3000000-0000-0000-0000-00000000000e');
SELECT pg_temp.ok((SELECT count(*) FROM public.fec_exports) = 0, 'comptable d''une autre entreprise : rien de visible');
SELECT pg_temp.fails($q$SELECT pg_temp.fec(1, 'e3000000-0000-0000-0000-00000000000e', p_company => '2e000000-0000-0000-0000-00000000000a')$q$,
  'comptable d''une autre entreprise : refus sans divulguer l''historique', 'réservée');
SELECT pg_temp.act_as('e3000000-0000-0000-0000-00000000000b');
SELECT pg_temp.ok((SELECT count(*) FROM public.fec_exports) = 0, 'autre organisation : rien de visible');
-- ------------------------------------------------------------------ stockage
RESET ROLE;
SELECT pg_temp.ok(to_regclass('storage.buckets') IS NULL OR (SELECT NOT public FROM storage.buckets WHERE id = 'fec'),
  'bucket « fec » privé (si le schéma storage existe)');
ROLLBACK;
\echo 'Tous les tests du FEC Bénin (SQL) sont passés.'
