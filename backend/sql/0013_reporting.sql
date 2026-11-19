-- =====================================================================
-- KOFINEX — Migration 0013 : reporting et génération documentaire (lot 11)
-- Documents PDF, Excel et Word établis à partir de données validées uniquement :
--   * rapport financier (analyse terminée) ; suivi budgétaire (budget approuvé) ;
--   * rapports du contrôle interne (tests revus, évaluations approuvées) ;
--   * rapport d'audit interne (rapport émis, contenu figé) ; synthèse des anomalies d'audit financier (seuils approuvés).
-- Chaque document généré est figé : empreinte du fichier, empreinte des données, contenu structuré, sources et modèle
-- utilisés. Les brouillons IA non relus n'y figurent que sur demande et sont alors signalés ; un commentaire rejeté
-- n'y figure jamais. Les modèles de rapport sont versionnés et figés à la publication.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. Modèles de rapport (table du lot 1 complétée)
-- ---------------------------------------------------------------------
ALTER TABLE public.report_templates
  ADD COLUMN document_type text NOT NULL DEFAULT 'financial_report' CHECK (document_type IN
    ('financial_report','budget_report','ic_report','internal_audit_report','fa_summary')),
  ADD COLUMN version       int  NOT NULL DEFAULT 1 CHECK (version >= 1),
  ADD COLUMN status        text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published','archived')),
  ADD COLUMN content       jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(content) = 'object'),
  ADD COLUMN published_by  uuid REFERENCES public.profiles(id),
  ADD COLUMN published_at  timestamptz,
  ADD CONSTRAINT report_templates_branding_color CHECK (
    branding->>'primary_color' IS NULL OR branding->>'primary_color' ~ '^#[0-9A-Fa-f]{6}$'),
  ADD CONSTRAINT report_templates_published CHECK (status = 'draft' OR (published_by IS NOT NULL AND published_at IS NOT NULL));
CREATE UNIQUE INDEX report_templates_version_uniq ON public.report_templates
  (coalesce(organization_id, '00000000-0000-0000-0000-000000000000'::uuid), document_type, name, version);

CREATE OR REPLACE FUNCTION public.guard_report_template() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status <> 'draft' THEN
      RAISE EXCEPTION 'Modèle publié : conservé (archivez-le)' USING ERRCODE = 'check_violation';
    END IF;
    RETURN OLD;
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.status <> 'draft' THEN
      RAISE EXCEPTION 'Modèle : créé en brouillon' USING ERRCODE = 'check_violation';
    END IF;
    NEW.created_by := auth.uid();
    RETURN NEW;
  END IF;
  IF OLD.status = 'archived' THEN
    RAISE EXCEPTION 'Modèle archivé : non modifiable' USING ERRCODE = 'check_violation';
  END IF;
  IF OLD.status = 'published' THEN
    IF NEW.status <> 'archived' OR (to_jsonb(NEW) - ARRAY['status','updated_at','is_default'])
                                  IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['status','updated_at','is_default']) THEN
      RAISE EXCEPTION 'Modèle publié : figé (créez une nouvelle version)' USING ERRCODE = 'check_violation';
    END IF;
  ELSIF NEW.status = 'published' THEN
    IF NEW.published_by IS DISTINCT FROM auth.uid() THEN
      RAISE EXCEPTION 'Publication : au nom de l''utilisateur authentifié' USING ERRCODE = 'insufficient_privilege';
    END IF;
    NEW.published_at := now();
  ELSIF NEW.status <> 'draft' THEN
    RAISE EXCEPTION 'Modèle : publiez-le avant de l''archiver' USING ERRCODE = 'check_violation';
  END IF;
  IF (NEW.organization_id, NEW.document_type, NEW.created_by, NEW.created_at)
     IS DISTINCT FROM (OLD.organization_id, OLD.document_type, OLD.created_by, OLD.created_at) THEN
    RAISE EXCEPTION 'Modèle : organisation, type et auteur non modifiables' USING ERRCODE = 'check_violation';
  END IF;
  NEW.updated_at := now();
  RETURN NEW;
END $$;
CREATE TRIGGER report_templates_guard BEFORE INSERT OR UPDATE OR DELETE ON public.report_templates
  FOR EACH ROW EXECUTE FUNCTION public.guard_report_template();

