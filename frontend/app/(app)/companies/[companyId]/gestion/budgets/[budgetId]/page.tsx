"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Archive, Check, ChevronLeft, CopyPlus, Plus, Send, Trash2, Undo2 } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import {
  BUDGET_STATUS_LABELS, FORECAST_MODE_LABELS, type Budget, type BudgetAccount, type BudgetKind, type BudgetLine, type Company, type CostCenter,
  type FiscalYear, type ForecastMode, type Tracking,
} from "@/lib/types";
import { cn, formatAmount, formatDate, formatPct } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading, PageHeader } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const AMOUNT_RE = /^-?\d+(\.\d{1,2})?$/;
/** « 12 500,5 » -> « 12500.5 » ; null si le texte n'est pas un montant au centime. */
function parseAmount(s: string): string | null {
  const v = s.replace(/[\s  ]/g, "").replace(",", ".");
  return AMOUNT_RE.test(v) ? v : null;
}

function monthLabels(fy: FiscalYear | null): string[] {
  if (!fy) return Array.from({ length: 12 }, (_, i) => `M${i + 1}`);
  const start = new Date(`${fy.start_date}T00:00:00`);
  return Array.from({ length: 12 }, (_, i) => {
    const d = new Date(start.getFullYear(), start.getMonth() + i, 1);
    return d.toLocaleDateString("fr-FR", { month: "short", year: "2-digit" });
  });
}

// ------------------------------------------------------------------ éditeur de lignes
// Compte choisi dans le plan comptable de référence (plan de l'entreprise, sinon référentiel publié) : son intitulé,
// sa classe et son parent sont repris du serveur. Les totaux affichés sont ceux du serveur (aucun calcul de montant ici).
interface Row {
  rubric: string; account_prefix: string; cost_center_id: string; label: string; forecast_mode: ForecastMode;
  monthly: boolean; annual: string; months: string[];
}
const blankRow = (rubric = ""): Row => ({ rubric, account_prefix: "", cost_center_id: "", label: "", forecast_mode: "manual",
                                          monthly: false, annual: "", months: Array(12).fill("") });

function toRows(lines: BudgetLine[]): Row[] {
  const map = new Map<string, Row>();
  for (const l of lines) {
    const free = !l.account_prefix && !l.cost_center_id ? l.label ?? "" : "";
    const key = `${l.rubric ?? ""}|${l.account_prefix ?? ""}|${l.cost_center_id ?? ""}|${free}`;
    const r = map.get(key) ?? { ...blankRow(l.rubric ?? ""), account_prefix: l.account_prefix ?? "", cost_center_id: l.cost_center_id ?? "",
                                label: l.label ?? "", forecast_mode: l.forecast_mode ?? "manual" };
    if (l.period === 0) r.annual = l.amount;
    else { r.monthly = true; r.months[l.period - 1] = l.amount; }
    map.set(key, r);
  }
  return [...map.values()];
}

function toLines(rows: Row[]): { lines: BudgetLine[]; error: string | null } {
  const lines: BudgetLine[] = [];
  for (const [i, r] of rows.entries()) {
    const where = `Ligne ${i + 1}${r.label ? ` (« ${r.label} »)` : ""}`;
    if (!r.account_prefix && !r.cost_center_id && !r.rubric.trim()) return { lines, error: `${where} : indiquez un compte, un centre ou une rubrique.` };
    if (!r.account_prefix && !r.cost_center_id && !r.label.trim()) return { lines, error: `${where} : une ligne sans compte ni centre doit avoir un libellé.` };
    if (r.account_prefix && !/^\d{1,20}$/.test(r.account_prefix)) return { lines, error: `${where} : choisissez un compte dans la liste.` };
    const base = { account_prefix: r.account_prefix || null, cost_center_id: r.cost_center_id || null, label: r.label.trim() || null,
                   rubric: r.rubric.trim() || null, forecast_mode: r.forecast_mode };
    if (r.monthly) {
      for (let m = 0; m < 12; m++) {
        if (!r.months[m]) continue;
        const a = parseAmount(r.months[m]);
        if (a === null) return { lines, error: `${where}, mois ${m + 1} : montant invalide (2 décimales maximum).` };
        lines.push({ ...base, period: m + 1, amount: a });
      }
    } else {
      const a = parseAmount(r.annual);
      if (a === null) return { lines, error: `${where} : montant annuel invalide (2 décimales maximum).` };
      lines.push({ ...base, period: 0, amount: a });
    }
  }
  return { lines, error: null };
}

