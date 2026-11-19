-- =====================================================================
-- KOFINEX — Migration 0014 : comptabilité générale native (lot 3B, étapes A et B)
-- Paramètres, plan comptable de l'entreprise, tiers, journaux, séquences, écritures natives et leurs lignes,
-- historique du circuit de validation, lettrage.
--
-- Les écritures natives sont distinctes des grands livres importés (ledger_lines, lot 3) et des balances
-- importées (trial_balance_entries) : ces tables ne sont ni lues ni modifiées ici.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 0. Pièces justificatives : nouveau type de document (ensemble élargi, aucune valeur retirée)
-- ---------------------------------------------------------------------
ALTER TABLE public.financial_documents DROP CONSTRAINT financial_documents_document_type_check;
ALTER TABLE public.financial_documents ADD CONSTRAINT financial_documents_document_type_check CHECK (document_type IN
  ('trial_balance','financial_statements','general_ledger','tax_return','budget','other','accounting_voucher'));

-- ---------------------------------------------------------------------
-- 1. Paramètres comptables de l'entreprise (absence de ligne = valeurs par défaut)
-- ---------------------------------------------------------------------
CREATE TABLE public.accounting_settings (
  company_id           uuid PRIMARY KEY,
  organization_id      uuid NOT NULL,
  review_required      boolean NOT NULL DEFAULT false,   -- étape « en revue » avant validation
  segregation_required boolean NOT NULL DEFAULT true,    -- le validateur n'est pas l'auteur
  updated_by           uuid REFERENCES public.profiles(id),
  updated_at           timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE
);

CREATE OR REPLACE FUNCTION public.acc_review_required(p_company uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT coalesce((SELECT review_required FROM public.accounting_settings WHERE company_id = p_company), false)
$$;
CREATE OR REPLACE FUNCTION public.acc_segregation_required(p_company uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT coalesce((SELECT segregation_required FROM public.accounting_settings WHERE company_id = p_company), true)
$$;

-- ---------------------------------------------------------------------
-- 2. Plan comptable de l'entreprise : comptes ouverts, chacun rattaché à un compte du référentiel publié
-- ---------------------------------------------------------------------
CREATE TABLE public.company_accounts (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id       uuid NOT NULL,
  company_id            uuid NOT NULL,
  account_number        varchar(20) NOT NULL CHECK (account_number ~ '^[1-9][0-9]{1,19}$'),
  label                 text NOT NULL CHECK (length(btrim(label)) > 0),
  framework_version_id  uuid NOT NULL REFERENCES public.framework_versions(id),
  chart_account_number  varchar(20) NOT NULL,
  nature                text,              -- copiée du référentiel au rattachement
  requires_third_party  boolean NOT NULL DEFAULT false,   -- compte collectif : tiers obligatoire sur chaque ligne
  third_party_kind      text CHECK (third_party_kind IS NULL OR third_party_kind IN
                          ('customer','supplier','employee','tax_authority','social_body','other')),
  lettering_enabled     boolean NOT NULL DEFAULT false,
  is_active             boolean NOT NULL DEFAULT true,
  created_by            uuid NOT NULL REFERENCES public.profiles(id),
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_id, account_number),
  UNIQUE (id, company_id),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  CHECK (account_number LIKE chart_account_number || '%'),
  CHECK (third_party_kind IS NULL OR requires_third_party)
);

CREATE OR REPLACE FUNCTION public.guard_company_account() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_status text; v_nature text; v_used boolean;
BEGIN
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;   -- compte utilisé : refus par la clé étrangère des lignes
  SELECT v.status INTO v_status FROM public.framework_versions v WHERE v.id = NEW.framework_version_id;
  IF v_status IS DISTINCT FROM 'published' AND (TG_OP = 'INSERT' OR NEW.framework_version_id IS DISTINCT FROM OLD.framework_version_id) THEN
    RAISE EXCEPTION 'Le compte doit être rattaché à une version publiée du référentiel' USING ERRCODE = 'check_violation';
  END IF;
  SELECT c.nature INTO v_nature FROM public.chart_of_accounts c
   WHERE c.framework_version_id = NEW.framework_version_id AND c.account_number = NEW.chart_account_number;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Compte % absent du plan de comptes du référentiel', NEW.chart_account_number USING ERRCODE = 'check_violation';
  END IF;
  NEW.nature := v_nature;
  IF TG_OP = 'INSERT' THEN
    NEW.created_by := coalesce(auth.uid(), NEW.created_by);
  ELSE
    IF NEW.company_id <> OLD.company_id OR NEW.organization_id <> OLD.organization_id OR NEW.created_by <> OLD.created_by THEN
      RAISE EXCEPTION 'Compte : entreprise et auteur non modifiables' USING ERRCODE = 'check_violation';
    END IF;
    SELECT EXISTS (SELECT 1 FROM public.journal_entry_lines l WHERE l.company_id = OLD.company_id AND l.account_number = OLD.account_number)
      INTO v_used;
    IF v_used AND (NEW.account_number <> OLD.account_number OR NEW.chart_account_number <> OLD.chart_account_number
                   OR NEW.requires_third_party <> OLD.requires_third_party) THEN
      RAISE EXCEPTION 'Compte % déjà mouvementé : numéro, rattachement et caractère collectif non modifiables', OLD.account_number
        USING ERRCODE = 'check_violation';
    END IF;
    NEW.updated_at := now();
  END IF;
  RETURN NEW;
END $$;

-- ---------------------------------------------------------------------
-- 3. Tiers
-- ---------------------------------------------------------------------
CREATE TABLE public.third_parties (
  id                         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id            uuid NOT NULL,
  company_id                 uuid NOT NULL,
  code                       text NOT NULL CHECK (code ~ '^[A-Za-z0-9._-]{1,30}$'),
  name                       text NOT NULL CHECK (length(btrim(name)) > 0),
  kind                       text NOT NULL CHECK (kind IN ('customer','supplier','employee','tax_authority','social_body','other')),
  collective_account_number  varchar(20),
  tax_id                     text,
  registration_number        text,
  address                    text,
  city                       text,
  country_code               char(2),
  email                      text,
  phone                      text,
  is_active                  boolean NOT NULL DEFAULT true,
  created_by                 uuid NOT NULL REFERENCES public.profiles(id),
  created_at                 timestamptz NOT NULL DEFAULT now(),
  updated_at                 timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_id, code),
  UNIQUE (id, company_id),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (company_id, collective_account_number) REFERENCES public.company_accounts(company_id, account_number)
);

