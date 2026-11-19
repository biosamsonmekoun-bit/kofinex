// Types alignés sur les schémas Pydantic de l'API (backend/app/schemas/tenancy.py)

export type OrgRole = "owner" | "admin" | "member" | "viewer";
export type CompanyRole = "org_admin" | "accountant" | "controller" | "analyst" | "auditor" | "viewer";
export type FrameworkCode = "SYSCOHADA_REV" | "SYSCEBNL";

export interface Profile {
  id: string;
  email: string;
  full_name: string | null;
  phone: string | null;
  locale: string;
  is_platform_admin: boolean;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  org_type: string;
  country_code: string | null;
  default_currency: string;
  is_demo: boolean;
  created_at: string;
  my_role: OrgRole | null;
}

export interface Member {
  id: string;
  user_id: string;
  email: string;
  full_name: string | null;
  role: OrgRole;
  created_at: string;
}

export interface Company {
  id: string;
  organization_id: string;
  name: string;
  legal_name: string | null;
  legal_form: string | null;
  registration_number: string | null;
  tax_id: string | null;
  country_code: string | null;
  currency: string;
  framework_code: FrameworkCode;
  framework_name: string;
  activity_sector: string | null;
  address: string | null;
  city: string | null;
  fiscal_year_start_month: number;
  is_demo: boolean;
  archived_at: string | null;
  created_at: string;
  my_role: CompanyRole | null;
  my_permissions: string[];
}

export interface CompanyMember {
  id: string;
  user_id: string;
  email: string;
  full_name: string | null;
  role: Exclude<CompanyRole, "org_admin">;
}

export interface FiscalYear {
  id: string;
  company_id: string;
  label: string;
  start_date: string;
  end_date: string;
  status: "open" | "closed" | "archived";
  closed_at: string | null;
  created_at: string;
  active_import_job_id: string | null;
  active_ledger_import_job_id?: string | null;
}

export interface OrgPermissions {
  role: OrgRole;
  can_manage: boolean;
  can_create_company: boolean;
  can_delete: boolean;
}

export const ORG_ROLE_LABELS: Record<OrgRole, string> = {
  owner: "Propriétaire",
  admin: "Administrateur",
  member: "Membre",
  viewer: "Lecteur",
};

export const COMPANY_ROLE_LABELS: Record<CompanyRole, string> = {
  org_admin: "Administrateur",
  accountant: "Comptable",
  controller: "Contrôleur de gestion",
  analyst: "Analyste",
  auditor: "Auditeur",
  viewer: "Lecteur",
};

export const ORG_TYPE_LABELS: Record<string, string> = {
  accounting_firm: "Cabinet comptable",
  company: "Entreprise",
  group: "Groupe",
  consulting: "Cabinet de conseil",
  audit: "Cabinet d'audit",
  non_profit: "Entité à but non lucratif",
};

// ------------------------------------------------------------------ importation
export type ImportStatus =
  | "pending" | "parsing" | "awaiting_mapping" | "validating" | "awaiting_confirmation"
  | "completed" | "superseded" | "failed" | "cancelled";

export const IMPORT_STATUS_LABELS: Record<ImportStatus, string> = {
  pending: "En attente", parsing: "Lecture du fichier…", awaiting_mapping: "Colonnes à vérifier",
  validating: "Contrôles en cours…", awaiting_confirmation: "À valider", completed: "Validé",
  superseded: "Remplacé", failed: "Échec", cancelled: "Annulé",
};

export interface SheetMeta {
  name: string;
  rows: number;
  columns: number;
  source: string;
  header_row: number | null;
  suggested_mapping: Record<string, number>;
  headers: string[];
  notes: string[];
  warnings: string[];
  preview_start: number;
  preview: (string | number | null)[][];
  preview_confidence: (number | null)[][] | null;
}

export interface ControlResult {
  code: string;
  title: string;
  status: "passed" | "failed" | "skipped";
  severity: "error" | "warning" | "info";
  message: string;
  details: Record<string, unknown>;
}

