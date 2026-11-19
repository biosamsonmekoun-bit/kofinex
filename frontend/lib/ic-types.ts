// Contrôle interne (lot 9) : types et libellés partagés.
import type { PersonRef } from "@/lib/types";

export type Tone = "neutral" | "blue" | "green" | "amber" | "red" | "gold";
export type Conclusion = "effective" | "partially_effective" | "ineffective" | "not_tested" | "not_applicable";
export type Existence = "existing" | "expected" | "not_formalized" | "absent";

export const CONCLUSION: Record<Conclusion, [string, Tone]> = {
  effective: ["Efficace", "green"], partially_effective: ["Partiellement efficace", "amber"], ineffective: ["Inefficace", "red"],
  not_tested: ["Non testé", "neutral"], not_applicable: ["Non applicable", "neutral"],
};
export const DESIGN_CONCLUSION: Record<Conclusion, string> = {
  effective: "Conception adéquate", partially_effective: "Conception partiellement adéquate", ineffective: "Conception inadéquate",
  not_tested: "Non testé", not_applicable: "Non applicable",
};
export const EXISTENCE: Record<Existence, [string, Tone]> = {
  existing: ["Existant", "blue"], expected: ["Attendu", "amber"], not_formalized: ["Non formalisé", "amber"], absent: ["Absent", "red"],
};
export const FREQUENCY: Record<string, string> = {
  on_occurrence: "À chaque opération", daily: "Quotidienne", weekly: "Hebdomadaire", monthly: "Mensuelle", quarterly: "Trimestrielle",
  semiannual: "Semestrielle", annual: "Annuelle", ad_hoc: "Ponctuelle",
};
export const NATURE: Record<string, string> = { preventive: "Préventif", detective: "Détectif" };
export const AUTOMATION: Record<string, string> = { manual: "Manuel", automated: "Automatique", semi_automated: "Semi-automatique" };
export const TIMING: Record<string, string> = { permanent: "Permanent", periodic: "Périodique" };
export const TEST_METHODS: Record<string, string> = {
  document_review: "Examen documentaire", observation: "Observation", inquiry: "Entretien", inspection: "Inspection",
  reconciliation: "Rapprochement", recalculation: "Recalcul", reperformance: "Réexécution", data_analysis: "Analyse de données",
};
export const TEST_STATUS: Record<string, [string, Tone]> = {
  planned: ["Planifié", "neutral"], in_progress: ["En cours", "blue"], prepared: ["Préparé", "amber"], reviewed: ["Revu", "green"],
};
export const ASSESSMENT_STATUS: Record<string, [string, Tone]> = {
  draft: ["Brouillon", "neutral"], submitted: ["Soumise", "amber"], approved: ["Approuvée", "green"],
};
export const SCOPES: Record<string, string> = {
  overall: "Dispositif général", domain: "Domaine", process: "Processus", cycle: "Cycle", component: "Composante du référentiel",
  risk: "Risque", control: "Contrôle",
};
export const IC_ROLES: Record<string, string> = {
  ic_manager: "Responsable du contrôle interne", daf: "Directeur administratif et financier", domain_owner: "Responsable de domaine",
  process_owner: "Responsable de processus", control_performer: "Exécutant du contrôle", supervisor: "Superviseur", observer: "Observateur",
};
export const FRAMEWORK_CATEGORY: Record<string, string> = {
  ic_framework: "Cadre de contrôle interne", professional_standard: "Référentiel professionnel d'audit",
  legal_requirement: "Exigence juridique ou comptable", internal_methodology: "Méthodologie interne",
};
export const STAGE_TONE: Record<string, Tone> = {
  draft: "neutral", validated: "blue", communicated: "blue", responded: "blue", action_planned: "amber", implementation: "amber",
  verification: "amber", closed: "green",
};
export const INDICATOR_TONE: Record<string, Tone> = {
  uncovered: "red", not_tested: "neutral", ineffective: "red", partial: "amber", effective: "green",
};
export const DESIGN_CRITERIA: Record<string, string> = {
  responds_to_risk: "Répond réellement au risque identifié", well_defined: "Est correctement défini", owner_assigned: "Est attribué à un responsable",
  frequency_adequate: "Dispose d'une fréquence adaptée", documented: "Est documenté", independent: "Est suffisamment indépendant",
  prevents_or_detects: "Permet de prévenir ou de détecter le risque",
};
export const ANSWERS: Record<string, string> = { yes: "Oui", partial: "Partiellement", no: "Non", na: "Sans objet" };

