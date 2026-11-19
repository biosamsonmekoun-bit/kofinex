-- =====================================================================
-- KOFINEX — Migration 0005 : moteur financier
--   * structure des états et concepts d'analyse, par version de référentiel (figés à la publication)
--   * bibliothèque de formules versionnées et immuables
--   * analyses : états produits, indicateurs N et N-1, contrôles
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. Structure des états financiers (donnée du référentiel)
-- ---------------------------------------------------------------------
CREATE TABLE public.statement_line_definitions (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  framework_version_id uuid NOT NULL REFERENCES public.framework_versions(id) ON DELETE CASCADE,
  statement_type       text NOT NULL CHECK (statement_type IN
                        ('balance_sheet_assets','balance_sheet_liabilities','income_statement','cash_flow','off_balance')),
  line_code            text NOT NULL CHECK (line_code ~ '^[A-Za-z0-9_]{1,40}$'),
  label                text NOT NULL,
  display_order        int NOT NULL,
  kind                 text NOT NULL CHECK (kind IN ('detail','total','title')),
  total_formula        jsonb,          -- [[1,"AE"],[-1,"AF"]]
  total_formula_text   text,
  role                 text CHECK (role IN ('total_actif','total_passif','resultat_bilan','resultat_compte_resultat')),
  level                smallint NOT NULL DEFAULT 0 CHECK (level BETWEEN 0 AND 4),
  source_row           int,
  UNIQUE (framework_version_id, line_code),
  CHECK (kind <> 'total' OR total_formula IS NOT NULL)
);
CREATE UNIQUE INDEX statement_line_definitions_role_uq
  ON public.statement_line_definitions (framework_version_id, role) WHERE role IS NOT NULL;

-- ---------------------------------------------------------------------
-- 2. Concepts d'analyse liés au référentiel
-- ---------------------------------------------------------------------
CREATE TABLE public.framework_concepts (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  framework_version_id uuid NOT NULL REFERENCES public.framework_versions(id) ON DELETE CASCADE,
  concept_code         text NOT NULL CHECK (concept_code ~ '^[a-z][a-z0-9_]{1,60}$'),
  expression           text NOT NULL,
  expression_ast       jsonb NOT NULL,
  source_reference     text,
  source_row           int,
  UNIQUE (framework_version_id, concept_code)
);

ALTER TABLE public.framework_versions
  ADD COLUMN structure_sha256    char(64),
  ADD COLUMN concepts_sha256     char(64),
  ADD COLUMN structure_loaded_at timestamptz,
  ADD COLUMN concepts_loaded_at  timestamptz;

CREATE TRIGGER statement_line_definitions_guard
  BEFORE INSERT OR UPDATE OR DELETE ON public.statement_line_definitions
  FOR EACH ROW EXECUTE FUNCTION public.guard_framework_content();
CREATE TRIGGER framework_concepts_guard
  BEFORE INSERT OR UPDATE OR DELETE ON public.framework_concepts
  FOR EACH ROW EXECUTE FUNCTION public.guard_framework_content();

ALTER TABLE public.statement_line_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.framework_concepts ENABLE ROW LEVEL SECURITY;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.statement_line_definitions, public.framework_concepts TO authenticated;
GRANT ALL ON public.statement_line_definitions, public.framework_concepts TO service_role;
CREATE POLICY statement_line_definitions_select ON public.statement_line_definitions FOR SELECT TO authenticated USING (true);
CREATE POLICY statement_line_definitions_admin ON public.statement_line_definitions FOR ALL TO authenticated
  USING (authz.is_platform_admin()) WITH CHECK (authz.is_platform_admin());
CREATE POLICY framework_concepts_select ON public.framework_concepts FOR SELECT TO authenticated USING (true);
CREATE POLICY framework_concepts_admin ON public.framework_concepts FOR ALL TO authenticated
  USING (authz.is_platform_admin()) WITH CHECK (authz.is_platform_admin());

-- ---------------------------------------------------------------------
-- 3. Bibliothèque de formules : unités / catégories, immuabilité
-- ---------------------------------------------------------------------
ALTER TABLE public.financial_formulas DROP CONSTRAINT financial_formulas_unit_check;
ALTER TABLE public.financial_formulas ADD CONSTRAINT financial_formulas_unit_check
  CHECK (unit IN ('amount','ratio','percent','days','times','years'));
ALTER TABLE public.financial_formulas DROP CONSTRAINT financial_formulas_category_check;
ALTER TABLE public.financial_formulas ADD CONSTRAINT financial_formulas_category_check
  CHECK (category IN ('sig','caf','structure','liquidity','solvency','profitability','activity','growth','cash','custom'));
ALTER TABLE public.financial_formulas
  ADD COLUMN library_version text,           -- ex. KOFINEX-STD-1 (NULL pour une formule propre à un tenant)
  ADD COLUMN published_at    timestamptz;

