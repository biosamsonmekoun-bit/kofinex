-- =====================================================================
-- Tests migration 0012 : intelligence artificielle (acteur IA, réglages, messages, commentaires, suggestions,
-- provenance, isolation). L'IA propose, un humain décide.
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
CREATE OR REPLACE FUNCTION pg_temp.ai(on_ boolean) RETURNS void LANGUAGE sql AS $$
  SELECT set_config('kofinex.actor', CASE WHEN on_ THEN 'ai' ELSE '' END, true);
$$;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA pg_temp TO authenticated;

-- a : alice (propriétaire) ; c : carl (comptable de l'entité) ; v : vera (lectrice de l'entité)
-- 1 mona (manager) ; 4 sam (auditeur) ; 5 aude (auditée) ; 6 olga (observatrice) ; b : bob (autre organisation)
INSERT INTO auth.users (id, email) VALUES
  ('e0000000-0000-0000-0000-00000000000a', 'alice@ai.test'), ('e0000000-0000-0000-0000-00000000000c', 'carl@ai.test'),
  ('e0000000-0000-0000-0000-00000000000d', 'vera@ai.test'), ('e1000000-0000-0000-0000-000000000001', 'mona@ai.test'),
  ('e4000000-0000-0000-0000-000000000004', 'sam@ai.test'), ('e5000000-0000-0000-0000-000000000005', 'aude@ai.test'),
  ('e6000000-0000-0000-0000-000000000006', 'olga@ai.test'), ('eb000000-0000-0000-0000-00000000000b', 'bob@ab.test');
INSERT INTO public.accounting_frameworks (id, code, name) VALUES ('f0000000-0000-0000-0000-0000000000fa', 'TEST_FWA', 'Test');

SET LOCAL session_replication_role = replica;
INSERT INTO public.profiles (id, email) SELECT id, email FROM auth.users WHERE email LIKE '%@a_.test' ON CONFLICT DO NOTHING;
INSERT INTO public.organizations (id, name, slug, created_by) VALUES
  ('1a000000-0000-0000-0000-00000000000a', 'Groupe IA', 'grp-ai', 'e0000000-0000-0000-0000-00000000000a'),
  ('1a000000-0000-0000-0000-00000000000b', 'Autre IA', 'autre-ai', 'eb000000-0000-0000-0000-00000000000b');
INSERT INTO public.organization_members (organization_id, user_id, role) VALUES
  ('1a000000-0000-0000-0000-00000000000a', 'e0000000-0000-0000-0000-00000000000a', 'owner'),
  ('1a000000-0000-0000-0000-00000000000b', 'eb000000-0000-0000-0000-00000000000b', 'owner');
INSERT INTO public.organization_members (organization_id, user_id, role)
SELECT '1a000000-0000-0000-0000-00000000000a', u, 'member' FROM unnest(ARRAY[
  'e0000000-0000-0000-0000-00000000000c','e0000000-0000-0000-0000-00000000000d','e1000000-0000-0000-0000-000000000001',
  'e4000000-0000-0000-0000-000000000004','e5000000-0000-0000-0000-000000000005','e6000000-0000-0000-0000-000000000006']::uuid[]) u;
INSERT INTO public.companies (id, organization_id, name, framework_id, created_by) VALUES
  ('2a000000-0000-0000-0000-00000000000a', '1a000000-0000-0000-0000-00000000000a', 'Filiale IA',
   'f0000000-0000-0000-0000-0000000000fa', 'e0000000-0000-0000-0000-00000000000a');
INSERT INTO public.company_members (organization_id, company_id, user_id, role) VALUES
  ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', 'e0000000-0000-0000-0000-00000000000c', 'accountant'),
  ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', 'e0000000-0000-0000-0000-00000000000d', 'viewer');
INSERT INTO public.fiscal_years (id, organization_id, company_id, label, start_date, end_date, created_by) VALUES
  ('3a000000-0000-0000-0000-00000000000a', '1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
   '2025', '2025-01-01', '2025-12-31', 'e0000000-0000-0000-0000-00000000000a');
INSERT INTO public.financial_analyses (id, organization_id, company_id, fiscal_year_id, analysis_type, engine_version, status, started_by)
VALUES ('4a000000-0000-0000-0000-00000000000a', '1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
        '3a000000-0000-0000-0000-00000000000a', 'annual', 'test', 'completed', 'e0000000-0000-0000-0000-00000000000c');
