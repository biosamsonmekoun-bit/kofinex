-- =====================================================================
-- Tests migration 0018 (lot 12A) : catalogue versionné, compte de facturation, abonnements.
-- RLS (administrateur de la plateforme, owner, admin, membre, autre organisation, visiteur anonyme), écriture
-- commerciale refusée au client, version publiée figée, montants selon la devise, un seul abonnement vivant,
-- un seul essai par organisation et par identité de facturation, journal, acteur IA.
-- Montants et offres FICTIFS.
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
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA pg_temp TO authenticated, anon;

INSERT INTO auth.users (id, email) VALUES
  ('aa000000-0000-0000-0000-0000000000aa', 'plateforme@kofinex.test'),
  ('a0000000-0000-0000-0000-00000000000a', 'alice@cabinet-a.test'),     -- owner A
  ('d0000000-0000-0000-0000-00000000000d', 'dan@cabinet-a.test'),       -- admin A
  ('c0000000-0000-0000-0000-00000000000c', 'carla@cabinet-a.test'),     -- membre A
  ('b0000000-0000-0000-0000-00000000000b', 'bob@cabinet-b.test');       -- owner B
UPDATE public.profiles SET is_platform_admin = true WHERE id = 'aa000000-0000-0000-0000-0000000000aa';

SELECT pg_temp.ok((SELECT count(*) FROM public.billing_modules) = 11
                  AND NOT EXISTS (SELECT 1 FROM public.billing_modules WHERE key = 'connectors'),
                  'modules : les 11 modules livrés, sans connecteurs (12C)');
SELECT pg_temp.ok((SELECT grace_days = 7 AND seller_country = 'BJ' AND jsonb_object_keys_count = 17
                     FROM public.billing_settings, LATERAL (SELECT count(*) AS jsonb_object_keys_count
                                                             FROM jsonb_object_keys(country_currencies)) k),
                  'paramètres : grâce 7 jours, vendeur au Bénin, 17 pays OHADA (§ 16)');
SELECT pg_temp.ok(public.billing_currency_for('cm') = 'XAF' AND public.billing_currency_for('KM') = 'KMF'
                  AND public.billing_currency_for('FR') IS NULL, 'devise par pays : CM → XAF, KM → KMF, FR non ouvert');

SET LOCAL ROLE authenticated;
SELECT pg_temp.act_as('a0000000-0000-0000-0000-00000000000a');
INSERT INTO public.organizations (id, name, slug, created_by)
VALUES ('10000000-0000-0000-0000-00000000000a', 'Cabinet A', 'cabinet-a-billing', 'a0000000-0000-0000-0000-00000000000a');
INSERT INTO public.organization_members (organization_id, user_id, role) VALUES
  ('10000000-0000-0000-0000-00000000000a', 'd0000000-0000-0000-0000-00000000000d', 'admin'),
  ('10000000-0000-0000-0000-00000000000a', 'c0000000-0000-0000-0000-00000000000c', 'member');
SELECT pg_temp.act_as('b0000000-0000-0000-0000-00000000000b');
INSERT INTO public.organizations (id, name, slug, created_by)
VALUES ('10000000-0000-0000-0000-00000000000b', 'Cabinet B', 'cabinet-b-billing', 'b0000000-0000-0000-0000-00000000000b');

-- ---------------------------------------------------------------- catalogue
SELECT pg_temp.act_as('a0000000-0000-0000-0000-00000000000a');
SELECT pg_temp.fails($q$INSERT INTO public.billing_products (code, kind, name) VALUES ('PIRATE', 'plan', 'x')$q$,
                     'owner : création d''offre refusée');
UPDATE public.billing_settings SET grace_days = 90;     -- RLS : aucune ligne modifiable par l'owner
SELECT pg_temp.ok((SELECT grace_days FROM public.billing_settings) = 7, 'owner : paramètres de la plateforme non modifiables');

SELECT pg_temp.act_as('aa000000-0000-0000-0000-0000000000aa');
INSERT INTO public.billing_products (id, code, kind, name) VALUES
  ('20000000-0000-0000-0000-000000000001', 'TEST_ESSENTIEL', 'plan', 'Offre de test'),
  ('20000000-0000-0000-0000-000000000002', 'TEST_OPTION', 'addon', 'Option de test');
