"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import type { IcDomain } from "@/lib/ic-types";
import { AREA, IcShell, canManage } from "@/components/ic-shell";
import { ProcessDialog, useIcRefs } from "@/components/ic-forms";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

type Template = { code: string; name: string; category: string; processes: string[]; used: boolean };
const CATEGORY: Record<string, string> = { accounting_financial: "Comptable et financier", organizational: "Organisationnel", custom: "Personnalisé" };

function DomainDialog({ cid, d, onClose, onSaved }: { cid: string; d: IcDomain | null; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState({ code: d?.code ?? "", name: d?.name ?? "", category: d?.category ?? "custom", cycle_code: d?.cycle_code ?? "",
    description: d?.description ?? "", owner_name: d?.owner_name ?? "", is_active: d?.is_active ?? true, display_order: d?.display_order ?? 0 });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function save(ev: React.FormEvent) {
    ev.preventDefault(); setBusy(true); setErr(null);
    const body = { ...f, cycle_code: f.cycle_code || null, description: f.description || null, owner_name: f.owner_name || null };
    try { if (d) await api.patch(`/companies/${cid}/ic/domains/${d.id}`, body); else await api.post(`/companies/${cid}/ic/domains`, body); onSaved(); }
    catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }
  return (
    <Dialog open onClose={onClose} title={d ? `Domaine ${d.code}` : "Nouveau domaine"}>
      <form onSubmit={save} className="space-y-3">
        {err && <Alert>{err}</Alert>}
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Code" htmlFor="d-c" required><Input id="d-c" required disabled={!!d} value={f.code} onChange={(x) => setF({ ...f, code: x.target.value })} /></Field>
          <div className="sm:col-span-2"><Field label="Intitulé" htmlFor="d-n" required><Input id="d-n" required value={f.name} onChange={(x) => setF({ ...f, name: x.target.value })} /></Field></div>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Catégorie" htmlFor="d-cat"><Select id="d-cat" value={f.category} onChange={(x) => setF({ ...f, category: x.target.value })}>
            {Object.entries(CATEGORY).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
          <Field label="Cycle d'audit (code)" htmlFor="d-cy" hint="Code d'un cycle de la méthodologie d'audit financier, pour le rapprochement"><Input id="d-cy" value={f.cycle_code} onChange={(x) => setF({ ...f, cycle_code: x.target.value })} /></Field>
          <Field label="Responsable" htmlFor="d-o"><Input id="d-o" value={f.owner_name} onChange={(x) => setF({ ...f, owner_name: x.target.value })} /></Field>
        </div>
        <Field label="Description" htmlFor="d-de"><textarea id="d-de" rows={2} className={AREA} value={f.description} onChange={(x) => setF({ ...f, description: x.target.value })} /></Field>
        {d && <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="h-4 w-4" checked={f.is_active} onChange={(x) => setF({ ...f, is_active: x.target.checked })} /> Domaine actif</label>}
        <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={onClose}>Annuler</Button><Button type="submit" loading={busy}>Enregistrer</Button></div>
      </form>
    </Dialog>
  );
}

export default function DomainsPage() {
  const { companyId: cid } = useParams<{ companyId: string }>();
  const refs = useIcRefs(cid);
  const { data: templates, reload: reloadT } = useApiResource<Template[]>(`/companies/${cid}/ic/templates`);
  const [chosen, setChosen] = useState<string[]>([]);
  const [withProc, setWithProc] = useState(true);
  const [dlg, setDlg] = useState<IcDomain | "new" | null>(null);
  const [proc, setProc] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const refresh = async () => { setDlg(null); setProc(null); await refs.reload(); await reloadT(); };
  async function instantiate() {
    setBusy(true); setErr(null);
    try { await api.post(`/companies/${cid}/ic/domains/from-templates`, { codes: chosen, with_processes: withProc }); setChosen([]); await refresh(); }
    catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }
  async function remove(d: IcDomain) {
    setErr(null);
    try { await api.del(`/companies/${cid}/ic/domains/${d.id}`); await refresh(); } catch (x) { setErr(errorMessage(x)); }
  }
  return (
    <IcShell cid={cid} title="Domaines et cartographie des processus"
             description="Organisez le dispositif par domaine, cycle, processus et sous-processus. Les modèles sont des structures d'organisation modifiables, sans contenu normatif.">
      {(access) => (
        <div className="space-y-5">
          {err && <Alert>{err}</Alert>}
          <div className="flex justify-end gap-2">
            {access.can_manage_registry && <Button size="sm" variant="outline" onClick={() => setProc("new")}><Plus className="h-4 w-4" /> Processus</Button>}
            {access.is_admin && <Button size="sm" onClick={() => setDlg("new")}><Plus className="h-4 w-4" /> Domaine</Button>}
          </div>
          {refs.domains.length === 0 ? <EmptyState title="Aucun domaine" description="Choisissez ci-dessous les domaines utiles à l'entité, ou créez les vôtres." /> : (
            <Table>
              <THead><tr><TH>Domaine</TH><TH>Catégorie</TH><TH>Cycle</TH><TH>Processus</TH><TH>Responsable</TH><TH /></tr></THead>
              <TBody>{refs.domains.map((d) => (
                <TR key={d.id}>
                  <TD><Link className="text-link hover:underline" href={`/companies/${cid}/controle-interne/domaines/${d.id}`}>{d.code} — {d.name}</Link> {!d.is_active && <Badge>Inactif</Badge>}</TD>
                  <TD>{CATEGORY[d.category]}</TD><TD>{d.cycle_code ?? "—"}</TD>
                  <TD>{refs.processes.filter((p) => p.domain_id === d.id).length}</TD><TD>{d.owner_name ?? "—"}</TD>
                  <TD className="text-right">
                    {canManage(access, d.id) && <Button size="icon" variant="ghost" aria-label={`Modifier ${d.code}`} onClick={() => setDlg(d)}><Pencil className="h-4 w-4" /></Button>}
                    {access.is_admin && <Button size="icon" variant="ghost" aria-label={`Supprimer ${d.code}`} onClick={() => remove(d)}><Trash2 className="h-4 w-4" /></Button>}
                  </TD>
                </TR>
              ))}</TBody>
            </Table>
          )}
          {access.is_admin && templates && (
            <Card>
              <CardHeader><CardTitle>Modèles de domaines</CardTitle>
                <CardDescription>Cochez les domaines à créer. Aucun domaine n&apos;est imposé ; tout reste modifiable, désactivable et complétable.</CardDescription></CardHeader>
              <CardContent className="space-y-3">
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {templates.map((t) => (
                    <label key={t.code} className="flex items-start gap-2 rounded-md border p-2 text-sm">
                      <input type="checkbox" className="mt-0.5 h-4 w-4" disabled={t.used} checked={chosen.includes(t.code)}
                             onChange={(x) => setChosen(x.target.checked ? [...chosen, t.code] : chosen.filter((c) => c !== t.code))} />
                      <span><span className="font-medium">{t.code} — {t.name}</span>
                        <span className="block text-xs text-muted-foreground">{CATEGORY[t.category]} · {t.processes.length ? `${t.processes.length} processus proposés` : "processus à définir"}{t.used ? " · déjà créé" : ""}</span></span>
                    </label>
                  ))}
                </div>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="h-4 w-4" checked={withProc} onChange={(x) => setWithProc(x.target.checked)} /> Créer aussi les processus proposés</label>
                  <Button size="sm" disabled={!chosen.length} loading={busy} onClick={instantiate}>Créer {chosen.length || ""} domaine(s)</Button>
                </div>
              </CardContent>
            </Card>
          )}
          {dlg && <DomainDialog cid={cid} d={dlg === "new" ? null : dlg} onClose={() => setDlg(null)} onSaved={refresh} />}
          {proc && <ProcessDialog cid={cid} proc={null} domains={refs.domains.filter((d) => canManage(access, d.id))} processes={refs.processes} onClose={() => setProc(null)} onSaved={refresh} />}
        </div>
      )}
    </IcShell>
  );
}
