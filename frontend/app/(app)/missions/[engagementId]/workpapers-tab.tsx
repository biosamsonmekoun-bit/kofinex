"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Plus } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { WORKPAPER_STATUS_LABELS, type Engagement, type WorkpaperDetail, type WorkpaperStatus, type WorkProgram } from "@/lib/types";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

export const WP_TONE: Record<WorkpaperStatus, "neutral" | "blue" | "amber" | "green"> = { draft: "neutral", prepared: "blue", reviewed: "amber", approved: "green" };

interface Row { id: string; procedure_id: string | null; reference: string; title: string; status: WorkpaperStatus; version: number; updated_at: string; open_notes: number }

export function WorkpapersTab({ e }: { e: Engagement }) {
  const router = useRouter();
  const { data, error, loading } = useApiResource<Row[]>(`/engagements/${e.id}/workpapers`);
  const { data: programs } = useApiResource<WorkProgram[]>(`/engagements/${e.id}/programs`);
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ reference: "", title: "", procedure_id: "" });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const canEdit = (e.capabilities ?? []).includes("edit_workpapers");
  const procs = (programs ?? []).flatMap((p) => p.procedures);

  async function create(ev: React.FormEvent) {
    ev.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const w = await api.post<WorkpaperDetail>(`/engagements/${e.id}/workpapers`, { ...f, procedure_id: f.procedure_id || null });
      router.push(`/missions/${e.id}/feuilles/${w.id}`);
    } catch (x) { setErr(errorMessage(x)); setBusy(false); }
  }

  if (loading && !data) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">Circuit : préparée → revue → approuvée. Toute modification d&apos;une feuille signée la renvoie en brouillon et révoque ses signatures.</p>
        {canEdit && <Button size="sm" onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> Feuille de travail</Button>}
      </div>
      {data && data.length === 0 ? <EmptyState title="Aucune feuille de travail" /> : (
        <Table>
          <THead><tr><TH>Référence</TH><TH>Titre</TH><TH>Procédure</TH><TH>Statut</TH><TH className="text-right">Version</TH><TH>Notes ouvertes</TH><TH>Modifiée le</TH></tr></THead>
          <TBody>
            {data?.map((w) => (
              <TR key={w.id}>
                <TD className="font-medium"><Link className="text-link hover:underline" href={`/missions/${e.id}/feuilles/${w.id}`}>{w.reference}</Link></TD>
                <TD>{w.title}</TD>
                <TD>{procs.find((p) => p.id === w.procedure_id)?.code ?? "—"}</TD>
                <TD><Badge tone={WP_TONE[w.status]}>{WORKPAPER_STATUS_LABELS[w.status]}</Badge></TD>
                <TD className="text-right">{w.version}</TD>
                <TD>{w.open_notes ? <Badge tone="amber">{w.open_notes}</Badge> : "—"}</TD>
                <TD>{formatDate(w.updated_at)}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
      <Dialog open={open} onClose={() => setOpen(false)} title="Nouvelle feuille de travail">
        <form onSubmit={create} className="space-y-3">
          {err && <Alert>{err}</Alert>}
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Référence" htmlFor="w-ref" required><Input id="w-ref" value={f.reference} onChange={(x) => setF({ ...f, reference: x.target.value })} required /></Field>
            <div className="sm:col-span-2"><Field label="Titre" htmlFor="w-title" required><Input id="w-title" value={f.title} onChange={(x) => setF({ ...f, title: x.target.value })} required /></Field></div>
          </div>
          <Field label="Procédure" htmlFor="w-proc">
            <Select id="w-proc" value={f.procedure_id} onChange={(x) => setF({ ...f, procedure_id: x.target.value })}>
              <option value="">—</option>{procs.map((p) => <option key={p.id} value={p.id}>{p.code} — {p.title}</option>)}
            </Select>
          </Field>
          <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => setOpen(false)}>Annuler</Button><Button type="submit" loading={busy}>Créer</Button></div>
        </form>
      </Dialog>
    </div>
  );
}
