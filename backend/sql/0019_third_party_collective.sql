-- =====================================================================
-- KOFINEX — Migration 0019 : plan tiers, rattachement obligatoire à un compte collectif
-- (correctif du contrôle de gestion, phase 2 ; décision 1 du 20 novembre 2026, docs/CONTROLE_GESTION.md § 12)
--
-- Un compte auxiliaire de tiers (client, fournisseur, salarié, autre) est un tiers (`third_parties`, code
-- alphanumérique, ex. 4011TOY) rattaché à un compte collectif de l'entreprise : le plan comptable reste numérique.
-- Aucune donnée n'est modifiée ni supprimée :
-- - la contrainte est posée NOT VALID : elle s'impose à tout nouveau tiers et à toute modification, les tiers
--   existants non rattachés sont signalés à l'écran et ne peuvent plus être utilisés sur une écriture tant qu'ils
--   ne sont pas rattachés ;
-- - la migration 0014 n'est pas réécrite : les gardes ajoutées sont de nouveaux déclencheurs.
-- =====================================================================

-- 1. Rattachement obligatoire (reprise contrôlée des tiers existants)
ALTER TABLE public.third_parties
  ADD CONSTRAINT third_parties_collective_required CHECK (collective_account_number IS NOT NULL) NOT VALID;

-- 2. Le compte collectif de rattachement doit être actif au moment du rattachement
CREATE OR REPLACE FUNCTION public.guard_third_party_collective() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_active boolean;
BEGIN
  IF NEW.collective_account_number IS NOT NULL
     AND (TG_OP = 'INSERT' OR NEW.collective_account_number IS DISTINCT FROM OLD.collective_account_number) THEN
    SELECT is_active INTO v_active FROM public.company_accounts
     WHERE company_id = NEW.company_id AND account_number = NEW.collective_account_number;
    IF NOT v_active THEN
      RAISE EXCEPTION 'Le compte collectif % est en sommeil : rattachement impossible', NEW.collective_account_number
        USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER third_parties_collective_guard BEFORE INSERT OR UPDATE ON public.third_parties
  FOR EACH ROW EXECUTE FUNCTION public.guard_third_party_collective();

-- 3. Un compte collectif auquel des tiers sont rattachés garde son caractère collectif et un type compatible
CREATE OR REPLACE FUNCTION public.guard_collective_with_third_parties() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_bad text;
BEGIN
  IF NEW.requires_third_party IS DISTINCT FROM OLD.requires_third_party
     OR NEW.third_party_kind IS DISTINCT FROM OLD.third_party_kind THEN
    SELECT string_agg(t.code, ', ' ORDER BY t.code) INTO v_bad FROM public.third_parties t
     WHERE t.company_id = OLD.company_id AND t.collective_account_number = OLD.account_number
       AND (NOT NEW.requires_third_party OR (NEW.third_party_kind IS NOT NULL AND NEW.third_party_kind <> t.kind));
    IF v_bad IS NOT NULL THEN
      RAISE EXCEPTION 'Compte % : tiers rattachés incompatibles avec ce changement (%)', OLD.account_number, v_bad
        USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER company_accounts_guard_third_parties BEFORE UPDATE ON public.company_accounts
  FOR EACH ROW EXECUTE FUNCTION public.guard_collective_with_third_parties();

-- 4. Un tiers non rattaché (reprise) ne peut pas être porté sur une ligne d'écriture
CREATE OR REPLACE FUNCTION public.guard_line_third_party_attached() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_code text;
BEGIN
  IF NEW.third_party_id IS NOT NULL
     AND (TG_OP = 'INSERT' OR NEW.third_party_id IS DISTINCT FROM OLD.third_party_id) THEN
    SELECT code INTO v_code FROM public.third_parties WHERE id = NEW.third_party_id AND collective_account_number IS NULL;
    IF v_code IS NOT NULL THEN
      RAISE EXCEPTION 'Tiers % non rattaché à un compte collectif : rattachez-le avant de l''utiliser', v_code
        USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER journal_entry_lines_third_party_attached BEFORE INSERT OR UPDATE ON public.journal_entry_lines
  FOR EACH ROW EXECUTE FUNCTION public.guard_line_third_party_attached();
