-- =====================================================================
-- Tests migration 0010 : grand livre (lignes, validation contrôlée en base, grand livre actif, gel,
-- accès, populations d'audit tirées des écritures).
-- =====================================================================
\set QUIET on
BEGIN;
CREATE OR REPLACE FUNCTION pg_temp.ok(cond boolean, label text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  IF cond IS DISTINCT FROM true THEN RAISE EXCEPTION 'ÉCHEC : %', label; END IF;
  RAISE NOTICE 'ok - %', label;
END $$;
CREATE OR REPLACE FUNCTION pg_temp.fails(q text, label text, pattern text DEFAULT NULL) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  BEGIN EXECUTE q;
  EXCEPTION WHEN OTHERS THEN
    IF pattern IS NOT NULL AND SQLERRM NOT ILIKE '%' || pattern || '%' THEN
      RAISE EXCEPTION 'ÉCHEC : % (erreur inattendue : %)', label, SQLERRM;
    END IF;
    RAISE NOTICE 'ok - % (refusé : %)', label, SQLERRM; RETURN;
  END;
  RAISE EXCEPTION 'ÉCHEC : % (aucune erreur levée)', label;
END $$;
CREATE OR REPLACE FUNCTION pg_temp.act_as(uid uuid) RETURNS void LANGUAGE sql AS $$
  SELECT set_config('request.jwt.claims', json_build_object('sub', uid, 'role', 'authenticated')::text, true);
$$;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA pg_temp TO authenticated;

-- a : alice (propriétaire) ; c : carl (comptable de l'entité) ; v : vera (lectrice) ; s : sam (auditeur de mission,
-- sans rôle sur l'entité) ; b : bob (autre organisation)
INSERT INTO auth.users (id, email) VALUES
  ('e0000000-0000-0000-0000-00000000000a', 'alice@gl.test'), ('e0000000-0000-0000-0000-00000000000c', 'carl@gl.test'),
  ('e0000000-0000-0000-0000-00000000000f', 'vera@gl.test'), ('e0000000-0000-0000-0000-000000000005', 'sam@gl.test'),
  ('e0000000-0000-0000-0000-00000000000b', 'bob@gm.test');
INSERT INTO public.accounting_frameworks (id, code, name) VALUES ('f0000000-0000-0000-0000-0000000000fa', 'TEST_FWA', 'Test');

SET LOCAL session_replication_role = replica;
INSERT INTO public.profiles (id, email) SELECT id, email FROM auth.users WHERE email LIKE '%@g_.test' ON CONFLICT DO NOTHING;
INSERT INTO public.organizations (id, name, slug, created_by) VALUES
  ('1a000000-0000-0000-0000-00000000000a', 'Cabinet GL', 'cab-gl', 'e0000000-0000-0000-0000-00000000000a'),
  ('1a000000-0000-0000-0000-00000000000b', 'Cabinet GM', 'cab-gm', 'e0000000-0000-0000-0000-00000000000b');
INSERT INTO public.organization_members (organization_id, user_id, role) VALUES
  ('1a000000-0000-0000-0000-00000000000a', 'e0000000-0000-0000-0000-00000000000a', 'owner'),
  ('1a000000-0000-0000-0000-00000000000a', 'e0000000-0000-0000-0000-00000000000c', 'member'),
  ('1a000000-0000-0000-0000-00000000000a', 'e0000000-0000-0000-0000-00000000000f', 'member'),
  ('1a000000-0000-0000-0000-00000000000a', 'e0000000-0000-0000-0000-000000000005', 'member'),
  ('1a000000-0000-0000-0000-00000000000b', 'e0000000-0000-0000-0000-00000000000b', 'owner');
INSERT INTO public.companies (id, organization_id, name, framework_id, created_by) VALUES
  ('2a000000-0000-0000-0000-00000000000a', '1a000000-0000-0000-0000-00000000000a', 'Client GL',
   'f0000000-0000-0000-0000-0000000000fa', 'e0000000-0000-0000-0000-00000000000a');
INSERT INTO public.company_members (organization_id, company_id, user_id, role) VALUES
  ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', 'e0000000-0000-0000-0000-00000000000c', 'accountant'),
  ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', 'e0000000-0000-0000-0000-00000000000f', 'viewer');
INSERT INTO public.fiscal_years (id, organization_id, company_id, label, start_date, end_date, created_by) VALUES
  ('3a000000-0000-0000-0000-000000002025', '1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
   '2025', '2025-01-01', '2025-12-31', 'e0000000-0000-0000-0000-00000000000a');
INSERT INTO public.import_jobs (id, organization_id, company_id, fiscal_year_id, source_format, status, kind, started_by) VALUES
  ('4a000000-0000-0000-0000-000000000001', '1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
   '3a000000-0000-0000-0000-000000002025', 'csv', 'awaiting_confirmation', 'ledger', 'e0000000-0000-0000-0000-00000000000c'),
  ('4a000000-0000-0000-0000-000000000002', '1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
   '3a000000-0000-0000-0000-000000002025', 'csv', 'awaiting_confirmation', 'trial_balance', 'e0000000-0000-0000-0000-00000000000c'),
  ('4a000000-0000-0000-0000-000000000003', '1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
   '3a000000-0000-0000-0000-000000002025', 'csv', 'awaiting_confirmation', 'ledger', 'e0000000-0000-0000-0000-00000000000c');
INSERT INTO public.engagements (id, organization_id, company_id, fiscal_year_id, engagement_type, reference, name, created_by)
VALUES ('5a000000-0000-0000-0000-00000000000a', '1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
        '3a000000-0000-0000-0000-000000002025', 'statutory_audit', 'CAC-GL', 'Audit GL', 'e0000000-0000-0000-0000-00000000000a');
INSERT INTO public.engagement_members (organization_id, engagement_id, user_id, role, independence_confirmed_at) VALUES
  ('1a000000-0000-0000-0000-00000000000a', '5a000000-0000-0000-0000-00000000000a', 'e0000000-0000-0000-0000-000000000005', 'staff', now());
SET LOCAL session_replication_role = origin;

SET LOCAL ROLE authenticated;
SELECT pg_temp.act_as('e0000000-0000-0000-0000-00000000000c');

-- ------------------------------------------------------- lignes et validation
SELECT pg_temp.fails($q$INSERT INTO public.ledger_lines (organization_id, company_id, fiscal_year_id, import_job_id, source_row, status,
  entry_date, account_number, debit, raw) VALUES ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
  '3a000000-0000-0000-0000-000000002025', '4a000000-0000-0000-0000-000000000002', 1, 'valid', '2025-03-01', '411000', 10, '[]')$q$,
  'lignes rattachées à un import de balance refusées', 'grand livre requis');
INSERT INTO public.ledger_lines (organization_id, company_id, fiscal_year_id, import_job_id, source_row, status, journal_code,
                                 entry_number, entry_date, account_number, label, debit, credit, raw)
SELECT '1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', '3a000000-0000-0000-0000-000000002025',
       '4a000000-0000-0000-0000-000000000001', n, s, j, e, d::date, a, l, dv, cv, '[]'
  FROM (VALUES (2, 'valid', 'VT', '1', '2025-03-15', '411000', 'Facture F12', 1200, 0),
               (3, 'valid', 'VT', '1', '2025-03-15', '701000', 'Facture F12', 0, 1100),
               (4, 'valid', 'BQ', '2', '2025-04-05', '521000', 'Règlement', 1200, 0),
               (5, 'valid', 'BQ', '2', '2025-04-05', '411000', 'Règlement', 0, 1200),
               (6, 'error', 'OD', '3', '2025-05-01', '601000', 'Illisible', 0, 0)) t(n, s, j, e, d, a, l, dv, cv);
SELECT pg_temp.ok((SELECT count(*) FROM public.ledger_lines) = 5, 'comptable : lignes du grand livre enregistrées');
SELECT pg_temp.fails($q$UPDATE public.import_jobs SET status = 'completed', validated_by = 'e0000000-0000-0000-0000-00000000000c',
  completed_at = now() WHERE id = '4a000000-0000-0000-0000-000000000001'$q$, 'validation avec une ligne en erreur', 'en erreur');
DELETE FROM public.ledger_lines WHERE status = 'error';
SELECT pg_temp.fails($q$UPDATE public.import_jobs SET status = 'completed', validated_by = 'e0000000-0000-0000-0000-00000000000c',
  completed_at = now() WHERE id = '4a000000-0000-0000-0000-000000000001'$q$, 'validation d''un grand livre déséquilibré', 'déséquilibré');
UPDATE public.ledger_lines SET credit = 1000, debit = 0 WHERE source_row = 3;
INSERT INTO public.ledger_lines (organization_id, company_id, fiscal_year_id, import_job_id, source_row, status, journal_code,
                                 entry_number, entry_date, account_number, debit, credit, raw)
VALUES ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', '3a000000-0000-0000-0000-000000002025',
        '4a000000-0000-0000-0000-000000000001', 7, 'valid', 'BQ', '2', '2025-04-05', '708000', 0, 200, '[]');
SELECT pg_temp.fails($q$UPDATE public.import_jobs SET status = 'completed', validated_by = 'e0000000-0000-0000-0000-00000000000c',
  completed_at = now() WHERE id = '4a000000-0000-0000-0000-000000000001'$q$,
  'grand livre équilibré mais écritures déséquilibrées', 'écriture(s) déséquilibrée(s)');
UPDATE public.ledger_lines SET journal_code = 'VT', entry_number = '1' WHERE source_row = 7;
UPDATE public.ledger_lines SET entry_date = '2026-01-02' WHERE source_row = 4;
UPDATE public.ledger_lines SET entry_date = '2026-01-02' WHERE source_row = 5;
SELECT pg_temp.fails($q$UPDATE public.import_jobs SET status = 'completed', validated_by = 'e0000000-0000-0000-0000-00000000000c',
  completed_at = now() WHERE id = '4a000000-0000-0000-0000-000000000001'$q$, 'écritures hors de l''exercice', 'hors de l''exercice');
UPDATE public.ledger_lines SET entry_date = '2025-04-05' WHERE source_row IN (4, 5);
SELECT pg_temp.fails($q$UPDATE public.fiscal_years SET active_ledger_import_job_id = '4a000000-0000-0000-0000-000000000001'$q$,
  'grand livre non validé : ne peut pas devenir actif', 'validé');
UPDATE public.import_jobs SET status = 'completed', validated_by = 'e0000000-0000-0000-0000-00000000000c', completed_at = now()
 WHERE id = '4a000000-0000-0000-0000-000000000001';
SELECT pg_temp.ok(true, 'grand livre équilibré, écritures équilibrées, dates dans l''exercice : validé');
UPDATE public.fiscal_years SET active_ledger_import_job_id = '4a000000-0000-0000-0000-000000000001';
SELECT pg_temp.ok((SELECT active_ledger_import_job_id IS NOT NULL FROM public.fiscal_years), 'grand livre actif de l''exercice');
SELECT pg_temp.fails($q$UPDATE public.fiscal_years SET active_import_job_id = '4a000000-0000-0000-0000-000000000001'$q$,
  'un grand livre ne peut pas devenir la balance de l''exercice', 'import de balance');
SELECT pg_temp.fails($q$UPDATE public.ledger_lines SET debit = 999 WHERE source_row = 2$q$, 'grand livre validé : écritures figées', 'figées');
SELECT pg_temp.fails($q$DELETE FROM public.ledger_lines$q$, 'grand livre validé : suppression refusée', 'figées');

-- ------------------------------------------------------- accès
SELECT pg_temp.act_as('e0000000-0000-0000-0000-00000000000f');
SELECT pg_temp.ok((SELECT count(*) FROM public.ledger_lines) = 5, 'lecteur de l''entité : lecture du grand livre');
SELECT pg_temp.fails($q$INSERT INTO public.ledger_lines (organization_id, company_id, fiscal_year_id, import_job_id, source_row, status,
  raw) VALUES ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', '3a000000-0000-0000-0000-000000002025',
  '4a000000-0000-0000-0000-000000000003', 99, 'skipped', '[]')$q$, 'lecteur : écriture refusée', 'row-level security');
