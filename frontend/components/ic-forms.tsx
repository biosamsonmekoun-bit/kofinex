"use client";

import { useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { personName, type Methodology, type PersonRef } from "@/lib/types";
import {
  AUTOMATION, EXISTENCE, FREQUENCY, NATURE, TIMING, type IcControl, type IcDomain, type IcObjective, type IcProcess, type IcRisk,
} from "@/lib/ic-types";
import { formatDate } from "@/lib/utils";
import { AREA } from "@/components/ic-shell";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Loading } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

type Scale = { likelihood: { score: number; label: string }[]; impact: { score: number; label: string }[] };
type Level = { code: string; label: string };
const nn = (v: string) => (v.trim() ? v.trim() : null);
const num = (v: string) => (v ? Number(v) : null);

function Actions({ onClose, busy }: { onClose: () => void; busy: boolean }) {
  return <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={onClose}>Annuler</Button><Button type="submit" loading={busy}>Enregistrer</Button></div>;
}

export function ProcessDialog({ cid, proc, domains, processes, defaultDomain, onClose, onSaved }: {
  cid: string; proc: IcProcess | null; domains: IcDomain[]; processes: IcProcess[]; defaultDomain?: string | null; onClose: () => void; onSaved: () => void;
}) {
  const [f, setF] = useState({ code: proc?.code ?? "", name: proc?.name ?? "", parent_id: proc?.parent_id ?? "", domain_id: proc?.domain_id ?? defaultDomain ?? "",
    owner_name: proc?.owner_name ?? "", description: proc?.description ?? "", is_active: proc?.is_active ?? true });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function save(ev: React.FormEvent) {
    ev.preventDefault(); setBusy(true); setErr(null);
    const body = { code: f.code, name: f.name, parent_id: f.parent_id || null, domain_id: f.domain_id || null, owner_name: nn(f.owner_name),
      description: nn(f.description), is_active: f.is_active };
    try { if (proc) await api.patch(`/companies/${cid}/ic/processes/${proc.id}`, body); else await api.post(`/companies/${cid}/ic/processes`, body); onSaved(); }
    catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }
  return (
    <Dialog open onClose={onClose} title={proc ? `Processus ${proc.code}` : "Nouveau processus ou sous-processus"} description="Registre des processus partagé avec l'audit interne. Un sous-processus hérite du domaine de son parent.">
      <form onSubmit={save} className="space-y-3">
        {err && <Alert>{err}</Alert>}
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Code" htmlFor="p-c" required><Input id="p-c" required disabled={!!proc} value={f.code} onChange={(x) => setF({ ...f, code: x.target.value })} /></Field>
          <div className="sm:col-span-2"><Field label="Intitulé" htmlFor="p-n" required><Input id="p-n" required value={f.name} onChange={(x) => setF({ ...f, name: x.target.value })} /></Field></div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Domaine" htmlFor="p-d"><Select id="p-d" value={f.domain_id} onChange={(x) => setF({ ...f, domain_id: x.target.value })}>
            <option value="">—</option>{domains.map((d) => <option key={d.id} value={d.id}>{d.code} — {d.name}</option>)}</Select></Field>
          <Field label="Processus parent" htmlFor="p-p"><Select id="p-p" value={f.parent_id} onChange={(x) => setF({ ...f, parent_id: x.target.value })}>
            <option value="">—</option>{processes.filter((p) => p.id !== proc?.id).map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}</Select></Field>
        </div>
        <Field label="Responsable du processus" htmlFor="p-o"><Input id="p-o" value={f.owner_name} onChange={(x) => setF({ ...f, owner_name: x.target.value })} /></Field>
        <Field label="Description" htmlFor="p-de"><textarea id="p-de" rows={2} className={AREA} value={f.description} onChange={(x) => setF({ ...f, description: x.target.value })} /></Field>
        {proc && <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="h-4 w-4" checked={f.is_active} onChange={(x) => setF({ ...f, is_active: x.target.checked })} /> Actif</label>}
        <Actions onClose={onClose} busy={busy} />
      </form>
    </Dialog>
  );
}