INSERT INTO public.engagements (id, organization_id, company_id, engagement_type, reference, name, created_by)
VALUES ('6a000000-0000-0000-0000-00000000000a', '1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
        'internal_audit', 'IA-1', 'Audit des achats', 'e1000000-0000-0000-0000-000000000001');
INSERT INTO public.engagement_members (organization_id, engagement_id, user_id, role, independence_confirmed_at)
SELECT '1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a', u, r,
       CASE WHEN r = 'auditee' THEN NULL ELSE now() END FROM (VALUES
  ('e1000000-0000-0000-0000-000000000001'::uuid, 'manager'), ('e4000000-0000-0000-0000-000000000004'::uuid, 'staff'),
  ('e5000000-0000-0000-0000-000000000005'::uuid, 'auditee'), ('e6000000-0000-0000-0000-000000000006'::uuid, 'observer')) t(u, r);
INSERT INTO public.work_programs (id, organization_id, engagement_id, code, title) VALUES
  ('7a000000-0000-0000-0000-00000000000a', '1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a', 'P1', 'Achats');
SET LOCAL session_replication_role = origin;

SET LOCAL ROLE authenticated;

-- ------------------------------------------------------- réglages de l'organisation
SELECT pg_temp.act_as('e0000000-0000-0000-0000-00000000000c');
SELECT pg_temp.fails($q$INSERT INTO public.ai_conversations (organization_id, company_id, user_id, title)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', 'e0000000-0000-0000-0000-00000000000c', 'x')$q$,
  'IA désactivée par défaut : conversation refusée', 'non activée');
SELECT pg_temp.fails($q$INSERT INTO public.ai_settings (organization_id, enabled, allowed_uses, acceptance_note, updated_by)
  VALUES ('1a000000-0000-0000-0000-00000000000a', true, '{finance_assistant}', 'Accord de la direction', 'e0000000-0000-0000-0000-00000000000c')$q$,
  'membre : activation de l''IA refusée');
SELECT pg_temp.act_as('e0000000-0000-0000-0000-00000000000a');
SELECT pg_temp.fails($q$INSERT INTO public.ai_settings (organization_id, enabled, allowed_uses, updated_by)
  VALUES ('1a000000-0000-0000-0000-00000000000a', true, '{finance_assistant}', 'e0000000-0000-0000-0000-00000000000a')$q$,
  'activation sans acceptation motivée', 'check');
SELECT pg_temp.fails($q$INSERT INTO public.ai_settings (organization_id, enabled, allowed_uses, acceptance_note, updated_by)
  VALUES ('1a000000-0000-0000-0000-00000000000a', true, '{finance_assistant}', 'Accord de la direction générale', 'e0000000-0000-0000-0000-00000000000c')$q$,
  'réglages enregistrés au nom d''un autre', 'au nom');
SELECT pg_temp.fails($q$INSERT INTO public.ai_settings (organization_id, enabled, allowed_uses, acceptance_note, updated_by)
  VALUES ('1a000000-0000-0000-0000-00000000000a', true, '{opinion_d_audit}', 'Accord de la direction générale', 'e0000000-0000-0000-0000-00000000000a')$q$,
  'usage inconnu refusé', 'check');
INSERT INTO public.ai_settings (organization_id, enabled, allowed_uses, acceptance_note, updated_by)
VALUES ('1a000000-0000-0000-0000-00000000000a', true, '{finance_assistant,analysis_commentary,audit_risks,audit_procedures,drafting}',
        'Accord de la direction générale du 18/11/2026 (test)', 'e0000000-0000-0000-0000-00000000000a');
SELECT pg_temp.ok(public.ai_allowed('1a000000-0000-0000-0000-00000000000a', 'audit_risks')
                  AND NOT public.ai_allowed('1a000000-0000-0000-0000-00000000000a', 'anomaly_explanation'),
                  'usages autorisés un par un');
SELECT pg_temp.act_as('eb000000-0000-0000-0000-00000000000b');
SELECT pg_temp.ok((SELECT count(*) FROM public.ai_settings) = 0, 'autre organisation : réglages invisibles');

-- ------------------------------------------------------- conversation et messages
SELECT pg_temp.act_as('e0000000-0000-0000-0000-00000000000c');
INSERT INTO public.ai_conversations (id, organization_id, company_id, fiscal_year_id, analysis_id, user_id, title)
VALUES ('8a000000-0000-0000-0000-00000000000a', '1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
        '3a000000-0000-0000-0000-00000000000a', '4a000000-0000-0000-0000-00000000000a', 'e0000000-0000-0000-0000-00000000000c', 'Exercice 2025');
