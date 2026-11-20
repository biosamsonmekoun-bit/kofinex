"use client";

/** Plan de trésorerie prévisionnel (phase 4, docs/CONTROLE_GESTION.md § 12.5). Tous les totaux, soldes, écarts et taux
 *  viennent du serveur (Decimal) : l'écran ne fait que saisir des montants et afficher les chaînes reçues. */
import { useEffect, useMemo, useState } from "react";
import { Download, Plus, Trash2 } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import type { FiscalYear } from "@/lib/types";
import type {
  TreasuryBudgetOption, TreasuryMethod, TreasuryOpeningProposal, TreasuryPlan, TreasuryPlanDetail, TreasuryRolling,
  TreasuryRow, TreasuryScenario, TreasurySection, TreasuryView,
} from "@/lib/treasury-types";
import { cn, formatAmount, formatPct } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";

const STATUS = { draft: ["Brouillon", "neutral"], approved: ["Approuvé", "green"], archived: ["Archivé", "neutral"] } as const;
const METHODS: [TreasuryMethod, string][] = [["manual", "Saisie manuelle"], ["percent_of", "% d'une autre rubrique"],
  ["from_budget", "Budget décalé"]];
type Display = "forecast" | "actual" | "variance" | "rate";
const AMOUNT = /^\d{1,18}(\.\d{1,2})?$/;

interface Draft {
  key: string; parent_key: string | null; section: TreasurySection; code: string; label: string; order: number;
  prefixes: string; method: TreasuryMethod; base_key: string | null; rate: string; budget_id: string | null; delay_months: number;
}

function toDrafts(p: TreasuryPlanDetail): Draft[] {
  return p.rubrics.map((r) => ({
    key: r.id, parent_key: r.parent_id, section: r.section, code: r.code ?? "", label: r.label, order: r.order,
    prefixes: r.prefixes.join(", "), method: r.method, base_key: r.base_rubric_id, rate: r.rate ?? "", budget_id: r.budget_id,
    delay_months: r.delay_months,
  }));
}

const amt = (v: string | null | undefined) => (v === null || v === undefined ? "—" : formatAmount(v, { blankZero: true }) || "—");
const neg = (v: string | null | undefined) => !!v && v.startsWith("-");

export function TreasuryPlanTab({ cid, fy, canWrite, canApprove }: {
  cid: string; fy: FiscalYear; canWrite: boolean; canApprove: boolean;
}) {
  const base = `/companies/${cid}/fiscal-years/${fy.id}/treasury-plans`;
  const list = useApiResource<TreasuryPlan[]>(base);
  const [selected, setSelected] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  useEffect(() => {
    if (list.data && list.data.length && !list.data.some((p) => p.id === selected)) setSelected(list.data[0].id);
  }, [list.data, selected]);

  if (list.loading && !list.data) return <Loading />;
  if (list.error) return <Alert>{list.error}</Alert>;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-3xl text-sm text-muted-foreground">
          Encaissements (A) et décaissements (B) prévus par mois ; flux net = A − B ; le solde de fin d&apos;un mois est le solde
          de début du suivant. Le réalisé est lu sur les mouvements réels de trésorerie, affectés aux rubriques par le compte de
          contrepartie. La prévision initiale est figée à l&apos;approbation ; la prévision actualisée se saisit ensuite.
        </p>
        <div className="flex items-center gap-2">
          {list.data && list.data.length > 0 && (
            <Select aria-label="Plan" value={selected ?? ""} onChange={(e) => setSelected(e.target.value)}>
              {list.data.map((p) => <option key={p.id} value={p.id}>{p.name} · {STATUS[p.status][0]}</option>)}
            </Select>
          )}
          {canWrite && <Button size="sm" onClick={() => setCreating(true)}><Plus className="h-4 w-4" /> Nouveau plan</Button>}
        </div>
      </div>
      {list.data && list.data.length === 0 && (
        <EmptyState title="Aucun plan de trésorerie pour cet exercice"
                    description="Créez un plan : rubriques, comptes associés et montants mensuels prévus." />
      )}
      {selected && <PlanEditor key={selected} cid={cid} fyId={fy.id} planId={selected} canWrite={canWrite} canApprove={canApprove}
                               onChanged={list.reload} onDeleted={() => { setSelected(null); void list.reload(); }} />}
      <CreateDialog open={creating} base={base} onClose={() => setCreating(false)}
                    onCreated={(id) => { setCreating(false); setSelected(id); void list.reload(); }} />
    </div>
  );
}

