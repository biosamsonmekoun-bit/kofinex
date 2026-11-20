-- =====================================================================
-- KOFINEX — Migration 0018 : lot 12A, catalogue commercial et abonnements
-- (docs/LOT12_SAAS_CONCEPTION.md, § 2, § 4, § 5, § 8, § 10, § 14 et décisions du § 16)
--
-- - Catalogue versionné : offres et options, versions figées à la publication, prix par périodicité et devise,
--   modules et quotas par version. Aucun prix ni quota n'est chargé ici : ce sont des données saisies par
--   l'administrateur de la plateforme.
-- - Abonnements : la table `subscriptions` (migration 0001) est complétée, jamais remplacée. Le client n'y écrit
--   jamais directement : l'essai, la demande de résiliation et son retrait passent par des fonctions qui imposent
--   les règles en base (propriétaire seul, version publiée, un seul essai par organisation et par identité de
--   facturation). L'activation payante arrive avec l'étape 12B (paiement vérifié par le serveur).
-- - Le catalogue publié est lisible sans connexion (rôle anon), pour la page publique des tarifs.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 0. Garde : `subscriptions` n'est alimentée par aucun code avant ce lot (§ 2.3)
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM public.subscriptions) THEN
    RAISE EXCEPTION 'Migration 0018 : la table subscriptions contient des lignes ; reprise de données à prévoir avant de compléter son schéma';
  END IF;
END $$;

-- ---------------------------------------------------------------------
-- 1. Paramètres de la plateforme (une seule ligne)
-- ---------------------------------------------------------------------
CREATE TABLE public.billing_settings (
  id                        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  singleton                 boolean NOT NULL DEFAULT true UNIQUE CHECK (singleton),
  -- impayés (§ 5.4) : période de grâce, puis lecture seule ; délai avant résiliation non fixé = aucune résiliation
  grace_days                int NOT NULL CHECK (grace_days BETWEEN 0 AND 90),
  suspension_to_cancel_days int CHECK (suspension_to_cancel_days IS NULL OR suspension_to_cancel_days BETWEEN 1 AND 3650),
  renewal_notice_days       int CHECK (renewal_notice_days IS NULL OR renewal_notice_days BETWEEN 1 AND 90),
  reminder_days             int[] NOT NULL DEFAULT '{}',
  max_orgs_per_user         int CHECK (max_orgs_per_user IS NULL OR max_orgs_per_user >= 1),
  -- entité vendeuse (§ 16, décision 1 : Bénin) ; identifiants à fournir
  seller_name               text,
  seller_country            char(2) NOT NULL CHECK (seller_country ~ '^[A-Z]{2}$'),
  seller_tax_id             text,
  seller_address            text,
  -- pays de facturation ouverts et devise de chacun : donnée publiée, pas un calcul (§ 4)
  country_currencies        jsonb NOT NULL,
  updated_by                uuid REFERENCES public.profiles(id),
  created_at                timestamptz NOT NULL DEFAULT now(),
  updated_at                timestamptz NOT NULL DEFAULT now()
);

-- Devises de facturation retenues (§ 16, décisions 2 et 5) et décimales ISO 4217 : XOF, XAF, GNF, KMF 0 ; CDF 2.
CREATE OR REPLACE FUNCTION public.billing_currency_ok(p_currency text) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$ SELECT p_currency IN ('XOF','XAF','GNF','KMF','CDF') $$;
CREATE OR REPLACE FUNCTION public.billing_amount_ok(p_amount numeric, p_currency text) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
  SELECT p_amount >= 0 AND (CASE WHEN p_currency = 'CDF' THEN p_amount = round(p_amount, 2)
                                 ELSE p_amount = trunc(p_amount) END)
$$;

CREATE OR REPLACE FUNCTION public.guard_billing_settings() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE k text; v text;
BEGIN
  IF jsonb_typeof(NEW.country_currencies) <> 'object' OR NEW.country_currencies = '{}'::jsonb THEN
    RAISE EXCEPTION 'Paramètres : liste des pays de facturation vide' USING ERRCODE = 'check_violation';
  END IF;
  FOR k, v IN SELECT key, value #>> '{}' FROM jsonb_each(NEW.country_currencies) LOOP
    IF k !~ '^[A-Z]{2}$' OR NOT public.billing_currency_ok(v) THEN
      RAISE EXCEPTION 'Paramètres : pays « % » ou devise « % » invalide', k, v USING ERRCODE = 'check_violation';
    END IF;
  END LOOP;
  NEW.updated_by := coalesce(auth.uid(), NEW.updated_by);
  RETURN NEW;
END $$;
CREATE TRIGGER billing_settings_guard BEFORE INSERT OR UPDATE ON public.billing_settings
  FOR EACH ROW EXECUTE FUNCTION public.guard_billing_settings();

-- Valeurs arrêtées au § 16 : grâce de 7 jours (décision 7) ; aucune résiliation automatique (délai non fixé) ;
-- vendeur au Bénin (décision 1) ; 17 États de l'OHADA et leur devise (décisions 2 et 5).
INSERT INTO public.billing_settings (grace_days, seller_country, country_currencies) VALUES (7, 'BJ', jsonb_build_object(
  'BJ','XOF', 'BF','XOF', 'CI','XOF', 'GW','XOF', 'ML','XOF', 'NE','XOF', 'SN','XOF', 'TG','XOF',
  'CM','XAF', 'CF','XAF', 'CG','XAF', 'GA','XAF', 'GQ','XAF', 'TD','XAF',
  'GN','GNF', 'KM','KMF', 'CD','CDF'));

CREATE OR REPLACE FUNCTION public.billing_currency_for(p_country text) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT country_currencies ->> upper(p_country) FROM public.billing_settings WHERE singleton
$$;