INSERT INTO public.billing_product_versions (id, product_id, version_no, label, trial_days) VALUES
  ('30000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000001', 1, 'v1', 30),
  ('30000000-0000-0000-0000-000000000002', '20000000-0000-0000-0000-000000000001', 2, 'v2', 30);
SELECT pg_temp.fails($q$INSERT INTO public.billing_product_versions (product_id, version_no, label, status)
                        VALUES ('20000000-0000-0000-0000-000000000001', 9, 'x', 'published')$q$,
                     'une version se crée en brouillon');
SELECT pg_temp.fails($q$INSERT INTO public.billing_prices (product_version_id, billing_interval, currency, amount)
                        VALUES ('30000000-0000-0000-0000-000000000001', 'month', 'XOF', 15000.50)$q$,
                     'XOF sans décimale : 15 000,50 refusé');
SELECT pg_temp.fails($q$INSERT INTO public.billing_prices (product_version_id, billing_interval, currency, amount)
                        VALUES ('30000000-0000-0000-0000-000000000001', 'month', 'EUR', 10)$q$, 'devise non retenue refusée');
INSERT INTO public.billing_prices (product_version_id, billing_interval, currency, amount) VALUES
  ('30000000-0000-0000-0000-000000000001', 'month', 'XOF', 15000),
  ('30000000-0000-0000-0000-000000000001', 'month', 'CDF', 12.50),
  ('30000000-0000-0000-0000-000000000002', 'month', 'XOF', 20000);
SELECT pg_temp.ok(true, 'prix : XOF entier et CDF à deux décimales acceptés');
SELECT pg_temp.fails($q$UPDATE public.billing_product_versions SET status = 'published'
                        WHERE id = '30000000-0000-0000-0000-000000000001'$q$, 'publication sans module de base refusée');
INSERT INTO public.billing_entitlements (product_version_id, kind, module_key, quota_key, limit_value)
SELECT v, 'module', 'core', NULL, NULL FROM unnest(ARRAY['30000000-0000-0000-0000-000000000001',
                                                       '30000000-0000-0000-0000-000000000002']::uuid[]) v
UNION ALL SELECT '30000000-0000-0000-0000-000000000001', 'quota', NULL, 'users', 5;
SELECT pg_temp.fails($q$INSERT INTO public.billing_entitlements (product_version_id, kind, module_key)
                        VALUES ('30000000-0000-0000-0000-000000000001', 'module', 'connectors')$q$,
                     'module non livré refusé');

-- visibilité des brouillons
SELECT pg_temp.act_as('a0000000-0000-0000-0000-00000000000a');
SELECT pg_temp.ok((SELECT count(*) FROM public.billing_product_versions) = 0
                  AND (SELECT count(*) FROM public.billing_prices) = 0, 'owner : brouillons invisibles');

SELECT pg_temp.act_as('aa000000-0000-0000-0000-0000000000aa');
UPDATE public.billing_product_versions SET status = 'published' WHERE id = '30000000-0000-0000-0000-000000000001';
SELECT pg_temp.ok((SELECT published_at IS NOT NULL AND published_by = 'aa000000-0000-0000-0000-0000000000aa'
                     FROM public.billing_product_versions WHERE id = '30000000-0000-0000-0000-000000000001'),
                  'publication : date et auteur posés par la base');
SELECT pg_temp.fails($q$UPDATE public.billing_prices SET amount = 1 WHERE product_version_id = '30000000-0000-0000-0000-000000000001'$q$,
                     'version publiée : prix figé');
SELECT pg_temp.fails($q$INSERT INTO public.billing_entitlements (product_version_id, kind, quota_key, limit_value)
                        VALUES ('30000000-0000-0000-0000-000000000001', 'quota', 'companies', 99)$q$,
                     'version publiée : droits figés');
SELECT pg_temp.fails($q$UPDATE public.billing_product_versions SET trial_days = 365
                        WHERE id = '30000000-0000-0000-0000-000000000001'$q$, 'version publiée : essai figé');
