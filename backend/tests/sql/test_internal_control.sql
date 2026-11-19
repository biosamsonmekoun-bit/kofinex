-- =====================================================================
-- Tests migration 0011 : contrôle interne (domaines, registre partagé, contrôles, matrice, rattachements
-- aux référentiels, exécutions supervisées, tests préparés/revus, synthèse, évaluations figées,
-- déficiences et clôture, prise en compte par l'audit financier, gel, isolation, droits).
-- Les échelles et référentiels utilisés sont FICTIFS (données de test).
-- =====================================================================
\set QUIET on
BEGIN;
CREATE OR REPLACE FUNCTION pg_temp.ok(cond boolean, label text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  IF cond IS DISTINCT FROM true THEN RAISE EXCEPTION 'ÉCHEC : %', label; END IF;
  RAISE NOTICE 'ok - %', label;
END $$;
CREATE OR REPLACE FUNCTION pg_temp.fails(q text, label text, pattern text DEFAULT NULL) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  BEGIN EXECUTE q;
  EXCEPTION WHEN OTHERS THEN
    IF pattern IS NOT NULL AND SQLERRM NOT ILIKE '%' || pattern || '%' THEN
      RAISE EXCEPTION 'ÉCHEC : % (erreur inattendue : %)', label, SQLERRM;
    END IF;
    RAISE NOTICE 'ok - % (refusé : %)', label, SQLERRM; RETURN;
  END;
  RAISE EXCEPTION 'ÉCHEC : % (aucune erreur levée)', label;
END $$;
CREATE OR REPLACE FUNCTION pg_temp.act_as(uid uuid) RETURNS void LANGUAGE sql AS $$
  SELECT set_config('request.jwt.claims', json_build_object('sub', uid, 'role', 'authenticated')::text, true);
$$;
CREATE OR REPLACE FUNCTION pg_temp.n(q text) RETURNS bigint LANGUAGE plpgsql AS $$
DECLARE r bigint; BEGIN EXECUTE q INTO r; RETURN r; END $$;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA pg_temp TO authenticated;

-- alice (propriétaire) ; cara (responsable du contrôle interne) ; dom (responsable du domaine Achats) ; eric (exécutant) ;
-- sue (superviseur) ; olga (observatrice) ; mission d'évaluation : mona (manager), paul (associé), ines (chef de mission),
-- sam (auditeur), aude (auditée) ; fred (chef de mission d'audit financier) ; bob (autre organisation)
INSERT INTO auth.users (id, email) VALUES
  ('e0000000-0000-0000-0000-00000000000a', 'alice@ic.test'), ('e1000000-0000-0000-0000-000000000001', 'cara@ic.test'),
  ('e2000000-0000-0000-0000-000000000002', 'dom@ic.test'), ('e3000000-0000-0000-0000-000000000003', 'eric@ic.test'),
  ('e4000000-0000-0000-0000-000000000004', 'sue@ic.test'), ('e5000000-0000-0000-0000-000000000005', 'mona@ic.test'),
  ('e6000000-0000-0000-0000-000000000006', 'paul@ic.test'), ('e7000000-0000-0000-0000-000000000007', 'sam@ic.test'),
  ('e8000000-0000-0000-0000-000000000008', 'aude@ic.test'), ('e9000000-0000-0000-0000-000000000009', 'fred@ic.test'),
  ('ea000000-0000-0000-0000-00000000000c', 'olga@ic.test'), ('ec000000-0000-0000-0000-00000000000d', 'ines@ic.test'),
  ('eb000000-0000-0000-0000-00000000000b', 'bob@ix.test');
INSERT INTO public.accounting_frameworks (id, code, name) VALUES ('f0000000-0000-0000-0000-0000000000fa', 'TEST_FW10', 'Test');

SET LOCAL session_replication_role = replica;
INSERT INTO public.profiles (id, email) SELECT id, email FROM auth.users WHERE email LIKE '%@i_.test' ON CONFLICT DO NOTHING;
INSERT INTO public.organizations (id, name, slug, created_by) VALUES
  ('1a000000-0000-0000-0000-00000000000a', 'Groupe CI', 'groupe-ci', 'e0000000-0000-0000-0000-00000000000a'),
  ('1a000000-0000-0000-0000-00000000000b', 'Autre CI', 'autre-ci', 'eb000000-0000-0000-0000-00000000000b');
INSERT INTO public.organization_members (organization_id, user_id, role) VALUES
  ('1a000000-0000-0000-0000-00000000000a', 'e0000000-0000-0000-0000-00000000000a', 'owner'),
  ('1a000000-0000-0000-0000-00000000000b', 'eb000000-0000-0000-0000-00000000000b', 'owner');
INSERT INTO public.organization_members (organization_id, user_id, role)
SELECT '1a000000-0000-0000-0000-00000000000a', u, 'member' FROM unnest(ARRAY[
  'e1000000-0000-0000-0000-000000000001','e2000000-0000-0000-0000-000000000002','e3000000-0000-0000-0000-000000000003',
  'e4000000-0000-0000-0000-000000000004','e5000000-0000-0000-0000-000000000005','e6000000-0000-0000-0000-000000000006',
  'e7000000-0000-0000-0000-000000000007','e8000000-0000-0000-0000-000000000008','e9000000-0000-0000-0000-000000000009',
  'ea000000-0000-0000-0000-00000000000c','ec000000-0000-0000-0000-00000000000d']::uuid[]) u;
INSERT INTO public.companies (id, organization_id, name, framework_id, created_by) VALUES
  ('2a000000-0000-0000-0000-00000000000a', '1a000000-0000-0000-0000-00000000000a', 'Filiale CI',
   'f0000000-0000-0000-0000-0000000000fa', 'e0000000-0000-0000-0000-00000000000a');
INSERT INTO public.fiscal_years (id, organization_id, company_id, label, start_date, end_date, created_by) VALUES
  ('7a000000-0000-0000-0000-00000000000a', '1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
   '2026', '2026-01-01', '2026-12-31', 'e0000000-0000-0000-0000-00000000000a');
INSERT INTO public.methodology_versions (id, organization_id, kind, name, version_label, source_reference, status, published_at,
                                         framework_category, issuing_body, created_by) VALUES
  ('3a000000-0000-0000-0000-00000000000a', '1a000000-0000-0000-0000-00000000000a', 'internal_control', 'Cadre CI test', 'v1',
   'Cadre FICTIF de test', 'published', now(), 'ic_framework', 'Organisme fictif', 'e0000000-0000-0000-0000-00000000000a'),
  ('3a000000-0000-0000-0000-00000000000b', '1a000000-0000-0000-0000-00000000000a', 'internal_control', 'Exigences test', 'v1',
   'Exigences FICTIVES de test', 'published', now(), 'legal_requirement', NULL, 'e0000000-0000-0000-0000-00000000000a'),
  ('3a000000-0000-0000-0000-00000000000c', '1a000000-0000-0000-0000-00000000000a', 'internal_control', 'Brouillon test', 'v0',
   'Brouillon FICTIF', 'draft', NULL, 'internal_methodology', NULL, 'e0000000-0000-0000-0000-00000000000a');
INSERT INTO public.methodology_items (id, version_id, item_type, code, label, parent_code, content) VALUES
  ('3b000000-0000-0000-0000-000000000001', '3a000000-0000-0000-0000-00000000000a', 'ic_component', 'CMP1', 'Composante test', NULL, '{}'),
  ('3b000000-0000-0000-0000-000000000002', '3a000000-0000-0000-0000-00000000000a', 'ic_principle', 'PR1', 'Principe test', 'CMP1', '{}'),
  ('3b000000-0000-0000-0000-000000000003', '3a000000-0000-0000-0000-00000000000b', 'ic_requirement', 'EX1', 'Exigence test', NULL, '{}'),
  ('3b000000-0000-0000-0000-000000000004', '3a000000-0000-0000-0000-00000000000c', 'ic_principle', 'BR1', 'Principe brouillon', NULL, '{}'),
  ('3b000000-0000-0000-0000-000000000005', '3a000000-0000-0000-0000-00000000000a', 'risk_scale', 'GRILLE', 'Grille test', NULL,
   '{"likelihood":[{"score":1,"label":"Faible"},{"score":2,"label":"Moyenne"},{"score":3,"label":"Forte"}],
     "impact":[{"score":1,"label":"Faible"},{"score":2,"label":"Moyen"},{"score":3,"label":"Fort"}]}'),
  ('3b000000-0000-0000-0000-000000000006', '3a000000-0000-0000-0000-00000000000a', 'control_level_scale', 'MAITRISE',
   'Niveau de maîtrise (test)', NULL,
   '{"levels":[{"code":"M1","label":"Maîtrisé (test)"},{"code":"M2","label":"Partiel (test)"},{"code":"M3","label":"Non maîtrisé (test)"}]}'),
  ('3b000000-0000-0000-0000-000000000007', '3a000000-0000-0000-0000-00000000000a', 'deficiency_scale', 'DEF', 'Déficiences (test)', NULL,
   '{"levels":[{"code":"D1","label":"Majeure (test)","rank":1},{"code":"D2","label":"Mineure (test)","rank":2}]}'),
  ('3b000000-0000-0000-0000-000000000008', '3a000000-0000-0000-0000-00000000000a', 'finding_scale', 'CONST', 'Constats (test)', NULL,
   '{"levels":[{"code":"N1","label":"Majeur (test)","rank":1}]}');
INSERT INTO public.engagements (id, organization_id, company_id, engagement_type, reference, name, methodology_version_id,
                                period_start, period_end, fiscal_year_id, created_by) VALUES
  ('6a000000-0000-0000-0000-00000000000a', '1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
   'ic_assessment', 'CI-2026', 'Évaluation du contrôle interne 2026', '3a000000-0000-0000-0000-00000000000a',
   '2026-01-01', '2026-06-30', NULL, 'e5000000-0000-0000-0000-000000000005'),
  ('6a000000-0000-0000-0000-00000000000b', '1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
   'statutory_audit', 'CAC-2026', 'Audit légal 2026', NULL, NULL, NULL, '7a000000-0000-0000-0000-00000000000a',
   'e9000000-0000-0000-0000-000000000009');
INSERT INTO public.engagement_members (organization_id, engagement_id, user_id, role, independence_confirmed_at)
SELECT '1a000000-0000-0000-0000-00000000000a', e, u, r, CASE WHEN r = 'auditee' THEN NULL ELSE now() END FROM (VALUES
  ('6a000000-0000-0000-0000-00000000000a'::uuid, 'e5000000-0000-0000-0000-000000000005'::uuid, 'manager'),
  ('6a000000-0000-0000-0000-00000000000a'::uuid, 'e6000000-0000-0000-0000-000000000006'::uuid, 'partner'),
  ('6a000000-0000-0000-0000-00000000000a'::uuid, 'ec000000-0000-0000-0000-00000000000d'::uuid, 'in_charge'),
  ('6a000000-0000-0000-0000-00000000000a'::uuid, 'e7000000-0000-0000-0000-000000000007'::uuid, 'staff'),
  ('6a000000-0000-0000-0000-00000000000a'::uuid, 'e8000000-0000-0000-0000-000000000008'::uuid, 'auditee'),
  ('6a000000-0000-0000-0000-00000000000b'::uuid, 'e9000000-0000-0000-0000-000000000009'::uuid, 'in_charge')) t(e, u, r);
INSERT INTO public.ic_members (organization_id, company_id, user_id, role) VALUES
  ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', 'e1000000-0000-0000-0000-000000000001', 'ic_manager'),
  ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', 'ea000000-0000-0000-0000-00000000000c', 'observer');
SET LOCAL session_replication_role = origin;

SET LOCAL ROLE authenticated;

-- ------------------------------------------------------- domaines et rôles
SELECT pg_temp.act_as('e2000000-0000-0000-0000-000000000002');
SELECT pg_temp.fails($q$INSERT INTO public.ic_domains (organization_id, company_id, code, name)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', 'X', 'X')$q$,
  'sans rôle : création d''un domaine refusée');
SELECT pg_temp.act_as('e1000000-0000-0000-0000-000000000001');
INSERT INTO public.ic_domains (id, organization_id, company_id, code, name, category, template_code, cycle_code) VALUES
  ('4a000000-0000-0000-0000-000000000001', '1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
   'ACH', 'Achats et fournisseurs', 'accounting_financial', 'purchases', 'ACHATS'),
  ('4a000000-0000-0000-0000-000000000002', '1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
   'VEN', 'Ventes et clients', 'accounting_financial', 'sales', NULL);
INSERT INTO public.ic_members (organization_id, company_id, user_id, role, domain_id) VALUES
  ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', 'e2000000-0000-0000-0000-000000000002',
   'domain_owner', '4a000000-0000-0000-0000-000000000001'),
  ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', 'e3000000-0000-0000-0000-000000000003',
   'control_performer', '4a000000-0000-0000-0000-000000000001'),
  ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', 'e4000000-0000-0000-0000-000000000004',
   'supervisor', '4a000000-0000-0000-0000-000000000001');
