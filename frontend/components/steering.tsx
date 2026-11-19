"use client";

/**
 * Éléments partagés du pilotage (contrôle de gestion) : filtres de période communs, état des données et actualisation,
 * cartes d'indicateurs, classements Top 10, détail jusqu'aux écritures. Aucune valeur n'est calculée ici : l'écran
 * affiche ce que renvoie l'API `/companies/{id}/fiscal-years/{fy}/steering/…`.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowDownRight, ArrowUpRight, RefreshCw } from "lucide-react";
import { useApiResource } from "@/lib/use-api";
import type { FiscalYear } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

export type Num = string | number | null | undefined;
export const MONTHS = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"];
export const SHORT = ["Janv.", "Févr.", "Mars", "Avr.", "Mai", "Juin", "Juil.", "Août", "Sept.", "Oct.", "Nov.", "Déc."];
export const SERIES = { blue: "hsl(var(--chart-blue))", orange: "hsl(var(--chart-orange))", green: "hsl(var(--chart-green))", violet: "hsl(var(--chart-violet))" };
export const tooltipStyle: React.CSSProperties = { background: "hsl(var(--popover))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 };

const n = (v: Num) => (v === null || v === undefined || v === "" ? null : Number(v));
const nf = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
export const cur = (c?: string) => (c === "XOF" || c === "XAF" ? "FCFA" : c ?? "");
/** Montant entier avec la devise ; « — » si la donnée est absente (jamais zéro par défaut). */
export function money(v: Num, c?: string) { const x = n(v); return x === null ? "—" : `${nf.format(x)}${c ? ` ${cur(c)}` : ""}`; }
export function pctTxt(v: Num) { const x = n(v); return x === null ? "—" : `${nf1.format(x)} %`; }

// ------------------------------------------------------------------ période partagée
export interface PeriodState { view: "year" | "month" | "cumulative" | "custom"; month: number; from: string; to: string; compare: boolean; source: string }
export const defaultPeriod: PeriodState = { view: "year", month: 1, from: "", to: "", compare: true, source: "auto" };
/** Une période personnalisée n'est envoyée au serveur qu'avec ses deux dates. */
export function periodReady(p: PeriodState) { return p.view !== "custom" || (!!p.from && !!p.to && p.from <= p.to); }
export function periodQuery(p: PeriodState, extra: Record<string, string> = {}) {
  const q = new URLSearchParams({ view: p.view, source: p.source, ...extra });
  if (p.view === "month" || p.view === "cumulative") q.set("month", String(p.month));
  if (p.view === "custom" && p.from && p.to) { q.set("date_from", p.from); q.set("date_to", p.to); }
  return q;
}
function fyMonths(fy: FiscalYear) {
  const [sy, sm] = fy.start_date.split("-").map(Number); const [ey, em] = fy.end_date.split("-").map(Number);
  const out: { rank: number; label: string }[] = [];
  for (let y = sy, m = sm, r = 1; y < ey || (y === ey && m <= em); r++, m === 12 ? (y++, m = 1) : m++) out.push({ rank: r, label: `${MONTHS[m - 1]} ${y}` });
  return out;
}

