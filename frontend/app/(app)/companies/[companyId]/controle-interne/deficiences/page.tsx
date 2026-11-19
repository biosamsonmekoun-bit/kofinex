"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useApiResource } from "@/lib/use-api";
import { STAGE_TONE, type IcDeficiency } from "@/lib/ic-types";
import { ACTION_STATUS } from "@/lib/ia-types";
import { formatDate } from "@/lib/utils";
import { IcShell } from "@/components/ic-shell";
import { useIcRefs } from "@/components/ic-forms";
import { Pager, SearchBox, useListView } from "@/components/ic-list";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Select } from "@/components/ui/form";

const STAGES: [string, string][] = [
  ["draft", "Brouillon"], ["validated", "Validée"], ["communicated", "Communiquée"], ["responded", "Réponse reçue"], ["action_planned", "Plan d'action"],
  ["implementation", "Mise en œuvre"], ["verification", "Vérification"], ["closed", "Clôturée"],
];
type Candidate = { type: "test_result" | "missing_control" | "uncovered_risk"; control_id?: string; risk_id?: string; code: string; title: string; detail: string };

export default function IcDeficienciesPage() {
  const { companyId: cid } = useParams<{ companyId: string }>();
  const refs = useIcRefs(cid);
  const [domain, setDomain] = useState("");
  const [stage, setStage] = useState("");
  const qs = new URLSearchParams();
  if (domain) qs.set("domain_id", domain);
  if (stage) qs.set("stage", stage);
  const { data, error, loading } = useApiResource<IcDeficiency[]>(`/companies/${cid}/ic/deficiencies?${qs.toString()}`);
  const { data: cands } = useApiResource<Candidate[]>(`/companies/${cid}/ic/deficiency-candidates${domain ? `?domain_id=${domain}` : ""}`);
  const [order, setOrder] = useState("");
  const sorted = !data || !order ? data : [...data].sort((a, b) => order === "ref" ? a.reference.localeCompare(b.reference)
    : (a.rating_rank ?? Number.MAX_SAFE_INTEGER) - (b.rating_rank ?? Number.MAX_SAFE_INTEGER));
  const v = useListView(sorted, { text: (d) => `${d.reference} ${d.title} ${d.control ?? ""} ${d.engagement_reference}`, pageSize: 20 });
  const base = `/companies/${cid}/controle-interne`;
  return (
    <IcShell cid={cid} title="Déficiences et constats"
             description="Constats de nature « déficience de contrôle interne » rédigés dans les missions, rattachés au contrôle. Une déficience validée n'est modifiable qu'après un retour en brouillon tracé.">
      {() => (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <SearchBox value={v.q} onChange={v.setQ} />
            <Select aria-label="Domaine" className="w-56" value={domain} onChange={(x) => setDomain(x.target.value)}>
              <option value="">Tous les domaines</option>{refs.domains.map((d) => <option key={d.id} value={d.id}>{d.code} — {d.name}</option>)}
            </Select>
            <Select aria-label="Étape" className="w-48" value={stage} onChange={(x) => setStage(x.target.value)}>
              <option value="">Toutes les étapes</option>{STAGES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </Select>
            <Select aria-label="Tri" className="w-56" value={order} onChange={(x) => setOrder(x.target.value)}>
              <option value="">Par mission</option><option value="ref">Par référence</option><option value="rank">Par rang de l&apos;échelle de la méthodologie</option>
            </Select>
          </div>
          {error && <Alert>{error}</Alert>}
          {loading && !data && <Loading />}
          {data && data.length === 0 && <EmptyState title="Aucune déficience" description="Les déficiences se rédigent dans l'onglet Constats d'une mission d'évaluation du contrôle interne." />}
          {v.rows.map((d) => (
            <Card key={d.id}>
              <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-2">
                <div>
                  <CardTitle>{d.reference} — {d.title}</CardTitle>
                  <CardDescription>
                    Contrôle {d.control_id ? <Link className="text-link hover:underline" href={`${base}/controles/${d.control_id}`}>{d.control}</Link> : "—"} · mission{" "}
                    <Link className="text-link hover:underline" href={`/missions/${d.engagement_id}?tab=findings`}>{d.engagement_reference}</Link>
                    {d.domain_id && ` · ${refs.domains.find((x) => x.id === d.domain_id)?.name ?? ""}`}
                  </CardDescription>
                </div>
                <span className="flex gap-2">{d.rating_label && <Badge tone="amber">{d.rating_label}</Badge>}<Badge tone={STAGE_TONE[d.stage]}>{d.stage_label}</Badge></span>
              </CardHeader>
              <CardContent className="grid gap-3 text-sm sm:grid-cols-2">
                <p><span className="text-xs text-muted-foreground">Critère de référence</span><br />{d.criteria}</p>
                <p><span className="text-xs text-muted-foreground">Situation observée</span><br />{d.condition}</p>
                <p><span className="text-xs text-muted-foreground">Cause</span><br />{d.cause ?? "—"}</p>
                <p><span className="text-xs text-muted-foreground">Conséquence</span><br />{d.effect ?? "—"}</p>
                <p className="sm:col-span-2"><span className="text-xs text-muted-foreground">Réponse de la direction</span><br />{d.management_response ? `${d.management_response}${d.response_by_name ? ` — ${d.response_by_name}` : ""}` : "—"}</p>
                {d.recommendations.map((r) => (
                  <div key={r.id} className="space-y-1 rounded-md border p-2 sm:col-span-2">
                    <p><span className="font-medium">{r.reference}</span> {r.text}</p>
                    {r.action_plans.map((a) => (
                      <p key={a.id} className="text-xs">{a.description} · {a.owner_name} · échéance {formatDate(a.due_date)}{" "}
                        <Badge tone={ACTION_STATUS[a.status as keyof typeof ACTION_STATUS]?.[1]}>{ACTION_STATUS[a.status as keyof typeof ACTION_STATUS]?.[0] ?? a.status}</Badge>{" "}
                        {a.overdue && <Badge tone="red">En retard</Badge>}</p>
                    ))}
                  </div>
                ))}
                {d.closed_at && <p className="text-xs text-muted-foreground sm:col-span-2">Clôturée le {formatDate(d.closed_at)} : {d.closure_note}</p>}
              </CardContent>
            </Card>
          ))}
          {data && data.length > 0 && <Pager {...v} />}
          <Card>
            <CardHeader><CardTitle>Points à examiner</CardTitle>
              <CardDescription>Contrôles conclus inefficaces ou partiellement efficaces, contrôles attendus ou absents, risques non couverts, sans déficience enregistrée. Rien n&apos;est créé automatiquement : la qualification relève de votre jugement.</CardDescription></CardHeader>
            <CardContent className="space-y-1 text-sm">
              {!cands ? <Loading /> : cands.length === 0 ? <p className="text-muted-foreground">Aucun point.</p> : cands.map((c, i) => (
                <p key={i}>
                  <Badge>{c.type === "test_result" ? "Résultat de test" : c.type === "missing_control" ? "Contrôle manquant" : "Risque non couvert"}</Badge>{" "}
                  {c.control_id ? <Link className="text-link hover:underline" href={`${base}/controles/${c.control_id}`}>{c.code} — {c.title}</Link> : <>{c.code} — {c.title}</>}
                  <span className="text-muted-foreground"> · {c.detail}</span>
                </p>
              ))}
            </CardContent>
          </Card>
        </div>
      )}
    </IcShell>
  );
}
