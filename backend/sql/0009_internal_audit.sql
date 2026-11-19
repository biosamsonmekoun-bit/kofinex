-- =====================================================================
-- KOFINEX — Migration 0009 : audit interne (lot 8)
-- Plan annuel d'audit, historique de la cartographie des risques, constats, recommandations,
-- plans d'action et leur suivi, rapports d'audit, accès de l'audité, conditions d'émission.
-- Aucune échelle de cotation n'est fournie : l'échelle des constats est une donnée de la méthodologie.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 0. Méthodologie : échelle de cotation des constats
-- ---------------------------------------------------------------------
ALTER TABLE public.methodology_items DROP CONSTRAINT methodology_items_item_type_check;
ALTER TABLE public.methodology_items ADD CONSTRAINT methodology_items_item_type_check CHECK (item_type IN
  ('assertion','cycle','risk_scale','procedure_template','ic_component','ic_principle','deficiency_scale','parameter',
   'finding_scale'));

-- Rôle dans la mission, indépendance déclarée (équipe) ou rôle sans déclaration (audité, observateur)
CREATE OR REPLACE FUNCTION authz.ia_role(p_engagement uuid) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT role FROM public.engagement_members
   WHERE engagement_id = p_engagement AND user_id = auth.uid()
     AND (independence_confirmed_at IS NOT NULL OR role IN ('auditee','observer'))
