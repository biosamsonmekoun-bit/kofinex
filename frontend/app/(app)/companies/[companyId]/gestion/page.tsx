"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { ChevronLeft } from "lucide-react";
import { useApiResource } from "@/lib/use-api";
import type { Company, FiscalYear } from "@/lib/types";
import { cn } from "@/lib/utils";
import { rememberOrg } from "@/components/app-shell";
import { Alert, EmptyState, Loading, PageHeader } from "@/components/ui/feedback";
import { Select } from "@/components/ui/form";
import { BudgetsTab } from "./budgets-tab";
import { CentersTab } from "./centers-tab";
import { DashboardTab } from "./dashboard-tab";
import { ModelsTab } from "./models-tab";
import { ProjectionsTab } from "./projections-tab";
import { FinancialTab } from "./financial-tab";
import { BudgetDashboardTab } from "./budget-dashboard-tab";
import { AnalysisTab, PayrollTab, TreasuryTab } from "./treasury-payroll-tabs";
import { TreasuryPlanTab } from "./treasury-plan-tab";

/** Quatre espaces (évolution du contrôle de gestion) ; les onglets du lot 5 sont conservés et rangés dans ces espaces. */
type Tab = "financial" | "treasury" | "payroll" | "budget-dashboard" | "budgets" | "centers" | "treasury-plan" | "analysis" | "models" | "projections" | "dashboard";
const SPACES: [string, [Tab, string][]][] = [
  ["Tableau de bord financier", [["financial", "Performance financière"], ["treasury", "Trésorerie"], ["payroll", "Masse salariale"]]],
  ["Tableau de bord budgétaire", [["budget-dashboard", "Budget et réalisé"]]],
  ["Gestion budgétaire", [["budgets", "Budgets et prévisions"], ["centers", "Centres et saisies"], ["treasury-plan", "Plan de trésorerie"]]],
  ["Analyse et aide à la décision", [["analysis", "Points d'attention"], ["models", "Coûts, marges et seuils"], ["projections", "Projections"],
    ["dashboard", "Synthèse des modèles"]]],
];
const TABS = SPACES.flatMap(([, tabs]) => tabs);

export default function ManagementPage() {
  const { companyId } = useParams<{ companyId: string }>();
  const search = useSearchParams();
  const router = useRouter();
  const { data: company, error } = useApiResource<Company>(`/companies/${companyId}`);
  const { data: years, error: fyError } = useApiResource<FiscalYear[]>(`/companies/${companyId}/fiscal-years`);
  const tab = (TABS.some(([t]) => t === search.get("tab")) ? search.get("tab") : "financial") as Tab;
  const [fyId, setFyId] = useState<string | null>(search.get("fy"));

  useEffect(() => { if (company) rememberOrg(company.organization_id); }, [company]);
  useEffect(() => {
    if (!fyId && years?.length) setFyId(years[0].id);   // exercice le plus récent
  }, [years, fyId]);

  const fy = useMemo(() => years?.find((y) => y.id === fyId) ?? null, [years, fyId]);

  function go(next: { tab?: Tab; fy?: string }) {
    const p = new URLSearchParams(search.toString());
    if (next.tab) p.set("tab", next.tab);
    if (next.fy) { p.set("fy", next.fy); setFyId(next.fy); }
    router.replace(`/companies/${companyId}/gestion?${p.toString()}`, { scroll: false });
  }

  if (error || fyError) return <Alert>{error ?? fyError}</Alert>;
  if (!company || !years) return <Loading />;
  const canWrite = company.my_permissions.includes("budget.write");
  const canApprove = company.my_permissions.includes("budget.approve");

  return (
    <>
      <Link href={`/companies/${company.id}`}
            className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ChevronLeft className="h-4 w-4" /> {company.name}
      </Link>
      <PageHeader
        title="Contrôle de gestion"
        description="Pilotage financier et budgétaire alimenté par les écritures validées ; budgets, coûts, marges et projections."
        actions={years.length > 0 && (
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            Exercice
            <Select className="w-40" value={fyId ?? ""} onChange={(e) => go({ fy: e.target.value })} aria-label="Exercice">
              {years.map((y) => <option key={y.id} value={y.id}>{y.label}{y.status === "closed" ? " (clôturé)" : ""}</option>)}
            </Select>
          </label>
        )}
      />
      {years.length === 0 ? (
        <EmptyState title="Aucun exercice" description="Créez un exercice dans la fiche de l'entreprise pour établir des budgets." />
      ) : fy && (
        <>
          {tab === "models" && !fy.active_import_job_id && (
            <Alert kind="info" className="mb-4">
              Aucune balance validée pour l&apos;exercice {fy.label} : les coûts complets et le seuil de rentabilité utilisent la balance de
              l&apos;exercice.
            </Alert>
          )}
          <nav aria-label="Espaces du contrôle de gestion" className="mb-5 space-y-2">
            <div role="tablist" className="flex flex-wrap gap-1">
              {SPACES.map(([label, tabs]) => {
                const active = tabs.some(([id]) => id === tab);
                return (
                  <button key={label} role="tab" aria-selected={active} onClick={() => go({ tab: tabs[0][0] })}
                          className={cn("rounded-md px-3 py-1.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                            active ? "bg-primary text-primary-foreground" : "bg-card hover:bg-muted")}>
                    {label}
                  </button>
                );
              })}
            </div>
            <div role="tablist" className="flex gap-1 overflow-x-auto border-b">
              {(SPACES.find(([, tabs]) => tabs.some(([id]) => id === tab))?.[1] ?? []).map(([id, label]) => (
                <button key={id} role="tab" aria-selected={tab === id} onClick={() => go({ tab: id })}
                        className={cn("-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
                          tab === id ? "border-primary font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground")}>
                  {label}
                </button>
              ))}
            </div>
          </nav>
          {tab === "financial" && <FinancialTab cid={company.id} fy={fy} />}
          {tab === "treasury" && <TreasuryTab cid={company.id} fy={fy} />}
          {tab === "payroll" && <PayrollTab cid={company.id} fy={fy} canDetail={company.my_permissions.includes("payroll.detail")} />}
          {tab === "budget-dashboard" && <BudgetDashboardTab cid={company.id} fy={fy} currency={company.currency} />}
          {tab === "analysis" && <AnalysisTab cid={company.id} fy={fy} currency={company.currency} />}
          {tab === "dashboard" && <DashboardTab companyId={company.id} fy={fy} />}
          {tab === "budgets" && <BudgetsTab companyId={company.id} fy={fy} years={years} canWrite={canWrite} />}
          {tab === "centers" && <CentersTab companyId={company.id} fy={fy} canWrite={canWrite} />}
          {tab === "models" && <ModelsTab companyId={company.id} fy={fy} canWrite={canWrite} canApprove={canApprove} />}
          {tab === "projections" && <ProjectionsTab companyId={company.id} />}
          {tab === "treasury-plan" && <TreasuryPlanTab cid={company.id} fy={fy} canWrite={canWrite} canApprove={canApprove} />}
        </>
      )}
    </>
  );
}
