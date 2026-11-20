-- =====================================================================
-- KOFINEX — Migration 0020 : budget relié au plan comptable (correctif du contrôle de gestion, phase 3)
-- Décisions du 20 novembre 2026 (docs/CONTROLE_GESTION.md § 12.1) :
--   2. comptes d'un budget : plan comptable de l'entreprise s'il est ouvert, sinon référentiel publié de l'exercice ;
--   3. comptes de bilan autorisés uniquement pour un budget d'investissement (classe 2 et comptes 16) ; les racines
--      autorisées par type de budget sont des DONNÉES (`budget_kinds`), marquées « à valider ».
-- Aucune donnée existante n'est modifiée : les budgets existants deviennent des budgets « de résultat » (comportement
-- du lot 5 inchangé) ; le contrôle des comptes s'applique aux lignes créées ou modifiées. 0001 et 0006 non réécrites.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. Types de budget et racines de comptes autorisées (données de plateforme)
-- ---------------------------------------------------------------------
CREATE TABLE public.budget_kinds (
  key             text PRIMARY KEY CHECK (key ~ '^[a-z_]{2,30}$'),
  label           text NOT NULL,
  allowed_prefixes text[] NOT NULL CHECK (cardinality(allowed_prefixes) > 0),
  -- natures des comptes du référentiel admises : charges / produits (budget de résultat) ou bilan (investissement)
  allowed_natures text[] NOT NULL CHECK (allowed_natures <@ ARRAY['expense','income','asset','liability','equity']::text[]),
  -- réalisé : soldes de l'exercice (comptes de gestion) ou mouvements de l'exercice (comptes de bilan, hors à-nouveaux)
  actual_basis    text NOT NULL CHECK (actual_basis IN ('balance','movements')),
  status          text NOT NULL DEFAULT 'to_validate' CHECK (status IN ('to_validate','validated')),
  source          text NOT NULL,
  display_order   int NOT NULL DEFAULT 0,
  updated_by      uuid REFERENCES public.profiles(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);
-- [À VALIDER] Répartition proposée ; seule la règle « investissement : classe 2 et comptes 16 » est une décision
-- (n° 3 du 20 novembre 2026). Les racines sont celles des plans SYSCOHADA révisé et SYSCEBNL (classes 6, 7, 8 :
-- charges et produits ; 60 : achats ; 70 : ventes).
INSERT INTO public.budget_kinds (key, label, allowed_prefixes, allowed_natures, actual_basis, source, display_order) VALUES
  ('general',     'Budget de résultat (charges et produits)', '{6,7,8}', '{expense,income}', 'balance',
   'Comportement du lot 5 (charges et produits) — [À VALIDER] racines 6, 7, 8', 10),
  ('sales',       'Budget des ventes',      '{70}', '{income}',  'balance', '[À VALIDER] racine 70 (ventes)', 20),
  ('purchases',   'Budget des achats',      '{60}', '{expense}', 'balance', '[À VALIDER] racine 60 (achats)', 30),
  ('expenses',    'Budget des charges',     '{6}',  '{expense}', 'balance', '[À VALIDER] classe 6 (charges)', 40),
  ('investments', 'Budget des investissements', '{2,16}', '{asset,liability}', 'movements',
   'Décision n° 3 du 20 novembre 2026 : classe 2 et comptes 16 — [À VALIDER] réalisé = mouvements de l''exercice', 50);

CREATE OR REPLACE FUNCTION public.guard_budget_kind() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Type de budget : suppression impossible' USING ERRCODE = 'check_violation';
  END IF;
  IF EXISTS (SELECT 1 FROM unnest(NEW.allowed_prefixes) p WHERE p !~ '^[1-9][0-9]{0,9}$') THEN
    RAISE EXCEPTION 'Type de budget % : racines de comptes numériques attendues', NEW.key USING ERRCODE = 'check_violation';
  END IF;
  IF TG_OP = 'UPDATE' AND NEW.key <> OLD.key THEN
    RAISE EXCEPTION 'Type de budget : clé non modifiable' USING ERRCODE = 'check_violation';
  END IF;
  NEW.updated_by := coalesce(auth.uid(), NEW.updated_by);
  RETURN NEW;
END $$;
CREATE TRIGGER budget_kinds_guard BEFORE INSERT OR UPDATE OR DELETE ON public.budget_kinds
  FOR EACH ROW EXECUTE FUNCTION public.guard_budget_kind();

-- ---------------------------------------------------------------------
-- 2. Type d'un budget (les budgets existants : budget de résultat)
-- ---------------------------------------------------------------------
ALTER TABLE public.budgets
  ADD COLUMN budget_kind text NOT NULL DEFAULT 'general' REFERENCES public.budget_kinds(key);

-- le type est figé hors brouillon et dès qu'une ligne existe (les lignes ont été contrôlées pour ce type)
CREATE OR REPLACE FUNCTION public.guard_budget_kind_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.budget_kind IS DISTINCT FROM OLD.budget_kind
     AND (OLD.status <> 'draft' OR EXISTS (SELECT 1 FROM public.budget_lines WHERE budget_id = OLD.id)) THEN
    RAISE EXCEPTION 'Type de budget non modifiable : budget hors brouillon ou déjà garni de lignes' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER budgets_kind_guard BEFORE UPDATE ON public.budgets
  FOR EACH ROW EXECUTE FUNCTION public.guard_budget_kind_change();

-- ---------------------------------------------------------------------
-- 3. Rubriques budgétaires (regroupement des lignes ; une rubrique peut couvrir plusieurs comptes ou aucun)
-- ---------------------------------------------------------------------
CREATE TABLE public.budget_rubrics (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  company_id      uuid NOT NULL,
  budget_id       uuid NOT NULL,
  label           text NOT NULL CHECK (length(btrim(label)) > 0),
  display_order   int NOT NULL DEFAULT 0,
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (budget_id, label),
  UNIQUE (id, company_id),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (budget_id, company_id) REFERENCES public.budgets(id, company_id) ON DELETE CASCADE
);
-- même règle que les lignes : un budget hors brouillon est figé (fonction de la migration 0006, réutilisée)
CREATE TRIGGER budget_rubrics_guard BEFORE INSERT OR UPDATE OR DELETE ON public.budget_rubrics
  FOR EACH ROW EXECUTE FUNCTION public.guard_budget_lines();

ALTER TABLE public.budget_lines
  ADD COLUMN rubric_id     uuid,
  ADD COLUMN forecast_mode text NOT NULL DEFAULT 'manual' CHECK (forecast_mode IN ('manual','calculated','imported')),
  ADD FOREIGN KEY (rubric_id, company_id) REFERENCES public.budget_rubrics(id, company_id) ON DELETE CASCADE;
-- une ligne de rubrique peut n'avoir ni compte ni centre (rubrique de gestion sans compte associé)
ALTER TABLE public.budget_lines DROP CONSTRAINT budget_lines_check;
ALTER TABLE public.budget_lines ADD CONSTRAINT budget_lines_check
  CHECK (account_number IS NOT NULL OR cost_center_id IS NOT NULL OR rubric_id IS NOT NULL);
CREATE INDEX budget_lines_rubric_idx ON public.budget_lines (rubric_id) WHERE rubric_id IS NOT NULL;

-- ---------------------------------------------------------------------
-- 4. Plan comptable de référence d'un budget
-- ---------------------------------------------------------------------
-- Comptes sélectionnables pour un exercice : si l'entreprise a ouvert son plan comptable, ses comptes actifs et les
-- comptes du référentiel qui les regroupent (racines, ex. 60, 601) ; sinon, le référentiel publié de l'exercice.
-- Lecture contrôlée par l'accès à l'entreprise ; le plan comptable n'est jamais modifié ici.
CREATE OR REPLACE FUNCTION public.budget_reference_accounts(p_company uuid, p_fiscal_year uuid)
RETURNS TABLE (account_number text, label text, nature text, account_class int, source text, is_active boolean)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public AS $$
DECLARE v_version uuid; v_end date;
BEGIN
  IF NOT authz.can_access_company(p_company) THEN
    RAISE EXCEPTION 'Entreprise inaccessible' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF EXISTS (SELECT 1 FROM public.company_accounts WHERE company_id = p_company) THEN
    RETURN QUERY
      SELECT a.account_number::text, a.label, a.nature, substr(a.account_number, 1, 1)::int, 'company'::text, a.is_active
        FROM public.company_accounts a WHERE a.company_id = p_company
      UNION ALL
      SELECT c.account_number::text, c.label, c.nature, c.account_class::int, 'framework_parent'::text, true
        FROM public.chart_of_accounts c
       WHERE c.framework_version_id IN (SELECT DISTINCT framework_version_id FROM public.company_accounts WHERE company_id = p_company)
         AND NOT EXISTS (SELECT 1 FROM public.company_accounts a2 WHERE a2.company_id = p_company AND a2.account_number = c.account_number)
         AND EXISTS (SELECT 1 FROM public.company_accounts a3 WHERE a3.company_id = p_company AND a3.is_active
                        AND a3.account_number LIKE c.account_number || '%');
    RETURN;
  END IF;
  SELECT coalesce(fy.framework_version_id, j.framework_version_id), fy.end_date INTO v_version, v_end
    FROM public.fiscal_years fy LEFT JOIN public.import_jobs j ON j.id = fy.active_import_job_id
   WHERE fy.id = p_fiscal_year AND fy.company_id = p_company;
  v_version := coalesce(v_version, public.applicable_framework_version(p_company, v_end));
  RETURN QUERY
    SELECT c.account_number::text, c.label, c.nature, c.account_class::int, 'framework'::text, true
      FROM public.chart_of_accounts c WHERE c.framework_version_id = v_version;
END $$;
REVOKE ALL ON FUNCTION public.budget_reference_accounts(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.budget_reference_accounts(uuid, uuid) TO authenticated, service_role;

-- Contrôle d'une ligne créée ou modifiée : compte du plan de référence, actif, dans les racines et natures du type
CREATE OR REPLACE FUNCTION public.guard_budget_line_account() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_kind public.budget_kinds; v_fy uuid; v_acc record;
BEGIN
  IF NEW.account_number IS NULL THEN RETURN NEW; END IF;
  IF TG_OP = 'UPDATE' AND NEW.account_number IS NOT DISTINCT FROM OLD.account_number THEN RETURN NEW; END IF;
  SELECT k.* INTO v_kind FROM public.budgets b JOIN public.budget_kinds k ON k.key = b.budget_kind WHERE b.id = NEW.budget_id;
  SELECT fiscal_year_id INTO v_fy FROM public.budgets WHERE id = NEW.budget_id;
  SELECT * INTO v_acc FROM public.budget_reference_accounts(NEW.company_id, v_fy) r WHERE r.account_number = NEW.account_number
   LIMIT 1;
  IF v_acc.account_number IS NULL THEN
    RAISE EXCEPTION 'Compte % absent du plan comptable de référence du budget (plan de l''entreprise, sinon référentiel publié)',
      NEW.account_number USING ERRCODE = 'check_violation';
  END IF;
  IF NOT v_acc.is_active THEN
    RAISE EXCEPTION 'Compte % en sommeil : non budgétable', NEW.account_number USING ERRCODE = 'check_violation';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM unnest(v_kind.allowed_prefixes) p WHERE NEW.account_number LIKE p || '%') THEN
    RAISE EXCEPTION 'Compte % hors des racines autorisées pour « % » (%)', NEW.account_number, v_kind.label,
      array_to_string(v_kind.allowed_prefixes, ', ') USING ERRCODE = 'check_violation';
  END IF;
  IF v_acc.nature IS NULL OR NOT (v_acc.nature = ANY (v_kind.allowed_natures)) THEN
    RAISE EXCEPTION 'Compte % de nature « % » : non admis dans « % »', NEW.account_number, coalesce(v_acc.nature, 'inconnue'),
      v_kind.label USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER budget_lines_account_guard BEFORE INSERT OR UPDATE ON public.budget_lines
  FOR EACH ROW EXECUTE FUNCTION public.guard_budget_line_account();

-- ---------------------------------------------------------------------
-- 5. Journal, acteur IA, RLS
-- ---------------------------------------------------------------------
CREATE TRIGGER budget_kinds_audit AFTER INSERT OR UPDATE OR DELETE ON public.budget_kinds
  FOR EACH ROW EXECUTE FUNCTION public.audit_row_change();
CREATE TRIGGER budget_rubrics_audit AFTER INSERT OR UPDATE OR DELETE ON public.budget_rubrics
  FOR EACH ROW EXECUTE FUNCTION public.audit_row_change();
CREATE TRIGGER "0_not_ai" BEFORE INSERT OR UPDATE OR DELETE ON public.budget_kinds
  FOR EACH ROW EXECUTE FUNCTION public.guard_not_ai();
CREATE TRIGGER "0_not_ai" BEFORE INSERT OR UPDATE OR DELETE ON public.budget_rubrics
  FOR EACH ROW EXECUTE FUNCTION public.guard_not_ai();
CREATE TRIGGER budget_kinds_updated_at BEFORE UPDATE ON public.budget_kinds
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.budget_kinds ENABLE ROW LEVEL SECURITY;
CREATE POLICY budget_kinds_select ON public.budget_kinds FOR SELECT TO authenticated USING (true);
CREATE POLICY budget_kinds_admin ON public.budget_kinds FOR UPDATE TO authenticated
  USING (authz.is_platform_admin()) WITH CHECK (authz.is_platform_admin());
GRANT SELECT, UPDATE (label, allowed_prefixes, allowed_natures, status, source, display_order) ON public.budget_kinds TO authenticated;
GRANT ALL ON public.budget_kinds TO service_role;

-- rubriques : mêmes droits que les lignes de budget (lecture : accès à l'entreprise ; écriture : budget.write)
ALTER TABLE public.budget_rubrics ENABLE ROW LEVEL SECURITY;
CREATE POLICY budget_rubrics_select ON public.budget_rubrics FOR SELECT TO authenticated
  USING (authz.can_access_company(company_id));
CREATE POLICY budget_rubrics_write ON public.budget_rubrics FOR ALL TO authenticated
  USING (authz.has_company_role(company_id, ARRAY['accountant','controller']))
  WITH CHECK (authz.has_company_role(company_id, ARRAY['accountant','controller']));
GRANT SELECT, INSERT, UPDATE, DELETE ON public.budget_rubrics TO authenticated;
GRANT ALL ON public.budget_rubrics TO service_role;
