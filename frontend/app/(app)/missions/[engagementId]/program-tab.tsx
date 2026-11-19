"use client";

import { useState } from "react";
import Link from "next/link";
import { ListPlus, Pencil, Plus, Trash2 } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import {
  NATURE_LABELS, PROCEDURE_STATUS_LABELS, WORKPAPER_STATUS_LABELS, personName, type AuditProcedure, type Engagement,
  type EngagementRisk, type MethodologyItem, type ProcedureNature, type ProcedureStatus, type RiskScale, type WorkProgram,
} from "@/lib/types";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";

type PForm = { program_id: string; code: string; title: string; objective: string; nature: ProcedureNature; steps: string;
               assertion_codes: string[]; assigned_to: string; due_date: string; status: ProcedureStatus; na_reason: string; risk_ids: string[] };

export function ProgramTab({ e }: { e: Engagement }) {
  const base = `/engagements/${e.id}`;
  const { data, error, loading, reload } = useApiResource<WorkProgram[]>(`${base}/programs`);
  const { data: riskData } = useApiResource<{ risks: EngagementRisk[]; scale: RiskScale | null }>(`${base}/risks`);
  const { data: items } = useApiResource<MethodologyItem[]>(`${base}/methodology-items`);
  const caps = e.capabilities ?? [];
  const canPlan = caps.includes("plan");
  const canExecute = caps.includes("edit_procedures");
  const team = (e.members ?? []).filter((m) => ["partner", "manager", "in_charge", "staff"].includes(m.role));
  const templates = (items ?? []).filter((i) => i.item_type === "procedure_template");
  const assertions = (items ?? []).filter((i) => i.item_type === "assertion");
  const risks = riskData?.risks ?? [];

  const [err, setErr] = useState<string | null>(null);
  const [pgOpen, setPgOpen] = useState(false);
  const [pg, setPg] = useState({ code: "", title: "", objective: "" });
  const [proc, setProc] = useState<PForm | null>(null);
  const [procId, setProcId] = useState<string | null>(null);
  const [tplFor, setTplFor] = useState<string | null>(null);
  const [tplSel, setTplSel] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  async function run(fn: () => Promise<unknown>, after?: () => void) {
    setBusy(true);
    setErr(null);
    try { await fn(); after?.(); await reload(); } catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }

  function editProc(programId: string, p?: AuditProcedure) {
    setErr(null);
    setProcId(p?.id ?? null);
    setProc(p ? { program_id: p.program_id, code: p.code, title: p.title, objective: p.objective ?? "", nature: p.nature,
                  steps: p.steps.join("\n"), assertion_codes: p.assertion_codes, assigned_to: p.assigned_to ?? "",
                  due_date: p.due_date ?? "", status: p.status, na_reason: p.na_reason ?? "", risk_ids: p.risk_ids }
      : { program_id: programId, code: "", title: "", objective: "", nature: "detail_test", steps: "", assertion_codes: [],
          assigned_to: "", due_date: "", status: "not_started", na_reason: "", risk_ids: [] });
  }

  function saveProc(ev: React.FormEvent) {
    ev.preventDefault();
    if (!proc) return;
    const body = { ...proc, objective: proc.objective || null, steps: proc.steps.split("\n").map((s) => s.trim()).filter(Boolean),
                   assigned_to: proc.assigned_to || null, due_date: proc.due_date || null, na_reason: proc.na_reason || null };
    void run(() => (procId ? api.patch(`${base}/procedures/${procId}`, body) : api.post(`${base}/procedures`, body)), () => setProc(null));
  }

  if (loading && !data) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  return (
    <div className="space-y-4">
      {err && !proc && <Alert>{err}</Alert>}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">Chaque procédure est rattachée aux risques qu&apos;elle couvre ; un risque sans procédure bloque l&apos;émission.</p>
        {canPlan && <Button size="sm" onClick={() => setPgOpen(true)}><Plus className="h-4 w-4" /> Programme</Button>}
      </div>
      {data && data.length === 0 && <EmptyState title="Aucun programme de travail" description="Créez un programme (par cycle ou par domaine), puis ses procédures, à la main ou depuis les programmes types de la méthodologie." />}
      {data?.map((g) => (
        <Card key={g.id}>
          <CardHeader className="flex-row items-start justify-between gap-3">
            <div>
              <CardTitle>{g.code} — {g.title}</CardTitle>
              {g.objective && <CardDescription>{g.objective}</CardDescription>}
            </div>
            {canPlan && (
              <div className="flex flex-wrap gap-2">
                {templates.length > 0 && <Button size="sm" variant="outline" onClick={() => { setTplFor(g.id); setTplSel([]); }}><ListPlus className="h-4 w-4" /> Programmes types</Button>}
                <Button size="sm" variant="outline" onClick={() => editProc(g.id)}><Plus className="h-4 w-4" /> Procédure</Button>
                <Button size="icon" variant="ghost" aria-label={`Supprimer ${g.code}`} onClick={() => run(() => api.del(`${base}/programs/${g.id}`))}><Trash2 className="h-4 w-4" /></Button>
              </div>
            )}
          </CardHeader>
          <CardContent className="space-y-2">
            {g.procedures.length === 0 && <p className="text-sm text-muted-foreground">Aucune procédure.</p>}
            {g.procedures.map((p) => (
              <div key={p.id} className="rounded-md border p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="font-medium">{p.code} — {p.title} {p.origin === "template" && <Badge className="ml-1">Programme type</Badge>}{p.origin === "ai_suggestion" && <Badge tone="gold" className="ml-1">Suggestion IA</Badge>}</p>
                    <p className="text-xs text-muted-foreground">
                      {NATURE_LABELS[p.nature]} · {p.assigned_to ? personName(team.find((m) => m.user_id === p.assigned_to)?.user) : "Non affectée"}
                      {p.due_date && ` · échéance ${formatDate(p.due_date)}`} · risques : {p.risk_ids.length ? p.risk_ids.map((id) => risks.find((r) => r.id === id)?.code ?? "?").join(", ") : "aucun"}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge tone={p.status === "done" ? "green" : p.status === "in_progress" ? "blue" : "neutral"}>{PROCEDURE_STATUS_LABELS[p.status]}</Badge>
                    {(canPlan || canExecute) && <Button variant="ghost" size="icon" aria-label={`Modifier ${p.code}`} onClick={() => editProc(g.id, p)}><Pencil className="h-4 w-4" /></Button>}
                    {canPlan && <Button variant="ghost" size="icon" aria-label={`Supprimer ${p.code}`} onClick={() => run(() => api.del(`${base}/procedures/${p.id}`))}><Trash2 className="h-4 w-4" /></Button>}
                  </div>
                </div>
                {p.steps.length > 0 && <ol className="mt-2 list-decimal space-y-0.5 pl-5 text-sm">{p.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>}
                {p.status === "not_applicable" && p.na_reason && <p className="mt-1 text-xs text-muted-foreground">Non applicable : {p.na_reason}</p>}
                {p.workpapers.length > 0 && (
                  <p className="mt-2 text-xs">Feuilles : {p.workpapers.map((w) => (
                    <Link key={w.id} href={`/missions/${e.id}/feuilles/${w.id}`} className="mr-2 text-link hover:underline">{w.reference} ({WORKPAPER_STATUS_LABELS[w.status]})</Link>))}</p>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      ))}

      <Dialog open={pgOpen} onClose={() => setPgOpen(false)} title="Nouveau programme">
        <form className="space-y-3" onSubmit={(x) => { x.preventDefault(); void run(() => api.post(`${base}/programs`, { ...pg, objective: pg.objective || null }), () => { setPgOpen(false); setPg({ code: "", title: "", objective: "" }); }); }}>
          {err && <Alert>{err}</Alert>}
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Code" htmlFor="pg-code" required><Input id="pg-code" value={pg.code} onChange={(x) => setPg({ ...pg, code: x.target.value })} required /></Field>
            <div className="sm:col-span-2"><Field label="Intitulé" htmlFor="pg-title" required><Input id="pg-title" value={pg.title} onChange={(x) => setPg({ ...pg, title: x.target.value })} required /></Field></div>
          </div>
          <Field label="Objectif" htmlFor="pg-obj"><Input id="pg-obj" value={pg.objective} onChange={(x) => setPg({ ...pg, objective: x.target.value })} /></Field>
          <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => setPgOpen(false)}>Annuler</Button><Button type="submit" loading={busy}>Créer</Button></div>
        </form>
      </Dialog>

      <Dialog open={tplFor !== null} onClose={() => setTplFor(null)} title="Procédures depuis les programmes types" description="Les procédures sont copiées dans la mission ; vous pouvez ensuite les adapter.">
        <div className="space-y-3">
          {err && <Alert>{err}</Alert>}
          <div className="max-h-80 space-y-1 overflow-y-auto">
            {templates.map((t) => (
              <label key={t.code} className="flex items-start gap-2 text-sm">
                <input type="checkbox" className="mt-0.5 h-4 w-4" checked={tplSel.includes(t.code)}
                       onChange={(x) => setTplSel(x.target.checked ? [...tplSel, t.code] : tplSel.filter((c) => c !== t.code))} />
                <span><span className="font-medium">{t.code}</span> {t.label}</span>
              </label>
            ))}
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setTplFor(null)}>Annuler</Button>
            <Button loading={busy} disabled={!tplSel.length} onClick={() => run(() => api.post(`${base}/procedures/from-templates`, { program_id: tplFor, template_codes: tplSel }), () => setTplFor(null))}>Ajouter</Button>
          </div>
        </div>
      </Dialog>

      <Dialog open={proc !== null} onClose={() => setProc(null)} title={procId ? "Modifier la procédure" : "Nouvelle procédure"}>
        {proc && (
          <form onSubmit={saveProc} className="space-y-3">
            {err && <Alert>{err}</Alert>}
            {!canPlan && <Alert kind="info">Vous pouvez mettre à jour l&apos;avancement ; la conception de la procédure relève du chef de mission.</Alert>}
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Code" htmlFor="p-code" required><Input id="p-code" value={proc.code} disabled={!canPlan} onChange={(x) => setProc({ ...proc, code: x.target.value })} required /></Field>
              <div className="sm:col-span-2"><Field label="Intitulé" htmlFor="p-title" required><Input id="p-title" value={proc.title} disabled={!canPlan} onChange={(x) => setProc({ ...proc, title: x.target.value })} required /></Field></div>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Nature" htmlFor="p-nat">
                <Select id="p-nat" value={proc.nature} disabled={!canPlan} onChange={(x) => setProc({ ...proc, nature: x.target.value as ProcedureNature })}>
                  {Object.entries(NATURE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </Select>
              </Field>
              <Field label="Affectée à" htmlFor="p-ass">
                <Select id="p-ass" value={proc.assigned_to} disabled={!canPlan} onChange={(x) => setProc({ ...proc, assigned_to: x.target.value })}>
                  <option value="">—</option>{team.map((m) => <option key={m.user_id} value={m.user_id}>{personName(m.user)}</option>)}
                </Select>
              </Field>
              <Field label="Échéance" htmlFor="p-due"><Input id="p-due" type="date" value={proc.due_date} disabled={!canPlan} onChange={(x) => setProc({ ...proc, due_date: x.target.value })} /></Field>
            </div>
            <Field label="Objectif" htmlFor="p-obj"><Input id="p-obj" value={proc.objective} disabled={!canPlan} onChange={(x) => setProc({ ...proc, objective: x.target.value })} /></Field>
            <Field label="Étapes (une par ligne)" htmlFor="p-steps">
              <textarea id="p-steps" rows={4} value={proc.steps} disabled={!canPlan} onChange={(x) => setProc({ ...proc, steps: x.target.value })}
                        className="w-full rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground disabled:opacity-60" />
            </Field>
            {canPlan && risks.length > 0 && (
              <fieldset>
                <legend className="mb-1 text-sm font-medium">Risques couverts</legend>
                <div className="flex flex-wrap gap-3">
                  {risks.map((r) => (
                    <label key={r.id} className="flex items-center gap-1.5 text-sm">
                      <input type="checkbox" className="h-4 w-4" checked={proc.risk_ids.includes(r.id)}
                             onChange={(x) => setProc({ ...proc, risk_ids: x.target.checked ? [...proc.risk_ids, r.id] : proc.risk_ids.filter((i) => i !== r.id) })} />
                      {r.code}
                    </label>
                  ))}
                </div>
              </fieldset>
            )}
            {canPlan && assertions.length > 0 && (
              <fieldset>
                <legend className="mb-1 text-sm font-medium">Assertions</legend>
                <div className="flex flex-wrap gap-3">
                  {assertions.map((a) => (
                    <label key={a.code} className="flex items-center gap-1.5 text-sm">
                      <input type="checkbox" className="h-4 w-4" checked={proc.assertion_codes.includes(a.code)}
                             onChange={(x) => setProc({ ...proc, assertion_codes: x.target.checked ? [...proc.assertion_codes, a.code] : proc.assertion_codes.filter((c) => c !== a.code) })} />
                      {a.label}
                    </label>
                  ))}
                </div>
              </fieldset>
            )}
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Avancement" htmlFor="p-status">
                <Select id="p-status" value={proc.status} onChange={(x) => setProc({ ...proc, status: x.target.value as ProcedureStatus })}>
                  {Object.entries(PROCEDURE_STATUS_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </Select>
              </Field>
              {proc.status === "not_applicable" && (
                <Field label="Motif « non applicable »" htmlFor="p-na" required><Input id="p-na" value={proc.na_reason} onChange={(x) => setProc({ ...proc, na_reason: x.target.value })} /></Field>
              )}
            </div>
            <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => setProc(null)}>Annuler</Button><Button type="submit" loading={busy}>Enregistrer</Button></div>
          </form>
        )}
      </Dialog>
    </div>
  );
}
