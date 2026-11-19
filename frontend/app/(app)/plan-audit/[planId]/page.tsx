"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { CheckCircle2, ChevronLeft, History, Lock, Pencil, Plus, Trash2 } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { personName, type Company, type Engagement } from "@/lib/types";
import { FIELD_LABELS, ITEM_STATUS, PLAN_STATUS, type AuditPlan, type PlanHistory, type PlanItem, type PlanItemStatus } from "@/lib/ia-types";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading, PageHeader } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const AREA = "w-full rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30";
type ItemForm = { company_id: string; process_id: string; title: string; rationale: string; priority_rank: string; planned_start: string;
                  planned_end: string; budget_days: string; change_reason: string };
const EMPTY: ItemForm = { company_id: "", process_id: "", title: "", rationale: "", priority_rank: "", planned_start: "", planned_end: "",
                          budget_days: "", change_reason: "" };

function ItemDialog({ plan, item, onClose, onSaved }: { plan: AuditPlan; item: PlanItem | null; onClose: () => void; onSaved: (p: AuditPlan) => void }) {
  const { data: companies } = useApiResource<Company[]>(`/organizations/${plan.organization_id}/companies`);
  const [f, setF] = useState<ItemForm>(item ? { company_id: item.company_id, process_id: item.process_id ?? "", title: item.title,
    rationale: item.rationale, priority_rank: item.priority_rank ? String(item.priority_rank) : "", planned_start: item.planned_start ?? "",
    planned_end: item.planned_end ?? "", budget_days: item.budget_days ?? "", change_reason: "" } : EMPTY);
  const { data: procs } = useApiResource<{ id: string; code: string; name: string }[]>(f.company_id ? `/companies/${f.company_id}/processes` : null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const approved = plan.status === "approved";

  async function save(ev: React.FormEvent) {
    ev.preventDefault();
    setBusy(true); setErr(null);
    const body = { company_id: f.company_id, process_id: f.process_id || null, title: f.title, rationale: f.rationale,
      priority_rank: f.priority_rank ? Number(f.priority_rank) : null, planned_start: f.planned_start || null, planned_end: f.planned_end || null,
      budget_days: f.budget_days ? f.budget_days.replace(",", ".") : null, change_reason: f.change_reason || null };
    try {
      onSaved(item ? await api.patch<AuditPlan>(`/audit-plan-items/${item.id}`, body) : await api.post<AuditPlan>(`/audit-plans/${plan.id}/items`, body));
    } catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }

  return (
    <Dialog open onClose={onClose} title={item ? "Modifier la mission prévue" : "Ajouter une mission au plan"}>
      <form onSubmit={save} className="space-y-3">
        {err && <Alert>{err}</Alert>}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Entité" htmlFor="it-c" required>
            <Select id="it-c" value={f.company_id} required onChange={(x) => setF({ ...f, company_id: x.target.value, process_id: "" })}>
              <option value="">Choisir…</option>{companies?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
          </Field>
          <Field label="Processus (cartographie)" htmlFor="it-p">
            <Select id="it-p" value={f.process_id} onChange={(x) => setF({ ...f, process_id: x.target.value })} disabled={!f.company_id}>
              <option value="">—</option>{procs?.map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
            </Select>
          </Field>
        </div>
        <Field label="Intitulé" htmlFor="it-t" required><Input id="it-t" required value={f.title} onChange={(x) => setF({ ...f, title: x.target.value })} /></Field>
        <Field label="Justification (risques couverts, demande, obligation)" htmlFor="it-r" required>
          <textarea id="it-r" rows={3} required minLength={10} className={AREA} value={f.rationale} onChange={(x) => setF({ ...f, rationale: x.target.value })} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-4">
          <Field label="Priorité (1 = 1re)" htmlFor="it-pr"><Input id="it-pr" inputMode="numeric" value={f.priority_rank} onChange={(x) => setF({ ...f, priority_rank: x.target.value.replace(/\D/g, "") })} /></Field>
          <Field label="Début" htmlFor="it-s"><Input id="it-s" type="date" value={f.planned_start} onChange={(x) => setF({ ...f, planned_start: x.target.value })} /></Field>
          <Field label="Fin" htmlFor="it-e"><Input id="it-e" type="date" value={f.planned_end} onChange={(x) => setF({ ...f, planned_end: x.target.value })} /></Field>
          <Field label="Budget (jours)" htmlFor="it-b"><Input id="it-b" inputMode="decimal" value={f.budget_days} onChange={(x) => setF({ ...f, budget_days: x.target.value })} /></Field>
        </div>
        {approved && (
          <Field label="Motif de la modification (requis : plan approuvé)" htmlFor="it-cr" required>
            <Input id="it-cr" required value={f.change_reason} onChange={(x) => setF({ ...f, change_reason: x.target.value })} />
          </Field>
        )}
        <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={onClose}>Annuler</Button><Button type="submit" loading={busy}>Enregistrer</Button></div>
      </form>
    </Dialog>
  );
}

function StatusDialog({ plan, item, onClose, onSaved }: { plan: AuditPlan; item: PlanItem; onClose: () => void; onSaved: (p: AuditPlan) => void }) {
  const { data: engs } = useApiResource<Engagement[]>(`/organizations/${plan.organization_id}/engagements`);
  const [status, setStatus] = useState<PlanItemStatus>(item.status);
  const [reason, setReason] = useState("");
  const [eng, setEng] = useState(item.engagement_id ?? "");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const candidates = (engs ?? []).filter((e) => e.engagement_type === "internal_audit" && e.company_id === item.company_id);
  async function save() {
    setBusy(true); setErr(null);
    try {
      onSaved(await api.patch<AuditPlan>(`/audit-plan-items/${item.id}`, { status, engagement_id: eng || null,
        ...(status !== item.status ? { status_reason: reason || null } : {}) }));
    } catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }
  return (
    <Dialog open onClose={onClose} title={`Avancement — ${item.title}`}>
      <div className="space-y-3">
        {err && <Alert>{err}</Alert>}
        <Field label="Mission d'audit interne rattachée" htmlFor="st-e">
          <Select id="st-e" value={eng} onChange={(x) => setEng(x.target.value)}>
            <option value="">—</option>{candidates.map((e) => <option key={e.id} value={e.id}>{e.reference} — {e.name}</option>)}
          </Select>
        </Field>
        <Field label="Statut" htmlFor="st-s">
          <Select id="st-s" value={status} onChange={(x) => setStatus(x.target.value as PlanItemStatus)}>
            {(Object.keys(ITEM_STATUS) as PlanItemStatus[]).map((s) => <option key={s} value={s}>{ITEM_STATUS[s][0]}</option>)}
          </Select>
        </Field>
        {status === "completed" && <p className="text-xs text-muted-foreground">« Réalisée » exige une mission rattachée et émise.</p>}
        {status !== item.status && (
          <Field label={`Motif${["postponed", "cancelled"].includes(status) ? " (requis)" : ""}`} htmlFor="st-r">
            <Input id="st-r" value={reason} onChange={(x) => setReason(x.target.value)} />
          </Field>
        )}
        <div className="flex justify-end gap-2"><Button variant="outline" onClick={onClose}>Annuler</Button><Button loading={busy} onClick={save}>Enregistrer</Button></div>
      </div>
    </Dialog>
  );
}

function HistoryDialog({ item, onClose }: { item: PlanItem; onClose: () => void }) {
  const { data } = useApiResource<PlanHistory[]>(`/audit-plan-items/${item.id}/history`);
  return (
    <Dialog open onClose={onClose} title={`Historique — ${item.title}`}>
      {!data ? <Loading /> : (
        <ul className="space-y-2 text-sm">
          {data.map((h) => (
            <li key={h.id} className="border-b pb-2">
              <p><strong>{h.operation === "insert" ? "Ajout" : `Modification : ${h.changed_fields.map((c) => FIELD_LABELS[c] ?? c).join(", ")}`}</strong></p>
              <p className="text-xs text-muted-foreground">{formatDate(h.changed_at)} · {personName(h.changed_by)}{h.reason && ` · motif : ${h.reason}`}</p>
            </li>
          ))}
        </ul>
      )}
    </Dialog>
  );
}

export default function AuditPlanPage() {
  const { planId } = useParams<{ planId: string }>();
  const router = useRouter();
  const { data: plan, error, loading, setData } = useApiResource<AuditPlan>(`/audit-plans/${planId}`);
  const [itemDlg, setItemDlg] = useState<PlanItem | "new" | null>(null);
  const [statusDlg, setStatusDlg] = useState<PlanItem | null>(null);
  const [historyDlg, setHistoryDlg] = useState<PlanItem | null>(null);
  const [approve, setApprove] = useState<{ approval_body: string; approval_reference: string; approval_date: string } | null>(null);
  const [cancel, setCancel] = useState<{ item: PlanItem; reason: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  if (loading && !plan) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  if (!plan) return null;
  const items = Array.isArray(plan.items) ? plan.items : [];
  const can = !!plan.can_manage && plan.status !== "closed";

  async function act(key: string, fn: () => Promise<AuditPlan | void>) {
    setBusy(key); setErr(null);
    try { const r = await fn(); if (r) setData(r); return true; } catch (x) { setErr(errorMessage(x)); return false; } finally { setBusy(null); }
  }

  return (
    <>
      <Link href={`/organizations/${plan.organization_id}/plan-audit`} className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ChevronLeft className="h-4 w-4" /> Plans d&apos;audit</Link>
      <PageHeader title={plan.title}
                  description={<span className="flex flex-wrap items-center gap-2"><Badge tone={PLAN_STATUS[plan.status][1]}>{PLAN_STATUS[plan.status][0]}</Badge>
                    <span>{formatDate(plan.period_start)} – {formatDate(plan.period_end)}</span>
                    {plan.approval_body && <span>· approuvé par {plan.approval_body} le {formatDate(plan.approval_date)}{plan.approval_reference && ` (${plan.approval_reference})`}, enregistré par {personName(plan.approved_by_user)}</span>}</span>}
                  actions={can && <>
                    {plan.status === "draft" && <Button size="sm" onClick={() => setApprove({ approval_body: "", approval_reference: "", approval_date: "" })} disabled={!items.length}><CheckCircle2 className="h-4 w-4" /> Enregistrer l&apos;approbation</Button>}
                    {plan.status === "approved" && <Button size="sm" variant="outline" loading={busy === "close"} onClick={() => act("close", () => api.post(`/audit-plans/${plan.id}/close`, {}))}><Lock className="h-4 w-4" /> Clôturer</Button>}
                    {plan.status === "draft" && <Button size="icon" variant="ghost" aria-label="Supprimer le plan" onClick={async () => { if (await act("del", () => api.del(`/audit-plans/${plan.id}`))) router.push(`/organizations/${plan.organization_id}/plan-audit`); }}><Trash2 className="h-4 w-4" /></Button>}
                  </>} />
      {err && <Alert className="mb-4">{err}</Alert>}
      {plan.status === "approved" && <Alert kind="info" className="mb-4">Plan approuvé : toute modification est motivée et historisée ; une mission prévue s&apos;annule ou se reporte, elle ne se supprime pas.</Alert>}

      {plan.summary && (
        <div className="mb-5 grid gap-3 sm:grid-cols-4">
          {[["Missions prévues", String(plan.summary.items)], ["Réalisées", String(plan.summary.by_status.completed ?? 0)],
            ["Taux de réalisation", plan.summary.completion_rate !== null ? `${plan.summary.completion_rate.replace(".", ",")} %` : "—"],
            ["Budget (jours)", plan.summary.budget_days.replace(".", ",")]].map(([l, v]) => (
            <Card key={l}><CardContent className="pt-4"><p className="text-xs text-muted-foreground">{l}</p><p className="text-xl font-semibold tabular-nums">{v}</p></CardContent></Card>
          ))}
        </div>
      )}

      <Card>
        <CardHeader className="flex-row items-start justify-between gap-3">
          <div><CardTitle>Missions du plan</CardTitle>
            <CardDescription>{plan.summary?.added_after_approval ? `${plan.summary.added_after_approval} ajout(s) après approbation.` : "Ordonnées par priorité puis par date de début."}</CardDescription></div>
          {can && <Button size="sm" onClick={() => setItemDlg("new")}><Plus className="h-4 w-4" /> Mission</Button>}
        </CardHeader>
        <CardContent>
          {items.length === 0 ? <EmptyState title="Aucune mission prévue" /> : (
            <Table>
              <THead><tr><TH>Priorité</TH><TH>Mission</TH><TH>Entité / processus</TH><TH>Période</TH><TH className="text-right">Jours</TH><TH>Mission rattachée</TH><TH>Statut</TH><TH /></tr></THead>
              <TBody>
                {items.map((i) => (
                  <TR key={i.id}>
                    <TD>{i.priority_rank ?? "—"}</TD>
                    <TD><span className="font-medium">{i.title}</span>{i.added_after_approval && <Badge className="ml-1">Ajout</Badge>}
                      <p className="text-xs text-muted-foreground">{i.rationale}</p></TD>
                    <TD>{i.company}<p className="text-xs text-muted-foreground">{i.process ?? "—"}</p></TD>
                    <TD className="whitespace-nowrap">{i.planned_start ? `${formatDate(i.planned_start)} – ${formatDate(i.planned_end)}` : "—"}</TD>
                    <TD className="text-right">{i.budget_days?.replace(".", ",") ?? "—"}</TD>
                    <TD>{i.engagement ? <Link className="text-link hover:underline" href={`/missions/${i.engagement.id}`}>{i.engagement.reference}</Link> : "—"}</TD>
                    <TD><Badge tone={ITEM_STATUS[i.status][1]}>{ITEM_STATUS[i.status][0]}</Badge>{i.status_reason && <p className="text-xs text-muted-foreground">{i.status_reason}</p>}</TD>
                    <TD className="whitespace-nowrap text-right">
                      <Button size="icon" variant="ghost" aria-label="Historique" onClick={() => setHistoryDlg(i)}><History className="h-4 w-4" /></Button>
                      {can && <>
                        <Button size="sm" variant="outline" onClick={() => setStatusDlg(i)}>Avancement</Button>
                        <Button size="icon" variant="ghost" aria-label="Modifier" onClick={() => setItemDlg(i)}><Pencil className="h-4 w-4" /></Button>
                        {plan.status === "draft"
                          ? <Button size="icon" variant="ghost" aria-label="Supprimer" onClick={() => act(i.id, async () => { await api.del(`/audit-plan-items/${i.id}`); return api.get<AuditPlan>(`/audit-plans/${plan.id}`); })}><Trash2 className="h-4 w-4" /></Button>
                          : !["cancelled", "completed"].includes(i.status) && <Button size="sm" variant="ghost" onClick={() => setCancel({ item: i, reason: "" })}>Annuler</Button>}
                      </>}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {itemDlg && <ItemDialog plan={plan} item={itemDlg === "new" ? null : itemDlg} onClose={() => setItemDlg(null)} onSaved={(p) => { setData(p); setItemDlg(null); }} />}
      {statusDlg && <StatusDialog plan={plan} item={statusDlg} onClose={() => setStatusDlg(null)} onSaved={(p) => { setData(p); setStatusDlg(null); }} />}
      {historyDlg && <HistoryDialog item={historyDlg} onClose={() => setHistoryDlg(null)} />}
      <Dialog open={approve !== null} onClose={() => setApprove(null)} title="Approbation du plan" description="Enregistrez la décision de l'instance qui a approuvé le plan. Une fois approuvé, le plan est figé ; ses évolutions sont motivées.">
        {approve && (
          <form className="space-y-3" onSubmit={async (x) => { x.preventDefault(); if (await act("approve", () => api.post(`/audit-plans/${plan.id}/approve`, { ...approve, approval_reference: approve.approval_reference || null }))) setApprove(null); }}>
            {err && <Alert>{err}</Alert>}
            <Field label="Instance (comité d'audit, conseil…)" htmlFor="ap-b" required><Input id="ap-b" required value={approve.approval_body} onChange={(x) => setApprove({ ...approve, approval_body: x.target.value })} /></Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Date de la décision" htmlFor="ap-d" required><Input id="ap-d" type="date" required value={approve.approval_date} onChange={(x) => setApprove({ ...approve, approval_date: x.target.value })} /></Field>
              <Field label="Référence (procès-verbal…)" htmlFor="ap-r"><Input id="ap-r" value={approve.approval_reference} onChange={(x) => setApprove({ ...approve, approval_reference: x.target.value })} /></Field>
            </div>
            <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => setApprove(null)}>Annuler</Button><Button type="submit" loading={busy === "approve"}>Enregistrer</Button></div>
          </form>
        )}
      </Dialog>
      <Dialog open={cancel !== null} onClose={() => setCancel(null)} title="Annuler la mission prévue">
        {cancel && (
          <div className="space-y-3">
            <Field label="Motif (requis)" htmlFor="cc-r" required><Input id="cc-r" value={cancel.reason} onChange={(x) => setCancel({ ...cancel, reason: x.target.value })} /></Field>
            <div className="flex justify-end gap-2"><Button variant="outline" onClick={() => setCancel(null)}>Retour</Button>
              <Button variant="destructive" disabled={cancel.reason.trim().length < 3} loading={busy === "cancel"} onClick={async () => {
                if (await act("cancel", () => api.patch(`/audit-plan-items/${cancel.item.id}`, { status: "cancelled", status_reason: cancel.reason }))) setCancel(null);
              }}>Annuler la mission</Button></div>
          </div>
        )}
      </Dialog>
    </>
  );
}
