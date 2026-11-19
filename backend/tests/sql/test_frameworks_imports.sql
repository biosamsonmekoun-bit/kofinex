-- =====================================================================
-- Tests migration 0004 : verrouillage des versions de référentiel, lignes d'import.
-- Données FICTIVES (référentiel de test, comptes de test).
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
  ('aa000000-0000-0000-0000-0000000000aa', 'admin@plateforme.test'),
  ('a0000000-0000-0000-0000-00000000000a', 'alice@a.test'),
  ('b0000000-0000-0000-0000-00000000000b', 'bob@b.test'),
  ('c0000000-0000-0000-0000-00000000000c', 'carla@a.test');
UPDATE public.profiles SET is_platform_admin = true WHERE id = 'aa000000-0000-0000-0000-0000000000aa';
INSERT INTO public.accounting_frameworks (id, code, name)
VALUES ('f0000000-0000-0000-0000-0000000000f1', 'TEST_FW', 'Référentiel de test');

SET LOCAL ROLE authenticated;

-- ------------------------------------------------------- versions (admin plateforme)
SELECT pg_temp.act_as('a0000000-0000-0000-0000-00000000000a');
SELECT pg_temp.fails($q$INSERT INTO public.framework_versions (framework_id, version_label, effective_from, source_reference)
  VALUES ('f0000000-0000-0000-0000-0000000000f1', 'pirate', '2020-01-01', 'x')$q$,
  'un utilisateur ordinaire ne crée pas de version de référentiel');

SELECT pg_temp.act_as('aa000000-0000-0000-0000-0000000000aa');
INSERT INTO public.framework_versions (id, framework_id, version_label, effective_from, source_reference)
VALUES ('fa000000-0000-0000-0000-0000000000a1', 'f0000000-0000-0000-0000-0000000000f1', 'T-2018',
        '2018-01-01', 'Texte de test');
INSERT INTO public.chart_of_accounts (framework_version_id, account_number, label, account_class, nature)
VALUES ('fa000000-0000-0000-0000-0000000000a1', '41', 'Racine test', 4, 'asset'),
       ('fa000000-0000-0000-0000-0000000000a1', '411', 'Compte test', 4, 'asset');
SELECT pg_temp.ok(true, 'admin plateforme : version brouillon et plan de comptes chargés');

UPDATE public.framework_versions SET status = 'published', published_at = now(),
       published_by = 'aa000000-0000-0000-0000-0000000000aa'
 WHERE id = 'fa000000-0000-0000-0000-0000000000a1';
SELECT pg_temp.ok(true, 'publication');

SELECT pg_temp.fails($q$INSERT INTO public.chart_of_accounts (framework_version_id, account_number, label, account_class)
  VALUES ('fa000000-0000-0000-0000-0000000000a1', '412', 'Ajout', 4)$q$, 'version publiée : ajout de compte refusé');
SELECT pg_temp.fails($q$UPDATE public.chart_of_accounts SET label = 'modifié'
  WHERE framework_version_id = 'fa000000-0000-0000-0000-0000000000a1'$q$, 'version publiée : modification refusée');
SELECT pg_temp.fails($q$DELETE FROM public.chart_of_accounts
  WHERE framework_version_id = 'fa000000-0000-0000-0000-0000000000a1'$q$, 'version publiée : suppression refusée');
SELECT pg_temp.fails($q$UPDATE public.framework_versions SET source_reference = 'autre'
  WHERE id = 'fa000000-0000-0000-0000-0000000000a1'$q$, 'version publiée : métadonnées figées');
SELECT pg_temp.fails($q$DELETE FROM public.framework_versions WHERE id = 'fa000000-0000-0000-0000-0000000000a1'$q$,
  'version publiée : non supprimable');

INSERT INTO public.framework_versions (id, framework_id, version_label, effective_from, source_reference)
VALUES ('fa000000-0000-0000-0000-0000000000a2', 'f0000000-0000-0000-0000-0000000000f1', 'T-2024',
        '2024-01-01', 'Texte de test 2');
SELECT pg_temp.fails($q$UPDATE public.framework_versions SET status = 'published', published_at = now()
  WHERE id = 'fa000000-0000-0000-0000-0000000000a2'$q$,
  'deux versions publiées ne peuvent pas couvrir la même période');
UPDATE public.framework_versions SET effective_to = '2024-01-01' WHERE id = 'fa000000-0000-0000-0000-0000000000a1';
UPDATE public.framework_versions SET status = 'published', published_at = now()
 WHERE id = 'fa000000-0000-0000-0000-0000000000a2';
SELECT pg_temp.ok(true, 'versions successives après fixation de la date de fin');

