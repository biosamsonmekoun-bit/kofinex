// Audit financier (lot 7) : types et libellés partagés par les onglets de la mission.
import type { PersonRef } from "./types";

export interface FaMateriality {
  id: string; version: number; benchmark_label: string; benchmark_source: "statement_line" | "manual";
  benchmark_line_code: string | null; benchmark_amount: string; overall_pct: string; overall_amount: string;
  performance_pct: string; performance_amount: string; trivial_pct: string; trivial_amount: string; basis: string;
  status: "draft" | "approved" | "superseded"; approved_at: string | null; created_at: string;
  created_by_user?: PersonRef | null; approved_by_user?: PersonRef | null;
}
export interface FaCheck { code: string; label: string; passed: boolean; detail: string | null }
export interface FaOverview {
  materiality: FaMateriality | null; accounts: Record<string, number>; samples: Record<string, number>;
  confirmations: Record<string, number>; misstatements: Record<string, number>; checks: FaCheck[];
}
export interface StatementLine { statement_type: string; code: string; label: string; kind: string; role: string | null; net: string | null }
export interface FaAccount {
  id: string; account_number: string; account_label: string | null; cycle_code: string | null; balance_n: string;
  balance_n1: string | null; variation: string | null; threshold_used: string | null; requires_explanation: boolean;
  explanation: string | null; conclusion: string | null; status: "to_review" | "reviewed"; workpaper_id: string | null;
  reviewed_at: string | null;
}
export interface FaCycleTotal { cycle_code: string | null; accounts: number; balance_n: string; balance_n1: string; to_review: number; to_explain: number }
export interface FaPopulation {
  id: string; name: string; description: string | null; source: "balance" | "file" | "ledger"; account_prefixes: string[];
  item_count: number; total_amount: string; absolute_total: string; sha256: string; created_at: string; frozen: boolean;
}
export interface FaPopItem { id: string; line_no: number; reference: string; item_date: string | null; label: string | null; account_number: string | null; amount: string }
export type SampleMethod = "random" | "systematic" | "mus" | "key_items" | "judgmental";
export interface FaSampleItem {
  id: string; population_item_id: string; selection_reason: string; book_amount: string; audited_amount: string | null;
  misstatement: string | null; result: "pending" | "no_exception" | "exception"; comment: string | null; tested_at: string | null;
  item: FaPopItem;
}
export interface FaProjection { method: string; tested: number; pending: number; actual: string; projected: string | null; explanation: string }
export interface FaSample {
  id: string; population_id: string; reference: string; objective: string; method: SampleMethod; requested_size: number | null;
  size_basis: string; seed: number | null; parameters: Record<string, string | number>; selected_count: number;
  status: "testing" | "concluded"; actual_misstatement: string | null; projected_misstatement: string | null;
  projection: FaProjection | null; conclusion: string | null; concluded_at: string | null; tested: number; exceptions: number;
  population: { id: string; name: string; item_count: number; absolute_total: string } | null;
  items?: FaSampleItem[]; preview?: FaProjection | null;
}
export type ConfStatus = "prepared" | "sent" | "received" | "no_response" | "closed";
export interface FaConfirmation {
  id: string; reference: string; confirmation_type: string; third_party: string; contact: string | null; account_number: string | null;
  balance_date: string; book_balance: string | null; request_form: "positive" | "negative" | "blank"; status: ConfStatus;
  sent_on: string | null; reminder_dates: string[]; received_on: string | null; confirmed_amount: string | null; difference: string | null;
  reconciliation: string | null; alternative_procedures: string | null; conclusion: string | null; closed_at: string | null;
}
export type MsStatus = "proposed" | "corrected" | "uncorrected" | "withdrawn";
export interface FaMisstatement {
  id: string; reference: string; source_type: string; source_id: string | null; kind: "factual" | "judgmental" | "projected";
  description: string; status: MsStatus; entity_response: string | null; withdrawn_reason: string | null; decided_at: string | null;
  lines: { id: string; account_number: string; label: string | null; debit: string; credit: string }[];
}
export interface FaAggregate {
  count: number; effect_result?: string; effect_total_assets?: string; position?: Position | null;
  effects: { statement_type: string; code: string; label: string; before: string; after: string; delta: string }[] | null;
}
export type Position = "below_trivial" | "below_overall" | "above_overall";
export interface FaSummary {
  framework_available: boolean; materiality: { overall: string; performance: string; trivial: string; version: number } | null;
  items: { id: string; reference: string; kind: string; status: MsStatus; description: string; amount: string; effect_result: string | null; position: Position | null }[];
  corrected: FaAggregate; uncorrected: FaAggregate; proposed: FaAggregate;
  conclusion: { text: string; updated_at: string } | null;
}

export const METHOD_LABELS: Record<SampleMethod, string> = {
  random: "Aléatoire simple", systematic: "Systématique", mus: "Unités monétaires", key_items: "Éléments clés (au-dessus d'un seuil)",
  judgmental: "Sélection raisonnée",
};
export const REASON_LABELS: Record<string, string> = { random: "Tirage", interval: "Intervalle", key_item: "Élément clé", judgment: "Choix" };
export const CONF_TYPE_LABELS: Record<string, string> = {
  receivable: "Client", payable: "Fournisseur", bank: "Banque", legal: "Avocat / conseil", other: "Autre",
};
export const CONF_FORM_LABELS = { positive: "Positive", negative: "Négative", blank: "En blanc (solde non indiqué)" } as const;
export const CONF_STATUS: Record<ConfStatus, [string, "neutral" | "blue" | "amber" | "green" | "red"]> = {
  prepared: ["Préparée", "neutral"], sent: ["Envoyée", "blue"], received: ["Reçue", "amber"], no_response: ["Sans réponse", "red"],
  closed: ["Close", "green"],
};
export const MS_STATUS: Record<MsStatus, [string, "neutral" | "blue" | "amber" | "green" | "red"]> = {
  proposed: ["Proposée", "amber"], corrected: ["Corrigée par l'entité", "green"], uncorrected: ["Non corrigée", "red"],
  withdrawn: ["Retirée", "neutral"],
};
export const MS_KIND_LABELS = { factual: "Avérée", judgmental: "De jugement", projected: "Extrapolée" } as const;
export const POSITION_LABELS: Record<Position, [string, "green" | "amber" | "red"]> = {
  below_trivial: ["Sous le seuil des anomalies insignifiantes", "green"], below_overall: ["Sous le seuil de signification", "amber"],
  above_overall: ["Égale ou supérieure au seuil de signification", "red"],
};

/** Saisie française (« 1 200,50 ») → décimal pour l'API (« 1200.50 ») ; null si vide ; NaN refusé. */
export function toDecimal(input: string): string | null {
  const s = input.replace(/[\s  ]/g, "").replace(",", ".");
  if (!s) return null;
  if (!/^-?\d+(\.\d{1,2})?$/.test(s)) throw new Error(`Montant invalide : « ${input} » (2 décimales au plus).`);
  return s;
}
