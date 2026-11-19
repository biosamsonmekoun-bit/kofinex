import type { PersonRef } from "@/lib/types";

/** Réponse de GET /companies/{cid}/fiscal-years/{fy}/dashboard (montants en chaînes décimales). */
export type Num = string | number;

export interface DashPeriod { key: string; label: string; from: number; to: number }

export interface DashKpi {
  code: string; name?: string; available: boolean; reason?: string;
  value?: Num | null; previous?: Num | null; variation?: Num | null; unit?: string; status?: string; message?: string | null;
}

export interface DashGroup { key: string; label: string; amount: Num; share: Num | null; includes?: string[] }
export interface DashBreakdown { total: Num; groups: DashGroup[]; unclassified_accounts: number }

export interface DashAlert {
  key: string; title: string; detail: string; state: "todo" | "progress" | "done" | "none"; count: number;
  items?: { severity: string; title: string }[];
}

export interface DashActivity { id: string; action: string; label: string; entity_type: string; at: string; user: PersonRef | null }

export interface DashboardData {
  company: { id: string; name: string; currency: string; is_demo: boolean };
  fiscal_year: { id: string; label: string; start_date: string; end_date: string };
  previous_label: string | null;
  period: DashPeriod;
  periods: DashPeriod[];
  analysis: { id: string; completed_at: string } | null;
  kpis: { revenue: DashKpi; net_income: DashKpi; cash: DashKpi };
  expenses: DashBreakdown | null;
  income: DashBreakdown | null;
  breakdown_source: "ledger" | "trial_balance" | null;
  breakdown_note: string | null;
  indicators: DashKpi[];
  monthly: { available: true; months: { period: number; label: string; year: number; income: Num; expense: Num }[] } | { available: false; reason: string };
  alerts: DashAlert[];
  activities: DashActivity[];
}

/** Nombre d'alertes appelant une action (cloche de la barre supérieure). */
export function actionableCount(d: DashboardData | null): number {
  if (!d) return 0;
  return d.alerts.reduce((n, a) => n + (a.state === "todo" ? Math.max(1, a.count) : a.state === "progress" ? a.count : 0), 0);
}
