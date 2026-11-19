"use client";

import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useApiResource } from "@/lib/use-api";
import { BUDGET_STATUS_LABELS, type DashboardBudget, type FiscalYear, type ManagementDashboard } from "@/lib/types";
import { formatAmount, formatAmountShort, formatDate, formatPct } from "@/lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { KpiCard, KpiGrid } from "@/components/ui/kpi-card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

// Couleurs : tokens de graphique uniquement (clair / sombre)
const C_BUDGET = "hsl(var(--chart-5))";
const C_ACTUAL = "hsl(var(--chart-1))";
const AXIS = { tick: { fill: "hsl(var(--muted-foreground))", fontSize: 12 }, tickLine: false };

function num(v: string | null | undefined): number | null {
  if (v === null || v === undefined) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: { name: string; value: number; payload: Record<string, string> }[]; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border bg-popover px-3 py-2 text-sm text-popover-foreground shadow-md">
      <p className="mb-1 text-xs text-muted-foreground">{label}</p>
      {payload.map((p) => (
        <p key={p.name} className="tabular-nums">{p.name} : {formatAmount(p.payload[`${p.name}_raw`] ?? String(p.value))}</p>
      ))}
    </div>
  );
}

function BudgetBlock({ b }: { b: DashboardBudget }) {
  const t = b.totals;
  const rows = (["produit", "charge", "solde"] as const).filter((k) => t[k]).map((k) => ({
    label: k === "produit" ? "Produits" : k === "charge" ? "Charges" : "Solde",
    Budget: num(t[k]!.budget) ?? 0, Réalisé: num(t[k]!.actual) ?? 0,
    Budget_raw: t[k]!.budget, Réalisé_raw: t[k]!.actual ?? "",
  }));
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          {b.name} <span className="text-sm font-normal text-muted-foreground">v{b.version}</span>
          <Badge tone={b.status === "approved" ? "green" : "neutral"}>{BUDGET_STATUS_LABELS[b.status]}</Badge>
        </CardTitle>
        <CardDescription>{b.lines} ligne{b.lines > 1 ? "s" : ""} de suivi — budget et réalisé de l&apos;exercice.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {b.warnings.map((w) => <Alert key={w} kind="warning">{w}</Alert>)}
        {rows.length > 0 ? (
          <div className="h-64" role="img" aria-label="Budget et réalisé par nature">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={rows} barGap={2} barCategoryGap="30%">
                <CartesianGrid stroke="hsl(var(--border))" vertical={false} />
                <XAxis dataKey="label" {...AXIS} axisLine={{ stroke: "hsl(var(--border))" }} />
                <YAxis width={88} {...AXIS} axisLine={false}
                       tickFormatter={(v: number) => v.toLocaleString("fr-FR", { notation: "compact", maximumFractionDigits: 1 })} />
                <Tooltip cursor={{ fill: "hsl(var(--muted))" }} content={<ChartTooltip />} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="Budget" fill={C_BUDGET} radius={[4, 4, 0, 0]} maxBarSize={36} />
                <Bar dataKey="Réalisé" fill={C_ACTUAL} radius={[4, 4, 0, 0]} maxBarSize={36} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : <p className="text-sm text-muted-foreground">Totaux par nature non disponibles.</p>}
        <div>
          <p className="mb-2 text-sm font-medium">
            Écarts défavorables les plus importants
            <span className="ml-2 font-normal text-muted-foreground">
              ({b.unfavorable_count} défavorable{b.unfavorable_count > 1 ? "s" : ""}, {b.favorable_count} favorable{b.favorable_count > 1 ? "s" : ""})
            </span>
          </p>
          {b.unfavorable.length === 0 ? <p className="text-sm text-muted-foreground">Aucun écart défavorable.</p> : (
            <Table>
              <THead><tr><TH>Ligne</TH><TH className="text-right">Budget</TH><TH className="text-right">Réalisé</TH><TH className="text-right">Écart</TH><TH className="text-right">Réalisation</TH></tr></THead>
              <TBody>
                {b.unfavorable.map((r, i) => (
                  <TR key={i}>
                    <TD>{r.label} <span className="text-xs text-muted-foreground">{r.account_prefix ?? ""}</span></TD>
                    <TD className="text-right">{formatAmount(r.budget)}</TD>
                    <TD className="text-right">{formatAmount(r.actual)}</TD>
                    <TD className="text-right font-medium text-destructive-strong">{formatAmount(r.variance)}</TD>
                    <TD className="text-right">{formatPct(r.realization_pct)}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export function DashboardTab({ companyId, fy }: { companyId: string; fy: FiscalYear }) {
  const { data: d, error, loading } = useApiResource<ManagementDashboard>(
    `/companies/${companyId}/fiscal-years/${fy.id}/management-dashboard`);
  if (loading && !d) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  if (!d) return null;

  const empty = !d.budget && !d.forecast && !d.cost_centers && !d.full_cost && !d.cvp && !d.standard_cost;
  if (empty) {
    return <EmptyState title="Rien à afficher pour cet exercice"
                       description="Créez un budget, des centres de coûts avec leurs saisies, ou un modèle de coûts : le tableau de bord en reprend les résultats calculés." />;
  }
  const solde = d.budget?.totals.solde;
  const real = d.budget?.totals.charge;
  const realization = real && real.actual !== null && num(real.budget) ? (num(real.actual)! / num(real.budget)! * 100).toFixed(1) : null;
  const stale = [d.full_cost, d.cvp, d.standard_cost].filter((m) => m && !m.results_current);

  return (
    <div className="space-y-5">
      {d.notes.map((n) => <Alert key={n} kind="warning">{n}</Alert>)}
      {stale.length > 0 && (
        <Alert kind="warning">Des résultats de modèles sont antérieurs à la dernière modification des paramètres ou de la balance : recalculez-les.</Alert>
      )}
      <KpiGrid>
        {solde && <KpiCard label="Solde réalisé (produits − charges)" value={formatAmountShort(solde.actual)}
                           hint={`Budget : ${formatAmountShort(solde.budget)}`} />}
        {real && <KpiCard label="Charges : taux de réalisation" value={formatPct(realization)}
                          hint={`${formatAmountShort(real.actual)} / ${formatAmountShort(real.budget)}`} />}
        {d.full_cost && <KpiCard label="Résultat analytique" value={formatAmountShort(d.full_cost.analytical_result)}
                                 hint={`${d.full_cost.name} v${d.full_cost.version}`} />}
        {d.cvp && <KpiCard label="Seuil de rentabilité" value={formatAmountShort(d.cvp.breakeven)}
                           hint={d.cvp.breakeven_date ? `Point mort : ${formatDate(d.cvp.breakeven_date)}` : "Point mort non atteint"} />}
        {d.cvp && <KpiCard label="Indice de sécurité" value={formatPct(d.cvp.safety_index_pct)}
                           hint={`Taux de marge sur coût variable : ${formatPct(d.cvp.contribution_rate_pct)}`} />}
        {d.standard_cost && <KpiCard label="Écart global sur coûts préétablis" value={formatAmountShort(d.standard_cost.totals.total)}
                                     hint="Positif = défavorable" />}
      </KpiGrid>

      <div className="grid gap-5 2xl:grid-cols-2">
        {d.budget && <BudgetBlock b={d.budget} />}
        {d.forecast && <BudgetBlock b={d.forecast} />}
      </div>

      {d.full_cost && (
        <Card>
          <CardHeader>
            <CardTitle>Coûts de revient et marges par objet</CardTitle>
            <CardDescription>{d.full_cost.name} v{d.full_cost.version} — calculé le {formatDate(d.full_cost.computed_at)}</CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <THead><tr><TH>Objet</TH><TH className="text-right">Coût de revient</TH><TH className="text-right">Coût unitaire</TH><TH className="text-right">Chiffre d&apos;affaires</TH><TH className="text-right">Marge</TH><TH className="text-right">Taux de marge</TH></tr></THead>
              <TBody>
                {d.full_cost.objects.map((o) => {
                  const rate = num(o.revenue) && o.margin !== null ? (num(o.margin)! / num(o.revenue)! * 100).toFixed(1) : null;
                  return (
                    <TR key={o.code}>
                      <TD><span className="font-medium">{o.code}</span> <span className="text-muted-foreground">{o.name}</span></TD>
                      <TD className="text-right">{formatAmount(o.cost)}</TD>
                      <TD className="text-right">{formatAmount(o.unit_cost)}</TD>
                      <TD className="text-right">{o.revenue === null ? "—" : formatAmount(o.revenue)}</TD>
                      <TD className={num(o.margin) !== null && num(o.margin)! < 0 ? "text-right font-medium text-destructive-strong" : "text-right font-medium"}>
                        {o.margin === null ? "—" : formatAmount(o.margin)}
                      </TD>
                      <TD className="text-right">{formatPct(rate)}</TD>
                    </TR>
                  );
                })}
              </TBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {d.cost_centers && (
        <Card>
          <CardHeader>
            <CardTitle>Coûts saisis par centre et par mois</CardTitle>
            <CardDescription>Saisies analytiques de l&apos;exercice — total {formatAmount(d.cost_centers.total)}</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-5 lg:grid-cols-2">
            <div className="h-56" role="img" aria-label="Coûts analytiques par mois de l'exercice">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={d.cost_centers.by_period.map((p) => ({ label: `M${p.period}`, Coûts: num(p.amount) ?? 0, Coûts_raw: p.amount }))}>
                  <CartesianGrid stroke="hsl(var(--border))" vertical={false} />
                  <XAxis dataKey="label" {...AXIS} axisLine={{ stroke: "hsl(var(--border))" }} />
                  <YAxis width={80} {...AXIS} axisLine={false}
                         tickFormatter={(v: number) => v.toLocaleString("fr-FR", { notation: "compact", maximumFractionDigits: 1 })} />
                  <Tooltip cursor={{ fill: "hsl(var(--muted))" }} content={<ChartTooltip />} />
                  <Bar dataKey="Coûts" fill={C_ACTUAL} radius={[4, 4, 0, 0]} maxBarSize={28} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <Table>
              <THead><tr><TH>Centre</TH><TH className="text-right">Coûts</TH></tr></THead>
              <TBody>
                {d.cost_centers.by_center.map((c) => (
                  <TR key={c.cost_center_id}><TD>{c.label}</TD><TD className="text-right">{formatAmount(c.amount)}</TD></TR>
                ))}
              </TBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {d.cvp && (
        <Card>
          <CardHeader>
            <CardTitle>Marge sur coût variable et seuil de rentabilité</CardTitle>
            <CardDescription>{d.cvp.name} v{d.cvp.version}</CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-x-8 gap-y-2 text-sm sm:grid-cols-2 lg:grid-cols-3">
              {([
                ["Chiffre d'affaires", formatAmount(d.cvp.revenue)], ["Charges variables", formatAmount(d.cvp.variable_costs)],
                ["Marge sur coût variable", formatAmount(d.cvp.contribution_margin)], ["Charges fixes", formatAmount(d.cvp.fixed_costs)],
                ["Résultat", formatAmount(d.cvp.result)], ["Marge de sécurité", formatAmount(d.cvp.safety_margin)],
                ["Levier opérationnel", d.cvp.operating_leverage === null ? "—" : Number(d.cvp.operating_leverage).toLocaleString("fr-FR", { maximumFractionDigits: 2 })],
                ["Point mort (jours)", d.cvp.breakeven_days === null ? "—" : Number(d.cvp.breakeven_days).toLocaleString("fr-FR", { maximumFractionDigits: 1 })],
                ["Charges non classées", formatAmount(d.cvp.unclassified_charges)],
              ] as const).map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4 border-b py-1.5">
                  <dt className="text-muted-foreground">{k}</dt><dd className="tabular-nums font-medium">{v || "—"}</dd>
                </div>
              ))}
            </dl>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
