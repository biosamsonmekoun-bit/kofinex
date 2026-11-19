-- =====================================================================
-- KOFINEX — Migration 0008 : audit financier et comptable (lot 7)
-- Seuils, revue des comptes par cycle, populations et échantillons, tests, circularisations,
-- anomalies et ajustements, synthèse des anomalies non corrigées.
-- Aucun pourcentage, taille d'échantillon ou facteur n'est fixé ici : ce sont des saisies justifiées.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 0. Réservé aux missions d'audit financier
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.guard_fa_engagement() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_type text;
BEGIN
  SELECT engagement_type INTO v_type FROM public.engagements WHERE id = NEW.engagement_id;
  IF v_type NOT IN ('statutory_audit','contractual_audit') THEN
    RAISE EXCEPTION 'Fonction réservée aux missions d''audit légal ou contractuel' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION authz.fa_role(p_engagement uuid) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT role FROM public.engagement_members
   WHERE engagement_id = p_engagement AND user_id = auth.uid() AND independence_confirmed_at IS NOT NULL
$$;
REVOKE ALL ON FUNCTION authz.fa_role(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION authz.fa_role(uuid) TO authenticated, service_role;

-- ---------------------------------------------------------------------
-- 1. Seuils (versions ; une seule approuvée à la fois)
-- ---------------------------------------------------------------------
CREATE TABLE public.fa_materiality (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id      uuid NOT NULL,
  engagement_id        uuid NOT NULL,
  version              int  NOT NULL CHECK (version > 0),
  benchmark_label      text NOT NULL CHECK (length(trim(benchmark_label)) > 0),
  benchmark_source     text NOT NULL CHECK (benchmark_source IN ('statement_line','manual')),
  benchmark_line_code  text,
  source_import_job_id uuid,
  benchmark_amount     numeric(20,2) NOT NULL CHECK (benchmark_amount > 0),
  overall_pct          numeric(7,4) NOT NULL CHECK (overall_pct > 0 AND overall_pct <= 100),
  overall_amount       numeric(20,2) NOT NULL,
  performance_pct      numeric(7,4) NOT NULL CHECK (performance_pct > 0 AND performance_pct <= 100),
  performance_amount   numeric(20,2) NOT NULL,
  trivial_pct          numeric(7,4) NOT NULL CHECK (trivial_pct > 0 AND trivial_pct <= 100),
  trivial_amount       numeric(20,2) NOT NULL,
  basis                text NOT NULL CHECK (length(trim(basis)) >= 10),   -- justification et source des pourcentages
  status               text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','superseded')),
  created_by           uuid NOT NULL REFERENCES public.profiles(id),
  approved_by          uuid REFERENCES public.profiles(id),
  approved_at          timestamptz,
  created_at           timestamptz NOT NULL DEFAULT now(),
  UNIQUE (engagement_id, version),
  FOREIGN KEY (engagement_id, organization_id) REFERENCES public.engagements(id, organization_id) ON DELETE CASCADE,
  -- les montants sont toujours le produit exact des pourcentages (arrondi au centime)
  CHECK (overall_amount = round(benchmark_amount * overall_pct / 100, 2)),
  CHECK (performance_amount = round(overall_amount * performance_pct / 100, 2)),
  CHECK (trivial_amount = round(overall_amount * trivial_pct / 100, 2)),
  CHECK ((benchmark_source = 'statement_line') = (benchmark_line_code IS NOT NULL AND source_import_job_id IS NOT NULL)),
  CHECK ((status = 'draft') = (approved_by IS NULL))
);
CREATE UNIQUE INDEX fa_materiality_one_approved ON public.fa_materiality (engagement_id) WHERE status = 'approved';

CREATE OR REPLACE FUNCTION public.guard_fa_materiality() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_role text;
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF NEW.created_by IS DISTINCT FROM auth.uid() THEN
      RAISE EXCEPTION 'Seuils : saisis au nom de l''utilisateur authentifié' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.status <> 'draft' THEN
      RAISE EXCEPTION 'Seuils : une nouvelle version commence en brouillon' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
  END IF;
  IF TG_OP = 'DELETE' THEN
    IF OLD.status <> 'draft' THEN
      RAISE EXCEPTION 'Seuils approuvés : conservés (créez une nouvelle version)' USING ERRCODE = 'check_violation';
    END IF;
    RETURN OLD;
  END IF;
  IF OLD.status = 'superseded' OR (OLD.status = 'approved' AND NEW.status <> 'superseded') THEN
    RAISE EXCEPTION 'Seuils approuvés : non modifiables (créez une nouvelle version)' USING ERRCODE = 'check_violation';
  END IF;
  IF OLD.status = 'approved' THEN        -- remplacement par une nouvelle version : seul le statut change
    IF (to_jsonb(NEW) - 'status') IS DISTINCT FROM (to_jsonb(OLD) - 'status') THEN
      RAISE EXCEPTION 'Seuils approuvés : non modifiables' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
  END IF;
  IF NEW.status = 'approved' THEN
    v_role := authz.fa_role(NEW.engagement_id);
    IF coalesce(v_role, '') NOT IN ('partner','manager') OR NEW.approved_by IS DISTINCT FROM auth.uid() THEN
      RAISE EXCEPTION 'Approbation des seuils : manager ou associé, en son nom' USING ERRCODE = 'insufficient_privilege';
    END IF;
    NEW.approved_at := now();
    UPDATE public.fa_materiality SET status = 'superseded'
     WHERE engagement_id = NEW.engagement_id AND status = 'approved' AND id <> NEW.id;
  ELSIF NEW.status = 'superseded' THEN
    RAISE EXCEPTION 'Seul un seuil approuvé peut être remplacé' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.created_by IS DISTINCT FROM OLD.created_by OR NEW.version IS DISTINCT FROM OLD.version THEN
    RAISE EXCEPTION 'Seuils : auteur et version immuables' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER fa_materiality_guard BEFORE INSERT OR UPDATE OR DELETE ON public.fa_materiality
  FOR EACH ROW EXECUTE FUNCTION public.guard_fa_materiality();

-- ---------------------------------------------------------------------
-- 2. Cycles et revue des comptes (balance N / N-1 vérifiée en base)
-- ---------------------------------------------------------------------
CREATE TABLE public.fa_cycle_mappings (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  engagement_id   uuid NOT NULL,
  account_prefix  varchar(20) NOT NULL CHECK (account_prefix ~ '^[0-9]+$'),
  cycle_code      text NOT NULL CHECK (length(trim(cycle_code)) > 0),
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (engagement_id, account_prefix),
  FOREIGN KEY (engagement_id, organization_id) REFERENCES public.engagements(id, organization_id) ON DELETE CASCADE
);

CREATE TABLE public.fa_account_reviews (
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id        uuid NOT NULL,
  engagement_id          uuid NOT NULL,
  account_number         varchar(20) NOT NULL CHECK (account_number ~ '^[0-9]+$'),
  account_label          text,
  cycle_code             text,
  source_import_job_id   uuid NOT NULL,
  previous_import_job_id uuid,
  balance_n              numeric(20,2) NOT NULL,
  balance_n1             numeric(20,2),
  variation              numeric(20,2) GENERATED ALWAYS AS (balance_n - balance_n1) STORED,
  threshold_used         numeric(20,2),
  requires_explanation   boolean NOT NULL DEFAULT false,
  explanation            text,
  conclusion             text,
  status                 text NOT NULL DEFAULT 'to_review' CHECK (status IN ('to_review','reviewed')),
  workpaper_id           uuid,
  reviewed_by            uuid REFERENCES public.profiles(id),
  reviewed_at            timestamptz,
  created_at             timestamptz NOT NULL DEFAULT now(),
  updated_at             timestamptz NOT NULL DEFAULT now(),
  UNIQUE (engagement_id, account_number),
  UNIQUE (id, engagement_id),
  FOREIGN KEY (engagement_id, organization_id) REFERENCES public.engagements(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (workpaper_id, engagement_id) REFERENCES public.workpapers(id, engagement_id) ON DELETE SET NULL (workpaper_id),
  CHECK (status = 'to_review' OR (conclusion IS NOT NULL AND length(trim(conclusion)) > 0 AND reviewed_by IS NOT NULL
                                  AND (NOT requires_explanation OR length(trim(coalesce(explanation, ''))) > 0)))
);

-- Les soldes doivent être ceux des balances validées ; le dépassement est recalculé à partir du seuil approuvé
CREATE OR REPLACE FUNCTION public.guard_fa_account_review() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_fy uuid; v_active uuid; v_n numeric; v_n1 numeric; v_thr numeric;
BEGIN
  IF TG_OP = 'INSERT' OR (NEW.balance_n, NEW.balance_n1, NEW.source_import_job_id, NEW.previous_import_job_id,
                          NEW.account_number, NEW.threshold_used)
       IS DISTINCT FROM (OLD.balance_n, OLD.balance_n1, OLD.source_import_job_id, OLD.previous_import_job_id,
                         OLD.account_number, OLD.threshold_used) THEN
    SELECT e.fiscal_year_id, f.active_import_job_id INTO v_fy, v_active
      FROM public.engagements e JOIN public.fiscal_years f ON f.id = e.fiscal_year_id WHERE e.id = NEW.engagement_id;
    IF v_active IS NULL OR NEW.source_import_job_id <> v_active THEN
      RAISE EXCEPTION 'Revue des comptes : la balance de référence est la balance validée de l''exercice de la mission'
        USING ERRCODE = 'check_violation';
    END IF;
    SELECT coalesce(sum(closing_debit - closing_credit), 0) INTO v_n FROM public.trial_balance_entries
     WHERE import_job_id = NEW.source_import_job_id AND account_number = NEW.account_number;
    IF NEW.balance_n <> v_n THEN
      RAISE EXCEPTION 'Compte % : solde N différent de la balance validée', NEW.account_number USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.previous_import_job_id IS NOT NULL THEN
      IF NOT EXISTS (SELECT 1 FROM public.fiscal_years p JOIN public.fiscal_years c ON c.id = v_fy
                      WHERE p.company_id = c.company_id AND p.end_date < c.start_date
                        AND p.active_import_job_id = NEW.previous_import_job_id) THEN
        RAISE EXCEPTION 'Balance N-1 : balance validée d''un exercice antérieur de la même entité requise'
          USING ERRCODE = 'check_violation';
      END IF;
      SELECT coalesce(sum(closing_debit - closing_credit), 0) INTO v_n1 FROM public.trial_balance_entries
       WHERE import_job_id = NEW.previous_import_job_id AND account_number = NEW.account_number;
      IF NEW.balance_n1 IS DISTINCT FROM v_n1 THEN
        RAISE EXCEPTION 'Compte % : solde N-1 différent de la balance validée', NEW.account_number
          USING ERRCODE = 'check_violation';
      END IF;
    ELSIF NEW.balance_n1 IS NOT NULL THEN
      RAISE EXCEPTION 'Solde N-1 sans balance N-1' USING ERRCODE = 'check_violation';
    END IF;
    SELECT performance_amount INTO v_thr FROM public.fa_materiality
     WHERE engagement_id = NEW.engagement_id AND status = 'approved';
    IF NEW.threshold_used IS DISTINCT FROM v_thr THEN
      RAISE EXCEPTION 'Revue des comptes : le seuil utilisé est le seuil de planification approuvé' USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  NEW.requires_explanation := NEW.threshold_used IS NOT NULL
    AND abs(coalesce(NEW.balance_n - NEW.balance_n1, NEW.balance_n)) >= NEW.threshold_used;
  IF NEW.status = 'reviewed' AND (TG_OP = 'INSERT' OR OLD.status <> 'reviewed') THEN
    IF coalesce(authz.fa_role(NEW.engagement_id), '') NOT IN ('partner','manager','in_charge','staff')
       OR NEW.reviewed_by IS DISTINCT FROM auth.uid() THEN
      RAISE EXCEPTION 'Revue du compte : par un membre de l''équipe, en son nom' USING ERRCODE = 'insufficient_privilege';
    END IF;
    NEW.reviewed_at := now();
  ELSIF NEW.status = 'to_review' THEN
    NEW.reviewed_by := NULL; NEW.reviewed_at := NULL;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER fa_account_reviews_guard BEFORE INSERT OR UPDATE ON public.fa_account_reviews
  FOR EACH ROW EXECUTE FUNCTION public.guard_fa_account_review();

-- ---------------------------------------------------------------------
-- 3. Populations, échantillons, tests
-- ---------------------------------------------------------------------
CREATE TABLE public.fa_populations (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id      uuid NOT NULL,
  engagement_id        uuid NOT NULL,
  name                 text NOT NULL CHECK (length(trim(name)) > 0),
  description          text,
  source               text NOT NULL CHECK (source IN ('balance','file')),
  account_prefixes     text[] NOT NULL DEFAULT '{}',
  source_import_job_id uuid,
  source_evidence_id   uuid,
  item_count           int NOT NULL CHECK (item_count >= 0),
  total_amount         numeric(20,2) NOT NULL,
  absolute_total       numeric(20,2) NOT NULL CHECK (absolute_total >= 0),
  sha256               text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  created_by           uuid NOT NULL REFERENCES public.profiles(id),
  created_at           timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id, engagement_id),
  FOREIGN KEY (engagement_id, organization_id) REFERENCES public.engagements(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (source_evidence_id, engagement_id) REFERENCES public.evidence_items(id, engagement_id),
  CHECK ((source = 'balance' AND source_import_job_id IS NOT NULL) OR (source = 'file' AND source_evidence_id IS NOT NULL))
);

CREATE TABLE public.fa_population_items (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  engagement_id   uuid NOT NULL,
  population_id   uuid NOT NULL,
  line_no         int  NOT NULL CHECK (line_no > 0),
  reference       text NOT NULL,
  item_date       date,
  label           text,
  account_number  varchar(20),
  amount          numeric(20,2) NOT NULL,
  UNIQUE (population_id, line_no),
  UNIQUE (id, engagement_id),
  FOREIGN KEY (population_id, engagement_id) REFERENCES public.fa_populations(id, engagement_id) ON DELETE CASCADE
);

CREATE TABLE public.fa_samples (
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id        uuid NOT NULL,
  engagement_id          uuid NOT NULL,
  population_id          uuid NOT NULL,
  reference              text NOT NULL CHECK (length(trim(reference)) > 0),
  objective              text NOT NULL CHECK (length(trim(objective)) > 0),
  method                 text NOT NULL CHECK (method IN ('random','systematic','mus','key_items','judgmental')),
  requested_size         int CHECK (requested_size > 0),
  size_basis             text NOT NULL CHECK (length(trim(size_basis)) >= 10),   -- justification / paramètre de la méthodologie
  seed                   bigint,
  parameters             jsonb NOT NULL DEFAULT '{}',
  selected_count         int NOT NULL CHECK (selected_count > 0),
  procedure_id           uuid,
  workpaper_id           uuid,
  status                 text NOT NULL DEFAULT 'testing' CHECK (status IN ('testing','concluded')),
  actual_misstatement    numeric(20,2),
  projected_misstatement numeric(20,2),
  projection             jsonb,
  conclusion             text,
  concluded_by           uuid REFERENCES public.profiles(id),
  concluded_at           timestamptz,
  created_by             uuid NOT NULL REFERENCES public.profiles(id),
  created_at             timestamptz NOT NULL DEFAULT now(),
  updated_at             timestamptz NOT NULL DEFAULT now(),
  UNIQUE (engagement_id, reference),
  UNIQUE (id, engagement_id),
  FOREIGN KEY (engagement_id, organization_id) REFERENCES public.engagements(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (population_id, engagement_id) REFERENCES public.fa_populations(id, engagement_id),
  FOREIGN KEY (procedure_id, engagement_id) REFERENCES public.procedures(id, engagement_id) ON DELETE SET NULL (procedure_id),
  FOREIGN KEY (workpaper_id, engagement_id) REFERENCES public.workpapers(id, engagement_id) ON DELETE SET NULL (workpaper_id),
  CHECK (method IN ('key_items','judgmental') OR (seed IS NOT NULL AND requested_size IS NOT NULL)),
  CHECK (status = 'testing' OR (conclusion IS NOT NULL AND length(trim(conclusion)) > 0 AND concluded_by IS NOT NULL
                                AND actual_misstatement IS NOT NULL))
);

CREATE TABLE public.fa_sample_items (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id    uuid NOT NULL,
  engagement_id      uuid NOT NULL,
  sample_id          uuid NOT NULL,
  population_item_id uuid NOT NULL,
  selection_reason   text NOT NULL CHECK (selection_reason IN ('random','interval','key_item','judgment')),
  book_amount        numeric(20,2) NOT NULL,
  audited_amount     numeric(20,2),
  misstatement       numeric(20,2) GENERATED ALWAYS AS (book_amount - audited_amount) STORED,
  result             text NOT NULL DEFAULT 'pending' CHECK (result IN ('pending','no_exception','exception')),
  comment            text,
  tested_by          uuid REFERENCES public.profiles(id),
  tested_at          timestamptz,
  UNIQUE (sample_id, population_item_id),
  UNIQUE (id, engagement_id),
  FOREIGN KEY (sample_id, engagement_id) REFERENCES public.fa_samples(id, engagement_id) ON DELETE CASCADE,
  FOREIGN KEY (population_item_id, engagement_id) REFERENCES public.fa_population_items(id, engagement_id),
  CHECK (result = 'pending' OR (audited_amount IS NOT NULL AND tested_by IS NOT NULL)),
  CHECK (result <> 'no_exception' OR audited_amount = book_amount),
  CHECK (result <> 'exception' OR length(trim(coalesce(comment, ''))) > 0)
);

-- Population : figée dès qu'un échantillon y est tiré ; totaux et empreinte recalculés à la création d'un échantillon
CREATE OR REPLACE FUNCTION public.guard_fa_population() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_pop uuid;
BEGIN
  v_pop := (to_jsonb(coalesce(NEW, OLD)) ->> CASE WHEN TG_TABLE_NAME = 'fa_populations' THEN 'id' ELSE 'population_id' END)::uuid;
  IF EXISTS (SELECT 1 FROM public.fa_samples WHERE population_id = v_pop) THEN
    RAISE EXCEPTION 'Population figée : un échantillon y a été tiré' USING ERRCODE = 'check_violation';
  END IF;
  IF TG_TABLE_NAME = 'fa_populations' AND TG_OP = 'INSERT' THEN
    IF (to_jsonb(NEW) ->> 'created_by')::uuid IS DISTINCT FROM auth.uid() THEN
      RAISE EXCEPTION 'Population : créée au nom de l''utilisateur authentifié' USING ERRCODE = 'insufficient_privilege';
    END IF;
  END IF;
  RETURN coalesce(NEW, OLD);
END $$;
CREATE TRIGGER fa_populations_guard BEFORE INSERT OR UPDATE OR DELETE ON public.fa_populations
  FOR EACH ROW EXECUTE FUNCTION public.guard_fa_population();
CREATE TRIGGER fa_population_items_guard BEFORE INSERT OR UPDATE OR DELETE ON public.fa_population_items
  FOR EACH ROW EXECUTE FUNCTION public.guard_fa_population();

CREATE OR REPLACE FUNCTION public.guard_fa_sample() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_count int; v_total numeric; v_abs numeric; p public.fa_populations; v_pending int; v_items int; v_role text;
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF NEW.created_by IS DISTINCT FROM auth.uid() THEN
      RAISE EXCEPTION 'Échantillon : créé au nom de l''utilisateur authentifié' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF coalesce(current_setting('kofinex.sampling', true), 'off') <> 'on' THEN
      RAISE EXCEPTION 'Échantillon : la sélection est faite par le moteur de KOFINEX' USING ERRCODE = 'insufficient_privilege';
    END IF;
    SELECT * INTO p FROM public.fa_populations WHERE id = NEW.population_id;
    SELECT count(*), coalesce(sum(amount), 0), coalesce(sum(abs(amount)), 0) INTO v_count, v_total, v_abs
      FROM public.fa_population_items WHERE population_id = NEW.population_id;
    IF (v_count, v_total, v_abs) IS DISTINCT FROM (p.item_count, p.total_amount, p.absolute_total) THEN
      RAISE EXCEPTION 'Population incohérente (nombre ou totaux) : tirage refusé' USING ERRCODE = 'check_violation';
    END IF;
    NEW.status := 'testing';
    RETURN NEW;
  END IF;
  IF TG_OP = 'DELETE' THEN
    IF OLD.status = 'concluded' OR EXISTS (SELECT 1 FROM public.fa_sample_items WHERE sample_id = OLD.id AND result <> 'pending') THEN
      RAISE EXCEPTION 'Échantillon testé : suppression impossible' USING ERRCODE = 'check_violation';
    END IF;
    RETURN OLD;
  END IF;
  IF (NEW.population_id, NEW.method, NEW.requested_size, NEW.seed, NEW.parameters, NEW.selected_count, NEW.created_by)
     IS DISTINCT FROM (OLD.population_id, OLD.method, OLD.requested_size, OLD.seed, OLD.parameters, OLD.selected_count,
                       OLD.created_by) THEN
    RAISE EXCEPTION 'Échantillon : paramètres de sélection immuables' USING ERRCODE = 'check_violation';
  END IF;
  IF OLD.status = 'concluded' AND NEW.status = 'concluded' THEN
    RAISE EXCEPTION 'Échantillon conclu : rouvrez-le pour le modifier' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.status = 'concluded' AND OLD.status = 'testing' THEN
    SELECT count(*) FILTER (WHERE result = 'pending'), count(*) INTO v_pending, v_items
      FROM public.fa_sample_items WHERE sample_id = NEW.id;
    IF v_pending > 0 OR v_items <> NEW.selected_count THEN
      RAISE EXCEPTION 'Échantillon : % élément(s) non testé(s)', v_pending USING ERRCODE = 'check_violation';
    END IF;
    IF coalesce(current_setting('kofinex.sampling', true), 'off') <> 'on' THEN
      RAISE EXCEPTION 'Conclusion : projection calculée par le moteur de KOFINEX' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.actual_misstatement IS DISTINCT FROM (SELECT coalesce(sum(misstatement), 0) FROM public.fa_sample_items
                                                  WHERE sample_id = NEW.id) THEN
      RAISE EXCEPTION 'Conclusion : anomalie constatée incohérente avec les tests' USING ERRCODE = 'check_violation';
    END IF;
    v_role := authz.fa_role(NEW.engagement_id);
    IF coalesce(v_role, '') NOT IN ('partner','manager','in_charge','staff') OR NEW.concluded_by IS DISTINCT FROM auth.uid() THEN
      RAISE EXCEPTION 'Conclusion : par un membre de l''équipe, en son nom' USING ERRCODE = 'insufficient_privilege';
    END IF;
    NEW.concluded_at := now();
  ELSIF NEW.status = 'testing' AND OLD.status = 'concluded' THEN
    IF coalesce(authz.fa_role(NEW.engagement_id), '') NOT IN ('partner','manager','in_charge') THEN
      RAISE EXCEPTION 'Réouverture d''un échantillon : encadrement de la mission' USING ERRCODE = 'insufficient_privilege';
    END IF;
    NEW.concluded_by := NULL; NEW.concluded_at := NULL; NEW.conclusion := NULL;
    NEW.actual_misstatement := NULL; NEW.projected_misstatement := NULL; NEW.projection := NULL;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER fa_samples_guard BEFORE INSERT OR UPDATE OR DELETE ON public.fa_samples
  FOR EACH ROW EXECUTE FUNCTION public.guard_fa_sample();

CREATE OR REPLACE FUNCTION public.guard_fa_sample_item() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_status text; v_amount numeric; v_pop uuid;
BEGIN
  SELECT status, population_id INTO v_status, v_pop FROM public.fa_samples WHERE id = coalesce(NEW.sample_id, OLD.sample_id);
  IF v_status = 'concluded' THEN
    RAISE EXCEPTION 'Échantillon conclu : tests figés' USING ERRCODE = 'check_violation';
  END IF;
  IF TG_OP IN ('INSERT','DELETE') THEN
    IF coalesce(current_setting('kofinex.sampling', true), 'off') <> 'on' THEN
      RAISE EXCEPTION 'Éléments de l''échantillon : fixés par la sélection' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  END IF;
  IF TG_OP = 'UPDATE' AND (NEW.sample_id, NEW.population_item_id, NEW.selection_reason, NEW.book_amount)
       IS DISTINCT FROM (OLD.sample_id, OLD.population_item_id, OLD.selection_reason, OLD.book_amount) THEN
    RAISE EXCEPTION 'Élément de l''échantillon : sélection immuable' USING ERRCODE = 'check_violation';
  END IF;
  SELECT amount INTO v_amount FROM public.fa_population_items WHERE id = NEW.population_item_id AND population_id = v_pop;
  IF v_amount IS NULL OR v_amount <> NEW.book_amount THEN
    RAISE EXCEPTION 'Élément hors population ou montant comptable différent' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.result <> 'pending' AND (TG_OP = 'INSERT' OR (NEW.result, NEW.audited_amount, NEW.comment)
                                   IS DISTINCT FROM (OLD.result, OLD.audited_amount, OLD.comment)) THEN
    IF NEW.tested_by IS DISTINCT FROM auth.uid() THEN
      RAISE EXCEPTION 'Test : enregistré au nom de l''utilisateur authentifié' USING ERRCODE = 'insufficient_privilege';
    END IF;
    NEW.tested_at := now();
  ELSIF NEW.result = 'pending' THEN
    NEW.audited_amount := NULL; NEW.tested_by := NULL; NEW.tested_at := NULL;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER fa_sample_items_guard BEFORE INSERT OR UPDATE OR DELETE ON public.fa_sample_items
  FOR EACH ROW EXECUTE FUNCTION public.guard_fa_sample_item();

-- ---------------------------------------------------------------------
-- 4. Circularisations (confirmations externes)
-- ---------------------------------------------------------------------
CREATE TABLE public.fa_confirmations (
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id        uuid NOT NULL,
  engagement_id          uuid NOT NULL,
  reference              text NOT NULL CHECK (length(trim(reference)) > 0),
  confirmation_type      text NOT NULL CHECK (confirmation_type IN ('receivable','payable','bank','legal','other')),
  third_party            text NOT NULL CHECK (length(trim(third_party)) > 0),
  contact                text,
  account_number         varchar(20),
  balance_date           date NOT NULL,
  book_balance           numeric(20,2),
  request_form           text NOT NULL CHECK (request_form IN ('positive','negative','blank')),
  status                 text NOT NULL DEFAULT 'prepared'
                           CHECK (status IN ('prepared','sent','received','no_response','closed')),
  sent_on                date,
  reminder_dates         date[] NOT NULL DEFAULT '{}',
  received_on            date,
  confirmed_amount       numeric(20,2),
  difference             numeric(20,2) GENERATED ALWAYS AS (book_balance - confirmed_amount) STORED,
  reconciliation         text,
  alternative_procedures text,
  conclusion             text,
  population_item_id     uuid,
  workpaper_id           uuid,
  created_by             uuid NOT NULL REFERENCES public.profiles(id),
  closed_by              uuid REFERENCES public.profiles(id),
  closed_at              timestamptz,
  created_at             timestamptz NOT NULL DEFAULT now(),
  updated_at             timestamptz NOT NULL DEFAULT now(),
  UNIQUE (engagement_id, reference),
  UNIQUE (id, engagement_id),
  FOREIGN KEY (engagement_id, organization_id) REFERENCES public.engagements(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (population_item_id, engagement_id) REFERENCES public.fa_population_items(id, engagement_id),
  FOREIGN KEY (workpaper_id, engagement_id) REFERENCES public.workpapers(id, engagement_id) ON DELETE SET NULL (workpaper_id),
  CHECK (book_balance IS NOT NULL OR confirmation_type IN ('legal','other')),
  CHECK (received_on IS NULL OR (sent_on IS NOT NULL AND received_on >= sent_on))
);

CREATE OR REPLACE FUNCTION public.guard_fa_confirmation() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status <> 'prepared' THEN
      RAISE EXCEPTION 'Demande envoyée : conservée au dossier' USING ERRCODE = 'check_violation';
    END IF;
    RETURN OLD;
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.created_by IS DISTINCT FROM auth.uid() THEN
      RAISE EXCEPTION 'Demande : créée au nom de l''utilisateur authentifié' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.status <> 'prepared' THEN
      RAISE EXCEPTION 'Demande : commence au statut « préparée »' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.status = 'closed' AND NEW.status = 'closed' THEN
    RAISE EXCEPTION 'Circularisation close : non modifiable' USING ERRCODE = 'check_violation';
  END IF;
  IF OLD.status <> 'prepared' AND (NEW.third_party, NEW.confirmation_type, NEW.book_balance, NEW.balance_date,
                                   NEW.request_form, NEW.account_number, NEW.sent_on)
       IS DISTINCT FROM (OLD.third_party, OLD.confirmation_type, OLD.book_balance, OLD.balance_date,
                         OLD.request_form, OLD.account_number, OLD.sent_on) THEN
    RAISE EXCEPTION 'Demande envoyée : son contenu ne change plus' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status THEN
    IF (OLD.status, NEW.status) = ('prepared','sent') THEN
      IF NEW.sent_on IS NULL THEN RAISE EXCEPTION 'Date d''envoi requise' USING ERRCODE = 'check_violation'; END IF;
    ELSIF (OLD.status, NEW.status) IN (('sent','received'), ('no_response','received')) THEN
      IF NEW.received_on IS NULL OR (NEW.confirmed_amount IS NULL AND NEW.book_balance IS NOT NULL) THEN
        RAISE EXCEPTION 'Réponse : date de réception et montant confirmé requis' USING ERRCODE = 'check_violation';
      END IF;
    ELSIF (OLD.status, NEW.status) = ('sent','no_response') THEN
      NULL;
    ELSIF (OLD.status, NEW.status) IN (('received','closed'), ('no_response','closed')) THEN
      IF length(trim(coalesce(NEW.conclusion, ''))) = 0 THEN
        RAISE EXCEPTION 'Clôture : conclusion requise' USING ERRCODE = 'check_violation';
      END IF;
      IF NEW.status = 'closed' AND OLD.status = 'received' AND coalesce(NEW.book_balance - NEW.confirmed_amount, 0) <> 0
         AND length(trim(coalesce(NEW.reconciliation, ''))) = 0 THEN
        RAISE EXCEPTION 'Écart de % : rapprochement requis avant clôture', NEW.book_balance - NEW.confirmed_amount USING ERRCODE = 'check_violation';
      END IF;
      IF OLD.status = 'no_response' AND NEW.request_form <> 'negative'
         AND length(trim(coalesce(NEW.alternative_procedures, ''))) = 0 THEN
        RAISE EXCEPTION 'Sans réponse : procédures alternatives requises avant clôture' USING ERRCODE = 'check_violation';
      END IF;
      IF coalesce(authz.fa_role(NEW.engagement_id), '') NOT IN ('partner','manager','in_charge','staff') THEN
        RAISE EXCEPTION 'Clôture réservée à l''équipe' USING ERRCODE = 'insufficient_privilege';
      END IF;
      NEW.closed_by := auth.uid(); NEW.closed_at := now();
    ELSIF (OLD.status, NEW.status) IN (('closed','received'), ('closed','no_response')) THEN
      IF coalesce(authz.fa_role(NEW.engagement_id), '') NOT IN ('partner','manager','in_charge') THEN
        RAISE EXCEPTION 'Réouverture : encadrement de la mission' USING ERRCODE = 'insufficient_privilege';
      END IF;
      NEW.closed_by := NULL; NEW.closed_at := NULL;
    ELSE
      RAISE EXCEPTION 'Circularisation : transition interdite % → %', OLD.status, NEW.status USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER fa_confirmations_guard BEFORE INSERT OR UPDATE OR DELETE ON public.fa_confirmations
  FOR EACH ROW EXECUTE FUNCTION public.guard_fa_confirmation();

-- ---------------------------------------------------------------------
-- 5. Anomalies et écritures d'ajustement proposées
-- ---------------------------------------------------------------------
CREATE TABLE public.fa_misstatements (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id  uuid NOT NULL,
  engagement_id    uuid NOT NULL,
  reference        text NOT NULL CHECK (length(trim(reference)) > 0),
  source_type      text NOT NULL CHECK (source_type IN ('sample','confirmation','account_review','analytical','other')),
  source_id        uuid,
  kind             text NOT NULL CHECK (kind IN ('factual','judgmental','projected')),
  description      text NOT NULL CHECK (length(trim(description)) > 0),
  status           text NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','corrected','uncorrected','withdrawn')),
  entity_response  text,
  withdrawn_reason text,
  decided_by       uuid REFERENCES public.profiles(id),
  decided_at       timestamptz,
  created_by       uuid NOT NULL REFERENCES public.profiles(id),
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (engagement_id, reference),
  UNIQUE (id, engagement_id),
  FOREIGN KEY (engagement_id, organization_id) REFERENCES public.engagements(id, organization_id) ON DELETE CASCADE,
  CHECK (kind <> 'projected' OR source_type = 'sample'),
  CHECK (source_type IN ('analytical','other') OR source_id IS NOT NULL),
  CHECK (status NOT IN ('corrected','uncorrected') OR length(trim(coalesce(entity_response, ''))) > 0),
  CHECK (status <> 'withdrawn' OR length(trim(coalesce(withdrawn_reason, ''))) > 0)
);

CREATE TABLE public.fa_misstatement_lines (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id  uuid NOT NULL,
  engagement_id    uuid NOT NULL,
  misstatement_id  uuid NOT NULL,
  account_number   varchar(20) NOT NULL CHECK (account_number ~ '^[0-9]+$'),
  label            text,
  debit            numeric(20,2) NOT NULL DEFAULT 0 CHECK (debit >= 0),
  credit           numeric(20,2) NOT NULL DEFAULT 0 CHECK (credit >= 0),
  FOREIGN KEY (misstatement_id, engagement_id) REFERENCES public.fa_misstatements(id, engagement_id) ON DELETE CASCADE,
  CHECK ((debit > 0) <> (credit > 0))
);

CREATE OR REPLACE FUNCTION public.guard_fa_misstatement() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_ok boolean;
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF NEW.created_by IS DISTINCT FROM auth.uid() THEN
      RAISE EXCEPTION 'Anomalie : saisie au nom de l''utilisateur authentifié' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.status <> 'proposed' THEN
      RAISE EXCEPTION 'Anomalie : commence au statut « proposée »' USING ERRCODE = 'check_violation';
    END IF;
  ELSIF TG_OP = 'DELETE' THEN
    IF OLD.status <> 'proposed' THEN
      RAISE EXCEPTION 'Anomalie décidée : conservée (retirez-la avec un motif)' USING ERRCODE = 'check_violation';
    END IF;
    RETURN OLD;
  ELSE
    IF OLD.status <> 'proposed' AND (NEW.kind, NEW.description, NEW.source_type, NEW.source_id, NEW.reference)
         IS DISTINCT FROM (OLD.kind, OLD.description, OLD.source_type, OLD.source_id, OLD.reference) THEN
      RAISE EXCEPTION 'Anomalie décidée : contenu figé' USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.status IS DISTINCT FROM OLD.status THEN
      IF NOT ((OLD.status = 'proposed' AND NEW.status IN ('corrected','uncorrected','withdrawn'))
              OR (OLD.status IN ('corrected','uncorrected','withdrawn') AND NEW.status = 'proposed')
              OR (OLD.status IN ('corrected','uncorrected') AND NEW.status IN ('corrected','uncorrected'))) THEN
        RAISE EXCEPTION 'Anomalie : transition interdite % → %', OLD.status, NEW.status USING ERRCODE = 'check_violation';
      END IF;
      IF coalesce(authz.fa_role(NEW.engagement_id), '') NOT IN ('partner','manager','in_charge') THEN
        RAISE EXCEPTION 'Décision sur une anomalie : encadrement de la mission' USING ERRCODE = 'insufficient_privilege';
      END IF;
      IF NEW.status = 'proposed' THEN
        NEW.decided_by := NULL; NEW.decided_at := NULL;
      ELSE
        NEW.decided_by := auth.uid(); NEW.decided_at := now();
      END IF;
    END IF;
  END IF;
  -- la source existe dans la mission
  IF NEW.source_type = 'sample' THEN
    v_ok := EXISTS (SELECT 1 FROM public.fa_samples WHERE id = NEW.source_id AND engagement_id = NEW.engagement_id);
  ELSIF NEW.source_type = 'confirmation' THEN
    v_ok := EXISTS (SELECT 1 FROM public.fa_confirmations WHERE id = NEW.source_id AND engagement_id = NEW.engagement_id);
  ELSIF NEW.source_type = 'account_review' THEN
    v_ok := EXISTS (SELECT 1 FROM public.fa_account_reviews WHERE id = NEW.source_id AND engagement_id = NEW.engagement_id);
  ELSE
    v_ok := true;
  END IF;
  IF NOT v_ok THEN
    RAISE EXCEPTION 'Anomalie : source introuvable dans la mission' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER fa_misstatements_guard BEFORE INSERT OR UPDATE OR DELETE ON public.fa_misstatements
  FOR EACH ROW EXECUTE FUNCTION public.guard_fa_misstatement();

CREATE OR REPLACE FUNCTION public.guard_fa_misstatement_line() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM public.fa_misstatements WHERE id = coalesce(NEW.misstatement_id, OLD.misstatement_id)
                                                     AND status <> 'proposed') THEN
    RAISE EXCEPTION 'Anomalie décidée : écriture figée' USING ERRCODE = 'check_violation';
  END IF;
  RETURN coalesce(NEW, OLD);
END $$;
CREATE TRIGGER fa_misstatement_lines_guard BEFORE INSERT OR UPDATE OR DELETE ON public.fa_misstatement_lines
  FOR EACH ROW EXECUTE FUNCTION public.guard_fa_misstatement_line();

-- Écriture équilibrée, vérifiée en fin de transaction
CREATE OR REPLACE FUNCTION public.check_fa_misstatement_balanced() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_id uuid; v_d numeric; v_c numeric; v_n int;
BEGIN
  v_id := (to_jsonb(coalesce(NEW, OLD)) ->> CASE WHEN TG_TABLE_NAME = 'fa_misstatements' THEN 'id' ELSE 'misstatement_id' END)::uuid;
  IF NOT EXISTS (SELECT 1 FROM public.fa_misstatements WHERE id = v_id) THEN RETURN NULL; END IF;
  SELECT coalesce(sum(debit), 0), coalesce(sum(credit), 0), count(*) INTO v_d, v_c, v_n
    FROM public.fa_misstatement_lines WHERE misstatement_id = v_id;
  IF v_n < 2 OR v_d <> v_c THEN
    RAISE EXCEPTION 'Écriture d''ajustement déséquilibrée ou incomplète (débit %, crédit %, % ligne(s))', v_d, v_c, v_n
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER fa_misstatements_balanced AFTER INSERT OR UPDATE ON public.fa_misstatements
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.check_fa_misstatement_balanced();
CREATE CONSTRAINT TRIGGER fa_misstatement_lines_balanced AFTER INSERT OR UPDATE OR DELETE ON public.fa_misstatement_lines
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.check_fa_misstatement_balanced();

-- Conclusion de l'auditeur sur les anomalies non corrigées
CREATE TABLE public.fa_conclusions (
  engagement_id          uuid PRIMARY KEY,
  organization_id        uuid NOT NULL,
  uncorrected_conclusion text NOT NULL CHECK (length(trim(uncorrected_conclusion)) > 0),
  updated_by             uuid NOT NULL REFERENCES public.profiles(id),
  updated_at             timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (engagement_id, organization_id) REFERENCES public.engagements(id, organization_id) ON DELETE CASCADE
);
CREATE OR REPLACE FUNCTION public.guard_fa_conclusion() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF coalesce(authz.fa_role(NEW.engagement_id), '') NOT IN ('partner','manager') OR NEW.updated_by IS DISTINCT FROM auth.uid() THEN
    RAISE EXCEPTION 'Conclusion sur les anomalies : manager ou associé, en son nom' USING ERRCODE = 'insufficient_privilege';
  END IF;
  NEW.updated_at := now();
  RETURN NEW;
END $$;
CREATE TRIGGER fa_conclusions_guard BEFORE INSERT OR UPDATE ON public.fa_conclusions
  FOR EACH ROW EXECUTE FUNCTION public.guard_fa_conclusion();

-- ---------------------------------------------------------------------
-- 6. Rattachements (éléments probants, notes de revue) aux objets du lot 7
-- ---------------------------------------------------------------------
ALTER TABLE public.evidence_links DROP CONSTRAINT evidence_links_object_type_check;
ALTER TABLE public.evidence_links ADD CONSTRAINT evidence_links_object_type_check CHECK (object_type IN
  ('workpaper','procedure','engagement_risk','fa_sample_item','fa_confirmation','fa_misstatement','fa_account_review'));

-- ---------------------------------------------------------------------
-- 7. Conditions d'émission propres à l'audit financier
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.guard_fa_issuance() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_n int;
BEGIN
  IF NOT (OLD.status = 'reporting' AND NEW.status = 'issued')
     OR NEW.engagement_type NOT IN ('statutory_audit','contractual_audit') THEN
    RETURN NEW;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.fa_materiality WHERE engagement_id = NEW.id AND status = 'approved') THEN
    RAISE EXCEPTION 'Audit financier : seuils non approuvés' USING ERRCODE = 'check_violation';
  END IF;
  SELECT count(*) INTO v_n FROM public.fa_account_reviews WHERE engagement_id = NEW.id AND status <> 'reviewed';
  IF v_n > 0 THEN
    RAISE EXCEPTION 'Audit financier : % compte(s) non revu(s)', v_n USING ERRCODE = 'check_violation';
  END IF;
  SELECT count(*) INTO v_n FROM public.fa_samples WHERE engagement_id = NEW.id AND status <> 'concluded';
  IF v_n > 0 THEN
    RAISE EXCEPTION 'Audit financier : % échantillon(s) non conclu(s)', v_n USING ERRCODE = 'check_violation';
  END IF;
  SELECT count(*) INTO v_n FROM public.fa_confirmations WHERE engagement_id = NEW.id AND status <> 'closed';
  IF v_n > 0 THEN
    RAISE EXCEPTION 'Audit financier : % circularisation(s) non close(s)', v_n USING ERRCODE = 'check_violation';
  END IF;
  SELECT count(*) INTO v_n FROM public.fa_misstatements WHERE engagement_id = NEW.id AND status = 'proposed';
  IF v_n > 0 THEN
    RAISE EXCEPTION 'Audit financier : % anomalie(s) sans décision', v_n USING ERRCODE = 'check_violation';
  END IF;
  IF EXISTS (SELECT 1 FROM public.fa_misstatements WHERE engagement_id = NEW.id AND status = 'uncorrected')
     AND NOT EXISTS (SELECT 1 FROM public.fa_conclusions WHERE engagement_id = NEW.id) THEN
    RAISE EXCEPTION 'Audit financier : conclusion sur les anomalies non corrigées requise' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER engagements_fa_issuance BEFORE UPDATE ON public.engagements
  FOR EACH ROW EXECUTE FUNCTION public.guard_fa_issuance();

-- ---------------------------------------------------------------------
-- 8. Gel, type de mission, updated_at
-- ---------------------------------------------------------------------
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['fa_materiality','fa_cycle_mappings','fa_account_reviews','fa_populations','fa_population_items',
                           'fa_samples','fa_sample_items','fa_confirmations','fa_misstatements','fa_misstatement_lines',
                           'fa_conclusions'] LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE INSERT OR UPDATE OR DELETE ON public.%I
                    FOR EACH ROW EXECUTE FUNCTION public.guard_dossier_open()', t || '_dossier_open', t);
  END LOOP;
  FOREACH t IN ARRAY ARRAY['fa_materiality','fa_cycle_mappings','fa_account_reviews','fa_populations','fa_confirmations',
                           'fa_misstatements','fa_conclusions'] LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE INSERT ON public.%I FOR EACH ROW EXECUTE FUNCTION public.guard_fa_engagement()',
                   t || '_fa_type', t);
  END LOOP;
  FOREACH t IN ARRAY ARRAY['fa_account_reviews','fa_samples','fa_confirmations','fa_misstatements'] LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.set_updated_at()',
                   t || '_updated_at', t);
  END LOOP;