SELECT pg_temp.act_as('e0000000-0000-0000-0000-000000000005');
SELECT pg_temp.ok((SELECT count(*) FROM public.ledger_lines) = 5, 'équipe de mission sans rôle sur l''entité : lecture du grand livre');
SELECT pg_temp.act_as('e0000000-0000-0000-0000-00000000000b');
SELECT pg_temp.ok((SELECT count(*) FROM public.ledger_lines) = 0, 'autre organisation : grand livre invisible');

-- ------------------------------------------------------- populations d'audit tirées des écritures
SELECT pg_temp.act_as('e0000000-0000-0000-0000-000000000005');
SELECT pg_temp.fails($q$INSERT INTO public.fa_populations (organization_id, engagement_id, name, source, source_import_job_id,
  item_count, total_amount, absolute_total, sha256, created_by) VALUES ('1a000000-0000-0000-0000-00000000000a',
  '5a000000-0000-0000-0000-00000000000a', 'Ventes', 'ledger', '4a000000-0000-0000-0000-000000000002', 1, 0, 0, repeat('b', 64),
  'e0000000-0000-0000-0000-000000000005')$q$, 'population « grand livre » sur un autre import refusée', 'grand livre validé');
INSERT INTO public.fa_populations (id, organization_id, engagement_id, name, source, source_import_job_id, filters, item_count,
                                   total_amount, absolute_total, sha256, created_by)
