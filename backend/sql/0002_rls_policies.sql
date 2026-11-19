-- =====================================================================
-- KOFINEX — Migration 0002 : sécurité (RLS Supabase, privilèges, gardes)
--
-- Modèle :
--   * Rôles d'organisation : owner > admin > member > viewer
--   * Rôles d'entreprise   : accountant, controller, analyst, auditor, viewer
--   * owner/admin de l'organisation = tous les droits sur ses entreprises
--   * member/viewer d'organisation = accès uniquement aux entreprises où
--     ils figurent dans company_members
-- Les fonctions d'autorisation sont dans le schéma `authz` (non exposé par
-- l'API PostgREST de Supabase), SECURITY DEFINER pour éviter la récursion RLS.
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS authz;
REVOKE ALL ON SCHEMA authz FROM PUBLIC;
GRANT USAGE ON SCHEMA authz TO authenticated, service_role;

CREATE OR REPLACE FUNCTION authz.is_platform_admin() RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT coalesce((SELECT is_platform_admin FROM public.profiles WHERE id = auth.uid()), false)
$$;

CREATE OR REPLACE FUNCTION authz.org_role(p_org uuid) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT role FROM public.organization_members
   WHERE organization_id = p_org AND user_id = auth.uid()
$$;

CREATE OR REPLACE FUNCTION authz.is_org_member(p_org uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT EXISTS (SELECT 1 FROM public.organization_members
                  WHERE organization_id = p_org AND user_id = auth.uid())
$$;

CREATE OR REPLACE FUNCTION authz.has_org_role(p_org uuid, p_roles text[]) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT EXISTS (SELECT 1 FROM public.organization_members
                  WHERE organization_id = p_org AND user_id = auth.uid() AND role = ANY (p_roles))
$$;

-- Rôle effectif sur une entreprise : 'org_admin' pour owner/admin de l'organisation,
-- sinon le rôle dans company_members, sinon NULL.
CREATE OR REPLACE FUNCTION authz.company_role(p_company uuid) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT CASE
           WHEN om.role IN ('owner','admin') THEN 'org_admin'
           ELSE cm.role
         END
    FROM public.companies c
    JOIN public.organization_members om
      ON om.organization_id = c.organization_id AND om.user_id = auth.uid()
    LEFT JOIN public.company_members cm
      ON cm.company_id = c.id AND cm.user_id = auth.uid()
   WHERE c.id = p_company
$$;

CREATE OR REPLACE FUNCTION authz.can_access_company(p_company uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT authz.company_role(p_company) IS NOT NULL
$$;

CREATE OR REPLACE FUNCTION authz.has_company_role(p_company uuid, p_roles text[]) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT coalesce(authz.company_role(p_company) = ANY (p_roles || ARRAY['org_admin']), false)
$$;

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA authz FROM PUBLIC;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA authz TO authenticated, service_role;

-- ---------------------------------------------------------------------
-- Privilèges de base
-- ---------------------------------------------------------------------
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO authenticated;
GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;

-- profils : créés par trigger ; l'utilisateur ne modifie que ses champs non sensibles
REVOKE INSERT, UPDATE, DELETE ON public.profiles FROM authenticated;
GRANT UPDATE (full_name, phone, avatar_url, locale) ON public.profiles TO authenticated;

-- journal d'audit : ajout seul
REVOKE UPDATE, DELETE ON public.audit_logs FROM authenticated;

-- abonnements / paiements : écrits uniquement par le backend (webhooks du prestataire)
REVOKE INSERT, UPDATE, DELETE ON public.subscriptions, public.payments FROM authenticated;

-- intégrations : les identifiants chiffrés ne sont jamais lisibles côté client
REVOKE SELECT ON public.integrations FROM authenticated;
GRANT SELECT (id, organization_id, company_id, provider, status, config, last_verified_at,
              last_sync_at, last_error, created_by, created_at, updated_at)
  ON public.integrations TO authenticated;

-- champs d'identité figés après création
REVOKE UPDATE ON public.organizations FROM authenticated;
GRANT UPDATE (name, slug, org_type, country_code, default_currency, archived_at)
  ON public.organizations TO authenticated;

-- ---------------------------------------------------------------------
-- Activation RLS sur toutes les tables du schéma public
-- ---------------------------------------------------------------------
DO $$
DECLARE t text;
BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
  END LOOP;
END $$;

-- ---------------------------------------------------------------------
-- Identité & tenants
-- ---------------------------------------------------------------------
CREATE POLICY profiles_select ON public.profiles FOR SELECT TO authenticated
  USING (
    id = auth.uid()
    OR authz.is_platform_admin()
    OR EXISTS (SELECT 1 FROM public.organization_members me
                 JOIN public.organization_members other
                   ON other.organization_id = me.organization_id
                WHERE me.user_id = auth.uid() AND other.user_id = profiles.id)
  );
CREATE POLICY profiles_update ON public.profiles FOR UPDATE TO authenticated
  USING (id = auth.uid()) WITH CHECK (id = auth.uid());

CREATE POLICY organizations_select ON public.organizations FOR SELECT TO authenticated
  USING (authz.is_org_member(id) OR created_by = auth.uid() OR authz.is_platform_admin());
CREATE POLICY organizations_insert ON public.organizations FOR INSERT TO authenticated
  WITH CHECK (created_by = auth.uid() AND is_demo = false);
CREATE POLICY organizations_update ON public.organizations FOR UPDATE TO authenticated
  USING (authz.has_org_role(id, ARRAY['owner','admin']))
  WITH CHECK (authz.has_org_role(id, ARRAY['owner','admin']));
CREATE POLICY organizations_delete ON public.organizations FOR DELETE TO authenticated
  USING (authz.has_org_role(id, ARRAY['owner']));

CREATE POLICY org_members_select ON public.organization_members FOR SELECT TO authenticated
  USING (authz.is_org_member(organization_id));
-- un admin gère les membres mais ne peut ni créer ni modifier un owner
CREATE POLICY org_members_insert ON public.organization_members FOR INSERT TO authenticated
  WITH CHECK (
    authz.has_org_role(organization_id, ARRAY['owner'])
    OR (authz.has_org_role(organization_id, ARRAY['admin']) AND role <> 'owner')
  );
CREATE POLICY org_members_update ON public.organization_members FOR UPDATE TO authenticated
  USING (
    authz.has_org_role(organization_id, ARRAY['owner'])
    OR (authz.has_org_role(organization_id, ARRAY['admin']) AND role <> 'owner')
  )
  WITH CHECK (
    authz.has_org_role(organization_id, ARRAY['owner'])
    OR (authz.has_org_role(organization_id, ARRAY['admin']) AND role <> 'owner')
  );
CREATE POLICY org_members_delete ON public.organization_members FOR DELETE TO authenticated
  USING (
    user_id = auth.uid()   -- quitter l'organisation
    OR authz.has_org_role(organization_id, ARRAY['owner'])
    OR (authz.has_org_role(organization_id, ARRAY['admin']) AND role <> 'owner')
  );

-- La 2e condition ne relit pas la ligne : indispensable pour INSERT … RETURNING,
-- où la ligne nouvellement insérée n'est pas encore visible des fonctions STABLE.
CREATE POLICY companies_select ON public.companies FOR SELECT TO authenticated
  USING (authz.can_access_company(id) OR authz.has_org_role(organization_id, ARRAY['owner','admin']));
CREATE POLICY companies_insert ON public.companies FOR INSERT TO authenticated
  WITH CHECK (authz.has_org_role(organization_id, ARRAY['owner','admin'])
              AND created_by = auth.uid() AND is_demo = false);
CREATE POLICY companies_update ON public.companies FOR UPDATE TO authenticated
  USING (authz.has_org_role(organization_id, ARRAY['owner','admin']))
  WITH CHECK (authz.has_org_role(organization_id, ARRAY['owner','admin']));
CREATE POLICY companies_delete ON public.companies FOR DELETE TO authenticated
  USING (authz.has_org_role(organization_id, ARRAY['owner']));

CREATE POLICY company_members_select ON public.company_members FOR SELECT TO authenticated
  USING (authz.can_access_company(company_id));
CREATE POLICY company_members_write ON public.company_members FOR ALL TO authenticated
  USING (authz.has_org_role(organization_id, ARRAY['owner','admin']))
  WITH CHECK (authz.has_org_role(organization_id, ARRAY['owner','admin']));

CREATE POLICY fiscal_years_select ON public.fiscal_years FOR SELECT TO authenticated
  USING (authz.can_access_company(company_id));
CREATE POLICY fiscal_years_insert ON public.fiscal_years FOR INSERT TO authenticated
  WITH CHECK (authz.has_company_role(company_id, ARRAY['accountant']) AND created_by = auth.uid());
CREATE POLICY fiscal_years_update ON public.fiscal_years FOR UPDATE TO authenticated
  USING (authz.has_company_role(company_id, ARRAY['accountant']))
  WITH CHECK (authz.has_company_role(company_id, ARRAY['accountant']));
CREATE POLICY fiscal_years_delete ON public.fiscal_years FOR DELETE TO authenticated
  USING (authz.has_org_role(organization_id, ARRAY['owner','admin']) AND status = 'open');

-- ---------------------------------------------------------------------
-- Référentiels globaux : lecture pour tous, écriture administrateurs plateforme
-- ---------------------------------------------------------------------
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['accounting_frameworks','framework_versions','chart_of_accounts'] LOOP
    EXECUTE format('CREATE POLICY %I ON public.%I FOR SELECT TO authenticated USING (true)',
                   t || '_select', t);
    EXECUTE format('CREATE POLICY %I ON public.%I FOR ALL TO authenticated
                      USING (authz.is_platform_admin()) WITH CHECK (authz.is_platform_admin())',
                   t || '_admin_write', t);
  END LOOP;
END $$;

-- Tables mixtes : ligne officielle (organization_id NULL) ou surcharge d'un tenant
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['account_mappings','financial_formulas','report_templates'] LOOP
    EXECUTE format($f$
      CREATE POLICY %I ON public.%I FOR SELECT TO authenticated
        USING (organization_id IS NULL OR authz.is_org_member(organization_id))$f$,
      t || '_select', t);
    EXECUTE format($f$
      CREATE POLICY %I ON public.%I FOR ALL TO authenticated
        USING (CASE WHEN organization_id IS NULL THEN authz.is_platform_admin()
                    ELSE authz.has_org_role(organization_id, ARRAY['owner','admin']) END)
        WITH CHECK (CASE WHEN organization_id IS NULL THEN authz.is_platform_admin()
                    ELSE authz.has_org_role(organization_id, ARRAY['owner','admin']) END)$f$,
      t || '_write', t);
  END LOOP;
END $$;

-- ---------------------------------------------------------------------
-- Tables rattachées à une entreprise : lecture = accès à l'entreprise,
-- écriture = rôle(s) d'entreprise listé(s) (+ owner/admin d'organisation)
-- ---------------------------------------------------------------------
DO $$
DECLARE
  spec  record;
BEGIN
  FOR spec IN
    SELECT * FROM (VALUES
      ('financial_documents',   ARRAY['accountant']),
      ('import_jobs',           ARRAY['accountant']),
      ('trial_balance_entries', ARRAY['accountant']),
      ('financial_statements',  ARRAY['accountant']),
      ('financial_analyses',    ARRAY['accountant','controller','analyst']),
      ('financial_alerts',      ARRAY['accountant','controller','analyst']),
      ('cost_centers',          ARRAY['accountant','controller']),
      ('budgets',               ARRAY['accountant','controller']),
      ('budget_lines',          ARRAY['accountant','controller']),
      ('budget_actuals',        ARRAY['accountant','controller']),
      ('cost_entries',          ARRAY['accountant','controller']),
      ('ai_reports',            ARRAY['accountant','controller','analyst']),
      ('generated_reports',     ARRAY['accountant','controller','analyst'])
    ) AS s(tbl, roles)
  LOOP
    EXECUTE format('CREATE POLICY %I ON public.%I FOR SELECT TO authenticated
                      USING (authz.can_access_company(company_id))',
                   spec.tbl || '_select', spec.tbl);
    EXECUTE format('CREATE POLICY %I ON public.%I FOR INSERT TO authenticated
                      WITH CHECK (authz.has_company_role(company_id, %L::text[]))',
                   spec.tbl || '_insert', spec.tbl, spec.roles);
    EXECUTE format('CREATE POLICY %I ON public.%I FOR UPDATE TO authenticated
                      USING (authz.has_company_role(company_id, %L::text[]))
                      WITH CHECK (authz.has_company_role(company_id, %L::text[]))',
                   spec.tbl || '_update', spec.tbl, spec.roles, spec.roles);
    EXECUTE format('CREATE POLICY %I ON public.%I FOR DELETE TO authenticated
                      USING (authz.has_company_role(company_id, %L::text[]))',
                   spec.tbl || '_delete', spec.tbl, spec.roles);
  END LOOP;
END $$;

-- Tables filles sans company_id : on remonte au parent
CREATE POLICY fs_lines_select ON public.financial_statement_lines FOR SELECT TO authenticated
  USING (EXISTS (SELECT 1 FROM public.financial_statements s
                  WHERE s.id = statement_id AND authz.can_access_company(s.company_id)));
CREATE POLICY fs_lines_write ON public.financial_statement_lines FOR ALL TO authenticated
  USING (EXISTS (SELECT 1 FROM public.financial_statements s
                  WHERE s.id = statement_id AND authz.has_company_role(s.company_id, ARRAY['accountant'])))
  WITH CHECK (EXISTS (SELECT 1 FROM public.financial_statements s
                  WHERE s.id = statement_id AND authz.has_company_role(s.company_id, ARRAY['accountant'])));

CREATE POLICY indicators_select ON public.financial_indicators FOR SELECT TO authenticated
  USING (EXISTS (SELECT 1 FROM public.financial_analyses a
                  WHERE a.id = analysis_id AND authz.can_access_company(a.company_id)));
CREATE POLICY indicators_write ON public.financial_indicators FOR ALL TO authenticated
  USING (EXISTS (SELECT 1 FROM public.financial_analyses a
                  WHERE a.id = analysis_id
                    AND authz.has_company_role(a.company_id, ARRAY['accountant','controller','analyst'])))
  WITH CHECK (EXISTS (SELECT 1 FROM public.financial_analyses a
                  WHERE a.id = analysis_id
                    AND authz.has_company_role(a.company_id, ARRAY['accountant','controller','analyst'])));

CREATE POLICY import_mappings_select ON public.import_mappings FOR SELECT TO authenticated
  USING (CASE WHEN company_id IS NULL THEN authz.is_org_member(organization_id)
              ELSE authz.can_access_company(company_id) END);
CREATE POLICY import_mappings_write ON public.import_mappings FOR ALL TO authenticated
  USING (CASE WHEN company_id IS NULL THEN authz.has_org_role(organization_id, ARRAY['owner','admin'])
              ELSE authz.has_company_role(company_id, ARRAY['accountant']) END)
  WITH CHECK (CASE WHEN company_id IS NULL THEN authz.has_org_role(organization_id, ARRAY['owner','admin'])
              ELSE authz.has_company_role(company_id, ARRAY['accountant']) END);

-- Conversations IA : privées à leur auteur, qui doit avoir accès à l'entreprise
CREATE POLICY ai_conv_select ON public.ai_conversations FOR SELECT TO authenticated
  USING (user_id = auth.uid() AND authz.can_access_company(company_id));
CREATE POLICY ai_conv_write ON public.ai_conversations FOR ALL TO authenticated
  USING (user_id = auth.uid()
         AND authz.has_company_role(company_id, ARRAY['accountant','controller','analyst']))
  WITH CHECK (user_id = auth.uid()
         AND authz.has_company_role(company_id, ARRAY['accountant','controller','analyst']));

CREATE POLICY ai_messages_select ON public.ai_messages FOR SELECT TO authenticated
  USING (EXISTS (SELECT 1 FROM public.ai_conversations c
                  WHERE c.id = conversation_id AND c.user_id = auth.uid()
                    AND authz.can_access_company(c.company_id)));
CREATE POLICY ai_messages_insert ON public.ai_messages FOR INSERT TO authenticated
  WITH CHECK (EXISTS (SELECT 1 FROM public.ai_conversations c
                  WHERE c.id = conversation_id AND c.user_id = auth.uid()
                    AND authz.has_company_role(c.company_id, ARRAY['accountant','controller','analyst'])));

-- Intégrations : gérées par owner/admin ; lecture aussi pour le comptable de l'entreprise
CREATE POLICY integrations_select ON public.integrations FOR SELECT TO authenticated
  USING (authz.has_org_role(organization_id, ARRAY['owner','admin'])
         OR (company_id IS NOT NULL AND authz.has_company_role(company_id, ARRAY['accountant'])));
CREATE POLICY integrations_write ON public.integrations FOR ALL TO authenticated
  USING (authz.has_org_role(organization_id, ARRAY['owner','admin']))
  WITH CHECK (authz.has_org_role(organization_id, ARRAY['owner','admin']));

-- Audit : lecture owner/admin ou comptable/auditeur de l'entreprise concernée
CREATE POLICY audit_logs_select ON public.audit_logs FOR SELECT TO authenticated
  USING (
    (organization_id IS NOT NULL AND authz.has_org_role(organization_id, ARRAY['owner','admin']))
    OR (company_id IS NOT NULL AND authz.has_company_role(company_id, ARRAY['accountant','auditor']))
    OR authz.is_platform_admin()
  );
CREATE POLICY audit_logs_insert ON public.audit_logs FOR INSERT TO authenticated
  WITH CHECK (user_id = auth.uid()
              AND (organization_id IS NULL OR authz.is_org_member(organization_id)));

-- Abonnements & paiements : lecture owner/admin
CREATE POLICY subscriptions_select ON public.subscriptions FOR SELECT TO authenticated
  USING (authz.has_org_role(organization_id, ARRAY['owner','admin']));
CREATE POLICY payments_select ON public.payments FOR SELECT TO authenticated
  USING (authz.has_org_role(organization_id, ARRAY['owner']));

-- ---------------------------------------------------------------------
-- Gardes métier : un exercice clôturé est figé
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.guard_closed_fiscal_year() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  fy_status text;
BEGIN
  SELECT status INTO fy_status FROM public.fiscal_years
   WHERE id = coalesce(NEW.fiscal_year_id, OLD.fiscal_year_id);
  IF fy_status IS NOT NULL AND fy_status <> 'open' THEN
    RAISE EXCEPTION 'Exercice clôturé : modification de % interdite', TG_TABLE_NAME
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN coalesce(NEW, OLD);
END $$;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['trial_balance_entries','import_jobs','financial_statements'] LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE INSERT OR UPDATE OR DELETE ON public.%I
                      FOR EACH ROW EXECUTE FUNCTION public.guard_closed_fiscal_year()',
                   t || '_closed_fy_guard', t);
  END LOOP;
END $$;

-- Une organisation de démonstration ne peut être créée que par le service (script de seed)
-- (garanti par les policies : is_demo = false imposé aux utilisateurs).
