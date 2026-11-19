-- =====================================================================
-- KOFINEX — Migration 0017 : types des états financiers produits par l'analyse
-- La migration 0005 a défini la structure des états avec les types balance_sheet_assets, balance_sheet_liabilities et
-- off_balance (statement_line_definitions), mais la contrainte de financial_statements (migration 0001) ne les acceptait
-- pas : l'analyse financière, qui crée un état par type de la structure, échouait à l'enregistrement.
-- Les valeurs d'origine (balance_sheet, notes) sont conservées : aucune ligne existante n'est rendue invalide.
-- =====================================================================
ALTER TABLE public.financial_statements
  DROP CONSTRAINT financial_statements_statement_type_check,
  ADD CONSTRAINT financial_statements_statement_type_check CHECK (statement_type IN
    ('balance_sheet_assets','balance_sheet_liabilities','income_statement','cash_flow','off_balance',
     'balance_sheet','notes'));