export function RiskDialog({ cid, risk, domains, processes, objectives, defaultDomain, onClose, onSaved }: {
  cid: string; risk: IcRisk | null; domains: IcDomain[]; processes: IcProcess[]; objectives: IcObjective[]; defaultDomain?: string | null;
  onClose: () => void; onSaved: () => void;
}) {
  const [f, setF] = useState({ code: risk?.code ?? "", title: risk?.title ?? "", description: risk?.description ?? "", domain_id: risk?.domain_id ?? defaultDomain ?? "",
    process_id: risk?.process_id ?? "", objective_id: risk?.objective_id ?? "", category: risk?.category ?? "", causes: risk?.causes ?? "",
    consequences: risk?.consequences ?? "", owner_name: risk?.owner_name ?? "", cycle_code: risk?.cycle_code ?? "", scale_version_id: risk?.scale_version_id ?? "",
    il: String(risk?.inherent_likelihood ?? ""), ii: String(risk?.inherent_impact ?? ""), rl: String(risk?.residual_likelihood ?? ""),
    ri: String(risk?.residual_impact ?? ""), level: risk?.control_level_code ?? "", status: risk?.status ?? "active" });
  const { data: methods } = useApiResource<Methodology[]>("/methodologies");
  const { data: m } = useApiResource<{ items: { item_type: string; content: Scale & { levels?: Level[] } }[] }>(f.scale_version_id ? `/methodologies/${f.scale_version_id}` : null);
  const scale = m?.items.find((i) => i.item_type === "risk_scale")?.content;
  const levels = m?.items.find((i) => i.item_type === "control_level_scale")?.content.levels ?? [];
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function save(ev: React.FormEvent) {
    ev.preventDefault(); setBusy(true); setErr(null);
    const body = { code: f.code, title: f.title, description: nn(f.description), domain_id: f.domain_id || null, process_id: f.process_id || null,
      objective_id: f.objective_id || null, category: nn(f.category), causes: nn(f.causes), consequences: nn(f.consequences), owner_name: nn(f.owner_name),
      cycle_code: nn(f.cycle_code), scale_version_id: f.scale_version_id || null, inherent_likelihood: num(f.il), inherent_impact: num(f.ii),
      residual_likelihood: num(f.rl), residual_impact: num(f.ri), control_level_code: f.level || null, status: f.status };
    try { if (risk) await api.patch(`/companies/${cid}/ic/risks/${risk.id}`, body); else await api.post(`/companies/${cid}/ic/risks`, body); onSaved(); }
    catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }
  const lvl = (axis: "likelihood" | "impact", id: string, v: string, set: (s: string) => void) => (
    <Select id={id} value={v} onChange={(x) => set(x.target.value)} disabled={!scale}>
      <option value="">—</option>{scale?.[axis].map((l) => <option key={l.score} value={l.score}>{l.score} — {l.label}</option>)}
    </Select>
  );
  const text = (k: "causes" | "consequences" | "description", label: string) => (
    <Field label={label} htmlFor={`r-${k}`}><textarea id={`r-${k}`} rows={2} className={AREA} value={f[k]} onChange={(x) => setF({ ...f, [k]: x.target.value })} /></Field>
  );
  return (
    <Dialog open onClose={onClose} title={risk ? `Risque ${risk.code}` : "Nouveau risque"} description="Registre des risques partagé. Les cotations utilisent la grille de la méthodologie publiée choisie ; chaque modification est historisée.">
      <form onSubmit={save} className="space-y-3">
        {err && <Alert>{err}</Alert>}
        <div className="grid gap-3 sm:grid-cols-4">
          <Field label="Code" htmlFor="r-c" required><Input id="r-c" required value={f.code} onChange={(x) => setF({ ...f, code: x.target.value })} /></Field>
          <div className="sm:col-span-2"><Field label="Intitulé" htmlFor="r-t" required><Input id="r-t" required value={f.title} onChange={(x) => setF({ ...f, title: x.target.value })} /></Field></div>
          <Field label="Catégorie" htmlFor="r-cat"><Input id="r-cat" value={f.category} onChange={(x) => setF({ ...f, category: x.target.value })} /></Field>
        </div>
        {text("description", "Description")}
        <div className="grid gap-3 sm:grid-cols-2">{text("causes", "Causes")}{text("consequences", "Conséquences")}</div>
        <div className="grid gap-3 sm:grid-cols-4">
          <Field label="Domaine" htmlFor="r-d"><Select id="r-d" value={f.domain_id} onChange={(x) => setF({ ...f, domain_id: x.target.value })}>
            <option value="">—</option>{domains.map((d) => <option key={d.id} value={d.id}>{d.code} — {d.name}</option>)}</Select></Field>
          <Field label="Processus / sous-processus" htmlFor="r-p"><Select id="r-p" value={f.process_id} onChange={(x) => setF({ ...f, process_id: x.target.value })}>
            <option value="">—</option>{processes.filter((p) => !f.domain_id || p.domain_id === f.domain_id).map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}</Select></Field>
          <Field label="Objectif de contrôle" htmlFor="r-o"><Select id="r-o" value={f.objective_id} onChange={(x) => setF({ ...f, objective_id: x.target.value })}>
            <option value="">—</option>{objectives.map((o) => <option key={o.id} value={o.id}>{o.code} — {o.statement}</option>)}</Select></Field>
          <Field label="Cycle (code)" htmlFor="r-cy"><Input id="r-cy" value={f.cycle_code} onChange={(x) => setF({ ...f, cycle_code: x.target.value })} /></Field>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Propriétaire du risque" htmlFor="r-ow"><Input id="r-ow" value={f.owner_name} onChange={(x) => setF({ ...f, owner_name: x.target.value })} /></Field>
          <Field label="Grille de cotation (méthodologie publiée)" htmlFor="r-s"><Select id="r-s" value={f.scale_version_id} onChange={(x) => setF({ ...f, scale_version_id: x.target.value })}>
            <option value="">—</option>{methods?.filter((x) => x.status === "published").map((x) => <option key={x.id} value={x.id}>{x.name} {x.version_label}</option>)}</Select></Field>
        </div>
        <div className="grid gap-3 sm:grid-cols-5">
          <Field label="Probabilité inhérente" htmlFor="r-il">{lvl("likelihood", "r-il", f.il, (v) => setF({ ...f, il: v }))}</Field>
          <Field label="Impact inhérent" htmlFor="r-ii">{lvl("impact", "r-ii", f.ii, (v) => setF({ ...f, ii: v }))}</Field>
          <Field label="Niveau de maîtrise" htmlFor="r-lv"><Select id="r-lv" value={f.level} disabled={!levels.length} onChange={(x) => setF({ ...f, level: x.target.value })}>
            <option value="">—</option>{levels.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}</Select></Field>
          <Field label="Probabilité résiduelle" htmlFor="r-rl">{lvl("likelihood", "r-rl", f.rl, (v) => setF({ ...f, rl: v }))}</Field>
          <Field label="Impact résiduel" htmlFor="r-ri">{lvl("impact", "r-ri", f.ri, (v) => setF({ ...f, ri: v }))}</Field>
        </div>
        {f.scale_version_id && !levels.length && <p className="text-xs text-muted-foreground">Cette méthodologie ne contient pas d&apos;échelle de niveau de maîtrise (control_level_scale).</p>}
        {risk && <Field label="Statut" htmlFor="r-st"><Select id="r-st" value={f.status} onChange={(x) => setF({ ...f, status: x.target.value as "active" })}><option value="active">Actif</option><option value="retired">Retiré</option></Select></Field>}
        <Actions onClose={onClose} busy={busy} />
      </form>
    </Dialog>
  );
}