CREATE OR REPLACE FUNCTION public.guard_third_party() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_acc public.company_accounts;
BEGIN
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  IF NEW.collective_account_number IS NOT NULL THEN
    SELECT * INTO v_acc FROM public.company_accounts WHERE company_id = NEW.company_id AND account_number = NEW.collective_account_number;
    IF NOT v_acc.requires_third_party OR (v_acc.third_party_kind IS NOT NULL AND v_acc.third_party_kind <> NEW.kind) THEN
      RAISE EXCEPTION 'Le compte % n''est pas un compte collectif de ce type de tiers', NEW.collective_account_number
        USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  IF TG_OP = 'INSERT' THEN
    NEW.created_by := coalesce(auth.uid(), NEW.created_by);
  ELSE
    IF NEW.company_id <> OLD.company_id OR NEW.created_by <> OLD.created_by THEN
      RAISE EXCEPTION 'Tiers : entreprise et auteur non modifiables' USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.code <> OLD.code AND EXISTS (SELECT 1 FROM public.journal_entry_lines WHERE third_party_id = OLD.id) THEN
      RAISE EXCEPTION 'Tiers déjà mouvementé : code non modifiable' USING ERRCODE = 'check_violation';
    END IF;
    NEW.updated_at := now();
  END IF;
  RETURN NEW;
END $$;

-- ---------------------------------------------------------------------
-- 4. Journaux et séquences de numérotation
-- ---------------------------------------------------------------------
CREATE TABLE public.journals (
  id                          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id             uuid NOT NULL,
  company_id                  uuid NOT NULL,
  code                        text NOT NULL CHECK (code ~ '^[A-Z0-9]{1,8}$'),
  label                       text NOT NULL CHECK (length(btrim(label)) > 0),
  journal_type                text NOT NULL CHECK (journal_type IN
                                ('purchases','sales','bank','cash','general','payroll','fixed_assets','inventory','opening')),
  number_prefix               text NOT NULL CHECK (number_prefix ~ '^[A-Z0-9_-]{0,12}$'),
  counterpart_account_number  varchar(20),   -- banque / caisse : compte de trésorerie du journal
  allowed_users               uuid[],        -- NULL : tous les comptables ; sinon utilisateurs autorisés (administrateurs toujours)
  is_active                   boolean NOT NULL DEFAULT true,
  created_by                  uuid NOT NULL REFERENCES public.profiles(id),
  created_at                  timestamptz NOT NULL DEFAULT now(),
  updated_at                  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_id, code),
  UNIQUE (id, company_id),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (company_id, counterpart_account_number) REFERENCES public.company_accounts(company_id, account_number)
);

CREATE OR REPLACE FUNCTION public.guard_journal() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;   -- journal mouvementé : refus par la clé étrangère des écritures
  IF TG_OP = 'INSERT' THEN
    NEW.created_by := coalesce(auth.uid(), NEW.created_by);
    RETURN NEW;
  END IF;
  IF NEW.company_id <> OLD.company_id OR NEW.created_by <> OLD.created_by THEN
    RAISE EXCEPTION 'Journal : entreprise et auteur non modifiables' USING ERRCODE = 'check_violation';
  END IF;
  IF (NEW.code <> OLD.code OR NEW.journal_type <> OLD.journal_type OR NEW.number_prefix <> OLD.number_prefix)
     AND EXISTS (SELECT 1 FROM public.journal_entries WHERE journal_id = OLD.id) THEN
    RAISE EXCEPTION 'Journal % déjà utilisé : code, type et préfixe de numérotation non modifiables', OLD.code
      USING ERRCODE = 'check_violation';
  END IF;
  NEW.updated_at := now();
  RETURN NEW;
END $$;

CREATE TABLE public.journal_sequences (
  journal_id      uuid NOT NULL,
  fiscal_year_id  uuid NOT NULL,
  organization_id uuid NOT NULL,
  company_id      uuid NOT NULL,
  last_number     int NOT NULL CHECK (last_number >= 0),
  PRIMARY KEY (journal_id, fiscal_year_id),
  FOREIGN KEY (journal_id, company_id) REFERENCES public.journals(id, company_id) ON DELETE CASCADE,
  FOREIGN KEY (fiscal_year_id, company_id) REFERENCES public.fiscal_years(id, company_id) ON DELETE CASCADE
);

