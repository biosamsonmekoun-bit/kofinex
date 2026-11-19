-- =====================================================================
-- KOFINEX — 0006 : contrôle de gestion (lot 5)
--   budgets (scénarios budget / prévision, circuit de validation, gel), centres de coûts,
--   modèles de calcul de coûts (coûts complets, coût-volume-profit, coûts préétablis).
--   Les tables cost_centers, budgets, budget_lines, cost_entries existent depuis 0001.
-- =====================================================================

-- ---------------------------------------------------------------------
-- Centres de coûts
-- ---------------------------------------------------------------------
ALTER TABLE public.cost_centers
  ADD COLUMN description text,
  ADD COLUMN work_unit   text;          -- nature de l'unité d'œuvre habituelle (libellé libre)

-- ---------------------------------------------------------------------
-- Budgets : scénario, hypothèses, circuit
-- ---------------------------------------------------------------------
ALTER TABLE public.budgets
  ADD COLUMN scenario         text NOT NULL DEFAULT 'budget' CHECK (scenario IN ('budget','forecast')),
  ADD COLUMN notes            text,
  ADD COLUMN assumptions      jsonb NOT NULL DEFAULT '{}'::jsonb,   -- hypothèses de prévision saisies
  ADD COLUMN source_budget_id uuid,
  ADD COLUMN submitted_by     uuid REFERENCES public.profiles(id),
  ADD COLUMN submitted_at     timestamptz,
  ADD FOREIGN KEY (source_budget_id, company_id) REFERENCES public.budgets(id, company_id);

COMMENT ON COLUMN public.budget_lines.account_number IS
  'Racine de compte budgétée (charges ou produits) ; le réalisé agrège tous les comptes de la racine';

CREATE INDEX budgets_fy_idx ON public.budgets (fiscal_year_id, scenario);

-- Circuit : draft → submitted → approved → archived ; submitted → draft (renvoi).
-- Seul un budget « draft » est modifiable ; un budget approuvé est figé (sauf archivage).
CREATE OR REPLACE FUNCTION public.guard_budget() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status IN ('approved','archived') THEN
      RAISE EXCEPTION 'Budget approuvé ou archivé : suppression impossible' USING ERRCODE = 'check_violation';
    END IF;
    RETURN OLD;
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status THEN
    IF NOT ((OLD.status = 'draft' AND NEW.status = 'submitted')
         OR (OLD.status = 'submitted' AND NEW.status IN ('draft','approved'))
         OR (OLD.status = 'approved' AND NEW.status = 'archived')
         OR (OLD.status = 'draft' AND NEW.status = 'archived')) THEN
      RAISE EXCEPTION 'Transition de statut interdite : % → %', OLD.status, NEW.status USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.status = 'approved' AND NEW.approved_by = NEW.created_by
       AND NOT authz.has_org_role(NEW.organization_id, ARRAY['owner','admin']) THEN
      RAISE EXCEPTION 'Le budget doit être approuvé par une autre personne que son auteur'
        USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.status <> 'draft' AND (NEW.name, NEW.version, NEW.scenario, NEW.currency, NEW.fiscal_year_id,
                               NEW.assumptions, NEW.notes)
      IS DISTINCT FROM (OLD.name, OLD.version, OLD.scenario, OLD.currency, OLD.fiscal_year_id,
                        OLD.assumptions, OLD.notes) THEN
    RAISE EXCEPTION 'Budget % : seul un brouillon est modifiable', OLD.status USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER budgets_guard BEFORE UPDATE OR DELETE ON public.budgets
  FOR EACH ROW EXECUTE FUNCTION public.guard_budget();

CREATE OR REPLACE FUNCTION public.guard_budget_lines() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE v_status text;
BEGIN
  SELECT status INTO v_status FROM public.budgets WHERE id = coalesce(NEW.budget_id, OLD.budget_id);
  -- suppression en cascade d'un brouillon : le budget n'existe déjà plus
  IF v_status IS NOT NULL AND v_status <> 'draft' THEN
    RAISE EXCEPTION 'Budget % : lignes non modifiables', v_status USING ERRCODE = 'check_violation';
  END IF;
  RETURN coalesce(NEW, OLD);
