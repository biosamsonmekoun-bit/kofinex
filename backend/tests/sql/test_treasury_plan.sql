-- =====================================================================
-- Tests migration 0021 : plan de trésorerie (phase 4 du correctif du contrôle de gestion).
-- Rubriques et sous-rubriques, montants positifs sur les lignes de saisie, prévision initiale figée à l'approbation et
-- recopiée en prévision actualisée, plan archivé figé, RLS, acteur IA, journal. Données FICTIVES ; transaction annulée.
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
CREATE OR REPLACE FUNCTION pg_temp.amt(r uuid, sc text, p int, a numeric) RETURNS void LANGUAGE sql AS $$
  INSERT INTO public.treasury_amounts (organization_id, company_id, plan_id, rubric_id, scenario, period, amount)
  VALUES ('1e000000-0000-0000-0000-00000000000a', '2e000000-0000-0000-0000-00000000000a', '7e000000-0000-0000-0000-0000000000a1', r, sc, p, a);
$$;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA pg_temp TO authenticated;

INSERT INTO auth.users (id, email) VALUES
  ('e4000000-0000-0000-0000-00000000000a', 'alice@tp.test'), ('e4000000-0000-0000-0000-00000000000c', 'carl@tp.test'),
  ('e4000000-0000-0000-0000-00000000000f', 'vera@tp.test'), ('e4000000-0000-0000-0000-00000000000b', 'bob@tp2.test');
INSERT INTO public.accounting_frameworks (id, code, name) VALUES ('f4000000-0000-0000-0000-0000000000fa', 'TEST_TRESO', 'Test trésorerie');
SET LOCAL session_replication_role = replica;
INSERT INTO public.profiles (id, email) SELECT id, email FROM auth.users WHERE email LIKE '%@tp%.test' ON CONFLICT DO NOTHING;
INSERT INTO public.organizations (id, name, slug, created_by) VALUES
  ('1e000000-0000-0000-0000-00000000000a', 'Cabinet TP', 'cab-tp', 'e4000000-0000-0000-0000-00000000000a'),
  ('1e000000-0000-0000-0000-00000000000b', 'Cabinet TP2', 'cab-tp2', 'e4000000-0000-0000-0000-00000000000b');
INSERT INTO public.organization_members (organization_id, user_id, role) VALUES
  ('1e000000-0000-0000-0000-00000000000a', 'e4000000-0000-0000-0000-00000000000a', 'owner'),
  ('1e000000-0000-0000-0000-00000000000a', 'e4000000-0000-0000-0000-00000000000c', 'member'),
  ('1e000000-0000-0000-0000-00000000000a', 'e4000000-0000-0000-0000-00000000000f', 'member'),
  ('1e000000-0000-0000-0000-00000000000b', 'e4000000-0000-0000-0000-00000000000b', 'owner');
INSERT INTO public.companies (id, organization_id, name, framework_id, created_by) VALUES
  ('2e000000-0000-0000-0000-00000000000a', '1e000000-0000-0000-0000-00000000000a', 'Société TP', 'f4000000-0000-0000-0000-0000000000fa', 'e4000000-0000-0000-0000-00000000000a');
INSERT INTO public.company_members (organization_id, company_id, user_id, role) VALUES
  ('1e000000-0000-0000-0000-00000000000a', '2e000000-0000-0000-0000-00000000000a', 'e4000000-0000-0000-0000-00000000000c', 'controller'),
  ('1e000000-0000-0000-0000-00000000000a', '2e000000-0000-0000-0000-00000000000a', 'e4000000-0000-0000-0000-00000000000f', 'viewer');
INSERT INTO public.fiscal_years (id, organization_id, company_id, label, start_date, end_date, created_by) VALUES
  ('3e000000-0000-0000-0000-00000000000a', '1e000000-0000-0000-0000-00000000000a', '2e000000-0000-0000-0000-00000000000a', '2026', '2026-01-01', '2026-12-31', 'e4000000-0000-0000-0000-00000000000a');
SET LOCAL session_replication_role = origin;

SET LOCAL ROLE authenticated;
SELECT pg_temp.act_as('e4000000-0000-0000-0000-00000000000f');
SELECT pg_temp.fails($q$INSERT INTO public.treasury_plans (organization_id, company_id, fiscal_year_id, name, created_by)
  VALUES ('1e000000-0000-0000-0000-00000000000a', '2e000000-0000-0000-0000-00000000000a', '3e000000-0000-0000-0000-00000000000a', 'X',
          'e4000000-0000-0000-0000-00000000000f')$q$, 'lecteur : création de plan refusée', 'row-level security');

