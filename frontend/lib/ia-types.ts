// Audit interne (lot 8) : types et libellés partagés.
import type { PersonRef } from "./types";

export type PlanStatus = "draft" | "approved" | "closed";
export type PlanItemStatus = "planned" | "in_progress" | "completed" | "postponed" | "cancelled";
export interface PlanItem {
  id: string; plan_id: string; company_id: string; process_id: string | null; title: string; rationale: string;
  priority_rank: number | null; planned_start: string | null; planned_end: string | null; budget_days: string | null;
  engagement_id: string | null; status: PlanItemStatus; status_reason: string | null; added_after_approval: boolean;
  change_reason: string | null; company: string | null; process: string | null;
  engagement: { id: string; reference: string; status: string } | null;
}
export interface AuditPlan {
  id: string; organization_id: string; title: string; period_start: string; period_end: string; description: string | null;
  status: PlanStatus; approval_body: string | null; approval_reference: string | null; approval_date: string | null;
  approved_at: string | null; approved_by_user?: PersonRef | null; can_manage?: boolean; items?: PlanItem[] | number;
  summary?: { items: number; by_status: Record<string, number>; budget_days: string; completed_budget_days: string;
              added_after_approval: number; completion_rate: string | null };
}
export interface PlanHistory { id: string; operation: "insert" | "update"; changed_fields: string[]; reason: string | null;
  after: Record<string, unknown>; changed_by: PersonRef | null; changed_at: string }

export const PLAN_STATUS: Record<PlanStatus, [string, "neutral" | "green" | "amber"]> = {
  draft: ["Brouillon", "neutral"], approved: ["Approuvé", "green"], closed: ["Clôturé", "amber"],
};
export const ITEM_STATUS: Record<PlanItemStatus, [string, "neutral" | "blue" | "green" | "amber" | "red"]> = {
  planned: ["Prévue", "neutral"], in_progress: ["En cours", "blue"], completed: ["Réalisée", "green"],
  postponed: ["Reportée", "amber"], cancelled: ["Annulée", "red"],
};
export const FIELD_LABELS: Record<string, string> = {
  title: "intitulé", company_id: "entité", process_id: "processus", rationale: "justification", priority_rank: "priorité",
  planned_start: "début", planned_end: "fin", budget_days: "budget", engagement_id: "mission", status: "statut",
  status_reason: "motif du statut", change_reason: "motif de modification",
};

// ---------------------------------------------------------------- cartographie
export interface MapCell { likelihood: number; impact: number; score: number; significant: boolean | null;
  risks: { id: string; code: string; title: string; process: string | null; score: number; significant: boolean | null }[] }
export interface RiskMap {
  basis: "inherent" | "residual"; scale_version_id: string | null; scale_versions: string[];
  map: { likelihood: { score: number; label: string }[]; impact: { score: number; label: string }[]; significant_from: number | null;
         cells: MapCell[]; unrated: { id: string; code: string; title: string }[];
         invalid: { id: string; code: string; title: string; message: string }[] } | null;
  unscaled: { id: string; code: string; title: string }[]; other_scale: { id: string; code: string; title: string }[];
  processes: { id: string; code: string; name: string; parent_id: string | null; owner_name: string | null; is_active: boolean;
               risks: number; plan_items: { title: string; status: PlanItemStatus; plan: string | null; planned_start: string | null }[] }[];
}
export interface RegistryRisk {
  id: string; code: string; title: string; description: string | null; process_id: string | null; scale_version_id: string | null;
  inherent_likelihood: number | null; inherent_impact: number | null; residual_likelihood: number | null; residual_impact: number | null;
  status: "active" | "retired";
}

// ---------------------------------------------------------------- constats
export type FindingStatus = "draft" | "validated" | "communicated" | "closed";
export type ActionStatus = "planned" | "in_progress" | "implemented" | "verified" | "not_implemented" | "risk_accepted";
export interface ActionPlan {
  id: string; recommendation_id: string; description: string; owner_name: string; owner_user_id: string | null; due_date: string;
  status: ActionStatus; overdue?: boolean; updates?: ActionUpdate[];
}
export interface ActionUpdate { id: string; status: ActionStatus; comment: string; new_due_date: string | null; author_role: string;
  author: PersonRef | null; created_at: string }
export interface Recommendation { id: string; finding_id: string; reference: string; text: string; action_plans: ActionPlan[] }
export interface Finding {
  id: string; origin?: string; ai_suggestion_id?: string | null; reference: string; title: string; condition: string; criteria: string; cause: string | null; effect: string | null;
  rating_code: string | null; rating_label: string | null; rating_rank: number | null; process_id: string | null; process: string | null;
  engagement_risk_id: string | null; risk: string | null; workpaper_id: string | null; status: FindingStatus;
  validated_at: string | null; communicated_at: string | null; response_due: string | null; management_response: string | null;
  response_by_name: string | null; response_at: string | null; reopen_reason: string | null; created_by: string;
  kind: "audit_finding" | "ic_deficiency" | "management_letter_point"; control_id: string | null; risk_id: string | null;
  domain_id: string | null; closed_at: string | null; closure_note: string | null;
  created_by_user: PersonRef | null; validated_by_user: PersonRef | null; recommendations: Recommendation[];
}
export interface FindingLevel { code: string; label: string; rank: number }

export const FINDING_STATUS: Record<FindingStatus, [string, "neutral" | "blue" | "green"]> = {
  draft: ["Brouillon", "neutral"], validated: ["Validé", "blue"], communicated: ["Communiqué à l'audité", "green"],
  closed: ["Clos", "green"],
};
export const ACTION_STATUS: Record<ActionStatus, [string, "neutral" | "blue" | "amber" | "green" | "red"]> = {
  planned: ["Prévue", "neutral"], in_progress: ["En cours", "blue"], implemented: ["Mise en œuvre (déclarée)", "amber"],
  verified: ["Vérifiée", "green"], not_implemented: ["Non mise en œuvre", "red"], risk_accepted: ["Risque accepté", "amber"],
};
export const ROLE_SHORT: Record<string, string> = {
  partner: "Associé", manager: "Manager", in_charge: "Chef de mission", staff: "Auditeur", auditee: "Audité",
};

// ---------------------------------------------------------------- rapports
export interface AuditReport {
  id: string; version: number; title: string; executive_summary: string | null; overall_conclusion: string | null;
  distribution: string | null; status: "draft" | "issued" | "superseded"; content_sha256: string | null; issued_at: string | null;
  issued_by_user: PersonRef | null; created_at: string;
}
export interface ReportContent {
  draft: boolean; title: string; version: number; executive_summary: string | null; overall_conclusion: string | null;
  distribution: string | null; issued_at?: string | null; content_sha256?: string | null; issued_by_name?: string | null;
  engagement: { reference: string; name: string; company: string; objectives: string | null; scope: string | null;
                period_start: string | null; period_end: string | null };
  methodology: { name: string; version_label: string; source_reference: string } | null;
  rating_counts: { code: string | null; label: string; count: number }[];
  findings: { reference: string; title: string; rating_label: string | null; condition: string; criteria: string; cause: string | null;
              effect: string | null; process: string | null; management_response: string | null; response_by_name: string | null;
              response_at: string | null;
              recommendations: { reference: string; text: string; action_plans: { description: string; owner_name: string;
                                 due_date: string; status: ActionStatus }[] }[] }[];
}
