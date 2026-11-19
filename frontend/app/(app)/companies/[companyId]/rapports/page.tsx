"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ChevronLeft } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import type { Budget, Company, FiscalYear } from "@/lib/types";
import { DOC_TYPE_LABELS, type DocFormat, type GeneratedDoc } from "@/lib/report-types";
import { DocumentsTable, FormatAndTemplate, openDocument } from "@/components/reports";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, Loading, PageHeader } from "@/components/ui/feedback";
import { Field, Select } from "@/components/ui/form";

type Kind = "financial_report" | "budget_report" | "ic_report";
const IC_KINDS: [string, string][] = [
  ["assessment", "Rapport d'évaluation du contrôle interne"], ["risk_map", "Cartographie des risques"], ["matrix", "Matrice risques-contrôles"],
  ["ineffective_controls", "État des contrôles inefficaces"], ["deficiencies", "Rapport des déficiences"], ["remediation", "Suivi des plans de remédiation"],
];

export default function CompanyReportsPage() {
  const { companyId: cid } = useParams<{ companyId: string }>();
  const { data: company } = useApiResource<Company>(`/companies/${cid}`);
  const { data: years } = useApiResource<FiscalYear[]>(`/companies/${cid}/fiscal-years`);
  const { data: docs, reload, error } = useApiResource<GeneratedDoc[]>(`/companies/${cid}/documents`);
  const [kind, setKind] = useState<Kind>("financial_report");
  const [fmt, setFmt] = useState<DocFormat>("pdf");
  const [tpl, setTpl] = useState("");
  const [fy, setFy] = useState("");
  const [budget, setBudget] = useState("");
  const [icKind, setIcKind] = useState("assessment");
  const [drafts, setDrafts] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [last, setLast] = useState<GeneratedDoc | null>(null);
  useEffect(() => { if (!fy && years?.length) setFy(years[years.length - 1].id); }, [years, fy]);
  const { data: budgets } = useApiResource<Budget[]>(kind === "budget_report" && fy ? `/companies/${cid}/fiscal-years/${fy}/budgets` : null);
  const approved = budgets?.filter((b) => b.status === "approved" || b.status === "archived") ?? [];
  async function generate() {
    setBusy(true); setErr(null); setLast(null);
    const body: Record<string, unknown> = { document_type: kind, format: fmt, template_id: tpl || null };
    if (kind === "financial_report") Object.assign(body, { fiscal_year_id: fy, include_unreviewed_ai: drafts });
    if (kind === "budget_report") body.budget_id = budget;
    if (kind === "ic_report") body.ic_kind = icKind;
    try { const g = await api.post<GeneratedDoc>(`/companies/${cid}/documents`, body); setLast(g); await reload(); if (g.status === "ready") await openDocument(g.id); }
    catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }
  return (
    <>
      <Link href={`/companies/${cid}`} className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ChevronLeft className="h-4 w-4" /> {company?.name ?? "Entreprise"}
      </Link>
      <PageHeader title="Rapports et documents" description="Documents PDF, Excel ou Word établis à partir de données validées uniquement. Chaque document est figé et conservé avec l'empreinte de son fichier, celle de ses données et la liste de ses sources." />
      <div className="space-y-5">
        <Card>
          <CardHeader><CardTitle>Générer un document</CardTitle>
            <CardDescription>Rapport financier : analyse terminée. Suivi budgétaire : budget approuvé. Contrôle interne : tests revus et évaluations approuvées.</CardDescription></CardHeader>
          <CardContent className="space-y-3">
            {err && <Alert>{err}</Alert>}
            {last?.status === "failed" && <Alert>Génération en échec, tracée : {last.failure_reason}</Alert>}
            <div className="grid gap-3 sm:grid-cols-4">
              <Field label="Document" htmlFor="rp-k"><Select id="rp-k" value={kind} onChange={(x) => { setKind(x.target.value as Kind); setTpl(""); }}>
                {(["financial_report", "budget_report", "ic_report"] as Kind[]).map((k) => <option key={k} value={k}>{DOC_TYPE_LABELS[k]}</option>)}</Select></Field>
              {kind !== "ic_report" && (
                <Field label="Exercice" htmlFor="rp-y"><Select id="rp-y" value={fy} onChange={(x) => { setFy(x.target.value); setBudget(""); }}>
                  {years?.map((y) => <option key={y.id} value={y.id}>{y.label}</option>)}</Select></Field>
              )}
              {kind === "budget_report" && (
                <Field label="Budget approuvé" htmlFor="rp-b"><Select id="rp-b" value={budget} onChange={(x) => setBudget(x.target.value)}>
                  <option value="">—</option>{approved.map((b) => <option key={b.id} value={b.id}>{b.name} v{b.version}</option>)}</Select></Field>
              )}
              {kind === "ic_report" && (
                <Field label="Rapport" htmlFor="rp-ic"><Select id="rp-ic" value={icKind} onChange={(x) => setIcKind(x.target.value)}>
                  {IC_KINDS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select></Field>
              )}
              <FormatAndTemplate orgId={company?.organization_id} docType={kind} fmt={fmt} setFmt={setFmt} tpl={tpl} setTpl={setTpl} />
            </div>
            {kind === "financial_report" && (
              <label className="flex items-start gap-2 text-sm">
                <input type="checkbox" className="mt-0.5 h-4 w-4" checked={drafts} onChange={(x) => setDrafts(x.target.checked)} />
                <span>Inclure aussi les commentaires IA non relus. Ils seront signalés comme brouillons en tête du document et à leur emplacement.
                  Par défaut, seuls les commentaires relus figurent ; les commentaires rejetés ne figurent jamais.</span>
              </label>
            )}
            {kind === "budget_report" && budgets && approved.length === 0 && <p className="text-xs text-muted-foreground">Aucun budget approuvé pour cet exercice.</p>}
            {kind === "ic_report" && <p className="text-xs text-muted-foreground">Rapports par domaine, processus ou cycle : depuis l&apos;espace Rapports du <Link className="underline" href={`/companies/${cid}/controle-interne/rapports`}>contrôle interne</Link>, avec leurs filtres.</p>}
            <div className="flex justify-end">
              <Button loading={busy} disabled={(kind !== "ic_report" && !fy) || (kind === "budget_report" && !budget)} onClick={generate}>Générer et télécharger</Button>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Documents générés</CardTitle><CardDescription>Documents de l&apos;entreprise ; les documents des missions sont dans chaque mission.</CardDescription></CardHeader>
          <CardContent>{error ? <Alert>{error}</Alert> : !docs ? <Loading /> : <DocumentsTable docs={docs} />}</CardContent>
        </Card>
      </div>
    </>
  );
}
