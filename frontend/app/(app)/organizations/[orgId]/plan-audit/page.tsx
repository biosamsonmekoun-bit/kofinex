"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Plus } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { PLAN_STATUS, type AuditPlan } from "@/lib/ia-types";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading, PageHeader } from "@/components/ui/feedback";
import { Field, Input } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

export default function AuditPlansPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const router = useRouter();
  const { data, error, loading } = useApiResource<{ plans: AuditPlan[]; can_manage: boolean }>(`/organizations/${orgId}/audit-plans`);
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ title: "", period_start: "", period_end: "", description: "" });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function create(ev: React.FormEvent) {
    ev.preventDefault();
    setBusy(true); setErr(null);
    try {
      const p = await api.post<AuditPlan>(`/organizations/${orgId}/audit-plans`, { ...f, description: f.description || null });
      router.push(`/plan-audit/${p.id}`);
    } catch (x) { setErr(errorMessage(x)); setBusy(false); }
  }

  return (
    <>
      <PageHeader title="Plan d'audit"
                  description="Plan pluriannuel ou annuel des missions d'audit interne, fondé sur la cartographie des risques. L'approbation par l'instance compétente est enregistrée ; toute modification ultérieure est motivée et historisée."
                  actions={data?.can_manage && <Button size="sm" onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> Nouveau plan</Button>} />
      {loading && !data && <Loading />}
      {error && <Alert>{error}</Alert>}
      {data && data.plans.length === 0 && <EmptyState title="Aucun plan d'audit" description={data.can_manage ? "Créez le plan de la période, ajoutez les missions prévues puis enregistrez son approbation." : "Les propriétaires et administrateurs de l'organisation établissent le plan."} />}
      {data && data.plans.length > 0 && (
        <Table>
          <THead><tr><TH>Plan</TH><TH>Période</TH><TH className="text-right">Missions</TH><TH>Statut</TH><TH>Approbation</TH></tr></THead>
          <TBody>
            {data.plans.map((p) => (
              <TR key={p.id}>
                <TD className="font-medium"><Link className="text-link hover:underline" href={`/plan-audit/${p.id}`}>{p.title}</Link></TD>
                <TD>{formatDate(p.period_start)} – {formatDate(p.period_end)}</TD>
                <TD className="text-right">{typeof p.items === "number" ? p.items : "—"}</TD>
                <TD><Badge tone={PLAN_STATUS[p.status][1]}>{PLAN_STATUS[p.status][0]}</Badge></TD>
                <TD>{p.approval_body ? `${p.approval_body}, ${formatDate(p.approval_date)}` : "—"}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
      <Dialog open={open} onClose={() => setOpen(false)} title="Nouveau plan d'audit">
        <form onSubmit={create} className="space-y-3">
          {err && <Alert>{err}</Alert>}
          <Field label="Intitulé" htmlFor="pl-t" required><Input id="pl-t" required value={f.title} onChange={(x) => setF({ ...f, title: x.target.value })} /></Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Début de période" htmlFor="pl-s" required><Input id="pl-s" type="date" required value={f.period_start} onChange={(x) => setF({ ...f, period_start: x.target.value })} /></Field>
            <Field label="Fin de période" htmlFor="pl-e" required><Input id="pl-e" type="date" required value={f.period_end} onChange={(x) => setF({ ...f, period_end: x.target.value })} /></Field>
          </div>
          <Field label="Descriptif" htmlFor="pl-d"><Input id="pl-d" value={f.description} onChange={(x) => setF({ ...f, description: x.target.value })} /></Field>
          <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => setOpen(false)}>Annuler</Button><Button type="submit" loading={busy}>Créer</Button></div>
        </form>
      </Dialog>
    </>
  );
}