SELECT pg_temp.fails($q$DELETE FROM public.billing_product_versions WHERE id = '30000000-0000-0000-0000-000000000001'$q$,
                     'version publiée : suppression refusée');
SELECT pg_temp.fails($q$UPDATE public.billing_product_versions SET status = 'published'
                        WHERE id = '30000000-0000-0000-0000-000000000002'$q$,
                     'une seule version publiée par offre');
SELECT pg_temp.fails($q$UPDATE public.billing_products SET kind = 'addon' WHERE id = '20000000-0000-0000-0000-000000000001'$q$,
                     'offre : nature non modifiable');

-- visiteur anonyme : catalogue publié seulement
SET LOCAL ROLE anon;
SELECT pg_temp.ok((SELECT count(*) FROM public.billing_product_versions) = 1
                  AND (SELECT count(*) FROM public.billing_prices) = 2
                  AND (SELECT count(*) FROM public.billing_products) = 1
                  AND (SELECT count(*) FROM public.billing_entitlements) = 2,
                  'anonyme : seule la version publiée (prix, droits, offre) est visible');
SELECT pg_temp.ok((SELECT country_currencies ->> 'SN' FROM public.billing_settings) = 'XOF',
                  'anonyme : pays et devises lisibles');
SELECT pg_temp.fails($q$SELECT grace_days FROM public.billing_settings$q$, 'anonyme : autres paramètres illisibles');
SELECT pg_temp.fails($q$SELECT * FROM public.billing_promotions$q$, 'anonyme : promotions illisibles');
SELECT pg_temp.fails($q$INSERT INTO public.billing_products (code, kind, name) VALUES ('ANON', 'plan', 'x')$q$,
                     'anonyme : écriture refusée');
SET LOCAL ROLE authenticated;

-- ---------------------------------------------------------------- compte de facturation
SELECT pg_temp.act_as('c0000000-0000-0000-0000-00000000000c');
SELECT pg_temp.fails($q$INSERT INTO public.billing_accounts (organization_id, legal_name, address, country_code, billing_email)
                        VALUES ('10000000-0000-0000-0000-00000000000a', 'X', 'Cotonou', 'BJ', 'x@a.test')$q$,
                     'membre : compte de facturation non modifiable');
SELECT pg_temp.act_as('a0000000-0000-0000-0000-00000000000a');
SELECT pg_temp.fails($q$INSERT INTO public.billing_accounts (organization_id, legal_name, address, country_code, billing_email)
                        VALUES ('10000000-0000-0000-0000-00000000000a', 'Cabinet A SARL', 'Cotonou', 'FR', 'f@a.test')$q$,
                     'pays hors OHADA refusé');
INSERT INTO public.billing_accounts (organization_id, legal_name, tax_id, address, country_code, billing_email)
VALUES ('10000000-0000-0000-0000-00000000000a', 'Cabinet A SARL', ' ifu 3201 ', 'Cotonou', 'BJ', ' Compta@Cabinet-A.test ');
SELECT pg_temp.ok((SELECT tax_id = 'IFU3201' AND billing_email = 'compta@cabinet-a.test' FROM public.billing_accounts),
                  'identifiant fiscal et e-mail normalisés');
SELECT pg_temp.act_as('d0000000-0000-0000-0000-00000000000d');
SELECT pg_temp.ok((SELECT count(*) FROM public.billing_accounts) = 1, 'admin : compte de facturation lisible');
SELECT pg_temp.act_as('c0000000-0000-0000-0000-00000000000c');
SELECT pg_temp.ok((SELECT count(*) FROM public.billing_accounts) = 0, 'membre : compte de facturation invisible');
SELECT pg_temp.act_as('b0000000-0000-0000-0000-00000000000b');
SELECT pg_temp.ok((SELECT count(*) FROM public.billing_accounts) = 0, 'autre organisation : compte invisible');

-- ---------------------------------------------------------------- abonnement
SELECT pg_temp.act_as('a0000000-0000-0000-0000-00000000000a');
SELECT pg_temp.fails($q$INSERT INTO public.subscriptions (organization_id, plan_code, status)
                        VALUES ('10000000-0000-0000-0000-00000000000a', 'X', 'active')$q$,
                     'owner : écriture directe d''un abonnement refusée');
