-- =====================================================================
-- KOFINEX — Migration 0015 : seuils d'alerte budgétaire par entreprise (contrôle de gestion, pilotage)
-- Seule table ajoutée par l'évolution du contrôle de gestion : les indicateurs sont recalculés à la demande à partir des
-- sources validées (écritures natives, grand livre ou balance importés) ; aucune copie des écritures n'est stockée.
-- =====================================================================
CREATE TABLE public.management_alert_settings (
  company_id              uuid PRIMARY KEY,
  organization_id         uuid NOT NULL,
  consumption_info_pct    numeric(6,2) NOT NULL DEFAULT 80  CHECK (consumption_info_pct BETWEEN 0 AND 1000),
  overrun_warning_pct     numeric(6,2) NOT NULL DEFAULT 100 CHECK (overrun_warning_pct BETWEEN 0 AND 1000),
  overrun_critical_pct    numeric(6,2) NOT NULL DEFAULT 110 CHECK (overrun_critical_pct BETWEEN 0 AND 1000),
  pace_gap_points         numeric(6,2) NOT NULL DEFAULT 15  CHECK (pace_gap_points BETWEEN 0 AND 100),
  under_execution_points  numeric(6,2) NOT NULL DEFAULT 25  CHECK (under_execution_points BETWEEN 0 AND 100),
  center_variance_pct     numeric(6,2) NOT NULL DEFAULT 10  CHECK (center_variance_pct BETWEEN 0 AND 1000),
  change_pct              numeric(6,2) NOT NULL DEFAULT 10  CHECK (change_pct BETWEEN 0 AND 1000),       -- variation significative N / N-1
  concentration_pct       numeric(6,2) NOT NULL DEFAULT 30  CHECK (concentration_pct BETWEEN 0 AND 100),  -- part du premier client / fournisseur
  updated_by              uuid REFERENCES public.profiles(id),
  updated_at              timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (company_id, organization_id) REFERENCES public.companies(id, organization_id) ON DELETE CASCADE,
  CHECK (consumption_info_pct <= overrun_warning_pct AND overrun_warning_pct <= overrun_critical_pct)
);

CREATE OR REPLACE FUNCTION public.guard_management_alert_settings() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF TG_OP = 'UPDATE' AND (NEW.company_id <> OLD.company_id OR NEW.organization_id <> OLD.organization_id) THEN
    RAISE EXCEPTION 'Seuils : entreprise non modifiable' USING ERRCODE = 'check_violation';
  END IF;
  NEW.updated_by := coalesce(auth.uid(), NEW.updated_by);
  NEW.updated_at := now();
  RETURN NEW;
END $$;
CREATE TRIGGER management_alert_settings_guard BEFORE INSERT OR UPDATE ON public.management_alert_settings
  FOR EACH ROW EXECUTE FUNCTION public.guard_management_alert_settings();
CREATE TRIGGER management_alert_settings_audit AFTER INSERT OR UPDATE OR DELETE ON public.management_alert_settings
  FOR EACH ROW EXECUTE FUNCTION public.audit_row_change();
CREATE TRIGGER "0_not_ai" BEFORE INSERT OR UPDATE OR DELETE ON public.management_alert_settings
  FOR EACH ROW EXECUTE FUNCTION public.guard_not_ai();

ALTER TABLE public.management_alert_settings ENABLE ROW LEVEL SECURITY;
-- lecture : membres de l'entreprise ; écriture : contrôleurs de gestion et administrateurs (droits d'approbation budgétaire)
CREATE POLICY management_alert_settings_select ON public.management_alert_settings FOR SELECT TO authenticated
  USING (authz.can_access_company(company_id));
CREATE POLICY management_alert_settings_write ON public.management_alert_settings FOR ALL TO authenticated
  USING (authz.has_company_role(company_id, ARRAY['controller']))
  WITH CHECK (authz.has_company_role(company_id, ARRAY['controller']));
GRANT SELECT, INSERT, UPDATE, DELETE ON public.management_alert_settings TO authenticated;
GRANT ALL ON public.management_alert_settings TO service_role;