export function RiskHistory({ cid, risk, onClose }: { cid: string; risk: IcRisk; onClose: () => void }) {
  const { data } = useApiResource<{ inherent_likelihood: number | null; inherent_impact: number | null; residual_likelihood: number | null;
    residual_impact: number | null; control_level_code: string | null; changed_at: string; changed_by: PersonRef | null }[]>(`/companies/${cid}/ic/risks/${risk.id}/history`);
  const pair = (a: number | null, b: number | null) => (a && b ? `${a} × ${b} = ${a * b}` : "—");
  return (
    <Dialog open onClose={onClose} title={`Historique des évaluations — ${risk.code}`}>
      {!data ? <Loading /> : (
        <Table>
          <THead><tr><TH>Date</TH><TH>Inhérent</TH><TH>Maîtrise</TH><TH>Résiduel</TH><TH>Par</TH></tr></THead>
          <TBody>{data.map((h, i) => <TR key={i}><TD>{formatDate(h.changed_at)}</TD><TD>{pair(h.inherent_likelihood, h.inherent_impact)}</TD><TD>{h.control_level_code ?? "—"}</TD><TD>{pair(h.residual_likelihood, h.residual_impact)}</TD><TD>{personName(h.changed_by)}</TD></TR>)}</TBody>
        </Table>
      )}
    </Dialog>
  );
}

