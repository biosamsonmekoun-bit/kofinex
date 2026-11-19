-- =====================================================================
-- KOFINEX — Migration 0012 : intelligence artificielle (lot 10)
-- L'IA assiste, elle ne décide pas. Cette migration impose en base :
--   * un « acteur IA » de session (kofinex.actor = 'ai') posé par l'API pendant le traitement d'une réponse du
--     modèle : aucune table métier ne peut alors être écrite, seules les tables ai_* le peuvent ;
--   * les sorties du modèle (messages assistant, commentaires, suggestions) ne s'enregistrent que sous cet acteur,
--     au nom de l'utilisateur qui les a demandées, et ne se modifient jamais ;
--   * les décisions (accepter, rejeter, relire) sont prises par un humain authentifié, hors acteur IA ;
--   * un objet issu d'une suggestion (risque, procédure, constat) porte sa provenance, naît en brouillon, sans
--     cotation ni attribution, et seulement après acceptation par la personne qui le crée ;
--   * l'activation de l'IA est un choix explicite de l'organisation, usage par usage.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. Acteur IA
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.ai_actor() RETURNS boolean
LANGUAGE sql STABLE AS $$ SELECT coalesce(current_setting('kofinex.actor', true), '') = 'ai' $$;

CREATE OR REPLACE FUNCTION public.guard_not_ai() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF public.ai_actor() THEN
    RAISE EXCEPTION 'IA : écriture interdite dans « % » (l''IA propose, un humain décide)', TG_TABLE_NAME
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN coalesce(NEW, OLD);
END $$;

-- ---------------------------------------------------------------------
-- 2. Réglages IA de l'organisation (désactivée par défaut)
-- ---------------------------------------------------------------------
CREATE TABLE public.ai_settings (
  organization_id uuid PRIMARY KEY REFERENCES public.organizations(id) ON DELETE CASCADE,
  enabled         boolean NOT NULL DEFAULT false,
  allowed_uses    text[] NOT NULL DEFAULT '{}' CHECK (allowed_uses <@ ARRAY['finance_assistant','analysis_commentary',
                    'audit_risks','audit_procedures','anomaly_explanation','drafting']::text[]),
  -- motif de l'activation : transmission de données à un fournisseur externe acceptée par l'organisation
  acceptance_note text,
  updated_by      uuid NOT NULL REFERENCES public.profiles(id),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CHECK (NOT enabled OR length(trim(coalesce(acceptance_note, ''))) >= 10)
);

CREATE OR REPLACE FUNCTION public.guard_ai_settings() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Réglages IA : désactivez l''IA plutôt que de supprimer les réglages' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.updated_by IS DISTINCT FROM auth.uid() THEN
    RAISE EXCEPTION 'Réglages IA : modifiés au nom de l''utilisateur authentifié' USING ERRCODE = 'insufficient_privilege';
  END IF;
  NEW.updated_at := now();
  RETURN NEW;
END $$;
CREATE TRIGGER ai_settings_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ai_settings
  FOR EACH ROW EXECUTE FUNCTION public.guard_ai_settings();