END $$;

CREATE INDEX fa_population_items_pop_idx ON public.fa_population_items (population_id, line_no);
CREATE INDEX fa_sample_items_sample_idx ON public.fa_sample_items (sample_id);
CREATE INDEX fa_misstatement_lines_idx ON public.fa_misstatement_lines (misstatement_id);
CREATE INDEX fa_account_reviews_cycle_idx ON public.fa_account_reviews (engagement_id, cycle_code);

-- ---------------------------------------------------------------------
-- 9. RLS : lecture par l'équipe d'audit (indépendance déclarée), écriture selon le rôle
-- ---------------------------------------------------------------------
DO $$
DECLARE spec record;
BEGIN
  FOR spec IN SELECT * FROM (VALUES
      ('fa_materiality',        ARRAY['partner','manager','in_charge']),
      ('fa_cycle_mappings',     ARRAY['partner','manager','in_charge']),
      ('fa_account_reviews',    ARRAY['partner','manager','in_charge','staff']),
      ('fa_populations',        ARRAY['partner','manager','in_charge','staff']),
      ('fa_population_items',   ARRAY['partner','manager','in_charge','staff']),
      ('fa_samples',            ARRAY['partner','manager','in_charge','staff']),
      ('fa_sample_items',       ARRAY['partner','manager','in_charge','staff']),
      ('fa_confirmations',      ARRAY['partner','manager','in_charge','staff']),
      ('fa_misstatements',      ARRAY['partner','manager','in_charge','staff']),
      ('fa_misstatement_lines', ARRAY['partner','manager','in_charge','staff']),
      ('fa_conclusions',        ARRAY['partner','manager'])
    ) AS s(tbl, roles)
  LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', spec.tbl);
    EXECUTE format('CREATE POLICY %I ON public.%I FOR SELECT TO authenticated USING (authz.can_read_dossier(engagement_id))',
                   spec.tbl || '_select', spec.tbl);
    EXECUTE format('CREATE POLICY %I ON public.%I FOR INSERT TO authenticated
                      WITH CHECK (authz.has_engagement_role(engagement_id, %L::text[]))', spec.tbl || '_insert', spec.tbl, spec.roles);
    EXECUTE format('CREATE POLICY %I ON public.%I FOR UPDATE TO authenticated
                      USING (authz.has_engagement_role(engagement_id, %L::text[]))
                      WITH CHECK (authz.has_engagement_role(engagement_id, %L::text[]))',
                   spec.tbl || '_update', spec.tbl, spec.roles, spec.roles);
    EXECUTE format('CREATE POLICY %I ON public.%I FOR DELETE TO authenticated
                      USING (authz.has_engagement_role(engagement_id, %L::text[]))', spec.tbl || '_delete', spec.tbl, spec.roles);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON public.%I TO authenticated', spec.tbl);
    EXECUTE format('GRANT ALL ON public.%I TO service_role', spec.tbl);
  END LOOP;
END $$;

-- ---------------------------------------------------------------------
-- 10. Lecture seule des données comptables de l'entité auditée par l'équipe de mission
--     (indépendance déclarée, mission ni archivée ; l'audité n'en bénéficie pas)
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION authz.audits_company(p_company uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.engagements e JOIN public.engagement_members m ON m.engagement_id = e.id
     WHERE e.company_id = p_company AND e.status <> 'archived'
       AND m.user_id = auth.uid() AND m.independence_confirmed_at IS NOT NULL
       AND m.role IN ('partner','manager','in_charge','staff','quality_reviewer','observer'))
$$;
REVOKE ALL ON FUNCTION authz.audits_company(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION authz.audits_company(uuid) TO authenticated, service_role;

CREATE POLICY fiscal_years_select_audit ON public.fiscal_years FOR SELECT TO authenticated
  USING (authz.audits_company(company_id));
CREATE POLICY trial_balance_entries_select_audit ON public.trial_balance_entries FOR SELECT TO authenticated
  USING (authz.audits_company(company_id));
CREATE POLICY import_jobs_select_audit ON public.import_jobs FOR SELECT TO authenticated
  USING (authz.audits_company(company_id));
