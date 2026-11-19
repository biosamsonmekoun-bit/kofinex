"use client";

import { useRef, useState } from "react";
import { Database, Download, FileUp, Trash2 } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { personName, type Engagement, type EvidenceItem } from "@/lib/types";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const SOURCES = { auditor: "Équipe d'audit", auditee: "Audité", third_party: "Tiers", platform: "Plateforme (données figées)" } as const;

function size(n: number | null) {
  if (!n) return "";
  return n > 1048576 ? `${(n / 1048576).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} Mo` : `${Math.ceil(n / 1024)} Ko`;
}

export function EvidenceTab({ e }: { e: Engagement }) {
  const { data, error, loading, reload } = useApiResource<EvidenceItem[]>(`/engagements/${e.id}/evidence`);
  const fileRef = useRef<HTMLInputElement>(null);
  const [f, setF] = useState({ title: "", description: "", source: "auditor", obtained_on: "" });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const canAdd = (e.capabilities ?? []).includes("add_evidence");

  async function upload(ev: React.FormEvent) {
    ev.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    fd.append("title", f.title || file.name);
    if (f.description) fd.append("description", f.description);
    fd.append("source", f.source);
    if (f.obtained_on) fd.append("obtained_on", f.obtained_on);
    setBusy("upload");
    setErr(null);
    try {
      await api.upload(`/engagements/${e.id}/evidence`, fd);
      setF({ title: "", description: "", source: "auditor", obtained_on: "" });
      if (fileRef.current) fileRef.current.value = "";
      await reload();
    } catch (x) { setErr(errorMessage(x)); } finally { setBusy(null); }
  }

  async function act(key: string, fn: () => Promise<unknown>) {
    setBusy(key);
    setErr(null);
    try { await fn(); await reload(); } catch (x) { setErr(errorMessage(x)); } finally { setBusy(null); }
  }

  async function open(item: EvidenceItem) {
    setErr(null);
    try {
      const r = await api.get<{ kind: string; url?: string; snapshot?: unknown }>(`/engagements/${e.id}/evidence/${item.id}/download`);
      if (r.url) window.open(r.url, "_blank", "noopener");
      else {
        const blob = new Blob([JSON.stringify(r.snapshot, null, 2)], { type: "application/json" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `${item.title}.json`;
        a.click();
        URL.revokeObjectURL(a.href);
      }
    } catch (x) { setErr(errorMessage(x)); }
  }

  if (loading && !data) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  return (
    <div className="space-y-4">
      {err && <Alert>{err}</Alert>}
      {canAdd && (
        <Card>
          <CardHeader>
            <CardTitle>Ajouter un élément probant</CardTitle>
            <CardDescription>Le fichier est contrôlé (format réel, macros refusées) et conservé tel quel ; son empreinte SHA-256 est enregistrée. Formats : PDF, PNG, JPEG, XLSX, DOCX, CSV, TXT (50 Mo).</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <form onSubmit={upload} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Field label="Fichier" htmlFor="ev-file" required><Input id="ev-file" ref={fileRef} type="file" accept=".pdf,.png,.jpg,.jpeg,.xlsx,.docx,.csv,.txt" /></Field>
              <Field label="Titre" htmlFor="ev-title"><Input id="ev-title" value={f.title} onChange={(x) => setF({ ...f, title: x.target.value })} /></Field>
              <Field label="Source" htmlFor="ev-src">
                <Select id="ev-src" value={f.source} onChange={(x) => setF({ ...f, source: x.target.value })}>
                  {(["auditor", "auditee", "third_party"] as const).map((k) => <option key={k} value={k}>{SOURCES[k]}</option>)}
                </Select>
              </Field>
              <Field label="Obtenu le" htmlFor="ev-date"><Input id="ev-date" type="date" value={f.obtained_on} onChange={(x) => setF({ ...f, obtained_on: x.target.value })} /></Field>
              <div className="flex items-end gap-2 sm:col-span-2 lg:col-span-4">
                <Button type="submit" loading={busy === "upload"}><FileUp className="h-4 w-4" /> Déposer</Button>
                {e.fiscal_year_id && (
                  <Button type="button" variant="outline" loading={busy === "snapshot"}
                          onClick={() => act("snapshot", () => api.post(`/engagements/${e.id}/evidence/balance-snapshot`, {}))}>
                    <Database className="h-4 w-4" /> Figer la balance validée de l&apos;exercice
                  </Button>
                )}
              </div>
            </form>
          </CardContent>
        </Card>
      )}
      {data && data.length === 0 ? <EmptyState title="Aucun élément probant" /> : (
        <Table>
          <THead><tr><TH>Élément</TH><TH>Source</TH><TH>Obtenu le</TH><TH>Déposé par</TH><TH>Empreinte</TH><TH>Rattachements</TH><TH /></tr></THead>
          <TBody>
            {data?.map((i) => (
              <TR key={i.id}>
                <TD><span className="font-medium">{i.title}</span>
                  <p className="text-xs text-muted-foreground">{i.kind === "snapshot" ? `Données figées (${String(i.snapshot_ref?.rows ?? "")} lignes)` : `${i.original_filename} · ${size(i.size_bytes)}`}</p></TD>
                <TD>{SOURCES[i.source as keyof typeof SOURCES] ?? i.source}</TD>
                <TD>{formatDate(i.obtained_on)}</TD>
                <TD>{personName(i.uploaded_by_user)}</TD>
                <TD><code className="text-xs" title={i.sha256}>{i.sha256.slice(0, 12)}…</code></TD>
                <TD>{i.links.length ? <Badge tone="blue">{i.links.length}</Badge> : <span className="text-xs text-muted-foreground">Aucun</span>}</TD>
                <TD className="whitespace-nowrap text-right">
                  <Button variant="ghost" size="icon" aria-label={`Ouvrir ${i.title}`} onClick={() => open(i)}><Download className="h-4 w-4" /></Button>
                  {canAdd && <Button variant="ghost" size="icon" aria-label={`Retirer ${i.title}`} disabled={busy === i.id}
                                     onClick={() => act(i.id, () => api.del(`/engagements/${e.id}/evidence/${i.id}`))}><Trash2 className="h-4 w-4" /></Button>}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </div>
  );
}
