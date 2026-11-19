"use client";

import { useState } from "react";
import { CheckCircle2, MessageSquareReply, Pencil, Plus, Send, Trash2, Undo2 } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { personName, type Engagement, type EngagementRisk, type RiskScale } from "@/lib/types";
import {
  ACTION_STATUS, FINDING_STATUS, ROLE_SHORT, type ActionPlan, type ActionStatus, type ActionUpdate, type Finding, type FindingLevel,
} from "@/lib/ia-types";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";

const AREA = "w-full rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30";
type Data = { findings: Finding[]; levels: FindingLevel[]; deficiency_levels?: FindingLevel[]; capabilities: string[] };
type FForm = { reference: string; title: string; condition: string; criteria: string; cause: string; effect: string; rating_code: string;
               process_id: string; engagement_risk_id: string; kind: string; control_id: string; risk_id: string };
type IcRegistry = { controls: { id: string; code: string; title: string }[]; risks: { id: string; code: string; title: string }[] };

function FindingDialog({ e, data, f, onClose, onSaved }: { e: Engagement; data: Data; f: Finding | null; onClose: () => void; onSaved: (d: Data) => void }) {
  const base = `/engagements/${e.id}`;
  const icCapable = e.engagement_type === "ic_assessment" || e.engagement_type === "internal_audit";
  const { data: reg } = useApiResource<IcRegistry>(icCapable ? `${base}/ic/registry` : null);
  const { data: procs } = useApiResource<{ id: string; code: string; name: string }[]>(`/companies/${e.company_id}/processes`);
  const { data: risks } = useApiResource<{ risks: EngagementRisk[]; scale: RiskScale | null }>(`${base}/risks`);
  const [v, setV] = useState<FForm>({ reference: f?.reference ?? "", title: f?.title ?? "", condition: f?.condition ?? "", criteria: f?.criteria ?? "",
    cause: f?.cause ?? "", effect: f?.effect ?? "", rating_code: f?.rating_code ?? "", process_id: f?.process_id ?? "", engagement_risk_id: f?.engagement_risk_id ?? "",
    kind: f?.kind ?? (e.engagement_type === "ic_assessment" ? "ic_deficiency" : "audit_finding"), control_id: f?.control_id ?? "", risk_id: f?.risk_id ?? "" });
  const deficiency = v.kind === "ic_deficiency";
  const levels = deficiency && data.deficiency_levels?.length ? data.deficiency_levels : data.levels;
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function save(ev: React.FormEvent) {
    ev.preventDefault();
    setBusy(true); setErr(null);
    const body = Object.fromEntries(Object.entries(v).map(([k, x]) => [k, x || null]));
    body.kind = v.kind;
    try { onSaved(f ? await api.patch<Data>(`${base}/findings/${f.id}`, body) : await api.post<Data>(`${base}/findings`, body)); }
    catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }
  const area = (k: keyof FForm, label: string, req = false, rows = 3) => (
    <Field label={label} htmlFor={`fd-${k}`} required={req}>
      <textarea id={`fd-${k}`} rows={rows} required={req} className={AREA} value={v[k]} onChange={(x) => setV({ ...v, [k]: x.target.value })} />
    </Field>
  );
  return (
    <Dialog open onClose={onClose} title={f ? `Constat ${f.reference}` : "Nouveau constat"} description="Constat, référentiel, cause et conséquence : uniquement ce qui a été constaté et documenté.">
      <form onSubmit={save} className="space-y-3">
        {err && <Alert>{err}</Alert>}
        <div className="grid gap-3 sm:grid-cols-4">
          <Field label="Référence" htmlFor="fd-ref" required><Input id="fd-ref" required value={v.reference} onChange={(x) => setV({ ...v, reference: x.target.value })} /></Field>
          <div className="sm:col-span-3"><Field label="Titre" htmlFor="fd-title" required><Input id="fd-title" required value={v.title} onChange={(x) => setV({ ...v, title: x.target.value })} /></Field></div>
        </div>
        {icCapable && (
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Nature" htmlFor="fd-kind">
              <Select id="fd-kind" value={v.kind} disabled={!!f} onChange={(x) => setV({ ...v, kind: x.target.value, rating_code: "" })}>
                <option value="audit_finding">Constat d&apos;audit</option><option value="ic_deficiency">Déficience de contrôle interne</option>
              </Select>
            </Field>
            {deficiency && (
              <>
                <Field label="Contrôle concerné" htmlFor="fd-ctl" required>
                  <Select id="fd-ctl" required value={v.control_id} onChange={(x) => setV({ ...v, control_id: x.target.value })}>
                    <option value="">—</option>{reg?.controls.map((c) => <option key={c.id} value={c.id}>{c.code} — {c.title}</option>)}
                  </Select>
                </Field>
                <Field label="Risque associé (registre)" htmlFor="fd-rr">
                  <Select id="fd-rr" value={v.risk_id} onChange={(x) => setV({ ...v, risk_id: x.target.value })}>
                    <option value="">—</option>{reg?.risks.map((r) => <option key={r.id} value={r.id}>{r.code} — {r.title}</option>)}
                  </Select>
                </Field>
              </>
            )}
          </div>
        )}
        {area("condition", deficiency ? "Situation observée" : "Constat (ce qui a été observé)", true)}
        {area("criteria", deficiency ? "Critère de référence (ce qui était attendu)" : "Référentiel (ce qui était attendu)", true, 2)}
        <div className="grid gap-3 sm:grid-cols-2">{area("cause", "Cause", false, 2)}{area("effect", "Conséquence / risque", false, 2)}</div>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label={deficiency ? "Niveau de gravité" : "Cotation"} htmlFor="fd-rate">
            <Select id="fd-rate" value={v.rating_code} onChange={(x) => setV({ ...v, rating_code: x.target.value })} disabled={!levels.length}>
              <option value="">—</option>{levels.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
            </Select>
            {!levels.length && <p className="mt-1 text-xs text-muted-foreground">La méthodologie de la mission n&apos;a pas d&apos;échelle {deficiency ? "des déficiences (deficiency_scale) ni " : ""}des constats (finding_scale).</p>}
          </Field>
          <Field label="Processus" htmlFor="fd-proc">
            <Select id="fd-proc" value={v.process_id} onChange={(x) => setV({ ...v, process_id: x.target.value })}>
              <option value="">—</option>{procs?.map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
            </Select>
          </Field>
          <Field label="Risque de la mission" htmlFor="fd-risk">
            <Select id="fd-risk" value={v.engagement_risk_id} onChange={(x) => setV({ ...v, engagement_risk_id: x.target.value })}>
              <option value="">—</option>{risks?.risks.map((r) => <option key={r.id} value={r.id}>{r.code} — {r.title}</option>)}
            </Select>
          </Field>
        </div>
        <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={onClose}>Annuler</Button><Button type="submit" loading={busy}>Enregistrer</Button></div>
      </form>
    </Dialog>
  );
}

function ActionRow({ e, a, caps, onChanged }: { e: Engagement; a: ActionPlan; caps: string[]; onChanged: () => void }) {
  const base = `/engagements/${e.id}/action-plans/${a.id}`;
  const [open, setOpen] = useState(false);
  const { data: updates, reload } = useApiResource<ActionUpdate[]>(open ? `${base}/updates` : null);
  const [u, setU] = useState({ status: a.status as ActionStatus, comment: "", new_due_date: "" });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const options = (Object.keys(ACTION_STATUS) as ActionStatus[]).filter((s) => s !== "verified" || (caps.includes("verify_actions") && a.status === "implemented"));
  async function post() {
    setBusy(true); setErr(null);
    try { await api.post(`${base}/updates`, { ...u, new_due_date: u.new_due_date || null }); setU({ ...u, comment: "", new_due_date: "" }); await reload(); onChanged(); }
    catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }
  return (
    <div className="rounded-md border p-2 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span>{a.description} <span className="text-xs text-muted-foreground">· {a.owner_name} · échéance {formatDate(a.due_date)}</span></span>
        <span className="flex items-center gap-2">
          {a.overdue && <Badge tone="red">En retard</Badge>}
          <Badge tone={ACTION_STATUS[a.status][1]}>{ACTION_STATUS[a.status][0]}</Badge>
          <Button size="sm" variant="ghost" onClick={() => setOpen(!open)}>{open ? "Masquer le suivi" : "Suivi"}</Button>
        </span>
      </div>
      {open && (
        <div className="mt-2 space-y-2 border-t pt-2">
          {updates?.length === 0 && <p className="text-xs text-muted-foreground">Aucune mise à jour.</p>}
          {updates?.map((x) => (
            <p key={x.id} className="text-xs"><Badge tone={ACTION_STATUS[x.status][1]}>{ACTION_STATUS[x.status][0]}</Badge> {x.comment}
              <span className="text-muted-foreground"> — {personName(x.author)} ({ROLE_SHORT[x.author_role] ?? x.author_role}), {formatDate(x.created_at)}{x.new_due_date && `, nouvelle échéance ${formatDate(x.new_due_date)}`}</span></p>
          ))}
          {err && <Alert>{err}</Alert>}
          {caps.includes("follow_up") && a.status !== "verified" && (
            <div className="grid gap-2 sm:grid-cols-[10rem_minmax(0,1fr)_9rem_auto]">
              <Select aria-label="Statut" value={u.status} onChange={(x) => setU({ ...u, status: x.target.value as ActionStatus })}>
                {options.map((s) => <option key={s} value={s}>{ACTION_STATUS[s][0]}</option>)}
              </Select>
              <Input aria-label="Commentaire" placeholder="Commentaire (requis)" value={u.comment} onChange={(x) => setU({ ...u, comment: x.target.value })} />
              <Input aria-label="Nouvelle échéance" type="date" value={u.new_due_date} onChange={(x) => setU({ ...u, new_due_date: x.target.value })} />
              <Button size="sm" loading={busy} disabled={u.comment.trim().length < 3} onClick={post}>Ajouter</Button>
            </div>
          )}
          {u.status === "verified" && <p className="text-xs text-muted-foreground">Décrivez les travaux de vérification ; joignez les éléments probants dans l&apos;onglet correspondant.</p>}
        </div>
      )}
    </div>
  );
}

function FindingCard({ e, f, caps, myRole, onData, reload, onEdit }: { e: Engagement; f: Finding; caps: string[]; myRole: string | null; onData: (d: Data) => void; reload: () => void; onEdit: () => void }) {
  const base = `/engagements/${e.id}`;
  const [rec, setRec] = useState({ reference: "", text: "" });
  const [resp, setResp] = useState<{ management_response: string; response_by_name: string } | null>(null);
  const [ap, setAp] = useState<{ rec: string; description: string; owner_name: string; due_date: string } | null>(null);
  const [reopen, setReopen] = useState<string | null>(null);
  const [closing, setClosing] = useState<string | null>(null);
  const [due, setDue] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const draft = f.status === "draft";
  async function act(key: string, fn: () => Promise<Data | unknown>) {
    setBusy(key); setErr(null);
    try { const d = await fn(); if (d && typeof d === "object" && "findings" in (d as object)) onData(d as Data); else reload(); return true; }
    catch (x) { setErr(errorMessage(x)); return false; } finally { setBusy(null); }
  }
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-3">
        <div>
          <CardTitle>{f.reference} — {f.title} {f.rating_label && <Badge tone={f.rating_rank === 1 ? "red" : "amber"} className="ml-1">{f.rating_label}</Badge>}</CardTitle>
          <CardDescription>
            <Badge tone={FINDING_STATUS[f.status][1]}>{FINDING_STATUS[f.status][0]}</Badge>
            {f.kind === "ic_deficiency" && <Badge tone="gold" className="ml-1">Déficience de contrôle interne</Badge>}
            {f.origin === "ai_suggestion" && <Badge tone="gold" className="ml-1">Projet issu d&apos;une suggestion IA</Badge>}
            {f.process && ` · ${f.process}`}{f.risk && ` · risque ${f.risk}`} · rédigé par {personName(f.created_by_user)}
            {f.validated_at && ` · validé le ${formatDate(f.validated_at)} par ${personName(f.validated_by_user)}`}
            {f.response_due && ` · réponse attendue le ${formatDate(f.response_due)}`}
          </CardDescription>
          {f.reopen_reason && draft && <p className="mt-1 text-xs text-muted-foreground">Remis en brouillon : {f.reopen_reason}</p>}
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          {draft && caps.includes("validate_findings") && <Button size="sm" loading={busy === "validate"} onClick={() => act("validate", () => api.post(`${base}/findings/${f.id}/status`, { action: "validate" }))}><CheckCircle2 className="h-4 w-4" /> Valider</Button>}
          {f.status === "validated" && caps.includes("communicate_findings") && (
            <span className="flex items-center gap-1">
              <Input aria-label="Réponse attendue le" type="date" className="w-36" value={due} onChange={(x) => setDue(x.target.value)} />
              <Button size="sm" loading={busy === "communicate"} onClick={() => act("communicate", () => api.post(`${base}/findings/${f.id}/status`, { action: "communicate", response_due: due || null }))}><Send className="h-4 w-4" /> Communiquer</Button>
            </span>
          )}
          {f.status === "communicated" && caps.includes("close_findings") && <Button size="sm" variant="outline" onClick={() => setClosing("")}><CheckCircle2 className="h-4 w-4" /> Clôturer</Button>}
          {!draft && f.status !== "closed" && caps.includes("validate_findings") && !["issued", "archived"].includes(e.status) && <Button size="sm" variant="ghost" onClick={() => setReopen("")}><Undo2 className="h-4 w-4" /> Brouillon</Button>}
          {f.status === "communicated" && caps.includes("respond_findings") && <Button size="sm" variant="outline" onClick={() => setResp({ management_response: f.management_response ?? "", response_by_name: f.response_by_name ?? "" })}><MessageSquareReply className="h-4 w-4" /> {f.management_response ? "Modifier la réponse" : "Répondre"}</Button>}
          {draft && caps.includes("edit_findings") && <Button size="icon" variant="ghost" aria-label={`Modifier ${f.reference}`} onClick={onEdit}><Pencil className="h-4 w-4" /></Button>}
          {draft && caps.includes("edit_findings") && <Button size="icon" variant="ghost" aria-label="Supprimer le constat" onClick={() => act("del", () => api.del(`${base}/findings/${f.id}`))}><Trash2 className="h-4 w-4" /></Button>}
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {err && <Alert>{err}</Alert>}
        <dl className="grid gap-2 sm:grid-cols-2">
          <div><dt className="text-xs font-medium text-muted-foreground">Constat</dt><dd className="whitespace-pre-wrap">{f.condition}</dd></div>
          <div><dt className="text-xs font-medium text-muted-foreground">Référentiel</dt><dd className="whitespace-pre-wrap">{f.criteria}</dd></div>
          {f.cause && <div><dt className="text-xs font-medium text-muted-foreground">Cause</dt><dd className="whitespace-pre-wrap">{f.cause}</dd></div>}
          {f.effect && <div><dt className="text-xs font-medium text-muted-foreground">Conséquence</dt><dd className="whitespace-pre-wrap">{f.effect}</dd></div>}
        </dl>
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Recommandations</p>
          {f.recommendations.length === 0 && <p className="text-muted-foreground">Aucune recommandation (au moins une est requise pour valider).</p>}
          {f.recommendations.map((r) => (
            <div key={r.id} className="space-y-2 rounded-md bg-muted/40 p-3">
              <div className="flex items-start justify-between gap-2">
                <p><span className="font-medium">{r.reference}</span> {r.text}</p>
                {draft && caps.includes("edit_findings") && <Button size="icon" variant="ghost" aria-label={`Supprimer ${r.reference}`} onClick={() => act(r.id, () => api.del(`${base}/recommendations/${r.id}`))}><Trash2 className="h-4 w-4" /></Button>}
              </div>
              {r.action_plans.map((a) => <ActionRow key={a.id} e={e} a={a} caps={caps} onChanged={reload} />)}
              {caps.includes("follow_up") && (f.status === "communicated" || myRole !== "auditee") && !["issued", "archived"].includes(e.status) && (
                <Button size="sm" variant="outline" onClick={() => setAp({ rec: r.id, description: "", owner_name: "", due_date: "" })}><Plus className="h-4 w-4" /> Plan d&apos;action</Button>
              )}
            </div>
          ))}
          {draft && caps.includes("edit_findings") && (
            <div className="grid gap-2 sm:grid-cols-[6rem_minmax(0,1fr)_auto]">
              <Input aria-label="Référence de la recommandation" placeholder="Réf." value={rec.reference} onChange={(x) => setRec({ ...rec, reference: x.target.value })} />
              <Input aria-label="Recommandation" placeholder="Recommandation…" value={rec.text} onChange={(x) => setRec({ ...rec, text: x.target.value })} />
              <Button size="sm" variant="outline" disabled={!rec.reference || !rec.text} loading={busy === "rec"}
                      onClick={async () => { if (await act("rec", () => api.post(`${base}/findings/${f.id}/recommendations`, rec))) setRec({ reference: "", text: "" }); }}>Ajouter</Button>
            </div>
          )}
        </div>
        {f.status === "closed" && <Alert kind="success">Clos le {formatDate(f.closed_at)} : {f.closure_note}</Alert>}
        {(f.status === "communicated" || f.status === "closed") && (
          <div className="border-l-2 border-primary/40 pl-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Réponse de la direction</p>
            {f.management_response ? <p className="whitespace-pre-wrap">{f.management_response} <span className="text-xs text-muted-foreground">— {f.response_by_name}, {formatDate(f.response_at)}</span></p>
              : <p className="text-muted-foreground">Non reçue.</p>}
          </div>
        )}
      </CardContent>
      <Dialog open={resp !== null} onClose={() => setResp(null)} title={`Réponse de la direction — ${f.reference}`}
              description={myRole === "auditee" ? "Votre réponse est enregistrée à votre nom et reprise dans le rapport." : "Saisie par l'équipe d'audit : indiquez l'auteur de la réponse (nom et fonction)."}>
        {resp && (
          <div className="space-y-3">
            <textarea aria-label="Réponse" rows={5} className={AREA} value={resp.management_response} onChange={(x) => setResp({ ...resp, management_response: x.target.value })} />
            <Field label={myRole === "auditee" ? "Nom et fonction (facultatif)" : "Auteur de la réponse (requis)"} htmlFor="rs-n">
              <Input id="rs-n" value={resp.response_by_name} onChange={(x) => setResp({ ...resp, response_by_name: x.target.value })} />
            </Field>
            <div className="flex justify-end gap-2"><Button variant="outline" onClick={() => setResp(null)}>Annuler</Button>
              <Button loading={busy === "resp"} onClick={async () => { if (await act("resp", () => api.post(`${base}/findings/${f.id}/response`, { management_response: resp.management_response || null, response_by_name: resp.response_by_name || null }))) setResp(null); }}>Enregistrer</Button></div>
          </div>
        )}
      </Dialog>
      <Dialog open={ap !== null} onClose={() => setAp(null)} title="Plan d'action de la direction">
        {ap && (
          <div className="space-y-3">
            <Field label="Action décidée" htmlFor="ap-d" required><textarea id="ap-d" rows={2} className={AREA} value={ap.description} onChange={(x) => setAp({ ...ap, description: x.target.value })} /></Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Responsable" htmlFor="ap-o" required><Input id="ap-o" value={ap.owner_name} onChange={(x) => setAp({ ...ap, owner_name: x.target.value })} /></Field>
              <Field label="Échéance" htmlFor="ap-e" required><Input id="ap-e" type="date" value={ap.due_date} onChange={(x) => setAp({ ...ap, due_date: x.target.value })} /></Field>
            </div>
            <div className="flex justify-end gap-2"><Button variant="outline" onClick={() => setAp(null)}>Annuler</Button>
              <Button loading={busy === "ap"} disabled={!ap.description || !ap.owner_name || !ap.due_date} onClick={async () => {
                if (await act("ap", () => api.post(`${base}/recommendations/${ap.rec}/action-plans`, { description: ap.description, owner_name: ap.owner_name, due_date: ap.due_date }))) setAp(null);
              }}>Enregistrer</Button></div>
          </div>
        )}
      </Dialog>
      <Dialog open={closing !== null} onClose={() => setClosing(null)} title={`Clôturer ${f.reference}`}
              description="Possible lorsque chaque recommandation a un plan d'action vérifié ou en risque accepté ; la base le vérifie.">
        <div className="space-y-3">
          <Field label="Note de clôture (requise)" htmlFor="cl-n" required><Input id="cl-n" value={closing ?? ""} onChange={(x) => setClosing(x.target.value)} /></Field>
          <div className="flex justify-end gap-2"><Button variant="outline" onClick={() => setClosing(null)}>Annuler</Button>
            <Button disabled={(closing ?? "").trim().length < 3} loading={busy === "close"} onClick={async () => { if (await act("close", () => api.post(`${base}/findings/${f.id}/status`, { action: "close", reason: closing }))) setClosing(null); }}>Clôturer</Button></div>
        </div>
      </Dialog>
      <Dialog open={reopen !== null} onClose={() => setReopen(null)} title="Remettre le constat en brouillon" description="La validation et la communication sont annulées ; le motif est conservé.">
        <div className="space-y-3">
          <Field label="Motif (requis)" htmlFor="ro-r" required><Input id="ro-r" value={reopen ?? ""} onChange={(x) => setReopen(x.target.value)} /></Field>
          <div className="flex justify-end gap-2"><Button variant="outline" onClick={() => setReopen(null)}>Annuler</Button>
            <Button disabled={(reopen ?? "").trim().length < 3} loading={busy === "reopen"} onClick={async () => { if (await act("reopen", () => api.post(`${base}/findings/${f.id}/status`, { action: "reopen", reason: reopen }))) setReopen(null); }}>Remettre en brouillon</Button></div>
        </div>
      </Dialog>
    </Card>
  );
}

export function FindingsTab({ e }: { e: Engagement }) {
  const { data, error, loading, reload, setData } = useApiResource<Data>(`/engagements/${e.id}/findings`);
  const [edit, setEdit] = useState<Finding | "new" | null>(null);
  if (loading && !data) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  if (!data) return null;
  const caps = data.capabilities;
  const counts = data.findings.reduce<Record<string, number>>((a, f) => ({ ...a, [f.status]: (a[f.status] ?? 0) + 1 }), {});
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-3xl text-sm text-muted-foreground">
          {e.my_role === "auditee"
            ? "Constats qui vous ont été communiqués : répondez-y et indiquez vos plans d'action et leur avancement. Le dossier de travail de l'équipe d'audit ne vous est pas accessible."
            : "Brouillon → validé (manager ou associé, autre que l'auteur, au moins une recommandation) → communiqué à l'audité. Un constat validé est figé ; sa remise en brouillon est motivée."}
        </p>
        {caps.includes("edit_findings") && <Button size="sm" onClick={() => setEdit("new")}><Plus className="h-4 w-4" /> Constat</Button>}
      </div>
      {data.findings.length > 0 && e.my_role !== "auditee" && (
        <p className="text-sm">{(Object.keys(FINDING_STATUS) as (keyof typeof FINDING_STATUS)[]).filter((s) => counts[s]).map((s) => `${counts[s]} ${FINDING_STATUS[s][0].toLowerCase()}`).join(" · ")}</p>
      )}
      {data.findings.length === 0 && <EmptyState title={e.my_role === "auditee" ? "Aucun constat communiqué" : "Aucun constat"} />}
      {data.findings.map((f) => (
        <FindingCard key={f.id} e={e} f={f} caps={caps} myRole={e.my_role ?? null} onData={setData} reload={() => void reload()} onEdit={() => setEdit(f)} />
      ))}
      {edit && <FindingDialog e={e} data={data} f={edit === "new" ? null : edit} onClose={() => setEdit(null)} onSaved={(d) => { setData(d); setEdit(null); }} />}
    </div>
  );
}
