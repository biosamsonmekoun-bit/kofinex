"use client";

import { useState } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { CENTER_TYPE_LABELS, type CenterType, type CostCenter, type CostEntry, type FiscalYear } from "@/lib/types";
import { formatAmount, formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const NATURES = { direct: "Directe", indirect: "Indirecte", fixed: "Fixe", variable: "Variable", semi_variable: "Semi-variable" } as const;

type CenterForm = Omit<CostCenter, "id">;
const EMPTY_CENTER: CenterForm = { code: "", name: "", center_type: "main", parent_id: null, description: null, work_unit: null, is_active: true };

function CenterDialog({ companyId, centers, editing, onClose, onSaved }: {
  companyId: string; centers: CostCenter[]; editing: CostCenter | "new" | null; onClose: () => void; onSaved: () => void;
}) {
  const [f, setF] = useState<CenterForm>(editing && editing !== "new" ? { ...editing } : EMPTY_CENTER);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const isNew = editing === "new";

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const body = { ...f, parent_id: f.parent_id || null, description: f.description || null, work_unit: f.work_unit || null };
      if (isNew) await api.post(`/companies/${companyId}/cost-centers`, body);
      else await api.patch(`/companies/${companyId}/cost-centers/${(editing as CostCenter).id}`, body);
      onSaved();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={editing !== null} onClose={onClose} title={isNew ? "Nouveau centre de coûts" : "Modifier le centre"}>
      <form onSubmit={save} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Code" htmlFor="cc-code" required>
            <Input id="cc-code" value={f.code} maxLength={30} onChange={(e) => setF({ ...f, code: e.target.value })} required />
          </Field>
          <div className="sm:col-span-2">
            <Field label="Nom" htmlFor="cc-name" required>
              <Input id="cc-name" value={f.name} maxLength={200} onChange={(e) => setF({ ...f, name: e.target.value })} required />
            </Field>
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Type" htmlFor="cc-type">
            <Select id="cc-type" value={f.center_type} onChange={(e) => setF({ ...f, center_type: e.target.value as CenterType })}>
              {Object.entries(CENTER_TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </Select>
          </Field>
          <Field label="Centre parent" htmlFor="cc-parent" hint="Le réalisé d'un centre inclut celui de ses sous-centres.">
            <Select id="cc-parent" value={f.parent_id ?? ""} onChange={(e) => setF({ ...f, parent_id: e.target.value || null })}>
              <option value="">Aucun</option>
              {centers.filter((c) => editing === "new" || c.id !== (editing as CostCenter).id)
                .map((c) => <option key={c.id} value={c.id}>{c.code} — {c.name}</option>)}
            </Select>
          </Field>
        </div>
        <Field label="Unité d'œuvre habituelle" htmlFor="cc-uo" hint="Libellé libre, par exemple « heure-machine ».">
          <Input id="cc-uo" value={f.work_unit ?? ""} maxLength={100} onChange={(e) => setF({ ...f, work_unit: e.target.value })} />
        </Field>
        <Field label="Description" htmlFor="cc-desc">
          <Input id="cc-desc" value={f.description ?? ""} maxLength={2000} onChange={(e) => setF({ ...f, description: e.target.value })} />
        </Field>
        {!isNew && (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} className="h-4 w-4" /> Centre actif
          </label>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>Annuler</Button>
          <Button type="submit" loading={saving}>Enregistrer</Button>
        </div>
      </form>
    </Dialog>
  );
}

function EntryForm({ companyId, fy, centers, onSaved }: { companyId: string; fy: FiscalYear; centers: CostCenter[]; onSaved: () => void }) {
  const [f, setF] = useState({ cost_center_id: "", account_number: "", entry_date: fy.start_date, amount: "", cost_nature: "indirect", description: "" });
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const amount = f.amount.replace(/[\s  ]/g, "").replace(",", ".");
    if (!/^-?\d+(\.\d{1,2})?$/.test(amount)) { setError("Montant invalide (2 décimales maximum)."); return; }
    setSaving(true);
    setError(null);
    try {
      await api.post(`/companies/${companyId}/fiscal-years/${fy.id}/cost-entries`, {
        ...f, amount, account_number: f.account_number || null, description: f.description || null });
      setF({ ...f, amount: "", description: "" });
      onSaved();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={save} className="space-y-3">
      {error && <Alert>{error}</Alert>}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
        <div className="lg:col-span-2">
          <Field label="Centre" htmlFor="ce-center" required>
            <Select id="ce-center" value={f.cost_center_id} onChange={(e) => setF({ ...f, cost_center_id: e.target.value })} required>
              <option value="">Choisir…</option>
              {centers.filter((c) => c.is_active).map((c) => <option key={c.id} value={c.id}>{c.code} — {c.name}</option>)}
            </Select>
          </Field>
        </div>
        <Field label="Compte" htmlFor="ce-acct"><Input id="ce-acct" value={f.account_number} inputMode="numeric" onChange={(e) => setF({ ...f, account_number: e.target.value.trim() })} /></Field>
        <Field label="Date" htmlFor="ce-date" required>
          <Input id="ce-date" type="date" min={fy.start_date} max={fy.end_date} value={f.entry_date} onChange={(e) => setF({ ...f, entry_date: e.target.value })} required />
        </Field>
        <Field label="Montant" htmlFor="ce-amount" required><Input id="ce-amount" value={f.amount} inputMode="decimal" className="text-right" onChange={(e) => setF({ ...f, amount: e.target.value })} required /></Field>
        <Field label="Nature" htmlFor="ce-nature">
          <Select id="ce-nature" value={f.cost_nature} onChange={(e) => setF({ ...f, cost_nature: e.target.value })}>
            {Object.entries(NATURES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
        </Field>
      </div>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="flex-1"><Field label="Libellé" htmlFor="ce-desc"><Input id="ce-desc" value={f.description} maxLength={500} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field></div>
        <Button type="submit" loading={saving}><Plus className="h-4 w-4" /> Ajouter</Button>
      </div>
    </form>
  );
}

export function CentersTab({ companyId, fy, canWrite }: { companyId: string; fy: FiscalYear; canWrite: boolean }) {
  const centersRes = useApiResource<CostCenter[]>(`/companies/${companyId}/cost-centers`);
  const entriesRes = useApiResource<{ total: number; total_amount: string; items: CostEntry[] }>(
    `/companies/${companyId}/fiscal-years/${fy.id}/cost-entries?limit=200`);
  const [editing, setEditing] = useState<CostCenter | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const centers = centersRes.data ?? [];
  const name = (id: string | null) => { const c = centers.find((x) => x.id === id); return c ? `${c.code} — ${c.name}` : ""; };

  async function remove(path: string, reload: () => Promise<void>) {
    setError(null);
    try { await api.del(path); await reload(); } catch (e) { setError(errorMessage(e)); }
  }

  if (centersRes.loading && !centersRes.data) return <Loading />;
  if (centersRes.error) return <Alert>{centersRes.error}</Alert>;
  const closed = fy.status !== "open";

  return (
    <div className="space-y-5">
      {error && <Alert>{error}</Alert>}
      <Card>
        <CardHeader className="flex-row items-start justify-between gap-3">
          <div>
            <CardTitle>Centres de coûts</CardTitle>
            <CardDescription>Structure analytique de l&apos;entreprise, commune à tous les exercices.</CardDescription>
          </div>
          {canWrite && <Button size="sm" onClick={() => setEditing("new")}><Plus className="h-4 w-4" /> Centre</Button>}
        </CardHeader>
        <CardContent className="p-0">
          {centers.length === 0 ? (
            <div className="p-5"><EmptyState title="Aucun centre de coûts" description="Créez les centres principaux, auxiliaires ou de structure de l'entreprise." /></div>
          ) : (
            <Table>
              <THead><tr><TH>Code</TH><TH>Nom</TH><TH>Type</TH><TH>Parent</TH><TH>Unité d&apos;œuvre</TH><TH>État</TH><TH /></tr></THead>
              <TBody>
                {centers.map((c) => (
                  <TR key={c.id}>
                    <TD className="font-medium">{c.code}</TD><TD>{c.name}</TD><TD>{CENTER_TYPE_LABELS[c.center_type]}</TD>
                    <TD>{name(c.parent_id)}</TD><TD>{c.work_unit ?? ""}</TD>
                    <TD>{c.is_active ? <Badge tone="green">Actif</Badge> : <Badge>Inactif</Badge>}</TD>
                    <TD className="whitespace-nowrap text-right">
                      {canWrite && (
                        <>
                          <Button variant="ghost" size="icon" aria-label={`Modifier ${c.code}`} onClick={() => setEditing(c)}><Pencil className="h-4 w-4" /></Button>
                          <Button variant="ghost" size="icon" aria-label={`Supprimer ${c.code}`} onClick={() => remove(`/companies/${companyId}/cost-centers/${c.id}`, centersRes.reload)}><Trash2 className="h-4 w-4" /></Button>
                        </>
                      )}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Saisies analytiques — exercice {fy.label}</CardTitle>
          <CardDescription>
            Coûts affectés aux centres : ils alimentent le réalisé des lignes de budget par centre, mois par mois.
            {entriesRes.data && <> Total : <span className="tabular-nums">{formatAmount(entriesRes.data.total_amount)}</span> ({entriesRes.data.total} saisie{entriesRes.data.total > 1 ? "s" : ""}).</>}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {canWrite && !closed && centers.length > 0 && <EntryForm companyId={companyId} fy={fy} centers={centers} onSaved={entriesRes.reload} />}
          {closed && <Alert kind="info">Exercice clôturé : les saisies analytiques sont figées.</Alert>}
          {entriesRes.error && <Alert>{entriesRes.error}</Alert>}
          {entriesRes.data && entriesRes.data.items.length > 0 && (
            <Table>
              <THead><tr><TH>Date</TH><TH>Centre</TH><TH>Compte</TH><TH>Libellé</TH><TH>Nature</TH><TH className="text-right">Montant</TH><TH /></tr></THead>
              <TBody>
                {entriesRes.data.items.map((e) => (
                  <TR key={e.id}>
                    <TD className="whitespace-nowrap">{formatDate(e.entry_date)}</TD><TD>{name(e.cost_center_id)}</TD>
                    <TD>{e.account_number ?? ""}</TD><TD>{e.description ?? ""}</TD>
                    <TD>{NATURES[e.cost_nature as keyof typeof NATURES] ?? e.cost_nature}</TD>
                    <TD className="text-right">{formatAmount(e.amount)}</TD>
                    <TD className="text-right">
                      {canWrite && !closed && (
                        <Button variant="ghost" size="icon" aria-label="Supprimer la saisie" onClick={() => remove(`/companies/${companyId}/cost-entries/${e.id}`, entriesRes.reload)}>
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      )}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
          {entriesRes.data && entriesRes.data.total > entriesRes.data.items.length && (
            <p className="text-xs text-muted-foreground">Les {entriesRes.data.items.length} saisies les plus récentes sont affichées.</p>
          )}
        </CardContent>
      </Card>

      {editing && (
        <CenterDialog key={editing === "new" ? "new" : editing.id} companyId={companyId} centers={centers} editing={editing}
                      onClose={() => setEditing(null)} onSaved={() => { setEditing(null); void centersRes.reload(); }} />
      )}
    </div>
  );
}