SELECT pg_temp.ok(true, 'comptable : conversation ouverte');
INSERT INTO public.ai_messages (organization_id, conversation_id, role, content)
VALUES ('1a000000-0000-0000-0000-00000000000a', '8a000000-0000-0000-0000-00000000000a', 'user', 'Que dire de la trésorerie ?');
SELECT pg_temp.fails($q$INSERT INTO public.ai_messages (organization_id, conversation_id, role, content, context_snapshot, validation, model)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '8a000000-0000-0000-0000-00000000000a', 'assistant', 'Réponse forgée', '{}', '{}', 'm')$q$,
  'réponse « IA » écrite hors traitement du modèle', 'traitement du modèle');
SELECT pg_temp.ai(true);
SELECT pg_temp.fails($q$INSERT INTO public.ai_messages (organization_id, conversation_id, role, content)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '8a000000-0000-0000-0000-00000000000a', 'assistant', 'Sans contexte')$q$,
  'réponse IA sans contexte ni contrôle des chiffres', 'contexte');
INSERT INTO public.ai_messages (id, organization_id, conversation_id, role, content, context_snapshot, validation, model, prompt_version)
VALUES ('8b000000-0000-0000-0000-00000000000a', '1a000000-0000-0000-0000-00000000000a', '8a000000-0000-0000-0000-00000000000a',
        'assistant', 'La trésorerie nette est de 1 200.', '{"facts":[{"ref":"F1","value":"1200"}]}', '{"status":"verified"}', 'modele-test', 'KOFINEX-AI-1');
SELECT pg_temp.ok(true, 'réponse IA enregistrée sous l''acteur IA, avec contexte et contrôle');
SELECT pg_temp.fails($q$INSERT INTO public.ai_messages (organization_id, conversation_id, role, content)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '8a000000-0000-0000-0000-00000000000a', 'user', 'Question forgée par l''IA')$q$,
  'acteur IA : question au nom de l''utilisateur refusée', 'utilisateur');
SELECT pg_temp.ai(false);
UPDATE public.ai_messages SET content = 'Corrigé' WHERE id = '8b000000-0000-0000-0000-00000000000a';
SELECT pg_temp.ok((SELECT content FROM public.ai_messages WHERE id = '8b000000-0000-0000-0000-00000000000a') = 'La trésorerie nette est de 1 200.',
                  'message IA : non modifiable (RLS)');
RESET ROLE;
SELECT pg_temp.fails($q$UPDATE public.ai_messages SET content = 'Corrigé' WHERE id = '8b000000-0000-0000-0000-00000000000a'$q$,
  'message IA : non modifiable même hors RLS (déclencheur)', 'conservé');
SET LOCAL ROLE authenticated;
SELECT pg_temp.fails($q$DELETE FROM public.ai_conversations WHERE id = '8a000000-0000-0000-0000-00000000000a'$q$,
  'conversation : messages conservés (suppression refusée)', 'conservé');
SELECT pg_temp.act_as('e0000000-0000-0000-0000-00000000000d');
SELECT pg_temp.ok((SELECT count(*) FROM public.ai_messages) = 0, 'conversation privée : autre utilisateur de l''entité, aucun message');
SELECT pg_temp.fails($q$INSERT INTO public.ai_conversations (organization_id, company_id, user_id, title)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', 'e0000000-0000-0000-0000-00000000000d', 'x')$q$,
  'lecteur de l''entité : pas d''assistant');

-- ------------------------------------------------------- l'acteur IA n'écrit aucune table métier
SELECT pg_temp.act_as('e0000000-0000-0000-0000-00000000000c');
SELECT pg_temp.ai(true);
SELECT pg_temp.fails($q$UPDATE public.fiscal_years SET label = '2025 (IA)'$q$, 'acteur IA : exercice non modifiable', 'IA');
SELECT pg_temp.fails($q$INSERT INTO public.cost_centers (organization_id, company_id, code, name)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', 'X', 'X')$q$,
  'acteur IA : aucune création dans les tables métier', 'IA');