-- ------------------------------------------------------- entreprise de test
SELECT pg_temp.act_as('a0000000-0000-0000-0000-00000000000a');
INSERT INTO public.organizations (id, name, slug, created_by)
VALUES ('10000000-0000-0000-0000-00000000000a', 'Org A', 'org-a-fw', 'a0000000-0000-0000-0000-00000000000a');
INSERT INTO public.organization_members (organization_id, user_id, role)
VALUES ('10000000-0000-0000-0000-00000000000a', 'c0000000-0000-0000-0000-00000000000c', 'member');
INSERT INTO public.companies (id, organization_id, name, framework_id, created_by)
VALUES ('20000000-0000-0000-0000-0000000000a1', '10000000-0000-0000-0000-00000000000a', 'A1',
        'f0000000-0000-0000-0000-0000000000f1', 'a0000000-0000-0000-0000-00000000000a');
INSERT INTO public.company_members (organization_id, company_id, user_id, role)
VALUES ('10000000-0000-0000-0000-00000000000a', '20000000-0000-0000-0000-0000000000a1',
        'c0000000-0000-0000-0000-00000000000c', 'viewer');

SELECT pg_temp.ok(public.applicable_framework_version('20000000-0000-0000-0000-0000000000a1', '2023-12-31')
                  = 'fa000000-0000-0000-0000-0000000000a1', 'version applicable en 2023 : T-2018');
SELECT pg_temp.ok(public.applicable_framework_version('20000000-0000-0000-0000-0000000000a1', '2025-12-31')
                  = 'fa000000-0000-0000-0000-0000000000a2', 'version applicable en 2025 : T-2024');
SELECT pg_temp.ok(public.applicable_framework_version('20000000-0000-0000-0000-0000000000a1', '2017-12-31') IS NULL,
                  'aucune version avant 2018');

INSERT INTO public.fiscal_years (id, organization_id, company_id, label, start_date, end_date, created_by)
VALUES ('30000000-0000-0000-0000-0000000000a1', '10000000-0000-0000-0000-00000000000a',
        '20000000-0000-0000-0000-0000000000a1', '2025', '2025-01-01', '2025-12-31',
        'a0000000-0000-0000-0000-00000000000a');
INSERT INTO public.import_jobs (id, organization_id, company_id, fiscal_year_id, source_format, started_by)
VALUES ('40000000-0000-0000-0000-0000000000a1', '10000000-0000-0000-0000-00000000000a',
        '20000000-0000-0000-0000-0000000000a1', '30000000-0000-0000-0000-0000000000a1', 'xlsx',
        'a0000000-0000-0000-0000-00000000000a');
INSERT INTO public.import_staging_rows (organization_id, company_id, fiscal_year_id, import_job_id, source_row,
                                        status, account_number, closing_debit, raw)
VALUES ('10000000-0000-0000-0000-00000000000a', '20000000-0000-0000-0000-0000000000a1',
        '30000000-0000-0000-0000-0000000000a1', '40000000-0000-0000-0000-0000000000a1', 5, 'valid', '411100',
        1000, '["411100", 1000]');
SELECT pg_temp.fails($q$INSERT INTO public.import_staging_rows (organization_id, company_id, fiscal_year_id,
    import_job_id, source_row, status, raw)
  VALUES ('10000000-0000-0000-0000-00000000000a', '20000000-0000-0000-0000-0000000000a1',
          '30000000-0000-0000-0000-0000000000a1', '40000000-0000-0000-0000-0000000000a1', 6, 'valid', '[]')$q$,
  'ligne valide sans numéro de compte refusée');
SELECT pg_temp.fails($q$UPDATE public.import_jobs SET status = 'inconnu'
  WHERE id = '40000000-0000-0000-0000-0000000000a1'$q$, 'statut d''import inconnu refusé');

SELECT pg_temp.act_as('c0000000-0000-0000-0000-00000000000c');
SELECT pg_temp.ok((SELECT count(*) FROM public.import_staging_rows) = 1, 'lecteur : voit les lignes importées');
SELECT pg_temp.fails($q$INSERT INTO public.import_staging_rows (organization_id, company_id, fiscal_year_id,
    import_job_id, source_row, status, account_number, raw)
  VALUES ('10000000-0000-0000-0000-00000000000a', '20000000-0000-0000-0000-0000000000a1',
          '30000000-0000-0000-0000-0000000000a1', '40000000-0000-0000-0000-0000000000a1', 7, 'valid', '401', '[]')$q$,
  'lecteur : écriture refusée');

SELECT pg_temp.act_as('b0000000-0000-0000-0000-00000000000b');
SELECT pg_temp.ok((SELECT count(*) FROM public.import_staging_rows) = 0, 'autre tenant : aucune ligne visible');
SELECT pg_temp.ok((SELECT count(*) FROM public.chart_of_accounts) = 2, 'référentiels lisibles par tous');

SELECT pg_temp.act_as('a0000000-0000-0000-0000-00000000000a');
UPDATE public.fiscal_years SET status = 'closed', closed_at = now() WHERE id = '30000000-0000-0000-0000-0000000000a1';
SELECT pg_temp.fails($q$DELETE FROM public.import_staging_rows$q$, 'exercice clôturé : lignes d''import figées');

ROLLBACK;
\echo 'Tous les tests référentiels / imports sont passés.'
