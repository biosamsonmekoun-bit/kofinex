"use client";

import { useState } from "react";
import { CheckCircle2, Plus, Trash2 } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { personName, type Engagement } from "@/lib/types";
import { toDecimal, type FaMateriality, type StatementLine } from "@/lib/fa-types";
import { formatAmount, formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";

const AREA = "w-full rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30";
const STATUS = { draft: ["Brouillon", "neutral"], approved: ["Approuvée", "green"], superseded: ["Remplacée", "amber"] } as const;
const EMPTY = { benchmark_label: "", benchmark_source: "statement_line" as "statement_line" | "manual", benchmark_line_code: "",
                benchmark_amount: "", overall_pct: "", performance_pct: "", trivial_pct: "", basis: "" };

export function FaMaterialityPanel({ e, onChanged }: { e: Engagement; onChanged: () => void }) {
  const base = `/engagements/${e.id}/fa`;
  const { data, error, loading, reload } = useApiResource<{ versions: FaMateriality[]; methodology_parameters: { code: string; label: string; content: Record<string, unknown> }[] }>(`${base}/materiality`);
  const { data: lines, error: linesError } = useApiResource<StatementLine[]>(`${base}/materiality/benchmarks`);
  const caps = e.capabilities ?? [];
  const [form, setForm] = useState<typeof EMPTY | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function act(key: string, fn: () => Promise<unknown>) {
    setBusy(key); setErr(null);
    try { await fn(); await reload(); onChanged(); return true; } catch (x) { setErr(errorMessage(x)); return false; } finally { setBusy(null); }
  }

  async function save(ev: React.FormEvent) {
    ev.preventDefault();
    if (!form) return;
    let amount: string | null = null;
    try { amount = form.benchmark_source === "manual" ? toDecimal(form.benchmark_amount) : null; } catch (x) { setErr((x as Error).message); return; }
    const pct = (v: string) => v.replace(",", ".").trim();
    const ok = await act("save", () => api.post(`${base}/materiality`, {
      ...form, benchmark_line_code: form.benchmark_source === "statement_line" ? form.benchmark_line_code : null, benchmark_amount: amount,
      overall_pct: pct(form.overall_pct), performance_pct: pct(form.performance_pct), trivial_pct: pct(form.trivial_pct) }));
    if (ok) setForm(null);
  }

  if (loading && !data) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  const selectable = (lines ?? []).filter((l) => l.net !== null && l.net !== "0");
  const chosen = selectable.find((l) => l.code === form?.benchmark_line_code);
  return (
    <div className="space-y-4">
      {err && !form && <Alert>{err}</Alert>}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-2xl text-sm text-muted-foreground">
          Seuil de signification = référence × pourcentage ; seuil de planification et seuil des anomalies insignifiantes en % du seuil de signification.
          Les pourcentages sont votre jugement (ou ceux de votre méthodologie) : KOFINEX n&apos;en propose aucun. Une version approuvée est figée ;
          pour réviser les seuils, créez une nouvelle version.
        </p>
        {caps.includes("plan") && <Button size="sm" onClick={() => { setErr(null); setForm(EMPTY); }}><Plus className="h-4 w-4" /> Nouvelle version</Button>}
      </div>
      {data && data.versions.length === 0 && <EmptyState title="Aucun seuil" description="Déterminez les seuils de la mission avant la revue des comptes et l'évaluation des anomalies." />}
      {data?.versions.map((m) => (
        <Card key={m.id}>
          <CardHeader className="flex-row items-start justify-between gap-3">
            <div>
              <CardTitle>Version {m.version} <Badge tone={STATUS[m.status][1]} className="ml-1">{STATUS[m.status][0]}</Badge></CardTitle>
              <CardDescription>
                {m.benchmark_label} : {formatAmount(m.benchmark_amount)}{m.benchmark_source === "statement_line" && ` (ligne ${m.benchmark_line_code} des états, balance validée)`}
                {m.approved_at && ` · approuvée le ${formatDate(m.approved_at)} par ${personName(m.approved_by_user)}`}
              </CardDescription>
            </div>
            {m.status === "draft" && (
              <div className="flex gap-2">
                {caps.includes("approve_materiality") && <Button size="sm" loading={busy === m.id} onClick={() => act(m.id, () => api.post(`${base}/materiality/${m.id}/approve`, {}))}><CheckCircle2 className="h-4 w-4" /> Approuver</Button>}
                {caps.includes("plan") && <Button size="icon" variant="ghost" aria-label="Supprimer le brouillon" onClick={() => act("del", () => api.del(`${base}/materiality/${m.id}`))}><Trash2 className="h-4 w-4" /></Button>}
              </div>
            )}
          </CardHeader>
          <CardContent>
            <dl className="grid gap-3 text-sm sm:grid-cols-3">
              <div><dt className="text-muted-foreground">Seuil de signification ({m.overall_pct.replace(".", ",")} %)</dt><dd className="text-lg font-semibold tabular-nums">{formatAmount(m.overall_amount)}</dd></div>
              <div><dt className="text-muted-foreground">Seuil de planification ({m.performance_pct.replace(".", ",")} %)</dt><dd className="text-lg font-semibold tabular-nums">{formatAmount(m.performance_amount)}</dd></div>
              <div><dt className="text-muted-foreground">Anomalies insignifiantes ({m.trivial_pct.replace(".", ",")} %)</dt><dd className="text-lg font-semibold tabular-nums">{formatAmount(m.trivial_amount)}</dd></div>
            </dl>
            <p className="mt-3 whitespace-pre-wrap text-sm"><span className="text-muted-foreground">Justification : </span>{m.basis}</p>
          </CardContent>
        </Card>
      ))}

      <Dialog open={form !== null} onClose={() => setForm(null)} title="Nouvelle version des seuils">
        {form && (
          <form onSubmit={save} className="space-y-3">
            {err && <Alert>{err}</Alert>}
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Origine de la référence" htmlFor="m-src">
                <Select id="m-src" value={form.benchmark_source} onChange={(x) => setForm({ ...form, benchmark_source: x.target.value as "manual" })}>
                  <option value="statement_line">Ligne des états de l&apos;exercice</option><option value="manual">Montant saisi</option>
                </Select>
              </Field>
              <Field label="Libellé de la référence" htmlFor="m-lbl" required><Input id="m-lbl" required value={form.benchmark_label} onChange={(x) => setForm({ ...form, benchmark_label: x.target.value })} /></Field>
            </div>
            {form.benchmark_source === "statement_line" ? (
              <Field label="Ligne des états" htmlFor="m-line" required>
                <Select id="m-line" value={form.benchmark_line_code} onChange={(x) => {
                  const l = selectable.find((y) => y.code === x.target.value);
                  setForm({ ...form, benchmark_line_code: x.target.value, benchmark_label: form.benchmark_label || l?.label || "" });
                }}>
                  <option value="">Choisir…</option>
                  {selectable.map((l) => <option key={`${l.statement_type}-${l.code}`} value={l.code}>{l.code} — {l.label} ({formatAmount(l.net)})</option>)}
                </Select>
                {linesError && <p className="mt-1 text-xs text-destructive">{linesError}</p>}
                {lines && !selectable.length && <p className="mt-1 text-xs text-muted-foreground">États indisponibles (balance validée et référentiel publié requis) : saisissez le montant.</p>}
                {chosen && <p className="mt-1 text-xs text-muted-foreground">Valeur retenue : {formatAmount(chosen.net!.replace("-", ""))} (valeur absolue).</p>}
              </Field>
            ) : (
              <Field label="Montant de référence" htmlFor="m-amt" required><Input id="m-amt" inputMode="decimal" value={form.benchmark_amount} onChange={(x) => setForm({ ...form, benchmark_amount: x.target.value })} /></Field>
            )}
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Seuil de signification (% de la référence)" htmlFor="m-o" required><Input id="m-o" inputMode="decimal" required value={form.overall_pct} onChange={(x) => setForm({ ...form, overall_pct: x.target.value })} /></Field>
              <Field label="Planification (% du seuil)" htmlFor="m-p" required><Input id="m-p" inputMode="decimal" required value={form.performance_pct} onChange={(x) => setForm({ ...form, performance_pct: x.target.value })} /></Field>
              <Field label="Insignifiantes (% du seuil)" htmlFor="m-t" required><Input id="m-t" inputMode="decimal" required value={form.trivial_pct} onChange={(x) => setForm({ ...form, trivial_pct: x.target.value })} /></Field>
            </div>
            {data && data.methodology_parameters.length > 0 && (
              <div className="rounded-md border bg-muted/40 p-3 text-xs">
                <p className="mb-1 font-medium">Paramètres de la méthodologie de la mission</p>
                <ul className="space-y-0.5">{data.methodology_parameters.map((p) => <li key={p.code}><strong>{p.code}</strong> {p.label} <code>{JSON.stringify(p.content)}</code></li>)}</ul>
              </div>
            )}
            <Field label="Justification (choix de la référence et des pourcentages, source)" htmlFor="m-b" required>
              <textarea id="m-b" rows={3} className={AREA} required minLength={10} value={form.basis} onChange={(x) => setForm({ ...form, basis: x.target.value })} />
            </Field>
            <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => setForm(null)}>Annuler</Button><Button type="submit" loading={busy === "save"}>Calculer et enregistrer</Button></div>
          </form>
        )}
      </Dialog>
    </div>
  );
}
