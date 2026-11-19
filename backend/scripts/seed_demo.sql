-- =====================================================================
-- DONNÉES DE DÉMONSTRATION — à n'exécuter que sur un environnement de test.
-- Tout est marqué is_demo = true et préfixé « [DÉMO] » ; l'interface affiche
-- un bandeau « Données de démonstration » pour ces organisations.
--
-- Usage : psql "$DATABASE_URL" -v demo_user="'<uuid d'un utilisateur existant>'" -f scripts/seed_demo.sql
-- Les balances de démonstration seront ajoutées avec le module d'importation (phase 3).
-- =====================================================================
\set ON_ERROR_STOP on
BEGIN;

INSERT INTO public.organizations (id, name, slug, org_type, country_code, default_currency, is_demo, created_by)
VALUES ('de000000-0000-0000-0000-000000000001', '[DÉMO] Cabinet Démonstration', 'demo-cabinet',
        'accounting_firm', 'CI', 'XOF', true, :demo_user)
ON CONFLICT (slug) DO NOTHING;

INSERT INTO public.companies (id, organization_id, name, legal_form, country_code, currency, framework_id,
                              activity_sector, is_demo, created_by)
SELECT 'de000000-0000-0000-0000-0000000000c1', 'de000000-0000-0000-0000-000000000001',
       '[DÉMO] Société Industrielle Exemple', 'SA', 'CI', 'XOF', f.id, 'Industrie agroalimentaire', true, :demo_user
  FROM public.accounting_frameworks f WHERE f.code = 'SYSCOHADA_REV'
ON CONFLICT DO NOTHING;

INSERT INTO public.companies (id, organization_id, name, legal_form, country_code, currency, framework_id,
                              activity_sector, is_demo, created_by)
SELECT 'de000000-0000-0000-0000-0000000000c2', 'de000000-0000-0000-0000-000000000001',
       '[DÉMO] Association Exemple', 'Association', 'SN', 'XOF', f.id, 'Santé communautaire', true, :demo_user
  FROM public.accounting_frameworks f WHERE f.code = 'SYSCEBNL'
ON CONFLICT DO NOTHING;

INSERT INTO public.fiscal_years (organization_id, company_id, label, start_date, end_date, created_by)
SELECT 'de000000-0000-0000-0000-000000000001', c.id, y::text, make_date(y, 1, 1), make_date(y, 12, 31), :demo_user
  FROM unnest(ARRAY['de000000-0000-0000-0000-0000000000c1','de000000-0000-0000-0000-0000000000c2']::uuid[]) AS c(id),
       generate_series(2023, 2025) AS y
ON CONFLICT DO NOTHING;

COMMIT;