SELECT pg_temp.act_as('e4000000-0000-0000-0000-000000000004');
SELECT pg_temp.fails($q$INSERT INTO public.evidence_items (organization_id, engagement_id, kind, title, source, obtained_on, sha256, snapshot, uploaded_by)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a', 'snapshot', 'Preuve IA', 'ia', '2026-11-18',
          repeat('a', 64), '{}', 'e4000000-0000-0000-0000-000000000004')$q$,
  'acteur IA : aucun élément probant', 'IA');
SELECT pg_temp.fails($q$INSERT INTO public.signoffs (organization_id, engagement_id, object_type, object_id, signoff_role, user_id, content_hash)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a', 'engagement', '6a000000-0000-0000-0000-00000000000a',
          'preparer', 'e4000000-0000-0000-0000-000000000004', repeat('b', 64))$q$,
  'acteur IA : aucune signature', 'IA');
SELECT pg_temp.act_as('e1000000-0000-0000-0000-000000000001');
SELECT pg_temp.ok((SELECT count(*) FROM public.work_programs) = 1, 'manager : programme visible (cible du test suivant)');
SELECT pg_temp.fails($q$UPDATE public.work_programs SET objective = 'Objectif rédigé par l''IA'$q$, 'acteur IA : programme non modifiable', 'IA');
SELECT pg_temp.fails($q$UPDATE public.engagements SET status = 'fieldwork'$q$, 'acteur IA : aucune phase de mission changée', 'IA');
SELECT pg_temp.act_as('e4000000-0000-0000-0000-000000000004');
SELECT pg_temp.fails($q$INSERT INTO public.engagement_risks (organization_id, engagement_id, code, title, origin)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a', 'RX', 'Risque direct', 'manual')$q$,
  'acteur IA : aucun risque créé directement', 'IA');

-- ------------------------------------------------------- suggestions
SELECT pg_temp.fails($q$INSERT INTO public.ai_suggestions (organization_id, company_id, engagement_id, kind, payload, context_snapshot,
  validation, model, prompt_version, requested_by)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a',
          'anomaly_explanation', '{"text":"x"}', '{}', '{}', 'm', 'v', 'e4000000-0000-0000-0000-000000000004')$q$,
  'usage non activé : suggestion refusée', 'non activée');
INSERT INTO public.ai_suggestions (id, organization_id, company_id, engagement_id, kind, payload, sources, context_snapshot, validation,
                                   model, prompt_version, requested_by)
VALUES ('9a000000-0000-0000-0000-000000000001', '1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
        '6a000000-0000-0000-0000-00000000000a', 'engagement_risk',
        '{"code":"R-IA1","title":"Fractionnement de commandes","description":"Commandes sous le seuil d''approbation"}',
        '["F1"]', '{"facts":[]}', '{"status":"verified"}', 'modele-test', 'KOFINEX-AI-1', 'e4000000-0000-0000-0000-000000000004'),
       ('9a000000-0000-0000-0000-000000000002', '1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
        '6a000000-0000-0000-0000-00000000000a', 'procedure', '{"code":"PR-IA1","title":"Revue des commandes fractionnées","nature":"detail_test"}',
        '[]', '{"facts":[]}', '{"status":"verified"}', 'modele-test', 'KOFINEX-AI-1', 'e4000000-0000-0000-0000-000000000004'),
       ('9a000000-0000-0000-0000-000000000003', '1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
        '6a000000-0000-0000-0000-00000000000a', 'finding_draft', '{"reference":"C-IA1","title":"Commandes non approuvées","condition":"x","criteria":"y"}',
        '[]', '{"facts":[]}', '{"status":"warning"}', 'modele-test', 'KOFINEX-AI-1', 'e4000000-0000-0000-0000-000000000004');
SELECT pg_temp.ok(true, 'suggestions enregistrées sous l''acteur IA, en attente');
SELECT pg_temp.fails($q$UPDATE public.ai_suggestions SET status = 'accepted', decided_by = 'e4000000-0000-0000-0000-000000000004'
  WHERE id = '9a000000-0000-0000-0000-000000000001'$q$, 'acteur IA : acceptation de sa propre suggestion refusée', 'humaine');
SELECT pg_temp.ai(false);
SELECT pg_temp.fails($q$INSERT INTO public.ai_suggestions (organization_id, company_id, engagement_id, kind, payload, context_snapshot,
  validation, model, prompt_version, requested_by)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a',
          'engagement_risk', '{"title":"x"}', '{}', '{}', 'm', 'v', 'e4000000-0000-0000-0000-000000000004')$q$,
  'suggestion « IA » forgée hors traitement du modèle', 'traitement du modèle');
