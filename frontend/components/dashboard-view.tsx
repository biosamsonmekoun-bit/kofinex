"use client";

/**
 * Vue du tableau de bord financier (maquette de référence KOFINEX).
 * Purement présentationnelle : elle affiche ce que l'API renvoie (ou, sur la page publique de démonstration, un jeu
 * de données fictives explicitement signalé). Elle ne calcule aucun indicateur : seules des mises en forme
 * (unités, pourcentages, libellés) sont faites ici. Toute donnée absente est affichée comme telle.
 */

import Link from "next/link";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import {
  AlertTriangle, ArrowDownRight, ArrowUpRight, BarChart3, BarChart4, CalendarCheck, CheckCircle2, Coins, FileText, Landmark,
} from "lucide-react";
import type { DashAlert, DashBreakdown, DashKpi, DashboardData, Num } from "@/lib/dashboard-types";
import { Badge } from "@/components/ui/feedback";
import { cn } from "@/lib/utils";

// ------------------------------------------------------------------ mise en forme (aucun calcul financier)
const n = (v: Num | null | undefined): number | null => (v === null || v === undefined || v === "" ? null : Number(v));
const nf1 = new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const nf0 = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 });

export function currencyLabel(code: string) {
  return code === "XOF" || code === "XAF" ? "FCFA" : code;
}

/** Échelle d'affichage commune à un ensemble de montants. */
function scaleFor(max: number): { div: number; suffix: string } {
  const a = Math.abs(max);
  if (a >= 1e9) return { div: 1e9, suffix: "Md" };
  if (a >= 1e6) return { div: 1e6, suffix: "M" };
  if (a >= 1e4) return { div: 1e3, suffix: "k" };
  return { div: 1, suffix: "" };
}

export function money(v: Num | null | undefined, cur?: string): string {
  const x = n(v);
  if (x === null) return "—";
  const { div, suffix } = scaleFor(x);
  const txt = div === 1 ? nf0.format(x) : `${nf1.format(x / div)} ${suffix}`;
  return cur ? `${txt} ${cur}` : txt;
}

const pctTxt = (v: Num | null | undefined) => (n(v) === null ? "—" : `${nf1.format(n(v)!)} %`);
const signedPct = (v: number) => `${v > 0 ? "+" : ""}${nf1.format(v)} %`;
const sentence = (s: string) => (s === s.toUpperCase() ? s.charAt(0) + s.slice(1).toLowerCase() : s);

const SERIES = ["hsl(var(--chart-blue))", "hsl(var(--chart-orange))", "hsl(var(--chart-green))", "hsl(var(--chart-violet))"];

