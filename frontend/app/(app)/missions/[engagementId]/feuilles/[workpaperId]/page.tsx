"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ChevronLeft, Link2, PenLine, Save, Unlink } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import {
  SIGNOFF_LABELS, WORKPAPER_STATUS_LABELS, personName, type Engagement, type EvidenceItem, type Signoff, type WorkpaperDetail,
} from "@/lib/types";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, Loading, PageHeader } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { NoteCard } from "../../notes-tab";
import { WP_TONE } from "../../workpapers-tab";

const AREA = "w-full rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30 disabled:opacity-70";

export default function WorkpaperPage() {
  const { engagementId, workpaperId } = useParams<{ engagementId: string; workpaperId: string }>();
  const base = `/engagements/${engagementId}`;
  const { data: e } = useApiResource<Engagement>(base);
  const { data: w, error, loading, setData } = useApiResource<WorkpaperDetail>(`${base}/workpapers/${workpaperId}`);
  const { data: evidence } = useApiResource<EvidenceItem[]>(`${base}/evidence`);
  const [draft, setDraft] = useState<Partial<WorkpaperDetail> | null>(null);
  const [msg, setMsg] = useState<{ kind: "error" | "success" | "warning"; text: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [revoke, setRevoke] = useState<Signoff | null>(null);
  const [reason, setReason] = useState("");
  const [note, setNote] = useState({ body: "", assigned_to: "" });
  const [linkId, setLinkId] = useState("");

  if (loading && !w) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  if (!w || !e) return <Loading />;
  const caps = e.capabilities ?? [];
  const canEdit = caps.includes("edit_workpapers");
  const v = { ...w, ...(draft ?? {}) };
  const active = w.signoffs.filter((s) => !s.revoked_at);
  const has = (r: Signoff["signoff_role"]) => active.some((s) => s.signoff_role === r);
  const openNotes = w.review_notes.filter((n) => n.status !== "closed").length;

  async function run(key: string, fn: () => Promise<WorkpaperDetail | unknown>, ok?: string) {
    setBusy(key);
    setMsg(null);
    try {
      const r = await fn();
      if (r && typeof r === "object" && "content_hash" in (r as object)) setData(r as WorkpaperDetail);
      else setData(await api.get<WorkpaperDetail>(`${base}/workpapers/${workpaperId}`));
      if (ok) setMsg({ kind: "success", text: ok });
    } catch (x) { setMsg({ kind: "error", text: errorMessage(x) }); } finally { setBusy(null); }
  }

  async function save() {
    const signed = w!.status !== "draft";
    await run("save", () => api.patch<WorkpaperDetail>(`${base}/workpapers/${w!.id}`, {
      reference: v.reference, title: v.title, procedure_id: v.procedure_id, objective: v.objective || null,
      work_performed: v.work_performed || null, conclusion: v.conclusion || null, content: v.content ?? {},
    }), signed ? "Feuille enregistrée : elle repasse en brouillon et ses signatures sont révoquées." : "Feuille enregistrée.");
    setDraft(null);
  }

  const signButtons: [Signoff["signoff_role"], string, boolean][] = [
    ["preparer", "Signer « préparé par »", caps.includes("sign_preparer") && !has("preparer")],
    ["reviewer", "Signer « revu par »", caps.includes("sign_reviewer") && has("preparer") && !has("reviewer")],
    ["approver", "Approuver", caps.includes("sign_approver") && has("reviewer") && !has("approver")],
    ["quality_reviewer", "Signer la revue qualité", caps.includes("sign_quality") && !has("quality_reviewer")],
  ];
  const linkable = (evidence ?? []).filter((x) => !w.evidence.some((l) => l.id === x.id));

  return (
    <>
      <Link href={`/missions/${engagementId}?tab=workpapers`} className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ChevronLeft className="h-4 w-4" /> {e.reference} — feuilles de travail
      </Link>
      <PageHeader title={`${w.reference} — ${w.title}`}
                  description={<span className="flex flex-wrap items-center gap-2"><Badge tone={WP_TONE[w.status]}>{WORKPAPER_STATUS_LABELS[w.status]}</Badge>
                    <span>Version {w.version} · modifiée le {formatDate(w.updated_at)} par {personName(w.updated_by_user)}</span>
                    <code className="text-xs" title="Empreinte du contenu signé">{w.content_hash.slice(0, 12)}…</code></span>}
                  actions={canEdit && <Button size="sm" onClick={save} loading={busy === "save"} disabled={!draft}><Save className="h-4 w-4" /> Enregistrer</Button>} />
      {msg && <Alert kind={msg.kind} className="mb-4">{msg.text}</Alert>}
      {draft && w.status !== "draft" && <Alert kind="warning" className="mb-4">Cette feuille est signée : l&apos;enregistrement révoquera ses signatures.</Alert>}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="space-y-4">
          <Card>
            <CardContent className="space-y-3 pt-5">
              <div className="grid gap-3 sm:grid-cols-3">
                <Field label="Référence" htmlFor="wp-ref"><Input id="wp-ref" value={v.reference} disabled={!canEdit} onChange={(x) => setDraft({ ...draft, reference: x.target.value })} /></Field>
                <div className="sm:col-span-2"><Field label="Titre" htmlFor="wp-title"><Input id="wp-title" value={v.title} disabled={!canEdit} onChange={(x) => setDraft({ ...draft, title: x.target.value })} /></Field></div>
              </div>
              <Field label="Objectif" htmlFor="wp-obj"><textarea id="wp-obj" rows={2} className={AREA} value={v.objective ?? ""} disabled={!canEdit} onChange={(x) => setDraft({ ...draft, objective: x.target.value })} /></Field>
              <Field label="Travaux réalisés" htmlFor="wp-work"><textarea id="wp-work" rows={10} className={AREA} value={v.work_performed ?? ""} disabled={!canEdit} onChange={(x) => setDraft({ ...draft, work_performed: x.target.value })} /></Field>
              <Field label="Conclusion" htmlFor="wp-concl"><textarea id="wp-concl" rows={3} className={AREA} value={v.conclusion ?? ""} disabled={!canEdit} onChange={(x) => setDraft({ ...draft, conclusion: x.target.value })} /></Field>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Notes de revue ({openNotes} à traiter)</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {w.review_notes.map((n) => <NoteCard key={n.id} e={e} n={n} onChanged={() => run("note", async () => null)} />)}
              {caps.includes("write_review_notes") && (
                <form className="space-y-2" onSubmit={(x) => { x.preventDefault(); void run("note-add", () => api.post(`${base}/review-notes`, {
                  object_type: "workpaper", object_id: w.id, body: note.body, assigned_to: note.assigned_to || null })).then(() => setNote({ body: "", assigned_to: "" })); }}>
                  <textarea aria-label="Nouvelle note de revue" rows={2} className={AREA} placeholder="Nouvelle note de revue…" value={note.body} onChange={(x) => setNote({ ...note, body: x.target.value })} />
                  <div className="flex flex-wrap gap-2">
                    <Select aria-label="Destinataire" className="w-56" value={note.assigned_to} onChange={(x) => setNote({ ...note, assigned_to: x.target.value })}>
                      <option value="">Destinataire (facultatif)</option>
                      {(e.members ?? []).filter((m) => !["auditee", "observer"].includes(m.role)).map((m) => <option key={m.user_id} value={m.user_id}>{personName(m.user)}</option>)}
                    </Select>
                    <Button type="submit" size="sm" loading={busy === "note-add"} disabled={!note.body.trim()}>Ajouter la note</Button>
                  </div>
                </form>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Signatures</CardTitle>
              <CardDescription>Chaque signature porte l&apos;empreinte du contenu ; le réviseur doit être différent du préparateur et d&apos;un rôle supérieur.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              {w.signoffs.length === 0 && <p className="text-muted-foreground">Aucune signature.</p>}
              {w.signoffs.map((s) => (
                <div key={s.id} className="border-b pb-2">
                  <div className="flex items-center justify-between gap-2">
                    <span>{SIGNOFF_LABELS[s.signoff_role]} <strong>{personName(s.user)}</strong></span>
                    {s.revoked_at ? <Badge>Révoquée</Badge> : <Badge tone="green">Active</Badge>}
                  </div>
                  <p className="text-xs text-muted-foreground">{formatDate(s.signed_at)}{s.revoked_at && ` — ${s.revoked_reason}`}</p>
                  {!s.revoked_at && !["issued", "archived"].includes(e.status) && (
                    <Button variant="link" size="sm" className="h-auto p-0 text-xs" onClick={() => { setRevoke(s); setReason(""); }}>Révoquer</Button>
                  )}
                </div>
              ))}
              <div className="flex flex-col gap-2">
                {signButtons.filter(([, , show]) => show).map(([role, label]) => (
                  <Button key={role} size="sm" variant={role === "approver" ? "default" : "outline"} loading={busy === role}
                          disabled={!!draft} onClick={() => run(role, () => api.post<WorkpaperDetail>(`${base}/workpapers/${w.id}/sign`, { role }))}>
                    <PenLine className="h-4 w-4" /> {label}
                  </Button>
                ))}
                {draft && <p className="text-xs text-muted-foreground">Enregistrez la feuille avant de la signer.</p>}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Éléments probants</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-sm">
              {w.evidence.length === 0 && <p className="text-muted-foreground">Aucun élément rattaché.</p>}
              {w.evidence.map((x) => (
                <div key={x.link_id} className="flex items-center justify-between gap-2">
                  <span>{x.title} <code className="text-xs text-muted-foreground">{x.sha256.slice(0, 8)}</code></span>
                  {canEdit && w.status === "draft" && <Button variant="ghost" size="icon" aria-label={`Détacher ${x.title}`} onClick={() => run("unlink", () => api.del(`${base}/evidence-links/${x.link_id}`))}><Unlink className="h-4 w-4" /></Button>}
                </div>
              ))}
              {caps.includes("add_evidence") && w.status === "draft" && linkable.length > 0 && (
                <div className="flex gap-2 pt-2">
                  <Select aria-label="Élément à rattacher" value={linkId} onChange={(x) => setLinkId(x.target.value)}>
                    <option value="">Rattacher un élément…</option>{linkable.map((x) => <option key={x.id} value={x.id}>{x.title}</option>)}
                  </Select>
                  <Button size="sm" variant="outline" disabled={!linkId} loading={busy === "link"}
                          onClick={() => run("link", () => api.post(`${base}/evidence/${linkId}/links`, { object_type: "workpaper", object_id: w.id })).then(() => setLinkId(""))}>
                    <Link2 className="h-4 w-4" />
                  </Button>
                </div>
              )}
              {w.status !== "draft" && <p className="text-xs text-muted-foreground">Feuille signée : les rattachements sont figés.</p>}
            </CardContent>
          </Card>
        </div>
      </div>

      <Dialog open={revoke !== null} onClose={() => setRevoke(null)} title="Révoquer la signature" description="Le motif est conservé ; les signatures qui en dépendent sont révoquées aussi.">
        <div className="space-y-3">
          <Field label="Motif" htmlFor="rv" required><Input id="rv" value={reason} onChange={(x) => setReason(x.target.value)} /></Field>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setRevoke(null)}>Annuler</Button>
            <Button variant="destructive" disabled={reason.trim().length < 3} loading={busy === "revoke"}
                    onClick={() => run("revoke", () => api.post(`${base}/signoffs/${revoke!.id}/revoke`, { reason })).then(() => setRevoke(null))}>Révoquer</Button>
          </div>
        </div>
      </Dialog>
    </>
  );
}
