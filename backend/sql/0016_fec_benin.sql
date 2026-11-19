-- =====================================================================
-- KOFINEX — Migration 0016 : Fichier des Écritures Comptables (FEC) — DGI Bénin
-- Historique des générations (copie immuable du fichier, empreinte, résultat du contrôle) et traçabilité de chaque ligne
-- du fichier jusqu'à la ligne d'écriture native validée dont elle provient.
-- Les écritures sont lues dans journal_entries / journal_entry_lines (migration 0014) : aucune copie des écritures, aucun
-- second système de journaux. Une génération n'écrase jamais une génération antérieure.
-- =====================================================================
CREATE TABLE public.fec_exports (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id     uuid NOT NULL,
  company_id          uuid NOT NULL,
  fiscal_year_id      uuid NOT NULL,
  version_no          int  NOT NULL CHECK (version_no > 0),          -- rang de la génération pour l'exercice
  kind                text NOT NULL CHECK (kind IN ('final','working')),   -- définitive ou fichier de travail
  period_start        date NOT NULL,
  period_end          date NOT NULL,
  ifu                 text NOT NULL CHECK (length(btrim(ifu)) > 0),
  filename            text NOT NULL CHECK (filename ~ '^FEC_[A-Za-z0-9]+_[0-9]{8}\.(txt|csv)$'),
  file_format         text NOT NULL CHECK (file_format IN ('txt','csv')),
  encoding            text NOT NULL CHECK (encoding IN ('ascii','iso-8859-15')),
  -- art. 4 : zones séparées par une tabulation (le second caractère cité est absent du texte signé) ; enregistrements
  -- terminés par retour chariot et/ou fin de ligne ; aucune ligne d'en-tête (une ligne = une écriture comptable)
  field_separator     text NOT NULL CHECK (field_separator = 'tab'),
  record_separator    text NOT NULL CHECK (record_separator IN ('crlf','lf','cr')),
  max_lines_per_file  int  CHECK (max_lines_per_file IS NULL OR max_lines_per_file > 0),  -- fractionnement (art. 6)
  accounting_type     text NOT NULL CHECK (accounting_type IN ('accrual','cash')),  -- engagement ou trésorerie (champs 19 à 21)
  line_count          int  NOT NULL CHECK (line_count >= 0),
  entry_count         int  NOT NULL CHECK (entry_count >= 0),
  total_debit         numeric(20,2) NOT NULL,
  total_credit        numeric(20,2) NOT NULL,
  blocking_count      int  NOT NULL CHECK (blocking_count >= 0),
  warning_count       int  NOT NULL CHECK (warning_count >= 0),
  -- compliant : aucune anomalie bloquante et spécification confirmée ; spec_pending : aucune anomalie bloquante, mais
  -- paramètres réglementaires encore à confirmer contre l'arrêté ; non_compliant : anomalies bloquantes
  compliance          text NOT NULL CHECK (compliance IN ('compliant','spec_pending','non_compliant')),
  spec_version        text NOT NULL,
  spec_confirmed      boolean NOT NULL,
  anomalies           jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(anomalies) = 'array'),
  source_state        jsonb NOT NULL DEFAULT '{}'::jsonb,           -- état des sources à la génération (écritures, dernière validation)
  -- fichiers produits : un seul (FEC_IFU_AAAAMMJJ) ou, s'il est scindé, FEC_IFU_AAAAMMJJ_1 à _n (art. 6)
  -- [{part, filename, storage_path, size_bytes, sha256, line_count}]
  parts               jsonb NOT NULL CHECK (jsonb_typeof(parts) = 'array' AND jsonb_array_length(parts) >= 1),
  size_bytes          bigint NOT NULL CHECK (size_bytes > 0),
  sha256              char(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),   -- empreinte de l'ensemble des fichiers
  doc_storage_path    text NOT NULL,
  doc_sha256          char(64) NOT NULL CHECK (doc_sha256 ~ '^[0-9a-f]{64}$'),
  generator_version   text NOT NULL,
  generated_by        uuid NOT NULL REFERENCES public.profiles(id),
  generated_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id, company_id),
  UNIQUE (company_id, fiscal_year_id, version_no),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (fiscal_year_id, company_id) REFERENCES public.fiscal_years(id, company_id),
  CHECK (period_end >= period_start),
  CHECK ((compliance = 'non_compliant') = (blocking_count > 0)),
  CHECK (compliance <> 'compliant' OR spec_confirmed),
  CHECK (kind = 'working' OR blocking_count = 0)                      -- une génération définitive est sans anomalie bloquante
);
CREATE INDEX fec_exports_company_idx ON public.fec_exports (company_id, fiscal_year_id, generated_at DESC);

