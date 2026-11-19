"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Copy, Download, Paperclip, RotateCcw, Trash2 } from "lucide-react";
import { AccountingShell } from "@/components/accounting-shell";
import { EntryEditor } from "@/components/entry-editor";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import type { EntryDetail } from "@/lib/accounting-types";
import { ORIGIN_LABEL, STATUS_LABEL, STATUS_TONE, amount } from "@/lib/accounting-types";
import { personName, type FiscalYear } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, Loading } from "@/components/ui/feedback";
import { Field, Input } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const EVENT_LABEL: Record<string, string> = {
  created: "Création", submitted: "Soumission", withdrawn: "Retrait de la soumission", review_started: "Mise en revue", validated: "Validation",
  rejected: "Rejet", returned_to_draft: "Reprise en brouillon", reversed: "Extourne", deleted: "Suppression",
};

export default function EntryPage() {
  const { companyId: cid, entryId } = useParams<{ companyId: string; entryId: string }>();
  return (
    <AccountingShell cid={cid} title="Écriture" needFy>
      {({ years }) => <EntryView cid={cid} id={entryId} years={years} />}
    </AccountingShell>
  );
}

function EntryView({ cid, id, years }: { cid: string; id: string; years: FiscalYear[] }) {
  const router = useRouter();
  const A = `/companies/${cid}/accounting/entries/${id}`;
  const { data: e, error, reload, setData } = useApiResource<EntryDetail>(A);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "error" | "success"; text: string } | null>(null);
  const [reject, setReject] = useState(false);
  const [reason, setReason] = useState("");
  const [rev, setRev] = useState(false);
  const [revDate, setRevDate] = useState("");
  const [withCorrection, setWithCorrection] = useState(true);

  if (error) return <Alert>{error}</Alert>;
  if (!e) return <Loading />;
  const fy = years.find((y) => y.id === e.fiscal_year_id);

  async function run(fn: () => Promise<unknown>, ok?: string) {
    setBusy(true); setMsg(null);
    try { await fn(); if (ok) setMsg({ kind: "success", text: ok }); }
    catch (err) { setMsg({ kind: "error", text: errorMessage(err) }); }
    finally { setBusy(false); }
  }
  const act = (action: string, extra: object = {}, ok?: string) =>
    run(async () => setData(await api.post<EntryDetail>(`${A}/transition`, { action, ...extra })), ok);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-xl font-semibold">{e.number ?? "Numéro attribué à la validation"}</h2>
        <Badge tone={STATUS_TONE[e.status]}>{STATUS_LABEL[e.status]}</Badge>
        <Badge>{ORIGIN_LABEL[e.origin]}</Badge>
        <span className="text-sm text-muted-foreground">{e.journal_code} · {e.journal_label}</span>
      </div>
      {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}
      {e.status === "rejected" && e.rejection_reason && <Alert kind="warning">Rejetée : {e.rejection_reason}</Alert>}
      {Object.values(e.related).map((r) => (
        <p key={r.id} className="text-sm">
          {r.id === e.reverses_entry_id ? "Extourne de " : r.id === e.corrects_entry_id ? "Correction de " : "Extournée par "}
          <Link className="text-link underline" href={`/companies/${cid}/comptabilite/ecritures/${r.id}`}>{r.number ?? r.label}</Link> ({STATUS_LABEL[r.status]})
        </p>
      ))}

      <div className="flex flex-wrap gap-2">
        {e.actions.submit && <Button disabled={busy || !e.check?.balanced} onClick={() => act("submit", {}, "Écriture soumise.")}>Soumettre</Button>}
        {e.actions.withdraw && <Button variant="outline" disabled={busy} onClick={() => act("withdraw")}>Retirer la soumission</Button>}
        {e.actions.start_review && <Button disabled={busy} onClick={() => act("start_review")}>Prendre en revue</Button>}
        {e.actions.validate && <Button disabled={busy} onClick={() => act("validate", {}, "Écriture validée : elle est désormais définitive.")}>Valider</Button>}
        {e.actions.reject && <Button variant="outline" disabled={busy} onClick={() => setReject(true)}>Rejeter</Button>}
        {e.actions.reopen && <Button variant="outline" disabled={busy} onClick={() => act("reopen")}>Reprendre en brouillon</Button>}
        {e.actions.reverse && <Button variant="outline" disabled={busy} onClick={() => { setRevDate(e.entry_date); setRev(true); }}><RotateCcw className="h-4 w-4" aria-hidden /> Extourner / corriger</Button>}
        {e.actions.duplicate && fy?.status === "open" && <Button variant="ghost" disabled={busy} onClick={() => run(async () => {
          const d = await api.post<EntryDetail>(`${A}/duplicate`); router.push(`/companies/${cid}/comptabilite/ecritures/${d.id}`);
        })}><Copy className="h-4 w-4" aria-hidden /> Dupliquer</Button>}
        {e.actions.delete && <Button variant="ghost" disabled={busy} onClick={() => run(async () => {
          await api.del(A); router.push(`/companies/${cid}/comptabilite`);
        })}><Trash2 className="h-4 w-4" aria-hidden /> Supprimer</Button>}
        {(e.status === "submitted" || e.status === "under_review") && !e.actions.validate && e.settings.segregation_required &&
          <span className="self-center text-xs text-muted-foreground">Séparation des tâches : la validation est faite par une autre personne que l&apos;auteur.</span>}
      </div>

      {e.actions.edit && fy ? (
        <EntryEditor cid={cid} fy={fy} entry={e} onSaved={(d) => { setData(d); setMsg({ kind: "success", text: "Brouillon enregistré." }); }} />
      ) : (
        <>
          <Card>
            <CardContent className="grid gap-3 pt-5 text-sm sm:grid-cols-3 lg:grid-cols-6">
              <Info label="Date" value={new Date(e.entry_date).toLocaleDateString("fr-FR")} />
              <Info label="Pièce" value={e.piece_ref ?? "—"} />
              <Info label="Date de pièce" value={e.piece_date ? new Date(e.piece_date).toLocaleDateString("fr-FR") : "—"} />
              <Info label="Tiers" value={e.third_party ? `${e.third_party.code} · ${e.third_party.name}` : "—"} />
              <Info label="Exercice" value={fy?.label ?? "—"} />
              <Info label="Libellé" value={e.label} />
            </CardContent>
          </Card>
          <Table>
            <THead><tr><TH>#</TH><TH>Compte</TH><TH>Intitulé</TH><TH>Tiers</TH><TH>Libellé</TH><TH className="text-right">Débit</TH><TH className="text-right">Crédit</TH></tr></THead>
            <TBody>
              {e.lines.map((l) => (
                <TR key={l.id}>
                  <TD className="text-xs text-muted-foreground">{l.line_no}</TD><TD className="font-medium">{l.account_number}</TD>
                  <TD className="text-xs">{l.account_label}</TD><TD className="text-xs">{l.third_party ? `${l.third_party.code} · ${l.third_party.name}` : ""}</TD>
                  <TD>{l.label ?? ""}</TD><TD className="text-right">{amount(l.debit, true)}</TD><TD className="text-right">{amount(l.credit, true)}</TD>
                </TR>
              ))}
              <TR className="bg-muted/40 font-semibold"><TD colSpan={5}>Totaux</TD><TD className="text-right">{amount(e.total_debit)}</TD><TD className="text-right">{amount(e.total_credit)}</TD></TR>
            </TBody>
          </Table>
        </>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Pièces justificatives</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            {!e.attachments.length && <p className="text-muted-foreground">Aucune pièce jointe.</p>}
            {e.attachments.map((a) => (
              <div key={a.document_id} className="flex items-center gap-2">
                <Paperclip className="h-4 w-4 text-muted-foreground" aria-hidden />
                <span className="flex-1 truncate">{a.filename}</span>
                <Button size="sm" variant="ghost" onClick={() => run(async () => {
                  const { url } = await api.get<{ url: string }>(`${A}/attachments/${a.document_id}/url`); window.open(url, "_blank", "noopener");
                })}><Download className="h-4 w-4" aria-hidden /> Ouvrir</Button>
                {e.actions.edit && <Button size="sm" variant="ghost" onClick={() => run(async () => { await api.del(`${A}/attachments/${a.document_id}`); await reload(); })}>Détacher</Button>}
              </div>
            ))}
            {(e.actions.edit || e.status === "submitted" || e.status === "under_review") && e.actions.duplicate && (
              <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-link">
                <input type="file" className="sr-only" accept=".pdf,.xlsx,.xls,.csv" onChange={(ev) => {
                  const f = ev.target.files?.[0]; if (!f) return;
                  const form = new FormData(); form.append("file", f);
                  void run(async () => { await api.upload(`${A}/attachments`, form); await reload(); }, "Pièce jointe.");
                  ev.target.value = "";
                }} />
                <Paperclip className="h-4 w-4" aria-hidden /> Joindre une pièce (PDF, Excel ou CSV)
              </label>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Historique du circuit</CardTitle></CardHeader>
          <CardContent>
            <ol className="space-y-2 text-sm">
              {e.events.map((ev, i) => (
                <li key={i} className="flex flex-wrap gap-x-2">
                  <span className="font-medium">{EVENT_LABEL[ev.action] ?? ev.action}</span>
                  <span className="text-muted-foreground">{new Date(ev.at).toLocaleString("fr-FR")} · {personName(ev.actor)}</span>
                  {ev.reason && <span className="w-full text-xs text-muted-foreground">{ev.reason}</span>}
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      </div>

      <Dialog open={reject} onClose={() => setReject(false)} title="Rejeter l'écriture" description="Le motif est conservé dans l'historique et communiqué à l'auteur.">
        <form onSubmit={(ev) => { ev.preventDefault(); void act("reject", { reason }, "Écriture rejetée.").then(() => setReject(false)); }} className="space-y-3">
          <Field label="Motif" htmlFor="rr" required><Input id="rr" value={reason} minLength={5} required onChange={(ev) => setReason(ev.target.value)} /></Field>
          <Button type="submit" disabled={busy || reason.trim().length < 5}>Rejeter</Button>
        </form>
      </Dialog>
      <Dialog open={rev} onClose={() => setRev(false)} title="Extourner l'écriture"
              description="Une écriture validée n'est jamais modifiée : l'extourne inverse ses lignes et suit le circuit de validation. La correction, en brouillon, reprend les lignes d'origine pour être rectifiée.">
        <form className="space-y-3" onSubmit={(ev) => { ev.preventDefault(); void run(async () => {
          const r = await api.post<{ reversal_id: string; correction_id: string | null }>(`${A}/reverse`, { entry_date: revDate, with_correction: withCorrection });
          router.push(`/companies/${cid}/comptabilite/ecritures/${r.correction_id ?? r.reversal_id}`);
        }); }}>
          <Field label="Date de l'extourne" htmlFor="rd" required hint="Dans le même exercice, au plus tôt à la date de l'écriture d'origine">
            <Input id="rd" type="date" value={revDate} min={e.entry_date} max={fy?.end_date} required onChange={(ev) => setRevDate(ev.target.value)} />
          </Field>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={withCorrection} onChange={(ev) => setWithCorrection(ev.target.checked)} /> Préparer aussi l&apos;écriture de correction</label>
          <Button type="submit" disabled={busy || !revDate}>Créer l&apos;extourne</Button>
        </form>
      </Dialog>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return <div><p className="text-xs text-muted-foreground">{label}</p><p className="font-medium">{value}</p></div>;
}
