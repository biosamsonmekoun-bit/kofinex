"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { DOC_TYPE_LABELS, FINANCIAL_SECTION_LABELS, TEMPLATE_STATUS, type DocumentType, type ReportTemplate } from "@/lib/report-types";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading, PageHeader } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";

type Data = { can_edit: boolean; items: ReportTemplate[]; financial_sections: string[] };
const AREA = "w-full rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30";

export default function ReportTemplatesPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const base = `/organizations/${orgId}/report-templates`;
  const { data, error, reload } = useApiResource<Data>(base);
  const [edit, setEdit] = useState<ReportTemplate | "new" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  async function act(t: ReportTemplate, action: "publish" | "archive" | "new-version") {
    setErr(null);
    try { const r = await api.post<ReportTemplate>(`${base}/${t.id}/${action}`); await reload(); if (action === "new-version") setEdit(r); }
    catch (x) { setErr(errorMessage(x)); }
  }
  async function del(t: ReportTemplate) {
    setErr(null);
    try { await api.del(`${base}/${t.id}`); await reload(); } catch (x) { setErr(errorMessage(x)); }
  }
  return (
    <>
      <PageHeader title="Modèles de rapports" description="Intitulés, textes d'introduction et de clôture, sections et couleur des documents générés. Un modèle publié est figé : pour le modifier, créez une nouvelle version. Les chiffres et les constats viennent toujours des données validées."
                  actions={data?.can_edit ? <Button size="sm" onClick={() => setEdit("new")}>Nouveau modèle</Button> : undefined} />
      {error && <Alert>{error}</Alert>}
      {err && <Alert>{err}</Alert>}
      {!data ? <Loading /> : data.items.length === 0 ? <EmptyState title="Aucun modèle" description="Sans modèle, les documents utilisent la présentation KOFINEX par défaut." /> : (
        <div className="grid gap-4 lg:grid-cols-2">
          {data.items.map((t) => (
            <Card key={t.id}>
              <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-2">
                <div><CardTitle>{t.name} — v{t.version}</CardTitle><CardDescription>{DOC_TYPE_LABELS[t.document_type]}{t.organization_id ? "" : " · modèle de la plateforme"}</CardDescription></div>
                <Badge tone={TEMPLATE_STATUS[t.status][1]}>{TEMPLATE_STATUS[t.status][0]}</Badge>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                {t.content.title && <p><span className="text-xs text-muted-foreground">Titre :</span> {t.content.title}</p>}
                {t.content.intro && <p className="line-clamp-3"><span className="text-xs text-muted-foreground">Introduction :</span> {t.content.intro}</p>}
                {t.sections.length > 0 && <p className="text-xs text-muted-foreground">Sections : {t.sections.map((s) => FINANCIAL_SECTION_LABELS[s] ?? s).join(", ")}</p>}
                {t.branding.primary_color && <p className="text-xs text-muted-foreground">Couleur : {t.branding.primary_color}</p>}
                {t.published_at && <p className="text-xs text-muted-foreground">Publié le {formatDate(t.published_at)}</p>}
                {data.can_edit && t.organization_id && (
                  <div className="flex flex-wrap gap-2 pt-1">
                    {t.status === "draft" && <><Button size="sm" variant="outline" onClick={() => setEdit(t)}>Modifier</Button>
                      <Button size="sm" onClick={() => act(t, "publish")}>Publier</Button>
                      <Button size="sm" variant="ghost" onClick={() => del(t)}>Supprimer</Button></>}
                    {t.status === "published" && <><Button size="sm" variant="outline" onClick={() => act(t, "new-version")}>Nouvelle version</Button>
                      <Button size="sm" variant="ghost" onClick={() => act(t, "archive")}>Archiver</Button></>}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      {edit && data && <TemplateDialog base={base} t={edit === "new" ? null : edit} sections={data.financial_sections} onClose={() => setEdit(null)}
                                       onDone={async () => { setEdit(null); await reload(); }} />}
    </>
  );
}

function TemplateDialog({ base, t, sections, onClose, onDone }: { base: string; t: ReportTemplate | null; sections: string[]; onClose: () => void; onDone: () => void }) {
  const [f, setF] = useState({ name: t?.name ?? "", document_type: (t?.document_type ?? "financial_report") as DocumentType, sections: t?.sections ?? [],
    title: t?.content.title ?? "", intro_title: t?.content.intro_title ?? "", intro: t?.content.intro ?? "", closing_title: t?.content.closing_title ?? "",
    closing: t?.content.closing ?? "", primary_color: t?.branding.primary_color ?? "" });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function save(ev: React.FormEvent) {
    ev.preventDefault(); setBusy(true); setErr(null);
    const body = { ...f, primary_color: f.primary_color.trim() || null };
    try { if (t) await api.patch(`${base}/${t.id}`, body); else await api.post(base, body); onDone(); } catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }
  const txt = (k: "title" | "intro_title" | "closing_title", label: string) => (
    <Field label={label} htmlFor={`tp-${k}`}><Input id={`tp-${k}`} value={f[k]} onChange={(x) => setF({ ...f, [k]: x.target.value })} /></Field>
  );
  return (
    <Dialog open onClose={onClose} size="lg" title={t ? `Modèle ${t.name} — v${t.version}` : "Nouveau modèle"}>
      <form onSubmit={save} className="space-y-3">
        {err && <Alert>{err}</Alert>}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Nom" htmlFor="tp-n" required><Input id="tp-n" required disabled={!!t && t.version > 1} value={f.name} onChange={(x) => setF({ ...f, name: x.target.value })} /></Field>
          <Field label="Type de document" htmlFor="tp-d"><Select id="tp-d" disabled={!!t} value={f.document_type} onChange={(x) => setF({ ...f, document_type: x.target.value as DocumentType, sections: [] })}>
            {(Object.keys(DOC_TYPE_LABELS) as DocumentType[]).map((k) => <option key={k} value={k}>{DOC_TYPE_LABELS[k]}</option>)}</Select></Field>
        </div>
        {txt("title", "Titre du document (facultatif, remplace le titre par défaut)")}
        {f.document_type === "financial_report" && (
          <fieldset><legend className="mb-1 text-sm font-medium">Sections incluses (aucune cochée : toutes)</legend>
            <div className="flex flex-wrap gap-3">{sections.map((s) => (
              <label key={s} className="flex items-center gap-1.5 text-sm"><input type="checkbox" className="h-4 w-4" checked={f.sections.includes(s)}
                onChange={(x) => setF({ ...f, sections: x.target.checked ? [...f.sections, s] : f.sections.filter((y) => y !== s) })} /> {FINANCIAL_SECTION_LABELS[s] ?? s}</label>
            ))}</div></fieldset>
        )}
        <div className="grid gap-3 sm:grid-cols-2">{txt("intro_title", "Intitulé de l'introduction")}{txt("closing_title", "Intitulé des mentions finales")}</div>
        <Field label="Introduction" htmlFor="tp-i"><textarea id="tp-i" rows={3} className={AREA} value={f.intro} onChange={(x) => setF({ ...f, intro: x.target.value })} /></Field>
        <Field label="Mentions finales" htmlFor="tp-c"><textarea id="tp-c" rows={3} className={AREA} value={f.closing} onChange={(x) => setF({ ...f, closing: x.target.value })} /></Field>
        <Field label="Couleur principale (#RRGGBB, facultatif)" htmlFor="tp-col" hint="Par défaut : bleu nuit KOFINEX">
          <Input id="tp-col" placeholder="#RRGGBB" value={f.primary_color} onChange={(x) => setF({ ...f, primary_color: x.target.value })} /></Field>
        <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={onClose}>Annuler</Button><Button type="submit" loading={busy}>Enregistrer</Button></div>
      </form>
    </Dialog>
  );
}
