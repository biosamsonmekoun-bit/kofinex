"use client";

import { useState } from "react";
import { FileDown, FileSignature, Plus, Save, Trash2 } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { personName, type Engagement } from "@/lib/types";
import { ACTION_STATUS, type AuditReport, type ReportContent } from "@/lib/ia-types";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Field, Input } from "@/components/ui/form";

const AREA = "w-full rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30 disabled:opacity-70";
const STATUS = { draft: ["Projet", "amber"], issued: ["Émis", "green"], superseded: ["Remplacé", "neutral"] } as const;
type Data = { reports: AuditReport[]; capabilities: string[] };

function Preview({ e, r }: { e: Engagement; r: AuditReport }) {
  const { data: c, error } = useApiResource<ReportContent>(`/engagements/${e.id}/reports/${r.id}/content?v=${r.status}-${r.content_sha256 ?? r.created_at}`);
  if (error) return <Alert>{error}</Alert>;
  if (!c) return <Loading />;
  return (
    <article className="space-y-4 rounded-lg border bg-card p-6 text-sm shadow-card">
      {c.draft && <p className="text-xs font-semibold uppercase tracking-widest text-warning-strong">Projet — document de travail non émis</p>}
      <header>
        <h2 className="text-xl font-semibold">{c.title}</h2>
        <p className="text-muted-foreground">{c.engagement.company} · {c.engagement.reference} — {c.engagement.name}
          {c.engagement.period_start && ` · du ${formatDate(c.engagement.period_start)} au ${formatDate(c.engagement.period_end)}`}</p>
        {c.methodology && <p className="text-xs text-muted-foreground">Méthodologie : {c.methodology.name} {c.methodology.version_label} (source : {c.methodology.source_reference})</p>}
      </header>
      {[["Synthèse", c.executive_summary], ["Objectifs", c.engagement.objectives], ["Périmètre", c.engagement.scope], ["Conclusion générale", c.overall_conclusion]]
        .filter(([, t]) => t).map(([h, t]) => <section key={h}><h3 className="font-semibold">{h}</h3><p className="whitespace-pre-wrap">{t}</p></section>)}
      {c.rating_counts.length > 0 && <p>{c.rating_counts.map((x) => `${x.label} : ${x.count}`).join(" · ")}</p>}
      <section className="space-y-3">
        <h3 className="font-semibold">Constats et recommandations</h3>
        {c.findings.length === 0 && <p className="text-muted-foreground">Aucun constat.</p>}
        {c.findings.map((f) => (
          <div key={f.reference} className="border-t pt-2">
            <p className="font-medium">{f.reference} — {f.title}{f.rating_label && ` [${f.rating_label}]`}</p>
            <p><span className="text-muted-foreground">Constat : </span>{f.condition}</p>
            <p><span className="text-muted-foreground">Référentiel : </span>{f.criteria}</p>
            {f.cause && <p><span className="text-muted-foreground">Cause : </span>{f.cause}</p>}
            {f.effect && <p><span className="text-muted-foreground">Conséquence : </span>{f.effect}</p>}
            {f.recommendations.map((rc) => (
              <div key={rc.reference} className="mt-1">
                <p><span className="font-medium">Recommandation {rc.reference} : </span>{rc.text}</p>
                <ul className="list-disc pl-5">{rc.action_plans.map((a, i) => <li key={i}>{a.description} — {a.owner_name} — {formatDate(a.due_date)} — {ACTION_STATUS[a.status][0]}</li>)}</ul>
              </div>
            ))}
            <p><span className="text-muted-foreground">Réponse de la direction : </span>{f.management_response ? `${f.management_response} (${f.response_by_name}, ${formatDate(f.response_at)})` : "non reçue à la date du rapport."}</p>
          </div>
        ))}
      </section>
      {c.distribution && <section><h3 className="font-semibold">Diffusion</h3><p className="whitespace-pre-wrap">{c.distribution}</p></section>}
      {!c.draft && <p className="text-xs text-muted-foreground">Émis par {c.issued_by_name} le {formatDate(c.issued_at)} · empreinte SHA-256 {c.content_sha256}</p>}
    </article>
  );
}

