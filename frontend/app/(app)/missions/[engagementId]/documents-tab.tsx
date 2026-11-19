"use client";

import { useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import type { Engagement } from "@/lib/types";
import { DOC_TYPE_LABELS, type DocFormat, type DocumentType, type GeneratedDoc } from "@/lib/report-types";
import { DocumentsTable, FormatAndTemplate, openDocument } from "@/components/reports";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, Loading } from "@/components/ui/feedback";

const FA = ["statutory_audit", "contractual_audit"];
const TEAM = ["partner", "manager", "in_charge", "staff"];

/** Onglet « Documents » : exports figés du rapport émis (audit interne) ou de la synthèse des anomalies (audit financier). */
export function DocumentsTab({ e }: { e: Engagement }) {
  const { data, error, reload } = useApiResource<GeneratedDoc[]>(`/engagements/${e.id}/documents`);
  const type: DocumentType | null = FA.includes(e.engagement_type) ? "fa_summary" : ["internal_audit", "ic_assessment"].includes(e.engagement_type) ? "internal_audit_report" : null;
  const [fmt, setFmt] = useState<DocFormat>("pdf");
  const [tpl, setTpl] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  async function go() {
    setBusy(true); setErr(null);
    try { const g = await api.post<GeneratedDoc>(`/engagements/${e.id}/documents`, { document_type: type, format: fmt, template_id: tpl || null }); await reload(); if (g.status === "ready") await openDocument(g.id); }
    catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }
  return (
    <div className="space-y-5">
      {type && e.my_role && TEAM.includes(e.my_role) && (
        <Card>
          <CardHeader><CardTitle>{DOC_TYPE_LABELS[type]}</CardTitle>
            <CardDescription>{type === "internal_audit_report"
              ? "Export du rapport émis, tel qu'il a été figé (son empreinte est reprise dans les sources). Un projet ne s'exporte pas ici."
              : "Récapitulatif des seuils approuvés, des anomalies et de leurs effets, et de la conclusion rédigée par l'équipe. Aucune opinion n'est produite."}</CardDescription></CardHeader>
          <CardContent className="space-y-3">
            {err && <Alert>{err}</Alert>}
            <div className="grid gap-3 sm:grid-cols-3">
              <FormatAndTemplate orgId={e.organization_id} docType={type} fmt={fmt} setFmt={setFmt} tpl={tpl} setTpl={setTpl} />
              <div className="flex items-end"><Button loading={busy} onClick={go}>Générer et télécharger</Button></div>
            </div>
          </CardContent>
        </Card>
      )}
      <Card>
        <CardHeader><CardTitle>Documents générés de la mission</CardTitle></CardHeader>
        <CardContent>{error ? <Alert>{error}</Alert> : !data ? <Loading /> : <DocumentsTable docs={data} />}</CardContent>
      </Card>
    </div>
  );
}