CREATE OR REPLACE FUNCTION public.ai_allowed(p_org uuid, p_use text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT EXISTS (SELECT 1 FROM public.ai_settings s WHERE s.organization_id = p_org AND s.enabled AND p_use = ANY (s.allowed_uses))
$$;
REVOKE ALL ON FUNCTION public.ai_allowed(uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.ai_allowed(uuid, text) TO authenticated, service_role;

-- ---------------------------------------------------------------------
-- 3. Conversations et messages : sorties du modèle sous l'acteur IA, jamais modifiées
-- ---------------------------------------------------------------------
ALTER TABLE public.ai_conversations ADD COLUMN purpose text NOT NULL DEFAULT 'finance_assistant'
  CHECK (purpose IN ('finance_assistant'));
ALTER TABLE public.ai_messages ADD COLUMN prompt_version text;

CREATE OR REPLACE FUNCTION public.guard_ai_conversation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF public.ai_actor() THEN
      RAISE EXCEPTION 'Conversation : ouverte par l''utilisateur, pas par l''IA' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NOT public.ai_allowed(NEW.organization_id, NEW.purpose) THEN
      RAISE EXCEPTION 'IA non activée pour cet usage dans l''organisation' USING ERRCODE = 'check_violation';
    END IF;
  ELSIF TG_OP = 'UPDATE' THEN
    IF (NEW.organization_id, NEW.company_id, NEW.user_id, NEW.purpose, NEW.created_at)
       IS DISTINCT FROM (OLD.organization_id, OLD.company_id, OLD.user_id, OLD.purpose, OLD.created_at) THEN
      RAISE EXCEPTION 'Conversation : seuls le titre, l''exercice et l''analyse de contexte changent' USING ERRCODE = 'check_violation';
    END IF;
    NEW.updated_at := now();
  END IF;
  RETURN coalesce(NEW, OLD);
END $$;
CREATE TRIGGER ai_conversations_guard BEFORE INSERT OR UPDATE ON public.ai_conversations
  FOR EACH ROW EXECUTE FUNCTION public.guard_ai_conversation();

CREATE OR REPLACE FUNCTION public.guard_ai_message() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE c record;
BEGIN
  IF TG_OP <> 'INSERT' THEN
    RAISE EXCEPTION 'Message IA : conservé tel quel (ni modification ni suppression)' USING ERRCODE = 'check_violation';
  END IF;
  SELECT organization_id, user_id, purpose INTO c FROM public.ai_conversations WHERE id = NEW.conversation_id;
  IF c.user_id IS DISTINCT FROM auth.uid() THEN
    RAISE EXCEPTION 'Message : dans une conversation de l''utilisateur authentifié' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF NOT public.ai_allowed(c.organization_id, c.purpose) THEN
    RAISE EXCEPTION 'IA non activée pour cet usage dans l''organisation' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.role = 'assistant' THEN
    IF NOT public.ai_actor() THEN
      RAISE EXCEPTION 'Réponse IA : enregistrée uniquement par le traitement du modèle' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.context_snapshot IS NULL OR NEW.validation IS NULL OR NEW.model IS NULL THEN
      RAISE EXCEPTION 'Réponse IA : contexte transmis, contrôle des chiffres et modèle requis' USING ERRCODE = 'check_violation';
    END IF;
  ELSIF NEW.role = 'user' THEN
    IF public.ai_actor() THEN
      RAISE EXCEPTION 'Question : posée par l''utilisateur, pas par l''IA' USING ERRCODE = 'insufficient_privilege';
    END IF;
  ELSE
    RAISE EXCEPTION 'Message : rôle « % » non enregistré', NEW.role USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER ai_messages_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ai_messages
  FOR EACH ROW EXECUTE FUNCTION public.guard_ai_message();

-- ---------------------------------------------------------------------
-- 4. Commentaires d'analyse (table ai_reports du lot 1) : contenu figé, relu par un humain
-- ---------------------------------------------------------------------
ALTER TABLE public.ai_reports ADD COLUMN review_note text;

CREATE OR REPLACE FUNCTION public.guard_ai_report() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Commentaire IA : conservé (rejetez-le plutôt)' USING ERRCODE = 'check_violation';
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NOT public.ai_actor() THEN
      RAISE EXCEPTION 'Commentaire IA : produit uniquement par le traitement du modèle' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.created_by IS DISTINCT FROM auth.uid() OR NEW.status <> 'draft' OR NEW.reviewed_by IS NOT NULL OR NEW.validation IS NULL THEN
      RAISE EXCEPTION 'Commentaire IA : brouillon au nom du demandeur, avec contrôle des chiffres' USING ERRCODE = 'check_violation';
    END IF;
    IF NOT public.ai_allowed(NEW.organization_id, 'analysis_commentary') THEN
      RAISE EXCEPTION 'IA non activée pour cet usage dans l''organisation' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
  END IF;
  IF public.ai_actor() THEN
    RAISE EXCEPTION 'Commentaire IA : la relecture est humaine' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF (to_jsonb(NEW) - ARRAY['status','reviewed_by','reviewed_at','review_note'])
     IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['status','reviewed_by','reviewed_at','review_note']) THEN
    RAISE EXCEPTION 'Commentaire IA : contenu figé (seule la relecture s''enregistre)' USING ERRCODE = 'check_violation';
  END IF;
  IF OLD.status <> 'draft' OR NEW.status NOT IN ('reviewed','rejected') THEN
    RAISE EXCEPTION 'Commentaire IA : relu une seule fois (brouillon → relu ou rejeté)' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.reviewed_by IS DISTINCT FROM auth.uid() THEN
    RAISE EXCEPTION 'Relecture : au nom de l''utilisateur authentifié' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF NEW.status = 'rejected' AND length(trim(coalesce(NEW.review_note, ''))) < 3 THEN
    RAISE EXCEPTION 'Rejet : motif requis' USING ERRCODE = 'check_violation';
  END IF;
  NEW.reviewed_at := now();
  RETURN NEW;
END $$;
CREATE TRIGGER ai_reports_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ai_reports
  FOR EACH ROW EXECUTE FUNCTION public.guard_ai_report();

-- ---------------------------------------------------------------------
-- 5. Suggestions d'audit
-- ---------------------------------------------------------------------
CREATE TABLE public.ai_suggestions (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id     uuid NOT NULL,
  company_id          uuid NOT NULL,
  engagement_id       uuid NOT NULL,
  kind                text NOT NULL CHECK (kind IN ('engagement_risk','procedure','finding_draft','synthesis_draft',
                                                     'anomaly_explanation')),
  payload             jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),   -- proposition structurée du modèle
  sources             jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(sources) = 'array'),
  context_snapshot    jsonb NOT NULL,      -- données exactement transmises au modèle
  validation          jsonb NOT NULL,      -- contrôle des chiffres et des références
  model               text NOT NULL,
  prompt_version      text NOT NULL,
  input_tokens        int,
  output_tokens       int,
  status              text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','accepted','rejected')),
  requested_by        uuid NOT NULL REFERENCES public.profiles(id),
  decided_by          uuid REFERENCES public.profiles(id),
  decided_at          timestamptz,
  decision_note       text,
  accepted_payload    jsonb,               -- version relue et éventuellement corrigée par l'humain
  created_object_type text CHECK (created_object_type IN ('engagement_risks','procedures','findings')),
  created_object_id   uuid,
  created_at          timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id, engagement_id),
  FOREIGN KEY (engagement_id, organization_id) REFERENCES public.engagements(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  CHECK (status = 'pending' OR (decided_by IS NOT NULL AND decided_at IS NOT NULL)),
  CHECK (status <> 'rejected' OR length(trim(coalesce(decision_note, ''))) >= 3),
  CHECK (created_object_id IS NULL OR status = 'accepted')
);
CREATE INDEX ai_suggestions_engagement_idx ON public.ai_suggestions (engagement_id, created_at DESC);

