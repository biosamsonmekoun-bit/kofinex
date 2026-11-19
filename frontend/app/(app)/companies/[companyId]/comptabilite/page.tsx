"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Plus } from "lucide-react";
import { AccountingShell } from "@/components/accounting-shell";
import { useApiResource } from "@/lib/use-api";
import type { EntryRow, Journal } from "@/lib/accounting-types";
import { ORIGIN_LABEL, STATUS_LABEL, STATUS_TONE, amount } from "@/lib/accounting-types";
import { personName } from "@/lib/types";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Input, Select } from "@/components/ui/form";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const VIEWS: [string, string, string[]][] = [
  ["validation", "À valider", ["submitted", "under_review"]], ["saisie", "Brouillons", ["draft"]], ["rejetees", "Rejetées", ["rejected"]],
  ["historique", "Historique validé", ["validated", "reversed"]], ["toutes", "Toutes", []],
];
const PAGE = 50;

/** Écritures natives de l'exercice : file de validation, brouillons, rejets et historique. */
export default function EntriesPage() {
  const { companyId: cid } = useParams<{ companyId: string }>();
  return (
    <AccountingShell cid={cid} title="Écritures" needFy actions={
      <Link href={`/companies/${cid}/comptabilite/nouvelle`}><Button><Plus className="h-4 w-4" aria-hidden /> Nouvelle écriture</Button></Link>}>
      {({ fy }) => <EntryList cid={cid} fyId={fy!.id} />}
    </AccountingShell>
  );
}

function EntryList({ cid, fyId }: { cid: string; fyId: string }) {
  const [view, setView] = useState("validation");
  const [q, setQ] = useState("");
  const [journal, setJournal] = useState("");
  const [page, setPage] = useState(0);
  const statuses = VIEWS.find((v) => v[0] === view)![2];
  const qs = new URLSearchParams({ fiscal_year_id: fyId, limit: String(PAGE), offset: String(page * PAGE) });
  statuses.forEach((s) => qs.append("status", s));
  if (q.trim()) qs.set("q", q.trim());
  if (journal) qs.set("journal_id", journal);
  const { data, error, loading } = useApiResource<{ total: number; items: EntryRow[] }>(`/companies/${cid}/accounting/entries?${qs}`);
  const { data: journals } = useApiResource<Journal[]>(`/companies/${cid}/accounting/journals`);
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE)) : 1;
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div role="tablist" aria-label="Vues" className="flex flex-wrap gap-1">
          {VIEWS.map(([k, label]) => (
            <button key={k} role="tab" aria-selected={view === k} onClick={() => { setView(k); setPage(0); }}
                    className={cn("rounded-md px-3 py-1.5 text-sm transition-colors", view === k ? "bg-primary text-primary-foreground" : "hover:bg-muted")}>
              {label}
            </button>
          ))}
        </div>
        <Select aria-label="Journal" className="w-44" value={journal} onChange={(e) => { setJournal(e.target.value); setPage(0); }}>
          <option value="">Tous les journaux</option>
          {journals?.map((j) => <option key={j.id} value={j.id}>{j.code} · {j.label}</option>)}
        </Select>
        <Input aria-label="Rechercher" className="w-64" placeholder="Libellé, pièce ou numéro…" value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} />
      </div>
      {error && <Alert>{error}</Alert>}
      {loading && !data ? <Loading /> : !data?.items.length ? (
        <EmptyState title="Aucune écriture" description={view === "validation" ? "Aucune écriture n'attend de validation." : "Aucune écriture dans cette vue."} />
      ) : (
        <>
          <Table>
            <THead><tr><TH>Date</TH><TH>Journal</TH><TH>Numéro</TH><TH>Pièce</TH><TH>Libellé</TH><TH>Provenance</TH><TH>Statut</TH><TH>Auteur</TH><TH className="text-right">Montant</TH></tr></THead>
            <TBody>
              {data.items.map((e) => (
                <TR key={e.id}>
                  <TD className="whitespace-nowrap">{new Date(e.entry_date).toLocaleDateString("fr-FR")}</TD>
                  <TD>{e.journal_code}</TD>
                  <TD className="whitespace-nowrap font-medium">
                    <Link className="text-link hover:underline" href={`/companies/${cid}/comptabilite/ecritures/${e.id}`}>{e.number ?? "(provisoire)"}</Link>
                  </TD>
                  <TD>{e.piece_ref}</TD>
                  <TD className="max-w-xs truncate" title={e.label}>{e.label}</TD>
                  <TD>{ORIGIN_LABEL[e.origin]}</TD>
                  <TD><Badge tone={STATUS_TONE[e.status]}>{STATUS_LABEL[e.status]}</Badge></TD>
                  <TD className="text-xs">{personName(e.author)}</TD>
                  <TD className="whitespace-nowrap text-right">{amount(e.total_debit)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
            <span>{data.total} écriture(s){pages > 1 ? ` · page ${page + 1} / ${pages}` : ""}</span>
            {pages > 1 && <span className="flex gap-2">
              <Button size="sm" variant="outline" disabled={page === 0} onClick={() => setPage(page - 1)}>Précédente</Button>
              <Button size="sm" variant="outline" disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>Suivante</Button>
            </span>}
          </div>
        </>
      )}
    </>
  );
}
