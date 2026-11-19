"use client";

import { useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { personName, type Engagement } from "@/lib/types";
import {
  ASSESSMENT_STATUS, CONCLUSION, RELIANCE, SCOPES, TEST_METHODS, TEST_STATUS,
  type IcAssessment, type IcRegistry, type IcReliance, type IcTestBrief, type Synthesis,
} from "@/lib/ic-types";
import { formatDate } from "@/lib/utils";
import { AREA } from "@/components/ic-shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { TestDialog } from "./ic-test";

const FA_TYPES = ["statutory_audit", "contractual_audit"];
const nn = (v: string) => (v.trim() ? v.trim() : null);
type MissionTest = IcTestBrief & { procedure_id: string | null; sample_size: number | null };

/** Onglet « Contrôle interne » d'une mission : programme et tests (évaluation du CI, audit interne) ou prise en compte (audit financier). */
export function IcTab({ e }: { e: Engagement }) {
  if (FA_TYPES.includes(e.engagement_type)) return <Reliances e={e} />;
  return (
    <div className="space-y-6">
      <Tests e={e} />
      <Assessments e={e} />
      <p className="text-xs text-muted-foreground">
        Les déficiences se rédigent dans l&apos;onglet <Link className="text-link underline" href={`/missions/${e.id}?tab=findings`}>Constats et recommandations</Link> (nature
        « déficience de contrôle interne », rattachée au contrôle) et suivent le circuit du lot 8 : validation, communication, réponse, plan d&apos;action, vérification, clôture.
      </p>
    </div>
  );
}

function Tests({ e }: { e: Engagement }) {
  const caps = e.capabilities ?? [];
  const base = `/engagements/${e.id}/ic`;
  const { data, error, loading, reload } = useApiResource<MissionTest[]>(`${base}/tests`);
  const { data: reg } = useApiResource<IcRegistry>(caps.includes("read_findings") ? `${base}/registry` : null);
  const search = useSearchParams();
  const [open, setOpen] = useState<string | null>(search.get("test"));
  const [dialog, setDialog] = useState<"program" | "test" | null>(null);
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-2">
        <div>
          <CardTitle>Programme de contrôle et tests</CardTitle>
          <CardDescription>Tests de conception et d&apos;efficacité opérationnelle des contrôles de l&apos;entité, avec préparateur et réviseur distincts.</CardDescription>
        </div>
        {caps.includes("plan") && reg && (
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={() => setDialog("program")}>Créer un programme</Button>
            <Button size="sm" onClick={() => setDialog("test")}>Nouveau test</Button>
          </div>
        )}
      </CardHeader>
      <CardContent>
        {error && <Alert>{error}</Alert>}
        {loading && !data && <Loading />}
        {data && data.length === 0 && <EmptyState title="Aucun test" description="Créez un programme à partir du catalogue des contrôles de l'entité, ou un test isolé." />}
        {data && data.length > 0 && (
          <Table>
            <THead><tr><TH>Référence</TH><TH>Contrôle</TH><TH>Type</TH><TH>Période</TH><TH>Échantillon</TH><TH>Statut</TH><TH>Conclusion</TH></tr></THead>
            <TBody>{data.map((t) => (
              <TR key={t.id} className="cursor-pointer" onClick={() => setOpen(t.id)}>
                <TD><button type="button" className="text-link hover:underline" onClick={() => setOpen(t.id)}>{t.reference}</button></TD>
                <TD>{t.control}</TD>
                <TD>{t.test_type === "design" ? "Conception" : "Efficacité"}</TD>
                <TD>{t.period_start ? `${formatDate(t.period_start)} → ${formatDate(t.period_end)}` : "—"}</TD>
                <TD>{t.sample_size ?? "—"}</TD>
                <TD><Badge tone={TEST_STATUS[t.status]?.[1]}>{TEST_STATUS[t.status]?.[0] ?? t.status}</Badge></TD>
                <TD>{t.conclusion ? <Badge tone={CONCLUSION[t.conclusion][1]}>{t.conclusion_label}</Badge> : "—"}</TD>
              </TR>
            ))}</TBody>
          </Table>
        )}
      </CardContent>
      {open && <TestDialog e={e} testId={open} onClose={() => setOpen(null)} onChanged={reload} />}
      {dialog === "program" && reg && <ProgramDialog e={e} reg={reg} onClose={() => setDialog(null)} onDone={() => { setDialog(null); reload(); }} />}
      {dialog === "test" && reg && <NewTestDialog e={e} reg={reg} onClose={() => setDialog(null)} onDone={(id) => { setDialog(null); reload(); setOpen(id); }} />}
    </Card>
  );
}

