"use client";

import { useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { personName, type Engagement, type EvidenceItem } from "@/lib/types";
import {
  ANSWERS, CONCLUSION, DESIGN_CONCLUSION, ITEM_RESULT, SELECTION, TEST_METHODS, TEST_STATUS,
  type Answer, type Conclusion, type IcTestDetail, type IcTestItem,
} from "@/lib/ic-types";
import { formatAmount, formatDate } from "@/lib/utils";
import { AREA } from "@/components/ic-shell";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, Loading } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const nn = (v: string) => (v.trim() ? v.trim() : null);
const int = (v: string) => (v.trim() === "" ? null : Number(v));

function formOf(t: IcTestDetail) {
  return {
    reference: t.reference, test_methods: t.test_methods ?? [], objective: t.objective ?? "", test_procedure: t.test_procedure,
    period_start: t.period_start ?? "", period_end: t.period_end ?? "", population_description: t.population_description ?? "",
    population_size: t.population_size?.toString() ?? "", population_source: t.population_source ?? "", selection_method: t.selection_method ?? "",
    sample_size: t.sample_size?.toString() ?? "", sample_size_basis: t.sample_size_basis ?? "", acceptance_criteria: t.acceptance_criteria ?? "",
    tolerable_exceptions: t.tolerable_exceptions?.toString() ?? "", expected_result: t.expected_result ?? "",
    answers: { ...((t.test_type === "design" ? t.design_answers : t.operating_answers) ?? {}) } as Record<string, Answer>,
    results_summary: t.results_summary ?? "", exceptions_summary: t.exceptions_summary ?? "", conclusion: t.conclusion ?? "",
    conclusion_rationale: t.conclusion_rationale ?? "",
  };
}

/** Fiche d'un test de contrôle : paramètres, critères, éléments, preuves, conclusion, circuit préparateur / réviseur. */
export function TestDialog({ e, testId, onClose, onChanged }: { e: Engagement; testId: string; onClose: () => void; onChanged: () => void }) {
  const base = `/engagements/${e.id}/ic/tests/${testId}`;
  const caps = e.capabilities ?? [];
  const { data: t, setData, error } = useApiResource<IcTestDetail>(base);
  return (
    <Dialog open onClose={onClose} size="xl" title={t ? `Test ${t.reference} — ${t.test_type === "design" ? "conception" : "efficacité opérationnelle"}` : "Test"}
            description={t?.control ? `Contrôle ${t.control.code} — ${t.control.title}` : undefined}>
      {error && <Alert>{error}</Alert>}
      {!t ? <Loading /> : <TestBody e={e} t={t} caps={caps} base={base} onData={(x) => { setData(x); onChanged(); }} />}
    </Dialog>
  );
}