export interface ImportJob {
  id: string;
  company_id: string;
  fiscal_year_id: string;
  document_id: string | null;
  source_format: string;
  status: ImportStatus;
  sheet_name: string | null;
  header_row: number | null;
  column_map: Record<string, number> | null;
  options: Record<string, unknown>;
  mapping_id: string | null;
  sheets: SheetMeta[] | null;
  extraction: { filename?: string; method?: string; page_count?: number | null; ocr_pages?: number[];
                duplicate_of_document?: string | null; size_bytes?: number } | null;
  controls: { results: ControlResult[]; totals: Record<string, { debit: string; credit: string; difference: string }>;
              line_count: number; blocking: boolean; requires_acknowledgment: boolean } | null;
  total_rows: number | null;
  valid_rows: number | null;
  error_rows: number | null;
  failure_reason: string | null;
  framework_version_id: string | null;
  validated_at: string | null;
  created_at: string;
  field_labels: Record<string, string>;
}

export interface ImportListItem {
  id: string;
  status: ImportStatus;
  source_format: string;
  filename: string | null;
  method: string | null;
  fiscal_year_id: string;
  fiscal_year_label: string | null;
  valid_rows: number | null;
  error_rows: number | null;
  blocking: boolean | null;
  created_at: string;
  validated_at: string | null;
}

export interface StagingRow {
  source_row: number;
  source_page: number | null;
  status: "valid" | "error" | "skipped" | "total";
  account_number: string | null;
  account_label: string | null;
  closing_debit: string | null;
  closing_credit: string | null;
  ocr_confidence: string | null;
  issues: { code: string; message: string; severity: string }[];
  raw: unknown[];
}

export const AMOUNT_FIELDS = ["opening_debit", "opening_credit", "movement_debit", "movement_credit",
  "closing_debit", "closing_credit"] as const;

// ------------------------------------------------------------------ référentiels
export interface FrameworkVersion {
  id: string;
  framework_code: string;
  framework_name: string;
  version_label: string;
  effective_from: string;
  effective_to: string | null;
  source_reference: string;
  source_url: string | null;
  status: "draft" | "published" | "deprecated";
  published_at: string | null;
  notes: string | null;
  chart_sha256: string | null;
  mappings_sha256: string | null;
  chart_loaded_at: string | null;
  mappings_loaded_at: string | null;
  validation: LoadReport & { validated_at?: string } | null;
  account_count: number;
  mapping_count: number;
  structure_line_count: number;
  concept_count: number;
  concept_total: number;
}

export interface LoadReport {
  errors: number;
  warnings: number;
  issues: { severity: "error" | "warning" | "info"; code: string; message: string; row: number | null }[];
}

export const VERSION_STATUS: Record<FrameworkVersion["status"], { label: string; tone: "amber" | "green" | "neutral" }> = {
  draft: { label: "Brouillon", tone: "amber" },
  published: { label: "Publiée", tone: "green" },
  deprecated: { label: "Retirée", tone: "neutral" },
};

// ------------------------------------------------------------------ moteur financier
export interface StatementLine {
  code: string; label: string; kind: "detail" | "total" | "title"; role: string | null; level: number;
  gross: string | null; depreciation: string | null; net: string | null; previous: string | null; accounts: number;
}

export interface IndicatorValue {
  code: string; version: number; name: string; category: string; unit: string;
  value: string | null; status: "ok" | "missing_input" | "division_by_zero" | "error"; message: string | null;
  previous_value: string | null; previous_status: string | null; inputs: Record<string, string | null>;
  expression: string | null; description: string | null; convention_notes: string | null; custom: boolean;
}

export interface CheckResult { code: string; status: "passed" | "failed" | "skipped"; severity?: string; message: string;
  title?: string; difference?: string | null; details?: Record<string, unknown> }

export interface Analysis {
  id: string; fiscal_year_id: string; status: "running" | "completed" | "failed"; failure_reason: string | null;
  engine_version: string; framework_version_id: string | null; previous_fiscal_year_id: string | null;
  started_at: string; completed_at: string | null; parameters: Record<string, string>;
  controls: { statements: CheckResult[]; cross_checks: CheckResult[] } | null;
  summary: { indicators: Record<string, number>; formulas: number; concepts_missing: string[];
             unmapped_accounts: number; has_previous_year: boolean } | null;
  statements: Record<string, StatementLine[]>;
  indicators: IndicatorValue[];
  alerts: { severity: string; rule_code: string; title: string; message: string; evidence: Record<string, unknown> }[];
}

export interface FormulaDef {
  id: string; code: string; version: number; name: string; category: string; expression: string; unit: string;
  rounding_scale: number; zero_division_policy: string; missing_input_policy: string; description: string | null;
  convention_notes: string | null; status: string; library_version: string | null; custom: boolean;
  published_at: string | null;
}