$$;
REVOKE ALL ON FUNCTION authz.ia_role(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION authz.ia_role(uuid) TO authenticated, service_role;

CREATE OR REPLACE FUNCTION public.guard_ia_engagement() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF (SELECT engagement_type FROM public.engagements WHERE id = NEW.engagement_id) NOT IN ('internal_audit','ic_assessment') THEN
    RAISE EXCEPTION 'Fonction réservée aux missions d''audit interne et d''évaluation du contrôle interne'
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;

-- ---------------------------------------------------------------------
-- 1. Plan annuel d'audit
-- ---------------------------------------------------------------------
CREATE TABLE public.audit_plans (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id    uuid NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
  title              text NOT NULL CHECK (length(trim(title)) > 0),
  period_start       date NOT NULL,
  period_end         date NOT NULL,
  description        text,
  status             text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','closed')),
  approval_body      text,               -- instance qui a approuvé (comité d'audit, conseil…)
  approval_reference text,               -- procès-verbal, délibération
  approval_date      date,
  approved_by        uuid REFERENCES public.profiles(id),   -- qui a enregistré l'approbation
  approved_at        timestamptz,
  created_by         uuid NOT NULL REFERENCES public.profiles(id),
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, title),
  UNIQUE (id, organization_id),
  CHECK (period_end > period_start),
  CHECK (status = 'draft' OR (length(trim(coalesce(approval_body, ''))) > 0 AND approval_date IS NOT NULL
                              AND approved_by IS NOT NULL))
);

CREATE TABLE public.audit_plan_items (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id      uuid NOT NULL,
  plan_id              uuid NOT NULL,
  company_id           uuid NOT NULL,
  process_id           uuid,
  title                text NOT NULL CHECK (length(trim(title)) > 0),
  rationale            text NOT NULL CHECK (length(trim(rationale)) >= 10),   -- justification fondée sur les risques
  priority_rank        int CHECK (priority_rank > 0),
  planned_start        date,
  planned_end          date,
  budget_days          numeric(8,2) CHECK (budget_days >= 0),
  engagement_id        uuid,
  status               text NOT NULL DEFAULT 'planned'
                         CHECK (status IN ('planned','in_progress','completed','postponed','cancelled')),
  status_reason        text,
  added_after_approval boolean NOT NULL DEFAULT false,
  change_reason        text,
  created_by           uuid NOT NULL REFERENCES public.profiles(id),
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (plan_id, organization_id) REFERENCES public.audit_plans(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id),
  FOREIGN KEY (process_id, company_id) REFERENCES public.processes(id, company_id),
  FOREIGN KEY (engagement_id, organization_id) REFERENCES public.engagements(id, organization_id) ON DELETE SET NULL (engagement_id),
  CHECK (planned_end IS NULL OR planned_start IS NULL OR planned_end >= planned_start),
  CHECK (status NOT IN ('postponed','cancelled') OR length(trim(coalesce(status_reason, ''))) > 0)
);
CREATE UNIQUE INDEX audit_plan_items_engagement_uq ON public.audit_plan_items (engagement_id) WHERE engagement_id IS NOT NULL;

CREATE TABLE public.audit_plan_item_history (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  plan_item_id    uuid NOT NULL REFERENCES public.audit_plan_items(id) ON DELETE CASCADE,
  operation       text NOT NULL CHECK (operation IN ('insert','update')),
  before          jsonb,
  after           jsonb NOT NULL,
  reason          text,
  changed_by      uuid REFERENCES public.profiles(id),
  changed_at      timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION public.guard_audit_plan() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status <> 'draft' THEN
      RAISE EXCEPTION 'Plan approuvé : conservé (clôturez-le)' USING ERRCODE = 'check_violation';
    END IF;
    RETURN OLD;
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.created_by IS DISTINCT FROM auth.uid() OR NEW.status <> 'draft' THEN
      RAISE EXCEPTION 'Plan : créé en brouillon, au nom de l''utilisateur authentifié' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.status <> 'draft' AND (NEW.title, NEW.period_start, NEW.period_end, NEW.approval_body, NEW.approval_reference,
                                NEW.approval_date, NEW.approved_by, NEW.created_by)
       IS DISTINCT FROM (OLD.title, OLD.period_start, OLD.period_end, OLD.approval_body, OLD.approval_reference,
                         OLD.approval_date, OLD.approved_by, OLD.created_by) THEN
    RAISE EXCEPTION 'Plan approuvé : en-tête et approbation figés' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status THEN
    IF (OLD.status, NEW.status) = ('draft','approved') THEN
      IF NEW.approved_by IS DISTINCT FROM auth.uid() THEN
        RAISE EXCEPTION 'Approbation enregistrée au nom de l''utilisateur authentifié' USING ERRCODE = 'insufficient_privilege';
      END IF;
      IF NOT EXISTS (SELECT 1 FROM public.audit_plan_items WHERE plan_id = NEW.id) THEN
        RAISE EXCEPTION 'Plan vide : ajoutez les missions prévues avant l''approbation' USING ERRCODE = 'check_violation';
      END IF;
      NEW.approved_at := now();
    ELSIF (OLD.status, NEW.status) = ('approved','closed') THEN
      IF EXISTS (SELECT 1 FROM public.audit_plan_items WHERE plan_id = NEW.id AND status IN ('planned','in_progress')) THEN
        RAISE EXCEPTION 'Clôture : chaque mission du plan doit être réalisée, reportée ou annulée' USING ERRCODE = 'check_violation';
      END IF;
    ELSE
      RAISE EXCEPTION 'Plan : transition interdite % → %', OLD.status, NEW.status USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER audit_plans_guard BEFORE INSERT OR UPDATE OR DELETE ON public.audit_plans
  FOR EACH ROW EXECUTE FUNCTION public.guard_audit_plan();

CREATE OR REPLACE FUNCTION public.guard_audit_plan_item() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_plan text; v_eng public.engagements;
BEGIN
  SELECT status INTO v_plan FROM public.audit_plans WHERE id = coalesce(NEW.plan_id, OLD.plan_id);
  IF v_plan = 'closed' THEN
    RAISE EXCEPTION 'Plan clôturé : non modifiable' USING ERRCODE = 'check_violation';
  END IF;
  IF TG_OP = 'DELETE' THEN
    IF v_plan <> 'draft' THEN
      RAISE EXCEPTION 'Plan approuvé : une mission prévue s''annule avec un motif, elle ne se supprime pas'
        USING ERRCODE = 'check_violation';
    END IF;
    RETURN OLD;
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.created_by IS DISTINCT FROM auth.uid() THEN
      RAISE EXCEPTION 'Mission prévue : saisie au nom de l''utilisateur authentifié' USING ERRCODE = 'insufficient_privilege';
    END IF;
    NEW.added_after_approval := v_plan = 'approved';
  ELSIF NEW.plan_id <> OLD.plan_id OR NEW.added_after_approval <> OLD.added_after_approval OR NEW.created_by <> OLD.created_by THEN
    RAISE EXCEPTION 'Mission prévue : plan, origine et auteur immuables' USING ERRCODE = 'check_violation';
  END IF;
  -- toute modification après approbation est motivée (ajout, contenu ; le statut a son propre motif)
  IF v_plan = 'approved' AND (TG_OP = 'INSERT' OR (NEW.title, NEW.company_id, NEW.process_id, NEW.rationale, NEW.priority_rank,
                                                   NEW.planned_start, NEW.planned_end, NEW.budget_days)
                               IS DISTINCT FROM (OLD.title, OLD.company_id, OLD.process_id, OLD.rationale, OLD.priority_rank,
                                                 OLD.planned_start, OLD.planned_end, OLD.budget_days))
     AND (length(trim(coalesce(NEW.change_reason, ''))) = 0
          OR (TG_OP = 'UPDATE' AND NEW.change_reason IS NOT DISTINCT FROM OLD.change_reason)) THEN
    RAISE EXCEPTION 'Plan approuvé : motif de la modification requis' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.engagement_id IS NOT NULL THEN
    SELECT * INTO v_eng FROM public.engagements WHERE id = NEW.engagement_id;
    IF v_eng.engagement_type <> 'internal_audit' OR v_eng.company_id <> NEW.company_id THEN
      RAISE EXCEPTION 'La mission rattachée doit être une mission d''audit interne de la même entité'
        USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  IF NEW.status = 'completed' AND (TG_OP = 'INSERT' OR OLD.status <> 'completed')
     AND (v_eng.id IS NULL OR v_eng.status NOT IN ('issued','archived')) THEN
    RAISE EXCEPTION 'Réalisée : la mission rattachée doit être émise' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER audit_plan_items_guard BEFORE INSERT OR UPDATE OR DELETE ON public.audit_plan_items
  FOR EACH ROW EXECUTE FUNCTION public.guard_audit_plan_item();

CREATE OR REPLACE FUNCTION public.log_audit_plan_item() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF TG_OP = 'UPDATE' AND (to_jsonb(NEW) - 'updated_at') = (to_jsonb(OLD) - 'updated_at') THEN
    RETURN NULL;
  END IF;
  INSERT INTO public.audit_plan_item_history (organization_id, plan_item_id, operation, before, after, reason, changed_by)
  VALUES (NEW.organization_id, NEW.id, lower(TG_OP), CASE WHEN TG_OP = 'UPDATE' THEN to_jsonb(OLD) END, to_jsonb(NEW),
          CASE WHEN TG_OP = 'INSERT' THEN NEW.change_reason
               WHEN NEW.status IS DISTINCT FROM OLD.status THEN NEW.status_reason
               WHEN NEW.change_reason IS DISTINCT FROM OLD.change_reason THEN NEW.change_reason END,
          auth.uid());
  RETURN NULL;
END $$;
CREATE TRIGGER audit_plan_items_history AFTER INSERT OR UPDATE ON public.audit_plan_items
  FOR EACH ROW EXECUTE FUNCTION public.log_audit_plan_item();

-- ---------------------------------------------------------------------
-- 2. Cartographie : historique des cotations du registre des risques
-- ---------------------------------------------------------------------
CREATE TABLE public.risk_rating_history (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id     uuid NOT NULL,
  company_id          uuid NOT NULL,
  risk_id             uuid NOT NULL REFERENCES public.risks(id) ON DELETE CASCADE,
  scale_version_id    uuid,
  inherent_likelihood smallint,
  inherent_impact     smallint,
  residual_likelihood smallint,
  residual_impact     smallint,
  changed_by          uuid REFERENCES public.profiles(id),
  changed_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX risk_rating_history_idx ON public.risk_rating_history (risk_id, changed_at);

CREATE OR REPLACE FUNCTION public.log_risk_rating() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF TG_OP = 'INSERT' OR (NEW.scale_version_id, NEW.inherent_likelihood, NEW.inherent_impact, NEW.residual_likelihood,
                          NEW.residual_impact)
       IS DISTINCT FROM (OLD.scale_version_id, OLD.inherent_likelihood, OLD.inherent_impact, OLD.residual_likelihood,
                         OLD.residual_impact) THEN
    INSERT INTO public.risk_rating_history (organization_id, company_id, risk_id, scale_version_id, inherent_likelihood,
                                            inherent_impact, residual_likelihood, residual_impact, changed_by)
    VALUES (NEW.organization_id, NEW.company_id, NEW.id, NEW.scale_version_id, NEW.inherent_likelihood, NEW.inherent_impact,
            NEW.residual_likelihood, NEW.residual_impact, auth.uid());
  END IF;
  RETURN NULL;
END $$;
CREATE TRIGGER risks_rating_history AFTER INSERT OR UPDATE ON public.risks
  FOR EACH ROW EXECUTE FUNCTION public.log_risk_rating();

-- ---------------------------------------------------------------------
-- 3. Constats et recommandations
-- ---------------------------------------------------------------------
ALTER TABLE public.engagement_risks ADD CONSTRAINT engagement_risks_id_engagement_key UNIQUE (id, engagement_id);

CREATE TABLE public.findings (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id     uuid NOT NULL,
  engagement_id       uuid NOT NULL,
  reference           text NOT NULL CHECK (length(trim(reference)) > 0),
  title               text NOT NULL CHECK (length(trim(title)) > 0),
  condition           text NOT NULL CHECK (length(trim(condition)) > 0),   -- ce qui a été constaté
  criteria            text NOT NULL CHECK (length(trim(criteria)) > 0),    -- référentiel attendu
  cause               text,
  effect              text,                                                -- conséquence, risque
  rating_code         text,                                                -- niveau de l'échelle de la méthodologie
  process_id          uuid,
  engagement_risk_id  uuid,
  workpaper_id        uuid,
  status              text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','validated','communicated')),
  validated_by        uuid REFERENCES public.profiles(id),
  validated_at        timestamptz,
  communicated_by     uuid REFERENCES public.profiles(id),
  communicated_at     timestamptz,
  response_due        date,
  management_response text,
  response_by_name    text,             -- auteur de la réponse (direction de l'entité)
  response_user_id    uuid REFERENCES public.profiles(id),   -- si saisie par l'audité lui-même
  response_recorded_by uuid REFERENCES public.profiles(id),
  response_at         timestamptz,
  reopen_reason       text,
  created_by          uuid NOT NULL REFERENCES public.profiles(id),
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  UNIQUE (engagement_id, reference),
  UNIQUE (id, engagement_id),
  FOREIGN KEY (engagement_id, organization_id) REFERENCES public.engagements(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (engagement_risk_id, engagement_id) REFERENCES public.engagement_risks(id, engagement_id),
  FOREIGN KEY (workpaper_id, engagement_id) REFERENCES public.workpapers(id, engagement_id) ON DELETE SET NULL (workpaper_id),
  CHECK (status = 'draft' OR (validated_by IS NOT NULL AND rating_code IS NOT NULL)),
  CHECK (status <> 'communicated' OR communicated_by IS NOT NULL),
  CHECK (management_response IS NULL OR (length(trim(response_by_name)) > 0 AND response_at IS NOT NULL))
);

CREATE TABLE public.recommendations (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  engagement_id   uuid NOT NULL,
  finding_id      uuid NOT NULL,
  reference       text NOT NULL CHECK (length(trim(reference)) > 0),
  text            text NOT NULL CHECK (length(trim(text)) > 0),
  created_by      uuid NOT NULL REFERENCES public.profiles(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (engagement_id, reference),
  UNIQUE (id, engagement_id),
  FOREIGN KEY (finding_id, engagement_id) REFERENCES public.findings(id, engagement_id) ON DELETE CASCADE
);

CREATE OR REPLACE FUNCTION public.guard_finding() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_role text; v_company uuid; v_levels jsonb; v_content_changed boolean; v_response_changed boolean;
BEGIN
  v_role := coalesce(authz.ia_role(coalesce(NEW.engagement_id, OLD.engagement_id)), '');
  IF TG_OP = 'DELETE' THEN
    IF OLD.status <> 'draft' THEN
      RAISE EXCEPTION 'Constat validé : conservé (remettez-le en brouillon pour le modifier)' USING ERRCODE = 'check_violation';
    END IF;
    RETURN OLD;
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.created_by IS DISTINCT FROM auth.uid() OR NEW.status <> 'draft' OR NEW.management_response IS NOT NULL THEN
      RAISE EXCEPTION 'Constat : créé en brouillon, au nom de l''utilisateur authentifié' USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  v_content_changed := TG_OP = 'INSERT' OR (NEW.reference, NEW.title, NEW.condition, NEW.criteria, NEW.cause, NEW.effect,
      NEW.rating_code, NEW.process_id, NEW.engagement_risk_id, NEW.workpaper_id)
    IS DISTINCT FROM (OLD.reference, OLD.title, OLD.condition, OLD.criteria, OLD.cause, OLD.effect, OLD.rating_code,
                      OLD.process_id, OLD.engagement_risk_id, OLD.workpaper_id);
  v_response_changed := TG_OP = 'UPDATE' AND (NEW.management_response, NEW.response_by_name, NEW.response_user_id)
    IS DISTINCT FROM (OLD.management_response, OLD.response_by_name, OLD.response_user_id);

  -- l'audité ne peut que répondre à un constat communiqué
  IF v_role = 'auditee' THEN
    IF TG_OP = 'INSERT' OR v_content_changed OR NEW.status IS DISTINCT FROM OLD.status OR OLD.status <> 'communicated'
       OR (to_jsonb(NEW) - ARRAY['management_response','response_by_name','response_user_id','response_recorded_by',
                                 'response_at','updated_at'])
          IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['management_response','response_by_name','response_user_id',
                                                   'response_recorded_by','response_at','updated_at']) THEN
      RAISE EXCEPTION 'Audité : seule la réponse à un constat communiqué est possible' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.response_user_id IS DISTINCT FROM auth.uid() THEN
      RAISE EXCEPTION 'Réponse : enregistrée au nom de l''utilisateur authentifié' USING ERRCODE = 'insufficient_privilege';
    END IF;
  ELSIF v_role NOT IN ('partner','manager','in_charge','staff') THEN
    RAISE EXCEPTION 'Constats : équipe d''audit ou audité uniquement' USING ERRCODE = 'insufficient_privilege';
  END IF;

  IF TG_OP = 'UPDATE' AND OLD.status <> 'draft' AND NEW.status <> 'draft' AND v_content_changed THEN
    RAISE EXCEPTION 'Constat validé : contenu figé (remettez-le en brouillon, avec un motif)' USING ERRCODE = 'check_violation';
  END IF;
  IF v_response_changed THEN
    IF NEW.status <> 'communicated' THEN
      RAISE EXCEPTION 'Réponse : le constat doit avoir été communiqué' USING ERRCODE = 'check_violation';
    END IF;
    IF v_role <> 'auditee' AND NEW.response_user_id IS NOT NULL THEN
      RAISE EXCEPTION 'Réponse saisie par l''équipe : indiquez son auteur, pas un compte' USING ERRCODE = 'check_violation';
    END IF;
    NEW.response_recorded_by := auth.uid();
    NEW.response_at := CASE WHEN NEW.management_response IS NULL THEN NULL ELSE now() END;
  END IF;

  -- références internes à la mission
  IF NEW.process_id IS NOT NULL THEN
    SELECT company_id INTO v_company FROM public.engagements WHERE id = NEW.engagement_id;
    IF NOT EXISTS (SELECT 1 FROM public.processes WHERE id = NEW.process_id AND company_id = v_company) THEN
      RAISE EXCEPTION 'Processus hors de l''entité auditée' USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  IF NEW.rating_code IS NOT NULL AND v_content_changed THEN
    SELECT i.content -> 'levels' INTO v_levels FROM public.engagements e
      JOIN public.methodology_items i ON i.version_id = e.methodology_version_id AND i.item_type = 'finding_scale'
     WHERE e.id = NEW.engagement_id;
    IF v_levels IS NULL OR NOT EXISTS (SELECT 1 FROM jsonb_array_elements(v_levels) l WHERE l ->> 'code' = NEW.rating_code) THEN
      RAISE EXCEPTION 'Cotation « % » absente de l''échelle des constats de la méthodologie', NEW.rating_code
        USING ERRCODE = 'check_violation';
    END IF;
  END IF;

  IF TG_OP = 'UPDATE' AND NEW.status IS DISTINCT FROM OLD.status THEN
    IF (OLD.status, NEW.status) = ('draft','validated') THEN
      IF v_role NOT IN ('partner','manager') OR NEW.validated_by IS DISTINCT FROM auth.uid() THEN
        RAISE EXCEPTION 'Validation d''un constat : manager ou associé, en son nom' USING ERRCODE = 'insufficient_privilege';
      END IF;
      IF NEW.validated_by = NEW.created_by THEN
        RAISE EXCEPTION 'Validation : par une autre personne que l''auteur du constat' USING ERRCODE = 'check_violation';
      END IF;
      IF NOT EXISTS (SELECT 1 FROM public.recommendations WHERE finding_id = NEW.id) THEN
        RAISE EXCEPTION 'Validation : au moins une recommandation est requise' USING ERRCODE = 'check_violation';
      END IF;
      NEW.validated_at := now(); NEW.reopen_reason := NULL;
    ELSIF (OLD.status, NEW.status) = ('validated','communicated') THEN
      IF v_role NOT IN ('partner','manager','in_charge') OR NEW.communicated_by IS DISTINCT FROM auth.uid() THEN
        RAISE EXCEPTION 'Communication à l''audité : encadrement de la mission, en son nom' USING ERRCODE = 'insufficient_privilege';
      END IF;
      NEW.communicated_at := now();
    ELSIF NEW.status = 'draft' THEN
      IF v_role NOT IN ('partner','manager') OR length(trim(coalesce(NEW.reopen_reason, ''))) < 3 THEN
        RAISE EXCEPTION 'Remise en brouillon : manager ou associé, motif requis' USING ERRCODE = 'check_violation';
      END IF;
      NEW.validated_by := NULL; NEW.validated_at := NULL; NEW.communicated_by := NULL; NEW.communicated_at := NULL;
    ELSE
      RAISE EXCEPTION 'Constat : transition interdite % → %', OLD.status, NEW.status USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER findings_guard BEFORE INSERT OR UPDATE OR DELETE ON public.findings
  FOR EACH ROW EXECUTE FUNCTION public.guard_finding();

CREATE OR REPLACE FUNCTION public.guard_recommendation() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF (SELECT status FROM public.findings WHERE id = coalesce(NEW.finding_id, OLD.finding_id)) <> 'draft' THEN
    RAISE EXCEPTION 'Constat validé : recommandations figées' USING ERRCODE = 'check_violation';
  END IF;
  IF TG_OP = 'INSERT' AND NEW.created_by IS DISTINCT FROM auth.uid() THEN
    RAISE EXCEPTION 'Recommandation : saisie au nom de l''utilisateur authentifié' USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN coalesce(NEW, OLD);
END $$;
CREATE TRIGGER recommendations_guard BEFORE INSERT OR UPDATE OR DELETE ON public.recommendations
  FOR EACH ROW EXECUTE FUNCTION public.guard_recommendation();

-- ---------------------------------------------------------------------
-- 4. Plans d'action et suivi (le suivi continue après l'émission de la mission)
-- ---------------------------------------------------------------------
CREATE TABLE public.action_plans (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id   uuid NOT NULL,
  engagement_id     uuid NOT NULL,
  company_id        uuid NOT NULL,
  recommendation_id uuid NOT NULL,
  description       text NOT NULL CHECK (length(trim(description)) > 0),   -- action décidée par la direction
  owner_name        text NOT NULL CHECK (length(trim(owner_name)) > 0),
  owner_user_id     uuid REFERENCES public.profiles(id),
  due_date          date NOT NULL,
  status            text NOT NULL DEFAULT 'planned'
                      CHECK (status IN ('planned','in_progress','implemented','verified','not_implemented','risk_accepted')),
  created_by        uuid NOT NULL REFERENCES public.profiles(id),
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id, engagement_id),
  FOREIGN KEY (engagement_id, organization_id) REFERENCES public.engagements(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (recommendation_id, engagement_id) REFERENCES public.recommendations(id, engagement_id) ON DELETE CASCADE
);
CREATE INDEX action_plans_company_idx ON public.action_plans (company_id, status, due_date);

CREATE TABLE public.action_plan_updates (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  engagement_id   uuid NOT NULL,
  action_plan_id  uuid NOT NULL,
  status          text NOT NULL
                    CHECK (status IN ('planned','in_progress','implemented','verified','not_implemented','risk_accepted')),
  comment         text NOT NULL CHECK (length(trim(comment)) >= 3),
  new_due_date    date,
  author_id       uuid NOT NULL REFERENCES public.profiles(id),
  author_role     text NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (action_plan_id, engagement_id) REFERENCES public.action_plans(id, engagement_id) ON DELETE CASCADE
);
CREATE INDEX action_plan_updates_idx ON public.action_plan_updates (action_plan_id, created_at);

CREATE OR REPLACE FUNCTION public.guard_action_plan() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_role text; v_finding text;
BEGIN
  v_role := coalesce(authz.ia_role(coalesce(NEW.engagement_id, OLD.engagement_id)), '');
  IF TG_OP = 'DELETE' THEN
    IF EXISTS (SELECT 1 FROM public.action_plan_updates WHERE action_plan_id = OLD.id)
       OR (SELECT status FROM public.engagements WHERE id = OLD.engagement_id) IN ('issued','archived') THEN
      RAISE EXCEPTION 'Plan d''action suivi ou mission émise : conservé' USING ERRCODE = 'check_violation';
    END IF;
    IF v_role NOT IN ('partner','manager','in_charge','staff') THEN
      RAISE EXCEPTION 'Suppression : équipe d''audit' USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN OLD;
  END IF;
  IF v_role NOT IN ('partner','manager','in_charge','staff','auditee') THEN
    RAISE EXCEPTION 'Plans d''action : équipe d''audit ou audité' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.created_by IS DISTINCT FROM auth.uid() OR NEW.status <> 'planned' THEN
      RAISE EXCEPTION 'Plan d''action : créé « prévu », au nom de l''utilisateur authentifié' USING ERRCODE = 'check_violation';
    END IF;
    SELECT f.status INTO v_finding FROM public.recommendations r JOIN public.findings f ON f.id = r.finding_id
     WHERE r.id = NEW.recommendation_id;
    IF v_role = 'auditee' AND v_finding <> 'communicated' THEN
      RAISE EXCEPTION 'Audité : plan d''action sur un constat communiqué uniquement' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF (SELECT status FROM public.engagements WHERE id = NEW.engagement_id) IN ('issued','archived') THEN
      RAISE EXCEPTION 'Mission émise : les plans d''action se créent avant l''émission du rapport' USING ERRCODE = 'check_violation';
    END IF;
    NEW.company_id := (SELECT company_id FROM public.engagements WHERE id = NEW.engagement_id);
    RETURN NEW;
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status OR NEW.due_date IS DISTINCT FROM OLD.due_date THEN
    IF coalesce(current_setting('kofinex.action_update', true), 'off') <> 'on' THEN
      RAISE EXCEPTION 'Statut et échéance : modifiés par une mise à jour de suivi' USING ERRCODE = 'check_violation';
    END IF;
  ELSIF (NEW.description, NEW.owner_name, NEW.owner_user_id, NEW.recommendation_id, NEW.company_id, NEW.created_by)
          IS DISTINCT FROM (OLD.description, OLD.owner_name, OLD.owner_user_id, OLD.recommendation_id, OLD.company_id,
                            OLD.created_by)
        AND (SELECT status FROM public.engagements WHERE id = NEW.engagement_id) IN ('issued','archived') THEN
    RAISE EXCEPTION 'Mission émise : le plan d''action figure au rapport, seul son suivi évolue' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER action_plans_guard BEFORE INSERT OR UPDATE OR DELETE ON public.action_plans
  FOR EACH ROW EXECUTE FUNCTION public.guard_action_plan();

-- Une mise à jour de suivi : transitions contrôlées, vérification par l'équipe d'audit, historique non modifiable
CREATE OR REPLACE FUNCTION public.guard_action_plan_update() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_role text; v_old text;
BEGIN
  IF TG_OP <> 'INSERT' THEN
    RAISE EXCEPTION 'Historique du suivi : non modifiable' USING ERRCODE = 'check_violation';
  END IF;
  v_role := coalesce(authz.ia_role(NEW.engagement_id), '');
  IF v_role NOT IN ('partner','manager','in_charge','staff','auditee') OR NEW.author_id IS DISTINCT FROM auth.uid() THEN
    RAISE EXCEPTION 'Suivi : équipe d''audit ou audité, en son nom' USING ERRCODE = 'insufficient_privilege';
  END IF;
  NEW.author_role := v_role;
  SELECT status INTO v_old FROM public.action_plans WHERE id = NEW.action_plan_id FOR UPDATE;
  IF v_old = 'verified' THEN
    RAISE EXCEPTION 'Action vérifiée : suivi clos' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.status = 'verified' THEN
    IF v_role NOT IN ('partner','manager','in_charge') THEN
      RAISE EXCEPTION 'Vérification de la mise en œuvre : encadrement de la mission' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF v_old <> 'implemented' THEN
      RAISE EXCEPTION 'Vérification : l''action doit avoir été déclarée mise en œuvre' USING ERRCODE = 'check_violation';
    END IF;
  ELSIF NEW.status = 'risk_accepted' AND v_role NOT IN ('auditee','partner','manager') THEN
    RAISE EXCEPTION 'Acceptation du risque : déclarée par l''audité ou enregistrée par le manager ou l''associé'
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  PERFORM set_config('kofinex.action_update', 'on', true);
  UPDATE public.action_plans SET status = NEW.status, due_date = coalesce(NEW.new_due_date, due_date)
   WHERE id = NEW.action_plan_id;
  PERFORM set_config('kofinex.action_update', 'off', true);
  RETURN NEW;
END $$;
CREATE TRIGGER action_plan_updates_guard BEFORE INSERT OR UPDATE OR DELETE ON public.action_plan_updates
  FOR EACH ROW EXECUTE FUNCTION public.guard_action_plan_update();

-- ---------------------------------------------------------------------
-- 5. Rapports d'audit (versions ; la version émise est figée avec l'empreinte de son contenu)
-- ---------------------------------------------------------------------
CREATE TABLE public.audit_reports (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id    uuid NOT NULL,
  engagement_id      uuid NOT NULL,
  version            int  NOT NULL CHECK (version > 0),
  title              text NOT NULL CHECK (length(trim(title)) > 0),
  executive_summary  text,
  overall_conclusion text,
  distribution       text,
  status             text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','issued','superseded')),
  snapshot           jsonb,
  content_sha256     text,
  issued_by          uuid REFERENCES public.profiles(id),
  issued_at          timestamptz,
  created_by         uuid NOT NULL REFERENCES public.profiles(id),
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (engagement_id, version),
  FOREIGN KEY (engagement_id, organization_id) REFERENCES public.engagements(id, organization_id) ON DELETE CASCADE,
  CHECK (status = 'draft' OR (snapshot IS NOT NULL AND content_sha256 IS NOT NULL AND issued_by IS NOT NULL
                              AND length(trim(coalesce(overall_conclusion, ''))) > 0))
);
CREATE UNIQUE INDEX audit_reports_one_draft ON public.audit_reports (engagement_id) WHERE status = 'draft';
CREATE UNIQUE INDEX audit_reports_one_issued ON public.audit_reports (engagement_id) WHERE status = 'issued';

CREATE OR REPLACE FUNCTION public.guard_audit_report() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_role text; v_n int;
BEGIN
  v_role := coalesce(authz.ia_role(coalesce(NEW.engagement_id, OLD.engagement_id)), '');
  IF TG_OP = 'DELETE' THEN
    IF OLD.status <> 'draft' THEN
      RAISE EXCEPTION 'Rapport émis : conservé' USING ERRCODE = 'check_violation';
    END IF;
    RETURN OLD;
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.created_by IS DISTINCT FROM auth.uid() OR NEW.status <> 'draft' OR NEW.snapshot IS NOT NULL THEN
      RAISE EXCEPTION 'Rapport : créé en projet, au nom de l''utilisateur authentifié' USING ERRCODE = 'check_violation';
    END IF;
    IF v_role NOT IN ('partner','manager','in_charge') THEN
      RAISE EXCEPTION 'Rapport : encadrement de la mission' USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.status = 'superseded' OR (OLD.status = 'issued' AND NEW.status <> 'superseded') THEN
    RAISE EXCEPTION 'Rapport émis : non modifiable (une nouvelle version le remplacera)' USING ERRCODE = 'check_violation';
  END IF;
  IF OLD.status = 'issued' THEN
    IF (to_jsonb(NEW) - ARRAY['status','updated_at']) IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['status','updated_at'])
       OR coalesce(current_setting('kofinex.report_issue', true), 'off') <> 'on' THEN
      RAISE EXCEPTION 'Rapport émis : non modifiable' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
  END IF;
  IF v_role NOT IN ('partner','manager','in_charge') THEN
    RAISE EXCEPTION 'Rapport : encadrement de la mission' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF NEW.status = 'draft' AND NEW.snapshot IS NOT NULL THEN
    RAISE EXCEPTION 'Projet de rapport : le contenu figé n''existe qu''à l''émission' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.status = 'issued' THEN
    IF v_role <> 'partner' OR NEW.issued_by IS DISTINCT FROM auth.uid() THEN
      RAISE EXCEPTION 'Émission du rapport : associé (responsable de l''audit), en son nom' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF coalesce(current_setting('kofinex.report_issue', true), 'off') <> 'on' THEN
      RAISE EXCEPTION 'Émission : contenu assemblé par KOFINEX' USING ERRCODE = 'insufficient_privilege';
    END IF;
    SELECT count(*) INTO v_n FROM public.findings WHERE engagement_id = NEW.engagement_id AND status <> 'communicated';
    IF v_n > 0 THEN
      RAISE EXCEPTION 'Émission : % constat(s) non validé(s) ou non communiqué(s)', v_n USING ERRCODE = 'check_violation';
    END IF;
    IF (NEW.snapshot -> 'findings') IS NULL
       OR jsonb_array_length(NEW.snapshot -> 'findings') <> (SELECT count(*) FROM public.findings WHERE engagement_id = NEW.engagement_id) THEN
      RAISE EXCEPTION 'Émission : le contenu doit reprendre tous les constats de la mission' USING ERRCODE = 'check_violation';
    END IF;
    NEW.content_sha256 := encode(sha256(convert_to(NEW.snapshot::text, 'UTF8')), 'hex');
    NEW.issued_at := now();
    UPDATE public.audit_reports SET status = 'superseded'
     WHERE engagement_id = NEW.engagement_id AND status = 'issued' AND id <> NEW.id;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER audit_reports_guard BEFORE INSERT OR UPDATE OR DELETE ON public.audit_reports
  FOR EACH ROW EXECUTE FUNCTION public.guard_audit_report();

-- Émission de la mission d'audit interne : rapport émis requis
CREATE OR REPLACE FUNCTION public.guard_ia_issuance() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF OLD.status = 'reporting' AND NEW.status = 'issued' AND NEW.engagement_type = 'internal_audit'
     AND NOT EXISTS (SELECT 1 FROM public.audit_reports WHERE engagement_id = NEW.id AND status = 'issued') THEN
    RAISE EXCEPTION 'Audit interne : le rapport doit être émis avant la mission' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER engagements_check_ia_issuance BEFORE UPDATE ON public.engagements
  FOR EACH ROW EXECUTE FUNCTION public.guard_ia_issuance();

-- ---------------------------------------------------------------------
-- 6. Gel, type de mission, updated_at, rattachements
-- ---------------------------------------------------------------------
DO $$
DECLARE t text;
BEGIN
  -- le dossier émis fige constats, recommandations et rapports (pas les plans d'action ni leur suivi)
  FOREACH t IN ARRAY ARRAY['findings','recommendations'] LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE INSERT OR UPDATE OR DELETE ON public.%I
                    FOR EACH ROW EXECUTE FUNCTION public.guard_dossier_open()', t || '_dossier_open', t);
  END LOOP;
  FOREACH t IN ARRAY ARRAY['findings','audit_reports'] LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE INSERT ON public.%I FOR EACH ROW EXECUTE FUNCTION public.guard_ia_engagement()',
                   t || '_ia_type', t);
  END LOOP;
  FOREACH t IN ARRAY ARRAY['audit_plans','audit_plan_items','findings','action_plans','audit_reports'] LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.set_updated_at()',
                   t || '_updated_at', t);
  END LOOP;
END $$;

-- Rapport : la création et les modifications du projet sont permises tant que la mission n'est pas émise
CREATE OR REPLACE FUNCTION public.guard_report_open() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF (SELECT status FROM public.engagements WHERE id = coalesce(NEW.engagement_id, OLD.engagement_id)) IN ('issued','archived')
     AND coalesce(current_setting('kofinex.report_issue', true), 'off') <> 'on' THEN
    RAISE EXCEPTION 'Mission émise : rapports figés' USING ERRCODE = 'check_violation';
  END IF;
  RETURN coalesce(NEW, OLD);
END $$;
CREATE TRIGGER audit_reports_dossier_open BEFORE INSERT OR UPDATE OR DELETE ON public.audit_reports
  FOR EACH ROW EXECUTE FUNCTION public.guard_report_open();

ALTER TABLE public.evidence_links DROP CONSTRAINT evidence_links_object_type_check;
ALTER TABLE public.evidence_links ADD CONSTRAINT evidence_links_object_type_check CHECK (object_type IN
  ('workpaper','procedure','engagement_risk','fa_sample_item','fa_confirmation','fa_misstatement','fa_account_review',
   'finding','action_plan'));

CREATE INDEX findings_engagement_idx ON public.findings (engagement_id, status);
CREATE INDEX recommendations_finding_idx ON public.recommendations (finding_id);
CREATE INDEX audit_plan_items_plan_idx ON public.audit_plan_items (plan_id);

-- ---------------------------------------------------------------------
-- 7. RLS
-- ---------------------------------------------------------------------
-- Plan : lecture par les membres de l'organisation, écriture par ses propriétaires et administrateurs
ALTER TABLE public.audit_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_plan_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_plan_item_history ENABLE ROW LEVEL SECURITY;
CREATE POLICY audit_plans_select ON public.audit_plans FOR SELECT TO authenticated USING (authz.is_org_member(organization_id));
CREATE POLICY audit_plans_write ON public.audit_plans FOR ALL TO authenticated
  USING (authz.has_org_role(organization_id, ARRAY['owner','admin']))
  WITH CHECK (authz.has_org_role(organization_id, ARRAY['owner','admin']));
CREATE POLICY audit_plan_items_select ON public.audit_plan_items FOR SELECT TO authenticated
  USING (authz.is_org_member(organization_id));
CREATE POLICY audit_plan_items_write ON public.audit_plan_items FOR ALL TO authenticated
  USING (authz.has_org_role(organization_id, ARRAY['owner','admin']))
  WITH CHECK (authz.has_org_role(organization_id, ARRAY['owner','admin']));
CREATE POLICY audit_plan_item_history_select ON public.audit_plan_item_history FOR SELECT TO authenticated
  USING (authz.is_org_member(organization_id));
GRANT SELECT, INSERT, UPDATE, DELETE ON public.audit_plans, public.audit_plan_items TO authenticated;
GRANT SELECT ON public.audit_plan_item_history TO authenticated;

ALTER TABLE public.risk_rating_history ENABLE ROW LEVEL SECURITY;
CREATE POLICY risk_rating_history_select ON public.risk_rating_history FOR SELECT TO authenticated
  USING (authz.can_access_company(company_id) OR authz.audits_company(company_id));
GRANT SELECT ON public.risk_rating_history TO authenticated;

-- Lecture par l'audité : constats communiqués, leurs recommandations, plans d'action et suivi
CREATE OR REPLACE FUNCTION authz.auditee_sees_finding(p_finding uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT EXISTS (SELECT 1 FROM public.findings f
                  WHERE f.id = p_finding AND f.status = 'communicated' AND authz.ia_role(f.engagement_id) = 'auditee')
$$;
REVOKE ALL ON FUNCTION authz.auditee_sees_finding(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION authz.auditee_sees_finding(uuid) TO authenticated, service_role;

ALTER TABLE public.findings ENABLE ROW LEVEL SECURITY;
CREATE POLICY findings_select ON public.findings FOR SELECT TO authenticated
  USING (authz.can_read_dossier(engagement_id) OR (status = 'communicated' AND authz.ia_role(engagement_id) = 'auditee'));
CREATE POLICY findings_insert ON public.findings FOR INSERT TO authenticated
  WITH CHECK (authz.has_engagement_role(engagement_id, ARRAY['partner','manager','in_charge','staff']));
CREATE POLICY findings_update ON public.findings FOR UPDATE TO authenticated
  USING (authz.has_engagement_role(engagement_id, ARRAY['partner','manager','in_charge','staff'])
         OR (status = 'communicated' AND authz.ia_role(engagement_id) = 'auditee'))
  WITH CHECK (authz.has_engagement_role(engagement_id, ARRAY['partner','manager','in_charge','staff','auditee']));
CREATE POLICY findings_delete ON public.findings FOR DELETE TO authenticated
  USING (authz.has_engagement_role(engagement_id, ARRAY['partner','manager','in_charge','staff']));

ALTER TABLE public.recommendations ENABLE ROW LEVEL SECURITY;
CREATE POLICY recommendations_select ON public.recommendations FOR SELECT TO authenticated
  USING (authz.can_read_dossier(engagement_id) OR authz.auditee_sees_finding(finding_id));
CREATE POLICY recommendations_write ON public.recommendations FOR ALL TO authenticated
  USING (authz.has_engagement_role(engagement_id, ARRAY['partner','manager','in_charge','staff']))
  WITH CHECK (authz.has_engagement_role(engagement_id, ARRAY['partner','manager','in_charge','staff']));

ALTER TABLE public.action_plans ENABLE ROW LEVEL SECURITY;
CREATE POLICY action_plans_select ON public.action_plans FOR SELECT TO authenticated
  USING (authz.can_read_dossier(engagement_id) OR authz.ia_role(engagement_id) = 'auditee');
CREATE POLICY action_plans_insert ON public.action_plans FOR INSERT TO authenticated
  WITH CHECK (authz.has_engagement_role(engagement_id, ARRAY['partner','manager','in_charge','staff','auditee']));
CREATE POLICY action_plans_update ON public.action_plans FOR UPDATE TO authenticated
  USING (authz.has_engagement_role(engagement_id, ARRAY['partner','manager','in_charge','staff','auditee']))
  WITH CHECK (authz.has_engagement_role(engagement_id, ARRAY['partner','manager','in_charge','staff','auditee']));
CREATE POLICY action_plans_delete ON public.action_plans FOR DELETE TO authenticated
  USING (authz.has_engagement_role(engagement_id, ARRAY['partner','manager','in_charge','staff']));

ALTER TABLE public.action_plan_updates ENABLE ROW LEVEL SECURITY;
CREATE POLICY action_plan_updates_select ON public.action_plan_updates FOR SELECT TO authenticated
  USING (authz.can_read_dossier(engagement_id) OR authz.ia_role(engagement_id) = 'auditee');
CREATE POLICY action_plan_updates_insert ON public.action_plan_updates FOR INSERT TO authenticated
  WITH CHECK (authz.has_engagement_role(engagement_id, ARRAY['partner','manager','in_charge','staff','auditee']));

ALTER TABLE public.audit_reports ENABLE ROW LEVEL SECURITY;
CREATE POLICY audit_reports_select ON public.audit_reports FOR SELECT TO authenticated
  USING (authz.can_read_dossier(engagement_id) OR (status = 'issued' AND authz.ia_role(engagement_id) = 'auditee'));
CREATE POLICY audit_reports_write ON public.audit_reports FOR ALL TO authenticated
  USING (authz.has_engagement_role(engagement_id, ARRAY['partner','manager','in_charge']))
  WITH CHECK (authz.has_engagement_role(engagement_id, ARRAY['partner','manager','in_charge']));

GRANT SELECT, INSERT, UPDATE, DELETE ON public.findings, public.recommendations, public.action_plans, public.audit_reports
  TO authenticated;
GRANT SELECT, INSERT ON public.action_plan_updates TO authenticated;
GRANT ALL ON public.audit_plans, public.audit_plan_items, public.audit_plan_item_history, public.risk_rating_history,
  public.findings, public.recommendations, public.action_plans, public.action_plan_updates, public.audit_reports TO service_role;
