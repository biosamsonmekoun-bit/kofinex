"use client";

import { useState } from "react";
import { Download, Plus, Trash2 } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import type { Engagement } from "@/lib/types";
import {
  CONF_FORM_LABELS, CONF_STATUS, CONF_TYPE_LABELS, toDecimal, type ConfStatus, type FaConfirmation, type FaPopulation, type FaSample,
} from "@/lib/fa-types";
import { formatAmount, formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const AREA = "w-full rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30";
const today = () => new Date().toISOString().slice(0, 10);

function NewDialog({ e, open, onClose, onDone }: { e: Engagement; open: boolean; onClose: () => void; onDone: () => void }) {
  const base = `/engagements/${e.id}/fa`;
  const { data: pops } = useApiResource<FaPopulation[]>(open ? `${base}/populations` : null);
  const { data: samples } = useApiResource<FaSample[]>(open ? `${base}/samples` : null);
  const [mode, setMode] = useState<"single" | "population">("population");
  const [f, setF] = useState({ reference: "", confirmation_type: "receivable", third_party: "", contact: "", account_number: "",
    balance_date: e.period_end ?? "", book_balance: "", request_form: "positive", population_id: "", sample_id: "", reference_prefix: "C" });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    setBusy(true); setErr(null);
    try {
      if (mode === "single") {
        await api.post(`${base}/confirmations`, { reference: f.reference, confirmation_type: f.confirmation_type, third_party: f.third_party,
          contact: f.contact || null, account_number: f.account_number || null, balance_date: f.balance_date,
          book_balance: toDecimal(f.book_balance), request_form: f.request_form });
      } else {
        await api.post(`${base}/confirmations/from-population`, { population_id: f.population_id, sample_id: f.sample_id || null,
          confirmation_type: f.confirmation_type, balance_date: f.balance_date, request_form: f.request_form, reference_prefix: f.reference_prefix });
      }
      onDone();
    } catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }

  const popSamples = (samples ?? []).filter((s) => s.population_id === f.population_id);
  return (
    <Dialog open={open} onClose={onClose} title="Préparer des demandes de confirmation">
      <form onSubmit={submit} className="space-y-3">
        {err && <Alert>{err}</Alert>}
        <div className="flex gap-2">
          <Button type="button" size="sm" variant={mode === "population" ? "default" : "outline"} onClick={() => setMode("population")}>Depuis une population</Button>
          <Button type="button" size="sm" variant={mode === "single" ? "default" : "outline"} onClick={() => setMode("single")}>Demande unique</Button>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Type" htmlFor="cf-type">
            <Select id="cf-type" value={f.confirmation_type} onChange={(x) => setF({ ...f, confirmation_type: x.target.value })}>
              {Object.entries(CONF_TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </Select>
          </Field>
          <Field label="Forme" htmlFor="cf-form">
            <Select id="cf-form" value={f.request_form} onChange={(x) => setF({ ...f, request_form: x.target.value })}>
              {Object.entries(CONF_FORM_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </Select>
          </Field>
          <Field label="Date d'arrêté" htmlFor="cf-date" required><Input id="cf-date" type="date" required value={f.balance_date} onChange={(x) => setF({ ...f, balance_date: x.target.value })} /></Field>
        </div>
        {mode === "population" ? (
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Population" htmlFor="cf-pop" required>
              <Select id="cf-pop" value={f.population_id} onChange={(x) => setF({ ...f, population_id: x.target.value, sample_id: "" })}>
                <option value="">Choisir…</option>{pops?.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.item_count})</option>)}
              </Select>
            </Field>
            <Field label="Limiter à l'échantillon" htmlFor="cf-s">
              <Select id="cf-s" value={f.sample_id} onChange={(x) => setF({ ...f, sample_id: x.target.value })}>
                <option value="">Tous les éléments</option>{popSamples.map((s) => <option key={s.id} value={s.id}>{s.reference} ({s.selected_count})</option>)}
              </Select>
            </Field>
            <Field label="Préfixe des références" htmlFor="cf-pre"><Input id="cf-pre" value={f.reference_prefix} onChange={(x) => setF({ ...f, reference_prefix: x.target.value })} /></Field>
            <p className="text-xs text-muted-foreground sm:col-span-3">Une demande par élément : tiers = libellé de l&apos;élément, solde = son montant. Complétez ensuite les coordonnées.</p>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Référence" htmlFor="cf-ref" required><Input id="cf-ref" required value={f.reference} onChange={(x) => setF({ ...f, reference: x.target.value })} /></Field>
            <Field label="Tiers" htmlFor="cf-tp" required><Input id="cf-tp" required value={f.third_party} onChange={(x) => setF({ ...f, third_party: x.target.value })} /></Field>
            <Field label="Compte" htmlFor="cf-acc"><Input id="cf-acc" inputMode="numeric" value={f.account_number} onChange={(x) => setF({ ...f, account_number: x.target.value.replace(/\D/g, "") })} /></Field>
            <Field label="Solde comptable" htmlFor="cf-bal"><Input id="cf-bal" inputMode="decimal" value={f.book_balance} onChange={(x) => setF({ ...f, book_balance: x.target.value })} /></Field>
            <div className="sm:col-span-2"><Field label="Coordonnées" htmlFor="cf-ct"><Input id="cf-ct" value={f.contact} onChange={(x) => setF({ ...f, contact: x.target.value })} /></Field></div>
          </div>
        )}
        <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={onClose}>Annuler</Button><Button type="submit" loading={busy}>Préparer</Button></div>
      </form>
    </Dialog>
  );
}

function Detail({ e, c, onClose, onDone }: { e: Engagement; c: FaConfirmation; onClose: () => void; onDone: () => void }) {
  const url = `/engagements/${e.id}/fa/confirmations/${c.id}`;
  const [f, setF] = useState({ contact: c.contact ?? "", sent_on: c.sent_on ?? today(), reminder: today(), received_on: c.received_on ?? today(),
    confirmed_amount: c.confirmed_amount ?? "", reconciliation: c.reconciliation ?? "", alternative_procedures: c.alternative_procedures ?? "",
    conclusion: c.conclusion ?? "" });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const editable = (e.capabilities ?? []).includes("edit_procedures");
  const canReopen = (e.capabilities ?? []).includes("plan");

  async function patch(key: string, body: Record<string, unknown>) {
    setBusy(key); setErr(null);
    try { await api.patch(url, body); onDone(); } catch (x) { setErr(errorMessage(x)); } finally { setBusy(null); }
  }
  const diff = (() => { try { const a = toDecimal(f.confirmed_amount); return a !== null && c.book_balance !== null ? Number(c.book_balance) - Number(a) : null; } catch { return null; } })();
  const text = { reconciliation: f.reconciliation || null, alternative_procedures: f.alternative_procedures || null, conclusion: f.conclusion || null };

  return (
    <Dialog open onClose={onClose} title={`${c.reference} — ${c.third_party}`}
            description={`${CONF_TYPE_LABELS[c.confirmation_type]} · ${CONF_FORM_LABELS[c.request_form]} · arrêté au ${formatDate(c.balance_date)}${c.book_balance !== null ? ` · solde comptable ${formatAmount(c.book_balance)}` : ""}`}>
      <div className="space-y-3 text-sm">
        {err && <Alert>{err}</Alert>}
        <p><Badge tone={CONF_STATUS[c.status][1]}>{CONF_STATUS[c.status][0]}</Badge>
          {c.sent_on && ` · envoyée le ${formatDate(c.sent_on)}`}{c.reminder_dates.length > 0 && ` · relances : ${c.reminder_dates.map(formatDate).join(", ")}`}
          {c.received_on && ` · reçue le ${formatDate(c.received_on)}`}</p>
        {c.status === "prepared" && editable && (
          <>
            <Field label="Coordonnées du tiers" htmlFor="cd-ct"><Input id="cd-ct" value={f.contact} onChange={(x) => setF({ ...f, contact: x.target.value })} /></Field>
            <div className="flex items-end gap-2">
              <Field label="Envoyée le" htmlFor="cd-sent"><Input id="cd-sent" type="date" value={f.sent_on} onChange={(x) => setF({ ...f, sent_on: x.target.value })} /></Field>
              <Button loading={busy === "sent"} onClick={() => patch("sent", { contact: f.contact || null, status: "sent", sent_on: f.sent_on })}>Marquer envoyée</Button>
            </div>
          </>
        )}
        {(c.status === "sent" || c.status === "no_response") && editable && (
          <div className="space-y-3">
            {c.status === "sent" && (
              <div className="flex flex-wrap items-end gap-2">
                <Field label="Relance le" htmlFor="cd-rem"><Input id="cd-rem" type="date" value={f.reminder} onChange={(x) => setF({ ...f, reminder: x.target.value })} /></Field>
                <Button variant="outline" loading={busy === "rem"} onClick={() => patch("rem", { add_reminder: f.reminder })}>Enregistrer la relance</Button>
                <Button variant="outline" loading={busy === "nr"} onClick={() => patch("nr", { status: "no_response" })}>Sans réponse</Button>
              </div>
            )}
            <div className="flex flex-wrap items-end gap-2">
              <Field label="Reçue le" htmlFor="cd-rec"><Input id="cd-rec" type="date" value={f.received_on} onChange={(x) => setF({ ...f, received_on: x.target.value })} /></Field>
              <Field label="Montant confirmé" htmlFor="cd-amt"><Input id="cd-amt" inputMode="decimal" value={f.confirmed_amount} onChange={(x) => setF({ ...f, confirmed_amount: x.target.value })} /></Field>
              <Button loading={busy === "rec"} onClick={async () => {
                try { await patch("rec", { status: "received", received_on: f.received_on, confirmed_amount: toDecimal(f.confirmed_amount) }); } catch (x) { setErr(errorMessage(x)); }
              }}>Enregistrer la réponse</Button>
            </div>
            {diff !== null && diff !== 0 && <p className="text-xs">Écart prévisible : {formatAmount(diff.toFixed(2))}</p>}
            <p className="text-xs text-muted-foreground">Joignez la réponse reçue dans l&apos;onglet « Éléments probants ».</p>
          </div>
        )}
        {c.status === "received" && c.difference !== null && <p>Écart (comptable − confirmé) : <strong className="tabular-nums">{formatAmount(c.difference)}</strong></p>}
        {(c.status === "received" || c.status === "no_response") && editable && (
          <div className="space-y-3">
            {c.status === "received" && c.difference !== null && c.difference !== "0" && (
              <Field label="Rapprochement de l'écart (requis)" htmlFor="cd-rap"><textarea id="cd-rap" rows={2} className={AREA} value={f.reconciliation} onChange={(x) => setF({ ...f, reconciliation: x.target.value })} /></Field>
            )}
            {c.status === "no_response" && (
              <Field label={`Procédures alternatives${c.request_form !== "negative" ? " (requises)" : ""}`} htmlFor="cd-alt">
                <textarea id="cd-alt" rows={2} className={AREA} value={f.alternative_procedures} onChange={(x) => setF({ ...f, alternative_procedures: x.target.value })} />
              </Field>
            )}
            <Field label="Conclusion" htmlFor="cd-con"><textarea id="cd-con" rows={2} className={AREA} value={f.conclusion} onChange={(x) => setF({ ...f, conclusion: x.target.value })} /></Field>
            <div className="flex justify-end"><Button loading={busy === "close"} onClick={() => patch("close", { ...text, status: "closed" })}>Clore</Button></div>
          </div>
        )}
        {c.status === "closed" && (
          <div className="space-y-1">
            {c.reconciliation && <p><span className="text-muted-foreground">Rapprochement : </span>{c.reconciliation}</p>}
            {c.alternative_procedures && <p><span className="text-muted-foreground">Procédures alternatives : </span>{c.alternative_procedures}</p>}
            <p><span className="text-muted-foreground">Conclusion : </span>{c.conclusion}</p>
            {canReopen && <Button size="sm" variant="outline" loading={busy === "reopen"} onClick={() => patch("reopen", { status: c.received_on ? "received" : "no_response" })}>Rouvrir</Button>}
          </div>
        )}
      </div>
    </Dialog>
  );
}

export function FaConfirmationsPanel({ e, onChanged }: { e: Engagement; onChanged: () => void }) {
  const base = `/engagements/${e.id}/fa`;
  const { data, error, loading, reload } = useApiResource<FaConfirmation[]>(`${base}/confirmations`);
  const [open, setOpen] = useState(false);
  const [sel, setSel] = useState<FaConfirmation | null>(null);
  const [filter, setFilter] = useState<ConfStatus | "all">("all");
  const [err, setErr] = useState<string | null>(null);
  const canEdit = (e.capabilities ?? []).includes("edit_procedures");
  const done = async () => { setOpen(false); setSel(null); await reload(); onChanged(); };

  if (loading && !data) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  const rows = (data ?? []).filter((c) => filter === "all" || c.status === filter);
  const counts = (data ?? []).reduce<Record<string, number>>((a, c) => ({ ...a, [c.status]: (a[c.status] ?? 0) + 1 }), {});
  return (
    <div className="space-y-4">
      {err && <Alert>{err}</Alert>}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-sm text-muted-foreground">Préparation, envoi, relances, réponses, écarts et procédures alternatives. Une demande envoyée ne change plus et ne se supprime pas ; un écart se rapproche avant la clôture.</p>
        <div className="flex gap-2">
          {data && data.length > 0 && <Button size="sm" variant="outline" onClick={() => api.download(`${base}/confirmations.csv`, `circularisations-${e.reference}.csv`)}><Download className="h-4 w-4" /> Liste (CSV)</Button>}
          {canEdit && <Button size="sm" onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> Demandes</Button>}
        </div>
      </div>
      {data && data.length > 0 && (
        <div className="flex flex-wrap gap-2 text-xs">
          <Button size="sm" variant={filter === "all" ? "secondary" : "ghost"} onClick={() => setFilter("all")}>Toutes ({data.length})</Button>
          {(Object.keys(CONF_STATUS) as ConfStatus[]).filter((s) => counts[s]).map((s) => (
            <Button key={s} size="sm" variant={filter === s ? "secondary" : "ghost"} onClick={() => setFilter(s)}>{CONF_STATUS[s][0]} ({counts[s]})</Button>
          ))}
        </div>
      )}
      {data && data.length === 0 ? <EmptyState title="Aucune circularisation" /> : (
        <Table>
          <THead><tr><TH>Réf.</TH><TH>Tiers</TH><TH>Type</TH><TH className="text-right">Solde comptable</TH><TH className="text-right">Confirmé</TH><TH className="text-right">Écart</TH><TH>Statut</TH><TH /></tr></THead>
          <TBody>{rows.map((c) => (
            <TR key={c.id} className="cursor-pointer" onClick={() => setSel(c)}>
              <TD className="font-medium">{c.reference}</TD><TD>{c.third_party}</TD><TD>{CONF_TYPE_LABELS[c.confirmation_type]}</TD>
              <TD className="text-right tabular-nums">{formatAmount(c.book_balance)}</TD><TD className="text-right tabular-nums">{formatAmount(c.confirmed_amount)}</TD>
              <TD className="text-right tabular-nums">{c.difference && c.difference !== "0" ? <Badge tone="amber">{formatAmount(c.difference)}</Badge> : formatAmount(c.difference)}</TD>
              <TD><Badge tone={CONF_STATUS[c.status][1]}>{CONF_STATUS[c.status][0]}</Badge></TD>
              <TD>{canEdit && c.status === "prepared" && <Button size="icon" variant="ghost" aria-label={`Supprimer ${c.reference}`} onClick={async (x) => {
                x.stopPropagation(); try { await api.del(`${base}/confirmations/${c.id}`); await done(); } catch (y) { setErr(errorMessage(y)); } }}><Trash2 className="h-4 w-4" /></Button>}</TD>
            </TR>))}
          </TBody>
        </Table>
      )}
      <NewDialog e={e} open={open} onClose={() => setOpen(false)} onDone={done} />
      {sel && <Detail key={sel.id + sel.status} e={e} c={sel} onClose={() => setSel(null)} onDone={done} />}
    </div>
  );
}
