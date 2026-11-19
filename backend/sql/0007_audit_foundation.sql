-- =====================================================================
-- KOFINEX — 0007 : socle commun d'audit (lot 6)
--   méthodologies versionnées, missions, équipe et indépendance, registre des processus et
--   des risques, risques de mission, programmes et procédures, feuilles de travail, éléments
--   probants, notes de revue, signatures, circuits de validation, gel du dossier.
-- Principe : les règles de supervision sont appliquées par la base (triggers), pas seulement
-- par l'API ; une signature exige un utilisateur authentifié (auth.uid()) membre de la mission.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. Méthodologies (données versionnées, comme les référentiels comptables)
-- ---------------------------------------------------------------------
CREATE TABLE public.methodology_versions (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id  uuid REFERENCES public.organizations(id) ON DELETE CASCADE,   -- NULL : méthodologie de la plateforme
  kind             text NOT NULL CHECK (kind IN ('audit','internal_control')),
  name             text NOT NULL CHECK (length(trim(name)) > 0),
  version_label    text NOT NULL CHECK (length(trim(version_label)) > 0),
  source_reference text NOT NULL CHECK (length(trim(source_reference)) > 0),
  description      text,
  status           text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published','archived')),
  published_at     timestamptz,
  published_by     uuid REFERENCES public.profiles(id),
  created_by       uuid NOT NULL REFERENCES public.profiles(id),
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  CHECK (status = 'draft' OR published_at IS NOT NULL)
);
CREATE UNIQUE INDEX methodology_versions_uniq ON public.methodology_versions
  (coalesce(organization_id, '00000000-0000-0000-0000-000000000000'::uuid), name, version_label);

CREATE TABLE public.methodology_items (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  version_id    uuid NOT NULL REFERENCES public.methodology_versions(id) ON DELETE CASCADE,
  item_type     text NOT NULL CHECK (item_type IN ('assertion','cycle','risk_scale','procedure_template',
                                                   'ic_component','ic_principle','deficiency_scale','parameter')),
  code          text NOT NULL CHECK (code ~ '^[A-Za-z0-9_.-]{1,40}$'),
  label         text NOT NULL CHECK (length(trim(label)) > 0),
  parent_code   text,
  content       jsonb NOT NULL DEFAULT '{}'::jsonb,
  display_order int NOT NULL DEFAULT 0,
  source_row    int,
  UNIQUE (version_id, item_type, code)
);

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
    IF OLD.status = 'published' AND (NEW.status <> 'archived' OR (NEW.name, NEW.version_label, NEW.source_reference,
        NEW.kind, NEW.organization_id) IS DISTINCT FROM (OLD.name, OLD.version_label, OLD.source_reference, OLD.kind,
        OLD.organization_id)) THEN
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
CREATE TRIGGER methodology_versions_guard BEFORE UPDATE OR DELETE ON public.methodology_versions
  FOR EACH ROW EXECUTE FUNCTION public.guard_methodology();
CREATE TRIGGER methodology_items_guard BEFORE INSERT OR UPDATE OR DELETE ON public.methodology_items
  FOR EACH ROW EXECUTE FUNCTION public.guard_methodology();

-- ---------------------------------------------------------------------
-- 2. Registre des processus et des risques de l'entité (partagé audit / contrôle interne)
-- ---------------------------------------------------------------------
CREATE TABLE public.processes (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  company_id      uuid NOT NULL,
  parent_id       uuid,
  code            text NOT NULL CHECK (length(trim(code)) > 0),
  name            text NOT NULL CHECK (length(trim(name)) > 0),
  owner_name      text,
  description     text,
  is_active       boolean NOT NULL DEFAULT true,
  created_by      uuid REFERENCES public.profiles(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_id, code),
  UNIQUE (id, company_id),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (parent_id, company_id) REFERENCES public.processes(id, company_id),
  CHECK (parent_id IS NULL OR parent_id <> id)
);

CREATE TABLE public.risks (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id     uuid NOT NULL,
  company_id          uuid NOT NULL,
  process_id          uuid,
  code                text NOT NULL CHECK (length(trim(code)) > 0),
  title               text NOT NULL CHECK (length(trim(title)) > 0),
  description         text,
  cycle_code          text,
  assertion_codes     text[] NOT NULL DEFAULT '{}',
  scale_version_id    uuid REFERENCES public.methodology_versions(id),   -- grille de cotation utilisée
  inherent_likelihood smallint CHECK (inherent_likelihood >= 1),
  inherent_impact     smallint CHECK (inherent_impact >= 1),
  residual_likelihood smallint CHECK (residual_likelihood >= 1),
  residual_impact     smallint CHECK (residual_impact >= 1),
  status              text NOT NULL DEFAULT 'active' CHECK (status IN ('active','retired')),
  created_by          uuid REFERENCES public.profiles(id),
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_id, code),
  UNIQUE (id, company_id),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (process_id, company_id) REFERENCES public.processes(id, company_id)
);

-- ---------------------------------------------------------------------
-- 3. Missions et équipe
-- ---------------------------------------------------------------------
CREATE TABLE public.engagements (
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id        uuid NOT NULL,
  company_id             uuid NOT NULL,
  fiscal_year_id         uuid,
  engagement_type        text NOT NULL CHECK (engagement_type IN ('statutory_audit','contractual_audit','internal_audit','ic_assessment')),
  reference              text NOT NULL CHECK (length(trim(reference)) > 0),
  name                   text NOT NULL CHECK (length(trim(name)) > 0),
  objectives             text,
  scope                  text,
  period_start           date,
  period_end             date,
  planned_start          date,
  planned_end            date,
  methodology_version_id uuid REFERENCES public.methodology_versions(id),
  status                 text NOT NULL DEFAULT 'planning'
                           CHECK (status IN ('planning','fieldwork','review','reporting','issued','archived')),
  issued_at              timestamptz,
  issued_by              uuid REFERENCES public.profiles(id),
  archived_at            timestamptz,
  reopened_at            timestamptz,
  reopened_by            uuid REFERENCES public.profiles(id),
  reopen_reason          text,
  created_by             uuid NOT NULL REFERENCES public.profiles(id),
  created_at             timestamptz NOT NULL DEFAULT now(),
  updated_at             timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, reference),
  UNIQUE (id, organization_id),
  UNIQUE (id, company_id),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (fiscal_year_id, company_id) REFERENCES public.fiscal_years(id, company_id),
  CHECK (period_end IS NULL OR period_start IS NULL OR period_end >= period_start),
  CHECK (planned_end IS NULL OR planned_start IS NULL OR planned_end >= planned_start)
);
CREATE INDEX engagements_company_idx ON public.engagements (company_id, status);

