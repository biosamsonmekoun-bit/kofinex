"use client";

import { useState } from "react";
import { Download, Pencil, Plus, Trash2 } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import type { Engagement } from "@/lib/types";
import {
  MS_KIND_LABELS, MS_STATUS, POSITION_LABELS, toDecimal, type FaAccount, type FaAggregate, type FaConfirmation, type FaMisstatement,
  type FaSample, type FaSummary, type MsStatus,
} from "@/lib/fa-types";
import { formatAmount, formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const AREA = "w-full rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30";
type Line = { account_number: string; label: string; debit: string; credit: string };
type Form = { reference: string; source_type: string; source_id: string; kind: string; description: string; lines: Line[] };
const EMPTY_LINE: Line = { account_number: "", label: "", debit: "", credit: "" };
const SOURCES = { sample: "Échantillon", confirmation: "Circularisation", account_review: "Revue d'un compte", analytical: "Revue analytique", other: "Autre" } as const;

function cents(v: string): number {
  try { const d = toDecimal(v); return d === null ? 0 : Math.round(Number(d) * 100); } catch { return NaN; }
}

function EditDialog({ e, initial, id, onClose, onDone }: { e: Engagement; initial: Form; id: string | null; onClose: () => void; onDone: () => void }) {
  const base = `/engagements/${e.id}/fa`;
  const [f, setF] = useState<Form>(initial);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { data: samples } = useApiResource<FaSample[]>(f.source_type === "sample" ? `${base}/samples` : null);
  const { data: confs } = useApiResource<FaConfirmation[]>(f.source_type === "confirmation" ? `${base}/confirmations` : null);
  const { data: accs } = useApiResource<{ accounts: FaAccount[] }>(f.source_type === "account_review" ? `${base}/account-reviews` : null);
  const td = f.lines.reduce((a, l) => a + cents(l.debit), 0);
  const tc = f.lines.reduce((a, l) => a + cents(l.credit), 0);
  const sources = f.source_type === "sample" ? (samples ?? []).map((s) => [s.id, `${s.reference} — constatée ${formatAmount(s.actual_misstatement)}, extrapolée ${formatAmount(s.projected_misstatement)}`])
    : f.source_type === "confirmation" ? (confs ?? []).map((c) => [c.id, `${c.reference} — ${c.third_party}${c.difference ? ` (écart ${formatAmount(c.difference)})` : ""}`])
    : f.source_type === "account_review" ? (accs?.accounts ?? []).map((a) => [a.id, `${a.account_number} ${a.account_label ?? ""}`]) : [];

  async function save(ev: React.FormEvent) {
    ev.preventDefault();
    setBusy(true); setErr(null);
    try {
      const body = { ...f, source_id: f.source_id || null,
        lines: f.lines.filter((l) => l.account_number).map((l) => ({ account_number: l.account_number, label: l.label || null,
          debit: toDecimal(l.debit) ?? "0", credit: toDecimal(l.credit) ?? "0" })) };
      if (id) await api.put(`${base}/misstatements/${id}`, body); else await api.post(`${base}/misstatements`, body);
      onDone();
    } catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }
  const setLine = (i: number, patch: Partial<Line>) => setF({ ...f, lines: f.lines.map((l, k) => (k === i ? { ...l, ...patch } : l)) });

  return (
    <Dialog open onClose={onClose} title={id ? "Modifier l'anomalie" : "Nouvelle anomalie"} description="L'écriture d'ajustement proposée doit être équilibrée ; son effet sur les états est calculé par le moteur des états financiers.">
      <form onSubmit={save} className="space-y-3">
        {err && <Alert>{err}</Alert>}
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Référence" htmlFor="ms-ref" required><Input id="ms-ref" required value={f.reference} onChange={(x) => setF({ ...f, reference: x.target.value })} /></Field>
          <Field label="Nature" htmlFor="ms-kind">
            <Select id="ms-kind" value={f.kind} onChange={(x) => setF({ ...f, kind: x.target.value, source_type: x.target.value === "projected" ? "sample" : f.source_type })}>
              {Object.entries(MS_KIND_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </Select>
          </Field>
          <Field label="Origine" htmlFor="ms-src">
            <Select id="ms-src" value={f.source_type} disabled={f.kind === "projected"} onChange={(x) => setF({ ...f, source_type: x.target.value, source_id: "" })}>
              {Object.entries(SOURCES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </Select>
          </Field>
        </div>
        {["sample", "confirmation", "account_review"].includes(f.source_type) && (
          <Field label="Source" htmlFor="ms-sid" required>
            <Select id="ms-sid" value={f.source_id} onChange={(x) => setF({ ...f, source_id: x.target.value })}>
              <option value="">Choisir…</option>{sources.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>
          </Field>
        )}
        <Field label="Description" htmlFor="ms-desc" required><textarea id="ms-desc" rows={2} className={AREA} required value={f.description} onChange={(x) => setF({ ...f, description: x.target.value })} /></Field>
        <div>
          <p className="mb-1 text-sm font-medium">Écriture d&apos;ajustement proposée</p>
          <div className="space-y-2">
            {f.lines.map((l, i) => (
              <div key={i} className="grid grid-cols-[7rem_minmax(0,1fr)_7rem_7rem_2.25rem] gap-2">
                <Input aria-label="Compte" inputMode="numeric" placeholder="Compte" value={l.account_number} onChange={(x) => setLine(i, { account_number: x.target.value.replace(/\D/g, "") })} />
                <Input aria-label="Libellé" placeholder="Libellé" value={l.label} onChange={(x) => setLine(i, { label: x.target.value })} />
                <Input aria-label="Débit" inputMode="decimal" placeholder="Débit" value={l.debit} onChange={(x) => setLine(i, { debit: x.target.value, credit: x.target.value ? "" : l.credit })} />
                <Input aria-label="Crédit" inputMode="decimal" placeholder="Crédit" value={l.credit} onChange={(x) => setLine(i, { credit: x.target.value, debit: x.target.value ? "" : l.debit })} />
                <Button type="button" variant="ghost" size="icon" aria-label="Retirer la ligne" disabled={f.lines.length <= 2} onClick={() => setF({ ...f, lines: f.lines.filter((_, k) => k !== i) })}><Trash2 className="h-4 w-4" /></Button>
              </div>
            ))}
          </div>
          <div className="mt-2 flex items-center justify-between text-sm">
            <Button type="button" size="sm" variant="outline" onClick={() => setF({ ...f, lines: [...f.lines, { ...EMPTY_LINE }] })}><Plus className="h-4 w-4" /> Ligne</Button>
            <span className={Number.isNaN(td + tc) || td !== tc ? "text-destructive" : "text-muted-foreground"}>
              Débit {formatAmount((td / 100).toFixed(2))} · Crédit {formatAmount((tc / 100).toFixed(2))}{td !== tc && " — déséquilibrée"}
            </span>
          </div>
        </div>
        <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={onClose}>Annuler</Button><Button type="submit" loading={busy} disabled={td !== tc || td === 0}>Enregistrer</Button></div>
      </form>
    </Dialog>
  );
}

function Decision({ e, m, onClose, onDone }: { e: Engagement; m: FaMisstatement; onClose: () => void; onDone: () => void }) {
  const [status, setStatus] = useState<MsStatus>(m.status === "proposed" ? "corrected" : "proposed");
  const [response, setResponse] = useState(m.entity_response ?? "");
  const [reason, setReason] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit() {
    setBusy(true); setErr(null);
    try {
      await api.post(`/engagements/${e.id}/fa/misstatements/${m.id}/decision`, { status, entity_response: response || null, withdrawn_reason: reason || null });
      onDone();
    } catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }
  const options: MsStatus[] = m.status === "proposed" ? ["corrected", "uncorrected", "withdrawn"] : m.status === "withdrawn" ? ["proposed"]
    : ["proposed", m.status === "corrected" ? "uncorrected" : "corrected"];
  return (
    <Dialog open onClose={onClose} title={`Décision — ${m.reference}`} description="Corrigée : l'entité passe l'écriture (elle entre dans la balance ajustée). Non corrigée : elle reste dans la synthèse.">
      <div className="space-y-3">
        {err && <Alert>{err}</Alert>}
        <Field label="Décision" htmlFor="dc-s">
          <Select id="dc-s" value={status} onChange={(x) => setStatus(x.target.value as MsStatus)}>{options.map((o) => <option key={o} value={o}>{o === "proposed" ? "Remettre en proposition" : MS_STATUS[o][0]}</option>)}</Select>
        </Field>
        {(status === "corrected" || status === "uncorrected") && <Field label="Réponse de l'entité (requise)" htmlFor="dc-r"><textarea id="dc-r" rows={2} className={AREA} value={response} onChange={(x) => setResponse(x.target.value)} /></Field>}
        {status === "withdrawn" && <Field label="Motif du retrait (requis)" htmlFor="dc-w"><textarea id="dc-w" rows={2} className={AREA} value={reason} onChange={(x) => setReason(x.target.value)} /></Field>}
        <div className="flex justify-end gap-2"><Button variant="outline" onClick={onClose}>Annuler</Button><Button loading={busy} onClick={submit}>Valider</Button></div>
      </div>
    </Dialog>
  );
}

function Aggregate({ title, a, description }: { title: string; a: FaAggregate; description: string }) {
  return (
    <Card>
      <CardHeader><CardTitle>{title} ({a.count})</CardTitle><CardDescription>{description}</CardDescription></CardHeader>
      <CardContent className="space-y-2 text-sm">
        {a.effects === null ? <p className="text-muted-foreground">Effets non calculables : référentiel publié requis pour l&apos;exercice.</p> : a.count === 0 ? <p className="text-muted-foreground">Aucune.</p> : (
          <>
            <p>Effet sur le résultat : <strong className="tabular-nums">{formatAmount(a.effect_result)}</strong> · sur le total de l&apos;actif : <strong className="tabular-nums">{formatAmount(a.effect_total_assets)}</strong></p>
            {a.position && <Badge tone={POSITION_LABELS[a.position][1]}>{POSITION_LABELS[a.position][0]}</Badge>}
            <Table>
              <THead><tr><TH>Ligne des états</TH><TH className="text-right">Publié</TH><TH className="text-right">Effet</TH><TH className="text-right">Après</TH></tr></THead>
              <TBody>{a.effects.map((x) => (
                <TR key={`${x.statement_type}-${x.code}`}><TD>{x.code} — {x.label}</TD><TD className="text-right tabular-nums">{formatAmount(x.before)}</TD>
                  <TD className="text-right tabular-nums">{formatAmount(x.delta)}</TD><TD className="text-right tabular-nums">{formatAmount(x.after)}</TD></TR>))}
              </TBody>
            </Table>
          </>
        )}
      </CardContent>
    </Card>
  );
}

export function FaMisstatementsPanel({ e, onChanged }: { e: Engagement; onChanged: () => void }) {
  const base = `/engagements/${e.id}/fa`;
  const { data, error, loading, reload } = useApiResource<FaMisstatement[]>(`${base}/misstatements`);
  const { data: summary, reload: reloadSummary, error: sumErr } = useApiResource<FaSummary>(`${base}/summary`);
  const [edit, setEdit] = useState<{ id: string | null; form: Form } | null>(null);
  const [decide, setDecide] = useState<FaMisstatement | null>(null);
  const [concl, setConcl] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const caps = e.capabilities ?? [];
  const done = async () => { setEdit(null); setDecide(null); await reload(); await reloadSummary(); onChanged(); };

  if (loading && !data) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  const effects = new Map((summary?.items ?? []).map((i) => [i.id, i]));
  return (
    <div className="space-y-5">
      {err && <Alert>{err}</Alert>}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-sm text-muted-foreground">
          Chaque anomalie porte une écriture d&apos;ajustement équilibrée. La balance validée n&apos;est jamais modifiée : la balance ajustée et les effets sont recalculés.
          La position par rapport aux seuils est une comparaison arithmétique ; la conclusion revient à l&apos;associé ou au manager.
        </p>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => api.download(`${base}/adjusted-balance?fmt=csv`, `balance-ajustee-${e.reference}.csv`)}><Download className="h-4 w-4" /> Balance ajustée</Button>
          {caps.includes("edit_procedures") && <Button size="sm" onClick={() => setEdit({ id: null, form: { reference: `AJ${(data?.length ?? 0) + 1}`, source_type: "other", source_id: "", kind: "factual", description: "", lines: [{ ...EMPTY_LINE }, { ...EMPTY_LINE }] } })}><Plus className="h-4 w-4" /> Anomalie</Button>}
        </div>
      </div>
      {data && data.length === 0 ? <EmptyState title="Aucune anomalie" /> : (
        <Table>
          <THead><tr><TH>Réf.</TH><TH>Anomalie</TH><TH>Nature</TH><TH className="text-right">Montant</TH><TH className="text-right">Effet sur le résultat</TH><TH>Statut</TH><TH /></tr></THead>
          <TBody>{data?.map((m) => {
            const fx = effects.get(m.id);
            return (
              <TR key={m.id}>
                <TD className="font-medium">{m.reference}</TD>
                <TD>{m.description}<p className="text-xs text-muted-foreground">{SOURCES[m.source_type as keyof typeof SOURCES]}{m.lines.map((l) => ` · ${l.account_number} ${l.debit !== "0" ? `D ${formatAmount(l.debit)}` : `C ${formatAmount(l.credit)}`}`).join("")}</p>
                  {m.entity_response && <p className="text-xs">Réponse de l&apos;entité : {m.entity_response}</p>}</TD>
                <TD>{MS_KIND_LABELS[m.kind]}</TD>
                <TD className="text-right tabular-nums">{formatAmount(fx?.amount)}</TD>
                <TD className="text-right tabular-nums">{fx?.effect_result != null ? formatAmount(fx.effect_result) : "—"}
                  {fx?.position && <p><Badge tone={POSITION_LABELS[fx.position][1]}>{fx.position === "below_trivial" ? "Insignifiante" : fx.position === "above_overall" ? "≥ seuil" : "< seuil"}</Badge></p>}</TD>
                <TD><Badge tone={MS_STATUS[m.status][1]}>{MS_STATUS[m.status][0]}</Badge>{m.decided_at && <p className="text-xs text-muted-foreground">{formatDate(m.decided_at)}</p>}</TD>
                <TD className="whitespace-nowrap text-right">
                  {caps.includes("decide_misstatements") && <Button size="sm" variant="outline" onClick={() => setDecide(m)}>Décision</Button>}
                  {caps.includes("edit_procedures") && m.status === "proposed" && <>
                    <Button size="icon" variant="ghost" aria-label={`Modifier ${m.reference}`} onClick={() => setEdit({ id: m.id, form: { reference: m.reference, source_type: m.source_type, source_id: m.source_id ?? "", kind: m.kind, description: m.description,
                      lines: m.lines.map((l) => ({ account_number: l.account_number, label: l.label ?? "", debit: l.debit === "0" ? "" : l.debit, credit: l.credit === "0" ? "" : l.credit })) } })}><Pencil className="h-4 w-4" /></Button>
                    <Button size="icon" variant="ghost" aria-label={`Supprimer ${m.reference}`} onClick={async () => { try { await api.del(`${base}/misstatements/${m.id}`); await done(); } catch (x) { setErr(errorMessage(x)); } }}><Trash2 className="h-4 w-4" /></Button>
                  </>}
                </TD>
              </TR>
            );
          })}</TBody>
        </Table>
      )}

      {sumErr && <Alert kind="warning">{sumErr}</Alert>}
      {summary && (
        <>
          {summary.materiality ? (
            <p className="text-sm">Seuils approuvés (v{summary.materiality.version}) : signification <strong>{formatAmount(summary.materiality.overall)}</strong> · planification {formatAmount(summary.materiality.performance)} · insignifiantes {formatAmount(summary.materiality.trivial)}</p>
          ) : <Alert kind="warning">Aucun seuil approuvé : les anomalies ne sont pas comparées aux seuils.</Alert>}
          <div className="grid gap-4 xl:grid-cols-2">
            <Aggregate title="Anomalies non corrigées" a={summary.uncorrected} description="Cumul à apprécier au regard du seuil de signification." />
            <Aggregate title="Ajustements corrigés par l'entité" a={summary.corrected} description="Différence entre les états publiés et les états ajustés." />
          </div>
          <Card>
            <CardHeader><CardTitle>Conclusion sur les anomalies non corrigées</CardTitle>
              <CardDescription>Requise avant l&apos;émission si au moins une anomalie n&apos;est pas corrigée. Rédigée par le manager ou l&apos;associé.</CardDescription></CardHeader>
            <CardContent className="space-y-2 text-sm">
              {summary.conclusion && concl === null && <p className="whitespace-pre-wrap">{summary.conclusion.text} <span className="text-xs text-muted-foreground">({formatDate(summary.conclusion.updated_at)})</span></p>}
              {caps.includes("conclude_misstatements") && (concl === null
                ? <Button size="sm" variant="outline" onClick={() => setConcl(summary.conclusion?.text ?? "")}>{summary.conclusion ? "Modifier" : "Rédiger"}</Button>
                : <>
                  <textarea aria-label="Conclusion" rows={4} className={AREA} value={concl} onChange={(x) => setConcl(x.target.value)} />
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" onClick={() => setConcl(null)}>Annuler</Button>
                    <Button size="sm" loading={busy} disabled={concl.trim().length < 10} onClick={async () => {
                      setBusy(true); setErr(null);
                      try { await api.put(`${base}/conclusion`, { text: concl }); setConcl(null); await reloadSummary(); onChanged(); } catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
                    }}>Enregistrer</Button>
                  </div>
                </>)}
              {!summary.conclusion && !caps.includes("conclude_misstatements") && <p className="text-muted-foreground">Non rédigée.</p>}
            </CardContent>
          </Card>
        </>
      )}
      {edit && <EditDialog e={e} initial={edit.form} id={edit.id} onClose={() => setEdit(null)} onDone={done} />}
      {decide && <Decision e={e} m={decide} onClose={() => setDecide(null)} onDone={done} />}
    </div>
  );
}
