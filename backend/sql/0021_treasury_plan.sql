-- =====================================================================
-- KOFINEX — Migration 0021 : plan de trésorerie (correctif du contrôle de gestion, phase 4)
-- Décision 4 du 20 novembre 2026 (docs/CONTROLE_GESTION.md § 12.1) : prévision par rubriques avec règles de
-- calendrier, réalisé lu sur les comptes de trésorerie, aucune échéance simulée.
-- Modèle de référence : classeur « PLAN DE TRESORRRIE (1).xlsx » (feuilles Feuil1 et SUIVI) — comptes, intitulés,
-- A. encaissements, B. décaissements, sous-rubriques, douze mois, total, soldes de début et de fin de mois.
-- Les montants sont des prévisions : aucune écriture comptable n'est créée ni lue en écriture ici. Les soldes, totaux
-- et écarts sont calculés par le moteur (Decimal), jamais stockés. Aucune migration antérieure n'est réécrite.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. Plan de trésorerie d'un exercice
-- ---------------------------------------------------------------------
CREATE TABLE public.treasury_plans (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  company_id      uuid NOT NULL,
  fiscal_year_id  uuid NOT NULL,
  name            text NOT NULL CHECK (length(btrim(name)) > 0),
  currency        char(3) NOT NULL DEFAULT 'XOF' CHECK (currency ~ '^[A-Z]{3}$'),
  -- solde initial de trésorerie (début du premier mois) : saisi, ou repris de la comptabilité à une date donnée
  opening_balance numeric(20,2) NOT NULL DEFAULT 0,
  opening_source  text NOT NULL DEFAULT 'manual' CHECK (opening_source IN ('manual','accounting')),
  status          text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','archived')),
  notes           text,
  approved_by     uuid REFERENCES public.profiles(id),
  approved_at     timestamptz,
  created_by      uuid NOT NULL REFERENCES public.profiles(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (fiscal_year_id, name),
  UNIQUE (id, company_id),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (fiscal_year_id, company_id) REFERENCES public.fiscal_years(id, company_id) ON DELETE CASCADE,
  CHECK ((status = 'draft') = (approved_at IS NULL) OR status = 'archived')
);

-- ---------------------------------------------------------------------
-- 2. Rubriques : A. encaissements / B. décaissements, sous-rubriques, comptes associés, modalité de prévision
-- ---------------------------------------------------------------------
CREATE TABLE public.treasury_rubrics (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id  uuid NOT NULL,
  company_id       uuid NOT NULL,
  plan_id          uuid NOT NULL,
  parent_id        uuid REFERENCES public.treasury_rubrics(id) ON DELETE CASCADE,
  section          text NOT NULL CHECK (section IN ('receipts','disbursements')),
  code             text CHECK (code IS NULL OR code ~ '^[0-9]{1,20}$'),       -- colonne « CPTES » (affichage)
  label            text NOT NULL CHECK (length(btrim(label)) > 0),
  display_order    int NOT NULL DEFAULT 0,
  -- comptes de contrepartie des mouvements de trésorerie rattachés à la rubrique (réalisé) ; racines numériques
  account_prefixes text[] NOT NULL DEFAULT '{}',
  -- modalité de prévision : saisie ; pourcentage d'une autre rubrique (taux saisi par l'utilisateur) ; budget décalé
  -- d'un nombre de mois (règle de calendrier : délai de règlement)
  method           text NOT NULL DEFAULT 'manual' CHECK (method IN ('manual','percent_of','from_budget')),
  base_rubric_id   uuid REFERENCES public.treasury_rubrics(id) ON DELETE SET NULL,
  rate             numeric(9,4) CHECK (rate IS NULL OR (rate >= 0 AND rate <= 1000)),
  budget_id        uuid,
  delay_months     int NOT NULL DEFAULT 0 CHECK (delay_months BETWEEN 0 AND 12),
  cost_center_id   uuid,
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id, company_id),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (plan_id, company_id) REFERENCES public.treasury_plans(id, company_id) ON DELETE CASCADE,
  FOREIGN KEY (budget_id, company_id) REFERENCES public.budgets(id, company_id) ON DELETE SET NULL (budget_id),
  FOREIGN KEY (cost_center_id, company_id) REFERENCES public.cost_centers(id, company_id) ON DELETE SET NULL (cost_center_id),
  CHECK (method <> 'percent_of' OR (base_rubric_id IS NOT NULL AND rate IS NOT NULL)),
  CHECK (method <> 'from_budget' OR budget_id IS NOT NULL),
  CHECK (base_rubric_id IS NULL OR base_rubric_id <> id)
);
CREATE INDEX treasury_rubrics_plan_idx ON public.treasury_rubrics (plan_id, section, display_order);