SELECT pg_temp.fails($q$SELECT public.billing_start_trial('10000000-0000-0000-0000-00000000000a',
                        '30000000-0000-0000-0000-000000000002', 'month')$q$, 'essai sur un brouillon refusé');
SELECT pg_temp.fails($q$SELECT public.billing_start_trial('10000000-0000-0000-0000-00000000000a',
                        '30000000-0000-0000-0000-000000000001', 'year')$q$, 'essai sans prix pour la périodicité refusé');
SELECT pg_temp.act_as('d0000000-0000-0000-0000-00000000000d');
SELECT pg_temp.fails($q$SELECT public.billing_start_trial('10000000-0000-0000-0000-00000000000a',
                        '30000000-0000-0000-0000-000000000001', 'month')$q$, 'admin : essai réservé au propriétaire');
SELECT pg_temp.act_as('a0000000-0000-0000-0000-00000000000a');
SELECT public.billing_start_trial('10000000-0000-0000-0000-00000000000a', '30000000-0000-0000-0000-000000000001', 'month');
SELECT pg_temp.ok((SELECT status = 'trialing' AND currency = 'XOF' AND billing_interval = 'month'
                          AND trial_end BETWEEN now() + interval '29 days 23 hours' AND now() + interval '30 days 1 hour'
                          AND plan_code = 'TEST_ESSENTIEL' AND trial_tax_id = 'IFU3201'
                     FROM public.subscriptions WHERE organization_id = '10000000-0000-0000-0000-00000000000a'),
                  'essai : 30 jours fixés par la version, devise du pays (XOF)');
SELECT pg_temp.ok((SELECT count(*) FROM public.subscription_items WHERE kind = 'plan') = 1, 'essai : ligne d''offre créée');
SELECT pg_temp.fails($q$SELECT public.billing_start_trial('10000000-0000-0000-0000-00000000000a',
                        '30000000-0000-0000-0000-000000000001', 'month')$q$, 'un seul abonnement vivant');
SELECT pg_temp.fails($q$UPDATE public.billing_accounts SET country_code = 'CM'$q$,
                     'abonnement en cours : changement de devise refusé');
UPDATE public.billing_accounts SET country_code = 'SN';
SELECT pg_temp.ok((SELECT country_code FROM public.billing_accounts) = 'SN', 'changement de pays dans la même devise permis');

SELECT pg_temp.act_as('c0000000-0000-0000-0000-00000000000c');
SELECT pg_temp.ok((SELECT count(*) FROM public.subscriptions) = 0, 'membre : abonnement illisible (RLS)');
SELECT pg_temp.ok((SELECT status FROM public.billing_subscription_state('10000000-0000-0000-0000-00000000000a')) = 'trialing'
                  AND (SELECT count(*) FROM public.billing_subscription_items('10000000-0000-0000-0000-00000000000a')) = 1,
                  'membre : état de l''abonnement lisible pour l''affichage des droits');
SELECT pg_temp.fails($q$SELECT * FROM public.billing_org_usage('10000000-0000-0000-0000-00000000000a', now() - interval '1 day', now())$q$,
                     'membre : usages réservés');
SELECT pg_temp.fails($q$SELECT public.billing_schedule_cancel('10000000-0000-0000-0000-00000000000a', 'x')$q$,
                     'membre : résiliation refusée');
SELECT pg_temp.act_as('b0000000-0000-0000-0000-00000000000b');
SELECT pg_temp.ok((SELECT count(*) FROM public.billing_subscription_state('10000000-0000-0000-0000-00000000000a')) = 0,
                  'autre organisation : état invisible');
SELECT pg_temp.act_as('d0000000-0000-0000-0000-00000000000d');
SELECT pg_temp.ok((SELECT count(*) FROM public.subscriptions) = 1
                  AND (SELECT used FROM public.billing_org_usage('10000000-0000-0000-0000-00000000000a',
                         now() - interval '1 day', now() + interval '1 day') WHERE key = 'users') = 3,
                  'admin : abonnement lisible, usages mesurés (3 membres)');

