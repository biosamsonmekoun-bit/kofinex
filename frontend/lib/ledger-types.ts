// Grand livre (complément du lot 3) : types partagés.
import type { ControlResult, ImportStatus } from "./types";

export interface LedgerSheet {
  name: string; rows: number; columns: number; header_row: number | null; suggested_mapping: Record<string, number>;
  headers: string[]; format: "fec" | "generic"; warnings: string[]; notes: string[]; preview_start: number;
  preview: (string | number | null)[][];
}
export interface LedgerOptions {
  decimal_separator: "," | "." | null; amount_sign: "debit_positive" | "credit_positive" | null;
  negative_amounts: "error" | "move_to_other_side"; opening_journals: string[]; skip_zero_lines: boolean;
  /** replace : remplace le grand livre actif (fichier complet ou correctif) ; complement : le complète (doublons écartés). */
  mode?: "replace" | "complement";
}
/** Résultat d'un import complémentaire (contrôles de l'import). */
export interface ComplementSummary {
  carried: number; duplicates: number; added: number; conflicts: number; added_months: string[]; existing_months: string[];
  overlapping_months: string[]; complement_of: string;
}
export interface LedgerJob {
  id: string; company_id: string; fiscal_year_id: string; document_id: string | null; source_format: string; status: ImportStatus;
  kind: "ledger"; sheet_name: string | null; header_row: number | null; column_map: Record<string, number> | null;
  options: Partial<LedgerOptions>; sheets: LedgerSheet[] | null; extraction: Record<string, unknown>;
  controls: { results: ControlResult[]; totals: Record<string, Record<string, string>>; line_count: number; blocking: boolean;
              requires_acknowledgment: boolean; complement?: ComplementSummary } | null;
  total_rows: number | null; valid_rows: number | null; error_rows: number | null; failure_reason: string | null;
  validated_at: string | null; field_labels: Record<string, string>; fields: string[];
}
export interface LedgerImportRow {
  id: string; status: ImportStatus; source_format: string; filename: string | null; fiscal_year_id: string; fiscal_year_label: string | null;
  valid_rows: number | null; error_rows: number | null; blocking: boolean | null; active: boolean; created_at: string; validated_at: string | null;
}
export interface LedgerLineRow {
  id?: string; source_row: number; status?: string; issues?: { code: string; field: string | null; message: string }[];
  journal_code: string | null; journal_label: string | null; entry_number: string | null; entry_date: string | null;
  document_ref: string | null; document_date: string | null; account_number: string | null; account_label: string | null;
  auxiliary_account: string | null; auxiliary_label: string | null; label: string | null; debit: string; credit: string;
  lettering: string | null; lettering_date: string | null; validation_date: string | null; currency_amount: string | null;
  currency: string | null; running_balance?: string | null;
}
export interface LedgerPage {
  import_job_id: string; total_count: number; totals: { debit: string; credit: string; net: string };
  opening_balance: string | null; running_balance: boolean; items: LedgerLineRow[];
}
export interface LedgerAccount {
  account_number: string; label: string | null; lines: number; opening: string; debit: string; credit: string; balance: string;
  tb: { movement_debit: string; movement_credit: string; opening: string; closing: string; movement_gap: boolean; opening_gap: boolean } | null;
}
export interface LedgerJournal {
  journal: string; label: string | null; debit: string; credit: string; lines: number;
  months: { period: number; month: string; entries: number; lines: number; debit: string; credit: string }[];
}
export interface LedgerAnalytics {
  weekend_entries: { count: number; entries: { journal: string; entry_number: string | null; entry_date: string; lines: number; debit: string; weekday: string }[] };
  possible_duplicates: { account_number: string; entry_date: string; debit: string; credit: string; label: string; occurrences: number; entries: number }[];
  lines_without_label: number; validated_after_year_end: number | null;
  numbering_gaps: { journal: string; gaps: { from: number; to: number }[]; numeric: number; total: number }[];
  round_amounts: { multiple: string; count: number; lines: { journal: string; entry_number: string | null; entry_date: string; account_number: string; label: string | null; debit: string; credit: string }[] } | null;
  benford: { min_amount: string; count: number; digits: { digit: number; observed: number; observed_pct: string | null; expected_pct: string }[] };
  notes: string[];
}
