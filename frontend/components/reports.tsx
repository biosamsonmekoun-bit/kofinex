"use client";

import { useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { personName } from "@/lib/types";
import { FORMAT_LABELS, type DocFormat, type DocumentType, type GeneratedDoc, type ReportTemplate } from "@/lib/report-types";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Alert, Badge, EmptyState } from "@/components/ui/feedback";
import { Field, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

export async function openDocument(id: string) {
  const r = await api.get<{ url: string }>(`/documents/${id}/download`);
  window.open(r.url, "_blank", "noopener");
}

function size(n: number | null) {
  if (!n) return "—";
  return n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} Ko` : `${(n / 1024 / 1024).toFixed(1).replace(".", ",")} Mo`;
}

/** Documents générés : figés, avec empreintes du fichier et des données, sources et auteur. */
export function DocumentsTable({ docs }: { docs: GeneratedDoc[] | null | undefined }) {
  const [open, setOpen] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  if (!docs) return null;
  if (docs.length === 0) return <EmptyState title="Aucun document généré" description="Les documents générés sont conservés, figés, avec leur empreinte." />;
  return (
    <>
      {err && <Alert>{err}</Alert>}
      <Table>
        <THead><tr><TH>Document</TH><TH>Format</TH><TH>Établi le</TH><TH>Par</TH><TH>Empreinte des données</TH><TH /></tr></THead>
        <TBody>{docs.map((g) => (
          <TR key={g.id}>
            <TD>
              <span className="font-medium">{g.title ?? g.document_label}</span>
              <span className="block text-xs text-muted-foreground">{g.document_label}{g.template_version ? ` · modèle v${g.template_version}` : ""}</span>
              {g.contains_ai_drafts && <Badge tone="amber" className="mt-1">Contient des brouillons IA non relus</Badge>}
              {g.status === "failed" && <span className="block text-xs text-destructive">Échec : {g.failure_reason}</span>}
              {open === g.id && (
                <div className="mt-2 space-y-0.5 rounded-md border bg-muted/40 p-2 text-xs">
                  <p>Fichier : {g.filename} · {size(g.size_bytes)} · SHA-256 {g.sha256}</p>
                  <p>Données : SHA-256 {g.data_sha256} · {g.generator_version}</p>
                  <p className="font-medium">Sources</p>
                  {g.source_refs.map((s, i) => <p key={i}>• {s.label ?? s.type}{s.id ? ` — ${s.id}` : ""}</p>)}
                </div>
              )}
            </TD>
            <TD><Badge>{FORMAT_LABELS[g.format]}</Badge></TD>
            <TD>{formatDate(g.created_at)}</TD>
            <TD>{personName(g.requested_by_user)}</TD>
            <TD className="font-mono text-xs">{g.data_sha256 ? `${g.data_sha256.slice(0, 12)}…` : "—"}</TD>
            <TD className="whitespace-nowrap text-right">
              <Button size="sm" variant="ghost" onClick={() => setOpen(open === g.id ? null : g.id)}>{open === g.id ? "Masquer" : "Détails"}</Button>
              {g.status === "ready" && <Button size="sm" variant="outline" onClick={async () => { setErr(null); try { await openDocument(g.id); } catch (x) { setErr(errorMessage(x)); } }}>Télécharger</Button>}
            </TD>
          </TR>
        ))}</TBody>
      </Table>
    </>
  );
}

/** Choix du format et du modèle publié (facultatif). */
export function FormatAndTemplate({ orgId, docType, fmt, setFmt, tpl, setTpl }: {
  orgId: string | null | undefined; docType: DocumentType; fmt: DocFormat; setFmt: (f: DocFormat) => void; tpl: string; setTpl: (t: string) => void;
}) {
  const { data } = useApiResource<{ items: ReportTemplate[] }>(orgId ? `/organizations/${orgId}/report-templates?document_type=${docType}` : null);
  const published = data?.items.filter((t) => t.status === "published") ?? [];
  return (
    <>
      <Field label="Format" htmlFor="rp-f"><Select id="rp-f" value={fmt} onChange={(x) => setFmt(x.target.value as DocFormat)}>
        {(Object.keys(FORMAT_LABELS) as DocFormat[]).map((f) => <option key={f} value={f}>{FORMAT_LABELS[f]}</option>)}</Select></Field>
      <Field label="Modèle" htmlFor="rp-t"><Select id="rp-t" value={tpl} onChange={(x) => setTpl(x.target.value)}>
        <option value="">Présentation KOFINEX par défaut</option>
        {published.map((t) => <option key={t.id} value={t.id}>{t.name} (v{t.version})</option>)}</Select></Field>
    </>
  );
}
