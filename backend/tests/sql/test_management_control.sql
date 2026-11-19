-- =====================================================================
-- Tests migration 0006 : contrôle de gestion (circuit budgétaire, gel, séparation des tâches, RLS).
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

-- alice : propriétaire de l'organisation ; carl : contrôleur de gestion ; dan : lecteur ; bob : autre organisation
INSERT INTO auth.users (id, email) VALUES
  ('a0000000-0000-0000-0000-00000000000a', 'alice@a.test'), ('c0000000-0000-0000-0000-00000000000c', 'carl@a.test'),
  ('d0000000-0000-0000-0000-00000000000d', 'dan@a.test'), ('b0000000-0000-0000-0000-00000000000b', 'bob@b.test');
INSERT INTO public.accounting_frameworks (id, code, name)
VALUES ('f0000000-0000-0000-0000-0000000000f6', 'TEST_FW6', 'Référentiel de test');

SET LOCAL ROLE authenticated;
SELECT pg_temp.act_as('a0000000-0000-0000-0000-00000000000a');
INSERT INTO public.organizations (id, name, slug, created_by)
VALUES ('10000000-0000-0000-0000-00000000006a', 'Org A', 'org-a-cg', 'a0000000-0000-0000-0000-00000000000a');
INSERT INTO public.organization_members (organization_id, user_id, role) VALUES
  ('10000000-0000-0000-0000-00000000006a', 'c0000000-0000-0000-0000-00000000000c', 'member'),
  ('10000000-0000-0000-0000-00000000006a', 'd0000000-0000-0000-0000-00000000000d', 'member');
INSERT INTO public.companies (id, organization_id, name, framework_id, created_by)
VALUES ('20000000-0000-0000-0000-00000000006a', '10000000-0000-0000-0000-00000000006a', 'A1',
        'f0000000-0000-0000-0000-0000000000f6', 'a0000000-0000-0000-0000-00000000000a');
INSERT INTO public.company_members (organization_id, company_id, user_id, role) VALUES
  ('10000000-0000-0000-0000-00000000006a', '20000000-0000-0000-0000-00000000006a', 'c0000000-0000-0000-0000-00000000000c', 'controller'),
  ('10000000-0000-0000-0000-00000000006a', '20000000-0000-0000-0000-00000000006a', 'd0000000-0000-0000-0000-00000000000d', 'viewer');
INSERT INTO public.fiscal_years (id, organization_id, company_id, label, start_date, end_date, created_by)
VALUES ('30000000-0000-0000-0000-00000000006a', '10000000-0000-0000-0000-00000000006a',
        '20000000-0000-0000-0000-00000000006a', '2025', '2025-01-01', '2025-12-31', 'a0000000-0000-0000-0000-00000000000a');

-- ------------------------------------------------------- centres et saisies (contrôleur)
SELECT pg_temp.act_as('c0000000-0000-0000-0000-00000000000c');
INSERT INTO public.cost_centers (id, organization_id, company_id, code, name, center_type, work_unit)
VALUES ('60000000-0000-0000-0000-00000000006a', '10000000-0000-0000-0000-00000000006a',
        '20000000-0000-0000-0000-00000000006a', 'ATEL', 'Atelier', 'main', 'heure-machine');
INSERT INTO public.cost_entries (organization_id, company_id, fiscal_year_id, cost_center_id, account_number, entry_date,
                                 amount, cost_nature, source, created_by)
VALUES ('10000000-0000-0000-0000-00000000006a', '20000000-0000-0000-0000-00000000006a',
        '30000000-0000-0000-0000-00000000006a', '60000000-0000-0000-0000-00000000006a', '601', '2025-03-01',
        1000, 'direct', 'manual', 'c0000000-0000-0000-0000-00000000000c');
SELECT pg_temp.ok(true, 'contrôleur : centre et saisie analytique créés');

SELECT pg_temp.act_as('d0000000-0000-0000-0000-00000000000d');
SELECT pg_temp.ok((SELECT count(*) FROM public.cost_centers) = 1, 'lecteur : centres visibles');
SELECT pg_temp.fails($q$INSERT INTO public.cost_centers (organization_id, company_id, code, name, center_type)
  VALUES ('10000000-0000-0000-0000-00000000006a', '20000000-0000-0000-0000-00000000006a', 'X', 'X', 'main')$q$,
  'lecteur : création de centre refusée');

-- ------------------------------------------------------- circuit budgétaire
SELECT pg_temp.act_as('c0000000-0000-0000-0000-00000000000c');
INSERT INTO public.budgets (id, organization_id, company_id, fiscal_year_id, name, created_by)
VALUES ('70000000-0000-0000-0000-00000000006a', '10000000-0000-0000-0000-00000000006a',
        '20000000-0000-0000-0000-00000000006a', '30000000-0000-0000-0000-00000000006a', 'Budget 2025',
        'c0000000-0000-0000-0000-00000000000c');
INSERT INTO public.budget_lines (organization_id, company_id, budget_id, account_number, label, period, amount)
VALUES ('10000000-0000-0000-0000-00000000006a', '20000000-0000-0000-0000-00000000006a',
        '70000000-0000-0000-0000-00000000006a', '601', 'Achats', 0, 12000);