CREATE OR REPLACE FUNCTION public.guard_financial_formula() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status <> 'draft' THEN
      RAISE EXCEPTION 'Formule publiée : suppression impossible (retirez-la)' USING ERRCODE = 'check_violation';
    END IF;
    RETURN OLD;
  END IF;
  IF OLD.status = 'published' AND (
       (to_jsonb(NEW) - 'status') IS DISTINCT FROM (to_jsonb(OLD) - 'status')
       OR NEW.status NOT IN ('published','deprecated')) THEN
    RAISE EXCEPTION 'Formule publiée : créez une nouvelle version au lieu de la modifier'
      USING ERRCODE = 'check_violation';
  END IF;
  IF OLD.status = 'deprecated' AND to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD) THEN
    RAISE EXCEPTION 'Formule retirée : aucune modification possible' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER financial_formulas_guard
  BEFORE UPDATE OR DELETE ON public.financial_formulas
  FOR EACH ROW EXECUTE FUNCTION public.guard_financial_formula();

-- ---------------------------------------------------------------------
-- 4. Analyses, états, indicateurs
-- ---------------------------------------------------------------------
ALTER TABLE public.financial_analyses
  ADD COLUMN framework_version_id    uuid REFERENCES public.framework_versions(id),
  ADD COLUMN source_import_job_id    uuid REFERENCES public.import_jobs(id),
  ADD COLUMN previous_fiscal_year_id uuid REFERENCES public.fiscal_years(id),
  ADD COLUMN previous_import_job_id  uuid REFERENCES public.import_jobs(id),
  ADD COLUMN controls                jsonb,     -- contrôles des états + contrôles croisés
  ADD COLUMN summary                 jsonb;     -- compteurs (indicateurs calculés, non calculables…)

ALTER TABLE public.financial_statements
  ADD COLUMN analysis_id uuid,
  ADD CONSTRAINT financial_statements_analysis_fk
    FOREIGN KEY (analysis_id, organization_id) REFERENCES public.financial_analyses(id, organization_id)
    ON DELETE CASCADE;
CREATE INDEX financial_statements_analysis_idx ON public.financial_statements (analysis_id);

ALTER TABLE public.financial_statement_lines
  ADD COLUMN kind  text NOT NULL DEFAULT 'detail' CHECK (kind IN ('detail','total','title')),
  ADD COLUMN role  text,
  ADD COLUMN level smallint NOT NULL DEFAULT 0;

ALTER TABLE public.financial_indicators
  ADD COLUMN message         text,
  ADD COLUMN previous_value  numeric(24,6),
  ADD COLUMN previous_status text;

-- Une analyse terminée est figée (on en relance une nouvelle) ; ses résultats aussi.
CREATE OR REPLACE FUNCTION public.guard_completed_analysis() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  v_status text;
BEGIN
  IF TG_TABLE_NAME = 'financial_analyses' THEN
    IF OLD.status = 'completed' AND TG_OP = 'UPDATE' THEN
      RAISE EXCEPTION 'Analyse terminée : non modifiable' USING ERRCODE = 'check_violation';
    END IF;
    RETURN coalesce(NEW, OLD);
  END IF;
  SELECT status INTO v_status FROM public.financial_analyses
   WHERE id = (to_jsonb(coalesce(NEW, OLD)) ->> 'analysis_id')::uuid;
  IF v_status = 'completed' AND TG_OP <> 'DELETE' THEN
    RAISE EXCEPTION 'Analyse terminée : résultats non modifiables' USING ERRCODE = 'check_violation';
  END IF;
  RETURN coalesce(NEW, OLD);
END $$;

CREATE TRIGGER financial_analyses_guard BEFORE UPDATE ON public.financial_analyses
  FOR EACH ROW EXECUTE FUNCTION public.guard_completed_analysis();
CREATE TRIGGER financial_indicators_guard BEFORE INSERT OR UPDATE ON public.financial_indicators
  FOR EACH ROW EXECUTE FUNCTION public.guard_completed_analysis();

CREATE INDEX financial_analyses_fy_idx ON public.financial_analyses (fiscal_year_id, started_at DESC)
  WHERE status = 'completed';

-- L'établissement des états fait partie de l'analyse : contrôleurs et analystes peuvent la lancer.
-- La validation / modification des états reste réservée au comptable.
DROP POLICY financial_statements_insert ON public.financial_statements;
CREATE POLICY financial_statements_insert ON public.financial_statements FOR INSERT TO authenticated
  WITH CHECK (authz.has_company_role(company_id, ARRAY['accountant','controller','analyst']));
DROP POLICY fs_lines_write ON public.financial_statement_lines;
CREATE POLICY fs_lines_insert ON public.financial_statement_lines FOR INSERT TO authenticated
  WITH CHECK (EXISTS (SELECT 1 FROM public.financial_statements s WHERE s.id = statement_id
                AND authz.has_company_role(s.company_id, ARRAY['accountant','controller','analyst'])));
CREATE POLICY fs_lines_update ON public.financial_statement_lines FOR UPDATE TO authenticated
  USING (EXISTS (SELECT 1 FROM public.financial_statements s WHERE s.id = statement_id
                AND authz.has_company_role(s.company_id, ARRAY['accountant'])));
CREATE POLICY fs_lines_delete ON public.financial_statement_lines FOR DELETE TO authenticated
  USING (EXISTS (SELECT 1 FROM public.financial_statements s WHERE s.id = statement_id
                AND authz.has_company_role(s.company_id, ARRAY['accountant'])));
