/** Comptabilité native (lot 3B) : types des réponses de l'API /companies/{id}/accounting/… (montants en chaînes décimales). */
import type { PersonRef } from "@/lib/types";

export type Dec = string;
export type EntryStatus = "draft" | "submitted" | "under_review" | "validated" | "rejected" | "reversed";
export type EntryOrigin = "manual" | "generated" | "inventory" | "reversal" | "correction" | "opening";
export type TpKind = "customer" | "supplier" | "employee" | "tax_authority" | "social_body" | "other";
export type JournalType = "purchases" | "sales" | "bank" | "cash" | "general" | "payroll" | "fixed_assets" | "inventory" | "opening";

export interface AccSettings {
  review_required: boolean; segregation_required: boolean; updated_at: string | null;
  permissions: { setup: boolean; settings: boolean; write: boolean; validate: boolean; fec?: boolean };
}
export interface CompanyAccount {
  id: string; account_number: string; label: string; chart_account_number: string; framework_version_id: string; nature: string | null;
  requires_third_party: boolean; third_party_kind: TpKind | null; lettering_enabled: boolean; is_active: boolean; used?: boolean;
}
export interface ThirdParty {
  id: string; code: string; name: string; kind: TpKind; collective_account_number: string | null; tax_id: string | null;
  registration_number: string | null; address: string | null; city: string | null; country_code: string | null; email: string | null;
  phone: string | null; is_active: boolean;
}
export interface Journal {
  id: string; code: string; label: string; journal_type: JournalType; number_prefix: string; counterpart_account_number: string | null;
  allowed_users: string[] | null; is_active: boolean; entries: number;
}
export interface TpRef { id: string; code: string; name: string; kind?: TpKind }
export interface EntryRow {
  id: string; fiscal_year_id: string; journal_id: string; journal_code: string | null; entry_date: string; piece_ref: string | null;
  label: string; origin: EntryOrigin; status: EntryStatus; number: string | null; total_debit: Dec; total_credit: Dec; line_count: number;
  author?: PersonRef | null; rejection_reason: string | null;
}
export interface EntryLine {
  id: string; line_no: number; account_number: string; account_label: string | null; third_party: TpRef | null; label: string | null;
  debit: Dec; credit: Dec; cost_center_id: string | null; currency: string | null; currency_amount: Dec | null; lettering_id: string | null;
}
export interface EntryDetail extends EntryRow {
  piece_date: string | null; third_party_id: string | null; third_party: TpRef | null; journal_label: string | null; journal_type: JournalType | null;
  reverses_entry_id: string | null; corrects_entry_id: string | null; reversed_by_entry_id: string | null;
  people: Record<string, PersonRef | undefined>; lines: EntryLine[];
  check: { balanced: boolean; difference: Dec; issues: string[] } | null;
  events: { action: string; from_status: string | null; to_status: string | null; reason: string | null; at: string; actor: PersonRef | null }[];
  attachments: { document_id: string; filename: string; size_bytes: number; mime_type: string; attached_at: string }[];
  related: Record<string, { id: string; number: string | null; status: EntryStatus; label: string }>;
  settings: { review_required: boolean; segregation_required: boolean };
  actions: Record<"edit" | "delete" | "submit" | "withdraw" | "start_review" | "validate" | "reject" | "reopen" | "reverse" | "duplicate", boolean>;
}
export interface LedgerLine {
  entry_date: string; journal: string; number: string; entry_id: string; line_id: string; piece_ref: string | null; label: string | null;
  third_party: TpRef | null; debit: Dec; credit: Dec; balance: Dec; lettering: string | null; origin: EntryOrigin;
}
export interface LedgerAccount { account: string; label: string | null; opening: Dec; debit: Dec; credit: Dec; closing: Dec; lines: LedgerLine[] }
export interface BalanceRow {
  account: string; label: string | null; third_party: TpRef | null; opening_debit: Dec; opening_credit: Dec; debit: Dec; credit: Dec;
  closing_debit: Dec; closing_credit: Dec;
}
export interface BalanceData {
  fiscal_year: { id: string; label: string; status: string }; scope: string; auxiliary: boolean; rows: BalanceRow[];
  totals: Record<"opening_debit" | "opening_credit" | "debit" | "credit" | "closing_debit" | "closing_credit", Dec>;
  checks: Record<"opening_balanced" | "movements_balanced" | "closing_balanced", boolean>; balanced: boolean;
  entries_count: number; pending_count: number;
  comparative: null | { available: false; reason: string } | { available: true; previous_label: string; rows: { account: string; label: string | null; current: Dec; previous: Dec; change: Dec }[] };
}

export const STATUS_LABEL: Record<EntryStatus, string> = {
  draft: "Brouillon", submitted: "Soumise", under_review: "En revue", validated: "Validée", rejected: "Rejetée", reversed: "Extournée",
};
export const STATUS_TONE: Record<EntryStatus, "neutral" | "blue" | "green" | "amber" | "red" | "gold"> = {
  draft: "neutral", submitted: "blue", under_review: "amber", validated: "green", rejected: "red", reversed: "neutral",
};
export const ORIGIN_LABEL: Record<EntryOrigin, string> = {
  manual: "Saisie", generated: "Générée", inventory: "Inventaire", reversal: "Extourne", correction: "Correction", opening: "À-nouveaux",
};
export const TP_KIND_LABEL: Record<TpKind, string> = {
  customer: "Client", supplier: "Fournisseur", employee: "Salarié", tax_authority: "Administration fiscale", social_body: "Organisme social", other: "Autre",
};
export const JOURNAL_TYPE_LABEL: Record<JournalType, string> = {
  purchases: "Achats", sales: "Ventes", bank: "Banque", cash: "Caisse", general: "Opérations diverses", payroll: "Paie",
  fixed_assets: "Immobilisations", inventory: "Stocks", opening: "À-nouveaux",
};

const nf = new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
/** Mise en forme d'un montant décimal (chaîne) sans passer par un calcul flottant. */
export function amount(v: Dec | number | null | undefined, blankZero = false): string {
  if (v === null || v === undefined || v === "") return "";
  const n = Number(v);
  if (blankZero && n === 0) return "";
  return nf.format(n);
}
/** Addition exacte de montants décimaux à deux décimales (en centimes entiers). */
export function sumDec(values: (Dec | null | undefined)[]): string {
  let cents = BigInt(0);
  for (const v of values) cents += toCents(v);
  return fromCents(cents);
}
export function toCents(v: Dec | null | undefined): bigint {
  const s = (v ?? "").toString().trim().replace(/\s/g, "").replace(",", ".");
  if (!s) return BigInt(0);
  const m = /^(\d+)(?:\.(\d{0,2}))?$/.exec(s);
  if (!m) return BigInt(0);
  return BigInt(m[1]) * BigInt(100) + BigInt((m[2] ?? "").padEnd(2, "0") || "0");
}
export function fromCents(c: bigint): string {
  const neg = c < BigInt(0); const a = neg ? -c : c;
  return `${neg ? "-" : ""}${a / BigInt(100)}.${(a % BigInt(100)).toString().padStart(2, "0")}`;
}
export function isAmount(v: string): boolean { return v.trim() === "" || /^\d+(?:[.,]\d{0,2})?$/.test(v.trim().replace(/\s/g, "")); }
