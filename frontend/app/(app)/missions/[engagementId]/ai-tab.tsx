"use client";

import { useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { personName, type Engagement } from "@/lib/types";
import { SUGGESTION_STATUS, type AiStatus, type AiSuggestion, type SuggestionKind } from "@/lib/ai-types";
import { formatDate } from "@/lib/utils";
import { AiDraftBadge, AiUnavailable, ContextView, NumberCheck } from "@/components/ai-common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, Badge, Loading } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";

type Data = { status: AiStatus; kinds: { kind: SuggestionKind; label: string; available: boolean; reason: string | null }[]; items: AiSuggestion[] };
const AREA = "w-full rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30";
const FIELD_LABELS: Record<string, string> = {
  code: "Code", title: "Intitulé", description: "Description", cycle_code: "Cycle", assertion_codes: "Assertions", rationale: "Justification",
  template_code: "Programme type", risk_codes: "Risques visés", condition: "Situation observée", criteria: "Critère de référence",
  cause: "Cause", effect: "Conséquence", recommendation: "Recommandation", text: "Texte", test: "Analyse", rank: "Ordre d'examen",
  explanation: "Explication", what_to_examine: "À examiner", reference: "Référence",
};
const EDIT: Record<SuggestionKind, string[]> = {
  engagement_risk: ["code", "title", "description"], procedure: ["code", "title"],
  finding_draft: ["reference", "title", "condition", "criteria", "cause", "effect", "recommendation"],
  synthesis_draft: ["title", "text"], anomaly_explanation: ["explanation", "what_to_examine"],
};
const CREATES: Record<SuggestionKind, string> = {
  engagement_risk: "Crée un risque de mission sans cotation (à coter ensuite).", procedure: "Crée la procédure du programme type, non attribuée.",
  finding_draft: "Crée un constat en brouillon (et sa recommandation), soumis au circuit de validation.",
  synthesis_draft: "Conserve le texte relu ; rien n'est créé dans le dossier.", anomaly_explanation: "Conserve l'explication relue ; rien n'est créé.",
};

/** Onglet « Assistant IA » : suggestions demandées au modèle, décidées par l'équipe. */
export function AiTab({ e }: { e: Engagement }) {
  const base = `/engagements/${e.id}/ai/suggestions`;
  const { data, error, reload } = useApiResource<Data>(base);
  const [filter, setFilter] = useState<"pending" | "all">("pending");
  if (error) return <Alert>{error}</Alert>;
  if (!data) return <Loading />;
  const items = data.items.filter((s) => filter === "all" || s.status === "pending");
  return (
    <div className="space-y-5">
      <AiUnavailable status={data.status} />
      <Alert kind="info">
        L&apos;IA propose à partir des données du dossier et de la méthodologie ; elle ne crée aucune preuve, ne signe, ne cote, ne valide ni ne conclut.
        Une suggestion acceptée devient un brouillon à votre nom, marqué « issu d&apos;une suggestion IA ».
      </Alert>
      {data.status.configured && <Generate e={e} kinds={data.kinds} onDone={reload} />}
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold">Suggestions</h2>
        <Select aria-label="Filtre" className="w-56" value={filter} onChange={(x) => setFilter(x.target.value as "all")}>
          <option value="pending">En attente de décision</option><option value="all">Toutes (historique)</option>
        </Select>
      </div>
      {items.length === 0 && <p className="text-sm text-muted-foreground">Aucune suggestion {filter === "pending" ? "en attente" : ""}.</p>}
      {items.map((s) => <SuggestionCard key={s.id} e={e} s={s} onDone={reload} />)}
    </div>
  );
}

function Generate({ e, kinds, onDone }: { e: Engagement; kinds: Data["kinds"]; onDone: () => void }) {
  const first = kinds.find((k) => k.available)?.kind ?? kinds[0].kind;
  const [kind, setKind] = useState<SuggestionKind>(first);
  const [req, setReq] = useState("");
  const [src, setSrc] = useState("");
  const [rm, setRm] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [res, setRes] = useState<{ created: string[]; discarded: string[] } | null>(null);
  const ic = ["internal_audit", "ic_assessment"].includes(e.engagement_type);
  const { data: wps } = useApiResource<{ id: string; reference: string; title: string }[]>(kind === "finding_draft" ? `/engagements/${e.id}/workpapers` : null);
  const { data: tests } = useApiResource<{ id: string; reference: string; control: string | null }[]>(kind === "finding_draft" && ic ? `/engagements/${e.id}/ic/tests` : null);
  const k = kinds.find((x) => x.kind === kind)!;
  async function go() {
    setBusy(true); setErr(null); setRes(null);
    const [source_type, source_id] = src ? src.split(":") : [null, null];
    try {
      setRes(await api.post(`/engagements/${e.id}/ai/suggestions`, { kind, request: req.trim() || null, source_type, source_id,
        round_multiple: rm ? Number(rm) : null }));
      onDone();
    } catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }
  return (
    <Card>
      <CardHeader><CardTitle>Demander des suggestions</CardTitle>
        <CardDescription>Le contexte transmis (données calculées du dossier, cartographie, méthodologie) est conservé avec chaque suggestion.</CardDescription></CardHeader>
      <CardContent className="space-y-3">
        {err && <Alert>{err}</Alert>}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Type" htmlFor="g-k"><Select id="g-k" value={kind} onChange={(x) => { setKind(x.target.value as SuggestionKind); setSrc(""); }}>
            {kinds.map((x) => <option key={x.kind} value={x.kind} disabled={!x.available}>{x.label}{x.available ? "" : " (indisponible)"}</option>)}</Select></Field>
          {kind === "finding_draft" && (
            <Field label="Source (travaux enregistrés)" htmlFor="g-s" required><Select id="g-s" value={src} onChange={(x) => setSrc(x.target.value)}>
              <option value="">—</option>
              {wps?.map((w) => <option key={w.id} value={`workpaper:${w.id}`}>Feuille {w.reference} — {w.title}</option>)}
              {tests?.map((t) => <option key={t.id} value={`control_test:${t.id}`}>Test {t.reference} — {t.control}</option>)}
            </Select></Field>
          )}
          {kind === "anomaly_explanation" && (
            <Field label="Multiple de montants ronds (facultatif)" htmlFor="g-rm" hint="Paramètre de l'analyse déterministe, fixé par vous"><Input id="g-rm" type="number" min={0} value={rm} onChange={(x) => setRm(x.target.value)} /></Field>
          )}
        </div>
        {!k.available && <p className="text-xs text-muted-foreground">{k.reason}</p>}
        <Field label="Précisions pour le modèle (facultatif)" htmlFor="g-r"><textarea id="g-r" rows={2} className={AREA} value={req} onChange={(x) => setReq(x.target.value)} /></Field>
        <div className="flex justify-end"><Button loading={busy} disabled={!k.available || (kind === "finding_draft" && !src)} onClick={go}>Demander</Button></div>
        {res && (
          <Alert kind={res.created.length ? "success" : "info"}>
            {res.created.length} suggestion(s) enregistrée(s).
            {res.discarded.length > 0 && <> Écartées par les contrôles de KOFINEX : {res.discarded.join(" ")}</>}
          </Alert>
        )}
      </CardContent>
    </Card>
  );
}

function show(v: unknown): string {
  if (Array.isArray(v)) return v.join(", ") || "—";
  if (v === null || v === undefined || v === "") return "—";
  return String(v);
}

function SuggestionCard({ e, s, onDone }: { e: Engagement; s: AiSuggestion; onDone: () => void }) {
  const [mode, setMode] = useState<"view" | "accept" | "reject">("view");
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [program, setProgram] = useState("");
  const [control, setControl] = useState("");
  const [note, setNote] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { data: programs } = useApiResource<{ id: string; code: string; title: string }[]>(mode === "accept" && s.kind === "procedure" ? `/engagements/${e.id}/programs` : null);
  const { data: reg } = useApiResource<{ controls: { id: string; code: string; title: string }[] }>(
    mode === "accept" && s.kind === "finding_draft" && e.engagement_type === "ic_assessment" ? `/engagements/${e.id}/ic/registry` : null);
  const shown = s.accepted_payload ?? s.payload;
  async function decide(action: "accept" | "reject") {
    setBusy(true); setErr(null);
    try {
      if (action === "accept") await api.post(`/engagements/${e.id}/ai/suggestions/${s.id}/accept`, { edits, program_id: program || null, control_id: control || null, note: note.trim() || null });
      else await api.post(`/engagements/${e.id}/ai/suggestions/${s.id}/reject`, { note });
      onDone();
    } catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-2">
        <div>
          <CardTitle className="flex flex-wrap items-center gap-2"><AiDraftBadge /> {s.kind_label}</CardTitle>
          <CardDescription>Demandée par {personName(s.requested_by_user)} le {formatDate(s.created_at)} · {s.model} · {s.prompt_version}</CardDescription>
        </div>
        <Badge tone={SUGGESTION_STATUS[s.status][1]}>{SUGGESTION_STATUS[s.status][0]}</Badge>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <dl className="grid gap-2 sm:grid-cols-2">
          {Object.entries(shown).map(([k, v]) => (
            <div key={k} className={["description", "rationale", "condition", "criteria", "text", "explanation"].includes(k) ? "sm:col-span-2" : ""}>
              <dt className="text-xs text-muted-foreground">{FIELD_LABELS[k] ?? k}</dt><dd className="whitespace-pre-line">{show(v)}</dd>
            </div>
          ))}
        </dl>
        <div className="flex flex-wrap items-center gap-2">
          <NumberCheck v={s.validation} />
          {s.sources.length > 0 && <span className="text-xs text-muted-foreground">Sources citées : {s.sources.join(", ")}</span>}
        </div>
        {s.validation.request && <p className="text-xs text-muted-foreground">Demande : {s.validation.request}</p>}
        {s.status !== "pending" && (
          <p className="text-xs text-muted-foreground">{s.status === "accepted" ? "Acceptée" : "Rejetée"} par {personName(s.decided_by_user)} le {formatDate(s.decided_at)}
            {s.decision_note && ` — ${s.decision_note}`}{s.created_object_id && " · objet créé en brouillon dans le dossier"}</p>
        )}
        {err && <Alert>{err}</Alert>}
        {s.status === "pending" && mode === "view" && (
          <div className="flex gap-2">
            <Button size="sm" onClick={() => setMode("accept")}>Relire et accepter</Button>
            <Button size="sm" variant="outline" onClick={() => setMode("reject")}>Rejeter</Button>
          </div>
        )}
        {mode === "accept" && (
          <div className="space-y-2 rounded-md border p-3">
            <p className="text-xs text-muted-foreground">{CREATES[s.kind]} Corrigez si besoin avant d&apos;accepter.</p>
            {EDIT[s.kind].map((k) => {
              const cur = edits[k] ?? show(s.payload[k]).replace(/^—$/, "");
              const long = ["description", "condition", "criteria", "cause", "effect", "recommendation", "text", "explanation", "what_to_examine"].includes(k);
              return (
                <Field key={k} label={FIELD_LABELS[k] ?? k} htmlFor={`e-${s.id}-${k}`} required={k === "reference"}>
                  {long ? <textarea id={`e-${s.id}-${k}`} rows={3} className={AREA} value={cur} onChange={(x) => setEdits({ ...edits, [k]: x.target.value })} />
                    : <Input id={`e-${s.id}-${k}`} value={cur} onChange={(x) => setEdits({ ...edits, [k]: x.target.value })} />}
                </Field>
              );
            })}
            {s.kind === "procedure" && (
              <Field label="Programme de travail" htmlFor={`p-${s.id}`} required><Select id={`p-${s.id}`} value={program} onChange={(x) => setProgram(x.target.value)}>
                <option value="">—</option>{programs?.map((p) => <option key={p.id} value={p.id}>{p.code} — {p.title}</option>)}</Select></Field>
            )}
            {reg && (
              <Field label="Contrôle concerné (déficience)" htmlFor={`c-${s.id}`} required><Select id={`c-${s.id}`} value={control} onChange={(x) => setControl(x.target.value)}>
                <option value="">—</option>{reg.controls.map((c) => <option key={c.id} value={c.id}>{c.code} — {c.title}</option>)}</Select></Field>
            )}
            <Input aria-label="Note" placeholder="Note de décision (facultatif)" value={note} onChange={(x) => setNote(x.target.value)} />
            <div className="flex gap-2">
              <Button size="sm" loading={busy} onClick={() => decide("accept")}>Accepter</Button>
              <Button size="sm" variant="ghost" onClick={() => setMode("view")}>Annuler</Button>
            </div>
          </div>
        )}
        {mode === "reject" && (
          <div className="flex gap-2">
            <Input aria-label="Motif du rejet" placeholder="Motif du rejet (requis)" value={note} onChange={(x) => setNote(x.target.value)} />
            <Button size="sm" variant="outline" loading={busy} disabled={note.trim().length < 3} onClick={() => decide("reject")}>Rejeter</Button>
            <Button size="sm" variant="ghost" onClick={() => setMode("view")}>Annuler</Button>
          </div>
        )}
        <ContextView s={s.context_snapshot} />
      </CardContent>
    </Card>
  );
}
