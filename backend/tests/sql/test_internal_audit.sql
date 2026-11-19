-- =====================================================================
-- Tests migration 0009 : audit interne (plan annuel, cartographie, constats, recommandations,
-- plans d'action et suivi, rapports, accès de l'audité, émission, gel).
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
CREATE OR REPLACE FUNCTION pg_temp.dbg(t text) RETURNS boolean LANGUAGE plpgsql AS $$ BEGIN RAISE NOTICE 'DBG %', t; RETURN false; END $$;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA pg_temp TO authenticated;

-- a : alice (propriétaire de l'organisation) ; 1 mona (manager) ; 2 paul (associé) ; 3 ines (chef de mission)
-- 4 sam (auditeur) ; 5 aude (auditée) ; b bob (autre organisation)
INSERT INTO auth.users (id, email) VALUES
  ('d0000000-0000-0000-0000-00000000000a', 'alice@ia.test'), ('d1000000-0000-0000-0000-000000000001', 'mona@ia.test'),
  ('d2000000-0000-0000-0000-000000000002', 'paul@ia.test'), ('d3000000-0000-0000-0000-000000000003', 'ines@ia.test'),
  ('d4000000-0000-0000-0000-000000000004', 'sam@ia.test'), ('d5000000-0000-0000-0000-000000000005', 'aude@ia.test'),
  ('db000000-0000-0000-0000-00000000000b', 'bob@ib.test');
INSERT INTO public.accounting_frameworks (id, code, name) VALUES ('f0000000-0000-0000-0000-0000000000f9', 'TEST_FW9', 'Test');

SET LOCAL session_replication_role = replica;
INSERT INTO public.profiles (id, email) SELECT id, email FROM auth.users WHERE email LIKE '%@i_.test' ON CONFLICT DO NOTHING;
INSERT INTO public.organizations (id, name, slug, created_by) VALUES
  ('19000000-0000-0000-0000-00000000000a', 'Direction audit IA', 'dir-ia', 'd0000000-0000-0000-0000-00000000000a'),
  ('19000000-0000-0000-0000-00000000000b', 'Cabinet IB', 'cab-ib', 'db000000-0000-0000-0000-00000000000b');
INSERT INTO public.organization_members (organization_id, user_id, role) VALUES
  ('19000000-0000-0000-0000-00000000000a', 'd0000000-0000-0000-0000-00000000000a', 'owner'),
  ('19000000-0000-0000-0000-00000000000b', 'db000000-0000-0000-0000-00000000000b', 'owner');
INSERT INTO public.organization_members (organization_id, user_id, role)
SELECT '19000000-0000-0000-0000-00000000000a', u, 'member' FROM unnest(ARRAY[
  'd1000000-0000-0000-0000-000000000001','d2000000-0000-0000-0000-000000000002','d3000000-0000-0000-0000-000000000003',
  'd4000000-0000-0000-0000-000000000004','d5000000-0000-0000-0000-000000000005']::uuid[]) u;
INSERT INTO public.companies (id, organization_id, name, framework_id, created_by) VALUES
  ('29000000-0000-0000-0000-00000000000a', '19000000-0000-0000-0000-00000000000a', 'Filiale IA',
   'f0000000-0000-0000-0000-0000000000f9', 'd0000000-0000-0000-0000-00000000000a');
INSERT INTO public.methodology_versions (id, organization_id, kind, name, version_label, source_reference, status, published_at, created_by)
VALUES ('39000000-0000-0000-0000-00000000000a', '19000000-0000-0000-0000-00000000000a', 'audit', 'Méthode IA test', 'v1',
        'Méthodologie FICTIVE de test', 'published', now(), 'd0000000-0000-0000-0000-00000000000a');
INSERT INTO public.methodology_items (version_id, item_type, code, label, content) VALUES
  ('39000000-0000-0000-0000-00000000000a', 'risk_scale', 'GRILLE', 'Grille test',
   '{"likelihood":[{"score":1,"label":"Faible"},{"score":2,"label":"Forte"}],"impact":[{"score":1,"label":"Faible"},{"score":2,"label":"Fort"}]}'),
  ('39000000-0000-0000-0000-00000000000a', 'finding_scale', 'ECHELLE', 'Échelle des constats (test)',
   '{"levels":[{"code":"N1","label":"Majeur (test)","rank":1},{"code":"N2","label":"Mineur (test)","rank":2}]}');
INSERT INTO public.processes (id, organization_id, company_id, code, name) VALUES
  ('49000000-0000-0000-0000-00000000000a', '19000000-0000-0000-0000-00000000000a', '29000000-0000-0000-0000-00000000000a',
   'ACH', 'Achats');
INSERT INTO public.risks (id, organization_id, company_id, process_id, code, title, scale_version_id, inherent_likelihood, inherent_impact)
VALUES ('59000000-0000-0000-0000-00000000000a', '19000000-0000-0000-0000-00000000000a', '29000000-0000-0000-0000-00000000000a',
        '49000000-0000-0000-0000-00000000000a', 'R1', 'Fraude fournisseurs', '39000000-0000-0000-0000-00000000000a', 2, 2);
INSERT INTO public.engagements (id, organization_id, company_id, engagement_type, reference, name, methodology_version_id, created_by)
VALUES ('69000000-0000-0000-0000-00000000000a', '19000000-0000-0000-0000-00000000000a', '29000000-0000-0000-0000-00000000000a',
        'internal_audit', 'AI-ACH', 'Audit des achats', '39000000-0000-0000-0000-00000000000a', 'd1000000-0000-0000-0000-000000000001'),
       ('69000000-0000-0000-0000-00000000000b', '19000000-0000-0000-0000-00000000000a', '29000000-0000-0000-0000-00000000000a',
        'contractual_audit', 'CA-1', 'Audit contractuel', NULL, 'd1000000-0000-0000-0000-000000000001');
INSERT INTO public.engagement_members (organization_id, engagement_id, user_id, role, independence_confirmed_at)
SELECT '19000000-0000-0000-0000-00000000000a', '69000000-0000-0000-0000-00000000000a', u, r,
       CASE WHEN r = 'auditee' THEN NULL ELSE now() END FROM (VALUES
  ('d1000000-0000-0000-0000-000000000001'::uuid, 'manager'), ('d2000000-0000-0000-0000-000000000002'::uuid, 'partner'),
  ('d3000000-0000-0000-0000-000000000003'::uuid, 'in_charge'), ('d4000000-0000-0000-0000-000000000004'::uuid, 'staff'),
  ('d5000000-0000-0000-0000-000000000005'::uuid, 'auditee')) t(u, r);
SET LOCAL session_replication_role = origin;

SET LOCAL ROLE authenticated;

-- ------------------------------------------------------- plan annuel
SELECT pg_temp.act_as('d4000000-0000-0000-0000-000000000004');
SELECT pg_temp.fails($q$INSERT INTO public.audit_plans (organization_id, title, period_start, period_end, created_by)
  VALUES ('19000000-0000-0000-0000-00000000000a', 'Plan 2027', '2027-01-01', '2027-12-31', 'd4000000-0000-0000-0000-000000000004')$q$,
  'membre simple : création du plan refusée');
SELECT pg_temp.act_as('d0000000-0000-0000-0000-00000000000a');
INSERT INTO public.audit_plans (id, organization_id, title, period_start, period_end, created_by)
VALUES ('79000000-0000-0000-0000-00000000000a', '19000000-0000-0000-0000-00000000000a', 'Plan 2027', '2027-01-01', '2027-12-31',
        'd0000000-0000-0000-0000-00000000000a');
SELECT pg_temp.fails($q$UPDATE public.audit_plans SET status = 'approved', approval_body = 'Comité', approval_date = '2026-12-15',
  approved_by = 'd0000000-0000-0000-0000-00000000000a'$q$, 'approbation d''un plan vide', 'vide');
INSERT INTO public.audit_plan_items (id, organization_id, plan_id, company_id, process_id, title, rationale, planned_start, planned_end,
                                     budget_days, created_by)
VALUES ('89000000-0000-0000-0000-000000000001', '19000000-0000-0000-0000-00000000000a', '79000000-0000-0000-0000-00000000000a',
        '29000000-0000-0000-0000-00000000000a', '49000000-0000-0000-0000-00000000000a', 'Audit des achats',
        'Risque R1 coté 2 × 2 dans la cartographie', '2027-03-01', '2027-04-30', 25, 'd0000000-0000-0000-0000-00000000000a');
SELECT pg_temp.fails($q$UPDATE public.audit_plans SET status = 'approved', approval_date = '2026-12-15',
  approved_by = 'd0000000-0000-0000-0000-00000000000a'$q$, 'approbation sans instance d''approbation', 'check');
SELECT pg_temp.fails($q$UPDATE public.audit_plans SET status = 'approved', approval_body = 'Comité', approval_date = '2026-12-15',
  approved_by = 'd1000000-0000-0000-0000-000000000001'$q$, 'approbation enregistrée au nom d''un autre', 'au nom');
UPDATE public.audit_plans SET status = 'approved', approval_body = 'Comité d''audit (test)', approval_reference = 'PV 2026-12',
  approval_date = '2026-12-15', approved_by = 'd0000000-0000-0000-0000-00000000000a';
SELECT pg_temp.ok((SELECT approved_at IS NOT NULL FROM public.audit_plans), 'plan approuvé, instance et date enregistrées');
SELECT pg_temp.fails($q$UPDATE public.audit_plans SET period_end = '2027-11-30'$q$, 'plan approuvé : en-tête figé', 'figés');
SELECT pg_temp.fails($q$INSERT INTO public.audit_plan_items (organization_id, plan_id, company_id, title, rationale, created_by)
  VALUES ('19000000-0000-0000-0000-00000000000a', '79000000-0000-0000-0000-00000000000a', '29000000-0000-0000-0000-00000000000a',
          'Audit de la paie', 'Demande de la direction générale', 'd0000000-0000-0000-0000-00000000000a')$q$,
  'ajout après approbation sans motif', 'motif');
INSERT INTO public.audit_plan_items (id, organization_id, plan_id, company_id, title, rationale, change_reason, created_by)
VALUES ('89000000-0000-0000-0000-000000000002', '19000000-0000-0000-0000-00000000000a', '79000000-0000-0000-0000-00000000000a',
        '29000000-0000-0000-0000-00000000000a', 'Audit de la paie', 'Demande de la direction générale',
        'Ajout décidé par le comité du 15/02', 'd0000000-0000-0000-0000-00000000000a');
SELECT pg_temp.ok((SELECT added_after_approval FROM public.audit_plan_items WHERE id = '89000000-0000-0000-0000-000000000002'),
  'ajout après approbation marqué comme tel');
SELECT pg_temp.fails($q$UPDATE public.audit_plan_items SET budget_days = 30 WHERE id = '89000000-0000-0000-0000-000000000001'$q$,
  'modification après approbation sans motif', 'motif');
UPDATE public.audit_plan_items SET budget_days = 30, change_reason = 'Extension du périmètre aux frais généraux'
 WHERE id = '89000000-0000-0000-0000-000000000001';
SELECT pg_temp.fails($q$UPDATE public.audit_plan_items SET status = 'cancelled' WHERE id = '89000000-0000-0000-0000-000000000002'$q$,
  'annulation sans motif', 'check');
SELECT pg_temp.fails($q$DELETE FROM public.audit_plan_items WHERE id = '89000000-0000-0000-0000-000000000002'$q$,
  'plan approuvé : suppression refusée', 'annule');
UPDATE public.audit_plan_items SET status = 'postponed', status_reason = 'Réorganisation du service paie'
 WHERE id = '89000000-0000-0000-0000-000000000002';
SELECT pg_temp.fails($q$UPDATE public.audit_plan_items SET engagement_id = '69000000-0000-0000-0000-00000000000b'
  WHERE id = '89000000-0000-0000-0000-000000000001'$q$, 'rattachement à une mission d''un autre type', 'audit interne');
UPDATE public.audit_plan_items SET engagement_id = '69000000-0000-0000-0000-00000000000a', status = 'in_progress'
 WHERE id = '89000000-0000-0000-0000-000000000001';
SELECT pg_temp.fails($q$UPDATE public.audit_plan_items SET status = 'completed' WHERE id = '89000000-0000-0000-0000-000000000001'$q$,
  'réalisée alors que la mission n''est pas émise', 'émise');
SELECT pg_temp.ok((SELECT count(*) FROM public.audit_plan_item_history) = 5, 'historique du plan : 5 opérations tracées');
SELECT pg_temp.ok((SELECT reason FROM public.audit_plan_item_history WHERE after ->> 'engagement_id' IS NOT NULL) IS NULL,
  'historique : pas de motif hérité d''une modification précédente');
SELECT pg_temp.ok((SELECT reason FROM public.audit_plan_item_history WHERE after ->> 'status' = 'postponed') = 'Réorganisation du service paie',
  'historique : motif du report conservé');
SELECT pg_temp.fails($q$UPDATE public.audit_plans SET status = 'closed'$q$, 'clôture avec une mission en cours', 'réalisée');

-- ------------------------------------------------------- cartographie : historique des cotations
RESET ROLE;
UPDATE public.risks SET residual_likelihood = 1, residual_impact = 2 WHERE id = '59000000-0000-0000-0000-00000000000a';
SET LOCAL ROLE authenticated;
SELECT pg_temp.ok((SELECT count(*) FROM public.risk_rating_history) = 1 AND
                  (SELECT residual_impact FROM public.risk_rating_history) = 2, 'cotation du risque historisée');

-- ------------------------------------------------------- constats et recommandations
SELECT pg_temp.act_as('d4000000-0000-0000-0000-000000000004');
INSERT INTO public.findings (id, organization_id, engagement_id, reference, title, condition, criteria, cause, effect, process_id, created_by)
VALUES ('99000000-0000-0000-0000-000000000001', '19000000-0000-0000-0000-00000000000a', '69000000-0000-0000-0000-00000000000a',
        'C1', 'Fournisseurs créés sans contrôle', '12 fournisseurs créés sans validation', 'Procédure achats : double validation',
        'Absence de contrôle dans l''outil', 'Risque de fournisseur fictif', '49000000-0000-0000-0000-00000000000a',
        'd4000000-0000-0000-0000-000000000004');
SELECT pg_temp.fails($q$UPDATE public.findings SET rating_code = 'N9'$q$, 'cotation absente de l''échelle de la méthodologie', 'absente');
UPDATE public.findings SET rating_code = 'N1';
SELECT pg_temp.fails($q$UPDATE public.findings SET status = 'validated', validated_by = 'd4000000-0000-0000-0000-000000000004'$q$,
  'auditeur : validation refusée', 'manager');
SELECT pg_temp.act_as('d1000000-0000-0000-0000-000000000001');
SELECT pg_temp.fails($q$UPDATE public.findings SET status = 'validated', validated_by = 'd1000000-0000-0000-0000-000000000001'$q$,
  'validation sans recommandation', 'recommandation');
INSERT INTO public.recommendations (id, organization_id, engagement_id, finding_id, reference, text, created_by)
VALUES ('a9000000-0000-0000-0000-000000000001', '19000000-0000-0000-0000-00000000000a', '69000000-0000-0000-0000-00000000000a',
        '99000000-0000-0000-0000-000000000001', 'R1.1', 'Mettre en place la double validation dans l''outil',
        'd1000000-0000-0000-0000-000000000001');
INSERT INTO public.findings (id, organization_id, engagement_id, reference, title, condition, criteria, rating_code, created_by)
VALUES ('99000000-0000-0000-0000-000000000002', '19000000-0000-0000-0000-00000000000a', '69000000-0000-0000-0000-00000000000a',
        'C2', 'Bons de commande non signés', '3 bons sur 25', 'Procédure achats', 'N2', 'd1000000-0000-0000-0000-000000000001');
INSERT INTO public.recommendations (organization_id, engagement_id, finding_id, reference, text, created_by)
VALUES ('19000000-0000-0000-0000-00000000000a', '69000000-0000-0000-0000-00000000000a', '99000000-0000-0000-0000-000000000002',
        'R2.1', 'Rappeler la procédure', 'd1000000-0000-0000-0000-000000000001');
SELECT pg_temp.fails($q$UPDATE public.findings SET status = 'validated', validated_by = 'd1000000-0000-0000-0000-000000000001'
  WHERE reference = 'C2'$q$, 'validation par l''auteur du constat', 'autre personne');
UPDATE public.findings SET status = 'validated', validated_by = 'd1000000-0000-0000-0000-000000000001' WHERE reference = 'C1';
SELECT pg_temp.ok((SELECT validated_at IS NOT NULL FROM public.findings WHERE reference = 'C1'), 'constat C1 validé par le manager');
SELECT pg_temp.fails($q$UPDATE public.findings SET condition = 'Autre constat' WHERE reference = 'C1'$q$, 'constat validé : contenu figé', 'figé');
SELECT pg_temp.fails($q$INSERT INTO public.recommendations (organization_id, engagement_id, finding_id, reference, text, created_by)
  VALUES ('19000000-0000-0000-0000-00000000000a', '69000000-0000-0000-0000-00000000000a', '99000000-0000-0000-0000-000000000001',
          'R1.2', 'Autre', 'd1000000-0000-0000-0000-000000000001')$q$, 'constat validé : recommandations figées', 'figées');
SELECT pg_temp.act_as('d5000000-0000-0000-0000-000000000005');
SELECT pg_temp.ok((SELECT count(*) FROM public.findings) = 0 AND (SELECT count(*) FROM public.recommendations) = 0,
  'audité : constats non communiqués invisibles');
SELECT pg_temp.act_as('d4000000-0000-0000-0000-000000000004');
SELECT pg_temp.fails($q$UPDATE public.findings SET status = 'communicated', communicated_by = 'd4000000-0000-0000-0000-000000000004'
  WHERE reference = 'C1'$q$, 'auditeur : communication refusée', 'encadrement');
SELECT pg_temp.act_as('d3000000-0000-0000-0000-000000000003');
UPDATE public.findings SET status = 'communicated', communicated_by = 'd3000000-0000-0000-0000-000000000003', response_due = '2027-05-15'
 WHERE reference = 'C1';
SELECT pg_temp.act_as('d5000000-0000-0000-0000-000000000005');
SELECT pg_temp.ok((SELECT count(*) FROM public.findings) = 1 AND (SELECT count(*) FROM public.recommendations) = 1,
  'audité : constat communiqué et sa recommandation visibles');
SELECT pg_temp.ok((SELECT count(*) FROM public.workpapers) = 0, 'audité : dossier de travail toujours invisible');
SELECT pg_temp.fails($q$UPDATE public.findings SET title = 'Titre modifié'$q$, 'audité : modification du constat refusée', 'réponse');
SELECT pg_temp.fails($q$UPDATE public.findings SET management_response = 'D''accord', response_by_name = 'DAF',
  response_user_id = 'd4000000-0000-0000-0000-000000000004'$q$, 'audité : réponse au nom d''un autre', 'au nom');
UPDATE public.findings SET management_response = 'Nous mettrons en place la double validation au T2.', response_by_name = 'Aude, DAF',
  response_user_id = 'd5000000-0000-0000-0000-000000000005';
SELECT pg_temp.ok((SELECT response_at IS NOT NULL AND response_recorded_by = 'd5000000-0000-0000-0000-000000000005' FROM public.findings),
  'audité : réponse de la direction enregistrée');
SELECT pg_temp.act_as('d3000000-0000-0000-0000-000000000003');
SELECT pg_temp.fails($q$UPDATE public.findings SET management_response = 'x', response_by_name = 'DAF',
  response_user_id = 'd5000000-0000-0000-0000-000000000005' WHERE reference = 'C1'$q$,
  'équipe : réponse attribuée à un compte refusée', 'auteur');

-- ------------------------------------------------------- plans d'action et suivi
SELECT pg_temp.act_as('d5000000-0000-0000-0000-000000000005');
INSERT INTO public.action_plans (id, organization_id, engagement_id, company_id, recommendation_id, description, owner_name, due_date,
                                 created_by)
VALUES ('b9000000-0000-0000-0000-000000000001', '19000000-0000-0000-0000-00000000000a', '69000000-0000-0000-0000-00000000000a',
        '00000000-0000-0000-0000-000000000000', 'a9000000-0000-0000-0000-000000000001', 'Paramétrer la double validation',
        'Responsable achats', '2027-06-30', 'd5000000-0000-0000-0000-000000000005');
SELECT pg_temp.ok((SELECT company_id = '29000000-0000-0000-0000-00000000000a' FROM public.action_plans), 'plan d''action : entité reprise de la mission');
SELECT pg_temp.fails($q$UPDATE public.action_plans SET status = 'implemented'$q$, 'statut modifié sans mise à jour de suivi', 'suivi');
INSERT INTO public.action_plan_updates (organization_id, engagement_id, action_plan_id, status, comment, author_id, author_role)
VALUES ('19000000-0000-0000-0000-00000000000a', '69000000-0000-0000-0000-00000000000a', 'b9000000-0000-0000-0000-000000000001',
        'in_progress', 'Demande de paramétrage envoyée à l''éditeur', 'd5000000-0000-0000-0000-000000000005', 'x');
SELECT pg_temp.ok((SELECT status FROM public.action_plans) = 'in_progress', 'suivi : statut mis à jour par l''audité');
SELECT pg_temp.fails($q$INSERT INTO public.action_plan_updates (organization_id, engagement_id, action_plan_id, status, comment,
  author_id, author_role) VALUES ('19000000-0000-0000-0000-00000000000a', '69000000-0000-0000-0000-00000000000a',
  'b9000000-0000-0000-0000-000000000001', 'verified', 'Vérifié', 'd5000000-0000-0000-0000-000000000005', 'x')$q$,
  'audité : vérification refusée', 'encadrement');
SELECT pg_temp.act_as('d3000000-0000-0000-0000-000000000003');
SELECT pg_temp.fails($q$INSERT INTO public.action_plan_updates (organization_id, engagement_id, action_plan_id, status, comment,
  author_id, author_role) VALUES ('19000000-0000-0000-0000-00000000000a', '69000000-0000-0000-0000-00000000000a',
  'b9000000-0000-0000-0000-000000000001', 'verified', 'Vérifié', 'd3000000-0000-0000-0000-000000000003', 'x')$q$,
  'vérification d''une action non déclarée mise en œuvre', 'déclarée');
SELECT pg_temp.act_as('d5000000-0000-0000-0000-000000000005');
INSERT INTO public.action_plan_updates (organization_id, engagement_id, action_plan_id, status, comment, new_due_date, author_id, author_role)
VALUES ('19000000-0000-0000-0000-00000000000a', '69000000-0000-0000-0000-00000000000a', 'b9000000-0000-0000-0000-000000000001',
        'implemented', 'Paramétrage en production le 20/06', '2027-06-20', 'd5000000-0000-0000-0000-000000000005', 'x');
SELECT pg_temp.act_as('d3000000-0000-0000-0000-000000000003');
INSERT INTO public.action_plan_updates (organization_id, engagement_id, action_plan_id, status, comment, author_id, author_role)
VALUES ('19000000-0000-0000-0000-00000000000a', '69000000-0000-0000-0000-00000000000a', 'b9000000-0000-0000-0000-000000000001',
        'verified', 'Test de 10 créations : double validation effective', 'd3000000-0000-0000-0000-000000000003', 'x');
SELECT pg_temp.ok((SELECT status = 'verified' AND due_date = '2027-06-20' FROM public.action_plans), 'action vérifiée par le chef de mission');
SELECT pg_temp.ok((SELECT string_agg(author_role, ',' ORDER BY created_at) FROM public.action_plan_updates) = 'auditee,auditee,in_charge',
  'suivi : rôle de chaque auteur enregistré par la base');
SELECT pg_temp.fails($q$INSERT INTO public.action_plan_updates (organization_id, engagement_id, action_plan_id, status, comment,
  author_id, author_role) VALUES ('19000000-0000-0000-0000-00000000000a', '69000000-0000-0000-0000-00000000000a',
  'b9000000-0000-0000-0000-000000000001', 'in_progress', 'Retour', 'd3000000-0000-0000-0000-000000000003', 'x')$q$,
  'action vérifiée : suivi clos', 'clos');
SELECT pg_temp.fails($q$UPDATE public.action_plan_updates SET comment = 'modifié'$q$, 'historique du suivi non modifiable', 'permission');
SELECT pg_temp.fails($q$DELETE FROM public.action_plan_updates$q$, 'historique du suivi non supprimable', 'permission');

-- ------------------------------------------------------- rapport
SELECT pg_temp.act_as('d4000000-0000-0000-0000-000000000004');
SELECT pg_temp.fails($q$INSERT INTO public.audit_reports (organization_id, engagement_id, version, title, created_by)
  VALUES ('19000000-0000-0000-0000-00000000000a', '69000000-0000-0000-0000-00000000000a', 1, 'Rapport', 'd4000000-0000-0000-0000-000000000004')$q$,
  'auditeur : création du rapport refusée');
SELECT pg_temp.act_as('d3000000-0000-0000-0000-000000000003');
INSERT INTO public.audit_reports (id, organization_id, engagement_id, version, title, overall_conclusion, created_by)
VALUES ('c9000000-0000-0000-0000-000000000001', '19000000-0000-0000-0000-00000000000a', '69000000-0000-0000-0000-00000000000a', 1,
        'Rapport d''audit des achats', 'Dispositif à renforcer (jugement de l''auditeur)', 'd3000000-0000-0000-0000-000000000003');
SELECT pg_temp.act_as('d2000000-0000-0000-0000-000000000002');
SELECT pg_temp.fails($q$UPDATE public.audit_reports SET status = 'issued', issued_by = 'd2000000-0000-0000-0000-000000000002',
  snapshot = '{"findings":[1,2]}'$q$, 'émission sans assemblage par KOFINEX', 'assemblé');
SELECT set_config('kofinex.report_issue', 'on', true);
SELECT pg_temp.fails($q$UPDATE public.audit_reports SET status = 'issued', issued_by = 'd2000000-0000-0000-0000-000000000002',
  snapshot = '{"findings":[1,2]}'$q$, 'émission avec un constat en brouillon', 'non validé');
SELECT pg_temp.act_as('d2000000-0000-0000-0000-000000000002');
UPDATE public.findings SET status = 'validated', validated_by = 'd2000000-0000-0000-0000-000000000002' WHERE reference = 'C2';
UPDATE public.findings SET status = 'communicated', communicated_by = 'd2000000-0000-0000-0000-000000000002' WHERE reference = 'C2';
SELECT pg_temp.fails($q$UPDATE public.audit_reports SET status = 'issued', issued_by = 'd2000000-0000-0000-0000-000000000002',
  snapshot = '{"findings":[1]}'$q$, 'contenu ne reprenant pas tous les constats', 'tous les constats');
SELECT pg_temp.act_as('d1000000-0000-0000-0000-000000000001');
SELECT pg_temp.fails($q$UPDATE public.audit_reports SET status = 'issued', issued_by = 'd1000000-0000-0000-0000-000000000001',
  snapshot = '{"findings":[1,2]}'$q$, 'manager : émission du rapport refusée', 'associé');
SELECT pg_temp.act_as('d2000000-0000-0000-0000-000000000002');
UPDATE public.audit_reports SET status = 'issued', issued_by = 'd2000000-0000-0000-0000-000000000002',
  snapshot = '{"findings":[{"reference":"C1"},{"reference":"C2"}]}';
SELECT set_config('kofinex.report_issue', 'off', true);
SELECT pg_temp.ok((SELECT content_sha256 = encode(sha256(convert_to(snapshot::text, 'UTF8')), 'hex') AND issued_at IS NOT NULL
                   FROM public.audit_reports), 'rapport émis : empreinte du contenu calculée par la base');
SELECT pg_temp.fails($q$UPDATE public.audit_reports SET overall_conclusion = 'Autre'$q$, 'rapport émis : non modifiable', 'non modifiable');
SELECT pg_temp.fails($q$DELETE FROM public.audit_reports$q$, 'rapport émis : non supprimable', 'conservé');
SELECT pg_temp.act_as('d5000000-0000-0000-0000-000000000005');
SELECT pg_temp.ok((SELECT count(*) FROM public.audit_reports) = 1, 'audité : rapport émis visible');

-- ------------------------------------------------------- émission, gel, suivi après émission
SELECT pg_temp.act_as('d3000000-0000-0000-0000-000000000003');
INSERT INTO public.action_plans (id, organization_id, engagement_id, company_id, recommendation_id, description, owner_name, due_date,
                                 created_by)
SELECT 'b9000000-0000-0000-0000-000000000002', '19000000-0000-0000-0000-00000000000a', '69000000-0000-0000-0000-00000000000a',
       '29000000-0000-0000-0000-00000000000a', id, 'Note de rappel', 'Directeur des achats', '2027-04-30',
       'd3000000-0000-0000-0000-000000000003' FROM public.recommendations WHERE reference = 'R2.1';
RESET ROLE;
SET LOCAL session_replication_role = replica;
UPDATE public.engagements SET status = 'reporting' WHERE id = '69000000-0000-0000-0000-00000000000a';
SET LOCAL session_replication_role = origin;
SET LOCAL ROLE authenticated;
SELECT pg_temp.act_as('d2000000-0000-0000-0000-000000000002');
DELETE FROM public.audit_reports WHERE status = 'draft';
SELECT pg_temp.ok(EXISTS (SELECT 1 FROM public.audit_reports WHERE status = 'issued'), 'rapport émis présent avant l''émission de la mission');
RESET ROLE;
SET LOCAL session_replication_role = replica;
UPDATE public.audit_reports SET status = 'superseded';
SET LOCAL session_replication_role = origin;
SET LOCAL ROLE authenticated;
SELECT pg_temp.act_as('d2000000-0000-0000-0000-000000000002');
SELECT pg_temp.fails($q$UPDATE public.engagements SET status = 'issued' WHERE id = '69000000-0000-0000-0000-00000000000a'$q$,
  'mission d''audit interne émise sans rapport émis', 'rapport');
RESET ROLE;
SET LOCAL session_replication_role = replica;
UPDATE public.audit_reports SET status = 'issued';
UPDATE public.engagements SET status = 'issued' WHERE id = '69000000-0000-0000-0000-00000000000a';
SET LOCAL session_replication_role = origin;
SET LOCAL ROLE authenticated;
SELECT pg_temp.act_as('d3000000-0000-0000-0000-000000000003');
SELECT pg_temp.fails($q$UPDATE public.findings SET status = 'draft', reopen_reason = 'test' WHERE reference = 'C2'$q$,
  'mission émise : constats figés', 'figé');
SELECT pg_temp.fails($q$UPDATE public.action_plans SET description = 'Autre' WHERE id = 'b9000000-0000-0000-0000-000000000002'$q$,
  'mission émise : contenu du plan d''action figé', 'figure au rapport');
SELECT pg_temp.act_as('d5000000-0000-0000-0000-000000000005');
INSERT INTO public.action_plan_updates (organization_id, engagement_id, action_plan_id, status, comment, author_id, author_role)
VALUES ('19000000-0000-0000-0000-00000000000a', '69000000-0000-0000-0000-00000000000a', 'b9000000-0000-0000-0000-000000000002',
        'risk_accepted', 'Risque accepté par la direction générale (note du 02/05)', 'd5000000-0000-0000-0000-000000000005', 'x');
SELECT pg_temp.ok((SELECT status FROM public.action_plans WHERE id = 'b9000000-0000-0000-0000-000000000002') = 'risk_accepted',
  'suivi après émission : acceptation du risque par l''audité');
SELECT pg_temp.act_as('d0000000-0000-0000-0000-00000000000a');
UPDATE public.audit_plan_items SET status = 'completed' WHERE id = '89000000-0000-0000-0000-000000000001';
SELECT pg_temp.ok((SELECT status FROM public.audit_plan_items WHERE id = '89000000-0000-0000-0000-000000000001') = 'completed',
  'plan : mission réalisée une fois émise');

-- ------------------------------------------------------- cloisonnement
SELECT pg_temp.act_as('db000000-0000-0000-0000-00000000000b');
SELECT pg_temp.ok((SELECT count(*) FROM public.audit_plans) + (SELECT count(*) FROM public.findings)
                  + (SELECT count(*) FROM public.action_plans) + (SELECT count(*) FROM public.audit_reports)
                  + (SELECT count(*) FROM public.risk_rating_history) = 0, 'autre organisation : rien de visible');

ROLLBACK;
\echo 'Tous les tests de l''audit interne (SQL) sont passés.'