export function ReportTab({ e }: { e: Engagement }) {
  const base = `/engagements/${e.id}/reports`;
  const { data, error, loading, setData } = useApiResource<Data>(base);
  const [sel, setSel] = useState<string | null>(null);
  const [form, setForm] = useState<{ title: string; executive_summary: string; overall_conclusion: string; distribution: string } | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  if (loading && !data) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  if (!data) return null;
  const caps = data.capabilities;
  const current = data.reports.find((r) => r.id === sel) ?? data.reports[0];
  const draft = data.reports.find((r) => r.status === "draft");
  const editing = form && current?.status === "draft";

  async function act(key: string, fn: () => Promise<Data | void>) {
    setBusy(key); setErr(null);
    try { const d = await fn(); if (d) setData(d); return true; } catch (x) { setErr(errorMessage(x)); return false; } finally { setBusy(null); }
  }
  const startEdit = (r: AuditReport) => setForm({ title: r.title, executive_summary: r.executive_summary ?? "", overall_conclusion: r.overall_conclusion ?? "", distribution: r.distribution ?? "" });

  return (
    <div className="space-y-4">
      {err && <Alert>{err}</Alert>}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-3xl text-sm text-muted-foreground">
          Le rapport reprend les constats communiqués, leurs recommandations, les plans d&apos;action et les réponses de la direction, tels que saisis par l&apos;équipe ; KOFINEX ne rédige aucun texte.
          L&apos;émission (associé) fige le contenu et son empreinte ; une nouvelle version le remplace si la mission est rouverte.
        </p>
        {caps.includes("edit_report") && !draft && (
          <Button size="sm" loading={busy === "new"} onClick={() => act("new", () => api.post<Data>(base, { title: `Rapport d'audit — ${e.name}` }))}><Plus className="h-4 w-4" /> {data.reports.length ? "Nouvelle version" : "Projet de rapport"}</Button>
        )}
      </div>
      {data.reports.length === 0 ? <EmptyState title="Aucun rapport" description={caps.includes("edit_report") ? "Créez le projet de rapport quand les constats sont validés." : "Le rapport n'a pas encore été émis."} /> : (
        <div className="grid gap-5 xl:grid-cols-[16rem_minmax(0,1fr)]">
          <Card>
            <CardHeader><CardTitle>Versions</CardTitle></CardHeader>
            <CardContent className="space-y-1">
              {data.reports.map((r) => (
                <button key={r.id} onClick={() => { setSel(r.id); setForm(null); }} aria-current={current?.id === r.id ? "true" : undefined}
                        className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted aria-[current=true]:bg-muted">
                  <span>v{r.version}{r.issued_at && <span className="block text-xs text-muted-foreground">{formatDate(r.issued_at)}</span>}</span>
                  <Badge tone={STATUS[r.status][1]}>{STATUS[r.status][0]}</Badge>
                </button>
              ))}
            </CardContent>
          </Card>
          {current && (
            <div className="space-y-4">
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={() => api.download(`${base}/${current.id}/docx`, `rapport-${e.reference}-v${current.version}.docx`)}><FileDown className="h-4 w-4" /> Word</Button>
                {current.status === "draft" && caps.includes("edit_report") && !editing && <Button size="sm" variant="outline" onClick={() => startEdit(current)}>Rédiger</Button>}
                {current.status === "draft" && caps.includes("issue_report") && <Button size="sm" onClick={() => setConfirm(true)}><FileSignature className="h-4 w-4" /> Émettre</Button>}
                {current.status === "draft" && caps.includes("edit_report") && <Button size="icon" variant="ghost" aria-label="Supprimer le projet" onClick={() => act("del", async () => { await api.del(`${base}/${current.id}`); setSel(null); return api.get<Data>(base); })}><Trash2 className="h-4 w-4" /></Button>}
              </div>
              {current.status !== "draft" && <p className="text-xs text-muted-foreground">Émis le {formatDate(current.issued_at)} par {personName(current.issued_by_user)} · empreinte {current.content_sha256?.slice(0, 16)}…</p>}
              {editing && form && (
                <Card>
                  <CardHeader><CardTitle>Rédaction</CardTitle><CardDescription>Ces textes sont les vôtres ; les constats se modifient dans l&apos;onglet « Constats ».</CardDescription></CardHeader>
                  <CardContent className="space-y-3">
                    <Field label="Titre" htmlFor="rp-t" required><Input id="rp-t" value={form.title} onChange={(x) => setForm({ ...form, title: x.target.value })} /></Field>
                    <Field label="Synthèse" htmlFor="rp-s"><textarea id="rp-s" rows={4} className={AREA} value={form.executive_summary} onChange={(x) => setForm({ ...form, executive_summary: x.target.value })} /></Field>
                    <Field label="Conclusion générale (requise pour émettre)" htmlFor="rp-c"><textarea id="rp-c" rows={4} className={AREA} value={form.overall_conclusion} onChange={(x) => setForm({ ...form, overall_conclusion: x.target.value })} /></Field>
                    <Field label="Diffusion" htmlFor="rp-d"><Input id="rp-d" value={form.distribution} onChange={(x) => setForm({ ...form, distribution: x.target.value })} /></Field>
                    <div className="flex justify-end gap-2"><Button variant="outline" onClick={() => setForm(null)}>Fermer</Button>
                      <Button loading={busy === "save"} onClick={async () => { if (await act("save", () => api.patch<Data>(`${base}/${current.id}`, form))) setForm(null); }}><Save className="h-4 w-4" /> Enregistrer</Button></div>
                  </CardContent>
                </Card>
              )}
              <Preview key={`${current.id}-${current.status}-${busy}`} e={e} r={current} />
            </div>
          )}
        </div>
      )}
      <Dialog open={confirm} onClose={() => setConfirm(false)} title="Émettre le rapport" description="Le contenu est figé avec son empreinte et devient visible de l'audité. Tous les constats doivent être communiqués.">
        <div className="flex justify-end gap-2"><Button variant="outline" onClick={() => setConfirm(false)}>Annuler</Button>
          <Button loading={busy === "issue"} onClick={async () => { if (current && await act("issue", () => api.post<Data>(`${base}/${current.id}/issue`, {}))) setConfirm(false); }}>Émettre</Button></div>
      </Dialog>
    </div>
  );
}