export interface IcAccess {
  company_role: string | null; is_admin: boolean; audits: boolean; can_manage_registry: boolean; managed_domains: string[];
  roles: { role: string; role_label: string; domain_id: string | null }[];
}
export interface IcDomain {
  id: string; code: string; name: string; category: string; template_code: string | null; cycle_code: string | null;
  description: string | null; owner_name: string | null; owner_user_id: string | null; is_active: boolean; display_order: number;
}
export interface IcProcess { id: string; code: string; name: string; parent_id: string | null; domain_id: string | null; owner_name: string | null; description: string | null; is_active: boolean }
export interface IcObjective { id: string; code: string; statement: string; domain_id: string | null; process_id: string | null; assertion_codes: string[]; is_active: boolean }
export interface IcRisk {
  id: string; code: string; title: string; description: string | null; process_id: string | null; domain_id: string | null;
  objective_id: string | null; category: string | null; causes: string | null; consequences: string | null; owner_name: string | null;
  cycle_code: string | null; scale_version_id: string | null; inherent_likelihood: number | null; inherent_impact: number | null;
  residual_likelihood: number | null; residual_impact: number | null; control_level_code: string | null; control_level_label?: string | null;
  inherent_score: number | null; residual_score: number | null; status: "active" | "retired"; indicator: string | null; indicator_label: string | null;
}
export interface IcControl {
  id: string; code: string; title: string; description: string | null; control_objective: string | null; domain_id: string | null;
  process_id: string | null; objective_id: string | null; existence: Existence; existence_label: string; owner_name: string;
  owner_user_id: string | null; performer_name: string | null; performer_user_id: string | null; supervisor_name: string | null;
  supervisor_user_id: string | null; frequency: string | null; nature: string | null; automation: string | null; timing: string | null;
  execution_mode: string | null; expected_evidence: string | null; procedure_text: string | null; success_criteria: string | null;
  is_key: boolean; implemented_on: string | null; operational_status: "active" | "suspended" | "retired"; version: number;
  design: Conclusion | null; operating: Conclusion | null; conclusion: Conclusion; conclusion_label: string; risks: number;
}
export interface IcTestBrief {
  id: string; engagement_id: string; control_id: string; reference: string; test_type: "design" | "operating"; period_start: string | null;
  period_end: string | null; conclusion: Conclusion | null; status: string; reviewed_at: string | null; conclusion_label: string | null;
  control?: string | null; engagement_reference?: string | null;
}
export interface IcActionPlan { id: string; description: string; owner_name: string; due_date: string; status: string; engagement_id: string; overdue: boolean }
export interface IcDeficiency {
  id: string; engagement_id: string; engagement_reference: string; reference: string; title: string; condition: string; criteria: string;
  cause: string | null; effect: string | null; rating_code: string | null; rating_label: string | null; rating_rank: number | null;
  control_id: string | null; control: string | null; risk_id: string | null; domain_id: string | null; status: string; stage: string;
  stage_label: string; management_response: string | null; response_by_name: string | null; closed_at: string | null; closure_note: string | null;
  recommendations: { id: string; reference: string; text: string; action_plans: IcActionPlan[] }[];
}
export interface IcDashboard {
  domains: number; domains_assessed: number; processes: number; risks: number; controls_existing: number; controls_missing: number;
  controls_tested: number; effective: number; partially_effective: number; ineffective: number; not_tested: number; not_applicable: number;
  effective_rate: number | null; uncovered_risks: number; deficiency_levels: { code: string; label: string; rank: number | null; open: number }[];
  deficiencies_top_level: number | null; deficiencies_open: number; action_plans: number; action_plans_overdue: number;
  implementation_rate: number | null; verified_rate: number | null;
  by_domain: ({ id: string; code: string; name: string; is_active: boolean; processes: number; risks: number; controls: number } & Record<Conclusion, number>)[];
}
export interface MatrixRow {
  risk_id: string; risk_code: string; risk_title: string; control_id: string | null; control_code?: string; control_title?: string;
  existence?: Existence; missing?: boolean; is_key?: boolean; owner?: string | null; frequency?: string | null; expected_evidence?: string | null;
  coverage?: string; design?: Conclusion | null; operating?: Conclusion | null; conclusion?: Conclusion; evidence_count?: number;
  indicator: string; indicator_label: string; conclusion_label?: string | null; process?: string | null; objective?: string | null;
}
export interface Matrix { rows: MatrixRow[]; uncovered_risks: { risk_id: string; code: string; title: string; expected_controls: string[] }[]; orphan_controls: { control_id: string; code: string; title: string }[] }
export interface ReportSection { key: string; title: string; columns: { key: string; label: string }[]; rows: Record<string, string | number | null>[] }
export interface IcReport { kind: string; title: string; generated_at: string; sections: ReportSection[]; sources: Record<string, number> }
export interface IcExecution {
  id: string; occurrence_label: string; occurrence_date: string; outcome: string; comment: string | null; exceptions: string | null;
  performed_at: string; evidence_filename: string | null; evidence_sha256: string | null; supervision_status: string; supervised_at: string | null;
  supervision_comment: string | null; performed_by: PersonRef | null; supervised_by: PersonRef | null; performed_by_id: string;
}
export const OUTCOME: Record<string, [string, Tone]> = {
  performed: ["Réalisé", "green"], performed_with_exceptions: ["Réalisé avec exceptions", "amber"], not_performed: ["Non réalisé", "red"],
};
export const SUPERVISION: Record<string, [string, Tone]> = { pending: ["À superviser", "neutral"], approved: ["Approuvée", "green"], rejected: ["Rejetée", "red"] };