-- ---------------------------------------------------------------------
-- 2. Documents générés (table du lot 1 généralisée)
-- ---------------------------------------------------------------------
ALTER TABLE public.generated_reports ALTER COLUMN analysis_id DROP NOT NULL;
ALTER TABLE public.generated_reports
  ADD COLUMN engagement_id     uuid,
  ADD COLUMN document_type     text NOT NULL DEFAULT 'financial_report' CHECK (document_type IN
    ('financial_report','budget_report','ic_report','internal_audit_report','fa_summary')),
  ADD COLUMN subtype           text,                 -- ex. type de rapport du contrôle interne
  ADD COLUMN title             text,
  ADD COLUMN filename          text,
  ADD COLUMN mime_type         text,
  ADD COLUMN size_bytes        bigint CHECK (size_bytes IS NULL OR size_bytes > 0),
  ADD COLUMN data_sha256       char(64),             -- empreinte du contenu structuré (indépendante du format)
  ADD COLUMN content_snapshot  jsonb,                -- contenu structuré exact mis en forme
  ADD COLUMN source_refs       jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(source_refs) = 'array'),
  ADD COLUMN parameters        jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN template_version  int,
  ADD COLUMN generator_version text,
  ADD COLUMN contains_ai_drafts boolean NOT NULL DEFAULT false,
  ADD FOREIGN KEY (engagement_id, organization_id) REFERENCES public.engagements(id, organization_id) ON DELETE CASCADE,
  ADD CONSTRAINT generated_reports_ready CHECK (status <> 'ready' OR (data_sha256 IS NOT NULL AND content_snapshot IS NOT NULL
                                                                      AND filename IS NOT NULL AND size_bytes IS NOT NULL)),
  ADD CONSTRAINT generated_reports_failed CHECK (status <> 'failed' OR length(trim(coalesce(failure_reason, ''))) > 0);
CREATE INDEX generated_reports_company_idx ON public.generated_reports (company_id, created_at DESC);
CREATE INDEX generated_reports_engagement_idx ON public.generated_reports (engagement_id, created_at DESC) WHERE engagement_id IS NOT NULL;

CREATE OR REPLACE FUNCTION public.report_source(p_refs jsonb, p_type text) RETURNS uuid
LANGUAGE sql IMMUTABLE AS $$
  SELECT authz.try_uuid(r->>'id') FROM jsonb_array_elements(p_refs) r WHERE r->>'type' = p_type LIMIT 1
$$;

