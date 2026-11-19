"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ChevronLeft, FileUp } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { IMPORT_STATUS_LABELS, type Company, type FiscalYear } from "@/lib/types";
import type { LedgerImportRow, LedgerJob } from "@/lib/ledger-types";
import { cn, formatDate } from "@/lib/utils";
import { statusTone } from "../imports-tab";
import { LedgerAccounts, LedgerAnalyticsPanel, LedgerBrowser, LedgerJournals } from "@/components/ledger-views";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, Badge, EmptyState, Loading, PageHeader } from "@/components/ui/feedback";
import { Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const TABS = [["imports", "Imports"], ["lines", "Consultation"], ["accounts", "Comptes"], ["journals", "Centralisation"], ["analytics", "Analyses"]] as const;
type Tab = (typeof TABS)[number][0];

function Imports({ company, fy }: { company: Company; fy: FiscalYear }) {
  const router = useRouter();
  const { data, error } = useApiResource<LedgerImportRow[]>(`/companies/${company.id}/ledger-imports?fiscal_year_id=${fy.id}`);
  const fileRef = useRef<HTMLInputElement>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function upload(ev: React.FormEvent) {
    ev.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    fd.append("fiscal_year_id", fy.id);
    setBusy(true); setErr(null);
    try { const j = await api.upload<LedgerJob>(`/companies/${company.id}/ledger-imports`, fd); router.push(`/companies/${company.id}/grand-livre/imports/${j.id}`); }
    catch (x) { setErr(errorMessage(x)); setBusy(false); }
  }
  return (
    <div className="space-y-4">
      {fy.status === "open" ? (
        <Card>
          <CardHeader><CardTitle>Déposer le grand livre de l&apos;exercice {fy.label}</CardTitle>
            <CardDescription>Export du logiciel comptable (Excel ou CSV), dont le fichier des écritures comptables (FEC), dont les colonnes sont reconnues automatiquement. Le grand livre validé remplace le précédent ; la balance de l&apos;exercice n&apos;est pas modifiée.</CardDescription></CardHeader>
          <CardContent>
            {err && <Alert className="mb-3">{err}</Alert>}
            <form onSubmit={upload} className="flex flex-col gap-2 sm:flex-row">
              <Input ref={fileRef} type="file" accept=".xlsx,.xls,.csv,.txt" aria-label="Fichier du grand livre" />
              <Button type="submit" loading={busy}><FileUp className="h-4 w-4" /> Déposer</Button>
            </form>
          </CardContent>
        </Card>
      ) : <Alert kind="info">Exercice clôturé : aucun import n&apos;est possible.</Alert>}
      {error && <Alert>{error}</Alert>}
      {data && data.length === 0 && <EmptyState title="Aucun import de grand livre pour cet exercice" />}
      {data && data.length > 0 && (
        <Table>
          <THead><tr><TH>Fichier</TH><TH>Déposé le</TH><TH className="text-right">Lignes valides</TH><TH className="text-right">En erreur</TH><TH>Statut</TH></tr></THead>
          <TBody>{data.map((j) => (
            <TR key={j.id}>
              <TD className="font-medium"><Link className="text-link hover:underline" href={`/companies/${company.id}/grand-livre/imports/${j.id}`}>{j.filename}</Link>{j.active && <Badge tone="green" className="ml-2">Grand livre de l&apos;exercice</Badge>}</TD>
              <TD>{formatDate(j.created_at)}</TD><TD className="text-right">{j.valid_rows ?? "—"}</TD><TD className="text-right">{j.error_rows || "—"}</TD>
              <TD><Badge tone={statusTone(j.status)}>{IMPORT_STATUS_LABELS[j.status]}</Badge></TD>
            </TR>))}
          </TBody>
        </Table>
      )}
    </div>
  );
}

export default function GeneralLedgerPage() {
  const { companyId } = useParams<{ companyId: string }>();
  const { data: company } = useApiResource<Company>(`/companies/${companyId}`);
  const { data: fys } = useApiResource<FiscalYear[]>(`/companies/${companyId}/fiscal-years`);
  const [fyId, setFyId] = useState("");
  const [tab, setTab] = useState<Tab>("imports");
  const [account, setAccount] = useState<string | undefined>();
  if (!company || !fys) return <Loading />;
  const fy = fys.find((x) => x.id === fyId) ?? fys[0];
  const base = fy ? `/companies/${companyId}/fiscal-years/${fy.id}/ledger` : "";
  const hasLedger = !!fy?.active_ledger_import_job_id;
  return (
    <>
      <Link href={`/companies/${companyId}`} className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ChevronLeft className="h-4 w-4" /> {company.name}</Link>
      <PageHeader title="Grand livre"
                  description="Écritures comptables importées : consultation, rapprochement avec la balance, centralisation, analyses de données. Le grand livre alimente aussi le réalisé mensuel du contrôle de gestion et les populations d'audit."
                  actions={fys.length > 0 && (
                    <Select aria-label="Exercice" className="w-48" value={fy?.id ?? ""} onChange={(x) => { setFyId(x.target.value); setAccount(undefined); }}>
                      {fys.map((x) => <option key={x.id} value={x.id}>Exercice {x.label}</option>)}
                    </Select>
                  )} />
      {!fy ? <EmptyState title="Aucun exercice" description="Créez d'abord l'exercice dans la fiche de l'entreprise." /> : (
        <>
          <div role="tablist" className="mb-5 flex gap-1 overflow-x-auto border-b">
            {TABS.map(([id, label]) => (
              <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}
                      className={cn("-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
                        tab === id ? "border-primary font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground")}>{label}</button>
            ))}
          </div>
          {tab === "imports" && <Imports company={company} fy={fy} />}
          {tab !== "imports" && !hasLedger && <EmptyState title="Aucun grand livre validé pour cet exercice" description="Déposez et validez le grand livre dans l'onglet « Imports »." />}
          {tab === "lines" && hasLedger && <LedgerBrowser key={`${fy.id}-${account ?? ""}`} base={base} initialAccount={account} />}
          {tab === "accounts" && hasLedger && <LedgerAccounts base={base} onOpen={(a) => { setAccount(a); setTab("lines"); }} />}
          {tab === "journals" && hasLedger && <LedgerJournals base={base} />}
          {tab === "analytics" && hasLedger && <LedgerAnalyticsPanel base={base} />}
        </>
      )}
    </>
  );
}