-- Traçabilité : ligne n du fichier → ligne d'écriture native validée
CREATE TABLE public.fec_export_lines (
  export_id        uuid NOT NULL,
  row_no           int  NOT NULL CHECK (row_no > 0),
  organization_id  uuid NOT NULL,
  company_id       uuid NOT NULL,
  entry_id         uuid NOT NULL,
  entry_line_id    uuid NOT NULL,
  PRIMARY KEY (export_id, row_no),
  UNIQUE (export_id, entry_line_id),                                  -- une ligne d'écriture n'apparaît qu'une fois
  FOREIGN KEY (export_id, company_id) REFERENCES public.fec_exports(id, company_id) ON DELETE CASCADE,
  FOREIGN KEY (entry_id, company_id) REFERENCES public.journal_entries(id, company_id),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------------
-- Gardes : copie immuable, auteur authentifié, version suivante, exercice et période cohérents, sources validées
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.guard_fec_export() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_fy record; v_next int; v_n int; v_name text; v_expected text; v_lines int := 0;
BEGIN
  IF TG_OP <> 'INSERT' THEN
    RAISE EXCEPTION 'FEC : génération figée (ni modification ni suppression) ; générez une nouvelle version'
      USING ERRCODE = 'check_violation';
  END IF;
  -- droit vérifié avant toute lecture (fonction SECURITY DEFINER : rien ne doit filtrer vers un tiers)
  IF NOT authz.has_company_role(NEW.company_id, ARRAY['accountant']) THEN
    RAISE EXCEPTION 'FEC : génération réservée aux comptables et administrateurs de l''entreprise'
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF NEW.generated_by IS DISTINCT FROM auth.uid() THEN
    RAISE EXCEPTION 'FEC : généré au nom de l''utilisateur authentifié' USING ERRCODE = 'insufficient_privilege';
  END IF;
  SELECT start_date, end_date INTO v_fy FROM public.fiscal_years WHERE id = NEW.fiscal_year_id AND company_id = NEW.company_id;
  IF NEW.period_start < v_fy.start_date OR NEW.period_end > v_fy.end_date THEN
    RAISE EXCEPTION 'FEC : période comprise dans l''exercice' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.filename !~ ('_' || to_char(v_fy.end_date, 'YYYYMMDD') || '\.') THEN
    RAISE EXCEPTION 'FEC : le nom du fichier porte la date de clôture de l''exercice' USING ERRCODE = 'check_violation';
  END IF;
  PERFORM pg_advisory_xact_lock(hashtext('fec:' || NEW.company_id::text || ':' || NEW.fiscal_year_id::text));
  SELECT coalesce(max(version_no), 0) + 1 INTO v_next FROM public.fec_exports
   WHERE company_id = NEW.company_id AND fiscal_year_id = NEW.fiscal_year_id;
  IF NEW.version_no <> v_next THEN
    RAISE EXCEPTION 'FEC : version % attendue', v_next USING ERRCODE = 'check_violation';
  END IF;
  -- noms des fichiers : unique = nom réglementaire ; scindé = suffixes _1 à _n consécutifs
  v_n := jsonb_array_length(NEW.parts);
  FOR i IN 1..v_n LOOP
    v_name := NEW.parts -> (i - 1) ->> 'filename';
    v_expected := CASE WHEN v_n = 1 THEN NEW.filename
                       ELSE regexp_replace(NEW.filename, '\.(txt|csv)$', '_' || i || '.\1') END;
    IF v_name IS DISTINCT FROM v_expected
       OR (NEW.parts -> (i - 1) ->> 'sha256') !~ '^[0-9a-f]{64}$'
       OR coalesce((NEW.parts -> (i - 1) ->> 'storage_path'), '') !~ ('^' || NEW.organization_id || '/' || NEW.company_id || '/') THEN
      RAISE EXCEPTION 'FEC : fichier % non conforme au nommage FEC_IFU_AAAAMMJJ[_X] ou au rangement de l''entreprise', i
        USING ERRCODE = 'check_violation';
    END IF;
    v_lines := v_lines + coalesce((NEW.parts -> (i - 1) ->> 'line_count')::int, -1);
  END LOOP;
  IF v_lines <> NEW.line_count THEN
    RAISE EXCEPTION 'FEC : le nombre de lignes des fichiers ne correspond pas au total' USING ERRCODE = 'check_violation';
  END IF;
  NEW.generated_at := now();
  RETURN NEW;
END $$;
CREATE TRIGGER fec_exports_guard BEFORE INSERT OR UPDATE OR DELETE ON public.fec_exports
  FOR EACH ROW EXECUTE FUNCTION public.guard_fec_export();
CREATE TRIGGER fec_exports_audit AFTER INSERT ON public.fec_exports
  FOR EACH ROW EXECUTE FUNCTION public.audit_row_change();
CREATE TRIGGER "0_not_ai" BEFORE INSERT OR UPDATE OR DELETE ON public.fec_exports
  FOR EACH ROW EXECUTE FUNCTION public.guard_not_ai();

CREATE OR REPLACE FUNCTION public.guard_fec_export_line() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v record;
BEGIN
  IF TG_OP <> 'INSERT' THEN
    RAISE EXCEPTION 'FEC : traçabilité figée' USING ERRCODE = 'check_violation';
  END IF;
  IF NOT authz.has_company_role(NEW.company_id, ARRAY['accountant']) THEN
    RAISE EXCEPTION 'FEC : traçabilité réservée aux comptables et administrateurs de l''entreprise'
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  SELECT e.status, e.fiscal_year_id, l.entry_id INTO v
    FROM public.journal_entry_lines l JOIN public.journal_entries e ON e.id = l.entry_id
   WHERE l.id = NEW.entry_line_id AND l.company_id = NEW.company_id;
  IF v.entry_id IS DISTINCT FROM NEW.entry_id OR v.status NOT IN ('validated','reversed')
     OR v.fiscal_year_id IS DISTINCT FROM (SELECT fiscal_year_id FROM public.fec_exports WHERE id = NEW.export_id) THEN
    RAISE EXCEPTION 'FEC : seules les lignes d''écritures validées de l''exercice sont reprises' USING ERRCODE = 'check_violation';
  END IF;
  IF (SELECT generated_by FROM public.fec_exports WHERE id = NEW.export_id) IS DISTINCT FROM auth.uid() THEN
    RAISE EXCEPTION 'FEC : traçabilité écrite par l''auteur de la génération' USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER fec_export_lines_guard BEFORE INSERT OR UPDATE OR DELETE ON public.fec_export_lines
  FOR EACH ROW EXECUTE FUNCTION public.guard_fec_export_line();
CREATE TRIGGER "0_not_ai" BEFORE INSERT OR UPDATE OR DELETE ON public.fec_export_lines
  FOR EACH ROW EXECUTE FUNCTION public.guard_not_ai();

-- ---------------------------------------------------------------------
-- RLS : comptables et administrateurs de l'entreprise uniquement (le FEC contient toutes les écritures, paie comprise)
-- ---------------------------------------------------------------------
ALTER TABLE public.fec_exports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.fec_export_lines ENABLE ROW LEVEL SECURITY;
CREATE POLICY fec_exports_select ON public.fec_exports FOR SELECT TO authenticated
  USING (authz.has_company_role(company_id, ARRAY['accountant']));
CREATE POLICY fec_exports_insert ON public.fec_exports FOR INSERT TO authenticated
  WITH CHECK (authz.has_company_role(company_id, ARRAY['accountant']));
CREATE POLICY fec_export_lines_select ON public.fec_export_lines FOR SELECT TO authenticated
  USING (authz.has_company_role(company_id, ARRAY['accountant']));
CREATE POLICY fec_export_lines_insert ON public.fec_export_lines FOR INSERT TO authenticated
  WITH CHECK (authz.has_company_role(company_id, ARRAY['accountant']));
REVOKE UPDATE, DELETE ON public.fec_exports, public.fec_export_lines FROM authenticated;
GRANT SELECT, INSERT ON public.fec_exports, public.fec_export_lines TO authenticated;
GRANT ALL ON public.fec_exports, public.fec_export_lines TO service_role;

-- ---------------------------------------------------------------------
-- Stockage : bucket privé ; dépôt par l'API (clé de service), lecture réservée aux comptables et administrateurs
-- ---------------------------------------------------------------------
DO $outer$
BEGIN
  IF to_regclass('storage.buckets') IS NULL OR to_regclass('storage.objects') IS NULL THEN
    RAISE NOTICE 'Schéma storage absent : bucket FEC non créé';
    RETURN;
  END IF;
  INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
  VALUES ('fec', 'fec', false, 524288000, ARRAY['text/plain', 'text/csv'])
  ON CONFLICT (id) DO UPDATE SET public = false, file_size_limit = EXCLUDED.file_size_limit,
                                 allowed_mime_types = EXCLUDED.allowed_mime_types;
  EXECUTE $p$
    CREATE POLICY fec_files_read ON storage.objects FOR SELECT TO authenticated
      USING (bucket_id = 'fec' AND authz.has_company_role(authz.storage_object_company(name), ARRAY['accountant']))$p$;
END $outer$;