function LinesEditor({ companyId, budget, centers, months, onSaved }: {
  companyId: string; budget: Budget; centers: CostCenter[]; months: string[]; onSaved: (b: Budget) => void;
}) {
  const [rows, setRows] = useState<Row[]>(() => toRows(budget.lines ?? []));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const { data: accounts } = useApiResource<{ source: string; items: BudgetAccount[] }>(
    `/companies/${companyId}/fiscal-years/${budget.fiscal_year_id}/budget-accounts?kind=${budget.budget_kind}&limit=2000`);
  const byNumber = useMemo(() => new Map((accounts?.items ?? []).map((a) => [a.account_number, a])), [accounts]);
  const set = (i: number, patch: Partial<Row>) => { setSaved(false); setDirty(true); setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r))); };
  // totaux du serveur pour la dernière version enregistrée
  const serverTotal = (r: Row) => budget.grouped?.find((g) => (g.rubric ?? "") === r.rubric && (g.account_number ?? "") === r.account_prefix
    && (g.cost_center_id ?? "") === r.cost_center_id && (r.account_prefix || r.cost_center_id || g.label === r.label))?.total;
  const groups = useMemo(() => {
    const order: string[] = [];
    const idx = new Map<string, number[]>();
    rows.forEach((r, i) => { const k = r.rubric.trim(); if (!idx.has(k)) { idx.set(k, []); order.push(k); } idx.get(k)!.push(i); });
    return order.map((k) => ({ rubric: k, indexes: idx.get(k)! }));
  }, [rows]);

  function pickAccount(i: number, text: string) {
    const num = text.split(/\s/)[0].replace(/\D/g, "");
    const acc = byNumber.get(num);
    set(i, { account_prefix: num, ...(acc && !rows[i].label ? { label: acc.label } : {}) });
  }

  async function save() {
    const { lines, error: e } = toLines(rows);
    if (e) { setError(e); return; }
    setSaving(true);
    setError(null);
    try {
      onSaved(await api.put<Budget>(`/companies/${companyId}/budgets/${budget.id}/lines`, lines));
      setSaved(true);
      setDirty(false);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-3">
      {error && <Alert>{error}</Alert>}
      {saved && <Alert kind="success">Lignes enregistrées.</Alert>}
      <p className="text-sm text-muted-foreground">
        Choisissez le compte dans le {accounts?.source === "company" ? "plan comptable de l'entreprise" : "référentiel publié de l'exercice"} :
        son intitulé est repris automatiquement. Une rubrique regroupe plusieurs comptes, ou une ligne de gestion sans compte.
        Une ligne peut aussi porter un centre de coûts. Montant annuel, ou mensuel par mois de l&apos;exercice.
      </p>
      <datalist id="budget-accounts">
        {(accounts?.items ?? []).map((a) => <option key={a.account_number} value={`${a.account_number} ${a.label}`} />)}
      </datalist>
      {groups.map((g) => (
        <div key={g.rubric || "_"} className="overflow-x-auto rounded-lg border bg-card shadow-card">
          <button type="button" className="flex w-full items-center justify-between gap-2 border-b bg-muted/50 px-3 py-2 text-left text-sm font-semibold"
                  aria-expanded={!collapsed[g.rubric]} onClick={() => setCollapsed((c) => ({ ...c, [g.rubric]: !c[g.rubric] }))}>
            <span>{g.rubric || "Sans rubrique"} <span className="font-normal text-muted-foreground">({g.indexes.length} ligne{g.indexes.length > 1 ? "s" : ""})</span></span>
            <span className="text-xs font-normal text-muted-foreground">{collapsed[g.rubric] ? "Afficher" : "Réduire"}</span>
          </button>
          {!collapsed[g.rubric] && (
            <table className="w-full text-sm tabular-nums">
              <thead className="border-b bg-muted/30 text-left text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="px-2 py-2">Rubrique</th><th className="px-2 py-2">Compte</th><th className="px-2 py-2">Libellé</th>
                  <th className="px-2 py-2">Centre</th><th className="px-2 py-2">Prévision</th><th className="px-2 py-2">Saisie</th>
                  <th className="px-2 py-2 text-right">Montant(s)</th><th className="px-2 py-2 text-right">Total annuel</th><th className="px-2 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y">
                {g.indexes.map((i) => {
                  const r = rows[i];
                  const acc = r.account_prefix ? byNumber.get(r.account_prefix) : undefined;
                  const total = dirty ? undefined : serverTotal(r);
                  return (
                    <tr key={i} className="align-top">
                      <td className="px-2 py-2"><Input aria-label="Rubrique budgétaire" value={r.rubric} onChange={(e) => set(i, { rubric: e.target.value })} className="min-w-32" /></td>
                      <td className="px-2 py-2">
                        <Input aria-label="Compte" list="budget-accounts" value={r.account_prefix} placeholder="Numéro ou intitulé"
                               onChange={(e) => pickAccount(i, e.target.value)} className="w-36" />
                        {r.account_prefix && (acc
                          ? <p className="mt-1 max-w-48 text-[11px] text-muted-foreground">{acc.label} · classe {acc.account_class}{acc.parent ? ` · ${acc.parent}` : ""}</p>
                          : <p className="mt-1 text-[11px] text-destructive-strong">Compte hors du plan de référence ou du type de budget</p>)}
                      </td>
                      <td className="px-2 py-2"><Input aria-label="Libellé" value={r.label} placeholder={acc?.label ?? "Libellé"} onChange={(e) => set(i, { label: e.target.value })} className="min-w-40" /></td>
                      <td className="px-2 py-2">
                        <Select aria-label="Centre de coûts" value={r.cost_center_id} onChange={(e) => set(i, { cost_center_id: e.target.value })} className="min-w-32">
                          <option value="">—</option>
                          {centers.map((c) => <option key={c.id} value={c.id}>{c.code} — {c.name}</option>)}
                        </Select>
                      </td>
                      <td className="px-2 py-2">
                        <Select aria-label="Mode de prévision" value={r.forecast_mode} onChange={(e) => set(i, { forecast_mode: e.target.value as ForecastMode })} className="w-28">
                          {(Object.keys(FORECAST_MODE_LABELS) as ForecastMode[]).map((m) => <option key={m} value={m}>{FORECAST_MODE_LABELS[m]}</option>)}
                        </Select>
                      </td>
                      <td className="px-2 py-2">
                        <Select aria-label="Mode de saisie" value={r.monthly ? "m" : "a"} onChange={(e) => set(i, { monthly: e.target.value === "m" })} className="w-28">
                          <option value="a">Annuel</option><option value="m">Mensuel</option>
                        </Select>
                      </td>
                      <td className="px-2 py-2">
                        {r.monthly ? (
                          <div className="grid grid-cols-3 gap-1 sm:grid-cols-6">
                            {months.map((m, k) => (
                              <label key={k} className="text-[11px] text-muted-foreground">{m}
                                <Input value={r.months[k]} inputMode="decimal" className="h-8 text-right"
                                       onChange={(e) => set(i, { months: r.months.map((v, j) => (j === k ? e.target.value : v)) })} />
                              </label>
                            ))}
                          </div>
                        ) : (
                          <Input aria-label="Montant annuel" value={r.annual} inputMode="decimal" className="ml-auto w-36 text-right"
                                 onChange={(e) => set(i, { annual: e.target.value })} />
                        )}
                      </td>
                      <td className="px-2 py-2 text-right" title={total ? "Calculé par le serveur" : "Enregistrez pour obtenir le total"}>
                        {total ? formatAmount(total) : <span className="text-muted-foreground">—</span>}
                      </td>
                      <td className="px-2 py-2 text-right">
                        <Button variant="ghost" size="icon" aria-label="Supprimer la ligne" onClick={() => { setDirty(true); setRows((rs) => rs.filter((_, j) => j !== i)); }}>
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      ))}
      {dirty && <p className="text-xs text-muted-foreground">Modifications non enregistrées : les totaux sont recalculés par le serveur à l&apos;enregistrement.</p>}
      <div className="flex flex-wrap justify-between gap-2">
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => { setDirty(true); setRows((rs) => [...rs, blankRow(rs[rs.length - 1]?.rubric ?? "")]); }}>
            <Plus className="h-4 w-4" /> Ajouter une ligne
          </Button>
          <Button variant="outline" size="sm" onClick={() => { setDirty(true); setRows((rs) => [...rs, blankRow("Nouvelle rubrique")]); }}>
            <Plus className="h-4 w-4" /> Nouvelle rubrique
          </Button>
        </div>
        <Button size="sm" onClick={save} loading={saving}>Enregistrer les lignes</Button>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ prévision par hypothèses
function ProjectionForm({ companyId, budget, years, onDone }: {
  companyId: string; budget: Budget; years: FiscalYear[]; onDone: (b: Budget) => void;
}) {
  const sources = years.filter((y) => y.active_import_job_id);
  const [source, setSource] = useState(sources[0]?.id ?? "");
  const [items, setItems] = useState([{ prefix: "", label: "", rate: "0" }]);
  const [spread, setSpread] = useState<"annual" | "equal">("annual");
  const [replace, setReplace] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setError(null);
    for (const it of items) {
      if (!/^\d{1,20}$/.test(it.prefix) || !it.label.trim()) { setError("Chaque hypothèse demande une racine de compte et un libellé."); return; }
      if (!/^-?\d+([.,]\d{1,4})?$/.test(it.rate.trim())) { setError(`Taux invalide pour ${it.prefix}.`); return; }
    }
    setBusy(true);
    try {
      onDone(await api.post<Budget>(`/companies/${companyId}/budgets/${budget.id}/project`, {
        source_fiscal_year_id: source, spread, replace,
        items: items.map((it) => ({ prefix: it.prefix, label: it.label.trim(), rate_pct: it.rate.trim().replace(",", ".") })),
      }));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (sources.length === 0) return <Alert kind="info">Aucun exercice avec balance validée : la prévision par hypothèses part d&apos;un réalisé.</Alert>;
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Montant prévu = réalisé de la racine sur l&apos;exercice source × (1 + taux d&apos;évolution). Les taux sont vos hypothèses ;
        ils sont enregistrés avec le budget.
      </p>
      {error && <Alert>{error}</Alert>}
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Exercice source (réalisé)" htmlFor="p-src">
          <Select id="p-src" value={source} onChange={(e) => setSource(e.target.value)}>
            {sources.map((y) => <option key={y.id} value={y.id}>{y.label}</option>)}
          </Select>
        </Field>
        <Field label="Répartition" htmlFor="p-spread">
          <Select id="p-spread" value={spread} onChange={(e) => setSpread(e.target.value as "annual" | "equal")}>
            <option value="annual">Montant annuel</option><option value="equal">12 mensualités égales</option>
          </Select>
        </Field>
        <label className="flex items-end gap-2 pb-2 text-sm">
          <input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} className="h-4 w-4 accent-[hsl(var(--primary))]" />
          Remplacer les lignes existantes
        </label>
      </div>
      <Table>
        <THead><tr><TH>Racine</TH><TH>Libellé</TH><TH className="text-right">Taux d&apos;évolution (%)</TH><TH /></tr></THead>
        <TBody>
          {items.map((it, i) => (
            <TR key={i}>
              <TD><Input aria-label="Racine" value={it.prefix} className="w-24" onChange={(e) => setItems((xs) => xs.map((x, j) => (j === i ? { ...x, prefix: e.target.value.trim() } : x)))} /></TD>
              <TD><Input aria-label="Libellé" value={it.label} onChange={(e) => setItems((xs) => xs.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} /></TD>
              <TD><Input aria-label="Taux" value={it.rate} className="ml-auto w-28 text-right" inputMode="decimal" onChange={(e) => setItems((xs) => xs.map((x, j) => (j === i ? { ...x, rate: e.target.value } : x)))} /></TD>
              <TD className="text-right"><Button variant="ghost" size="icon" aria-label="Retirer" onClick={() => setItems((xs) => xs.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4" /></Button></TD>
            </TR>
          ))}
        </TBody>
      </Table>
      <div className="flex justify-between">
        <Button variant="outline" size="sm" onClick={() => setItems((xs) => [...xs, { prefix: "", label: "", rate: "0" }])}><Plus className="h-4 w-4" /> Hypothèse</Button>
        <Button size="sm" onClick={run} loading={busy} disabled={!items.length}>Calculer les lignes</Button>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ suivi
function TrackingView({ t, centers, months }: { t: Tracking; centers: CostCenter[]; months: string[] }) {
  const centerName = (id: string | null) => centers.find((c) => c.id === id)?.code ?? "";
  const [open, setOpen] = useState<number | null>(null);
  if (t.rows.length === 0) return <EmptyState title="Aucune ligne budgétée" description="Ajoutez des lignes dans l'onglet « Lignes »." />;
  return (
    <div className="space-y-3">
      {t.warnings.map((w) => <Alert key={w} kind="warning">{w}</Alert>)}
      <Table>
        <THead>
          <tr><TH>Ligne</TH><TH>Nature</TH><TH className="text-right">Budget</TH><TH className="text-right">Réalisé</TH>
              <TH className="text-right">Écart</TH><TH className="text-right">Réalisation</TH><TH>Appréciation</TH></tr>
        </THead>
        <TBody>
          {t.rows.map((r, i) => (
            <Fragment key={i}>
              <TR className={cn(r.actual_by_period && "cursor-pointer")} onClick={() => r.actual_by_period && setOpen(open === i ? null : i)}>
                <TD>
                  <span className="font-medium">{r.label}</span>
                  <span className="ml-2 text-xs text-muted-foreground">{r.account_prefix ?? ""}{r.cost_center_id ? ` · ${centerName(r.cost_center_id)}` : ""}</span>
                  {r.notes.map((n) => <p key={n} className="text-xs text-muted-foreground">{n}</p>)}
                </TD>
                <TD className="capitalize">{r.nature}</TD>
                <TD className="text-right">{formatAmount(r.budget)}</TD>
                <TD className="text-right">{r.actual === null ? <span className="text-muted-foreground">Indisponible</span> : formatAmount(r.actual)}</TD>
                <TD className="text-right font-medium">{formatAmount(r.variance)}</TD>
                <TD className="text-right">{formatPct(r.realization_pct)}</TD>
                <TD>
                  {r.favorable === true && <Badge tone="green">Favorable</Badge>}
                  {r.favorable === false && <Badge tone="red">Défavorable</Badge>}
                  {r.favorable === null && r.variance !== null && <Badge>Conforme</Badge>}
                </TD>
              </TR>
              {open === i && r.actual_by_period && (
                <tr className="bg-muted/40">
                  <td colSpan={7} className="px-4 py-3">
                    <div className="grid grid-cols-3 gap-2 text-xs sm:grid-cols-6 lg:grid-cols-12">
                      {months.map((m, k) => (
                        <div key={k} className="rounded border bg-card p-2">
                          <p className="text-muted-foreground">{m}</p>
                          <p>B : {formatAmount(r.budget_by_period[String(k + 1)] ?? "0")}</p>
                          <p>R : {formatAmount(r.actual_by_period?.[String(k + 1)] ?? "0")}</p>
                        </div>
                      ))}
                    </div>
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </TBody>
        <tfoot className="border-t-2 bg-muted/40 font-semibold">
          {(["produit", "charge", "solde"] as const).filter((k) => t.totals[k]).map((k) => (
            <tr key={k}>
              <td className="px-4 py-2" colSpan={2}>{k === "produit" ? "Total produits" : k === "charge" ? "Total charges" : "Solde (produits − charges)"}</td>
              <td className="px-4 py-2 text-right">{formatAmount(t.totals[k]!.budget)}</td>
              <td className="px-4 py-2 text-right">{formatAmount(t.totals[k]!.actual)}</td>
              <td className="px-4 py-2 text-right">{formatAmount(t.totals[k]!.variance)}</td>
              <td colSpan={2} />
            </tr>
          ))}
        </tfoot>
      </Table>
      <details className="text-xs text-muted-foreground">
        <summary className="cursor-pointer text-link">Conventions de calcul</summary>
        <ul className="mt-2 list-disc space-y-1 pl-5">{t.conventions.map((c) => <li key={c}>{c}</li>)}</ul>
      </details>
    </div>
  );
}

// ------------------------------------------------------------------ page
export default function BudgetPage() {
  const { companyId, budgetId } = useParams<{ companyId: string; budgetId: string }>();
  const router = useRouter();
  const base = `/companies/${companyId}`;
  const { data: company } = useApiResource<Company>(base);
  const { data: budget, error, loading, setData } = useApiResource<Budget>(`${base}/budgets/${budgetId}`);
  const { data: kinds } = useApiResource<BudgetKind[]>(`${base}/budget-kinds`);
  const { data: years } = useApiResource<FiscalYear[]>(`${base}/fiscal-years`);
  const { data: centers } = useApiResource<CostCenter[]>(`${base}/cost-centers`);
  const [tab, setTab] = useState<"tracking" | "lines" | "projection">("tracking");
  const [tracking, setTracking] = useState<Tracking | null>(null);
  const [trackError, setTrackError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const fy = useMemo(() => years?.find((y) => y.id === budget?.fiscal_year_id) ?? null, [years, budget]);
  const months = useMemo(() => monthLabels(fy), [fy]);

  useEffect(() => {
    if (tab !== "tracking" || !budget) return;
    setTrackError(null);
    api.get<Tracking>(`${base}/budgets/${budget.id}/tracking`).then(setTracking).catch((e) => setTrackError(errorMessage(e)));
  }, [tab, budget, base]);

  if (loading && !budget) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  if (!budget || !company) return <Loading />;

  const canWrite = company.my_permissions.includes("budget.write");
  const canApprove = company.my_permissions.includes("budget.approve");
  const draft = budget.status === "draft";

  async function act(action: string, method: "post" | "del" = "post") {
    setBusy(action);
    setActionError(null);
    try {
      if (method === "del") {
        await api.del(`${base}/budgets/${budget!.id}`);
        router.replace(`${base}/gestion?tab=budgets&fy=${budget!.fiscal_year_id}`);
        return;
      }
      const b = await api.post<Budget>(`${base}/budgets/${budget!.id}/${action}`);
      if (action === "new-version") { router.push(`${base}/gestion/budgets/${b.id}`); return; }
      setData({ ...budget!, ...b });
    } catch (e) {
      setActionError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  const tabs = [["tracking", "Suivi des écarts"], ["lines", draft && canWrite ? "Lignes" : "Lignes (lecture)"],
                ...(draft && canWrite ? [["projection", "Prévision par hypothèses"]] : [])] as [typeof tab, string][];

  return (
    <>
      <Link href={`${base}/gestion?tab=budgets&fy=${budget.fiscal_year_id}`}
            className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ChevronLeft className="h-4 w-4" /> Contrôle de gestion
      </Link>
      <PageHeader
        title={`${budget.name} — v${budget.version}`}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <Badge tone={budget.status === "approved" ? "green" : budget.status === "submitted" ? "blue" : "neutral"}>{BUDGET_STATUS_LABELS[budget.status]}</Badge>
            <span>{budget.scenario === "forecast" ? "Prévision" : "Budget"} · {kinds?.find((k) => k.key === budget.budget_kind)?.label ?? budget.budget_kind} · exercice {fy?.label ?? "…"} · {budget.currency}</span>
            {budget.approved_at && <span>· approuvé le {formatDate(budget.approved_at)}</span>}
          </span>
        }
        actions={
          <>
            {draft && canWrite && <Button size="sm" onClick={() => act("submit")} loading={busy === "submit"}><Send className="h-4 w-4" /> Soumettre</Button>}
            {budget.status === "submitted" && canApprove && (
              <>
                <Button size="sm" variant="outline" onClick={() => act("return")} loading={busy === "return"}><Undo2 className="h-4 w-4" /> Renvoyer</Button>
                <Button size="sm" onClick={() => act("approve")} loading={busy === "approve"}><Check className="h-4 w-4" /> Approuver</Button>
              </>
            )}
            {canWrite && <Button size="sm" variant="outline" onClick={() => act("new-version")} loading={busy === "new-version"}><CopyPlus className="h-4 w-4" /> Nouvelle version</Button>}
            {canApprove && (draft || budget.status === "approved") && <Button size="sm" variant="outline" onClick={() => act("archive")} loading={busy === "archive"}><Archive className="h-4 w-4" /> Archiver</Button>}
            {draft && canWrite && <Button size="sm" variant="destructive" onClick={() => setConfirmDelete(true)}><Trash2 className="h-4 w-4" /> Supprimer</Button>}
          </>
        }
      />
      {actionError && <Alert className="mb-4">{actionError}</Alert>}
      {budget.assumptions && "projection" in budget.assumptions && (
        <Alert kind="info" className="mb-4">Lignes établies par hypothèses à partir du réalisé de l&apos;exercice {String((budget.assumptions.projection as { source_fiscal_year?: string }).source_fiscal_year ?? "")}.</Alert>
      )}
      <div role="tablist" className="mb-4 flex gap-1 overflow-x-auto border-b">
        {tabs.map(([id, label]) => (
          <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}
                  className={cn("-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
                    tab === id ? "border-primary font-medium" : "border-transparent text-muted-foreground hover:text-foreground")}>{label}</button>
        ))}
      </div>
      {tab === "tracking" && (trackError ? <Alert>{trackError}</Alert> : tracking ? <TrackingView t={tracking} centers={centers ?? []} months={months} /> : <Loading />)}
      {tab === "lines" && draft && canWrite && (
        <BudgetImport companyId={companyId} budgetId={budget.id} onImported={(b) => setData({ ...budget, ...b })} />
      )}
      {tab === "lines" && (draft && canWrite ? (
        <LinesEditor key={`${budget.total_lines}-${budget.lines?.length ?? 0}`} companyId={companyId} budget={budget} centers={centers ?? []} months={months}
                     onSaved={(b) => setData({ ...budget, ...b })} />
      ) : (
        <Card>
          <CardHeader><CardTitle>Lignes du budget</CardTitle></CardHeader>
          <CardContent className="p-0">
            <Table>
              <THead><tr><TH>Libellé</TH><TH>Racine</TH><TH>Centre</TH><TH>Période</TH><TH className="text-right">Montant</TH></tr></THead>
              <TBody>
                {(budget.lines ?? []).map((l, i) => (
                  <TR key={i}><TD>{l.label}</TD><TD>{l.account_prefix ?? ""}</TD>
                    <TD>{centers?.find((c) => c.id === l.cost_center_id)?.code ?? ""}</TD>
                    <TD>{l.period === 0 ? "Annuel" : months[l.period - 1]}</TD><TD className="text-right">{formatAmount(l.amount)}</TD></TR>
                ))}
              </TBody>
            </Table>
          </CardContent>
        </Card>
      ))}
      {tab === "projection" && years && (
        <ProjectionForm companyId={companyId} budget={budget} years={years}
                        onDone={(b) => { setData({ ...budget, ...b }); setTab("lines"); }} />
      )}
      <Dialog open={confirmDelete} onClose={() => setConfirmDelete(false)} title="Supprimer ce budget ?"
              description="Le brouillon et toutes ses lignes seront supprimés.">
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => setConfirmDelete(false)}>Annuler</Button>
          <Button variant="destructive" onClick={() => act("delete", "del")} loading={busy === "delete"}>Supprimer</Button>
        </div>
      </Dialog>
    </>
  );
}


/** Import des lignes d'un brouillon depuis un fichier Excel ou CSV : contrôle d'abord (sans enregistrer), puis import. */
function BudgetImport({ companyId, budgetId, onImported }: { companyId: string; budgetId: string; onImported: (b: Budget) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [res, setRes] = useState<{ imported: boolean; lines: number; errors: string[]; total: string; sheet: string; budget?: Budget } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function send(dry: boolean) {
    if (!file) return;
    setBusy(true); setError(null);
    try {
      const form = new FormData(); form.append("file", file);
      const r = await api.upload<NonNullable<typeof res>>(`/companies/${companyId}/budgets/${budgetId}/lines/import?dry_run=${dry}`, form);
      setRes(r);
      if (r.imported && r.budget) onImported(r.budget);
    } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  return (
    <Card className="mb-4">
      <CardHeader><CardTitle>Importer les lignes (Excel ou CSV)</CardTitle></CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-muted-foreground">Colonnes : « compte » (racine) et/ou « centre » (code), « libellé », puis soit « période » (0 = annuel, 1 à 12) et « montant »,
          soit une colonne par mois de l&apos;exercice (« M1 » à « M12 ») et/ou « annuel ». L&apos;import remplace les lignes du brouillon.</p>
        <input type="file" accept=".xlsx,.xls,.csv" aria-label="Fichier de budget" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setRes(null); }} />
        <div className="flex gap-2">
          <Button size="sm" variant="outline" disabled={!file || busy} onClick={() => void send(true)}>Contrôler</Button>
          <Button size="sm" disabled={!file || busy || !res || res.imported || res.errors.length > 0} onClick={() => void send(false)}>Importer</Button>
        </div>
        {error && <Alert>{error}</Alert>}
        {res && (res.errors.length ? (
          <Alert kind="warning"><p className="font-medium">{res.errors.length} anomalie(s) : rien n&apos;est importé.</p>
            <ul className="mt-1 list-disc pl-5">{res.errors.slice(0, 20).map((x, i) => <li key={i}>{x}</li>)}</ul></Alert>
        ) : <Alert kind="success">{res.imported ? "Lignes importées" : "Contrôle réussi"} : {res.lines} ligne(s), total {formatAmount(res.total)} (feuille « {res.sheet} »).</Alert>)}
      </CardContent>
    </Card>
  );
}