function CreateDialog({ open, base, onClose, onCreated }: {
  open: boolean; base: string; onClose: () => void; onCreated: (id: string) => void;
}) {
  const [name, setName] = useState("");
  const [opening, setOpening] = useState("0");
  const [template, setTemplate] = useState(true);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function propose() {
    setMsg(null);
    try {
      const p = await api.get<TreasuryOpeningProposal>(`${base}/opening-proposal`);
      if (p.available && p.opening_balance !== undefined) setOpening(p.opening_balance);
      else setMsg(p.reason ?? "Solde comptable indisponible.");
    } catch (e) { setMsg(errorMessage(e)); }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!/^-?\d{1,18}(\.\d{1,2})?$/.test(opening.trim())) { setMsg("Solde initial : nombre à deux décimales au plus."); return; }
    setBusy(true);
    setMsg(null);
    try {
      const p = await api.post<TreasuryPlanDetail>(base, { name, opening_balance: opening.trim(), template });
      onCreated(p.id);
    } catch (err) { setMsg(errorMessage(err)); } finally { setBusy(false); }
  }

  return (
    <Dialog open={open} onClose={onClose} title="Nouveau plan de trésorerie">
      <form onSubmit={submit} className="space-y-3">
        <Field label="Nom" htmlFor="tp-name" required><Input id="tp-name" value={name} onChange={(e) => setName(e.target.value)} required /></Field>
        <Field label="Solde de trésorerie au début de l'exercice" htmlFor="tp-open"
               hint="Saisi, ou proposé d'après la comptabilité (à-nouveaux des comptes de trésorerie).">
          <div className="flex gap-2">
            <Input id="tp-open" value={opening} onChange={(e) => setOpening(e.target.value)} inputMode="decimal" />
            <Button type="button" variant="outline" size="sm" onClick={propose}>Proposer</Button>
          </div>
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={template} onChange={(e) => setTemplate(e.target.checked)} />
          Partir des rubriques proposées (modifiables, sans compte associé) [À VALIDER]
        </label>
        {msg && <Alert>{msg}</Alert>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>Annuler</Button>
          <Button type="submit" disabled={busy || !name.trim()}>Créer</Button>
        </div>
      </form>
    </Dialog>
  );
}