SELECT pg_temp.ok((SELECT count(*) FROM public.ic_domains) = 2, 'responsable du contrôle interne : domaines créés');
SELECT pg_temp.fails($q$INSERT INTO public.ic_members (organization_id, company_id, user_id, role)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', 'e2000000-0000-0000-0000-000000000002',
          'domain_owner')$q$, 'responsable de domaine sans domaine', 'check');
SELECT pg_temp.act_as('e2000000-0000-0000-0000-000000000002');
SELECT pg_temp.fails($q$INSERT INTO public.ic_members (organization_id, company_id, user_id, role)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', 'e2000000-0000-0000-0000-000000000002',
          'ic_manager')$q$, 'responsable de domaine : ne s''attribue pas de rôle');
SELECT pg_temp.act_as('eb000000-0000-0000-0000-00000000000b');
SELECT pg_temp.ok((SELECT count(*) FROM public.ic_domains) = 0, 'autre organisation : aucun domaine visible');
SELECT pg_temp.act_as('e3000000-0000-0000-0000-000000000003');
SELECT pg_temp.ok((SELECT count(*) FROM public.companies WHERE id = '2a000000-0000-0000-0000-00000000000a') = 1,
  'exécutant (rôle de contrôle interne) : entité visible');

-- ------------------------------------------------------- registre partagé : processus et risques
SELECT pg_temp.act_as('e2000000-0000-0000-0000-000000000002');
INSERT INTO public.processes (id, organization_id, company_id, domain_id, code, name) VALUES
  ('4b000000-0000-0000-0000-000000000001', '1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
   '4a000000-0000-0000-0000-000000000001', 'ACH-CMD', 'Commandes');
INSERT INTO public.processes (id, organization_id, company_id, parent_id, code, name) VALUES
  ('4b000000-0000-0000-0000-000000000002', '1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
   '4b000000-0000-0000-0000-000000000001', 'ACH-CMD-VAL', 'Validation des commandes');
SELECT pg_temp.ok((SELECT domain_id FROM public.processes WHERE id = '4b000000-0000-0000-0000-000000000002')
  = '4a000000-0000-0000-0000-000000000001', 'sous-processus : domaine hérité du parent');
SELECT pg_temp.fails($q$INSERT INTO public.processes (organization_id, company_id, domain_id, code, name) VALUES
  ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', '4a000000-0000-0000-0000-000000000002',
   'VEN-1', 'Facturation')$q$, 'responsable des achats : processus des ventes refusé');
INSERT INTO public.control_objectives (id, organization_id, company_id, domain_id, process_id, code, statement) VALUES
  ('4c000000-0000-0000-0000-000000000001', '1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
   '4a000000-0000-0000-0000-000000000001', '4b000000-0000-0000-0000-000000000001', 'OBJ-1', 'Seules les commandes autorisées sont passées');
