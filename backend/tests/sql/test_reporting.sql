-- =====================================================================
-- Tests migration 0013 : reporting (documents figés, données validées uniquement, brouillons IA signalés,
-- modèles versionnés, accès par entreprise, contrôle interne ou dossier de mission).
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
-- document « prêt » minimal : seuls varient le type, les rattachements et les sources
CREATE OR REPLACE FUNCTION pg_temp.doc(p_type text, p_analysis uuid, p_engagement uuid, p_refs jsonb, p_ai uuid[] DEFAULT '{}',
                                       p_drafts boolean DEFAULT false, p_subtype text DEFAULT NULL, p_by uuid DEFAULT NULL) RETURNS text
LANGUAGE sql AS $$
  SELECT format($q$INSERT INTO public.generated_reports (organization_id, company_id, analysis_id, engagement_id, document_type, subtype,
    format, status, storage_path, sha256, data_sha256, content_snapshot, source_refs, filename, size_bytes, ai_report_ids,
    contains_ai_drafts, requested_by)
    VALUES ('1b000000-0000-0000-0000-00000000000a', '2b000000-0000-0000-0000-00000000000a', %L, %L, %L, %L, 'pdf', 'ready',
            'p/x.pdf', repeat('a', 64), repeat('b', 64), '{"blocks":[]}', %L, 'x.pdf', 10, %L, %L, %L)$q$,
    p_analysis, p_engagement, p_type, p_subtype, p_refs, p_ai, p_drafts,
    coalesce(p_by, (current_setting('request.jwt.claims')::json->>'sub')::uuid))
$$;
CREATE OR REPLACE FUNCTION pg_temp.run(q text) RETURNS void LANGUAGE plpgsql AS $$ BEGIN EXECUTE q; END $$;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA pg_temp TO authenticated;

-- a alice (propriétaire) ; c carl (comptable) ; v vera (lectrice) ; 1 mona (manager) ; 4 sam (auditeur) ; 5 aude (auditée) ;
-- b bob (autre organisation)
INSERT INTO auth.users (id, email) VALUES
  ('f0000000-0000-0000-0000-00000000000a', 'alice@rp.test'), ('f0000000-0000-0000-0000-00000000000c', 'carl@rp.test'),
  ('f0000000-0000-0000-0000-00000000000d', 'vera@rp.test'), ('f1000000-0000-0000-0000-000000000001', 'mona@rp.test'),
  ('f4000000-0000-0000-0000-000000000004', 'sam@rp.test'), ('f5000000-0000-0000-0000-000000000005', 'aude@rp.test'),
  ('fb000000-0000-0000-0000-00000000000b', 'bob@rq.test');
INSERT INTO public.accounting_frameworks (id, code, name) VALUES ('f0000000-0000-0000-0000-0000000000fb', 'TEST_FWB', 'Test');

SET LOCAL session_replication_role = replica;
INSERT INTO public.profiles (id, email) SELECT id, email FROM auth.users WHERE email LIKE '%@r_.test' ON CONFLICT DO NOTHING;
INSERT INTO public.organizations (id, name, slug, created_by) VALUES
  ('1b000000-0000-0000-0000-00000000000a', 'Groupe RP', 'grp-rp', 'f0000000-0000-0000-0000-00000000000a'),
  ('1b000000-0000-0000-0000-00000000000b', 'Autre RP', 'autre-rp', 'fb000000-0000-0000-0000-00000000000b');
INSERT INTO public.organization_members (organization_id, user_id, role) VALUES
  ('1b000000-0000-0000-0000-00000000000a', 'f0000000-0000-0000-0000-00000000000a', 'owner'),
  ('1b000000-0000-0000-0000-00000000000b', 'fb000000-0000-0000-0000-00000000000b', 'owner');
INSERT INTO public.organization_members (organization_id, user_id, role)
SELECT '1b000000-0000-0000-0000-00000000000a', u, 'member' FROM unnest(ARRAY[
  'f0000000-0000-0000-0000-00000000000c','f0000000-0000-0000-0000-00000000000d','f1000000-0000-0000-0000-000000000001',
  'f4000000-0000-0000-0000-000000000004','f5000000-0000-0000-0000-000000000005']::uuid[]) u;