CREATE OR REPLACE FUNCTION public.guard_generated_report() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v record; v_id uuid; v_bad int; v_drafts int;
BEGIN
  IF TG_OP <> 'INSERT' THEN
    RAISE EXCEPTION 'Document généré : figé (ni modification ni suppression) ; générez-en un nouveau' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.requested_by IS DISTINCT FROM auth.uid() THEN
    RAISE EXCEPTION 'Document : généré au nom de l''utilisateur authentifié' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF NEW.status NOT IN ('ready','failed') THEN
    RAISE EXCEPTION 'Document : enregistré prêt ou en échec' USING ERRCODE = 'check_violation';
  END IF;
  NEW.created_at := now();
  NEW.completed_at := now();
  IF NEW.status = 'failed' THEN
    RETURN NEW;
  END IF;
  -- données validées uniquement, selon le type de document
  IF NEW.document_type = 'financial_report' THEN
    SELECT company_id, status INTO v FROM public.financial_analyses WHERE id = NEW.analysis_id;
    IF NEW.analysis_id IS NULL OR v.company_id IS DISTINCT FROM NEW.company_id OR v.status <> 'completed' OR NEW.engagement_id IS NOT NULL THEN
      RAISE EXCEPTION 'Rapport financier : analyse terminée de l''entreprise' USING ERRCODE = 'check_violation';
    END IF;
    SELECT count(*) FILTER (WHERE r.id IS NULL OR r.analysis_id <> NEW.analysis_id OR r.status = 'rejected'),
           count(*) FILTER (WHERE r.status = 'draft')
      INTO v_bad, v_drafts
      FROM unnest(NEW.ai_report_ids) AS x(id) LEFT JOIN public.ai_reports r ON r.id = x.id;
    IF v_bad > 0 THEN
      RAISE EXCEPTION 'Rapport financier : commentaire IA rejeté ou d''une autre analyse' USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.contains_ai_drafts IS DISTINCT FROM (v_drafts > 0) THEN
      RAISE EXCEPTION 'Rapport financier : la présence de brouillons IA non relus doit être signalée' USING ERRCODE = 'check_violation';
    END IF;
  ELSE
    IF cardinality(NEW.ai_report_ids) > 0 OR NEW.contains_ai_drafts THEN
      RAISE EXCEPTION 'Commentaires IA : réservés au rapport financier' USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.analysis_id IS NOT NULL THEN
      RAISE EXCEPTION 'Analyse de référence : rapport financier uniquement' USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  IF NEW.document_type = 'budget_report' THEN
    v_id := public.report_source(NEW.source_refs, 'budget');
    SELECT company_id, status INTO v FROM public.budgets WHERE id = v_id;
    IF v_id IS NULL OR v.company_id IS DISTINCT FROM NEW.company_id OR v.status NOT IN ('approved','archived') OR NEW.engagement_id IS NOT NULL THEN
      RAISE EXCEPTION 'Suivi budgétaire : budget approuvé de l''entreprise' USING ERRCODE = 'check_violation';
    END IF;
  ELSIF NEW.document_type = 'ic_report' THEN
    IF NEW.subtype IS NULL OR NEW.subtype NOT IN ('assessment','domain','process','cycle','risk_map','matrix','ineffective_controls',
                                                   'deficiencies','remediation') OR NEW.engagement_id IS NOT NULL THEN
      RAISE EXCEPTION 'Rapport de contrôle interne : type de rapport connu, au niveau de l''entité' USING ERRCODE = 'check_violation';
    END IF;
  ELSIF NEW.document_type = 'internal_audit_report' THEN
    v_id := public.report_source(NEW.source_refs, 'audit_report');
    SELECT engagement_id, status, content_sha256 INTO v FROM public.audit_reports WHERE id = v_id;
    IF v_id IS NULL OR NEW.engagement_id IS NULL OR v.engagement_id IS DISTINCT FROM NEW.engagement_id OR v.status <> 'issued' THEN
      RAISE EXCEPTION 'Rapport d''audit interne : rapport émis de la mission (un projet ne s''exporte pas ici)' USING ERRCODE = 'check_violation';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM jsonb_array_elements(NEW.source_refs) r
                    WHERE r->>'type' = 'audit_report' AND r->>'content_sha256' = v.content_sha256) THEN
      RAISE EXCEPTION 'Rapport d''audit interne : empreinte du rapport émis requise dans les sources' USING ERRCODE = 'check_violation';
    END IF;
  ELSIF NEW.document_type = 'fa_summary' THEN
    SELECT e.engagement_type, e.company_id INTO v FROM public.engagements e WHERE e.id = NEW.engagement_id;
    IF NEW.engagement_id IS NULL OR v.engagement_type NOT IN ('statutory_audit','contractual_audit') OR v.company_id <> NEW.company_id THEN
      RAISE EXCEPTION 'Synthèse des anomalies : mission d''audit financier' USING ERRCODE = 'check_violation';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.fa_materiality m WHERE m.engagement_id = NEW.engagement_id AND m.status = 'approved'
                     AND m.id = public.report_source(NEW.source_refs, 'materiality')) THEN
      RAISE EXCEPTION 'Synthèse des anomalies : seuils approuvés requis et cités dans les sources' USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  IF NEW.engagement_id IS NOT NULL
     AND (SELECT company_id FROM public.engagements WHERE id = NEW.engagement_id) IS DISTINCT FROM NEW.company_id THEN
    RAISE EXCEPTION 'Document : entité de la mission' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.template_id IS NOT NULL THEN
    SELECT status, version, document_type, organization_id INTO v FROM public.report_templates WHERE id = NEW.template_id;
    IF v.status <> 'published' OR v.document_type <> NEW.document_type
       OR (v.organization_id IS NOT NULL AND v.organization_id <> NEW.organization_id) OR v.version IS DISTINCT FROM NEW.template_version THEN
      RAISE EXCEPTION 'Modèle : version publiée, du même type et de l''organisation' USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER generated_reports_guard BEFORE INSERT OR UPDATE OR DELETE ON public.generated_reports
  FOR EACH ROW EXECUTE FUNCTION public.guard_generated_report();

-- ---------------------------------------------------------------------
-- 3. RLS des documents : entreprise, contrôle interne ou dossier de mission
-- ---------------------------------------------------------------------
DROP POLICY IF EXISTS generated_reports_select ON public.generated_reports;
DROP POLICY IF EXISTS generated_reports_insert ON public.generated_reports;
DROP POLICY IF EXISTS generated_reports_update ON public.generated_reports;
DROP POLICY IF EXISTS generated_reports_delete ON public.generated_reports;
CREATE POLICY generated_reports_select ON public.generated_reports FOR SELECT TO authenticated
  USING (CASE
    WHEN engagement_id IS NOT NULL THEN authz.can_read_dossier(engagement_id)
    WHEN document_type = 'ic_report' THEN authz.ic_reader(company_id)
    ELSE authz.can_access_company(company_id) END);
CREATE POLICY generated_reports_insert ON public.generated_reports FOR INSERT TO authenticated
  WITH CHECK (CASE
    WHEN engagement_id IS NOT NULL THEN authz.has_engagement_role(engagement_id, ARRAY['partner','manager','in_charge','staff'])
    WHEN document_type = 'ic_report' THEN authz.ic_reader(company_id)
    ELSE authz.has_company_role(company_id, ARRAY['accountant','controller','analyst']) END);

-- ---------------------------------------------------------------------
-- 4. Interdit IA (lot 10) : déjà posé sur ces deux tables par la migration 0012
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = '0_not_ai' AND tgrelid = 'public.generated_reports'::regclass)
     OR NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = '0_not_ai' AND tgrelid = 'public.report_templates'::regclass) THEN
    RAISE EXCEPTION 'Migration 0013 : déclencheur 0_not_ai attendu sur les tables de reporting';
  END IF;
END $$;