function Panel({ title, action, children, className }: { title: React.ReactNode; action?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <section className={cn("flex min-w-0 flex-col rounded-xl border bg-card p-5 text-card-foreground shadow-card", className)}>
      <header className="mb-4 flex items-baseline justify-between gap-3">
        <h2 className="text-[17px] font-semibold leading-tight">{title}</h2>
        {action}
      </header>
      {children}
    </section>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-1 items-center justify-center rounded-lg border border-dashed bg-muted/40 px-4 py-10 text-center text-sm text-muted-foreground">{children}</div>;
}

function Variation({ value, label }: { value: Num | null | undefined; label?: string | null }) {
  const v = n(value);
  if (v === null) return <p className="text-[13px] text-muted-foreground" title="Non calculée : exercice précédent absent ou nul">Variation non disponible</p>;
  const up = v >= 0;
  const Icon = up ? ArrowUpRight : ArrowDownRight;
  return (
    <div>
      <p className={cn("flex items-center gap-1 text-[14px] font-semibold", up ? "text-success-strong" : "text-destructive-strong")}>
        <Icon className="h-4 w-4" aria-hidden /> {signedPct(v)}
      </p>
      {label && <p className="text-[12.5px] text-muted-foreground">vs. {label}</p>}
    </div>
  );
}

function KpiTile({ icon: Icon, tone, title, kpi, value, cur, foot }: {
  icon: React.ElementType; tone: string; title: string; kpi?: DashKpi; value?: Num | null; cur: string; foot: React.ReactNode;
}) {
  const val = kpi ? (kpi.available ? kpi.value : null) : value;
  return (
    <div className="flex min-w-0 flex-col rounded-xl border bg-card p-5 shadow-card">
      <Icon className={cn("mb-3 h-8 w-8", tone)} strokeWidth={2.2} aria-hidden />
      <p className="text-[15px] font-semibold">{title}</p>
      <p className="mt-1.5 truncate text-[24px] font-bold leading-tight tabular" title={val != null ? `${nf0.format(n(val)!)} ${cur}` : undefined}>
        {val != null ? money(val, cur) : "—"}
      </p>
      <div className="mt-2 min-h-[38px]">
        {kpi && !kpi.available ? <p className="text-[12.5px] text-muted-foreground">{kpi.reason ?? kpi.message ?? "Non disponible"}</p> : foot}
      </div>
    </div>
  );
}

function Donut({ data, cur, emptyText }: { data: DashBreakdown | null; cur: string; emptyText: string }) {
  const groups = (data?.groups ?? []).filter((g) => (n(g.amount) ?? 0) > 0);
  if (!data || !groups.length) return <Empty>{emptyText}</Empty>;
  const rows = groups.map((g, i) => ({ name: sentence(g.label), value: n(g.amount)!, share: g.share, color: SERIES[i % SERIES.length], key: g.key }));
  const total = n(data.total)!;
  const { div, suffix } = scaleFor(total);
  return (
    <div className="flex flex-1 flex-col items-center gap-5 sm:flex-row">
      <div className="relative h-[190px] w-[190px] shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={rows} dataKey="value" nameKey="name" innerRadius="62%" outerRadius="100%" startAngle={90} endAngle={-270}
                 paddingAngle={1} stroke="hsl(var(--card))" strokeWidth={2} isAnimationActive={false}>
              {rows.map((r) => <Cell key={r.key} fill={r.color} />)}
            </Pie>
            <Tooltip formatter={(v: number, name: string) => [money(v, cur), name]} contentStyle={tooltipStyle} />
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center leading-tight">
          <span className="text-[22px] font-bold tabular">{div === 1 ? nf0.format(total) : `${nf1.format(total / div)} ${suffix}`}</span>
          <span className="text-[15px] font-semibold">{cur}</span>
        </div>
      </div>
      <ul className="w-full min-w-0 flex-1 space-y-3" aria-label="Légende">
        {rows.map((r) => (
          <li key={r.key} className="flex items-center gap-2 text-[13px]">
            <span className="h-3 w-3 shrink-0 rounded-[3px]" style={{ background: r.color }} aria-hidden />
            <span className="min-w-0 flex-1 truncate" title={r.name}>{r.name}</span>
            <span className="font-medium tabular">{pctTxt(r.share)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

const tooltipStyle: React.CSSProperties = {
  background: "hsl(var(--popover))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12, color: "hsl(var(--popover-foreground))",
};

function MonthlyBars({ data, cur }: { data: DashboardData["monthly"]; cur: string }) {
  if (!data.available) return { body: <Empty>{data.reason}</Empty>, unit: `${cur}` };
  const max = Math.max(0, ...data.months.flatMap((m) => [Math.abs(n(m.income) ?? 0), Math.abs(n(m.expense) ?? 0)]));
  const { div, suffix } = scaleFor(max);
  const rows = data.months.map((m) => ({ label: m.label, year: m.year, Produits: (n(m.income) ?? 0) / div, Charges: (n(m.expense) ?? 0) / div }));
  const unit = `${suffix ? `${suffix} ` : ""}${cur}`;
  const body = (
    <div className="h-[230px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} barGap={3} barCategoryGap="26%" margin={{ top: 4, right: 4, bottom: 0, left: -18 }}>
          <CartesianGrid vertical={false} stroke="hsl(var(--border))" strokeDasharray="3 3" />
          <XAxis dataKey="label" tickLine={false} axisLine={{ stroke: "hsl(var(--border))" }} tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }} />
          <YAxis tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }}
                 tickFormatter={(v: number) => nf0.format(v)} width={48} />
          <Tooltip cursor={{ fill: "hsl(var(--muted))", opacity: 0.6 }} contentStyle={tooltipStyle}
                   labelFormatter={(l: string, p: { payload?: { year?: number } }[]) => `${l} ${p?.[0]?.payload?.year ?? ""}`}
                   formatter={(v: number, name: string) => [`${div === 1 ? nf0.format(v) : nf1.format(v)} ${unit}`, name]} />
          <Legend verticalAlign="bottom" iconType="square" iconSize={11} wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
          <Bar dataKey="Produits" fill="hsl(var(--chart-blue))" radius={[3, 3, 0, 0]} maxBarSize={16} isAnimationActive={false} />
          <Bar dataKey="Charges" fill="hsl(var(--chart-orange))" radius={[3, 3, 0, 0]} maxBarSize={16} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
  return { body, unit };
}

const ALERT_ICON: Record<DashAlert["state"], { icon: React.ElementType; tone: string }> = {
  todo: { icon: AlertTriangle, tone: "text-warning" },
  progress: { icon: CalendarCheck, tone: "text-primary" },
  done: { icon: CheckCircle2, tone: "text-success" },
  none: { icon: AlertTriangle, tone: "text-muted-foreground" },
};
const ALERT_BADGE: Record<DashAlert["state"], { label: string; tone: "amber" | "blue" | "green" | "neutral" }> = {
  todo: { label: "À traiter", tone: "amber" }, progress: { label: "En cours", tone: "blue" },
  done: { label: "Terminée", tone: "green" }, none: { label: "Indisponible", tone: "neutral" },
};

function when(iso: string) {
  const d = new Date(iso);
  const today = new Date();
  const y = new Date(); y.setDate(today.getDate() - 1);
  const hm = d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  if (d.toDateString() === today.toDateString()) return `Aujourd'hui à ${hm}`;
  if (d.toDateString() === y.toDateString()) return `Hier à ${hm}`;
  return `${d.toLocaleDateString("fr-FR")} à ${hm}`;
}

export interface DashboardLinks { alerts?: string | null; activities?: string | null }

export function DashboardView({ data, links, compact = false, demo = false }: {
  data: DashboardData; links?: DashboardLinks; compact?: boolean; demo?: boolean;
}) {
  const cur = currencyLabel(data.company.currency);
  const fullYear = data.period.key === "year";
  const bars = MonthlyBars({ data: data.monthly, cur });
  const seeAll = (href?: string | null) => (href ? <Link href={href} className="text-[13px] font-medium text-link hover:underline">Voir tout</Link> : null);
  const k = data.kpis;
  const scope = fullYear ? "Cumul exercice" : `Cumul ${data.period.label}`;

  return (
    <div className={cn("space-y-5", compact && "space-y-3")}>
      <div>
        <h1 className="text-[26px] font-bold leading-tight">Tableau de bord</h1>
        <p className="mt-1 text-[15px] text-muted-foreground">Vue synthétique de la situation financière et opérationnelle</p>
        {demo && (
          <p className="mt-2 inline-flex items-center gap-2 rounded-md border border-warning/40 bg-warning/10 px-2.5 py-1 text-[12.5px] font-semibold text-warning-strong">
            Démonstration — données fictives, sans lien avec une entreprise réelle
          </p>
        )}
        {!fullYear && !demo && (
          <p className="mt-2 text-[12.5px] text-muted-foreground">
            Chiffre d&apos;affaires, résultat net, trésorerie et indicateurs : analyse annuelle de l&apos;exercice {data.fiscal_year.label}.
            Charges, produits et graphiques : période {data.period.label}.
          </p>
        )}
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiTile icon={BarChart4} tone="text-success" title="Chiffre d'affaires" kpi={k.revenue} cur={cur}
                 foot={<Variation value={k.revenue.variation} label={data.previous_label} />} />
        <KpiTile icon={Coins} tone="text-primary" title="Résultat net" kpi={k.net_income} cur={cur}
                 foot={<Variation value={k.net_income.variation} label={data.previous_label} />} />
        <KpiTile icon={Landmark} tone="text-violet" title="Trésorerie" kpi={k.cash} cur={cur}
                 foot={<p className="text-[13px] text-muted-foreground">Trésorerie nette à la clôture</p>} />
        <KpiTile icon={BarChart3} tone="text-chart-orange" title="Charges totales" value={data.expenses?.total ?? null} cur={cur}
                 foot={<p className="text-[13px] text-muted-foreground">{data.expenses ? scope : (data.breakdown_note ?? "Non disponible")}</p>} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title={<>Évolution des produits et charges <span className="text-[12px] font-normal text-muted-foreground">(en {bars.unit})</span></>}>
          {bars.body}
        </Panel>
        <Panel title="Structure des charges">
          <Donut data={data.expenses} cur={cur} emptyText={data.breakdown_note ?? "Aucune charge dans les données validées de la période."} />
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Principaux indicateurs financiers">
          {data.analysis ? (
            <div className="overflow-hidden rounded-lg border">
              <table className="w-full text-[13px]">
                <thead className="bg-muted/70 text-left text-[12.5px] font-semibold">
                  <tr><th className="px-3 py-2.5">Indicateur</th><th className="px-3 py-2.5 text-right">Valeur</th><th className="px-3 py-2.5 text-right">Variation</th></tr>
                </thead>
                <tbody className="divide-y">
                  {data.indicators.map((i) => {
                    const v = n(i.variation);
                    return (
                      <tr key={i.code}>
                        <td className="px-3 py-2.5">{i.name ?? i.code}</td>
                        <td className="px-3 py-2.5 text-right font-medium tabular">{i.available ? money(i.value) : "—"}</td>
                        <td className={cn("px-3 py-2.5 text-right font-semibold tabular", v === null ? "text-muted-foreground" : v >= 0 ? "text-success-strong" : "text-destructive-strong")}
                            title={v === null ? "Non calculée : valeur N-1 absente ou nulle" : undefined}>
                          {v === null ? "—" : <span className="inline-flex items-center gap-1">{v >= 0 ? <ArrowUpRight className="h-3.5 w-3.5" aria-hidden /> : <ArrowDownRight className="h-3.5 w-3.5" aria-hidden />}{signedPct(v)}</span>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : <Empty>Aucune analyse financière terminée pour cet exercice : lancez l&apos;analyse après validation de la balance.</Empty>}
        </Panel>
        <Panel title="Alertes financières" action={seeAll(links?.alerts)}>
          <ul className="divide-y">
            {data.alerts.map((a) => {
              const I = ALERT_ICON[a.state]; const b = ALERT_BADGE[a.state];
              return (
                <li key={a.key} className="flex items-center gap-3 py-3 first:pt-0 last:pb-0">
                  <I.icon className={cn("h-6 w-6 shrink-0", I.tone)} strokeWidth={2.2} aria-hidden />
                  <div className="min-w-0 flex-1">
                    <p className="text-[14px] font-semibold">{a.title}</p>
                    <p className="truncate text-[12.5px] text-muted-foreground">{a.detail}</p>
                  </div>
                  <Badge tone={b.tone} className="rounded-md px-2.5 py-1">{b.label}</Badge>
                </li>
              );
            })}
          </ul>
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Répartition des produits">
          <Donut data={data.income} cur={cur} emptyText={data.breakdown_note ?? "Aucun produit dans les données validées de la période."} />
        </Panel>
        <Panel title="Activités récentes" action={seeAll(links?.activities)}>
          {data.activities.length ? (
            <ul className="divide-y">
              {data.activities.slice(0, compact ? 3 : 5).map((x) => (
                <li key={x.id} className="flex items-center gap-3 py-3 first:pt-0 last:pb-0">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary"><FileText className="h-[18px] w-[18px]" aria-hidden /></span>
                  <div className="min-w-0">
                    <p className="truncate text-[14px] font-semibold">{x.label}</p>
                    <p className="truncate text-[12.5px] text-muted-foreground">{when(x.at)}{x.user ? ` · ${x.user.full_name || x.user.email}` : ""}</p>
                  </div>
                </li>
              ))}
            </ul>
          ) : <Empty>Aucune activité journalisée pour cette entreprise.</Empty>}
        </Panel>
      </div>
    </div>
  );
}