SELECT pg_temp.fails($q$UPDATE public.ai_suggestions SET payload = '{"title":"modifié"}' WHERE id = '9a000000-0000-0000-0000-000000000001'$q$,
  'proposition du modèle : non modifiable', 'ne changent pas');
SELECT pg_temp.fails($q$UPDATE public.ai_suggestions SET status = 'rejected', decided_by = 'e4000000-0000-0000-0000-000000000004'
  WHERE id = '9a000000-0000-0000-0000-000000000002'$q$, 'rejet sans motif', 'check');
SELECT pg_temp.fails($q$UPDATE public.ai_suggestions SET status = 'accepted', decided_by = 'e1000000-0000-0000-0000-000000000001'
  WHERE id = '9a000000-0000-0000-0000-000000000001'$q$, 'décision enregistrée au nom d''un autre', 'au nom');

-- provenance : objet créé seulement après acceptation, par le décideur (la manager, qui planifie)
SELECT pg_temp.act_as('e1000000-0000-0000-0000-000000000001');
SELECT pg_temp.fails($q$INSERT INTO public.engagement_risks (organization_id, engagement_id, code, title, origin, ai_suggestion_id)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a', 'R-IA1', 'Fractionnement', 'ai_suggestion',
          '9a000000-0000-0000-0000-000000000001')$q$, 'risque IA avant acceptation', 'acceptée');
UPDATE public.ai_suggestions SET status = 'accepted', decided_by = 'e1000000-0000-0000-0000-000000000001',
  accepted_payload = '{"code":"R-IA1","title":"Fractionnement de commandes (relu)"}' WHERE id = '9a000000-0000-0000-0000-000000000001';
SELECT pg_temp.ok((SELECT decided_at IS NOT NULL FROM public.ai_suggestions WHERE id = '9a000000-0000-0000-0000-000000000001'),
                  'manager : suggestion acceptée, date enregistrée');
SELECT pg_temp.fails($q$INSERT INTO public.engagement_risks (organization_id, engagement_id, code, title, origin, ai_suggestion_id, likelihood, impact)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a', 'R-IA1', 'Fractionnement', 'ai_suggestion',
          '9a000000-0000-0000-0000-000000000001', 2, 2)$q$, 'risque IA coté d''office', 'cotation');
SELECT pg_temp.fails($q$INSERT INTO public.procedures (organization_id, engagement_id, program_id, code, title, nature, origin, ai_suggestion_id)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a', '7a000000-0000-0000-0000-00000000000a',
          'PR-X', 'X', 'other', 'ai_suggestion', '9a000000-0000-0000-0000-000000000001')$q$,
  'provenance : suggestion d''une autre nature', 'même nature');
INSERT INTO public.engagement_risks (id, organization_id, engagement_id, code, title, origin, ai_suggestion_id, created_by)
VALUES ('aa000000-0000-0000-0000-000000000001', '1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a',
        'R-IA1', 'Fractionnement de commandes (relu)', 'ai_suggestion', '9a000000-0000-0000-0000-000000000001', 'e1000000-0000-0000-0000-000000000001');
UPDATE public.ai_suggestions SET created_object_type = 'engagement_risks', created_object_id = 'aa000000-0000-0000-0000-000000000001'
 WHERE id = '9a000000-0000-0000-0000-000000000001';
SELECT pg_temp.ok((SELECT origin = 'ai_suggestion' AND likelihood IS NULL FROM public.engagement_risks WHERE id = 'aa000000-0000-0000-0000-000000000001'),
                  'risque créé depuis la suggestion : provenance conservée, cotation laissée à l''auditeur');
UPDATE public.engagement_risks SET likelihood = 2, impact = 1 WHERE id = 'aa000000-0000-0000-0000-000000000001';
SELECT pg_temp.ok(true, 'auditeur : cotation ensuite');
SELECT pg_temp.fails($q$UPDATE public.engagement_risks SET origin = 'manual', ai_suggestion_id = NULL WHERE id = 'aa000000-0000-0000-0000-000000000001'$q$,
  'provenance : non modifiable', 'non modifiable');
SELECT pg_temp.fails($q$INSERT INTO public.engagement_risks (organization_id, engagement_id, code, title, origin, ai_suggestion_id)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a', 'R-IA2', 'Doublon', 'ai_suggestion',
          '9a000000-0000-0000-0000-000000000001')$q$, 'suggestion déjà reprise : second objet refusé', 'pas encore reprise');
