"use client";

import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useApiResource } from "@/lib/use-api";
import type { FiscalYear } from "@/lib/types";
import { Alert, EmptyState, Loading } from "@/components/ui/feedback";
import { Select } from "@/components/ui/form";
import {
  DataStatus, Drill, type DrillTarget, Kpi, type Num, PeriodBar, type PeriodState, Reliability, SERIES, SHORT, TopList, money, periodQuery, periodReady, tooltipStyle,
} from "@/components/steering";

type K = Record<string, Num>;
interface Top { total?: Num; items?: { key: string; label: string; amount: Num; share: Num; rank: number }[]; available?: boolean; reason?: string; coverage?: Num; unattributed?: Num }
interface Fin {
  available: boolean; reason?: string; source: string | null; source_notes: string[]; computed_at: string; watermark: never;
  company: { currency: string }; period: { from: string; to: string };
  kpis: K; library: Record<string, { name: string; value: Num; status: string; message: string | null }> & { error?: string };
  tops: Record<"produits_ao" | "charges_ao" | "produits_hao" | "charges_hao" | "clients" | "fournisseurs", Top>;
  monthly: ({ period: number; year: number; month: number } & K)[] | null;
  reliability: { level: string; provisional: boolean; reserves: string[] };
  comparison: null | { available: false; reason: string } | { available: true; fiscal_year: string; period: { from: string; to: string }; kpis: K; variations: K; notes: string[] };
  conventions: string[];
}

const MAIN: [string, string, string][] = [["marge_ao", "Marge AO", ""], ["marge_hao", "Marge HAO", ""], ["marge_totale", "Marge totale", ""],
  ["charges_ao", "Charges AO", "charges_ao"], ["produits_ao", "Produits AO", "produits_ao"]];
const LIB: [string, string][] = [["CA", "Chiffre d'affaires"], ["EBE", "Excédent brut d'exploitation"], ["RESULTAT_EXPLOITATION", "Résultat d'exploitation"],
  ["RESULTAT_FINANCIER", "Résultat financier"], ["RAO", "Résultat des activités ordinaires"], ["RESULTAT_HAO", "Résultat HAO"], ["RESULTAT_NET", "Résultat net"]];