-- Numéro suivant : verrou de ligne, aucun trou (l'incrément est annulé avec la transaction qui échoue)
CREATE OR REPLACE FUNCTION public.je_next_number(p_journal uuid, p_fy uuid) RETURNS int
LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
  INSERT INTO public.journal_sequences (journal_id, fiscal_year_id, organization_id, company_id, last_number)
  SELECT j.id, p_fy, j.organization_id, j.company_id, 1 FROM public.journals j WHERE j.id = p_journal
  ON CONFLICT (journal_id, fiscal_year_id) DO UPDATE SET last_number = public.journal_sequences.last_number + 1
  RETURNING last_number
$$;
REVOKE ALL ON FUNCTION public.je_next_number(uuid, uuid) FROM PUBLIC, authenticated;

-- ---------------------------------------------------------------------
-- 5. Écritures natives
-- ---------------------------------------------------------------------
CREATE TABLE public.journal_entries (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id       uuid NOT NULL,
  company_id            uuid NOT NULL,
  fiscal_year_id        uuid NOT NULL,
  journal_id            uuid NOT NULL,
  entry_date            date NOT NULL,
  piece_ref             text,
  piece_date            date,
  label                 text NOT NULL CHECK (length(btrim(label)) > 0),
  third_party_id        uuid,
  -- provenance : saisie, génération depuis un auxiliaire, travaux d'inventaire, extourne, correction, à-nouveaux
  origin                text NOT NULL DEFAULT 'manual'
                          CHECK (origin IN ('manual','generated','inventory','reversal','correction','opening')),
  source_type           text,
  source_id             uuid,
  reverses_entry_id     uuid,
  corrects_entry_id     uuid,
  status                text NOT NULL DEFAULT 'draft'
                          CHECK (status IN ('draft','submitted','under_review','validated','rejected','reversed')),
  number                text,
  sequence_no           int,
  total_debit           numeric(20,2) NOT NULL DEFAULT 0,
  total_credit          numeric(20,2) NOT NULL DEFAULT 0,
  line_count            int NOT NULL DEFAULT 0,
  created_by            uuid NOT NULL REFERENCES public.profiles(id),
  submitted_by          uuid REFERENCES public.profiles(id),
  submitted_at          timestamptz,
  reviewed_by           uuid REFERENCES public.profiles(id),
  reviewed_at           timestamptz,
  validated_by          uuid REFERENCES public.profiles(id),
  validated_at          timestamptz,
  rejected_by           uuid REFERENCES public.profiles(id),
  rejected_at           timestamptz,
  rejection_reason      text,
  reversed_by_entry_id  uuid,
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id, company_id),
  UNIQUE (journal_id, fiscal_year_id, number),
  UNIQUE (journal_id, fiscal_year_id, sequence_no),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (fiscal_year_id, company_id) REFERENCES public.fiscal_years(id, company_id),
  FOREIGN KEY (journal_id, company_id) REFERENCES public.journals(id, company_id),
  FOREIGN KEY (third_party_id, company_id) REFERENCES public.third_parties(id, company_id),
  FOREIGN KEY (reverses_entry_id, company_id) REFERENCES public.journal_entries(id, company_id),
  FOREIGN KEY (corrects_entry_id, company_id) REFERENCES public.journal_entries(id, company_id),
  FOREIGN KEY (reversed_by_entry_id, company_id) REFERENCES public.journal_entries(id, company_id),
  CHECK ((status IN ('validated','reversed')) = (number IS NOT NULL AND sequence_no IS NOT NULL AND validated_by IS NOT NULL)),
  CHECK ((origin = 'reversal') = (reverses_entry_id IS NOT NULL)),
  CHECK ((origin = 'correction') = (corrects_entry_id IS NOT NULL)),
  CHECK ((origin = 'generated') = (source_type IS NOT NULL AND source_id IS NOT NULL)),
  CHECK ((status = 'reversed') = (reversed_by_entry_id IS NOT NULL)),
  CHECK (status <> 'rejected' OR length(btrim(coalesce(rejection_reason, ''))) >= 5)
);
CREATE INDEX journal_entries_fy_idx ON public.journal_entries (company_id, fiscal_year_id, status, entry_date);
CREATE INDEX journal_entries_journal_idx ON public.journal_entries (journal_id, entry_date);
-- une seule extourne en cours ou validée par écriture ; une seule écriture par opération source
CREATE UNIQUE INDEX journal_entries_one_reversal_uq ON public.journal_entries (reverses_entry_id)
  WHERE reverses_entry_id IS NOT NULL AND status <> 'rejected';
CREATE UNIQUE INDEX journal_entries_one_posting_uq ON public.journal_entries (company_id, source_type, source_id)
  WHERE source_id IS NOT NULL AND status <> 'rejected';

CREATE TABLE public.journal_entry_lines (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id   uuid NOT NULL,
  company_id        uuid NOT NULL,
  fiscal_year_id    uuid NOT NULL,
  entry_id          uuid NOT NULL,
  line_no           int NOT NULL CHECK (line_no > 0),
  account_number    varchar(20) NOT NULL,
  third_party_id    uuid,
  label             text,
  debit             numeric(20,2) NOT NULL DEFAULT 0 CHECK (debit >= 0),
  credit            numeric(20,2) NOT NULL DEFAULT 0 CHECK (credit >= 0),
  cost_center_id    uuid,
  currency          char(3),
  currency_amount   numeric(20,2),
  lettering_id      uuid,
  UNIQUE (entry_id, line_no),
  FOREIGN KEY (entry_id, company_id) REFERENCES public.journal_entries(id, company_id) ON DELETE CASCADE,
  FOREIGN KEY (company_id, account_number) REFERENCES public.company_accounts(company_id, account_number)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  FOREIGN KEY (third_party_id, company_id) REFERENCES public.third_parties(id, company_id),
  FOREIGN KEY (cost_center_id, company_id) REFERENCES public.cost_centers(id, company_id),
  FOREIGN KEY (fiscal_year_id, company_id) REFERENCES public.fiscal_years(id, company_id),
  CHECK ((debit > 0) <> (credit > 0)),
  CHECK ((currency IS NULL) = (currency_amount IS NULL))
);
CREATE INDEX journal_entry_lines_account_idx ON public.journal_entry_lines (company_id, fiscal_year_id, account_number);
CREATE INDEX journal_entry_lines_tp_idx ON public.journal_entry_lines (third_party_id) WHERE third_party_id IS NOT NULL;

-- Pièces justificatives rattachées (fichiers dans financial_documents)
CREATE TABLE public.journal_entry_attachments (
  entry_id        uuid NOT NULL,
  document_id     uuid NOT NULL REFERENCES public.financial_documents(id),
  organization_id uuid NOT NULL,
  company_id      uuid NOT NULL,
  attached_by     uuid NOT NULL REFERENCES public.profiles(id),
  attached_at     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (entry_id, document_id),
  FOREIGN KEY (entry_id, company_id) REFERENCES public.journal_entries(id, company_id) ON DELETE CASCADE
);

