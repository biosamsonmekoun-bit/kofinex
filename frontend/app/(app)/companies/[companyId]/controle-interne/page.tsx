"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useApiResource } from "@/lib/use-api";
import { CONCLUSION, pct, type IcDashboard } from "@/lib/ic-types";
import { IcShell } from "@/components/ic-shell";
import { useIcRefs } from "@/components/ic-forms";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Select } from "@/components/ui/form";
import { KpiCard } from "@/components/ui/kpi-card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

export default function IcDashboardPage() {
  const { companyId: cid } = useParams<{ companyId: string }>();
  const refs = useIcRefs(cid);
  const [domain, setDomain] = useState("");
  const [process, setProcess] = useState("");
  const qs = new URLSearchParams();
  if (domain) qs.set("domain_id", domain);
  if (process) qs.set("process_id", process);
  const { data, error, loading } = useApiResource<IcDashboard>(`/companies/${cid}/ic/dashboard?${qs.toString()}`);
  const base = `/companies/${cid}/controle-interne`;
  return (
    <IcShell cid={cid} title="Tableau de bord du contrôle interne"
             description="Indicateurs calculés sur les données enregistrées : un contrôle n'est « efficace » qu'avec un test d'efficacité revu et concluant.">
      {() => (
        <div className="space-y-5">
          <div className="flex flex-wrap gap-3">
            <Select aria-label="Domaine" className="w-64" value={domain} onChange={(x) => { setDomain(x.target.value); setProcess(""); }}>
              <option value="">Tous les domaines</option>{refs.domains.map((d) => <option key={d.id} value={d.id}>{d.code} — {d.name}</option>)}
            </Select>
            <Select aria-label="Processus" className="w-64" value={process} onChange={(x) => setProcess(x.target.value)}>
              <option value="">Tous les processus</option>
              {refs.processes.filter((p) => !domain || p.domain_id === domain).map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
            </Select>
          </div>
          {error && <Alert>{error}</Alert>}
          {loading && !data && <Loading />}
          {data && (
            <>
              {data.domains === 0 && (
                <EmptyState title="Aucun domaine" description="Commencez par créer les domaines et cycles de l'entité, à partir des modèles ou librement."
                            action={<Link className="text-sm text-link underline" href={`${base}/domaines`}>Ouvrir les domaines</Link>} />
              )}
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <KpiCard label="Domaines évalués" value={`${data.domains_assessed} / ${data.domains}`} hint="évaluation approuvée" />
                <KpiCard label="Processus recensés" value={data.processes} />
                <KpiCard label="Risques identifiés" value={data.risks} hint={`${data.uncovered_risks} non couvert(s)`} />
                <KpiCard label="Contrôles existants" value={data.controls_existing} hint={`${data.controls_missing} attendu(s) ou absent(s)`} />
                <KpiCard label="Contrôles testés" value={data.controls_tested} hint={`${data.not_tested} non testé(s)`} />
                <KpiCard label="Taux de contrôles efficaces" value={pct(data.effective_rate)} hint="sur les contrôles conclus (efficace, partiel, inefficace)" />
                <KpiCard label="Partiellement efficaces" value={data.partially_effective} />
                <KpiCard label="Inefficaces" value={data.ineffective} />
                <KpiCard label="Risques non couverts" value={data.uncovered_risks} onClick={() => location.assign(`${base}/matrice`)} />
                <KpiCard label={data.deficiency_levels.length ? `Déficiences ouvertes — ${data.deficiency_levels[0]?.label ?? ""}` : "Déficiences ouvertes"}
                         value={data.deficiencies_top_level ?? data.deficiencies_open}
                         hint={data.deficiency_levels.length ? `${data.deficiencies_open} au total` : "échelle de la méthodologie non trouvée"} />
                <KpiCard label="Plans d'action en retard" value={data.action_plans_overdue} hint={`${data.action_plans} plan(s)`} onClick={() => location.assign(`${base}/suivi`)} />
                <KpiCard label="Mise en œuvre des recommandations" value={pct(data.implementation_rate)} hint={`vérifiée : ${pct(data.verified_rate)}`} />
              </div>
              {data.deficiency_levels.length > 0 && (
                <p className="text-sm text-muted-foreground">Déficiences ouvertes par niveau de l&apos;échelle de la méthodologie : {data.deficiency_levels.map((l) => `${l.label} ${l.open}`).join(" · ")}</p>
              )}
              <Card>
                <CardHeader><CardTitle>Par domaine</CardTitle><CardDescription>Conclusions des derniers tests revus, contrôles existants ou non formalisés.</CardDescription></CardHeader>
                <CardContent>
                  {data.by_domain.length === 0 ? <p className="text-sm text-muted-foreground">Aucun domaine.</p> : (
                    <Table>
                      <THead><tr><TH>Domaine</TH><TH>Processus</TH><TH>Risques</TH><TH>Contrôles</TH>
                        {(["effective", "partially_effective", "ineffective", "not_tested"] as const).map((k) => <TH key={k}>{CONCLUSION[k][0]}</TH>)}</tr></THead>
                      <TBody>{data.by_domain.map((d) => (
                        <TR key={d.id}>
                          <TD><Link className="text-link hover:underline" href={`${base}/domaines/${d.id}`}>{d.code} — {d.name}</Link> {!d.is_active && <Badge>Inactif</Badge>}</TD>
                          <TD>{d.processes}</TD><TD>{d.risks}</TD><TD>{d.controls}</TD>
                          {(["effective", "partially_effective", "ineffective", "not_tested"] as const).map((k) => <TD key={k}>{d[k] ? <Badge tone={CONCLUSION[k][1]}>{d[k]}</Badge> : "0"}</TD>)}
                        </TR>
                      ))}</TBody>
                    </Table>
                  )}
                </CardContent>
              </Card>
            </>
          )}
        </div>
      )}
    </IcShell>
  );
}
