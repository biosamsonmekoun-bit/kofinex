-- =====================================================================
-- Tests migration 0020 : budget relié au plan comptable (phase 3 du correctif du contrôle de gestion).
-- Types de budget (racines en données), plan de référence (plan de l'entreprise, sinon référentiel publié), comptes en
-- sommeil, budget d'investissement (classe 2 et 16), type figé, rubriques (avec ou sans compte), RLS, acteur IA.
-- Données FICTIVES ; transaction annulée à la fin.
-- =====================================================================
\set QUIET on
BEGIN;
CREATE OR REPLACE FUNCTION pg_temp.ok(cond boolean, label text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  IF cond IS DISTINCT FROM true THEN RAISE EXCEPTION 'ÉCHEC : %', label; END IF;
  RAISE NOTICE 'ok - %', label;
END $$;
CREATE OR REPLACE FUNCTION pg_temp.fails(q text, label text, expected text DEFAULT NULL) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  BEGIN
    EXECUTE q;
  EXCEPTION WHEN OTHERS THEN
    IF expected IS NOT NULL AND position(expected IN SQLERRM) = 0 THEN
      RAISE EXCEPTION 'ÉCHEC : % (erreur inattendue : %)', label, SQLERRM;
    END IF;
    RAISE NOTICE 'ok - % (refusé : %)', label, SQLERRM; RETURN;
  END;
  RAISE EXCEPTION 'ÉCHEC : % (aucune erreur levée)', label;
END $$;
CREATE OR REPLACE FUNCTION pg_temp.act_as(uid uuid) RETURNS void LANGUAGE sql AS $$
  SELECT set_config('request.jwt.claims', json_build_object('sub', uid, 'role', 'authenticated')::text, true);
$$;
-- ligne de budget annuelle (raccourci)
CREATE OR REPLACE FUNCTION pg_temp.line(b uuid, co uuid, acc text, rub uuid DEFAULT NULL) RETURNS void LANGUAGE sql AS $$
  INSERT INTO public.budget_lines (organization_id, company_id, budget_id, account_number, rubric_id, label, period, amount)
  VALUES ('1d000000-0000-0000-0000-00000000000a', co, b, acc, rub, coalesce(acc, 'Rubrique'), 0, 1000);
$$;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA pg_temp TO authenticated;

INSERT INTO auth.users (id, email) VALUES
  ('e3000000-0000-0000-0000-00000000000a', 'alice@bg.test'), ('e3000000-0000-0000-0000-00000000000c', 'carl@bg.test'),
  ('e3000000-0000-0000-0000-00000000000f', 'vera@bg.test'), ('e3000000-0000-0000-0000-00000000000b', 'bob@bg2.test');
INSERT INTO public.accounting_frameworks (id, code, name) VALUES ('f3000000-0000-0000-0000-0000000000fa', 'TEST_BUDG', 'Test budget');
SET LOCAL session_replication_role = replica;
INSERT INTO public.profiles (id, email) SELECT id, email FROM auth.users WHERE email LIKE '%@bg%.test' ON CONFLICT DO NOTHING;
INSERT INTO public.framework_versions (id, framework_id, version_label, effective_from, source_reference, status, published_at) VALUES
  ('f3000000-0000-0000-0000-0000000000f1', 'f3000000-0000-0000-0000-0000000000fa', 'TEST', '2020-01-01', 'Référentiel FICTIF', 'published', now());
INSERT INTO public.chart_of_accounts (framework_version_id, account_number, label, account_class, nature)
SELECT 'f3000000-0000-0000-0000-0000000000f1', n, l, substr(n, 1, 1)::int, k FROM (VALUES
  ('6', 'Charges', 'expense'), ('60', 'Achats', 'expense'), ('601', 'Achats de marchandises', 'expense'),
  ('62', 'Services extérieurs', 'expense'), ('70', 'Ventes', 'income'), ('701', 'Ventes de marchandises', 'income'),
  ('2', 'Immobilisations', 'asset'), ('21', 'Immobilisations corporelles', 'asset'), ('211', 'Terrains', 'asset'),
  ('16', 'Emprunts', 'liability'), ('162', 'Emprunts bancaires', 'liability'), ('401', 'Fournisseurs', 'liability')) t(n, l, k);
INSERT INTO public.organizations (id, name, slug, created_by) VALUES
  ('1d000000-0000-0000-0000-00000000000a', 'Cabinet BG', 'cab-bg', 'e3000000-0000-0000-0000-00000000000a'),
  ('1d000000-0000-0000-0000-00000000000b', 'Cabinet BG2', 'cab-bg2', 'e3000000-0000-0000-0000-00000000000b');
INSERT INTO public.organization_members (organization_id, user_id, role) VALUES
  ('1d000000-0000-0000-0000-00000000000a', 'e3000000-0000-0000-0000-00000000000a', 'owner'),
  ('1d000000-0000-0000-0000-00000000000a', 'e3000000-0000-0000-0000-00000000000c', 'member'),
  ('1d000000-0000-0000-0000-00000000000a', 'e3000000-0000-0000-0000-00000000000f', 'member'),
  ('1d000000-0000-0000-0000-00000000000b', 'e3000000-0000-0000-0000-00000000000b', 'owner');
-- I : entreprise sans plan comptable ouvert (référentiel publié) ; N : entreprise au plan comptable natif
INSERT INTO public.companies (id, organization_id, name, framework_id, created_by) VALUES
  ('2d000000-0000-0000-0000-0000000000a1', '1d000000-0000-0000-0000-00000000000a', 'Importée', 'f3000000-0000-0000-0000-0000000000fa', 'e3000000-0000-0000-0000-00000000000a'),
  ('2d000000-0000-0000-0000-0000000000a2', '1d000000-0000-0000-0000-00000000000a', 'Native', 'f3000000-0000-0000-0000-0000000000fa', 'e3000000-0000-0000-0000-00000000000a');
INSERT INTO public.company_members (organization_id, company_id, user_id, role)
SELECT '1d000000-0000-0000-0000-00000000000a', c, u, r FROM (VALUES
  ('2d000000-0000-0000-0000-0000000000a1'::uuid, 'e3000000-0000-0000-0000-00000000000c'::uuid, 'controller'),
  ('2d000000-0000-0000-0000-0000000000a2', 'e3000000-0000-0000-0000-00000000000c', 'controller'),
  ('2d000000-0000-0000-0000-0000000000a1', 'e3000000-0000-0000-0000-00000000000f', 'viewer')) t(c, u, r);
INSERT INTO public.fiscal_years (id, organization_id, company_id, label, start_date, end_date, created_by) VALUES
  ('3d000000-0000-0000-0000-0000000000a1', '1d000000-0000-0000-0000-00000000000a', '2d000000-0000-0000-0000-0000000000a1', '2026', '2026-01-01', '2026-12-31', 'e3000000-0000-0000-0000-00000000000a'),
  ('3d000000-0000-0000-0000-0000000000a2', '1d000000-0000-0000-0000-00000000000a', '2d000000-0000-0000-0000-0000000000a2', '2026', '2026-01-01', '2026-12-31', 'e3000000-0000-0000-0000-00000000000a');
-- (déclencheurs désactivés : la nature, normalement recopiée du référentiel par la base, est posée ici)
INSERT INTO public.company_accounts (organization_id, company_id, account_number, label, framework_version_id, chart_account_number, nature,
                                     is_active, created_by)
SELECT '1d000000-0000-0000-0000-00000000000a', '2d000000-0000-0000-0000-0000000000a2', n, l, 'f3000000-0000-0000-0000-0000000000f1', c, k, a,
       'e3000000-0000-0000-0000-00000000000c'
  FROM (VALUES ('601100', 'Achats locaux', '601', 'expense', true), ('601200', 'Achats importés (sommeil)', '601', 'expense', false),
               ('211000', 'Terrains', '211', 'asset', true)) t(n, l, c, k, a);
SET LOCAL session_replication_role = origin;

SELECT pg_temp.ok((SELECT count(*) FROM public.budget_kinds) = 5
                  AND (SELECT allowed_prefixes FROM public.budget_kinds WHERE key = 'investments') = '{2,16}'
                  AND NOT EXISTS (SELECT 1 FROM public.budget_kinds WHERE status <> 'to_validate'),
                  'types de budget en données, racines « à valider » ; investissement : classe 2 et 16');

SET LOCAL ROLE authenticated;
SELECT pg_temp.act_as('e3000000-0000-0000-0000-00000000000c');
UPDATE public.budget_kinds SET allowed_prefixes = '{1,2,3,4,5,6,7,8,9}' WHERE key = 'general';     -- RLS : aucune ligne
SELECT pg_temp.ok((SELECT allowed_prefixes FROM public.budget_kinds WHERE key = 'general') = '{6,7,8}',
                  'contrôleur : racines autorisées non modifiables (administrateur de la plateforme seulement)');
INSERT INTO public.budgets (id, organization_id, company_id, fiscal_year_id, name, created_by) VALUES
  ('7d000000-0000-0000-0000-0000000000a1', '1d000000-0000-0000-0000-00000000000a', '2d000000-0000-0000-0000-0000000000a1',
   '3d000000-0000-0000-0000-0000000000a1', 'Résultat', 'e3000000-0000-0000-0000-00000000000c');
INSERT INTO public.budgets (id, organization_id, company_id, fiscal_year_id, name, budget_kind, created_by) VALUES
  ('7d000000-0000-0000-0000-0000000000b1', '1d000000-0000-0000-0000-00000000000a', '2d000000-0000-0000-0000-0000000000a1',
   '3d000000-0000-0000-0000-0000000000a1', 'Investissements', 'investments', 'e3000000-0000-0000-0000-00000000000c'),
  ('7d000000-0000-0000-0000-0000000000a2', '1d000000-0000-0000-0000-00000000000a', '2d000000-0000-0000-0000-0000000000a2',
   '3d000000-0000-0000-0000-0000000000a2', 'Résultat natif', 'general', 'e3000000-0000-0000-0000-00000000000c');
SELECT pg_temp.ok((SELECT budget_kind FROM public.budgets WHERE id = '7d000000-0000-0000-0000-0000000000a1') = 'general',
                  'budget sans type précisé : budget de résultat (budgets existants inchangés)');

-- ------------------------------------------------------- entreprise sans plan ouvert : référentiel publié
SELECT pg_temp.line('7d000000-0000-0000-0000-0000000000a1', '2d000000-0000-0000-0000-0000000000a1', '601');
SELECT pg_temp.line('7d000000-0000-0000-0000-0000000000a1', '2d000000-0000-0000-0000-0000000000a1', '70');
SELECT pg_temp.ok((SELECT count(*) FROM public.budget_lines WHERE budget_id = '7d000000-0000-0000-0000-0000000000a1') = 2,
                  'référentiel publié : comptes 601 et racine 70 acceptés');
SELECT pg_temp.fails($q$SELECT pg_temp.line('7d000000-0000-0000-0000-0000000000a1', '2d000000-0000-0000-0000-0000000000a1', '609')$q$,
                     'compte absent du référentiel refusé', 'absent du plan comptable de référence');
SELECT pg_temp.fails($q$SELECT pg_temp.line('7d000000-0000-0000-0000-0000000000a1', '2d000000-0000-0000-0000-0000000000a1', '211')$q$,
                     'budget de résultat : compte de bilan refusé', 'hors des racines autorisées');
SELECT pg_temp.line('7d000000-0000-0000-0000-0000000000b1', '2d000000-0000-0000-0000-0000000000a1', '211');
SELECT pg_temp.line('7d000000-0000-0000-0000-0000000000b1', '2d000000-0000-0000-0000-0000000000a1', '162');
SELECT pg_temp.ok((SELECT count(*) FROM public.budget_lines WHERE budget_id = '7d000000-0000-0000-0000-0000000000b1') = 2,
                  'budget d''investissement : classe 2 et comptes 16 acceptés');
SELECT pg_temp.fails($q$SELECT pg_temp.line('7d000000-0000-0000-0000-0000000000b1', '2d000000-0000-0000-0000-0000000000a1', '401')$q$,
                     'budget d''investissement : autre compte de bilan refusé', 'hors des racines autorisées');
SELECT pg_temp.fails($q$SELECT pg_temp.line('7d000000-0000-0000-0000-0000000000b1', '2d000000-0000-0000-0000-0000000000a1', '601')$q$,
                     'budget d''investissement : compte de charges refusé', 'hors des racines autorisées');

-- ------------------------------------------------------- entreprise au plan ouvert : plan de l'entreprise
SELECT pg_temp.line('7d000000-0000-0000-0000-0000000000a2', '2d000000-0000-0000-0000-0000000000a2', '601100');
SELECT pg_temp.line('7d000000-0000-0000-0000-0000000000a2', '2d000000-0000-0000-0000-0000000000a2', '60');
SELECT pg_temp.ok((SELECT count(*) FROM public.budget_lines WHERE budget_id = '7d000000-0000-0000-0000-0000000000a2') = 2,
                  'plan de l''entreprise : compte 601100 et racine 60 qui le regroupe acceptés');
SELECT pg_temp.fails($q$SELECT pg_temp.line('7d000000-0000-0000-0000-0000000000a2', '2d000000-0000-0000-0000-0000000000a2', '601200')$q$,
                     'compte en sommeil refusé', 'en sommeil');
SELECT pg_temp.fails($q$SELECT pg_temp.line('7d000000-0000-0000-0000-0000000000a2', '2d000000-0000-0000-0000-0000000000a2', '701')$q$,
                     'compte du référentiel non ouvert dans le plan de l''entreprise refusé', 'absent du plan comptable de référence');
SELECT pg_temp.ok((SELECT count(*) FROM public.budget_reference_accounts('2d000000-0000-0000-0000-0000000000a2', '3d000000-0000-0000-0000-0000000000a2')
                     WHERE account_number = '601200' AND NOT is_active) = 1
                  AND NOT EXISTS (SELECT 1 FROM public.budget_reference_accounts('2d000000-0000-0000-0000-0000000000a2', '3d000000-0000-0000-0000-0000000000a2')
                                   WHERE account_number IN ('7', '70', '701')),
                  'plan de référence : comptes de l''entreprise et racines qui les regroupent seulement');

-- ------------------------------------------------------- type figé, rubriques
SELECT pg_temp.fails($q$UPDATE public.budgets SET budget_kind = 'investments' WHERE id = '7d000000-0000-0000-0000-0000000000a1'$q$,
                     'type figé dès qu''une ligne existe', 'Type de budget non modifiable');
INSERT INTO public.budget_rubrics (id, organization_id, company_id, budget_id, label) VALUES
  ('8d000000-0000-0000-0000-0000000000a1', '1d000000-0000-0000-0000-00000000000a', '2d000000-0000-0000-0000-0000000000a1',
   '7d000000-0000-0000-0000-0000000000a1', 'Frais de mission');
SELECT pg_temp.line('7d000000-0000-0000-0000-0000000000a1', '2d000000-0000-0000-0000-0000000000a1', NULL, '8d000000-0000-0000-0000-0000000000a1');
SELECT pg_temp.line('7d000000-0000-0000-0000-0000000000a1', '2d000000-0000-0000-0000-0000000000a1', '62', '8d000000-0000-0000-0000-0000000000a1');
SELECT pg_temp.ok((SELECT count(*) FROM public.budget_lines WHERE rubric_id = '8d000000-0000-0000-0000-0000000000a1') = 2,
                  'rubrique : une ligne sans compte et une ligne sur un compte');
SELECT pg_temp.fails($q$INSERT INTO public.budget_lines (organization_id, company_id, budget_id, label, period, amount)
  VALUES ('1d000000-0000-0000-0000-00000000000a', '2d000000-0000-0000-0000-0000000000a1', '7d000000-0000-0000-0000-0000000000a1', 'Vide', 0, 1)$q$,
  'ligne sans compte, sans centre et sans rubrique refusée', 'budget_lines_check');
SELECT pg_temp.fails($q$UPDATE public.budget_lines SET forecast_mode = 'estimé' WHERE rubric_id = '8d000000-0000-0000-0000-0000000000a1'$q$,
                     'mode de prévision hors liste refusé', 'forecast_mode');
UPDATE public.budget_lines SET forecast_mode = 'imported' WHERE rubric_id = '8d000000-0000-0000-0000-0000000000a1';
SELECT pg_temp.ok((SELECT count(*) FROM public.budget_lines WHERE forecast_mode = 'imported') = 2, 'mode de prévision : importé');

SELECT pg_temp.act_as('e3000000-0000-0000-0000-00000000000f');
SELECT pg_temp.ok((SELECT count(*) FROM public.budget_rubrics) = 1, 'lecteur : rubriques lisibles');
SELECT pg_temp.fails($q$INSERT INTO public.budget_rubrics (organization_id, company_id, budget_id, label) VALUES
  ('1d000000-0000-0000-0000-00000000000a', '2d000000-0000-0000-0000-0000000000a1', '7d000000-0000-0000-0000-0000000000a1', 'Pirate')$q$,
  'lecteur : création de rubrique refusée', 'row-level security');
SELECT pg_temp.act_as('e3000000-0000-0000-0000-00000000000b');
SELECT pg_temp.ok((SELECT count(*) FROM public.budget_rubrics) = 0, 'autre organisation : rubriques invisibles');
SELECT pg_temp.fails($q$SELECT * FROM public.budget_reference_accounts('2d000000-0000-0000-0000-0000000000a1', '3d000000-0000-0000-0000-0000000000a1')$q$,
                     'autre organisation : plan de référence inaccessible', 'inaccessible');

SELECT pg_temp.act_as('e3000000-0000-0000-0000-00000000000c');
UPDATE public.budgets SET status = 'submitted', submitted_by = 'e3000000-0000-0000-0000-00000000000c', submitted_at = now()
 WHERE id = '7d000000-0000-0000-0000-0000000000a1';
SELECT pg_temp.fails($q$UPDATE public.budget_rubrics SET label = 'Autre' WHERE id = '8d000000-0000-0000-0000-0000000000a1'$q$,
                     'budget soumis : rubriques figées', 'lignes non modifiables');
SELECT set_config('kofinex.actor', 'ai', true);
SELECT pg_temp.fails($q$INSERT INTO public.budget_rubrics (organization_id, company_id, budget_id, label) VALUES
  ('1d000000-0000-0000-0000-00000000000a', '2d000000-0000-0000-0000-0000000000a2', '7d000000-0000-0000-0000-0000000000a2', 'IA')$q$,
  'IA : écriture des rubriques interdite', 'IA');
SELECT set_config('kofinex.actor', '', true);

RESET ROLE;
ROLLBACK;
\echo 'Tous les tests du budget relié au plan comptable (SQL) sont passés.'
