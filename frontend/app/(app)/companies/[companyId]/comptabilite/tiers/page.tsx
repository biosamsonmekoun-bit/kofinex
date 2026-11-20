"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { Plus } from "lucide-react";
import { AccountingShell } from "@/components/accounting-shell";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import type { CompanyAccount, ThirdParty, TpCategory, TpKind } from "@/lib/accounting-types";
import { TP_CATEGORY_LABEL, TP_KIND_LABEL } from "@/lib/accounting-types";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const FIELDS = ["code", "name", "kind", "collective_account_number", "tax_id", "registration_number", "address", "city", "country_code", "email", "phone"] as const;
type Form = Record<(typeof FIELDS)[number], string> & { is_active: boolean };
const EMPTY: Form = { code: "", name: "", kind: "customer", collective_account_number: "", tax_id: "", registration_number: "", address: "", city: "", country_code: "", email: "", phone: "", is_active: true };

export default function ThirdPartiesPage() {
  const { companyId: cid } = useParams<{ companyId: string }>();
  return <AccountingShell cid={cid} title="Plan tiers">{({ settings }) => <Tiers cid={cid} canEdit={settings.permissions.setup} />}</AccountingShell>;
}

function Tiers({ cid, canEdit }: { cid: string; canEdit: boolean }) {
  const A = `/companies/${cid}/accounting`;
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("");
  const [category, setCategory] = useState<TpCategory | "">("");
  const [toAttach, setToAttach] = useState(false);
  const qs = new URLSearchParams({ limit: "2000", ...(q ? { q } : {}), ...(kind ? { kind } : {}), ...(category ? { category } : {}),
                                   ...(toAttach ? { unattached: "true" } : {}) });
  const { data, error, reload } = useApiResource<{ total: number; items: ThirdParty[]; categories: Record<TpCategory, number>; unattached: number }>(
    `${A}/third-parties?${qs}`);
  const { data: accounts } = useApiResource<{ items: CompanyAccount[] }>(`${A}/accounts?active=true&limit=5000`);
  const [edit, setEdit] = useState<ThirdParty | "new" | null>(null);
  const [f, setF] = useState<Form>(EMPTY);
  const [msg, setMsg] = useState<string | null>(null);
  const collectives = (accounts?.items ?? []).filter((a) => a.requires_third_party && (!a.third_party_kind || a.third_party_kind === f.kind));

  function open(t: ThirdParty | "new") {
    setMsg(null); setEdit(t);
    setF(t === "new" ? EMPTY : { ...(Object.fromEntries(FIELDS.map((k) => [k, (t[k] as string | null) ?? ""])) as unknown as Form), is_active: t.is_active });
  }
  async function save() {
    setMsg(null);
    const body = { ...Object.fromEntries(FIELDS.map((k) => [k, f[k].trim() === "" ? null : f[k].trim()])), is_active: f.is_active };
    try {
      if (edit === "new") await api.post(`${A}/third-parties`, body); else await api.patch(`${A}/third-parties/${(edit as ThirdParty).id}`, body);
      setEdit(null); await reload();
    } catch (e) { setMsg(errorMessage(e)); }
  }
  if (error) return <Alert>{error}</Alert>;
  if (!data) return <Loading />;
  const label: Record<string, string> = { tax_id: "Numéro fiscal", registration_number: "Registre du commerce", address: "Adresse", city: "Ville",
    country_code: "Pays (ISO, ex. CI)", email: "Courriel", phone: "Téléphone" };
  const total = Object.values(data.categories).reduce((x, y) => x + y, 0);
  return (
    <>
      <p className="mb-3 text-sm text-muted-foreground">
        Comptes auxiliaires de tiers (code alphanumérique, ex. 4011TOY), chacun rattaché à un compte collectif numérique du plan
        comptable. Leurs soldes individuels figurent dans la balance auxiliaire et remontent dans leur compte collectif.
      </p>
      <div role="tablist" aria-label="Catégories de tiers" className="mb-3 flex flex-wrap gap-1 border-b">
        {([["", "Tous", total], ...(Object.keys(TP_CATEGORY_LABEL) as TpCategory[]).map((c) => [c, TP_CATEGORY_LABEL[c], data.categories[c]])] as [TpCategory | "", string, number][]).map(([c, l, n]) => (
          <button key={c || "all"} type="button" role="tab" aria-selected={category === c} onClick={() => { setCategory(c); setKind(""); }}
                  className={`-mb-px border-b-2 px-3 py-2 text-sm ${category === c ? "border-primary font-semibold" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
            {l} <span className="tabular-nums text-muted-foreground">({n})</span>
          </button>
        ))}
      </div>
      {data.unattached > 0 && (
        <Alert kind="warning" className="mb-3">
          {data.unattached} tiers repris ne sont rattachés à aucun compte collectif : ils ne peuvent plus être utilisés sur une écriture tant
          qu&apos;ils ne sont pas rattachés.{" "}
          <button type="button" className="font-semibold underline" onClick={() => setToAttach(!toAttach)}>{toAttach ? "Afficher tous les tiers" : "Afficher les tiers à rattacher"}</button>
        </Alert>
      )}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Input aria-label="Rechercher un tiers" className="w-64" placeholder="Code, nom, numéro fiscal…" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select aria-label="Type" className="w-48" value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="">Tous les types</option>{Object.entries(TP_KIND_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select>
        {canEdit && <Button onClick={() => open("new")}><Plus className="h-4 w-4" aria-hidden /> Nouveau tiers</Button>}
      </div>
      {!data.items.length ? <EmptyState title={toAttach ? "Aucun tiers à rattacher" : "Aucun tiers"} description="Créez les clients, fournisseurs, salariés et autres tiers, chacun rattaché à un compte collectif." /> : (
        <Table>
          <THead><tr><TH>Code auxiliaire</TH><TH>Intitulé</TH><TH>Type</TH><TH>Compte collectif</TH><TH>Numéro fiscal</TH><TH>Ville</TH><TH>État</TH><TH /></tr></THead>
          <TBody>{data.items.map((t) => (
            <TR key={t.id}><TD className="font-medium">{t.code}</TD><TD>{t.name}</TD><TD>{TP_KIND_LABEL[t.kind]}</TD><TD>{t.attached ? t.collective_account_number : <Badge tone="amber">À rattacher</Badge>}</TD>
              <TD className="text-xs">{t.tax_id ?? ""}</TD><TD className="text-xs">{t.city ?? ""}</TD>
              <TD>{t.is_active ? <Badge tone="green">Actif</Badge> : <Badge>En sommeil</Badge>}</TD>
              <TD>{canEdit && <Button size="sm" variant="ghost" onClick={() => open(t)}>Modifier</Button>}</TD></TR>))}
          </TBody>
        </Table>
      )}
      <Dialog open={edit !== null} onClose={() => setEdit(null)} title={edit === "new" ? "Nouveau tiers" : `Tiers ${f.code}`} size="lg">
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); void save(); }}>
          {msg && <Alert>{msg}</Alert>}
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Code auxiliaire" htmlFor="tc" required hint="Lettres et chiffres (ex. 4011TOY)."><Input id="tc" value={f.code} required maxLength={30} onChange={(e) => setF({ ...f, code: e.target.value.replace(/[^A-Za-z0-9._-]/g, "") })} /></Field>
            <Field label="Type" htmlFor="tk" required><Select id="tk" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value as TpKind, collective_account_number: "" })}>
              {Object.entries(TP_KIND_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select></Field>
            <div className="sm:col-span-2"><Field label="Nom ou raison sociale" htmlFor="tn" required><Input id="tn" value={f.name} required onChange={(e) => setF({ ...f, name: e.target.value })} /></Field></div>
            <Field label="Compte collectif de rattachement" htmlFor="ta" required
                   hint={collectives.length ? "Comptes collectifs actifs compatibles avec le type de tiers." : "Aucun compte collectif actif de ce type : déclarez-en un dans le plan comptable."}>
              <Select id="ta" required value={f.collective_account_number} onChange={(e) => setF({ ...f, collective_account_number: e.target.value })}>
              <option value="" disabled>Choisir…</option>{collectives.map((a) => <option key={a.id} value={a.account_number}>{a.account_number} · {a.label}</option>)}</Select></Field>
            {(["tax_id", "registration_number", "address", "city", "country_code", "email", "phone"] as const).map((k) => (
              <Field key={k} label={label[k]} htmlFor={`t-${k}`}><Input id={`t-${k}`} value={f[k]} onChange={(e) => setF({ ...f, [k]: k === "country_code" ? e.target.value.toUpperCase().slice(0, 2) : e.target.value })} /></Field>
            ))}
          </div>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} /> Actif (décocher pour mettre en sommeil)</label>
          <Button type="submit" disabled={!f.collective_account_number}>Enregistrer</Button>
        </form>
      </Dialog>
    </>
  );
}
