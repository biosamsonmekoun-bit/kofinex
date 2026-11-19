-- =====================================================================
-- Tests migration 0007 : socle commun d'audit (accès, indépendance, signatures, revue, circuit, gel).
-- =====================================================================
\set QUIET on
BEGIN;
CREATE OR REPLACE FUNCTION pg_temp.ok(cond boolean, label text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  IF cond IS DISTINCT FROM true THEN RAISE EXCEPTION 'ÉCHEC : %', label; END IF;
  RAISE NOTICE 'ok - %', label;
END $$;
CREATE OR REPLACE FUNCTION pg_temp.fails(q text, label text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  BEGIN EXECUTE q; EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'ok - % (refusé : %)', label, SQLERRM; RETURN; END;
  RAISE EXCEPTION 'ÉCHEC : % (aucune erreur levée)', label;
END $$;
CREATE OR REPLACE FUNCTION pg_temp.act_as(uid uuid) RETURNS void LANGUAGE sql AS $$
  SELECT set_config('request.jwt.claims', json_build_object('sub', uid, 'role', 'authenticated')::text, true);
$$;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA pg_temp TO authenticated;

-- a: alice (propriétaire) ; 1: mona (manager, créatrice) ; 2: paul (associé) ; 3: ines (chef de mission) ;
-- 4: sam (assistant) ; 5: quentin (revue qualité) ; 6: olga (observatrice) ; 7: aude (audité) ; b: bob (autre organisation)
INSERT INTO auth.users (id, email) VALUES
  ('a0000000-0000-0000-0000-00000000000a', 'alice@a.test'), ('a1000000-0000-0000-0000-000000000001', 'mona@a.test'),
  ('a2000000-0000-0000-0000-000000000002', 'paul@a.test'), ('a3000000-0000-0000-0000-000000000003', 'ines@a.test'),
  ('a4000000-0000-0000-0000-000000000004', 'sam@a.test'), ('a5000000-0000-0000-0000-000000000005', 'quentin@a.test'),
  ('a6000000-0000-0000-0000-000000000006', 'olga@a.test'), ('a7000000-0000-0000-0000-000000000007', 'aude@a.test'),
  ('b0000000-0000-0000-0000-00000000000b', 'bob@b.test');
INSERT INTO public.accounting_frameworks (id, code, name) VALUES ('f0000000-0000-0000-0000-0000000000f7', 'TEST_FW7', 'Test');

SET LOCAL ROLE authenticated;
SELECT pg_temp.act_as('a0000000-0000-0000-0000-00000000000a');
INSERT INTO public.organizations (id, name, slug, created_by)
VALUES ('10000000-0000-0000-0000-00000000007a', 'Cabinet A', 'cab-a-au', 'a0000000-0000-0000-0000-00000000000a');
INSERT INTO public.organization_members (organization_id, user_id, role)
SELECT '10000000-0000-0000-0000-00000000007a', u, 'member' FROM unnest(ARRAY[
  'a1000000-0000-0000-0000-000000000001','a2000000-0000-0000-0000-000000000002','a3000000-0000-0000-0000-000000000003',
  'a4000000-0000-0000-0000-000000000004','a5000000-0000-0000-0000-000000000005','a6000000-0000-0000-0000-000000000006',
  'a7000000-0000-0000-0000-000000000007']::uuid[]) u;
INSERT INTO public.companies (id, organization_id, name, framework_id, created_by)
VALUES ('20000000-0000-0000-0000-00000000007a', '10000000-0000-0000-0000-00000000007a', 'Client X',
        'f0000000-0000-0000-0000-0000000000f7', 'a0000000-0000-0000-0000-00000000000a');
INSERT INTO public.company_members (organization_id, company_id, user_id, role) VALUES
  ('10000000-0000-0000-0000-00000000007a', '20000000-0000-0000-0000-00000000007a', 'a1000000-0000-0000-0000-000000000001', 'auditor');

-- ------------------------------------------------------- méthodologie de l'organisation
INSERT INTO public.methodology_versions (id, organization_id, kind, name, version_label, source_reference, created_by)
VALUES ('40000000-0000-0000-0000-00000000007a', '10000000-0000-0000-0000-00000000007a', 'audit', 'Méthode test', 'v1',
        'Méthodologie FICTIVE de test', 'a0000000-0000-0000-0000-00000000000a');
INSERT INTO public.methodology_items (version_id, item_type, code, label, content) VALUES
  ('40000000-0000-0000-0000-00000000007a', 'assertion', 'EX', 'Existence (test)', '{}'),
  ('40000000-0000-0000-0000-00000000007a', 'risk_scale', 'GRILLE', 'Grille test', '{"likelihood":[1,2,3],"impact":[1,2,3]}');
UPDATE public.methodology_versions SET status = 'published', published_at = now(), published_by = 'a0000000-0000-0000-0000-00000000000a'
 WHERE id = '40000000-0000-0000-0000-00000000007a';
SELECT pg_temp.fails($q$INSERT INTO public.methodology_items (version_id, item_type, code, label)
  VALUES ('40000000-0000-0000-0000-00000000007a', 'assertion', 'CO', 'x')$q$, 'méthodologie publiée : éléments figés');

SELECT pg_temp.act_as('a1000000-0000-0000-0000-000000000001');
SELECT pg_temp.fails($q$INSERT INTO public.methodology_versions (organization_id, kind, name, version_label, source_reference, created_by)
  VALUES ('10000000-0000-0000-0000-00000000007a', 'audit', 'x', 'x', 'x', 'a1000000-0000-0000-0000-000000000001')$q$,
  'membre non administrateur : méthodologie non modifiable');

-- ------------------------------------------------------- création, équipe, indépendance
INSERT INTO public.engagements (id, organization_id, company_id, engagement_type, reference, name, methodology_version_id, created_by)
VALUES ('50000000-0000-0000-0000-00000000007a', '10000000-0000-0000-0000-00000000007a', '20000000-0000-0000-0000-00000000007a',
        'ic_assessment', 'CI-2025-01', 'Évaluation du contrôle interne 2025', '40000000-0000-0000-0000-00000000007a',
        'a1000000-0000-0000-0000-000000000001');
SELECT pg_temp.ok((SELECT role FROM public.engagement_members WHERE user_id = 'a1000000-0000-0000-0000-000000000001') = 'manager',
  'la créatrice devient manager de la mission');
SELECT pg_temp.fails($q$INSERT INTO public.engagement_members (organization_id, engagement_id, user_id, role)
  VALUES ('10000000-0000-0000-0000-00000000007a', '50000000-0000-0000-0000-00000000007a', 'a2000000-0000-0000-0000-000000000002', 'partner')$q$,
  'indépendance non confirmée : composition de l''équipe refusée');
SELECT public.confirm_independence('50000000-0000-0000-0000-00000000007a', 'Je déclare être indépendante (test).');
INSERT INTO public.engagement_members (organization_id, engagement_id, user_id, role)
SELECT '10000000-0000-0000-0000-00000000007a', '50000000-0000-0000-0000-00000000007a', u, r FROM (VALUES
  ('a2000000-0000-0000-0000-000000000002'::uuid, 'partner'), ('a3000000-0000-0000-0000-000000000003'::uuid, 'in_charge'),
  ('a4000000-0000-0000-0000-000000000004'::uuid, 'staff'), ('a5000000-0000-0000-0000-000000000005'::uuid, 'quality_reviewer'),
  ('a6000000-0000-0000-0000-000000000006'::uuid, 'observer'), ('a7000000-0000-0000-0000-000000000007'::uuid, 'auditee')) t(u, r);
SELECT pg_temp.ok(true, 'équipe constituée par la manager');
SELECT pg_temp.fails($q$UPDATE public.engagement_members SET independence_confirmed_at = now()
  WHERE user_id = 'a4000000-0000-0000-0000-000000000004'$q$, 'indépendance d''autrui non modifiable');
SELECT pg_temp.fails($q$INSERT INTO public.engagement_members (organization_id, engagement_id, user_id, role)
  VALUES ('10000000-0000-0000-0000-00000000007a', '50000000-0000-0000-0000-00000000007a', 'b0000000-0000-0000-0000-00000000000b', 'staff')$q$,
  'membre hors organisation refusé');

SELECT pg_temp.act_as('a4000000-0000-0000-0000-000000000004');
SELECT pg_temp.fails($q$INSERT INTO public.workpapers (organization_id, engagement_id, reference, title, created_by)
  VALUES ('10000000-0000-0000-0000-00000000007a', '50000000-0000-0000-0000-00000000007a', 'X', 'x', 'a4000000-0000-0000-0000-000000000004')$q$,
  'indépendance non confirmée : pas d''accès au dossier');
DO $$ DECLARE u uuid; BEGIN
  FOREACH u IN ARRAY ARRAY['a2000000-0000-0000-0000-000000000002','a3000000-0000-0000-0000-000000000003',
    'a4000000-0000-0000-0000-000000000004','a5000000-0000-0000-0000-000000000005']::uuid[] LOOP
    PERFORM pg_temp.act_as(u);
    PERFORM public.confirm_independence('50000000-0000-0000-0000-00000000007a', 'Déclaration d''indépendance (test)');
  END LOOP;
END $$;
SELECT pg_temp.ok(true, 'indépendance confirmée par chacun');

-- ------------------------------------------------------- planification
SELECT pg_temp.act_as('a3000000-0000-0000-0000-000000000003');
SELECT pg_temp.fails($q$UPDATE public.engagements SET status = 'fieldwork'$q$, 'chef de mission : lancement des travaux réservé au manager');
SELECT pg_temp.act_as('a1000000-0000-0000-0000-000000000001');
UPDATE public.engagements SET status = 'fieldwork' WHERE id = '50000000-0000-0000-0000-00000000007a';
SELECT pg_temp.ok((SELECT status FROM public.engagements) = 'fieldwork', 'manager : travaux lancés');

SELECT pg_temp.act_as('a3000000-0000-0000-0000-000000000003');
INSERT INTO public.engagement_risks (id, organization_id, engagement_id, code, title, assertion_codes, likelihood, impact, created_by)
VALUES ('60000000-0000-0000-0000-00000000007a', '10000000-0000-0000-0000-00000000007a', '50000000-0000-0000-0000-00000000007a',
        'R1', 'Risque test', ARRAY['EX'], 3, 2, 'a3000000-0000-0000-0000-000000000003');
INSERT INTO public.work_programs (id, organization_id, engagement_id, code, title)
VALUES ('61000000-0000-0000-0000-00000000007a', '10000000-0000-0000-0000-00000000007a', '50000000-0000-0000-0000-00000000007a', 'P1', 'Programme test');
SELECT pg_temp.fails($q$INSERT INTO public.procedures (organization_id, engagement_id, program_id, code, title, nature, assigned_to)
  VALUES ('10000000-0000-0000-0000-00000000007a', '50000000-0000-0000-0000-00000000007a', '61000000-0000-0000-0000-00000000007a',
          'X', 'x', 'inspection', 'a6000000-0000-0000-0000-000000000006')$q$, 'procédure affectée à un observateur refusée');
INSERT INTO public.procedures (id, organization_id, engagement_id, program_id, code, title, nature, assigned_to)
VALUES ('62000000-0000-0000-0000-00000000007a', '10000000-0000-0000-0000-00000000007a', '50000000-0000-0000-0000-00000000007a',
        '61000000-0000-0000-0000-00000000007a', 'P1.1', 'Inspection test', 'inspection', 'a4000000-0000-0000-0000-000000000004');
INSERT INTO public.procedure_risks (procedure_id, engagement_risk_id, engagement_id)
VALUES ('62000000-0000-0000-0000-00000000007a', '60000000-0000-0000-0000-00000000007a', '50000000-0000-0000-0000-00000000007a');
SELECT pg_temp.ok(true, 'risque, programme et procédure créés par le chef de mission');

-- ------------------------------------------------------- feuille de travail et signatures
SELECT pg_temp.act_as('a4000000-0000-0000-0000-000000000004');
INSERT INTO public.workpapers (id, organization_id, engagement_id, procedure_id, reference, title, work_performed, conclusion, status, created_by)
VALUES ('70000000-0000-0000-0000-00000000007a', '10000000-0000-0000-0000-00000000007a', '50000000-0000-0000-0000-00000000007a',
        '62000000-0000-0000-0000-00000000007a', 'A-100', 'Feuille test', 'Travaux (test)', 'Conclusion (test)', 'approved',
        'a4000000-0000-0000-0000-000000000004');
SELECT pg_temp.ok((SELECT status = 'draft' AND length(content_hash) = 64 FROM public.workpapers),
  'feuille créée en brouillon avec empreinte (statut fourni ignoré)');
SELECT pg_temp.fails($q$UPDATE public.workpapers SET status = 'approved'$q$, 'statut non modifiable directement');
SELECT pg_temp.fails($q$INSERT INTO public.signoffs (organization_id, engagement_id, object_type, object_id, signoff_role, user_id, member_role, content_hash)
  VALUES ('10000000-0000-0000-0000-00000000007a', '50000000-0000-0000-0000-00000000007a', 'workpaper', '70000000-0000-0000-0000-00000000007a',
          'preparer', 'a3000000-0000-0000-0000-000000000003', 'x', 'x')$q$, 'signature au nom d''autrui refusée');
INSERT INTO public.signoffs (organization_id, engagement_id, object_type, object_id, signoff_role, user_id, member_role, content_hash)
VALUES ('10000000-0000-0000-0000-00000000007a', '50000000-0000-0000-0000-00000000007a', 'workpaper', '70000000-0000-0000-0000-00000000007a',
        'preparer', 'a4000000-0000-0000-0000-000000000004', 'x', 'falsifiée');
SELECT pg_temp.ok((SELECT status FROM public.workpapers) = 'prepared'
                  AND (SELECT content_hash FROM public.signoffs) = (SELECT content_hash FROM public.workpapers),
  'préparation signée : empreinte de la base, statut « préparée »');
SELECT pg_temp.fails($q$INSERT INTO public.signoffs (organization_id, engagement_id, object_type, object_id, signoff_role, user_id, member_role, content_hash)
  VALUES ('10000000-0000-0000-0000-00000000007a', '50000000-0000-0000-0000-00000000007a', 'workpaper', '70000000-0000-0000-0000-00000000007a',
          'reviewer', 'a4000000-0000-0000-0000-000000000004', 'x', 'x')$q$, 'le préparateur ne se revoit pas');

SELECT pg_temp.act_as('a3000000-0000-0000-0000-000000000003');
INSERT INTO public.signoffs (organization_id, engagement_id, object_type, object_id, signoff_role, user_id, member_role, content_hash)
VALUES ('10000000-0000-0000-0000-00000000007a', '50000000-0000-0000-0000-00000000007a', 'workpaper', '70000000-0000-0000-0000-00000000007a',
        'reviewer', 'a3000000-0000-0000-0000-000000000003', 'x', 'x');
SELECT pg_temp.ok((SELECT status FROM public.workpapers) = 'reviewed', 'revue par le chef de mission');

SELECT pg_temp.act_as('a5000000-0000-0000-0000-000000000005');
INSERT INTO public.review_notes (id, organization_id, engagement_id, object_type, object_id, body, author_id, assigned_to)
VALUES ('80000000-0000-0000-0000-00000000007a', '10000000-0000-0000-0000-00000000007a', '50000000-0000-0000-0000-00000000007a',
        'workpaper', '70000000-0000-0000-0000-00000000007a', 'Préciser l''échantillon (test).',
        'a5000000-0000-0000-0000-000000000005', 'a4000000-0000-0000-0000-000000000004');
SELECT pg_temp.act_as('a1000000-0000-0000-0000-000000000001');
SELECT pg_temp.fails($q$INSERT INTO public.signoffs (organization_id, engagement_id, object_type, object_id, signoff_role, user_id, member_role, content_hash)
  VALUES ('10000000-0000-0000-0000-00000000007a', '50000000-0000-0000-0000-00000000007a', 'workpaper', '70000000-0000-0000-0000-00000000007a',
          'approver', 'a1000000-0000-0000-0000-000000000001', 'x', 'x')$q$, 'approbation refusée : note de revue ouverte');
SELECT pg_temp.act_as('a4000000-0000-0000-0000-000000000004');
SELECT pg_temp.fails($q$UPDATE public.review_notes SET status = 'closed'$q$, 'l''assistant ne clôt pas la note du réviseur');
UPDATE public.review_notes SET status = 'answered', response = 'Échantillon précisé (test).';
SELECT pg_temp.act_as('a5000000-0000-0000-0000-000000000005');
UPDATE public.review_notes SET status = 'closed';
SELECT pg_temp.ok((SELECT status FROM public.review_notes) = 'closed', 'note répondue puis close par son auteur');
SELECT pg_temp.fails($q$DELETE FROM public.review_notes$q$, 'une note ne se supprime pas');
SELECT pg_temp.act_as('a1000000-0000-0000-0000-000000000001');
INSERT INTO public.signoffs (organization_id, engagement_id, object_type, object_id, signoff_role, user_id, member_role, content_hash)
VALUES ('10000000-0000-0000-0000-00000000007a', '50000000-0000-0000-0000-00000000007a', 'workpaper', '70000000-0000-0000-0000-00000000007a',
        'approver', 'a1000000-0000-0000-0000-000000000001', 'x', 'x');
SELECT pg_temp.ok((SELECT status FROM public.workpapers) = 'approved', 'feuille approuvée par la manager');

-- modification après signature : retour en brouillon, signatures révoquées
SELECT pg_temp.act_as('a4000000-0000-0000-0000-000000000004');
UPDATE public.workpapers SET work_performed = 'Travaux complétés (test)';
SELECT pg_temp.ok((SELECT status = 'draft' AND version = 2 FROM public.workpapers)
                  AND (SELECT count(*) FROM public.signoffs WHERE revoked_at IS NULL) = 0,
  'modification après signature : brouillon, version 2, signatures révoquées');
SELECT pg_temp.fails($q$DELETE FROM public.signoffs$q$, 'une signature ne se supprime pas');

-- nouvelle chaîne de signatures, puis révocation de la revue par le réviseur
INSERT INTO public.signoffs (organization_id, engagement_id, object_type, object_id, signoff_role, user_id, member_role, content_hash)
VALUES ('10000000-0000-0000-0000-00000000007a', '50000000-0000-0000-0000-00000000007a', 'workpaper', '70000000-0000-0000-0000-00000000007a',
        'preparer', 'a4000000-0000-0000-0000-000000000004', 'x', 'x');
SELECT pg_temp.act_as('a3000000-0000-0000-0000-000000000003');
INSERT INTO public.signoffs (organization_id, engagement_id, object_type, object_id, signoff_role, user_id, member_role, content_hash)
VALUES ('10000000-0000-0000-0000-00000000007a', '50000000-0000-0000-0000-00000000007a', 'workpaper', '70000000-0000-0000-0000-00000000007a',
        'reviewer', 'a3000000-0000-0000-0000-000000000003', 'x', 'x');
UPDATE public.signoffs SET revoked_at = now(), revoked_reason = 'Revue à reprendre (test)'
 WHERE signoff_role = 'reviewer' AND revoked_at IS NULL;
SELECT pg_temp.ok((SELECT status FROM public.workpapers) = 'prepared', 'revue révoquée : feuille de nouveau « préparée »');
INSERT INTO public.signoffs (organization_id, engagement_id, object_type, object_id, signoff_role, user_id, member_role, content_hash)
VALUES ('10000000-0000-0000-0000-00000000007a', '50000000-0000-0000-0000-00000000007a', 'workpaper', '70000000-0000-0000-0000-00000000007a',
        'reviewer', 'a3000000-0000-0000-0000-000000000003', 'x', 'x');

-- ------------------------------------------------------- éléments probants
SELECT pg_temp.act_as('a4000000-0000-0000-0000-000000000004');
INSERT INTO public.evidence_items (id, organization_id, engagement_id, kind, title, source, snapshot, sha256, uploaded_by)
VALUES ('90000000-0000-0000-0000-00000000007a', '10000000-0000-0000-0000-00000000007a', '50000000-0000-0000-0000-00000000007a',
        'snapshot', 'Extrait de balance (test)', 'platform', '{"rows": []}', repeat('a', 64), 'a4000000-0000-0000-0000-000000000004');
SELECT pg_temp.fails($q$UPDATE public.evidence_items SET sha256 = repeat('b', 64)$q$, 'élément probant : contenu immuable');
UPDATE public.evidence_items SET description = 'Description ajoutée (test)';
SELECT pg_temp.fails($q$INSERT INTO public.evidence_links (engagement_id, evidence_id, object_type, object_id)
  VALUES ('50000000-0000-0000-0000-00000000007a', '90000000-0000-0000-0000-00000000007a', 'workpaper', '70000000-0000-0000-0000-00000000007a')$q$,
  'lien vers une feuille signée refusé');
INSERT INTO public.evidence_links (engagement_id, evidence_id, object_type, object_id)
VALUES ('50000000-0000-0000-0000-00000000007a', '90000000-0000-0000-0000-00000000007a', 'procedure', '62000000-0000-0000-0000-00000000007a');
SELECT pg_temp.ok(true, 'élément rattaché à la procédure');

RESET ROLE;
SELECT set_config('request.jwt.claims', '', true);
SELECT pg_temp.fails($q$INSERT INTO public.signoffs (organization_id, engagement_id, object_type, object_id, signoff_role, user_id, member_role, content_hash)
  VALUES ('10000000-0000-0000-0000-00000000007a', '50000000-0000-0000-0000-00000000007a', 'workpaper', '70000000-0000-0000-0000-00000000007a',
          'approver', 'a1000000-0000-0000-0000-000000000001', 'x', 'x')$q$, 'sans utilisateur authentifié (service, IA) : signature impossible');
SELECT pg_temp.fails($q$INSERT INTO public.evidence_items (organization_id, engagement_id, kind, title, source, snapshot, sha256, uploaded_by)
  VALUES ('10000000-0000-0000-0000-00000000007a', '50000000-0000-0000-0000-00000000007a', 'snapshot', 'x', 'platform', '{}',
          repeat('c', 64), 'a4000000-0000-0000-0000-000000000004')$q$, 'sans utilisateur authentifié : élément probant impossible');
SET LOCAL ROLE authenticated;

-- ------------------------------------------------------- visibilité
SELECT pg_temp.act_as('a7000000-0000-0000-0000-000000000007');
SELECT pg_temp.ok((SELECT count(*) FROM public.engagements) = 1 AND (SELECT count(*) FROM public.workpapers) = 0
                  AND (SELECT count(*) FROM public.evidence_items) = 0, 'audité : en-tête visible, dossier invisible');
SELECT pg_temp.act_as('a6000000-0000-0000-0000-000000000006');
SELECT pg_temp.ok((SELECT count(*) FROM public.workpapers) = 1, 'observateur : dossier lisible');
SELECT pg_temp.fails($q$INSERT INTO public.review_notes (organization_id, engagement_id, object_type, object_id, body, author_id)
  VALUES ('10000000-0000-0000-0000-00000000007a', '50000000-0000-0000-0000-00000000007a', 'engagement',
          '50000000-0000-0000-0000-00000000007a', 'x', 'a6000000-0000-0000-0000-000000000006')$q$, 'observateur : aucune écriture');
SELECT pg_temp.act_as('a0000000-0000-0000-0000-00000000000a');
SELECT pg_temp.ok((SELECT count(*) FROM public.engagements) = 1 AND (SELECT count(*) FROM public.workpapers) = 0,
  'administrateur non membre : en-tête visible (affectations), dossier invisible');
SELECT pg_temp.act_as('b0000000-0000-0000-0000-00000000000b');
SELECT pg_temp.ok((SELECT count(*) FROM public.engagements) + (SELECT count(*) FROM public.engagement_members)
                  + (SELECT count(*) FROM public.signoffs) = 0, 'autre organisation : rien de visible');

-- ------------------------------------------------------- circuit jusqu'à l'émission
SELECT pg_temp.act_as('a1000000-0000-0000-0000-000000000001');
INSERT INTO public.signoffs (organization_id, engagement_id, object_type, object_id, signoff_role, user_id, member_role, content_hash)
VALUES ('10000000-0000-0000-0000-00000000007a', '50000000-0000-0000-0000-00000000007a', 'workpaper', '70000000-0000-0000-0000-00000000007a',
        'approver', 'a1000000-0000-0000-0000-000000000001', 'x', 'x');
UPDATE public.engagements SET status = 'review';
UPDATE public.engagements SET status = 'reporting';
SELECT pg_temp.fails($q$UPDATE public.engagements SET status = 'issued'$q$, 'émission réservée à l''associé');
SELECT pg_temp.act_as('a2000000-0000-0000-0000-000000000002');
SELECT pg_temp.fails($q$UPDATE public.engagements SET status = 'issued'$q$, 'émission refusée sans revue qualité ni approbation');
SELECT pg_temp.fails($q$INSERT INTO public.signoffs (organization_id, engagement_id, object_type, object_id, signoff_role, user_id, member_role, content_hash)
  VALUES ('10000000-0000-0000-0000-00000000007a', '50000000-0000-0000-0000-00000000007a', 'engagement', '50000000-0000-0000-0000-00000000007a',
          'quality_reviewer', 'a2000000-0000-0000-0000-000000000002', 'x', 'x')$q$, 'revue qualité : pas par l''associé');
SELECT pg_temp.act_as('a5000000-0000-0000-0000-000000000005');
INSERT INTO public.signoffs (organization_id, engagement_id, object_type, object_id, signoff_role, user_id, member_role, content_hash)
VALUES ('10000000-0000-0000-0000-00000000007a', '50000000-0000-0000-0000-00000000007a', 'engagement', '50000000-0000-0000-0000-00000000007a',
        'quality_reviewer', 'a5000000-0000-0000-0000-000000000005', 'x', 'x');
SELECT pg_temp.act_as('a2000000-0000-0000-0000-000000000002');
INSERT INTO public.signoffs (organization_id, engagement_id, object_type, object_id, signoff_role, user_id, member_role, content_hash)
VALUES ('10000000-0000-0000-0000-00000000007a', '50000000-0000-0000-0000-00000000007a', 'engagement', '50000000-0000-0000-0000-00000000007a',
        'approver', 'a2000000-0000-0000-0000-000000000002', 'x', 'x');
UPDATE public.engagements SET status = 'issued';
SELECT pg_temp.ok((SELECT status = 'issued' AND issued_by = 'a2000000-0000-0000-0000-000000000002' FROM public.engagements),
  'mission émise par l''associé');

SELECT pg_temp.act_as('a4000000-0000-0000-0000-000000000004');
SELECT pg_temp.fails($q$UPDATE public.workpapers SET conclusion = 'autre'$q$, 'mission émise : dossier figé');
SELECT pg_temp.fails($q$INSERT INTO public.evidence_items (organization_id, engagement_id, kind, title, source, snapshot, sha256, uploaded_by)
  VALUES ('10000000-0000-0000-0000-00000000007a', '50000000-0000-0000-0000-00000000007a', 'snapshot', 'x', 'platform', '{}',
          repeat('d', 64), 'a4000000-0000-0000-0000-000000000004')$q$, 'mission émise : aucun nouvel élément');

SELECT pg_temp.act_as('a1000000-0000-0000-0000-000000000001');
UPDATE public.engagements SET status = 'archived';
SELECT pg_temp.fails($q$UPDATE public.engagements SET status = 'reporting', reopen_reason = 'Erreur matérielle constatée (test)'$q$,
  'réouverture refusée à la manager');
SELECT pg_temp.act_as('a2000000-0000-0000-0000-000000000002');
SELECT pg_temp.fails($q$UPDATE public.engagements SET status = 'reporting'$q$, 'réouverture sans motif refusée');
UPDATE public.engagements SET status = 'reporting', reopen_reason = 'Erreur matérielle constatée (test)';
SELECT pg_temp.ok((SELECT status = 'reporting' AND reopened_by IS NOT NULL FROM public.engagements)
                  AND (SELECT count(*) FROM public.signoffs WHERE object_type = 'engagement' AND revoked_at IS NULL) = 0,
  'réouverture motivée par l''associé : signatures de mission révoquées');

ROLLBACK;
\echo 'Tous les tests du socle d''audit (SQL) sont passés.'
