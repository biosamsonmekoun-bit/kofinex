-- =====================================================================
-- Tests migration 0005 : bibliothèque immuable, structure figée, analyses figées.
-- Prérequis : bibliothèque standard chargée (alembic 0005 ou scripts/library_seed_sql.py).
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

INSERT INTO auth.users (id, email) VALUES ('aa000000-0000-0000-0000-0000000000aa', 'admin@plateforme.test'),
  ('a0000000-0000-0000-0000-00000000000a', 'alice@a.test'), ('b0000000-0000-0000-0000-00000000000b', 'bob@b.test');
UPDATE public.profiles SET is_platform_admin = true WHERE id = 'aa000000-0000-0000-0000-0000000000aa';
INSERT INTO public.accounting_frameworks (id, code, name)
VALUES ('f0000000-0000-0000-0000-0000000000f1', 'TEST_FW5', 'Référentiel de test');

SELECT pg_temp.ok((SELECT count(*) FROM public.financial_formulas
                    WHERE organization_id IS NULL AND status = 'published' AND library_version IS NOT NULL) >= 30,
                  'bibliothèque standard publiée');

SET LOCAL ROLE authenticated;
SELECT pg_temp.act_as('a0000000-0000-0000-0000-00000000000a');
SELECT pg_temp.ok((SELECT count(*) FROM public.financial_formulas WHERE code = 'FR') = 1, 'formules lisibles par tous');
WITH u AS (UPDATE public.financial_formulas SET status = 'deprecated' WHERE code = 'FR' RETURNING 1)
SELECT pg_temp.ok((SELECT count(*) FROM u) = 0, 'utilisateur : bibliothèque non modifiable (0 ligne)');

RESET ROLE;
SELECT pg_temp.fails($q$UPDATE public.financial_formulas SET expression = '1' WHERE code = 'FR'$q$,
  'formule publiée : expression figée même pour le propriétaire de la base');
SELECT pg_temp.fails($q$DELETE FROM public.financial_formulas WHERE code = 'FR'$q$, 'formule publiée : non supprimable');
UPDATE public.financial_formulas SET status = 'deprecated' WHERE code = 'ROTATION_ACTIF';
SELECT pg_temp.ok(true, 'formule publiée : retrait possible');
SELECT pg_temp.fails($q$UPDATE public.financial_formulas SET status = 'published' WHERE code = 'ROTATION_ACTIF'$q$,
  'formule retirée : définitive');

SET LOCAL ROLE authenticated;
SELECT pg_temp.act_as('aa000000-0000-0000-0000-0000000000aa');
INSERT INTO public.framework_versions (id, framework_id, version_label, effective_from, source_reference)
VALUES ('fa000000-0000-0000-0000-0000000000a5', 'f0000000-0000-0000-0000-0000000000f1', 'T5', '2018-01-01', 'Test');
INSERT INTO public.statement_line_definitions (framework_version_id, statement_type, line_code, label, display_order, kind)
VALUES ('fa000000-0000-0000-0000-0000000000a5', 'balance_sheet_assets', 'L1', 'Ligne test', 1, 'detail');
INSERT INTO public.framework_concepts (framework_version_id, concept_code, expression, expression_ast)
VALUES ('fa000000-0000-0000-0000-0000000000a5', 'stocks', 'line("L1")', '{"fn":"line","args":["L1"]}');
SELECT pg_temp.fails($q$INSERT INTO public.statement_line_definitions (framework_version_id, statement_type, line_code,
    label, display_order, kind) VALUES ('fa000000-0000-0000-0000-0000000000a5', 'balance_sheet_assets', 'L2', 'x', 2, 'total')$q$,
  'ligne de total sans formule refusée');
UPDATE public.framework_versions SET status = 'published', published_at = now()
 WHERE id = 'fa000000-0000-0000-0000-0000000000a5';
SELECT pg_temp.fails($q$UPDATE public.statement_line_definitions SET label = 'x'$q$, 'version publiée : structure figée');
SELECT pg_temp.fails($q$DELETE FROM public.framework_concepts$q$, 'version publiée : concepts figés');

SELECT pg_temp.act_as('b0000000-0000-0000-0000-00000000000b');
SELECT pg_temp.fails($q$INSERT INTO public.framework_concepts (framework_version_id, concept_code, expression, expression_ast)
  VALUES ('fa000000-0000-0000-0000-0000000000a5', 'stocks_bis', '1', '{"num":"1"}')$q$, 'utilisateur : concepts non modifiables');

-- ------------------------------------------------------- analyse figée une fois terminée
SELECT pg_temp.act_as('a0000000-0000-0000-0000-00000000000a');
INSERT INTO public.organizations (id, name, slug, created_by)
VALUES ('10000000-0000-0000-0000-00000000000a', 'Org A', 'org-a-fe', 'a0000000-0000-0000-0000-00000000000a');
INSERT INTO public.companies (id, organization_id, name, framework_id, created_by)
VALUES ('20000000-0000-0000-0000-0000000000a1', '10000000-0000-0000-0000-00000000000a', 'A1',
        'f0000000-0000-0000-0000-0000000000f1', 'a0000000-0000-0000-0000-00000000000a');
INSERT INTO public.fiscal_years (id, organization_id, company_id, label, start_date, end_date, created_by)
VALUES ('30000000-0000-0000-0000-0000000000a1', '10000000-0000-0000-0000-00000000000a',
        '20000000-0000-0000-0000-0000000000a1', '2025', '2025-01-01', '2025-12-31', 'a0000000-0000-0000-0000-00000000000a');
INSERT INTO public.financial_analyses (id, organization_id, company_id, fiscal_year_id, analysis_type, engine_version,
                                       status, started_by)
VALUES ('50000000-0000-0000-0000-0000000000a1', '10000000-0000-0000-0000-00000000000a',
        '20000000-0000-0000-0000-0000000000a1', '30000000-0000-0000-0000-0000000000a1', 'annual', 'TEST', 'running',
        'a0000000-0000-0000-0000-00000000000a');
INSERT INTO public.financial_indicators (organization_id, analysis_id, formula_id, formula_code, formula_version, value,
                                         status, unit)
SELECT '10000000-0000-0000-0000-00000000000a', '50000000-0000-0000-0000-0000000000a1', id, code, version, 100, 'ok', unit
  FROM public.financial_formulas WHERE code = 'FR';
UPDATE public.financial_analyses SET status = 'completed', completed_at = now()
 WHERE id = '50000000-0000-0000-0000-0000000000a1';
SELECT pg_temp.ok(true, 'analyse : indicateurs enregistrés puis analyse terminée');
SELECT pg_temp.fails($q$UPDATE public.financial_indicators SET value = 1$q$, 'analyse terminée : indicateurs figés');
SELECT pg_temp.fails($q$UPDATE public.financial_analyses SET summary = '{}'$q$, 'analyse terminée : figée');

SELECT pg_temp.act_as('b0000000-0000-0000-0000-00000000000b');
SELECT pg_temp.ok((SELECT count(*) FROM public.financial_indicators) = 0, 'autre tenant : indicateurs invisibles');
SELECT pg_temp.ok((SELECT count(*) FROM public.financial_analyses) = 0, 'autre tenant : analyses invisibles');

ROLLBACK;
\echo 'Tous les tests du moteur financier (SQL) sont passés.'
