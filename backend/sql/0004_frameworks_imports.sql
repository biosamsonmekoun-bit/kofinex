-- =====================================================================
-- KOFINEX — Migration 0004 : référentiels versionnés et importation des balances
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. Versions de référentiel : traçabilité des sources et verrouillage
-- ---------------------------------------------------------------------
ALTER TABLE public.framework_versions
  ADD COLUMN source_url         text,
  ADD COLUMN chart_sha256       char(64),
  ADD COLUMN mappings_sha256    char(64),
  ADD COLUMN chart_loaded_at    timestamptz,
  ADD COLUMN mappings_loaded_at timestamptz,
  ADD COLUMN validation         jsonb,
  ADD COLUMN created_by         uuid REFERENCES public.profiles(id);

-- Deux versions publiées d'un même référentiel ne peuvent pas couvrir la même période.
ALTER TABLE public.framework_versions
  ADD CONSTRAINT framework_versions_no_overlap
  EXCLUDE USING gist (
    framework_id WITH =,
    daterange(effective_from, coalesce(effective_to, 'infinity'::date), '[)') WITH &&
  ) WHERE (status = 'published');

ALTER TABLE public.chart_of_accounts ADD COLUMN source_row int;
ALTER TABLE public.account_mappings  ADD COLUMN source_row int;

-- Une version publiée (ou retirée) est figée : son contenu ne change plus jamais.
CREATE OR REPLACE FUNCTION public.guard_framework_version() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status <> 'draft' THEN
      RAISE EXCEPTION 'Une version publiée ou retirée ne peut pas être supprimée'
        USING ERRCODE = 'check_violation';
    END IF;
    RETURN OLD;
  END IF;
  IF OLD.status = 'published' THEN
    -- seules évolutions permises : retrait (deprecated) et date de fin d'application
    IF (to_jsonb(NEW) - ARRAY['status','effective_to','updated_at'])
       IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['status','effective_to','updated_at'])
       OR NEW.status NOT IN ('published','deprecated') THEN
      RAISE EXCEPTION 'Version publiée : seuls le retrait et la date de fin peuvent être modifiés'
        USING ERRCODE = 'check_violation';
    END IF;
  ELSIF OLD.status = 'deprecated' AND (to_jsonb(NEW) - 'updated_at') IS DISTINCT FROM (to_jsonb(OLD) - 'updated_at') THEN
    RAISE EXCEPTION 'Version retirée : aucune modification possible' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER framework_versions_guard
  BEFORE UPDATE OR DELETE ON public.framework_versions
  FOR EACH ROW EXECUTE FUNCTION public.guard_framework_version();

CREATE OR REPLACE FUNCTION public.guard_framework_content() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  v_status text;
  -- to_jsonb : chart_of_accounts n'a pas de colonne organization_id
  v_org    uuid := (to_jsonb(coalesce(NEW, OLD)) ->> 'organization_id')::uuid;
BEGIN
  SELECT status INTO v_status FROM public.framework_versions
   WHERE id = coalesce(NEW.framework_version_id, OLD.framework_version_id);
  -- les surcharges propres à un tenant (account_mappings.organization_id non NULL) restent modifiables
  IF v_status IS NOT NULL AND v_status <> 'draft' AND v_org IS NULL THEN
    RAISE EXCEPTION 'Contenu d''une version publiée non modifiable (%)', TG_TABLE_NAME
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN coalesce(NEW, OLD);
END $$;

CREATE TRIGGER chart_of_accounts_guard
  BEFORE INSERT OR UPDATE OR DELETE ON public.chart_of_accounts
  FOR EACH ROW EXECUTE FUNCTION public.guard_framework_content();
CREATE TRIGGER account_mappings_guard
  BEFORE INSERT OR UPDATE OR DELETE ON public.account_mappings
  FOR EACH ROW EXECUTE FUNCTION public.guard_framework_content();