-- ---------------------------------------------------------------------
-- 3. Montants mensuels : prévision initiale (figée à l'approbation) et prévision actualisée
-- ---------------------------------------------------------------------
CREATE TABLE public.treasury_amounts (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  company_id      uuid NOT NULL,
  plan_id         uuid NOT NULL,
  rubric_id       uuid NOT NULL,
  scenario        text NOT NULL CHECK (scenario IN ('initial','updated')),
  period          smallint NOT NULL CHECK (period BETWEEN 1 AND 12),      -- mois de l'exercice
  amount          numeric(20,2) NOT NULL CHECK (amount >= 0),             -- le sens vient de la section
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (rubric_id, scenario, period),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (plan_id, company_id) REFERENCES public.treasury_plans(id, company_id) ON DELETE CASCADE,
  FOREIGN KEY (rubric_id, company_id) REFERENCES public.treasury_rubrics(id, company_id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------------
-- 4. Gardes
-- ---------------------------------------------------------------------
-- Circuit : brouillon → approuvé → archivé (ou brouillon → archivé). À l'approbation, la prévision initiale est figée
-- et recopiée en prévision actualisée ; seule cette dernière reste modifiable. Un plan archivé est figé.
CREATE OR REPLACE FUNCTION public.guard_treasury_plan() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status <> 'draft' THEN
      RAISE EXCEPTION 'Plan de trésorerie approuvé ou archivé : suppression impossible' USING ERRCODE = 'check_violation';
    END IF;
    RETURN OLD;
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.status <> 'draft' THEN
      RAISE EXCEPTION 'Un plan de trésorerie se crée en brouillon' USING ERRCODE = 'check_violation';
    END IF;
    NEW.created_by := coalesce(auth.uid(), NEW.created_by);
    RETURN NEW;
  END IF;
  IF NEW.company_id <> OLD.company_id OR NEW.fiscal_year_id <> OLD.fiscal_year_id THEN
    RAISE EXCEPTION 'Plan de trésorerie : entreprise et exercice non modifiables' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status THEN
    IF NOT ((OLD.status = 'draft' AND NEW.status IN ('approved','archived')) OR (OLD.status = 'approved' AND NEW.status = 'archived')) THEN
      RAISE EXCEPTION 'Transition interdite : % → %', OLD.status, NEW.status USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.status = 'approved' THEN
      NEW.approved_at := now();
      NEW.approved_by := coalesce(auth.uid(), NEW.approved_by);
    END IF;
  ELSIF OLD.status = 'archived'
     OR (OLD.status = 'approved' AND (NEW.opening_balance, NEW.opening_source, NEW.currency, NEW.name)
                                      IS DISTINCT FROM (OLD.opening_balance, OLD.opening_source, OLD.currency, OLD.name)) THEN
    RAISE EXCEPTION 'Plan de trésorerie % : figé (seules les notes d''un plan approuvé changent)', OLD.status
      USING ERRCODE = 'check_violation';
  END IF;
  NEW.updated_at := now();
  RETURN NEW;
END $$;
CREATE TRIGGER treasury_plans_guard BEFORE INSERT OR UPDATE OR DELETE ON public.treasury_plans
  FOR EACH ROW EXECUTE FUNCTION public.guard_treasury_plan();

CREATE OR REPLACE FUNCTION public.after_treasury_plan_approved() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status = 'approved' AND OLD.status = 'draft' THEN
    DELETE FROM public.treasury_amounts WHERE plan_id = NEW.id AND scenario = 'updated';
    INSERT INTO public.treasury_amounts (organization_id, company_id, plan_id, rubric_id, scenario, period, amount)
    SELECT organization_id, company_id, plan_id, rubric_id, 'updated', period, amount
      FROM public.treasury_amounts WHERE plan_id = NEW.id AND scenario = 'initial';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER treasury_plans_after_approval AFTER UPDATE ON public.treasury_plans
  FOR EACH ROW EXECUTE FUNCTION public.after_treasury_plan_approved();

-- Structure (rubriques) : modifiable en brouillon seulement ; parent et rubrique de base dans le même plan et la même
-- section ; un seul niveau de sous-rubriques (rubrique → sous-rubriques), comme le modèle.
CREATE OR REPLACE FUNCTION public.guard_treasury_rubric() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE v_status text; v_parent public.treasury_rubrics; v_base public.treasury_rubrics;
BEGIN
  SELECT status INTO v_status FROM public.treasury_plans WHERE id = coalesce(NEW.plan_id, OLD.plan_id);
  IF v_status IS NOT NULL AND v_status <> 'draft' THEN
    RAISE EXCEPTION 'Plan de trésorerie % : rubriques figées', v_status USING ERRCODE = 'check_violation';
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  IF EXISTS (SELECT 1 FROM unnest(NEW.account_prefixes) p WHERE p !~ '^[1-9][0-9]{0,19}$') THEN
    RAISE EXCEPTION 'Rubrique « % » : comptes associés numériques attendus', NEW.label USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.parent_id IS NOT NULL THEN
    SELECT * INTO v_parent FROM public.treasury_rubrics WHERE id = NEW.parent_id;
    IF v_parent.plan_id <> NEW.plan_id OR v_parent.section <> NEW.section OR v_parent.parent_id IS NOT NULL THEN
      RAISE EXCEPTION 'Sous-rubrique « % » : rubrique parente du même plan, de la même section et de premier niveau', NEW.label
        USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  IF NEW.base_rubric_id IS NOT NULL THEN
    SELECT * INTO v_base FROM public.treasury_rubrics WHERE id = NEW.base_rubric_id;
    IF v_base.plan_id <> NEW.plan_id THEN
      RAISE EXCEPTION 'Rubrique « % » : rubrique de base d''un autre plan', NEW.label USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  IF NEW.budget_id IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM public.budgets b JOIN public.treasury_plans t ON t.id = NEW.plan_id
        WHERE b.id = NEW.budget_id AND b.fiscal_year_id = t.fiscal_year_id) THEN
    RAISE EXCEPTION 'Rubrique « % » : budget d''un autre exercice', NEW.label USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER treasury_rubrics_guard BEFORE INSERT OR UPDATE OR DELETE ON public.treasury_rubrics
  FOR EACH ROW EXECUTE FUNCTION public.guard_treasury_rubric();

-- Montants : sur une rubrique sans sous-rubrique (la rubrique parente est leur somme) ; prévision initiale modifiable
-- en brouillon ; prévision actualisée modifiable une fois le plan approuvé (et pas archivé).
CREATE OR REPLACE FUNCTION public.guard_treasury_amount() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE v_status text; v_scenario text; v_rubric uuid;
BEGIN
  v_scenario := coalesce(NEW.scenario, OLD.scenario);
  v_rubric := coalesce(NEW.rubric_id, OLD.rubric_id);
  SELECT status INTO v_status FROM public.treasury_plans WHERE id = coalesce(NEW.plan_id, OLD.plan_id);
  IF v_status IS NULL THEN RETURN coalesce(NEW, OLD); END IF;     -- suppression en cascade d'un brouillon
  -- recopie de la prévision initiale à l'approbation (déclencheur after_treasury_plan_approved)
  IF pg_trigger_depth() > 1 AND v_scenario = 'updated' THEN RETURN coalesce(NEW, OLD); END IF;
  IF v_status = 'archived'
     OR (v_scenario = 'initial' AND v_status <> 'draft')
     OR (v_scenario = 'updated' AND v_status <> 'approved') THEN
    RAISE EXCEPTION 'Plan de trésorerie % : prévision % non modifiable', v_status,
      CASE v_scenario WHEN 'initial' THEN 'initiale' ELSE 'actualisée' END USING ERRCODE = 'check_violation';
  END IF;
  IF TG_OP <> 'DELETE' THEN
    IF EXISTS (SELECT 1 FROM public.treasury_rubrics WHERE parent_id = v_rubric) THEN
      RAISE EXCEPTION 'Montant sur une rubrique qui a des sous-rubriques : saisir les sous-rubriques' USING ERRCODE = 'check_violation';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.treasury_rubrics WHERE id = v_rubric AND plan_id = NEW.plan_id) THEN
      RAISE EXCEPTION 'Rubrique d''un autre plan' USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  RETURN coalesce(NEW, OLD);
END $$;
CREATE TRIGGER treasury_amounts_guard BEFORE INSERT OR UPDATE OR DELETE ON public.treasury_amounts
  FOR EACH ROW EXECUTE FUNCTION public.guard_treasury_amount();

-- ---------------------------------------------------------------------
-- 5. Journal, acteur IA, RLS (mêmes droits que les budgets : lecture des membres, écriture comptables et contrôleurs)
-- ---------------------------------------------------------------------
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['treasury_plans','treasury_rubrics','treasury_amounts'] LOOP
    EXECUTE format('CREATE TRIGGER %I AFTER INSERT OR UPDATE OR DELETE ON public.%I
                      FOR EACH ROW EXECUTE FUNCTION public.audit_row_change()', t || '_audit', t);
    EXECUTE format('CREATE TRIGGER %I BEFORE INSERT OR UPDATE OR DELETE ON public.%I
                      FOR EACH ROW EXECUTE FUNCTION public.guard_not_ai()', '0_not_ai', t);
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY %I ON public.%I FOR SELECT TO authenticated USING (authz.can_access_company(company_id))',
                   t || '_select', t);
    EXECUTE format('CREATE POLICY %I ON public.%I FOR ALL TO authenticated
                      USING (authz.has_company_role(company_id, ARRAY[''accountant'',''controller'']))
                      WITH CHECK (authz.has_company_role(company_id, ARRAY[''accountant'',''controller'']))', t || '_write', t);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON public.%I TO authenticated', t);
    EXECUTE format('GRANT ALL ON public.%I TO service_role', t);
  END LOOP;
END $$;
