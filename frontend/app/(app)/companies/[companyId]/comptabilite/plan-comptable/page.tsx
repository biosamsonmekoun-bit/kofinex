"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { Plus } from "lucide-react";
import { AccountingShell } from "@/components/accounting-shell";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import type { CompanyAccount, TpKind } from "@/lib/accounting-types";
import { TP_KIND_LABEL } from "@/lib/accounting-types";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

type Form = { account_number: string; label: string; third_party_kind: TpKind | ""; lettering_enabled: boolean; is_active: boolean };

/** Plan comptable de l'entreprise : comptes ouverts, chacun rattaché à un compte du référentiel publié. */
export default function ChartPage() {
  const { companyId: cid } = useParams<{ companyId: string }>();
  return <AccountingShell cid={cid} title="Plan comptable">{({ settings }) => <Chart cid={cid} canEdit={settings.permissions.setup} />}</AccountingShell>;
}

function Chart({ cid, canEdit }: { cid: string; canEdit: boolean }) {
  const A = `/companies/${cid}/accounting`;
  const [q, setQ] = useState("");
  const { data, error, reload } = useApiResource<{ total: number; items: CompanyAccount[] }>(`${A}/accounts?limit=5000${q ? `&q=${encodeURIComponent(q)}` : ""}`);
  const [edit, setEdit] = useState<CompanyAccount | "new" | null>(null);
  const [f, setF] = useState<Form>({ account_number: "", label: "", third_party_kind: "", lettering_enabled: false, is_active: true });
  const [msg, setMsg] = useState<{ kind: "error" | "success"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  function open(a: CompanyAccount | "new") {
    setMsg(null); setEdit(a);
    setF(a === "new" ? { account_number: "", label: "", third_party_kind: "", lettering_enabled: false, is_active: true }
      : { account_number: a.account_number, label: a.label, third_party_kind: a.third_party_kind ?? "", lettering_enabled: a.lettering_enabled, is_active: a.is_active });
  }
  async function save() {
    setMsg(null);
    try {
      const kind = f.third_party_kind || null;
      if (edit === "new") await api.post(`${A}/accounts`, { account_number: f.account_number, label: f.label, third_party_kind: kind, requires_third_party: !!kind, lettering_enabled: f.lettering_enabled });
      else await api.patch(`${A}/accounts/${(edit as CompanyAccount).id}`, { label: f.label, third_party_kind: kind, requires_third_party: !!kind, lettering_enabled: f.lettering_enabled, is_active: f.is_active });
      setEdit(null); await reload();
    } catch (e) { setMsg({ kind: "error", text: errorMessage(e) }); }
  }
  async function importChart() {
    setBusy(true); setMsg(null);
    try {
      const r = await api.post<{ created: number; framework_version: string | null }>(`${A}/accounts/import-chart`, {});
      setMsg({ kind: "success", text: `${r.created} compte(s) ouvert(s) à partir du référentiel ${r.framework_version ?? ""}. Indiquez ensuite les comptes collectifs (tiers) et lettrables.` });
      await reload();
    } catch (e) { setMsg({ kind: "error", text: errorMessage(e) }); } finally { setBusy(false); }
  }
  if (error) return <Alert>{error}</Alert>;
  if (!data) return <Loading />;
  const used = edit !== "new" && edit !== null && !!edit.used;
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Input aria-label="Rechercher un compte" className="w-64" placeholder="Numéro ou intitulé…" value={q} onChange={(e) => setQ(e.target.value)} />
        {canEdit && <>
          <Button onClick={() => open("new")}><Plus className="h-4 w-4" aria-hidden /> Ouvrir un compte</Button>
          <Button variant="outline" disabled={busy} onClick={() => void importChart()}>Ouvrir les comptes du référentiel</Button>
        </>}
      </div>
      {msg && !edit && <Alert kind={msg.kind} className="mb-3">{msg.text}</Alert>}
      {!data.items.length ? <EmptyState title="Plan comptable vide" description="Ouvrez les comptes du référentiel publié de l'entreprise, ou un compte à la fois." /> : (
        <Table>
          <THead><tr><TH>Compte</TH><TH>Intitulé</TH><TH>Référentiel</TH><TH>Nature</TH><TH>Tiers</TH><TH>Lettrable</TH><TH>État</TH><TH /></tr></THead>
          <TBody>{data.items.map((a) => (
            <TR key={a.id}>
              <TD className="font-medium">{a.account_number}</TD><TD>{a.label}</TD><TD className="text-xs text-muted-foreground">{a.chart_account_number}</TD>
              <TD className="text-xs">{a.nature ?? ""}</TD><TD className="text-xs">{a.third_party_kind ? TP_KIND_LABEL[a.third_party_kind] : a.requires_third_party ? "Obligatoire" : ""}</TD>
              <TD>{a.lettering_enabled ? "Oui" : ""}</TD><TD>{a.is_active ? <Badge tone="green">Actif</Badge> : <Badge>Désactivé</Badge>}</TD>
              <TD>{canEdit && <Button size="sm" variant="ghost" onClick={() => open(a)}>Modifier</Button>}</TD>
            </TR>))}
          </TBody>
        </Table>
      )}
      <p className="mt-2 text-xs text-muted-foreground">{data.total} compte(s)</p>
      <Dialog open={edit !== null} onClose={() => setEdit(null)} title={edit === "new" ? "Ouvrir un compte" : `Compte ${f.account_number}`}
              description="Chaque compte relève d'un compte du plan du référentiel publié (rattachement automatique par le numéro).">
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); void save(); }}>
          {msg && edit && <Alert kind={msg.kind}>{msg.text}</Alert>}
          <Field label="Numéro" htmlFor="an" required><Input id="an" inputMode="numeric" value={f.account_number} disabled={edit !== "new"} required
            onChange={(e) => setF({ ...f, account_number: e.target.value.replace(/[^0-9]/g, "") })} /></Field>
          <Field label="Intitulé" htmlFor="al" required><Input id="al" value={f.label} required onChange={(e) => setF({ ...f, label: e.target.value })} /></Field>
          <Field label="Compte collectif : tiers obligatoire" htmlFor="ak" hint={used ? "Compte mouvementé : caractère collectif figé" : undefined}>
            <Select id="ak" value={f.third_party_kind} disabled={used} onChange={(e) => setF({ ...f, third_party_kind: e.target.value as TpKind | "" })}>
              <option value="">Non</option>{Object.entries(TP_KIND_LABEL).map(([k, l]) => <option key={k} value={k}>Oui — {l}</option>)}</Select></Field>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.lettering_enabled} onChange={(e) => setF({ ...f, lettering_enabled: e.target.checked })} /> Lettrable</label>
          {edit !== "new" && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} /> Actif</label>}
          <Button type="submit">Enregistrer</Button>
        </form>
      </Dialog>
    </>
  );
}
