/** Plan de trésorerie (phase 4 du correctif du contrôle de gestion). Montants en chaînes décimales : aucun calcul ici. */
export type TreasurySection = "receipts" | "disbursements";
export type TreasuryMethod = "manual" | "percent_of" | "from_budget";
export type TreasuryScenario = "initial" | "updated";

export interface TreasuryPlan {
  id: string; fiscal_year_id: string; name: string; currency: string; opening_balance: string;
  opening_source: "manual" | "accounting"; status: "draft" | "approved" | "archived"; notes: string | null;
  approved_by: string | null; approved_at: string | null; created_by: string; created_at: string;
}

export interface TreasuryRubric {
  id: string; parent_id: string | null; section: TreasurySection; code: string | null; label: string; order: number;
  prefixes: string[]; method: TreasuryMethod; base_rubric_id: string | null; rate: string | null; budget_id: string | null;
  delay_months: number; cost_center_id: string | null;
}

export interface TreasuryPlanDetail extends TreasuryPlan {
  rubrics: TreasuryRubric[];
  amounts: Record<TreasuryScenario, Record<string, string[]>>;
}

export interface TreasuryVariance { forecast: string; actual: string | null; variance: string | null; rate: string | null }

export interface TreasuryRow {
  id: string; section: TreasurySection; code: string | null; label: string; level: number; has_children: boolean;
  months: string[]; total: string; actual: (string | null)[]; variance: TreasuryVariance[]; actual_total: string;
}

export interface TreasuryView {
  plan: TreasuryPlan; scenario: TreasuryScenario; months: string[]; as_of: string; closed_months: number;
  rows: TreasuryRow[];
  totals: { receipts: string[]; disbursements: string[]; net: string[]; opening: string[]; closing: string[];
    annual: { receipts: string; disbursements: string; net: string; opening: string; closing: string } };
  negative_months: number[]; financing_need: string;
  actual: { source: string | null; source_notes: string[]; receipts: (string | null)[]; disbursements: (string | null)[];
    net: (string | null)[]; unassigned: Record<TreasurySection, (string | null)[]>; check: boolean;
    variance_receipts: TreasuryVariance[]; variance_disbursements: TreasuryVariance[] };
  conventions: string[];
}

export interface TreasuryRollingMonth {
  basis: "actual" | "forecast" | "none"; net: string | null; opening: string | null; closing: string | null;
}

export interface TreasuryRolling {
  as_of: string; start_opening: string; labels: string[]; months: TreasuryRollingMonth[]; complete: boolean;
  negative_months: number[]; financing_need: string; notes: string[];
}

export interface TreasuryBudgetOption { id: string; name: string; version: number; status: string }

export interface TreasuryOpeningProposal {
  available: boolean; opening_balance?: string; source?: string | null; reason?: string;
  accounts?: { account: string; opening: string }[];
}