export const CATEGORY_LABELS: Record<string, string> = {
  sig: "Soldes intermédiaires de gestion", caf: "Capacité d'autofinancement", structure: "Équilibre financier",
  liquidity: "Liquidité", solvency: "Solvabilité et endettement", profitability: "Rentabilité et marges",
  activity: "Activité et rotations", growth: "Croissance", cash: "Trésorerie", custom: "Indicateurs personnalisés",
};
export const CATEGORY_ORDER = ["sig", "caf", "structure", "liquidity", "solvency", "profitability", "activity",
  "growth", "cash", "custom"];
export const STATEMENT_LABELS: Record<string, string> = {
  balance_sheet_assets: "Bilan — actif", balance_sheet_liabilities: "Bilan — passif",
  income_statement: "Compte de résultat", cash_flow: "Tableau des flux de trésorerie", off_balance: "Hors bilan",
};

// ------------------------------------------------------------------ contrôle de gestion
export type CenterType = "main" | "auxiliary" | "structure" | "profit" | "investment";
export const CENTER_TYPE_LABELS: Record<CenterType, string> = {
  main: "Principal", auxiliary: "Auxiliaire", structure: "Structure", profit: "Centre de profit", investment: "Centre d'investissement",
};
export interface CostCenter {
  id: string; code: string; name: string; center_type: CenterType; parent_id: string | null;
  description: string | null; work_unit: string | null; is_active: boolean;
}
export interface CostEntry {
  id: string; cost_center_id: string; account_number: string | null; entry_date: string; amount: string;
  cost_nature: string; description: string | null; source: string;
}
export type BudgetStatus = "draft" | "submitted" | "approved" | "archived";
export const BUDGET_STATUS_LABELS: Record<BudgetStatus, string> = {
  draft: "Brouillon", submitted: "Soumis", approved: "Approuvé", archived: "Archivé",
};
export interface BudgetLine {
  id?: string; account_prefix: string | null; cost_center_id: string | null; label: string; period: number;
  amount: string; notes?: string | null;
}
export interface Budget {
  id: string; fiscal_year_id: string; name: string; version: number; status: BudgetStatus;
  scenario: "budget" | "forecast"; currency: string; notes: string | null; assumptions: Record<string, unknown>;
  source_budget_id: string | null; submitted_by: string | null; submitted_at: string | null;
  approved_by: string | null; approved_at: string | null; created_by: string; created_at: string;
  total_lines: number; lines?: BudgetLine[];
}
export interface TrackingRow {
  account_prefix: string | null; cost_center_id: string | null; label: string; nature: "charge" | "produit";
  budget: string; budget_by_period: Record<string, string>; actual: string | null;
  actual_by_period: Record<string, string> | null; actual_source: string; variance: string | null;
  realization_pct: string | null; favorable: boolean | null; notes: string[];
}
export interface TotalsRow { budget: string; actual: string | null; variance: string | null }
export interface Tracking {
  budget_id: string; fiscal_year: string; rows: TrackingRow[];
  totals: Partial<Record<"produit" | "charge" | "solde", TotalsRow>>; warnings: string[]; conventions: string[];
}
export type ModelType = "full_cost" | "cvp" | "standard_cost";
export const MODEL_TYPE_LABELS: Record<ModelType, string> = {
  full_cost: "Coûts complets (centres d'analyse)", cvp: "Marges et seuil de rentabilité", standard_cost: "Coûts préétablis (écarts)",
};
export interface CostingModel {
  id: string; fiscal_year_id: string; name: string; model_type: ModelType; version: number; status: "draft" | "validated";
  computed_at: string | null; validated_by: string | null; validated_at: string | null; created_at: string;
  parameters?: Record<string, unknown>; results?: Record<string, unknown> | null; results_current?: boolean;
}
export interface ModelHead { model_id: string; name: string; version: number; status: string; computed_at: string | null; results_current: boolean }
export interface ManagementDashboard {
  fiscal_year: { id: string; label: string; start_date: string; end_date: string };
  has_balance: boolean;
  budget: DashboardBudget | null; forecast: DashboardBudget | null;
  cost_centers: { by_center: { cost_center_id: string; label: string; amount: string }[];
                  by_period: { period: number; amount: string }[]; total: string } | null;
  full_cost: (ModelHead & { analytical_result: string | null; total_incorporated: string;
              imputation_differences: Record<string, string>;
              objects: { code: string; name: string; revenue: string | null; cost: string; unit_cost: string | null;
                         cost_of_sales: string | null; margin: string | null }[] }) | null;
  cvp: (ModelHead & Record<"revenue" | "variable_costs" | "contribution_margin" | "contribution_rate_pct" | "fixed_costs"
        | "result" | "breakeven" | "breakeven_days" | "breakeven_date" | "safety_margin" | "safety_index_pct"
        | "operating_leverage" | "unclassified_charges", string | null>) | null;
  standard_cost: (ModelHead & { totals: Record<string, string>; actual_output: string }) | null;
  notes: string[];
}
export interface DashboardBudget {
  budget_id: string; name: string; version: number; status: BudgetStatus;
  totals: Tracking["totals"]; lines: number; warnings: string[];
  unfavorable: { label: string; account_prefix: string | null; cost_center_id: string | null; nature: string;
                 budget: string; actual: string | null; variance: string | null; realization_pct: string | null }[];
  favorable_count: number; unfavorable_count: number;
}