export function PeriodBar({ fy, value, onChange, showCompare = true }: { fy: FiscalYear; value: PeriodState; onChange: (p: PeriodState) => void; showCompare?: boolean }) {
  const months = fyMonths(fy);
  return (
    <div className="mb-4 flex flex-wrap items-end gap-3 rounded-lg border bg-card p-3 shadow-card text-sm">
      <label className="flex flex-col gap-1"><span className="text-xs text-muted-foreground">Vue</span>
        <Select value={value.view} onChange={(e) => onChange({ ...value, view: e.target.value as PeriodState["view"] })} className="w-44">
          <option value="year">Exercice complet</option><option value="month">Mois</option><option value="cumulative">Cumul depuis le début</option><option value="custom">Période personnalisée</option>
        </Select></label>
      {(value.view === "month" || value.view === "cumulative") && (
        <label className="flex flex-col gap-1"><span className="text-xs text-muted-foreground">{value.view === "month" ? "Mois" : "Jusqu'à fin"}</span>
          <Select value={value.month} onChange={(e) => onChange({ ...value, month: Number(e.target.value) })} className="w-44">
            {months.map((m) => <option key={m.rank} value={m.rank}>{m.label}</option>)}
          </Select></label>
      )}
      {value.view === "custom" && <>
        <label className="flex flex-col gap-1"><span className="text-xs text-muted-foreground">Du</span>
          <Input type="date" min={fy.start_date} max={fy.end_date} value={value.from} onChange={(e) => onChange({ ...value, from: e.target.value })} /></label>
        <label className="flex flex-col gap-1"><span className="text-xs text-muted-foreground">Au</span>
          <Input type="date" min={fy.start_date} max={fy.end_date} value={value.to} onChange={(e) => onChange({ ...value, to: e.target.value })} /></label>
      </>}
      <label className="flex flex-col gap-1"><span className="text-xs text-muted-foreground">Source</span>
        <Select value={value.source} onChange={(e) => onChange({ ...value, source: e.target.value })} className="w-56">
          <option value="auto">Automatique (natif, sinon importé)</option><option value="native">Écritures natives validées</option>
          <option value="imported">Grand livre importé</option><option value="trial_balance">Balance importée (annuel)</option>
        </Select></label>
      {!periodReady(value) && <span className="pb-2 text-xs text-warning-strong">Indiquez les deux dates de la période (début ≤ fin).</span>}
      {showCompare && <label className="flex items-center gap-2 pb-2"><input type="checkbox" checked={value.compare} onChange={(e) => onChange({ ...value, compare: e.target.checked })} /> Comparer à N-1 (période équivalente)</label>}
    </div>
  );
}

// ------------------------------------------------------------------ état des données et actualisation
const SOURCE_LABEL: Record<string, string> = { native: "Écritures natives validées", imported: "Grand livre importé", trial_balance: "Balance importée" };

export function DataStatus({ cid, fyId, data, loading, reload }: {
  cid: string; fyId: string; loading: boolean; reload: () => Promise<void>;
  data: { source?: string | null; source_notes?: string[]; computed_at?: string; watermark?: { token: string; native_last_validated_at?: string | null; native_last_entry?: { number: string | null; label: string } | null; native_pending: number; ledger_imported_at?: string | null } } | null;
}) {
  const [stale, setStale] = useState(false);
  const { data: wm, reload: rewm } = useApiResource<{ token: string }>(`/companies/${cid}/fiscal-years/${fyId}/steering/watermark`);
  useEffect(() => { const t = setInterval(() => { void rewm(); }, 60_000); return () => clearInterval(t); }, [rewm]);
  useEffect(() => { setStale(!!(wm && data?.watermark && wm.token !== data.watermark.token)); }, [wm, data]);
  const w = data?.watermark;
  return (
    <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground" role="status">
      {loading ? <span>Actualisation en cours…</span> : data?.computed_at && <span>Calculé le {new Date(data.computed_at).toLocaleString("fr-FR")}</span>}
      {data?.source && <span>Source : <strong className="text-foreground">{SOURCE_LABEL[data.source] ?? data.source}</strong></span>}
      {w?.native_last_entry && <span>Dernière écriture intégrée : {w.native_last_entry.number} ({w.native_last_validated_at ? new Date(w.native_last_validated_at).toLocaleString("fr-FR") : ""})</span>}
      {w?.ledger_imported_at && data?.source === "imported" && <span>Grand livre importé le {new Date(w.ledger_imported_at).toLocaleString("fr-FR")}</span>}
      {!!w?.native_pending && <Badge tone="amber">{w.native_pending} écriture(s) en attente de validation</Badge>}
      {stale && <Badge tone="blue">Nouvelles données disponibles</Badge>}
      <Button size="sm" variant="ghost" onClick={() => { void reload(); void rewm(); }} disabled={loading}><RefreshCw className="h-3.5 w-3.5" aria-hidden /> Actualiser</Button>
      {data?.source_notes?.map((x, i) => <span key={i} className="w-full">{x}</span>)}
    </div>
  );
}