/** Tableau de bord financier : soldes AO / HAO et indicateurs de la bibliothèque, Top 10, évolutions, N / N-1. */
export function FinancialTab({ cid, fy }: { cid: string; fy: FiscalYear }) {
  const [p, setP] = useState<PeriodState>({ view: "year", month: 1, from: "", to: "", compare: true, source: "auto" });
  const [drill, setDrill] = useState<DrillTarget | null>(null);
  const [basis, setBasis] = useState<"revenue" | "invoiced">("revenue");
  const q = periodQuery(p, { compare: String(p.compare), partner_basis: basis });
  const { data, error, loading, reload } = useApiResource<Fin>(periodReady(p) ? `/companies/${cid}/fiscal-years/${fy.id}/steering/financial?${q}` : null);
  const c = data?.company?.currency;
  const comp = data?.comparison && data.comparison.available ? data.comparison : null;
  return (
    <>
      <PeriodBar fy={fy} value={p} onChange={setP} />
      <DataStatus cid={cid} fyId={fy.id} data={data ?? null} loading={loading} reload={reload} />
      {error ? <Alert>{error}</Alert> : !periodReady(p) ? null : !data ? <Loading /> : !data.available ? <EmptyState title="Aucun réalisé" description={data.reason ?? ""} /> : (
        <div className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            {MAIN.map(([k, t, d]) => <Kpi key={k} title={t} value={data.kpis[k]} currency={c} variation={comp ? comp.variations[k] : undefined}
              onOpen={d ? () => setDrill({ kind: d, title: t }) : undefined} />)}
          </div>
          <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-9">
            {LIB.map(([code, t]) => {
              const r = data.library?.[code];
              return <Kpi key={code} title={t} value={r?.value} currency={c} hint={r && r.status !== "ok" ? (r.message ?? "Non calculé") : undefined}
                onOpen={code === "CA" ? () => setDrill({ kind: "chiffre_affaires", title: t }) : undefined} />;
            })}
            <Kpi title="Total des charges" value={data.kpis.total_charges} currency={c} variation={comp ? comp.variations.total_charges : undefined} onOpen={() => setDrill({ kind: "total_charges", title: "Total des charges" })} />
            <Kpi title="Total des produits" value={data.kpis.total_produits} currency={c} variation={comp ? comp.variations.total_produits : undefined} onOpen={() => setDrill({ kind: "total_produits", title: "Total des produits" })} />
            <Kpi title="Impôt et participation" value={data.kpis.impot_participation} currency={c} hint="Hors HAO (référentiel) ; inclus dans le résultat net" />
          </div>
          {data.library?.error && <Alert kind="warning">Indicateurs de la bibliothèque : {data.library.error}</Alert>}
          {data.comparison && !data.comparison.available && <Alert kind="info">Comparaison N-1 : {data.comparison.reason}</Alert>}
          {comp && <p className="text-xs text-muted-foreground">Comparaison avec l&apos;exercice {comp.fiscal_year}, du {new Date(comp.period.from).toLocaleDateString("fr-FR")} au {new Date(comp.period.to).toLocaleDateString("fr-FR")}. {comp.notes.join(" ")}</p>}

          <div className="grid gap-4 lg:grid-cols-2">
            <section className="rounded-xl border bg-card p-4 shadow-card">
              <h3 className="mb-3 text-sm font-semibold">Charges et produits AO / HAO{comp ? " (N et N-1)" : ""}</h3>
              <div className="h-[240px]"><ResponsiveContainer width="100%" height="100%">
                <BarChart data={[["Produits AO", "produits_ao"], ["Charges AO", "charges_ao"], ["Produits HAO", "produits_hao"], ["Charges HAO", "charges_hao"]].map(([l, k]) => ({ l, N: Number(data.kpis[k] ?? 0), ...(comp ? { "N-1": Number(comp.kpis[k] ?? 0) } : {}) }))}>
                  <CartesianGrid vertical={false} stroke="hsl(var(--border))" strokeDasharray="3 3" />
                  <XAxis dataKey="l" tick={{ fontSize: 12 }} /><YAxis tick={{ fontSize: 11 }} tickFormatter={(v: number) => money(v)} width={80} />
                  <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => money(v, c)} /><Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="N" fill={SERIES.blue} radius={[3, 3, 0, 0]} maxBarSize={28} />
                  {comp && <Bar dataKey="N-1" fill={SERIES.orange} radius={[3, 3, 0, 0]} maxBarSize={28} />}
                </BarChart></ResponsiveContainer></div>
            </section>
            <section className="rounded-xl border bg-card p-4 shadow-card">
              <h3 className="mb-3 text-sm font-semibold">Évolution mensuelle des marges</h3>
              {!data.monthly ? <p className="text-sm text-muted-foreground">Vue mensuelle indisponible avec la balance importée (montants annuels).</p> : (
                <div className="h-[240px]"><ResponsiveContainer width="100%" height="100%">
                  <LineChart data={data.monthly.map((m) => ({ l: SHORT[m.month - 1], "Marge AO": Number(m.marge_ao), "Marge HAO": Number(m.marge_hao), "Marge totale": Number(m.marge_totale) }))}>
                    <CartesianGrid vertical={false} stroke="hsl(var(--border))" strokeDasharray="3 3" />
                    <XAxis dataKey="l" tick={{ fontSize: 12 }} /><YAxis tick={{ fontSize: 11 }} tickFormatter={(v: number) => money(v)} width={80} />
                    <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => money(v, c)} /><Legend wrapperStyle={{ fontSize: 12 }} />
                    <Line dataKey="Marge AO" stroke={SERIES.blue} strokeWidth={2} dot={{ r: 3 }} />
                    <Line dataKey="Marge HAO" stroke={SERIES.violet} strokeWidth={2} dot={{ r: 3 }} />
                    <Line dataKey="Marge totale" stroke={SERIES.green} strokeWidth={2} dot={{ r: 3 }} />
                  </LineChart></ResponsiveContainer></div>
              )}
            </section>
          </div>
          {data.monthly && (
            <section className="rounded-xl border bg-card p-4 shadow-card">
              <h3 className="mb-3 text-sm font-semibold">Chiffre d&apos;affaires, charges et résultat par mois</h3>
              <div className="h-[240px]"><ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.monthly.map((m) => ({ l: SHORT[m.month - 1], "Chiffre d'affaires": Number(m.chiffre_affaires), Charges: Number(m.total_charges), Résultat: Number(m.resultat) }))}>
                  <CartesianGrid vertical={false} stroke="hsl(var(--border))" strokeDasharray="3 3" />
                  <XAxis dataKey="l" tick={{ fontSize: 12 }} /><YAxis tick={{ fontSize: 11 }} tickFormatter={(v: number) => money(v)} width={80} />
                  <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => money(v, c)} /><Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="Chiffre d'affaires" fill={SERIES.blue} radius={[3, 3, 0, 0]} maxBarSize={14} />
                  <Bar dataKey="Charges" fill={SERIES.orange} radius={[3, 3, 0, 0]} maxBarSize={14} />
                  <Bar dataKey="Résultat" fill={SERIES.green} radius={[3, 3, 0, 0]} maxBarSize={14} />
                </BarChart></ResponsiveContainer></div>
              <MonthlyTable rows={data.monthly} currency={c} />
            </section>
          )}

          <label className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">Classement des clients et fournisseurs :</span>
            <Select className="w-auto" value={basis} onChange={(e) => setBasis(e.target.value as "revenue" | "invoiced")}>
              <option value="revenue">Chiffre d&apos;affaires et charges HT des écritures</option>
              <option value="invoiced">Montants facturés sur les comptes de tiers (TTC)</option>
            </Select>
          </label>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <TopList title="Top 10 des produits AO" data={data.tops.produits_ao} currency={c} onOpen={(k) => setDrill({ kind: "account", key: k, title: `Compte ${k}` })} />
            <TopList title="Top 10 des charges AO" data={data.tops.charges_ao} currency={c} onOpen={(k) => setDrill({ kind: "account", key: k, title: `Compte ${k}` })} />
            <TopList title="Top 10 des clients" data={data.tops.clients} currency={c} onOpen={(k) => setDrill({ kind: "partner", key: k, title: "Opérations du client" })} />
            <TopList title="Top 10 des produits HAO" data={data.tops.produits_hao} currency={c} onOpen={(k) => setDrill({ kind: "account", key: k, title: `Compte ${k}` })} />
            <TopList title="Top 10 des charges HAO" data={data.tops.charges_hao} currency={c} onOpen={(k) => setDrill({ kind: "account", key: k, title: `Compte ${k}` })} />
            <TopList title="Top 10 des fournisseurs" data={data.tops.fournisseurs} currency={c} onOpen={(k) => setDrill({ kind: "partner", key: k, title: "Opérations du fournisseur" })} />
          </div>
          <Reliability r={data.reliability} />
          <details className="text-xs text-muted-foreground"><summary className="cursor-pointer">Conventions de calcul</summary>
            <ul className="mt-2 list-disc space-y-1 pl-5">{data.conventions.map((x, i) => <li key={i}>{x}</li>)}</ul></details>
        </div>
      )}
      <Drill cid={cid} fyId={fy.id} period={p} target={drill} onClose={() => setDrill(null)} currency={c} />
    </>
  );
}