VALUES ('6a000000-0000-0000-0000-00000000000a', '1a000000-0000-0000-0000-00000000000a', '5a000000-0000-0000-0000-00000000000a',
        'Écritures de ventes', 'ledger', '4a000000-0000-0000-0000-000000000001', '{"account_prefixes":["70"]}', 1, -1000, 1000,
        repeat('c', 64), 'e0000000-0000-0000-0000-000000000005');
SELECT pg_temp.fails($q$INSERT INTO public.fa_population_items (organization_id, engagement_id, population_id, line_no, reference,
  amount, ledger_line_id) SELECT '1a000000-0000-0000-0000-00000000000a', '5a000000-0000-0000-0000-00000000000a',
  '6a000000-0000-0000-0000-00000000000a', 1, 'VT/1', -900, id FROM public.ledger_lines WHERE source_row = 3$q$,
  'élément de population au montant différent de l''écriture', 'montant différent');
INSERT INTO public.fa_population_items (organization_id, engagement_id, population_id, line_no, reference, amount, ledger_line_id)
SELECT '1a000000-0000-0000-0000-00000000000a', '5a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a',
       1, 'VT/1', -1000, id FROM public.ledger_lines WHERE source_row = 3;
SELECT pg_temp.ok((SELECT count(*) FROM public.fa_population_items WHERE ledger_line_id IS NOT NULL) = 1,
  'population d''audit tirée d''une écriture du grand livre');

ROLLBACK;
\echo 'Tous les tests du grand livre (SQL) sont passés.'
