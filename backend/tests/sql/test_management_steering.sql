-- =====================================================================
-- Tests migration 0015 : seuils d'alerte du contrôle de gestion (RLS, droits, cohérence, isolation, acteur IA).
-- Données FICTIVES.
-- =====================================================================
\set QUIET on
BEGIN;
CREATE OR REPLACE FUNCTION pg_temp.ok(cond boolean, label text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN IF cond IS DISTINCT FROM true THEN RAISE EXCEPTION 'ÉCHEC : %', label; END IF; RAISE NOTICE 'ok - %', label; END $$;
CREATE OR REPLACE FUNCTION pg_temp.fails(q text, label text, pattern text DEFAULT NULL) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  BEGIN EXECUTE q;
  EXCEPTION WHEN OTHERS THEN
    IF pattern IS NOT NULL AND SQLERRM NOT ILIKE '%' || pattern || '%' THEN RAISE EXCEPTION 'ÉCHEC : % (%)', label, SQLERRM; END IF;
    RAISE NOTICE 'ok - % (refusé : %)', label, SQLERRM; RETURN;
  END;
  RAISE EXCEPTION 'ÉCHEC : % (aucune erreur levée)', label;
END $$;
CREATE OR REPLACE FUNCTION pg_temp.act_as(uid uuid) RETURNS void LANGUAGE sql AS $$
  SELECT set_config('request.jwt.claims', json_build_object('sub', uid, 'role', 'authenticated')::text, true);
$$;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA pg_temp TO authenticated;

INSERT INTO auth.users (id, email) VALUES
  ('e2000000-0000-0000-0000-00000000000a', 'own@ms.test'), ('e2000000-0000-0000-0000-00000000000c', 'ctrl@ms.test'),
  ('e2000000-0000-0000-0000-00000000000d', 'acc@ms.test'), ('e2000000-0000-0000-0000-00000000000b', 'out@mt.test');
INSERT INTO public.accounting_frameworks (id, code, name) VALUES ('f2000000-0000-0000-0000-0000000000fa', 'TEST_MS', 'Test');
SET LOCAL session_replication_role = replica;
INSERT INTO public.profiles (id, email) SELECT id, email FROM auth.users WHERE email LIKE '%@m_.test' ON CONFLICT DO NOTHING;
INSERT INTO public.organizations (id, name, slug, created_by) VALUES
  ('1c000000-0000-0000-0000-00000000000a', 'Org MS', 'org-ms', 'e2000000-0000-0000-0000-00000000000a'),
  ('1c000000-0000-0000-0000-00000000000b', 'Org MT', 'org-mt', 'e2000000-0000-0000-0000-00000000000b');
INSERT INTO public.organization_members (organization_id, user_id, role) VALUES
  ('1c000000-0000-0000-0000-00000000000a', 'e2000000-0000-0000-0000-00000000000a', 'owner'),
  ('1c000000-0000-0000-0000-00000000000a', 'e2000000-0000-0000-0000-00000000000c', 'member'),
  ('1c000000-0000-0000-0000-00000000000a', 'e2000000-0000-0000-0000-00000000000d', 'member'),
  ('1c000000-0000-0000-0000-00000000000b', 'e2000000-0000-0000-0000-00000000000b', 'owner');
INSERT INTO public.companies (id, organization_id, name, framework_id, created_by) VALUES
  ('2c000000-0000-0000-0000-00000000000a', '1c000000-0000-0000-0000-00000000000a', 'Entité MS', 'f2000000-0000-0000-0000-0000000000fa',
   'e2000000-0000-0000-0000-00000000000a');
INSERT INTO public.company_members (organization_id, company_id, user_id, role) VALUES
  ('1c000000-0000-0000-0000-00000000000a', '2c000000-0000-0000-0000-00000000000a', 'e2000000-0000-0000-0000-00000000000c', 'controller'),
  ('1c000000-0000-0000-0000-00000000000a', '2c000000-0000-0000-0000-00000000000a', 'e2000000-0000-0000-0000-00000000000d', 'accountant');
SET LOCAL session_replication_role = origin;
SET LOCAL ROLE authenticated;

SELECT pg_temp.act_as('e2000000-0000-0000-0000-00000000000d');
SELECT pg_temp.fails($q$INSERT INTO public.management_alert_settings (company_id, organization_id) VALUES
  ('2c000000-0000-0000-0000-00000000000a', '1c000000-0000-0000-0000-00000000000a')$q$, 'comptable : seuils réservés au contrôle', 'row-level security');
SELECT pg_temp.act_as('e2000000-0000-0000-0000-00000000000c');
SELECT pg_temp.fails($q$INSERT INTO public.management_alert_settings (company_id, organization_id, overrun_warning_pct, overrun_critical_pct)
  VALUES ('2c000000-0000-0000-0000-00000000000a', '1c000000-0000-0000-0000-00000000000a', 120, 110)$q$,
  'seuils incohérents (avertissement > critique)', 'check');
INSERT INTO public.management_alert_settings (company_id, organization_id, overrun_critical_pct)
  VALUES ('2c000000-0000-0000-0000-00000000000a', '1c000000-0000-0000-0000-00000000000a', 120);
SELECT pg_temp.ok((SELECT overrun_critical_pct = 120 AND updated_by = 'e2000000-0000-0000-0000-00000000000c' FROM public.management_alert_settings),
  'contrôleur : seuils enregistrés, auteur tracé');
SELECT pg_temp.act_as('e2000000-0000-0000-0000-00000000000a');
SELECT pg_temp.ok((SELECT count(*) FROM public.audit_logs WHERE entity_type = 'management_alert_settings') >= 1, 'modification journalisée (lue par le propriétaire)');
SELECT pg_temp.act_as('e2000000-0000-0000-0000-00000000000c');
SELECT set_config('kofinex.actor', 'ai', true);
SELECT pg_temp.fails($q$UPDATE public.management_alert_settings SET change_pct = 5$q$, 'acteur IA : aucune modification', 'IA');
SELECT set_config('kofinex.actor', '', true);
SELECT pg_temp.act_as('e2000000-0000-0000-0000-00000000000d');
SELECT pg_temp.ok((SELECT count(*) FROM public.management_alert_settings) = 1, 'comptable : lecture des seuils');
UPDATE public.management_alert_settings SET change_pct = 1;
SELECT pg_temp.ok((SELECT change_pct FROM public.management_alert_settings) = 10, 'comptable : modification sans effet (RLS)');
SELECT pg_temp.act_as('e2000000-0000-0000-0000-00000000000b');
SELECT pg_temp.ok((SELECT count(*) FROM public.management_alert_settings) = 0, 'autre organisation : rien de visible');
ROLLBACK;
\echo 'Tous les tests des seuils du contrôle de gestion (SQL) sont passés.'