CREATE OR REPLACE FUNCTION public.ai_use_of(p_kind text) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE p_kind WHEN 'engagement_risk' THEN 'audit_risks' WHEN 'procedure' THEN 'audit_procedures'
                     WHEN 'anomaly_explanation' THEN 'anomaly_explanation' ELSE 'drafting' END
$$;

CREATE OR REPLACE FUNCTION public.guard_ai_suggestion() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE v_company uuid; v_role text;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Suggestion IA : conservée (rejetez-la plutôt)' USING ERRCODE = 'check_violation';
  END IF;
  v_role := authz.engagement_role(NEW.engagement_id);
  IF TG_OP = 'INSERT' THEN
    IF NOT public.ai_actor() THEN
      RAISE EXCEPTION 'Suggestion IA : produite uniquement par le traitement du modèle' USING ERRCODE = 'insufficient_privilege';
    END IF;
    SELECT company_id INTO v_company FROM public.engagements WHERE id = NEW.engagement_id;
    IF NEW.company_id IS DISTINCT FROM v_company THEN
      RAISE EXCEPTION 'Suggestion IA : entité de la mission' USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.requested_by IS DISTINCT FROM auth.uid() OR NEW.status <> 'pending' OR NEW.decided_by IS NOT NULL
       OR NEW.accepted_payload IS NOT NULL OR NEW.created_object_id IS NOT NULL THEN
      RAISE EXCEPTION 'Suggestion IA : en attente, au nom du demandeur' USING ERRCODE = 'check_violation';
    END IF;
    IF NOT authz.has_engagement_role(NEW.engagement_id, ARRAY['partner','manager','in_charge','staff']) THEN
      RAISE EXCEPTION 'Suggestion IA : demandée par un membre de l''équipe de mission' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NOT public.ai_allowed(NEW.organization_id, public.ai_use_of(NEW.kind)) THEN
      RAISE EXCEPTION 'IA non activée pour cet usage dans l''organisation' USING ERRCODE = 'check_violation';
    END IF;
    NEW.created_at := now();
    RETURN NEW;
  END IF;
  -- décision humaine
  IF public.ai_actor() THEN
    RAISE EXCEPTION 'Suggestion IA : la décision est humaine' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF (to_jsonb(NEW) - ARRAY['status','decided_by','decided_at','decision_note','accepted_payload','created_object_type','created_object_id'])
     IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['status','decided_by','decided_at','decision_note','accepted_payload','created_object_type','created_object_id']) THEN
    RAISE EXCEPTION 'Suggestion IA : la proposition, ses sources et son contexte ne changent pas' USING ERRCODE = 'check_violation';
  END IF;
  IF OLD.status = 'pending' THEN
    IF NEW.status NOT IN ('accepted','rejected') THEN
      RAISE EXCEPTION 'Suggestion IA : acceptée ou rejetée' USING ERRCODE = 'check_violation';
    END IF;
    IF NOT authz.has_engagement_role(NEW.engagement_id, ARRAY['partner','manager','in_charge','staff']) THEN
      RAISE EXCEPTION 'Décision : membre de l''équipe de mission' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.decided_by IS DISTINCT FROM auth.uid() THEN
      RAISE EXCEPTION 'Décision : au nom de l''utilisateur authentifié' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.status = 'rejected' AND (NEW.accepted_payload IS NOT NULL OR NEW.created_object_id IS NOT NULL) THEN
      RAISE EXCEPTION 'Suggestion rejetée : rien n''est repris' USING ERRCODE = 'check_violation';
    END IF;
    NEW.decided_at := now();
    RETURN NEW;
  END IF;
  -- après la décision : seul le rattachement de l'objet créé, une fois, par le décideur
  IF OLD.status = 'accepted' AND OLD.created_object_id IS NULL AND NEW.created_object_id IS NOT NULL
     AND (to_jsonb(NEW) - ARRAY['created_object_type','created_object_id'])
         IS NOT DISTINCT FROM (to_jsonb(OLD) - ARRAY['created_object_type','created_object_id'])
     AND OLD.decided_by = auth.uid() THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'Suggestion IA décidée : figée' USING ERRCODE = 'check_violation';
