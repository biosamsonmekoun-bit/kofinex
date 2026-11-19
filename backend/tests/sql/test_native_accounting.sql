-- =====================================================================
-- Tests migration 0014 : comptabilité générale native (lot 3B, étapes A et B)
-- Plan comptable de l'entreprise, tiers, journaux, circuit de validation, immutabilité, numérotation sans doublon,
-- extournes, double comptabilisation, lettrage, exercice clôturé, RLS, isolation, acteur IA. Données FICTIVES.
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
-- lettrage puis contrôle immédiat des contraintes différées (dans une sous-transaction annulée en cas d'échec)
CREATE OR REPLACE FUNCTION pg_temp.letter(p_lettering uuid, p_lines uuid[]) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  UPDATE public.journal_entry_lines SET lettering_id = p_lettering WHERE id = ANY (p_lines);
  SET CONSTRAINTS ALL IMMEDIATE;
  SET CONSTRAINTS ALL DEFERRED;
END $$;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA pg_temp TO authenticated;

-- a : alice (propriétaire) ; c : carl (comptable, préparateur) ; d : dina (comptable, validatrice) ; v : vera (lectrice) ;
-- s : sam (équipe de mission, sans rôle sur l'entité) ; b : bob (autre organisation)
INSERT INTO auth.users (id, email) VALUES
  ('e1000000-0000-0000-0000-00000000000a', 'alice@na.test'), ('e1000000-0000-0000-0000-00000000000c', 'carl@na.test'),
  ('e1000000-0000-0000-0000-00000000000d', 'dina@na.test'), ('e1000000-0000-0000-0000-00000000000f', 'vera@na.test'),
  ('e1000000-0000-0000-0000-000000000005', 'sam@na.test'), ('e1000000-0000-0000-0000-00000000000b', 'bob@nb.test');
INSERT INTO public.accounting_frameworks (id, code, name) VALUES ('f1000000-0000-0000-0000-0000000000fa', 'TEST_NAT', 'Test natif');

SET LOCAL session_replication_role = replica;
INSERT INTO public.profiles (id, email) SELECT id, email FROM auth.users WHERE email LIKE '%@n_.test' ON CONFLICT DO NOTHING;
INSERT INTO public.framework_versions (id, framework_id, version_label, effective_from, source_reference, status, published_at) VALUES
  ('f1000000-0000-0000-0000-0000000000f1', 'f1000000-0000-0000-0000-0000000000fa', 'TEST', '2020-01-01', 'Référentiel FICTIF', 'published', now()),
  ('f1000000-0000-0000-0000-0000000000f2', 'f1000000-0000-0000-0000-0000000000fa', 'BROUILLON', '2020-01-01', 'Référentiel FICTIF', 'draft', NULL);
INSERT INTO public.chart_of_accounts (framework_version_id, account_number, label, account_class, nature) VALUES
  ('f1000000-0000-0000-0000-0000000000f1', '401', 'Fournisseurs', 4, 'liability'),
  ('f1000000-0000-0000-0000-0000000000f1', '411', 'Clients', 4, 'asset'),
  ('f1000000-0000-0000-0000-0000000000f1', '521', 'Banques', 5, 'asset'),
  ('f1000000-0000-0000-0000-0000000000f1', '601', 'Achats de marchandises', 6, 'expense'),
  ('f1000000-0000-0000-0000-0000000000f1', '701', 'Ventes de marchandises', 7, 'income'),
  ('f1000000-0000-0000-0000-0000000000f2', '411', 'Clients', 4, 'asset');
INSERT INTO public.organizations (id, name, slug, created_by) VALUES
  ('1b000000-0000-0000-0000-00000000000a', 'Cabinet NA', 'cab-na', 'e1000000-0000-0000-0000-00000000000a'),
  ('1b000000-0000-0000-0000-00000000000b', 'Cabinet NB', 'cab-nb', 'e1000000-0000-0000-0000-00000000000b');
INSERT INTO public.organization_members (organization_id, user_id, role) VALUES
  ('1b000000-0000-0000-0000-00000000000a', 'e1000000-0000-0000-0000-00000000000a', 'owner'),
  ('1b000000-0000-0000-0000-00000000000a', 'e1000000-0000-0000-0000-00000000000c', 'member'),
  ('1b000000-0000-0000-0000-00000000000a', 'e1000000-0000-0000-0000-00000000000d', 'member'),
  ('1b000000-0000-0000-0000-00000000000a', 'e1000000-0000-0000-0000-00000000000f', 'member'),
  ('1b000000-0000-0000-0000-00000000000a', 'e1000000-0000-0000-0000-000000000005', 'member'),
  ('1b000000-0000-0000-0000-00000000000b', 'e1000000-0000-0000-0000-00000000000b', 'owner');
INSERT INTO public.companies (id, organization_id, name, framework_id, created_by) VALUES
  ('2b000000-0000-0000-0000-00000000000a', '1b000000-0000-0000-0000-00000000000a', 'Client natif',
   'f1000000-0000-0000-0000-0000000000fa', 'e1000000-0000-0000-0000-00000000000a');
INSERT INTO public.company_members (organization_id, company_id, user_id, role) VALUES
  ('1b000000-0000-0000-0000-00000000000a', '2b000000-0000-0000-0000-00000000000a', 'e1000000-0000-0000-0000-00000000000c', 'accountant'),
  ('1b000000-0000-0000-0000-00000000000a', '2b000000-0000-0000-0000-00000000000a', 'e1000000-0000-0000-0000-00000000000d', 'accountant'),
  ('1b000000-0000-0000-0000-00000000000a', '2b000000-0000-0000-0000-00000000000a', 'e1000000-0000-0000-0000-00000000000f', 'viewer');
INSERT INTO public.fiscal_years (id, organization_id, company_id, label, start_date, end_date, status, closed_at, closed_by, created_by) VALUES
  ('3b000000-0000-0000-0000-000000002025', '1b000000-0000-0000-0000-00000000000a', '2b000000-0000-0000-0000-00000000000a',
   '2025', '2025-01-01', '2025-12-31', 'open', NULL, NULL, 'e1000000-0000-0000-0000-00000000000a'),
  ('3b000000-0000-0000-0000-000000002024', '1b000000-0000-0000-0000-00000000000a', '2b000000-0000-0000-0000-00000000000a',
   '2024', '2024-01-01', '2024-12-31', 'closed', now(), 'e1000000-0000-0000-0000-00000000000a', 'e1000000-0000-0000-0000-00000000000a');
INSERT INTO public.engagements (id, organization_id, company_id, fiscal_year_id, engagement_type, reference, name, created_by)
VALUES ('5b000000-0000-0000-0000-00000000000a', '1b000000-0000-0000-0000-00000000000a', '2b000000-0000-0000-0000-00000000000a',
        '3b000000-0000-0000-0000-000000002025', 'statutory_audit', 'CAC-NA', 'Audit NA', 'e1000000-0000-0000-0000-00000000000a');
INSERT INTO public.engagement_members (organization_id, engagement_id, user_id, role, independence_confirmed_at) VALUES
  ('1b000000-0000-0000-0000-00000000000a', '5b000000-0000-0000-0000-00000000000a', 'e1000000-0000-0000-0000-000000000005', 'staff', now());
SET LOCAL session_replication_role = origin;

SET LOCAL ROLE authenticated;
SELECT pg_temp.act_as('e1000000-0000-0000-0000-00000000000c');

-- ------------------------------------------------------- plan comptable de l'entreprise
CREATE TEMP VIEW o AS SELECT '1b000000-0000-0000-0000-00000000000a'::uuid AS org, '2b000000-0000-0000-0000-00000000000a'::uuid AS co,
  '3b000000-0000-0000-0000-000000002025'::uuid AS fy, 'f1000000-0000-0000-0000-0000000000f1'::uuid AS v;
GRANT SELECT ON o TO authenticated;
SELECT pg_temp.fails($q$INSERT INTO public.company_accounts (organization_id, company_id, account_number, label, framework_version_id,
  chart_account_number, created_by) SELECT org, co, '609100', 'X', v, '609', 'e1000000-0000-0000-0000-00000000000c' FROM o$q$,
  'compte rattaché à un compte absent du référentiel', 'absent du plan');
SELECT pg_temp.fails($q$INSERT INTO public.company_accounts (organization_id, company_id, account_number, label, framework_version_id,
  chart_account_number, created_by) SELECT org, co, '602100', 'X', v, '601', 'e1000000-0000-0000-0000-00000000000c' FROM o$q$,
  'numéro de compte hors de la rubrique du référentiel', 'check');
SELECT pg_temp.fails($q$INSERT INTO public.company_accounts (organization_id, company_id, account_number, label, framework_version_id,
  chart_account_number, created_by) SELECT org, co, '411900', 'X', 'f1000000-0000-0000-0000-0000000000f2', '411',
  'e1000000-0000-0000-0000-00000000000c' FROM o$q$, 'référentiel non publié refusé', 'version publiée');
INSERT INTO public.company_accounts (organization_id, company_id, account_number, label, framework_version_id, chart_account_number,
                                     requires_third_party, third_party_kind, lettering_enabled, created_by)
SELECT org, co, n, l, v, c, tp, k, lt, 'e1000000-0000-0000-0000-00000000000c' FROM o,
  (VALUES ('401100', 'Fournisseurs locaux', '401', true, 'supplier', true), ('411100', 'Clients', '411', true, 'customer', true),
          ('521100', 'Banque A', '521', false, NULL, false), ('601100', 'Achats', '601', false, NULL, false),
          ('701100', 'Ventes', '701', false, NULL, false)) t(n, l, c, tp, k, lt);
SELECT pg_temp.ok((SELECT nature FROM public.company_accounts WHERE account_number = '411100') = 'asset',
  'comptes ouverts ; nature reprise du référentiel');

-- ------------------------------------------------------- tiers
SELECT pg_temp.fails($q$INSERT INTO public.third_parties (organization_id, company_id, code, name, kind, collective_account_number,
  created_by) SELECT org, co, 'C1', 'Client 1', 'customer', '401100', 'e1000000-0000-0000-0000-00000000000c' FROM o$q$,
  'client rattaché au collectif fournisseurs refusé', 'compte collectif');
INSERT INTO public.third_parties (id, organization_id, company_id, code, name, kind, collective_account_number, created_by)
SELECT i, org, co, c, n, k, a, 'e1000000-0000-0000-0000-00000000000c' FROM o,
  (VALUES ('7b000000-0000-0000-0000-0000000000c1'::uuid, 'C1', 'Client 1', 'customer', '411100'),
          ('7b000000-0000-0000-0000-0000000000f1'::uuid, 'F1', 'Fournisseur 1', 'supplier', '401100')) t(i, c, n, k, a);
SELECT pg_temp.ok((SELECT count(*) FROM public.third_parties) = 2, 'tiers créés');

-- ------------------------------------------------------- journaux
SELECT pg_temp.fails($q$INSERT INTO public.journals (organization_id, company_id, code, label, journal_type, number_prefix, created_by)
  SELECT org, co, 'vt', 'Ventes', 'sales', 'VT-', 'e1000000-0000-0000-0000-00000000000c' FROM o$q$, 'code de journal invalide', 'check');
INSERT INTO public.journals (id, organization_id, company_id, code, label, journal_type, number_prefix, counterpart_account_number,
                             allowed_users, created_by)
SELECT i, org, co, c, l, t, p, a, u, 'e1000000-0000-0000-0000-00000000000c' FROM o,
  (VALUES ('8b000000-0000-0000-0000-0000000000a1'::uuid, 'VT', 'Ventes', 'sales', 'VT-', NULL, NULL::uuid[]),
          ('8b000000-0000-0000-0000-0000000000a2'::uuid, 'BQ', 'Banque A', 'bank', 'BQ-', '521100', NULL),
          ('8b000000-0000-0000-0000-0000000000a3'::uuid, 'PA', 'Paie', 'payroll', 'PA-', NULL,
           ARRAY['e1000000-0000-0000-0000-00000000000d'::uuid])) t(i, c, l, t, p, a, u);
SELECT pg_temp.fails($q$INSERT INTO public.journals (organization_id, company_id, code, label, journal_type, number_prefix, created_by)
  SELECT org, co, 'VT', 'Doublon', 'sales', 'X', 'e1000000-0000-0000-0000-00000000000c' FROM o$q$, 'code de journal en double', 'duplicate');
SELECT pg_temp.fails($q$INSERT INTO public.journal_entries (organization_id, company_id, fiscal_year_id, journal_id, entry_date, label,
  created_by) SELECT org, co, fy, '8b000000-0000-0000-0000-0000000000a3', '2025-02-01', 'Paie', 'e1000000-0000-0000-0000-00000000000c'
  FROM o$q$, 'journal réservé à d''autres utilisateurs', 'réservé');

-- ------------------------------------------------------- saisie
SELECT pg_temp.fails($q$INSERT INTO public.journal_entries (organization_id, company_id, fiscal_year_id, journal_id, entry_date, label,
  status, created_by) SELECT org, co, fy, '8b000000-0000-0000-0000-0000000000a1', '2025-03-15', 'F12', 'validated',
  'e1000000-0000-0000-0000-00000000000c' FROM o$q$, 'écriture créée directement validée', 'brouillon');
SELECT pg_temp.fails($q$INSERT INTO public.journal_entries (organization_id, company_id, fiscal_year_id, journal_id, entry_date, label,
  origin, source_type, source_id, created_by) SELECT org, co, fy, '8b000000-0000-0000-0000-0000000000a1', '2025-03-15', 'Auto',
  'generated', 'sales_invoice', gen_random_uuid(), 'e1000000-0000-0000-0000-00000000000c' FROM o$q$,
  'écriture « générée » saisie à la main', 'moteur de génération');
INSERT INTO public.journal_entries (id, organization_id, company_id, fiscal_year_id, journal_id, entry_date, piece_ref, label, created_by)
SELECT i, org, co, fy, j, d::date, p, l, 'e1000000-0000-0000-0000-00000000000c' FROM o,
  (VALUES ('9b000000-0000-0000-0000-000000000001'::uuid, '8b000000-0000-0000-0000-0000000000a1'::uuid, '2025-03-15', 'F12', 'Facture F12'),
          ('9b000000-0000-0000-0000-000000000002'::uuid, '8b000000-0000-0000-0000-0000000000a1'::uuid, '2025-03-20', 'F13', 'Facture F13'),
          ('9b000000-0000-0000-0000-000000000003'::uuid, '8b000000-0000-0000-0000-0000000000a2'::uuid, '2025-04-05', 'RB1', 'Règlement F12'))
  t(i, j, d, p, l);
SELECT pg_temp.fails($q$INSERT INTO public.journal_entry_lines (organization_id, company_id, fiscal_year_id, entry_id, line_no,
  account_number, debit, credit) SELECT org, co, fy, '9b000000-0000-0000-0000-000000000001', 9, '701100', 10, 10 FROM o$q$,
  'ligne au débit et au crédit', 'check');
SELECT pg_temp.fails($q$INSERT INTO public.journal_entry_lines (organization_id, company_id, fiscal_year_id, entry_id, line_no,
  account_number, debit) SELECT org, co, fy, '9b000000-0000-0000-0000-000000000001', 9, '709999', 10 FROM o$q$,
  'compte non ouvert dans le plan de l''entreprise', 'foreign key');
INSERT INTO public.journal_entry_lines (organization_id, company_id, fiscal_year_id, entry_id, line_no, account_number, third_party_id, debit, credit)
SELECT org, co, fy, e, n, a, t, dv, cv FROM o,
  (VALUES ('9b000000-0000-0000-0000-000000000001'::uuid, 1, '411100', NULL::uuid, 1200, 0), ('9b000000-0000-0000-0000-000000000001'::uuid, 2, '701100', NULL, 0, 1100),
          ('9b000000-0000-0000-0000-000000000002'::uuid, 1, '411100', '7b000000-0000-0000-0000-0000000000c1', 500, 0),
          ('9b000000-0000-0000-0000-000000000002'::uuid, 2, '701100', NULL, 0, 500),
          ('9b000000-0000-0000-0000-000000000003'::uuid, 1, '521100', NULL, 1200, 0),
          ('9b000000-0000-0000-0000-000000000003'::uuid, 2, '411100', '7b000000-0000-0000-0000-0000000000c1', 0, 1200)) t(e, n, a, t, dv, cv);
SELECT pg_temp.ok((SELECT total_debit = 1200 AND total_credit = 1100 AND line_count = 2 FROM public.journal_entries
  WHERE id = '9b000000-0000-0000-0000-000000000001'), 'totaux tenus à partir des lignes');
SELECT pg_temp.fails($q$UPDATE public.journal_entries SET total_credit = 1200 WHERE id = '9b000000-0000-0000-0000-000000000001'$q$,
  'totaux non modifiables directement', 'Totaux');
SELECT pg_temp.fails($q$UPDATE public.journal_entries SET status = 'submitted' WHERE id = '9b000000-0000-0000-0000-000000000001'$q$,
  'soumission d''une écriture déséquilibrée', 'déséquilibrée');
UPDATE public.journal_entry_lines SET credit = 1200 WHERE entry_id = '9b000000-0000-0000-0000-000000000001' AND line_no = 2;
SELECT pg_temp.fails($q$UPDATE public.journal_entries SET status = 'submitted' WHERE id = '9b000000-0000-0000-0000-000000000001'$q$,
  'compte collectif sans tiers', 'Tiers obligatoire');
UPDATE public.journal_entry_lines SET third_party_id = '7b000000-0000-0000-0000-0000000000c1'
 WHERE entry_id = '9b000000-0000-0000-0000-000000000001' AND line_no = 1;
SELECT pg_temp.fails($q$UPDATE public.journal_entry_lines SET third_party_id = '7b000000-0000-0000-0000-0000000000f1'
  WHERE entry_id = '9b000000-0000-0000-0000-000000000002' AND line_no = 1; UPDATE public.journal_entries SET status = 'submitted'
  WHERE id = '9b000000-0000-0000-0000-000000000002'$q$, 'fournisseur sur le collectif clients', 'type incompatible');
UPDATE public.journal_entries SET status = 'submitted' WHERE id IN ('9b000000-0000-0000-0000-000000000001',
  '9b000000-0000-0000-0000-000000000002', '9b000000-0000-0000-0000-000000000003');
SELECT pg_temp.ok((SELECT bool_and(status = 'submitted' AND submitted_by = 'e1000000-0000-0000-0000-00000000000c')
  FROM public.journal_entries), 'écritures équilibrées soumises par leur auteur');
SELECT pg_temp.fails($q$UPDATE public.journal_entry_lines SET debit = 1300 WHERE entry_id = '9b000000-0000-0000-0000-000000000001'
  AND line_no = 1$q$, 'ligne d''une écriture soumise figée', 'brouillon uniquement');
SELECT pg_temp.fails($q$UPDATE public.journal_entries SET label = 'Autre' WHERE id = '9b000000-0000-0000-0000-000000000001'$q$,
  'en-tête d''une écriture soumise figé', 'brouillon uniquement');

-- ------------------------------------------------------- validation : séparation des tâches, droits, numérotation
SELECT pg_temp.fails($q$UPDATE public.journal_entries SET status = 'validated' WHERE id = '9b000000-0000-0000-0000-000000000001'$q$,
  'le préparateur ne valide pas sa propre écriture', 'Séparation des tâches');
SELECT pg_temp.act_as('e1000000-0000-0000-0000-00000000000f');
UPDATE public.journal_entries SET status = 'validated' WHERE id = '9b000000-0000-0000-0000-000000000001';
SELECT pg_temp.act_as('e1000000-0000-0000-0000-00000000000d');
SELECT pg_temp.ok((SELECT status FROM public.journal_entries WHERE id = '9b000000-0000-0000-0000-000000000001') = 'submitted',
  'lecteur : validation sans effet (RLS)');
UPDATE public.journal_entries SET status = 'validated' WHERE id = '9b000000-0000-0000-0000-000000000001';
UPDATE public.journal_entries SET status = 'validated' WHERE id = '9b000000-0000-0000-0000-000000000003';
SELECT pg_temp.ok((SELECT number = 'VT-000001' AND sequence_no = 1 AND validated_by = 'e1000000-0000-0000-0000-00000000000d'
  FROM public.journal_entries WHERE id = '9b000000-0000-0000-0000-000000000001'), 'validation : numéro définitif VT-000001');
SELECT pg_temp.ok((SELECT number FROM public.journal_entries WHERE id = '9b000000-0000-0000-0000-000000000003') = 'BQ-000001',
  'séquence propre à chaque journal');
SELECT pg_temp.fails($q$UPDATE public.journal_entries SET status = 'validated' WHERE id = '9b000000-0000-0000-0000-000000000001'$q$,
  'double validation refusée', 'immuable');
SELECT pg_temp.fails($q$UPDATE public.journal_entries SET label = 'Corrigé' WHERE id = '9b000000-0000-0000-0000-000000000001'$q$,
  'écriture validée immuable (en-tête)', 'immuable');
SELECT pg_temp.fails($q$UPDATE public.journal_entry_lines SET debit = 1 WHERE entry_id = '9b000000-0000-0000-0000-000000000001'
  AND line_no = 1$q$, 'écriture validée immuable (lignes)', 'brouillon uniquement');
SELECT pg_temp.fails($q$DELETE FROM public.journal_entries WHERE id = '9b000000-0000-0000-0000-000000000001'$q$,
  'écriture validée non supprimable', 'brouillon ou rejetée');
SELECT pg_temp.fails($q$INSERT INTO public.journal_sequences (journal_id, fiscal_year_id, organization_id, company_id, last_number)
  SELECT '8b000000-0000-0000-0000-0000000000a1', fy, org, co, 99 FROM o$q$, 'séquences non modifiables par les utilisateurs', 'permission');
SELECT pg_temp.fails($q$UPDATE public.journal_entries SET number = 'VT-000099' WHERE id = '9b000000-0000-0000-0000-000000000002'$q$,
  'numéro non attribuable à la main', 'attribués par KOFINEX');

-- ------------------------------------------------------- rejet et reprise
SELECT pg_temp.fails($q$UPDATE public.journal_entries SET status = 'rejected', rejection_reason = 'non' WHERE
  id = '9b000000-0000-0000-0000-000000000002'$q$, 'rejet sans motif suffisant', 'Motif');
UPDATE public.journal_entries SET status = 'rejected', rejection_reason = 'Montant à vérifier'
 WHERE id = '9b000000-0000-0000-0000-000000000002';
SELECT pg_temp.fails($q$UPDATE public.journal_entries SET status = 'draft' WHERE id = '9b000000-0000-0000-0000-000000000002'$q$,
  'seul l''auteur reprend une écriture rejetée', 'auteur');
SELECT pg_temp.act_as('e1000000-0000-0000-0000-00000000000c');
UPDATE public.journal_entries SET status = 'draft' WHERE id = '9b000000-0000-0000-0000-000000000002';
SELECT pg_temp.ok((SELECT array_agg(action ORDER BY created_at, action) FROM public.journal_entry_events
  WHERE entry_id = '9b000000-0000-0000-0000-000000000002') @> ARRAY['created','submitted','rejected','returned_to_draft'],
  'historique du circuit : création, soumission, rejet, reprise');
SELECT pg_temp.ok((SELECT reason FROM public.journal_entry_events WHERE entry_id = '9b000000-0000-0000-0000-000000000002'
  AND action = 'rejected') = 'Montant à vérifier', 'motif du rejet conservé');
SELECT pg_temp.fails($q$DELETE FROM public.journal_entry_events$q$, 'historique non supprimable par les utilisateurs', 'permission');

-- ------------------------------------------------------- extourne
SELECT pg_temp.fails($q$INSERT INTO public.journal_entries (organization_id, company_id, fiscal_year_id, journal_id, entry_date, label,
  origin, reverses_entry_id, created_by) SELECT org, co, fy, '8b000000-0000-0000-0000-0000000000a1', '2025-03-25', 'Extourne',
  'reversal', '9b000000-0000-0000-0000-000000000002', 'e1000000-0000-0000-0000-00000000000c' FROM o$q$,
  'extourne d''une écriture non validée', 'validée peut être extournée');
SELECT pg_temp.fails($q$INSERT INTO public.journal_entries (organization_id, company_id, fiscal_year_id, journal_id, entry_date, label,
  origin, reverses_entry_id, created_by) SELECT org, co, fy, '8b000000-0000-0000-0000-0000000000a1', '2025-03-01', 'Extourne',
  'reversal', '9b000000-0000-0000-0000-000000000001', 'e1000000-0000-0000-0000-00000000000c' FROM o$q$,
  'extourne antérieure à l''écriture d''origine', 'antérieure');
INSERT INTO public.journal_entries (id, organization_id, company_id, fiscal_year_id, journal_id, entry_date, label, origin,
                                    reverses_entry_id, created_by)
SELECT '9b000000-0000-0000-0000-000000000004', org, co, fy, '8b000000-0000-0000-0000-0000000000a1', '2025-03-31', 'Extourne VT-000001',
       'reversal', '9b000000-0000-0000-0000-000000000001', 'e1000000-0000-0000-0000-00000000000c' FROM o;
INSERT INTO public.journal_entry_lines (organization_id, company_id, fiscal_year_id, entry_id, line_no, account_number, third_party_id, debit, credit)
SELECT org, co, fy, '9b000000-0000-0000-0000-000000000004', n, a, t, dv, cv FROM o,
  (VALUES (1, '411100', '7b000000-0000-0000-0000-0000000000c1'::uuid, 0, 1000), (2, '701100', NULL, 1000, 0)) t(n, a, t, dv, cv);
SELECT pg_temp.fails($q$UPDATE public.journal_entries SET status = 'submitted' WHERE id = '9b000000-0000-0000-0000-000000000004'$q$,
  'extourne qui n''inverse pas exactement l''écriture d''origine', 'inverser exactement');
UPDATE public.journal_entry_lines SET credit = 1200 WHERE entry_id = '9b000000-0000-0000-0000-000000000004' AND line_no = 1;
UPDATE public.journal_entry_lines SET debit = 1200 WHERE entry_id = '9b000000-0000-0000-0000-000000000004' AND line_no = 2;
UPDATE public.journal_entries SET status = 'submitted' WHERE id = '9b000000-0000-0000-0000-000000000004';
SELECT pg_temp.fails($q$INSERT INTO public.journal_entries (organization_id, company_id, fiscal_year_id, journal_id, entry_date, label,
  origin, reverses_entry_id, created_by) SELECT org, co, fy, '8b000000-0000-0000-0000-0000000000a1', '2025-04-01', 'Extourne bis',
  'reversal', '9b000000-0000-0000-0000-000000000001', 'e1000000-0000-0000-0000-00000000000c' FROM o$q$,
  'deuxième extourne de la même écriture', 'duplicate');
SELECT pg_temp.act_as('e1000000-0000-0000-0000-00000000000d');
UPDATE public.journal_entries SET status = 'validated' WHERE id = '9b000000-0000-0000-0000-000000000004';
SELECT pg_temp.ok((SELECT status = 'reversed' AND reversed_by_entry_id = '9b000000-0000-0000-0000-000000000004'
  FROM public.journal_entries WHERE id = '9b000000-0000-0000-0000-000000000001'), 'extourne validée : écriture d''origine extournée');
SELECT pg_temp.ok((SELECT number FROM public.journal_entries WHERE id = '9b000000-0000-0000-0000-000000000004') = 'VT-000002',
  'extourne numérotée à la suite dans son journal');
SELECT pg_temp.ok((SELECT count(*) FROM public.journal_entry_events WHERE entry_id = '9b000000-0000-0000-0000-000000000001'
  AND action = 'reversed') = 1, 'historique : extourne tracée sur l''écriture d''origine');
SELECT pg_temp.fails($q$UPDATE public.journal_entries SET status = 'validated', reversed_by_entry_id = NULL WHERE
  id = '9b000000-0000-0000-0000-000000000001'$q$, 'une écriture extournée reste figée', 'immuable');

-- ------------------------------------------------------- journaux et comptes utilisés
SELECT pg_temp.act_as('e1000000-0000-0000-0000-00000000000c');
SELECT pg_temp.fails($q$DELETE FROM public.journals WHERE id = '8b000000-0000-0000-0000-0000000000a1'$q$,
  'journal mouvementé non supprimable', 'foreign key');
SELECT pg_temp.fails($q$UPDATE public.journals SET code = 'VE' WHERE id = '8b000000-0000-0000-0000-0000000000a1'$q$,
  'code d''un journal utilisé non modifiable', 'déjà utilisé');
SELECT pg_temp.fails($q$UPDATE public.company_accounts SET requires_third_party = false, third_party_kind = NULL
  WHERE account_number = '411100'$q$, 'compte mouvementé : caractère collectif figé', 'déjà mouvementé');
SELECT pg_temp.fails($q$DELETE FROM public.company_accounts WHERE account_number = '701100'$q$,
  'compte mouvementé non supprimable', 'foreign key');
UPDATE public.journals SET is_active = false WHERE id = '8b000000-0000-0000-0000-0000000000a2';
SELECT pg_temp.fails($q$INSERT INTO public.journal_entries (organization_id, company_id, fiscal_year_id, journal_id, entry_date, label,
  created_by) SELECT org, co, fy, '8b000000-0000-0000-0000-0000000000a2', '2025-05-01', 'X', 'e1000000-0000-0000-0000-00000000000c'
  FROM o$q$, 'saisie dans un journal désactivé', 'désactivé');
SELECT pg_temp.fails($q$INSERT INTO public.journal_entries (organization_id, company_id, fiscal_year_id, journal_id, entry_date, label,
  created_by) SELECT org, co, '3b000000-0000-0000-0000-000000002024', '8b000000-0000-0000-0000-0000000000a1', '2024-05-01', 'X',
  'e1000000-0000-0000-0000-00000000000c' FROM o$q$, 'saisie dans un exercice clôturé', 'clôturé');
DELETE FROM public.journal_entries WHERE id = '9b000000-0000-0000-0000-000000000002';
SELECT pg_temp.ok(NOT EXISTS (SELECT 1 FROM public.journal_entries WHERE id = '9b000000-0000-0000-0000-000000000002')
  AND EXISTS (SELECT 1 FROM public.journal_entry_events WHERE entry_id = '9b000000-0000-0000-0000-000000000002' AND action = 'deleted'),
  'brouillon supprimé par son auteur ; historique conservé');

-- ------------------------------------------------------- lettrage
-- facture F12 (débit 411100 : 1 200, extournée) et extourne (crédit 1 200) ; règlement RB1 (crédit 1 200)
INSERT INTO public.letterings (id, organization_id, company_id, account_number, third_party_id, code, amount, created_by)
SELECT 'ab000000-0000-0000-0000-000000000001', org, co, '411100', '7b000000-0000-0000-0000-0000000000c1', 'A', 1200,
       'e1000000-0000-0000-0000-00000000000c' FROM o;
SELECT pg_temp.fails($q$SELECT pg_temp.letter('ab000000-0000-0000-0000-000000000001',
  ARRAY(SELECT id FROM public.journal_entry_lines WHERE entry_id = '9b000000-0000-0000-0000-000000000001' AND line_no = 1))$q$,
  'lettrage d''une seule ligne (déséquilibré)', 'déséquilibré');
SELECT pg_temp.fails($q$SELECT pg_temp.letter('ab000000-0000-0000-0000-000000000001',
  ARRAY(SELECT id FROM public.journal_entry_lines WHERE entry_id = '9b000000-0000-0000-0000-000000000001'))$q$,
  'lettrage de lignes d''un autre compte', 'même compte');
SELECT pg_temp.letter('ab000000-0000-0000-0000-000000000001',
  ARRAY(SELECT l.id FROM public.journal_entry_lines l WHERE l.account_number = '411100'
         AND l.entry_id IN ('9b000000-0000-0000-0000-000000000001', '9b000000-0000-0000-0000-000000000004')));
SELECT pg_temp.ok((SELECT count(*) FROM public.journal_entry_lines WHERE lettering_id = 'ab000000-0000-0000-0000-000000000001') = 2,
  'lettrage équilibré de la facture et de son extourne');
SELECT pg_temp.fails($q$SELECT pg_temp.letter('ab000000-0000-0000-0000-000000000001',
  ARRAY(SELECT id FROM public.journal_entry_lines WHERE entry_id = '9b000000-0000-0000-0000-000000000003' AND account_number = '411100'))$q$,
  'ajout d''une ligne à un lettrage équilibré', 'déséquilibré');
SELECT pg_temp.fails($q$UPDATE public.letterings SET amount = 1 WHERE id = 'ab000000-0000-0000-0000-000000000001'$q$,
  'lettrage non modifiable', 'non modifiable');
DELETE FROM public.letterings WHERE id = 'ab000000-0000-0000-0000-000000000001';
SELECT pg_temp.ok(NOT EXISTS (SELECT 1 FROM public.journal_entry_lines WHERE lettering_id IS NOT NULL), 'délettrage');

-- ------------------------------------------------------- étape de revue (paramètre des administrateurs)
SELECT pg_temp.fails($q$INSERT INTO public.accounting_settings (company_id, organization_id, review_required) SELECT co, org, true
  FROM o$q$, 'comptable : paramètres réservés aux administrateurs', 'row-level security');
SELECT pg_temp.act_as('e1000000-0000-0000-0000-00000000000a');
INSERT INTO public.accounting_settings (company_id, organization_id, review_required) SELECT co, org, true FROM o;
SELECT pg_temp.act_as('e1000000-0000-0000-0000-00000000000c');
INSERT INTO public.journal_entries (id, organization_id, company_id, fiscal_year_id, journal_id, entry_date, label, created_by)
SELECT '9b000000-0000-0000-0000-000000000005', org, co, fy, '8b000000-0000-0000-0000-0000000000a1', '2025-06-01', 'Facture F20',
       'e1000000-0000-0000-0000-00000000000c' FROM o;
INSERT INTO public.journal_entry_lines (organization_id, company_id, fiscal_year_id, entry_id, line_no, account_number, third_party_id, debit, credit)
SELECT org, co, fy, '9b000000-0000-0000-0000-000000000005', n, a, t, dv, cv FROM o,
  (VALUES (1, '411100', '7b000000-0000-0000-0000-0000000000c1'::uuid, 300.50, 0), (2, '701100', NULL, 0, 300.50)) t(n, a, t, dv, cv);
UPDATE public.journal_entries SET status = 'submitted' WHERE id = '9b000000-0000-0000-0000-000000000005';
SELECT pg_temp.fails($q$UPDATE public.journal_entries SET status = 'under_review' WHERE id = '9b000000-0000-0000-0000-000000000005'$q$,
  'l''auteur ne révise pas sa propre écriture', 'Séparation des tâches');
SELECT pg_temp.act_as('e1000000-0000-0000-0000-00000000000d');
SELECT pg_temp.fails($q$UPDATE public.journal_entries SET status = 'validated' WHERE id = '9b000000-0000-0000-0000-000000000005'$q$,
  'revue obligatoire avant la validation', 'Revue obligatoire');
UPDATE public.journal_entries SET status = 'under_review' WHERE id = '9b000000-0000-0000-0000-000000000005';
UPDATE public.journal_entries SET status = 'validated' WHERE id = '9b000000-0000-0000-0000-000000000005';
SELECT pg_temp.ok((SELECT number = 'VT-000003' AND reviewed_by IS NOT NULL FROM public.journal_entries
  WHERE id = '9b000000-0000-0000-0000-000000000005'), 'revue puis validation : VT-000003, sans trou de numérotation');

-- ------------------------------------------------------- accès et isolation
SELECT pg_temp.act_as('e1000000-0000-0000-0000-00000000000f');
SELECT pg_temp.ok((SELECT count(*) FROM public.journal_entries) = 4, 'lecteur : lecture des écritures');
SELECT pg_temp.fails($q$INSERT INTO public.journal_entries (organization_id, company_id, fiscal_year_id, journal_id, entry_date, label,
  created_by) SELECT org, co, fy, '8b000000-0000-0000-0000-0000000000a1', '2025-05-01', 'X', 'e1000000-0000-0000-0000-00000000000f'
  FROM o$q$, 'lecteur : saisie refusée', 'row-level security');
SELECT pg_temp.act_as('e1000000-0000-0000-0000-000000000005');
SELECT pg_temp.ok((SELECT count(*) FROM public.journal_entry_lines) = 8, 'équipe de mission : lecture seule des écritures de l''entité');
SELECT pg_temp.fails($q$INSERT INTO public.journals (organization_id, company_id, code, label, journal_type, number_prefix, created_by)
  SELECT org, co, 'OD', 'OD', 'general', 'OD-', 'e1000000-0000-0000-0000-000000000005' FROM o$q$,
  'équipe de mission : aucune écriture', 'row-level security');
SELECT pg_temp.act_as('e1000000-0000-0000-0000-00000000000b');
SELECT pg_temp.ok((SELECT count(*) FROM public.journal_entries) + (SELECT count(*) FROM public.journals)
  + (SELECT count(*) FROM public.company_accounts) + (SELECT count(*) FROM public.journal_entry_events) = 0,
  'autre organisation : rien de visible');

-- ------------------------------------------------------- acteur IA
SELECT pg_temp.act_as('e1000000-0000-0000-0000-00000000000c');
SELECT set_config('kofinex.actor', 'ai', true);
SELECT pg_temp.fails($q$INSERT INTO public.journals (organization_id, company_id, code, label, journal_type, number_prefix, created_by)
  SELECT org, co, 'IA', 'IA', 'general', 'IA-', 'e1000000-0000-0000-0000-00000000000c' FROM o$q$, 'acteur IA : aucune écriture', 'IA');
SELECT set_config('kofinex.actor', '', true);

-- ------------------------------------------------------- historique : immuable même pour le propriétaire de la base
RESET ROLE;
SELECT pg_temp.fails($q$UPDATE public.journal_entry_events SET reason = 'x'$q$, 'historique non modifiable', 'non modifiable');

ROLLBACK;
\echo 'Tous les tests de la comptabilité native (SQL) sont passés.'
