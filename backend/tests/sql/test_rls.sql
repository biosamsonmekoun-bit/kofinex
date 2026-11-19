-- =====================================================================
-- Tests d'isolation multi-tenant et des gardes métier.
-- Exécution :  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/sql/test_rls.sql
-- (base locale avec sql/local/00_supabase_shim.sql + migrations appliquées)
-- Tout est exécuté dans une transaction annulée à la fin.
-- =====================================================================
\set QUIET on
BEGIN;

CREATE OR REPLACE FUNCTION pg_temp.ok(cond boolean, label text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
  IF cond IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'ÉCHEC : %', label;
  END IF;
  RAISE NOTICE 'ok - %', label;
END $$;

-- Exécute une requête qui DOIT échouer.
CREATE OR REPLACE FUNCTION pg_temp.fails(q text, label text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
  BEGIN
    EXECUTE q;
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'ok - % (refusé : %)', label, SQLERRM;
    RETURN;
  END;
  RAISE EXCEPTION 'ÉCHEC : % (aucune erreur levée)', label;
END $$;

CREATE OR REPLACE FUNCTION pg_temp.act_as(uid uuid) RETURNS void
LANGUAGE sql AS $$
  SELECT set_config('request.jwt.claims', json_build_object('sub', uid, 'role', 'authenticated')::text, true);
$$;

GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA pg_temp TO authenticated;

-- ---------------------------------------------------------------- données
INSERT INTO auth.users (id, email) VALUES
  ('a0000000-0000-0000-0000-00000000000a', 'alice@cabinet-a.test'),   -- owner org A
  ('b0000000-0000-0000-0000-00000000000b', 'bob@cabinet-b.test'),     -- owner org B
  ('c0000000-0000-0000-0000-00000000000c', 'carla@cabinet-a.test'),   -- member org A, comptable de A1
  ('d0000000-0000-0000-0000-00000000000d', 'dan@cabinet-a.test'),     -- admin org A
  ('e0000000-0000-0000-0000-00000000000e', 'eve@cabinet-a.test');     -- member org A sans entreprise

INSERT INTO public.accounting_frameworks (id, code, name) VALUES
  ('f0000000-0000-0000-0000-000000000001', 'TEST_LUCRATIF', 'Référentiel de test 1'),
  ('f0000000-0000-0000-0000-000000000002', 'TEST_BNL', 'Référentiel de test 2');

SET LOCAL ROLE authenticated;

-- ------------------------------------------------------- Alice crée org A
SELECT pg_temp.act_as('a0000000-0000-0000-0000-00000000000a');
WITH ins AS (
  INSERT INTO public.organizations (id, name, slug, created_by)
  VALUES ('10000000-0000-0000-0000-00000000000a', 'Cabinet A', 'cabinet-a', 'a0000000-0000-0000-0000-00000000000a')
  RETURNING id)
SELECT pg_temp.ok((SELECT count(*) FROM ins) = 1, 'création d''organisation avec RETURNING');
SELECT pg_temp.ok((SELECT role FROM public.organization_members
                    WHERE organization_id = '10000000-0000-0000-0000-00000000000a'
                      AND user_id = 'a0000000-0000-0000-0000-00000000000a') = 'owner',
                  'le créateur devient owner');

SELECT pg_temp.fails($q$INSERT INTO public.organizations (name, slug, created_by)
  VALUES ('Usurpée', 'usurpee', 'b0000000-0000-0000-0000-00000000000b')$q$,
  'impossible de créer une organisation au nom d''un autre');

SELECT pg_temp.fails($q$INSERT INTO public.organizations (name, slug, created_by, is_demo)
  VALUES ('Démo', 'demo-x', 'a0000000-0000-0000-0000-00000000000a', true)$q$,
  'un utilisateur ne peut pas créer une organisation de démonstration');

INSERT INTO public.organization_members (organization_id, user_id, role) VALUES
  ('10000000-0000-0000-0000-00000000000a', 'c0000000-0000-0000-0000-00000000000c', 'member'),
  ('10000000-0000-0000-0000-00000000000a', 'd0000000-0000-0000-0000-00000000000d', 'admin'),
  ('10000000-0000-0000-0000-00000000000a', 'e0000000-0000-0000-0000-00000000000e', 'member');

-- RETURNING (comme l'ORM) : la policy SELECT est évaluée sur la ligne tout juste insérée
WITH ins AS (
  INSERT INTO public.companies (id, organization_id, name, framework_id, created_by) VALUES
    ('20000000-0000-0000-0000-0000000000a1', '10000000-0000-0000-0000-00000000000a', 'Client A1',
     'f0000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-00000000000a'),
    ('20000000-0000-0000-0000-0000000000a2', '10000000-0000-0000-0000-00000000000a', 'Association A2',
     'f0000000-0000-0000-0000-000000000002', 'a0000000-0000-0000-0000-00000000000a')
  RETURNING id)
SELECT pg_temp.ok((SELECT count(*) FROM ins) = 2, 'création d''entreprises avec RETURNING');

WITH ins AS (
  INSERT INTO public.company_members (organization_id, company_id, user_id, role) VALUES
    ('10000000-0000-0000-0000-00000000000a', '20000000-0000-0000-0000-0000000000a1',
     'c0000000-0000-0000-0000-00000000000c', 'accountant')
  RETURNING id)
SELECT pg_temp.ok((SELECT count(*) FROM ins) = 1, 'attribution d''entreprise avec RETURNING');

INSERT INTO public.fiscal_years (id, organization_id, company_id, label, start_date, end_date, created_by) VALUES
  ('30000000-0000-0000-0000-0000000000a1', '10000000-0000-0000-0000-00000000000a',
   '20000000-0000-0000-0000-0000000000a1', '2025', '2025-01-01', '2025-12-31',
   'a0000000-0000-0000-0000-00000000000a');

-- ------------------------------------------------------- Bob crée org B
SELECT pg_temp.act_as('b0000000-0000-0000-0000-00000000000b');
INSERT INTO public.organizations (id, name, slug, created_by)
VALUES ('10000000-0000-0000-0000-00000000000b', 'Cabinet B', 'cabinet-b', 'b0000000-0000-0000-0000-00000000000b');
INSERT INTO public.companies (id, organization_id, name, framework_id, created_by) VALUES
  ('20000000-0000-0000-0000-0000000000b1', '10000000-0000-0000-0000-00000000000b', 'Client B1',
   'f0000000-0000-0000-0000-000000000001', 'b0000000-0000-0000-0000-00000000000b');

-- --------------------------------------------- Isolation entre tenants
SELECT pg_temp.ok((SELECT count(*) FROM public.organizations) = 1, 'Bob ne voit que son organisation');
SELECT pg_temp.ok((SELECT count(*) FROM public.companies) = 1, 'Bob ne voit que ses entreprises');
SELECT pg_temp.ok((SELECT count(*) FROM public.fiscal_years) = 0, 'Bob ne voit pas les exercices de A');
SELECT pg_temp.ok((SELECT count(*) FROM public.profiles
                    WHERE id = 'a0000000-0000-0000-0000-00000000000a') = 0,
                  'Bob ne voit pas le profil d''Alice');

SELECT pg_temp.fails($q$INSERT INTO public.companies (organization_id, name, framework_id, created_by)
  VALUES ('10000000-0000-0000-0000-00000000000a', 'Intrus', 'f0000000-0000-0000-0000-000000000001',
          'b0000000-0000-0000-0000-00000000000b')$q$,
  'Bob ne peut pas créer une entreprise dans l''organisation A');

SELECT pg_temp.fails($q$INSERT INTO public.organization_members (organization_id, user_id, role)
  VALUES ('10000000-0000-0000-0000-00000000000a', 'b0000000-0000-0000-0000-00000000000b', 'owner')$q$,
  'Bob ne peut pas s''ajouter à l''organisation A');

-- clé composite : une ligne de B ne peut pas viser une entreprise de A
SELECT pg_temp.fails($q$INSERT INTO public.fiscal_years (organization_id, company_id, label, start_date, end_date, created_by)
  VALUES ('10000000-0000-0000-0000-00000000000b', '20000000-0000-0000-0000-0000000000a1', 'X',
          '2024-01-01', '2024-12-31', 'b0000000-0000-0000-0000-00000000000b')$q$,
  'clé étrangère composite : pas de référence croisée entre tenants');

WITH changed AS (UPDATE public.companies SET name = 'Piratée' WHERE id = '20000000-0000-0000-0000-0000000000a1'
  RETURNING 1)
SELECT pg_temp.ok((SELECT count(*) FROM changed) = 0, 'Bob ne peut pas modifier une entreprise de A (0 ligne affectée)');

-- --------------------------------------------- Rôles à l'intérieur de A
SELECT pg_temp.act_as('c0000000-0000-0000-0000-00000000000c');
SELECT pg_temp.ok((SELECT count(*) FROM public.companies) = 1,
                  'Carla (member) ne voit que l''entreprise qui lui est attribuée');
SELECT pg_temp.ok((SELECT count(*) FROM public.fiscal_years) = 1, 'Carla voit l''exercice de A1');
WITH ins AS (
  INSERT INTO public.fiscal_years (organization_id, company_id, label, start_date, end_date, created_by)
  VALUES ('10000000-0000-0000-0000-00000000000a', '20000000-0000-0000-0000-0000000000a1', '2024',
          '2024-01-01', '2024-12-31', 'c0000000-0000-0000-0000-00000000000c')
  RETURNING id)
SELECT pg_temp.ok((SELECT count(*) FROM ins) = 1, 'Carla (comptable) peut créer un exercice (RETURNING)');
SELECT pg_temp.fails($q$INSERT INTO public.fiscal_years (organization_id, company_id, label, start_date, end_date, created_by)
  VALUES ('10000000-0000-0000-0000-00000000000a', '20000000-0000-0000-0000-0000000000a1', '2025-bis',
          '2025-06-01', '2026-05-31', 'c0000000-0000-0000-0000-00000000000c')$q$,
  'exercices qui se chevauchent refusés');
SELECT pg_temp.fails($q$INSERT INTO public.companies (organization_id, name, framework_id, created_by)
  VALUES ('10000000-0000-0000-0000-00000000000a', 'Nouvelle', 'f0000000-0000-0000-0000-000000000001',
          'c0000000-0000-0000-0000-00000000000c')$q$,
  'un member ne crée pas d''entreprise');
SELECT pg_temp.fails($q$UPDATE public.profiles SET is_platform_admin = true
  WHERE id = 'c0000000-0000-0000-0000-00000000000c'$q$,
  'un utilisateur ne peut pas s''octroyer le rôle administrateur plateforme');
WITH changed AS (UPDATE public.profiles SET full_name = 'Carla K.' WHERE id = 'c0000000-0000-0000-0000-00000000000c'
  RETURNING 1)
SELECT pg_temp.ok((SELECT count(*) FROM changed) > 0, 'un utilisateur modifie son nom');

SELECT pg_temp.act_as('e0000000-0000-0000-0000-00000000000e');
SELECT pg_temp.ok((SELECT count(*) FROM public.companies) = 0,
                  'Eve (member sans attribution) ne voit aucune entreprise');
SELECT pg_temp.ok((SELECT count(*) FROM public.audit_logs) = 0, 'Eve ne lit pas le journal d''audit');

SELECT pg_temp.act_as('d0000000-0000-0000-0000-00000000000d');
SELECT pg_temp.ok((SELECT count(*) FROM public.companies) = 2, 'Dan (admin) voit toutes les entreprises de A');
SELECT pg_temp.fails($q$UPDATE public.organization_members SET role = 'owner'
  WHERE user_id = 'd0000000-0000-0000-0000-00000000000d'
    AND organization_id = '10000000-0000-0000-0000-00000000000a'$q$,
  'un admin ne peut pas se promouvoir owner');
WITH changed AS (UPDATE public.organization_members SET role = 'viewer'
 WHERE user_id = 'a0000000-0000-0000-0000-00000000000a'
  RETURNING 1)
SELECT pg_temp.ok((SELECT count(*) FROM changed) = 0, 'un admin ne peut pas rétrograder l''owner');

-- --------------------------------------------- Dernier owner
SELECT pg_temp.act_as('a0000000-0000-0000-0000-00000000000a');
SELECT pg_temp.fails($q$UPDATE public.organization_members SET role = 'admin'
  WHERE user_id = 'a0000000-0000-0000-0000-00000000000a'$q$,
  'le dernier owner ne peut pas être rétrogradé');

-- --------------------------------------------- Exercice clôturé figé
INSERT INTO public.import_jobs (id, organization_id, company_id, fiscal_year_id, source_format, started_by)
VALUES ('40000000-0000-0000-0000-0000000000a1', '10000000-0000-0000-0000-00000000000a',
        '20000000-0000-0000-0000-0000000000a1', '30000000-0000-0000-0000-0000000000a1', 'xlsx',
        'a0000000-0000-0000-0000-00000000000a');
INSERT INTO public.trial_balance_entries (organization_id, company_id, fiscal_year_id, import_job_id,
                                          account_number, closing_debit)
VALUES ('10000000-0000-0000-0000-00000000000a', '20000000-0000-0000-0000-0000000000a1',
        '30000000-0000-0000-0000-0000000000a1', '40000000-0000-0000-0000-0000000000a1', '521100', 1500000.00);
SELECT pg_temp.fails($q$INSERT INTO public.trial_balance_entries (organization_id, company_id, fiscal_year_id,
    import_job_id, account_number, closing_debit)
  VALUES ('10000000-0000-0000-0000-00000000000a', '20000000-0000-0000-0000-0000000000a1',
          '30000000-0000-0000-0000-0000000000a1', '40000000-0000-0000-0000-0000000000a1', '601', -5)$q$,
  'montants négatifs refusés dans les colonnes débit/crédit');
UPDATE public.fiscal_years SET status = 'closed', closed_at = now(),
       closed_by = 'a0000000-0000-0000-0000-00000000000a'
 WHERE id = '30000000-0000-0000-0000-0000000000a1';
SELECT pg_temp.fails($q$UPDATE public.trial_balance_entries SET closing_debit = 1
  WHERE fiscal_year_id = '30000000-0000-0000-0000-0000000000a1'$q$,
  'balance d''un exercice clôturé non modifiable');

-- --------------------------------------------- Intégrations
SELECT pg_temp.fails($q$INSERT INTO public.integrations (organization_id, provider, status, created_by)
  VALUES ('10000000-0000-0000-0000-00000000000a', 'odoo', 'active', 'a0000000-0000-0000-0000-00000000000a')$q$,
  'une intégration ne peut pas être « active » sans vérification réelle');
INSERT INTO public.integrations (organization_id, provider, encrypted_credentials, created_by)
VALUES ('10000000-0000-0000-0000-00000000000a', 'odoo', 'gAAAA-chiffré', 'a0000000-0000-0000-0000-00000000000a');
SELECT pg_temp.fails($q$SELECT encrypted_credentials FROM public.integrations$q$,
  'identifiants chiffrés illisibles côté client');

-- --------------------------------------------- Audit
SELECT pg_temp.ok((SELECT count(*) FROM public.audit_logs
                    WHERE organization_id = '10000000-0000-0000-0000-00000000000a') >= 8,
                  'les modifications sont journalisées automatiquement');
SELECT pg_temp.ok((SELECT count(*) FROM public.audit_logs
                    WHERE entity_type = 'integrations' AND changes ? 'encrypted_credentials') = 0,
                  'les secrets ne sont pas copiés dans le journal');
SELECT pg_temp.fails($q$DELETE FROM public.audit_logs$q$, 'journal d''audit non effaçable (client)');

RESET ROLE;
SELECT pg_temp.fails($q$INSERT INTO public.fiscal_years (organization_id, company_id, label, start_date, end_date, created_by)
  VALUES ('10000000-0000-0000-0000-00000000000b', '20000000-0000-0000-0000-0000000000a1', 'X',
          '2019-01-01', '2019-12-31', 'b0000000-0000-0000-0000-00000000000b')$q$,
  'clé composite : même sans RLS (superutilisateur), une référence croisée est impossible');
SELECT pg_temp.fails($q$UPDATE public.audit_logs SET action = 'x'$q$,
  'journal d''audit non modifiable même par le propriétaire');

-- --------------------------------------------- Suppression d'organisation
SET LOCAL ROLE authenticated;
SELECT pg_temp.act_as('b0000000-0000-0000-0000-00000000000b');
WITH changed AS (DELETE FROM public.organizations WHERE id = '10000000-0000-0000-0000-00000000000a'
  RETURNING 1)
SELECT pg_temp.ok((SELECT count(*) FROM changed) = 0, 'Bob ne peut pas supprimer l''organisation A');
WITH changed AS (DELETE FROM public.organizations WHERE id = '10000000-0000-0000-0000-00000000000b'
  RETURNING 1)
SELECT pg_temp.ok((SELECT count(*) FROM changed) > 0, 'l''owner supprime son organisation (cascade OK, audit conservé)');

RESET ROLE;
SELECT pg_temp.ok((SELECT count(*) FROM public.audit_logs WHERE entity_type = 'organizations'
                    AND action = 'DELETE') = 1, 'trace de suppression conservée');

ROLLBACK;
\echo 'Tous les tests RLS sont passés.'
