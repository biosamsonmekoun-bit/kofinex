"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import type { IcReport } from "@/lib/ic-types";
import type { GeneratedDoc } from "@/lib/report-types";
import { openDocument } from "@/components/reports";
import { formatDate } from "@/lib/utils";
import { IcShell } from "@/components/ic-shell";
import { useIcRefs } from "@/components/ic-forms";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, Loading } from "@/components/ui/feedback";
import { Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const KINDS: [string, string][] = [
  ["assessment", "Rapport d'évaluation du contrôle interne"], ["domain", "Rapport par domaine"], ["process", "Rapport par processus"],
  ["cycle", "Rapport par cycle comptable"], ["risk_map", "Cartographie des risques"], ["matrix", "Matrice risques-contrôles"],
  ["ineffective_controls", "État des contrôles inefficaces"], ["deficiencies", "Rapport des déficiences"], ["remediation", "Suivi des plans de remédiation"],
];

export default function IcReportsPage() {
  const { companyId: cid } = useParams<{ companyId: string }>();
  const refs = useIcRefs(cid);
  const [kind, setKind] = useState("assessment");
  const [domain, setDomain] = useState("");
  const [process, setProcess] = useState("");
  const [cycle, setCycle] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const qs = new URLSearchParams();
  if (domain) qs.set("domain_id", domain);
  if (process) qs.set("process_id", process);
  if (cycle.trim()) qs.set("cycle_code", cycle.trim());
  const needs = kind === "domain" ? !domain : kind === "process" ? !process : kind === "cycle" ? !cycle.trim() : false;
  const { data, error, loading } = useApiResource<IcReport>(needs ? null : `/companies/${cid}/ic/reports/${kind}?${qs.toString()}`);
  const [exporting, setExporting] = useState<string | null>(null);
  async function exportDoc(format: "pdf" | "xlsx" | "docx") {
    setExporting(format); setErr(null);
    try {
      const g = await api.post<GeneratedDoc>(`/companies/${cid}/documents`, { document_type: "ic_report", format, ic_kind: kind,
        domain_id: domain || null, process_id: process || null, cycle_code: cycle.trim() || null });
      if (g.status === "ready") await openDocument(g.id); else setErr(`Génération en échec : ${g.failure_reason}`);
    } catch (x) { setErr(errorMessage(x)); } finally { setExporting(null); }
  }
  async function csv(key: string) {
    setErr(null);
    try { await api.download(`/companies/${cid}/ic/reports/${kind}/${key}.csv?${qs.toString()}`, `controle-interne-${kind}-${key}.csv`); } catch (x) { setErr(errorMessage(x)); }
  }
  return (
    <IcShell cid={cid} title="Rapports et synthèses"
             description="Établis à partir des données enregistrées : seules les évaluations approuvées et les tests revus alimentent les conclusions. Chaque section s'exporte en CSV ; le rapport complet s'exporte en PDF, Excel ou Word, figé avec son empreinte.">
      {() => (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <Select aria-label="Rapport" className="w-80" value={kind} onChange={(x) => setKind(x.target.value)}>
              {KINDS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </Select>
            <Select aria-label="Domaine" className="w-56" value={domain} onChange={(x) => { setDomain(x.target.value); setProcess(""); }}>
              <option value="">{kind === "domain" ? "Choisir un domaine…" : "Tous les domaines"}</option>{refs.domains.map((d) => <option key={d.id} value={d.id}>{d.code} — {d.name}</option>)}
            </Select>
            <Select aria-label="Processus" className="w-56" value={process} onChange={(x) => setProcess(x.target.value)}>
              <option value="">{kind === "process" ? "Choisir un processus…" : "Tous les processus"}</option>
              {refs.processes.filter((p) => !domain || p.domain_id === domain).map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
            </Select>
            <Input aria-label="Cycle (code)" className="w-40" placeholder="Cycle (code)" value={cycle} onChange={(x) => setCycle(x.target.value)} />
          </div>
          {needs && <Alert kind="info">Choisissez le {kind === "domain" ? "domaine" : kind === "process" ? "processus" : "cycle"} du rapport.</Alert>}
          {(error || err) && <Alert>{error ?? err}</Alert>}
          {loading && !data && <Loading />}
          {data && (
            <>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                <h2 className="text-lg font-semibold">{data.title}</h2>
                <p className="text-xs text-muted-foreground">Établi le {formatDate(data.generated_at)} · sources : {Object.entries(data.sources).map(([k, n]) => `${k} ${n}`).join(" · ")}</p>
                </div>
                <div className="flex gap-2">
                  {(["pdf", "xlsx", "docx"] as const).map((f) => (
                    <Button key={f} size="sm" variant="outline" loading={exporting === f} onClick={() => exportDoc(f)}>{{ pdf: "PDF", xlsx: "Excel", docx: "Word" }[f]}</Button>
                  ))}
                </div>
              </div>
              {data.sections.map((s) => (
                <Card key={s.key}>
                  <CardHeader className="flex flex-row items-start justify-between gap-2">
                    <div><CardTitle>{s.title}</CardTitle><CardDescription>{s.rows.length} ligne(s)</CardDescription></div>
                    <Button size="sm" variant="outline" disabled={!s.rows.length} onClick={() => csv(s.key)}>CSV</Button>
                  </CardHeader>
                  <CardContent>
                    {s.rows.length === 0 ? <p className="text-sm text-muted-foreground">Aucune donnée enregistrée.</p> : (
                      <Table>
                        <THead><tr>{s.columns.map((c) => <TH key={c.key}>{c.label}</TH>)}</tr></THead>
                        <TBody>{s.rows.map((r, i) => <TR key={i}>{s.columns.map((c) => <TD key={c.key}>{r[c.key] ?? "—"}</TD>)}</TR>)}</TBody>
                      </Table>
                    )}
                  </CardContent>
                </Card>
              ))}
            </>
          )}
        </div>
      )}
    </IcShell>
  );
}