SELECT pg_temp.fails($q$INSERT INTO public.risks (organization_id, company_id, process_id, code, title, scale_version_id,
  inherent_likelihood, inherent_impact) VALUES ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
  '4b000000-0000-0000-0000-000000000001', 'R-X', 'Hors grille', '3a000000-0000-0000-0000-00000000000a', 4, 1)$q$,
  'cotation hors de la grille versionnée', 'grille');
SELECT pg_temp.fails($q$INSERT INTO public.risks (organization_id, company_id, process_id, code, title, inherent_likelihood,
  inherent_impact) VALUES ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
  '4b000000-0000-0000-0000-000000000001', 'R-X', 'Sans grille', 2, 2)$q$, 'cotation sans version de méthodologie', 'méthodologie');
SELECT pg_temp.fails($q$INSERT INTO public.risks (organization_id, company_id, process_id, code, title, scale_version_id,
  control_level_code) VALUES ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
  '4b000000-0000-0000-0000-000000000001', 'R-X', 'Niveau inconnu', '3a000000-0000-0000-0000-00000000000a', 'M9')$q$,
  'niveau de maîtrise absent de l''échelle', 'maîtrise');
INSERT INTO public.risks (id, organization_id, company_id, process_id, objective_id, code, title, category, causes, consequences,
                          owner_name, scale_version_id, inherent_likelihood, inherent_impact, residual_likelihood, residual_impact)
VALUES ('5a000000-0000-0000-0000-000000000001', '1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
        '4b000000-0000-0000-0000-000000000001', '4c000000-0000-0000-0000-000000000001', 'R-ACH-1', 'Commande non autorisée',
        'Opérationnel', 'Absence de délégation formalisée', 'Engagements non maîtrisés', 'Directeur des achats',
        '3a000000-0000-0000-0000-00000000000a', 3, 3, 2, 3),
       ('5a000000-0000-0000-0000-000000000002', '1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
        '4b000000-0000-0000-0000-000000000001', NULL, 'R-ACH-2', 'Fournisseur fictif', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
SELECT pg_temp.ok((SELECT domain_id FROM public.risks WHERE code = 'R-ACH-1') = '4a000000-0000-0000-0000-000000000001',
  'risque : domaine hérité du processus');
UPDATE public.risks SET control_level_code = 'M2' WHERE code = 'R-ACH-1';
SELECT pg_temp.ok((SELECT count(*) FROM public.risk_rating_history WHERE risk_id = '5a000000-0000-0000-0000-000000000001'
                    AND control_level_code = 'M2') = 1, 'niveau de maîtrise historisé');

-- ------------------------------------------------------- catalogue des contrôles et matrice
SELECT pg_temp.fails($q$INSERT INTO public.controls (organization_id, company_id, process_id, code, title, owner_name)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', '4b000000-0000-0000-0000-000000000001',
          'C-X', 'Existant non caractérisé', 'Chef comptable')$q$, 'contrôle existant sans fréquence, nature ni mode', 'check');
SELECT pg_temp.fails($q$INSERT INTO public.controls (organization_id, company_id, process_id, code, title, owner_name, existence)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', '4b000000-0000-0000-0000-000000000001',
          'C-X', 'Sans responsable', ' ', 'expected')$q$, 'contrôle sans responsable identifiable', 'check');
INSERT INTO public.controls (id, organization_id, company_id, process_id, objective_id, code, title, owner_name, performer_name,
                             performer_user_id, supervisor_user_id, frequency, nature, automation, timing, is_key,
                             expected_evidence, procedure_text, success_criteria)
VALUES ('5b000000-0000-0000-0000-000000000001', '1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
        '4b000000-0000-0000-0000-000000000001', '4c000000-0000-0000-0000-000000000001', 'C-ACH-1',
        'Approbation des commandes selon la délégation', 'Directeur des achats', 'Eric', 'e3000000-0000-0000-0000-000000000003',
        'e4000000-0000-0000-0000-000000000004', 'monthly', 'preventive', 'manual', 'permanent', true,
        'Bons de commande signés', 'Revue mensuelle des commandes', 'Toute commande signée par un délégataire'),
       ('5b000000-0000-0000-0000-000000000003', '1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
        '4b000000-0000-0000-0000-000000000001', NULL, 'C-ACH-3', 'Rapprochement commande-réception-facture', 'Chef comptable',
        NULL, NULL, NULL, 'on_occurrence', 'detective', 'semi_automated', 'permanent', false, NULL, NULL, NULL);
INSERT INTO public.controls (id, organization_id, company_id, domain_id, code, title, owner_name, existence) VALUES
  ('5b000000-0000-0000-0000-000000000002', '1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
   '4a000000-0000-0000-0000-000000000001', 'C-ACH-2', 'Revue du fichier fournisseurs', 'Directeur financier', 'expected');
SELECT pg_temp.fails($q$INSERT INTO public.controls (organization_id, company_id, domain_id, code, title, owner_name, existence)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', '4a000000-0000-0000-0000-000000000002',
          'C-VEN-1', 'Contrôle des avoirs', 'DAF', 'expected')$q$, 'responsable des achats : contrôle des ventes refusé');
INSERT INTO public.control_risks (organization_id, company_id, control_id, risk_id, coverage) VALUES
  ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', '5b000000-0000-0000-0000-000000000001',
   '5a000000-0000-0000-0000-000000000001', 'full'),
  ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', '5b000000-0000-0000-0000-000000000003',
   '5a000000-0000-0000-0000-000000000001', 'partial'),
  ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', '5b000000-0000-0000-0000-000000000002',
   '5a000000-0000-0000-0000-000000000002', 'full');
SELECT pg_temp.ok((SELECT count(*) FROM public.control_risks WHERE risk_id = '5a000000-0000-0000-0000-000000000001') = 2,
  'matrice : un risque couvert par plusieurs contrôles');
UPDATE public.controls SET description = 'Délégation mise à jour' WHERE code = 'C-ACH-1';
SELECT pg_temp.ok((SELECT version FROM public.controls WHERE code = 'C-ACH-1') = 2, 'contrôle : version incrémentée');
SELECT pg_temp.ok((SELECT count(*) FROM public.ic_history WHERE object_id = '5b000000-0000-0000-0000-000000000001'
                    AND action = 'update' AND before ->> 'description' IS NULL) = 1, 'contrôle : modification historisée');
SELECT pg_temp.fails($q$INSERT INTO public.ic_framework_links (organization_id, company_id, object_type, object_id, item_id)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', 'control',
          '5b000000-0000-0000-0000-000000000001', '3b000000-0000-0000-0000-000000000004')$q$,
  'rattachement à un référentiel non publié', 'publiée');
INSERT INTO public.ic_framework_links (organization_id, company_id, object_type, object_id, item_id) VALUES
  ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', 'control', '5b000000-0000-0000-0000-000000000001',
   '3b000000-0000-0000-0000-000000000002'),
  ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', 'control', '5b000000-0000-0000-0000-000000000001',
   '3b000000-0000-0000-0000-000000000003');
SELECT pg_temp.ok((SELECT count(*) FROM public.ic_framework_links WHERE object_id = '5b000000-0000-0000-0000-000000000001') = 2,
  'contrôle rattaché à deux référentiels');
SELECT pg_temp.act_as('ea000000-0000-0000-0000-00000000000c');
SELECT pg_temp.ok((SELECT count(*) FROM public.controls) = 3, 'observatrice : catalogue visible');
SELECT pg_temp.ok(pg_temp.n($q$WITH u AS (UPDATE public.controls SET title = 'x' RETURNING 1) SELECT count(*) FROM u$q$) = 0,
  'observatrice : aucune modification possible');
SELECT pg_temp.act_as('e0000000-0000-0000-0000-00000000000a');
SELECT pg_temp.fails($q$INSERT INTO public.framework_mappings (organization_id, source_item_id, target_item_id, relation, rationale, created_by)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '3b000000-0000-0000-0000-000000000001', '3b000000-0000-0000-0000-000000000002',
          'related', 'même version', 'e0000000-0000-0000-0000-00000000000a')$q$, 'correspondance dans une même version', 'différents');
