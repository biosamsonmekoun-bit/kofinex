-- =====================================================================
-- Tests migration 0019 : plan tiers, rattachement obligatoire à un compte collectif.
-- Auxiliaire alphanumérique (4011TOY) rattaché à un collectif numérique, compatibilité de type, collectif en sommeil,
-- collectif protégé quand des tiers y sont rattachés, reprise contrôlée d'un tiers existant non rattaché.
-- Données FICTIVES ; transaction annulée à la fin.
-- =====================================================================
\set QUIET on
BEGIN;
CREATE OR REPLACE FUNCTION pg_temp.ok(cond boolean, label text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  IF cond IS DISTINCT FROM true THEN RAISE EXCEPTION 'ÉCHEC : %', label; END IF;
  RAISE NOTICE 'ok - %', label;
END $$;
CREATE OR REPLACE FUNCTION pg_temp.fails(q text, label text, expected text DEFAULT NULL) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  BEGIN
    EXECUTE q;
  EXCEPTION WHEN OTHERS THEN
    IF expected IS NOT NULL AND position(expected IN SQLERRM) = 0 THEN
      RAISE EXCEPTION 'ÉCHEC : % (erreur inattendue : %)', label, SQLERRM;
    END IF;
    RAISE NOTICE 'ok - % (refusé : %)', label, SQLERRM; RETURN;
  END;
  RAISE EXCEPTION 'ÉCHEC : % (aucune erreur levée)', label;
END $$;
CREATE OR REPLACE FUNCTION pg_temp.act_as(uid uuid) RETURNS void LANGUAGE sql AS $$
  SELECT set_config('request.jwt.claims', json_build_object('sub', uid, 'role', 'authenticated')::text, true);
$$;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA pg_temp TO authenticated;

INSERT INTO auth.users (id, email) VALUES
  ('e2000000-0000-0000-0000-00000000000a', 'alice@tc.test'), ('e2000000-0000-0000-0000-00000000000c', 'carl@tc.test');
INSERT INTO public.accounting_frameworks (id, code, name) VALUES ('f2000000-0000-0000-0000-0000000000fa', 'TEST_TIERS', 'Test tiers');
SET LOCAL session_replication_role = replica;
INSERT INTO public.profiles (id, email) SELECT id, email FROM auth.users WHERE email LIKE '%@tc.test' ON CONFLICT DO NOTHING;
INSERT INTO public.framework_versions (id, framework_id, version_label, effective_from, source_reference, status, published_at) VALUES
  ('f2000000-0000-0000-0000-0000000000f1', 'f2000000-0000-0000-0000-0000000000fa', 'TEST', '2020-01-01', 'Référentiel FICTIF', 'published', now());
INSERT INTO public.chart_of_accounts (framework_version_id, account_number, label, account_class, nature) VALUES
  ('f2000000-0000-0000-0000-0000000000f1', '401', 'Fournisseurs', 4, 'liability'),
  ('f2000000-0000-0000-0000-0000000000f1', '4011', 'Fournisseurs – divisionnaire', 4, 'liability'),
  ('f2000000-0000-0000-0000-0000000000f1', '4111', 'Clients – divisionnaire', 4, 'asset'),
  ('f2000000-0000-0000-0000-0000000000f1', '601', 'Achats', 6, 'expense');
INSERT INTO public.organizations (id, name, slug, created_by) VALUES
  ('1c000000-0000-0000-0000-00000000000a', 'Cabinet TC', 'cab-tc', 'e2000000-0000-0000-0000-00000000000a');
INSERT INTO public.organization_members (organization_id, user_id, role) VALUES
  ('1c000000-0000-0000-0000-00000000000a', 'e2000000-0000-0000-0000-00000000000a', 'owner'),
  ('1c000000-0000-0000-0000-00000000000a', 'e2000000-0000-0000-0000-00000000000c', 'member');
INSERT INTO public.companies (id, organization_id, name, framework_id, created_by) VALUES
  ('2c000000-0000-0000-0000-00000000000a', '1c000000-0000-0000-0000-00000000000a', 'Société tiers',
   'f2000000-0000-0000-0000-0000000000fa', 'e2000000-0000-0000-0000-00000000000a');
INSERT INTO public.company_members (organization_id, company_id, user_id, role) VALUES
  ('1c000000-0000-0000-0000-00000000000a', '2c000000-0000-0000-0000-00000000000a', 'e2000000-0000-0000-0000-00000000000c', 'accountant');
INSERT INTO public.fiscal_years (id, organization_id, company_id, label, start_date, end_date, status, created_by) VALUES
  ('3c000000-0000-0000-0000-000000002026', '1c000000-0000-0000-0000-00000000000a', '2c000000-0000-0000-0000-00000000000a',
   '2026', '2026-01-01', '2026-12-31', 'open', 'e2000000-0000-0000-0000-00000000000a');
SET LOCAL session_replication_role = origin;

-- reprise : un tiers créé avant la règle, sans compte collectif (la contrainte est NOT VALID, comme dans la migration)
ALTER TABLE public.third_parties DROP CONSTRAINT third_parties_collective_required;
INSERT INTO public.third_parties (id, organization_id, company_id, code, name, kind, created_by) VALUES
  ('7c000000-0000-0000-0000-0000000000a0', '1c000000-0000-0000-0000-00000000000a', '2c000000-0000-0000-0000-00000000000a',
   'ANCIEN01', 'Tiers repris (non rattaché)', 'supplier', 'e2000000-0000-0000-0000-00000000000c');
ALTER TABLE public.third_parties
  ADD CONSTRAINT third_parties_collective_required CHECK (collective_account_number IS NOT NULL) NOT VALID;
SELECT pg_temp.ok((SELECT NOT convalidated FROM pg_constraint WHERE conname = 'third_parties_collective_required'),
                  'contrainte posée sans revalider les tiers existants (aucune donnée modifiée)');

SET LOCAL ROLE authenticated;
SELECT pg_temp.act_as('e2000000-0000-0000-0000-00000000000c');
CREATE TEMP VIEW o AS SELECT '1c000000-0000-0000-0000-00000000000a'::uuid AS org, '2c000000-0000-0000-0000-00000000000a'::uuid AS co,
  '3c000000-0000-0000-0000-000000002026'::uuid AS fy, 'f2000000-0000-0000-0000-0000000000f1'::uuid AS v;
GRANT SELECT ON o TO authenticated;

-- plan : principal 4010000, divisionnaire 4011000 (collectifs fournisseurs), 4111000 (collectif clients), 6011000
INSERT INTO public.company_accounts (organization_id, company_id, account_number, label, framework_version_id, chart_account_number,
                                     requires_third_party, third_party_kind, lettering_enabled, created_by)
SELECT org, co, n, l, v, c, tp, k, tp, 'e2000000-0000-0000-0000-00000000000c' FROM o,
  (VALUES ('4010000', 'Fournisseurs', '401', true, 'supplier'), ('4011000', 'Fournisseurs – divisionnaire 4011', '4011', true, 'supplier'),
          ('4111000', 'Clients – divisionnaire 4111', '4111', true, 'customer'), ('6011000', 'Achats', '601', false, NULL)) t(n, l, c, tp, k);
SELECT pg_temp.fails($q$INSERT INTO public.company_accounts (organization_id, company_id, account_number, label, framework_version_id,
  chart_account_number, created_by) SELECT org, co, '4011TOY', 'Auxiliaire en compte', v, '4011', 'e2000000-0000-0000-0000-00000000000c' FROM o$q$,
  'plan comptable numérique : un auxiliaire alphanumérique n''est pas un compte', 'check');

-- ------------------------------------------------------- plan tiers
SELECT pg_temp.fails($q$INSERT INTO public.third_parties (organization_id, company_id, code, name, kind, created_by)
  SELECT org, co, 'SANSCOLL', 'Sans collectif', 'supplier', 'e2000000-0000-0000-0000-00000000000c' FROM o$q$,
  'tiers sans compte collectif refusé', 'third_parties_collective_required');
SELECT pg_temp.fails($q$INSERT INTO public.third_parties (organization_id, company_id, code, name, kind, collective_account_number, created_by)
  SELECT org, co, '4111TOY', 'Client TOYOTA', 'customer', '4011000', 'e2000000-0000-0000-0000-00000000000c' FROM o$q$,
  'client rattaché à un collectif fournisseurs refusé', 'compte collectif');
SELECT pg_temp.fails($q$INSERT INTO public.third_parties (organization_id, company_id, code, name, kind, collective_account_number, created_by)
  SELECT org, co, 'X1', 'Sur un compte non collectif', 'supplier', '6011000', 'e2000000-0000-0000-0000-00000000000c' FROM o$q$,
  'rattachement à un compte non collectif refusé', 'compte collectif');
INSERT INTO public.third_parties (id, organization_id, company_id, code, name, kind, collective_account_number, created_by)
SELECT i, org, co, c, n, k, a, 'e2000000-0000-0000-0000-00000000000c' FROM o,
  (VALUES ('7c000000-0000-0000-0000-0000000000f1'::uuid, '4011TOY', 'Fournisseur TOYOTA', 'supplier', '4011000'),
          ('7c000000-0000-0000-0000-0000000000c1'::uuid, '4111TOY', 'Client TOYOTA', 'customer', '4111000')) t(i, c, n, k, a);
SELECT pg_temp.ok((SELECT count(*) FROM public.third_parties WHERE code IN ('4011TOY', '4111TOY')) = 2,
                  'auxiliaires alphanumériques 4011TOY et 4111TOY rattachés à leur collectif');

-- collectif en sommeil
UPDATE public.company_accounts SET is_active = false WHERE account_number = '4010000';
SELECT pg_temp.fails($q$INSERT INTO public.third_parties (organization_id, company_id, code, name, kind, collective_account_number, created_by)
  SELECT org, co, '4010NEW', 'Nouveau', 'supplier', '4010000', 'e2000000-0000-0000-0000-00000000000c' FROM o$q$,
  'rattachement à un collectif en sommeil refusé', 'en sommeil');
SELECT pg_temp.fails($q$UPDATE public.third_parties SET collective_account_number = '4010000' WHERE code = '4011TOY'$q$,
                     'transfert vers un collectif en sommeil refusé', 'en sommeil');
UPDATE public.third_parties SET name = 'Fournisseur TOYOTA SA' WHERE code = '4011TOY';
SELECT pg_temp.ok((SELECT name FROM public.third_parties WHERE code = '4011TOY') = 'Fournisseur TOYOTA SA',
                  'modification d''un tiers sans changement de collectif permise');

-- collectif protégé tant que des tiers y sont rattachés
SELECT pg_temp.fails($q$UPDATE public.company_accounts SET requires_third_party = false, third_party_kind = NULL
                        WHERE account_number = '4011000'$q$, 'collectif avec tiers : caractère collectif conservé', 'tiers rattachés');
SELECT pg_temp.fails($q$UPDATE public.company_accounts SET third_party_kind = 'customer' WHERE account_number = '4011000'$q$,
                     'collectif avec tiers : type incompatible refusé', 'tiers rattachés');
UPDATE public.company_accounts SET label = 'Fournisseurs – locaux' WHERE account_number = '4011000';
SELECT pg_temp.ok((SELECT label FROM public.company_accounts WHERE account_number = '4011000') = 'Fournisseurs – locaux',
                  'collectif avec tiers : intitulé modifiable');

-- ------------------------------------------------------- reprise contrôlée du tiers non rattaché
INSERT INTO public.journals (id, organization_id, company_id, code, label, journal_type, number_prefix, created_by)
SELECT '8c000000-0000-0000-0000-0000000000a1', org, co, 'HA', 'Achats', 'purchases', 'HA-', 'e2000000-0000-0000-0000-00000000000c' FROM o;
INSERT INTO public.journal_entries (id, organization_id, company_id, fiscal_year_id, journal_id, entry_date, label, created_by)
SELECT '9c000000-0000-0000-0000-000000000001', org, co, fy, '8c000000-0000-0000-0000-0000000000a1', '2026-02-10', 'Facture', 'e2000000-0000-0000-0000-00000000000c' FROM o;
SELECT pg_temp.fails($q$UPDATE public.third_parties SET name = 'Renommé' WHERE code = 'ANCIEN01'$q$,
                     'tiers repris : toute modification exige le rattachement', 'third_parties_collective_required');
SELECT pg_temp.fails($q$INSERT INTO public.journal_entry_lines (organization_id, company_id, fiscal_year_id, entry_id, line_no, account_number,
  third_party_id, credit) SELECT org, co, fy, '9c000000-0000-0000-0000-000000000001', 1, '4011000', '7c000000-0000-0000-0000-0000000000a0', 100 FROM o$q$,
  'tiers non rattaché : inutilisable sur une écriture', 'non rattaché');
UPDATE public.third_parties SET collective_account_number = '4011000' WHERE code = 'ANCIEN01';
INSERT INTO public.journal_entry_lines (organization_id, company_id, fiscal_year_id, entry_id, line_no, account_number, third_party_id, debit, credit)
SELECT org, co, fy, '9c000000-0000-0000-0000-000000000001', n, a, t, dv, cv FROM o,
  (VALUES (1, '4011000', '7c000000-0000-0000-0000-0000000000a0'::uuid, 0, 100), (2, '6011000', NULL::uuid, 100, 0)) t(n, a, t, dv, cv);
SELECT pg_temp.ok((SELECT line_count FROM public.journal_entries WHERE id = '9c000000-0000-0000-0000-000000000001') = 2,
                  'tiers repris rattaché : de nouveau utilisable');
SELECT pg_temp.fails($q$DELETE FROM public.company_accounts WHERE account_number = '4011000'$q$,
                     'compte utilisé (lignes et tiers) : suppression refusée', 'foreign key');

RESET ROLE;
ROLLBACK;
\echo 'Tous les tests du plan tiers (SQL) sont passés.'