SELECT pg_temp.fails($q$UPDATE public.ai_suggestions SET created_object_id = NULL WHERE id = '9a000000-0000-0000-0000-000000000001'$q$,
  'suggestion décidée : figée', 'figée');
SELECT pg_temp.fails($q$INSERT INTO public.engagement_risks (organization_id, engagement_id, code, title, ai_suggestion_id)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a', 'R-M', 'Manuel', '9a000000-0000-0000-0000-000000000001')$q$,
  'objet manuel rattaché à une suggestion', 'implique');

-- procédure : non attribuée ; constat : brouillon ; acceptation par une autre personne que le créateur
UPDATE public.ai_suggestions SET status = 'accepted', decided_by = 'e1000000-0000-0000-0000-000000000001' WHERE id = '9a000000-0000-0000-0000-000000000002';
SELECT pg_temp.act_as('e4000000-0000-0000-0000-000000000004');
SELECT pg_temp.fails($q$INSERT INTO public.procedures (organization_id, engagement_id, program_id, code, title, nature, origin, ai_suggestion_id)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a', '7a000000-0000-0000-0000-00000000000a',
          'PR-IA1', 'Revue', 'detail_test', 'ai_suggestion', '9a000000-0000-0000-0000-000000000002')$q$,
  'objet créé par un autre que le décideur', 'acceptée par vous');
SELECT pg_temp.act_as('e1000000-0000-0000-0000-000000000001');
SELECT pg_temp.fails($q$INSERT INTO public.procedures (organization_id, engagement_id, program_id, code, title, nature, origin, ai_suggestion_id, assigned_to)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a', '7a000000-0000-0000-0000-00000000000a',
          'PR-IA1', 'Revue', 'detail_test', 'ai_suggestion', '9a000000-0000-0000-0000-000000000002', 'e4000000-0000-0000-0000-000000000004')$q$,
  'procédure IA attribuée d''office', 'non attribuée');
INSERT INTO public.procedures (organization_id, engagement_id, program_id, code, title, nature, origin, ai_suggestion_id)
VALUES ('1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a', '7a000000-0000-0000-0000-00000000000a',
        'PR-IA1', 'Revue des commandes fractionnées', 'detail_test', 'ai_suggestion', '9a000000-0000-0000-0000-000000000002');
SELECT pg_temp.ok(true, 'procédure créée depuis la suggestion, non attribuée, non commencée');
SELECT pg_temp.act_as('e4000000-0000-0000-0000-000000000004');
UPDATE public.ai_suggestions SET status = 'rejected', decided_by = 'e4000000-0000-0000-0000-000000000004',
  decision_note = 'Chiffre non traçable dans la proposition' WHERE id = '9a000000-0000-0000-0000-000000000003';
SELECT pg_temp.fails($q$INSERT INTO public.findings (organization_id, engagement_id, reference, title, condition, criteria, created_by, origin, ai_suggestion_id)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a', 'C-IA1', 'x', 'x', 'y',
          'e4000000-0000-0000-0000-000000000004', 'ai_suggestion', '9a000000-0000-0000-0000-000000000003')$q$,
  'suggestion rejetée : aucun constat', 'acceptée');
SELECT pg_temp.ok((SELECT decision_note FROM public.ai_suggestions WHERE id = '9a000000-0000-0000-0000-000000000003') IS NOT NULL,
                  'rejet motivé conservé');

-- accès
SELECT pg_temp.act_as('e6000000-0000-0000-0000-000000000006');
SELECT pg_temp.ok((SELECT count(*) FROM public.ai_suggestions) = 3, 'observatrice : suggestions consultables');
UPDATE public.ai_suggestions SET decision_note = 'Avis de l''observatrice' WHERE id = '9a000000-0000-0000-0000-000000000003';
SELECT pg_temp.ok((SELECT decision_note FROM public.ai_suggestions WHERE id = '9a000000-0000-0000-0000-000000000003')
                  = 'Chiffre non traçable dans la proposition', 'observatrice : aucune décision ni modification (RLS)');