// ------------------------------------------------------------------ cartes et classements
export function Kpi({ title, value, currency, variation, onOpen, hint, tone, text }: {
  title: string; value: Num; currency?: string; variation?: Num; onOpen?: () => void; hint?: string; tone?: "good" | "bad"; text?: string;
}) {
  const v = n(variation);
  const body = (
    <>
      <p className="text-[13px] font-medium text-muted-foreground">{title}</p>
      <p className={cn("mt-1 truncate text-[22px] font-bold tabular-nums", tone === "bad" && n(value) !== null && n(value)! < 0 && "text-destructive-strong")}>{text ?? money(value, currency)}</p>
      {v !== null ? (
        <p className={cn("mt-1 flex items-center gap-1 text-xs font-semibold", v >= 0 ? "text-success-strong" : "text-destructive-strong")}>
          {v >= 0 ? <ArrowUpRight className="h-3.5 w-3.5" aria-hidden /> : <ArrowDownRight className="h-3.5 w-3.5" aria-hidden />}{v > 0 ? "+" : ""}{nf1.format(v)} % vs N-1
        </p>
      ) : variation !== undefined ? <p className="mt-1 text-xs text-muted-foreground">Variation non calculable</p> : null}
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
    </>
  );
  return onOpen
    ? <button type="button" onClick={onOpen} className="rounded-xl border bg-card p-4 text-left shadow-card transition-shadow hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label={`${title} : ouvrir le détail`}>{body}</button>
    : <div className="rounded-xl border bg-card p-4 shadow-card">{body}</div>;
}

export interface TopItem { key: string; label: string; amount: Num; share: Num; rank: number; rubric?: string | null }
export function TopList({ title, data, currency, onOpen }: {
  title: string; currency?: string; onOpen?: (key: string) => void;
  data: { total?: Num; items?: TopItem[]; count?: number; available?: boolean; reason?: string; coverage?: Num; unattributed?: Num } | undefined;
}) {
  return (
    <section className="rounded-xl border bg-card p-4 shadow-card">
      <h3 className="mb-3 flex items-baseline justify-between text-sm font-semibold"><span>{title}</span>
        {data?.total !== undefined && <span className="text-xs font-normal text-muted-foreground">Total {money(data.total, currency)}</span>}</h3>
      {data?.available === false ? <p className="text-sm text-muted-foreground">{data.reason}</p> : !data?.items?.length ? <p className="text-sm text-muted-foreground">Aucun montant sur la période.</p> : (
        <ol className="space-y-2">
          {data.items.map((i) => (
            <li key={i.key}>
              <button type="button" disabled={!onOpen} onClick={() => onOpen?.(i.key)} className="w-full text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-default">
                <span className="flex items-baseline gap-2 text-[13px]">
                  <span className="w-5 shrink-0 text-xs text-muted-foreground">{i.rank}</span>
                  <span className="min-w-0 flex-1 truncate" title={i.label}>{i.label}</span>
                  <span className="font-medium tabular-nums">{money(i.amount)}</span>
                  <span className="w-14 text-right text-xs text-muted-foreground tabular-nums">{pctTxt(i.share)}</span>
                </span>
                <span className="ml-7 mt-1 block h-1.5 rounded-full bg-muted" aria-hidden>
                  <span className="block h-1.5 rounded-full bg-primary" style={{ width: `${Math.min(100, Math.max(0, n(i.share) ?? 0))}%` }} />
                </span>
              </button>
            </li>
          ))}
        </ol>
      )}
      {data?.coverage !== undefined && data.coverage !== null && n(data.coverage)! < 100 && (
        <p className="mt-3 text-xs text-muted-foreground">Attribué à un tiers : {pctTxt(data.coverage)} du total ; {money(data.unattributed, currency)} non attribuables (écritures sans tiers ou à plusieurs tiers).</p>
      )}
    </section>
  );
}

export function Reliability({ r }: { r?: { level: string; provisional: boolean; reserves: string[] } }) {
  if (!r) return null;
  const lab = { high: ["Fiabilité élevée", "green"], medium: ["Fiabilité moyenne", "amber"], low: ["Fiabilité faible", "red"] }[r.level] ?? ["—", "neutral"];
  return (
    <section className="rounded-xl border bg-card p-4 shadow-card">
      <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">Qualité des données <Badge tone={lab[1] as "green"}>{lab[0]}</Badge>{r.provisional && <Badge tone="amber">Résultats provisoires</Badge>}</h3>
      {r.reserves.length ? <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">{r.reserves.map((x, i) => <li key={i}>{x}</li>)}</ul>
        : <p className="text-sm text-muted-foreground">Aucune réserve.</p>}
    </section>
  );
}