UPDATE public.budgets SET status = 'submitted', submitted_by = 'c0000000-0000-0000-0000-00000000000c',
                          submitted_at = now() WHERE id = '70000000-0000-0000-0000-00000000006a';
SELECT pg_temp.fails($q$INSERT INTO public.budget_lines (organization_id, company_id, budget_id, account_number, label, period, amount)
  VALUES ('10000000-0000-0000-0000-00000000006a', '20000000-0000-0000-0000-00000000006a',
          '70000000-0000-0000-0000-00000000006a', '62', 'Services', 0, 1)$q$, 'budget soumis : lignes figées');
SELECT pg_temp.fails($q$UPDATE public.budgets SET name = 'autre' WHERE id = '70000000-0000-0000-0000-00000000006a'$q$,
  'budget soumis : en-tête figé');
SELECT pg_temp.fails($q$UPDATE public.budgets SET status = 'approved', approved_by = 'c0000000-0000-0000-0000-00000000000c',
  approved_at = now() WHERE id = '70000000-0000-0000-0000-00000000006a'$q$, 'auteur non administrateur : auto-approbation refusée');

SELECT pg_temp.act_as('a0000000-0000-0000-0000-00000000000a');
UPDATE public.budgets SET status = 'approved', approved_by = 'a0000000-0000-0000-0000-00000000000a', approved_at = now()
 WHERE id = '70000000-0000-0000-0000-00000000006a';
SELECT pg_temp.ok((SELECT status FROM public.budgets WHERE id = '70000000-0000-0000-0000-00000000006a') = 'approved',
  'approbation par une autre personne');
SELECT pg_temp.fails($q$UPDATE public.budgets SET status = 'draft' WHERE id = '70000000-0000-0000-0000-00000000006a'$q$,
  'budget approuvé : retour en brouillon interdit');
SELECT pg_temp.fails($q$DELETE FROM public.budgets WHERE id = '70000000-0000-0000-0000-00000000006a'$q$,
  'budget approuvé : suppression interdite');
SELECT pg_temp.fails($q$UPDATE public.budget_lines SET amount = 1$q$, 'budget approuvé : lignes figées');
UPDATE public.budgets SET status = 'archived' WHERE id = '70000000-0000-0000-0000-00000000006a';
SELECT pg_temp.ok(true, 'budget approuvé : archivage possible');

-- ------------------------------------------------------- modèles de coûts
SELECT pg_temp.act_as('c0000000-0000-0000-0000-00000000000c');
INSERT INTO public.costing_models (id, organization_id, company_id, fiscal_year_id, name, model_type, parameters, created_by)
VALUES ('80000000-0000-0000-0000-00000000006a', '10000000-0000-0000-0000-00000000006a',
        '20000000-0000-0000-0000-00000000006a', '30000000-0000-0000-0000-00000000006a', 'Coûts complets', 'full_cost',
        '{}', 'c0000000-0000-0000-0000-00000000000c');
SELECT pg_temp.fails($q$UPDATE public.costing_models SET status = 'validated', validated_by = 'c0000000-0000-0000-0000-00000000000c',
  validated_at = now() WHERE id = '80000000-0000-0000-0000-00000000006a'$q$, 'validation sans résultat calculé refusée');
UPDATE public.costing_models SET results = '{"ok": true}', computed_at = now(), status = 'validated',
       validated_by = 'c0000000-0000-0000-0000-00000000000c', validated_at = now()
 WHERE id = '80000000-0000-0000-0000-00000000006a';
SELECT pg_temp.fails($q$UPDATE public.costing_models SET parameters = '{"x": 1}'$q$, 'modèle validé : figé');
SELECT pg_temp.fails($q$DELETE FROM public.costing_models$q$, 'modèle validé : non supprimable');

SELECT pg_temp.act_as('d0000000-0000-0000-0000-00000000000d');
WITH u AS (UPDATE public.cost_entries SET amount = 1 RETURNING 1)
SELECT pg_temp.ok((SELECT count(*) FROM u) = 0, 'lecteur : saisies analytiques non modifiables (0 ligne)');

SELECT pg_temp.act_as('b0000000-0000-0000-0000-00000000000b');
SELECT pg_temp.ok((SELECT count(*) FROM public.costing_models) + (SELECT count(*) FROM public.budgets)
                  + (SELECT count(*) FROM public.cost_entries) = 0, 'autre organisation : rien de visible');

-- ------------------------------------------------------- exercice clôturé
RESET ROLE;
UPDATE public.fiscal_years SET status = 'closed', closed_at = now(), closed_by = 'a0000000-0000-0000-0000-00000000000a'
 WHERE id = '30000000-0000-0000-0000-00000000006a';
SELECT pg_temp.fails($q$UPDATE public.cost_entries SET amount = 5$q$, 'exercice clôturé : saisies analytiques figées');

ROLLBACK;
\echo 'Tous les tests du contrôle de gestion (SQL) sont passés.'
