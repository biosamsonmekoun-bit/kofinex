"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Pencil, Plus } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import {
  CONCLUSION, EXISTENCE, INDICATOR_TONE, STAGE_TONE, TEST_STATUS, pct, type IcControl, type IcDashboard, type IcDeficiency, type IcDomain,
  type IcObjective, type IcProcess, type IcRisk, type IcTestBrief,
} from "@/lib/ic-types";
import { formatDate } from "@/lib/utils";
import { AREA, IcShell } from "@/components/ic-shell";
import { ControlDialog, ProcessDialog, RiskDialog, useIcRefs } from "@/components/ic-forms";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, Loading } from "@/components/ui/feedback";
import { Field, Input } from "@/components/ui/form";
import { KpiCard } from "@/components/ui/kpi-card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

type Overview = {
  domain: IcDomain; can_manage: boolean; processes: IcProcess[]; objectives: IcObjective[]; risks: IcRisk[]; controls: IcControl[];
  tests: IcTestBrief[]; deficiencies: IcDeficiency[]; uncovered_risks: { risk_id: string; code: string; title: string }[]; dashboard: IcDashboard;
};

function ObjectiveDialog({ cid, domainId, processes, onClose, onSaved }: { cid: string; domainId: string; processes: IcProcess[]; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState({ code: "", statement: "", process_id: "" });
  const [err, setErr] = useState<string | null>(null);
  async function save(ev: React.FormEvent) {
    ev.preventDefault(); setErr(null);
    try { await api.post(`/companies/${cid}/ic/objectives`, { ...f, process_id: f.process_id || null, domain_id: domainId }); onSaved(); }
    catch (x) { setErr(errorMessage(x)); }
  }
  return (
    <Dialog open onClose={onClose} title="Nouvel objectif de contrôle">
      <form onSubmit={save} className="space-y-3">
        {err && <Alert>{err}</Alert>}
        <Field label="Code" htmlFor="o-c" required><Input id="o-c" required value={f.code} onChange={(x) => setF({ ...f, code: x.target.value })} /></Field>
        <Field label="Énoncé" htmlFor="o-s" required><textarea id="o-s" required rows={2} className={AREA} value={f.statement} onChange={(x) => setF({ ...f, statement: x.target.value })} /></Field>
        <Field label="Processus" htmlFor="o-p"><select id="o-p" className={AREA} value={f.process_id} onChange={(x) => setF({ ...f, process_id: x.target.value })}>
          <option value="">—</option>{processes.map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}</select></Field>
        <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={onClose}>Annuler</Button><Button type="submit">Enregistrer</Button></div>
      </form>
    </Dialog>
  );
}

export default function DomainOverviewPage() {
  const { companyId: cid, domainId } = useParams<{ companyId: string; domainId: string }>();
  const refs = useIcRefs(cid);
  const { data, error, loading, reload } = useApiResource<Overview>(`/companies/${cid}/ic/domains/${domainId}/overview`);
  const [dlg, setDlg] = useState<"process" | "risk" | "control" | "objective" | null>(null);
  const [editProc, setEditProc] = useState<IcProcess | null>(null);
  const [editRisk, setEditRisk] = useState<IcRisk | null>(null);
  const base = `/companies/${cid}/controle-interne`;
  const done = async () => { setDlg(null); setEditProc(null); setEditRisk(null); await reload(); await refs.reload(); };
  const procName = (id: string | null) => data?.processes.find((p) => p.id === id)?.code ?? "—";
  return (
    <IcShell cid={cid} title={data ? `${data.domain.code} — ${data.domain.name}` : "Domaine"}
             description="Processus, risques, contrôles, tests, déficiences et recommandations du domaine.">
      {() => (
        <>
          {error && <Alert>{error}</Alert>}
          {loading && !data && <Loading />}
          {data && (
            <div className="space-y-5">
              {data.can_manage && (
                <div className="flex flex-wrap justify-end gap-2">
                  <Button size="sm" variant="outline" onClick={() => setDlg("process")}><Plus className="h-4 w-4" /> Processus</Button>
                  <Button size="sm" variant="outline" onClick={() => setDlg("objective")}><Plus className="h-4 w-4" /> Objectif</Button>
                  <Button size="sm" variant="outline" onClick={() => setDlg("risk")}><Plus className="h-4 w-4" /> Risque</Button>
                  <Button size="sm" onClick={() => setDlg("control")}><Plus className="h-4 w-4" /> Contrôle</Button>
                </div>
              )}
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                <KpiCard label="Processus" value={data.processes.length} />
                <KpiCard label="Risques" value={data.dashboard.risks} hint={`${data.dashboard.uncovered_risks} non couvert(s)`} />
                <KpiCard label="Contrôles existants" value={data.dashboard.controls_existing} hint={`${data.dashboard.controls_tested} testé(s)`} />
                <KpiCard label="Taux d'efficacité" value={pct(data.dashboard.effective_rate)} />
                <KpiCard label="Déficiences ouvertes" value={data.dashboard.deficiencies_open} hint={`${data.dashboard.action_plans_overdue} action(s) en retard`} />
              </div>
              <Card><CardHeader><CardTitle>Processus et sous-processus</CardTitle></CardHeader><CardContent>
                <Table><THead><tr><TH>Code</TH><TH>Intitulé</TH><TH>Parent</TH><TH>Responsable</TH><TH /></tr></THead>
                  <TBody>{data.processes.map((p) => <TR key={p.id}><TD>{p.code}</TD><TD>{p.name} {!p.is_active && <Badge>Inactif</Badge>}</TD><TD>{p.parent_id ? procName(p.parent_id) : "—"}</TD><TD>{p.owner_name ?? "—"}</TD>
                    <TD className="text-right">{data.can_manage && <Button size="icon" variant="ghost" aria-label={`Modifier ${p.code}`} onClick={() => setEditProc(p)}><Pencil className="h-4 w-4" /></Button>}</TD></TR>)}</TBody></Table>
                {data.objectives.length > 0 && <div className="mt-3 space-y-1 text-sm"><p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Objectifs de contrôle</p>
                  {data.objectives.map((o) => <p key={o.id}><span className="font-medium">{o.code}</span> {o.statement}</p>)}</div>}
              </CardContent></Card>
              <Card><CardHeader><CardTitle>Risques</CardTitle></CardHeader><CardContent>
                <Table><THead><tr><TH>Risque</TH><TH>Processus</TH><TH>Inhérent</TH><TH>Maîtrise</TH><TH>Résiduel</TH><TH>Couverture</TH><TH /></tr></THead>
                  <TBody>{data.risks.map((r) => <TR key={r.id}><TD>{r.code} — {r.title}</TD><TD>{procName(r.process_id)}</TD><TD>{r.inherent_score ?? "—"}</TD><TD>{r.control_level_label ?? "—"}</TD><TD>{r.residual_score ?? "—"}</TD>
                    <TD>{r.indicator && <Badge tone={INDICATOR_TONE[r.indicator]}>{r.indicator_label}</Badge>}</TD>
                    <TD className="text-right">{data.can_manage && <Button size="icon" variant="ghost" aria-label={`Modifier ${r.code}`} onClick={() => setEditRisk(r)}><Pencil className="h-4 w-4" /></Button>}</TD></TR>)}</TBody></Table>
              </CardContent></Card>
              <Card><CardHeader><CardTitle>Contrôles</CardTitle></CardHeader><CardContent>
                <Table><THead><tr><TH>Contrôle</TH><TH>Processus</TH><TH>Statut</TH><TH>Responsable</TH><TH>Risques</TH><TH>Conclusion</TH></tr></THead>
                  <TBody>{data.controls.map((c) => <TR key={c.id}><TD><Link className="text-link hover:underline" href={`${base}/controles/${c.id}`}>{c.code} — {c.title}</Link> {c.is_key && <Badge tone="gold">Clé</Badge>}</TD>
                    <TD>{procName(c.process_id)}</TD><TD><Badge tone={EXISTENCE[c.existence][1]}>{EXISTENCE[c.existence][0]}</Badge></TD><TD>{c.owner_name}</TD><TD>{c.risks}</TD>
                    <TD><Badge tone={CONCLUSION[c.conclusion][1]}>{CONCLUSION[c.conclusion][0]}</Badge></TD></TR>)}</TBody></Table>
              </CardContent></Card>
              <Card><CardHeader><CardTitle>Tests</CardTitle></CardHeader><CardContent>
                {data.tests.length === 0 ? <p className="text-sm text-muted-foreground">Aucun test visible.</p> : (
                  <Table><THead><tr><TH>Réf.</TH><TH>Type</TH><TH>Période</TH><TH>Statut</TH><TH>Conclusion</TH></tr></THead>
                    <TBody>{data.tests.map((t) => <TR key={t.id}><TD><Link className="text-link hover:underline" href={`/missions/${t.engagement_id}?tab=ic&test=${t.id}`}>{t.reference}</Link></TD>
                      <TD>{t.test_type === "design" ? "Conception" : "Efficacité"}</TD><TD>{t.period_start ? `${formatDate(t.period_start)} – ${formatDate(t.period_end)}` : "—"}</TD>
                      <TD><Badge tone={TEST_STATUS[t.status][1]}>{TEST_STATUS[t.status][0]}</Badge></TD><TD>{t.conclusion ? <Badge tone={CONCLUSION[t.conclusion][1]}>{CONCLUSION[t.conclusion][0]}</Badge> : "—"}</TD></TR>)}</TBody></Table>
                )}
              </CardContent></Card>
              <Card><CardHeader><CardTitle>Déficiences et recommandations</CardTitle></CardHeader><CardContent className="space-y-2">
                {data.deficiencies.length === 0 && <p className="text-sm text-muted-foreground">Aucune déficience visible.</p>}
                {data.deficiencies.map((d) => (
                  <div key={d.id} className="rounded-md border p-3 text-sm">
                    <p className="font-medium">{d.reference} — {d.title} {d.rating_label && <Badge tone="amber">{d.rating_label}</Badge>} <Badge tone={STAGE_TONE[d.stage]}>{d.stage_label}</Badge></p>
                    <p className="text-muted-foreground">{d.control} · mission {d.engagement_reference}</p>
                    {d.recommendations.map((r) => <p key={r.id} className="mt-1">→ {r.reference} {r.text} <span className="text-xs text-muted-foreground">({r.action_plans.length} plan(s) d&apos;action)</span></p>)}
                  </div>
                ))}
              </CardContent></Card>
              {(dlg === "process" || editProc) && <ProcessDialog cid={cid} proc={editProc} domains={refs.domains} processes={refs.processes} defaultDomain={domainId} onClose={() => { setDlg(null); setEditProc(null); }} onSaved={done} />}
              {(dlg === "risk" || editRisk) && <RiskDialog cid={cid} risk={editRisk} domains={refs.domains} processes={refs.processes} objectives={refs.objectives} defaultDomain={domainId} onClose={() => { setDlg(null); setEditRisk(null); }} onSaved={done} />}
              {dlg === "control" && <ControlDialog cid={cid} control={null} domains={refs.domains} processes={refs.processes} objectives={refs.objectives} defaultDomain={domainId} onClose={() => setDlg(null)} onSaved={done} />}
              {dlg === "objective" && <ObjectiveDialog cid={cid} domainId={domainId} processes={data.processes} onClose={() => setDlg(null)} onSaved={done} />}
            </div>
          )}
        </>
      )}
    </IcShell>
  );
}
