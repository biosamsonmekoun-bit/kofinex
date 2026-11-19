"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useApiResource } from "@/lib/use-api";
import type { Company, Engagement } from "@/lib/types";
import type { IcTestBrief } from "@/lib/ic-types";
import { formatDate } from "@/lib/utils";
import { IcShell } from "@/components/ic-shell";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const IC_TYPES = ["ic_assessment", "internal_audit"];

export default function IcProgramsPage() {
  const { companyId: cid } = useParams<{ companyId: string }>();
  const { data: company } = useApiResource<Company>(`/companies/${cid}`);
  const { data: engagements, error } = useApiResource<Engagement[]>(company ? `/organizations/${company.organization_id}/engagements` : null);
  const { data: tests } = useApiResource<IcTestBrief[]>(`/companies/${cid}/ic/tests`);
  const missions = engagements?.filter((e) => e.company_id === cid && IC_TYPES.includes(e.engagement_type));
  const stats = (id: string) => {
    const t = tests?.filter((x) => x.engagement_id === id) ?? [];
    return { total: t.length, design: t.filter((x) => x.test_type === "design").length, operating: t.filter((x) => x.test_type === "operating").length,
             reviewed: t.filter((x) => x.status === "reviewed").length };
  };
  return (
    <IcShell cid={cid} title="Programmes de contrôle"
             description="Les programmes se conçoivent dans une mission (onglet Contrôle interne) : un programme de travail du socle d'audit, une procédure et un test planifié par contrôle et par type de test.">
      {() => (
        <div className="space-y-4">
          {error && <Alert>{error}</Alert>}
          {!missions ? <Loading /> : missions.length === 0 ? (
            <EmptyState title="Aucune mission de contrôle interne" description="Créez une mission « évaluation du contrôle interne » ou « audit interne » pour cette entité."
                        action={company ? <Link className="text-sm text-link underline" href={`/organizations/${company.organization_id}/missions`}>Ouvrir les missions</Link> : undefined} />
          ) : (
            <Card>
              <CardHeader><CardTitle>Missions de l&apos;entité</CardTitle><CardDescription>Missions visibles pour vous ; les tests comptés sont ceux auxquels vous avez accès.</CardDescription></CardHeader>
              <CardContent>
                <Table>
                  <THead><tr><TH>Mission</TH><TH>Type</TH><TH>Période</TH><TH>Statut</TH><TH>Tests</TH><TH>Conception / efficacité</TH><TH>Revus</TH></tr></THead>
                  <TBody>{missions.map((e) => {
                    const s = stats(e.id);
                    return (
                      <TR key={e.id}>
                        <TD><Link className="text-link hover:underline" href={`/missions/${e.id}?tab=ic`}>{e.reference} — {e.name}</Link></TD>
                        <TD>{e.type_label}</TD>
                        <TD>{e.period_start ? `${formatDate(e.period_start)} → ${formatDate(e.period_end)}` : "—"}</TD>
                        <TD><Badge>{e.status_label}</Badge></TD>
                        <TD>{s.total}</TD><TD>{s.design} / {s.operating}</TD><TD>{s.reviewed}</TD>
                      </TR>
                    );
                  })}</TBody>
                </Table>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </IcShell>
  );
}