function ControlPicker({ reg, value, onChange }: { reg: IcRegistry; value: string[]; onChange: (v: string[]) => void }) {
  const [domain, setDomain] = useState("");
  const list = reg.controls.filter((c) => !domain || c.domain_id === domain);
  return (
    <div className="space-y-2">
      <Select aria-label="Domaine" value={domain} onChange={(x) => setDomain(x.target.value)}>
        <option value="">Tous les domaines</option>{reg.domains.map((d) => <option key={d.id} value={d.id}>{d.code} — {d.name}</option>)}
      </Select>
      <div className="max-h-56 space-y-1 overflow-y-auto rounded-md border p-2">
        {list.length === 0 && <p className="text-sm text-muted-foreground">Aucun contrôle dans le catalogue de l&apos;entité.</p>}
        {list.map((c) => (
          <label key={c.id} className="flex items-center gap-2 text-sm">
            <input type="checkbox" className="h-4 w-4" checked={value.includes(c.id)}
                   onChange={(x) => onChange(x.target.checked ? [...value, c.id] : value.filter((v) => v !== c.id))} />
            {c.code} — {c.title} {c.is_key && <Badge tone="gold">Clé</Badge>} {c.existence !== "existing" && <Badge>{c.existence}</Badge>}
          </label>
        ))}
      </div>
    </div>
  );
}

function ProgramDialog({ e, reg, onClose, onDone }: { e: Engagement; reg: IcRegistry; onClose: () => void; onDone: () => void }) {
  const [f, setF] = useState({ code: "", title: "", objective: "", control_ids: [] as string[], design: true, operating: true,
    period_start: e.period_start ?? "", period_end: e.period_end ?? "" });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<number | null>(null);
  async function save(ev: React.FormEvent) {
    ev.preventDefault(); setBusy(true); setErr(null);
    try {
      const r = await api.post<{ tests: number }>(`/engagements/${e.id}/ic/program`, {
        code: f.code, title: f.title, objective: nn(f.objective), control_ids: f.control_ids,
        test_types: [f.design && "design", f.operating && "operating"].filter(Boolean), period_start: f.period_start || null, period_end: f.period_end || null,
      });
      setDone(r.tests);
    } catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }
  return (
    <Dialog open onClose={done !== null ? onDone : onClose} size="lg" title="Programme de contrôle"
            description="Crée un programme de travail de la mission (socle d'audit), une procédure et un test planifié par contrôle et par type de test.">
      {done !== null ? (
        <div className="space-y-3"><Alert kind="success">{done} test(s) planifié(s). Le programme figure aussi dans l&apos;onglet Programme.</Alert><div className="flex justify-end"><Button onClick={onDone}>Fermer</Button></div></div>
      ) : (
        <form onSubmit={save} className="space-y-3">
          {err && <Alert>{err}</Alert>}
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Code" htmlFor="pg-c" required><Input id="pg-c" required value={f.code} onChange={(x) => setF({ ...f, code: x.target.value })} /></Field>
            <div className="sm:col-span-2"><Field label="Intitulé" htmlFor="pg-t" required><Input id="pg-t" required value={f.title} onChange={(x) => setF({ ...f, title: x.target.value })} /></Field></div>
          </div>
          <Field label="Objectif" htmlFor="pg-o"><textarea id="pg-o" rows={2} className={AREA} value={f.objective} onChange={(x) => setF({ ...f, objective: x.target.value })} /></Field>
          <Field label="Contrôles à tester" htmlFor="pg-ctl" required><ControlPicker reg={reg} value={f.control_ids} onChange={(v) => setF({ ...f, control_ids: v })} /></Field>
          <div className="flex flex-wrap gap-4 text-sm">
            <label className="flex items-center gap-2"><input type="checkbox" className="h-4 w-4" checked={f.design} onChange={(x) => setF({ ...f, design: x.target.checked })} /> Tests de conception</label>
            <label className="flex items-center gap-2"><input type="checkbox" className="h-4 w-4" checked={f.operating} onChange={(x) => setF({ ...f, operating: x.target.checked })} /> Tests d&apos;efficacité opérationnelle</label>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Début de la période examinée" htmlFor="pg-ps"><Input id="pg-ps" type="date" value={f.period_start} onChange={(x) => setF({ ...f, period_start: x.target.value })} /></Field>
            <Field label="Fin de la période examinée" htmlFor="pg-pe"><Input id="pg-pe" type="date" value={f.period_end} onChange={(x) => setF({ ...f, period_end: x.target.value })} /></Field>
          </div>
          <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={onClose}>Annuler</Button>
            <Button type="submit" loading={busy} disabled={!f.control_ids.length || (!f.design && !f.operating)}>Créer le programme</Button></div>
        </form>
      )}
    </Dialog>
  );
}

