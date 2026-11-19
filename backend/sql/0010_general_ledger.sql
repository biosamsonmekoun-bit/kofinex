-- =====================================================================
-- KOFINEX — Migration 0010 : grand livre (complément du lot 3)
-- Imports de grand livre (même cycle que les balances), lignes d'écritures, grand livre actif de l'exercice,
-- populations d'audit tirées des écritures, lecture par l'équipe de mission.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. Type d'import et grand livre actif de l'exercice
-- ---------------------------------------------------------------------
ALTER TABLE public.import_jobs ADD COLUMN kind text NOT NULL DEFAULT 'trial_balance'
  CHECK (kind IN ('trial_balance','ledger'));
ALTER TABLE public.import_mappings ADD COLUMN kind text NOT NULL DEFAULT 'trial_balance'
  CHECK (kind IN ('trial_balance','ledger'));

ALTER TABLE public.fiscal_years ADD COLUMN active_ledger_import_job_id uuid;
ALTER TABLE public.fiscal_years
  ADD CONSTRAINT fiscal_years_active_ledger_fk
  FOREIGN KEY (active_ledger_import_job_id, id) REFERENCES public.import_jobs(id, fiscal_year_id)
  DEFERRABLE INITIALLY DEFERRED;

-- La balance active est une balance validée, le grand livre actif un grand livre validé
CREATE OR REPLACE FUNCTION public.guard_active_imports() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_kind text; v_status text;
BEGIN
  IF NEW.active_import_job_id IS DISTINCT FROM OLD.active_import_job_id AND NEW.active_import_job_id IS NOT NULL THEN
    SELECT kind, status INTO v_kind, v_status FROM public.import_jobs WHERE id = NEW.active_import_job_id;
    IF v_kind <> 'trial_balance' THEN
      RAISE EXCEPTION 'La balance de l''exercice doit être un import de balance' USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  IF NEW.active_ledger_import_job_id IS DISTINCT FROM OLD.active_ledger_import_job_id
     AND NEW.active_ledger_import_job_id IS NOT NULL THEN
    SELECT kind, status INTO v_kind, v_status FROM public.import_jobs WHERE id = NEW.active_ledger_import_job_id;
    IF v_kind <> 'ledger' OR v_status <> 'completed' THEN
      RAISE EXCEPTION 'Le grand livre de l''exercice doit être un import de grand livre validé' USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER fiscal_years_active_imports_guard BEFORE UPDATE ON public.fiscal_years
  FOR EACH ROW EXECUTE FUNCTION public.guard_active_imports();