export const pct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${v.toLocaleString("fr-FR")} %`);

export const OPERATING_CRITERIA: Record<string, string> = {
  performed: "A réellement été exécuté", right_person: "A été exécuté par la bonne personne", right_frequency: "A été réalisé à la bonne fréquence",
  evidence_produced: "A produit les preuves attendues", supervised: "A été correctement supervisé", anomalies_handled: "A permis de détecter ou prévenir les anomalies",
};
export const ITEM_RESULT: Record<string, [string, Tone]> = {
  pending: ["À tester", "neutral"], compliant: ["Conforme", "green"], exception: ["Exception", "red"], not_applicable: ["Sans objet", "neutral"],
};
export const SELECTION: Record<string, string> = { all: "Exhaustive", random: "Aléatoire", systematic: "Systématique", judgmental: "Par jugement" };
export const RELIANCE: Record<string, [string, Tone]> = {
  rely: ["Confiance", "green"], partial_rely: ["Confiance partielle", "amber"], no_reliance: ["Pas de confiance", "red"],
};
export type Answer = { answer: "yes" | "partial" | "no" | "na"; comment?: string };

export interface IcTestItem {
  id: string; item_ref: string; description: string | null; item_date: string | null; amount: string | null; execution_id: string | null;
  selection_order: number | null; result: "pending" | "compliant" | "exception" | "not_applicable"; exception_description: string | null;
  na_reason: string | null; tested_at: string | null; tested_by_user: PersonRef | null;
}
export interface IcTestDetail {
  id: string; engagement_id: string; control_id: string; risk_id: string | null; procedure_id: string | null; workpaper_id: string | null;
  reference: string; test_type: "design" | "operating"; test_methods: string[]; objective: string | null; test_procedure: string;
  responsible_user_id: string | null; period_start: string | null; period_end: string | null; population_description: string | null;
  population_size: number | null; population_source: string | null; selection_method: string | null; sample_size: number | null;
  sample_size_basis: string | null; selection_params: Record<string, unknown> | null; acceptance_criteria: string | null;
  tolerable_exceptions: number | null; expected_result: string | null; design_answers: Record<string, Answer> | null;
  operating_answers: Record<string, Answer> | null; results_summary: string | null; exceptions_summary: string | null;
  conclusion: Conclusion | null; conclusion_rationale: string | null; status: string; prepared_at: string | null; reviewed_at: string | null;
  reopen_reason: string | null; control: IcControl | null; criteria: Record<string, string>; conclusion_label: string | null;
  prepared_by_user: PersonRef | null; reviewed_by_user: PersonRef | null; responsible_user: PersonRef | null; items: IcTestItem[];
  evidence: { link_id: string; object_type: string; object_id: string; evidence_id: string; title: string; sha256: string }[];
  check: { items: number; pending: number; compliant: number; exceptions: number; not_applicable: number; missing: string[];
    negative: string[]; allowed: Conclusion[]; blockers: Record<string, string[]> };
}
export interface IcRegistry {
  domains: IcDomain[]; processes: IcProcess[]; risks: { id: string; code: string; title: string; domain_id: string | null; process_id: string | null }[];
  controls: { id: string; code: string; title: string; domain_id: string | null; process_id: string | null; existence: Existence; is_key: boolean }[];
  components: { id: string; item_type: string; code: string; label: string }[]; control_levels: { code: string; label: string }[];
  cycles: { code: string; label: string }[];
}
export interface IcAssessment {
  id: string; engagement_id: string; reference: string; scope_type: string; domain_id: string | null; process_id: string | null;
  risk_id: string | null; control_id: string | null; framework_item_id: string | null; cycle_code: string | null; as_of_date: string;
  rating_code: string | null; rating_label?: string | null; conclusion: string | null; basis: Synthesis | null; status: string;
  prepared_at: string | null; approved_at: string | null; return_reason: string | null; prepared_by_user?: PersonRef | null;
  approved_by_user?: PersonRef | null; preview?: Synthesis | null;
}
export interface Synthesis {
  rule: string; controls: number; effective: number; partially_effective: number; ineffective: number; not_tested: number;
  not_applicable: number; key_ineffective: number; missing_controls: number; risks: number; uncovered_risks: number;
}
export interface IcReliance {
  id: string; control_test_id: string; cycle_code: string | null; assertion_codes: string[]; decision: string; rationale: string;
  approach_impact: string | null; period_overlap: boolean | null; snapshot: Record<string, unknown> | null; decided_at: string;
  status: string; withdrawn_reason: string | null; decided_by: PersonRef | null;
}
