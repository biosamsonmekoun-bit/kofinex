"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { AccountingShell } from "@/components/accounting-shell";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import type { CompanyAccount, Dec, ThirdParty } from "@/lib/accounting-types";
import { amount, fromCents, toCents } from "@/lib/accounting-types";
import { Button } from "@/components/ui/button";
import { Alert, EmptyState, Loading } from "@/components/ui/feedback";
import { Field, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

interface LItem { line_id: string; entry_id: string; entry_date: string; journal: string; number: string; piece_ref: string | null; label: string | null;
  debit: Dec; credit: Dec; lettering_id: string | null; lettering: string | null; fiscal_year_open: boolean }

/** Lettrage des comptes lettrables : rapprochement de lignes validées qui se soldent entre elles. */
export default function LetteringPage() {
  const { companyId: cid } = useParams<{ companyId: string }>();
  return <AccountingShell cid={cid} title="Lettrage">{({ settings }) => <Lettering cid={cid} canWrite={settings.permissions.write} />}</AccountingShell>;
}

function Lettering({ cid, canWrite }: { cid: string; canWrite: boolean }) {
  const A = `/companies/${cid}/accounting`;
  const { data: accounts } = useApiResource<{ items: CompanyAccount[] }>(`${A}/accounts?limit=5000`);
  const { data: tps } = useApiResource<{ items: ThirdParty[] }>(`${A}/third-parties?limit=2000`);
  const lettrable = (accounts?.items ?? []).filter((a) => a.lettering_enabled);
  const [account, setAccount] = useState("");
  const [tp, setTp] = useState("");
  const [state, setState] = useState("open");
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [msg, setMsg] = useState<{ kind: "error" | "success"; text: string } | null>(null);
  const acc = lettrable.find((a) => a.account_number === account);
  const needTp = !!acc?.requires_third_party;
  const path = account && (!needTp || tp) ? `${A}/lettering?${new URLSearchParams({ account, state, ...(tp ? { third_party_id: tp } : {}) })}` : null;
  const { data, error, loading, reload } = useApiResource<{ items: LItem[]; balance: Dec }>(path);
  const chosen = (data?.items ?? []).filter((i) => sel.has(i.line_id));
  const diff = useMemo(() => chosen.reduce((s, i) => s + toCents(i.debit) - toCents(i.credit), BigInt(0)), [chosen]);
  const tpChoices = (tps?.items ?? []).filter((t) => !acc?.third_party_kind || t.kind === acc.third_party_kind);

  async function letter() {
    setMsg(null);
    try {
      const r = await api.post<{ code: string }>(`${A}/lettering`, { line_ids: [...sel] });
      setSel(new Set()); setMsg({ kind: "success", text: `Lettrage ${r.code} enregistré.` }); await reload();
    } catch (e) { setMsg({ kind: "error", text: errorMessage(e) }); }
  }
  async function unletter(id: string) {
    setMsg(null);
    try { await api.del(`${A}/lettering/${id}`); await reload(); } catch (e) { setMsg({ kind: "error", text: errorMessage(e) }); }
  }

  if (!accounts) return <Loading />;
  if (!lettrable.length) return <EmptyState title="Aucun compte lettrable" description="Activez le lettrage sur les comptes concernés (clients, fournisseurs, comptes d'attente) dans le plan comptable."
    action={<Link className="text-sm font-medium text-link underline" href={`/companies/${cid}/comptabilite/plan-comptable`}>Ouvrir le plan comptable</Link>} />;
  return (
    <>
      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <Field label="Compte" htmlFor="la"><Select id="la" value={account} onChange={(e) => { setAccount(e.target.value); setTp(""); setSel(new Set()); }}>
          <option value="">— Choisir —</option>{lettrable.map((a) => <option key={a.id} value={a.account_number}>{a.account_number} · {a.label}</option>)}</Select></Field>
        {needTp && <Field label="Tiers" htmlFor="lt"><Select id="lt" value={tp} onChange={(e) => { setTp(e.target.value); setSel(new Set()); }}>
          <option value="">— Choisir —</option>{tpChoices.map((t) => <option key={t.id} value={t.id}>{t.code} · {t.name}</option>)}</Select></Field>}
        <Field label="Lignes" htmlFor="ls"><Select id="ls" value={state} onChange={(e) => { setState(e.target.value); setSel(new Set()); }}>
          <option value="open">Non lettrées</option><option value="lettered">Lettrées</option><option value="all">Toutes</option></Select></Field>
      </div>
      {msg && <Alert kind={msg.kind} className="mb-3">{msg.text}</Alert>}
      {error && <Alert>{error}</Alert>}
      {!path ? <p className="text-sm text-muted-foreground">Choisissez un compte{needTp ? " et un tiers" : ""}.</p> : loading && !data ? <Loading /> : !data?.items.length ? (
        <EmptyState title="Aucune ligne" description="Aucune ligne validée dans cette vue." />
      ) : (
        <>
          <Table>
            <THead><tr><TH className="w-8" /><TH>Date</TH><TH>Jnl</TH><TH>Numéro</TH><TH>Pièce</TH><TH>Libellé</TH><TH className="text-right">Débit</TH><TH className="text-right">Crédit</TH><TH>Lettrage</TH></tr></THead>
            <TBody>
              {data.items.map((i) => (
                <TR key={i.line_id}>
                  <TD>{!i.lettering_id && canWrite && i.fiscal_year_open && (
                    <input type="checkbox" aria-label={`Sélectionner ${i.number}`} checked={sel.has(i.line_id)}
                           onChange={(e) => setSel((s) => { const n = new Set(s); if (e.target.checked) n.add(i.line_id); else n.delete(i.line_id); return n; })} />)}</TD>
                  <TD className="whitespace-nowrap">{new Date(i.entry_date).toLocaleDateString("fr-FR")}</TD><TD>{i.journal}</TD>
                  <TD><Link className="text-link hover:underline" href={`/companies/${cid}/comptabilite/ecritures/${i.entry_id}`}>{i.number}</Link></TD>
                  <TD>{i.piece_ref}</TD><TD className="max-w-xs truncate">{i.label}</TD>
                  <TD className="text-right">{amount(i.debit, true)}</TD><TD className="text-right">{amount(i.credit, true)}</TD>
                  <TD>{i.lettering && <span className="inline-flex items-center gap-2 font-semibold">{i.lettering}
                    {canWrite && i.fiscal_year_open && <Button size="sm" variant="ghost" onClick={() => void unletter(i.lettering_id!)}>Délettrer</Button>}</span>}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
          {canWrite && (
            <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
              <span>{sel.size} ligne(s) sélectionnée(s) · écart {amount(fromCents(diff < BigInt(0) ? -diff : diff))}</span>
              <Button disabled={sel.size < 2 || diff !== BigInt(0)} onClick={() => void letter()}>Lettrer la sélection</Button>
              <span className="text-xs text-muted-foreground">Le lettrage est complet : la sélection doit être soldée. Les lignes d&apos;un exercice clôturé ne sont plus lettrables.</span>
            </div>
          )}
        </>
      )}
    </>
  );
}
