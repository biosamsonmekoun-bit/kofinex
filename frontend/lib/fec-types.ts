/** FEC DGI Bénin (arrêté n° 1085 du 23 avril 2020) : types de l'API `/companies/{id}/accounting/fec`. */

export type FecCompliance = "compliant" | "spec_pending" | "non_compliant";

export interface FecAnomaly {
  code: string; severity: "blocking" | "warning"; nature: string; description: string; action: string;
  entry_id: string | null; number: string | null; entry_date: string | null; journal: string | null; account: string | null;
}

export interface FecPoint { key: string; label: string; detail: string }

export interface FecFieldSpec { order: number; name: string; information: string; type: string; mandatory: boolean; format: string; source: string }

export interface FecSpec {
  version: string; confirmed: boolean; fields: FecFieldSpec[]; cash_fields: FecFieldSpec[];
  formats: string[]; encodings: Record<string, string>; separators: Record<string, string>; record_separators: Record<string, string>;
  filename_pattern: string; split_pattern: string; applied: FecPoint[]; unconfirmed: FecPoint[];
}

export interface FecPart { part: number | null; filename: string; size_bytes: number; sha256: string; line_count: number }

export interface FecExport {
  id: string; version_no: number; kind: "final" | "working"; period_start: string; period_end: string; filename: string;
  parts: FecPart[]; file_format: string; encoding: string; field_separator: string; record_separator: string;
  accounting_type: "accrual" | "cash"; line_count: number; entry_count: number; total_debit: string; total_credit: string;
  blocking_count: number; warning_count: number; compliance: FecCompliance; spec_version: string; spec_confirmed: boolean;
  sha256: string; size_bytes: number; doc_sha256: string; generated_by: string; generated_at: string; generated_by_name?: string | null;
}

export interface FecDashboard {
  fiscal_year: { id: string; label: string; start_date: string; end_date: string; status: string };
  company: { name: string; ifu: string | null; country_code: string | null };
  entries_total: number; entries_validated: number; entries_eligible: number;
  anomalies_blocking: number; anomalies_warning: number; last_export: FecExport | null; spec_confirmed: boolean;
}

export interface FecCheck {
  period_start: string; period_end: string; entries: number; eligible: number; lines: number; blocking: number; warnings: number;
  compliance: FecCompliance; can_generate_final: boolean; can_generate_working: boolean; total_debit: string; total_credit: string;
  anomalies: FecAnomaly[]; spec_confirmed: boolean; unconfirmed: FecPoint[]; filenames?: string[];
}

export const COMPLIANCE: Record<FecCompliance, { label: string; tone: "green" | "amber" | "red" }> = {
  compliant: { label: "Conforme", tone: "green" },
  spec_pending: { label: "Sans anomalie bloquante · points réglementaires à confirmer", tone: "amber" },
  non_compliant: { label: "Non conforme (fichier de travail)", tone: "red" },
};