INSERT INTO public.companies (id, organization_id, name, framework_id, created_by) VALUES
  ('2b000000-0000-0000-0000-00000000000a', '1b000000-0000-0000-0000-00000000000a', 'Filiale RP',
   'f0000000-0000-0000-0000-0000000000fb', 'f0000000-0000-0000-0000-00000000000a');
INSERT INTO public.company_members (organization_id, company_id, user_id, role) VALUES
  ('1b000000-0000-0000-0000-00000000000a', '2b000000-0000-0000-0000-00000000000a', 'f0000000-0000-0000-0000-00000000000c', 'accountant'),
  ('1b000000-0000-0000-0000-00000000000a', '2b000000-0000-0000-0000-00000000000a', 'f0000000-0000-0000-0000-00000000000d', 'viewer');
INSERT INTO public.fiscal_years (id, organization_id, company_id, label, start_date, end_date, created_by) VALUES
  ('3b000000-0000-0000-0000-00000000000a', '1b000000-0000-0000-0000-00000000000a', '2b000000-0000-0000-0000-00000000000a',
   '2025', '2025-01-01', '2025-12-31', 'f0000000-0000-0000-0000-00000000000a');
INSERT INTO public.financial_analyses (id, organization_id, company_id, fiscal_year_id, analysis_type, engine_version, status, started_by) VALUES
  ('4b000000-0000-0000-0000-00000000000a', '1b000000-0000-0000-0000-00000000000a', '2b000000-0000-0000-0000-00000000000a',
   '3b000000-0000-0000-0000-00000000000a', 'annual', 'test', 'completed', 'f0000000-0000-0000-0000-00000000000c'),
  ('4b000000-0000-0000-0000-00000000000b', '1b000000-0000-0000-0000-00000000000a', '2b000000-0000-0000-0000-00000000000a',
   '3b000000-0000-0000-0000-00000000000a', 'annual', 'test', 'failed', 'f0000000-0000-0000-0000-00000000000c');
INSERT INTO public.ai_reports (id, organization_id, company_id, analysis_id, section, content, context_snapshot, model, prompt_version, status, created_by)
SELECT ('5b000000-0000-0000-0000-00000000000' || n)::uuid, '1b000000-0000-0000-0000-00000000000a', '2b000000-0000-0000-0000-00000000000a',
       '4b000000-0000-0000-0000-00000000000a', 'cash', 'Commentaire ' || st, '{}', 'm', 'v', st, 'f0000000-0000-0000-0000-00000000000c'
  FROM (VALUES (1, 'reviewed'), (2, 'draft'), (3, 'rejected')) t(n, st);
INSERT INTO public.budgets (id, organization_id, company_id, fiscal_year_id, name, status, approved_by, approved_at, created_by) VALUES
  ('6b000000-0000-0000-0000-00000000000a', '1b000000-0000-0000-0000-00000000000a', '2b000000-0000-0000-0000-00000000000a',
   '3b000000-0000-0000-0000-00000000000a', 'Budget 2025', 'approved', 'f0000000-0000-0000-0000-00000000000a', now(), 'f0000000-0000-0000-0000-00000000000c');
INSERT INTO public.budgets (id, organization_id, company_id, fiscal_year_id, name, version, status, created_by) VALUES
  ('6b000000-0000-0000-0000-00000000000b', '1b000000-0000-0000-0000-00000000000a', '2b000000-0000-0000-0000-00000000000a',
   '3b000000-0000-0000-0000-00000000000a', 'Budget 2025', 2, 'draft', 'f0000000-0000-0000-0000-00000000000c');
INSERT INTO public.engagements (id, organization_id, company_id, engagement_type, reference, name, created_by) VALUES
  ('7b000000-0000-0000-0000-00000000000a', '1b000000-0000-0000-0000-00000000000a', '2b000000-0000-0000-0000-00000000000a',
   'internal_audit', 'IA-RP', 'Audit des achats', 'f1000000-0000-0000-0000-000000000001'),
  ('7b000000-0000-0000-0000-00000000000b', '1b000000-0000-0000-0000-00000000000a', '2b000000-0000-0000-0000-00000000000a',
   'statutory_audit', 'CAC-RP', 'Audit légal 2025', 'f1000000-0000-0000-0000-000000000001');
