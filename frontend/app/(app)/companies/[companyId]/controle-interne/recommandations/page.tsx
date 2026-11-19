"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useApiResource } from "@/lib/use-api";
import { STAGE_TONE, pct, type IcDeficiency } from "@/lib/ic-types";
import { IcShell } from "@/components/ic-shell";
import { useIcRefs } from "@/components/ic-forms";
import { Pager, SearchBox, useListView } from "@/components/ic-list";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Select } from "@/components/ui/form";
import { KpiCard } from "@/components/ui/kpi-card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

type Rec = { id: string; reference: string; text: string; plans: number; done: number; overdue: number; d: IcDeficiency };

export default function IcRecommendationsPage() {
  const { companyId: cid } = useParams<{ companyId: string }>();
  const refs = useIcRefs(cid);
  const [domain, setDomain] = useState("");
  const [state, setState] = useState("");
  const { data, error, loading } = useApiResource<IcDeficiency[]>(`/companies/${cid}/ic/deficiencies${domain ? `?domain_id=${domain}` : ""}`);
  const recs: Rec[] = (data ?? []).flatMap((d) => d.recommendations.map((r) => ({
    id: r.id, reference: r.reference, text: r.text, d, plans: r.action_plans.length,
    done: r.action_plans.filter((a) => a.status === "verified").length, overdue: r.action_plans.filter((a) => a.overdue).length,
  })));
  const rows = recs.filter((r) => !state || (state === "no_plan" ? r.plans === 0 : state === "overdue" ? r.overdue > 0 : state === "verified" ? r.plans > 0 && r.done === r.plans : r.plans > 0 && r.done < r.plans));
  const v = useListView(rows, { text: (r) => `${r.reference} ${r.text} ${r.d.reference} ${r.d.title}`, sort: { ref: (r) => r.reference, def: (r) => r.d.reference } });
  const withPlans = recs.filter((r) => r.plans > 0);
  const verified = withPlans.filter((r) => r.done === r.plans).length;
  return (
    <IcShell cid={cid} title="Recommandations" description="Recommandations rattachées aux déficiences (tables partagées avec l'audit interne). Elles se rédigent et se suivent dans la mission d'origine.">
      {() => (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <SearchBox value={v.q} onChange={v.setQ} />
            <Select aria-label="Domaine" className="w-56" value={domain} onChange={(x) => setDomain(x.target.value)}>
              <option value="">Tous les domaines</option>{refs.domains.map((d) => <option key={d.id} value={d.id}>{d.code} — {d.name}</option>)}
            </Select>
            <Select aria-label="État" className="w-56" value={state} onChange={(x) => setState(x.target.value)}>
              <option value="">Toutes</option><option value="no_plan">Sans plan d&apos;action</option><option value="open">Plans en cours</option>
              <option value="overdue">Avec action en retard</option><option value="verified">Entièrement vérifiées</option>
            </Select>
          </div>
          {error && <Alert>{error}</Alert>}
          {loading && !data && <Loading />}
          {data && (
            <div className="grid gap-3 sm:grid-cols-4">
              <KpiCard label="Recommandations" value={recs.length} />
              <KpiCard label="Sans plan d'action" value={recs.length - withPlans.length} />
              <KpiCard label="Avec action en retard" value={recs.filter((r) => r.overdue > 0).length} />
              <KpiCard label="Entièrement vérifiées" value={pct(withPlans.length ? Math.round((verified / withPlans.length) * 1000) / 10 : null)} hint={`${verified} sur ${withPlans.length} avec plan`} />
            </div>
          )}
          {data && recs.length === 0 && <EmptyState title="Aucune recommandation" description="Aucune recommandation n'est rattachée à une déficience visible." />}
          {rows.length > 0 && (
            <Card><CardContent className="pt-5">
              <Table>
                <THead><tr>{v.sortTh("ref", "Recommandation")}{v.sortTh("def", "Déficience")}<TH>Étape</TH><TH>Plans</TH><TH>Vérifiés</TH><TH>En retard</TH></tr></THead>
                <TBody>{v.rows.map((r) => (
                  <TR key={r.id}>
                    <TD><span className="font-medium">{r.reference}</span> {r.text}</TD>
                    <TD><Link className="text-link hover:underline" href={`/missions/${r.d.engagement_id}?tab=findings`}>{r.d.reference}</Link> {r.d.title}
                      {r.d.rating_label && <Badge tone="amber" className="ml-1">{r.d.rating_label}</Badge>}</TD>
                    <TD><Badge tone={STAGE_TONE[r.d.stage]}>{r.d.stage_label}</Badge></TD>
                    <TD>{r.plans}</TD><TD>{r.done}</TD><TD>{r.overdue ? <Badge tone="red">{r.overdue}</Badge> : "0"}</TD>
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
