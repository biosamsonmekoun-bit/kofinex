"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronRight, Plus } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { ORG_ROLE_LABELS, ORG_TYPE_LABELS, type Organization } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading, PageHeader } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";

function CreateOrganizationForm({ onCreated }: { onCreated: (org: Organization) => void }) {
  const [name, setName] = useState("");
  const [orgType, setOrgType] = useState("accounting_firm");
  const [country, setCountry] = useState("");
  const [currency, setCurrency] = useState("XOF");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const org = await api.post<Organization>("/organizations", {
        name: name.trim(), org_type: orgType, country_code: country || null, default_currency: currency,
      });
      onCreated(org);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      {error && <Alert>{error}</Alert>}
      <Field label="Nom de l'organisation" htmlFor="org-name" required>
        <Input id="org-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={200} autoFocus />
      </Field>
      <Field label="Type" htmlFor="org-type">
        <Select id="org-type" value={orgType} onChange={(e) => setOrgType(e.target.value)}>
          {Object.entries(ORG_TYPE_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </Select>
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Pays (code ISO)" htmlFor="org-country" hint="Ex. CI, SN, CM, BF">
          <Input id="org-country" value={country} maxLength={2}
                 onChange={(e) => setCountry(e.target.value.toUpperCase())} />
        </Field>
        <Field label="Devise par défaut" htmlFor="org-currency">
          <Select id="org-currency" value={currency} onChange={(e) => setCurrency(e.target.value)}>
            <option value="XOF">XOF — Franc CFA (UEMOA)</option>
            <option value="XAF">XAF — Franc CFA (CEMAC)</option>
            <option value="GNF">GNF — Franc guinéen</option>
            <option value="KMF">KMF — Franc comorien</option>
            <option value="CDF">CDF — Franc congolais</option>
            <option value="EUR">EUR — Euro</option>
            <option value="USD">USD — Dollar US</option>
          </Select>
        </Field>
      </div>
      <div className="flex justify-end">
        <Button type="submit" loading={saving} disabled={name.trim().length < 2}>Créer l&apos;organisation</Button>
      </div>
    </form>
  );
}

export default function OrganizationsPage() {
  const router = useRouter();
  const { data: orgs, error, loading } = useApiResource<Organization[]>("/organizations");
  const [open, setOpen] = useState(false);

  return (
    <>
      <PageHeader
        title="Organisations"
        description="Cabinets, groupes ou entités dont vous êtes membre."
        actions={<Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> Nouvelle organisation</Button>}
      />

      {loading && <Loading />}
      {error && <Alert>{error}</Alert>}
      {orgs && orgs.length === 0 && (
        <EmptyState
          title="Aucune organisation"
          description="Créez votre organisation pour ajouter vos entreprises, inviter vos collaborateurs et importer vos balances."
          action={<Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> Créer une organisation</Button>}
        />
      )}
      {orgs && orgs.length > 0 && (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {orgs.map((o) => (
            <Link key={o.id} href={`/organizations/${o.id}/companies`}>
              <Card className="flex items-center justify-between p-5 transition-shadow hover:shadow-md">
                <div className="min-w-0">
                  <p className="truncate font-medium">{o.name}</p>
                  <p className="mt-0.5 text-sm text-muted-foreground">
                    {ORG_TYPE_LABELS[o.org_type] ?? o.org_type} · {o.default_currency}
                  </p>
                  <div className="mt-2 flex gap-1.5">
                    {o.my_role && <Badge tone="blue">{ORG_ROLE_LABELS[o.my_role]}</Badge>}
                    {o.is_demo && <Badge tone="amber">Démonstration</Badge>}
                  </div>
                </div>
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
              </Card>
            </Link>
          ))}
        </div>
      )}

      <Dialog open={open} onClose={() => setOpen(false)} title="Nouvelle organisation"
              description="Vous en serez le propriétaire et pourrez inviter vos collaborateurs.">
        <CreateOrganizationForm onCreated={(org) => router.push(`/organizations/${org.id}/companies`)} />
      </Dialog>
    </>
  );
}