INSERT INTO public.framework_mappings (organization_id, source_item_id, target_item_id, relation, rationale, created_by)
VALUES ('1a000000-0000-0000-0000-00000000000a', '3b000000-0000-0000-0000-000000000002', '3b000000-0000-0000-0000-000000000003',
        'partial', 'Rapprochement déclaré par l''organisation (test)', 'e0000000-0000-0000-0000-00000000000a');
SELECT pg_temp.ok((SELECT count(*) FROM public.framework_mappings) = 1, 'correspondance entre référentiels déclarée');

-- ------------------------------------------------------- exécutions supervisées
SELECT pg_temp.act_as('e3000000-0000-0000-0000-000000000003');
SELECT pg_temp.fails($q$INSERT INTO public.control_executions (organization_id, company_id, control_id, occurrence_label,
  occurrence_date, outcome, performed_by) VALUES ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
  '5b000000-0000-0000-0000-000000000001', 'Janvier', '2026-01-31', 'performed', 'e4000000-0000-0000-0000-000000000004')$q$,
  'exécution au nom d''un autre');
INSERT INTO public.control_executions (id, organization_id, company_id, control_id, occurrence_label, occurrence_date, outcome,
                                       performed_by) VALUES
  ('5c000000-0000-0000-0000-000000000001', '1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
   '5b000000-0000-0000-0000-000000000001', 'Revue janvier', '2026-01-31', 'performed', 'e3000000-0000-0000-0000-000000000003'),
  ('5c000000-0000-0000-0000-000000000002', '1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
   '5b000000-0000-0000-0000-000000000001', 'Revue février', '2026-02-28', 'performed', 'e3000000-0000-0000-0000-000000000003'),
  ('5c000000-0000-0000-0000-000000000003', '1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
   '5b000000-0000-0000-0000-000000000001', 'Revue décembre 2025', '2025-12-31', 'performed', 'e3000000-0000-0000-0000-000000000003');
SELECT pg_temp.fails($q$UPDATE public.control_executions SET supervision_status = 'approved',
  supervised_by = 'e3000000-0000-0000-0000-000000000003' WHERE id = '5c000000-0000-0000-0000-000000000001'$q$,
  'exécutant : ne supervise pas sa propre exécution', 'autre personne');
SELECT pg_temp.act_as('e4000000-0000-0000-0000-000000000004');
UPDATE public.control_executions SET supervision_status = 'approved', supervised_by = 'e4000000-0000-0000-0000-000000000004'
 WHERE id IN ('5c000000-0000-0000-0000-000000000001', '5c000000-0000-0000-0000-000000000002');
SELECT pg_temp.ok((SELECT count(*) FROM public.control_executions WHERE supervision_status = 'approved') = 2,
  'superviseur : exécutions approuvées');
SELECT pg_temp.fails($q$UPDATE public.control_executions SET comment = 'modifié' WHERE id = '5c000000-0000-0000-0000-000000000001'$q$,
  'exécution supervisée : figée', 'figée');
SELECT pg_temp.fails($q$DELETE FROM public.control_executions WHERE id = '5c000000-0000-0000-0000-000000000003'$q$,
  'exécution : jamais supprimée (aucun droit de suppression)');

-- ------------------------------------------------------- tests de contrôles
SELECT pg_temp.act_as('e7000000-0000-0000-0000-000000000007');
SELECT pg_temp.fails($q$INSERT INTO public.control_tests (organization_id, engagement_id, company_id, control_id, reference, test_type,
  test_methods, test_procedure, status, created_by) VALUES ('1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a',
  '2a000000-0000-0000-0000-00000000000a', '5b000000-0000-0000-0000-000000000001', 'T-X', 'operating', ARRAY['inspection'], 'x',
  'prepared', 'e7000000-0000-0000-0000-000000000007')$q$, 'test créé directement « préparé »', 'planifié');
SELECT pg_temp.fails($q$INSERT INTO public.control_tests (organization_id, engagement_id, company_id, control_id, reference, test_type,
  test_methods, test_procedure, sample_size, created_by) VALUES ('1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a',
  '2a000000-0000-0000-0000-00000000000a', '5b000000-0000-0000-0000-000000000001', 'T-X', 'operating', ARRAY['inspection'], 'x', 2,
  'e7000000-0000-0000-0000-000000000007')$q$, 'taille d''échantillon sans fondement indiqué', 'check');
INSERT INTO public.control_tests (id, organization_id, engagement_id, company_id, control_id, risk_id, reference, test_type,
                                  test_methods, test_procedure, period_start, period_end, population_source, selection_method,
                                  sample_size, sample_size_basis, tolerable_exceptions, acceptance_criteria, created_by) VALUES
  ('5d000000-0000-0000-0000-000000000001', '1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a',
   '2a000000-0000-0000-0000-00000000000a', '5b000000-0000-0000-0000-000000000001', '5a000000-0000-0000-0000-000000000001',
   'T-OP-1', 'operating', ARRAY['inspection','reperformance'], 'Inspecter les revues mensuelles et leurs bons signés',
   '2026-01-01', '2026-06-30', 'executions', 'all', 2, 'Taille fixée par la méthodologie du cabinet (test)', 0,
   'Aucune exception', 'e7000000-0000-0000-0000-000000000007'),
  ('5d000000-0000-0000-0000-000000000002', '1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a',
   '2a000000-0000-0000-0000-00000000000a', '5b000000-0000-0000-0000-000000000001', NULL, 'T-CO-1', 'design',
   ARRAY['inquiry','document_review'], 'Examiner la délégation et la procédure', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
   'e7000000-0000-0000-0000-000000000007'),
  ('5d000000-0000-0000-0000-000000000003', '1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a',
   '2a000000-0000-0000-0000-00000000000a', '5b000000-0000-0000-0000-000000000003', NULL, 'T-OP-3', 'operating',
   ARRAY['reconciliation'], 'Rapprocher commandes, réceptions et factures', '2026-01-01', '2026-06-30', 'manual', 'judgmental',
   NULL, NULL, 0, 'Aucune exception', 'e7000000-0000-0000-0000-000000000007'),
  ('5d000000-0000-0000-0000-000000000004', '1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a',
   '2a000000-0000-0000-0000-00000000000a', '5b000000-0000-0000-0000-000000000002', NULL, 'T-NA', 'design', ARRAY['inquiry'],
   'Examen', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'e7000000-0000-0000-0000-000000000007');
SELECT pg_temp.fails($q$INSERT INTO public.control_test_items (organization_id, engagement_id, test_id, item_ref, execution_id)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a', '5d000000-0000-0000-0000-000000000001',
          'DEC', '5c000000-0000-0000-0000-000000000003')$q$, 'élément : exécution hors de la période testée', 'période');
INSERT INTO public.control_test_items (id, organization_id, engagement_id, test_id, item_ref, execution_id, selection_order) VALUES
  ('5e000000-0000-0000-0000-000000000001', '1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a',
   '5d000000-0000-0000-0000-000000000001', 'JAN', '5c000000-0000-0000-0000-000000000001', 1),
  ('5e000000-0000-0000-0000-000000000002', '1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a',
   '5d000000-0000-0000-0000-000000000001', 'FEV', '5c000000-0000-0000-0000-000000000002', 2);
UPDATE public.control_tests SET status = 'in_progress' WHERE id = '5d000000-0000-0000-0000-000000000001';
SELECT pg_temp.fails($q$UPDATE public.control_tests SET status = 'prepared', prepared_by = 'e7000000-0000-0000-0000-000000000007',
  conclusion = 'effective', conclusion_rationale = 'Revues conformes' WHERE id = '5d000000-0000-0000-0000-000000000001'$q$,
  'préparation avec des éléments non testés', 'non testé');
UPDATE public.control_test_items SET result = 'compliant' WHERE test_id = '5d000000-0000-0000-0000-000000000001';
SELECT pg_temp.ok((SELECT bool_and(tested_by = 'e7000000-0000-0000-0000-000000000007') FROM public.control_test_items
                    WHERE test_id = '5d000000-0000-0000-0000-000000000001'), 'élément : testeur enregistré');