function PlanEditor({ cid, fyId, planId, canWrite, canApprove, onChanged, onDeleted }: {
  cid: string; fyId: string; planId: string; canWrite: boolean; canApprove: boolean; onChanged: () => void; onDeleted: () => void;
}) {
  const P = `/companies/${cid}/treasury-plans/${planId}`;
  const detail = useApiResource<TreasuryPlanDetail>(P);
  const [scenario, setScenario] = useState<TreasuryScenario | null>(null);
  const [asOf, setAsOf] = useState("");
  const plan = detail.data;
  const sc: TreasuryScenario = scenario ?? (plan && plan.status !== "draft" ? "updated" : "initial");
  const q = new URLSearchParams({ scenario: sc, ...(asOf ? { as_of: asOf } : {}) }).toString();
  const view = useApiResource<TreasuryView>(plan ? `${P}/view?${q}` : null);
  const rolling = useApiResource<TreasuryRolling>(plan ? `${P}/rolling${asOf ? `?as_of=${asOf}` : ""}` : null);
  const budgets = useApiResource<TreasuryBudgetOption[]>(`/companies/${cid}/fiscal-years/${fyId}/treasury-plans/budgets`);
  const [msg, setMsg] = useState<string | null>(null);

  async function act(fn: () => Promise<unknown>) {
    setMsg(null);
    try {
      await fn();
      await detail.reload();
      void view.reload();
      void rolling.reload();
      onChanged();
    } catch (e) { setMsg(errorMessage(e)); }
  }

  if (detail.loading && !plan) return <Loading />;
  if (detail.error || !plan) return <Alert>{detail.error ?? "Plan introuvable"}</Alert>;
  const draft = plan.status === "draft";
  const editable = canWrite && ((sc === "initial" && draft) || (sc === "updated" && plan.status === "approved"));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={STATUS[plan.status][1]}>{STATUS[plan.status][0]}</Badge>
        <span className="text-sm text-muted-foreground">Solde initial {formatAmount(plan.opening_balance)} {plan.currency}</span>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Select aria-label="Prévision" value={sc} onChange={(e) => setScenario(e.target.value as TreasuryScenario)}>
            <option value="initial">Prévision initiale</option>
            <option value="updated" disabled={draft}>Prévision actualisée</option>
          </Select>
          <Input aria-label="Réalisé arrêté au" type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} className="w-40" />
          {(["xlsx", "pdf"] as const).map((f) => (
            <Button key={f} variant="outline" size="sm"
                    onClick={() => act(() => api.download(`${P}/export?format=${f}&scenario=${sc}`, `plan-tresorerie.${f}`))}>
              <Download className="h-4 w-4" /> {f === "xlsx" ? "Excel" : "PDF"}
            </Button>
          ))}
          {canApprove && draft && <Button size="sm" onClick={() => act(() => api.post(`${P}/approve`))}>Approuver</Button>}
          {canApprove && plan.status !== "archived" &&
            <Button size="sm" variant="outline" onClick={() => act(() => api.post(`${P}/archive`))}>Archiver</Button>}
          {canWrite && draft && (
            <Button size="sm" variant="ghost" aria-label="Supprimer le plan"
                    onClick={async () => { try { await api.del(P); onDeleted(); } catch (e) { setMsg(errorMessage(e)); } }}>
              <Trash2 className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>
      {msg && <Alert>{msg}</Alert>}
      {canWrite && draft && <Settings plan={plan} onSave={(body) => act(() => api.patch(P, body))} />}
      {canWrite && draft && (
        <Structure plan={plan} budgets={budgets.data ?? []} onSave={(rubrics) => act(() => api.put(`${P}/rubrics`, { rubrics }))} />
      )}
      {view.error && <Alert>{view.error}</Alert>}
      {view.data && (
        <Grid plan={plan} view={view.data} scenario={sc} editable={editable}
              onSave={(amounts) => act(() => api.put(`${P}/amounts`, { scenario: sc, amounts }))}
              onCalculate={(rid) => act(() => api.post(`${P}/rubrics/${rid}/calculate?scenario=${sc}`))} />
      )}
      {rolling.data && <Rolling data={rolling.data} currency={plan.currency} />}
    </div>
  );
}

function Settings({ plan, onSave }: { plan: TreasuryPlanDetail; onSave: (b: Record<string, string>) => void }) {
  const [name, setName] = useState(plan.name);
  const [opening, setOpening] = useState(plan.opening_balance);
  const [notes, setNotes] = useState(plan.notes ?? "");
  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Paramètres</CardTitle></CardHeader>
      <CardContent className="grid gap-3 sm:grid-cols-4">
        <Field label="Nom" htmlFor="tps-name"><Input id="tps-name" value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Solde initial" htmlFor="tps-open">
          <Input id="tps-open" value={opening} onChange={(e) => setOpening(e.target.value)} inputMode="decimal" />
        </Field>
        <Field label="Notes" htmlFor="tps-notes"><Input id="tps-notes" value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
        <div className="flex items-end">
          <Button size="sm" onClick={() => onSave({ name, opening_balance: opening.trim(), notes })}>Enregistrer</Button>
        </div>
      </CardContent>
    </Card>
  );
}

