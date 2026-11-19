"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ChevronLeft, History, Pencil, Plus } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { personName, type Methodology, type PersonRef } from "@/lib/types";
import { ITEM_STATUS, type RegistryRisk, type RiskMap } from "@/lib/ia-types";
import { cn, formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading, PageHeader } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

type Proc = RiskMap["processes"][number];
type Scale = { likelihood: { score: number; label: string }[]; impact: { score: number; label: string }[] };

function ProcessDialog({ cid, proc, all, onClose, onSaved }: { cid: string; proc: Proc | null; all: Proc[]; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState({ code: proc?.code ?? "", name: proc?.name ?? "", parent_id: proc?.parent_id ?? "", owner_name: proc?.owner_name ?? "",
                               is_active: proc?.is_active ?? true });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function save(ev: React.FormEvent) {
    ev.preventDefault();
    setBusy(true); setErr(null);
    try {
      const body = { name: f.name, parent_id: f.parent_id || null, owner_name: f.owner_name || null, is_active: f.is_active };
      if (proc) await api.patch(`/companies/${cid}/processes/${proc.id}`, body);
      else await api.post(`/companies/${cid}/processes`, { ...body, code: f.code });
      onSaved();
    } catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }
  return (
    <Dialog open onClose={onClose} title={proc ? `Processus ${proc.code}` : "Nouveau processus"}>
      <form onSubmit={save} className="space-y-3">
        {err && <Alert>{err}</Alert>}
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Code" htmlFor="pr-c" required><Input id="pr-c" required disabled={!!proc} value={f.code} onChange={(x) => setF({ ...f, code: x.target.value })} /></Field>
          <div className="sm:col-span-2"><Field label="Nom" htmlFor="pr-n" required><Input id="pr-n" required value={f.name} onChange={(x) => setF({ ...f, name: x.target.value })} /></Field></div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Processus parent" htmlFor="pr-p">
            <Select id="pr-p" value={f.parent_id} onChange={(x) => setF({ ...f, parent_id: x.target.value })}>
              <option value="">—</option>{all.filter((p) => p.id !== proc?.id).map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
            </Select>
          </Field>
          <Field label="Propriétaire du processus" htmlFor="pr-o"><Input id="pr-o" value={f.owner_name} onChange={(x) => setF({ ...f, owner_name: x.target.value })} /></Field>
        </div>
        {proc && <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="h-4 w-4" checked={f.is_active} onChange={(x) => setF({ ...f, is_active: x.target.checked })} /> Processus actif</label>}
        <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={onClose}>Annuler</Button><Button type="submit" loading={busy}>Enregistrer</Button></div>
      </form>
    </Dialog>
  );
}

function RiskDialog({ cid, risk, procs, methods, onClose, onSaved }: { cid: string; risk: RegistryRisk | null; procs: Proc[]; methods: Methodology[]; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState({ code: risk?.code ?? "", title: risk?.title ?? "", description: risk?.description ?? "", process_id: risk?.process_id ?? "",
    scale_version_id: risk?.scale_version_id ?? "", il: String(risk?.inherent_likelihood ?? ""), ii: String(risk?.inherent_impact ?? ""),
    rl: String(risk?.residual_likelihood ?? ""), ri: String(risk?.residual_impact ?? ""), status: risk?.status ?? "active" });
  const { data: scaleItems } = useApiResource<{ items: { item_type: string; content: Scale }[] }>(f.scale_version_id ? `/methodologies/${f.scale_version_id}` : null);
  const scale = scaleItems?.items?.find?.((i) => i.item_type === "risk_scale")?.content;
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const n = (v: string) => (v ? Number(v) : null);
  async function save(ev: React.FormEvent) {
    ev.preventDefault();
    setBusy(true); setErr(null);
    const body = { code: f.code, title: f.title, description: f.description || null, process_id: f.process_id || null,
      scale_version_id: f.scale_version_id || null, inherent_likelihood: n(f.il), inherent_impact: n(f.ii), residual_likelihood: n(f.rl),
      residual_impact: n(f.ri), status: f.status };
    try {
      if (risk) await api.patch(`/companies/${cid}/risks/${risk.id}`, body); else await api.post(`/companies/${cid}/risks`, body);
      onSaved();
    } catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }
  const lvl = (axis: "likelihood" | "impact", id: string, v: string, set: (s: string) => void) => (
    <Select id={id} value={v} onChange={(x) => set(x.target.value)} disabled={!scale}>
      <option value="">—</option>{scale?.[axis].map((l) => <option key={l.score} value={l.score}>{l.score} — {l.label}</option>)}
    </Select>
  );
  return (
    <Dialog open onClose={onClose} title={risk ? `Risque ${risk.code}` : "Nouveau risque"} description="Chaque modification de cotation est historisée.">
      <form onSubmit={save} className="space-y-3">
        {err && <Alert>{err}</Alert>}
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Code" htmlFor="rk-c" required><Input id="rk-c" required value={f.code} onChange={(x) => setF({ ...f, code: x.target.value })} /></Field>
          <div className="sm:col-span-2"><Field label="Risque" htmlFor="rk-t" required><Input id="rk-t" required value={f.title} onChange={(x) => setF({ ...f, title: x.target.value })} /></Field></div>
        </div>
        <Field label="Description" htmlFor="rk-d"><Input id="rk-d" value={f.description} onChange={(x) => setF({ ...f, description: x.target.value })} /></Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Processus" htmlFor="rk-p">
            <Select id="rk-p" value={f.process_id} onChange={(x) => setF({ ...f, process_id: x.target.value })}>
              <option value="">—</option>{procs.map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
            </Select>
          </Field>
          <Field label="Grille de cotation (méthodologie publiée)" htmlFor="rk-s">
            <Select id="rk-s" value={f.scale_version_id} onChange={(x) => setF({ ...f, scale_version_id: x.target.value })}>
              <option value="">—</option>{methods.filter((m) => m.status === "published").map((m) => <option key={m.id} value={m.id}>{m.name} {m.version_label}</option>)}
            </Select>
          </Field>
        </div>
        <div className="grid gap-3 sm:grid-cols-4">
          <Field label="Probabilité brute" htmlFor="rk-il">{lvl("likelihood", "rk-il", f.il, (v) => setF({ ...f, il: v }))}</Field>
          <Field label="Impact brut" htmlFor="rk-ii">{lvl("impact", "rk-ii", f.ii, (v) => setF({ ...f, ii: v }))}</Field>
          <Field label="Probabilité résiduelle" htmlFor="rk-rl">{lvl("likelihood", "rk-rl", f.rl, (v) => setF({ ...f, rl: v }))}</Field>
          <Field label="Impact résiduel" htmlFor="rk-ri">{lvl("impact", "rk-ri", f.ri, (v) => setF({ ...f, ri: v }))}</Field>
        </div>
        {risk && <Field label="Statut" htmlFor="rk-st"><Select id="rk-st" value={f.status} onChange={(x) => setF({ ...f, status: x.target.value as "active" })}><option value="active">Actif</option><option value="retired">Retiré</option></Select></Field>}
        <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={onClose}>Annuler</Button><Button type="submit" loading={busy}>Enregistrer</Button></div>
      </form>
    </Dialog>
  );
}

function RiskHistory({ cid, risk, onClose }: { cid: string; risk: RegistryRisk; onClose: () => void }) {
  const { data } = useApiResource<{ inherent_likelihood: number | null; inherent_impact: number | null; residual_likelihood: number | null;
    residual_impact: number | null; changed_at: string; changed_by: PersonRef | null }[]>(`/companies/${cid}/risks/${risk.id}/history`);
  const pair = (a: number | null, b: number | null) => (a && b ? `${a} × ${b} = ${a * b}` : "—");
  return (
    <Dialog open onClose={onClose} title={`Cotations successives — ${risk.code}`}>
      {!data ? <Loading /> : (
        <Table>
          <THead><tr><TH>Date</TH><TH>Brut</TH><TH>Résiduel</TH><TH>Par</TH></tr></THead>
          <TBody>{data.map((h, i) => <TR key={i}><TD>{formatDate(h.changed_at)}</TD><TD>{pair(h.inherent_likelihood, h.inherent_impact)}</TD><TD>{pair(h.residual_likelihood, h.residual_impact)}</TD><TD>{personName(h.changed_by)}</TD></TR>)}</TBody>
        </Table>
      )}
    </Dialog>
  );
}

export default function RiskMapPage() {
  const { companyId } = useParams<{ companyId: string }>();
  const [basis, setBasis] = useState<"inherent" | "residual">("inherent");
  const [scaleId, setScaleId] = useState<string>("");
  const { data, error, loading, reload } = useApiResource<RiskMap>(`/companies/${companyId}/risk-map?basis=${basis}${scaleId ? `&scale_version_id=${scaleId}` : ""}`);
  const { data: risks, reload: reloadRisks } = useApiResource<RegistryRisk[]>(`/companies/${companyId}/risks`);
  const { data: methods } = useApiResource<Methodology[]>("/methodologies");
  const [selected, setSelected] = useState<string | null>(null);
  const [procDlg, setProcDlg] = useState<Proc | "new" | null>(null);
  const [riskDlg, setRiskDlg] = useState<RegistryRisk | "new" | null>(null);
  const [hist, setHist] = useState<RegistryRisk | null>(null);
  const refresh = async () => { setProcDlg(null); setRiskDlg(null); await reload(); await reloadRisks(); };

  if (loading && !data) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  if (!data) return null;
  const m = data.map;
  const procs = data.processes;
  const procCode = (id: string | null) => procs.find((p) => p.id === id)?.code ?? "—";
  const shown = (risks ?? []).filter((r) => !selected || m?.cells.find((c) => `${c.likelihood}-${c.impact}` === selected)?.risks.some((x) => x.id === r.id));
  return (
    <>
      <Link href={`/companies/${companyId}`} className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ChevronLeft className="h-4 w-4" /> Entreprise</Link>
      <PageHeader title="Cartographie des processus et des risques"
                  description="Registre de l'entité, coté sur la grille d'une méthodologie publiée (aucune grille n'est fournie par KOFINEX). Il est partagé par l'audit interne, le contrôle interne et l'audit financier."
                  actions={<>
                    <Button size="sm" variant="outline" onClick={() => setProcDlg("new")}><Plus className="h-4 w-4" /> Processus</Button>
                    <Button size="sm" onClick={() => setRiskDlg("new")}><Plus className="h-4 w-4" /> Risque</Button>
                  </>} />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div role="group" aria-label="Cotation" className="flex gap-1">
          {(["inherent", "residual"] as const).map((b) => (
            <Button key={b} size="sm" variant={basis === b ? "default" : "outline"} onClick={() => setBasis(b)}>{b === "inherent" ? "Risque brut" : "Risque résiduel"}</Button>
          ))}
        </div>
        {data.scale_versions.length > 1 && (
          <Select aria-label="Grille" className="w-64" value={scaleId || data.scale_version_id || ""} onChange={(x) => setScaleId(x.target.value)}>
            {data.scale_versions.map((v) => <option key={v} value={v}>{methods?.find((x) => x.id === v)?.name ?? v}</option>)}
          </Select>
        )}
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Card>
          <CardHeader><CardTitle>Carte des risques ({basis === "inherent" ? "bruts" : "résiduels"})</CardTitle>
            <CardDescription>Probabilité × impact. {m?.significant_from ? `Cases encadrées : score ≥ ${m.significant_from} (seuil de la grille).` : "La grille ne fixe pas de seuil."} Cliquez une case pour filtrer.</CardDescription></CardHeader>
          <CardContent>
            {!m ? <EmptyState title="Aucun risque coté" description="Cotez les risques sur la grille d'une méthodologie publiée pour afficher la carte." /> : (
              <div className="overflow-x-auto">
                <table className="w-full border-separate border-spacing-1 text-xs">
                  <tbody>
                    {[...m.likelihood].reverse().map((l) => (
                      <tr key={l.score}>
                        <th scope="row" className="w-28 pr-2 text-right font-normal text-muted-foreground">{l.score} · {l.label}</th>
                        {m.impact.map((i) => {
                          const c = m.cells.find((x) => x.likelihood === l.score && x.impact === i.score)!;
                          const key = `${l.score}-${i.score}`;
                          return (
                            <td key={i.score} className="p-0">
                              <button onClick={() => setSelected(selected === key ? null : key)} aria-pressed={selected === key}
                                      aria-label={`Probabilité ${l.score}, impact ${i.score} : ${c.risks.length} risque(s)`}
                                      className={cn("flex h-16 w-full flex-col items-center justify-center rounded-md border text-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                                        c.risks.length ? "bg-primary/10 hover:bg-primary/20" : "bg-muted/40",
                                        c.significant && "border-2 border-destructive", selected === key && "ring-2 ring-primary")}>
                                <span className="text-lg font-semibold tabular-nums">{c.risks.length || ""}</span>
                                <span className="text-muted-foreground">score {c.score}</span>
                              </button>
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                    <tr><td />{m.impact.map((i) => <td key={i.score} className="pt-1 text-center text-muted-foreground">{i.score} · {i.label}</td>)}</tr>
                  </tbody>
                </table>
                <p className="mt-1 text-center text-xs text-muted-foreground">Impact →  ·  ↑ Probabilité</p>
                {m.invalid.length > 0 && <Alert kind="warning" className="mt-3">Cotation hors grille : {m.invalid.map((x) => x.code).join(", ")}. Corrigez-la.</Alert>}
                {(m.unrated.length > 0 || data.unscaled.length > 0) && <p className="mt-2 text-xs text-muted-foreground">Non cotés : {[...m.unrated, ...data.unscaled].map((x) => x.code).join(", ")}</p>}
                {data.other_scale.length > 0 && <p className="mt-1 text-xs text-muted-foreground">Cotés sur une autre grille : {data.other_scale.map((x) => x.code).join(", ")}</p>}
              </div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Processus et couverture par le plan d&apos;audit</CardTitle></CardHeader>
          <CardContent>
            {procs.length === 0 ? <EmptyState title="Aucun processus" /> : (
              <ul className="space-y-2 text-sm">
                {procs.map((p) => (
                  <li key={p.id} className={cn("flex items-start justify-between gap-2 border-b pb-2", !p.is_active && "opacity-60")}>
                    <div>
                      <p><span className="font-medium">{p.code}</span> {p.name}{p.parent_id && <span className="text-xs text-muted-foreground"> · sous {procCode(p.parent_id)}</span>}</p>
                      <p className="text-xs text-muted-foreground">{p.owner_name ?? "Propriétaire non renseigné"} · {p.risks} risque(s)</p>
                      {p.plan_items.length === 0 ? <p className="text-xs text-muted-foreground">Aucune mission planifiée</p>
                        : p.plan_items.map((i, k) => <p key={k} className="text-xs"><Badge tone={ITEM_STATUS[i.status][1]}>{ITEM_STATUS[i.status][0]}</Badge> {i.title} ({i.plan}{i.planned_start && `, ${formatDate(i.planned_start)}`})</p>)}
                    </div>
                    <Button size="icon" variant="ghost" aria-label={`Modifier ${p.code}`} onClick={() => setProcDlg(p)}><Pencil className="h-4 w-4" /></Button>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="mt-5">
        <CardHeader className="flex-row items-center justify-between gap-3"><CardTitle>Registre des risques{selected && " (case sélectionnée)"}</CardTitle>
          {selected && <Button size="sm" variant="ghost" onClick={() => setSelected(null)}>Tout afficher</Button>}</CardHeader>
        <CardContent>
          {risks && risks.length === 0 ? <EmptyState title="Aucun risque" /> : (
            <Table>
              <THead><tr><TH>Code</TH><TH>Risque</TH><TH>Processus</TH><TH className="text-right">Brut</TH><TH className="text-right">Résiduel</TH><TH>Statut</TH><TH /></tr></THead>
              <TBody>{shown.map((r) => (
                <TR key={r.id}>
                  <TD className="font-medium">{r.code}</TD><TD>{r.title}</TD><TD>{procCode(r.process_id)}</TD>
                  <TD className="text-right tabular-nums">{r.inherent_likelihood && r.inherent_impact ? r.inherent_likelihood * r.inherent_impact : "—"}</TD>
                  <TD className="text-right tabular-nums">{r.residual_likelihood && r.residual_impact ? r.residual_likelihood * r.residual_impact : "—"}</TD>
                  <TD>{r.status === "active" ? "Actif" : <Badge>Retiré</Badge>}</TD>
                  <TD className="whitespace-nowrap text-right">
                    <Button size="icon" variant="ghost" aria-label={`Historique ${r.code}`} onClick={() => setHist(r)}><History className="h-4 w-4" /></Button>
                    <Button size="icon" variant="ghost" aria-label={`Modifier ${r.code}`} onClick={() => setRiskDlg(r)}><Pencil className="h-4 w-4" /></Button>
                  </TD>
                </TR>))}
              </TBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {procDlg && <ProcessDialog cid={companyId} proc={procDlg === "new" ? null : procDlg} all={procs} onClose={() => setProcDlg(null)} onSaved={refresh} />}
      {riskDlg && <RiskDialog cid={companyId} risk={riskDlg === "new" ? null : riskDlg} procs={procs} methods={methods ?? []} onClose={() => setRiskDlg(null)} onSaved={refresh} />}
      {hist && <RiskHistory cid={companyId} risk={hist} onClose={() => setHist(null)} />}
    </>
  );
}