SELECT pg_temp.act_as('e4000000-0000-0000-0000-00000000000c');
INSERT INTO public.treasury_plans (id, organization_id, company_id, fiscal_year_id, name, opening_balance, created_by) VALUES
  ('7e000000-0000-0000-0000-0000000000a1', '1e000000-0000-0000-0000-00000000000a', '2e000000-0000-0000-0000-00000000000a',
   '3e000000-0000-0000-0000-00000000000a', 'Plan 2026', 10000000, 'e4000000-0000-0000-0000-00000000000c');
SELECT pg_temp.fails($q$INSERT INTO public.treasury_plans (organization_id, company_id, fiscal_year_id, name, status, created_by)
  VALUES ('1e000000-0000-0000-0000-00000000000a', '2e000000-0000-0000-0000-00000000000a', '3e000000-0000-0000-0000-00000000000a', 'Y',
          'approved', 'e4000000-0000-0000-0000-00000000000c')$q$, 'un plan se crée en brouillon', 'brouillon');
INSERT INTO public.treasury_rubrics (id, organization_id, company_id, plan_id, parent_id, section, code, label, display_order, account_prefixes)
SELECT i::uuid, '1e000000-0000-0000-0000-00000000000a', '2e000000-0000-0000-0000-00000000000a', '7e000000-0000-0000-0000-0000000000a1',
       p::uuid, s, c, l, o, pr::text[]
  FROM (VALUES ('8e000000-0000-0000-0000-0000000000a1', NULL, 'receipts', '70', 'Ventes', 1, '{411}'),
               ('8e000000-0000-0000-0000-0000000000a2', '8e000000-0000-0000-0000-0000000000a1', 'receipts', NULL, 'Dépôt', 1, '{}'),
               ('8e000000-0000-0000-0000-0000000000a3', '8e000000-0000-0000-0000-0000000000a1', 'receipts', NULL, 'Économat', 2, '{}'),
               ('8e000000-0000-0000-0000-0000000000b1', NULL, 'disbursements', '66', 'Personnel', 1, '{42,66}')) t(i, p, s, c, l, o, pr);
SELECT pg_temp.ok((SELECT count(*) FROM public.treasury_rubrics) = 4, 'rubriques A et B, sous-rubriques');
SELECT pg_temp.fails($q$INSERT INTO public.treasury_rubrics (organization_id, company_id, plan_id, parent_id, section, label)
  VALUES ('1e000000-0000-0000-0000-00000000000a', '2e000000-0000-0000-0000-00000000000a', '7e000000-0000-0000-0000-0000000000a1',
          '8e000000-0000-0000-0000-0000000000a1', 'disbursements', 'Mauvaise section')$q$, 'sous-rubrique d''une autre section refusée', 'même section');
SELECT pg_temp.fails($q$INSERT INTO public.treasury_rubrics (organization_id, company_id, plan_id, parent_id, section, label)
  VALUES ('1e000000-0000-0000-0000-00000000000a', '2e000000-0000-0000-0000-00000000000a', '7e000000-0000-0000-0000-0000000000a1',
          '8e000000-0000-0000-0000-0000000000a2', 'receipts', 'Troisième niveau')$q$, 'un seul niveau de sous-rubriques', 'premier niveau');
SELECT pg_temp.fails($q$UPDATE public.treasury_rubrics SET account_prefixes = '{4011TOY}' WHERE label = 'Personnel'$q$,
                     'comptes associés non numériques refusés', 'numériques');
SELECT pg_temp.fails($q$UPDATE public.treasury_rubrics SET method = 'percent_of' WHERE label = 'Personnel'$q$,
                     'rubrique calculée sans base ni taux refusée', 'check');

SELECT pg_temp.amt('8e000000-0000-0000-0000-0000000000a2', 'initial', 1, 800000);
SELECT pg_temp.amt('8e000000-0000-0000-0000-0000000000a3', 'initial', 1, 350000);
SELECT pg_temp.amt('8e000000-0000-0000-0000-0000000000b1', 'initial', 1, 705000);
SELECT pg_temp.ok((SELECT sum(amount) FROM public.treasury_amounts) = 1855000, 'prévision initiale saisie en brouillon');
SELECT pg_temp.fails($q$SELECT pg_temp.amt('8e000000-0000-0000-0000-0000000000a1', 'initial', 2, 1)$q$,
                     'montant sur une rubrique à sous-rubriques refusé', 'sous-rubriques');
SELECT pg_temp.fails($q$SELECT pg_temp.amt('8e000000-0000-0000-0000-0000000000b1', 'initial', 2, -5)$q$,
                     'montant négatif refusé (le sens vient de la section)', 'check');