END $$;
CREATE TRIGGER budget_lines_guard BEFORE INSERT OR UPDATE OR DELETE ON public.budget_lines
  FOR EACH ROW EXECUTE FUNCTION public.guard_budget_lines();

-- ---------------------------------------------------------------------
-- Saisies analytiques : interdites sur un exercice clôturé
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.guard_cost_entries() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE v_status text;
BEGIN
  SELECT status INTO v_status FROM public.fiscal_years WHERE id = coalesce(NEW.fiscal_year_id, OLD.fiscal_year_id);
  IF v_status = 'closed' THEN
    RAISE EXCEPTION 'Exercice clôturé : saisies analytiques non modifiables' USING ERRCODE = 'check_violation';
  END IF;
  RETURN coalesce(NEW, OLD);
END $$;
CREATE TRIGGER cost_entries_guard BEFORE INSERT OR UPDATE OR DELETE ON public.cost_entries
  FOR EACH ROW EXECUTE FUNCTION public.guard_cost_entries();
CREATE INDEX cost_entries_fy_idx ON public.cost_entries (fiscal_year_id, entry_date);

-- ---------------------------------------------------------------------
-- Modèles de calcul de coûts
-- ---------------------------------------------------------------------
CREATE TABLE public.costing_models (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  company_id      uuid NOT NULL,
  fiscal_year_id  uuid NOT NULL,
  name            text NOT NULL CHECK (length(trim(name)) > 0),
  model_type      text NOT NULL CHECK (model_type IN ('full_cost','cvp','standard_cost')),
  version         int NOT NULL DEFAULT 1 CHECK (version >= 1),
  status          text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','validated')),
  parameters      jsonb NOT NULL DEFAULT '{}'::jsonb,   -- clés, taux, standards : saisis par l'utilisateur
  results         jsonb,                                -- dernier calcul (traçable, figé à la validation)
  computed_at     timestamptz,
  balance_import_job_id uuid REFERENCES public.import_jobs(id),   -- balance utilisée pour le calcul
  validated_by    uuid REFERENCES public.profiles(id),
  validated_at    timestamptz,
  created_by      uuid NOT NULL REFERENCES public.profiles(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (fiscal_year_id, name, version),
  UNIQUE (id, company_id),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (fiscal_year_id, company_id) REFERENCES public.fiscal_years(id, company_id) ON DELETE CASCADE,
  CHECK (status <> 'validated' OR (validated_by IS NOT NULL AND validated_at IS NOT NULL AND results IS NOT NULL))
);
CREATE INDEX costing_models_fy_idx ON public.costing_models (fiscal_year_id, model_type);
CREATE TRIGGER costing_models_updated_at BEFORE UPDATE ON public.costing_models
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE OR REPLACE FUNCTION public.guard_costing_model() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status = 'validated' THEN
    RAISE EXCEPTION 'Modèle validé : non modifiable (créez une nouvelle version)' USING ERRCODE = 'check_violation';
  END IF;
  RETURN coalesce(NEW, OLD);
END $$;
CREATE TRIGGER costing_models_guard BEFORE UPDATE OR DELETE ON public.costing_models
  FOR EACH ROW EXECUTE FUNCTION public.guard_costing_model();

ALTER TABLE public.costing_models ENABLE ROW LEVEL SECURITY;
CREATE POLICY costing_models_select ON public.costing_models FOR SELECT TO authenticated
  USING (authz.can_access_company(company_id));
CREATE POLICY costing_models_insert ON public.costing_models FOR INSERT TO authenticated
  WITH CHECK (authz.has_company_role(company_id, ARRAY['accountant','controller']));
CREATE POLICY costing_models_update ON public.costing_models FOR UPDATE TO authenticated
  USING (authz.has_company_role(company_id, ARRAY['accountant','controller']))
  WITH CHECK (authz.has_company_role(company_id, ARRAY['accountant','controller']));
CREATE POLICY costing_models_delete ON public.costing_models FOR DELETE TO authenticated
  USING (authz.has_company_role(company_id, ARRAY['accountant','controller']));

GRANT SELECT, INSERT, UPDATE, DELETE ON public.costing_models TO authenticated;
GRANT ALL ON public.costing_models TO service_role;
