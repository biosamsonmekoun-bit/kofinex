"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useApiResource } from "@/lib/use-api";
import { ACTION_STATUS, type ActionStatus } from "@/lib/ia-types";
import { pct, type IcActionPlan, type IcDashboard } from "@/lib/ic-types";
import { formatDate } from "@/lib/utils";
import { IcShell } from "@/components/ic-shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, Badge, Loading } from "@/components/ui/feedback";
import { KpiCard } from "@/components/ui/kpi-card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

type Plan = IcActionPlan & { deficiency_reference: string; recommendation: string; engagement_reference: string };
const OPEN = ["planned", "in_progress", "implemented"];

export default function IcFollowUpPage() {
  const { companyId: cid } = useParams<{ companyId: string }>();
  const [onlyOverdue, setOnlyOverdue] = useState(false);
  const { data, error, loading } = useApiResource<Plan[]>(`/companies/${cid}/ic/action-plans${onlyOverdue ? "?overdue=true" : ""}`);
  const { data: dash } = useApiResource<IcDashboard>(`/companies/${cid}/ic/dashboard`);
  const today = new Date().toISOString().slice(0, 10);
  const in30 = new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10);
  const groups: [string, string, Plan[]][] = data ? [
    ["late", "En retard", data.filter((a) => a.overdue)],
    ["soon", "Échéance dans les 30 jours", data.filter((a) => !a.overdue && ["planned", "in_progress"].includes(a.status) && a.due_date >= today && a.due_date <= in30)],
    ["verify", "Déclarées mises en œuvre, à vérifier", data.filter((a) => a.status === "implemented")],
    ["later", "Autres actions ouvertes", data.filter((a) => OPEN.includes(a.status) && a.status !== "implemented" && !a.overdue && a.due_date > in30)],
  ] : [];
  return (
    <IcShell cid={cid} title="Suivi des actions"
             description="Les mises à jour de suivi et les vérifications se saisissent dans la mission d'origine, selon les droits de chacun (responsable du suivi, vérificateur distinct) ; elles restent possibles après l'émission.">
      {() => (
        <div className="space-y-4">
          {dash && (
            <div className="grid gap-3 sm:grid-cols-4">
              <KpiCard label="Plans d'action" value={dash.action_plans} />
              <KpiCard label="En retard" value={dash.action_plans_overdue} />
              <KpiCard label="Mise en œuvre des recommandations" value={pct(dash.implementation_rate)} />
              <KpiCard label="Mise en œuvre vérifiée" value={pct(dash.verified_rate)} />
            </div>
          )}
          <div className="flex justify-end">
            <Button size="sm" variant={onlyOverdue ? "default" : "outline"} onClick={() => setOnlyOverdue(!onlyOverdue)}>{onlyOverdue ? "Toutes les actions" : "Seulement en retard"}</Button>
          </div>
          {error && <Alert>{error}</Alert>}
          {loading && !data && <Loading />}
          {groups.map(([k, title, rows]) => (
            <Card key={k}>
              <CardHeader><CardTitle>{title}</CardTitle><CardDescription>{rows.length} action(s)</CardDescription></CardHeader>
              {rows.length > 0 && (
                <CardContent>
                  <Table>
                    <THead><tr><TH>Action</TH><TH>Responsable</TH><TH>Échéance</TH><TH>Statut</TH><TH>Déficience</TH><TH /></tr></THead>
                    <TBody>{[...rows].sort((a, b) => a.due_date.localeCompare(b.due_date)).map((a) => (
                      <TR key={a.id}>
                        <TD>{a.description}<span className="block text-xs text-muted-foreground">{a.recommendation}</span></TD>
                        <TD>{a.owner_name}</TD><TD>{formatDate(a.due_date)}</TD>
                        <TD><Badge tone={ACTION_STATUS[a.status as ActionStatus]?.[1]}>{ACTION_STATUS[a.status as ActionStatus]?.[0] ?? a.status}</Badge></TD>
                        <TD>{a.deficiency_reference}</TD>
                        <TD className="text-right"><Link className="text-sm text-link hover:underline" href={`/missions/${a.engagement_id}?tab=findings`}>Suivre dans {a.engagement_reference}</Link></TD>
                      </TR>
                    ))}</TBody>
                  </Table>
                </CardContent>
              )}
            </Card>
          ))}
        </div>
      )}
    </IcShell>
  );
}