SELECT pg_temp.fails($q$UPDATE public.control_tests SET status = 'prepared', prepared_by = 'e7000000-0000-0000-0000-000000000007',
  conclusion = 'effective', conclusion_rationale = 'Revues conformes' WHERE id = '5d000000-0000-0000-0000-000000000001'$q$,
  '« efficace » sans critères évalués', 'critères');
UPDATE public.control_tests SET operating_answers = '{"performed":{"answer":"yes"},"right_person":{"answer":"yes"},
  "right_frequency":{"answer":"yes"},"evidence_produced":{"answer":"yes"},"supervised":{"answer":"yes"},
  "anomalies_handled":{"answer":"na","comment":"Aucune anomalie sur la période"}}' WHERE id = '5d000000-0000-0000-0000-000000000001';
SELECT pg_temp.fails($q$UPDATE public.control_tests SET operating_answers = '{"inconnu":{"answer":"yes"}}'
  WHERE id = '5d000000-0000-0000-0000-000000000001'$q$, 'critère d''évaluation inconnu', 'invalides');
SELECT pg_temp.fails($q$UPDATE public.control_tests SET status = 'prepared', prepared_by = 'e7000000-0000-0000-0000-000000000007',
  conclusion = 'effective', conclusion_rationale = 'Revues conformes' WHERE id = '5d000000-0000-0000-0000-000000000001'$q$,
  '« efficace » sans élément probant', 'probant');
INSERT INTO public.evidence_items (id, organization_id, engagement_id, kind, title, source, snapshot, sha256, uploaded_by) VALUES
  ('5f000000-0000-0000-0000-000000000001', '1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a',
   'snapshot', 'Bons de commande signés (janvier-février)', 'auditee', '{"pieces": 2}',
   repeat('a', 64), 'e7000000-0000-0000-0000-000000000007'),
  ('5f000000-0000-0000-0000-000000000002', '1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a',
   'snapshot', 'Procédure de délégation', 'auditee', '{"pages": 3}', repeat('b', 64), 'e7000000-0000-0000-0000-000000000007');
INSERT INTO public.evidence_links (engagement_id, evidence_id, object_type, object_id, created_by) VALUES
  ('6a000000-0000-0000-0000-00000000000a', '5f000000-0000-0000-0000-000000000001', 'control_test_item',
   '5e000000-0000-0000-0000-000000000001', 'e7000000-0000-0000-0000-000000000007'),
  ('6a000000-0000-0000-0000-00000000000a', '5f000000-0000-0000-0000-000000000002', 'control_test',
   '5d000000-0000-0000-0000-000000000002', 'e7000000-0000-0000-0000-000000000007');
UPDATE public.control_tests SET status = 'prepared', prepared_by = 'e7000000-0000-0000-0000-000000000007', conclusion = 'effective',
  conclusion_rationale = 'Revues mensuelles réalisées, signées et supervisées' WHERE id = '5d000000-0000-0000-0000-000000000001';
SELECT pg_temp.fails($q$UPDATE public.control_tests SET results_summary = 'ajout' WHERE id = '5d000000-0000-0000-0000-000000000001'$q$,
  'test préparé : contenu figé', 'figé');
SELECT pg_temp.fails($q$UPDATE public.control_test_items SET result = 'exception', exception_description = 'x'
  WHERE id = '5e000000-0000-0000-0000-000000000001'$q$, 'test préparé : éléments figés', 'figés');
SELECT pg_temp.fails($q$UPDATE public.control_tests SET status = 'reviewed', reviewed_by = 'e7000000-0000-0000-0000-000000000007'
  WHERE id = '5d000000-0000-0000-0000-000000000001'$q$, 'préparateur : ne revoit pas son propre test', 'autre personne');
-- conception : critères tous positifs ; efficacité du contrôle C-ACH-3 : une exception pour zéro tolérée
UPDATE public.control_tests SET design_answers = '{"responds_to_risk":{"answer":"yes"},"well_defined":{"answer":"yes"},
  "owner_assigned":{"answer":"yes"},"frequency_adequate":{"answer":"yes"},"documented":{"answer":"yes"},"independent":{"answer":"yes"},
  "prevents_or_detects":{"answer":"yes"}}', status = 'in_progress' WHERE id = '5d000000-0000-0000-0000-000000000002';
UPDATE public.control_tests SET status = 'prepared', prepared_by = 'e7000000-0000-0000-0000-000000000007', conclusion = 'effective',
  conclusion_rationale = 'Conception adaptée au risque' WHERE id = '5d000000-0000-0000-0000-000000000002';
INSERT INTO public.control_test_items (organization_id, engagement_id, test_id, item_ref, result, exception_description) VALUES
  ('1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a', '5d000000-0000-0000-0000-000000000003',
   'FAC-101', 'compliant', NULL),
  ('1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a', '5d000000-0000-0000-0000-000000000003',
   'FAC-102', 'exception', 'Facture payée sans bon de réception');
SELECT pg_temp.fails($q$UPDATE public.control_tests SET status = 'prepared', prepared_by = 'e7000000-0000-0000-0000-000000000007',
  conclusion = 'effective', conclusion_rationale = 'x conforme' WHERE id = '5d000000-0000-0000-0000-000000000003'$q$,
  '« efficace » avec plus d''exceptions que tolérées', 'tolérée');
UPDATE public.control_tests SET status = 'prepared', prepared_by = 'e7000000-0000-0000-0000-000000000007',
  conclusion = 'partially_effective', conclusion_rationale = 'Une facture sur deux sans réception'
 WHERE id = '5d000000-0000-0000-0000-000000000003';
SELECT pg_temp.fails($q$UPDATE public.control_tests SET status = 'prepared', prepared_by = 'e7000000-0000-0000-0000-000000000007',
  conclusion = 'not_applicable' WHERE id = '5d000000-0000-0000-0000-000000000004'$q$, 'non applicable sans justification',
  'justification');
SELECT pg_temp.act_as('ec000000-0000-0000-0000-00000000000d');
UPDATE public.control_tests SET status = 'reviewed', reviewed_by = 'ec000000-0000-0000-0000-00000000000d'
 WHERE id IN ('5d000000-0000-0000-0000-000000000001', '5d000000-0000-0000-0000-000000000002', '5d000000-0000-0000-0000-000000000003');
SELECT pg_temp.ok((SELECT count(*) FROM public.control_tests WHERE status = 'reviewed') = 3,
  'chef de mission : revoit les tests préparés par l''auditeur');
SELECT pg_temp.fails($q$UPDATE public.control_tests SET conclusion = 'ineffective' WHERE id = '5d000000-0000-0000-0000-000000000001'$q$,
  'test revu : figé', 'figé');
SELECT pg_temp.fails($q$INSERT INTO public.evidence_links (engagement_id, evidence_id, object_type, object_id, created_by) VALUES
  ('6a000000-0000-0000-0000-00000000000a', '5f000000-0000-0000-0000-000000000002', 'control_test', '5d000000-0000-0000-0000-000000000001',
   'ec000000-0000-0000-0000-00000000000d')$q$, 'test revu : éléments probants figés', 'figé');
SELECT pg_temp.fails($q$DELETE FROM public.evidence_items WHERE id = '5f000000-0000-0000-0000-000000000001'$q$,
  'preuve d''un test revu : non supprimable', 'figé');
SELECT pg_temp.ok((SELECT conclusion FROM public.ic_control_status('2a000000-0000-0000-0000-00000000000a')
                    WHERE control_id = '5b000000-0000-0000-0000-000000000001') = 'effective',
  'synthèse : conception et efficacité concluantes → efficace');
SELECT pg_temp.ok((SELECT conclusion FROM public.ic_control_status('2a000000-0000-0000-0000-00000000000a')
                    WHERE control_id = '5b000000-0000-0000-0000-000000000003') = 'partially_effective',
  'synthèse : efficacité partielle');
SELECT pg_temp.ok((SELECT conclusion FROM public.ic_control_status('2a000000-0000-0000-0000-00000000000a')
                    WHERE control_id = '5b000000-0000-0000-0000-000000000002') = 'not_tested',
  'synthèse : contrôle déclaré mais non testé → non testé (jamais efficace par déclaration)');
