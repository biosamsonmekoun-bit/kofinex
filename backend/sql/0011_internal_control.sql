-- =====================================================================
-- KOFINEX — Migration 0011 : contrôle interne (lot 9)
-- Référentiels multi-cadres (métadonnées, exigences, correspondances), rôles du contrôle interne,
-- domaines et cycles, objectifs de contrôle, extension du registre partagé des processus et des
-- risques (aucun second registre), catalogue des contrôles, matrice risques-contrôles (N-N),
-- exécutions documentées et supervisées, tests de conception et d'efficacité (dans une mission),
-- évaluations figées à l'approbation, déficiences (findings.kind = 'ic_deficiency') et clôture,
-- prise en compte des tests par l'audit financier, historique.
-- Aucun contenu normatif n'est chargé : les composantes, principes, exigences et échelles sont des
-- données de méthodologies versionnées, importées par l'utilisateur avec leur source.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 0. Référentiels : nature, organisme, dates, document source ; nouveaux types d'éléments
-- ---------------------------------------------------------------------
ALTER TABLE public.methodology_versions
  ADD COLUMN framework_category text CHECK (framework_category IN
    ('ic_framework','professional_standard','legal_requirement','internal_methodology')),
  ADD COLUMN issuing_body    text,
  ADD COLUMN published_on    date,
  ADD COLUMN effective_from  date,
  ADD COLUMN source_document text;

ALTER TABLE public.methodology_items DROP CONSTRAINT methodology_items_item_type_check;
ALTER TABLE public.methodology_items ADD CONSTRAINT methodology_items_item_type_check CHECK (item_type IN
  ('assertion','cycle','risk_scale','procedure_template','ic_component','ic_principle','deficiency_scale','parameter',
   'finding_scale','ic_requirement','ic_criterion','control_level_scale'));

-- une version publiée est entièrement figée (toutes colonnes), seul l'archivage reste possible
CREATE OR REPLACE FUNCTION public.guard_methodology() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE v_status text;
BEGIN
  IF TG_TABLE_NAME = 'methodology_versions' THEN
    IF TG_OP = 'DELETE' THEN
      IF OLD.status <> 'draft' THEN RAISE EXCEPTION 'Méthodologie publiée : suppression impossible' USING ERRCODE = 'check_violation'; END IF;
      RETURN OLD;
    END IF;
    IF OLD.status = 'archived' THEN RAISE EXCEPTION 'Méthodologie archivée : non modifiable' USING ERRCODE = 'check_violation'; END IF;
    IF OLD.status = 'published' AND (NEW.status <> 'archived'
        OR (to_jsonb(NEW) - ARRAY['status','updated_at']) IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['status','updated_at'])) THEN
      RAISE EXCEPTION 'Méthodologie publiée : figée (seul l''archivage est possible)' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
  END IF;
  SELECT status INTO v_status FROM public.methodology_versions WHERE id = coalesce(NEW.version_id, OLD.version_id);
  IF v_status IS NOT NULL AND v_status <> 'draft' THEN
    RAISE EXCEPTION 'Méthodologie publiée : éléments figés' USING ERRCODE = 'check_violation';
  END IF;
  RETURN coalesce(NEW, OLD);
END $$;

-- Correspondances entre éléments de référentiels différents (déclarées et motivées, jamais déduites)
CREATE TABLE public.framework_mappings (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id  uuid REFERENCES public.organizations(id) ON DELETE CASCADE,   -- NULL : correspondance de la plateforme
  source_item_id   uuid NOT NULL REFERENCES public.methodology_items(id) ON DELETE CASCADE,
  target_item_id   uuid NOT NULL REFERENCES public.methodology_items(id) ON DELETE CASCADE,
  relation         text NOT NULL CHECK (relation IN ('equivalent','partial','related')),
  rationale        text NOT NULL CHECK (length(trim(rationale)) >= 3),
  source_reference text,
  created_by       uuid NOT NULL REFERENCES public.profiles(id),
  created_at       timestamptz NOT NULL DEFAULT now(),
  CHECK (source_item_id <> target_item_id)
);
CREATE UNIQUE INDEX framework_mappings_uniq ON public.framework_mappings
  (coalesce(organization_id, '00000000-0000-0000-0000-000000000000'::uuid), source_item_id, target_item_id);

CREATE OR REPLACE FUNCTION public.guard_framework_mapping() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE s record; t record;
BEGIN
  IF TG_OP = 'UPDATE' THEN
    RAISE EXCEPTION 'Correspondance : supprimez-la et déclarez-en une nouvelle' USING ERRCODE = 'check_violation';
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  IF NEW.created_by IS DISTINCT FROM auth.uid() THEN
    RAISE EXCEPTION 'Correspondance : déclarée au nom de l''utilisateur authentifié' USING ERRCODE = 'insufficient_privilege';
  END IF;
  SELECT i.item_type, i.version_id, v.organization_id, v.status INTO s
    FROM public.methodology_items i JOIN public.methodology_versions v ON v.id = i.version_id WHERE i.id = NEW.source_item_id;
  SELECT i.item_type, i.version_id, v.organization_id, v.status INTO t
    FROM public.methodology_items i JOIN public.methodology_versions v ON v.id = i.version_id WHERE i.id = NEW.target_item_id;
  IF s.version_id = t.version_id THEN
    RAISE EXCEPTION 'Correspondance : entre deux référentiels (ou versions) différents' USING ERRCODE = 'check_violation';
  END IF;
  IF s.item_type NOT IN ('ic_component','ic_principle','ic_requirement','ic_criterion')
     OR t.item_type NOT IN ('ic_component','ic_principle','ic_requirement','ic_criterion') THEN
    RAISE EXCEPTION 'Correspondance : composantes, principes, exigences ou critères uniquement' USING ERRCODE = 'check_violation';
  END IF;
  IF s.status <> 'published' OR t.status <> 'published' THEN
    RAISE EXCEPTION 'Correspondance : entre versions publiées' USING ERRCODE = 'check_violation';
  END IF;
  IF (s.organization_id IS NOT NULL AND s.organization_id IS DISTINCT FROM NEW.organization_id)
     OR (t.organization_id IS NOT NULL AND t.organization_id IS DISTINCT FROM NEW.organization_id) THEN
    RAISE EXCEPTION 'Correspondance : référentiel d''une autre organisation' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER framework_mappings_guard BEFORE INSERT OR UPDATE OR DELETE ON public.framework_mappings
  FOR EACH ROW EXECUTE FUNCTION public.guard_framework_mapping();

