"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Plus } from "lucide-react";
import { useApiResource } from "@/lib/use-api";
import { AUTOMATION, CONCLUSION, EXISTENCE, FREQUENCY, NATURE, type IcControl } from "@/lib/ic-types";
import { IcShell } from "@/components/ic-shell";
import { ControlDialog, useIcRefs } from "@/components/ic-forms";
import { Pager, SearchBox, useListView } from "@/components/ic-list";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

export default function IcControlsPage() {
  const { companyId: cid } = useParams<{ companyId: string }>();
  const router = useRouter();
  const refs = useIcRefs(cid);
  const [domain, setDomain] = useState("");
  const [process, setProcess] = useState("");
  const [existence, setExistence] = useState("");
  const [conclusion, setConclusion] = useState("");
  const qs = new URLSearchParams();
  if (domain) qs.set("domain_id", domain);
  if (process) qs.set("process_id", process);
  if (existence) qs.set("existence", existence);
  if (conclusion) qs.set("conclusion", conclusion);
  const { data, error, loading } = useApiResource<IcControl[]>(`/companies/${cid}/ic/controls?${qs.toString()}`);
  const [creating, setCreating] = useState(false);
  const base = `/companies/${cid}/controle-interne`;
  const v = useListView(data, {
    text: (c) => `${c.code} ${c.title} ${c.owner_name} ${c.performer_name ?? ""}`,
    sort: { code: (c) => c.code, owner: (c) => c.owner_name, risks: (c) => c.risks, conclusion: (c) => c.conclusion },
  });
  const pname = (id: string | null) => refs.processes.find((p) => p.id === id)?.code ?? "—";
  return (
    <IcShell cid={cid} title="Catalogue des contrôles"
             description="Contrôles existants, attendus, non formalisés ou absents. Conclusion issue des derniers tests revus : un contrôle déclaré existant reste « non testé » tant qu'aucun test ne l'a établi.">
      {(access) => (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <SearchBox value={v.q} onChange={v.setQ} />
            <Select aria-label="Domaine" className="w-52" value={domain} onChange={(x) => { setDomain(x.target.value); setProcess(""); }}>
              <option value="">Tous les domaines</option>{refs.domains.map((d) => <option key={d.id} value={d.id}>{d.code} — {d.name}</option>)}
            </Select>
            <Select aria-label="Processus" className="w-52" value={process} onChange={(x) => setProcess(x.target.value)}>
              <option value="">Tous les processus</option>{refs.processes.filter((p) => !domain || p.domain_id === domain).map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
            </Select>
            <Select aria-label="Statut" className="w-44" value={existence} onChange={(x) => setExistence(x.target.value)}>
              <option value="">Tous statuts</option>{Object.entries(EXISTENCE).map(([k, [l]]) => <option key={k} value={k}>{l}</option>)}
            </Select>
            <Select aria-label="Conclusion" className="w-48" value={conclusion} onChange={(x) => setConclusion(x.target.value)}>
              <option value="">Toutes conclusions</option>{Object.entries(CONCLUSION).map(([k, [l]]) => <option key={k} value={k}>{l}</option>)}
            </Select>
            {(access.is_admin || access.managed_domains.length > 0) && <Button size="sm" className="ml-auto" onClick={() => setCreating(true)}><Plus className="h-4 w-4" /> Nouveau contrôle</Button>}
          </div>
          {error && <Alert>{error}</Alert>}
          {loading && !data && <Loading />}
          {data && data.length === 0 && <EmptyState title="Aucun contrôle" description="Aucun contrôle ne correspond à ces filtres." />}
          {data && data.length > 0 && (
            <Card><CardContent className="pt-5">
              <Table>
                <THead><tr>{v.sortTh("code", "Contrôle")}<TH>Processus</TH><TH>Statut</TH>{v.sortTh("owner", "Responsable")}<TH>Caractéristiques</TH>
                  {v.sortTh("risks", "Risques")}<TH>Conception</TH><TH>Efficacité</TH>{v.sortTh("conclusion", "Conclusion")}</tr></THead>
                <TBody>{v.rows.map((c) => (
                  <TR key={c.id}>
                    <TD><Link className="text-link hover:underline" href={`${base}/controles/${c.id}`}>{c.code} — {c.title}</Link> {c.is_key && <Badge tone="gold">Clé</Badge>}
                      {c.operational_status !== "active" && <Badge>{c.operational_status === "suspended" ? "Suspendu" : "Retiré"}</Badge>}</TD>
                    <TD>{pname(c.process_id)}</TD>
                    <TD><Badge tone={EXISTENCE[c.existence][1]}>{EXISTENCE[c.existence][0]}</Badge></TD>
                    <TD>{c.owner_name}</TD>
                    <TD className="text-xs text-muted-foreground">{[c.frequency && FREQUENCY[c.frequency], c.nature && NATURE[c.nature], c.automation && AUTOMATION[c.automation]].filter(Boolean).join(" · ") || "—"}</TD>
                    <TD>{c.risks}</TD>
                    <TD>{c.design ? CONCLUSION[c.design][0] : "—"}</TD>
                    <TD>{c.operating ? CONCLUSION[c.operating][0] : "—"}</TD>
                    <TD><Badge tone={CONCLUSION[c.conclusion][1]}>{CONCLUSION[c.conclusion][0]}</Badge></TD>
                  </TR>
                ))}</TBody>
              </Table>
              <Pager {...v} />
            </CardContent></Card>
          )}
          {creating && <ControlDialog cid={cid} control={null} domains={refs.domains} processes={refs.processes} objectives={refs.objectives} defaultDomain={domain || null}
                                      onClose={() => setCreating(false)} onSaved={(c) => router.push(`${base}/controles/${c.id}`)} />}
        </div>
      )}
    </IcShell>
  );
}