-- ---------------------------------------------------------------------
-- 2. Lignes du grand livre (lues, contrôlées ; figées dès la validation de l'import)
-- ---------------------------------------------------------------------
CREATE TABLE public.ledger_lines (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id   uuid NOT NULL,
  company_id        uuid NOT NULL,
  fiscal_year_id    uuid NOT NULL,
  import_job_id     uuid NOT NULL,
  source_row        int  NOT NULL CHECK (source_row > 0),
  status            text NOT NULL CHECK (status IN ('valid','error','skipped')),
  journal_code      text,
  journal_label     text,
  entry_number      text,
  entry_date        date,
  document_ref      text,
  document_date     date,
  account_number    varchar(20) CHECK (account_number IS NULL OR account_number ~ '^[0-9]+$'),
  account_label     text,
  auxiliary_account text,
  auxiliary_label   text,
  label             text,
  debit             numeric(20,2) NOT NULL DEFAULT 0 CHECK (debit >= 0),
  credit            numeric(20,2) NOT NULL DEFAULT 0 CHECK (credit >= 0),
  lettering         text,
  lettering_date    date,
  validation_date   date,
  currency_amount   numeric(20,2),
  currency          text,
  issues            jsonb NOT NULL DEFAULT '[]'::jsonb,
  raw               jsonb NOT NULL,
  UNIQUE (import_job_id, source_row),
  UNIQUE (id, company_id),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (fiscal_year_id, company_id) REFERENCES public.fiscal_years(id, company_id) ON DELETE CASCADE,
  FOREIGN KEY (import_job_id, fiscal_year_id) REFERENCES public.import_jobs(id, fiscal_year_id) ON DELETE CASCADE,
  CHECK (status <> 'valid' OR (account_number IS NOT NULL AND entry_date IS NOT NULL AND NOT (debit > 0 AND credit > 0)))
);
CREATE INDEX ledger_lines_account_idx ON public.ledger_lines (import_job_id, account_number, entry_date, source_row);
CREATE INDEX ledger_lines_entry_idx ON public.ledger_lines (import_job_id, journal_code, entry_number);
CREATE INDEX ledger_lines_date_idx ON public.ledger_lines (import_job_id, entry_date);

CREATE OR REPLACE FUNCTION public.guard_ledger_line() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_kind text; v_status text;
BEGIN
  SELECT kind, status INTO v_kind, v_status FROM public.import_jobs WHERE id = coalesce(NEW.import_job_id, OLD.import_job_id);
  IF v_kind <> 'ledger' THEN
    RAISE EXCEPTION 'Lignes de grand livre : import de grand livre requis' USING ERRCODE = 'check_violation';
  END IF;
  IF v_status IN ('completed','superseded') THEN
    RAISE EXCEPTION 'Grand livre validé : écritures figées (importez un nouveau fichier pour le remplacer)'
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN coalesce(NEW, OLD);
END $$;
CREATE TRIGGER ledger_lines_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ledger_lines
  FOR EACH ROW EXECUTE FUNCTION public.guard_ledger_line();
CREATE TRIGGER ledger_lines_closed_fy_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ledger_lines
  FOR EACH ROW EXECUTE FUNCTION public.guard_closed_fiscal_year();

-- Validation d'un grand livre : aucune ligne en erreur, équilibre global et par écriture vérifiés en base
CREATE OR REPLACE FUNCTION public.guard_ledger_completion() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_err int; v_valid int; v_d numeric; v_c numeric; v_unbal int; v_out int; v_fy public.fiscal_years;
BEGIN
  IF NEW.kind <> 'ledger' OR NEW.status <> 'completed' OR OLD.status = 'completed' THEN
    RETURN NEW;
  END IF;
  SELECT count(*) FILTER (WHERE status = 'error'), count(*) FILTER (WHERE status = 'valid'),
         coalesce(sum(debit) FILTER (WHERE status = 'valid'), 0), coalesce(sum(credit) FILTER (WHERE status = 'valid'), 0)
    INTO v_err, v_valid, v_d, v_c FROM public.ledger_lines WHERE import_job_id = NEW.id;
  IF v_err > 0 OR v_valid = 0 THEN
    RAISE EXCEPTION 'Grand livre : % ligne(s) en erreur, % ligne(s) valides', v_err, v_valid USING ERRCODE = 'check_violation';
  END IF;
  IF v_d <> v_c THEN
    RAISE EXCEPTION 'Grand livre déséquilibré : débit %, crédit %', v_d, v_c USING ERRCODE = 'check_violation';
  END IF;
  SELECT count(*) INTO v_unbal FROM (
    SELECT 1 FROM public.ledger_lines WHERE import_job_id = NEW.id AND status = 'valid' AND entry_number IS NOT NULL
     GROUP BY coalesce(journal_code, ''), entry_number HAVING sum(debit) <> sum(credit)) x;
  IF v_unbal > 0 THEN
    RAISE EXCEPTION 'Grand livre : % écriture(s) déséquilibrée(s)', v_unbal USING ERRCODE = 'check_violation';
  END IF;
  SELECT * INTO v_fy FROM public.fiscal_years WHERE id = NEW.fiscal_year_id;
  SELECT count(*) INTO v_out FROM public.ledger_lines
   WHERE import_job_id = NEW.id AND status = 'valid' AND entry_date NOT BETWEEN v_fy.start_date AND v_fy.end_date;
  IF v_out > 0 THEN
    RAISE EXCEPTION 'Grand livre : % écriture(s) hors de l''exercice', v_out USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER import_jobs_ledger_completion BEFORE UPDATE ON public.import_jobs
  FOR EACH ROW EXECUTE FUNCTION public.guard_ledger_completion();

ALTER TABLE public.ledger_lines ENABLE ROW LEVEL SECURITY;
CREATE POLICY ledger_lines_select ON public.ledger_lines FOR SELECT TO authenticated
  USING (authz.can_access_company(company_id) OR authz.audits_company(company_id));
CREATE POLICY ledger_lines_write ON public.ledger_lines FOR ALL TO authenticated
  USING (authz.has_company_role(company_id, ARRAY['accountant']))
  WITH CHECK (authz.has_company_role(company_id, ARRAY['accountant']));
GRANT SELECT, INSERT, UPDATE, DELETE ON public.ledger_lines TO authenticated;
GRANT ALL ON public.ledger_lines TO service_role;

-- ---------------------------------------------------------------------
-- 3. Audit financier : populations tirées des écritures du grand livre validé
-- ---------------------------------------------------------------------
ALTER TABLE public.fa_populations DROP CONSTRAINT fa_populations_source_check;
ALTER TABLE public.fa_populations DROP CONSTRAINT fa_populations_check;
ALTER TABLE public.fa_populations ADD CONSTRAINT fa_populations_source_check CHECK (source IN ('balance','file','ledger'));
ALTER TABLE public.fa_populations ADD COLUMN filters jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE public.fa_populations ADD CONSTRAINT fa_populations_check CHECK (
  (source IN ('balance','ledger') AND source_import_job_id IS NOT NULL)
  OR (source = 'file' AND source_evidence_id IS NOT NULL));
ALTER TABLE public.fa_population_items ADD COLUMN ledger_line_id uuid REFERENCES public.ledger_lines(id);

-- Une population « grand livre » vient du grand livre actif de l'exercice audité, et chaque élément
-- reprend exactement le montant net de sa ligne
CREATE OR REPLACE FUNCTION public.guard_fa_ledger_population() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_src text; v_job uuid; v_active uuid; v_amount numeric;
BEGIN
  IF TG_TABLE_NAME = 'fa_populations' THEN
    IF NEW.source = 'ledger' THEN
      SELECT f.active_ledger_import_job_id INTO v_active FROM public.engagements e
        JOIN public.fiscal_years f ON f.id = e.fiscal_year_id WHERE e.id = NEW.engagement_id;
      IF v_active IS NULL OR NEW.source_import_job_id <> v_active THEN
        RAISE EXCEPTION 'Population : grand livre validé de l''exercice de la mission requis' USING ERRCODE = 'check_violation';
      END IF;
    END IF;
    RETURN NEW;
  END IF;
  SELECT source, source_import_job_id INTO v_src, v_job FROM public.fa_populations WHERE id = NEW.population_id;
  IF v_src = 'ledger' THEN
    SELECT debit - credit INTO v_amount FROM public.ledger_lines
     WHERE id = NEW.ledger_line_id AND import_job_id = v_job AND status = 'valid';
    IF v_amount IS NULL OR v_amount <> NEW.amount THEN
      RAISE EXCEPTION 'Élément de population : ligne du grand livre introuvable ou montant différent' USING ERRCODE = 'check_violation';
    END IF;
  ELSIF NEW.ledger_line_id IS NOT NULL THEN
    RAISE EXCEPTION 'Ligne de grand livre réservée aux populations « grand livre »' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER fa_populations_ledger_guard BEFORE INSERT OR UPDATE ON public.fa_populations
  FOR EACH ROW EXECUTE FUNCTION public.guard_fa_ledger_population();
CREATE TRIGGER fa_population_items_ledger_guard BEFORE INSERT OR UPDATE ON public.fa_population_items
  FOR EACH ROW EXECUTE FUNCTION public.guard_fa_ledger_population();