INSERT INTO public.engagement_members (organization_id, engagement_id, user_id, role, independence_confirmed_at)
SELECT '1b000000-0000-0000-0000-00000000000a', e, u, r, CASE WHEN r = 'auditee' THEN NULL ELSE now() END FROM (VALUES
  ('7b000000-0000-0000-0000-00000000000a'::uuid, 'f1000000-0000-0000-0000-000000000001'::uuid, 'manager'),
  ('7b000000-0000-0000-0000-00000000000a'::uuid, 'f4000000-0000-0000-0000-000000000004'::uuid, 'staff'),
  ('7b000000-0000-0000-0000-00000000000a'::uuid, 'f5000000-0000-0000-0000-000000000005'::uuid, 'auditee'),
  ('7b000000-0000-0000-0000-00000000000b'::uuid, 'f1000000-0000-0000-0000-000000000001'::uuid, 'manager')) t(e, u, r);
INSERT INTO public.audit_reports (id, organization_id, engagement_id, version, title, overall_conclusion, status, snapshot, content_sha256,
                                  issued_by, issued_at, created_by) VALUES
  ('8b000000-0000-0000-0000-000000000001', '1b000000-0000-0000-0000-00000000000a', '7b000000-0000-0000-0000-00000000000a', 1,
   'Rapport', 'Conclusion', 'issued', '{}', repeat('c', 64), 'f1000000-0000-0000-0000-000000000001', now(), 'f1000000-0000-0000-0000-000000000001'),
  ('8b000000-0000-0000-0000-000000000002', '1b000000-0000-0000-0000-00000000000a', '7b000000-0000-0000-0000-00000000000a', 2,
   'Projet', NULL, 'draft', NULL, NULL, NULL, NULL, 'f1000000-0000-0000-0000-000000000001');
INSERT INTO public.fa_materiality (id, organization_id, engagement_id, version, benchmark_label, benchmark_source, benchmark_amount,
  overall_pct, overall_amount, performance_pct, performance_amount, trivial_pct, trivial_amount, basis, status, approved_by, approved_at, created_by)
VALUES ('9b000000-0000-0000-0000-00000000000a', '1b000000-0000-0000-0000-00000000000a', '7b000000-0000-0000-0000-00000000000b', 1,
        'Total actif', 'manual', 1000000, 1, 10000, 50, 5000, 5, 500, 'Méthodologie FICTIVE de test', 'approved',
        'f1000000-0000-0000-0000-000000000001', now(), 'f1000000-0000-0000-0000-000000000001');
SET LOCAL session_replication_role = origin;

SET LOCAL ROLE authenticated;

-- ------------------------------------------------------- rapport financier
SELECT pg_temp.act_as('f0000000-0000-0000-0000-00000000000c');
SELECT pg_temp.fails(pg_temp.doc('financial_report', '4b000000-0000-0000-0000-00000000000b', NULL, '[]'),
  'rapport financier sur une analyse non terminée', 'terminée');
SELECT pg_temp.fails(pg_temp.doc('financial_report', NULL, NULL, '[]'), 'rapport financier sans analyse', 'terminée');
SELECT pg_temp.fails(pg_temp.doc('financial_report', '4b000000-0000-0000-0000-00000000000a', NULL, '[]',
  ARRAY['5b000000-0000-0000-0000-000000000003']::uuid[]), 'commentaire IA rejeté repris', 'rejeté');
SELECT pg_temp.fails(pg_temp.doc('financial_report', '4b000000-0000-0000-0000-00000000000a', NULL, '[]',
  ARRAY['5b000000-0000-0000-0000-000000000002']::uuid[], false), 'brouillon IA non relu non signalé', 'signalée');
SELECT pg_temp.fails(pg_temp.doc('financial_report', '4b000000-0000-0000-0000-00000000000a', NULL, '[]', '{}', true),
  'brouillon IA signalé à tort', 'signalée');
SELECT pg_temp.fails(pg_temp.doc('financial_report', '4b000000-0000-0000-0000-00000000000a', NULL, '[]', '{}', false, NULL,
  'f0000000-0000-0000-0000-00000000000a'), 'document au nom d''un autre', 'au nom');