function NewTestDialog({ e, reg, onClose, onDone }: { e: Engagement; reg: IcRegistry; onClose: () => void; onDone: (id: string) => void }) {
  const [f, setF] = useState({ control_id: "", risk_id: "", reference: "", test_type: "operating" as "design" | "operating", test_methods: [] as string[],
    test_procedure: "", period_start: e.period_start ?? "", period_end: e.period_end ?? "" });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function save(ev: React.FormEvent) {
    ev.preventDefault(); setBusy(true); setErr(null);
    try {
      const r = await api.post<{ id: string }>(`/engagements/${e.id}/ic/tests`, { ...f, risk_id: f.risk_id || null, period_start: f.period_start || null, period_end: f.period_end || null });
      onDone(r.id);
    } catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }
  return (
    <Dialog open onClose={onClose} size="lg" title="Nouveau test de contrôle">
      <form onSubmit={save} className="space-y-3">
        {err && <Alert>{err}</Alert>}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Contrôle" htmlFor="nt-c" required><Select id="nt-c" required value={f.control_id} onChange={(x) => setF({ ...f, control_id: x.target.value })}>
            <option value="">—</option>{reg.controls.map((c) => <option key={c.id} value={c.id}>{c.code} — {c.title}</option>)}</Select></Field>
          <Field label="Risque visé" htmlFor="nt-r"><Select id="nt-r" value={f.risk_id} onChange={(x) => setF({ ...f, risk_id: x.target.value })}>
            <option value="">—</option>{reg.risks.map((r) => <option key={r.id} value={r.id}>{r.code} — {r.title}</option>)}</Select></Field>
          <Field label="Référence" htmlFor="nt-ref" required><Input id="nt-ref" required value={f.reference} onChange={(x) => setF({ ...f, reference: x.target.value })} /></Field>
          <Field label="Type de test" htmlFor="nt-t"><Select id="nt-t" value={f.test_type} onChange={(x) => setF({ ...f, test_type: x.target.value as "design" })}>
            <option value="design">Test de conception</option><option value="operating">Test d&apos;efficacité opérationnelle</option></Select></Field>
          <Field label="Début de période" htmlFor="nt-ps"><Input id="nt-ps" type="date" value={f.period_start} onChange={(x) => setF({ ...f, period_start: x.target.value })} /></Field>
          <Field label="Fin de période" htmlFor="nt-pe"><Input id="nt-pe" type="date" value={f.period_end} onChange={(x) => setF({ ...f, period_end: x.target.value })} /></Field>
        </div>
        <div className="flex flex-wrap gap-3">{Object.entries(TEST_METHODS).map(([k, l]) => (
          <label key={k} className="flex items-center gap-1.5 text-sm"><input type="checkbox" className="h-4 w-4" checked={f.test_methods.includes(k)}
            onChange={(x) => setF({ ...f, test_methods: x.target.checked ? [...f.test_methods, k] : f.test_methods.filter((m) => m !== k) })} /> {l}</label>
        ))}</div>
        <Field label="Procédure de test" htmlFor="nt-p" required><textarea id="nt-p" required rows={3} className={AREA} value={f.test_procedure} onChange={(x) => setF({ ...f, test_procedure: x.target.value })} /></Field>
        <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={onClose}>Annuler</Button><Button type="submit" loading={busy}>Créer</Button></div>
      </form>
    </Dialog>
  );
}

