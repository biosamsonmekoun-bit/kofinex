"use client";

import { useState } from "react";
import Link from "next/link";
import { Download, Plus } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import type { Methodology, Organization } from "@/lib/types";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading, PageHeader } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const METHODOLOGY_STATUS = { draft: ["Brouillon", "neutral"], published: ["Publiée", "green"], archived: ["Archivée", "amber"] } as const;
const KIND = { audit: "Audit", internal_control: "Contrôle interne" } as const;

export default function MethodologiesPage() {
  const { data, error, loading } = useApiResource<Methodology[]>("/methodologies");
  const { data: orgs } = useApiResource<Organization[]>("/organizations");
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ organization_id: "", kind: "audit", name: "", version_label: "", source_reference: "", description: "",
    framework_category: "", issuing_body: "", published_on: "", effective_from: "", source_document: "" });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function create(ev: React.FormEvent) {
    ev.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const m = await api.post<Methodology>("/methodologies", { ...f, organization_id: f.organization_id || null, description: f.description || null,
        framework_category: f.framework_category || null, issuing_body: f.issuing_body.trim() || null, published_on: f.published_on || null,
        effective_from: f.effective_from || null, source_document: f.source_document.trim() || null });
      window.location.assign(`/methodologies/${m.id}`);
    } catch (x) { setErr(errorMessage(x)); setBusy(false); }
  }

  return (
    <>
      <PageHeader title="Méthodologies"
                  description="Référentiels d'audit et de contrôle interne chargés par vos soins (assertions, cycles, grilles de cotation, programmes types), versionnés. KOFINEX ne fournit aucun contenu normatif."
                  actions={<>
                    <Button variant="outline" size="sm" onClick={() => api.download("/methodology-template.csv", "modele-methodologie.csv")}><Download className="h-4 w-4" /> Modèle CSV</Button>
                    <Button size="sm" onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> Méthodologie</Button>
                  </>} />
      {loading && !data && <Loading />}
      {error && <Alert>{error}</Alert>}
      {data && data.length === 0 && <EmptyState title="Aucune méthodologie" description="Créez une version, chargez ses éléments depuis le modèle CSV, puis publiez-la pour l'utiliser dans vos missions." />}
      {data && data.length > 0 && (
        <Table>
          <THead><tr><TH>Nom</TH><TH>Version</TH><TH>Type</TH><TH>Portée</TH><TH className="text-right">Éléments</TH><TH>Statut</TH><TH>Publiée le</TH></tr></THead>
          <TBody>
            {data.map((m) => (
              <TR key={m.id}>
                <TD className="font-medium"><Link className="text-link hover:underline" href={`/methodologies/${m.id}`}>{m.name}</Link></TD>
                <TD>{m.version_label}</TD>
                <TD>{KIND[m.kind]}</TD>
                <TD>{m.organization_id ? orgs?.find((o) => o.id === m.organization_id)?.name ?? "Organisation" : "Plateforme"}</TD>
                <TD className="text-right">{typeof m.items === "number" ? m.items : "—"}</TD>
                <TD><Badge tone={METHODOLOGY_STATUS[m.status][1]}>{METHODOLOGY_STATUS[m.status][0]}</Badge></TD>
                <TD>{formatDate(m.published_at)}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
      <Dialog open={open} onClose={() => setOpen(false)} title="Nouvelle méthodologie" description="La source de référence (texte, édition, date) est obligatoire : elle est rappelée dans chaque mission qui utilise cette version.">
        <form onSubmit={create} className="space-y-3">
          {err && <Alert>{err}</Alert>}
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Portée" htmlFor="m-org">
              <Select id="m-org" value={f.organization_id} onChange={(x) => setF({ ...f, organization_id: x.target.value })}>
                <option value="">Plateforme (administrateurs de la plateforme)</option>
                {orgs?.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
              </Select>
            </Field>
            <Field label="Type" htmlFor="m-kind">
              <Select id="m-kind" value={f.kind} onChange={(x) => setF({ ...f, kind: x.target.value })}>
                <option value="audit">Audit</option><option value="internal_control">Contrôle interne</option>
              </Select>
            </Field>
            <Field label="Nom" htmlFor="m-name" required><Input id="m-name" value={f.name} onChange={(x) => setF({ ...f, name: x.target.value })} required /></Field>
            <Field label="Version" htmlFor="m-ver" required><Input id="m-ver" value={f.version_label} onChange={(x) => setF({ ...f, version_label: x.target.value })} required /></Field>
          </div>
          <Field label="Source de référence" htmlFor="m-src" required><Input id="m-src" value={f.source_reference} onChange={(x) => setF({ ...f, source_reference: x.target.value })} required minLength={3} /></Field>
          <Field label="Description" htmlFor="m-desc"><Input id="m-desc" value={f.description} onChange={(x) => setF({ ...f, description: x.target.value })} /></Field>
          {f.kind === "internal_control" && (
            <div className="space-y-3 rounded-md border p-3">
              <p className="text-xs text-muted-foreground">Nature du référentiel : un cadre de contrôle interne, un référentiel professionnel d&apos;audit et une exigence juridique ou comptable ne sont pas des normes équivalentes. Ces informations sont saisies par vous, d&apos;après le document source.</p>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Catégorie" htmlFor="m-cat"><Select id="m-cat" value={f.framework_category} onChange={(x) => setF({ ...f, framework_category: x.target.value })}>
                  <option value="">—</option><option value="ic_framework">Cadre de contrôle interne</option><option value="professional_standard">Référentiel professionnel d&apos;audit</option>
                  <option value="legal_requirement">Exigence juridique ou comptable</option><option value="internal_methodology">Méthodologie interne</option></Select></Field>
                <Field label="Organisme source" htmlFor="m-ib"><Input id="m-ib" value={f.issuing_body} onChange={(x) => setF({ ...f, issuing_body: x.target.value })} /></Field>
                <Field label="Date de publication" htmlFor="m-po"><Input id="m-po" type="date" value={f.published_on} onChange={(x) => setF({ ...f, published_on: x.target.value })} /></Field>
                <Field label="Date d'application" htmlFor="m-ef"><Input id="m-ef" type="date" value={f.effective_from} onChange={(x) => setF({ ...f, effective_from: x.target.value })} /></Field>
              </div>
              <Field label="Document source (référence, URL ou cote)" htmlFor="m-sd"><Input id="m-sd" value={f.source_document} onChange={(x) => setF({ ...f, source_document: x.target.value })} /></Field>
            </div>
          )}
          <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => setOpen(false)}>Annuler</Button><Button type="submit" loading={busy}>Créer</Button></div>
        </form>
      </Dialog>
    </>
  );
}
