-- =====================================================================
-- Tests migration 0017 : types acceptés par financial_statements.statement_type.
-- La contrainte est recopiée dans une table temporaire (LIKE … INCLUDING CONSTRAINTS : contrôles CHECK, sans clés
-- étrangères) pour l'éprouver sans construire toute une analyse.
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

SELECT pg_temp.ok((SELECT convalidated FROM pg_constraint WHERE conname = 'financial_statements_statement_type_check'),
                  'contrainte présente et validée');
CREATE TEMP TABLE fs_check (LIKE public.financial_statements INCLUDING CONSTRAINTS INCLUDING DEFAULTS);

-- chaque type de la structure des états (statement_line_definitions) est accepté
DO $$
DECLARE t text;
BEGIN
  FOR t IN SELECT x[1] FROM regexp_matches(pg_get_constraintdef((SELECT oid FROM pg_constraint
             WHERE conname = 'statement_line_definitions_statement_type_check')), '''([a-z_]+)''', 'g') AS x
  LOOP
    INSERT INTO fs_check (id, organization_id, company_id, fiscal_year_id, framework_version_id, statement_type,
                          engine_version, generated_by)
    VALUES (gen_random_uuid(), gen_random_uuid(), gen_random_uuid(), gen_random_uuid(), gen_random_uuid(), t, 'test',
            gen_random_uuid());
  END LOOP;
END $$;
SELECT pg_temp.ok((SELECT count(DISTINCT statement_type) FROM fs_check) = 5, 'les 5 types de la structure sont acceptés');

-- valeurs d'origine conservées
INSERT INTO fs_check (id, organization_id, company_id, fiscal_year_id, framework_version_id, statement_type, engine_version, generated_by)
SELECT gen_random_uuid(), gen_random_uuid(), gen_random_uuid(), gen_random_uuid(), gen_random_uuid(), t, 'test', gen_random_uuid()
  FROM unnest(ARRAY['balance_sheet','notes']) AS t;
SELECT pg_temp.ok((SELECT count(*) FROM fs_check WHERE statement_type IN ('balance_sheet','notes')) = 2,
                  'valeurs d''origine (balance_sheet, notes) toujours acceptées');

-- test négatif : un type inconnu est refusé
SELECT pg_temp.fails($q$INSERT INTO fs_check (id, organization_id, company_id, fiscal_year_id, framework_version_id,
  statement_type, engine_version, generated_by) VALUES (gen_random_uuid(), gen_random_uuid(), gen_random_uuid(),
  gen_random_uuid(), gen_random_uuid(), 'bilan_inconnu', 'test', gen_random_uuid())$q$, 'type inconnu refusé');

ROLLBACK;
\echo 'Tous les tests des types d''états financiers (SQL) sont passés.'