function SynthesisLine({ s }: { s: Synthesis }) {
  return (
    <p className="text-xs text-muted-foreground">
      Règle {s.rule} : {s.controls} contrôle(s) — {s.effective} efficace(s), {s.partially_effective} partiellement, {s.ineffective} inefficace(s)
      {s.key_ineffective ? ` (dont ${s.key_ineffective} clé(s))` : ""}, {s.not_tested} non testé(s), {s.not_applicable} non applicable(s) ;
      {" "}{s.missing_controls} contrôle(s) attendu(s) ou absent(s) ; {s.uncovered_risks} risque(s) non couvert(s) sur {s.risks}.
    </p>
  );
}

function Assessments({ e }: { e: Engagement }) {
  const caps = e.capabilities ?? [];
  const base = `/engagements/${e.id}/ic`;
  const { data, error, reload } = useApiResource<{ levels: { code: string; label: string }[]; items: IcAssessment[] }>(`${base}/assessments`);
  const { data: reg } = useApiResource<IcRegistry>(caps.includes("read_findings") ? `${base}/registry` : null);
  const [edit, setEdit] = useState<IcAssessment | "new" | null>(null);
  const [reason, setReason] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string | null>(null);
  async function act(a: IcAssessment, action: "submit" | "approve" | "return") {
    setErr(null);
    try { await api.post(`${base}/assessments/${a.id}/status`, { action, reason: nn(reason[a.id] ?? "") }); await reload(); } catch (x) { setErr(errorMessage(x)); }
  }
  const scopeLabel = (a: IcAssessment) => {
    const name = a.domain_id ? reg?.domains.find((d) => d.id === a.domain_id)?.name : a.process_id ? reg?.processes.find((p) => p.id === a.process_id)?.name
      : a.risk_id ? reg?.risks.find((r) => r.id === a.risk_id)?.code : a.control_id ? reg?.controls.find((c) => c.id === a.control_id)?.code
      : a.framework_item_id ? reg?.components.find((c) => c.id === a.framework_item_id)?.label : a.cycle_code;
    return `${SCOPES[a.scope_type]}${name ? ` — ${name}` : ""}`;
  };
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-2">
        <div>
          <CardTitle>Évaluations du dispositif</CardTitle>
          <CardDescription>
            Niveau de maîtrise choisi sur l&apos;échelle de la méthodologie de la mission. La synthèse des tests revus est calculée et figée par la base à la soumission ;
            chaque évaluation reste consultable, une nouvelle évaluation ne remplace pas les précédentes.
          </CardDescription>
        </div>
        {caps.includes("edit_procedures") && reg && <Button size="sm" onClick={() => setEdit("new")}>Nouvelle évaluation</Button>}
      </CardHeader>
      <CardContent className="space-y-3">
        {error && <Alert>{error}</Alert>}
        {err && <Alert>{err}</Alert>}
        {data && !data.levels.length && <Alert kind="info">La méthodologie de la mission ne contient pas d&apos;échelle de niveau de maîtrise (control_level_scale) : la soumission est impossible tant qu&apos;elle n&apos;est pas définie.</Alert>}
        {data?.items.length === 0 && <p className="text-sm text-muted-foreground">Aucune évaluation.</p>}
        {data?.items.map((a) => (
          <div key={a.id} className="space-y-2 rounded-md border p-3 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-medium">{a.reference} · {scopeLabel(a)} · au {formatDate(a.as_of_date)}</span>
              <span className="flex items-center gap-2">
                {a.rating_label && <Badge tone="blue">{a.rating_label}</Badge>}
                <Badge tone={ASSESSMENT_STATUS[a.status]?.[1]}>{ASSESSMENT_STATUS[a.status]?.[0]}</Badge>
              </span>
            </div>
            {a.conclusion && <p className="whitespace-pre-line">{a.conclusion}</p>}
            {(a.basis ?? a.preview) && <SynthesisLine s={(a.basis ?? a.preview)!} />}
            {a.status === "draft" && a.preview && <p className="text-xs text-muted-foreground">Synthèse provisoire, recalculée à la soumission.</p>}
            <p className="text-xs text-muted-foreground">
              {a.prepared_by_user && `Préparée par ${personName(a.prepared_by_user)} le ${formatDate(a.prepared_at)}. `}
              {a.approved_by_user && `Approuvée par ${personName(a.approved_by_user)} le ${formatDate(a.approved_at)}.`}
              {a.return_reason && ` Renvoyée : ${a.return_reason}`}
            </p>
            <div className="flex flex-wrap gap-2">
              {a.status === "draft" && caps.includes("edit_procedures") && <Button size="sm" variant="outline" onClick={() => setEdit(a)}>Modifier</Button>}
              {a.status === "draft" && caps.includes("sign_preparer") && <Button size="sm" onClick={() => act(a, "submit")}>Soumettre</Button>}
              {a.status === "submitted" && caps.includes("approve_ic") && (
                <>
                  <Button size="sm" onClick={() => act(a, "approve")}>Approuver</Button>
                  <Input aria-label="Motif du renvoi" className="w-64" placeholder="Motif du renvoi" value={reason[a.id] ?? ""} onChange={(x) => setReason({ ...reason, [a.id]: x.target.value })} />
                  <Button size="sm" variant="outline" disabled={(reason[a.id] ?? "").trim().length < 3} onClick={() => act(a, "return")}>Renvoyer</Button>
                </>
              )}
            </div>
          </div>
        ))}
      </CardContent>
      {edit && reg && data && <AssessmentDialog e={e} reg={reg} levels={data.levels} a={edit === "new" ? null : edit} onClose={() => setEdit(null)} onDone={() => { setEdit(null); reload(); }} />}
    </Card>
  );
}