function Structure({ plan, budgets, onSave }: {
  plan: TreasuryPlanDetail; budgets: TreasuryBudgetOption[]; onSave: (r: unknown[]) => void;
}) {
  const [rows, setRows] = useState<Draft[]>(() => toDrafts(plan));
  const [err, setErr] = useState<string | null>(null);
  const set = (k: string, patch: Partial<Draft>) => setRows((rs) => rs.map((r) => (r.key === k ? { ...r, ...patch } : r)));

  function add(section: TreasurySection) {
    const key = `new-${crypto.randomUUID()}`;
    setRows((rs) => [...rs, { key, parent_key: null, section, code: "", label: "Nouvelle rubrique", order: rs.length, prefixes: "",
      method: "manual", base_key: null, rate: "", budget_id: null, delay_months: 0 }]);
  }

  function save() {
    const bad = rows.find((r) => r.method === "percent_of" && (!r.base_key || !/^\d{1,5}(\.\d{1,4})?$/.test(r.rate)))
      ?? rows.find((r) => r.method === "from_budget" && !r.budget_id);
    if (bad) { setErr(`Rubrique « ${bad.label} » : modalité incomplète (rubrique de base et taux, ou budget).`); return; }
    setErr(null);
    onSave(rows.map((r) => ({
      key: r.key, parent_key: r.parent_key, section: r.section, code: r.code.trim() || null, label: r.label.trim(), order: r.order,
      prefixes: r.prefixes.split(/[,\s]+/).filter(Boolean), method: r.method, base_key: r.method === "percent_of" ? r.base_key : null,
      rate: r.method === "percent_of" ? r.rate : null, budget_id: r.method === "from_budget" ? r.budget_id : null,
      delay_months: r.delay_months,
    })));
  }

  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Rubriques et comptes associés</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground">
          Comptes associés : racines de comptes (ex. 411, 401, 66) qui affectent le réalisé à la rubrique. Taux et délais sont saisis
          par l&apos;utilisateur ; aucun n&apos;est imposé par le logiciel.
        </p>
        {(["receipts", "disbursements"] as const).map((section) => (
          <div key={section} className="space-y-2">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-medium">{section === "receipts" ? "A. Encaissements" : "B. Décaissements"}</h4>
              <Button size="sm" variant="outline" onClick={() => add(section)}><Plus className="h-4 w-4" /> Rubrique</Button>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="text-muted-foreground">
                  <tr className="text-left">
                    <th className="p-1">Rubrique mère</th><th className="p-1">Compte</th><th className="p-1">Intitulé</th>
                    <th className="p-1">Comptes associés</th><th className="p-1">Modalité</th><th className="p-1">Paramètres</th><th />
                  </tr>
                </thead>
                <tbody>
                  {rows.filter((r) => r.section === section).map((r) => (
                    <tr key={r.key} className="border-t">
                      <td className="p-1">
                        <Select value={r.parent_key ?? ""} onChange={(e) => set(r.key, { parent_key: e.target.value || null })}>
                          <option value="">—</option>
                          {rows.filter((x) => x.section === section && !x.parent_key && x.key !== r.key)
                            .map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}
                        </Select>
                      </td>
                      <td className="p-1"><Input className="w-20" value={r.code} onChange={(e) => set(r.key, { code: e.target.value })} /></td>
                      <td className="p-1"><Input value={r.label} onChange={(e) => set(r.key, { label: e.target.value })} /></td>
                      <td className="p-1"><Input className="w-32" value={r.prefixes} onChange={(e) => set(r.key, { prefixes: e.target.value })} /></td>
                      <td className="p-1">
                        <Select value={r.method} onChange={(e) => set(r.key, { method: e.target.value as TreasuryMethod })}>
                          {METHODS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                        </Select>
                      </td>
                      <td className="p-1">
                        {r.method === "percent_of" && (
                          <div className="flex gap-1">
                            <Select value={r.base_key ?? ""} onChange={(e) => set(r.key, { base_key: e.target.value || null })}>
                              <option value="">Base…</option>
                              {rows.filter((x) => x.key !== r.key).map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}
                            </Select>
                            <Input className="w-20" placeholder="%" value={r.rate} onChange={(e) => set(r.key, { rate: e.target.value })} />
                          </div>
                        )}
                        {r.method === "from_budget" && (
                          <div className="flex gap-1">
                            <Select value={r.budget_id ?? ""} onChange={(e) => set(r.key, { budget_id: e.target.value || null })}>
                              <option value="">Budget…</option>
                              {budgets.map((b) => <option key={b.id} value={b.id}>{b.name} v{b.version}</option>)}
                            </Select>
                            <Input className="w-16" type="number" min={0} max={12} aria-label="Délai (mois)" value={r.delay_months}
                                   onChange={(e) => set(r.key, { delay_months: Number.parseInt(e.target.value || "0", 10) })} />
                          </div>
                        )}
                      </td>
                      <td className="p-1">
                        <Button size="icon" variant="ghost" aria-label="Retirer"
                                onClick={() => setRows((rs) => rs.filter((x) => x.key !== r.key && x.parent_key !== r.key))}>
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
        {err && <Alert>{err}</Alert>}
        <div className="flex justify-end"><Button size="sm" onClick={save}>Enregistrer la structure</Button></div>
      </CardContent>
    </Card>
  );
}

function Grid({ plan, view, scenario, editable, onSave, onCalculate }: {
  plan: TreasuryPlanDetail; view: TreasuryView; scenario: TreasuryScenario; editable: boolean;
  onSave: (a: { rubric_id: string; period: number; amount: string }[]) => void; onCalculate: (rid: string) => void;
}) {
  const initial = useMemo(() => {
    const src = plan.amounts[scenario] ?? {};
    const out: Record<string, string[]> = {};
    for (const r of view.rows) out[r.id] = (src[r.id] ?? Array(12).fill("0")).map((v) => (/^0+(\.0+)?$/.test(v) ? "" : v));
    return out;
  }, [plan, scenario, view.rows]);
  const [cells, setCells] = useState(initial);
  useEffect(() => setCells(initial), [initial]);
  const [display, setDisplay] = useState<Display>("forecast");
  const [err, setErr] = useState<string | null>(null);
  const methods = new Map(plan.rubrics.map((r) => [r.id, r.method]));
  const dirty = JSON.stringify(cells) !== JSON.stringify(initial);

  function save() {
    const out: { rubric_id: string; period: number; amount: string }[] = [];
    for (const r of view.rows) {
      if (r.has_children) continue;
      for (let i = 0; i < 12; i++) {
        const v = (cells[r.id]?.[i] ?? "").trim().replace(/\s/g, "").replace(",", ".");
        if (!v) continue;
        if (!AMOUNT.test(v)) { setErr(`« ${r.label} », ${view.months[i]} : montant positif à deux décimales au plus.`); return; }
        out.push({ rubric_id: r.id, period: i + 1, amount: v });
      }
    }
    setErr(null);
    onSave(out);
  }

  function cell(r: TreasuryRow, i: number) {
    if (display === "forecast") {
      if (editable && !r.has_children) {
        return <Input className="h-7 w-24 px-1 text-right text-xs" aria-label={`${r.label} ${view.months[i]}`} value={cells[r.id]?.[i] ?? ""}
                      onChange={(e) => setCells((c) => ({ ...c, [r.id]: (c[r.id] ?? []).map((x, j) => (j === i ? e.target.value : x)) }))} />;
      }
      return amt(r.months[i]);
    }
    const v = r.variance[i];
    if (display === "actual") return amt(r.actual[i]);
    if (display === "variance") return <span className={cn(neg(v.variance) && "text-destructive")}>{amt(v.variance)}</span>;
    return v.rate === null ? "—" : formatPct(v.rate);
  }

  const totalLine = (label: string, values: (string | null)[], total?: string | null, strong = false) => (
    <tr className={cn("border-t", strong && "font-medium")}>
      <td className="sticky left-0 bg-card p-1" colSpan={2}>{label}</td>
      {values.map((v, i) => <td key={i} className={cn("p-1 text-right tabular-nums", neg(v) && "text-destructive")}>{amt(v)}</td>)}
      <td className="p-1 text-right tabular-nums">{total === undefined ? "" : amt(total)}</td>
    </tr>
  );
  const t = view.totals;
  const a = view.actual;
  const forecastMode = display === "forecast";

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="text-base">Plan mensuel · {plan.currency}</CardTitle>
        <div role="tablist" className="flex gap-1">
          {([["forecast", "Prévision"], ["actual", "Réalisé"], ["variance", "Écart"], ["rate", "Taux de réalisation"]] as [Display, string][])
            .map(([k, l]) => (
              <button key={k} role="tab" aria-selected={display === k} onClick={() => setDisplay(k)}
                      className={cn("rounded-md px-2 py-1 text-xs", display === k ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted")}>
                {l}
              </button>
            ))}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {view.negative_months.length > 0 && (
          <Alert kind="warning">
            Solde négatif prévu en {view.negative_months.map((m) => view.months[m - 1]).join(", ")} ; besoin de financement :{" "}
            {formatAmount(view.financing_need)} {plan.currency}.
          </Alert>
        )}
        {!forecastMode && (
          <p className="text-xs text-muted-foreground">
            Réalisé {a.source ? `(source : ${a.source})` : "indisponible"} jusqu&apos;au mois de {view.as_of} inclus ({view.closed_months} mois).
            {!a.check && " Contrôle encaissements − décaissements = variation de trésorerie non vérifié : voir les notes de la source."}
            {a.source_notes.map((n) => ` ${n}`)}
          </p>
        )}
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1100px] text-xs">
            <thead className="text-muted-foreground">
              <tr>
                <th className="sticky left-0 bg-card p-1 text-left">Comptes</th><th className="p-1 text-left">Intitulés</th>
                {view.months.map((m) => <th key={m} className="p-1 text-right">{m}</th>)}
                <th className="p-1 text-right">Total</th>
              </tr>
            </thead>
            <tbody>
              {(["receipts", "disbursements"] as const).map((s) => (
                <SectionRows key={s} title={s === "receipts" ? "A. ENCAISSEMENTS" : "B. DÉCAISSEMENTS"}>
                  {view.rows.filter((r) => r.section === s).map((r) => (
                    <tr key={r.id} className="border-t">
                      <td className="sticky left-0 bg-card p-1 text-muted-foreground">{r.code}</td>
                      <td className={cn("p-1", r.level ? "pl-5" : "font-medium")}>
                        {r.label}
                        {editable && forecastMode && methods.get(r.id) !== "manual" && (
                          <Button size="sm" variant="link" className="h-auto px-1 text-xs" onClick={() => onCalculate(r.id)}>calculer</Button>
                        )}
                      </td>
                      {Array.from({ length: 12 }, (_, i) => <td key={i} className="p-1 text-right tabular-nums">{cell(r, i)}</td>)}
                      <td className="p-1 text-right tabular-nums">{forecastMode ? amt(r.total) : display === "actual" ? amt(r.actual_total) : ""}</td>
                    </tr>
                  ))}
                  {forecastMode
                    ? totalLine(`Total ${s === "receipts" ? "A" : "B"}`, t[s], t.annual[s], true)
                    : totalLine(`Total ${s === "receipts" ? "A" : "B"} réalisé`, a[s], undefined, true)}
                  {!forecastMode && totalLine("dont non affecté", a.unassigned[s])}
                </SectionRows>
              ))}
              {forecastMode ? (
                <>
                  {totalLine("Solde au début du mois", t.opening)}
                  {totalLine("Flux net (A − B)", t.net, t.annual.net, true)}
                  {totalLine("Solde à la fin du mois", t.closing, undefined, true)}
                </>
              ) : totalLine("Flux net réalisé (A − B)", a.net, undefined, true)}
            </tbody>
          </table>
        </div>
        {err && <Alert>{err}</Alert>}
        {editable && forecastMode && (
          <div className="flex items-center justify-end gap-2">
            {dirty && <span className="text-xs text-muted-foreground">Modifications non enregistrées : totaux recalculés à l&apos;enregistrement.</span>}
            <Button size="sm" disabled={!dirty} onClick={save}>Enregistrer les montants</Button>
          </div>
        )}
        <ul className="list-disc space-y-0.5 pl-4 text-xs text-muted-foreground">{view.conventions.map((c) => <li key={c}>{c}</li>)}</ul>
      </CardContent>
    </Card>
  );
}

function SectionRows({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <>
      <tr className="border-t bg-muted/50"><td className="sticky left-0 bg-muted/50 p-1 font-semibold" colSpan={15}>{title}</td></tr>
      {children}
    </>
  );
}

function Rolling({ data, currency }: { data: TreasuryRolling; currency: string }) {
  const BASIS = { actual: "Réalisé", forecast: "Prévision", none: "—" } as const;
  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Prévision glissante sur douze mois · {currency}</CardTitle></CardHeader>
      <CardContent className="space-y-2">
        <p className="text-xs text-muted-foreground">Solde de départ : {formatAmount(data.start_opening)} {currency}. {data.notes.join(" ")}</p>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-xs">
            <thead className="text-muted-foreground">
              <tr><th className="p-1 text-left" />{data.labels.map((l) => <th key={l} className="p-1 text-right">{l}</th>)}</tr>
            </thead>
            <tbody>
              <tr className="border-t"><td className="p-1">Base</td>{data.months.map((m, i) => <td key={i} className="p-1 text-right">{BASIS[m.basis]}</td>)}</tr>
              {(["net", "closing"] as const).map((k) => (
                <tr key={k} className="border-t">
                  <td className="p-1">{k === "net" ? "Flux net" : "Solde de fin"}</td>
                  {data.months.map((m, i) => <td key={i} className={cn("p-1 text-right tabular-nums", neg(m[k]) && "text-destructive")}>{amt(m[k])}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
