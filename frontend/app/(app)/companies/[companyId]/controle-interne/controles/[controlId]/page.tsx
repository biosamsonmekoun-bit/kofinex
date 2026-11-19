"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Download, Pencil } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { personName, type PersonRef } from "@/lib/types";
import {
  AUTOMATION, CONCLUSION, EXISTENCE, FREQUENCY, NATURE, OUTCOME, STAGE_TONE, SUPERVISION, TEST_STATUS, TIMING,
  type IcControl, type IcDeficiency, type IcExecution, type IcRisk, type IcTestBrief,
} from "@/lib/ic-types";
import { formatDate } from "@/lib/utils";
import { AREA, IcShell } from "@/components/ic-shell";
import { ControlDialog, useIcRefs } from "@/components/ic-forms";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, Badge, Loading } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

type Detail = IcControl & {
  can_manage: boolean; can_execute: boolean; can_supervise: boolean;
  risks_covered: { risk_id: string; code: string; title: string; coverage: "full" | "partial"; assertion_codes: string[]; rationale: string | null }[];
  framework_links: { id: string; item_id: string; code: string; label: string; item_type: string; framework: string }[];
  tests: IcTestBrief[]; executions: IcExecution[]; deficiencies: IcDeficiency[];
};
type Fw = { versions: { id: string; name: string; version_label: string; status: string; items: { id: string; item_type: string; code: string; label: string }[] }[] };
type Hist = { object_type: string; action: string; reason: string | null; changed_at: string; changed_fields: string[]; version: number | null; changed_by: PersonRef | null };

const ITEM_TYPES: Record<string, string> = { ic_component: "Composante", ic_principle: "Principe", ic_requirement: "Exigence", ic_criterion: "Critère" };

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><dt className="text-xs text-muted-foreground">{label}</dt><dd className="whitespace-pre-line text-sm">{children || "—"}</dd></div>;
}