-- ---------------------------------------------------------------------
-- 2. Modules commercialisables (§ 3.1) : uniquement les modules livrés
-- ---------------------------------------------------------------------
CREATE TABLE public.billing_modules (
  key           text PRIMARY KEY CHECK (key ~ '^[a-z_]{2,40}$'),
  label         text NOT NULL,
  description   text,
  requires      text[] NOT NULL DEFAULT '{}',
  is_core       boolean NOT NULL DEFAULT false,      -- toujours inclus dans une offre de base
  display_order int NOT NULL DEFAULT 0,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);
-- Correspondance avec les modules livrés (constaté, § 3.1). `connectors` (12C) n'est pas ajouté : pas de module
-- vendu sans fonctionnalité.
INSERT INTO public.billing_modules (key, label, requires, is_core, display_order) VALUES
  ('core',               'Socle : organisations, entités, exercices, tableau de bord', '{}', true, 10),
  ('accounting_import',  'Import des balances et du grand livre', '{}', false, 20),
  ('native_accounting',  'Comptabilité générale native', '{}', false, 30),
  ('financial_analysis', 'Analyse financière', '{}', false, 40),
  ('management_control', 'Contrôle de gestion et pilotage', '{}', false, 50),
  ('audit_core',         'Socle d''audit : missions, programmes, preuves', '{}', false, 60),
  ('financial_audit',    'Audit financier et comptable', '{audit_core}', false, 70),
  ('internal_audit',     'Audit interne', '{audit_core}', false, 80),
  ('internal_control',   'Contrôle interne', '{audit_core}', false, 90),
  ('ai',                 'Assistant IA (activation par l''organisation requise)', '{}', false, 100),
  ('reporting',          'Rapports PDF, Excel et Word', '{}', false, 110);

CREATE OR REPLACE FUNCTION public.guard_billing_module() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM unnest(NEW.requires) r WHERE r = NEW.key
                OR NOT EXISTS (SELECT 1 FROM public.billing_modules m WHERE m.key = r)) THEN
    RAISE EXCEPTION 'Module % : dépendance inconnue ou circulaire', NEW.key USING ERRCODE = 'check_violation';
  END IF;
  IF TG_OP = 'UPDATE' AND NEW.key <> OLD.key THEN
    RAISE EXCEPTION 'Module : clé non modifiable' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER billing_modules_guard BEFORE INSERT OR UPDATE ON public.billing_modules
  FOR EACH ROW EXECUTE FUNCTION public.guard_billing_module();