function TestBody({ e, t, caps, base, onData }: { e: Engagement; t: IcTestDetail; caps: string[]; base: string; onData: (t: IcTestDetail) => void }) {
  const editable = caps.includes("edit_procedures") && ["planned", "in_progress"].includes(t.status);
  const [f, setF] = useState(() => formOf(t));
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  async function run(key: string, fn: () => Promise<IcTestDetail | void>) {
    setBusy(key); setErr(null);
    try { const r = await fn(); if (r) { onData(r); setF(formOf(r)); } else { const fresh = await api.get<IcTestDetail>(base); onData(fresh); setF(formOf(fresh)); } }
    catch (x) { setErr(errorMessage(x)); } finally { setBusy(null); }
  }
  const save = () => run("save", () => api.patch<IcTestDetail>(base, {
    reference: f.reference, test_type: t.test_type, test_methods: f.test_methods, objective: nn(f.objective), test_procedure: f.test_procedure,
    risk_id: t.risk_id, procedure_id: t.procedure_id, workpaper_id: t.workpaper_id, responsible_user_id: t.responsible_user_id,
    period_start: f.period_start || null, period_end: f.period_end || null, population_description: nn(f.population_description),
    population_size: int(f.population_size), population_source: f.population_source || null, selection_method: f.selection_method || null,
    sample_size: int(f.sample_size), sample_size_basis: nn(f.sample_size_basis), acceptance_criteria: nn(f.acceptance_criteria),
    tolerable_exceptions: int(f.tolerable_exceptions), expected_result: nn(f.expected_result),
    [t.test_type === "design" ? "design_answers" : "operating_answers"]: f.answers,
    results_summary: nn(f.results_summary), exceptions_summary: nn(f.exceptions_summary), conclusion: f.conclusion || null,
    conclusion_rationale: nn(f.conclusion_rationale),
  }));
  const action = (a: "prepare" | "review" | "return" | "reopen") =>
    run(a, () => api.post<IcTestDetail>(`${base}/status`, { action: a, reason: nn(reason) }).then((r) => { setReason(""); return r; }));
  const txt = (k: "objective" | "test_procedure" | "population_description" | "sample_size_basis" | "acceptance_criteria" | "expected_result" | "results_summary" | "exceptions_summary" | "conclusion_rationale", label: string, rows = 2, required = false) => (
    <Field label={label} htmlFor={`t-${k}`} required={required}>
      <textarea id={`t-${k}`} rows={rows} className={AREA} disabled={!editable} value={f[k]} onChange={(x) => setF({ ...f, [k]: x.target.value })} />
    </Field>
  );
  const labels = t.test_type === "design" ? DESIGN_CONCLUSION : Object.fromEntries(Object.entries(CONCLUSION).map(([k, v]) => [k, v[0]]));
  const chosen = (f.conclusion || null) as Conclusion | null;
  const blockers = chosen ? t.check.blockers[chosen] ?? [] : [];
  return (
    <div className="space-y-5">
      {err && <Alert>{err}</Alert>}
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge tone={TEST_STATUS[t.status]?.[1]}>{TEST_STATUS[t.status]?.[0] ?? t.status}</Badge>
        {t.conclusion && <Badge tone={CONCLUSION[t.conclusion][1]}>{labels[t.conclusion]}</Badge>}
        <span className="text-muted-foreground">
          Préparé : {t.prepared_by_user ? `${personName(t.prepared_by_user)}, ${formatDate(t.prepared_at)}` : "—"} · Revu : {t.reviewed_by_user ? `${personName(t.reviewed_by_user)}, ${formatDate(t.reviewed_at)}` : "—"}
        </span>
        {t.reopen_reason && <span className="w-full text-xs text-muted-foreground">Motif de réouverture : {t.reopen_reason}</span>}
      </div>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold">Programme du test</h3>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Référence" htmlFor="t-ref" required><Input id="t-ref" disabled={!editable} value={f.reference} onChange={(x) => setF({ ...f, reference: x.target.value })} /></Field>
          <Field label="Début de période" htmlFor="t-ps" required={t.test_type === "operating"}><Input id="t-ps" type="date" disabled={!editable} value={f.period_start} onChange={(x) => setF({ ...f, period_start: x.target.value })} /></Field>
          <Field label="Fin de période" htmlFor="t-pe" required={t.test_type === "operating"}><Input id="t-pe" type="date" disabled={!editable} value={f.period_end} onChange={(x) => setF({ ...f, period_end: x.target.value })} /></Field>
        </div>
        <fieldset>
          <legend className="mb-1 text-sm font-medium">Nature du test</legend>
          <div className="flex flex-wrap gap-3">
            {Object.entries(TEST_METHODS).map(([k, l]) => (
              <label key={k} className="flex items-center gap-1.5 text-sm">
                <input type="checkbox" className="h-4 w-4" disabled={!editable} checked={f.test_methods.includes(k)}
                       onChange={(x) => setF({ ...f, test_methods: x.target.checked ? [...f.test_methods, k] : f.test_methods.filter((m) => m !== k) })} /> {l}
              </label>
            ))}
          </div>
        </fieldset>
        {txt("objective", "Objectif")}
        {txt("test_procedure", "Procédure de test", 3, true)}
        <div className="grid gap-3 sm:grid-cols-4">
          <Field label="Taille de la population" htmlFor="t-pz"><Input id="t-pz" type="number" min={0} disabled={!editable} value={f.population_size} onChange={(x) => setF({ ...f, population_size: x.target.value })} /></Field>
          <Field label="Méthode de sélection" htmlFor="t-sm"><Select id="t-sm" disabled={!editable} value={f.selection_method} onChange={(x) => setF({ ...f, selection_method: x.target.value })}>
            <option value="">—</option>{Object.entries(SELECTION).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select></Field>
          <Field label="Taille de l'échantillon" htmlFor="t-ss" hint="Fixée par vous ou votre méthodologie"><Input id="t-ss" type="number" min={1} disabled={!editable} value={f.sample_size} onChange={(x) => setF({ ...f, sample_size: x.target.value })} /></Field>
          <Field label="Exceptions tolérées" htmlFor="t-te"><Input id="t-te" type="number" min={0} disabled={!editable} value={f.tolerable_exceptions} onChange={(x) => setF({ ...f, tolerable_exceptions: x.target.value })} /></Field>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          {txt("population_description", "Population concernée")}
          {txt("sample_size_basis", "Fondement de la taille (obligatoire si une taille est saisie)")}
          {txt("acceptance_criteria", "Critères d'acceptation")}
          {txt("expected_result", "Résultat attendu")}
        </div>
      </section>

      <section className="space-y-2">
        <h3 className="text-sm font-semibold">{t.test_type === "design" ? "Évaluation de la conception" : "Évaluation de l'efficacité opérationnelle"}</h3>
        <Table>
          <THead><tr><TH>Critère</TH><TH className="w-40">Réponse</TH><TH>Commentaire</TH></tr></THead>
          <TBody>{Object.entries(t.criteria).map(([k, label]) => {
            const a = f.answers[k];
            return (
              <TR key={k}>
                <TD>{label}</TD>
                <TD><Select aria-label={label} disabled={!editable} value={a?.answer ?? ""} onChange={(x) => {
                  const next = { ...f.answers };
                  if (x.target.value) next[k] = { ...(a ?? {}), answer: x.target.value as Answer["answer"] }; else delete next[k];
                  setF({ ...f, answers: next });
                }}><option value="">Non évalué</option>{Object.entries(ANSWERS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></TD>
                <TD><Input aria-label={`Commentaire — ${label}`} disabled={!editable || !a} value={a?.comment ?? ""}
                           onChange={(x) => setF({ ...f, answers: { ...f.answers, [k]: { ...a!, comment: x.target.value } } })} /></TD>
              </TR>
            );
          })}</TBody>
        </Table>
      </section>

      <Items e={e} t={t} base={base} editable={caps.includes("edit_procedures") && ["planned", "in_progress"].includes(t.status)} onData={onData} />
      <Evidence e={e} t={t} canEdit={caps.includes("edit_procedures") && ["planned", "in_progress"].includes(t.status)} onDone={() => run("ev", async () => undefined)} />

      <section className="space-y-3">
        <h3 className="text-sm font-semibold">Résultats et conclusion</h3>
        <p className="text-xs text-muted-foreground">
          {t.check.items} élément(s) : {t.check.compliant} conforme(s), {t.check.exceptions} exception(s), {t.check.not_applicable} sans objet, {t.check.pending} à tester.
          Un contrôle n&apos;est jamais conclu efficace sur sa seule déclaration : critères, éléments, période et preuve sont exigés, et la base de données refait la vérification.
        </p>
        <div className="grid gap-3 sm:grid-cols-2">{txt("results_summary", "Synthèse des résultats")}{txt("exceptions_summary", "Anomalies relevées")}</div>
        <Field label="Conclusion" htmlFor="t-cc">
          <Select id="t-cc" disabled={!editable} value={f.conclusion} onChange={(x) => setF({ ...f, conclusion: x.target.value })}>
            <option value="">—</option>{(Object.keys(CONCLUSION) as Conclusion[]).map((c) => <option key={c} value={c}>{labels[c]}</option>)}
          </Select>
        </Field>
        {chosen && blockers.length > 0 && <Alert kind="info">Conclusion non permise en l&apos;état (données enregistrées) : {blockers.join(" ")}</Alert>}
        {txt("conclusion_rationale", f.conclusion === "not_applicable" ? "Justification (obligatoire pour « non applicable »)" : "Justification de la conclusion")}
        {editable && <div className="flex justify-end"><Button loading={busy === "save"} onClick={save}>Enregistrer le test</Button></div>}
      </section>

      <section className="space-y-2 border-t pt-3">
        <h3 className="text-sm font-semibold">Préparation et revue</h3>
        <p className="text-xs text-muted-foreground">Le préparateur ne peut pas revoir son propre test. Un test revu ne peut être modifié qu&apos;après une réouverture motivée.</p>
        {(t.status === "prepared" || t.status === "reviewed") && (
          <Input aria-label="Motif" placeholder="Motif (requis pour rouvrir un test revu)" value={reason} onChange={(x) => setReason(x.target.value)} />
        )}
        <div className="flex flex-wrap gap-2">
          {caps.includes("sign_preparer") && t.status === "in_progress" && <Button size="sm" loading={busy === "prepare"} onClick={() => action("prepare")}>Déclarer préparé</Button>}
          {caps.includes("sign_reviewer") && t.status === "prepared" && <Button size="sm" loading={busy === "review"} onClick={() => action("review")}>Revoir et valider</Button>}
          {caps.includes("sign_preparer") && t.status === "prepared" && <Button size="sm" variant="outline" loading={busy === "return"} onClick={() => action("return")}>Renvoyer en cours</Button>}
          {caps.includes("approve_ic") && t.status === "reviewed" && <Button size="sm" variant="outline" loading={busy === "reopen"} disabled={reason.trim().length < 3} onClick={() => action("reopen")}>Rouvrir</Button>}
        </div>
      </section>
    </div>
  );
}

function Items({ e, t, base, editable, onData }: { e: Engagement; t: IcTestDetail; base: string; editable: boolean; onData: (t: IcTestDetail) => void }) {
  const [mode, setMode] = useState<"none" | "manual" | "select">("none");
  const [lines, setLines] = useState("");
  const [sel, setSel] = useState({ source: "executions" as "executions" | "list", method: t.selection_method || "all", size: t.sample_size?.toString() ?? "", seed: "", approved_only: true });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function go(fn: () => Promise<unknown>) {
    setBusy(true); setErr(null);
    try { await fn(); onData(await api.get<IcTestDetail>(base)); setMode("none"); setLines(""); } catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }
  const parse = () => lines.split(/\r?\n/).map((l) => l.trim()).filter(Boolean).map((l) => {
    const [item_ref, description, item_date, amount] = l.split(";").map((x) => x?.trim() ?? "");
    return { item_ref, description: description || null, item_date: item_date || null, amount: amount ? amount.replace(",", ".") : null };
  });
  return (
    <section className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Éléments testés</h3>
        {editable && (
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={() => setMode(mode === "manual" ? "none" : "manual")}>Ajouter des éléments</Button>
            <Button size="sm" variant="outline" disabled={t.items.length > 0} onClick={() => setMode(mode === "select" ? "none" : "select")}>Sélectionner un échantillon</Button>
          </div>
        )}
      </div>
      {err && <Alert>{err}</Alert>}
      {mode === "manual" && (
        <div className="space-y-2 rounded-md border p-3">
          <Field label="Une ligne par élément : référence;libellé;date (AAAA-MM-JJ);montant" htmlFor="t-lines">
            <textarea id="t-lines" rows={4} className={AREA} value={lines} onChange={(x) => setLines(x.target.value)} />
          </Field>
          <Button size="sm" loading={busy} disabled={!lines.trim()} onClick={() => go(() => api.post(`${base}/items`, { items: parse() }))}>Ajouter</Button>
        </div>
      )}
      {mode === "select" && (
        <div className="space-y-2 rounded-md border p-3">
          <p className="text-xs text-muted-foreground">Moteur d&apos;échantillonnage du projet. La taille et la graine sont fournies par vous ; aucune taille n&apos;est proposée.</p>
          <div className="grid gap-2 sm:grid-cols-4">
            <Field label="Population" htmlFor="s-src"><Select id="s-src" value={sel.source} onChange={(x) => setSel({ ...sel, source: x.target.value as "executions" })}>
              <option value="executions">Exécutions documentées du contrôle (période du test)</option><option value="list">Liste collée</option></Select></Field>
            <Field label="Méthode" htmlFor="s-m"><Select id="s-m" value={sel.method} onChange={(x) => setSel({ ...sel, method: x.target.value })}>
              {Object.entries(SELECTION).filter(([k]) => k !== "judgmental").map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select></Field>
            <Field label="Taille" htmlFor="s-z"><Input id="s-z" type="number" min={1} disabled={sel.method === "all"} value={sel.size} onChange={(x) => setSel({ ...sel, size: x.target.value })} /></Field>
            <Field label="Graine" htmlFor="s-sd"><Input id="s-sd" type="number" disabled={sel.method === "all"} value={sel.seed} onChange={(x) => setSel({ ...sel, seed: x.target.value })} /></Field>
          </div>
          {sel.source === "executions" && <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="h-4 w-4" checked={sel.approved_only} onChange={(x) => setSel({ ...sel, approved_only: x.target.checked })} /> Exécutions supervisées et approuvées uniquement</label>}
          {sel.source === "list" && <Field label="Population : référence;libellé;date;montant" htmlFor="s-pop"><textarea id="s-pop" rows={4} className={AREA} value={lines} onChange={(x) => setLines(x.target.value)} /></Field>}
          <Button size="sm" loading={busy} onClick={() => go(() => api.post(`${base}/select`, {
            source: sel.source, method: sel.method, size: sel.method === "all" ? null : int(sel.size), seed: sel.method === "all" ? null : int(sel.seed),
            population_text: sel.source === "list" ? lines : null, approved_only: sel.approved_only,
          }))}>Sélectionner</Button>
        </div>
      )}
      {t.selection_params && Object.keys(t.selection_params).length > 0 && (
        <p className="text-xs text-muted-foreground">Paramètres de sélection conservés : {Object.entries(t.selection_params).map(([k, v]) => `${k} = ${String(v)}`).join(" · ")}</p>
      )}
      {t.items.length === 0 ? <p className="text-sm text-muted-foreground">Aucun élément.</p> : (
        <Table>
          <THead><tr><TH>#</TH><TH>Référence</TH><TH>Date</TH><TH className="text-right">Montant</TH><TH>Résultat</TH><TH>Détail</TH></tr></THead>
          <TBody>{t.items.map((i) => <ItemRow key={i.id} e={e} i={i} editable={editable} onDone={async () => onData(await api.get<IcTestDetail>(base))} />)}</TBody>
        </Table>
      )}
    </section>
  );
}

function ItemRow({ e, i, editable, onDone }: { e: Engagement; i: IcTestItem; editable: boolean; onDone: () => Promise<void> }) {
  const [v, setV] = useState({ result: i.result, exception_description: i.exception_description ?? "", na_reason: i.na_reason ?? "" });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const dirty = v.result !== i.result || v.exception_description !== (i.exception_description ?? "") || v.na_reason !== (i.na_reason ?? "");
  async function save() {
    setBusy(true); setErr(null);
    try { await api.patch(`/engagements/${e.id}/ic/test-items/${i.id}`, { result: v.result, exception_description: nn(v.exception_description), na_reason: nn(v.na_reason) }); await onDone(); }
    catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }
  async function del() {
    setBusy(true); setErr(null);
    try { await api.del(`/engagements/${e.id}/ic/test-items/${i.id}`); await onDone(); } catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }
  return (
    <TR>
      <TD>{i.selection_order ?? "—"}</TD>
      <TD>{i.item_ref}{i.description && <span className="block text-xs text-muted-foreground">{i.description}</span>}</TD>
      <TD>{formatDate(i.item_date)}</TD>
      <TD className="text-right tabular-nums">{i.amount ? formatAmount(i.amount) : "—"}</TD>
      <TD>{editable ? (
        <Select aria-label={`Résultat ${i.item_ref}`} value={v.result} onChange={(x) => setV({ ...v, result: x.target.value as IcTestItem["result"] })}>
          {Object.entries(ITEM_RESULT).map(([k, [l]]) => <option key={k} value={k}>{l}</option>)}
        </Select>
      ) : <Badge tone={ITEM_RESULT[i.result][1]}>{ITEM_RESULT[i.result][0]}</Badge>}
        {i.tested_by_user && <span className="block text-xs text-muted-foreground">{personName(i.tested_by_user)}</span>}</TD>
      <TD>
        {err && <span className="block text-xs text-destructive">{err}</span>}
        {editable && v.result === "exception" && <Input aria-label="Description de l'exception" placeholder="Exception constatée (requise)" value={v.exception_description} onChange={(x) => setV({ ...v, exception_description: x.target.value })} />}
        {editable && v.result === "not_applicable" && <Input aria-label="Motif" placeholder="Motif (requis)" value={v.na_reason} onChange={(x) => setV({ ...v, na_reason: x.target.value })} />}
        {!editable && (i.exception_description || i.na_reason)}
        {editable && (
          <span className="mt-1 flex gap-1">
            <Button size="sm" variant="outline" disabled={!dirty} loading={busy} onClick={save}>Enregistrer</Button>
            <Button size="sm" variant="ghost" disabled={busy} onClick={del}>Retirer</Button>
          </span>
        )}
      </TD>
    </TR>
  );
}

function Evidence({ e, t, canEdit, onDone }: { e: Engagement; t: IcTestDetail; canEdit: boolean; onDone: () => void }) {
  const { data: all } = useApiResource<EvidenceItem[]>(canEdit ? `/engagements/${e.id}/evidence` : null);
  const [ev, setEv] = useState("");
  const [target, setTarget] = useState(`control_test:${t.id}`);
  const [err, setErr] = useState<string | null>(null);
  async function link() {
    const [object_type, object_id] = target.split(":");
    setErr(null);
    try { await api.post(`/engagements/${e.id}/evidence/${ev}/links`, { object_type, object_id }); setEv(""); onDone(); } catch (x) { setErr(errorMessage(x)); }
  }
  async function unlink(id: string) {
    setErr(null);
    try { await api.del(`/engagements/${e.id}/evidence-links/${id}`); onDone(); } catch (x) { setErr(errorMessage(x)); }
  }
  const itemRef = (id: string) => t.items.find((i) => i.id === id)?.item_ref;
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold">Éléments probants</h3>
      <p className="text-xs text-muted-foreground">Preuves du dossier (onglet Éléments probants), protégées par empreinte SHA-256 ; rattachées au test ou à un élément testé.</p>
      {err && <Alert>{err}</Alert>}
      {t.evidence.length === 0 ? <p className="text-sm text-muted-foreground">Aucune preuve rattachée.</p> : (
        <ul className="space-y-1 text-sm">{t.evidence.map((x) => (
          <li key={x.link_id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border px-2 py-1">
            <span>{x.title} <span className="text-xs text-muted-foreground">· {x.object_type === "control_test" ? "test" : `élément ${itemRef(x.object_id) ?? ""}`} · {x.sha256.slice(0, 12)}…</span></span>
            {canEdit && <Button size="sm" variant="ghost" onClick={() => unlink(x.link_id)}>Détacher</Button>}
          </li>
        ))}</ul>
      )}
      {canEdit && (
        <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_14rem_auto]">
          <Select aria-label="Élément probant" value={ev} onChange={(x) => setEv(x.target.value)}>
            <option value="">Choisir une preuve du dossier…</option>{all?.map((x) => <option key={x.id} value={x.id}>{x.title}</option>)}
          </Select>
          <Select aria-label="Rattacher à" value={target} onChange={(x) => setTarget(x.target.value)}>
            <option value={`control_test:${t.id}`}>Le test</option>
            {t.items.map((i) => <option key={i.id} value={`control_test_item:${i.id}`}>Élément {i.item_ref}</option>)}
          </Select>
          <Button size="sm" disabled={!ev} onClick={link}>Rattacher</Button>
        </div>
      )}
    </section>
  );
}