// ------------------------------------------------------------------ détail jusqu'aux écritures
export interface DrillTarget { kind: string; key?: string | null; title: string }
interface DrillData {
  total_lines: number; source: string; masked_payroll_lines: number; period: { from: string; to: string };
  accounts: { account: string; label: string | null; rubric: string | null; debit: string; credit: string }[];
  lines: { date: string; journal: string | null; number: string | null; piece: string | null; label: string | null; account: string; third_party: string | null; debit: string; credit: string; opening: boolean; entry_id: string | null }[];
}
export function Drill({ cid, fyId, period, target, onClose, currency }: { cid: string; fyId: string; period: PeriodState; target: DrillTarget | null; onClose: () => void; currency?: string }) {
  const [page, setPage] = useState(0);
  useEffect(() => setPage(0), [target]);
  const q = target ? periodQuery(period, { kind: target.kind, limit: "100", offset: String(page * 100), ...(target.key ? { key: target.key } : {}) }) : null;
  const { data, error, loading } = useApiResource<DrillData>(q ? `/companies/${cid}/fiscal-years/${fyId}/steering/drilldown?${q}` : null);
  return (
    <Dialog open={!!target} onClose={onClose} title={target?.title ?? ""} size="xl" description="Comptes et écritures sources de l'indicateur, sur la période sélectionnée.">
      {error ? <Alert>{error}</Alert> : loading || !data ? <Loading /> : !data.total_lines ? <EmptyState title="Aucune écriture" description="Aucun mouvement sur la période." /> : (
        <div className="space-y-4">
          <Table>
            <THead><tr><TH>Compte</TH><TH>Intitulé</TH><TH>Rubrique</TH><TH className="text-right">Débit</TH><TH className="text-right">Crédit</TH></tr></THead>
            <TBody>{data.accounts.map((a) => <TR key={a.account}><TD className="font-medium">{a.account}</TD><TD className="text-xs">{a.label}</TD><TD className="text-xs">{a.rubric}</TD>
              <TD className="text-right">{money(a.debit)}</TD><TD className="text-right">{money(a.credit)}</TD></TR>)}</TBody>
          </Table>
          {data.masked_payroll_lines > 0 && <Alert kind="info">{data.masked_payroll_lines} ligne(s) de rémunération masquée(s) : accès restreint.</Alert>}
          <Table>
            <THead><tr><TH>Date</TH><TH>Jnl</TH><TH>Numéro</TH><TH>Pièce</TH><TH>Libellé</TH><TH>Compte</TH><TH>Tiers</TH><TH className="text-right">Débit</TH><TH className="text-right">Crédit</TH></tr></THead>
            <TBody>{data.lines.map((l, i) => (
              <TR key={i}><TD className="whitespace-nowrap">{new Date(l.date).toLocaleDateString("fr-FR")}{l.opening ? " (AN)" : ""}</TD><TD>{l.journal}</TD>
                <TD>{l.entry_id ? <Link className="text-link hover:underline" href={`/companies/${cid}/comptabilite/ecritures/${l.entry_id}`}>{l.number}</Link> : l.number}</TD>
                <TD>{l.piece}</TD><TD className="max-w-xs truncate">{l.label}</TD><TD>{l.account}</TD><TD className="text-xs">{l.third_party}</TD>
                <TD className="text-right">{money(l.debit)}</TD><TD className="text-right">{money(l.credit)}</TD></TR>))}</TBody>
          </Table>
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>{data.total_lines} ligne(s) · {currency ? cur(currency) : ""}</span>
            {data.total_lines > 100 && <span className="flex gap-2">
              <Button size="sm" variant="outline" disabled={page === 0} onClick={() => setPage(page - 1)}>Précédentes</Button>
              <Button size="sm" variant="outline" disabled={(page + 1) * 100 >= data.total_lines} onClick={() => setPage(page + 1)}>Suivantes</Button></span>}
          </div>
        </div>
      )}
    </Dialog>
  );
}