SELECT pg_temp.fails($q$SELECT pg_temp.amt('8e000000-0000-0000-0000-0000000000b1', 'updated', 1, 9)$q$,
                     'brouillon : prévision actualisée non modifiable', 'actualisée');
SELECT pg_temp.fails($q$SELECT pg_temp.amt('8e000000-0000-0000-0000-0000000000b1', 'initial', 13, 9)$q$,
                     'treizième mois refusé', 'check');

-- approbation : prévision initiale figée et recopiée en prévision actualisée
UPDATE public.treasury_plans SET status = 'approved' WHERE id = '7e000000-0000-0000-0000-0000000000a1';
SELECT pg_temp.ok((SELECT approved_at IS NOT NULL AND approved_by = 'e4000000-0000-0000-0000-00000000000c' FROM public.treasury_plans),
                  'approbation : date et auteur posés par la base');
SELECT pg_temp.ok((SELECT count(*) FROM public.treasury_amounts WHERE scenario = 'updated') = 3
                  AND (SELECT sum(amount) FROM public.treasury_amounts WHERE scenario = 'updated') = 1855000,
                  'approbation : prévision actualisée initialisée par la prévision initiale');
SELECT pg_temp.fails($q$UPDATE public.treasury_amounts SET amount = 1 WHERE scenario = 'initial'$q$,
                     'plan approuvé : prévision initiale figée', 'initiale');
UPDATE public.treasury_amounts SET amount = 900000 WHERE scenario = 'updated' AND rubric_id = '8e000000-0000-0000-0000-0000000000a2';
SELECT pg_temp.ok((SELECT amount FROM public.treasury_amounts WHERE scenario = 'updated' AND rubric_id = '8e000000-0000-0000-0000-0000000000a2') = 900000
                  AND (SELECT amount FROM public.treasury_amounts WHERE scenario = 'initial' AND rubric_id = '8e000000-0000-0000-0000-0000000000a2') = 800000,
                  'plan approuvé : prévision actualisée modifiable, initiale inchangée');
SELECT pg_temp.fails($q$UPDATE public.treasury_rubrics SET label = 'Autre' WHERE label = 'Personnel'$q$, 'plan approuvé : rubriques figées', 'figées');
SELECT pg_temp.fails($q$UPDATE public.treasury_plans SET opening_balance = 1$q$, 'plan approuvé : solde initial figé', 'figé');
UPDATE public.treasury_plans SET notes = 'Actualisation de mars';
SELECT pg_temp.ok((SELECT notes FROM public.treasury_plans) = 'Actualisation de mars', 'plan approuvé : notes modifiables');
SELECT pg_temp.fails($q$DELETE FROM public.treasury_plans$q$, 'plan approuvé : suppression refusée', 'suppression');
SELECT pg_temp.fails($q$UPDATE public.treasury_plans SET status = 'draft'$q$, 'retour en brouillon interdit', 'Transition');

-- archivage : tout est figé
UPDATE public.treasury_plans SET status = 'archived';
SELECT pg_temp.fails($q$UPDATE public.treasury_amounts SET amount = 1 WHERE scenario = 'updated'$q$, 'plan archivé : prévision figée', 'archived');

-- cloisonnement, IA, journal
SELECT pg_temp.act_as('e4000000-0000-0000-0000-00000000000f');
SELECT pg_temp.ok((SELECT count(*) FROM public.treasury_amounts) = 6, 'lecteur : plan lisible');
SELECT pg_temp.act_as('e4000000-0000-0000-0000-00000000000b');
SELECT pg_temp.ok((SELECT count(*) FROM public.treasury_plans) = 0 AND (SELECT count(*) FROM public.treasury_rubrics) = 0,
                  'autre organisation : plan invisible');
SELECT pg_temp.act_as('e4000000-0000-0000-0000-00000000000c');
SELECT set_config('kofinex.actor', 'ai', true);
SELECT pg_temp.fails($q$INSERT INTO public.treasury_plans (organization_id, company_id, fiscal_year_id, name, created_by)
  VALUES ('1e000000-0000-0000-0000-00000000000a', '2e000000-0000-0000-0000-00000000000a', '3e000000-0000-0000-0000-00000000000a', 'IA',
          'e4000000-0000-0000-0000-00000000000c')$q$, 'IA : écriture interdite', 'IA');
SELECT set_config('kofinex.actor', '', true);
RESET ROLE;
SELECT pg_temp.ok((SELECT count(*) FROM public.audit_logs WHERE entity_type = 'treasury_plans'
                     AND user_id = 'e4000000-0000-0000-0000-00000000000c') >= 3, 'journal : plan tracé avec son auteur');

ROLLBACK;
\echo 'Tous les tests du plan de trésorerie (SQL) sont passés.'
