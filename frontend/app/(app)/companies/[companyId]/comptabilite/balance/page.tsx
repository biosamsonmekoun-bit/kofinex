"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { CheckCircle2, Download, XCircle } from "lucide-react";
import { AccountingShell } from "@/components/accounting-shell";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import type { BalanceData, Journal } from "@/lib/accounting-types";
import { amount } from "@/lib/accounting-types";
import { Button } from "@/components/ui/button";
import { Alert, EmptyState, Loading } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const SCOPES: [string, string][] = [["after_inventory", "Après inventaire"], ["before_inventory", "Avant inventaire"], ["final", "Définitive (exercice clôturé)"]];

/** Balance générale ou auxiliaire calculée à partir des écritures natives validées. */
export default function NativeBalancePage() {
  const { companyId: cid } = useParams<{ companyId: string }>();
  return (
    <AccountingShell cid={cid} title="Balance" needFy>
      {({ fy }) => <Balance cid={cid} fyId={fy!.id} closed={fy!.status === "closed"} />}
    </AccountingShell>
  );
}

function Balance({ cid, fyId, closed }: { cid: string; fyId: string; closed: boolean }) {
  const A = `/companies/${cid}/accounting`;
  const [f, setF] = useState({ scope: "after_inventory", auxiliary: false, compare: false, account: "", journal_id: "", date_from: "", date_to: "" });
  const [applied, setApplied] = useState(f);
  const [err, setErr] = useState<string | null>(null);
  const qs = new URLSearchParams(Object.entries(applied).filter(([, v]) => v !== "" && v !== false).map(([k, v]) => [k, String(v)]));
  const { data, error, loading } = useApiResource<BalanceData>(`${A}/fiscal-years/${fyId}/balance?${qs}`);
  const { data: journals } = useApiResource<Journal[]>(`${A}/journals`);
  const t = data?.totals;
  return (
    <>
      <form className="mb-4 grid gap-3 rounded-lg border bg-card p-4 shadow-card sm:grid-cols-3 lg:grid-cols-7" onSubmit={(e) => { e.preventDefault(); setApplied(f); }}>
        <Field label="Type" htmlFor="sc"><Select id="sc" value={f.scope} onChange={(e) => setF({ ...f, scope: e.target.value })}>
          {SCOPES.map(([k, l]) => <option key={k} value={k} disabled={k === "final" && !closed}>{l}</option>)}</Select></Field>
        <Field label="Compte (début)" htmlFor="ac"><Input id="ac" inputMode="numeric" value={f.account} onChange={(e) => setF({ ...f, account: e.target.value.replace(/[^0-9]/g, "") })} /></Field>
        <Field label="Journal" htmlFor="jn"><Select id="jn" value={f.journal_id} onChange={(e) => setF({ ...f, journal_id: e.target.value })}>
          <option value="">Tous</option>{journals?.map((j) => <option key={j.id} value={j.id}>{j.code}</option>)}</Select></Field>
        <Field label="Du" htmlFor="df"><Input id="df" type="date" value={f.date_from} onChange={(e) => setF({ ...f, date_from: e.target.value })} /></Field>
        <Field label="Au" htmlFor="dt"><Input id="dt" type="date" value={f.date_to} onChange={(e) => setF({ ...f, date_to: e.target.value })} /></Field>
        <div className="flex flex-col justify-end gap-1 text-sm">
          <label className="flex items-center gap-2"><input type="checkbox" checked={f.auxiliary} onChange={(e) => setF({ ...f, auxiliary: e.target.checked, compare: e.target.checked ? false : f.compare })} /> Balance auxiliaire (tiers)</label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={f.compare} disabled={f.auxiliary} onChange={(e) => setF({ ...f, compare: e.target.checked })} /> Comparatif N-1</label>
        </div>
        <div className="flex items-end gap-2">
          <Button type="submit">Calculer</Button>
          <Button type="button" variant="outline" aria-label="Exporter en CSV" onClick={() => api.download(`${A}/fiscal-years/${fyId}/balance.csv?${qs}`, "balance.csv").catch((e) => setErr(errorMessage(e)))}>
            <Download className="h-4 w-4" aria-hidden />
          </Button>
        </div>
      </form>
      {(error || err) && <Alert>{error ?? err}</Alert>}
      {loading && !data ? <Loading /> : !data ? null : (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-4 text-sm">
            {(["opening_balanced", "movements_balanced", "closing_balanced"] as const).map((k) => (
              <span key={k} className="inline-flex items-center gap-1">
                {data.checks[k] ? <CheckCircle2 className="h-4 w-4 text-success" aria-hidden /> : <XCircle className="h-4 w-4 text-destructive" aria-hidden />}
                {{ opening_balanced: "Soldes d'ouverture équilibrés", movements_balanced: "Mouvements équilibrés", closing_balanced: "Soldes de clôture équilibrés" }[k]}
                {!data.checks[k] && " : non"}
              </span>
            ))}
            <span className="text-muted-foreground">{data.entries_count} écriture(s) validée(s){data.pending_count ? ` · ${data.pending_count} non validée(s), non prise(s) en compte` : ""}</span>
          </div>
          {!data.rows.length ? <EmptyState title="Balance vide" description="Aucune écriture validée sur cette sélection." /> : (
            <Table>
              <THead><tr><TH>Compte</TH><TH>Intitulé</TH>{data.auxiliary && <TH>Tiers</TH>}<TH className="text-right">Ouv. débit</TH><TH className="text-right">Ouv. crédit</TH>
                <TH className="text-right">Mvt débit</TH><TH className="text-right">Mvt crédit</TH><TH className="text-right">Solde débiteur</TH><TH className="text-right">Solde créditeur</TH></tr></THead>
              <TBody>
                {data.rows.map((r, i) => (
                  <TR key={`${r.account}-${r.third_party?.id ?? i}`}>
                    <TD className="font-medium">{r.account}</TD><TD className="text-xs">{r.label}</TD>
                    {data.auxiliary && <TD className="text-xs">{r.third_party ? `${r.third_party.code} · ${r.third_party.name}` : ""}</TD>}
                    <TD className="text-right">{amount(r.opening_debit, true)}</TD><TD className="text-right">{amount(r.opening_credit, true)}</TD>
                    <TD className="text-right">{amount(r.debit, true)}</TD><TD className="text-right">{amount(r.credit, true)}</TD>
                    <TD className="text-right">{amount(r.closing_debit, true)}</TD><TD className="text-right">{amount(r.closing_credit, true)}</TD>
                  </TR>
                ))}
                {t && <TR className="bg-muted/40 font-semibold"><TD colSpan={data.auxiliary ? 3 : 2}>Totaux</TD>
                  <TD className="text-right">{amount(t.opening_debit)}</TD><TD className="text-right">{amount(t.opening_credit)}</TD>
                  <TD className="text-right">{amount(t.debit)}</TD><TD className="text-right">{amount(t.credit)}</TD>
                  <TD className="text-right">{amount(t.closing_debit)}</TD><TD className="text-right">{amount(t.closing_credit)}</TD></TR>}
              </TBody>
            </Table>
          )}
          {data.comparative && (data.comparative.available ? (
            <section className="mt-6">
              <h3 className="mb-2 text-sm font-semibold">Comparatif : solde N et N-1 ({data.comparative.previous_label})</h3>
              <Table>
                <THead><tr><TH>Compte</TH><TH>Intitulé</TH><TH className="text-right">Solde N</TH><TH className="text-right">Solde N-1</TH><TH className="text-right">Écart</TH></tr></THead>
                <TBody>{data.comparative.rows.map((r) => (
                  <TR key={r.account}><TD className="font-medium">{r.account}</TD><TD className="text-xs">{r.label}</TD>
                    <TD className="text-right">{amount(r.current)}</TD><TD className="text-right">{amount(r.previous)}</TD><TD className="text-right">{amount(r.change)}</TD></TR>
                ))}</TBody>
              </Table>
              <p className="mt-1 text-xs text-muted-foreground">Solde = débit − crédit (positif : débiteur, négatif : créditeur).</p>
            </section>
          ) : <Alert kind="info" className="mt-4">Comparatif indisponible : {data.comparative.reason}</Alert>)}
        </>
      )}
    </>
  );
}
