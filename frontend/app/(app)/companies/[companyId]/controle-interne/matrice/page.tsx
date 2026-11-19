"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { CONCLUSION, EXISTENCE, FREQUENCY, INDICATOR_TONE, type Matrix } from "@/lib/ic-types";
import { IcShell } from "@/components/ic-shell";
import { useIcRefs } from "@/components/ic-forms";
import { Pager, SearchBox, useListView } from "@/components/ic-list";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Select } from "@/components/ui/form";
import { KpiCard } from "@/components/ui/kpi-card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

export default function IcMatrixPage() {
  const { companyId: cid } = useParams<{ companyId: string }>();
  const refs = useIcRefs(cid);
  const [domain, setDomain] = useState("");
  const [process, setProcess] = useState("");
  const [indicator, setIndicator] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const qs = new URLSearchParams();
  if (domain) qs.set("domain_id", domain);
  if (process) qs.set("process_id", process);
  const { data, error, loading } = useApiResource<Matrix>(`/companies/${cid}/ic/matrix?${qs.toString()}`);
  const base = `/companies/${cid}/controle-interne`;
  const v = useListView(data?.rows.filter((r) => !indicator || r.indicator === indicator), {
    text: (r) => `${r.risk_code} ${r.risk_title} ${r.control_code ?? ""} ${r.control_title ?? ""} ${r.owner ?? ""} ${r.process ?? ""}`, pageSize: 50,
  });
  async function exportCsv() {
    setErr(null);
    try { await api.download(`/companies/${cid}/ic/reports/matrix/matrix.csv?${qs.toString()}`, "matrice-risques-controles.csv"); } catch (x) { setErr(errorMessage(x)); }
  }
  const covered = data ? new Set(data.rows.filter((r) => r.indicator !== "uncovered").map((r) => r.risk_id)).size : 0;
  return (
    <IcShell cid={cid} title="Matrice risques-contrôles"
             description="Une ligne par association risque-contrôle. Un risque n'est couvert que par un contrôle existant ou non formalisé et actif ; les contrôles attendus ou absents apparaissent comme manquants.">
      {() => (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <SearchBox value={v.q} onChange={v.setQ} />
            <Select aria-label="Domaine" className="w-56" value={domain} onChange={(x) => { setDomain(x.target.value); setProcess(""); }}>
              <option value="">Tous les domaines</option>{refs.domains.map((d) => <option key={d.id} value={d.id}>{d.code} — {d.name}</option>)}
            </Select>
            <Select aria-label="Processus" className="w-56" value={process} onChange={(x) => setProcess(x.target.value)}>
              <option value="">Tous les processus</option>{refs.processes.filter((p) => !domain || p.domain_id === domain).map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
            </Select>
            <Select aria-label="Indicateur" className="w-48" value={indicator} onChange={(x) => setIndicator(x.target.value)}>
              <option value="">Tous les indicateurs</option><option value="uncovered">Non couvert</option><option value="not_tested">Non testé</option>
              <option value="ineffective">Inefficace</option><option value="partial">Partiel</option><option value="effective">Efficace</option>
            </Select>
            <Button size="sm" variant="outline" className="ml-auto" disabled={!data?.rows.length} onClick={exportCsv}>Exporter en CSV</Button>
          </div>
          {(error || err) && <Alert>{error ?? err}</Alert>}
          {loading && !data && <Loading />}
          {data && (
            <>
              <div className="grid gap-3 sm:grid-cols-3">
                <KpiCard label="Risques couverts" value={covered} />
                <KpiCard label="Risques non couverts" value={data.uncovered_risks.length} />
                <KpiCard label="Contrôles sans risque associé" value={data.orphan_controls.length} />
              </div>
              {data.rows.length === 0 ? <EmptyState title="Matrice vide" description="Ajoutez des risques et associez-leur des contrôles depuis la fiche de chaque contrôle." /> : (
                <Card><CardContent className="pt-5">
                  <Table>
                    <THead><tr><TH>Processus / objectif</TH><TH>Risque</TH><TH>Contrôle</TH><TH>Statut</TH><TH>Responsable</TH><TH>Fréquence</TH>
                      <TH>Preuves</TH><TH>Conception</TH><TH>Efficacité</TH><TH>Indicateur</TH></tr></THead>
                    <TBody>{v.rows.map((r, i) => (
                      <TR key={`${r.risk_id}-${r.control_id ?? i}`}>
                        <TD className="text-xs">{r.process ?? "—"}{r.objective && <span className="block text-muted-foreground">{r.objective}</span>}</TD>
                        <TD><span className="font-medium">{r.risk_code}</span> {r.risk_title}</TD>
                        <TD>{r.control_id ? <Link className="text-link hover:underline" href={`${base}/controles/${r.control_id}`}>{r.control_code} — {r.control_title}</Link> : <span className="text-muted-foreground">Aucun contrôle</span>}
                          {r.is_key && <Badge tone="gold" className="ml-1">Clé</Badge>}{r.coverage === "partial" && <span className="block text-xs text-muted-foreground">Couverture partielle</span>}</TD>
                        <TD>{r.existence ? <Badge tone={EXISTENCE[r.existence][1]}>{EXISTENCE[r.existence][0]}</Badge> : "—"}{r.missing && <span className="block text-xs text-destructive">Manquant</span>}</TD>
                        <TD>{r.owner ?? "—"}</TD>
                        <TD>{r.frequency ? FREQUENCY[r.frequency] : "—"}</TD>
                        <TD>{r.control_id ? (r.evidence_count ?? 0) : "—"}{r.expected_evidence && <span className="block text-xs text-muted-foreground">Attendu : {r.expected_evidence}</span>}</TD>
                        <TD>{r.design ? CONCLUSION[r.design][0] : "—"}</TD>
                        <TD>{r.operating ? CONCLUSION[r.operating][0] : "—"}</TD>
                        <TD><Badge tone={INDICATOR_TONE[r.indicator]}>{r.indicator_label}</Badge></TD>
                      </TR>
                    ))}</TBody>
                  </Table>
                  <Pager {...v} />
                </CardContent></Card>
              )}
              <div className="grid gap-4 lg:grid-cols-2">
                <Card><CardHeader><CardTitle>Risques non couverts</CardTitle><CardDescription>Aucun contrôle existant actif ; les contrôles attendus déclarés sont rappelés.</CardDescription></CardHeader>
                  <CardContent className="space-y-1 text-sm">
                    {data.uncovered_risks.length === 0 ? <p className="text-muted-foreground">Aucun.</p> : data.uncovered_risks.map((r) => (
                      <p key={r.risk_id}><span className="font-medium">{r.code}</span> {r.title}{r.expected_controls.length > 0 && <span className="text-xs text-muted-foreground"> · attendu(s) : {r.expected_controls.join(", ")}</span>}</p>
                    ))}
                  </CardContent></Card>
                <Card><CardHeader><CardTitle>Contrôles sans risque associé</CardTitle></CardHeader>
                  <CardContent className="space-y-1 text-sm">
                    {data.orphan_controls.length === 0 ? <p className="text-muted-foreground">Aucun.</p> : data.orphan_controls.map((c) => (
                      <p key={c.control_id}><Link className="text-link hover:underline" href={`${base}/controles/${c.control_id}`}>{c.code} — {c.title}</Link></p>
                    ))}
                  </CardContent></Card>
              </div>
            </>
          )}
        </div>
      )}
    </IcShell>
  );
}
