// Intelligence artificielle (lot 10) : types partagés.
import type { PersonRef } from "@/lib/types";

export interface AiValidation {
  rule: string; status: "verified" | "warning"; checked: number; untraceable: { text: string; value: string }[];
  discarded_by_kofinex?: string[]; request?: string;
}
export interface AiStatus {
  configured: boolean; reason: string | null; provider: string | null; model: string | null; prompt_version: string; uses: Record<string, string>;
}
export interface AiSettings {
  organization_id: string; enabled: boolean; allowed_uses: string[]; acceptance_note: string | null; updated_at: string | null;
  can_edit: boolean; status: AiStatus;
}
export interface AiFact { ref: string; label: string; value?: string; unit?: string; period?: string; source?: string }
export interface AiSnapshot { purpose: string; title: string; facts: AiFact[]; data: Record<string, unknown> }
export interface AiMessage {
  id: string; role: "user" | "assistant"; content: string; context_snapshot: AiSnapshot | null; model: string | null;
  input_tokens: number | null; output_tokens: number | null; validation: AiValidation | null; prompt_version: string | null; created_at: string;
}
export interface AiConversation { id: string; fiscal_year_id: string | null; analysis_id: string | null; title: string | null; created_at: string; updated_at: string }
export interface AiReport {
  id: string; analysis_id: string; section: string; content: string; context_snapshot: AiSnapshot; model: string; prompt_version: string;
  validation: AiValidation | null; status: "draft" | "reviewed" | "rejected"; reviewed_at: string | null; review_note: string | null;
  created_at: string; created_by_user?: PersonRef | null; reviewed_by_user?: PersonRef | null;
}
export type SuggestionKind = "engagement_risk" | "procedure" | "finding_draft" | "synthesis_draft" | "anomaly_explanation";
export interface AiSuggestion {
  id: string; kind: SuggestionKind; kind_label: string; payload: Record<string, unknown>; sources: string[]; validation: AiValidation;
  context_snapshot: AiSnapshot | null;
  model: string; prompt_version: string; status: "pending" | "accepted" | "rejected"; decided_at: string | null; decision_note: string | null;
  accepted_payload: Record<string, unknown> | null; created_object_type: string | null; created_object_id: string | null; created_at: string;
  requested_by_user: PersonRef | null; decided_by_user: PersonRef | null;
}
export const SUGGESTION_STATUS: Record<string, [string, "neutral" | "green" | "red"]> = {
  pending: ["En attente de décision", "neutral"], accepted: ["Acceptée", "green"], rejected: ["Rejetée", "red"],
};
export const REPORT_STATUS: Record<string, [string, "amber" | "green" | "red"]> = {
  draft: ["Brouillon IA non relu", "amber"], reviewed: ["Relu", "green"], rejected: ["Rejeté", "red"],
};
