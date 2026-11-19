-- =====================================================================
-- Tests migration 0008 : audit financier (seuils, revue des comptes, échantillons, circularisations,
-- anomalies, conditions d'émission, gel, cloisonnement).
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

-- 1: mona (manager) ; 2: paul (associé) ; 3: ines (chef de mission) ; 4: sam (assistant) ; 6: olga (observatrice)
-- b: bob (autre organisation)
INSERT INTO auth.users (id, email) VALUES
  ('c0000000-0000-0000-0000-00000000000a', 'alice@fa.test'), ('c1000000-0000-0000-0000-000000000001', 'mona@fa.test'),
  ('c2000000-0000-0000-0000-000000000002', 'paul@fa.test'), ('c3000000-0000-0000-0000-000000000003', 'ines@fa.test'),
  ('c4000000-0000-0000-0000-000000000004', 'sam@fa.test'), ('c6000000-0000-0000-0000-000000000006', 'olga@fa.test'),
  ('cb000000-0000-0000-0000-00000000000b', 'bob@fb.test');
INSERT INTO public.accounting_frameworks (id, code, name) VALUES ('f0000000-0000-0000-0000-0000000000f8', 'TEST_FW8', 'Test');

-- Données de départ (balances validées N-1 et N), chargées sans passer par le circuit d'import
SET LOCAL session_replication_role = replica;
INSERT INTO public.profiles (id, email) SELECT id, email FROM auth.users WHERE email LIKE '%@f_.test' ON CONFLICT DO NOTHING;
INSERT INTO public.organizations (id, name, slug, created_by) VALUES
  ('18000000-0000-0000-0000-00000000000a', 'Cabinet FA', 'cab-fa', 'c0000000-0000-0000-0000-00000000000a'),
  ('18000000-0000-0000-0000-00000000000b', 'Cabinet FB', 'cab-fb', 'cb000000-0000-0000-0000-00000000000b');
INSERT INTO public.organization_members (organization_id, user_id, role) VALUES
  ('18000000-0000-0000-0000-00000000000a', 'c0000000-0000-0000-0000-00000000000a', 'owner'),
  ('18000000-0000-0000-0000-00000000000b', 'cb000000-0000-0000-0000-00000000000b', 'owner');
INSERT INTO public.organization_members (organization_id, user_id, role)
SELECT '18000000-0000-0000-0000-00000000000a', u, 'member' FROM unnest(ARRAY[
  'c1000000-0000-0000-0000-000000000001','c2000000-0000-0000-0000-000000000002','c3000000-0000-0000-0000-000000000003',
  'c4000000-0000-0000-0000-000000000004','c6000000-0000-0000-0000-000000000006']::uuid[]) u;
INSERT INTO public.companies (id, organization_id, name, framework_id, created_by) VALUES
  ('28000000-0000-0000-0000-00000000000a', '18000000-0000-0000-0000-00000000000a', 'Client FA',
   'f0000000-0000-0000-0000-0000000000f8', 'c0000000-0000-0000-0000-00000000000a');
INSERT INTO public.fiscal_years (id, organization_id, company_id, label, start_date, end_date, created_by) VALUES
  ('38000000-0000-0000-0000-000000002024', '18000000-0000-0000-0000-00000000000a', '28000000-0000-0000-0000-00000000000a',
   '2024', '2024-01-01', '2024-12-31', 'c0000000-0000-0000-0000-00000000000a'),
  ('38000000-0000-0000-0000-000000002025', '18000000-0000-0000-0000-00000000000a', '28000000-0000-0000-0000-00000000000a',
   '2025', '2025-01-01', '2025-12-31', 'c0000000-0000-0000-0000-00000000000a');
INSERT INTO public.import_jobs (id, organization_id, company_id, fiscal_year_id, source_format, status, started_by, validated_by,
                                completed_at) VALUES
  ('48000000-0000-0000-0000-000000002024', '18000000-0000-0000-0000-00000000000a', '28000000-0000-0000-0000-00000000000a',
   '38000000-0000-0000-0000-000000002024', 'csv', 'completed', 'c0000000-0000-0000-0000-00000000000a',
   'c0000000-0000-0000-0000-00000000000a', now()),
  ('48000000-0000-0000-0000-000000002025', '18000000-0000-0000-0000-00000000000a', '28000000-0000-0000-0000-00000000000a',
   '38000000-0000-0000-0000-000000002025', 'csv', 'completed', 'c0000000-0000-0000-0000-00000000000a',
   'c0000000-0000-0000-0000-00000000000a', now());
INSERT INTO public.trial_balance_entries (organization_id, company_id, fiscal_year_id, import_job_id, account_number,
                                          closing_debit, closing_credit) VALUES
  ('18000000-0000-0000-0000-00000000000a', '28000000-0000-0000-0000-00000000000a', '38000000-0000-0000-0000-000000002024',
   '48000000-0000-0000-0000-000000002024', '411000', 1000, 0),
  ('18000000-0000-0000-0000-00000000000a', '28000000-0000-0000-0000-00000000000a', '38000000-0000-0000-0000-000000002024',
   '48000000-0000-0000-0000-000000002024', '701000', 0, 1000),
  ('18000000-0000-0000-0000-00000000000a', '28000000-0000-0000-0000-00000000000a', '38000000-0000-0000-0000-000000002025',
   '48000000-0000-0000-0000-000000002025', '411000', 1500, 0),
  ('18000000-0000-0000-0000-00000000000a', '28000000-0000-0000-0000-00000000000a', '38000000-0000-0000-0000-000000002025',
   '48000000-0000-0000-0000-000000002025', '701000', 0, 1500);
UPDATE public.fiscal_years SET active_import_job_id = ('48000000-0000-0000-0000-00000000' || label)::uuid
 WHERE company_id = '28000000-0000-0000-0000-00000000000a';
INSERT INTO public.engagements (id, organization_id, company_id, fiscal_year_id, engagement_type, reference, name, created_by)
VALUES ('58000000-0000-0000-0000-00000000000a', '18000000-0000-0000-0000-00000000000a', '28000000-0000-0000-0000-00000000000a',
        '38000000-0000-0000-0000-000000002025', 'statutory_audit', 'CAC-FA', 'Audit légal FA', 'c1000000-0000-0000-0000-000000000001'),
       ('58000000-0000-0000-0000-00000000000b', '18000000-0000-0000-0000-00000000000a', '28000000-0000-0000-0000-00000000000a',
        NULL, 'internal_audit', 'AI-FA', 'Audit interne FA', 'c1000000-0000-0000-0000-000000000001');
INSERT INTO public.engagement_members (organization_id, engagement_id, user_id, role, independence_confirmed_at)
SELECT '18000000-0000-0000-0000-00000000000a', e, u, r, now() FROM (VALUES
  ('c1000000-0000-0000-0000-000000000001'::uuid, 'manager'), ('c2000000-0000-0000-0000-000000000002'::uuid, 'partner'),
  ('c3000000-0000-0000-0000-000000000003'::uuid, 'in_charge'), ('c4000000-0000-0000-0000-000000000004'::uuid, 'staff'),
  ('c6000000-0000-0000-0000-000000000006'::uuid, 'observer')) t(u, r),
  unnest(ARRAY['58000000-0000-0000-0000-00000000000a','58000000-0000-0000-0000-00000000000b']::uuid[]) e;
SET LOCAL session_replication_role = origin;

SET LOCAL ROLE authenticated;

-- ------------------------------------------------------- seuils
SELECT pg_temp.act_as('c4000000-0000-0000-0000-000000000004');
SELECT pg_temp.fails($q$INSERT INTO public.fa_materiality (organization_id, engagement_id, version, benchmark_label, benchmark_source,
  benchmark_amount, overall_pct, overall_amount, performance_pct, performance_amount, trivial_pct, trivial_amount, basis, created_by)
  VALUES ('18000000-0000-0000-0000-00000000000a', '58000000-0000-0000-0000-00000000000a', 1, 'CA', 'manual', 100000, 1, 1000, 50, 500,
          5, 50, 'Justification de test', 'c4000000-0000-0000-0000-000000000004')$q$, 'assistant : seuils non saisissables');
SELECT pg_temp.act_as('c3000000-0000-0000-0000-000000000003');
SELECT pg_temp.fails($q$INSERT INTO public.fa_materiality (organization_id, engagement_id, version, benchmark_label, benchmark_source,
  benchmark_amount, overall_pct, overall_amount, performance_pct, performance_amount, trivial_pct, trivial_amount, basis, created_by)
  VALUES ('18000000-0000-0000-0000-00000000000a', '58000000-0000-0000-0000-00000000000a', 1, 'CA', 'manual', 100000, 1, 1200, 50, 600,
          5, 60, 'Justification de test', 'c3000000-0000-0000-0000-000000000003')$q$, 'seuil incohérent avec le pourcentage', 'check');
INSERT INTO public.fa_materiality (id, organization_id, engagement_id, version, benchmark_label, benchmark_source,
  benchmark_amount, overall_pct, overall_amount, performance_pct, performance_amount, trivial_pct, trivial_amount, basis, created_by)
VALUES ('68000000-0000-0000-0000-000000000001', '18000000-0000-0000-0000-00000000000a', '58000000-0000-0000-0000-00000000000a', 1,
        'Chiffre d''affaires', 'manual', 100000, 1, 1000, 30, 300, 5, 50, 'Justification de test (jugement)',
        'c3000000-0000-0000-0000-000000000003');
SELECT pg_temp.ok(true, 'chef de mission : seuils v1 saisis (1 000 / 300 / 50)');
SELECT pg_temp.fails($q$INSERT INTO public.fa_materiality (organization_id, engagement_id, version, benchmark_label, benchmark_source,
  benchmark_amount, overall_pct, overall_amount, performance_pct, performance_amount, trivial_pct, trivial_amount, basis, created_by)
  VALUES ('18000000-0000-0000-0000-00000000000b', '58000000-0000-0000-0000-00000000000b', 1, 'CA', 'manual', 100000, 1, 1000, 50, 500,
          5, 50, 'Justification de test', 'c3000000-0000-0000-0000-000000000003')$q$, 'mission d''audit interne : seuils refusés');
SELECT pg_temp.fails($q$UPDATE public.fa_materiality SET status = 'approved', approved_by = 'c3000000-0000-0000-0000-000000000003'$q$,
  'chef de mission : approbation des seuils refusée', 'manager ou associé');
SELECT pg_temp.act_as('c1000000-0000-0000-0000-000000000001');
UPDATE public.fa_materiality SET status = 'approved', approved_by = 'c1000000-0000-0000-0000-000000000001'
 WHERE id = '68000000-0000-0000-0000-000000000001';
SELECT pg_temp.ok((SELECT approved_at IS NOT NULL FROM public.fa_materiality), 'manager : seuils approuvés et horodatés');
SELECT pg_temp.fails($q$UPDATE public.fa_materiality SET basis = 'Autre justification de test'$q$, 'seuils approuvés : non modifiables');
SELECT pg_temp.fails($q$DELETE FROM public.fa_materiality$q$, 'seuils approuvés : non supprimables');

-- ------------------------------------------------------- revue des comptes (soldes vérifiés en base)
SELECT pg_temp.act_as('c4000000-0000-0000-0000-000000000004');
SELECT pg_temp.fails($q$INSERT INTO public.fa_account_reviews (organization_id, engagement_id, account_number, source_import_job_id,
  previous_import_job_id, balance_n, balance_n1, threshold_used) VALUES ('18000000-0000-0000-0000-00000000000a',
  '58000000-0000-0000-0000-00000000000a', '411000', '48000000-0000-0000-0000-000000002025', '48000000-0000-0000-0000-000000002024',
  1400, 1000, 300)$q$, 'solde N différent de la balance validée', 'solde N');
SELECT pg_temp.fails($q$INSERT INTO public.fa_account_reviews (organization_id, engagement_id, account_number, source_import_job_id,
  balance_n, threshold_used) VALUES ('18000000-0000-0000-0000-00000000000a', '58000000-0000-0000-0000-00000000000a', '411000',
  '48000000-0000-0000-0000-000000002024', 1000, 300)$q$, 'balance d''un autre exercice refusée', 'balance validée');
SELECT pg_temp.fails($q$INSERT INTO public.fa_account_reviews (organization_id, engagement_id, account_number, source_import_job_id,
  previous_import_job_id, balance_n, balance_n1, threshold_used) VALUES ('18000000-0000-0000-0000-00000000000a',
  '58000000-0000-0000-0000-00000000000a', '411000', '48000000-0000-0000-0000-000000002025', '48000000-0000-0000-0000-000000002024',
  1500, 1000, 100)$q$, 'seuil différent du seuil de planification approuvé', 'seuil');
INSERT INTO public.fa_account_reviews (id, organization_id, engagement_id, account_number, source_import_job_id,
  previous_import_job_id, balance_n, balance_n1, threshold_used, cycle_code)
VALUES ('78000000-0000-0000-0000-000000000001', '18000000-0000-0000-0000-00000000000a', '58000000-0000-0000-0000-00000000000a',
        '411000', '48000000-0000-0000-0000-000000002025', '48000000-0000-0000-0000-000000002024', 1500, 1000, 300, 'CLIENTS');
SELECT pg_temp.ok((SELECT requires_explanation AND variation = 500 FROM public.fa_account_reviews),
  'variation de 500 ≥ seuil de 300 : explication requise');
SELECT pg_temp.fails($q$UPDATE public.fa_account_reviews SET requires_explanation = false, status = 'reviewed',
  conclusion = 'RAS', reviewed_by = 'c4000000-0000-0000-0000-000000000004'$q$, 'revue sans explication de la variation', 'check');
SELECT pg_temp.fails($q$UPDATE public.fa_account_reviews SET explanation = 'Hausse des ventes de décembre', status = 'reviewed',
  conclusion = 'RAS', reviewed_by = 'c3000000-0000-0000-0000-000000000003'$q$, 'revue au nom d''un autre', 'en son nom');
UPDATE public.fa_account_reviews SET explanation = 'Hausse des ventes de décembre', status = 'reviewed', conclusion = 'Solde justifié',
  reviewed_by = 'c4000000-0000-0000-0000-000000000004';
SELECT pg_temp.ok((SELECT status = 'reviewed' AND reviewed_at IS NOT NULL FROM public.fa_account_reviews), 'compte revu et expliqué');
SELECT pg_temp.fails($q$UPDATE public.fa_account_reviews SET balance_n = 1600$q$, 'solde du compte non falsifiable', 'solde N');

-- ------------------------------------------------------- population, échantillon, tests
INSERT INTO public.fa_populations (id, organization_id, engagement_id, name, source, source_import_job_id, item_count, total_amount,
                                   absolute_total, sha256, created_by)
VALUES ('88000000-0000-0000-0000-000000000001', '18000000-0000-0000-0000-00000000000a', '58000000-0000-0000-0000-00000000000a',
        'Créances clients', 'balance', '48000000-0000-0000-0000-000000002025', 3, 1600, 1800, repeat('a', 64),
        'c4000000-0000-0000-0000-000000000004');
INSERT INTO public.fa_population_items (id, organization_id, engagement_id, population_id, line_no, reference, amount) VALUES
  ('98000000-0000-0000-0000-000000000001', '18000000-0000-0000-0000-00000000000a', '58000000-0000-0000-0000-00000000000a',
   '88000000-0000-0000-0000-000000000001', 1, 'C1', 1000),
  ('98000000-0000-0000-0000-000000000002', '18000000-0000-0000-0000-00000000000a', '58000000-0000-0000-0000-00000000000a',
   '88000000-0000-0000-0000-000000000001', 2, 'C2', 700),
  ('98000000-0000-0000-0000-000000000003', '18000000-0000-0000-0000-00000000000a', '58000000-0000-0000-0000-00000000000a',
   '88000000-0000-0000-0000-000000000001', 3, 'C3', -100);
SELECT pg_temp.fails($q$INSERT INTO public.fa_samples (organization_id, engagement_id, population_id, reference, objective, method,
  requested_size, size_basis, seed, selected_count, created_by) VALUES ('18000000-0000-0000-0000-00000000000a',
  '58000000-0000-0000-0000-00000000000a', '88000000-0000-0000-0000-000000000001', 'E1', 'Existence', 'random', 2,
  'Taille fixée par jugement (test)', 42, 2, 'c4000000-0000-0000-0000-000000000004')$q$,
  'échantillon saisi à la main refusé (sélection par le moteur)', 'moteur');
SELECT set_config('kofinex.sampling', 'on', true);
INSERT INTO public.fa_samples (id, organization_id, engagement_id, population_id, reference, objective, method, requested_size,
                               size_basis, seed, selected_count, created_by)
VALUES ('a8000000-0000-0000-0000-000000000001', '18000000-0000-0000-0000-00000000000a', '58000000-0000-0000-0000-00000000000a',
        '88000000-0000-0000-0000-000000000001', 'E1', 'Existence des créances', 'random', 2, 'Taille fixée par jugement (test)', 42, 2,
        'c4000000-0000-0000-0000-000000000004');
INSERT INTO public.fa_sample_items (id, organization_id, engagement_id, sample_id, population_item_id, selection_reason, book_amount) VALUES
  ('b8000000-0000-0000-0000-000000000001', '18000000-0000-0000-0000-00000000000a', '58000000-0000-0000-0000-00000000000a',
   'a8000000-0000-0000-0000-000000000001', '98000000-0000-0000-0000-000000000001', 'random', 1000),
  ('b8000000-0000-0000-0000-000000000002', '18000000-0000-0000-0000-00000000000a', '58000000-0000-0000-0000-00000000000a',
   'a8000000-0000-0000-0000-000000000001', '98000000-0000-0000-0000-000000000002', 'random', 700);
SELECT set_config('kofinex.sampling', 'off', true);
SELECT pg_temp.ok((SELECT count(*) FROM public.fa_sample_items) = 2, 'échantillon tiré par le moteur : 2 éléments');
SELECT pg_temp.fails($q$UPDATE public.fa_population_items SET amount = 1 WHERE line_no = 3$q$, 'population figée après tirage', 'figée');
SELECT pg_temp.fails($q$UPDATE public.fa_samples SET seed = 1$q$, 'paramètres de sélection immuables', 'immuables');
SELECT pg_temp.fails($q$INSERT INTO public.fa_sample_items (organization_id, engagement_id, sample_id, population_item_id,
  selection_reason, book_amount) VALUES ('18000000-0000-0000-0000-00000000000a', '58000000-0000-0000-0000-00000000000a',
  'a8000000-0000-0000-0000-000000000001', '98000000-0000-0000-0000-000000000003', 'judgment', -100)$q$,
  'ajout d''un élément hors sélection refusé', 'sélection');
SELECT pg_temp.fails($q$UPDATE public.fa_sample_items SET book_amount = 999 WHERE id = 'b8000000-0000-0000-0000-000000000001'$q$,
  'montant comptable de l''élément immuable', 'immuable');
SELECT pg_temp.fails($q$UPDATE public.fa_sample_items SET result = 'no_exception', audited_amount = 900,
  tested_by = 'c4000000-0000-0000-0000-000000000004' WHERE id = 'b8000000-0000-0000-0000-000000000001'$q$,
  '« sans anomalie » avec un montant audité différent', 'check');
SELECT pg_temp.fails($q$UPDATE public.fa_sample_items SET result = 'exception', audited_amount = 900,
  tested_by = 'c4000000-0000-0000-0000-000000000004' WHERE id = 'b8000000-0000-0000-0000-000000000001'$q$,
  'anomalie sans commentaire', 'check');
SELECT pg_temp.fails($q$UPDATE public.fa_sample_items SET result = 'no_exception', audited_amount = 700,
  tested_by = 'c3000000-0000-0000-0000-000000000003' WHERE id = 'b8000000-0000-0000-0000-000000000002'$q$,
  'test enregistré au nom d''un autre', 'au nom');
UPDATE public.fa_sample_items SET result = 'exception', audited_amount = 900, comment = 'Avoir non comptabilisé',
  tested_by = 'c4000000-0000-0000-0000-000000000004' WHERE id = 'b8000000-0000-0000-0000-000000000001';
SELECT pg_temp.ok((SELECT misstatement FROM public.fa_sample_items WHERE id = 'b8000000-0000-0000-0000-000000000001') = 100,
  'anomalie de l''élément calculée (1 000 - 900)');
SELECT set_config('kofinex.sampling', 'on', true);
SELECT pg_temp.fails($q$UPDATE public.fa_samples SET status = 'concluded', conclusion = 'x', concluded_by = 'c4000000-0000-0000-0000-000000000004',
  actual_misstatement = 100$q$, 'conclusion avec un élément non testé', 'non testé');
SELECT set_config('kofinex.sampling', 'off', true);
UPDATE public.fa_sample_items SET result = 'no_exception', audited_amount = 700, tested_by = 'c4000000-0000-0000-0000-000000000004'
 WHERE id = 'b8000000-0000-0000-0000-000000000002';
SELECT pg_temp.fails($q$UPDATE public.fa_samples SET status = 'concluded', conclusion = 'x', concluded_by = 'c4000000-0000-0000-0000-000000000004',
  actual_misstatement = 100$q$, 'conclusion sans projection du moteur', 'moteur');
SELECT set_config('kofinex.sampling', 'on', true);
SELECT pg_temp.fails($q$UPDATE public.fa_samples SET status = 'concluded', conclusion = 'x', concluded_by = 'c4000000-0000-0000-0000-000000000004',
  actual_misstatement = 10$q$, 'anomalie constatée incohérente avec les tests', 'incohérente');
UPDATE public.fa_samples SET status = 'concluded', conclusion = 'Anomalie à proposer', concluded_by = 'c4000000-0000-0000-0000-000000000004',
  actual_misstatement = 100, projected_misstatement = 200;
SELECT set_config('kofinex.sampling', 'off', true);
SELECT pg_temp.ok((SELECT status = 'concluded' FROM public.fa_samples), 'échantillon conclu');
SELECT pg_temp.fails($q$UPDATE public.fa_sample_items SET comment = 'modifié' WHERE id = 'b8000000-0000-0000-0000-000000000001'$q$,
  'échantillon conclu : tests figés', 'figés');
SELECT pg_temp.fails($q$UPDATE public.fa_samples SET status = 'testing'$q$, 'assistant : réouverture refusée', 'encadrement');

-- ------------------------------------------------------- circularisations
INSERT INTO public.fa_confirmations (id, organization_id, engagement_id, reference, confirmation_type, third_party, account_number,
                                     balance_date, book_balance, request_form, created_by)
VALUES ('c8000000-0000-0000-0000-000000000001', '18000000-0000-0000-0000-00000000000a', '58000000-0000-0000-0000-00000000000a',
        'CC1', 'receivable', 'Client Alpha', '411000', '2025-12-31', 1000, 'positive', 'c4000000-0000-0000-0000-000000000004');
SELECT pg_temp.fails($q$UPDATE public.fa_confirmations SET status = 'sent'$q$, 'envoi sans date', 'date');
UPDATE public.fa_confirmations SET status = 'sent', sent_on = '2026-01-10';
SELECT pg_temp.fails($q$UPDATE public.fa_confirmations SET book_balance = 900$q$, 'demande envoyée : contenu figé', 'contenu');
SELECT pg_temp.fails($q$DELETE FROM public.fa_confirmations$q$, 'demande envoyée : non supprimable', 'conservée');
SELECT pg_temp.fails($q$UPDATE public.fa_confirmations SET status = 'received', received_on = '2026-01-20'$q$,
  'réponse sans montant confirmé', 'montant');
UPDATE public.fa_confirmations SET status = 'received', received_on = '2026-01-20', confirmed_amount = 900;
SELECT pg_temp.ok((SELECT difference FROM public.fa_confirmations) = 100, 'écart de circularisation calculé (100)');
SELECT pg_temp.fails($q$UPDATE public.fa_confirmations SET status = 'closed', conclusion = 'OK'$q$, 'clôture sans rapprochement de l''écart',
  'rapprochement');
UPDATE public.fa_confirmations SET status = 'closed', conclusion = 'Écart expliqué', reconciliation = 'Avoir du 28/12 non comptabilisé';
SELECT pg_temp.ok((SELECT closed_by = 'c4000000-0000-0000-0000-000000000004' FROM public.fa_confirmations), 'circularisation close');
SELECT pg_temp.fails($q$UPDATE public.fa_confirmations SET conclusion = 'Autre'$q$, 'circularisation close : figée', 'close');

-- ------------------------------------------------------- anomalies et ajustements
SELECT pg_temp.fails($q$DO $d$ BEGIN
  INSERT INTO public.fa_misstatements (id, organization_id, engagement_id, reference, source_type, source_id, kind, description, created_by)
  VALUES ('d8000000-0000-0000-0000-000000000009', '18000000-0000-0000-0000-00000000000a', '58000000-0000-0000-0000-00000000000a',
          'AJ9', 'confirmation', 'c8000000-0000-0000-0000-000000000001', 'factual', 'Test déséquilibré', 'c4000000-0000-0000-0000-000000000004');
  INSERT INTO public.fa_misstatement_lines (organization_id, engagement_id, misstatement_id, account_number, debit)
  VALUES ('18000000-0000-0000-0000-00000000000a', '58000000-0000-0000-0000-00000000000a', 'd8000000-0000-0000-0000-000000000009', '701000', 100);
  SET CONSTRAINTS ALL IMMEDIATE;
END $d$$q$, 'écriture d''ajustement déséquilibrée refusée', 'déséquilibrée');
SET CONSTRAINTS ALL DEFERRED;
SELECT pg_temp.fails($q$INSERT INTO public.fa_misstatements (organization_id, engagement_id, reference, source_type, source_id, kind,
  description, created_by) VALUES ('18000000-0000-0000-0000-00000000000a', '58000000-0000-0000-0000-00000000000a', 'AJ8', 'sample',
  'c8000000-0000-0000-0000-000000000001', 'factual', 'Source fausse', 'c4000000-0000-0000-0000-000000000004')$q$,
  'anomalie rattachée à une source inexistante', 'source');
INSERT INTO public.fa_misstatements (id, organization_id, engagement_id, reference, source_type, source_id, kind, description, created_by)
VALUES ('d8000000-0000-0000-0000-000000000001', '18000000-0000-0000-0000-00000000000a', '58000000-0000-0000-0000-00000000000a',
        'AJ1', 'confirmation', 'c8000000-0000-0000-0000-000000000001', 'factual', 'Avoir non comptabilisé',
        'c4000000-0000-0000-0000-000000000004');
INSERT INTO public.fa_misstatement_lines (organization_id, engagement_id, misstatement_id, account_number, debit, credit) VALUES
  ('18000000-0000-0000-0000-00000000000a', '58000000-0000-0000-0000-00000000000a', 'd8000000-0000-0000-0000-000000000001', '701000', 100, 0),
  ('18000000-0000-0000-0000-00000000000a', '58000000-0000-0000-0000-00000000000a', 'd8000000-0000-0000-0000-000000000001', '411000', 0, 100);
SET CONSTRAINTS ALL IMMEDIATE;
SET CONSTRAINTS ALL DEFERRED;
SELECT pg_temp.ok(true, 'anomalie proposée avec une écriture équilibrée');
SELECT pg_temp.fails($q$UPDATE public.fa_misstatements SET status = 'uncorrected', entity_response = 'Refus'$q$,
  'assistant : décision sur l''anomalie refusée', 'encadrement');
SELECT pg_temp.act_as('c3000000-0000-0000-0000-000000000003');
SELECT pg_temp.fails($q$UPDATE public.fa_misstatements SET status = 'uncorrected'$q$, 'décision sans réponse de l''entité', 'check');
UPDATE public.fa_misstatements SET status = 'uncorrected', entity_response = 'La direction ne corrige pas (montant faible)';
SELECT pg_temp.ok((SELECT decided_by = 'c3000000-0000-0000-0000-000000000003' FROM public.fa_misstatements), 'anomalie non corrigée, décision tracée');
SELECT pg_temp.fails($q$UPDATE public.fa_misstatement_lines SET debit = 50 WHERE debit > 0$q$, 'anomalie décidée : écriture figée', 'figée');
SELECT pg_temp.fails($q$INSERT INTO public.fa_conclusions (organization_id, engagement_id, uncorrected_conclusion, updated_by)
  VALUES ('18000000-0000-0000-0000-00000000000a', '58000000-0000-0000-0000-00000000000a', 'x', 'c3000000-0000-0000-0000-000000000003')$q$,
  'chef de mission : conclusion sur les anomalies refusée');

-- ------------------------------------------------------- cloisonnement
SELECT pg_temp.act_as('c4000000-0000-0000-0000-000000000004');
SELECT pg_temp.ok((SELECT count(*) FROM public.trial_balance_entries) = 4 AND (SELECT count(*) FROM public.fiscal_years) = 2,
  'équipe de mission : lecture des balances N et N-1 de l''entité auditée');
CREATE TEMP TABLE upd AS WITH u AS (UPDATE public.trial_balance_entries SET closing_debit = 0 RETURNING 1) SELECT count(*) AS n FROM u;
SELECT pg_temp.ok((SELECT n FROM upd) = 0, 'équipe de mission : balances non modifiables (0 ligne modifiée)');
SELECT pg_temp.act_as('c6000000-0000-0000-0000-000000000006');
SELECT pg_temp.ok((SELECT count(*) FROM public.fa_sample_items) = 2, 'observatrice : lecture du dossier');
SELECT pg_temp.fails($q$INSERT INTO public.fa_confirmations (organization_id, engagement_id, reference, confirmation_type, third_party,
  balance_date, book_balance, request_form, created_by) VALUES ('18000000-0000-0000-0000-00000000000a',
  '58000000-0000-0000-0000-00000000000a', 'CC9', 'bank', 'Banque', '2025-12-31', 1, 'positive', 'c6000000-0000-0000-0000-000000000006')$q$,
  'observatrice : écriture refusée');
SELECT pg_temp.act_as('cb000000-0000-0000-0000-00000000000b');
SELECT pg_temp.ok((SELECT count(*) FROM public.fa_materiality) + (SELECT count(*) FROM public.fa_misstatements)
                  + (SELECT count(*) FROM public.fa_population_items) + (SELECT count(*) FROM public.trial_balance_entries) = 0,
  'autre organisation : rien de visible (dossier ni balances)');

-- ------------------------------------------------------- émission
RESET ROLE;
SET LOCAL session_replication_role = replica;
UPDATE public.engagements SET status = 'reporting' WHERE id = '58000000-0000-0000-0000-00000000000a';
SET LOCAL session_replication_role = origin;
SET LOCAL ROLE authenticated;
SELECT pg_temp.act_as('c2000000-0000-0000-0000-000000000002');
SELECT pg_temp.fails($q$UPDATE public.engagements SET status = 'issued' WHERE id = '58000000-0000-0000-0000-00000000000a'$q$,
  'émission refusée sans conclusion sur les anomalies non corrigées', 'non corrigées');
INSERT INTO public.fa_conclusions (organization_id, engagement_id, uncorrected_conclusion, updated_by)
VALUES ('18000000-0000-0000-0000-00000000000a', '58000000-0000-0000-0000-00000000000a',
        'Anomalies non corrigées inférieures au seuil de signification (jugement de l''associé)', 'c2000000-0000-0000-0000-000000000002');
SELECT pg_temp.ok(true, 'associé : conclusion sur les anomalies non corrigées');
SELECT pg_temp.fails($q$UPDATE public.engagements SET status = 'issued' WHERE id = '58000000-0000-0000-0000-00000000000a'$q$,
  'conditions du socle encore requises (approbation de l''associé)', 'associé');
RESET ROLE;
SET LOCAL session_replication_role = replica;
UPDATE public.engagements SET status = 'issued' WHERE id = '58000000-0000-0000-0000-00000000000a';
SET LOCAL session_replication_role = origin;
SET LOCAL ROLE authenticated;
SELECT pg_temp.fails($q$UPDATE public.fa_account_reviews SET conclusion = 'modifiée'$q$, 'mission émise : dossier figé', 'figé');

ROLLBACK;
\echo 'Tous les tests de l''audit financier (SQL) sont passés.'