export function ControlDialog({ cid, control, domains, processes, objectives, defaultDomain, onClose, onSaved }: {
  cid: string; control: IcControl | null; domains: IcDomain[]; processes: IcProcess[]; objectives: IcObjective[]; defaultDomain?: string | null;
  onClose: () => void; onSaved: (c: IcControl) => void;
}) {
  const c = control;
  const [f, setF] = useState({
    code: c?.code ?? "", title: c?.title ?? "", description: c?.description ?? "", control_objective: c?.control_objective ?? "",
    domain_id: c?.domain_id ?? defaultDomain ?? "", process_id: c?.process_id ?? "", objective_id: c?.objective_id ?? "", existence: c?.existence ?? "existing",
    owner_name: c?.owner_name ?? "", performer_name: c?.performer_name ?? "", supervisor_name: c?.supervisor_name ?? "",
    performer_user_id: c?.performer_user_id ?? "", supervisor_user_id: c?.supervisor_user_id ?? "",
    frequency: c?.frequency ?? "", nature: c?.nature ?? "", automation: c?.automation ?? "", timing: c?.timing ?? "", execution_mode: c?.execution_mode ?? "",
    expected_evidence: c?.expected_evidence ?? "", procedure_text: c?.procedure_text ?? "", success_criteria: c?.success_criteria ?? "",
    is_key: c?.is_key ?? false, implemented_on: c?.implemented_on ?? "", operational_status: c?.operational_status ?? "active" });
  const { data: people } = useApiResource<PersonRef[]>(`/companies/${cid}/ic/candidates`);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function save(ev: React.FormEvent) {
    ev.preventDefault(); setBusy(true); setErr(null);
    const body = Object.fromEntries(Object.entries(f).map(([k, v]) => [k, typeof v === "string" ? (v.trim() || null) : v]));
    try { onSaved(c ? await api.patch<IcControl>(`/companies/${cid}/ic/controls/${c.id}`, body) : await api.post<IcControl>(`/companies/${cid}/ic/controls`, body)); }
    catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }
  const sel = (k: keyof typeof f, label: string, opts: Record<string, string>, id: string) => (
    <Field label={label} htmlFor={id} required={f.existence === "existing" && ["frequency", "nature", "automation"].includes(k as string)}>
      <Select id={id} value={String(f[k])} onChange={(x) => setF({ ...f, [k]: x.target.value })}>
        <option value="">—</option>{Object.entries(opts).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </Select>
    </Field>
  );
  const area = (k: "description" | "control_objective" | "execution_mode" | "expected_evidence" | "procedure_text" | "success_criteria", label: string, rows = 2) => (
    <Field label={label} htmlFor={`c-${k}`}><textarea id={`c-${k}`} rows={rows} className={AREA} value={f[k]} onChange={(x) => setF({ ...f, [k]: x.target.value })} /></Field>
  );
  const person = (k: "performer_user_id" | "supervisor_user_id", label: string) => (
    <Field label={label} htmlFor={`c-${k}`} hint="Compte utilisateur (droits d'exécution ou de supervision)">
      <Select id={`c-${k}`} value={f[k]} onChange={(x) => setF({ ...f, [k]: x.target.value })} disabled={!people}>
        <option value="">—</option>{people?.map((p) => <option key={p.id} value={p.id}>{personName(p)}</option>)}
      </Select>
    </Field>
  );
  return (
    <Dialog open onClose={onClose} title={c ? `Contrôle ${c.code} (version ${c.version})` : "Nouveau contrôle"}
            description="Un contrôle a toujours un responsable identifiable. Un contrôle « existant » est caractérisé (fréquence, nature, mode). Chaque modification crée une nouvelle version historisée.">
      <form onSubmit={save} className="space-y-3">
        {err && <Alert>{err}</Alert>}
        <div className="grid gap-3 sm:grid-cols-4">
          <Field label="Code" htmlFor="c-code" required><Input id="c-code" required value={f.code} onChange={(x) => setF({ ...f, code: x.target.value })} /></Field>
          <div className="sm:col-span-2"><Field label="Intitulé" htmlFor="c-t" required><Input id="c-t" required value={f.title} onChange={(x) => setF({ ...f, title: x.target.value })} /></Field></div>
          {sel("existence", "Statut du contrôle", Object.fromEntries(Object.entries(EXISTENCE).map(([k, v]) => [k, v[0]])), "c-ex")}
        </div>
        {area("description", "Description")}
        {area("control_objective", "Objectif du contrôle")}
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Domaine" htmlFor="c-d"><Select id="c-d" value={f.domain_id} onChange={(x) => setF({ ...f, domain_id: x.target.value })}>
            <option value="">—</option>{domains.map((d) => <option key={d.id} value={d.id}>{d.code} — {d.name}</option>)}</Select></Field>
          <Field label="Processus / sous-processus" htmlFor="c-p"><Select id="c-p" value={f.process_id} onChange={(x) => setF({ ...f, process_id: x.target.value })}>
            <option value="">—</option>{processes.filter((p) => !f.domain_id || p.domain_id === f.domain_id).map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}</Select></Field>
          <Field label="Objectif de contrôle (registre)" htmlFor="c-o"><Select id="c-o" value={f.objective_id} onChange={(x) => setF({ ...f, objective_id: x.target.value })}>
            <option value="">—</option>{objectives.map((o) => <option key={o.id} value={o.id}>{o.code} — {o.statement}</option>)}</Select></Field>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Responsable du contrôle" htmlFor="c-ow" required><Input id="c-ow" required value={f.owner_name} onChange={(x) => setF({ ...f, owner_name: x.target.value })} /></Field>
          <Field label="Exécutant (nom)" htmlFor="c-pn"><Input id="c-pn" value={f.performer_name} onChange={(x) => setF({ ...f, performer_name: x.target.value })} /></Field>
          <Field label="Superviseur (nom)" htmlFor="c-sn"><Input id="c-sn" value={f.supervisor_name} onChange={(x) => setF({ ...f, supervisor_name: x.target.value })} /></Field>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">{person("performer_user_id", "Exécutant (compte)")}{person("supervisor_user_id", "Superviseur (compte)")}</div>
        <div className="grid gap-3 sm:grid-cols-4">
          {sel("frequency", "Fréquence", FREQUENCY, "c-f")}{sel("nature", "Nature", NATURE, "c-n")}{sel("automation", "Mode", AUTOMATION, "c-a")}{sel("timing", "Permanent / périodique", TIMING, "c-ti")}
        </div>
        {area("execution_mode", "Mode d'exécution")}
        {area("procedure_text", "Procédure de contrôle (modalités d'exécution)", 4)}
        <div className="grid gap-3 sm:grid-cols-2">{area("expected_evidence", "Documents justificatifs attendus")}{area("success_criteria", "Critères de réussite")}</div>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Date de mise en place" htmlFor="c-im"><Input id="c-im" type="date" value={f.implemented_on} onChange={(x) => setF({ ...f, implemented_on: x.target.value })} /></Field>
          {sel("operational_status", "Statut opérationnel", { active: "Actif", suspended: "Suspendu", retired: "Retiré" }, "c-os")}
          <label className="mt-6 flex items-center gap-2 text-sm"><input type="checkbox" className="h-4 w-4" checked={f.is_key} onChange={(x) => setF({ ...f, is_key: x.target.checked })} /> Contrôle clé</label>
        </div>
        <Actions onClose={onClose} busy={busy} />
      </form>
    </Dialog>
  );
}

/** Données de référence des formulaires (domaines, processus, objectifs). */
export function useIcRefs(cid: string) {
  const d = useApiResource<IcDomain[]>(`/companies/${cid}/ic/domains`);
  const p = useApiResource<IcProcess[]>(`/companies/${cid}/ic/processes`);
  const o = useApiResource<IcObjective[]>(`/companies/${cid}/ic/objectives`);
  return { domains: d.data ?? [], processes: p.data ?? [], objectives: o.data ?? [],
           reload: async () => { await Promise.all([d.reload(), p.reload(), o.reload()]); } };
}