function AssessmentDialog({ e, reg, levels, a, onClose, onDone }: {
  e: Engagement; reg: IcRegistry; levels: { code: string; label: string }[]; a: IcAssessment | null; onClose: () => void; onDone: () => void;
}) {
  const [f, setF] = useState({ reference: a?.reference ?? "", scope_type: a?.scope_type ?? "overall", target: a?.domain_id ?? a?.process_id ?? a?.risk_id ?? a?.control_id ?? a?.framework_item_id ?? a?.cycle_code ?? "",
    as_of_date: a?.as_of_date ?? e.period_end ?? "", rating_code: a?.rating_code ?? "", conclusion: a?.conclusion ?? "" });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const options: Record<string, [string, string][]> = {
    domain: reg.domains.map((d) => [d.id, `${d.code} — ${d.name}`]), process: reg.processes.map((p) => [p.id, `${p.code} — ${p.name}`]),
    risk: reg.risks.map((r) => [r.id, `${r.code} — ${r.title}`]), control: reg.controls.map((c) => [c.id, `${c.code} — ${c.title}`]),
    component: reg.components.map((c) => [c.id, `${c.code} — ${c.label}`]), cycle: reg.cycles.map((c) => [c.code, `${c.code} — ${c.label}`]),
  };
  const key: Record<string, string> = { domain: "domain_id", process: "process_id", risk: "risk_id", control: "control_id", component: "framework_item_id", cycle: "cycle_code" };
  async function save(ev: React.FormEvent) {
    ev.preventDefault(); setBusy(true); setErr(null);
    const body: Record<string, unknown> = { reference: f.reference, scope_type: f.scope_type, as_of_date: f.as_of_date, rating_code: f.rating_code || null, conclusion: nn(f.conclusion) };
    if (key[f.scope_type]) body[key[f.scope_type]] = f.target || null;
    try {
      if (a) await api.patch(`/engagements/${e.id}/ic/assessments/${a.id}`, body); else await api.post(`/engagements/${e.id}/ic/assessments`, body);
      onDone();
    } catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }
  return (
    <Dialog open onClose={onClose} size="lg" title={a ? `Évaluation ${a.reference}` : "Nouvelle évaluation"}>
      <form onSubmit={save} className="space-y-3">
        {err && <Alert>{err}</Alert>}
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Référence" htmlFor="as-r" required><Input id="as-r" required value={f.reference} onChange={(x) => setF({ ...f, reference: x.target.value })} /></Field>
          <Field label="Niveau évalué" htmlFor="as-s"><Select id="as-s" value={f.scope_type} onChange={(x) => setF({ ...f, scope_type: x.target.value, target: "" })}>
            {Object.entries(SCOPES).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select></Field>
          <Field label="Date d'évaluation" htmlFor="as-d" required><Input id="as-d" type="date" required value={f.as_of_date} onChange={(x) => setF({ ...f, as_of_date: x.target.value })} /></Field>
        </div>
        {options[f.scope_type] && (
          <Field label={SCOPES[f.scope_type]} htmlFor="as-t" required><Select id="as-t" required value={f.target} onChange={(x) => setF({ ...f, target: x.target.value })}>
            <option value="">—</option>{options[f.scope_type].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></Field>
        )}
        {f.scope_type === "component" && !reg.components.length && <p className="text-xs text-muted-foreground">La méthodologie de la mission ne contient aucune composante ni principe.</p>}
        <Field label="Niveau de maîtrise (échelle de la méthodologie)" htmlFor="as-l" hint="Requis à la soumission"><Select id="as-l" value={f.rating_code} onChange={(x) => setF({ ...f, rating_code: x.target.value })}>
          <option value="">—</option>{levels.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}</Select></Field>
        <Field label="Conclusion motivée" htmlFor="as-c"><textarea id="as-c" rows={4} className={AREA} value={f.conclusion} onChange={(x) => setF({ ...f, conclusion: x.target.value })} /></Field>
        <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={onClose}>Annuler</Button><Button type="submit" loading={busy}>Enregistrer</Button></div>
      </form>
    </Dialog>
  );
}

type Candidate = IcTestBrief & { test_methods: string[]; control: string | null; is_key: boolean | null; conclusion_rationale: string | null };

function Reliances({ e }: { e: Engagement }) {
  const caps = e.capabilities ?? [];
  const base = `/engagements/${e.id}/ic`;
  const { data: rel, error, reload } = useApiResource<(IcReliance & Record<string, unknown>)[]>(`${base}/reliances`);
  const { data: cands } = useApiResource<Candidate[]>(`${base}/reliance-candidates`);
  const [pick, setPick] = useState<Candidate | null>(null);
  const [withdraw, setWithdraw] = useState<{ id: string; reason: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const used = new Set(rel?.map((r) => r.control_test_id));
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Prise en compte des tests de contrôle interne</CardTitle>
          <CardDescription>
            Décisions motivées de l&apos;équipe d&apos;audit financier sur des tests déjà revus. L&apos;appui exige un test d&apos;efficacité concluant dont la période recouvre
            la période auditée ; la période, le périmètre, la conclusion et les empreintes des preuves sont figés au moment de la décision.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {error && <Alert>{error}</Alert>}
          {err && <Alert>{err}</Alert>}
          {rel?.length === 0 && <p className="text-sm text-muted-foreground">Aucune décision.</p>}
          {rel?.map((r) => {
            const snap = (r.snapshot ?? {}) as { control?: { code?: string; title?: string }; test?: { reference?: string; period_start?: string; period_end?: string; conclusion?: string } };
            return (
              <div key={r.id} className="space-y-1 rounded-md border p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium">{snap.control?.code} — {snap.control?.title} · test {snap.test?.reference}</span>
                  <span className="flex gap-2"><Badge tone={RELIANCE[r.decision]?.[1]}>{RELIANCE[r.decision]?.[0]}</Badge>{r.status === "withdrawn" && <Badge>Retirée</Badge>}</span>
                </div>
                <p className="text-xs text-muted-foreground">Période testée {formatDate(snap.test?.period_start)} → {formatDate(snap.test?.period_end)} · {r.period_overlap ? "recouvre la période auditée" : "ne recouvre pas la période auditée"}
                  {r.cycle_code && ` · cycle ${r.cycle_code}`}{r.assertion_codes.length > 0 && ` · assertions ${r.assertion_codes.join(", ")}`}</p>
                <p>{r.rationale}</p>
                {r.approach_impact && <p className="text-xs">Adaptation de l&apos;approche : {r.approach_impact}</p>}
                <p className="text-xs text-muted-foreground">Décidé par {personName(r.decided_by)} le {formatDate(r.decided_at)}{r.withdrawn_reason && ` · retrait : ${r.withdrawn_reason}`}</p>
                {r.status === "active" && caps.includes("plan") && (withdraw?.id === r.id ? (
                  <div className="flex gap-2">
                    <Input aria-label="Motif du retrait" value={withdraw.reason} onChange={(x) => setWithdraw({ ...withdraw, reason: x.target.value })} placeholder="Motif (requis)" />
                    <Button size="sm" variant="outline" disabled={withdraw.reason.trim().length < 3} onClick={async () => {
                      setErr(null);
                      try { await api.post(`${base}/reliances/${r.id}/withdraw`, { reason: withdraw.reason }); setWithdraw(null); await reload(); } catch (x) { setErr(errorMessage(x)); }
                    }}>Retirer</Button>
                  </div>
                ) : <Button size="sm" variant="ghost" onClick={() => setWithdraw({ id: r.id, reason: "" })}>Retirer la décision</Button>)}
              </div>
            );
          })}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Tests revus disponibles</CardTitle><CardDescription>Tests de contrôles de l&apos;entité revus dans d&apos;autres missions et visibles pour vous.</CardDescription></CardHeader>
        <CardContent>
          {!cands ? <Loading /> : cands.length === 0 ? <p className="text-sm text-muted-foreground">Aucun test revu disponible.</p> : (
            <Table>
              <THead><tr><TH>Contrôle</TH><TH>Test</TH><TH>Type</TH><TH>Période</TH><TH>Conclusion</TH><TH /></tr></THead>
              <TBody>{cands.map((c) => (
                <TR key={c.id}>
                  <TD>{c.control} {c.is_key && <Badge tone="gold">Clé</Badge>}</TD><TD>{c.reference}</TD>
                  <TD>{c.test_type === "design" ? "Conception" : "Efficacité"}</TD>
                  <TD>{c.period_start ? `${formatDate(c.period_start)} → ${formatDate(c.period_end)}` : "—"}</TD>
                  <TD>{c.conclusion ? <Badge tone={CONCLUSION[c.conclusion][1]}>{c.conclusion_label}</Badge> : "—"}</TD>
                  <TD>{caps.includes("plan") && !used.has(c.id) && <Button size="sm" variant="outline" onClick={() => setPick(c)}>Décider</Button>}</TD>
                </TR>
              ))}</TBody>
            </Table>
          )}
        </CardContent>
      </Card>
      {pick && <RelianceDialog e={e} c={pick} onClose={() => setPick(null)} onDone={() => { setPick(null); reload(); }} />}
    </div>
  );
}

function RelianceDialog({ e, c, onClose, onDone }: { e: Engagement; c: Candidate; onClose: () => void; onDone: () => void }) {
  const [f, setF] = useState({ decision: c.test_type === "operating" && c.conclusion === "effective" ? "rely" : "no_reliance", cycle_code: "", assertions: "", rationale: "", approach_impact: "" });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function save(ev: React.FormEvent) {
    ev.preventDefault(); setBusy(true); setErr(null);
    try {
      await api.post(`/engagements/${e.id}/ic/reliances`, { control_test_id: c.id, decision: f.decision, cycle_code: nn(f.cycle_code),
        assertion_codes: f.assertions.split(",").map((x) => x.trim()).filter(Boolean), rationale: f.rationale, approach_impact: nn(f.approach_impact) });
      onDone();
    } catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }
  return (
    <Dialog open onClose={onClose} title={`Prise en compte — ${c.reference}`} description={c.conclusion_rationale ?? undefined}>
      <form onSubmit={save} className="space-y-3">
        {err && <Alert>{err}</Alert>}
        <Field label="Décision" htmlFor="rl-d"><Select id="rl-d" value={f.decision} onChange={(x) => setF({ ...f, decision: x.target.value })}>
          {Object.entries(RELIANCE).map(([k, [l]]) => <option key={k} value={k}>{l}</option>)}</Select></Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Cycle (code)" htmlFor="rl-c"><Input id="rl-c" value={f.cycle_code} onChange={(x) => setF({ ...f, cycle_code: x.target.value })} /></Field>
          <Field label="Assertions (codes, séparés par des virgules)" htmlFor="rl-a"><Input id="rl-a" value={f.assertions} onChange={(x) => setF({ ...f, assertions: x.target.value })} /></Field>
        </div>
        <Field label="Motivation" htmlFor="rl-r" required><textarea id="rl-r" required rows={3} className={AREA} value={f.rationale} onChange={(x) => setF({ ...f, rationale: x.target.value })} /></Field>
        <Field label="Adaptation de l'approche d'audit" htmlFor="rl-i"><textarea id="rl-i" rows={2} className={AREA} value={f.approach_impact} onChange={(x) => setF({ ...f, approach_impact: x.target.value })} /></Field>
        <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={onClose}>Annuler</Button><Button type="submit" loading={busy}>Enregistrer</Button></div>
      </form>
    </Dialog>
  );
}