CREATE TABLE public.engagement_members (
  id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id          uuid NOT NULL,
  engagement_id            uuid NOT NULL,
  user_id                  uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  role                     text NOT NULL CHECK (role IN ('partner','manager','in_charge','staff','quality_reviewer','auditee','observer')),
  planned_hours            numeric(8,2) CHECK (planned_hours IS NULL OR planned_hours >= 0),
  independence_confirmed_at timestamptz,
  independence_statement   text,
  added_by                 uuid REFERENCES public.profiles(id),
  created_at               timestamptz NOT NULL DEFAULT now(),
  updated_at               timestamptz NOT NULL DEFAULT now(),
  UNIQUE (engagement_id, user_id),
  FOREIGN KEY (engagement_id, organization_id) REFERENCES public.engagements(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (organization_id, user_id) REFERENCES public.organization_members(organization_id, user_id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------------
-- Fonctions d'accès (SECURITY DEFINER : lisent les membres sans être bloquées par la RLS)
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION authz.engagement_role(p_engagement uuid) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT role FROM public.engagement_members WHERE engagement_id = p_engagement AND user_id = auth.uid()
$$;

-- Rôle « actif » : membre ayant confirmé son indépendance (sauf audité et observateur)
CREATE OR REPLACE FUNCTION authz.has_engagement_role(p_engagement uuid, p_roles text[]) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT EXISTS (SELECT 1 FROM public.engagement_members
                  WHERE engagement_id = p_engagement AND user_id = auth.uid() AND role = ANY (p_roles)
                    AND (independence_confirmed_at IS NOT NULL OR role IN ('auditee','observer')))
$$;

-- Lecture du dossier de travail : équipe d'audit (l'audité n'y a pas accès)
CREATE OR REPLACE FUNCTION authz.can_read_dossier(p_engagement uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT authz.has_engagement_role(p_engagement,
           ARRAY['partner','manager','in_charge','staff','quality_reviewer','observer'])
$$;

CREATE OR REPLACE FUNCTION authz.engagement_org(p_engagement uuid) RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT organization_id FROM public.engagements WHERE id = p_engagement
$$;

REVOKE ALL ON FUNCTION authz.engagement_role(uuid), authz.has_engagement_role(uuid, text[]),
  authz.can_read_dossier(uuid), authz.engagement_org(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION authz.engagement_role(uuid), authz.has_engagement_role(uuid, text[]),
  authz.can_read_dossier(uuid), authz.engagement_org(uuid) TO authenticated, service_role;

-- Le créateur d'une mission en devient le manager (indépendance à confirmer)
CREATE OR REPLACE FUNCTION public.engagement_add_creator() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM public.organization_members WHERE organization_id = NEW.organization_id
                  AND user_id = NEW.created_by) THEN
    RAISE EXCEPTION 'Le créateur de la mission doit être membre de l''organisation' USING ERRCODE = 'check_violation';
  END IF;
  INSERT INTO public.engagement_members (organization_id, engagement_id, user_id, role, added_by)
  VALUES (NEW.organization_id, NEW.id, NEW.created_by, 'manager', NEW.created_by);
  RETURN NEW;
END $$;
CREATE TRIGGER engagements_add_creator AFTER INSERT ON public.engagements
  FOR EACH ROW EXECUTE FUNCTION public.engagement_add_creator();

-- Confirmation d'indépendance : par le membre lui-même, uniquement
CREATE OR REPLACE FUNCTION public.confirm_independence(p_engagement uuid, p_statement text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF auth.uid() IS NULL THEN RAISE EXCEPTION 'Authentification requise' USING ERRCODE = 'insufficient_privilege'; END IF;
  IF length(trim(coalesce(p_statement, ''))) = 0 THEN
    RAISE EXCEPTION 'La déclaration d''indépendance est obligatoire' USING ERRCODE = 'check_violation';
  END IF;
  PERFORM set_config('kofinex.independence', 'on', true);
  UPDATE public.engagement_members SET independence_confirmed_at = now(), independence_statement = p_statement
   WHERE engagement_id = p_engagement AND user_id = auth.uid();
  PERFORM set_config('kofinex.independence', 'off', true);
  IF NOT FOUND THEN RAISE EXCEPTION 'Vous n''êtes pas membre de cette mission' USING ERRCODE = 'check_violation'; END IF;
END $$;
REVOKE ALL ON FUNCTION public.confirm_independence(uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.confirm_independence(uuid, text) TO authenticated;

CREATE OR REPLACE FUNCTION public.guard_engagement_members() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE v_status text;
BEGIN
  SELECT status INTO v_status FROM public.engagements WHERE id = coalesce(NEW.engagement_id, OLD.engagement_id);
  IF v_status IN ('issued','archived') THEN
    RAISE EXCEPTION 'Mission %: équipe figée', v_status USING ERRCODE = 'check_violation';
  END IF;
  IF TG_OP = 'UPDATE' THEN
    IF (NEW.independence_confirmed_at, NEW.independence_statement) IS DISTINCT FROM
       (OLD.independence_confirmed_at, OLD.independence_statement)
       AND coalesce(current_setting('kofinex.independence', true), 'off') <> 'on' THEN
      RAISE EXCEPTION 'L''indépendance est confirmée par le membre lui-même' USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.role IS DISTINCT FROM OLD.role THEN
      NEW.independence_confirmed_at := NULL;     -- un changement de rôle appelle une nouvelle déclaration
      NEW.independence_statement := NULL;
    END IF;
  END IF;
  IF TG_OP = 'INSERT' THEN
    NEW.independence_confirmed_at := NULL;
    NEW.independence_statement := NULL;
  END IF;
  RETURN coalesce(NEW, OLD);
END $$;
CREATE TRIGGER engagement_members_guard BEFORE INSERT OR UPDATE OR DELETE ON public.engagement_members
  FOR EACH ROW EXECUTE FUNCTION public.guard_engagement_members();

-- ---------------------------------------------------------------------
-- 4. Dossier de travail
-- ---------------------------------------------------------------------
CREATE TABLE public.engagement_risks (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  engagement_id   uuid NOT NULL,
  risk_id         uuid REFERENCES public.risks(id),
  code            text NOT NULL CHECK (length(trim(code)) > 0),
  title           text NOT NULL CHECK (length(trim(title)) > 0),
  description     text,
  cycle_code      text,
  assertion_codes text[] NOT NULL DEFAULT '{}',
  likelihood      smallint CHECK (likelihood >= 1),
  impact          smallint CHECK (impact >= 1),
  is_significant  boolean NOT NULL DEFAULT false,
  planned_response text,
  origin          text NOT NULL DEFAULT 'manual' CHECK (origin IN ('manual','registry','ai_suggestion')),
  created_by      uuid REFERENCES public.profiles(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (engagement_id, code),
  FOREIGN KEY (engagement_id, organization_id) REFERENCES public.engagements(id, organization_id) ON DELETE CASCADE
);

CREATE TABLE public.work_programs (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  engagement_id   uuid NOT NULL,
  code            text NOT NULL CHECK (length(trim(code)) > 0),
  title           text NOT NULL CHECK (length(trim(title)) > 0),
  cycle_code      text,
  objective       text,
  display_order   int NOT NULL DEFAULT 0,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (engagement_id, code),
  UNIQUE (id, engagement_id),
  FOREIGN KEY (engagement_id, organization_id) REFERENCES public.engagements(id, organization_id) ON DELETE CASCADE
);

CREATE TABLE public.procedures (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id  uuid NOT NULL,
  engagement_id    uuid NOT NULL,
  program_id       uuid NOT NULL,
  code             text NOT NULL CHECK (length(trim(code)) > 0),
  title            text NOT NULL CHECK (length(trim(title)) > 0),
  objective        text,
  nature           text NOT NULL CHECK (nature IN ('control_test','analytical','detail_test','inquiry','observation',
                                                   'inspection','confirmation','recalculation','other')),
  steps            jsonb NOT NULL DEFAULT '[]'::jsonb,
  assertion_codes  text[] NOT NULL DEFAULT '{}',
  template_item_id uuid REFERENCES public.methodology_items(id),
  assigned_to      uuid REFERENCES public.profiles(id),
  due_date         date,
  status           text NOT NULL DEFAULT 'not_started' CHECK (status IN ('not_started','in_progress','done','not_applicable')),
  na_reason        text,
  origin           text NOT NULL DEFAULT 'manual' CHECK (origin IN ('manual','template','ai_suggestion')),
  display_order    int NOT NULL DEFAULT 0,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (engagement_id, code),
  UNIQUE (id, engagement_id),
  FOREIGN KEY (engagement_id, organization_id) REFERENCES public.engagements(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (program_id, engagement_id) REFERENCES public.work_programs(id, engagement_id) ON DELETE CASCADE,
  CHECK (status <> 'not_applicable' OR length(trim(coalesce(na_reason, ''))) > 0)
);

CREATE TABLE public.procedure_risks (
  procedure_id       uuid NOT NULL REFERENCES public.procedures(id) ON DELETE CASCADE,
  engagement_risk_id uuid NOT NULL REFERENCES public.engagement_risks(id) ON DELETE CASCADE,
  engagement_id      uuid NOT NULL REFERENCES public.engagements(id) ON DELETE CASCADE,
  PRIMARY KEY (procedure_id, engagement_risk_id)
);

CREATE TABLE public.workpapers (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  engagement_id   uuid NOT NULL,
  procedure_id    uuid,
  reference       text NOT NULL CHECK (length(trim(reference)) > 0),
  title           text NOT NULL CHECK (length(trim(title)) > 0),
  objective       text,
  work_performed  text,
  conclusion      text,
  content         jsonb NOT NULL DEFAULT '{}'::jsonb,
  status          text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','prepared','reviewed','approved')),
  version         int NOT NULL DEFAULT 1,
  content_hash    text NOT NULL DEFAULT '',
  origin          text NOT NULL DEFAULT 'manual' CHECK (origin IN ('manual','ai_suggestion')),
  created_by      uuid REFERENCES public.profiles(id),
  updated_by      uuid REFERENCES public.profiles(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (engagement_id, reference),
  UNIQUE (id, engagement_id),
  FOREIGN KEY (engagement_id, organization_id) REFERENCES public.engagements(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (procedure_id, engagement_id) REFERENCES public.procedures(id, engagement_id)
);

CREATE TABLE public.evidence_items (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id   uuid NOT NULL,
  engagement_id     uuid NOT NULL,
  kind              text NOT NULL CHECK (kind IN ('file','snapshot')),
  title             text NOT NULL CHECK (length(trim(title)) > 0),
  description       text,
  source            text NOT NULL CHECK (source IN ('auditor','auditee','platform','third_party')),
  obtained_on       date NOT NULL DEFAULT current_date,
  storage_path      text,
  original_filename text,
  mime_type         text,
  size_bytes        bigint,
  snapshot          jsonb,
  snapshot_ref      jsonb,                         -- ce qui a été figé (table, identifiants)
  sha256            text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  uploaded_by       uuid NOT NULL REFERENCES public.profiles(id),
  created_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id, engagement_id),
  FOREIGN KEY (engagement_id, organization_id) REFERENCES public.engagements(id, organization_id) ON DELETE CASCADE,
  CHECK ((kind = 'file' AND storage_path IS NOT NULL AND snapshot IS NULL)
      OR (kind = 'snapshot' AND snapshot IS NOT NULL AND storage_path IS NULL))
);

CREATE TABLE public.evidence_links (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  engagement_id uuid NOT NULL,
  evidence_id   uuid NOT NULL,
  object_type   text NOT NULL CHECK (object_type IN ('workpaper','procedure','engagement_risk')),
  object_id     uuid NOT NULL,
  created_by    uuid REFERENCES public.profiles(id),
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (evidence_id, object_type, object_id),
  FOREIGN KEY (evidence_id, engagement_id) REFERENCES public.evidence_items(id, engagement_id) ON DELETE CASCADE
);

CREATE TABLE public.review_notes (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  engagement_id uuid NOT NULL,
  object_type   text NOT NULL CHECK (object_type IN ('engagement','workpaper','procedure','engagement_risk')),
  object_id     uuid NOT NULL,
  body          text NOT NULL CHECK (length(trim(body)) > 0),
  author_id     uuid NOT NULL REFERENCES public.profiles(id),
  assigned_to   uuid REFERENCES public.profiles(id),
  status        text NOT NULL DEFAULT 'open' CHECK (status IN ('open','answered','closed')),
  response      text,
  responded_by  uuid REFERENCES public.profiles(id),
  responded_at  timestamptz,
  closed_by     uuid REFERENCES public.profiles(id),
  closed_at     timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (engagement_id, organization_id) REFERENCES public.engagements(id, organization_id) ON DELETE CASCADE,
  CHECK (status = 'open' OR response IS NOT NULL OR status = 'closed'),
  CHECK (status <> 'closed' OR (closed_by IS NOT NULL AND closed_at IS NOT NULL))
);
CREATE INDEX review_notes_object_idx ON public.review_notes (engagement_id, object_type, object_id, status);

CREATE TABLE public.signoffs (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  engagement_id  uuid NOT NULL,
  object_type    text NOT NULL CHECK (object_type IN ('workpaper','engagement')),
  object_id      uuid NOT NULL,
  signoff_role   text NOT NULL CHECK (signoff_role IN ('preparer','reviewer','quality_reviewer','approver')),
  user_id        uuid NOT NULL REFERENCES public.profiles(id),
  member_role    text NOT NULL,                  -- rôle de mission au moment de la signature
  content_hash   text NOT NULL,
  signed_at      timestamptz NOT NULL DEFAULT now(),
  revoked_at     timestamptz,
  revoked_reason text,
  FOREIGN KEY (engagement_id, organization_id) REFERENCES public.engagements(id, organization_id) ON DELETE CASCADE,
  CHECK ((revoked_at IS NULL) = (revoked_reason IS NULL))
);
CREATE UNIQUE INDEX signoffs_active_uniq ON public.signoffs (object_type, object_id, signoff_role) WHERE revoked_at IS NULL;

-- ---------------------------------------------------------------------
-- 5. Règles
-- ---------------------------------------------------------------------
-- Empreinte du contenu d'une feuille de travail (ce qui est signé)
CREATE OR REPLACE FUNCTION public.workpaper_hash(w public.workpapers) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
  SELECT encode(sha256(convert_to(concat_ws(E'\x1f', w.reference, w.title, coalesce(w.objective, ''),
           coalesce(w.work_performed, ''), coalesce(w.conclusion, ''), w.content::text,
           coalesce(w.procedure_id::text, '')), 'UTF8')), 'hex')
$$;

-- Dossier figé quand la mission est émise ou archivée
CREATE OR REPLACE FUNCTION public.guard_dossier_open() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE v_status text;
BEGIN
  SELECT status INTO v_status FROM public.engagements
   WHERE id = (to_jsonb(coalesce(NEW, OLD)) ->> 'engagement_id')::uuid;
  IF v_status IN ('issued','archived') THEN
    RAISE EXCEPTION 'Mission % : dossier figé', v_status USING ERRCODE = 'check_violation';
  END IF;
  RETURN coalesce(NEW, OLD);
END $$;
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['engagement_risks','work_programs','procedures','procedure_risks','workpapers',
                           'evidence_items','evidence_links','review_notes'] LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE INSERT OR UPDATE OR DELETE ON public.%I
                    FOR EACH ROW EXECUTE FUNCTION public.guard_dossier_open()', t || '_dossier_open', t);
  END LOOP;
END $$;

-- Feuilles : empreinte recalculée ; toute modification après signature révoque les signatures
CREATE OR REPLACE FUNCTION public.guard_workpaper() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status <> 'draft' OR EXISTS (SELECT 1 FROM public.signoffs WHERE object_type = 'workpaper'
                                          AND object_id = OLD.id AND revoked_at IS NULL) THEN
      RAISE EXCEPTION 'Feuille signée : suppression impossible' USING ERRCODE = 'check_violation';
    END IF;
    RETURN OLD;
  END IF;
  IF TG_OP = 'INSERT' THEN
    NEW.status := 'draft';
    NEW.version := 1;
    NEW.content_hash := public.workpaper_hash(NEW);
    RETURN NEW;
  END IF;
  NEW.content_hash := public.workpaper_hash(NEW);
  IF NEW.content_hash <> OLD.content_hash THEN
    NEW.version := OLD.version + 1;
    IF OLD.status <> 'draft' THEN
      PERFORM set_config('kofinex.system_revoke', 'on', true);
      UPDATE public.signoffs SET revoked_at = now(), revoked_reason = 'Contenu modifié après signature'
       WHERE object_type = 'workpaper' AND object_id = OLD.id AND revoked_at IS NULL;
      PERFORM set_config('kofinex.system_revoke', 'off', true);
      NEW.status := 'draft';
      RETURN NEW;
    END IF;
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status AND coalesce(current_setting('kofinex.signoff', true), 'off') <> 'on' THEN
    RAISE EXCEPTION 'Le statut d''une feuille résulte des signatures ; il ne se modifie pas directement'
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER workpapers_guard BEFORE INSERT OR UPDATE OR DELETE ON public.workpapers
  FOR EACH ROW EXECUTE FUNCTION public.guard_workpaper();

-- Signatures : humain authentifié, membre actif, séparation préparation / revue, ordre imposé
CREATE OR REPLACE FUNCTION public.apply_signoff() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
  v_role   text;
  v_wp     public.workpapers;
  v_eng    public.engagements;
  v_prep   public.signoffs;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Une signature ne se supprime pas (elle peut être révoquée)' USING ERRCODE = 'check_violation';
  END IF;
  IF TG_OP = 'UPDATE' THEN
    IF (NEW.object_type, NEW.object_id, NEW.signoff_role, NEW.user_id, NEW.content_hash, NEW.signed_at, NEW.member_role)
       IS DISTINCT FROM (OLD.object_type, OLD.object_id, OLD.signoff_role, OLD.user_id, OLD.content_hash, OLD.signed_at,
                         OLD.member_role) OR OLD.revoked_at IS NOT NULL THEN
      RAISE EXCEPTION 'Une signature n''est pas modifiable' USING ERRCODE = 'check_violation';
    END IF;
    IF coalesce(current_setting('kofinex.system_revoke', true), 'off') <> 'on'
       AND auth.uid() IS DISTINCT FROM OLD.user_id
       AND NOT authz.has_engagement_role(OLD.engagement_id, ARRAY['partner','manager']) THEN
      RAISE EXCEPTION 'Révocation : par le signataire, le manager ou l''associé' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF length(trim(coalesce(NEW.revoked_reason, ''))) = 0 THEN
      RAISE EXCEPTION 'Motif de révocation obligatoire' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
  END IF;

  IF auth.uid() IS NULL OR NEW.user_id IS DISTINCT FROM auth.uid() THEN
    RAISE EXCEPTION 'Une signature est apposée par l''utilisateur authentifié lui-même' USING ERRCODE = 'insufficient_privilege';
  END IF;
  SELECT * INTO v_eng FROM public.engagements WHERE id = NEW.engagement_id;
  IF v_eng.status IN ('issued','archived') THEN
    RAISE EXCEPTION 'Mission % : dossier figé', v_eng.status USING ERRCODE = 'check_violation';
  END IF;
  SELECT role INTO v_role FROM public.engagement_members
   WHERE engagement_id = NEW.engagement_id AND user_id = NEW.user_id
     AND independence_confirmed_at IS NOT NULL;
  IF v_role IS NULL THEN
    RAISE EXCEPTION 'Signature réservée aux membres de la mission ayant confirmé leur indépendance'
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  NEW.member_role := v_role;
  NEW.signed_at := now();
  NEW.revoked_at := NULL;
  NEW.revoked_reason := NULL;
  NEW.organization_id := v_eng.organization_id;

  IF NEW.object_type = 'engagement' THEN
    IF NEW.object_id <> NEW.engagement_id THEN RAISE EXCEPTION 'Objet incohérent' USING ERRCODE = 'check_violation'; END IF;
    IF NEW.signoff_role = 'quality_reviewer' AND v_role <> 'quality_reviewer' THEN
      RAISE EXCEPTION 'Revue qualité : réservée au réviseur qualité de la mission' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.signoff_role = 'approver' AND v_role <> 'partner' THEN
      RAISE EXCEPTION 'Approbation de la mission : réservée à l''associé' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.signoff_role NOT IN ('quality_reviewer','approver') THEN
      RAISE EXCEPTION 'Signature de mission : revue qualité ou approbation uniquement' USING ERRCODE = 'check_violation';
    END IF;
    IF v_eng.status <> 'reporting' THEN
      RAISE EXCEPTION 'La mission se signe en phase de rapport' USING ERRCODE = 'check_violation';
    END IF;
    NEW.content_hash := encode(sha256(convert_to(v_eng.id::text || v_eng.status || v_eng.updated_at::text, 'UTF8')), 'hex');
    RETURN NEW;
  END IF;

  SELECT * INTO v_wp FROM public.workpapers WHERE id = NEW.object_id AND engagement_id = NEW.engagement_id;
  IF v_wp.id IS NULL THEN RAISE EXCEPTION 'Feuille introuvable' USING ERRCODE = 'check_violation'; END IF;
  NEW.content_hash := v_wp.content_hash;     -- l'empreinte signée est celle de la base, jamais celle du client
  SELECT * INTO v_prep FROM public.signoffs WHERE object_type = 'workpaper' AND object_id = v_wp.id
     AND signoff_role = 'preparer' AND revoked_at IS NULL;

  IF NEW.signoff_role = 'preparer' THEN
    IF v_role NOT IN ('partner','manager','in_charge','staff') THEN
      RAISE EXCEPTION 'Préparation : réservée à l''équipe d''audit' USING ERRCODE = 'insufficient_privilege';
    END IF;
    PERFORM set_config('kofinex.signoff', 'on', true);
    UPDATE public.workpapers SET status = 'prepared' WHERE id = v_wp.id;
  ELSIF NEW.signoff_role = 'reviewer' THEN
    IF v_prep.id IS NULL THEN RAISE EXCEPTION 'La feuille doit d''abord être signée par son préparateur' USING ERRCODE = 'check_violation'; END IF;
    IF v_prep.user_id = NEW.user_id THEN
      RAISE EXCEPTION 'Séparation des tâches : le réviseur doit être différent du préparateur' USING ERRCODE = 'check_violation';
    END IF;
    IF v_role NOT IN ('partner','manager','in_charge') OR (v_prep.member_role = 'in_charge' AND v_role = 'in_charge')
       OR (v_prep.member_role IN ('manager','partner') AND v_role = 'in_charge') THEN
      RAISE EXCEPTION 'Revue : le réviseur doit avoir un rôle supérieur à celui du préparateur' USING ERRCODE = 'insufficient_privilege';
    END IF;
    PERFORM set_config('kofinex.signoff', 'on', true);
    UPDATE public.workpapers SET status = 'reviewed' WHERE id = v_wp.id;
  ELSIF NEW.signoff_role = 'approver' THEN
    IF v_role NOT IN ('partner','manager') THEN
      RAISE EXCEPTION 'Approbation : réservée au manager ou à l''associé' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.signoffs WHERE object_type = 'workpaper' AND object_id = v_wp.id
                     AND signoff_role = 'reviewer' AND revoked_at IS NULL) THEN
      RAISE EXCEPTION 'La feuille doit d''abord être revue' USING ERRCODE = 'check_violation';
    END IF;
    IF v_prep.user_id = NEW.user_id THEN
      RAISE EXCEPTION 'Séparation des tâches : l''approbateur doit être différent du préparateur' USING ERRCODE = 'check_violation';
    END IF;
    IF EXISTS (SELECT 1 FROM public.review_notes WHERE object_type = 'workpaper' AND object_id = v_wp.id
                 AND status <> 'closed') THEN
      RAISE EXCEPTION 'Des notes de revue sont encore ouvertes sur cette feuille' USING ERRCODE = 'check_violation';
    END IF;
    PERFORM set_config('kofinex.signoff', 'on', true);
    UPDATE public.workpapers SET status = 'approved' WHERE id = v_wp.id;
  ELSE   -- revue qualité d'une feuille : sans effet sur son statut
    IF v_role <> 'quality_reviewer' THEN
      RAISE EXCEPTION 'Revue qualité : réservée au réviseur qualité' USING ERRCODE = 'insufficient_privilege';
    END IF;
  END IF;
  PERFORM set_config('kofinex.signoff', 'off', true);
  RETURN NEW;
END $$;
CREATE TRIGGER signoffs_apply BEFORE INSERT OR UPDATE OR DELETE ON public.signoffs
  FOR EACH ROW EXECUTE FUNCTION public.apply_signoff();

-- Révocation par le signataire : statut de la feuille recalculé
CREATE OR REPLACE FUNCTION public.after_signoff_revoked() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
  v_status text;
  v_prev   text := coalesce(current_setting('kofinex.system_revoke', true), 'off');
BEGIN
  IF NEW.object_type <> 'workpaper' OR OLD.revoked_at IS NOT NULL OR NEW.revoked_at IS NULL THEN RETURN NEW; END IF;
  -- révocation déclenchée par la modification de la feuille elle-même : la feuille repasse en brouillon seule
  IF NEW.revoked_reason = 'Contenu modifié après signature' THEN RETURN NEW; END IF;
  -- une signature révoquée invalide celles qui en dépendent
  PERFORM set_config('kofinex.system_revoke', 'on', true);
  IF NEW.signoff_role = 'preparer' THEN
    UPDATE public.signoffs SET revoked_at = now(), revoked_reason = 'Préparation révoquée'
     WHERE object_type = 'workpaper' AND object_id = NEW.object_id AND revoked_at IS NULL AND signoff_role IN ('reviewer','approver');
  ELSIF NEW.signoff_role = 'reviewer' THEN
    UPDATE public.signoffs SET revoked_at = now(), revoked_reason = 'Revue révoquée'
     WHERE object_type = 'workpaper' AND object_id = NEW.object_id AND revoked_at IS NULL AND signoff_role = 'approver';
  END IF;
  PERFORM set_config('kofinex.system_revoke', v_prev, true);
  SELECT CASE
           WHEN bool_or(signoff_role = 'approver') THEN 'approved'
           WHEN bool_or(signoff_role = 'reviewer') THEN 'reviewed'
           WHEN bool_or(signoff_role = 'preparer') THEN 'prepared'
           ELSE 'draft' END
    INTO v_status
    FROM public.signoffs WHERE object_type = 'workpaper' AND object_id = NEW.object_id AND revoked_at IS NULL
     AND signoff_role <> 'quality_reviewer';
  PERFORM set_config('kofinex.signoff', 'on', true);
  UPDATE public.workpapers SET status = coalesce(v_status, 'draft')
   WHERE id = NEW.object_id AND status <> coalesce(v_status, 'draft');
  PERFORM set_config('kofinex.signoff', 'off', true);
  RETURN NEW;
END $$;
CREATE TRIGGER signoffs_revoked AFTER UPDATE ON public.signoffs
  FOR EACH ROW EXECUTE FUNCTION public.after_signoff_revoked();

-- Notes de revue : qui écrit quoi
CREATE OR REPLACE FUNCTION public.guard_review_note() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_role text;
BEGIN
  SELECT role INTO v_role FROM public.engagement_members WHERE engagement_id = coalesce(NEW.engagement_id, OLD.engagement_id)
     AND user_id = auth.uid() AND independence_confirmed_at IS NOT NULL;
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Une note de revue ne se supprime pas (elle se clôt)' USING ERRCODE = 'check_violation';
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.author_id IS DISTINCT FROM auth.uid() OR coalesce(v_role, '') NOT IN ('partner','manager','in_charge','quality_reviewer') THEN
      RAISE EXCEPTION 'Notes de revue : rédigées par un réviseur de la mission, en son nom' USING ERRCODE = 'insufficient_privilege';
    END IF;
    NEW.status := 'open';
    NEW.response := NULL; NEW.responded_by := NULL; NEW.responded_at := NULL; NEW.closed_by := NULL; NEW.closed_at := NULL;
    RETURN NEW;
  END IF;
  IF (NEW.body, NEW.object_type, NEW.object_id, NEW.author_id) IS DISTINCT FROM (OLD.body, OLD.object_type, OLD.object_id, OLD.author_id) THEN
    RAISE EXCEPTION 'Le texte d''une note de revue n''est pas modifiable' USING ERRCODE = 'check_violation';
  END IF;
  IF OLD.status = 'closed' THEN RAISE EXCEPTION 'Note close' USING ERRCODE = 'check_violation'; END IF;
  IF NEW.status = 'answered' THEN
    IF v_role IS NULL OR v_role IN ('observer','auditee') OR length(trim(coalesce(NEW.response, ''))) = 0 THEN
      RAISE EXCEPTION 'Réponse : par un membre de l''équipe, texte obligatoire' USING ERRCODE = 'check_violation';
    END IF;
    NEW.responded_by := auth.uid(); NEW.responded_at := now();
  ELSIF NEW.status = 'closed' THEN
    IF auth.uid() IS DISTINCT FROM OLD.author_id AND coalesce(v_role, '') NOT IN ('partner','manager') THEN
      RAISE EXCEPTION 'Clôture : par l''auteur de la note, le manager ou l''associé' USING ERRCODE = 'insufficient_privilege';
    END IF;
    NEW.closed_by := auth.uid(); NEW.closed_at := now();
  ELSIF NEW.status = 'open' AND OLD.status = 'answered' THEN
    IF auth.uid() IS DISTINCT FROM OLD.author_id THEN
      RAISE EXCEPTION 'Seul l''auteur peut rouvrir sa note' USING ERRCODE = 'insufficient_privilege';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER review_notes_guard BEFORE INSERT OR UPDATE OR DELETE ON public.review_notes
  FOR EACH ROW EXECUTE FUNCTION public.guard_review_note();

-- Éléments probants : immuables (seuls titre et description évoluent) ; liens figés sur feuille signée
CREATE OR REPLACE FUNCTION public.guard_evidence() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF TG_TABLE_NAME = 'evidence_items' THEN
    IF TG_OP = 'INSERT' THEN
      IF auth.uid() IS NULL OR NEW.uploaded_by IS DISTINCT FROM auth.uid() THEN
        RAISE EXCEPTION 'Élément probant : déposé au nom de l''utilisateur authentifié' USING ERRCODE = 'insufficient_privilege';
      END IF;
      RETURN NEW;
    END IF;
    IF TG_OP = 'UPDATE' THEN
      IF (NEW.kind, NEW.storage_path, NEW.sha256, NEW.snapshot, NEW.size_bytes, NEW.mime_type, NEW.original_filename,
          NEW.uploaded_by, NEW.engagement_id, NEW.source, NEW.obtained_on)
         IS DISTINCT FROM (OLD.kind, OLD.storage_path, OLD.sha256, OLD.snapshot, OLD.size_bytes, OLD.mime_type,
          OLD.original_filename, OLD.uploaded_by, OLD.engagement_id, OLD.source, OLD.obtained_on) THEN
        RAISE EXCEPTION 'Élément probant : contenu immuable (déposez une nouvelle version)' USING ERRCODE = 'check_violation';
      END IF;
      RETURN NEW;
    END IF;
    IF EXISTS (SELECT 1 FROM public.evidence_links l JOIN public.signoffs s
                 ON s.object_type = 'workpaper' AND s.object_id = l.object_id AND s.revoked_at IS NULL
                WHERE l.evidence_id = OLD.id AND l.object_type = 'workpaper') THEN
      RAISE EXCEPTION 'Élément rattaché à une feuille signée : suppression impossible' USING ERRCODE = 'check_violation';
    END IF;
    RETURN OLD;
  END IF;
  -- evidence_links
  IF coalesce(NEW.object_type, OLD.object_type) = 'workpaper' AND EXISTS (
       SELECT 1 FROM public.workpapers WHERE id = coalesce(NEW.object_id, OLD.object_id) AND status <> 'draft') THEN
    RAISE EXCEPTION 'Feuille signée : modifiez-la (signatures révoquées) avant de changer ses éléments probants'
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN coalesce(NEW, OLD);
END $$;
CREATE TRIGGER evidence_items_guard BEFORE INSERT OR UPDATE OR DELETE ON public.evidence_items
  FOR EACH ROW EXECUTE FUNCTION public.guard_evidence();
CREATE TRIGGER evidence_links_guard BEFORE INSERT OR UPDATE OR DELETE ON public.evidence_links
  FOR EACH ROW EXECUTE FUNCTION public.guard_evidence();

-- Procédures : l'affecté est membre de l'équipe
CREATE OR REPLACE FUNCTION public.guard_procedure() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF NEW.assigned_to IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM public.engagement_members WHERE engagement_id = NEW.engagement_id AND user_id = NEW.assigned_to
          AND role IN ('partner','manager','in_charge','staff')) THEN
    RAISE EXCEPTION 'Procédure affectée à une personne hors de l''équipe d''audit' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER procedures_assignee BEFORE INSERT OR UPDATE ON public.procedures
  FOR EACH ROW EXECUTE FUNCTION public.guard_procedure();

-- Mission : circuit, rôles, conditions d'émission, gel, réouverture motivée
CREATE OR REPLACE FUNCTION public.guard_engagement() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
  v_role text;
  v_meth public.methodology_versions;
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status <> 'planning' OR EXISTS (SELECT 1 FROM public.workpapers WHERE engagement_id = OLD.id)
       OR EXISTS (SELECT 1 FROM public.evidence_items WHERE engagement_id = OLD.id) THEN
      RAISE EXCEPTION 'Seule une mission en planification, sans feuille ni élément probant, peut être supprimée'
        USING ERRCODE = 'check_violation';
    END IF;
    RETURN OLD;
  END IF;
  IF NEW.methodology_version_id IS NOT NULL AND (TG_OP = 'INSERT'
       OR NEW.methodology_version_id IS DISTINCT FROM OLD.methodology_version_id) THEN
    IF TG_OP = 'UPDATE' AND OLD.status <> 'planning' THEN
      RAISE EXCEPTION 'La méthodologie se choisit en planification' USING ERRCODE = 'check_violation';
    END IF;
    SELECT * INTO v_meth FROM public.methodology_versions WHERE id = NEW.methodology_version_id;
    IF v_meth.status <> 'published' OR (v_meth.organization_id IS NOT NULL AND v_meth.organization_id <> NEW.organization_id) THEN
      RAISE EXCEPTION 'Méthodologie non publiée ou d''une autre organisation' USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  IF TG_OP = 'INSERT' THEN
    NEW.status := 'planning';
    RETURN NEW;
  END IF;

  v_role := authz.engagement_role(OLD.id);
  IF NEW.status IS DISTINCT FROM OLD.status THEN
    IF NOT authz.has_engagement_role(OLD.id, ARRAY['partner','manager','in_charge']) THEN
      RAISE EXCEPTION 'Changement de phase réservé à l''équipe d''encadrement (indépendance confirmée)'
        USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF (OLD.status, NEW.status) IN (('planning','fieldwork'), ('review','reporting'), ('reporting','review'))
       AND v_role NOT IN ('partner','manager') THEN
      RAISE EXCEPTION 'Transition réservée au manager ou à l''associé' USING ERRCODE = 'insufficient_privilege';
    ELSIF (OLD.status, NEW.status) IN (('fieldwork','review'), ('review','fieldwork')) THEN
      NULL;
    ELSIF (OLD.status, NEW.status) = ('reporting','issued') THEN
      IF v_role <> 'partner' THEN
        RAISE EXCEPTION 'Émission réservée à l''associé' USING ERRCODE = 'insufficient_privilege';
      END IF;
      IF EXISTS (SELECT 1 FROM public.workpapers WHERE engagement_id = OLD.id AND status <> 'approved') THEN
        RAISE EXCEPTION 'Toutes les feuilles de travail doivent être approuvées' USING ERRCODE = 'check_violation';
      END IF;
      IF EXISTS (SELECT 1 FROM public.review_notes WHERE engagement_id = OLD.id AND status <> 'closed') THEN
        RAISE EXCEPTION 'Des notes de revue sont encore ouvertes' USING ERRCODE = 'check_violation';
      END IF;
      IF EXISTS (SELECT 1 FROM public.engagement_members WHERE engagement_id = OLD.id AND role = 'quality_reviewer')
         AND NOT EXISTS (SELECT 1 FROM public.signoffs WHERE object_type = 'engagement' AND object_id = OLD.id
                           AND signoff_role = 'quality_reviewer' AND revoked_at IS NULL) THEN
        RAISE EXCEPTION 'La revue qualité de la mission n''est pas signée' USING ERRCODE = 'check_violation';
      END IF;
      IF NOT EXISTS (SELECT 1 FROM public.signoffs WHERE object_type = 'engagement' AND object_id = OLD.id
                       AND signoff_role = 'approver' AND revoked_at IS NULL) THEN
        RAISE EXCEPTION 'La mission doit être approuvée (signée) par l''associé avant émission' USING ERRCODE = 'check_violation';
      END IF;
      NEW.issued_at := now();
      NEW.issued_by := auth.uid();
    ELSIF (OLD.status, NEW.status) = ('issued','archived') THEN
      IF v_role NOT IN ('partner','manager') THEN
        RAISE EXCEPTION 'Archivage réservé au manager ou à l''associé' USING ERRCODE = 'insufficient_privilege';
      END IF;
      NEW.archived_at := now();
    ELSIF (OLD.status, NEW.status) IN (('archived','reporting'), ('issued','reporting')) THEN
      IF v_role <> 'partner' OR length(trim(coalesce(NEW.reopen_reason, ''))) < 10 THEN
        RAISE EXCEPTION 'Réouverture : par l''associé, avec un motif explicite' USING ERRCODE = 'check_violation';
      END IF;
      NEW.reopened_at := now();
      NEW.reopened_by := auth.uid();
      NEW.issued_at := NULL;
      NEW.issued_by := NULL;
      NEW.archived_at := NULL;
      PERFORM set_config('kofinex.system_revoke', 'on', true);
      UPDATE public.signoffs SET revoked_at = now(), revoked_reason = 'Mission rouverte'
       WHERE object_type = 'engagement' AND object_id = OLD.id AND revoked_at IS NULL;
      PERFORM set_config('kofinex.system_revoke', 'off', true);
    ELSIF NOT ((OLD.status, NEW.status) IN (('planning','fieldwork'), ('review','reporting'), ('reporting','review'))) THEN
      RAISE EXCEPTION 'Transition interdite : % → %', OLD.status, NEW.status USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.status IN ('issued','archived') AND (NEW.name, NEW.reference, NEW.objectives, NEW.scope, NEW.period_start,
      NEW.period_end, NEW.planned_start, NEW.planned_end, NEW.fiscal_year_id, NEW.engagement_type, NEW.company_id)
      IS DISTINCT FROM (OLD.name, OLD.reference, OLD.objectives, OLD.scope, OLD.period_start, OLD.period_end,
                        OLD.planned_start, OLD.planned_end, OLD.fiscal_year_id, OLD.engagement_type, OLD.company_id) THEN
    RAISE EXCEPTION 'Mission % : figée', OLD.status USING ERRCODE = 'check_violation';
  END IF;
  IF (NEW.engagement_type, NEW.company_id) IS DISTINCT FROM (OLD.engagement_type, OLD.company_id) THEN
    RAISE EXCEPTION 'Le type et l''entité d''une mission ne changent pas' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER engagements_guard BEFORE INSERT OR UPDATE OR DELETE ON public.engagements
  FOR EACH ROW EXECUTE FUNCTION public.guard_engagement();

-- Une signature de mission devient caduque si l'on revient en revue
CREATE OR REPLACE FUNCTION public.engagement_back_to_review() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF OLD.status = 'reporting' AND NEW.status = 'review' THEN
    PERFORM set_config('kofinex.system_revoke', 'on', true);
    UPDATE public.signoffs SET revoked_at = now(), revoked_reason = 'Retour en revue'
     WHERE object_type = 'engagement' AND object_id = NEW.id AND revoked_at IS NULL;
    PERFORM set_config('kofinex.system_revoke', 'off', true);
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER engagements_back_to_review AFTER UPDATE ON public.engagements
  FOR EACH ROW EXECUTE FUNCTION public.engagement_back_to_review();

-- updated_at
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['methodology_versions','processes','risks','engagements','engagement_members',
                           'engagement_risks','work_programs','procedures','workpapers','review_notes'] LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.set_updated_at()',
                   t || '_updated_at', t);
  END LOOP;
END $$;

-- ---------------------------------------------------------------------
-- 6. RLS
-- ---------------------------------------------------------------------
ALTER TABLE public.methodology_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.methodology_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY methodology_versions_select ON public.methodology_versions FOR SELECT TO authenticated
  USING (organization_id IS NULL OR authz.is_org_member(organization_id) OR authz.is_platform_admin());
CREATE POLICY methodology_versions_write ON public.methodology_versions FOR ALL TO authenticated
  USING ((organization_id IS NULL AND authz.is_platform_admin())
         OR (organization_id IS NOT NULL AND authz.has_org_role(organization_id, ARRAY['owner','admin'])))
  WITH CHECK ((organization_id IS NULL AND authz.is_platform_admin())
              OR (organization_id IS NOT NULL AND authz.has_org_role(organization_id, ARRAY['owner','admin'])));
CREATE POLICY methodology_items_select ON public.methodology_items FOR SELECT TO authenticated
  USING (EXISTS (SELECT 1 FROM public.methodology_versions v WHERE v.id = version_id));
CREATE POLICY methodology_items_write ON public.methodology_items FOR ALL TO authenticated
  USING (EXISTS (SELECT 1 FROM public.methodology_versions v WHERE v.id = version_id AND
           ((v.organization_id IS NULL AND authz.is_platform_admin())
            OR (v.organization_id IS NOT NULL AND authz.has_org_role(v.organization_id, ARRAY['owner','admin'])))))
  WITH CHECK (EXISTS (SELECT 1 FROM public.methodology_versions v WHERE v.id = version_id AND
           ((v.organization_id IS NULL AND authz.is_platform_admin())
            OR (v.organization_id IS NOT NULL AND authz.has_org_role(v.organization_id, ARRAY['owner','admin'])))));

ALTER TABLE public.processes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.risks ENABLE ROW LEVEL SECURITY;
CREATE POLICY processes_select ON public.processes FOR SELECT TO authenticated USING (authz.can_access_company(company_id));
CREATE POLICY processes_write ON public.processes FOR ALL TO authenticated
  USING (authz.has_company_role(company_id, ARRAY['auditor'])) WITH CHECK (authz.has_company_role(company_id, ARRAY['auditor']));
CREATE POLICY risks_select ON public.risks FOR SELECT TO authenticated USING (authz.can_access_company(company_id));
CREATE POLICY risks_write ON public.risks FOR ALL TO authenticated
  USING (authz.has_company_role(company_id, ARRAY['auditor'])) WITH CHECK (authz.has_company_role(company_id, ARRAY['auditor']));

ALTER TABLE public.engagements ENABLE ROW LEVEL SECURITY;
-- en-tête visible par les membres de la mission et par les administrateurs (staffing) ; le dossier, non
CREATE POLICY engagements_select ON public.engagements FOR SELECT TO authenticated
  USING (authz.engagement_role(id) IS NOT NULL OR authz.has_org_role(organization_id, ARRAY['owner','admin'])
         OR created_by = auth.uid());
CREATE POLICY engagements_insert ON public.engagements FOR INSERT TO authenticated
  WITH CHECK (created_by = auth.uid() AND authz.can_access_company(company_id)
              AND (authz.has_org_role(organization_id, ARRAY['owner','admin'])
                   OR authz.has_company_role(company_id, ARRAY['auditor'])));
CREATE POLICY engagements_update ON public.engagements FOR UPDATE TO authenticated
  USING (authz.has_engagement_role(id, ARRAY['partner','manager','in_charge']))
  WITH CHECK (authz.has_engagement_role(id, ARRAY['partner','manager','in_charge']));
CREATE POLICY engagements_delete ON public.engagements FOR DELETE TO authenticated
  USING (authz.has_engagement_role(id, ARRAY['partner','manager']));

ALTER TABLE public.engagement_members ENABLE ROW LEVEL SECURITY;
CREATE POLICY engagement_members_select ON public.engagement_members FOR SELECT TO authenticated
  USING (authz.engagement_role(engagement_id) IS NOT NULL OR authz.has_org_role(organization_id, ARRAY['owner','admin']));
-- composition de l'équipe : manager / associé de la mission, ou administrateurs de l'organisation (tracé au journal)
CREATE POLICY engagement_members_write ON public.engagement_members FOR ALL TO authenticated
  USING (authz.has_engagement_role(engagement_id, ARRAY['partner','manager'])
         OR authz.has_org_role(organization_id, ARRAY['owner','admin']))
  WITH CHECK (authz.has_engagement_role(engagement_id, ARRAY['partner','manager'])
              OR authz.has_org_role(organization_id, ARRAY['owner','admin']));

DO $$
DECLARE spec record;
BEGIN
  FOR spec IN SELECT * FROM (VALUES
      ('engagement_risks', ARRAY['partner','manager','in_charge']),
      ('work_programs',    ARRAY['partner','manager','in_charge']),
      ('procedures',       ARRAY['partner','manager','in_charge','staff']),
      ('procedure_risks',  ARRAY['partner','manager','in_charge']),
      ('workpapers',       ARRAY['partner','manager','in_charge','staff']),
      ('evidence_items',   ARRAY['partner','manager','in_charge','staff']),
      ('evidence_links',   ARRAY['partner','manager','in_charge','staff']),
      ('review_notes',     ARRAY['partner','manager','in_charge','staff','quality_reviewer']),
      ('signoffs',         ARRAY['partner','manager','in_charge','staff','quality_reviewer'])
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
  END LOOP;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.methodology_versions, public.methodology_items, public.processes, public.risks,
  public.engagements, public.engagement_members, public.engagement_risks, public.work_programs, public.procedures,
  public.procedure_risks, public.workpapers, public.evidence_items, public.evidence_links, public.review_notes,
  public.signoffs TO authenticated;
GRANT ALL ON public.methodology_versions, public.methodology_items, public.processes, public.risks, public.engagements,
  public.engagement_members, public.engagement_risks, public.work_programs, public.procedures, public.procedure_risks,
  public.workpapers, public.evidence_items, public.evidence_links, public.review_notes, public.signoffs TO service_role;

-- ---------------------------------------------------------------------
-- 7. Stockage des éléments probants : {organization_id}/{engagement_id}/{fichier}
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION authz.storage_object_engagement(p_name text) RETURNS uuid
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public AS $$
DECLARE
  parts  text[] := string_to_array(p_name, '/');
  result uuid;
BEGIN
  IF coalesce(array_length(parts, 1), 0) < 3 OR authz.try_uuid(parts[1]) IS NULL OR authz.try_uuid(parts[2]) IS NULL
     OR parts[array_length(parts, 1)] = '' THEN
    RETURN NULL;
  END IF;
  SELECT id INTO result FROM public.engagements WHERE id = parts[2]::uuid AND organization_id = parts[1]::uuid;
  RETURN result;
END $$;
REVOKE ALL ON FUNCTION authz.storage_object_engagement(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION authz.storage_object_engagement(text) TO authenticated, service_role;

DO $outer$
BEGIN
  IF to_regclass('storage.buckets') IS NULL OR to_regclass('storage.objects') IS NULL THEN
    RAISE NOTICE 'Schéma storage absent : bucket des éléments probants non créé';
    RETURN;
  END IF;
  INSERT INTO storage.buckets (id, name, public, file_size_limit)
  VALUES ('audit-evidence', 'audit-evidence', false, 52428800)
  ON CONFLICT (id) DO UPDATE SET public = false, file_size_limit = EXCLUDED.file_size_limit;
  -- lecture : équipe d'audit de la mission ; dépôt : par l'API (rôle de service) après contrôle du fichier ;
  -- ni modification ni suppression côté client (originaux immuables)
  EXECUTE $p$
    CREATE POLICY audit_evidence_read ON storage.objects FOR SELECT TO authenticated
      USING (bucket_id = 'audit-evidence' AND authz.can_read_dossier(authz.storage_object_engagement(name)))$p$;
END $outer$;