SELECT pg_temp.ok(public.ic_combine('effective', NULL) = 'not_tested' AND public.ic_combine('ineffective', 'effective') = 'ineffective'
  AND public.ic_combine('not_applicable', NULL) = 'not_applicable', 'règle de synthèse : la conception seule ne suffit pas');

-- ------------------------------------------------------- évaluations
SELECT pg_temp.act_as('e7000000-0000-0000-0000-000000000007');
INSERT INTO public.ic_assessments (id, organization_id, engagement_id, company_id, reference, scope_type, domain_id, as_of_date, created_by)
VALUES ('8a000000-0000-0000-0000-000000000001', '1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a',
        '2a000000-0000-0000-0000-00000000000a', 'EV-ACH', 'domain', '4a000000-0000-0000-0000-000000000001', '2026-06-30',
        'e7000000-0000-0000-0000-000000000007'),
       ('8a000000-0000-0000-0000-000000000002', '1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a',
        '2a000000-0000-0000-0000-00000000000a', 'EV-GLOBAL', 'overall', NULL, '2026-06-30', 'e7000000-0000-0000-0000-000000000007');
SELECT pg_temp.fails($q$INSERT INTO public.ic_assessments (organization_id, engagement_id, company_id, reference, scope_type, as_of_date,
  created_by) VALUES ('1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
  'EV-X', 'domain', '2026-06-30', 'e7000000-0000-0000-0000-000000000007')$q$, 'évaluation par domaine sans domaine', 'check');
SELECT pg_temp.fails($q$UPDATE public.ic_assessments SET status = 'submitted', prepared_by = 'e7000000-0000-0000-0000-000000000007',
  conclusion = 'Dispositif partiellement maîtrisé', rating_code = 'Z9' WHERE id = '8a000000-0000-0000-0000-000000000001'$q$,
  'niveau absent de l''échelle de la méthodologie', 'maîtrise');
UPDATE public.ic_assessments SET status = 'submitted', prepared_by = 'e7000000-0000-0000-0000-000000000007',
  conclusion = 'Dispositif partiellement maîtrisé', rating_code = 'M2'
 WHERE id IN ('8a000000-0000-0000-0000-000000000001', '8a000000-0000-0000-0000-000000000002');
SELECT pg_temp.ok((SELECT basis ->> 'controls' = '3' AND basis ->> 'effective' = '1' AND basis ->> 'partially_effective' = '1'
                     AND basis ->> 'not_tested' = '1' AND basis ->> 'missing_controls' = '1' AND basis ->> 'risks' = '2'
                     AND basis ->> 'uncovered_risks' = '1' AND basis ->> 'rule' = 'IC-SYNTH-1'
                     FROM public.ic_assessments WHERE id = '8a000000-0000-0000-0000-000000000001'),
  'soumission : synthèse calculée par la base (contrôles, conclusions, risques non couverts)');
SELECT pg_temp.fails($q$UPDATE public.ic_assessments SET conclusion = 'autre' WHERE id = '8a000000-0000-0000-0000-000000000001'$q$,
  'évaluation soumise : contenu figé', 'figé');
SELECT pg_temp.fails($q$UPDATE public.ic_assessments SET status = 'approved', approved_by = 'e7000000-0000-0000-0000-000000000007'
  WHERE id = '8a000000-0000-0000-0000-000000000001'$q$, 'auditeur : n''approuve pas sa propre évaluation');
SELECT pg_temp.act_as('e5000000-0000-0000-0000-000000000005');
UPDATE public.ic_assessments SET status = 'approved', approved_by = 'e5000000-0000-0000-0000-000000000005'
 WHERE id = '8a000000-0000-0000-0000-000000000001';
SELECT pg_temp.fails($q$UPDATE public.ic_assessments SET conclusion = 'révisée' WHERE id = '8a000000-0000-0000-0000-000000000001'$q$,
  'évaluation approuvée : figée', 'figée');
SELECT pg_temp.fails($q$DELETE FROM public.ic_assessments WHERE id = '8a000000-0000-0000-0000-000000000001'$q$,
  'évaluation approuvée : conservée', 'conservée');
-- réouverture motivée d'un test : historisée ; l'évaluation globale soumise ne peut plus être approuvée telle quelle
SELECT pg_temp.act_as('e7000000-0000-0000-0000-000000000007');
SELECT pg_temp.fails($q$UPDATE public.control_tests SET status = 'in_progress', reopen_reason = 'Nouvelle pièce'
  WHERE id = '5d000000-0000-0000-0000-000000000003'$q$, 'auditeur : ne rouvre pas un test revu', 'manager');
SELECT pg_temp.act_as('e5000000-0000-0000-0000-000000000005');
UPDATE public.control_tests SET status = 'in_progress', reopen_reason = 'Pièce complémentaire reçue de l''audité'
 WHERE id = '5d000000-0000-0000-0000-000000000003';
SELECT pg_temp.ok((SELECT count(*) FROM public.ic_history WHERE object_id = '5d000000-0000-0000-0000-000000000003'
                    AND action = 'status:in_progress' AND reason LIKE 'Pièce complémentaire%' AND before ->> 'conclusion' = 'partially_effective') = 1,
  'réouverture : motif et résultat précédent conservés');
SELECT pg_temp.fails($q$UPDATE public.ic_assessments SET status = 'approved', approved_by = 'e5000000-0000-0000-0000-000000000005'
  WHERE id = '8a000000-0000-0000-0000-000000000002'$q$, 'approbation refusée si les résultats ont changé depuis la soumission', 'changé');
SELECT pg_temp.ok((SELECT basis ->> 'partially_effective' FROM public.ic_assessments WHERE id = '8a000000-0000-0000-0000-000000000001') = '1',
  'évaluation approuvée : synthèse historique inchangée');
UPDATE public.ic_assessments SET status = 'draft', return_reason = 'Test T-OP-3 rouvert' WHERE id = '8a000000-0000-0000-0000-000000000002';
SELECT pg_temp.act_as('e7000000-0000-0000-0000-000000000007');
UPDATE public.control_tests SET status = 'prepared', prepared_by = 'e7000000-0000-0000-0000-000000000007',
  conclusion_rationale = 'Une facture sur deux sans réception ; pièce complémentaire examinée' WHERE id = '5d000000-0000-0000-0000-000000000003';
SELECT pg_temp.act_as('e6000000-0000-0000-0000-000000000006');
UPDATE public.control_tests SET status = 'reviewed', reviewed_by = 'e6000000-0000-0000-0000-000000000006'
 WHERE id = '5d000000-0000-0000-0000-000000000003';

-- ------------------------------------------------------- déficiences et remédiation
SELECT pg_temp.act_as('e7000000-0000-0000-0000-000000000007');
SELECT pg_temp.fails($q$INSERT INTO public.findings (organization_id, engagement_id, reference, title, condition, criteria, kind, created_by)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a', 'D-X', 'x', 'x', 'x', 'ic_deficiency',
          'e7000000-0000-0000-0000-000000000007')$q$, 'déficience sans contrôle concerné', 'check');
INSERT INTO public.findings (id, organization_id, engagement_id, reference, title, condition, criteria, cause, effect, kind,
                             control_id, risk_id, rating_code, created_by) VALUES
  ('9a000000-0000-0000-0000-000000000001', '1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a', 'D-1',
   'Paiements sans réception', 'Une facture payée sans bon de réception', 'Rapprochement à trois voies avant paiement',
   'Contrôle non bloquant', 'Paiement de prestations non reçues', 'ic_deficiency', '5b000000-0000-0000-0000-000000000003',
   '5a000000-0000-0000-0000-000000000001', 'D1', 'e7000000-0000-0000-0000-000000000007');
SELECT pg_temp.ok((SELECT domain_id FROM public.findings WHERE id = '9a000000-0000-0000-0000-000000000001')
  = '4a000000-0000-0000-0000-000000000001', 'déficience : domaine hérité du contrôle');