-- Version applicable à une entreprise à une date (fin d'exercice) : publiée, couvrant la date.
CREATE OR REPLACE FUNCTION public.applicable_framework_version(p_company uuid, p_date date) RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT v.id
    FROM public.companies c
    JOIN public.framework_versions v ON v.framework_id = c.framework_id
   WHERE c.id = p_company
     AND v.status = 'published'
     AND v.effective_from <= p_date
     AND (v.effective_to IS NULL OR v.effective_to > p_date)
   ORDER BY v.effective_from DESC
   LIMIT 1
$$;
GRANT EXECUTE ON FUNCTION public.applicable_framework_version(uuid, date) TO authenticated, service_role;

-- ---------------------------------------------------------------------
-- 2. Importations : métadonnées d'extraction et lignes de travail
-- ---------------------------------------------------------------------
ALTER TABLE public.import_jobs
  ADD COLUMN sheets                jsonb,     -- [{name, rows, columns, header_row, warnings}]
  ADD COLUMN extraction            jsonb,     -- {method, page_count, ocr_pages}
  ADD COLUMN options               jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN controls              jsonb,     -- rapport complet des contrôles de cohérence
  ADD COLUMN framework_version_id  uuid REFERENCES public.framework_versions(id),
  ADD COLUMN warnings_acknowledged boolean NOT NULL DEFAULT false,
  ADD COLUMN acknowledged_by       uuid REFERENCES public.profiles(id);

ALTER TABLE public.import_jobs DROP CONSTRAINT import_jobs_status_check;
ALTER TABLE public.import_jobs ADD CONSTRAINT import_jobs_status_check CHECK (status IN
  ('pending','parsing','awaiting_mapping','validating','awaiting_confirmation',
   'completed','superseded','failed','cancelled'));

-- Lignes lues et normalisées, en attente de validation (copiées dans trial_balance_entries
-- à la confirmation). Conservées ensuite pour la traçabilité de l'import.
CREATE TABLE public.import_staging_rows (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id  uuid NOT NULL,
  company_id       uuid NOT NULL,
  fiscal_year_id   uuid NOT NULL,
  import_job_id    uuid NOT NULL,
  source_row       int NOT NULL,
  source_page      int,
  status           text NOT NULL CHECK (status IN ('valid','error','skipped','total')),
  account_number   varchar(20) CHECK (account_number IS NULL OR account_number ~ '^[0-9]+$'),
  account_label    text,
  opening_debit    numeric(20,2),
  opening_credit   numeric(20,2),
  movement_debit   numeric(20,2),
  movement_credit  numeric(20,2),
  closing_debit    numeric(20,2),
  closing_credit   numeric(20,2),
  closing_computed boolean NOT NULL DEFAULT false,
  ocr_confidence   numeric(5,2),
  issues           jsonb NOT NULL DEFAULT '[]'::jsonb,
  raw              jsonb NOT NULL,
  UNIQUE (import_job_id, source_row),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (fiscal_year_id, company_id) REFERENCES public.fiscal_years(id, company_id) ON DELETE CASCADE,
  FOREIGN KEY (import_job_id, fiscal_year_id) REFERENCES public.import_jobs(id, fiscal_year_id) ON DELETE CASCADE,
  CHECK (status <> 'valid' OR account_number IS NOT NULL)
);
CREATE INDEX import_staging_rows_job_idx ON public.import_staging_rows (import_job_id, status, source_row);

ALTER TABLE public.trial_balance_entries
  ADD COLUMN source_page      int,
  ADD COLUMN closing_computed boolean NOT NULL DEFAULT false,
  ADD COLUMN ocr_confidence   numeric(5,2);

ALTER TABLE public.import_staging_rows ENABLE ROW LEVEL SECURITY;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.import_staging_rows TO authenticated;
GRANT ALL ON public.import_staging_rows TO service_role;

CREATE POLICY import_staging_rows_select ON public.import_staging_rows FOR SELECT TO authenticated
  USING (authz.can_access_company(company_id));
CREATE POLICY import_staging_rows_write ON public.import_staging_rows FOR ALL TO authenticated
  USING (authz.has_company_role(company_id, ARRAY['accountant']))
  WITH CHECK (authz.has_company_role(company_id, ARRAY['accountant']));

CREATE TRIGGER import_staging_rows_closed_fy_guard
  BEFORE INSERT OR UPDATE OR DELETE ON public.import_staging_rows
  FOR EACH ROW EXECUTE FUNCTION public.guard_closed_fiscal_year();

-- Un fichier déjà importé pour une entreprise est signalé (même empreinte SHA-256).
CREATE OR REPLACE FUNCTION public.find_duplicate_document(p_company uuid, p_sha256 text) RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT id FROM public.financial_documents
   WHERE company_id = p_company AND sha256 = p_sha256 AND deleted_at IS NULL
   ORDER BY created_at LIMIT 1
$$;
GRANT EXECUTE ON FUNCTION public.find_duplicate_document(uuid, text) TO authenticated, service_role;