export default function IcControlPage() {
  const { companyId: cid, controlId } = useParams<{ companyId: string; controlId: string }>();
  const path = `/companies/${cid}/ic/controls/${controlId}`;
  const refs = useIcRefs(cid);
  const { data: c, error, reload } = useApiResource<Detail>(path);
  const [editing, setEditing] = useState(false);
  return (
    <IcShell cid={cid} title={c ? `${c.code} — ${c.title}` : "Contrôle"} description={c ? `Version ${c.version} · responsable ${c.owner_name}` : undefined}
             actions={c?.can_manage ? <Button size="sm" variant="outline" onClick={() => setEditing(true)}><Pencil className="h-4 w-4" /> Modifier</Button> : undefined}>
      {() => (
        <>
          {error && <Alert>{error}</Alert>}
          {!c ? <Loading /> : (
            <div className="space-y-5">
              <div className="flex flex-wrap gap-2">
                <Badge tone={EXISTENCE[c.existence][1]}>{EXISTENCE[c.existence][0]}</Badge>
                {c.is_key && <Badge tone="gold">Contrôle clé</Badge>}
                <Badge tone={CONCLUSION[c.conclusion][1]}>{CONCLUSION[c.conclusion][0]}</Badge>
                {c.operational_status !== "active" && <Badge>{c.operational_status === "suspended" ? "Suspendu" : "Retiré"}</Badge>}
              </div>
              <Card><CardHeader><CardTitle>Fiche du contrôle</CardTitle></CardHeader><CardContent>
                <dl className="grid gap-4 sm:grid-cols-3">
                  <Row label="Objectif du contrôle">{c.control_objective}</Row>
                  <Row label="Domaine">{refs.domains.find((d) => d.id === c.domain_id)?.name}</Row>
                  <Row label="Processus">{refs.processes.find((p) => p.id === c.process_id)?.name}</Row>
                  <Row label="Responsable">{c.owner_name}</Row><Row label="Exécutant">{c.performer_name}</Row><Row label="Superviseur">{c.supervisor_name}</Row>
                  <Row label="Fréquence">{c.frequency && FREQUENCY[c.frequency]}</Row><Row label="Nature">{c.nature && NATURE[c.nature]}</Row>
                  <Row label="Mode">{c.automation && AUTOMATION[c.automation]}{c.timing && ` · ${TIMING[c.timing]}`}</Row>
                  <Row label="Mise en place">{formatDate(c.implemented_on)}</Row>
                  <Row label="Conception (dernier test revu)">{c.design && CONCLUSION[c.design][0]}</Row>
                  <Row label="Efficacité (dernier test revu)">{c.operating && CONCLUSION[c.operating][0]}</Row>
                </dl>
                <dl className="mt-4 grid gap-4 sm:grid-cols-2">
                  <Row label="Description">{c.description}</Row><Row label="Mode d'exécution">{c.execution_mode}</Row>
                  <Row label="Procédure de contrôle">{c.procedure_text}</Row><Row label="Documents justificatifs attendus">{c.expected_evidence}</Row>
                  <Row label="Critères de réussite">{c.success_criteria}</Row>
                </dl>
              </CardContent></Card>
              <RiskLinks cid={cid} c={c} onChanged={reload} />
              <FrameworkLinks cid={cid} c={c} onChanged={reload} />
              <Executions cid={cid} c={c} onChanged={reload} />
              <Card><CardHeader><CardTitle>Tests</CardTitle><CardDescription>Tests réalisés dans les missions (visibles : dossiers dont vous êtes membre ou tests revus). Les résultats antérieurs sont conservés.</CardDescription></CardHeader><CardContent>
                {c.tests.length === 0 ? <p className="text-sm text-muted-foreground">Aucun test.</p> : (
                  <Table><THead><tr><TH>Test</TH><TH>Type</TH><TH>Période</TH><TH>Statut</TH><TH>Conclusion</TH></tr></THead>
                    <TBody>{c.tests.map((t) => <TR key={t.id}><TD><Link className="text-link hover:underline" href={`/missions/${t.engagement_id}?tab=ic&test=${t.id}`}>{t.reference}</Link></TD>
                      <TD>{t.test_type === "design" ? "Conception" : "Efficacité"}</TD><TD>{t.period_start ? `${formatDate(t.period_start)} → ${formatDate(t.period_end)}` : "—"}</TD>
                      <TD><Badge tone={TEST_STATUS[t.status]?.[1]}>{TEST_STATUS[t.status]?.[0]}</Badge></TD>
                      <TD>{t.conclusion ? <Badge tone={CONCLUSION[t.conclusion][1]}>{CONCLUSION[t.conclusion][0]}</Badge> : "—"}</TD></TR>)}</TBody></Table>
                )}
              </CardContent></Card>
              <Card><CardHeader><CardTitle>Déficiences</CardTitle></CardHeader><CardContent className="space-y-2">
                {c.deficiencies.length === 0 && <p className="text-sm text-muted-foreground">Aucune déficience visible.</p>}
                {c.deficiencies.map((d) => (
                  <p key={d.id} className="text-sm"><Link className="text-link hover:underline" href={`/missions/${d.engagement_id}?tab=findings`}>{d.reference} — {d.title}</Link>{" "}
                    {d.rating_label && <Badge tone="amber">{d.rating_label}</Badge>} <Badge tone={STAGE_TONE[d.stage]}>{d.stage_label}</Badge></p>
                ))}
              </CardContent></Card>
              <ControlHistory path={`${path}/history`} />
            </div>
          )}
          {editing && c && <ControlDialog cid={cid} control={c} domains={refs.domains} processes={refs.processes} objectives={refs.objectives}
                                          onClose={() => setEditing(false)} onSaved={async () => { setEditing(false); await reload(); }} />}
        </>
      )}
    </IcShell>
  );
}

