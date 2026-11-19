"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Plus } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { COMPANY_ROLE_LABELS, type Company, type OrgPermissions } from "@/lib/types";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading, PageHeader } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const MONTHS = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre",
  "Octobre", "Novembre", "Décembre"];

function CreateCompanyForm({ orgId, onCreated }: { orgId: string; onCreated: (c: Company) => void }) {
  const [form, setForm] = useState({
    name: "", legal_name: "", legal_form: "", framework_code: "SYSCOHADA_REV", currency: "XOF",
    country_code: "", registration_number: "", tax_id: "", activity_sector: "", city: "",
    fiscal_year_start_month: 1,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof form) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm({ ...form, [k]: e.target.value });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    // champs facultatifs vides -> null (pas de chaîne vide en base)
    const payload = Object.fromEntries(Object.entries(form).map(([k, v]) =>
      [k, typeof v === "string" ? (v.trim() || null) : v]));
    payload.fiscal_year_start_month = Number(form.fiscal_year_start_month);
    try {
      onCreated(await api.post<Company>(`/organizations/${orgId}/companies`, payload));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      {error && <Alert>{error}</Alert>}
      <Field label="Nom usuel" htmlFor="c-name" required>
        <Input id="c-name" value={form.name} onChange={set("name")} autoFocus maxLength={200} />
      </Field>
      <Field label="Référentiel comptable" htmlFor="c-fw" required
             hint="Détermine le plan de comptes et la présentation des états financiers. Non modifiable ensuite.">
        <Select id="c-fw" value={form.framework_code} onChange={set("framework_code")}>
          <option value="SYSCOHADA_REV">SYSCOHADA révisé — entités à but lucratif</option>
          <option value="SYSCEBNL">SYSCEBNL — entités à but non lucratif</option>
        </Select>
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Raison sociale" htmlFor="c-legal"><Input id="c-legal" value={form.legal_name} onChange={set("legal_name")} /></Field>
        <Field label="Forme juridique" htmlFor="c-form"><Input id="c-form" value={form.legal_form} onChange={set("legal_form")} placeholder="SA, SARL, Association…" /></Field>
        <Field label="N° RCCM" htmlFor="c-rccm"><Input id="c-rccm" value={form.registration_number} onChange={set("registration_number")} /></Field>
        <Field label="Identifiant fiscal" htmlFor="c-tax" hint="NIF, IFU, NINEA…"><Input id="c-tax" value={form.tax_id} onChange={set("tax_id")} /></Field>
        <Field label="Pays (code ISO)" htmlFor="c-country"><Input id="c-country" maxLength={2} value={form.country_code}
               onChange={(e) => setForm({ ...form, country_code: e.target.value.toUpperCase() })} /></Field>
        <Field label="Ville" htmlFor="c-city"><Input id="c-city" value={form.city} onChange={set("city")} /></Field>
        <Field label="Devise" htmlFor="c-cur">
          <Select id="c-cur" value={form.currency} onChange={set("currency")}>
            {["XOF", "XAF", "GNF", "KMF", "CDF", "EUR", "USD"].map((c) => <option key={c}>{c}</option>)}
          </Select>
        </Field>
        <Field label="Début d'exercice" htmlFor="c-month">
          <Select id="c-month" value={form.fiscal_year_start_month} onChange={set("fiscal_year_start_month")}>
            {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
          </Select>
        </Field>
      </div>
      <Field label="Secteur d'activité" htmlFor="c-sector"><Input id="c-sector" value={form.activity_sector} onChange={set("activity_sector")} /></Field>
      <div className="flex justify-end">
        <Button type="submit" loading={saving} disabled={form.name.trim().length < 2}>Créer l&apos;entreprise</Button>
      </div>
    </form>
  );
}

export default function CompaniesPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const router = useRouter();
  const [showArchived, setShowArchived] = useState(false);
  const { data: companies, error, loading } =
    useApiResource<Company[]>(`/organizations/${orgId}/companies${showArchived ? "?include_archived=true" : ""}`);
  const { data: perms } = useApiResource<OrgPermissions>(`/organizations/${orgId}/permissions`);
  const [open, setOpen] = useState(false);

  const createButton = perms?.can_create_company && (
    <Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> Nouvelle entreprise</Button>
  );

  return (
    <>
      <PageHeader title="Entreprises" description="Entités analysées au sein de l'organisation." actions={createButton} />

      <label className="mb-3 flex items-center gap-2 text-sm text-muted-foreground">
        <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
        Afficher les entreprises archivées
      </label>

      {loading && <Loading />}
      {error && <Alert>{error}</Alert>}
      {companies && companies.length === 0 && (
        <EmptyState
          title="Aucune entreprise accessible"
          description={perms?.can_create_company
            ? "Ajoutez une première entreprise pour créer ses exercices et importer ses balances."
            : "Aucune entreprise ne vous a encore été attribuée. Contactez un administrateur de l'organisation."}
          action={createButton}
        />
      )}
      {companies && companies.length > 0 && (
        <Table>
          <THead>
            <tr><TH>Entreprise</TH><TH>Référentiel</TH><TH>Pays</TH><TH>Devise</TH><TH>Votre rôle</TH><TH>Créée le</TH></tr>
          </THead>
          <TBody>
            {companies.map((c) => (
              <TR key={c.id} className="cursor-pointer" onClick={() => router.push(`/companies/${c.id}`)}>
                <TD>
                  <Link href={`/companies/${c.id}`} className="font-medium hover:underline">{c.name}</Link>
                  {c.legal_name && <p className="text-xs text-muted-foreground">{c.legal_name}</p>}
                  <div className="mt-1 flex gap-1">
                    {c.is_demo && <Badge tone="amber">Démo</Badge>}
                    {c.archived_at && <Badge>Archivée</Badge>}
                  </div>
                </TD>
                <TD>{c.framework_name}</TD>
                <TD>{c.country_code ?? "—"}</TD>
                <TD>{c.currency}</TD>
                <TD>{c.my_role ? COMPANY_ROLE_LABELS[c.my_role] : "—"}</TD>
                <TD className="text-muted-foreground">{formatDate(c.created_at)}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}

      <Dialog open={open} onClose={() => setOpen(false)} title="Nouvelle entreprise">
        <CreateCompanyForm orgId={orgId} onCreated={(c) => router.push(`/companies/${c.id}`)} />
      </Dialog>
    </>
  );
}