// ------------------------------------------------------------------ audit : socle commun
export type EngagementStatus = "planning" | "fieldwork" | "review" | "reporting" | "issued" | "archived";
export type EngagementRole = "partner" | "manager" | "in_charge" | "staff" | "quality_reviewer" | "auditee" | "observer";
export const ENGAGEMENT_STATUS_LABELS: Record<EngagementStatus, string> = {
  planning: "Planification", fieldwork: "Travaux", review: "Revue", reporting: "Rapport", issued: "Émise", archived: "Archivée",
};
export const ENGAGEMENT_STATUS_TONE: Record<EngagementStatus, "neutral" | "blue" | "amber" | "green"> = {
  planning: "neutral", fieldwork: "blue", review: "amber", reporting: "amber", issued: "green", archived: "neutral",
};
export const ENGAGEMENT_ROLE_LABELS: Record<EngagementRole, string> = {
  partner: "Associé", manager: "Manager", in_charge: "Chef de mission", staff: "Auditeur",
  quality_reviewer: "Réviseur qualité", auditee: "Audité", observer: "Observateur",
};
export const ENGAGEMENT_TYPE_LABELS = {
  statutory_audit: "Audit légal", contractual_audit: "Audit contractuel", internal_audit: "Audit interne",
  ic_assessment: "Évaluation du contrôle interne",
} as const;
export type EngagementType = keyof typeof ENGAGEMENT_TYPE_LABELS;
export interface PersonRef { id: string; email: string; full_name: string | null }
export interface EngagementMember {
  id: string; user_id: string; role: EngagementRole; role_label: string; planned_hours: string | null;
  independence_confirmed_at: string | null; created_at: string; user: PersonRef | null;
}
export interface Engagement {
  id: string; organization_id: string; company_id: string; company_name: string | null; fiscal_year_id: string | null;
  engagement_type: EngagementType; type_label: string; reference: string; name: string; objectives: string | null;
  scope: string | null; period_start: string | null; period_end: string | null; planned_start: string | null;
  planned_end: string | null; methodology_version_id: string | null; status: EngagementStatus; status_label: string;
  issued_at: string | null; archived_at: string | null; reopened_at: string | null; reopen_reason: string | null;
  created_at: string; my_role: EngagementRole | null; independent: boolean;
  my_role_label?: string | null; is_org_admin?: boolean; capabilities?: string[]; next_statuses?: EngagementStatus[];
  fiscal_year_label?: string | null; methodology?: { id: string; name: string; version_label: string; source_reference: string } | null;
  members?: EngagementMember[];
}
export interface Signoff {
  id: string; signoff_role: "preparer" | "reviewer" | "quality_reviewer" | "approver"; user_id: string; member_role: string;
  content_hash: string; signed_at: string; revoked_at: string | null; revoked_reason: string | null; user: PersonRef | null;
}
export const SIGNOFF_LABELS = { preparer: "Préparé par", reviewer: "Revu par", approver: "Approuvé par", quality_reviewer: "Revue qualité" } as const;
export interface Supervision {
  workpapers: Record<"draft" | "prepared" | "reviewed" | "approved", number>;
  procedures: Record<"not_started" | "in_progress" | "done" | "not_applicable", number>;
  open_notes: number; answered_notes: number; risks_total: number;
  risks_uncovered: { id: string; code: string; title: string; is_significant: boolean }[];
  significant_uncovered: number; members_pending_independence: string[];
  overdue_procedures: { id: string; code: string; title: string; due_date: string; status: string }[];
  issuance_checks: { code: string; label: string; passed: boolean; detail: string | null }[];
  ready_to_issue: boolean; engagement_signoffs: Signoff[];
}
export interface EngagementRisk {
  id: string; risk_id: string | null; code: string; title: string; description: string | null; cycle_code: string | null;
  assertion_codes: string[]; likelihood: number | null; impact: number | null; is_significant: boolean;
  planned_response: string | null; origin: string; score: number | null; scale_significant: boolean | null; procedures: number;
}
export interface RiskScale { likelihood: { score: number; label: string }[]; impact: { score: number; label: string }[]; significant_from?: number }
export type ProcedureNature = "control_test" | "analytical" | "detail_test" | "inquiry" | "observation" | "inspection" | "confirmation" | "recalculation" | "other";
export const NATURE_LABELS: Record<ProcedureNature, string> = {
  control_test: "Test de contrôle", analytical: "Procédure analytique", detail_test: "Test de détail", inquiry: "Entretien",
  observation: "Observation", inspection: "Inspection", confirmation: "Confirmation", recalculation: "Recalcul", other: "Autre",
};
export type ProcedureStatus = "not_started" | "in_progress" | "done" | "not_applicable";
export const PROCEDURE_STATUS_LABELS: Record<ProcedureStatus, string> = {
  not_started: "Non commencée", in_progress: "En cours", done: "Réalisée", not_applicable: "Non applicable",
};
export interface AuditProcedure {
  id: string; program_id: string; code: string; title: string; objective: string | null; nature: ProcedureNature;
  steps: string[]; assertion_codes: string[]; template_item_id: string | null; assigned_to: string | null; due_date: string | null;
  status: ProcedureStatus; na_reason: string | null; origin: string; display_order: number; risk_ids: string[];
  workpapers: { id: string; reference: string; title: string; status: WorkpaperStatus }[];
}
export interface WorkProgram { id: string; code: string; title: string; cycle_code: string | null; objective: string | null; display_order: number; procedures: AuditProcedure[] }
export type WorkpaperStatus = "draft" | "prepared" | "reviewed" | "approved";
export const WORKPAPER_STATUS_LABELS: Record<WorkpaperStatus, string> = { draft: "Brouillon", prepared: "Préparée", reviewed: "Revue", approved: "Approuvée" };
export interface ReviewNote {
  id: string; object_type: string; object_id: string; body: string; author_id: string; assigned_to: string | null;
  status: "open" | "answered" | "closed"; response: string | null; responded_at: string | null; closed_at: string | null;
  created_at: string; author?: PersonRef | null; assignee?: PersonRef | null; object_label?: string | null;
}
export interface WorkpaperDetail {
  id: string; procedure_id: string | null; reference: string; title: string; objective: string | null; work_performed: string | null;
  conclusion: string | null; content: Record<string, unknown>; status: WorkpaperStatus; version: number; content_hash: string;
  origin: string; created_at: string; updated_at: string; signoffs: Signoff[];
  evidence: { id: string; title: string; kind: string; sha256: string; original_filename: string | null; link_id: string }[];
  review_notes: ReviewNote[]; created_by_user: PersonRef | null; updated_by_user: PersonRef | null;
}
export interface EvidenceItem {
  id: string; kind: "file" | "snapshot"; title: string; description: string | null; source: string; obtained_on: string;
  original_filename: string | null; mime_type: string | null; size_bytes: number | null; sha256: string;
  snapshot_ref: Record<string, unknown> | null; uploaded_by: string; created_at: string;
  links: { id: string; object_type: string; object_id: string }[]; uploaded_by_user: PersonRef | null;
}
export interface Methodology {
  id: string; organization_id: string | null; kind: "audit" | "internal_control"; name: string; version_label: string;
  source_reference: string; description: string | null; status: "draft" | "published" | "archived"; published_at: string | null;
  created_at: string; items?: number | MethodologyItem[]; can_manage: boolean;
}
export interface MethodologyItem { id: string; item_type: string; code: string; label: string; parent_code: string | null; content: Record<string, unknown>; display_order: number }
export const personName = (p: PersonRef | null | undefined) => (p ? p.full_name || p.email : "—");
