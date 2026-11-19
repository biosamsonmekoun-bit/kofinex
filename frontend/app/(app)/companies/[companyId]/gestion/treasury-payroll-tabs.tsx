"use client";

import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useApiResource } from "@/lib/use-api";
import type { FiscalYear } from "@/lib/types";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import {
  DataStatus, Drill, type DrillTarget, Kpi, type Num, PeriodBar, type PeriodState, SERIES, SHORT, defaultPeriod, money, pctTxt, periodQuery, periodReady, tooltipStyle,
} from "@/components/steering";

interface Acc { account: string; label: string | null; kind: string | null; opening: Num; receipts: Num; payments: Num; transfers: Num; closing: Num }
interface Tre {
  available: boolean; reason?: string; source: string | null; source_notes: string[]; computed_at: string; watermark: never; currency: string;
  opening: Num; receipts: Num; payments: Num; closing: Num; change: Num; internal_transfers: Num; check: boolean; accounts: Acc[];
  by_kind: Record<string, { opening: Num; closing: Num }>; receipts_by_category: { label: string; amount: Num; share: Num }[];
  payments_by_category: { label: string; amount: Num; share: Num }[]; monthly: { year: number; month: number; receipts: Num; payments: Num }[];
  notes: string[]; forecast: { reason: string }; conventions: string[];
}
const KIND: Record<string, string> = { bank: "Banque", cash: "Caisse", unknown: "Non distinguée" };

/** Tableau de bord de trésorerie : flux réellement enregistrés, transferts internes exclus, contrôle du solde. */
export function TreasuryTab({ cid, fy }: { cid: string; fy: FiscalYear }) {
  const [p, setP] = useState<PeriodState>(defaultPeriod);
  const [drill, setDrill] = useState<DrillTarget | null>(null);
  const { data, error, loading, reload } = useApiResource<Tre>(periodReady(p) ? `/companies/${cid}/fiscal-years/${fy.id}/steering/treasury?${periodQuery(p)}` : null);
  const c = data?.currency;
  return (
    <>
      <PeriodBar fy={fy} value={p} onChange={setP} showCompare={false} />
      <DataStatus cid={cid} fyId={fy.id} data={data ?? null} loading={loading} reload={reload} />
      {error ? <Alert>{error}</Alert> : !periodReady(p) ? null : !data ? <Loading /> : !data.available ? <EmptyState title="Trésorerie indisponible" description={data.reason ?? ""} /> : (
        <div className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-5">
            <Kpi title="Solde initial" value={data.opening} currency={c} />
            <Kpi title="Encaissements" value={data.receipts} currency={c} onOpen={() => setDrill({ kind: "treasury", title: "Mouvements de trésorerie" })} />
            <Kpi title="Décaissements" value={data.payments} currency={c} onOpen={() => setDrill({ kind: "treasury", title: "Mouvements de trésorerie" })} />
            <Kpi title="Solde final" value={data.closing} currency={c} tone="bad" />
            <Kpi title="Variation de trésorerie" value={data.change} currency={c} tone="bad" />
          </div>
          <p className="text-sm">{data.check
            ? <Badge tone="green">Contrôle vérifié : solde final = solde initial + encaissements − décaissements</Badge>
            : <Badge tone="red">Contrôle non vérifié : solde final ≠ initial + encaissements − décaissements</Badge>}
            <span className="ml-2 text-xs text-muted-foreground">Transferts internes exclus des flux : {money(data.internal_transfers, c)}</span></p>
          {data.notes.map((n, i) => <Alert key={i} kind="info">{n}</Alert>)}
          <div className="grid gap-4 lg:grid-cols-3">
            {Object.entries(data.by_kind).map(([k, v]) => <Kpi key={k} title={`Trésorerie ${KIND[k] ?? k}`} value={v.closing} currency={c} hint={`Solde initial ${money(v.opening, c)}`} />)}
          </div>
          {!!data.monthly.length && (
            <section className="rounded-xl border bg-card p-4 shadow-card">
              <h3 className="mb-3 text-sm font-semibold">Évolution mensuelle</h3>
              <div className="h-[220px]"><ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.monthly.map((m) => ({ l: `${SHORT[m.month - 1]} ${m.year}`, Encaissements: Number(m.receipts), Décaissements: Number(m.payments) }))}>
                  <CartesianGrid vertical={false} stroke="hsl(var(--border))" strokeDasharray="3 3" />
                  <XAxis dataKey="l" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} tickFormatter={(v: number) => money(v)} width={80} />
                  <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => money(v, c)} /><Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="Encaissements" fill={SERIES.green} radius={[3, 3, 0, 0]} maxBarSize={18} />
                  <Bar dataKey="Décaissements" fill={SERIES.orange} radius={[3, 3, 0, 0]} maxBarSize={18} />
                </BarChart></ResponsiveContainer></div>
            </section>
          )}
          <div className="grid gap-4 lg:grid-cols-2">
            {([["Encaissements par catégorie", data.receipts_by_category], ["Décaissements par catégorie", data.payments_by_category]] as const).map(([t, rows]) => (
              <section key={t} className="rounded-xl border bg-card p-4 shadow-card"><h3 className="mb-2 text-sm font-semibold">{t}</h3>
                {!rows.length ? <p className="text-sm text-muted-foreground">Aucun flux.</p> : <ul className="space-y-1 text-sm">{rows.map((r) => (
                  <li key={r.label} className="flex gap-2"><span className="flex-1 truncate">{r.label}</span><span className="tabular-nums">{money(r.amount)}</span><span className="w-14 text-right text-xs text-muted-foreground">{pctTxt(r.share)}</span></li>))}</ul>}
              </section>))}
          </div>
          <Table>
            <THead><tr><TH>Compte</TH><TH>Intitulé</TH><TH>Type</TH><TH className="text-right">Solde initial</TH><TH className="text-right">Encaissements</TH><TH className="text-right">Décaissements</TH><TH className="text-right">Transferts</TH><TH className="text-right">Solde final</TH></tr></THead>
            <TBody>{data.accounts.map((a) => (
              <TR key={a.account}>
                <TD className="font-medium"><button type="button" className="text-link hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  onClick={() => setDrill({ kind: "treasury", key: a.account, title: `Compte ${a.account}` })} aria-label={`Mouvements du compte ${a.account}`}>{a.account}</button></TD><TD className="text-xs">{a.label}</TD><TD className="text-xs">{KIND[a.kind ?? "unknown"]}</TD>
                <TD className="text-right">{money(a.opening)}</TD><TD className="text-right">{money(a.receipts)}</TD><TD className="text-right">{money(a.payments)}</TD>
                <TD className="text-right">{money(a.transfers)}</TD><TD className="text-right font-medium">{money(a.closing)}</TD></TR>))}</TBody>
          </Table>
          <p className="text-xs text-muted-foreground">Prévision de trésorerie : {data.forecast.reason}</p>
          <details className="text-xs text-muted-foreground"><summary className="cursor-pointer">Conventions</summary><ul className="mt-2 list-disc pl-5">{data.conventions.map((x, i) => <li key={i}>{x}</li>)}</ul></details>
        </div>
      )}
      <Drill cid={cid} fyId={fy.id} period={p} target={drill} onClose={() => setDrill(null)} currency={c} />
    </>
  );
}