SELECT pg_temp.act_as('a0000000-0000-0000-0000-00000000000a');
SELECT pg_temp.ok(public.billing_schedule_cancel('10000000-0000-0000-0000-00000000000a', 'Test')
                  = (SELECT trial_end FROM public.subscriptions), 'résiliation demandée : effet en fin d''essai');
SELECT pg_temp.fails($q$SELECT public.billing_schedule_cancel('10000000-0000-0000-0000-00000000000a', 'x')$q$,
                     'résiliation déjà demandée');
SELECT public.billing_reactivate('10000000-0000-0000-0000-00000000000a');
SELECT pg_temp.ok((SELECT cancel_at IS NULL AND cancel_reason IS NULL FROM public.subscriptions), 'réactivation : résiliation retirée');
SELECT pg_temp.fails($q$SELECT public.billing_reactivate('10000000-0000-0000-0000-00000000000a')$q$,
                     'réactivation sans résiliation en attente refusée');

-- anti-abus : même identifiant fiscal dans une autre organisation, même propriétaire dans une autre organisation
SELECT pg_temp.act_as('b0000000-0000-0000-0000-00000000000b');
INSERT INTO public.billing_accounts (organization_id, legal_name, tax_id, address, country_code, billing_email)
VALUES ('10000000-0000-0000-0000-00000000000b', 'Cabinet B', 'IFU 3201', 'Dakar', 'SN', 'b@cabinet-b.test');
SELECT pg_temp.fails($q$SELECT public.billing_start_trial('10000000-0000-0000-0000-00000000000b',
                        '30000000-0000-0000-0000-000000000001', 'month')$q$, 'essai refusé : identifiant fiscal déjà utilisé');
UPDATE public.billing_accounts SET tax_id = 'NINEA-777';
SELECT public.billing_start_trial('10000000-0000-0000-0000-00000000000b', '30000000-0000-0000-0000-000000000001', 'month');
SELECT pg_temp.ok(true, 'essai accordé avec une autre identité de facturation');
SELECT pg_temp.act_as('a0000000-0000-0000-0000-00000000000a');
INSERT INTO public.organizations (id, name, slug, created_by)
VALUES ('10000000-0000-0000-0000-0000000000a2', 'Cabinet A bis', 'cabinet-a-bis-billing', 'a0000000-0000-0000-0000-00000000000a');
INSERT INTO public.billing_accounts (organization_id, legal_name, tax_id, address, country_code, billing_email)
VALUES ('10000000-0000-0000-0000-0000000000a2', 'Autre', 'IFU-NOUVEAU', 'Lomé', 'TG', 'z@a.test');
SELECT pg_temp.fails($q$SELECT public.billing_start_trial('10000000-0000-0000-0000-0000000000a2',
                        '30000000-0000-0000-0000-000000000001', 'month')$q$, 'essai refusé : propriétaire ayant déjà eu un essai');

-- version retirée : les abonnés la lisent encore
SELECT pg_temp.act_as('aa000000-0000-0000-0000-0000000000aa');
UPDATE public.billing_product_versions SET status = 'retired' WHERE id = '30000000-0000-0000-0000-000000000001';
UPDATE public.billing_product_versions SET status = 'published' WHERE id = '30000000-0000-0000-0000-000000000002';
SELECT pg_temp.fails($q$UPDATE public.billing_product_versions SET label = 'v1 bis' WHERE id = '30000000-0000-0000-0000-000000000001'$q$,
                     'version retirée : figée');
SELECT pg_temp.act_as('c0000000-0000-0000-0000-00000000000c');
SELECT pg_temp.ok((SELECT count(*) FROM public.billing_entitlements WHERE product_version_id = '30000000-0000-0000-0000-000000000001') = 2,
                  'connecté : droits de la version retirée lisibles (abonnés)');
SET LOCAL ROLE anon;
SELECT pg_temp.ok((SELECT array_agg(label) FROM public.billing_product_versions) = ARRAY['v2'], 'anonyme : seule la nouvelle version publiée');
SET LOCAL ROLE authenticated;

