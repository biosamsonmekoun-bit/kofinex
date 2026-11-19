"use client";

import { useEffect, useState } from "react";
import { Plus, RefreshCw, Save, Trash2 } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import type { Engagement, WorkpaperStatus } from "@/lib/types";
import type { FaAccount, FaCycleTotal } from "@/lib/fa-types";
import { formatAmount } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const AREA = "w-full rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30";
type Cycles = { cycles: { code: string; label: string; account_prefixes?: string[] | null }[]; mappings: { account_prefix: string; cycle_code: string }[] };

function Mappings({ e, onSaved }: { e: Engagement; onSaved: () => void }) {
  const base = `/engagements/${e.id}/fa`;
  const { data, reload } = useApiResource<Cycles>(`${base}/cycles`);
  const [rows, setRows] = useState<{ account_prefix: string; cycle_code: string }[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const canPlan = (e.capabilities ?? []).includes("plan");
  useEffect(() => { if (data) setRows(data.mappings); }, [data]);
  if (!data) return null;
  const fromMethod = data.cycles.flatMap((c) => (c.account_prefixes ?? []).map((p) => ({ account_prefix: String(p), cycle_code: c.code })));

  async function save() {
    setBusy(true); setErr(null);
    try { await api.put(`${base}/cycles`, rows.filter((r) => r.account_prefix && r.cycle_code)); await reload(); onSaved(); }
    catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Rattachement des comptes aux cycles</CardTitle>
        <CardDescription>Préfixe le plus long retenu. Les cycles sont ceux de la méthodologie de la mission{data.cycles.length === 0 && " (aucun cycle défini)"}.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {err && <Alert>{err}</Alert>}
        {rows.map((r, i) => (
          <div key={i} className="flex gap-2">
            <Input aria-label="Préfixe de compte" className="w-32" inputMode="numeric" value={r.account_prefix} disabled={!canPlan}
                   onChange={(x) => setRows(rows.map((y, k) => (k === i ? { ...y, account_prefix: x.target.value.replace(/\D/g, "") } : y)))} />
            <Select aria-label="Cycle" value={r.cycle_code} disabled={!canPlan} onChange={(x) => setRows(rows.map((y, k) => (k === i ? { ...y, cycle_code: x.target.value } : y)))}>
              <option value="">Cycle…</option>{data.cycles.map((c) => <option key={c.code} value={c.code}>{c.code} — {c.label}</option>)}
            </Select>
            {canPlan && <Button variant="ghost" size="icon" aria-label="Retirer" onClick={() => setRows(rows.filter((_, k) => k !== i))}><Trash2 className="h-4 w-4" /></Button>}
          </div>
        ))}
        {canPlan && (
          <div className="flex flex-wrap gap-2 pt-1">
            <Button size="sm" variant="outline" onClick={() => setRows([...rows, { account_prefix: "", cycle_code: "" }])}><Plus className="h-4 w-4" /> Préfixe</Button>
            {fromMethod.length > 0 && <Button size="sm" variant="outline" onClick={() => setRows(fromMethod)}>Reprendre ceux de la méthodologie</Button>}
            <Button size="sm" onClick={save} loading={busy}><Save className="h-4 w-4" /> Enregistrer</Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function FaAccountsPanel({ e, onChanged, hasMateriality }: { e: Engagement; onChanged: () => void; hasMateriality: boolean }) {
  const base = `/engagements/${e.id}/fa`;
  const { data, error, loading, reload } = useApiResource<{ accounts: FaAccount[]; cycles: FaCycleTotal[]; has_previous: boolean }>(`${base}/account-reviews`);
  const { data: wps } = useApiResource<{ id: string; reference: string; title: string; status: WorkpaperStatus }[]>(`/engagements/${e.id}/workpapers`);
  const [cycle, setCycle] = useState<string>("all");
  const [onlyOpen, setOnlyOpen] = useState(false);
  const [edit, setEdit] = useState<FaAccount | null>(null);
  const [f, setF] = useState({ explanation: "", conclusion: "", workpaper_id: "" });
  const [msg, setMsg] = useState<{ kind: "error" | "success"; text: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const canEdit = (e.capabilities ?? []).includes("edit_procedures");

  async function refresh() {
    setBusy("refresh"); setMsg(null);
    try {
      const r = await api.post<{ created: number; updated: number; reset: number }>(`${base}/account-reviews/refresh`, {});
      setMsg({ kind: "success", text: `${r.created} compte(s) ajouté(s), ${r.updated} actualisé(s)${r.reset ? `, ${r.reset} à revoir (solde modifié)` : ""}.` });
      await reload(); onChanged();
    } catch (x) { setMsg({ kind: "error", text: errorMessage(x) }); } finally { setBusy(null); }
  }

  async function save(status?: "reviewed" | "to_review") {
    if (!edit) return;
    setBusy("save"); setMsg(null);
    try {
      await api.patch(`${base}/account-reviews/${edit.id}`, { explanation: f.explanation || null, conclusion: f.conclusion || null,
        workpaper_id: f.workpaper_id || null, ...(status ? { status } : {}) });
      setEdit(null); await reload(); onChanged();
    } catch (x) { setMsg({ kind: "error", text: errorMessage(x) }); } finally { setBusy(null); }
  }

  if (loading && !data) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  const rows = (data?.accounts ?? []).filter((a) => (cycle === "all" || (a.cycle_code ?? "") === cycle) && (!onlyOpen || a.status !== "reviewed"));
  return (
    <div className="space-y-4">
      <Mappings e={e} onSaved={() => void refresh()} />
      {msg && !edit && <Alert kind={msg.kind}>{msg.text}</Alert>}
      {!hasMateriality && <Alert kind="warning">Aucun seuil approuvé : les variations ne sont pas comparées au seuil de planification. Actualisez la revue après l&apos;approbation des seuils.</Alert>}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-sm text-muted-foreground">
          Soldes repris des balances validées N et N-1 (vérifiés en base). Une variation (ou un solde, sans N-1) égale ou supérieure au seuil de
          planification doit être expliquée avant de conclure.
        </p>
        {canEdit && <Button size="sm" onClick={refresh} loading={busy === "refresh"}><RefreshCw className="h-4 w-4" /> {data?.accounts.length ? "Actualiser depuis les balances" : "Établir depuis les balances"}</Button>}
      </div>
      {data && data.cycles.length > 0 && (
        <Table>
          <THead><tr><TH>Cycle</TH><TH className="text-right">Comptes</TH><TH className="text-right">Solde N</TH>{data.has_previous && <TH className="text-right">Solde N-1</TH>}<TH className="text-right">À expliquer</TH><TH className="text-right">À revoir</TH></tr></THead>
          <TBody>
            {data.cycles.map((c) => (
              <TR key={c.cycle_code ?? "-"} className="cursor-pointer" onClick={() => setCycle(c.cycle_code ?? "")}>
                <TD className="font-medium">{c.cycle_code ?? "Non rattachés"}</TD><TD className="text-right">{c.accounts}</TD>
                <TD className="text-right tabular-nums">{formatAmount(c.balance_n)}</TD>{data.has_previous && <TD className="text-right tabular-nums">{formatAmount(c.balance_n1)}</TD>}
                <TD className="text-right">{c.to_explain ? <Badge tone="amber">{c.to_explain}</Badge> : "—"}</TD><TD className="text-right">{c.to_review || "—"}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
      {data && data.accounts.length === 0 ? <EmptyState title="Revue des comptes non établie" description="Établissez-la depuis la balance validée de l'exercice audité (et celle de l'exercice précédent, si elle existe)." /> : (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <Select aria-label="Cycle" className="w-56" value={cycle} onChange={(x) => setCycle(x.target.value)}>
              <option value="all">Tous les cycles</option>{data?.cycles.map((c) => <option key={c.cycle_code ?? "-"} value={c.cycle_code ?? ""}>{c.cycle_code ?? "Non rattachés"}</option>)}
            </Select>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="h-4 w-4" checked={onlyOpen} onChange={(x) => setOnlyOpen(x.target.checked)} /> À revoir uniquement</label>
          </div>
          <Table>
            <THead><tr><TH>Compte</TH><TH>Cycle</TH><TH className="text-right">Solde N</TH>{data?.has_previous && <><TH className="text-right">Solde N-1</TH><TH className="text-right">Variation</TH></>}<TH>Revue</TH></tr></THead>
            <TBody>
              {rows.map((a) => (
                <TR key={a.id} className={canEdit ? "cursor-pointer" : undefined}
                    onClick={() => { if (!canEdit) return; setMsg(null); setEdit(a); setF({ explanation: a.explanation ?? "", conclusion: a.conclusion ?? "", workpaper_id: a.workpaper_id ?? "" }); }}>
                  <TD><span className="font-medium">{a.account_number}</span> <span className="text-xs text-muted-foreground">{a.account_label}</span></TD>
                  <TD>{a.cycle_code ?? "—"}</TD>
                  <TD className="text-right tabular-nums">{formatAmount(a.balance_n)}</TD>
                  {data?.has_previous && <><TD className="text-right tabular-nums">{formatAmount(a.balance_n1)}</TD><TD className="text-right tabular-nums">{formatAmount(a.variation)}</TD></>}
                  <TD>
                    {a.status === "reviewed" ? <Badge tone="green">Revu</Badge> : a.requires_explanation && !a.explanation ? <Badge tone="amber">À expliquer</Badge> : <Badge>À revoir</Badge>}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </>
      )}
      <Dialog open={edit !== null} onClose={() => setEdit(null)} title={edit ? `Compte ${edit.account_number}` : ""}
              description={edit ? `Solde N ${formatAmount(edit.balance_n)}${edit.balance_n1 !== null ? ` · N-1 ${formatAmount(edit.balance_n1)} · variation ${formatAmount(edit.variation)}` : ""}${edit.threshold_used ? ` · seuil ${formatAmount(edit.threshold_used)}` : ""}` : undefined}>
        {edit && (
          <div className="space-y-3">
            {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}
            {edit.requires_explanation && <Alert kind="warning">Variation égale ou supérieure au seuil de planification : explication requise.</Alert>}
            <Field label="Explication de la variation" htmlFor="ar-exp"><textarea id="ar-exp" rows={3} className={AREA} value={f.explanation} onChange={(x) => setF({ ...f, explanation: x.target.value })} /></Field>
            <Field label="Conclusion" htmlFor="ar-con"><textarea id="ar-con" rows={2} className={AREA} value={f.conclusion} onChange={(x) => setF({ ...f, conclusion: x.target.value })} /></Field>
            <Field label="Feuille de travail" htmlFor="ar-wp">
              <Select id="ar-wp" value={f.workpaper_id} onChange={(x) => setF({ ...f, workpaper_id: x.target.value })}>
                <option value="">—</option>{wps?.map((w) => <option key={w.id} value={w.id}>{w.reference} — {w.title}</option>)}
              </Select>
            </Field>
            <div className="flex flex-wrap justify-end gap-2">
              {edit.status === "reviewed" && <Button variant="outline" onClick={() => save("to_review")} loading={busy === "save"}>Remettre à revoir</Button>}
              <Button variant="outline" onClick={() => save()} loading={busy === "save"}>Enregistrer</Button>
              {edit.status !== "reviewed" && <Button onClick={() => save("reviewed")} loading={busy === "save"}>Conclure la revue</Button>}
            </div>
          </div>
        )}
      </Dialog>
    </div>
  );
}