SELECT pg_temp.run(pg_temp.doc('financial_report', '4b000000-0000-0000-0000-00000000000a', NULL, '[{"type":"analysis","id":"4b000000-0000-0000-0000-00000000000a"}]',
  ARRAY['5b000000-0000-0000-0000-000000000001','5b000000-0000-0000-0000-000000000002']::uuid[], true));
SELECT pg_temp.ok((SELECT contains_ai_drafts AND completed_at IS NOT NULL FROM public.generated_reports), 'rapport financier : brouillon IA signalé, document prêt');
UPDATE public.generated_reports SET title = 'Retouché';
DELETE FROM public.generated_reports;
SELECT pg_temp.ok((SELECT count(*) FROM public.generated_reports WHERE title IS NULL) = 1, 'document généré : ni modifié ni supprimé (RLS)');
RESET ROLE;
SELECT pg_temp.fails($q$UPDATE public.generated_reports SET title = 'Retouché'$q$, 'document généré : figé même hors RLS', 'figé');
SELECT pg_temp.fails($q$DELETE FROM public.generated_reports$q$, 'document généré : jamais supprimé, même hors RLS', 'figé');
SET LOCAL ROLE authenticated;
SELECT pg_temp.fails($q$INSERT INTO public.generated_reports (organization_id, company_id, analysis_id, document_type, format, status, requested_by)
  VALUES ('1b000000-0000-0000-0000-00000000000a', '2b000000-0000-0000-0000-00000000000a', '4b000000-0000-0000-0000-00000000000a',
          'financial_report', 'pdf', 'failed', 'f0000000-0000-0000-0000-00000000000c')$q$, 'échec sans motif', 'check');
INSERT INTO public.generated_reports (organization_id, company_id, analysis_id, document_type, format, status, failure_reason, requested_by)
VALUES ('1b000000-0000-0000-0000-00000000000a', '2b000000-0000-0000-0000-00000000000a', '4b000000-0000-0000-0000-00000000000a',
        'financial_report', 'pdf', 'failed', 'Rendu impossible (test)', 'f0000000-0000-0000-0000-00000000000c');
SELECT pg_temp.ok(true, 'échec de génération tracé avec son motif');

-- ------------------------------------------------------- suivi budgétaire, contrôle interne
SELECT pg_temp.fails(pg_temp.doc('budget_report', NULL, NULL, '[{"type":"budget","id":"6b000000-0000-0000-0000-00000000000b"}]'),
  'suivi d''un budget non approuvé', 'approuvé');
SELECT pg_temp.run(pg_temp.doc('budget_report', NULL, NULL, '[{"type":"budget","id":"6b000000-0000-0000-0000-00000000000a"}]'));
SELECT pg_temp.ok(true, 'suivi budgétaire d''un budget approuvé');
SELECT pg_temp.fails(pg_temp.doc('budget_report', '4b000000-0000-0000-0000-00000000000a', NULL, '[{"type":"budget","id":"6b000000-0000-0000-0000-00000000000a"}]',
  ARRAY['5b000000-0000-0000-0000-000000000001']::uuid[]), 'commentaires IA hors rapport financier', 'réservés');
SELECT pg_temp.fails(pg_temp.doc('ic_report', NULL, NULL, '[]', '{}', false, 'opinion'), 'rapport de contrôle interne inconnu', 'connu');
SELECT pg_temp.run(pg_temp.doc('ic_report', NULL, NULL, '[]', '{}', false, 'matrix'));
SELECT pg_temp.ok(true, 'matrice risques-contrôles exportée');
SELECT pg_temp.act_as('f0000000-0000-0000-0000-00000000000d');
SELECT pg_temp.ok((SELECT count(*) FROM public.generated_reports) = 4, 'lectrice de l''entité : documents consultables');
SELECT pg_temp.fails(pg_temp.doc('budget_report', NULL, NULL, '[{"type":"budget","id":"6b000000-0000-0000-0000-00000000000a"}]'),
  'lectrice : génération refusée');

