"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { History, Pencil, Plus } from "lucide-react";
import { useApiResource } from "@/lib/use-api";
import { INDICATOR_TONE, type IcRisk } from "@/lib/ic-types";
import { canManage, IcShell } from "@/components/ic-shell";
import { RiskDialog, RiskHistory, useIcRefs } from "@/components/ic-forms";
import { Pager, SearchBox, useListView } from "@/components/ic-list";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

export default function IcRisksPage() {
  const { companyId: cid } = useParams<{ companyId: string }>();
  const refs = useIcRefs(cid);
  const [domain, setDomain] = useState("");
  const [process, setProcess] = useState("");
  const [indicator, setIndicator] = useState("");
  const [status, setStatus] = useState("active");
  const qs = new URLSearchParams();
  if (domain) qs.set("domain_id", domain);
  if (process) qs.set("process_id", process);
  const { data, error, loading, reload } = useApiResource<IcRisk[]>(`/companies/${cid}/ic/risks?${qs.toString()}`);
  const [edit, setEdit] = useState<IcRisk | "new" | null>(null);
  const [hist, setHist] = useState<IcRisk | null>(null);
  const rows = data?.filter((r) => (!indicator || r.indicator === indicator) && (!status || r.status === status));
  const v = useListView(rows, {
    text: (r) => `${r.code} ${r.title} ${r.category ?? ""} ${r.owner_name ?? ""}`,
    sort: { code: (r) => r.code, inherent: (r) => r.inherent_score, residual: (r) => r.residual_score, category: (r) => r.category },
  });
  const name = (id: string | null, list: { id: string; code: string }[]) => list.find((x) => x.id === id)?.code ?? "—";
  return (
    <IcShell cid={cid} title="Registre des risques"
             description="Registre partagé avec l'audit interne. Cotations sur la grille versionnée de la méthodologie choisie ; aucune gravité n'est imposée par la plateforme.">
      {(access) => (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <SearchBox value={v.q} onChange={v.setQ} />
            <Select aria-label="Domaine" className="w-56" value={domain} onChange={(x) => { setDomain(x.target.value); setProcess(""); }}>
              <option value="">Tous les domaines</option>{refs.domains.map((d) => <option key={d.id} value={d.id}>{d.code} — {d.name}</option>)}
            </Select>
            <Select aria-label="Processus" className="w-56" value={process} onChange={(x) => setProcess(x.target.value)}>
              <option value="">Tous les processus</option>{refs.processes.filter((p) => !domain || p.domain_id === domain).map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
            </Select>
            <Select aria-label="Couverture" className="w-48" value={indicator} onChange={(x) => setIndicator(x.target.value)}>
              <option value="">Toute couverture</option><option value="uncovered">Non couvert</option><option value="not_tested">Non testé</option>
              <option value="ineffective">Inefficace</option><option value="partial">Partiel</option><option value="effective">Efficace</option>
            </Select>
            <Select aria-label="Statut" className="w-36" value={status} onChange={(x) => setStatus(x.target.value)}>
              <option value="active">Actifs</option><option value="retired">Retirés</option><option value="">Tous</option>
            </Select>
            {(access.can_manage_registry || access.is_admin || access.managed_domains.length > 0) && (
              <Button size="sm" className="ml-auto" onClick={() => setEdit("new")}><Plus className="h-4 w-4" /> Nouveau risque</Button>
            )}
          </div>
          {error && <Alert>{error}</Alert>}
          {loading && !data && <Loading />}
          {data && data.length === 0 && <EmptyState title="Aucun risque" description="Identifiez les risques par domaine, processus et objectif de contrôle." />}
          {data && data.length > 0 && (
            <Card><CardContent className="pt-5">
              <Table>
                <THead><tr>{v.sortTh("code", "Risque")}{v.sortTh("category", "Catégorie")}<TH>Domaine</TH><TH>Processus</TH>{v.sortTh("inherent", "Inhérent")}
                  <TH>Maîtrise</TH>{v.sortTh("residual", "Résiduel")}<TH>Propriétaire</TH><TH>Couverture</TH><TH /></tr></THead>
                <TBody>{v.rows.map((r) => (
                  <TR key={r.id}>
                    <TD><span className="font-medium">{r.code}</span> {r.title} {r.status === "retired" && <Badge>Retiré</Badge>}
                      {r.causes && <span className="block text-xs text-muted-foreground">Causes : {r.causes}</span>}</TD>
                    <TD>{r.category ?? "—"}</TD><TD>{name(r.domain_id, refs.domains)}</TD><TD>{name(r.process_id, refs.processes)}</TD>
                    <TD>{r.inherent_score ?? "—"}{r.inherent_likelihood && <span className="block text-xs text-muted-foreground">{r.inherent_likelihood} × {r.inherent_impact}</span>}</TD>
                    <TD>{r.control_level_label ?? r.control_level_code ?? "—"}</TD>
                    <TD>{r.residual_score ?? "—"}{r.residual_likelihood && <span className="block text-xs text-muted-foreground">{r.residual_likelihood} × {r.residual_impact}</span>}</TD>
                    <TD>{r.owner_name ?? "—"}</TD>
                    <TD>{r.indicator && <Badge tone={INDICATOR_TONE[r.indicator]}>{r.indicator_label}</Badge>}</TD>
                    <TD className="whitespace-nowrap text-right">
                      <Button size="icon" variant="ghost" aria-label={`Historique ${r.code}`} onClick={() => setHist(r)}><History className="h-4 w-4" /></Button>
                      {(access.can_manage_registry || canManage(access, r.domain_id)) && <Button size="icon" variant="ghost" aria-label={`Modifier ${r.code}`} onClick={() => setEdit(r)}><Pencil className="h-4 w-4" /></Button>}
                    </TD>
                  </TR>
                ))}</TBody>
              </Table>
              <Pager {...v} />
            </CardContent></Card>
          )}
          {edit && <RiskDialog cid={cid} risk={edit === "new" ? null : edit} domains={refs.domains} processes={refs.processes} objectives={refs.objectives}
                               defaultDomain={domain || null} onClose={() => setEdit(null)} onSaved={async () => { setEdit(null); await reload(); }} />}
          {hist && <RiskHistory cid={cid} risk={hist} onClose={() => setHist(null)} />}
        </div>
      )}
    </IcShell>
  );
}