-- ---------------------------------------------------------------------
-- 3. Offres et options, versions, prix, droits
-- ---------------------------------------------------------------------
CREATE TABLE public.billing_products (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code          text NOT NULL UNIQUE CHECK (code ~ '^[A-Z0-9_]{2,40}$'),
  kind          text NOT NULL CHECK (kind IN ('plan','addon')),
  name          text NOT NULL CHECK (length(btrim(name)) > 0),
  description   text,
  display_order int NOT NULL DEFAULT 0,
  created_by    uuid REFERENCES public.profiles(id),
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION public.guard_billing_product() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF EXISTS (SELECT 1 FROM public.billing_product_versions v WHERE v.product_id = OLD.id AND v.status <> 'draft') THEN
      RAISE EXCEPTION 'Offre déjà publiée : suppression impossible' USING ERRCODE = 'check_violation';
    END IF;
    RETURN OLD;
  END IF;
  IF TG_OP = 'UPDATE' AND (NEW.code <> OLD.code OR NEW.kind <> OLD.kind) THEN
    RAISE EXCEPTION 'Offre : code et nature non modifiables' USING ERRCODE = 'check_violation';
  END IF;
  IF TG_OP = 'INSERT' THEN NEW.created_by := coalesce(auth.uid(), NEW.created_by); END IF;
  RETURN NEW;
END $$;

CREATE TABLE public.billing_product_versions (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id   uuid NOT NULL REFERENCES public.billing_products(id) ON DELETE CASCADE,
  version_no   int NOT NULL CHECK (version_no >= 1),
  label        text NOT NULL CHECK (length(btrim(label)) > 0),
  description  text,
  status       text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published','retired')),
  trial_days   int CHECK (trial_days IS NULL OR trial_days BETWEEN 1 AND 365),   -- offres de base seulement
  published_at timestamptz,
  published_by uuid REFERENCES public.profiles(id),
  retired_at   timestamptz,
  created_by   uuid REFERENCES public.profiles(id),
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (product_id, version_no),
  CHECK ((status = 'draft') = (published_at IS NULL)),
  CHECK ((status = 'retired') = (retired_at IS NOT NULL))
);
-- une seule version publiée par offre : c'est celle que voit le catalogue
CREATE UNIQUE INDEX billing_product_versions_one_published_uq
  ON public.billing_product_versions (product_id) WHERE status = 'published';

CREATE TRIGGER billing_products_guard BEFORE INSERT OR UPDATE OR DELETE ON public.billing_products
  FOR EACH ROW EXECUTE FUNCTION public.guard_billing_product();

CREATE TABLE public.billing_prices (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  product_version_id uuid NOT NULL REFERENCES public.billing_product_versions(id) ON DELETE CASCADE,
  billing_interval   text NOT NULL CHECK (billing_interval IN ('month','year')),
  currency           char(3) NOT NULL CHECK (public.billing_currency_ok(currency)),
  amount             numeric(14,2) NOT NULL,
  created_at         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (product_version_id, billing_interval, currency),
  CHECK (public.billing_amount_ok(amount, currency))
);

CREATE TABLE public.billing_entitlements (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  product_version_id uuid NOT NULL REFERENCES public.billing_product_versions(id) ON DELETE CASCADE,
  kind               text NOT NULL CHECK (kind IN ('module','quota')),
  module_key         text REFERENCES public.billing_modules(key),
  -- grandeurs du § 3.3 ; unités par défaut [À VALIDER] (§ 16) : IA en jetons, sociétés non archivées
  quota_key          text CHECK (quota_key IN ('users','companies','engagements','storage_mb','imports_per_period',
                                               'reports_per_period','ai_tokens_per_period')),
  limit_value        bigint CHECK (limit_value IS NULL OR limit_value >= 0),   -- NULL : illimité
  created_at         timestamptz NOT NULL DEFAULT now(),
  CHECK ((kind = 'module' AND module_key IS NOT NULL AND quota_key IS NULL AND limit_value IS NULL)
      OR (kind = 'quota' AND quota_key IS NOT NULL AND module_key IS NULL)),
  UNIQUE (product_version_id, module_key),
  UNIQUE (product_version_id, quota_key)
);

-- Une version publiée est figée (prix, droits, essai) ; seul son retrait est permis. Une version retirée est
-- figée. Seul un brouillon se supprime.
CREATE OR REPLACE FUNCTION public.guard_billing_version() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE v_kind text;
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status <> 'draft' THEN
      RAISE EXCEPTION 'Version publiée ou retirée : suppression impossible' USING ERRCODE = 'check_violation';
    END IF;
    RETURN OLD;
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.status <> 'draft' THEN
      RAISE EXCEPTION 'Une version se crée en brouillon' USING ERRCODE = 'check_violation';
    END IF;
    NEW.created_by := coalesce(auth.uid(), NEW.created_by);
  ELSIF OLD.status = 'retired' THEN
    RAISE EXCEPTION 'Version retirée : aucune modification possible' USING ERRCODE = 'check_violation';
  ELSIF OLD.status = 'published' THEN
    IF NEW.status <> 'retired' OR (to_jsonb(NEW) - ARRAY['status','retired_at','updated_at'])
         IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['status','retired_at','updated_at']) THEN
      RAISE EXCEPTION 'Version publiée : figée (seul son retrait est possible)' USING ERRCODE = 'check_violation';
    END IF;
  ELSIF NEW.status = 'retired' THEN
    RAISE EXCEPTION 'Un brouillon se supprime, il ne se retire pas' USING ERRCODE = 'check_violation';
  ELSIF NEW.status = 'published' THEN
    -- contrôles minimaux en base ; la validation complète (dépendances, quotas) est faite par le moteur
    SELECT kind INTO v_kind FROM public.billing_products WHERE id = NEW.product_id;
    IF NOT EXISTS (SELECT 1 FROM public.billing_prices p WHERE p.product_version_id = NEW.id) THEN
      RAISE EXCEPTION 'Publication impossible : aucun prix' USING ERRCODE = 'check_violation';
    END IF;
    IF v_kind = 'plan' AND NOT EXISTS (SELECT 1 FROM public.billing_entitlements e JOIN public.billing_modules m
                                          ON m.key = e.module_key WHERE e.product_version_id = NEW.id AND m.is_core) THEN
      RAISE EXCEPTION 'Publication impossible : module de base absent' USING ERRCODE = 'check_violation';
    END IF;
    IF v_kind = 'addon' AND NEW.trial_days IS NOT NULL THEN
      RAISE EXCEPTION 'Une option n''a pas d''essai' USING ERRCODE = 'check_violation';
    END IF;
    NEW.published_at := now();
    NEW.published_by := coalesce(auth.uid(), NEW.published_by);
  END IF;
  IF TG_OP = 'UPDATE' AND NEW.product_id <> OLD.product_id THEN
    RAISE EXCEPTION 'Version : offre non modifiable' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.status = 'retired' THEN NEW.retired_at := coalesce(NEW.retired_at, now()); END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER billing_product_versions_guard BEFORE INSERT OR UPDATE OR DELETE ON public.billing_product_versions
  FOR EACH ROW EXECUTE FUNCTION public.guard_billing_version();

CREATE OR REPLACE FUNCTION public.guard_billing_version_content() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE v_status text;
BEGIN
  SELECT status INTO v_status FROM public.billing_product_versions
   WHERE id = coalesce(NEW.product_version_id, OLD.product_version_id);
  -- v_status NULL : suppression en cascade d'un brouillon
  IF v_status IS NOT NULL AND v_status <> 'draft' THEN
    RAISE EXCEPTION 'Version publiée ou retirée : prix et droits figés' USING ERRCODE = 'check_violation';
  END IF;
  IF TG_OP = 'UPDATE' AND NEW.product_version_id <> OLD.product_version_id THEN
    RAISE EXCEPTION 'Version de rattachement non modifiable' USING ERRCODE = 'check_violation';
  END IF;
  RETURN coalesce(NEW, OLD);
END $$;
CREATE TRIGGER billing_prices_guard BEFORE INSERT OR UPDATE OR DELETE ON public.billing_prices
  FOR EACH ROW EXECUTE FUNCTION public.guard_billing_version_content();
CREATE TRIGGER billing_entitlements_guard BEFORE INSERT OR UPDATE OR DELETE ON public.billing_entitlements
  FOR EACH ROW EXECUTE FUNCTION public.guard_billing_version_content();

