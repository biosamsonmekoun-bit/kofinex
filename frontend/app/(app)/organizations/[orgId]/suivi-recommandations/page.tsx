"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useApiResource } from "@/lib/use-api";
import type { Company } from "@/lib/types";
import { ACTION_STATUS, type ActionPlan, type ActionStatus } from "@/lib/ia-types";
import { formatDate } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, Badge, EmptyState, Loading, PageHeader } from "@/components/ui/feedback";
import { Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

type Row = ActionPlan & { company: string | null; engagement: { id: string; reference: string; name: string; status: string };
  finding: { id: string; reference: string; title: string; rating_code: string | null }; recommendation: { id: string; reference: string; text: string } };
type Data = { actions: Row[]; summary: { total: number; by_status: Record<string, number>; overdue: number; closed: number } };

export default function FollowUpPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const [company, setCompany] = useState("");
  const [status, setStatus] = useState<"open" | "all" | ActionStatus>("open");
  const [overdue, setOverdue] = useState(false);
  const qs = new URLSearchParams();
  if (company) qs.set("company_id", company);
  if (status === "open") qs.set("status_filter", "planned,in_progress,implemented,not_implemented");
  else if (status !== "all") qs.set("status_filter", status);
  if (overdue) qs.set("overdue", "true");
  const { data, error, loading } = useApiResource<Data>(`/organizations/${orgId}/action-plans?${qs.toString()}`);
  const { data: companies } = useApiResource<Company[]>(`/organizations/${orgId}/companies`);

  return (
    <>
      <PageHeader title="Suivi des recommandations"
                  description="Plans d'action de toutes les missions qui vous sont accessibles. Le suivi (mises à jour, vérification de la mise en œuvre) se fait depuis l'onglet « Constats et recommandations » de chaque mission, y compris après son émission." />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Select aria-label="Entité" className="w-56" value={company} onChange={(x) => setCompany(x.target.value)}>
          <option value="">Toutes les entités</option>{companies?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </Select>
        <Select aria-label="Statut" className="w-56" value={status} onChange={(x) => setStatus(x.target.value as typeof status)}>
          <option value="open">Non clôturées</option><option value="all">Toutes</option>
          {(Object.keys(ACTION_STATUS) as ActionStatus[]).map((s) => <option key={s} value={s}>{ACTION_STATUS[s][0]}</option>)}
        </Select>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="h-4 w-4" checked={overdue} onChange={(x) => setOverdue(x.target.checked)} /> En retard uniquement</label>
      </div>
      {loading && !data && <Loading />}
      {error && <Alert>{error}</Alert>}
      {data && (
        <>
          <div className="mb-4 grid gap-3 sm:grid-cols-4">
            {[["Plans d'action", data.summary.total], ["En retard", data.summary.overdue], ["Clôturés (vérifiés ou risque accepté)", data.summary.closed],
              ["Mis en œuvre, à vérifier", data.summary.by_status.implemented ?? 0]].map(([l, v]) => (
              <Card key={String(l)}><CardContent className="pt-4"><p className="text-xs text-muted-foreground">{l}</p><p className="text-xl font-semibold tabular-nums">{v}</p></CardContent></Card>
            ))}
          </div>
          {data.actions.length === 0 ? <EmptyState title="Aucun plan d'action" /> : (
            <Table>
              <THead><tr><TH>Entité</TH><TH>Mission</TH><TH>Constat / recommandation</TH><TH>Action</TH><TH>Responsable</TH><TH>Échéance</TH><TH>Statut</TH></tr></THead>
              <TBody>{data.actions.map((a) => (
                <TR key={a.id}>
                  <TD>{a.company}</TD>
                  <TD><Link className="text-link hover:underline" href={`/missions/${a.engagement.id}?tab=findings`}>{a.engagement.reference}</Link></TD>
                  <TD><span className="font-medium">{a.finding.reference}</span> {a.finding.title}<p className="text-xs text-muted-foreground">{a.recommendation.reference} — {a.recommendation.text}</p></TD>
                  <TD>{a.description}</TD><TD>{a.owner_name}</TD>
                  <TD className="whitespace-nowrap">{formatDate(a.due_date)}{a.overdue && <Badge tone="red" className="ml-1">En retard</Badge>}</TD>
                  <TD><Badge tone={ACTION_STATUS[a.status][1]}>{ACTION_STATUS[a.status][0]}</Badge></TD>
                </TR>))}
              </TBody>
            </Table>
          )}
        </>
      )}
    </>
  );
}
