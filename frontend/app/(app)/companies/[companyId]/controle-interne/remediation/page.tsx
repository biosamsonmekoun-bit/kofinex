"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useApiResource } from "@/lib/use-api";
import { ACTION_STATUS, type ActionStatus } from "@/lib/ia-types";
import type { IcActionPlan } from "@/lib/ic-types";
import { formatDate } from "@/lib/utils";
import { IcShell } from "@/components/ic-shell";
import { Pager, SearchBox, useListView } from "@/components/ic-list";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Select } from "@/components/ui/form";
import { KpiCard } from "@/components/ui/kpi-card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

type Plan = IcActionPlan & { deficiency_id: string; deficiency_reference: string; recommendation: string; engagement_reference: string };

export default function IcRemediationPage() {
  const { companyId: cid } = useParams<{ companyId: string }>();
  const [status, setStatus] = useState("");
  const { data, error, loading } = useApiResource<Plan[]>(`/companies/${cid}/ic/action-plans${status ? `?status_filter=${status}` : ""}`);
  const v = useListView(data, {
    text: (a) => `${a.description} ${a.owner_name} ${a.deficiency_reference} ${a.recommendation}`,
    sort: { due: (a) => a.due_date, owner: (a) => a.owner_name, status: (a) => a.status, def: (a) => a.deficiency_reference },
  });
  const count = (s: string) => data?.filter((a) => a.status === s).length ?? 0;
  return (
    <IcShell cid={cid} title="Plans de remédiation" description="Plans d'action rattachés aux recommandations des déficiences. L'historique de chaque plan est conservé et reste accessible après l'émission de la mission.">
      {() => (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <SearchBox value={v.q} onChange={v.setQ} />
            <Select aria-label="Statut" className="w-56" value={status} onChange={(x) => setStatus(x.target.value)}>
              <option value="">Tous les statuts</option>{(Object.keys(ACTION_STATUS) as ActionStatus[]).map((k) => <option key={k} value={k}>{ACTION_STATUS[k][0]}</option>)}
            </Select>
          </div>
          {error && <Alert>{error}</Alert>}
          {loading && !data && <Loading />}
          {data && !status && (
            <div className="grid gap-3 sm:grid-cols-5">
              <KpiCard label="Plans" value={data.length} />
              <KpiCard label="Prévus" value={count("planned")} />
              <KpiCard label="En cours" value={count("in_progress")} />
              <KpiCard label="Déclarés mis en œuvre" value={count("implemented")} />
              <KpiCard label="Vérifiés" value={count("verified")} />
            </div>
          )}
          {data && data.length === 0 && <EmptyState title="Aucun plan d'action" description="Les plans d'action se définissent sur les recommandations, dans la mission." />}
          {data && data.length > 0 && (
            <Card><CardContent className="pt-5">
              <Table>
                <THead><tr><TH>Action</TH>{v.sortTh("def", "Déficience")}{v.sortTh("owner", "Responsable")}{v.sortTh("due", "Échéance")}{v.sortTh("status", "Statut")}<TH>Mission</TH></tr></THead>
                <TBody>{v.rows.map((a) => (
                  <TR key={a.id}>
                    <TD>{a.description}<span className="block text-xs text-muted-foreground">{a.recommendation}</span></TD>
                    <TD>{a.deficiency_reference}</TD><TD>{a.owner_name}</TD>
                    <TD>{formatDate(a.due_date)} {a.overdue && <Badge tone="red">En retard</Badge>}</TD>
                    <TD><Badge tone={ACTION_STATUS[a.status as ActionStatus]?.[1]}>{ACTION_STATUS[a.status as ActionStatus]?.[0] ?? a.status}</Badge></TD>
                    <TD><Link className="text-link hover:underline" href={`/missions/${a.engagement_id}?tab=findings`}>{a.engagement_reference}</Link></TD>
                  </TR>
                ))}</TBody>
              </Table>
              <Pager {...v} />
            </CardContent></Card>
          )}
        </div>
      )}
    </IcShell>
  );
}