-- ------------------------------------------------------- rapport d'audit interne et synthèse des anomalies
SELECT pg_temp.act_as('f4000000-0000-0000-0000-000000000004');
SELECT pg_temp.fails(pg_temp.doc('internal_audit_report', NULL, '7b000000-0000-0000-0000-00000000000a',
  '[{"type":"audit_report","id":"8b000000-0000-0000-0000-000000000002"}]'), 'projet de rapport exporté comme rapport émis', 'émis');
SELECT pg_temp.fails(pg_temp.doc('internal_audit_report', NULL, '7b000000-0000-0000-0000-00000000000a',
  '[{"type":"audit_report","id":"8b000000-0000-0000-0000-000000000001","content_sha256":"faux"}]'), 'empreinte du rapport émis différente', 'empreinte');
SELECT pg_temp.run(pg_temp.doc('internal_audit_report', NULL, '7b000000-0000-0000-0000-00000000000a',
  format('[{"type":"audit_report","id":"8b000000-0000-0000-0000-000000000001","content_sha256":"%s"}]', repeat('c', 64))::jsonb));
SELECT pg_temp.ok(true, 'rapport émis exporté avec son empreinte');
SELECT pg_temp.fails(pg_temp.doc('fa_summary', NULL, '7b000000-0000-0000-0000-00000000000a', '[]'), 'synthèse des anomalies hors audit financier', 'audit financier');
SELECT pg_temp.act_as('f1000000-0000-0000-0000-000000000001');
SELECT pg_temp.fails(pg_temp.doc('fa_summary', NULL, '7b000000-0000-0000-0000-00000000000b', '[]'), 'synthèse sans seuils approuvés cités', 'seuils');
SELECT pg_temp.run(pg_temp.doc('fa_summary', NULL, '7b000000-0000-0000-0000-00000000000b', '[{"type":"materiality","id":"9b000000-0000-0000-0000-00000000000a"}]'));
SELECT pg_temp.ok(true, 'synthèse des anomalies sur seuils approuvés');
SELECT pg_temp.act_as('f0000000-0000-0000-0000-00000000000d');
SELECT pg_temp.ok((SELECT count(*) FROM public.generated_reports WHERE engagement_id IS NOT NULL) = 0,
                  'lectrice de l''entité : documents de mission invisibles');
SELECT pg_temp.act_as('f5000000-0000-0000-0000-000000000005');
SELECT pg_temp.ok((SELECT count(*) FROM public.generated_reports) = 0, 'audité : aucun document du dossier');
SELECT pg_temp.act_as('f4000000-0000-0000-0000-000000000004');
SELECT pg_temp.ok((SELECT count(*) FROM public.generated_reports WHERE engagement_id IS NOT NULL) = 1, 'auditeur : documents de sa mission seulement');
SELECT pg_temp.act_as('fb000000-0000-0000-0000-00000000000b');
SELECT pg_temp.ok((SELECT count(*) FROM public.generated_reports) = 0, 'autre organisation : aucun document');

-- ------------------------------------------------------- acteur IA
SELECT pg_temp.act_as('f0000000-0000-0000-0000-00000000000c');
SELECT set_config('kofinex.actor', 'ai', true);
SELECT pg_temp.fails(pg_temp.doc('budget_report', NULL, NULL, '[{"type":"budget","id":"6b000000-0000-0000-0000-00000000000a"}]'),
  'acteur IA : aucun document généré', 'IA');
SELECT set_config('kofinex.actor', '', true);

-- ------------------------------------------------------- modèles
SELECT pg_temp.act_as('f0000000-0000-0000-0000-00000000000c');
SELECT pg_temp.fails($q$INSERT INTO public.report_templates (organization_id, name, report_kind, sections, document_type)
  VALUES ('1b000000-0000-0000-0000-00000000000a', 'Rapport annuel', 'detailed', '[]', 'financial_report')$q$, 'comptable : modèle réservé aux administrateurs');
SELECT pg_temp.act_as('f0000000-0000-0000-0000-00000000000a');
SELECT pg_temp.fails($q$INSERT INTO public.report_templates (organization_id, name, report_kind, sections, document_type, branding)
  VALUES ('1b000000-0000-0000-0000-00000000000a', 'Rapport annuel', 'detailed', '[]', 'financial_report', '{"primary_color":"bleu"}')$q$,
  'couleur de marque invalide', 'check');