-- Historique du circuit (écrit uniquement par les déclencheurs ; jamais modifié ni supprimé)
CREATE TABLE public.journal_entry_events (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  company_id      uuid NOT NULL,
  entry_id        uuid NOT NULL,       -- sans clé étrangère : l'historique survit à la suppression d'un brouillon
  action          text NOT NULL,
  from_status     text,
  to_status       text,
  actor           uuid,
  reason          text,
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX journal_entry_events_entry_idx ON public.journal_entry_events (entry_id, created_at);

-- Lettrages (complets : les lignes lettrées ensemble s'équilibrent ; voir § 9)
CREATE TABLE public.letterings (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  company_id      uuid NOT NULL,
  account_number  varchar(20) NOT NULL,
  third_party_id  uuid,
  code            text NOT NULL CHECK (code ~ '^[A-Z]{1,6}$'),
  amount          numeric(20,2) NOT NULL CHECK (amount > 0),
  created_by      uuid NOT NULL REFERENCES public.profiles(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_id, account_number, code),
  UNIQUE (id, company_id),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  FOREIGN KEY (company_id, account_number) REFERENCES public.company_accounts(company_id, account_number),
  FOREIGN KEY (third_party_id, company_id) REFERENCES public.third_parties(id, company_id)
);
ALTER TABLE public.journal_entry_lines
  ADD CONSTRAINT journal_entry_lines_lettering_fk FOREIGN KEY (lettering_id, company_id)
  REFERENCES public.letterings(id, company_id) ON DELETE SET NULL (lettering_id);

-- ---------------------------------------------------------------------
-- 6. Contrôles d'une écriture (soumission et validation)
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.je_check(p_entry uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE e public.journal_entries; j public.journals; fy public.fiscal_years;
        v_n int; v_d numeric; v_c numeric; v_bad text; v_diff int;
BEGIN
  SELECT * INTO e FROM public.journal_entries WHERE id = p_entry;
  SELECT * INTO j FROM public.journals WHERE id = e.journal_id;
  SELECT * INTO fy FROM public.fiscal_years WHERE id = e.fiscal_year_id;
  IF NOT j.is_active THEN
    RAISE EXCEPTION 'Journal % désactivé', j.code USING ERRCODE = 'check_violation';
  END IF;
  IF e.entry_date NOT BETWEEN fy.start_date AND fy.end_date THEN
    RAISE EXCEPTION 'Date % hors de l''exercice %', e.entry_date, fy.label USING ERRCODE = 'check_violation';
  END IF;
  SELECT count(*), coalesce(sum(debit), 0), coalesce(sum(credit), 0) INTO v_n, v_d, v_c
    FROM public.journal_entry_lines WHERE entry_id = p_entry;
  IF v_n < 2 THEN
    RAISE EXCEPTION 'Écriture incomplète : au moins deux lignes' USING ERRCODE = 'check_violation';
  END IF;
  IF v_d <> v_c THEN
    RAISE EXCEPTION 'Écriture déséquilibrée : débit %, crédit %, écart %', v_d, v_c, v_d - v_c USING ERRCODE = 'check_violation';
  END IF;
  SELECT string_agg(l.account_number, ', ') INTO v_bad FROM public.journal_entry_lines l
    JOIN public.company_accounts a ON a.company_id = l.company_id AND a.account_number = l.account_number
   WHERE l.entry_id = p_entry AND NOT a.is_active;
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION 'Compte(s) désactivé(s) : %', v_bad USING ERRCODE = 'check_violation';
  END IF;
  SELECT string_agg(l.account_number, ', ') INTO v_bad FROM public.journal_entry_lines l
    JOIN public.company_accounts a ON a.company_id = l.company_id AND a.account_number = l.account_number
   WHERE l.entry_id = p_entry AND a.requires_third_party AND l.third_party_id IS NULL;
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION 'Tiers obligatoire sur le(s) compte(s) collectif(s) : %', v_bad USING ERRCODE = 'check_violation';
  END IF;
  SELECT string_agg(DISTINCT t.code, ', ') INTO v_bad FROM public.journal_entry_lines l
    JOIN public.company_accounts a ON a.company_id = l.company_id AND a.account_number = l.account_number
    JOIN public.third_parties t ON t.id = l.third_party_id
   WHERE l.entry_id = p_entry AND (NOT t.is_active OR (a.third_party_kind IS NOT NULL AND a.third_party_kind <> t.kind));
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION 'Tiers inactif ou d''un type incompatible avec le compte : %', v_bad USING ERRCODE = 'check_violation';
  END IF;
  -- extourne : exact miroir de l'écriture d'origine (mêmes comptes, tiers et montants, sens inversé)
  IF e.origin = 'reversal' THEN
    SELECT count(*) INTO v_diff FROM (
      (SELECT account_number, third_party_id, sum(debit) AS d, sum(credit) AS c FROM public.journal_entry_lines
        WHERE entry_id = e.reverses_entry_id GROUP BY 1, 2
       EXCEPT
       SELECT account_number, third_party_id, sum(credit), sum(debit) FROM public.journal_entry_lines
        WHERE entry_id = p_entry GROUP BY 1, 2)
      UNION ALL
      (SELECT account_number, third_party_id, sum(credit), sum(debit) FROM public.journal_entry_lines
        WHERE entry_id = p_entry GROUP BY 1, 2
       EXCEPT
       SELECT account_number, third_party_id, sum(debit), sum(credit) FROM public.journal_entry_lines
        WHERE entry_id = e.reverses_entry_id GROUP BY 1, 2)) x;
    IF v_diff > 0 THEN
      RAISE EXCEPTION 'Extourne : les lignes doivent inverser exactement celles de l''écriture d''origine' USING ERRCODE = 'check_violation';
    END IF;
  END IF;
END $$;
REVOKE ALL ON FUNCTION public.je_check(uuid) FROM PUBLIC, authenticated;

-- ---------------------------------------------------------------------
-- 7. Circuit de validation (déclencheur avant) : transitions, auteurs, immutabilité, numérotation
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.guard_journal_entry() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE j public.journals; v_role text; v_uid uuid := auth.uid(); v_orig public.journal_entries; v_seq int; v_jt text;
BEGIN
  -- ------------------------------------------------ suppression : brouillon ou écriture rejetée, par son auteur
  IF TG_OP = 'DELETE' THEN
    IF OLD.status NOT IN ('draft','rejected') THEN
      RAISE EXCEPTION 'Écriture % : seule une écriture en brouillon ou rejetée peut être supprimée', coalesce(OLD.number, OLD.id::text)
        USING ERRCODE = 'check_violation';
    END IF;
    IF v_uid IS NOT NULL AND OLD.created_by <> v_uid THEN
      RAISE EXCEPTION 'Seul l''auteur peut supprimer son brouillon' USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN OLD;
  END IF;

  SELECT * INTO j FROM public.journals WHERE id = NEW.journal_id;
  IF j.company_id IS DISTINCT FROM NEW.company_id THEN
    RAISE EXCEPTION 'Journal d''une autre entreprise' USING ERRCODE = 'check_violation';
  END IF;

  -- ------------------------------------------------ création
  IF TG_OP = 'INSERT' THEN
    IF NEW.status <> 'draft' OR NEW.number IS NOT NULL OR NEW.submitted_by IS NOT NULL OR NEW.validated_by IS NOT NULL
       OR NEW.reviewed_by IS NOT NULL OR NEW.rejected_by IS NOT NULL OR NEW.reversed_by_entry_id IS NOT NULL THEN
      RAISE EXCEPTION 'Une écriture est créée en brouillon' USING ERRCODE = 'check_violation';
    END IF;
    NEW.created_by := coalesce(v_uid, NEW.created_by);
    NEW.total_debit := 0; NEW.total_credit := 0; NEW.line_count := 0;
    IF NOT j.is_active THEN
      RAISE EXCEPTION 'Journal % désactivé' , j.code USING ERRCODE = 'check_violation';
    END IF;
    IF v_uid IS NOT NULL AND j.allowed_users IS NOT NULL AND authz.company_role(NEW.company_id) IS DISTINCT FROM 'org_admin'
       AND NOT (v_uid = ANY (j.allowed_users)) THEN
      RAISE EXCEPTION 'Journal % réservé à d''autres utilisateurs', j.code USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.origin = 'generated' AND coalesce(current_setting('kofinex.posting_engine', true), '') <> 'on' THEN
      RAISE EXCEPTION 'Écriture générée : réservée au moteur de génération comptable' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.origin = 'opening' AND j.journal_type <> 'opening' THEN
      RAISE EXCEPTION 'Écriture d''à-nouveaux : journal d''à-nouveaux requis' USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.origin = 'reversal' THEN
      SELECT * INTO v_orig FROM public.journal_entries WHERE id = NEW.reverses_entry_id;
      IF v_orig.status <> 'validated' THEN
        RAISE EXCEPTION 'Seule une écriture validée peut être extournée' USING ERRCODE = 'check_violation';
      END IF;
      IF NEW.fiscal_year_id <> v_orig.fiscal_year_id THEN
        RAISE EXCEPTION 'L''extourne est passée dans l''exercice de l''écriture d''origine' USING ERRCODE = 'check_violation';
      END IF;
      IF NEW.entry_date < v_orig.entry_date THEN
        RAISE EXCEPTION 'L''extourne ne peut pas être antérieure à l''écriture d''origine' USING ERRCODE = 'check_violation';
      END IF;
    END IF;
    IF NEW.origin = 'correction' THEN
      SELECT * INTO v_orig FROM public.journal_entries WHERE id = NEW.corrects_entry_id;
      IF v_orig.status NOT IN ('validated','reversed') THEN
        RAISE EXCEPTION 'Une correction porte sur une écriture validée' USING ERRCODE = 'check_violation';
      END IF;
    END IF;
    RETURN NEW;
  END IF;

  -- ------------------------------------------------ modification
  IF NEW.id <> OLD.id OR NEW.organization_id <> OLD.organization_id OR NEW.company_id <> OLD.company_id
     OR NEW.fiscal_year_id <> OLD.fiscal_year_id OR NEW.created_by <> OLD.created_by OR NEW.origin <> OLD.origin
     OR NEW.source_type IS DISTINCT FROM OLD.source_type OR NEW.source_id IS DISTINCT FROM OLD.source_id
     OR NEW.reverses_entry_id IS DISTINCT FROM OLD.reverses_entry_id OR NEW.corrects_entry_id IS DISTINCT FROM OLD.corrects_entry_id
     OR NEW.created_at <> OLD.created_at THEN
    RAISE EXCEPTION 'Écriture : entreprise, exercice, auteur et provenance non modifiables' USING ERRCODE = 'check_violation';
  END IF;

  -- totaux tenus par les lignes (déclencheur interne)
  IF coalesce(current_setting('kofinex.entry_totals', true), '') = OLD.id::text THEN
    IF OLD.status <> 'draft' THEN
      RAISE EXCEPTION 'Lignes figées hors brouillon' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
  END IF;
  IF NEW.total_debit <> OLD.total_debit OR NEW.total_credit <> OLD.total_credit OR NEW.line_count <> OLD.line_count THEN
    RAISE EXCEPTION 'Totaux calculés à partir des lignes : non modifiables directement' USING ERRCODE = 'check_violation';
  END IF;

  -- écriture validée : immuable ; seule l'extourne validée la fait passer à « extournée »
  IF OLD.status IN ('validated','reversed') THEN
    IF OLD.status = 'validated' AND NEW.status = 'reversed'
       AND coalesce(current_setting('kofinex.reversing', true), '') = OLD.id::text
       AND (to_jsonb(NEW) - 'status' - 'reversed_by_entry_id' - 'updated_at') = (to_jsonb(OLD) - 'status' - 'reversed_by_entry_id' - 'updated_at') THEN
      RETURN NEW;
    END IF;
    RAISE EXCEPTION 'Écriture % validée : immuable (corriger par une extourne puis une nouvelle écriture)', OLD.number
      USING ERRCODE = 'check_violation';
  END IF;

  IF NEW.number IS DISTINCT FROM OLD.number OR NEW.sequence_no IS DISTINCT FROM OLD.sequence_no
     OR NEW.reversed_by_entry_id IS DISTINCT FROM OLD.reversed_by_entry_id THEN
    RAISE EXCEPTION 'Numéro et extourne attribués par KOFINEX' USING ERRCODE = 'check_violation';
  END IF;

  IF NEW.status = OLD.status THEN
    IF OLD.status <> 'draft' THEN
      RAISE EXCEPTION 'Écriture % : modification possible en brouillon uniquement', OLD.status USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.journal_id <> OLD.journal_id THEN
      SELECT journal_type INTO v_jt FROM public.journals WHERE id = NEW.journal_id;
      IF NOT j.is_active OR (OLD.origin = 'opening' AND v_jt <> 'opening') THEN
        RAISE EXCEPTION 'Journal non utilisable pour cette écriture' USING ERRCODE = 'check_violation';
      END IF;
    END IF;
    NEW.updated_at := now();
    RETURN NEW;
  END IF;

  -- transitions
  IF NEW.journal_id <> OLD.journal_id OR NEW.entry_date <> OLD.entry_date OR NEW.label <> OLD.label
     OR NEW.piece_ref IS DISTINCT FROM OLD.piece_ref OR NEW.piece_date IS DISTINCT FROM OLD.piece_date
     OR NEW.third_party_id IS DISTINCT FROM OLD.third_party_id THEN
    RAISE EXCEPTION 'Changement de statut : l''en-tête ne peut pas être modifié en même temps' USING ERRCODE = 'check_violation';
  END IF;

  IF OLD.status = 'draft' AND NEW.status = 'submitted' THEN
    PERFORM public.je_check(OLD.id);
    NEW.submitted_by := coalesce(v_uid, NEW.submitted_by); NEW.submitted_at := now();
    NEW.rejected_by := NULL; NEW.rejected_at := NULL; NEW.rejection_reason := NULL;

  ELSIF OLD.status = 'submitted' AND NEW.status = 'draft' THEN           -- retrait par l'auteur
    IF v_uid IS NOT NULL AND v_uid <> OLD.created_by THEN
      RAISE EXCEPTION 'Seul l''auteur peut retirer sa soumission' USING ERRCODE = 'insufficient_privilege';
    END IF;
    NEW.submitted_by := NULL; NEW.submitted_at := NULL;

  ELSIF OLD.status = 'submitted' AND NEW.status = 'under_review' THEN
    IF NOT public.acc_review_required(OLD.company_id) THEN
      RAISE EXCEPTION 'Étape de revue non activée pour cette entreprise' USING ERRCODE = 'check_violation';
    END IF;
    IF public.acc_segregation_required(OLD.company_id) AND v_uid = OLD.created_by THEN
      RAISE EXCEPTION 'Séparation des tâches : l''auteur ne peut pas réviser sa propre écriture' USING ERRCODE = 'insufficient_privilege';
    END IF;
    NEW.reviewed_by := coalesce(v_uid, NEW.reviewed_by); NEW.reviewed_at := now();

  ELSIF NEW.status = 'validated' AND OLD.status IN ('submitted','under_review') THEN
    IF OLD.status = 'submitted' AND public.acc_review_required(OLD.company_id) THEN
      RAISE EXCEPTION 'Revue obligatoire avant la validation' USING ERRCODE = 'check_violation';
    END IF;
    IF v_uid IS NOT NULL THEN
      v_role := authz.company_role(OLD.company_id);
      IF v_role IS DISTINCT FROM 'org_admin' AND v_role IS DISTINCT FROM 'accountant' THEN
        RAISE EXCEPTION 'Validation réservée aux comptables et administrateurs' USING ERRCODE = 'insufficient_privilege';
      END IF;
      IF public.acc_segregation_required(OLD.company_id) AND v_uid IN (OLD.created_by, OLD.submitted_by) THEN
        RAISE EXCEPTION 'Séparation des tâches : le validateur doit être différent du préparateur' USING ERRCODE = 'insufficient_privilege';
      END IF;
    END IF;
    PERFORM public.je_check(OLD.id);
    v_seq := public.je_next_number(OLD.journal_id, OLD.fiscal_year_id);
    NEW.sequence_no := v_seq;
    NEW.number := j.number_prefix || lpad(v_seq::text, 6, '0');
    NEW.validated_by := coalesce(v_uid, NEW.validated_by); NEW.validated_at := now();

  ELSIF NEW.status = 'rejected' AND OLD.status IN ('submitted','under_review') THEN
    IF length(btrim(coalesce(NEW.rejection_reason, ''))) < 5 THEN
      RAISE EXCEPTION 'Motif de rejet obligatoire' USING ERRCODE = 'check_violation';
    END IF;
    NEW.rejected_by := coalesce(v_uid, NEW.rejected_by); NEW.rejected_at := now();

  ELSIF OLD.status = 'rejected' AND NEW.status = 'draft' THEN
    IF v_uid IS NOT NULL AND v_uid <> OLD.created_by THEN
      RAISE EXCEPTION 'Seul l''auteur peut reprendre une écriture rejetée' USING ERRCODE = 'insufficient_privilege';
    END IF;
    NEW.submitted_by := NULL; NEW.submitted_at := NULL; NEW.reviewed_by := NULL; NEW.reviewed_at := NULL;

  ELSE
    RAISE EXCEPTION 'Transition refusée : % → %', OLD.status, NEW.status USING ERRCODE = 'check_violation';
  END IF;
  NEW.updated_at := now();
  RETURN NEW;
END $$;

-- Après validation d'une extourne : l'écriture d'origine passe à « extournée » ; historique du circuit
CREATE OR REPLACE FUNCTION public.after_journal_entry() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_action text;
BEGIN
  IF TG_OP = 'INSERT' THEN
    INSERT INTO public.journal_entry_events (organization_id, company_id, entry_id, action, to_status, actor)
    VALUES (NEW.organization_id, NEW.company_id, NEW.id, 'created', NEW.status, NEW.created_by);
    RETURN NEW;
  END IF;
  IF TG_OP = 'DELETE' THEN
    INSERT INTO public.journal_entry_events (organization_id, company_id, entry_id, action, from_status, actor)
    VALUES (OLD.organization_id, OLD.company_id, OLD.id, 'deleted', OLD.status, auth.uid());
    RETURN OLD;
  END IF;
  IF NEW.status = OLD.status THEN RETURN NEW; END IF;
  v_action := CASE
    WHEN NEW.status = 'submitted' THEN 'submitted'
    WHEN NEW.status = 'under_review' THEN 'review_started'
    WHEN NEW.status = 'validated' THEN 'validated'
    WHEN NEW.status = 'rejected' THEN 'rejected'
    WHEN NEW.status = 'reversed' THEN 'reversed'
    WHEN OLD.status = 'submitted' THEN 'withdrawn'
    ELSE 'returned_to_draft' END;
  INSERT INTO public.journal_entry_events (organization_id, company_id, entry_id, action, from_status, to_status, actor, reason)
  VALUES (NEW.organization_id, NEW.company_id, NEW.id, v_action, OLD.status, NEW.status, coalesce(auth.uid(), NEW.validated_by),
          CASE WHEN NEW.status = 'rejected' THEN NEW.rejection_reason
               WHEN NEW.status = 'reversed' THEN 'Extournée par ' || (SELECT number FROM public.journal_entries WHERE id = NEW.reversed_by_entry_id) END);
  IF NEW.status = 'validated' AND NEW.origin = 'reversal' THEN
    PERFORM set_config('kofinex.reversing', NEW.reverses_entry_id::text, true);
    UPDATE public.journal_entries SET status = 'reversed', reversed_by_entry_id = NEW.id WHERE id = NEW.reverses_entry_id;
    PERFORM set_config('kofinex.reversing', '', true);
  END IF;
  RETURN NEW;
END $$;

-- ---------------------------------------------------------------------
-- 8. Lignes : modifiables en brouillon seulement ; totaux tenus à jour ; lettrage sur écritures validées
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.guard_journal_entry_line() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE e public.journal_entries; lt public.letterings; v_acc public.company_accounts;
BEGIN
  SELECT * INTO e FROM public.journal_entries WHERE id = coalesce(NEW.entry_id, OLD.entry_id);
  IF NOT FOUND AND TG_OP = 'DELETE' THEN RETURN OLD; END IF;   -- suppression du brouillon en cascade
  -- lettrage / délettrage : seule la colonne lettering_id change, sur une écriture validée
  IF TG_OP = 'UPDATE' AND (to_jsonb(NEW) - 'lettering_id') = (to_jsonb(OLD) - 'lettering_id')
     AND NEW.lettering_id IS DISTINCT FROM OLD.lettering_id THEN
    IF e.status NOT IN ('validated','reversed') THEN
      RAISE EXCEPTION 'Seules les lignes d''écritures validées peuvent être lettrées' USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.lettering_id IS NOT NULL THEN
      SELECT * INTO lt FROM public.letterings WHERE id = NEW.lettering_id;
      SELECT * INTO v_acc FROM public.company_accounts WHERE company_id = NEW.company_id AND account_number = NEW.account_number;
      IF lt.company_id <> NEW.company_id OR lt.account_number <> NEW.account_number
         OR lt.third_party_id IS DISTINCT FROM NEW.third_party_id THEN
        RAISE EXCEPTION 'Lettrage : la ligne doit porter le même compte et le même tiers' USING ERRCODE = 'check_violation';
      END IF;
      IF NOT v_acc.lettering_enabled THEN
        RAISE EXCEPTION 'Compte % non lettrable', NEW.account_number USING ERRCODE = 'check_violation';
      END IF;
      IF OLD.lettering_id IS NOT NULL THEN
        RAISE EXCEPTION 'Ligne déjà lettrée : délettrez d''abord' USING ERRCODE = 'check_violation';
      END IF;
    END IF;
    RETURN NEW;
  END IF;
  IF e.status <> 'draft' THEN
    RAISE EXCEPTION 'Écriture %(%) : lignes modifiables en brouillon uniquement', coalesce(e.number, ''), e.status
      USING ERRCODE = 'check_violation';
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  IF NEW.organization_id <> e.organization_id OR NEW.company_id <> e.company_id OR NEW.fiscal_year_id <> e.fiscal_year_id THEN
    RAISE EXCEPTION 'Ligne : entreprise et exercice de l''écriture obligatoires' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.lettering_id IS NOT NULL THEN
    RAISE EXCEPTION 'Une ligne de brouillon ne peut pas être lettrée' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION public.after_journal_entry_line() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_id uuid := coalesce(NEW.entry_id, OLD.entry_id);
BEGIN
  IF TG_OP = 'UPDATE' AND (to_jsonb(NEW) - 'lettering_id') = (to_jsonb(OLD) - 'lettering_id') THEN
    RETURN NEW;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.journal_entries WHERE id = v_id) THEN RETURN NULL; END IF;  -- suppression en cascade
  PERFORM set_config('kofinex.entry_totals', v_id::text, true);
  UPDATE public.journal_entries e SET
    total_debit = coalesce((SELECT sum(debit) FROM public.journal_entry_lines WHERE entry_id = v_id), 0),
    total_credit = coalesce((SELECT sum(credit) FROM public.journal_entry_lines WHERE entry_id = v_id), 0),
    line_count = (SELECT count(*) FROM public.journal_entry_lines WHERE entry_id = v_id)
   WHERE e.id = v_id;
  PERFORM set_config('kofinex.entry_totals', '', true);
  RETURN NULL;
END $$;

-- ---------------------------------------------------------------------
-- 9. Lettrage (complet : les lignes lettrées ensemble s'équilibrent)
-- ---------------------------------------------------------------------


CREATE OR REPLACE FUNCTION public.guard_lettering() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF TG_OP = 'UPDATE' THEN
    RAISE EXCEPTION 'Lettrage : non modifiable (délettrer puis lettrer à nouveau)' USING ERRCODE = 'check_violation';
  END IF;
  IF TG_OP = 'INSERT' THEN NEW.created_by := coalesce(auth.uid(), NEW.created_by); RETURN NEW; END IF;
  RETURN OLD;
END $$;

-- vérifié en fin de transaction : au moins deux lignes, débit = crédit = montant du lettrage
CREATE OR REPLACE FUNCTION public.check_lettering_balance() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_id uuid; v_n int; v_d numeric; v_c numeric; v_amount numeric;
BEGIN
  FOREACH v_id IN ARRAY ARRAY[NEW.lettering_id, OLD.lettering_id] LOOP
    CONTINUE WHEN v_id IS NULL;
    SELECT amount INTO v_amount FROM public.letterings WHERE id = v_id;
    CONTINUE WHEN NOT FOUND;
    SELECT count(*), coalesce(sum(debit), 0), coalesce(sum(credit), 0) INTO v_n, v_d, v_c
      FROM public.journal_entry_lines WHERE lettering_id = v_id;
    IF v_n < 2 OR v_d <> v_c OR v_d <> v_amount THEN
      RAISE EXCEPTION 'Lettrage déséquilibré : débit %, crédit % (% ligne(s))', v_d, v_c, v_n USING ERRCODE = 'check_violation';
    END IF;
  END LOOP;
  RETURN NULL;
END $$;

-- ---------------------------------------------------------------------
-- 10. Déclencheurs
-- ---------------------------------------------------------------------
CREATE TRIGGER company_accounts_guard BEFORE INSERT OR UPDATE OR DELETE ON public.company_accounts
  FOR EACH ROW EXECUTE FUNCTION public.guard_company_account();
CREATE TRIGGER third_parties_guard BEFORE INSERT OR UPDATE OR DELETE ON public.third_parties
  FOR EACH ROW EXECUTE FUNCTION public.guard_third_party();
CREATE TRIGGER journals_guard BEFORE INSERT OR UPDATE OR DELETE ON public.journals
  FOR EACH ROW EXECUTE FUNCTION public.guard_journal();
CREATE TRIGGER journal_entries_closed_fy_guard BEFORE INSERT OR UPDATE OR DELETE ON public.journal_entries
  FOR EACH ROW EXECUTE FUNCTION public.guard_closed_fiscal_year();
CREATE TRIGGER journal_entries_guard BEFORE INSERT OR UPDATE OR DELETE ON public.journal_entries
  FOR EACH ROW EXECUTE FUNCTION public.guard_journal_entry();
CREATE TRIGGER journal_entries_after AFTER INSERT OR UPDATE OR DELETE ON public.journal_entries
  FOR EACH ROW EXECUTE FUNCTION public.after_journal_entry();
CREATE TRIGGER journal_entry_lines_closed_fy_guard BEFORE INSERT OR UPDATE OR DELETE ON public.journal_entry_lines
  FOR EACH ROW EXECUTE FUNCTION public.guard_closed_fiscal_year();
CREATE TRIGGER journal_entry_lines_guard BEFORE INSERT OR UPDATE OR DELETE ON public.journal_entry_lines
  FOR EACH ROW EXECUTE FUNCTION public.guard_journal_entry_line();
CREATE TRIGGER journal_entry_lines_after AFTER INSERT OR UPDATE OR DELETE ON public.journal_entry_lines
  FOR EACH ROW EXECUTE FUNCTION public.after_journal_entry_line();
CREATE CONSTRAINT TRIGGER journal_entry_lines_lettering_check AFTER INSERT OR UPDATE OF lettering_id ON public.journal_entry_lines
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.check_lettering_balance();
CREATE TRIGGER letterings_guard BEFORE INSERT OR UPDATE OR DELETE ON public.letterings
  FOR EACH ROW EXECUTE FUNCTION public.guard_lettering();

CREATE OR REPLACE FUNCTION public.guard_immutable_event() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'Historique du circuit : non modifiable' USING ERRCODE = 'check_violation';
END $$;
CREATE TRIGGER journal_entry_events_immutable BEFORE UPDATE OR DELETE ON public.journal_entry_events
  FOR EACH ROW EXECUTE FUNCTION public.guard_immutable_event();

CREATE OR REPLACE FUNCTION public.guard_entry_attachment() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_status text; v_doc_company uuid;
BEGIN
  SELECT status INTO v_status FROM public.journal_entries WHERE id = coalesce(NEW.entry_id, OLD.entry_id);
  IF TG_OP = 'DELETE' THEN
    IF v_status IN ('validated','reversed') THEN
      RAISE EXCEPTION 'Pièce d''une écriture validée : non détachable' USING ERRCODE = 'check_violation';
    END IF;
    RETURN OLD;
  END IF;
  IF TG_OP = 'UPDATE' THEN
    RAISE EXCEPTION 'Pièce jointe : non modifiable' USING ERRCODE = 'check_violation';
  END IF;
  SELECT company_id INTO v_doc_company FROM public.financial_documents WHERE id = NEW.document_id;
  IF v_doc_company IS DISTINCT FROM NEW.company_id THEN
    RAISE EXCEPTION 'Pièce d''une autre entreprise' USING ERRCODE = 'check_violation';
  END IF;
  NEW.attached_by := coalesce(auth.uid(), NEW.attached_by);
  RETURN NEW;
END $$;
CREATE TRIGGER journal_entry_attachments_guard BEFORE INSERT OR UPDATE OR DELETE ON public.journal_entry_attachments
  FOR EACH ROW EXECUTE FUNCTION public.guard_entry_attachment();

-- journal d'audit (lot 1) et interdiction de l'acteur IA (lot 10) sur les nouvelles tables
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['accounting_settings','company_accounts','third_parties','journals','letterings'] LOOP
    EXECUTE format('CREATE TRIGGER %I AFTER INSERT OR UPDATE OR DELETE ON public.%I
                      FOR EACH ROW EXECUTE FUNCTION public.audit_row_change()', t || '_audit', t);
  END LOOP;
  FOREACH t IN ARRAY ARRAY['accounting_settings','company_accounts','third_parties','journals','journal_sequences',
                           'journal_entries','journal_entry_lines','journal_entry_attachments','journal_entry_events','letterings'] LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE INSERT OR UPDATE OR DELETE ON public.%I
                    FOR EACH ROW EXECUTE FUNCTION public.guard_not_ai()', '0_not_ai', t);
  END LOOP;
END $$;

-- ---------------------------------------------------------------------
-- 11. RLS
-- lecture : membres de l'entreprise et équipes de mission qui l'auditent (lecture seule) ;
-- écriture : comptables et administrateurs ; paramètres : administrateurs ;
-- séquences et historique : écrits uniquement par les fonctions de la base.
-- ---------------------------------------------------------------------
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['company_accounts','third_parties','journals','journal_entries','journal_entry_lines',
                           'journal_entry_attachments','letterings'] LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY %I ON public.%I FOR SELECT TO authenticated
                    USING (authz.can_access_company(company_id) OR authz.audits_company(company_id))', t || '_select', t);
    EXECUTE format('CREATE POLICY %I ON public.%I FOR INSERT TO authenticated
                    WITH CHECK (authz.has_company_role(company_id, ARRAY[''accountant'']))', t || '_insert', t);
    EXECUTE format('CREATE POLICY %I ON public.%I FOR UPDATE TO authenticated
                    USING (authz.has_company_role(company_id, ARRAY[''accountant'']))
                    WITH CHECK (authz.has_company_role(company_id, ARRAY[''accountant'']))', t || '_update', t);
    EXECUTE format('CREATE POLICY %I ON public.%I FOR DELETE TO authenticated
                    USING (authz.has_company_role(company_id, ARRAY[''accountant'']))', t || '_delete', t);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON public.%I TO authenticated', t);
    EXECUTE format('GRANT ALL ON public.%I TO service_role', t);
  END LOOP;
  FOREACH t IN ARRAY ARRAY['journal_sequences','journal_entry_events'] LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY %I ON public.%I FOR SELECT TO authenticated
                    USING (authz.can_access_company(company_id) OR authz.audits_company(company_id))', t || '_select', t);
    EXECUTE format('GRANT SELECT ON public.%I TO authenticated', t);
    EXECUTE format('REVOKE INSERT, UPDATE, DELETE ON public.%I FROM authenticated', t);
    EXECUTE format('GRANT ALL ON public.%I TO service_role', t);
  END LOOP;
END $$;

ALTER TABLE public.accounting_settings ENABLE ROW LEVEL SECURITY;
CREATE POLICY accounting_settings_select ON public.accounting_settings FOR SELECT TO authenticated
  USING (authz.can_access_company(company_id));
CREATE POLICY accounting_settings_write ON public.accounting_settings FOR ALL TO authenticated
  USING (authz.has_company_role(company_id, ARRAY[]::text[]))
  WITH CHECK (authz.has_company_role(company_id, ARRAY[]::text[]));
GRANT SELECT, INSERT, UPDATE, DELETE ON public.accounting_settings TO authenticated;
GRANT ALL ON public.accounting_settings TO service_role;

GRANT EXECUTE ON FUNCTION public.acc_review_required(uuid), public.acc_segregation_required(uuid) TO authenticated, service_role;
