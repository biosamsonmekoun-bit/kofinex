"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { Plus } from "lucide-react";
import { AccountingShell } from "@/components/accounting-shell";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import type { CompanyAccount, Journal, JournalType } from "@/lib/accounting-types";
import { JOURNAL_TYPE_LABEL } from "@/lib/accounting-types";
import type { CompanyMember } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

type Form = { code: string; label: string; journal_type: JournalType; number_prefix: string; counterpart_account_number: string; restricted: boolean; allowed_users: string[]; is_active: boolean };
const EMPTY: Form = { code: "", label: "", journal_type: "general", number_prefix: "", counterpart_account_number: "", restricted: false, allowed_users: [], is_active: true };

export default function JournalsPage() {
  const { companyId: cid } = useParams<{ companyId: string }>();
  return <AccountingShell cid={cid} title="Journaux">{({ settings }) => <Journals cid={cid} canEdit={settings.permissions.setup} />}</AccountingShell>;
}

function Journals({ cid, canEdit }: { cid: string; canEdit: boolean }) {
  const A = `/companies/${cid}/accounting`;
  const { data, error, reload } = useApiResource<Journal[]>(`${A}/journals`);
  const { data: accounts } = useApiResource<{ items: CompanyAccount[] }>(`${A}/accounts?active=true&limit=5000`);
  const { data: members } = useApiResource<CompanyMember[]>(`/companies/${cid}/members`);
  const [edit, setEdit] = useState<Journal | "new" | null>(null);
  const [f, setF] = useState<Form>(EMPTY);
  const [msg, setMsg] = useState<string | null>(null);
  const treasury = (accounts?.items ?? []).filter((a) => a.account_number.startsWith("5"));

  function open(j: Journal | "new") {
    setMsg(null); setEdit(j);
    setF(j === "new" ? EMPTY : { code: j.code, label: j.label, journal_type: j.journal_type, number_prefix: j.number_prefix,
      counterpart_account_number: j.counterpart_account_number ?? "", restricted: !!j.allowed_users, allowed_users: j.allowed_users ?? [], is_active: j.is_active });
  }
  async function save() {
    setMsg(null);
    const body = { code: f.code, label: f.label, journal_type: f.journal_type, number_prefix: f.number_prefix || (edit === "new" ? null : f.number_prefix),
      counterpart_account_number: f.counterpart_account_number || null, allowed_users: f.restricted ? f.allowed_users : null, is_active: f.is_active };
    try {
      if (edit === "new") await api.post(`${A}/journals`, body); else await api.patch(`${A}/journals/${(edit as Journal).id}`, body);
      setEdit(null); await reload();
    } catch (e) { setMsg(errorMessage(e)); }
  }
  async function remove(j: Journal) {
    try { await api.del(`${A}/journals/${j.id}`); await reload(); } catch (e) { setMsg(errorMessage(e)); }
  }
  if (error) return <Alert>{error}</Alert>;
  if (!data) return <Loading />;
  const used = edit !== "new" && edit !== null && edit.entries > 0;
  return (
    <>
      {canEdit && <Button className="mb-4" onClick={() => open("new")}><Plus className="h-4 w-4" aria-hidden /> Nouveau journal</Button>}
      {msg && !edit && <Alert className="mb-3">{msg}</Alert>}
      {!data.length ? <EmptyState title="Aucun journal" description="Créez les journaux de l'entreprise (ventes, achats, banque, caisse, opérations diverses…)." /> : (
        <Table>
          <THead><tr><TH>Code</TH><TH>Intitulé</TH><TH>Type</TH><TH>Préfixe</TH><TH>Trésorerie</TH><TH>Accès</TH><TH className="text-right">Écritures</TH><TH>État</TH><TH /></tr></THead>
          <TBody>{data.map((j) => (
            <TR key={j.id}>
              <TD className="font-semibold">{j.code}</TD><TD>{j.label}</TD><TD>{JOURNAL_TYPE_LABEL[j.journal_type]}</TD><TD>{j.number_prefix}</TD>
              <TD>{j.counterpart_account_number ?? ""}</TD><TD>{j.allowed_users ? `${j.allowed_users.length} utilisateur(s)` : "Comptables"}</TD>
              <TD className="text-right">{j.entries}</TD><TD>{j.is_active ? <Badge tone="green">Actif</Badge> : <Badge>Désactivé</Badge>}</TD>
              <TD className="whitespace-nowrap">{canEdit && <><Button size="sm" variant="ghost" onClick={() => open(j)}>Modifier</Button>
                {j.entries === 0 && <Button size="sm" variant="ghost" onClick={() => void remove(j)}>Supprimer</Button>}</>}</TD>
            </TR>))}
          </TBody>
        </Table>
      )}
      <Dialog open={edit !== null} onClose={() => setEdit(null)} title={edit === "new" ? "Nouveau journal" : "Modifier le journal"}
              description={used ? "Journal déjà utilisé : code, type et préfixe de numérotation sont figés." : undefined}>
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); void save(); }}>
          {msg && <Alert>{msg}</Alert>}
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Code" htmlFor="jc" required hint="Majuscules et chiffres, 8 au plus"><Input id="jc" value={f.code} disabled={used} required maxLength={8}
              onChange={(e) => setF({ ...f, code: e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "") })} /></Field>
            <Field label="Type" htmlFor="jt" required><Select id="jt" value={f.journal_type} disabled={used} onChange={(e) => setF({ ...f, journal_type: e.target.value as JournalType })}>
              {Object.entries(JOURNAL_TYPE_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select></Field>
          </div>
          <Field label="Intitulé" htmlFor="jl" required><Input id="jl" value={f.label} required onChange={(e) => setF({ ...f, label: e.target.value })} /></Field>
          <Field label="Préfixe de numérotation" htmlFor="jp" hint="Par défaut : code suivi d'un tiret (ex. VT-000001)"><Input id="jp" value={f.number_prefix} disabled={used} maxLength={12}
            onChange={(e) => setF({ ...f, number_prefix: e.target.value.toUpperCase().replace(/[^A-Z0-9_-]/g, "") })} /></Field>
          {(f.journal_type === "bank" || f.journal_type === "cash") && (
            <Field label="Compte de trésorerie" htmlFor="ja" required><Select id="ja" value={f.counterpart_account_number} required onChange={(e) => setF({ ...f, counterpart_account_number: e.target.value })}>
              <option value="">— Choisir —</option>{treasury.map((a) => <option key={a.id} value={a.account_number}>{a.account_number} · {a.label}</option>)}</Select></Field>
          )}
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.restricted} onChange={(e) => setF({ ...f, restricted: e.target.checked })} /> Réserver la saisie à certains utilisateurs</label>
          {f.restricted && <div className="max-h-40 space-y-1 overflow-y-auto rounded border p-2 text-sm">
            {(members ?? []).map((m) => (
              <label key={m.user_id} className="flex items-center gap-2"><input type="checkbox" checked={f.allowed_users.includes(m.user_id)}
                onChange={(e) => setF({ ...f, allowed_users: e.target.checked ? [...f.allowed_users, m.user_id] : f.allowed_users.filter((x) => x !== m.user_id) })} />
                {m.full_name || m.email} <span className="text-xs text-muted-foreground">({m.role})</span></label>))}
            <p className="text-xs text-muted-foreground">Les administrateurs de l&apos;organisation conservent l&apos;accès.</p></div>}
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} /> Actif</label>
          <Button type="submit">Enregistrer</Button>
        </form>
      </Dialog>
    </>
  );
}