-- ---------------------------------------------------------------------
-- 4. Promotions
-- ---------------------------------------------------------------------
CREATE TABLE public.billing_promotions (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code             text NOT NULL UNIQUE CHECK (code ~ '^[A-Z0-9_-]{3,40}$'),
  label            text NOT NULL,
  discount_type    text NOT NULL CHECK (discount_type IN ('percent','fixed')),
  percent          numeric(5,2) CHECK (percent IS NULL OR (percent > 0 AND percent <= 100)),
  fixed_amount     numeric(14,2),
  fixed_currency   char(3) CHECK (fixed_currency IS NULL OR public.billing_currency_ok(fixed_currency)),
  product_ids      uuid[],                 -- NULL : toutes les offres et options
  billing_interval text CHECK (billing_interval IS NULL OR billing_interval IN ('month','year')),
  duration         text NOT NULL CHECK (duration IN ('once','repeating','forever')),
  duration_periods int,
  valid_from       timestamptz NOT NULL DEFAULT now(),
  valid_until      timestamptz,
  max_redemptions  int CHECK (max_redemptions IS NULL OR max_redemptions >= 1),
  status           text NOT NULL DEFAULT 'active' CHECK (status IN ('active','disabled')),
  created_by       uuid REFERENCES public.profiles(id),
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  CHECK ((discount_type = 'percent' AND percent IS NOT NULL AND fixed_amount IS NULL AND fixed_currency IS NULL)
      OR (discount_type = 'fixed' AND percent IS NULL AND fixed_amount > 0 AND fixed_currency IS NOT NULL
          AND public.billing_amount_ok(fixed_amount, fixed_currency))),
  CHECK ((duration = 'repeating') = (duration_periods IS NOT NULL AND duration_periods >= 1)
         AND (duration = 'repeating' OR duration_periods IS NULL)),
  CHECK (valid_until IS NULL OR valid_until > valid_from)
);

-- Les conditions d'une promotion sont figées dès sa création (elles sont tracées sur les commandes) : seuls le
-- libellé, le statut, la fin de validité et le plafond d'utilisation changent. Pas de suppression.
CREATE OR REPLACE FUNCTION public.guard_billing_promotion() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Promotion : suppression impossible (la désactiver)' USING ERRCODE = 'check_violation';
  END IF;
  IF TG_OP = 'INSERT' THEN
    NEW.created_by := coalesce(auth.uid(), NEW.created_by);
  ELSIF (to_jsonb(NEW) - ARRAY['label','status','valid_until','max_redemptions','updated_at'])
        IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['label','status','valid_until','max_redemptions','updated_at']) THEN
    RAISE EXCEPTION 'Promotion : conditions figées (seuls le libellé, le statut, la fin de validité et le plafond changent)'
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER billing_promotions_guard BEFORE INSERT OR UPDATE OR DELETE ON public.billing_promotions
  FOR EACH ROW EXECUTE FUNCTION public.guard_billing_promotion();