-- ---------------------------------------------------------------------
-- 1. Domaines et cycles (structure configurable par entité)
-- ---------------------------------------------------------------------
CREATE TABLE public.ic_domains (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  company_id      uuid NOT NULL,
  code            text NOT NULL CHECK (code ~ '^[A-Za-z0-9_.-]{1,40}$'),
  name            text NOT NULL CHECK (length(trim(name)) > 0),
  category        text NOT NULL DEFAULT 'custom' CHECK (category IN ('accounting_financial','organizational','custom')),
  template_code   text,                  -- modèle d'origine (catalogue KOFINEX), s'il y en a un
  cycle_code      text,                  -- cycle de la méthodologie d'audit, pour le rapprochement avec l'audit financier
  description     text,
  owner_name      text,
  owner_user_id   uuid REFERENCES public.profiles(id),
  is_active       boolean NOT NULL DEFAULT true,
  display_order   int NOT NULL DEFAULT 0,
  created_by      uuid REFERENCES public.profiles(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_id, code),
  UNIQUE (id, company_id),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------------
-- 2. Rôles du contrôle interne (par entité, éventuellement limités à un domaine)
-- ---------------------------------------------------------------------
CREATE TABLE public.ic_members (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  company_id      uuid NOT NULL,
  user_id         uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  role            text NOT NULL CHECK (role IN ('ic_manager','daf','domain_owner','process_owner','control_performer',
                                                'supervisor','observer')),
  domain_id       uuid,
  granted_by      uuid REFERENCES public.profiles(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (organization_id, user_id) REFERENCES public.organization_members(organization_id, user_id) ON DELETE CASCADE,
  FOREIGN KEY (domain_id, company_id) REFERENCES public.ic_domains(id, company_id) ON DELETE CASCADE,
  CHECK (role NOT IN ('domain_owner','process_owner') OR domain_id IS NOT NULL),
  CHECK (role NOT IN ('ic_manager','daf','observer') OR domain_id IS NULL)
);
CREATE UNIQUE INDEX ic_members_uniq ON public.ic_members
  (company_id, user_id, role, coalesce(domain_id, '00000000-0000-0000-0000-000000000000'::uuid));
CREATE INDEX ic_members_user_idx ON public.ic_members (user_id, company_id);

-- rôles applicables à un domaine (un rôle sans domaine vaut pour toute l'entité)
CREATE OR REPLACE FUNCTION authz.ic_roles(p_company uuid, p_domain uuid) RETURNS text[]
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT coalesce(array_agg(DISTINCT role), '{}') FROM public.ic_members
   WHERE company_id = p_company AND user_id = auth.uid() AND (domain_id IS NULL OR domain_id = p_domain)
$$;
-- pilotage du dispositif : administrateur de l'organisation, responsable du contrôle interne, DAF
CREATE OR REPLACE FUNCTION authz.ic_admin(p_company uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT coalesce(authz.company_role(p_company) = 'org_admin', false)
      OR EXISTS (SELECT 1 FROM public.ic_members WHERE company_id = p_company AND user_id = auth.uid()
                    AND role IN ('ic_manager','daf'))
$$;
-- gestion d'un domaine : pilotes, ou responsable de domaine / de processus sur ce domaine
CREATE OR REPLACE FUNCTION authz.ic_manages(p_company uuid, p_domain uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT authz.ic_admin(p_company)
      OR (p_domain IS NOT NULL AND EXISTS (SELECT 1 FROM public.ic_members WHERE company_id = p_company AND user_id = auth.uid()
                                              AND role IN ('domain_owner','process_owner') AND domain_id = p_domain))
$$;
-- lecture du dispositif : accès à l'entité, rôle de contrôle interne ou équipe d'une mission sur l'entité
CREATE OR REPLACE FUNCTION authz.ic_reader(p_company uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT authz.can_access_company(p_company)
      OR EXISTS (SELECT 1 FROM public.ic_members WHERE company_id = p_company AND user_id = auth.uid())
      OR authz.audits_company(p_company)
$$;
REVOKE ALL ON FUNCTION authz.ic_roles(uuid, uuid), authz.ic_admin(uuid), authz.ic_manages(uuid, uuid), authz.ic_reader(uuid)
  FROM PUBLIC;
GRANT EXECUTE ON FUNCTION authz.ic_roles(uuid, uuid), authz.ic_admin(uuid), authz.ic_manages(uuid, uuid), authz.ic_reader(uuid)
  TO authenticated, service_role;

-- ---------------------------------------------------------------------
-- 3. Registre partagé : processus et risques complétés (pas de second registre)
-- ---------------------------------------------------------------------
ALTER TABLE public.processes
  ADD COLUMN domain_id     uuid,
  ADD COLUMN owner_user_id uuid REFERENCES public.profiles(id),
  ADD FOREIGN KEY (domain_id, company_id) REFERENCES public.ic_domains(id, company_id);

-- un sous-processus appartient au domaine de son processus parent
CREATE OR REPLACE FUNCTION public.guard_process_domain() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_parent uuid;
BEGIN
  IF NEW.parent_id IS NOT NULL THEN
    SELECT domain_id INTO v_parent FROM public.processes WHERE id = NEW.parent_id;
    IF v_parent IS NOT NULL THEN
      IF NEW.domain_id IS NULL THEN NEW.domain_id := v_parent;
      ELSIF NEW.domain_id <> v_parent THEN
        RAISE EXCEPTION 'Sous-processus : même domaine que le processus parent' USING ERRCODE = 'check_violation';
      END IF;
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER processes_domain BEFORE INSERT OR UPDATE ON public.processes
  FOR EACH ROW EXECUTE FUNCTION public.guard_process_domain();

CREATE TABLE public.control_objectives (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  company_id      uuid NOT NULL,
  domain_id       uuid,
  process_id      uuid,
  code            text NOT NULL CHECK (length(trim(code)) > 0),
  statement       text NOT NULL CHECK (length(trim(statement)) > 0),
  assertion_codes text[] NOT NULL DEFAULT '{}',
  is_active       boolean NOT NULL DEFAULT true,
  created_by      uuid REFERENCES public.profiles(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_id, code),
  UNIQUE (id, company_id),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (domain_id, company_id) REFERENCES public.ic_domains(id, company_id),
  FOREIGN KEY (process_id, company_id) REFERENCES public.processes(id, company_id)
);

ALTER TABLE public.risks
  ADD COLUMN domain_id          uuid,
  ADD COLUMN objective_id       uuid,
  ADD COLUMN category           text,
  ADD COLUMN causes             text,
  ADD COLUMN consequences       text,
  ADD COLUMN owner_name         text,
  ADD COLUMN owner_user_id      uuid REFERENCES public.profiles(id),
  ADD COLUMN control_level_code text,          -- niveau de maîtrise (échelle de la méthodologie)
  ADD FOREIGN KEY (domain_id, company_id) REFERENCES public.ic_domains(id, company_id),
  ADD FOREIGN KEY (objective_id, company_id) REFERENCES public.control_objectives(id, company_id);
CREATE INDEX risks_domain_idx ON public.risks (company_id, domain_id);

-- domaine hérité du processus ; cotations et niveau de maîtrise conformes à la grille versionnée choisie
CREATE OR REPLACE FUNCTION public.guard_risk_rating() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_domain uuid; v_scale jsonb; v_levels jsonb;
BEGIN
  IF NEW.process_id IS NOT NULL THEN
    SELECT domain_id INTO v_domain FROM public.processes WHERE id = NEW.process_id;
    IF v_domain IS NOT NULL THEN
      IF NEW.domain_id IS NULL THEN NEW.domain_id := v_domain;
      ELSIF NEW.domain_id <> v_domain THEN
        RAISE EXCEPTION 'Risque : domaine différent de celui de son processus' USING ERRCODE = 'check_violation';
      END IF;
    END IF;
  END IF;
  IF (NEW.inherent_likelihood IS NULL) <> (NEW.inherent_impact IS NULL)
     OR (NEW.residual_likelihood IS NULL) <> (NEW.residual_impact IS NULL) THEN
    RAISE EXCEPTION 'Cotation incomplète : probabilité et impact vont ensemble' USING ERRCODE = 'check_violation';
  END IF;
  IF num_nonnulls(NEW.inherent_likelihood, NEW.residual_likelihood, NEW.control_level_code) > 0 THEN
    IF NEW.scale_version_id IS NULL THEN
      RAISE EXCEPTION 'Cotation : indiquez la méthodologie (version) dont la grille est utilisée' USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.inherent_likelihood IS NOT NULL OR NEW.residual_likelihood IS NOT NULL THEN
      SELECT content INTO v_scale FROM public.methodology_items
       WHERE version_id = NEW.scale_version_id AND item_type = 'risk_scale' LIMIT 1;
      IF v_scale IS NULL THEN
        RAISE EXCEPTION 'Cotation : la méthodologie choisie n''a pas de grille de cotation' USING ERRCODE = 'check_violation';
      END IF;
      IF (NEW.inherent_likelihood IS NOT NULL AND (
            NOT EXISTS (SELECT 1 FROM jsonb_array_elements(v_scale -> 'likelihood') l WHERE (l ->> 'score')::int = NEW.inherent_likelihood)
         OR NOT EXISTS (SELECT 1 FROM jsonb_array_elements(v_scale -> 'impact') l WHERE (l ->> 'score')::int = NEW.inherent_impact)))
         OR (NEW.residual_likelihood IS NOT NULL AND (
            NOT EXISTS (SELECT 1 FROM jsonb_array_elements(v_scale -> 'likelihood') l WHERE (l ->> 'score')::int = NEW.residual_likelihood)
         OR NOT EXISTS (SELECT 1 FROM jsonb_array_elements(v_scale -> 'impact') l WHERE (l ->> 'score')::int = NEW.residual_impact))) THEN
        RAISE EXCEPTION 'Cotation hors de la grille de la méthodologie' USING ERRCODE = 'check_violation';
      END IF;
    END IF;
    IF NEW.control_level_code IS NOT NULL THEN
      SELECT content -> 'levels' INTO v_levels FROM public.methodology_items
       WHERE version_id = NEW.scale_version_id AND item_type = 'control_level_scale' LIMIT 1;
      IF v_levels IS NULL OR NOT EXISTS (SELECT 1 FROM jsonb_array_elements(v_levels) l WHERE l ->> 'code' = NEW.control_level_code) THEN
        RAISE EXCEPTION 'Niveau de maîtrise « % » absent de l''échelle de la méthodologie', NEW.control_level_code
          USING ERRCODE = 'check_violation';
      END IF;
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER risks_guard_rating BEFORE INSERT OR UPDATE ON public.risks
  FOR EACH ROW EXECUTE FUNCTION public.guard_risk_rating();

ALTER TABLE public.risk_rating_history ADD COLUMN control_level_code text;
CREATE OR REPLACE FUNCTION public.log_risk_rating() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF TG_OP = 'INSERT' OR (NEW.scale_version_id, NEW.inherent_likelihood, NEW.inherent_impact, NEW.residual_likelihood,
                          NEW.residual_impact, NEW.control_level_code)
       IS DISTINCT FROM (OLD.scale_version_id, OLD.inherent_likelihood, OLD.inherent_impact, OLD.residual_likelihood,
                         OLD.residual_impact, OLD.control_level_code) THEN
    INSERT INTO public.risk_rating_history (organization_id, company_id, risk_id, scale_version_id, inherent_likelihood,
                                            inherent_impact, residual_likelihood, residual_impact, control_level_code, changed_by)
    VALUES (NEW.organization_id, NEW.company_id, NEW.id, NEW.scale_version_id, NEW.inherent_likelihood, NEW.inherent_impact,
            NEW.residual_likelihood, NEW.residual_impact, NEW.control_level_code, auth.uid());
  END IF;
  RETURN NULL;
END $$;

-- ---------------------------------------------------------------------
-- 4. Catalogue des contrôles et matrice risques-contrôles
-- ---------------------------------------------------------------------
CREATE TABLE public.controls (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id    uuid NOT NULL,
  company_id         uuid NOT NULL,
  domain_id          uuid,
  process_id         uuid,
  objective_id       uuid,
  code               text NOT NULL CHECK (length(trim(code)) > 0),
  title              text NOT NULL CHECK (length(trim(title)) > 0),
  description        text,
  control_objective  text,
  existence          text NOT NULL DEFAULT 'existing'
                       CHECK (existence IN ('existing','expected','not_formalized','absent')),
  owner_name         text NOT NULL CHECK (length(trim(owner_name)) > 0),     -- responsable identifiable
  owner_user_id      uuid REFERENCES public.profiles(id),
  performer_name     text,
  performer_user_id  uuid REFERENCES public.profiles(id),
  supervisor_name    text,
  supervisor_user_id uuid REFERENCES public.profiles(id),
  frequency          text CHECK (frequency IN ('on_occurrence','daily','weekly','monthly','quarterly','semiannual','annual','ad_hoc')),
  nature             text CHECK (nature IN ('preventive','detective')),
  automation         text CHECK (automation IN ('manual','automated','semi_automated')),
  timing             text CHECK (timing IN ('permanent','periodic')),
  execution_mode     text,
  expected_evidence  text,
  procedure_text     text,              -- procédure de contrôle documentée (modalités d'exécution)
  success_criteria   text,
  is_key             boolean NOT NULL DEFAULT false,
  implemented_on     date,
  operational_status text NOT NULL DEFAULT 'active' CHECK (operational_status IN ('active','suspended','retired')),
  version            int NOT NULL DEFAULT 1,
  created_by         uuid REFERENCES public.profiles(id),
  updated_by         uuid REFERENCES public.profiles(id),
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_id, code),
  UNIQUE (id, company_id),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (domain_id, company_id) REFERENCES public.ic_domains(id, company_id),
  FOREIGN KEY (process_id, company_id) REFERENCES public.processes(id, company_id),
  FOREIGN KEY (objective_id, company_id) REFERENCES public.control_objectives(id, company_id),
  -- un contrôle existant est caractérisé (fréquence, nature, mode)
  CHECK (existence <> 'existing' OR (frequency IS NOT NULL AND nature IS NOT NULL AND automation IS NOT NULL)),
  CHECK (performer_user_id IS NULL OR supervisor_user_id IS NULL OR performer_user_id <> supervisor_user_id)
);
CREATE INDEX controls_domain_idx ON public.controls (company_id, domain_id, process_id);

CREATE OR REPLACE FUNCTION public.guard_control() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_domain uuid;
BEGIN
  IF NEW.process_id IS NOT NULL THEN
    SELECT domain_id INTO v_domain FROM public.processes WHERE id = NEW.process_id;
    IF v_domain IS NOT NULL THEN
      IF NEW.domain_id IS NULL THEN NEW.domain_id := v_domain;
      ELSIF NEW.domain_id <> v_domain THEN
        RAISE EXCEPTION 'Contrôle : domaine différent de celui de son processus' USING ERRCODE = 'check_violation';
      END IF;
    END IF;
  END IF;
  NEW.updated_by := auth.uid();
  IF TG_OP = 'INSERT' THEN
    NEW.version := 1;
    NEW.created_by := auth.uid();
  ELSIF (to_jsonb(NEW) - ARRAY['version','updated_by','updated_at']) IS DISTINCT FROM
        (to_jsonb(OLD) - ARRAY['version','updated_by','updated_at']) THEN
    NEW.version := OLD.version + 1;
  END IF;
  IF TG_OP = 'UPDATE' AND NEW.code <> OLD.code AND EXISTS (SELECT 1 FROM public.control_tests WHERE control_id = OLD.id) THEN
    RAISE EXCEPTION 'Contrôle testé : code figé' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER controls_guard BEFORE INSERT OR UPDATE ON public.controls
  FOR EACH ROW EXECUTE FUNCTION public.guard_control();

CREATE TABLE public.control_risks (
  organization_id uuid NOT NULL,
  company_id      uuid NOT NULL,
  control_id      uuid NOT NULL,
  risk_id         uuid NOT NULL,
  coverage        text NOT NULL DEFAULT 'full' CHECK (coverage IN ('full','partial')),
  assertion_codes text[] NOT NULL DEFAULT '{}',
  rationale       text,
  created_by      uuid REFERENCES public.profiles(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (control_id, risk_id),
  FOREIGN KEY (control_id, company_id) REFERENCES public.controls(id, company_id) ON DELETE CASCADE,
  FOREIGN KEY (risk_id, company_id) REFERENCES public.risks(id, company_id) ON DELETE CASCADE
);
CREATE INDEX control_risks_risk_idx ON public.control_risks (risk_id);

-- rattachement aux composantes, principes, exigences ou critères d'un ou plusieurs référentiels
CREATE TABLE public.ic_framework_links (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  company_id      uuid NOT NULL,
  object_type     text NOT NULL CHECK (object_type IN ('control','risk','objective','domain')),
  object_id       uuid NOT NULL,
  item_id         uuid NOT NULL REFERENCES public.methodology_items(id),
  created_by      uuid REFERENCES public.profiles(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (object_type, object_id, item_id),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE
);
CREATE INDEX ic_framework_links_item_idx ON public.ic_framework_links (item_id);

-- domaine d'un objet du dispositif (pour les droits)
CREATE OR REPLACE FUNCTION authz.ic_object_domain(p_type text, p_id uuid) RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT CASE p_type
    WHEN 'control'   THEN (SELECT domain_id FROM public.controls WHERE id = p_id)
    WHEN 'risk'      THEN (SELECT domain_id FROM public.risks WHERE id = p_id)
    WHEN 'objective' THEN (SELECT domain_id FROM public.control_objectives WHERE id = p_id)
    WHEN 'domain'    THEN p_id END
$$;
REVOKE ALL ON FUNCTION authz.ic_object_domain(text, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION authz.ic_object_domain(text, uuid) TO authenticated, service_role;

CREATE OR REPLACE FUNCTION public.guard_ic_framework_link() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v record; v_company uuid;
BEGIN
  IF TG_OP = 'UPDATE' THEN RAISE EXCEPTION 'Rattachement : supprimez-le et recréez-le' USING ERRCODE = 'check_violation'; END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  SELECT i.item_type, ver.organization_id, ver.status INTO v
    FROM public.methodology_items i JOIN public.methodology_versions ver ON ver.id = i.version_id WHERE i.id = NEW.item_id;
  IF v.item_type NOT IN ('ic_component','ic_principle','ic_requirement','ic_criterion') THEN
    RAISE EXCEPTION 'Rattachement : composante, principe, exigence ou critère d''un référentiel' USING ERRCODE = 'check_violation';
  END IF;
  IF v.status <> 'published' THEN
    RAISE EXCEPTION 'Rattachement : à une version publiée du référentiel' USING ERRCODE = 'check_violation';
  END IF;
  IF v.organization_id IS NOT NULL AND v.organization_id <> NEW.organization_id THEN
    RAISE EXCEPTION 'Rattachement : référentiel d''une autre organisation' USING ERRCODE = 'check_violation';
  END IF;
  v_company := CASE NEW.object_type
    WHEN 'control'   THEN (SELECT company_id FROM public.controls WHERE id = NEW.object_id)
    WHEN 'risk'      THEN (SELECT company_id FROM public.risks WHERE id = NEW.object_id)
    WHEN 'objective' THEN (SELECT company_id FROM public.control_objectives WHERE id = NEW.object_id)
    WHEN 'domain'    THEN (SELECT company_id FROM public.ic_domains WHERE id = NEW.object_id) END;
  IF v_company IS DISTINCT FROM NEW.company_id THEN
    RAISE EXCEPTION 'Rattachement : objet hors de l''entité' USING ERRCODE = 'check_violation';
  END IF;
  NEW.created_by := auth.uid();
  RETURN NEW;
END $$;
CREATE TRIGGER ic_framework_links_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ic_framework_links
  FOR EACH ROW EXECUTE FUNCTION public.guard_ic_framework_link();

-- ---------------------------------------------------------------------
-- 5. Exécutions des contrôles (documentées par l'exécutant, supervisées par une autre personne)
-- ---------------------------------------------------------------------
CREATE TABLE public.control_executions (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id     uuid NOT NULL,
  company_id          uuid NOT NULL,
  control_id          uuid NOT NULL,
  occurrence_label    text NOT NULL CHECK (length(trim(occurrence_label)) > 0),
  occurrence_date     date NOT NULL,
  outcome             text NOT NULL CHECK (outcome IN ('performed','performed_with_exceptions','not_performed')),
  comment             text,
  exceptions          text,
  performed_by        uuid NOT NULL REFERENCES public.profiles(id),
  performed_at        timestamptz NOT NULL DEFAULT now(),
  evidence_path       text,
  evidence_filename   text,
  evidence_mime       text,
  evidence_size       bigint,
  evidence_sha256     text CHECK (evidence_sha256 IS NULL OR evidence_sha256 ~ '^[0-9a-f]{64}$'),
  supervision_status  text NOT NULL DEFAULT 'pending' CHECK (supervision_status IN ('pending','approved','rejected')),
  supervised_by       uuid REFERENCES public.profiles(id),
  supervised_at       timestamptz,
  supervision_comment text,
  created_at          timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id, company_id),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (control_id, company_id) REFERENCES public.controls(id, company_id),
  CHECK (outcome <> 'performed_with_exceptions' OR length(trim(coalesce(exceptions, ''))) > 0),
  CHECK ((evidence_path IS NULL) = (evidence_sha256 IS NULL)),
  CHECK (supervision_status = 'pending' OR (supervised_by IS NOT NULL AND supervised_at IS NOT NULL)),
  CHECK (supervision_status <> 'rejected' OR length(trim(coalesce(supervision_comment, ''))) >= 3)
);
CREATE INDEX control_executions_idx ON public.control_executions (control_id, occurrence_date);

CREATE OR REPLACE FUNCTION public.guard_control_execution() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE c record;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Exécution d''un contrôle : conservée (trace de l''exécution)' USING ERRCODE = 'check_violation';
  END IF;
  SELECT company_id, domain_id, performer_user_id, supervisor_user_id INTO c FROM public.controls WHERE id = NEW.control_id;
  IF TG_OP = 'INSERT' THEN
    IF auth.uid() IS NULL OR NEW.performed_by IS DISTINCT FROM auth.uid() THEN
      RAISE EXCEPTION 'Exécution : documentée au nom de l''utilisateur authentifié' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NOT (c.performer_user_id = auth.uid() OR 'control_performer' = ANY (authz.ic_roles(c.company_id, c.domain_id))
            OR authz.ic_manages(c.company_id, c.domain_id)) THEN
      RAISE EXCEPTION 'Exécution : exécutant du contrôle ou responsable du domaine' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.supervision_status <> 'pending' OR NEW.supervised_by IS NOT NULL THEN
      RAISE EXCEPTION 'Exécution : supervisée après sa documentation' USING ERRCODE = 'check_violation';
    END IF;
    NEW.performed_at := now();
    RETURN NEW;
  END IF;
  IF OLD.supervision_status <> 'pending' THEN
    RAISE EXCEPTION 'Exécution supervisée : figée' USING ERRCODE = 'check_violation';
  END IF;
  IF (to_jsonb(NEW) - ARRAY['supervision_status','supervised_by','supervised_at','supervision_comment'])
     IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['supervision_status','supervised_by','supervised_at','supervision_comment']) THEN
    RAISE EXCEPTION 'Exécution : seule la supervision peut être enregistrée' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.supervision_status <> 'pending' THEN
    IF NEW.supervised_by IS DISTINCT FROM auth.uid() THEN
      RAISE EXCEPTION 'Supervision : au nom de l''utilisateur authentifié' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.supervised_by = OLD.performed_by THEN
      RAISE EXCEPTION 'Supervision : par une autre personne que l''exécutant' USING ERRCODE = 'check_violation';
    END IF;
    IF NOT (c.supervisor_user_id = auth.uid() OR 'supervisor' = ANY (authz.ic_roles(c.company_id, c.domain_id))
            OR authz.ic_manages(c.company_id, c.domain_id)) THEN
      RAISE EXCEPTION 'Supervision : superviseur du contrôle ou responsable du domaine' USING ERRCODE = 'insufficient_privilege';
    END IF;
    NEW.supervised_at := now();
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER control_executions_guard BEFORE INSERT OR UPDATE OR DELETE ON public.control_executions
  FOR EACH ROW EXECUTE FUNCTION public.guard_control_execution();

-- ---------------------------------------------------------------------
-- 6. Tests de contrôles (dans une mission : préparateur, réviseur, période, population, éléments)
-- ---------------------------------------------------------------------
CREATE TABLE public.control_tests (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id       uuid NOT NULL,
  engagement_id         uuid NOT NULL,
  company_id            uuid NOT NULL,
  control_id            uuid NOT NULL,
  risk_id               uuid,                 -- risque visé (registre)
  procedure_id          uuid,                 -- étape du programme de travail
  workpaper_id          uuid,
  reference             text NOT NULL CHECK (length(trim(reference)) > 0),
  test_type             text NOT NULL CHECK (test_type IN ('design','operating')),
  test_methods          text[] NOT NULL CHECK (cardinality(test_methods) >= 1 AND test_methods <@ ARRAY['document_review',
                          'observation','inquiry','inspection','reconciliation','recalculation','reperformance','data_analysis']),
  objective             text,
  test_procedure        text NOT NULL CHECK (length(trim(test_procedure)) > 0),
  responsible_user_id   uuid REFERENCES public.profiles(id),
  period_start          date,
  period_end            date,
  population_description text,
  population_size       int CHECK (population_size IS NULL OR population_size >= 0),
  population_source     text CHECK (population_source IN ('manual','executions','file')),
  selection_method      text CHECK (selection_method IN ('all','random','systematic','judgmental')),
  sample_size           int,
  sample_size_basis     text,                -- règle de la méthodologie ou jugement motivé (jamais fixé par KOFINEX)
  selection_params      jsonb NOT NULL DEFAULT '{}'::jsonb,
  acceptance_criteria   text,
  tolerable_exceptions  int CHECK (tolerable_exceptions IS NULL OR tolerable_exceptions >= 0),
  expected_result       text,
  design_answers        jsonb NOT NULL DEFAULT '{}'::jsonb,
  operating_answers     jsonb NOT NULL DEFAULT '{}'::jsonb,
  results_summary       text,
  exceptions_summary    text,
  conclusion            text CHECK (conclusion IN ('effective','partially_effective','ineffective','not_tested','not_applicable')),
  conclusion_rationale  text,
  status                text NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','in_progress','prepared','reviewed')),
  prepared_by           uuid REFERENCES public.profiles(id),
  prepared_at           timestamptz,
  reviewed_by           uuid REFERENCES public.profiles(id),
  reviewed_at           timestamptz,
  reopen_reason         text,
  created_by            uuid NOT NULL REFERENCES public.profiles(id),
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),
  UNIQUE (engagement_id, reference),
  UNIQUE (id, engagement_id),
  FOREIGN KEY (engagement_id, organization_id) REFERENCES public.engagements(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (engagement_id, company_id) REFERENCES public.engagements(id, company_id),
  FOREIGN KEY (control_id, company_id) REFERENCES public.controls(id, company_id),
  FOREIGN KEY (risk_id, company_id) REFERENCES public.risks(id, company_id),
  FOREIGN KEY (procedure_id, engagement_id) REFERENCES public.procedures(id, engagement_id) ON DELETE SET NULL (procedure_id),
  FOREIGN KEY (workpaper_id, engagement_id) REFERENCES public.workpapers(id, engagement_id) ON DELETE SET NULL (workpaper_id),
  CHECK (period_end IS NULL OR period_start IS NULL OR period_end >= period_start),
  CHECK (sample_size IS NULL OR (sample_size >= 1 AND length(trim(coalesce(sample_size_basis, ''))) > 0)),
  CHECK (status NOT IN ('prepared','reviewed') OR (conclusion IS NOT NULL AND prepared_by IS NOT NULL)),
  CHECK (status <> 'reviewed' OR (reviewed_by IS NOT NULL AND reviewed_by <> prepared_by))
);
CREATE INDEX control_tests_control_idx ON public.control_tests (company_id, control_id, status, reviewed_at);

CREATE TABLE public.control_test_items (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id       uuid NOT NULL,
  engagement_id         uuid NOT NULL,
  test_id               uuid NOT NULL,
  item_ref              text NOT NULL CHECK (length(trim(item_ref)) > 0),
  description           text,
  item_date             date,
  amount                numeric(20,2),
  execution_id          uuid REFERENCES public.control_executions(id),
  selection_order       int,
  result                text NOT NULL DEFAULT 'pending' CHECK (result IN ('pending','compliant','exception','not_applicable')),
  exception_description text,
  na_reason             text,
  tested_by             uuid REFERENCES public.profiles(id),
  tested_at             timestamptz,
  UNIQUE (test_id, item_ref),
  UNIQUE (id, engagement_id),
  FOREIGN KEY (test_id, engagement_id) REFERENCES public.control_tests(id, engagement_id) ON DELETE CASCADE,
  CHECK (result <> 'exception' OR length(trim(coalesce(exception_description, ''))) > 0),
  CHECK (result <> 'not_applicable' OR length(trim(coalesce(na_reason, ''))) > 0)
);

-- critères d'évaluation (6.2 conception, 6.3 efficacité opérationnelle) : réponses yes | no | partial | na
CREATE OR REPLACE FUNCTION public.ic_criteria(p_type text) RETURNS text[]
LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE p_type
    WHEN 'design' THEN ARRAY['responds_to_risk','well_defined','owner_assigned','frequency_adequate','documented',
                             'independent','prevents_or_detects']
    ELSE ARRAY['performed','right_person','right_frequency','evidence_produced','supervised','anomalies_handled'] END
$$;

CREATE OR REPLACE FUNCTION public.ic_answers_valid(p_answers jsonb, p_type text) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
  SELECT jsonb_typeof(p_answers) = 'object' AND NOT EXISTS (
    SELECT 1 FROM jsonb_each(p_answers) e
     WHERE NOT (e.key = ANY (public.ic_criteria(p_type)))
        OR jsonb_typeof(e.value) <> 'object'
        OR coalesce(e.value ->> 'answer', '') NOT IN ('yes','no','partial','na'))
$$;

CREATE OR REPLACE FUNCTION public.guard_control_test() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_role text; v_prep_role text; v_pending int; v_exc int; v_items int; v_answers jsonb; v_changed boolean;
BEGIN
  v_role := coalesce(authz.ia_role(coalesce(NEW.engagement_id, OLD.engagement_id)), '');
  IF TG_OP = 'DELETE' THEN
    IF OLD.status <> 'planned' AND OLD.status <> 'in_progress' THEN
      RAISE EXCEPTION 'Test préparé ou revu : conservé' USING ERRCODE = 'check_violation';
    END IF;
    IF v_role NOT IN ('partner','manager','in_charge') THEN
      RAISE EXCEPTION 'Suppression d''un test : encadrement de la mission' USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN OLD;
  END IF;
  IF v_role NOT IN ('partner','manager','in_charge','staff') THEN
    RAISE EXCEPTION 'Tests de contrôles : équipe de la mission' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF NOT public.ic_answers_valid(NEW.design_answers, 'design') OR NOT public.ic_answers_valid(NEW.operating_answers, 'operating') THEN
    RAISE EXCEPTION 'Réponses aux critères d''évaluation invalides' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.responsible_user_id IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM public.engagement_members WHERE engagement_id = NEW.engagement_id AND user_id = NEW.responsible_user_id
          AND role IN ('partner','manager','in_charge','staff')) THEN
    RAISE EXCEPTION 'Responsable du test hors de l''équipe de la mission' USING ERRCODE = 'check_violation';
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.created_by IS DISTINCT FROM auth.uid() OR NEW.status <> 'planned' OR NEW.conclusion IS NOT NULL THEN
      RAISE EXCEPTION 'Test : créé « planifié », sans conclusion, au nom de l''utilisateur authentifié' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
  END IF;

  v_changed := (to_jsonb(NEW) - ARRAY['status','prepared_by','prepared_at','reviewed_by','reviewed_at','reopen_reason','updated_at'])
               IS DISTINCT FROM
               (to_jsonb(OLD) - ARRAY['status','prepared_by','prepared_at','reviewed_by','reviewed_at','reopen_reason','updated_at']);
  IF OLD.status = 'reviewed' THEN
    IF NEW.status <> 'in_progress' OR v_changed THEN
      RAISE EXCEPTION 'Test revu : figé (réouverture motivée par le manager ou l''associé)' USING ERRCODE = 'check_violation';
    END IF;
    IF v_role NOT IN ('partner','manager') OR length(trim(coalesce(NEW.reopen_reason, ''))) < 3 THEN
      RAISE EXCEPTION 'Réouverture d''un test revu : manager ou associé, motif requis' USING ERRCODE = 'check_violation';
    END IF;
    NEW.reviewed_by := NULL; NEW.reviewed_at := NULL; NEW.prepared_by := NULL; NEW.prepared_at := NULL;
    RETURN NEW;
  END IF;
  IF OLD.status = 'prepared' AND v_changed THEN
    RAISE EXCEPTION 'Test préparé : contenu figé (renvoyez-le en cours pour le modifier)' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.status IS NOT DISTINCT FROM OLD.status THEN
    RETURN NEW;
  END IF;

  IF (OLD.status, NEW.status) = ('planned','in_progress') THEN
    RETURN NEW;
  ELSIF NEW.status = 'prepared' AND OLD.status IN ('planned','in_progress') THEN
    IF NEW.prepared_by IS DISTINCT FROM auth.uid() THEN
      RAISE EXCEPTION 'Préparation : au nom de l''utilisateur authentifié' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.conclusion IS NULL OR length(trim(coalesce(NEW.conclusion_rationale, ''))) < 3 THEN
      RAISE EXCEPTION 'Préparation : conclusion et justification requises' USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.conclusion IN ('effective','partially_effective','ineffective') THEN
      IF NEW.test_type = 'operating' AND (NEW.period_start IS NULL OR NEW.period_end IS NULL) THEN
        RAISE EXCEPTION 'Test d''efficacité : période examinée requise' USING ERRCODE = 'check_violation';
      END IF;
      SELECT count(*), count(*) FILTER (WHERE result = 'pending'), count(*) FILTER (WHERE result = 'exception')
        INTO v_items, v_pending, v_exc FROM public.control_test_items WHERE test_id = NEW.id;
      IF v_pending > 0 THEN
        RAISE EXCEPTION 'Préparation : % élément(s) sélectionné(s) non testé(s)', v_pending USING ERRCODE = 'check_violation';
      END IF;
      IF NEW.sample_size IS NOT NULL AND v_items < NEW.sample_size THEN
        RAISE EXCEPTION 'Préparation : % élément(s) testé(s) pour un échantillon de %', v_items, NEW.sample_size
          USING ERRCODE = 'check_violation';
      END IF;
      IF NEW.conclusion = 'effective' THEN
        IF v_exc > coalesce(NEW.tolerable_exceptions, 0) THEN
          RAISE EXCEPTION 'Conclusion « efficace » : % exception(s) pour % tolérée(s) par les critères d''acceptation',
            v_exc, coalesce(NEW.tolerable_exceptions, 0) USING ERRCODE = 'check_violation';
        END IF;
        v_answers := CASE NEW.test_type WHEN 'design' THEN NEW.design_answers ELSE NEW.operating_answers END;
        IF EXISTS (SELECT 1 FROM unnest(public.ic_criteria(NEW.test_type)) k WHERE NOT (v_answers ? k))
           OR EXISTS (SELECT 1 FROM jsonb_each(v_answers) e WHERE e.value ->> 'answer' IN ('no','partial')) THEN
          RAISE EXCEPTION 'Conclusion « efficace » : tous les critères doivent être évalués, sans réponse négative ou partielle'
            USING ERRCODE = 'check_violation';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM public.evidence_links l WHERE l.engagement_id = NEW.engagement_id AND (
                         (l.object_type = 'control_test' AND l.object_id = NEW.id)
                      OR (l.object_type = 'control_test_item' AND l.object_id IN
                            (SELECT id FROM public.control_test_items WHERE test_id = NEW.id)))) THEN
          RAISE EXCEPTION 'Conclusion « efficace » : au moins un élément probant rattaché au test' USING ERRCODE = 'check_violation';
        END IF;
      END IF;
    END IF;
    NEW.prepared_at := now();
  ELSIF (OLD.status, NEW.status) = ('prepared','reviewed') THEN
    IF NEW.reviewed_by IS DISTINCT FROM auth.uid() THEN
      RAISE EXCEPTION 'Revue : au nom de l''utilisateur authentifié' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.reviewed_by = OLD.prepared_by THEN
      RAISE EXCEPTION 'Revue : par une autre personne que le préparateur' USING ERRCODE = 'check_violation';
    END IF;
    SELECT role INTO v_prep_role FROM public.engagement_members WHERE engagement_id = NEW.engagement_id AND user_id = OLD.prepared_by;
    IF v_role NOT IN ('partner','manager','in_charge') OR (v_role = 'in_charge' AND coalesce(v_prep_role, '') <> 'staff') THEN
      RAISE EXCEPTION 'Revue : rôle supérieur à celui du préparateur' USING ERRCODE = 'insufficient_privilege';
    END IF;
    NEW.reviewed_at := now(); NEW.reopen_reason := NULL;
  ELSIF (OLD.status, NEW.status) = ('prepared','in_progress') THEN
    IF NOT (OLD.prepared_by = auth.uid() OR v_role IN ('partner','manager','in_charge')) THEN
      RAISE EXCEPTION 'Renvoi en cours : préparateur ou encadrement' USING ERRCODE = 'insufficient_privilege';
    END IF;
    NEW.prepared_by := NULL; NEW.prepared_at := NULL;
  ELSE
    RAISE EXCEPTION 'Test : transition interdite % → %', OLD.status, NEW.status USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER control_tests_guard BEFORE INSERT OR UPDATE OR DELETE ON public.control_tests
  FOR EACH ROW EXECUTE FUNCTION public.guard_control_test();

CREATE OR REPLACE FUNCTION public.guard_control_test_item() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE t record; x record;
BEGIN
  SELECT status, control_id, period_start, period_end INTO t FROM public.control_tests
   WHERE id = coalesce(NEW.test_id, OLD.test_id);
  IF t.status NOT IN ('planned','in_progress') THEN
    RAISE EXCEPTION 'Test préparé ou revu : éléments figés' USING ERRCODE = 'check_violation';
  END IF;
  IF coalesce(authz.ia_role(coalesce(NEW.engagement_id, OLD.engagement_id)), '') NOT IN ('partner','manager','in_charge','staff') THEN
    RAISE EXCEPTION 'Éléments testés : équipe de la mission' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  IF NEW.execution_id IS NOT NULL THEN
    SELECT control_id, occurrence_date INTO x FROM public.control_executions WHERE id = NEW.execution_id;
    IF x.control_id IS DISTINCT FROM t.control_id THEN
      RAISE EXCEPTION 'Élément : exécution d''un autre contrôle' USING ERRCODE = 'check_violation';
    END IF;
    IF (t.period_start IS NOT NULL AND x.occurrence_date < t.period_start) OR (t.period_end IS NOT NULL AND x.occurrence_date > t.period_end) THEN
      RAISE EXCEPTION 'Élément : exécution hors de la période testée' USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  IF TG_OP = 'INSERT' OR NEW.result IS DISTINCT FROM OLD.result OR NEW.exception_description IS DISTINCT FROM OLD.exception_description THEN
    IF NEW.result = 'pending' THEN NEW.tested_by := NULL; NEW.tested_at := NULL;
    ELSE NEW.tested_by := auth.uid(); NEW.tested_at := now(); END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER control_test_items_guard BEFORE INSERT OR UPDATE OR DELETE ON public.control_test_items
  FOR EACH ROW EXECUTE FUNCTION public.guard_control_test_item();

-- Éléments probants des tests : réutilise evidence_items / evidence_links du socle ; figés avec le test
ALTER TABLE public.evidence_links DROP CONSTRAINT evidence_links_object_type_check;
ALTER TABLE public.evidence_links ADD CONSTRAINT evidence_links_object_type_check CHECK (object_type IN
  ('workpaper','procedure','engagement_risk','fa_sample_item','fa_confirmation','fa_misstatement','fa_account_review',
   'finding','action_plan','control_test','control_test_item','ic_assessment'));
ALTER TABLE public.review_notes DROP CONSTRAINT review_notes_object_type_check;
ALTER TABLE public.review_notes ADD CONSTRAINT review_notes_object_type_check CHECK (object_type IN
  ('engagement','workpaper','procedure','engagement_risk','control_test','ic_assessment'));

CREATE OR REPLACE FUNCTION public.guard_ic_evidence_link() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_type text := coalesce(NEW.object_type, OLD.object_type); v_obj uuid := coalesce(NEW.object_id, OLD.object_id);
        v_status text;
BEGIN
  IF v_type = 'control_test' THEN
    SELECT status INTO v_status FROM public.control_tests WHERE id = v_obj;
  ELSIF v_type = 'control_test_item' THEN
    SELECT t.status INTO v_status FROM public.control_test_items i JOIN public.control_tests t ON t.id = i.test_id WHERE i.id = v_obj;
  ELSIF v_type = 'ic_assessment' THEN
    SELECT CASE WHEN status = 'draft' THEN 'in_progress' ELSE 'reviewed' END INTO v_status FROM public.ic_assessments WHERE id = v_obj;
  ELSE
    RETURN coalesce(NEW, OLD);
  END IF;
  IF TG_OP = 'INSERT' AND v_status IS NULL THEN
    RAISE EXCEPTION 'Élément probant : objet introuvable dans la mission' USING ERRCODE = 'check_violation';
  END IF;
  IF v_status IN ('prepared','reviewed') THEN
    RAISE EXCEPTION 'Test ou évaluation figé : éléments probants conservés en l''état' USING ERRCODE = 'check_violation';
  END IF;
  RETURN coalesce(NEW, OLD);
END $$;

-- ---------------------------------------------------------------------
-- 7. Synthèse déterministe des conclusions (règle IC-SYNTH-1, identique au moteur Python)
-- ---------------------------------------------------------------------
-- Conclusion d'un contrôle à partir des derniers tests revus (par type) :
--  1. aucun test revu → not_tested ; 2. tous « non applicable » → not_applicable ; 3. un test inefficace → ineffective ;
--  4. pas de test d'efficacité concluant (absent, non testé, non applicable) → not_tested (la conception seule ne suffit pas) ;
--  5. une conclusion partielle → partially_effective ; 6. sinon → effective.
CREATE OR REPLACE FUNCTION public.ic_combine(p_design text, p_operating text) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE
    WHEN p_design IS NULL AND p_operating IS NULL THEN 'not_tested'
    WHEN coalesce(p_design, 'not_applicable') = 'not_applicable' AND coalesce(p_operating, 'not_applicable') = 'not_applicable'
      THEN 'not_applicable'
    WHEN 'ineffective' IN (coalesce(p_design, ''), coalesce(p_operating, '')) THEN 'ineffective'
    WHEN p_operating IS NULL OR p_operating IN ('not_tested','not_applicable') THEN 'not_tested'
    WHEN 'partially_effective' IN (coalesce(p_design, ''), p_operating) THEN 'partially_effective'
    ELSE 'effective' END
$$;

-- Dernier test revu de chaque type, par contrôle (toutes missions de l'entité, ou une mission)
CREATE OR REPLACE FUNCTION public.ic_control_status(p_company uuid, p_engagement uuid DEFAULT NULL)
RETURNS TABLE (control_id uuid, design text, operating text, conclusion text, operating_test_id uuid,
               operating_period_end date)
LANGUAGE sql STABLE AS $$
  WITH t AS (
    SELECT DISTINCT ON (ct.control_id, ct.test_type) ct.control_id, ct.test_type, ct.conclusion, ct.id, ct.period_end
      FROM public.control_tests ct
     WHERE ct.company_id = p_company AND ct.status = 'reviewed' AND (p_engagement IS NULL OR ct.engagement_id = p_engagement)
     ORDER BY ct.control_id, ct.test_type, ct.reviewed_at DESC, ct.id)
  SELECT c.id, d.conclusion, o.conclusion, public.ic_combine(d.conclusion, o.conclusion), o.id, o.period_end
    FROM public.controls c
    LEFT JOIN t d ON d.control_id = c.id AND d.test_type = 'design'
    LEFT JOIN t o ON o.control_id = c.id AND o.test_type = 'operating'
   WHERE c.company_id = p_company
$$;

-- Contrôles et risques d'un périmètre d'évaluation
CREATE OR REPLACE FUNCTION public.ic_scope(p_company uuid, p_scope text, p_domain uuid, p_process uuid, p_risk uuid,
                                         p_control uuid, p_item uuid, p_cycle text)
RETURNS TABLE (kind text, id uuid)
LANGUAGE sql STABLE AS $$
  WITH RECURSIVE procs AS (
      SELECT p.id FROM public.processes p WHERE p.id = p_process
      UNION SELECT c.id FROM public.processes c JOIN procs ON c.parent_id = procs.id),
    items AS (
      SELECT i.id, i.version_id, i.code FROM public.methodology_items i WHERE i.id = p_item
      UNION SELECT c.id, c.version_id, c.code FROM public.methodology_items c
              JOIN items ON c.version_id = items.version_id AND c.parent_code = items.code),
    ctl AS (
      SELECT c.id FROM public.controls c
       WHERE c.company_id = p_company AND c.operational_status <> 'retired' AND (
             p_scope = 'overall'
          OR (p_scope = 'domain' AND c.domain_id = p_domain)
          OR (p_scope = 'process' AND c.process_id IN (SELECT id FROM procs))
          OR (p_scope = 'cycle' AND c.domain_id IN (SELECT d.id FROM public.ic_domains d WHERE d.company_id = p_company
                                                      AND d.cycle_code = p_cycle))
          OR (p_scope = 'component' AND c.id IN (SELECT l.object_id FROM public.ic_framework_links l
                                                  WHERE l.object_type = 'control' AND l.item_id IN (SELECT id FROM items)))
          OR (p_scope = 'risk' AND c.id IN (SELECT cr.control_id FROM public.control_risks cr WHERE cr.risk_id = p_risk))
          OR (p_scope = 'control' AND c.id = p_control))),
    rsk AS (
      SELECT r.id FROM public.risks r
       WHERE r.company_id = p_company AND r.status = 'active' AND (
             p_scope = 'overall'
          OR (p_scope = 'domain' AND r.domain_id = p_domain)
          OR (p_scope = 'process' AND r.process_id IN (SELECT id FROM procs))
          OR (p_scope = 'cycle' AND (r.cycle_code = p_cycle OR r.domain_id IN (
                SELECT d.id FROM public.ic_domains d WHERE d.company_id = p_company AND d.cycle_code = p_cycle)))
          OR (p_scope = 'component' AND r.id IN (SELECT l.object_id FROM public.ic_framework_links l
                                                  WHERE l.object_type = 'risk' AND l.item_id IN (SELECT id FROM items)))
          OR (p_scope = 'risk' AND r.id = p_risk)
          OR (p_scope = 'control' AND r.id IN (SELECT cr.risk_id FROM public.control_risks cr WHERE cr.control_id = p_control))))
  SELECT 'control', id FROM ctl UNION ALL SELECT 'risk', id FROM rsk
$$;

-- Synthèse chiffrée d'un périmètre (base d'une évaluation, enregistrée à la soumission)
CREATE OR REPLACE FUNCTION public.ic_synthesis(p_company uuid, p_engagement uuid, p_scope text, p_domain uuid, p_process uuid,
                                             p_risk uuid, p_control uuid, p_item uuid, p_cycle text)
RETURNS jsonb
LANGUAGE sql STABLE AS $$
  WITH sc AS (SELECT * FROM public.ic_scope(p_company, p_scope, p_domain, p_process, p_risk, p_control, p_item, p_cycle)),
    st AS (SELECT s.* FROM public.ic_control_status(p_company, p_engagement) s WHERE s.control_id IN
             (SELECT id FROM sc WHERE kind = 'control')),
    cov AS (SELECT r.id, EXISTS (SELECT 1 FROM public.control_risks cr JOIN public.controls c ON c.id = cr.control_id
                                  WHERE cr.risk_id = r.id AND c.existence IN ('existing','not_formalized')
                                    AND c.operational_status = 'active') AS covered
              FROM sc r WHERE r.kind = 'risk')
  SELECT jsonb_build_object(
    'rule', 'IC-SYNTH-1',
    'controls', (SELECT count(*) FROM st),
    'effective', (SELECT count(*) FROM st WHERE conclusion = 'effective'),
    'partially_effective', (SELECT count(*) FROM st WHERE conclusion = 'partially_effective'),
    'ineffective', (SELECT count(*) FROM st WHERE conclusion = 'ineffective'),
    'not_tested', (SELECT count(*) FROM st WHERE conclusion = 'not_tested'),
    'not_applicable', (SELECT count(*) FROM st WHERE conclusion = 'not_applicable'),
    'key_ineffective', (SELECT count(*) FROM st JOIN public.controls c ON c.id = st.control_id
                         WHERE st.conclusion = 'ineffective' AND c.is_key),
    'missing_controls', (SELECT count(*) FROM public.controls c WHERE c.id IN (SELECT id FROM sc WHERE kind = 'control')
                          AND c.existence IN ('expected','absent')),
    'risks', (SELECT count(*) FROM cov),
    'uncovered_risks', (SELECT count(*) FROM cov WHERE NOT covered),
    'controls_detail', coalesce((SELECT jsonb_agg(jsonb_build_object('control_id', st.control_id, 'design', st.design,
                          'operating', st.operating, 'conclusion', st.conclusion) ORDER BY st.control_id) FROM st), '[]'::jsonb))
$$;

-- ---------------------------------------------------------------------
-- 8. Évaluations du dispositif (figées à l'approbation ; chaque nouvelle évaluation est une nouvelle ligne)
-- ---------------------------------------------------------------------
CREATE TABLE public.ic_assessments (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id   uuid NOT NULL,
  engagement_id     uuid NOT NULL,
  company_id        uuid NOT NULL,
  reference         text NOT NULL CHECK (length(trim(reference)) > 0),
  scope_type        text NOT NULL CHECK (scope_type IN ('overall','domain','process','cycle','component','risk','control')),
  domain_id         uuid,
  process_id        uuid,
  risk_id           uuid,
  control_id        uuid,
  framework_item_id uuid REFERENCES public.methodology_items(id),
  cycle_code        text,
  as_of_date        date NOT NULL,
  rating_code       text,                 -- niveau de l'échelle control_level_scale de la méthodologie de la mission
  conclusion        text,
  basis             jsonb,                -- synthèse calculée par la base à la soumission
  status            text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','submitted','approved')),
  prepared_by       uuid REFERENCES public.profiles(id),
  prepared_at       timestamptz,
  approved_by       uuid REFERENCES public.profiles(id),
  approved_at       timestamptz,
  return_reason     text,
  created_by        uuid NOT NULL REFERENCES public.profiles(id),
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (engagement_id, reference),
  UNIQUE (id, engagement_id),
  FOREIGN KEY (engagement_id, organization_id) REFERENCES public.engagements(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (engagement_id, company_id) REFERENCES public.engagements(id, company_id),
  FOREIGN KEY (domain_id, company_id) REFERENCES public.ic_domains(id, company_id),
  FOREIGN KEY (process_id, company_id) REFERENCES public.processes(id, company_id),
  FOREIGN KEY (risk_id, company_id) REFERENCES public.risks(id, company_id),
  FOREIGN KEY (control_id, company_id) REFERENCES public.controls(id, company_id),
  CHECK (CASE scope_type
           WHEN 'overall'   THEN num_nonnulls(domain_id, process_id, risk_id, control_id, framework_item_id, cycle_code) = 0
           WHEN 'domain'    THEN domain_id IS NOT NULL AND num_nonnulls(process_id, risk_id, control_id, framework_item_id, cycle_code) = 0
           WHEN 'process'   THEN process_id IS NOT NULL AND num_nonnulls(domain_id, risk_id, control_id, framework_item_id, cycle_code) = 0
           WHEN 'cycle'     THEN cycle_code IS NOT NULL AND num_nonnulls(domain_id, process_id, risk_id, control_id, framework_item_id) = 0
           WHEN 'component' THEN framework_item_id IS NOT NULL AND num_nonnulls(domain_id, process_id, risk_id, control_id, cycle_code) = 0
           WHEN 'risk'      THEN risk_id IS NOT NULL AND num_nonnulls(domain_id, process_id, control_id, framework_item_id, cycle_code) = 0
           WHEN 'control'   THEN control_id IS NOT NULL AND num_nonnulls(domain_id, process_id, risk_id, framework_item_id, cycle_code) = 0
         END),
  CHECK (status = 'draft' OR (basis IS NOT NULL AND prepared_by IS NOT NULL AND rating_code IS NOT NULL)),
  CHECK (status <> 'approved' OR (approved_by IS NOT NULL AND approved_by <> prepared_by))
);
CREATE INDEX ic_assessments_company_idx ON public.ic_assessments (company_id, status, as_of_date);

CREATE OR REPLACE FUNCTION public.guard_ic_assessment() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_role text; v_levels jsonb; v_basis jsonb; v_item record;
BEGIN
  v_role := coalesce(authz.ia_role(coalesce(NEW.engagement_id, OLD.engagement_id)), '');
  IF TG_OP = 'DELETE' THEN
    IF OLD.status <> 'draft' THEN
      RAISE EXCEPTION 'Évaluation soumise ou approuvée : conservée' USING ERRCODE = 'check_violation';
    END IF;
    RETURN OLD;
  END IF;
  IF v_role NOT IN ('partner','manager','in_charge','staff') THEN
    RAISE EXCEPTION 'Évaluations : équipe de la mission' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF (SELECT engagement_type FROM public.engagements WHERE id = NEW.engagement_id) NOT IN ('ic_assessment','internal_audit') THEN
    RAISE EXCEPTION 'Évaluation du contrôle interne : mission d''évaluation du contrôle interne ou d''audit interne'
      USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.framework_item_id IS NOT NULL THEN
    SELECT i.item_type, v.status INTO v_item FROM public.methodology_items i
      JOIN public.methodology_versions v ON v.id = i.version_id WHERE i.id = NEW.framework_item_id;
    IF v_item.item_type NOT IN ('ic_component','ic_principle','ic_requirement') OR v_item.status <> 'published' THEN
      RAISE EXCEPTION 'Évaluation par composante : élément publié d''un référentiel' USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.created_by IS DISTINCT FROM auth.uid() OR NEW.status <> 'draft' OR NEW.basis IS NOT NULL THEN
      RAISE EXCEPTION 'Évaluation : créée en brouillon, au nom de l''utilisateur authentifié' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.status = 'approved' THEN
    RAISE EXCEPTION 'Évaluation approuvée : figée (créez une nouvelle évaluation)' USING ERRCODE = 'check_violation';
  END IF;
  IF OLD.status = 'submitted' AND NEW.status = 'submitted' THEN
    RAISE EXCEPTION 'Évaluation soumise : contenu figé jusqu''à l''approbation ou au renvoi' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.status = 'draft' AND OLD.status = 'draft' THEN
    IF NEW.basis IS NOT NULL THEN
      RAISE EXCEPTION 'Évaluation : la synthèse est calculée à la soumission' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
  END IF;
  v_basis := public.ic_synthesis(NEW.company_id, NEW.engagement_id, NEW.scope_type, NEW.domain_id, NEW.process_id, NEW.risk_id,
                                 NEW.control_id, NEW.framework_item_id, NEW.cycle_code);
  IF (OLD.status, NEW.status) = ('draft','submitted') THEN
    IF NEW.prepared_by IS DISTINCT FROM auth.uid() THEN
      RAISE EXCEPTION 'Soumission : au nom de l''utilisateur authentifié' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF length(trim(coalesce(NEW.conclusion, ''))) < 3 THEN
      RAISE EXCEPTION 'Soumission : conclusion requise' USING ERRCODE = 'check_violation';
    END IF;
    SELECT i.content -> 'levels' INTO v_levels FROM public.engagements e
      JOIN public.methodology_items i ON i.version_id = e.methodology_version_id AND i.item_type = 'control_level_scale'
     WHERE e.id = NEW.engagement_id;
    IF v_levels IS NULL THEN
      RAISE EXCEPTION 'La méthodologie de la mission ne contient pas d''échelle de niveau de maîtrise (control_level_scale)'
        USING ERRCODE = 'check_violation';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM jsonb_array_elements(v_levels) l WHERE l ->> 'code' = NEW.rating_code) THEN
      RAISE EXCEPTION 'Niveau de maîtrise « % » absent de l''échelle de la méthodologie', NEW.rating_code USING ERRCODE = 'check_violation';
    END IF;
    NEW.basis := v_basis; NEW.prepared_at := now(); NEW.return_reason := NULL;
  ELSIF (OLD.status, NEW.status) = ('submitted','approved') THEN
    IF v_role NOT IN ('partner','manager') OR NEW.approved_by IS DISTINCT FROM auth.uid() THEN
      RAISE EXCEPTION 'Approbation : manager ou associé, en son nom' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.approved_by = OLD.prepared_by THEN
      RAISE EXCEPTION 'Approbation : par une autre personne que le préparateur' USING ERRCODE = 'check_violation';
    END IF;
    IF (to_jsonb(NEW) - ARRAY['status','approved_by','approved_at','updated_at'])
       IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['status','approved_by','approved_at','updated_at']) THEN
      RAISE EXCEPTION 'Approbation : le contenu soumis ne se modifie pas' USING ERRCODE = 'check_violation';
    END IF;
    IF v_basis IS DISTINCT FROM OLD.basis THEN
      RAISE EXCEPTION 'Les résultats des tests ont changé depuis la soumission : renvoyez l''évaluation pour la resoumettre'
        USING ERRCODE = 'check_violation';
    END IF;
    NEW.approved_at := now();
  ELSIF (OLD.status, NEW.status) = ('submitted','draft') THEN
    IF v_role NOT IN ('partner','manager') OR length(trim(coalesce(NEW.return_reason, ''))) < 3 THEN
      RAISE EXCEPTION 'Renvoi : manager ou associé, motif requis' USING ERRCODE = 'check_violation';
    END IF;
    NEW.basis := NULL; NEW.prepared_by := NULL; NEW.prepared_at := NULL;
  ELSE
    RAISE EXCEPTION 'Évaluation : transition interdite % → %', OLD.status, NEW.status USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER ic_assessments_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ic_assessments
  FOR EACH ROW EXECUTE FUNCTION public.guard_ic_assessment();

CREATE TRIGGER evidence_links_ic_guard BEFORE INSERT OR UPDATE OR DELETE ON public.evidence_links
  FOR EACH ROW EXECUTE FUNCTION public.guard_ic_evidence_link();

-- ---------------------------------------------------------------------
-- 9. Audit financier : prise en compte de tests de contrôles déjà réalisés (sans les refaire)
-- ---------------------------------------------------------------------
CREATE TABLE public.control_test_reliances (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id  uuid NOT NULL,
  engagement_id    uuid NOT NULL,          -- mission d'audit financier
  company_id       uuid NOT NULL,
  control_test_id  uuid NOT NULL REFERENCES public.control_tests(id),
  cycle_code       text,
  assertion_codes  text[] NOT NULL DEFAULT '{}',
  decision         text NOT NULL CHECK (decision IN ('rely','partial_rely','no_reliance')),
  rationale        text NOT NULL CHECK (length(trim(rationale)) >= 3),
  approach_impact  text,                   -- adaptation de l'approche (nature, calendrier, étendue des contrôles de substance)
  period_overlap   boolean NOT NULL DEFAULT false,
  snapshot         jsonb NOT NULL DEFAULT '{}'::jsonb,   -- période, périmètre, conclusion, preuves (empreintes) au moment de la décision
  decided_by       uuid NOT NULL REFERENCES public.profiles(id),
  decided_at       timestamptz NOT NULL DEFAULT now(),
  status           text NOT NULL DEFAULT 'active' CHECK (status IN ('active','withdrawn')),
  withdrawn_reason text,
  UNIQUE (engagement_id, control_test_id),
  FOREIGN KEY (engagement_id, organization_id) REFERENCES public.engagements(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (engagement_id, company_id) REFERENCES public.engagements(id, company_id),
  CHECK (status <> 'withdrawn' OR length(trim(coalesce(withdrawn_reason, ''))) >= 3)
);

CREATE OR REPLACE FUNCTION public.guard_control_test_reliance() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_role text; e record; t record; v_start date; v_end date;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Prise en compte d''un test : conservée (retirez-la, avec un motif)' USING ERRCODE = 'check_violation';
  END IF;
  v_role := coalesce(authz.ia_role(NEW.engagement_id), '');
  IF v_role NOT IN ('partner','manager','in_charge') THEN
    RAISE EXCEPTION 'Prise en compte des tests de contrôle : encadrement de la mission' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF TG_OP = 'UPDATE' THEN
    IF OLD.status = 'withdrawn' OR NEW.status <> 'withdrawn'
       OR (to_jsonb(NEW) - ARRAY['status','withdrawn_reason']) IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['status','withdrawn_reason']) THEN
      RAISE EXCEPTION 'Prise en compte : seul le retrait motivé est possible' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
  END IF;
  SELECT en.engagement_type, en.period_start, en.period_end, fy.start_date, fy.end_date INTO e
    FROM public.engagements en LEFT JOIN public.fiscal_years fy ON fy.id = en.fiscal_year_id WHERE en.id = NEW.engagement_id;
  IF e.engagement_type NOT IN ('statutory_audit','contractual_audit') THEN
    RAISE EXCEPTION 'Prise en compte : mission d''audit financier' USING ERRCODE = 'check_violation';
  END IF;
  SELECT ct.*, c.code AS control_code, c.title AS control_title INTO t
    FROM public.control_tests ct JOIN public.controls c ON c.id = ct.control_id WHERE ct.id = NEW.control_test_id;
  IF t.company_id IS DISTINCT FROM NEW.company_id THEN
    RAISE EXCEPTION 'Test d''une autre entité' USING ERRCODE = 'check_violation';
  END IF;
  IF t.status <> 'reviewed' THEN
    RAISE EXCEPTION 'Seul un test revu peut être pris en compte' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.decided_by IS DISTINCT FROM auth.uid() THEN
    RAISE EXCEPTION 'Décision : au nom de l''utilisateur authentifié' USING ERRCODE = 'insufficient_privilege';
  END IF;
  v_start := coalesce(e.start_date, e.period_start); v_end := coalesce(e.end_date, e.period_end);
  NEW.period_overlap := t.period_start IS NOT NULL AND t.period_end IS NOT NULL AND v_start IS NOT NULL AND v_end IS NOT NULL
                        AND t.period_start <= v_end AND t.period_end >= v_start;
  IF NEW.decision = 'rely' AND (t.test_type <> 'operating' OR t.conclusion <> 'effective') THEN
    RAISE EXCEPTION 'Appui sur le contrôle : test d''efficacité opérationnelle conclu « efficace »' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.decision = 'partial_rely' AND (t.test_type <> 'operating' OR t.conclusion NOT IN ('effective','partially_effective')) THEN
    RAISE EXCEPTION 'Appui partiel : test d''efficacité opérationnelle conclu efficace ou partiellement efficace'
      USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.decision IN ('rely','partial_rely') AND NOT NEW.period_overlap THEN
    RAISE EXCEPTION 'Appui sur le contrôle : la période testée doit recouvrir la période auditée' USING ERRCODE = 'check_violation';
  END IF;
  NEW.decided_at := now(); NEW.status := 'active';
  NEW.snapshot := jsonb_build_object(
    'captured_at', now(),
    'control', jsonb_build_object('code', t.control_code, 'title', t.control_title),
    'test', jsonb_build_object('id', t.id, 'reference', t.reference, 'engagement_id', t.engagement_id, 'test_type', t.test_type,
              'test_methods', to_jsonb(t.test_methods), 'period_start', t.period_start, 'period_end', t.period_end,
              'population_description', t.population_description, 'population_size', t.population_size,
              'selection_method', t.selection_method, 'sample_size', t.sample_size, 'conclusion', t.conclusion,
              'conclusion_rationale', t.conclusion_rationale, 'prepared_by', t.prepared_by, 'reviewed_by', t.reviewed_by,
              'reviewed_at', t.reviewed_at),
    'items', (SELECT jsonb_build_object('total', count(*), 'compliant', count(*) FILTER (WHERE result = 'compliant'),
                                        'exceptions', count(*) FILTER (WHERE result = 'exception'))
                FROM public.control_test_items WHERE test_id = t.id),
    'evidence', coalesce((SELECT jsonb_agg(DISTINCT jsonb_build_object('title', ev.title, 'sha256', ev.sha256,
                                   'obtained_on', ev.obtained_on))
                FROM public.evidence_links l JOIN public.evidence_items ev ON ev.id = l.evidence_id
               WHERE (l.object_type = 'control_test' AND l.object_id = t.id)
                  OR (l.object_type = 'control_test_item' AND l.object_id IN (SELECT id FROM public.control_test_items
                                                                               WHERE test_id = t.id))), '[]'::jsonb));
  RETURN NEW;
END $$;
CREATE TRIGGER control_test_reliances_guard BEFORE INSERT OR UPDATE OR DELETE ON public.control_test_reliances
  FOR EACH ROW EXECUTE FUNCTION public.guard_control_test_reliance();

-- ---------------------------------------------------------------------
-- 10. Déficiences : constats typés, rattachés au contrôle ; clôture après vérification
-- ---------------------------------------------------------------------
ALTER TABLE public.findings
  ADD COLUMN kind         text NOT NULL DEFAULT 'audit_finding'
                            CHECK (kind IN ('audit_finding','ic_deficiency','management_letter_point')),
  ADD COLUMN control_id   uuid REFERENCES public.controls(id),
  ADD COLUMN risk_id      uuid REFERENCES public.risks(id),
  ADD COLUMN domain_id    uuid REFERENCES public.ic_domains(id),
  ADD COLUMN closed_by    uuid REFERENCES public.profiles(id),
  ADD COLUMN closed_at    timestamptz,
  ADD COLUMN closure_note text;
ALTER TABLE public.findings DROP CONSTRAINT findings_status_check;
ALTER TABLE public.findings ADD CONSTRAINT findings_status_check CHECK (status IN ('draft','validated','communicated','closed'));
ALTER TABLE public.findings ADD CONSTRAINT findings_closed_check
  CHECK (status <> 'closed' OR (closed_by IS NOT NULL AND closed_at IS NOT NULL AND length(trim(coalesce(closure_note, ''))) >= 3));
ALTER TABLE public.findings ADD CONSTRAINT findings_deficiency_check CHECK (kind <> 'ic_deficiency' OR control_id IS NOT NULL);
CREATE INDEX findings_control_idx ON public.findings (control_id) WHERE control_id IS NOT NULL;

CREATE OR REPLACE FUNCTION public.guard_finding() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_role text; v_company uuid; v_levels jsonb; v_content_changed boolean; v_response_changed boolean; v_open int;
BEGIN
  v_role := coalesce(authz.ia_role(coalesce(NEW.engagement_id, OLD.engagement_id)), '');
  IF TG_OP = 'DELETE' THEN
    IF OLD.status <> 'draft' THEN
      RAISE EXCEPTION 'Constat validé : conservé (remettez-le en brouillon pour le modifier)' USING ERRCODE = 'check_violation';
    END IF;
    RETURN OLD;
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.created_by IS DISTINCT FROM auth.uid() OR NEW.status <> 'draft' OR NEW.management_response IS NOT NULL
       OR NEW.closed_by IS NOT NULL THEN
      RAISE EXCEPTION 'Constat : créé en brouillon, au nom de l''utilisateur authentifié' USING ERRCODE = 'check_violation';
    END IF;
  ELSE
    IF NEW.kind IS DISTINCT FROM OLD.kind THEN
      RAISE EXCEPTION 'Constat : la nature (constat, déficience…) ne change pas' USING ERRCODE = 'check_violation';
    END IF;
    IF OLD.status = 'closed' THEN
      RAISE EXCEPTION 'Constat clos : figé' USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  SELECT company_id INTO v_company FROM public.engagements WHERE id = NEW.engagement_id;
  -- déficience : domaine hérité du contrôle
  IF NEW.kind = 'ic_deficiency' AND NEW.domain_id IS NULL AND NEW.control_id IS NOT NULL THEN
    NEW.domain_id := (SELECT domain_id FROM public.controls WHERE id = NEW.control_id);
  END IF;
  v_content_changed := TG_OP = 'INSERT' OR (NEW.reference, NEW.title, NEW.condition, NEW.criteria, NEW.cause, NEW.effect,
      NEW.rating_code, NEW.process_id, NEW.engagement_risk_id, NEW.workpaper_id, NEW.control_id, NEW.risk_id, NEW.domain_id)
    IS DISTINCT FROM (OLD.reference, OLD.title, OLD.condition, OLD.criteria, OLD.cause, OLD.effect, OLD.rating_code,
                      OLD.process_id, OLD.engagement_risk_id, OLD.workpaper_id, OLD.control_id, OLD.risk_id, OLD.domain_id);
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
  IF TG_OP = 'UPDATE' AND (NEW.closed_by, NEW.closed_at, NEW.closure_note) IS DISTINCT FROM (OLD.closed_by, OLD.closed_at, OLD.closure_note)
     AND NEW.status <> 'closed' THEN
    RAISE EXCEPTION 'Clôture : par la transition « clos »' USING ERRCODE = 'check_violation';
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

  -- références internes à l'entité auditée
  IF NEW.process_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM public.processes WHERE id = NEW.process_id AND company_id = v_company) THEN
    RAISE EXCEPTION 'Processus hors de l''entité auditée' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.control_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM public.controls WHERE id = NEW.control_id AND company_id = v_company) THEN
    RAISE EXCEPTION 'Contrôle hors de l''entité auditée' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.risk_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM public.risks WHERE id = NEW.risk_id AND company_id = v_company) THEN
    RAISE EXCEPTION 'Risque hors de l''entité auditée' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.domain_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM public.ic_domains WHERE id = NEW.domain_id AND company_id = v_company) THEN
    RAISE EXCEPTION 'Domaine hors de l''entité auditée' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.kind = 'ic_deficiency' AND (SELECT engagement_type FROM public.engagements WHERE id = NEW.engagement_id)
       NOT IN ('ic_assessment','internal_audit') THEN
    RAISE EXCEPTION 'Déficience de contrôle interne : mission d''évaluation du contrôle interne ou d''audit interne'
      USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.rating_code IS NOT NULL AND v_content_changed THEN
    -- déficience : échelle des déficiences de la méthodologie si elle existe, sinon échelle des constats
    SELECT coalesce(
             (SELECT i.content -> 'levels' FROM public.methodology_items i
               WHERE i.version_id = e.methodology_version_id AND i.item_type = 'deficiency_scale' AND NEW.kind = 'ic_deficiency' LIMIT 1),
             (SELECT i.content -> 'levels' FROM public.methodology_items i
               WHERE i.version_id = e.methodology_version_id AND i.item_type = 'finding_scale' LIMIT 1))
      INTO v_levels FROM public.engagements e WHERE e.id = NEW.engagement_id;
    IF v_levels IS NULL OR NOT EXISTS (SELECT 1 FROM jsonb_array_elements(v_levels) l WHERE l ->> 'code' = NEW.rating_code) THEN
      RAISE EXCEPTION 'Cotation « % » absente de l''échelle de la méthodologie', NEW.rating_code USING ERRCODE = 'check_violation';
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
    ELSIF (OLD.status, NEW.status) = ('communicated','closed') THEN
      IF v_role NOT IN ('partner','manager','in_charge') OR NEW.closed_by IS DISTINCT FROM auth.uid() THEN
        RAISE EXCEPTION 'Clôture : encadrement de la mission, en son nom' USING ERRCODE = 'insufficient_privilege';
      END IF;
      IF EXISTS (SELECT 1 FROM public.recommendations r WHERE r.finding_id = NEW.id
                  AND NOT EXISTS (SELECT 1 FROM public.action_plans a WHERE a.recommendation_id = r.id)) THEN
        RAISE EXCEPTION 'Clôture : chaque recommandation doit avoir un plan d''action' USING ERRCODE = 'check_violation';
      END IF;
      SELECT count(*) INTO v_open FROM public.action_plans a JOIN public.recommendations r ON r.id = a.recommendation_id
       WHERE r.finding_id = NEW.id AND a.status NOT IN ('verified','risk_accepted');
      IF v_open > 0 THEN
        RAISE EXCEPTION 'Clôture : % plan(s) d''action ni vérifié(s) ni en risque accepté', v_open USING ERRCODE = 'check_violation';
      END IF;
      NEW.closed_at := now();
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

-- après l'émission, le dossier reste figé ; seule la clôture d'un constat communiqué (suivi) reste possible
CREATE OR REPLACE FUNCTION public.guard_finding_open() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE v_status text;
BEGIN
  SELECT status INTO v_status FROM public.engagements WHERE id = coalesce(NEW.engagement_id, OLD.engagement_id);
  IF v_status IN ('issued','archived') THEN
    IF TG_OP = 'UPDATE' AND OLD.status = 'communicated' AND NEW.status = 'closed'
       AND (to_jsonb(NEW) - ARRAY['status','closed_by','closed_at','closure_note','updated_at'])
           IS NOT DISTINCT FROM (to_jsonb(OLD) - ARRAY['status','closed_by','closed_at','closure_note','updated_at']) THEN
      RETURN NEW;
    END IF;
    RAISE EXCEPTION 'Mission % : dossier figé', v_status USING ERRCODE = 'check_violation';
  END IF;
  RETURN coalesce(NEW, OLD);
END $$;
DROP TRIGGER findings_dossier_open ON public.findings;
CREATE TRIGGER findings_dossier_open BEFORE INSERT OR UPDATE OR DELETE ON public.findings
  FOR EACH ROW EXECUTE FUNCTION public.guard_finding_open();

-- l'émission du rapport accepte les constats clos ; contrôles d'émission inchangés sinon
DO $$
DECLARE src text; n text;
BEGIN
  src := pg_get_functiondef('public.guard_audit_report()'::regprocedure);
  n := replace(src, $r$engagement_id = NEW.engagement_id AND status <> 'communicated'$r$,
                    $r$engagement_id = NEW.engagement_id AND status NOT IN ('communicated','closed')$r$);
  IF n = src THEN RAISE EXCEPTION 'Migration 0011 : contrôle d''émission introuvable'; END IF;
  EXECUTE n;
END $$;

CREATE OR REPLACE FUNCTION authz.auditee_sees_finding(p_finding uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT EXISTS (SELECT 1 FROM public.findings f
                  WHERE f.id = p_finding AND f.status IN ('communicated','closed') AND authz.ia_role(f.engagement_id) = 'auditee')
$$;
-- les pilotes du contrôle interne (et le responsable du domaine) suivent les déficiences communiquées
CREATE OR REPLACE FUNCTION authz.ic_sees_finding(p_finding uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT EXISTS (SELECT 1 FROM public.findings f JOIN public.engagements e ON e.id = f.engagement_id
                  WHERE f.id = p_finding AND f.kind = 'ic_deficiency' AND f.status IN ('communicated','closed')
                    AND authz.ic_manages(e.company_id, f.domain_id))
$$;
REVOKE ALL ON FUNCTION authz.ic_sees_finding(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION authz.ic_sees_finding(uuid) TO authenticated, service_role;

DROP POLICY findings_select ON public.findings;
CREATE POLICY findings_select ON public.findings FOR SELECT TO authenticated
  USING (authz.can_read_dossier(engagement_id)
         OR (status IN ('communicated','closed') AND authz.ia_role(engagement_id) = 'auditee')
         OR authz.ic_sees_finding(id));
CREATE POLICY recommendations_select_ic ON public.recommendations FOR SELECT TO authenticated
  USING (authz.ic_sees_finding(finding_id));
CREATE POLICY action_plans_select_ic ON public.action_plans FOR SELECT TO authenticated
  USING (EXISTS (SELECT 1 FROM public.recommendations r WHERE r.id = recommendation_id AND authz.ic_sees_finding(r.finding_id)));
CREATE POLICY action_plan_updates_select_ic ON public.action_plan_updates FOR SELECT TO authenticated
  USING (EXISTS (SELECT 1 FROM public.action_plans a JOIN public.recommendations r ON r.id = a.recommendation_id
                  WHERE a.id = action_plan_id AND authz.ic_sees_finding(r.finding_id)));

-- ---------------------------------------------------------------------
-- 11. Historique du dispositif (non modifiable)
-- ---------------------------------------------------------------------
CREATE TABLE public.ic_history (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  company_id      uuid NOT NULL,
  object_type     text NOT NULL,
  object_id       uuid NOT NULL,
  action          text NOT NULL,
  reason          text,
  before          jsonb,
  after           jsonb,
  changed_by      uuid REFERENCES public.profiles(id),
  changed_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ic_history_object_idx ON public.ic_history (object_type, object_id, changed_at);
CREATE INDEX ic_history_company_idx ON public.ic_history (company_id, changed_at);

CREATE OR REPLACE FUNCTION public.log_ic_history() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE o jsonb := CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE to_jsonb(OLD) END;
        n jsonb := CASE WHEN TG_OP = 'DELETE' THEN NULL ELSE to_jsonb(NEW) END;
        r jsonb := coalesce(n, o); v_action text := lower(TG_OP); v_reason text; v_id uuid;
BEGIN
  IF TG_OP = 'UPDATE' THEN
    IF (n - ARRAY['updated_at','updated_by','version']) = (o - ARRAY['updated_at','updated_by','version']) THEN RETURN NULL; END IF;
    IF TG_TABLE_NAME IN ('control_tests','ic_assessments') THEN
      IF n ->> 'status' = o ->> 'status' THEN RETURN NULL; END IF;   -- seules les étapes du circuit sont tracées
      v_action := 'status:' || (n ->> 'status');
      v_reason := coalesce(n ->> 'reopen_reason', n ->> 'return_reason');
    ELSIF TG_TABLE_NAME = 'control_executions' THEN
      v_action := 'supervision:' || (n ->> 'supervision_status');
      v_reason := n ->> 'supervision_comment';
    END IF;
  END IF;
  v_id := CASE TG_TABLE_NAME WHEN 'control_risks' THEN (r ->> 'control_id')::uuid ELSE (r ->> 'id')::uuid END;
  INSERT INTO public.ic_history (organization_id, company_id, object_type, object_id, action, reason, before, after, changed_by)
  VALUES ((r ->> 'organization_id')::uuid, (r ->> 'company_id')::uuid, TG_TABLE_NAME, v_id, v_action, v_reason, o, n, auth.uid());
  RETURN NULL;
END $$;
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['ic_domains','control_objectives','controls','control_risks','control_executions','control_tests',
                           'ic_assessments','ic_members'] LOOP
    EXECUTE format('CREATE TRIGGER %I AFTER INSERT OR UPDATE OR DELETE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.log_ic_history()',
                   t || '_history', t);
  END LOOP;
END $$;

-- ---------------------------------------------------------------------
-- 12. Gel du dossier, type de mission, updated_at
-- ---------------------------------------------------------------------
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['control_tests','control_test_items','ic_assessments','control_test_reliances'] LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE INSERT OR UPDATE OR DELETE ON public.%I
                    FOR EACH ROW EXECUTE FUNCTION public.guard_dossier_open()', t || '_dossier_open', t);
  END LOOP;
  FOREACH t IN ARRAY ARRAY['ic_domains','control_objectives','controls','control_tests','ic_assessments'] LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.set_updated_at()',
                   t || '_updated_at', t);
  END LOOP;
END $$;

-- ---------------------------------------------------------------------
-- 13. RLS
-- ---------------------------------------------------------------------
ALTER TABLE public.framework_mappings ENABLE ROW LEVEL SECURITY;
CREATE POLICY framework_mappings_select ON public.framework_mappings FOR SELECT TO authenticated
  USING (organization_id IS NULL OR authz.is_org_member(organization_id) OR authz.is_platform_admin());
CREATE POLICY framework_mappings_write ON public.framework_mappings FOR ALL TO authenticated
  USING ((organization_id IS NULL AND authz.is_platform_admin())
         OR (organization_id IS NOT NULL AND authz.has_org_role(organization_id, ARRAY['owner','admin'])))
  WITH CHECK ((organization_id IS NULL AND authz.is_platform_admin())
              OR (organization_id IS NOT NULL AND authz.has_org_role(organization_id, ARRAY['owner','admin'])));

ALTER TABLE public.ic_domains ENABLE ROW LEVEL SECURITY;
CREATE POLICY ic_domains_select ON public.ic_domains FOR SELECT TO authenticated USING (authz.ic_reader(company_id));
CREATE POLICY ic_domains_insert ON public.ic_domains FOR INSERT TO authenticated WITH CHECK (authz.ic_admin(company_id));
CREATE POLICY ic_domains_update ON public.ic_domains FOR UPDATE TO authenticated
  USING (authz.ic_manages(company_id, id)) WITH CHECK (authz.ic_manages(company_id, id));
CREATE POLICY ic_domains_delete ON public.ic_domains FOR DELETE TO authenticated USING (authz.ic_admin(company_id));

ALTER TABLE public.ic_members ENABLE ROW LEVEL SECURITY;
CREATE POLICY ic_members_select ON public.ic_members FOR SELECT TO authenticated USING (authz.ic_reader(company_id));
CREATE POLICY ic_members_write ON public.ic_members FOR ALL TO authenticated
  USING (authz.ic_admin(company_id)) WITH CHECK (authz.ic_admin(company_id));

-- registre partagé : lecture élargie aux rôles du contrôle interne ; écriture : auditeurs de l'entité (lot 6)
-- ou gestionnaires du domaine concerné
DROP POLICY processes_select ON public.processes;
DROP POLICY processes_write ON public.processes;
DROP POLICY risks_select ON public.risks;
DROP POLICY risks_write ON public.risks;
CREATE POLICY processes_select ON public.processes FOR SELECT TO authenticated USING (authz.ic_reader(company_id));
CREATE POLICY processes_write ON public.processes FOR ALL TO authenticated
  USING (authz.has_company_role(company_id, ARRAY['auditor']) OR authz.ic_manages(company_id, domain_id))
  WITH CHECK (authz.has_company_role(company_id, ARRAY['auditor']) OR authz.ic_manages(company_id, domain_id));
CREATE POLICY risks_select ON public.risks FOR SELECT TO authenticated USING (authz.ic_reader(company_id));
CREATE POLICY risks_write ON public.risks FOR ALL TO authenticated
  USING (authz.has_company_role(company_id, ARRAY['auditor']) OR authz.ic_manages(company_id, domain_id))
  WITH CHECK (authz.has_company_role(company_id, ARRAY['auditor']) OR authz.ic_manages(company_id, domain_id));
DROP POLICY risk_rating_history_select ON public.risk_rating_history;
CREATE POLICY risk_rating_history_select ON public.risk_rating_history FOR SELECT TO authenticated
  USING (authz.ic_reader(company_id));

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['control_objectives','controls'] LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY %I ON public.%I FOR SELECT TO authenticated USING (authz.ic_reader(company_id))', t || '_select', t);
    EXECUTE format('CREATE POLICY %I ON public.%I FOR ALL TO authenticated USING (authz.ic_manages(company_id, domain_id))
                    WITH CHECK (authz.ic_manages(company_id, domain_id))', t || '_write', t);
  END LOOP;
END $$;

ALTER TABLE public.control_risks ENABLE ROW LEVEL SECURITY;
CREATE POLICY control_risks_select ON public.control_risks FOR SELECT TO authenticated USING (authz.ic_reader(company_id));
CREATE POLICY control_risks_write ON public.control_risks FOR ALL TO authenticated
  USING (authz.ic_manages(company_id, authz.ic_object_domain('control', control_id)))
  WITH CHECK (authz.ic_manages(company_id, authz.ic_object_domain('control', control_id)));

ALTER TABLE public.ic_framework_links ENABLE ROW LEVEL SECURITY;
CREATE POLICY ic_framework_links_select ON public.ic_framework_links FOR SELECT TO authenticated USING (authz.ic_reader(company_id));
CREATE POLICY ic_framework_links_write ON public.ic_framework_links FOR ALL TO authenticated
  USING (authz.ic_manages(company_id, authz.ic_object_domain(object_type, object_id)))
  WITH CHECK (authz.ic_manages(company_id, authz.ic_object_domain(object_type, object_id)));

-- exécutions : lecture par les lecteurs du dispositif ; les droits fins sont dans le trigger
ALTER TABLE public.control_executions ENABLE ROW LEVEL SECURITY;
CREATE POLICY control_executions_select ON public.control_executions FOR SELECT TO authenticated USING (authz.ic_reader(company_id));
CREATE POLICY control_executions_insert ON public.control_executions FOR INSERT TO authenticated
  WITH CHECK (authz.ic_reader(company_id) AND performed_by = auth.uid());
CREATE POLICY control_executions_update ON public.control_executions FOR UPDATE TO authenticated
  USING (authz.ic_reader(company_id)) WITH CHECK (authz.ic_reader(company_id));

-- tests : dossier de la mission ; une fois revus, consultables par les pilotes du contrôle interne et les équipes
-- des missions sur l'entité (audit interne, audit financier)
ALTER TABLE public.control_tests ENABLE ROW LEVEL SECURITY;
CREATE POLICY control_tests_select ON public.control_tests FOR SELECT TO authenticated
  USING (authz.can_read_dossier(engagement_id)
         OR (status = 'reviewed' AND (authz.audits_company(company_id)
                                      OR authz.ic_manages(company_id, authz.ic_object_domain('control', control_id))
                                      OR 'observer' = ANY (authz.ic_roles(company_id, NULL)))));
CREATE POLICY control_tests_write ON public.control_tests FOR ALL TO authenticated
  USING (authz.has_engagement_role(engagement_id, ARRAY['partner','manager','in_charge','staff']))
  WITH CHECK (authz.has_engagement_role(engagement_id, ARRAY['partner','manager','in_charge','staff']));
ALTER TABLE public.control_test_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY control_test_items_select ON public.control_test_items FOR SELECT TO authenticated
  USING (EXISTS (SELECT 1 FROM public.control_tests t WHERE t.id = test_id));
CREATE POLICY control_test_items_write ON public.control_test_items FOR ALL TO authenticated
  USING (authz.has_engagement_role(engagement_id, ARRAY['partner','manager','in_charge','staff']))
  WITH CHECK (authz.has_engagement_role(engagement_id, ARRAY['partner','manager','in_charge','staff']));

ALTER TABLE public.ic_assessments ENABLE ROW LEVEL SECURITY;
CREATE POLICY ic_assessments_select ON public.ic_assessments FOR SELECT TO authenticated
  USING (authz.can_read_dossier(engagement_id)
         OR (status = 'approved' AND (authz.ic_reader(company_id) OR authz.ia_role(engagement_id) = 'auditee')));
CREATE POLICY ic_assessments_write ON public.ic_assessments FOR ALL TO authenticated
  USING (authz.has_engagement_role(engagement_id, ARRAY['partner','manager','in_charge','staff']))
  WITH CHECK (authz.has_engagement_role(engagement_id, ARRAY['partner','manager','in_charge','staff']));

ALTER TABLE public.control_test_reliances ENABLE ROW LEVEL SECURITY;
CREATE POLICY control_test_reliances_select ON public.control_test_reliances FOR SELECT TO authenticated
  USING (authz.can_read_dossier(engagement_id));
CREATE POLICY control_test_reliances_write ON public.control_test_reliances FOR ALL TO authenticated
  USING (authz.has_engagement_role(engagement_id, ARRAY['partner','manager','in_charge']))
  WITH CHECK (authz.has_engagement_role(engagement_id, ARRAY['partner','manager','in_charge']));

ALTER TABLE public.ic_history ENABLE ROW LEVEL SECURITY;
CREATE POLICY ic_history_select ON public.ic_history FOR SELECT TO authenticated
  USING (authz.ic_admin(company_id) OR authz.audits_company(company_id)
         OR (authz.ic_reader(company_id) AND object_type IN ('ic_domains','control_objectives','controls','control_risks')));

-- l'entité est visible des personnes ayant un rôle de contrôle interne (et des équipes de mission sur l'entité)
CREATE POLICY companies_select_ic ON public.companies FOR SELECT TO authenticated USING (authz.ic_reader(id));

-- missions d'évaluation du contrôle interne : ouvertes aussi par les pilotes du dispositif
DROP POLICY engagements_insert ON public.engagements;
CREATE POLICY engagements_insert ON public.engagements FOR INSERT TO authenticated
  WITH CHECK (created_by = auth.uid() AND (authz.can_access_company(company_id) OR authz.ic_admin(company_id))
              AND (authz.has_org_role(organization_id, ARRAY['owner','admin'])
                   OR authz.has_company_role(company_id, ARRAY['auditor'])
                   OR (engagement_type = 'ic_assessment' AND authz.ic_admin(company_id))));

GRANT SELECT, INSERT, UPDATE, DELETE ON public.framework_mappings, public.ic_domains, public.ic_members, public.control_objectives,
  public.controls, public.control_risks, public.ic_framework_links, public.control_tests, public.control_test_items,
  public.ic_assessments TO authenticated;
GRANT SELECT, INSERT, UPDATE ON public.control_executions, public.control_test_reliances TO authenticated;
GRANT SELECT ON public.ic_history TO authenticated;
GRANT ALL ON public.framework_mappings, public.ic_domains, public.ic_members, public.control_objectives, public.controls,
  public.control_risks, public.ic_framework_links, public.control_executions, public.control_tests, public.control_test_items,
  public.ic_assessments, public.control_test_reliances, public.ic_history TO service_role;
REVOKE ALL ON FUNCTION public.ic_control_status(uuid, uuid), public.ic_scope(uuid, text, uuid, uuid, uuid, uuid, uuid, text),
  public.ic_synthesis(uuid, uuid, text, uuid, uuid, uuid, uuid, uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.ic_control_status(uuid, uuid), public.ic_scope(uuid, text, uuid, uuid, uuid, uuid, uuid, text),
  public.ic_synthesis(uuid, uuid, text, uuid, uuid, uuid, uuid, uuid, text) TO authenticated, service_role;

-- ---------------------------------------------------------------------
-- 14. Stockage des preuves d'exécution : {organization_id}/{company_id}/{fichier}
-- ---------------------------------------------------------------------
DO $outer$
BEGIN
  IF to_regclass('storage.buckets') IS NULL OR to_regclass('storage.objects') IS NULL THEN
    RAISE NOTICE 'Schéma storage absent : bucket des preuves d''exécution non créé';
    RETURN;
  END IF;
  INSERT INTO storage.buckets (id, name, public, file_size_limit)
  VALUES ('ic-evidence', 'ic-evidence', false, 52428800)
  ON CONFLICT (id) DO UPDATE SET public = false, file_size_limit = EXCLUDED.file_size_limit;
  -- lecture : lecteurs du dispositif de l'entité ; dépôt par l'API (rôle de service) après contrôle du fichier
  EXECUTE $p$
    CREATE POLICY ic_evidence_read ON storage.objects FOR SELECT TO authenticated
      USING (bucket_id = 'ic-evidence' AND coalesce(authz.ic_reader(authz.storage_object_company(name)), false))$p$;
END $outer$;
