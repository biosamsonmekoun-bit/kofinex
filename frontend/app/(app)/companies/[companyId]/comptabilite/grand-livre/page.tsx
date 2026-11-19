"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Download } from "lucide-react";
import { AccountingShell } from "@/components/accounting-shell";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import type { Journal, LedgerAccount, ThirdParty } from "@/lib/accounting-types";
import { ORIGIN_LABEL, amount } from "@/lib/accounting-types";
import { Button } from "@/components/ui/button";
import { Alert, EmptyState, Loading } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";

/** Grand livre calculé à partir des écritures natives validées (distinct du grand livre importé). */
export default function NativeLedgerPage() {
  const { companyId: cid } = useParams<{ companyId: string }>();
  return (
    <AccountingShell cid={cid} title="Grand livre" needFy description="Écritures natives validées uniquement ; le grand livre importé reste consultable dans « Grand livre importé » de l'entreprise.">
      {({ fy }) => <Ledger cid={cid} fyId={fy!.id} />}
    </AccountingShell>
  );
}

function Ledger({ cid, fyId }: { cid: string; fyId: string }) {
  const A = `/companies/${cid}/accounting`;
  const [f, setF] = useState({ account: "", journal_id: "", third_party_id: "", date_from: "", date_to: "", piece: "" });
  const [applied, setApplied] = useState(f);
  const [err, setErr] = useState<string | null>(null);
  const qs = new URLSearchParams(Object.entries(applied).filter(([, v]) => v) as [string, string][]);
  const { data, error, loading } = useApiResource<{ accounts: LedgerAccount[]; totals: { debit: string; credit: string } }>(`${A}/fiscal-years/${fyId}/ledger?${qs}`);
  const { data: journals } = useApiResource<Journal[]>(`${A}/journals`);
  const { data: tps } = useApiResource<{ items: ThirdParty[] }>(`${A}/third-parties?limit=2000`);
  return (
    <>
      <form className="mb-4 grid gap-3 rounded-lg border bg-card p-4 shadow-card sm:grid-cols-3 lg:grid-cols-7" onSubmit={(e) => { e.preventDefault(); setApplied(f); }}>
        <Field label="Compte (début du numéro)" htmlFor="ac"><Input id="ac" inputMode="numeric" value={f.account} onChange={(e) => setF({ ...f, account: e.target.value.replace(/[^0-9]/g, "") })} /></Field>
        <Field label="Journal" htmlFor="jn"><Select id="jn" value={f.journal_id} onChange={(e) => setF({ ...f, journal_id: e.target.value })}>
          <option value="">Tous</option>{journals?.map((j) => <option key={j.id} value={j.id}>{j.code}</option>)}</Select></Field>
        <Field label="Tiers" htmlFor="tp"><Select id="tp" value={f.third_party_id} onChange={(e) => setF({ ...f, third_party_id: e.target.value })}>
          <option value="">Tous</option>{tps?.items.map((t) => <option key={t.id} value={t.id}>{t.code} · {t.name}</option>)}</Select></Field>
        <Field label="Du" htmlFor="df"><Input id="df" type="date" value={f.date_from} onChange={(e) => setF({ ...f, date_from: e.target.value })} /></Field>
        <Field label="Au" htmlFor="dt"><Input id="dt" type="date" value={f.date_to} onChange={(e) => setF({ ...f, date_to: e.target.value })} /></Field>
        <Field label="Pièce" htmlFor="pc"><Input id="pc" value={f.piece} onChange={(e) => setF({ ...f, piece: e.target.value })} /></Field>
        <div className="flex items-end gap-2">
          <Button type="submit">Filtrer</Button>
          <Button type="button" variant="outline" aria-label="Exporter en CSV" onClick={() => api.download(`${A}/fiscal-years/${fyId}/ledger.csv?${qs}`, "grand-livre-natif.csv").catch((e) => setErr(errorMessage(e)))}>
            <Download className="h-4 w-4" aria-hidden />
          </Button>
        </div>
      </form>
      {(error || err) && <Alert>{error ?? err}</Alert>}
      {loading && !data ? <Loading /> : !data?.accounts.length ? (
        <EmptyState title="Aucun mouvement" description="Aucune écriture validée ne correspond à ces critères." />
      ) : (
        <div className="space-y-5">
          {data.accounts.map((a) => (
            <section key={a.account} className="overflow-x-auto rounded-lg border bg-card shadow-card">
              <h3 className="border-b bg-muted/50 px-4 py-2 text-sm font-semibold">{a.account} · {a.label ?? ""}</h3>
              <table className="w-full min-w-[900px] text-sm tabular-nums">
                <thead className="text-left text-[11px] uppercase tracking-wider text-muted-foreground">
                  <tr><th className="px-4 py-2">Date</th><th className="px-2 py-2">Jnl</th><th className="px-2 py-2">Numéro</th><th className="px-2 py-2">Pièce</th>
                    <th className="px-2 py-2">Libellé</th><th className="px-2 py-2">Tiers</th><th className="px-2 py-2">Let.</th>
                    <th className="px-2 py-2 text-right">Débit</th><th className="px-2 py-2 text-right">Crédit</th><th className="px-4 py-2 text-right">Solde</th></tr>
                </thead>
                <tbody className="divide-y">
                  <tr className="text-muted-foreground"><td className="px-4 py-2" colSpan={9}>Solde d&apos;ouverture</td><td className="px-4 py-2 text-right">{amount(a.opening)}</td></tr>
                  {a.lines.map((l) => (
                    <tr key={l.line_id}>
                      <td className="whitespace-nowrap px-4 py-2">{new Date(l.entry_date).toLocaleDateString("fr-FR")}</td>
                      <td className="px-2 py-2">{l.journal}</td>
                      <td className="whitespace-nowrap px-2 py-2"><Link className="text-link hover:underline" href={`/companies/${cid}/comptabilite/ecritures/${l.entry_id}`}>{l.number}</Link></td>
                      <td className="px-2 py-2">{l.piece_ref}</td>
                      <td className="max-w-xs truncate px-2 py-2" title={l.label ?? ""}>{l.label}{l.origin !== "manual" ? ` · ${ORIGIN_LABEL[l.origin]}` : ""}</td>
                      <td className="px-2 py-2 text-xs">{l.third_party?.code}</td>
                      <td className="px-2 py-2 text-xs font-semibold">{l.lettering}</td>
                      <td className="px-2 py-2 text-right">{amount(l.debit, true)}</td><td className="px-2 py-2 text-right">{amount(l.credit, true)}</td>
                      <td className="px-4 py-2 text-right">{amount(l.balance)}</td>
                    </tr>
                  ))}
                  <tr className="bg-muted/40 font-semibold"><td className="px-4 py-2" colSpan={7}>Totaux et solde final</td>
                    <td className="px-2 py-2 text-right">{amount(a.debit)}</td><td className="px-2 py-2 text-right">{amount(a.credit)}</td><td className="px-4 py-2 text-right">{amount(a.closing)}</td></tr>
                </tbody>
              </table>
            </section>
          ))}
          <p className="text-sm font-medium">Total des mouvements : débit {amount(data.totals.debit)} · crédit {amount(data.totals.credit)}</p>
        </div>
      )}
    </>
  );
}