-- ---------------------------------------------------------------------
-- 5. Compte de facturation (identité de l'acheteur, 1:1 avec l'organisation)
-- ---------------------------------------------------------------------
CREATE TABLE public.billing_accounts (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL UNIQUE REFERENCES public.organizations(id) ON DELETE CASCADE,
  legal_name      text NOT NULL CHECK (length(btrim(legal_name)) > 0),
  tax_id          text,                    -- identifiant fiscal (IFU, NIU…), normalisé en majuscules sans espace
  address         text NOT NULL CHECK (length(btrim(address)) > 0),
  city            text,
  country_code    char(2) NOT NULL CHECK (country_code ~ '^[A-Z]{2}$'),
  billing_email   text NOT NULL CHECK (billing_email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
  updated_by      uuid REFERENCES public.profiles(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION public.guard_billing_account() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'UPDATE' AND NEW.organization_id <> OLD.organization_id THEN
    RAISE EXCEPTION 'Compte de facturation : organisation non modifiable' USING ERRCODE = 'check_violation';
  END IF;
  NEW.tax_id := nullif(upper(regexp_replace(coalesce(NEW.tax_id, ''), '\s', '', 'g')), '');
  NEW.billing_email := lower(btrim(NEW.billing_email));
  IF public.billing_currency_for(NEW.country_code) IS NULL THEN
    RAISE EXCEPTION 'Pays de facturation non ouvert : %', NEW.country_code USING ERRCODE = 'check_violation';
  END IF;
  -- le pays fixe la devise de l'abonnement : il ne change plus une fois un abonnement souscrit
  IF TG_OP = 'UPDATE' AND NEW.country_code <> OLD.country_code
     AND public.billing_currency_for(NEW.country_code) IS DISTINCT FROM public.billing_currency_for(OLD.country_code)
     AND EXISTS (SELECT 1 FROM public.subscriptions s WHERE s.organization_id = NEW.organization_id
                    AND s.status IN ('trialing','incomplete','active','past_due','suspended')) THEN
    RAISE EXCEPTION 'Un abonnement est en cours : changement de devise de facturation impossible' USING ERRCODE = 'check_violation';
  END IF;
  NEW.updated_by := coalesce(auth.uid(), NEW.updated_by);
  RETURN NEW;
END $$;
CREATE TRIGGER billing_accounts_guard BEFORE INSERT OR UPDATE ON public.billing_accounts
  FOR EACH ROW EXECUTE FUNCTION public.guard_billing_account();

-- ---------------------------------------------------------------------
-- 6. Abonnements : compléments (ALTER, aucune colonne retirée)
-- ---------------------------------------------------------------------
ALTER TABLE public.subscriptions DROP CONSTRAINT subscriptions_status_check;
ALTER TABLE public.subscriptions ADD CONSTRAINT subscriptions_status_check
  CHECK (status IN ('trialing','incomplete','active','past_due','suspended','canceled','expired'));
DROP INDEX public.subscriptions_one_live_uq;
CREATE UNIQUE INDEX subscriptions_one_live_uq ON public.subscriptions (organization_id)
  WHERE status IN ('trialing','incomplete','active','past_due','suspended');

ALTER TABLE public.subscriptions
  ADD COLUMN product_version_id uuid REFERENCES public.billing_product_versions(id),
  ADD COLUMN billing_interval   text CHECK (billing_interval IS NULL OR billing_interval IN ('month','year')),
  ADD COLUMN currency           char(3) CHECK (currency IS NULL OR public.billing_currency_ok(currency)),
  ADD COLUMN trial_end          timestamptz,
  ADD COLUMN grace_until        timestamptz,
  ADD COLUMN suspended_at       timestamptz,
  ADD COLUMN canceled_at        timestamptz,
  ADD COLUMN cancel_reason      text,
  ADD COLUMN renewal_mode       text NOT NULL DEFAULT 'manual' CHECK (renewal_mode IN ('manual','automatic')),
  -- identité de facturation utilisée pour l'essai (anti-abus, § 12 règle 11)
  ADD COLUMN trial_tax_id       text,
  ADD COLUMN trial_owner_email  text,
  ADD CONSTRAINT subscriptions_id_org_uq UNIQUE (id, organization_id);
COMMENT ON COLUMN public.subscriptions.seats IS 'Conservée (0001) ; les droits sont lus dans le catalogue (billing_entitlements).';
COMMENT ON COLUMN public.subscriptions.max_companies IS 'Conservée (0001) ; les droits sont lus dans le catalogue (billing_entitlements).';
-- un seul essai par organisation, par identifiant fiscal et par e-mail du propriétaire
CREATE UNIQUE INDEX subscriptions_one_trial_per_org_uq ON public.subscriptions (organization_id) WHERE trial_end IS NOT NULL;
CREATE UNIQUE INDEX subscriptions_trial_tax_id_uq ON public.subscriptions (trial_tax_id) WHERE trial_tax_id IS NOT NULL;
CREATE UNIQUE INDEX subscriptions_trial_owner_email_uq ON public.subscriptions (trial_owner_email) WHERE trial_owner_email IS NOT NULL;

CREATE TABLE public.subscription_items (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id    uuid NOT NULL,
  subscription_id    uuid NOT NULL,
  product_version_id uuid NOT NULL REFERENCES public.billing_product_versions(id),
  kind               text NOT NULL CHECK (kind IN ('plan','addon')),
  quantity           int NOT NULL DEFAULT 1 CHECK (quantity >= 1),
  created_at         timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (subscription_id, organization_id) REFERENCES public.subscriptions(id, organization_id) ON DELETE CASCADE,
  UNIQUE (subscription_id, product_version_id),
  CHECK (kind <> 'plan' OR quantity = 1)
);
CREATE UNIQUE INDEX subscription_items_one_plan_uq ON public.subscription_items (subscription_id) WHERE kind = 'plan';

CREATE TABLE public.billing_promotion_redemptions (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  promotion_id    uuid NOT NULL REFERENCES public.billing_promotions(id),
  organization_id uuid NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
  subscription_id uuid,
  redeemed_by     uuid REFERENCES public.profiles(id),
  redeemed_at     timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (subscription_id, organization_id) REFERENCES public.subscriptions(id, organization_id),
  UNIQUE (promotion_id, organization_id)
);

-- ---------------------------------------------------------------------
-- 7. Opérations du client sur son abonnement (règles imposées en base)
-- ---------------------------------------------------------------------
-- Essai gratuit (§ 16, décision 4 : sans moyen de paiement) sur une offre de base publiée.
CREATE OR REPLACE FUNCTION public.billing_start_trial(p_org uuid, p_version uuid, p_interval text) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
  v_acc   public.billing_accounts;
  v_ver   public.billing_product_versions;
  v_prod  public.billing_products;
  v_cur   text;
  v_email text;
  v_id    uuid;
BEGIN
  IF public.ai_actor() THEN
    RAISE EXCEPTION 'IA : opération interdite' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF NOT authz.has_org_role(p_org, ARRAY['owner']) THEN
    RAISE EXCEPTION 'Réservé au propriétaire de l''organisation' USING ERRCODE = 'insufficient_privilege';
  END IF;
  SELECT * INTO v_acc FROM public.billing_accounts WHERE organization_id = p_org;
  IF v_acc.id IS NULL THEN
    RAISE EXCEPTION 'Renseignez d''abord les informations de facturation' USING ERRCODE = 'check_violation';
  END IF;
  SELECT * INTO v_ver FROM public.billing_product_versions WHERE id = p_version FOR SHARE;
  SELECT * INTO v_prod FROM public.billing_products WHERE id = v_ver.product_id;
  IF v_ver.id IS NULL OR v_ver.status <> 'published' OR v_prod.kind <> 'plan' THEN
    RAISE EXCEPTION 'Offre non publiée' USING ERRCODE = 'check_violation';
  END IF;
  IF v_ver.trial_days IS NULL THEN
    RAISE EXCEPTION 'Cette offre ne propose pas d''essai' USING ERRCODE = 'check_violation';
  END IF;
  v_cur := public.billing_currency_for(v_acc.country_code);
  IF NOT EXISTS (SELECT 1 FROM public.billing_prices WHERE product_version_id = p_version
                    AND billing_interval = p_interval AND currency = v_cur) THEN
    RAISE EXCEPTION 'Aucun prix publié en % pour cette périodicité', v_cur USING ERRCODE = 'check_violation';
  END IF;
  PERFORM 1 FROM public.organizations WHERE id = p_org FOR UPDATE;      -- sérialise deux demandes simultanées
  IF EXISTS (SELECT 1 FROM public.subscriptions WHERE organization_id = p_org
                AND status IN ('trialing','incomplete','active','past_due','suspended')) THEN
    RAISE EXCEPTION 'Un abonnement est déjà en cours' USING ERRCODE = 'unique_violation';
  END IF;
  IF EXISTS (SELECT 1 FROM public.subscriptions WHERE organization_id = p_org AND trial_end IS NOT NULL) THEN
    RAISE EXCEPTION 'L''essai gratuit a déjà été utilisé par cette organisation' USING ERRCODE = 'unique_violation';
  END IF;
  v_email := lower((SELECT email FROM auth.users WHERE id = auth.uid()));
  IF EXISTS (SELECT 1 FROM public.subscriptions WHERE trial_owner_email = v_email
                OR (v_acc.tax_id IS NOT NULL AND trial_tax_id = v_acc.tax_id)) THEN
    RAISE EXCEPTION 'L''essai gratuit a déjà été utilisé pour cette identité de facturation' USING ERRCODE = 'unique_violation';
  END IF;
  INSERT INTO public.subscriptions (organization_id, plan_code, status, product_version_id, billing_interval, currency,
                                    trial_end, current_period_start, current_period_end, trial_tax_id, trial_owner_email)
  VALUES (p_org, v_prod.code, 'trialing', p_version, p_interval, v_cur, now() + make_interval(days => v_ver.trial_days),
          now(), now() + make_interval(days => v_ver.trial_days), v_acc.tax_id, v_email)
  RETURNING id INTO v_id;
  INSERT INTO public.subscription_items (organization_id, subscription_id, product_version_id, kind, quantity)
  VALUES (p_org, v_id, p_version, 'plan', 1);
  RETURN v_id;
END $$;

-- Demande de résiliation par le propriétaire : effet en fin d'essai ou de période, réversible jusque-là.
CREATE OR REPLACE FUNCTION public.billing_schedule_cancel(p_org uuid, p_reason text) RETURNS timestamptz
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_sub public.subscriptions;
BEGIN
  IF public.ai_actor() THEN
    RAISE EXCEPTION 'IA : opération interdite' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF NOT authz.has_org_role(p_org, ARRAY['owner']) THEN
    RAISE EXCEPTION 'Réservé au propriétaire de l''organisation' USING ERRCODE = 'insufficient_privilege';
  END IF;
  SELECT * INTO v_sub FROM public.subscriptions WHERE organization_id = p_org
     AND status IN ('trialing','incomplete','active','past_due','suspended') FOR UPDATE;
  IF v_sub.id IS NULL OR v_sub.status NOT IN ('trialing','active') THEN
    RAISE EXCEPTION 'Aucun abonnement résiliable' USING ERRCODE = 'check_violation';
  END IF;
  IF v_sub.cancel_at IS NOT NULL THEN
    RAISE EXCEPTION 'Résiliation déjà demandée' USING ERRCODE = 'check_violation';
  END IF;
  UPDATE public.subscriptions SET cancel_at = coalesce(current_period_end, trial_end),
                                  cancel_reason = nullif(btrim(coalesce(p_reason, '')), '')
   WHERE id = v_sub.id RETURNING cancel_at INTO v_sub.cancel_at;
  RETURN v_sub.cancel_at;
END $$;

CREATE OR REPLACE FUNCTION public.billing_reactivate(p_org uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_sub public.subscriptions;
BEGIN
  IF public.ai_actor() THEN
    RAISE EXCEPTION 'IA : opération interdite' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF NOT authz.has_org_role(p_org, ARRAY['owner']) THEN
    RAISE EXCEPTION 'Réservé au propriétaire de l''organisation' USING ERRCODE = 'insufficient_privilege';
  END IF;
  SELECT * INTO v_sub FROM public.subscriptions WHERE organization_id = p_org
     AND status IN ('trialing','active') FOR UPDATE;
  IF v_sub.id IS NULL OR v_sub.cancel_at IS NULL OR v_sub.cancel_at <= now() THEN
    RAISE EXCEPTION 'Aucune résiliation en attente à annuler' USING ERRCODE = 'check_violation';
  END IF;
  UPDATE public.subscriptions SET cancel_at = NULL, cancel_reason = NULL WHERE id = v_sub.id;
END $$;

-- État de l'abonnement, lisible par tout membre (affichage des droits) ; les détails restent réservés (RLS).
CREATE OR REPLACE FUNCTION public.billing_subscription_state(p_org uuid)
RETURNS TABLE (id uuid, status text, product_version_id uuid, billing_interval text, currency text,
               trial_end timestamptz, cancel_at timestamptz, current_period_start timestamptz,
               current_period_end timestamptz, created_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT s.id, s.status, s.product_version_id, s.billing_interval, s.currency::text, s.trial_end, s.cancel_at,
         s.current_period_start, s.current_period_end, s.created_at
    FROM public.subscriptions s
   WHERE s.organization_id = p_org AND (authz.is_org_member(p_org) OR authz.is_platform_admin())
   ORDER BY (s.status IN ('trialing','incomplete','active','past_due','suspended')) DESC, s.created_at DESC
   LIMIT 1
$$;

CREATE OR REPLACE FUNCTION public.billing_subscription_items(p_org uuid)
RETURNS TABLE (product_version_id uuid, kind text, quantity int)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT i.product_version_id, i.kind, i.quantity
    FROM public.subscription_items i
   WHERE i.subscription_id = (SELECT st.id FROM public.billing_subscription_state(p_org) st)
$$;

-- Usages mesurés sur les tables existantes (§ 8.2), sans compteur dupliqué : propriétaire, administrateur,
-- administrateur de la plateforme.
CREATE OR REPLACE FUNCTION public.billing_org_usage(p_org uuid, p_from timestamptz, p_to timestamptz)
RETURNS TABLE (key text, used bigint)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF NOT (authz.has_org_role(p_org, ARRAY['owner','admin']) OR authz.is_platform_admin()) THEN
    RAISE EXCEPTION 'Réservé aux propriétaires et administrateurs' USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN QUERY
  SELECT 'users', count(*) FROM public.organization_members WHERE organization_id = p_org
  UNION ALL SELECT 'companies', count(*) FROM public.companies WHERE organization_id = p_org AND archived_at IS NULL
  UNION ALL SELECT 'engagements', count(*) FROM public.engagements WHERE organization_id = p_org AND archived_at IS NULL
  UNION ALL SELECT 'storage_bytes', coalesce(sum(nullif(o.metadata ->> 'size', '')::bigint), 0)::bigint
              FROM storage.objects o WHERE o.name LIKE p_org::text || '/%'
  UNION ALL SELECT 'imports_per_period', count(*) FROM public.import_jobs
             WHERE organization_id = p_org AND created_at >= p_from AND created_at < p_to
  UNION ALL SELECT 'reports_per_period', count(*) FROM public.generated_reports
             WHERE organization_id = p_org AND created_at >= p_from AND created_at < p_to
  UNION ALL SELECT 'ai_tokens_per_period', coalesce(sum(coalesce(input_tokens, 0) + coalesce(output_tokens, 0)), 0)::bigint
              FROM public.ai_messages WHERE organization_id = p_org AND created_at >= p_from AND created_at < p_to
  UNION ALL SELECT 'all_companies', count(*) FROM public.companies WHERE organization_id = p_org;
END $$;

-- ---------------------------------------------------------------------
-- 8. Journal, horodatage, interdiction de l'acteur IA
-- ---------------------------------------------------------------------
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['billing_settings','billing_modules','billing_products','billing_product_versions',
                           'billing_prices','billing_entitlements','billing_promotions','billing_accounts',
                           'subscription_items','billing_promotion_redemptions'] LOOP
    EXECUTE format('CREATE TRIGGER %I AFTER INSERT OR UPDATE OR DELETE ON public.%I
                      FOR EACH ROW EXECUTE FUNCTION public.audit_row_change()', t || '_audit', t);
  END LOOP;
  FOREACH t IN ARRAY ARRAY['billing_settings','billing_modules','billing_products','billing_product_versions',
                           'billing_prices','billing_entitlements','billing_promotions','billing_accounts',
                           'subscription_items','billing_promotion_redemptions'] LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE INSERT OR UPDATE OR DELETE ON public.%I
                    FOR EACH ROW EXECUTE FUNCTION public.guard_not_ai()', '0_not_ai', t);
  END LOOP;
  FOREACH t IN ARRAY ARRAY['billing_settings','billing_modules','billing_products','billing_product_versions',
                           'billing_promotions','billing_accounts'] LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.set_updated_at()',
                   t || '_updated_at', t);
  END LOOP;
END $$;

-- ---------------------------------------------------------------------
-- 9. RLS et droits
-- Catalogue : lecture publique des versions publiées (anon et authenticated), lecture des versions retirées par
-- les utilisateurs connectés (abonnés restés sur une version retirée), tout pour l'administrateur de la plateforme,
-- seul autorisé à écrire. Abonnements et lignes : aucune écriture cliente (fonctions ci-dessus).
-- ---------------------------------------------------------------------
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['billing_settings','billing_modules','billing_products','billing_product_versions',
                           'billing_prices','billing_entitlements','billing_promotions','billing_accounts',
                           'subscription_items','billing_promotion_redemptions'] LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('GRANT ALL ON public.%I TO service_role', t);
  END LOOP;
END $$;

-- paramètres : lecture par les utilisateurs connectés, liste des pays par tous ; écriture par l'administrateur
CREATE POLICY billing_settings_select ON public.billing_settings FOR SELECT TO authenticated, anon USING (true);
CREATE POLICY billing_settings_admin ON public.billing_settings FOR UPDATE TO authenticated
  USING (authz.is_platform_admin()) WITH CHECK (authz.is_platform_admin());
GRANT SELECT, UPDATE ON public.billing_settings TO authenticated;
GRANT SELECT (country_currencies) ON public.billing_settings TO anon;

CREATE POLICY billing_modules_select ON public.billing_modules FOR SELECT TO authenticated, anon USING (true);
CREATE POLICY billing_modules_admin ON public.billing_modules FOR UPDATE TO authenticated
  USING (authz.is_platform_admin()) WITH CHECK (authz.is_platform_admin());
GRANT SELECT, UPDATE (label, description, display_order) ON public.billing_modules TO authenticated;
GRANT SELECT ON public.billing_modules TO anon;

-- offres : visibles dès qu'une version est publiée (ou retirée, pour les connectés)
CREATE POLICY billing_products_public ON public.billing_products FOR SELECT TO anon
  USING (EXISTS (SELECT 1 FROM public.billing_product_versions v WHERE v.product_id = billing_products.id AND v.status = 'published'));
CREATE POLICY billing_products_select ON public.billing_products FOR SELECT TO authenticated
  USING (authz.is_platform_admin()
         OR EXISTS (SELECT 1 FROM public.billing_product_versions v WHERE v.product_id = billing_products.id AND v.status <> 'draft'));
CREATE POLICY billing_product_versions_public ON public.billing_product_versions FOR SELECT TO anon
  USING (status = 'published');
CREATE POLICY billing_product_versions_select ON public.billing_product_versions FOR SELECT TO authenticated
  USING (status <> 'draft' OR authz.is_platform_admin());
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['billing_prices','billing_entitlements'] LOOP
    EXECUTE format('CREATE POLICY %I ON public.%I FOR SELECT TO anon USING (EXISTS (SELECT 1 FROM public.billing_product_versions v
                      WHERE v.id = %I.product_version_id AND v.status = ''published''))', t || '_public', t, t);
    EXECUTE format('CREATE POLICY %I ON public.%I FOR SELECT TO authenticated USING (authz.is_platform_admin()
                      OR EXISTS (SELECT 1 FROM public.billing_product_versions v WHERE v.id = %I.product_version_id AND v.status <> ''draft''))',
                   t || '_select', t, t);
  END LOOP;
  FOREACH t IN ARRAY ARRAY['billing_products','billing_product_versions','billing_prices','billing_entitlements'] LOOP
    EXECUTE format('CREATE POLICY %I ON public.%I FOR INSERT TO authenticated WITH CHECK (authz.is_platform_admin())', t || '_admin_insert', t);
    EXECUTE format('CREATE POLICY %I ON public.%I FOR UPDATE TO authenticated USING (authz.is_platform_admin()) WITH CHECK (authz.is_platform_admin())', t || '_admin_update', t);
    EXECUTE format('CREATE POLICY %I ON public.%I FOR DELETE TO authenticated USING (authz.is_platform_admin())', t || '_admin_delete', t);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON public.%I TO authenticated', t);
    EXECUTE format('GRANT SELECT ON public.%I TO anon', t);
  END LOOP;
END $$;

-- promotions : administration seule (un code n'est pas public)
CREATE POLICY billing_promotions_admin ON public.billing_promotions FOR ALL TO authenticated
  USING (authz.is_platform_admin()) WITH CHECK (authz.is_platform_admin());
GRANT SELECT, INSERT, UPDATE ON public.billing_promotions TO authenticated;
CREATE POLICY billing_promotion_redemptions_select ON public.billing_promotion_redemptions FOR SELECT TO authenticated
  USING (authz.is_platform_admin() OR authz.has_org_role(organization_id, ARRAY['owner']));
GRANT SELECT ON public.billing_promotion_redemptions TO authenticated;

-- compte de facturation : lecture owner / admin / administrateur de la plateforme ; écriture owner
CREATE POLICY billing_accounts_select ON public.billing_accounts FOR SELECT TO authenticated
  USING (authz.has_org_role(organization_id, ARRAY['owner','admin']) OR authz.is_platform_admin());
CREATE POLICY billing_accounts_insert ON public.billing_accounts FOR INSERT TO authenticated
  WITH CHECK (authz.has_org_role(organization_id, ARRAY['owner']));
CREATE POLICY billing_accounts_update ON public.billing_accounts FOR UPDATE TO authenticated
  USING (authz.has_org_role(organization_id, ARRAY['owner'])) WITH CHECK (authz.has_org_role(organization_id, ARRAY['owner']));
GRANT SELECT, INSERT, UPDATE ON public.billing_accounts TO authenticated;

-- abonnements et lignes : lecture owner / admin / administrateur de la plateforme ; aucune écriture cliente
CREATE POLICY subscriptions_admin_select ON public.subscriptions FOR SELECT TO authenticated
  USING (authz.is_platform_admin());
CREATE POLICY subscription_items_select ON public.subscription_items FOR SELECT TO authenticated
  USING (authz.has_org_role(organization_id, ARRAY['owner','admin']) OR authz.is_platform_admin());
GRANT SELECT ON public.subscription_items TO authenticated;

REVOKE ALL ON FUNCTION public.billing_start_trial(uuid, uuid, text), public.billing_schedule_cancel(uuid, text),
  public.billing_reactivate(uuid), public.billing_subscription_state(uuid), public.billing_subscription_items(uuid),
  public.billing_org_usage(uuid, timestamptz, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.billing_start_trial(uuid, uuid, text), public.billing_schedule_cancel(uuid, text),
  public.billing_reactivate(uuid), public.billing_subscription_state(uuid), public.billing_subscription_items(uuid),
  public.billing_org_usage(uuid, timestamptz, timestamptz) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.billing_currency_for(text), public.billing_currency_ok(text),
  public.billing_amount_ok(numeric, text) TO authenticated, anon, service_role;

-- ---------------------------------------------------------------------
-- 10. Lectures contrôlées complémentaires
-- ---------------------------------------------------------------------
-- L'organisation a-t-elle des données ? (accès en lecture seule après un essai échu, § 8.1) : tout membre.
CREATE OR REPLACE FUNCTION public.billing_org_has_data(p_org uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT (authz.is_org_member(p_org) OR authz.is_platform_admin())
         AND EXISTS (SELECT 1 FROM public.companies WHERE organization_id = p_org)
$$;

-- Conditions d'un code promotionnel valide, pour l'aperçu chiffré d'un propriétaire ou administrateur
-- d'organisation : le code n'est pas listable (aucune lecture de la table), il se vérifie un par un.
CREATE OR REPLACE FUNCTION public.billing_promotion_lookup(p_org uuid, p_code text)
RETURNS TABLE (id uuid, code text, discount_type text, percent numeric, fixed_amount numeric, fixed_currency text,
               product_ids uuid[], billing_interval text, duration text, duration_periods int)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF NOT (authz.has_org_role(p_org, ARRAY['owner','admin']) OR authz.is_platform_admin()) THEN
    RAISE EXCEPTION 'Réservé aux propriétaires et administrateurs' USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN QUERY
  SELECT p.id, p.code, p.discount_type, p.percent, p.fixed_amount, p.fixed_currency::text, p.product_ids,
         p.billing_interval, p.duration, p.duration_periods
    FROM public.billing_promotions p
   WHERE p.code = upper(btrim(p_code)) AND p.status = 'active' AND p.valid_from <= now()
     AND (p.valid_until IS NULL OR p.valid_until > now())
     AND (p.max_redemptions IS NULL
          OR (SELECT count(*) FROM public.billing_promotion_redemptions r WHERE r.promotion_id = p.id) < p.max_redemptions)
     AND NOT EXISTS (SELECT 1 FROM public.billing_promotion_redemptions r WHERE r.promotion_id = p.id AND r.organization_id = p_org);
END $$;

REVOKE ALL ON FUNCTION public.billing_org_has_data(uuid), public.billing_promotion_lookup(uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.billing_org_has_data(uuid), public.billing_promotion_lookup(uuid, text)
  TO authenticated, service_role;
