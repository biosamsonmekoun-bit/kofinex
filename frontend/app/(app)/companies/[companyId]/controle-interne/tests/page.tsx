"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useApiResource } from "@/lib/use-api";
import { ASSESSMENT_STATUS, CONCLUSION, SCOPES, TEST_STATUS, type IcAssessment, type IcTestBrief } from "@/lib/ic-types";
import { formatDate } from "@/lib/utils";
import { IcShell } from "@/components/ic-shell";
import { Pager, SearchBox, useListView } from "@/components/ic-list";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

export default function IcTestsPage() {
  const { companyId: cid } = useParams<{ companyId: string }>();
  const [status, setStatus] = useState("");
  const [type, setType] = useState("");
  const [concl, setConcl] = useState("");
  const { data, error, loading } = useApiResource<IcTestBrief[]>(`/companies/${cid}/ic/tests${status ? `?status_filter=${status}` : ""}`);
  const { data: assessments } = useApiResource<IcAssessment[]>(`/companies/${cid}/ic/assessments`);
  const rows = data?.filter((t) => (!type || t.test_type === type) && (!concl || (concl === "none" ? !t.conclusion : t.conclusion === concl)));
  const v = useListView(rows, {
    text: (t) => `${t.reference} ${t.control ?? ""} ${t.engagement_reference ?? ""}`,
    sort: { ref: (t) => t.reference, control: (t) => t.control ?? null, end: (t) => t.period_end, reviewed: (t) => t.reviewed_at ?? null },
  });
  return (
    <IcShell cid={cid} title="Tests et évaluations"
             description="Tests de conception et d'efficacité des missions dont vous êtes membre, et tests revus des autres missions. Chaque nouveau test s'ajoute aux précédents : aucun résultat n'est écrasé.">
      {() => (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center gap-3">
            <SearchBox value={v.q} onChange={v.setQ} />
            <Select aria-label="Statut" className="w-40" value={status} onChange={(x) => setStatus(x.target.value)}>
              <option value="">Tous statuts</option>{Object.entries(TEST_STATUS).map(([k, [l]]) => <option key={k} value={k}>{l}</option>)}
            </Select>
            <Select aria-label="Type" className="w-44" value={type} onChange={(x) => setType(x.target.value)}>
              <option value="">Tous types</option><option value="design">Conception</option><option value="operating">Efficacité opérationnelle</option>
            </Select>
            <Select aria-label="Conclusion" className="w-48" value={concl} onChange={(x) => setConcl(x.target.value)}>
              <option value="">Toutes conclusions</option><option value="none">Sans conclusion</option>{Object.entries(CONCLUSION).map(([k, [l]]) => <option key={k} value={k}>{l}</option>)}
            </Select>
          </div>
          {error && <Alert>{error}</Alert>}
          {loading && !data && <Loading />}
          {data && data.length === 0 && <EmptyState title="Aucun test" description="Les tests se créent dans une mission d'évaluation du contrôle interne ou d'audit interne (onglet Contrôle interne)." />}
          {data && data.length > 0 && (
            <Card><CardContent className="pt-5">
              <Table>
                <THead><tr>{v.sortTh("ref", "Test")}{v.sortTh("control", "Contrôle")}<TH>Type</TH>{v.sortTh("end", "Période")}<TH>Mission</TH><TH>Statut</TH>{v.sortTh("reviewed", "Revu le")}<TH>Conclusion</TH></tr></THead>
                <TBody>{v.rows.map((t) => (
                  <TR key={t.id}>
                    <TD><Link className="text-link hover:underline" href={`/missions/${t.engagement_id}?tab=ic&test=${t.id}`}>{t.reference}</Link></TD>
                    <TD>{t.control_id ? <Link className="hover:underline" href={`/companies/${cid}/controle-interne/controles/${t.control_id}`}>{t.control}</Link> : t.control}</TD>
                    <TD>{t.test_type === "design" ? "Conception" : "Efficacité"}</TD>
                    <TD>{t.period_start ? `${formatDate(t.period_start)} → ${formatDate(t.period_end)}` : "—"}</TD>
                    <TD>{t.engagement_reference}</TD>
                    <TD><Badge tone={TEST_STATUS[t.status]?.[1]}>{TEST_STATUS[t.status]?.[0]}</Badge></TD>
                    <TD>{formatDate(t.reviewed_at)}</TD>
                    <TD>{t.conclusion ? <Badge tone={CONCLUSION[t.conclusion][1]}>{t.conclusion_label}</Badge> : "—"}</TD>
                  </TR>
                ))}</TBody>
              </Table>
              <Pager {...v} />
            </CardContent></Card>
          )}
          <Card>
            <CardHeader><CardTitle>Évaluations du dispositif</CardTitle><CardDescription>Évaluations approuvées, et celles des missions dont vous êtes membre. Les évaluations historiques restent consultables ; la synthèse est figée à la soumission.</CardDescription></CardHeader>
            <CardContent>
              {!assessments ? <Loading /> : assessments.length === 0 ? <p className="text-sm text-muted-foreground">Aucune évaluation.</p> : (
                <Table>
                  <THead><tr><TH>Référence</TH><TH>Niveau évalué</TH><TH>Au</TH><TH>Niveau de maîtrise</TH><TH>Synthèse</TH><TH>Statut</TH></tr></THead>
                  <TBody>{assessments.map((a) => (
                    <TR key={a.id}>
                      <TD><Link className="text-link hover:underline" href={`/missions/${a.engagement_id}?tab=ic`}>{a.reference}</Link></TD>
                      <TD>{SCOPES[a.scope_type]}{a.cycle_code && ` ${a.cycle_code}`}</TD>
                      <TD>{formatDate(a.as_of_date)}</TD>
                      <TD>{a.rating_code ?? "—"}</TD>
                      <TD className="text-xs">{a.basis ? `${a.basis.effective}/${a.basis.controls} efficace(s), ${a.basis.ineffective} inefficace(s), ${a.basis.not_tested} non testé(s), ${a.basis.uncovered_risks} risque(s) non couvert(s)` : "—"}</TD>
                      <TD><Badge tone={ASSESSMENT_STATUS[a.status]?.[1]}>{ASSESSMENT_STATUS[a.status]?.[0]}</Badge></TD>
                    </TR>
                  ))}</TBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </IcShell>
  );
}