function RiskLinks({ cid, c, onChanged }: { cid: string; c: Detail; onChanged: () => void }) {
  const { data: risks } = useApiResource<IcRisk[]>(c.can_manage ? `/companies/${cid}/ic/risks` : null);
  const [f, setF] = useState({ risk_id: "", coverage: "full", assertions: "", rationale: "" });
  const [err, setErr] = useState<string | null>(null);
  async function add() {
    setErr(null);
    try {
      await api.post(`/companies/${cid}/ic/controls/${c.id}/risks`, { risk_id: f.risk_id, coverage: f.coverage, rationale: f.rationale.trim() || null,
        assertion_codes: f.assertions.split(",").map((x) => x.trim()).filter(Boolean) });
      setF({ risk_id: "", coverage: "full", assertions: "", rationale: "" }); onChanged();
    } catch (x) { setErr(errorMessage(x)); }
  }
  async function remove(id: string) {
    setErr(null);
    try { await api.del(`/companies/${cid}/ic/controls/${c.id}/risks/${id}`); onChanged(); } catch (x) { setErr(errorMessage(x)); }
  }
  const linked = new Set(c.risks_covered.map((r) => r.risk_id));
  return (
    <Card><CardHeader><CardTitle>Risques couverts</CardTitle><CardDescription>Relation plusieurs-à-plusieurs : un contrôle peut couvrir plusieurs risques et un risque peut être couvert par plusieurs contrôles.</CardDescription></CardHeader>
      <CardContent className="space-y-3">
        {err && <Alert>{err}</Alert>}
        {c.risks_covered.length === 0 ? <p className="text-sm text-muted-foreground">Aucun risque associé.</p> : (
          <Table><THead><tr><TH>Risque</TH><TH>Couverture</TH><TH>Assertions</TH><TH>Justification</TH><TH /></tr></THead>
            <TBody>{c.risks_covered.map((r) => <TR key={r.risk_id}><TD>{r.code} — {r.title}</TD><TD>{r.coverage === "full" ? "Complète" : "Partielle"}</TD>
              <TD>{r.assertion_codes.join(", ") || "—"}</TD><TD>{r.rationale ?? "—"}</TD>
              <TD className="text-right">{c.can_manage && <Button size="sm" variant="ghost" onClick={() => remove(r.risk_id)}>Dissocier</Button>}</TD></TR>)}</TBody></Table>
        )}
        {c.can_manage && risks && (
          <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_9rem_10rem_minmax(0,1fr)_auto]">
            <Select aria-label="Risque" value={f.risk_id} onChange={(x) => setF({ ...f, risk_id: x.target.value })}>
              <option value="">Associer un risque…</option>{risks.filter((r) => !linked.has(r.id) && r.status === "active").map((r) => <option key={r.id} value={r.id}>{r.code} — {r.title}</option>)}
            </Select>
            <Select aria-label="Couverture" value={f.coverage} onChange={(x) => setF({ ...f, coverage: x.target.value })}><option value="full">Complète</option><option value="partial">Partielle</option></Select>
            <Input aria-label="Assertions" placeholder="Assertions (codes)" value={f.assertions} onChange={(x) => setF({ ...f, assertions: x.target.value })} />
            <Input aria-label="Justification" placeholder="Justification" value={f.rationale} onChange={(x) => setF({ ...f, rationale: x.target.value })} />
            <Button size="sm" disabled={!f.risk_id} onClick={add}>Associer</Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function FrameworkLinks({ cid, c, onChanged }: { cid: string; c: Detail; onChanged: () => void }) {
  const { data: fw } = useApiResource<Fw>(c.can_manage ? `/companies/${cid}/ic/frameworks` : null);
  const [version, setVersion] = useState("");
  const [item, setItem] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const items = fw?.versions.find((v) => v.id === version)?.items.filter((i) => ITEM_TYPES[i.item_type]) ?? [];
  async function add() {
    setErr(null);
    try { await api.post(`/companies/${cid}/ic/framework-links`, { object_type: "control", object_id: c.id, item_id: item }); setItem(""); onChanged(); }
    catch (x) { setErr(errorMessage(x)); }
  }
  async function remove(id: string) {
    setErr(null);
    try { await api.del(`/companies/${cid}/ic/framework-links/${id}`); onChanged(); } catch (x) { setErr(errorMessage(x)); }
  }
  return (
    <Card><CardHeader><CardTitle>Référentiels applicables</CardTitle><CardDescription>Composantes, principes, exigences ou critères de méthodologies publiées auxquels le contrôle est rattaché.</CardDescription></CardHeader>
      <CardContent className="space-y-3">
        {err && <Alert>{err}</Alert>}
        {c.framework_links.length === 0 ? <p className="text-sm text-muted-foreground">Aucun rattachement.</p> : (
          <ul className="space-y-1 text-sm">{c.framework_links.map((l) => (
            <li key={l.id} className="flex items-center justify-between gap-2"><span><span className="text-muted-foreground">{l.framework} · {ITEM_TYPES[l.item_type] ?? l.item_type}</span> {l.code} — {l.label}</span>
              {c.can_manage && <Button size="sm" variant="ghost" onClick={() => remove(l.id)}>Retirer</Button>}</li>
          ))}</ul>
        )}
        {c.can_manage && fw && (
          fw.versions.filter((v) => v.status === "published").length === 0
            ? <p className="text-xs text-muted-foreground">Aucun référentiel publié : importez-en un depuis l&apos;espace Référentiels.</p>
            : <div className="grid gap-2 sm:grid-cols-[16rem_minmax(0,1fr)_auto]">
                <Select aria-label="Référentiel" value={version} onChange={(x) => { setVersion(x.target.value); setItem(""); }}>
                  <option value="">Référentiel…</option>{fw.versions.filter((v) => v.status === "published").map((v) => <option key={v.id} value={v.id}>{v.name} {v.version_label}</option>)}
                </Select>
                <Select aria-label="Élément" value={item} disabled={!version} onChange={(x) => setItem(x.target.value)}>
                  <option value="">Élément…</option>{items.map((i) => <option key={i.id} value={i.id}>{ITEM_TYPES[i.item_type]} {i.code} — {i.label}</option>)}
                </Select>
                <Button size="sm" disabled={!item} onClick={add}>Rattacher</Button>
              </div>
        )}
      </CardContent>
    </Card>
  );
}

function Executions({ cid, c, onChanged }: { cid: string; c: Detail; onChanged: () => void }) {
  const [f, setF] = useState({ occurrence_label: "", occurrence_date: "", outcome: "performed", comment: "", exceptions: "" });
  const [file, setFile] = useState<File | null>(null);
  const [sup, setSup] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function add(ev: React.FormEvent) {
    ev.preventDefault(); setBusy(true); setErr(null);
    const fd = new FormData();
    Object.entries(f).forEach(([k, v]) => { if (v.trim()) fd.append(k, v.trim()); });
    if (file) fd.append("file", file);
    try { await api.upload(`/companies/${cid}/ic/controls/${c.id}/executions`, fd); setF({ occurrence_label: "", occurrence_date: "", outcome: "performed", comment: "", exceptions: "" }); setFile(null); onChanged(); }
    catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }
  async function supervise(id: string, decision: "approved" | "rejected") {
    setErr(null);
    try { await api.post(`/companies/${cid}/ic/executions/${id}/supervise`, { decision, comment: (sup[id] ?? "").trim() || null }); onChanged(); }
    catch (x) { setErr(errorMessage(x)); }
  }
  async function download(id: string) {
    setErr(null);
    try { const r = await api.get<{ url: string }>(`/companies/${cid}/ic/executions/${id}/download`); window.open(r.url, "_blank", "noopener"); }
    catch (x) { setErr(errorMessage(x)); }
  }
  return (
    <Card><CardHeader><CardTitle>Exécutions du contrôle</CardTitle>
      <CardDescription>Documentées par l&apos;exécutant (preuve facultative, empreinte SHA-256), supervisées par une autre personne. Elles peuvent former la population d&apos;un test.</CardDescription></CardHeader>
      <CardContent className="space-y-3">
        {err && <Alert>{err}</Alert>}
        {c.can_execute && c.existence !== "absent" && c.existence !== "expected" && (
          <form onSubmit={add} className="space-y-2 rounded-md border p-3">
            <div className="grid gap-2 sm:grid-cols-3">
              <Field label="Occurrence" htmlFor="x-l" required><Input id="x-l" required placeholder="ex. rapprochement de mars" value={f.occurrence_label} onChange={(x) => setF({ ...f, occurrence_label: x.target.value })} /></Field>
              <Field label="Date" htmlFor="x-d" required><Input id="x-d" type="date" required value={f.occurrence_date} onChange={(x) => setF({ ...f, occurrence_date: x.target.value })} /></Field>
              <Field label="Résultat" htmlFor="x-o"><Select id="x-o" value={f.outcome} onChange={(x) => setF({ ...f, outcome: x.target.value })}>
                {Object.entries(OUTCOME).map(([k, [l]]) => <option key={k} value={k}>{l}</option>)}</Select></Field>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <Field label="Commentaire" htmlFor="x-c"><textarea id="x-c" rows={2} className={AREA} value={f.comment} onChange={(x) => setF({ ...f, comment: x.target.value })} /></Field>
              <Field label="Exceptions relevées" htmlFor="x-e" required={f.outcome === "performed_with_exceptions"}><textarea id="x-e" rows={2} className={AREA} value={f.exceptions} onChange={(x) => setF({ ...f, exceptions: x.target.value })} /></Field>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <input type="file" aria-label="Preuve" className="text-sm" onChange={(x) => setFile(x.target.files?.[0] ?? null)} />
              <Button type="submit" size="sm" loading={busy}>Documenter l&apos;exécution</Button>
            </div>
          </form>
        )}
        {c.executions.length === 0 ? <p className="text-sm text-muted-foreground">Aucune exécution documentée.</p> : (
          <Table><THead><tr><TH>Date</TH><TH>Occurrence</TH><TH>Résultat</TH><TH>Exécutant</TH><TH>Preuve</TH><TH>Supervision</TH></tr></THead>
            <TBody>{c.executions.map((x) => (
              <TR key={x.id}>
                <TD>{formatDate(x.occurrence_date)}</TD>
                <TD>{x.occurrence_label}{x.exceptions && <span className="block text-xs text-muted-foreground">Exceptions : {x.exceptions}</span>}</TD>
                <TD><Badge tone={OUTCOME[x.outcome]?.[1]}>{OUTCOME[x.outcome]?.[0]}</Badge></TD>
                <TD>{personName(x.performed_by)}</TD>
                <TD>{x.evidence_filename ? <Button size="sm" variant="ghost" onClick={() => download(x.id)}><Download className="h-4 w-4" /> {x.evidence_filename}</Button> : "—"}</TD>
                <TD>
                  <Badge tone={SUPERVISION[x.supervision_status]?.[1]}>{SUPERVISION[x.supervision_status]?.[0]}</Badge>
                  {x.supervised_by && <span className="block text-xs text-muted-foreground">{personName(x.supervised_by)}, {formatDate(x.supervised_at)}{x.supervision_comment && ` — ${x.supervision_comment}`}</span>}
                  {x.supervision_status === "pending" && c.can_supervise && (
                    <span className="mt-1 flex flex-wrap gap-1">
                      <Input aria-label="Commentaire de supervision" className="h-8 w-40" placeholder="Commentaire" value={sup[x.id] ?? ""} onChange={(e) => setSup({ ...sup, [x.id]: e.target.value })} />
                      <Button size="sm" variant="outline" onClick={() => supervise(x.id, "approved")}>Approuver</Button>
                      <Button size="sm" variant="ghost" onClick={() => supervise(x.id, "rejected")}>Rejeter</Button>
                    </span>
                  )}
                </TD>
              </TR>
            ))}</TBody></Table>
        )}
        <p className="text-xs text-muted-foreground">La base refuse qu&apos;une personne supervise une exécution qu&apos;elle a elle-même documentée.</p>
      </CardContent>
    </Card>
  );
}

function ControlHistory({ path }: { path: string }) {
  const [open, setOpen] = useState(false);
  const { data } = useApiResource<Hist[]>(open ? path : null);
  return (
    <Card><CardHeader className="flex flex-row items-center justify-between"><CardTitle>Historique</CardTitle>
      <Button size="sm" variant="ghost" onClick={() => setOpen(!open)}>{open ? "Masquer" : "Afficher"}</Button></CardHeader>
      {open && <CardContent>
        {!data ? <Loading /> : data.length === 0 ? <p className="text-sm text-muted-foreground">Aucune entrée.</p> : (
          <Table><THead><tr><TH>Date</TH><TH>Objet</TH><TH>Action</TH><TH>Champs modifiés</TH><TH>Par</TH></tr></THead>
            <TBody>{data.map((h, i) => <TR key={i}><TD>{formatDate(h.changed_at)}</TD><TD>{h.object_type}{h.version ? ` v${h.version}` : ""}</TD><TD>{h.action}</TD>
              <TD className="text-xs">{h.changed_fields.join(", ") || "—"}{h.reason && <span className="block text-muted-foreground">{h.reason}</span>}</TD><TD>{personName(h.changed_by)}</TD></TR>)}</TBody></Table>
        )}
      </CardContent>}
    </Card>
  );
}