SELECT pg_temp.ok((SELECT count(*) FROM public.ai_suggestions WHERE status = 'pending') = 0, 'aucune suggestion en attente restante');
SELECT pg_temp.act_as('e5000000-0000-0000-0000-000000000005');
SELECT pg_temp.ok((SELECT count(*) FROM public.ai_suggestions) = 0, 'audité : aucune suggestion visible');
SELECT pg_temp.ai(true);
SELECT pg_temp.fails($q$INSERT INTO public.ai_suggestions (organization_id, company_id, engagement_id, kind, payload, context_snapshot,
  validation, model, prompt_version, requested_by)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a',
          'engagement_risk', '{"title":"x"}', '{}', '{}', 'm', 'v', 'e5000000-0000-0000-0000-000000000005')$q$,
  'audité : aucune suggestion demandée');
SELECT pg_temp.ai(false);
SELECT pg_temp.act_as('eb000000-0000-0000-0000-00000000000b');
SELECT pg_temp.ok((SELECT count(*) FROM public.ai_suggestions) = 0 AND (SELECT count(*) FROM public.ai_conversations) = 0,
                  'autre organisation : aucune donnée IA visible');

-- ------------------------------------------------------- commentaires d'analyse
SELECT pg_temp.act_as('e0000000-0000-0000-0000-00000000000c');
SELECT pg_temp.fails($q$INSERT INTO public.ai_reports (organization_id, company_id, analysis_id, section, content, context_snapshot, model,
  prompt_version, validation, created_by)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', '4a000000-0000-0000-0000-00000000000a',
          'cash', 'Commentaire forgé', '{}', 'm', 'v', '{}', 'e0000000-0000-0000-0000-00000000000c')$q$,
  'commentaire « IA » écrit hors traitement du modèle', 'traitement du modèle');
SELECT pg_temp.ai(true);
INSERT INTO public.ai_reports (id, organization_id, company_id, analysis_id, section, content, context_snapshot, model, prompt_version,
                               validation, created_by)
VALUES ('ba000000-0000-0000-0000-000000000001', '1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a',
        '4a000000-0000-0000-0000-00000000000a', 'cash', 'La trésorerie nette est positive.', '{"facts":[]}', 'modele-test', 'KOFINEX-AI-1',
        '{"status":"verified"}', 'e0000000-0000-0000-0000-00000000000c');
SELECT pg_temp.fails($q$UPDATE public.ai_reports SET status = 'reviewed', reviewed_by = 'e0000000-0000-0000-0000-00000000000c'$q$,
  'acteur IA : relecture refusée', 'humaine');
SELECT pg_temp.ai(false);
SELECT pg_temp.fails($q$UPDATE public.ai_reports SET content = 'Retouché'$q$, 'commentaire IA : contenu figé', 'figé');
SELECT pg_temp.fails($q$UPDATE public.ai_reports SET status = 'rejected', reviewed_by = 'e0000000-0000-0000-0000-00000000000c'$q$,
  'rejet de commentaire sans motif', 'motif');
UPDATE public.ai_reports SET status = 'reviewed', reviewed_by = 'e0000000-0000-0000-0000-00000000000c', review_note = 'Relu (test)';
SELECT pg_temp.ok((SELECT reviewed_at IS NOT NULL FROM public.ai_reports), 'commentaire relu par un humain, date enregistrée');
SELECT pg_temp.fails($q$UPDATE public.ai_reports SET status = 'rejected', review_note = 'Revirement'$q$, 'commentaire relu : décision unique', 'une seule');

-- ------------------------------------------------------- mission émise : plus de suggestion
RESET ROLE;
SET LOCAL session_replication_role = replica;
UPDATE public.engagements SET status = 'issued', issued_at = now() WHERE id = '6a000000-0000-0000-0000-00000000000a';
SET LOCAL session_replication_role = origin;
SET LOCAL ROLE authenticated;
SELECT pg_temp.act_as('e4000000-0000-0000-0000-000000000004');
SELECT pg_temp.ai(true);
SELECT pg_temp.fails($q$INSERT INTO public.ai_suggestions (organization_id, company_id, engagement_id, kind, payload, context_snapshot,
  validation, model, prompt_version, requested_by)
  VALUES ('1a000000-0000-0000-0000-00000000000a', '2a000000-0000-0000-0000-00000000000a', '6a000000-0000-0000-0000-00000000000a',
          'engagement_risk', '{"title":"x"}', '{}', '{}', 'm', 'v', 'e4000000-0000-0000-0000-000000000004')$q$,
  'mission émise : aucune nouvelle suggestion', 'figé');
SELECT pg_temp.ai(false);

ROLLBACK;