interface Pay {
  available: boolean; reason?: string; source: string | null; source_notes: string[]; computed_at: string; watermark: never; currency: string;
  total: Num; ratio_to_revenue: Num; items: { account: string; label: string; amount: Num; share: Num }[];
  monthly: { period: number; year: number; month: number; personnel: Num; chiffre_affaires: Num }[] | null;
  individual: { reason: string }; headcount: { reason: string }; conventions: string[];
}

/** Masse salariale agrégée (comptes de personnel du référentiel) ; détail individuel indisponible et protégé. */
export function PayrollTab({ cid, fy, canDetail }: { cid: string; fy: FiscalYear; canDetail: boolean }) {
  const [p, setP] = useState<PeriodState>(defaultPeriod);
  const [drill, setDrill] = useState<DrillTarget | null>(null);
  const { data, error, loading, reload } = useApiResource<Pay>(periodReady(p) ? `/companies/${cid}/fiscal-years/${fy.id}/steering/payroll?${periodQuery(p)}` : null);
  const c = data?.currency;
  return (
    <>
      <PeriodBar fy={fy} value={p} onChange={setP} showCompare={false} />
      <DataStatus cid={cid} fyId={fy.id} data={data ?? null} loading={loading} reload={reload} />
      {error ? <Alert>{error}</Alert> : !periodReady(p) ? null : !data ? <Loading /> : !data.available ? <EmptyState title="Masse salariale indisponible" description={data.reason ?? ""} /> : (
        <div className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-3">
            <Kpi title="Coût total du personnel" value={data.total} currency={c} onOpen={canDetail ? () => setDrill({ kind: "personnel", title: "Charges de personnel" }) : undefined}
                 hint={canDetail ? undefined : "Détail des écritures réservé aux comptables et administrateurs"} />
            <Kpi title="Masse salariale / chiffre d'affaires" value={data.ratio_to_revenue} text={pctTxt(data.ratio_to_revenue)} />
            <Kpi title="Effectif" value={null} hint={data.headcount.reason} />
          </div>
          <Alert kind="info">{data.individual.reason}</Alert>
          <Table>
            <THead><tr><TH>Compte</TH><TH>Intitulé</TH><TH className="text-right">Montant</TH><TH className="text-right">Part</TH></tr></THead>
            <TBody>{data.items.map((i) => <TR key={i.account}><TD className="font-medium">{i.account}</TD><TD>{i.label}</TD><TD className="text-right">{money(i.amount)}</TD><TD className="text-right">{pctTxt(i.share)}</TD></TR>)}</TBody>
          </Table>
          {data.monthly && (
            <section className="rounded-xl border bg-card p-4 shadow-card"><h3 className="mb-3 text-sm font-semibold">Évolution mensuelle</h3>
              <div className="h-[220px]"><ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.monthly.map((m) => ({ l: SHORT[m.month - 1], "Charges de personnel": Number(m.personnel) }))}>
                  <CartesianGrid vertical={false} stroke="hsl(var(--border))" strokeDasharray="3 3" />
                  <XAxis dataKey="l" tick={{ fontSize: 12 }} /><YAxis tick={{ fontSize: 11 }} tickFormatter={(v: number) => money(v)} width={80} />
                  <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => money(v, c)} />
                  <Bar dataKey="Charges de personnel" fill={SERIES.violet} radius={[3, 3, 0, 0]} maxBarSize={24} />
                </BarChart></ResponsiveContainer></div></section>
          )}
          <p className="text-xs text-muted-foreground">Comparaison au budget : voir le tableau de bord budgétaire (lignes portant sur les comptes de personnel).</p>
          <details className="text-xs text-muted-foreground"><summary className="cursor-pointer">Conventions</summary><ul className="mt-2 list-disc pl-5">{data.conventions.map((x, i) => <li key={i}>{x}</li>)}</ul></details>
        </div>
      )}
      <Drill cid={cid} fyId={fy.id} period={p} target={drill} onClose={() => setDrill(null)} currency={c} />
    </>
  );
}

