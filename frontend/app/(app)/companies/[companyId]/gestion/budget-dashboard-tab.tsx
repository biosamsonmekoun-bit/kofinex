"use client";

import { useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import type { FiscalYear } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { DataStatus, Drill, type DrillTarget, Kpi, MONTHS, type Num, SERIES, SHORT, defaultPeriod, money, pctTxt, tooltipStyle } from "@/components/steering";

interface Row { label: string; nature: "charge" | "produit"; account_prefix: string | null; cost_center_id: string | null; budget: Num; actual: Num; variance: Num;
  realization_pct: Num; favorable: boolean | null; notes: string[]; forecast: { remaining_budget: Num; trend: Num } }
interface Month { period: number; year: number; month: number; budget: Num; actual: Num; variance: Num; rate: Num; favorable: boolean | null }
interface AlertItem { level: "info" | "warning" | "critical"; code: string; title: string; label: string; account_prefix: string | null; budget: Num; actual: Num; rate: Num; detail: string }
interface NatKpi { available: boolean; initial?: Num; revised?: Num; approved?: Num; budget?: Num; actual?: Num; variance?: Num; execution_rate?: Num;
  available_budget?: Num; forecast_remaining_budget?: Num; forecast_trend?: Num; forecast_variance?: Num }
interface Dash {
  available: boolean; reason?: string; source?: string; source_notes?: string[]; computed_at?: string; watermark?: never;
  budget: { id: string; name: string; version: number; status: string; versions: { id: string; version: number; status: string }[] };
  elapsed_months: number; total_months: number; kpis: { charges: NatKpi; produits: NatKpi; analytical_actual: Num };
  monthly: { charges: Month[]; produits: Month[]; charges_cumulative: Month[]; produits_cumulative: Month[] }; alerts: AlertItem[]; tops: Record<"overruns" | "revenue_shortfalls" | "savings" | "most_consumed" | "centers", Row[]>;
  rows: Row[]; warnings: string[]; commitments: { reason: string }; conventions: string[];
}
const STATUS: Record<string, string> = { draft: "Brouillon", submitted: "Soumis", approved: "Approuvé", archived: "Archivé" };
const LEVEL = { critical: ["Critique", "red"], warning: ["Avertissement", "amber"], info: ["Information", "blue"] } as const;
const TOPS: [keyof Dash["tops"], string][] = [["overruns", "Dépassements de charges"], ["revenue_shortfalls", "Sous-exécution des recettes"], ["savings", "Économies"],
  ["most_consumed", "Budgets les plus consommés"], ["centers", "Écarts par centre"]];

/** Tableau de bord budgétaire : budget de référence, réalisé de la source choisie, écarts, prévision à terminaison, alertes. */
export function BudgetDashboardTab({ cid, fy, currency }: { cid: string; fy: FiscalYear; currency?: string }) {
  const { data: budgets } = useApiResource<{ id: string; name: string; version: number; status: string; scenario: string }[]>(`/companies/${cid}/fiscal-years/${fy.id}/budgets`);
  const [budgetId, setBudgetId] = useState("");
  const [source, setSource] = useState("auto");
  const [nature, setNature] = useState<"charges" | "produits">("charges");
  const [cumul, setCumul] = useState(false);
  const [topKey, setTopKey] = useState<keyof Dash["tops"]>("overruns");
  const [drill, setDrill] = useState<DrillTarget | null>(null);
  const [thOpen, setThOpen] = useState(false);
  const q = new URLSearchParams({ source, ...(budgetId ? { budget_id: budgetId } : {}) });
  const { data, error, loading, reload } = useApiResource<Dash>(`/companies/${cid}/fiscal-years/${fy.id}/steering/budget?${q}`);

  const shown: Month[] = data?.available ? data.monthly[cumul ? (`${nature}_cumulative` as const) : nature] : [];
  const k = data?.available ? data.kpis[nature] : null;

  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-3 rounded-lg border bg-card p-3 text-sm shadow-card">
        <label className="flex flex-col gap-1"><span className="text-xs text-muted-foreground">Budget</span>
          <Select className="w-72" value={budgetId} onChange={(e) => setBudgetId(e.target.value)}>
            <option value="">Budget de référence (approuvé, sinon le plus avancé)</option>
            {budgets?.filter((b) => b.scenario === "budget").map((b) => <option key={b.id} value={b.id}>{b.name} · v{b.version} · {STATUS[b.status] ?? b.status}</option>)}
          </Select></label>
        <label className="flex flex-col gap-1"><span className="text-xs text-muted-foreground">Source du réalisé</span>
          <Select className="w-56" value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="auto">Automatique (natif, sinon importé)</option><option value="native">Écritures natives validées</option>
            <option value="imported">Grand livre importé</option><option value="trial_balance">Balance importée (annuel)</option></Select></label>
        <Button variant="outline" size="sm" onClick={() => setThOpen(true)}>Seuils d&apos;alerte</Button>
      </div>
      <DataStatus cid={cid} fyId={fy.id} data={data?.available ? data : null} loading={loading} reload={reload} />
      {error ? <Alert>{error}</Alert> : !data ? <Loading /> : !data.available ? <EmptyState title="Aucun budget" description={`${data.reason} Créez-le dans « Gestion budgétaire ».`} /> : (
        <div className="space-y-5">
          <p className="text-sm text-muted-foreground">{data.budget.name} · version {data.budget.version} · {STATUS[data.budget.status]}
            {data.budget.status !== "approved" && <Badge tone="amber" className="ml-2">Budget non approuvé</Badge>}
            {" "}· {data.elapsed_months} mois écoulé(s) sur {data.total_months}</p>
          {data.warnings.map((w, i) => <Alert key={i} kind="warning">{w}</Alert>)}
          <div role="tablist" className="flex gap-1">
            {(["charges", "produits"] as const).map((x) => <button key={x} role="tab" aria-selected={nature === x} onClick={() => setNature(x)}
              className={`rounded-md px-3 py-1.5 text-sm ${nature === x ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}>{x === "charges" ? "Charges" : "Produits"}</button>)}
          </div>
          {!k?.available ? <EmptyState title={`Aucune ligne de ${nature}`} description="Le budget ne comporte pas de ligne de cette nature." /> : (
            <>
              <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-6">
                <Kpi title="Budget initial" value={k.initial} currency={currency} />
                <Kpi title="Budget révisé" value={k.revised} currency={currency} hint={k.revised == null ? "Aucune révision" : undefined} />
                <Kpi title="Budget approuvé" value={k.approved} currency={currency} hint={k.approved == null ? "Aucune version approuvée" : undefined} />
                <Kpi title="Réalisé comptable" value={k.actual} currency={currency} hint={k.actual == null ? "Réalisé indisponible" : undefined}
                  onOpen={() => setDrill({ kind: nature === "charges" ? "total_charges" : "total_produits", title: `Réalisé : ${nature}` })} />
                <Kpi title="Écart (réalisé − budget)" value={k.variance} currency={currency} />
                <Kpi title="Taux d'exécution" value={k.execution_rate} text={pctTxt(k.execution_rate)} />
                <Kpi title="Budget disponible" value={k.available_budget} currency={currency} hint="Engagements non suivis" />
                <Kpi title="Prévision à terminaison (budget restant)" value={k.forecast_remaining_budget} currency={currency} hint="Extrapolation" />
                <Kpi title="Prévision à terminaison (tendance)" value={k.forecast_trend} currency={currency} hint="Extrapolation" />
                <Kpi title="Écart prévisionnel" value={k.forecast_variance} currency={currency} />
                <Kpi title="Réalisé analytique (centres)" value={data.kpis.analytical_actual} currency={currency} hint={data.kpis.analytical_actual == null ? "Aucune ligne par centre" : undefined} />
              </div>
              <section className="rounded-xl border bg-card p-4 shadow-card">
                <h3 className="mb-3 flex flex-wrap items-center justify-between gap-2 text-sm font-semibold">Comparaison mensuelle
                  <label className="flex items-center gap-2 text-xs font-normal"><input type="checkbox" checked={cumul} onChange={(e) => setCumul(e.target.checked)} /> Vue cumulée</label></h3>
                <div className="h-[220px]"><ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={shown.map((m) => ({ l: SHORT[m.month - 1], Budget: Number(m.budget), Réalisé: m.actual === null ? null : Number(m.actual) }))}>
                    <CartesianGrid vertical={false} stroke="hsl(var(--border))" strokeDasharray="3 3" />
                    <XAxis dataKey="l" tick={{ fontSize: 12 }} /><YAxis tick={{ fontSize: 11 }} tickFormatter={(v: number) => money(v)} width={80} />
                    <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => money(v, currency)} /><Legend wrapperStyle={{ fontSize: 12 }} />
                    <Bar dataKey="Réalisé" fill={SERIES.blue} radius={[3, 3, 0, 0]} maxBarSize={20} />
                    <Line dataKey="Budget" stroke={SERIES.orange} strokeWidth={2} dot={{ r: 3 }} />
                  </ComposedChart></ResponsiveContainer></div>
                <Table>
                  <THead><tr><TH>Mois</TH><TH className="text-right">Budget</TH><TH className="text-right">Réalisé</TH><TH className="text-right">Écart</TH><TH className="text-right">Taux d&apos;exécution</TH><TH>Appréciation</TH></tr></THead>
                  <TBody>{shown.map((m) => (
                    <TR key={m.period}><TD>{MONTHS[m.month - 1]} {m.year}</TD><TD className="text-right">{money(m.budget)}</TD><TD className="text-right">{money(m.actual)}</TD>
                      <TD className="text-right">{money(m.variance)}</TD><TD className="text-right">{pctTxt(m.rate)}</TD>
                      <TD>{m.favorable === null ? "—" : m.favorable ? <Badge tone="green">Favorable</Badge> : <Badge tone="red">Défavorable</Badge>}</TD></TR>))}</TBody>
                </Table>
              </section>
            </>
          )}
          <section className="rounded-xl border bg-card p-4 shadow-card">
            <h3 className="mb-3 text-sm font-semibold">Alertes budgétaires ({data.alerts.length})</h3>
            {!data.alerts.length ? <p className="text-sm text-muted-foreground">Aucune alerte avec les seuils de l&apos;entreprise.</p> : (
              <ul className="divide-y text-sm">{data.alerts.map((a, i) => (
                <li key={i} className="flex flex-wrap items-center gap-2 py-2">
                  <Badge tone={LEVEL[a.level][1]}>{LEVEL[a.level][0]}</Badge><span className="font-medium">{a.title}</span>
                  <span>· {a.label}{a.account_prefix ? ` (${a.account_prefix})` : ""}</span>
                  <span className="text-muted-foreground">· budget {money(a.budget, currency)} · réalisé {money(a.actual, currency)} · {pctTxt(a.rate)}</span>
                  <span className="w-full text-xs text-muted-foreground">{a.detail}</span>
                  {a.account_prefix && <Button size="sm" variant="ghost" onClick={() => setDrill({ kind: "account_prefix", key: a.account_prefix, title: `Racine ${a.account_prefix}` })}>Écritures</Button>}
                </li>))}</ul>
            )}
          </section>
          <section className="rounded-xl border bg-card p-4 shadow-card">
            <div role="tablist" className="mb-3 flex flex-wrap gap-1">{TOPS.map(([key, l]) => <button key={key} role="tab" aria-selected={topKey === key} onClick={() => setTopKey(key)}
              className={`rounded-md px-3 py-1.5 text-xs ${topKey === key ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}>Top 10 · {l}</button>)}</div>
            {!data.tops[topKey].length ? <p className="text-sm text-muted-foreground">Aucune ligne.</p> : (
              <Table>
                <THead><tr><TH>#</TH><TH>Ligne</TH><TH className="text-right">Budget</TH><TH className="text-right">Réalisé</TH><TH className="text-right">Écart</TH><TH className="text-right">Taux</TH><TH /></tr></THead>
                <TBody>{data.tops[topKey].map((r, i) => (
                  <TR key={i}><TD>{i + 1}</TD><TD>{r.label}{r.account_prefix ? ` (${r.account_prefix})` : ""}</TD><TD className="text-right">{money(r.budget)}</TD>
                    <TD className="text-right">{money(r.actual)}</TD><TD className="text-right">{money(r.variance)}</TD><TD className="text-right">{pctTxt(r.realization_pct)}</TD>
                    <TD>{r.account_prefix && <Button size="sm" variant="ghost" onClick={() => setDrill({ kind: "account_prefix", key: r.account_prefix, title: `Racine ${r.account_prefix}` })}>Détail</Button>}</TD></TR>))}</TBody>
              </Table>
            )}
          </section>
          <p className="text-xs text-muted-foreground">{data.commitments.reason}</p>
          <details className="text-xs text-muted-foreground"><summary className="cursor-pointer">Conventions de calcul</summary>
            <ul className="mt-2 list-disc space-y-1 pl-5">{data.conventions.map((x, i) => <li key={i}>{x}</li>)}</ul></details>
        </div>
      )}
      <Drill cid={cid} fyId={fy.id} period={{ ...defaultPeriod, source }} target={drill} onClose={() => setDrill(null)} currency={currency} />
      <ThresholdsDialog cid={cid} open={thOpen} onClose={() => { setThOpen(false); void reload(); }} />
    </>
  );
}

const TH_FIELDS: [string, string][] = [["consumption_info_pct", "Information : consommation d'un budget de charges ≥ (%)"],
  ["overrun_warning_pct", "Avertissement : réalisé > budget à (%)"], ["overrun_critical_pct", "Critique : réalisé ≥ budget à (%)"],
  ["pace_gap_points", "Consommation en avance sur le temps écoulé (points)"], ["under_execution_points", "Recettes en retard sur le temps écoulé (points)"],
  ["center_variance_pct", "Écart d'un centre (% de son budget)"], ["change_pct", "Analyse : variation N / N-1 significative (%)"],
  ["concentration_pct", "Analyse : part du premier client / fournisseur (%)"]];

function ThresholdsDialog({ cid, open, onClose }: { cid: string; open: boolean; onClose: () => void }) {
  const { data, reload } = useApiResource<Record<string, string> & { can_edit: boolean; customized: boolean }>(open ? `/companies/${cid}/management-alert-settings` : null);
  const [f, setF] = useState<Record<string, string> | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const v = f ?? (data ? Object.fromEntries(TH_FIELDS.map(([k]) => [k, String(data[k])])) : null);
  async function save() {
    setMsg(null);
    try { await api.put(`/companies/${cid}/management-alert-settings`, v); await reload(); setF(null); onClose(); } catch (e) { setMsg(errorMessage(e)); }
  }
  return (
    <Dialog open={open} onClose={onClose} title="Seuils d'alerte" description="Propres à l'entreprise ; valeurs par défaut tant qu'ils ne sont pas paramétrés.">
      {!data || !v ? <Loading /> : (
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); void save(); }}>
          {msg && <Alert>{msg}</Alert>}
          {!data.customized && <Alert kind="info">Valeurs par défaut de KOFINEX, à adapter à l&apos;entreprise.</Alert>}
          {TH_FIELDS.map(([k, l]) => <Field key={k} label={l} htmlFor={`th-${k}`}>
            <Input id={`th-${k}`} inputMode="decimal" value={v[k]} disabled={!data.can_edit} onChange={(e) => setF({ ...v, [k]: e.target.value })} /></Field>)}
          {data.can_edit ? <Button type="submit">Enregistrer</Button> : <p className="text-xs text-muted-foreground">Modification réservée aux contrôleurs de gestion et aux administrateurs.</p>}
        </form>
      )}
    </Dialog>
  );
}