SELECT pg_temp.fails($q$UPDATE public.findings SET rating_code = 'N1' WHERE id = '9a000000-0000-0000-0000-000000000001'$q$,
  'déficience : cotée sur l''échelle des déficiences', 'échelle');
SELECT pg_temp.fails($q$UPDATE public.findings SET kind = 'audit_finding' WHERE id = '9a000000-0000-0000-0000-000000000001'$q$,
  'nature du constat immuable', 'nature');
INSERT INTO public.recommendations (id, organization_id, engagement_id, finding_id, reference, text, created_by) VALUES
  ('9b000000-0000-0000-0000-000000000001', '1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a',
   '9a000000-0000-0000-0000-000000000001', 'REC-1', 'Bloquer le paiement sans réception', 'e7000000-0000-0000-0000-000000000007');
SELECT pg_temp.act_as('e1000000-0000-0000-0000-000000000001');
SELECT pg_temp.ok((SELECT count(*) FROM public.findings) = 0, 'responsable CI : déficience en brouillon non visible');
SELECT pg_temp.act_as('e5000000-0000-0000-0000-000000000005');
UPDATE public.findings SET status = 'validated', validated_by = 'e5000000-0000-0000-0000-000000000005'
 WHERE id = '9a000000-0000-0000-0000-000000000001';
SELECT pg_temp.act_as('ec000000-0000-0000-0000-00000000000d');
UPDATE public.findings SET status = 'communicated', communicated_by = 'ec000000-0000-0000-0000-00000000000d'
 WHERE id = '9a000000-0000-0000-0000-000000000001';
SELECT pg_temp.act_as('e8000000-0000-0000-0000-000000000008');
UPDATE public.findings SET management_response = 'Accord ; blocage paramétré dans l''ERP', response_by_name = 'Aude, DAF',
  response_user_id = 'e8000000-0000-0000-0000-000000000008' WHERE id = '9a000000-0000-0000-0000-000000000001';
INSERT INTO public.action_plans (id, organization_id, engagement_id, company_id, recommendation_id, description, owner_name, due_date,
                                 created_by)
VALUES ('9c000000-0000-0000-0000-000000000001', '1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a',
        '2a000000-0000-0000-0000-00000000000a', '9b000000-0000-0000-0000-000000000001', 'Paramétrer le blocage dans l''ERP',
        'Aude', '2026-09-30', 'e8000000-0000-0000-0000-000000000008');
SELECT pg_temp.act_as('e1000000-0000-0000-0000-000000000001');
SELECT pg_temp.ok((SELECT count(*) FROM public.findings) = 1 AND (SELECT count(*) FROM public.action_plans) = 1,
  'responsable CI : déficience communiquée et plan de remédiation suivis');
SELECT pg_temp.ok(pg_temp.n($q$WITH u AS (UPDATE public.findings SET title = 'x' RETURNING 1) SELECT count(*) FROM u$q$) = 0,
  'responsable CI : lecture seule sur la déficience');
SELECT pg_temp.act_as('ec000000-0000-0000-0000-00000000000d');
SELECT pg_temp.fails($q$UPDATE public.findings SET status = 'closed', closed_by = 'ec000000-0000-0000-0000-00000000000d',
  closure_note = 'Clôture' WHERE id = '9a000000-0000-0000-0000-000000000001'$q$, 'clôture avant vérification du plan', 'vérifié');
SELECT pg_temp.act_as('e8000000-0000-0000-0000-000000000008');
INSERT INTO public.action_plan_updates (organization_id, engagement_id, action_plan_id, status, comment, author_id, author_role)
VALUES ('1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a', '9c000000-0000-0000-0000-000000000001',
        'implemented', 'Blocage en production', 'e8000000-0000-0000-0000-000000000008', 'auditee');
SELECT pg_temp.act_as('ec000000-0000-0000-0000-00000000000d');
INSERT INTO public.action_plan_updates (organization_id, engagement_id, action_plan_id, status, comment, author_id, author_role)
VALUES ('1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a', '9c000000-0000-0000-0000-000000000001',
        'verified', 'Test du blocage concluant', 'ec000000-0000-0000-0000-00000000000d', 'in_charge');
SELECT pg_temp.ok((SELECT count(*) FROM public.action_plan_updates WHERE action_plan_id = '9c000000-0000-0000-0000-000000000001') = 2,
  'historique de la remédiation conservé');
UPDATE public.findings SET status = 'closed', closed_by = 'ec000000-0000-0000-0000-00000000000d',
  closure_note = 'Remédiation vérifiée' WHERE id = '9a000000-0000-0000-0000-000000000001';
SELECT pg_temp.ok((SELECT closed_at IS NOT NULL FROM public.findings WHERE id = '9a000000-0000-0000-0000-000000000001'),
  'cycle complet : brouillon → validation → communication → réponse → plan → mise en œuvre → vérification → clôture');
SELECT pg_temp.fails($q$UPDATE public.findings SET reopen_reason = 'xxx', status = 'draft' WHERE id = '9a000000-0000-0000-0000-000000000001'$q$,
  'déficience close : figée', 'clos');

-- ------------------------------------------------------- audit financier : prise en compte des tests
SELECT pg_temp.act_as('e9000000-0000-0000-0000-000000000009');
SELECT pg_temp.ok((SELECT count(*) FROM public.control_tests) = 3, 'audit financier : tests revus de l''entité consultables');
SELECT pg_temp.ok((SELECT count(*) FROM public.control_tests WHERE status <> 'reviewed') = 0, 'audit financier : tests non revus invisibles');
SELECT pg_temp.ok((SELECT count(*) FROM public.ic_assessments) = 1, 'audit financier : évaluations approuvées consultables');
SELECT pg_temp.fails($q$INSERT INTO public.control_test_reliances (organization_id, engagement_id, company_id, control_test_id, decision,
  rationale, decided_by) VALUES ('1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000b',
  '2a000000-0000-0000-0000-00000000000a', '5d000000-0000-0000-0000-000000000003', 'rely', 'Test récent',
  'e9000000-0000-0000-0000-000000000009')$q$, 'appui total sur un test partiellement efficace', 'efficace');
INSERT INTO public.control_test_reliances (id, organization_id, engagement_id, company_id, control_test_id, cycle_code,
                                           assertion_codes, decision, rationale, approach_impact, decided_by) VALUES
  ('9d000000-0000-0000-0000-000000000001', '1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000b',
   '2a000000-0000-0000-0000-00000000000a', '5d000000-0000-0000-0000-000000000001', 'ACHATS', ARRAY['OCC'], 'rely',
   'Test revu, période couverte, contrôle clé pertinent pour l''assertion', 'Réduction de l''étendue des tests de détail',
   'e9000000-0000-0000-0000-000000000009'),
  ('9d000000-0000-0000-0000-000000000002', '1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000b',
   '2a000000-0000-0000-0000-00000000000a', '5d000000-0000-0000-0000-000000000003', 'ACHATS', '{}', 'partial_rely',
   'Exception isolée identifiée', 'Tests de détail étendus sur les paiements', 'e9000000-0000-0000-0000-000000000009');
SELECT pg_temp.ok((SELECT period_overlap AND snapshot -> 'test' ->> 'conclusion' = 'effective'
                     AND jsonb_array_length(snapshot -> 'evidence') = 1 AND snapshot -> 'evidence' -> 0 ->> 'sha256' = repeat('a', 64)
                     FROM public.control_test_reliances WHERE id = '9d000000-0000-0000-0000-000000000001'),
  'prise en compte : période, conclusion et empreintes des preuves conservées');
SELECT pg_temp.fails($q$UPDATE public.control_test_reliances SET status = 'withdrawn' WHERE id = '9d000000-0000-0000-0000-000000000002'$q$,
  'retrait sans motif', 'check');
UPDATE public.control_test_reliances SET status = 'withdrawn', withdrawn_reason = 'Approche revue après l''exception'
 WHERE id = '9d000000-0000-0000-0000-000000000002';
SELECT pg_temp.fails($q$DELETE FROM public.control_test_reliances WHERE id = '9d000000-0000-0000-0000-000000000001'$q$,
  'prise en compte : conservée');