function MonthlyTable({ rows, currency }: { rows: ({ month: number; year: number } & K)[]; currency?: string }) {
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="w-full min-w-[720px] text-xs tabular-nums">
        <thead className="text-left text-muted-foreground"><tr><th className="py-1">Mois</th><th className="text-right">CA</th><th className="text-right">Charges</th>
          <th className="text-right">Marge AO</th><th className="text-right">Marge totale</th><th className="text-right">Résultat</th><th className="text-right">Variation du résultat</th></tr></thead>
        <tbody className="divide-y">{rows.map((m) => {
          return <tr key={`${m.year}-${m.month}`}><td className="py-1">{SHORT[m.month - 1]} {m.year}</td><td className="text-right">{money(m.chiffre_affaires)}</td>
            <td className="text-right">{money(m.total_charges)}</td><td className="text-right">{money(m.marge_ao)}</td><td className="text-right">{money(m.marge_totale)}</td>
            <td className="text-right">{money(m.resultat)}</td><td className="text-right">{money(m.resultat_change)}</td></tr>;
        })}</tbody>
      </table>
      <p className="mt-1 text-[11px] text-muted-foreground">Montants en {currency === "XOF" || currency === "XAF" ? "FCFA" : currency}. Variation : écart avec le mois précédent.</p>
    </div>
  );
}