interface Insight { level: "info" | "warning" | "critical"; title: string; indicator: string; value: Num; reference: Num; gap: Num; detail: string | null; action: string; source: string | null }
const LEVEL = { critical: ["Critique", "red"], warning: ["Avertissement", "amber"], info: ["Information", "blue"] } as const;

/** Analyse et aide à la décision : constats factuels reliés à leurs indicateurs. */
export function AnalysisTab({ cid, fy, currency }: { cid: string; fy: FiscalYear; currency?: string }) {
  const [p, setP] = useState<PeriodState>(defaultPeriod);
  const { data, error, loading, reload } = useApiResource<{ available: boolean; reason?: string; items: Insight[]; note: string; computed_at: string; source: string; watermark: never; source_notes?: string[] }>(
    periodReady(p) ? `/companies/${cid}/fiscal-years/${fy.id}/steering/analysis?${periodQuery(p)}` : null);
  return (
    <>
      <PeriodBar fy={fy} value={p} onChange={setP} showCompare={false} />
      <DataStatus cid={cid} fyId={fy.id} data={data ?? null} loading={loading} reload={reload} />
      {error ? <Alert>{error}</Alert> : !periodReady(p) ? null : !data ? <Loading /> : !data.available ? <EmptyState title="Analyse indisponible" description={data.reason ?? ""} /> : (
        <>
          <p className="mb-3 text-xs text-muted-foreground">{data.note}</p>
          {!data.items.length ? <EmptyState title="Aucun point d'attention" description="Aucun constat ne dépasse les seuils de l'entreprise sur la période." /> : (
            <ul className="space-y-2">{data.items.map((x, i) => (
              <li key={i} className="rounded-lg border bg-card p-3 text-sm shadow-card">
                <p className="flex flex-wrap items-center gap-2"><Badge tone={LEVEL[x.level][1]}>{LEVEL[x.level][0]}</Badge><span className="font-semibold">{x.title}</span>
                  {x.value !== null && <span className="text-muted-foreground">· observé {money(x.value, currency)}{x.reference !== null ? ` · référence ${money(x.reference, currency)} · écart ${money(x.gap, currency)}` : ""}</span>}</p>
                {x.detail && <p className="mt-1">{x.detail}</p>}
                <p className="mt-1 text-xs text-muted-foreground">Point d&apos;attention : {x.action} · Source : {x.source ?? "—"}</p>
              </li>))}</ul>
          )}
        </>
      )}
    </>
  );
}