INSERT INTO public.report_templates (id, organization_id, name, report_kind, sections, document_type, content, branding)
VALUES ('ab000000-0000-0000-0000-000000000001', '1b000000-0000-0000-0000-00000000000a', 'Rapport annuel', 'detailed',
        '["statements","indicators"]', 'financial_report', '{"intro":"Introduction (test)"}', '{"primary_color":"#172554"}');
SELECT pg_temp.ok((SELECT created_by = 'f0000000-0000-0000-0000-00000000000a' FROM public.report_templates WHERE id = 'ab000000-0000-0000-0000-000000000001'),
                  'modèle créé en brouillon, auteur enregistré');
SELECT pg_temp.fails($q$UPDATE public.report_templates SET status = 'published', published_by = 'f0000000-0000-0000-0000-00000000000c'$q$,
  'publication au nom d''un autre', 'au nom');
UPDATE public.report_templates SET status = 'published', published_by = 'f0000000-0000-0000-0000-00000000000a';
SELECT pg_temp.ok((SELECT published_at IS NOT NULL FROM public.report_templates), 'modèle publié');
SELECT pg_temp.fails($q$UPDATE public.report_templates SET content = '{"intro":"Modifiée"}'$q$, 'modèle publié : figé', 'figé');
SELECT pg_temp.fails($q$DELETE FROM public.report_templates$q$, 'modèle publié : conservé', 'conservé');
SELECT pg_temp.act_as('f0000000-0000-0000-0000-00000000000c');
INSERT INTO public.generated_reports (organization_id, company_id, analysis_id, document_type, format, status, storage_path, sha256, data_sha256,
  content_snapshot, filename, size_bytes, template_id, template_version, requested_by)
VALUES ('1b000000-0000-0000-0000-00000000000a', '2b000000-0000-0000-0000-00000000000a', '4b000000-0000-0000-0000-00000000000a', 'financial_report',
        'docx', 'ready', 'p/y.docx', repeat('a', 64), repeat('b', 64), '{}', 'y.docx', 10, 'ab000000-0000-0000-0000-000000000001', 1,
        'f0000000-0000-0000-0000-00000000000c');
SELECT pg_temp.ok(true, 'document établi avec la version publiée du modèle');
SELECT pg_temp.fails($q$INSERT INTO public.generated_reports (organization_id, company_id, document_type, subtype, format, status, storage_path, sha256,
  data_sha256, content_snapshot, filename, size_bytes, template_id, template_version, requested_by)
  VALUES ('1b000000-0000-0000-0000-00000000000a', '2b000000-0000-0000-0000-00000000000a', 'ic_report', 'matrix', 'pdf', 'ready', 'p/z.pdf',
          repeat('a', 64), repeat('b', 64), '{}', 'z.pdf', 10, 'ab000000-0000-0000-0000-000000000001', 1, 'f0000000-0000-0000-0000-00000000000c')$q$,
  'modèle d''un autre type de document', 'même type');
SELECT pg_temp.act_as('f0000000-0000-0000-0000-00000000000a');
UPDATE public.report_templates SET status = 'archived';
SELECT pg_temp.act_as('f0000000-0000-0000-0000-00000000000c');
SELECT pg_temp.fails($q$INSERT INTO public.generated_reports (organization_id, company_id, analysis_id, document_type, format, status, storage_path,
  sha256, data_sha256, content_snapshot, filename, size_bytes, template_id, template_version, requested_by)
  VALUES ('1b000000-0000-0000-0000-00000000000a', '2b000000-0000-0000-0000-00000000000a', '4b000000-0000-0000-0000-00000000000a',
          'financial_report', 'pdf', 'ready', 'p/w.pdf', repeat('a', 64), repeat('b', 64), '{}', 'w.pdf', 10,
          'ab000000-0000-0000-0000-000000000001', 1, 'f0000000-0000-0000-0000-00000000000c')$q$, 'modèle archivé : plus utilisé', 'publiée');
SELECT pg_temp.act_as('fb000000-0000-0000-0000-00000000000b');
SELECT pg_temp.ok((SELECT count(*) FROM public.report_templates WHERE organization_id IS NOT NULL) = 0, 'autre organisation : modèles invisibles');

ROLLBACK;