SELECT pg_temp.ok(pg_temp.n($q$WITH u AS (UPDATE public.controls SET title = 'x' RETURNING 1) SELECT count(*) FROM u$q$) = 0,
  'auditeur financier : ne modifie pas les données opérationnelles');
SELECT pg_temp.act_as('e5000000-0000-0000-0000-000000000005');
SELECT pg_temp.fails($q$INSERT INTO public.control_test_reliances (organization_id, engagement_id, company_id, control_test_id, decision,
  rationale, decided_by) VALUES ('1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a',
  '2a000000-0000-0000-0000-00000000000a', '5d000000-0000-0000-0000-000000000001', 'no_reliance', 'x x x',
  'e5000000-0000-0000-0000-000000000005')$q$, 'prise en compte réservée aux missions d''audit financier', 'audit financier');

-- ------------------------------------------------------- isolation et accès
SELECT pg_temp.act_as('eb000000-0000-0000-0000-00000000000b');
SELECT pg_temp.ok((SELECT count(*) FROM public.controls) + (SELECT count(*) FROM public.control_tests)
                + (SELECT count(*) FROM public.ic_assessments) + (SELECT count(*) FROM public.control_executions)
                + (SELECT count(*) FROM public.ic_history) + (SELECT count(*) FROM public.control_risks) = 0,
  'autre organisation : aucune donnée du contrôle interne visible');
SELECT pg_temp.act_as('e8000000-0000-0000-0000-000000000008');
SELECT pg_temp.ok((SELECT count(*) FROM public.control_tests) = 0 AND (SELECT count(*) FROM public.ic_assessments) = 1,
  'audité : évaluation approuvée visible, dossier de tests non visible');
SELECT pg_temp.act_as('e1000000-0000-0000-0000-000000000001');
SELECT pg_temp.ok((SELECT count(*) FROM public.control_tests) = 3, 'responsable CI : tests revus consultables');
SELECT pg_temp.ok(pg_temp.n($q$WITH u AS (UPDATE public.control_tests SET results_summary = 'x' RETURNING 1) SELECT count(*) FROM u$q$) = 0,
  'responsable CI : ne modifie pas les tests de la mission');
INSERT INTO public.engagements (organization_id, company_id, engagement_type, reference, name, created_by)
VALUES ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', 'ic_assessment', 'CI-2027', 'Campagne 2027',
        'e1000000-0000-0000-0000-000000000001');
SELECT pg_temp.ok((SELECT count(*) FROM public.engagements WHERE reference = 'CI-2027') = 1,
  'responsable CI : ouvre une mission d''évaluation du contrôle interne');
SELECT pg_temp.fails($q$INSERT INTO public.engagements (organization_id, company_id, engagement_type, reference, name, created_by)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', 'statutory_audit', 'CAC-X', 'x',
          'e1000000-0000-0000-0000-000000000001')$q$, 'responsable CI : pas de mission d''audit légal');
SELECT pg_temp.act_as('e2000000-0000-0000-0000-000000000002');
SELECT pg_temp.ok((SELECT count(*) FROM public.control_tests WHERE status = 'reviewed') = 3,
  'responsable de domaine : résultats revus des contrôles de son domaine consultables');
SELECT pg_temp.ok((SELECT count(*) FROM public.ic_history WHERE object_type = 'control_tests') = 0
                  AND (SELECT count(*) FROM public.ic_history WHERE object_type = 'controls') > 0,
  'responsable de domaine : historique du catalogue visible, pas celui des dossiers de mission');

-- déficience D-2 : remédiation vérifiée avant l'émission, clôture après l'émission (suivi)
SELECT pg_temp.act_as('e7000000-0000-0000-0000-000000000007');
INSERT INTO public.findings (id, organization_id, engagement_id, reference, title, condition, criteria, kind, control_id, rating_code,
                             created_by)
VALUES ('9a000000-0000-0000-0000-000000000002', '1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a', 'D-2',
        'Fichier fournisseurs non revu', 'Aucune revue du fichier', 'Revue périodique du fichier fournisseurs', 'ic_deficiency',
        '5b000000-0000-0000-0000-000000000002', 'D2', 'e7000000-0000-0000-0000-000000000007');
INSERT INTO public.recommendations (id, organization_id, engagement_id, finding_id, reference, text, created_by) VALUES
  ('9b000000-0000-0000-0000-000000000002', '1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a',
   '9a000000-0000-0000-0000-000000000002', 'REC-2', 'Instaurer une revue trimestrielle', 'e7000000-0000-0000-0000-000000000007');
SELECT pg_temp.act_as('e5000000-0000-0000-0000-000000000005');
UPDATE public.findings SET status = 'validated', validated_by = 'e5000000-0000-0000-0000-000000000005'
 WHERE id = '9a000000-0000-0000-0000-000000000002';
UPDATE public.findings SET status = 'communicated', communicated_by = 'e5000000-0000-0000-0000-000000000005'
 WHERE id = '9a000000-0000-0000-0000-000000000002';
SELECT pg_temp.act_as('e8000000-0000-0000-0000-000000000008');
INSERT INTO public.action_plans (id, organization_id, engagement_id, company_id, recommendation_id, description, owner_name, due_date,
                                 created_by)
VALUES ('9c000000-0000-0000-0000-000000000002', '1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a',
        '2a000000-0000-0000-0000-00000000000a', '9b000000-0000-0000-0000-000000000002', 'Revue trimestrielle formalisée', 'Aude',
        '2026-12-31', 'e8000000-0000-0000-0000-000000000008');
INSERT INTO public.action_plan_updates (organization_id, engagement_id, action_plan_id, status, comment, author_id, author_role)
VALUES ('1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a', '9c000000-0000-0000-0000-000000000002',
        'implemented', 'Première revue réalisée', 'e8000000-0000-0000-0000-000000000008', 'auditee');
SELECT pg_temp.act_as('e5000000-0000-0000-0000-000000000005');
INSERT INTO public.action_plan_updates (organization_id, engagement_id, action_plan_id, status, comment, author_id, author_role)
VALUES ('1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a', '9c000000-0000-0000-0000-000000000002',
        'verified', 'Revue examinée', 'e5000000-0000-0000-0000-000000000005', 'manager');

-- ------------------------------------------------------- gel du dossier émis
RESET ROLE;
SET LOCAL session_replication_role = replica;
UPDATE public.engagements SET status = 'issued' WHERE id = '6a000000-0000-0000-0000-00000000000a';
SET LOCAL session_replication_role = origin;
SET LOCAL ROLE authenticated;
SELECT pg_temp.act_as('e5000000-0000-0000-0000-000000000005');
SELECT pg_temp.fails($q$UPDATE public.control_tests SET status = 'in_progress', reopen_reason = 'Après émission'
  WHERE id = '5d000000-0000-0000-0000-000000000001'$q$, 'mission émise : tests figés', 'figé');
SELECT pg_temp.fails($q$INSERT INTO public.ic_assessments (organization_id, engagement_id, company_id, reference, scope_type, as_of_date,
  created_by) VALUES ('1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
  'EV-Y', 'overall', '2026-06-30', 'e5000000-0000-0000-0000-000000000005')$q$, 'mission émise : pas de nouvelle évaluation', 'figé');
SELECT pg_temp.fails($q$UPDATE public.findings SET status = 'closed', closed_by = 'e5000000-0000-0000-0000-000000000005',
  closure_note = 'Clos', title = 'modifié' WHERE id = '9a000000-0000-0000-0000-000000000002'$q$,
  'mission émise : clôture sans autre modification', 'figé');
UPDATE public.findings SET status = 'closed', closed_by = 'e5000000-0000-0000-0000-000000000005',
  closure_note = 'Remédiation vérifiée après l''émission' WHERE id = '9a000000-0000-0000-0000-000000000002';
SELECT pg_temp.ok((SELECT status FROM public.findings WHERE id = '9a000000-0000-0000-0000-000000000002') = 'closed',
  'mission émise : la clôture d''une déficience remédiée reste possible');

ROLLBACK;