END $$;
CREATE TRIGGER ai_suggestions_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ai_suggestions
  FOR EACH ROW EXECUTE FUNCTION public.guard_ai_suggestion();
CREATE TRIGGER ai_suggestions_dossier_open BEFORE INSERT OR UPDATE OR DELETE ON public.ai_suggestions
  FOR EACH ROW EXECUTE FUNCTION public.guard_dossier_open();

-- ---------------------------------------------------------------------
-- 6. Provenance des objets créés à partir d'une suggestion
-- ---------------------------------------------------------------------
ALTER TABLE public.engagement_risks ADD COLUMN ai_suggestion_id uuid;
ALTER TABLE public.engagement_risks ADD FOREIGN KEY (ai_suggestion_id, engagement_id) REFERENCES public.ai_suggestions(id, engagement_id);
ALTER TABLE public.procedures ADD COLUMN ai_suggestion_id uuid;
ALTER TABLE public.procedures ADD FOREIGN KEY (ai_suggestion_id, engagement_id) REFERENCES public.ai_suggestions(id, engagement_id);
ALTER TABLE public.findings ADD COLUMN origin text NOT NULL DEFAULT 'manual' CHECK (origin IN ('manual','ai_suggestion'));
ALTER TABLE public.findings ADD COLUMN ai_suggestion_id uuid;
ALTER TABLE public.findings ADD FOREIGN KEY (ai_suggestion_id, engagement_id) REFERENCES public.ai_suggestions(id, engagement_id);
ALTER TABLE public.workpapers ADD CONSTRAINT workpapers_no_ai_origin CHECK (origin <> 'ai_suggestion');

CREATE OR REPLACE FUNCTION public.guard_ai_origin() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE s record; v_kind text; j jsonb;
BEGIN
  IF TG_OP = 'UPDATE' THEN
    IF (NEW.origin, NEW.ai_suggestion_id) IS DISTINCT FROM (OLD.origin, OLD.ai_suggestion_id) THEN
      RAISE EXCEPTION 'Provenance : non modifiable' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
  END IF;
  IF NEW.origin IS DISTINCT FROM 'ai_suggestion' THEN
    IF NEW.ai_suggestion_id IS NOT NULL THEN
      RAISE EXCEPTION 'Provenance : une suggestion IA implique l''origine « ai_suggestion »' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
  END IF;
  v_kind := CASE TG_TABLE_NAME WHEN 'engagement_risks' THEN 'engagement_risk' WHEN 'procedures' THEN 'procedure'
                               ELSE 'finding_draft' END;
  SELECT * INTO s FROM public.ai_suggestions WHERE id = NEW.ai_suggestion_id;
  IF s.id IS NULL OR s.engagement_id <> NEW.engagement_id OR s.kind <> v_kind THEN
    RAISE EXCEPTION 'Provenance : suggestion IA de même nature, dans la même mission' USING ERRCODE = 'check_violation';
  END IF;
  IF s.status <> 'accepted' OR s.decided_by IS DISTINCT FROM auth.uid() OR s.created_object_id IS NOT NULL THEN
    RAISE EXCEPTION 'Provenance : suggestion acceptée par vous, pas encore reprise' USING ERRCODE = 'check_violation';
  END IF;
  j := to_jsonb(NEW);
  IF TG_TABLE_NAME = 'engagement_risks'
     AND (j->>'likelihood' IS NOT NULL OR j->>'impact' IS NOT NULL OR coalesce((j->>'is_significant')::boolean, false)) THEN
    RAISE EXCEPTION 'Risque issu de l''IA : la cotation est faite ensuite par l''auditeur' USING ERRCODE = 'check_violation';
  END IF;
  IF TG_TABLE_NAME = 'procedures' AND (j->>'assigned_to' IS NOT NULL OR j->>'status' <> 'not_started') THEN
    RAISE EXCEPTION 'Procédure issue de l''IA : non attribuée et non commencée' USING ERRCODE = 'check_violation';
  END IF;
  IF TG_TABLE_NAME = 'findings' AND j->>'status' <> 'draft' THEN
    RAISE EXCEPTION 'Constat issu de l''IA : brouillon' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER engagement_risks_ai_origin BEFORE INSERT OR UPDATE ON public.engagement_risks
  FOR EACH ROW EXECUTE FUNCTION public.guard_ai_origin();
