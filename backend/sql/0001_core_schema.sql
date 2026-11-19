-- =====================================================================
-- KOFINEX — Migration 0001 : schéma principal
-- PostgreSQL 15+ (Supabase). Idempotence non recherchée : exécutée une
-- seule fois par Alembic (révision 0001).
--
-- Conventions :
--   * Clés primaires UUID (gen_random_uuid()).
--   * Montants : NUMERIC(20,2) ; indicateurs : NUMERIC(24,6). Jamais de float.
--   * Énumérations : text + CHECK (plus simples à faire évoluer que les ENUM).
--   * Isolation : toute table métier porte organization_id. Les tables liées
--     à une entreprise utilisent une clé étrangère COMPOSITE
--     (company_id, organization_id) -> companies(id, organization_id) afin
--     qu'une ligne ne puisse JAMAIS pointer vers l'entreprise d'un autre tenant.
--     Même principe pour (fiscal_year_id, company_id).
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- ---------------------------------------------------------------------
-- Utilitaires
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END $$;

-- =====================================================================
-- 1. IDENTITÉ & TENANTS
-- =====================================================================
CREATE TABLE public.profiles (
  id                uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email             text NOT NULL,
  full_name         text,
  phone             text,
  avatar_url        text,
  locale            text NOT NULL DEFAULT 'fr',
  is_platform_admin boolean NOT NULL DEFAULT false,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX profiles_email_idx ON public.profiles (lower(email));

-- Création automatique du profil à l'inscription Supabase.
CREATE OR REPLACE FUNCTION public.handle_new_user() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  INSERT INTO public.profiles (id, email, full_name)
  VALUES (NEW.id, coalesce(NEW.email, ''), NEW.raw_user_meta_data ->> 'full_name')
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END $$;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

CREATE TABLE public.organizations (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name             text NOT NULL CHECK (length(trim(name)) BETWEEN 2 AND 200),
  slug             text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  org_type         text NOT NULL DEFAULT 'company'
                   CHECK (org_type IN ('accounting_firm','company','group','consulting','audit','non_profit')),
  country_code     char(2),
  default_currency char(3) NOT NULL DEFAULT 'XOF',
  is_demo          boolean NOT NULL DEFAULT false,
  created_by       uuid NOT NULL REFERENCES public.profiles(id),
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  archived_at      timestamptz
);

CREATE TABLE public.organization_members (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
  user_id         uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  role            text NOT NULL CHECK (role IN ('owner','admin','member','viewer')),
  invited_by      uuid REFERENCES public.profiles(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, user_id)
);
CREATE INDEX organization_members_user_idx ON public.organization_members (user_id);

-- Le créateur d'une organisation en devient automatiquement propriétaire.
CREATE OR REPLACE FUNCTION public.handle_new_organization() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  INSERT INTO public.organization_members (organization_id, user_id, role)
  VALUES (NEW.id, NEW.created_by, 'owner');
  RETURN NEW;
END $$;

CREATE TRIGGER on_organization_created
  AFTER INSERT ON public.organizations
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_organization();

-- Une organisation doit toujours conserver au moins un propriétaire.
CREATE OR REPLACE FUNCTION public.ensure_last_owner() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  remaining int;
BEGIN
  IF OLD.role = 'owner' AND (TG_OP = 'DELETE' OR NEW.role <> 'owner') THEN
    -- Suppression en cascade de l'organisation : rien à protéger.
    IF NOT EXISTS (SELECT 1 FROM public.organizations WHERE id = OLD.organization_id) THEN
      RETURN OLD;
    END IF;
    SELECT count(*) INTO remaining
      FROM public.organization_members
     WHERE organization_id = OLD.organization_id AND role = 'owner' AND id <> OLD.id;
    IF remaining = 0 THEN
      RAISE EXCEPTION 'Une organisation doit conserver au moins un propriétaire'
        USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END $$;

CREATE TRIGGER organization_members_last_owner
  BEFORE UPDATE OR DELETE ON public.organization_members
  FOR EACH ROW EXECUTE FUNCTION public.ensure_last_owner();

-- =====================================================================
-- 2. RÉFÉRENTIELS COMPTABLES (données de référence globales, versionnées)
-- =====================================================================
CREATE TABLE public.accounting_frameworks (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code        text NOT NULL UNIQUE CHECK (code ~ '^[A-Z0-9_]+$'),
  name        text NOT NULL,
  description text,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE public.framework_versions (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  framework_id     uuid NOT NULL REFERENCES public.accounting_frameworks(id) ON DELETE RESTRICT,
  version_label    text NOT NULL,
  effective_from   date NOT NULL,
  effective_to     date,
  -- Référence officielle (ex. « Acte uniforme OHADA relatif au droit comptable, 26/01/2017 »)
  source_reference text NOT NULL,
  status           text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published','deprecated')),
  published_at     timestamptz,
  published_by     uuid REFERENCES public.profiles(id),
  notes            text,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (framework_id, version_label),
  CHECK (effective_to IS NULL OR effective_to > effective_from),
  CHECK (status <> 'published' OR published_at IS NOT NULL)
);

CREATE TABLE public.chart_of_accounts (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  framework_version_id uuid NOT NULL REFERENCES public.framework_versions(id) ON DELETE CASCADE,
  account_number       varchar(20) NOT NULL CHECK (account_number ~ '^[0-9]+$'),
  label                text NOT NULL,
  account_class        smallint NOT NULL CHECK (account_class BETWEEN 1 AND 9),
  parent_number        varchar(20),
  nature               text CHECK (nature IN ('asset','liability','equity','income','expense','off_balance','mixed')),
  normal_balance       text CHECK (normal_balance IN ('debit','credit','either')),
  is_postable          boolean NOT NULL DEFAULT true,
  created_at           timestamptz NOT NULL DEFAULT now(),
  UNIQUE (framework_version_id, account_number)
);
CREATE INDEX chart_of_accounts_prefix_idx
  ON public.chart_of_accounts (framework_version_id, account_number varchar_pattern_ops);

-- =====================================================================
-- 3. ENTREPRISES & EXERCICES
-- =====================================================================
CREATE TABLE public.companies (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id     uuid NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
  name                text NOT NULL CHECK (length(trim(name)) BETWEEN 2 AND 200),
  legal_name          text,
  legal_form          text,           -- SA, SARL, SAS, Association, ONG…
  registration_number text,           -- RCCM
  tax_id              text,           -- NIF / IFU / NINEA selon le pays
  country_code        char(2),
  currency            char(3) NOT NULL DEFAULT 'XOF',
  framework_id        uuid NOT NULL REFERENCES public.accounting_frameworks(id),
  activity_sector     text,
  address             text,
  city                text,
  fiscal_year_start_month smallint NOT NULL DEFAULT 1 CHECK (fiscal_year_start_month BETWEEN 1 AND 12),
  is_demo             boolean NOT NULL DEFAULT false,
  created_by          uuid NOT NULL REFERENCES public.profiles(id),
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  archived_at         timestamptz,
  UNIQUE (id, organization_id)
);
CREATE INDEX companies_org_idx ON public.companies (organization_id) WHERE archived_at IS NULL;
CREATE UNIQUE INDEX companies_org_tax_id_uq
  ON public.companies (organization_id, tax_id) WHERE tax_id IS NOT NULL AND archived_at IS NULL;

CREATE TABLE public.company_members (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  company_id      uuid NOT NULL,
  user_id         uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  role            text NOT NULL CHECK (role IN ('accountant','controller','analyst','auditor','viewer')),
  granted_by      uuid REFERENCES public.profiles(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_id, user_id),
  FOREIGN KEY (company_id, organization_id)
    REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  -- l'utilisateur doit être membre de l'organisation
  FOREIGN KEY (organization_id, user_id)
    REFERENCES public.organization_members(organization_id, user_id) ON DELETE CASCADE
);
CREATE INDEX company_members_user_idx ON public.company_members (user_id);

CREATE TABLE public.fiscal_years (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id       uuid NOT NULL,
  company_id            uuid NOT NULL,
  label                 text NOT NULL,
  start_date            date NOT NULL,
  end_date              date NOT NULL,
  framework_version_id  uuid REFERENCES public.framework_versions(id),
  status                text NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed','archived')),
  -- import de balance retenu comme référence (renseigné en phase 3)
  active_import_job_id  uuid,
  closed_at             timestamptz,
  closed_by             uuid REFERENCES public.profiles(id),
  created_by            uuid NOT NULL REFERENCES public.profiles(id),
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id, company_id),
  UNIQUE (company_id, label),
  FOREIGN KEY (company_id, organization_id)
    REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  CHECK (end_date > start_date),
  -- un exercice OHADA dure 12 mois, sauf premier exercice / modification (max 18 mois)
  CHECK (end_date <= start_date + interval '18 months'),
  CHECK (status = 'open' OR closed_at IS NOT NULL),
  -- deux exercices d'une même entreprise ne peuvent pas se chevaucher
  EXCLUDE USING gist (company_id WITH =, daterange(start_date, end_date, '[]') WITH &&)
);
CREATE INDEX fiscal_years_company_idx ON public.fiscal_years (company_id, start_date DESC);

-- Correspondances balance -> rubriques d'états financiers.
-- organization_id NULL = table officielle ; non NULL = surcharge d'un tenant.
CREATE TABLE public.account_mappings (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  framework_version_id uuid NOT NULL REFERENCES public.framework_versions(id) ON DELETE CASCADE,
  organization_id      uuid REFERENCES public.organizations(id) ON DELETE CASCADE,
  statement_type       text NOT NULL CHECK (statement_type IN
                        ('balance_sheet_assets','balance_sheet_liabilities','income_statement','cash_flow','off_balance')),
  line_code            text NOT NULL,       -- ex. « AE », « TA », « XB »
  line_label           text NOT NULL,
  account_prefix       varchar(20) NOT NULL CHECK (account_prefix ~ '^[0-9]+$'),
  excluded_prefixes    varchar(20)[] NOT NULL DEFAULT '{}',
  balance_rule         text NOT NULL CHECK (balance_rule IN
                        ('debit_balance','credit_balance','net_debit','net_credit','debit_movements','credit_movements')),
  amount_column        text NOT NULL DEFAULT 'net' CHECK (amount_column IN ('gross','depreciation','net')),
  sign                 smallint NOT NULL DEFAULT 1 CHECK (sign IN (1,-1)),
  priority             int NOT NULL DEFAULT 100,
  source_reference     text,
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now(),
  UNIQUE NULLS NOT DISTINCT
    (framework_version_id, organization_id, statement_type, line_code, account_prefix, amount_column)
);
CREATE INDEX account_mappings_lookup_idx
  ON public.account_mappings (framework_version_id, organization_id, statement_type);

-- =====================================================================
-- 4. DOCUMENTS & IMPORTS
-- =====================================================================
CREATE TABLE public.financial_documents (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id   uuid NOT NULL,
  company_id        uuid NOT NULL,
  fiscal_year_id    uuid,
  document_type     text NOT NULL CHECK (document_type IN
                     ('trial_balance','financial_statements','general_ledger','tax_return','budget','other')),
  original_filename text NOT NULL,
  storage_path      text NOT NULL UNIQUE,      -- {organization_id}/{company_id}/{uuid}.{ext}
  mime_type         text NOT NULL,
  size_bytes        bigint NOT NULL CHECK (size_bytes > 0),
  sha256            char(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  is_confidential   boolean NOT NULL DEFAULT true,
  uploaded_by       uuid NOT NULL REFERENCES public.profiles(id),
  created_at        timestamptz NOT NULL DEFAULT now(),
  deleted_at        timestamptz,
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (fiscal_year_id, company_id) REFERENCES public.fiscal_years(id, company_id),
  CHECK (storage_path LIKE organization_id::text || '/%')
);
CREATE INDEX financial_documents_company_idx ON public.financial_documents (company_id, created_at DESC);
CREATE INDEX financial_documents_hash_idx ON public.financial_documents (company_id, sha256);

CREATE TABLE public.import_mappings (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
  company_id      uuid,
  name            text NOT NULL,
  source_format   text NOT NULL CHECK (source_format IN ('xlsx','xls','csv','pdf','ocr','connector')),
  -- { "account_number": "B", "account_label": "C", "closing_debit": "G", ... }
  column_map      jsonb NOT NULL,
  options         jsonb NOT NULL DEFAULT '{}'::jsonb,   -- séparateur, décimales, ligne d'en-tête…
  is_default      boolean NOT NULL DEFAULT false,
  created_by      uuid NOT NULL REFERENCES public.profiles(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  CHECK (jsonb_typeof(column_map) = 'object')
);

CREATE TABLE public.import_jobs (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  company_id      uuid NOT NULL,
  fiscal_year_id  uuid NOT NULL,
  document_id     uuid REFERENCES public.financial_documents(id),
  mapping_id      uuid REFERENCES public.import_mappings(id) ON DELETE SET NULL,
  source_format   text NOT NULL CHECK (source_format IN ('xlsx','xls','csv','pdf','ocr','connector')),
  status          text NOT NULL DEFAULT 'pending' CHECK (status IN
                   ('pending','parsing','awaiting_mapping','validating','awaiting_confirmation',
                    'completed','failed','cancelled')),
  sheet_name      text,
  header_row      int CHECK (header_row IS NULL OR header_row >= 0),
  column_map      jsonb,          -- mapping effectivement appliqué (copie figée)
  preview         jsonb,          -- échantillon de lignes pour la prévisualisation
  total_rows      int,
  valid_rows      int,
  error_rows      int,
  errors          jsonb NOT NULL DEFAULT '[]'::jsonb,   -- [{row, column, code, message}]
  control_totals  jsonb,          -- totaux débit/crédit, écart d'équilibre
  celery_task_id  text,
  started_by      uuid NOT NULL REFERENCES public.profiles(id),
  validated_by    uuid REFERENCES public.profiles(id),
  validated_at    timestamptz,
  completed_at    timestamptz,
  failure_reason  text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id, fiscal_year_id),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (fiscal_year_id, company_id) REFERENCES public.fiscal_years(id, company_id) ON DELETE CASCADE,
  CHECK (status <> 'completed' OR (validated_by IS NOT NULL AND completed_at IS NOT NULL))
);
CREATE INDEX import_jobs_company_idx ON public.import_jobs (company_id, created_at DESC);

ALTER TABLE public.fiscal_years
  ADD CONSTRAINT fiscal_years_active_import_fk
  FOREIGN KEY (active_import_job_id, id) REFERENCES public.import_jobs(id, fiscal_year_id)
  DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE public.trial_balance_entries (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  company_id      uuid NOT NULL,
  fiscal_year_id  uuid NOT NULL,
  import_job_id   uuid NOT NULL,
  account_number  varchar(20) NOT NULL CHECK (account_number ~ '^[0-9]+$'),
  account_label   text,
  opening_debit   numeric(20,2) NOT NULL DEFAULT 0 CHECK (opening_debit  >= 0),
  opening_credit  numeric(20,2) NOT NULL DEFAULT 0 CHECK (opening_credit >= 0),
  movement_debit  numeric(20,2) NOT NULL DEFAULT 0 CHECK (movement_debit >= 0),
  movement_credit numeric(20,2) NOT NULL DEFAULT 0 CHECK (movement_credit >= 0),
  closing_debit   numeric(20,2) NOT NULL DEFAULT 0 CHECK (closing_debit  >= 0),
  closing_credit  numeric(20,2) NOT NULL DEFAULT 0 CHECK (closing_credit >= 0),
  source_row      int,
  raw_data        jsonb,          -- ligne d'origine non retraitée
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (import_job_id, account_number),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (fiscal_year_id, company_id) REFERENCES public.fiscal_years(id, company_id) ON DELETE CASCADE,
  FOREIGN KEY (import_job_id, fiscal_year_id) REFERENCES public.import_jobs(id, fiscal_year_id) ON DELETE CASCADE
);
CREATE INDEX trial_balance_entries_fy_idx
  ON public.trial_balance_entries (fiscal_year_id, account_number varchar_pattern_ops);

-- =====================================================================
-- 5. ÉTATS FINANCIERS
-- =====================================================================
CREATE TABLE public.financial_statements (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id      uuid NOT NULL,
  company_id           uuid NOT NULL,
  fiscal_year_id       uuid NOT NULL,
  framework_version_id uuid NOT NULL REFERENCES public.framework_versions(id),
  statement_type       text NOT NULL CHECK (statement_type IN
                        ('balance_sheet','income_statement','cash_flow','notes')),
  source_import_job_id uuid REFERENCES public.import_jobs(id),
  status               text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','validated','superseded')),
  engine_version       text NOT NULL,     -- version du moteur comptable ayant produit l'état
  control_results      jsonb NOT NULL DEFAULT '[]'::jsonb,   -- contrôles de cohérence
  generated_by         uuid NOT NULL REFERENCES public.profiles(id),
  generated_at         timestamptz NOT NULL DEFAULT now(),
  validated_by         uuid REFERENCES public.profiles(id),
  validated_at         timestamptz,
  UNIQUE (id, organization_id),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (fiscal_year_id, company_id) REFERENCES public.fiscal_years(id, company_id) ON DELETE CASCADE
);
-- un seul état « validé » par type et exercice
CREATE UNIQUE INDEX financial_statements_validated_uq
  ON public.financial_statements (fiscal_year_id, statement_type) WHERE status = 'validated';

CREATE TABLE public.financial_statement_lines (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id     uuid NOT NULL,
  statement_id        uuid NOT NULL,
  line_code           text NOT NULL,
  label               text NOT NULL,
  display_order       int NOT NULL,
  is_total            boolean NOT NULL DEFAULT false,
  amount_gross        numeric(20,2),
  amount_depreciation numeric(20,2),
  amount_net          numeric(20,2),
  amount_previous     numeric(20,2),
  -- comptes et règles ayant servi au calcul (traçabilité)
  computation_trace   jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (statement_id, line_code),
  FOREIGN KEY (statement_id, organization_id)
    REFERENCES public.financial_statements(id, organization_id) ON DELETE CASCADE
);

-- =====================================================================
-- 6. MOTEUR FINANCIER
-- =====================================================================
CREATE TABLE public.financial_formulas (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id      uuid REFERENCES public.organizations(id) ON DELETE CASCADE,  -- NULL = bibliothèque officielle
  framework_id         uuid REFERENCES public.accounting_frameworks(id),           -- NULL = tous référentiels
  code                 text NOT NULL CHECK (code ~ '^[A-Z][A-Z0-9_]*$'),
  version              int NOT NULL CHECK (version >= 1),
  name                 text NOT NULL,
  category             text NOT NULL CHECK (category IN
                        ('sig','caf','structure','liquidity','solvency','profitability','activity','cash','custom')),
  expression           text NOT NULL,        -- expression lisible, ex. « (XB - RA) / XB »
  expression_ast       jsonb NOT NULL,       -- arbre validé, seul format évalué
  unit                 text NOT NULL CHECK (unit IN ('amount','ratio','percent','days','times')),
  rounding_scale       smallint NOT NULL DEFAULT 2 CHECK (rounding_scale BETWEEN 0 AND 6),
  zero_division_policy text NOT NULL DEFAULT 'null' CHECK (zero_division_policy IN ('null','zero','error')),
  missing_input_policy text NOT NULL DEFAULT 'null' CHECK (missing_input_policy IN ('null','zero','error')),
  description          text,
  convention_notes     text,
  source_reference     text,
  status               text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published','deprecated')),
  created_by           uuid REFERENCES public.profiles(id),
  created_at           timestamptz NOT NULL DEFAULT now(),
  UNIQUE NULLS NOT DISTINCT (organization_id, framework_id, code, version)
);

CREATE TABLE public.financial_analyses (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id  uuid NOT NULL,
  company_id       uuid NOT NULL,
  fiscal_year_id   uuid NOT NULL,
  analysis_type    text NOT NULL CHECK (analysis_type IN ('annual','multi_year','budget_variance','cost','anomaly')),
  compared_fiscal_year_ids uuid[] NOT NULL DEFAULT '{}',
  parameters       jsonb NOT NULL DEFAULT '{}'::jsonb,
  engine_version   text NOT NULL,
  status           text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','running','completed','failed')),
  failure_reason   text,
  started_by       uuid NOT NULL REFERENCES public.profiles(id),
  started_at       timestamptz NOT NULL DEFAULT now(),
  completed_at     timestamptz,
  UNIQUE (id, organization_id),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (fiscal_year_id, company_id) REFERENCES public.fiscal_years(id, company_id) ON DELETE CASCADE
);
CREATE INDEX financial_analyses_company_idx ON public.financial_analyses (company_id, started_at DESC);

CREATE TABLE public.financial_indicators (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  analysis_id     uuid NOT NULL,
  formula_id      uuid NOT NULL REFERENCES public.financial_formulas(id),
  formula_code    text NOT NULL,
  formula_version int  NOT NULL,
  value           numeric(24,6),
  status          text NOT NULL CHECK (status IN ('ok','missing_input','division_by_zero','not_applicable','error')),
  unit            text NOT NULL,
  inputs          jsonb NOT NULL DEFAULT '{}'::jsonb,    -- valeurs exactes utilisées
  computed_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (analysis_id, formula_code),
  UNIQUE (id, organization_id),
  FOREIGN KEY (analysis_id, organization_id)
    REFERENCES public.financial_analyses(id, organization_id) ON DELETE CASCADE,
  CHECK (status <> 'ok' OR value IS NOT NULL)
);

CREATE TABLE public.financial_alerts (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  company_id      uuid NOT NULL,
  fiscal_year_id  uuid,
  analysis_id     uuid,
  indicator_id    uuid,
  severity        text NOT NULL CHECK (severity IN ('info','warning','critical')),
  rule_code       text NOT NULL,
  title           text NOT NULL,
  message         text NOT NULL,
  evidence        jsonb NOT NULL DEFAULT '{}'::jsonb,
  status          text NOT NULL DEFAULT 'open' CHECK (status IN ('open','acknowledged','resolved','dismissed')),
  handled_by      uuid REFERENCES public.profiles(id),
  handled_at      timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (fiscal_year_id, company_id) REFERENCES public.fiscal_years(id, company_id) ON DELETE CASCADE,
  FOREIGN KEY (analysis_id, organization_id) REFERENCES public.financial_analyses(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (indicator_id, organization_id) REFERENCES public.financial_indicators(id, organization_id) ON DELETE SET NULL (indicator_id)
);
CREATE INDEX financial_alerts_open_idx ON public.financial_alerts (company_id, status) WHERE status = 'open';

-- =====================================================================
-- 7. CONTRÔLE DE GESTION
-- =====================================================================
CREATE TABLE public.cost_centers (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  company_id      uuid NOT NULL,
  parent_id       uuid,
  code            text NOT NULL,
  name            text NOT NULL,
  center_type     text NOT NULL CHECK (center_type IN ('main','auxiliary','structure','profit','investment')),
  is_active       boolean NOT NULL DEFAULT true,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_id, code),
  UNIQUE (id, company_id),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (parent_id, company_id) REFERENCES public.cost_centers(id, company_id),
  CHECK (parent_id IS NULL OR parent_id <> id)
);

CREATE TABLE public.budgets (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  company_id      uuid NOT NULL,
  fiscal_year_id  uuid NOT NULL,
  name            text NOT NULL,
  version         int NOT NULL DEFAULT 1 CHECK (version >= 1),
  status          text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','submitted','approved','archived')),
  currency        char(3) NOT NULL DEFAULT 'XOF',
  approved_by     uuid REFERENCES public.profiles(id),
  approved_at     timestamptz,
  created_by      uuid NOT NULL REFERENCES public.profiles(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (fiscal_year_id, name, version),
  UNIQUE (id, company_id),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (fiscal_year_id, company_id) REFERENCES public.fiscal_years(id, company_id) ON DELETE CASCADE,
  CHECK (status <> 'approved' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL))
);

CREATE TABLE public.budget_lines (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  company_id      uuid NOT NULL,
  budget_id       uuid NOT NULL,
  cost_center_id  uuid,
  account_number  varchar(20) CHECK (account_number IS NULL OR account_number ~ '^[0-9]+$'),
  label           text NOT NULL,
  period          smallint NOT NULL CHECK (period BETWEEN 0 AND 12),   -- 0 = annuel
  amount          numeric(20,2) NOT NULL,
  notes           text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id, company_id),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (budget_id, company_id) REFERENCES public.budgets(id, company_id) ON DELETE CASCADE,
  FOREIGN KEY (cost_center_id, company_id) REFERENCES public.cost_centers(id, company_id),
  CHECK (account_number IS NOT NULL OR cost_center_id IS NOT NULL)
);
CREATE INDEX budget_lines_budget_idx ON public.budget_lines (budget_id, period);

CREATE TABLE public.budget_actuals (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  company_id      uuid NOT NULL,
  budget_line_id  uuid NOT NULL,
  period          smallint NOT NULL CHECK (period BETWEEN 0 AND 12),
  actual_amount   numeric(20,2) NOT NULL,
  source          text NOT NULL CHECK (source IN ('trial_balance','cost_entries','manual','connector')),
  source_ref      uuid,
  computed_at     timestamptz NOT NULL DEFAULT now(),
  computed_by     uuid REFERENCES public.profiles(id),
  UNIQUE (budget_line_id, period, source),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (budget_line_id, company_id) REFERENCES public.budget_lines(id, company_id) ON DELETE CASCADE
);

CREATE TABLE public.cost_entries (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  company_id      uuid NOT NULL,
  fiscal_year_id  uuid NOT NULL,
  cost_center_id  uuid NOT NULL,
  account_number  varchar(20) CHECK (account_number IS NULL OR account_number ~ '^[0-9]+$'),
  entry_date      date NOT NULL,
  amount          numeric(20,2) NOT NULL,
  cost_nature     text NOT NULL CHECK (cost_nature IN ('direct','indirect','fixed','variable','semi_variable')),
  allocation_key  text,
  description     text,
  source          text NOT NULL CHECK (source IN ('manual','import','allocation','connector')),
  created_by      uuid REFERENCES public.profiles(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (fiscal_year_id, company_id) REFERENCES public.fiscal_years(id, company_id) ON DELETE CASCADE,
  FOREIGN KEY (cost_center_id, company_id) REFERENCES public.cost_centers(id, company_id)
);
CREATE INDEX cost_entries_center_idx ON public.cost_entries (cost_center_id, entry_date);

-- =====================================================================
-- 8. INTELLIGENCE ARTIFICIELLE
-- =====================================================================
CREATE TABLE public.ai_conversations (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  company_id      uuid NOT NULL,
  fiscal_year_id  uuid,
  analysis_id     uuid,
  user_id         uuid NOT NULL REFERENCES public.profiles(id),
  title           text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id, organization_id),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (fiscal_year_id, company_id) REFERENCES public.fiscal_years(id, company_id) ON DELETE CASCADE,
  FOREIGN KEY (analysis_id, organization_id) REFERENCES public.financial_analyses(id, organization_id) ON DELETE SET NULL (analysis_id)
);
CREATE INDEX ai_conversations_user_idx ON public.ai_conversations (user_id, updated_at DESC);

CREATE TABLE public.ai_messages (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id  uuid NOT NULL,
  conversation_id  uuid NOT NULL,
  role             text NOT NULL CHECK (role IN ('user','assistant','system','tool')),
  content          text NOT NULL,
  -- données structurées exactement transmises au modèle (indicateurs calculés)
  context_snapshot jsonb,
  model            text,
  input_tokens     int,
  output_tokens    int,
  -- résultat du contrôle « chaque chiffre cité est traçable »
  validation       jsonb,
  created_at       timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (conversation_id, organization_id)
    REFERENCES public.ai_conversations(id, organization_id) ON DELETE CASCADE
);
CREATE INDEX ai_messages_conv_idx ON public.ai_messages (conversation_id, created_at);

CREATE TABLE public.ai_reports (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id  uuid NOT NULL,
  company_id       uuid NOT NULL,
  analysis_id      uuid NOT NULL,
  section          text NOT NULL CHECK (section IN
                    ('executive_summary','balance_sheet','income_statement','cash','ratios',
                     'risks','recommendations','conclusion','custom')),
  content          text NOT NULL,
  context_snapshot jsonb NOT NULL,
  model            text NOT NULL,
  prompt_version   text NOT NULL,
  validation       jsonb,
  status           text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','reviewed','rejected')),
  reviewed_by      uuid REFERENCES public.profiles(id),
  reviewed_at      timestamptz,
  created_by       uuid NOT NULL REFERENCES public.profiles(id),
  created_at       timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (analysis_id, organization_id) REFERENCES public.financial_analyses(id, organization_id) ON DELETE CASCADE
);

-- =====================================================================
-- 9. REPORTING
-- =====================================================================
CREATE TABLE public.report_templates (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid REFERENCES public.organizations(id) ON DELETE CASCADE,  -- NULL = modèle système
  name            text NOT NULL,
  report_kind     text NOT NULL CHECK (report_kind IN ('synthetic','detailed','strategic','custom')),
  sections        jsonb NOT NULL,       -- ordre et paramètres des sections
  branding        jsonb NOT NULL DEFAULT '{}'::jsonb,   -- logo_path, couleurs, polices
  is_default      boolean NOT NULL DEFAULT false,
  created_by      uuid REFERENCES public.profiles(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CHECK (jsonb_typeof(sections) = 'array')
);

-- Rapports générés (fichiers) — table complémentaire nécessaire à la traçabilité.
CREATE TABLE public.generated_reports (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  company_id      uuid NOT NULL,
  analysis_id     uuid NOT NULL,
  template_id     uuid REFERENCES public.report_templates(id) ON DELETE SET NULL,
  format          text NOT NULL CHECK (format IN ('pdf','xlsx','docx')),
  status          text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','generating','ready','failed')),
  storage_path    text,
  sha256          char(64),
  ai_report_ids   uuid[] NOT NULL DEFAULT '{}',
  failure_reason  text,
  requested_by    uuid NOT NULL REFERENCES public.profiles(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  completed_at    timestamptz,
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (analysis_id, organization_id) REFERENCES public.financial_analyses(id, organization_id) ON DELETE CASCADE,
  CHECK (status <> 'ready' OR (storage_path IS NOT NULL AND sha256 IS NOT NULL))
);

-- =====================================================================
-- 10. INTÉGRATIONS, AUDIT, ABONNEMENTS
-- =====================================================================
CREATE TABLE public.integrations (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id       uuid NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
  company_id            uuid,
  provider              text NOT NULL CHECK (provider IN
                         ('odoo','sage_business_cloud','sage_100_export','quickbooks','file_export','other')),
  status                text NOT NULL DEFAULT 'not_configured' CHECK (status IN
                         ('not_configured','pending_verification','active','error','disabled')),
  config                jsonb NOT NULL DEFAULT '{}'::jsonb,   -- paramètres non secrets
  encrypted_credentials text,                                  -- chiffré (Fernet) côté API
  last_verified_at      timestamptz,
  last_sync_at          timestamptz,
  last_error            text,
  created_by            uuid NOT NULL REFERENCES public.profiles(id),
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  -- « active » exige une vérification réelle réussie
  CHECK (status <> 'active' OR last_verified_at IS NOT NULL)
);

CREATE TABLE public.audit_logs (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid REFERENCES public.organizations(id) ON DELETE SET NULL,
  company_id      uuid,
  user_id         uuid,           -- pas de FK : le journal survit à la suppression d'un compte
  action          text NOT NULL,  -- ex. INSERT / UPDATE / DELETE / import.validated / report.exported
  entity_type     text NOT NULL,
  entity_id       uuid,
  changes         jsonb,
  ip_address      inet,
  user_agent      text,
  request_id      text,
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_logs_org_idx ON public.audit_logs (organization_id, created_at DESC);
CREATE INDEX audit_logs_entity_idx ON public.audit_logs (entity_type, entity_id);

-- Journal immuable : aucune modification ni suppression, même pour le propriétaire de la table
-- (seule exception : mise à NULL de organization_id lors de la suppression d'une organisation).
CREATE OR REPLACE FUNCTION public.audit_logs_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'UPDATE'
     AND NEW.organization_id IS NULL AND OLD.organization_id IS NOT NULL
     AND (to_jsonb(NEW) - 'organization_id') = (to_jsonb(OLD) - 'organization_id') THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'audit_logs est en ajout seul' USING ERRCODE = 'insufficient_privilege';
END $$;

CREATE TRIGGER audit_logs_no_update
  BEFORE UPDATE OR DELETE ON public.audit_logs
  FOR EACH ROW EXECUTE FUNCTION public.audit_logs_immutable();

-- Audit automatique des tables sensibles (impossible à contourner par l'application).
CREATE OR REPLACE FUNCTION public.audit_row_change() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
  rec      jsonb := to_jsonb(coalesce(NEW, OLD));
  old_rec  jsonb := CASE WHEN TG_OP <> 'INSERT' THEN to_jsonb(OLD) END;
  new_rec  jsonb := CASE WHEN TG_OP <> 'DELETE' THEN to_jsonb(NEW) END;
  diff     jsonb;
  org_id   uuid;
BEGIN
  IF TG_OP = 'UPDATE' THEN
    SELECT jsonb_object_agg(key, jsonb_build_object('old', old_rec -> key, 'new', value))
      INTO diff
      FROM jsonb_each(new_rec)
     WHERE key NOT IN ('updated_at') AND (old_rec -> key) IS DISTINCT FROM value;
    IF diff IS NULL THEN RETURN NEW; END IF;
  ELSE
    diff := coalesce(new_rec, old_rec) - 'encrypted_credentials';
  END IF;
  diff := diff - 'encrypted_credentials';

  org_id := CASE WHEN TG_TABLE_NAME = 'organizations' THEN (rec ->> 'id')::uuid
                 ELSE (rec ->> 'organization_id')::uuid END;
  -- Organisation en cours de suppression : on ne référence pas une ligne disparue.
  IF TG_OP = 'DELETE' AND NOT EXISTS (SELECT 1 FROM public.organizations WHERE id = org_id) THEN
    org_id := NULL;
  END IF;

  INSERT INTO public.audit_logs (organization_id, company_id, user_id, action, entity_type, entity_id, changes, request_id)
  VALUES (
    org_id,
    CASE WHEN TG_TABLE_NAME = 'companies' THEN (rec ->> 'id')::uuid ELSE (rec ->> 'company_id')::uuid END,
    auth.uid(),
    TG_OP,
    TG_TABLE_NAME,
    (rec ->> 'id')::uuid,
    diff,
    nullif(current_setting('app.request_id', true), '')
  );
  RETURN coalesce(NEW, OLD);
END $$;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'organizations','organization_members','companies','company_members','fiscal_years',
    'framework_versions','account_mappings','financial_formulas','import_jobs',
    'financial_statements','budgets','integrations'
  ] LOOP
    EXECUTE format(
      'CREATE TRIGGER %I AFTER INSERT OR UPDATE OR DELETE ON public.%I
         FOR EACH ROW EXECUTE FUNCTION public.audit_row_change()', t || '_audit', t);
  END LOOP;
END $$;

CREATE TABLE public.subscriptions (
  id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id          uuid NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
  plan_code                text NOT NULL,
  status                   text NOT NULL CHECK (status IN ('trialing','active','past_due','canceled','expired')),
  seats                    int NOT NULL DEFAULT 1 CHECK (seats >= 1),
  max_companies            int CHECK (max_companies IS NULL OR max_companies >= 1),
  provider                 text,       -- stripe, cinetpay, paydunya… (selon intégration réelle)
  provider_customer_id     text,
  provider_subscription_id text UNIQUE,
  current_period_start     timestamptz,
  current_period_end       timestamptz,
  cancel_at                timestamptz,
  created_at               timestamptz NOT NULL DEFAULT now(),
  updated_at               timestamptz NOT NULL DEFAULT now()
);
-- un seul abonnement actif/en essai par organisation
CREATE UNIQUE INDEX subscriptions_one_live_uq
  ON public.subscriptions (organization_id) WHERE status IN ('trialing','active','past_due');

CREATE TRIGGER subscriptions_audit AFTER INSERT OR UPDATE OR DELETE ON public.subscriptions
  FOR EACH ROW EXECUTE FUNCTION public.audit_row_change();

CREATE TABLE public.payments (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id     uuid NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
  subscription_id     uuid REFERENCES public.subscriptions(id) ON DELETE SET NULL,
  amount              numeric(14,2) NOT NULL CHECK (amount >= 0),
  currency            char(3) NOT NULL,
  status              text NOT NULL CHECK (status IN ('pending','succeeded','failed','refunded')),
  provider            text NOT NULL,
  provider_payment_id text NOT NULL,
  paid_at             timestamptz,
  raw_event           jsonb,
  created_at          timestamptz NOT NULL DEFAULT now(),
  UNIQUE (provider, provider_payment_id)
);
CREATE INDEX payments_org_idx ON public.payments (organization_id, created_at DESC);

-- ---------------------------------------------------------------------
-- updated_at automatique
-- ---------------------------------------------------------------------
DO $$
DECLARE t text;
BEGIN
  FOR t IN
    SELECT c.table_name FROM information_schema.columns c
     WHERE c.table_schema = 'public' AND c.column_name = 'updated_at'
  LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE ON public.%I
                    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at()', t || '_updated_at', t);
  END LOOP;
END $$;