-- ---------------------------------------------------------------- promotions
SELECT pg_temp.act_as('aa000000-0000-0000-0000-0000000000aa');
INSERT INTO public.billing_promotions (id, code, label, discount_type, percent, duration)
VALUES ('40000000-0000-0000-0000-000000000001', 'LANCEMENT', 'Lancement (test)', 'percent', 10, 'once');
SELECT pg_temp.fails($q$INSERT INTO public.billing_promotions (code, label, discount_type, fixed_amount, fixed_currency, duration)
                        VALUES ('FIXE', 'x', 'fixed', 100.5, 'XOF', 'once')$q$, 'remise fixe XOF à décimales refusée');
SELECT pg_temp.fails($q$UPDATE public.billing_promotions SET percent = 50$q$, 'promotion : conditions figées');
UPDATE public.billing_promotions SET status = 'disabled', label = 'Lancement (clos)';
SELECT pg_temp.ok((SELECT status FROM public.billing_promotions) = 'disabled', 'promotion : désactivation permise');
SELECT pg_temp.fails($q$DELETE FROM public.billing_promotions$q$, 'promotion : suppression refusée');
SELECT pg_temp.act_as('a0000000-0000-0000-0000-00000000000a');
SELECT pg_temp.ok((SELECT count(*) FROM public.billing_promotions) = 0, 'owner : promotions invisibles');

SELECT pg_temp.act_as('aa000000-0000-0000-0000-0000000000aa');
UPDATE public.billing_promotions SET status = 'active';
SELECT pg_temp.act_as('a0000000-0000-0000-0000-00000000000a');
SELECT pg_temp.ok((SELECT percent FROM public.billing_promotion_lookup('10000000-0000-0000-0000-00000000000a', ' lancement ')) = 10
                  AND (SELECT count(*) FROM public.billing_promotion_lookup('10000000-0000-0000-0000-00000000000a', 'INCONNU')) = 0,
                  'owner : un code se vérifie un par un (aucune liste)');
SELECT pg_temp.act_as('c0000000-0000-0000-0000-00000000000c');
SELECT pg_temp.fails($q$SELECT * FROM public.billing_promotion_lookup('10000000-0000-0000-0000-00000000000a', 'LANCEMENT')$q$,
                     'membre : vérification de code refusée');
SELECT pg_temp.ok(public.billing_org_has_data('10000000-0000-0000-0000-00000000000a') = false,
                  'membre : présence de données lisible (aucune entreprise)');
SELECT pg_temp.act_as('b0000000-0000-0000-0000-00000000000b');
SELECT pg_temp.ok(public.billing_org_has_data('10000000-0000-0000-0000-00000000000a') = false,
                  'autre organisation : présence de données non révélée');

-- ---------------------------------------------------------------- acteur IA, journal
SELECT pg_temp.act_as('aa000000-0000-0000-0000-0000000000aa');
SELECT set_config('kofinex.actor', 'ai', true);
SELECT pg_temp.fails($q$INSERT INTO public.billing_products (code, kind, name) VALUES ('IA', 'plan', 'x')$q$,
                     'IA : écriture du catalogue interdite');
SELECT pg_temp.act_as('a0000000-0000-0000-0000-00000000000a');
SELECT pg_temp.fails($q$SELECT public.billing_schedule_cancel('10000000-0000-0000-0000-00000000000a', 'x')$q$,
                     'IA : opération d''abonnement interdite');
SELECT set_config('kofinex.actor', '', true);
RESET ROLE;
SELECT pg_temp.ok((SELECT count(*) FROM public.audit_logs WHERE entity_type = 'subscriptions'
                     AND organization_id = '10000000-0000-0000-0000-00000000000a') >= 3
                  AND EXISTS (SELECT 1 FROM public.audit_logs WHERE entity_type = 'billing_product_versions'
                                AND user_id = 'aa000000-0000-0000-0000-0000000000aa'),
                  'journal : abonnement et catalogue tracés avec leur auteur');

ROLLBACK;
\echo 'Tous les tests de la facturation (catalogue et abonnements, SQL) sont passés.'