CREATE TRIGGER procedures_ai_origin BEFORE INSERT OR UPDATE ON public.procedures
  FOR EACH ROW EXECUTE FUNCTION public.guard_ai_origin();
CREATE TRIGGER findings_ai_origin BEFORE INSERT OR UPDATE ON public.findings
  FOR EACH ROW EXECUTE FUNCTION public.guard_ai_origin();

-- ---------------------------------------------------------------------
-- 7. Interdit général : sous l'acteur IA, aucune table métier n'est écrite
-- ---------------------------------------------------------------------
DO $$
DECLARE t text;
BEGIN
  FOR t IN SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'r'
              AND c.relname NOT IN ('ai_conversations','ai_messages','ai_reports','ai_suggestions','ai_settings','audit_logs')
  LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE INSERT OR UPDATE OR DELETE ON public.%I
                    FOR EACH ROW EXECUTE FUNCTION public.guard_not_ai()', '0_not_ai', t);
  END LOOP;
END $$;
-- les nouvelles tables des lots suivants doivent recevoir ce déclencheur (voir docs/IA.md)
DO $$
BEGIN
  IF to_regclass('storage.objects') IS NOT NULL THEN
    EXECUTE 'CREATE TRIGGER "0_not_ai" BEFORE INSERT OR UPDATE OR DELETE ON storage.objects
             FOR EACH ROW EXECUTE FUNCTION public.guard_not_ai()';
  END IF;
END $$;

-- ---------------------------------------------------------------------
-- 8. RLS
-- ---------------------------------------------------------------------
ALTER TABLE public.ai_settings ENABLE ROW LEVEL SECURITY;
CREATE POLICY ai_settings_select ON public.ai_settings FOR SELECT TO authenticated
  USING (authz.is_org_member(organization_id));
CREATE POLICY ai_settings_insert ON public.ai_settings FOR INSERT TO authenticated
  WITH CHECK (authz.has_org_role(organization_id, ARRAY['owner','admin']));
CREATE POLICY ai_settings_update ON public.ai_settings FOR UPDATE TO authenticated
  USING (authz.has_org_role(organization_id, ARRAY['owner','admin']))
  WITH CHECK (authz.has_org_role(organization_id, ARRAY['owner','admin']));

ALTER TABLE public.ai_suggestions ENABLE ROW LEVEL SECURITY;
CREATE POLICY ai_suggestions_select ON public.ai_suggestions FOR SELECT TO authenticated
  USING (authz.can_read_dossier(engagement_id));
CREATE POLICY ai_suggestions_insert ON public.ai_suggestions FOR INSERT TO authenticated
  WITH CHECK (authz.has_engagement_role(engagement_id, ARRAY['partner','manager','in_charge','staff']));
CREATE POLICY ai_suggestions_update ON public.ai_suggestions FOR UPDATE TO authenticated
  USING (authz.has_engagement_role(engagement_id, ARRAY['partner','manager','in_charge','staff']))
  WITH CHECK (authz.has_engagement_role(engagement_id, ARRAY['partner','manager','in_charge','staff']));

-- les messages n'ont ni UPDATE ni DELETE (aucune politique) ; les conversations restent privées à leur auteur
GRANT SELECT, INSERT, UPDATE ON public.ai_settings, public.ai_suggestions TO authenticated;
GRANT ALL ON public.ai_settings, public.ai_suggestions TO service_role;
