"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ChevronLeft, Gauge } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { COMPANY_ROLE_LABELS, type Company } from "@/lib/types";
import { cn } from "@/lib/utils";
import { rememberOrg } from "@/components/app-shell";
import { AuditLogTable } from "@/components/audit-log-table";
import { Button } from "@/components/ui/button";
import { Alert, Badge, Loading, PageHeader } from "@/components/ui/feedback";
import { Field, Input } from "@/components/ui/form";
import { CompanyAccess } from "./company-access";
import { FiscalYears } from "./fiscal-years";
import { ImportsTab } from "./imports-tab";

type Tab = "fiscal" | "imports" | "access" | "info" | "audit";

function CompanyInfo({ company, onSaved }: { company: Company; onSaved: (c: Company) => void }) {
  const editable = company.my_permissions.includes("company.update");
  const fields = ["name", "legal_name", "legal_form", "registration_number", "tax_id",
    "country_code", "city", "address", "activity_sector"] as const;
  const labels: Record<(typeof fields)[number], string> = {
    name: "Nom usuel", legal_name: "Raison sociale", legal_form: "Forme juridique", registration_number: "N° RCCM",
    tax_id: "Identifiant fiscal", country_code: "Pays (ISO)", city: "Ville", address: "Adresse",
    activity_sector: "Secteur d'activité",
  };
  const [form, setForm] = useState(() => Object.fromEntries(fields.map((f) => [f, company[f] ?? ""])) as Record<string, string>);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setNotice(null);
    const payload = Object.fromEntries(fields.map((f) => [f, form[f].trim() || null]));
    if (!payload.name) payload.name = company.name;
    try {
      onSaved(await api.patch<Company>(`/companies/${company.id}`, payload));
      setNotice({ kind: "success", text: "Informations enregistrées." });
    } catch (err) {
      setNotice({ kind: "error", text: errorMessage(err) });
    } finally {
      setSaving(false);
    }
  }

  async function toggleArchive() {
    const archiving = !company.archived_at;
    if (archiving && !window.confirm(`Archiver ${company.name} ? Elle n'apparaîtra plus dans la liste par défaut ; ses données sont conservées.`)) return;
    try {
      onSaved(await api.post<Company>(`/companies/${company.id}/${archiving ? "archive" : "restore"}`));
      setNotice({ kind: "success", text: archiving ? "Entreprise archivée." : "Entreprise restaurée." });
    } catch (err) {
      setNotice({ kind: "error", text: errorMessage(err) });
    }
  }

  return (
    <form onSubmit={save} className="max-w-3xl space-y-4">
      {notice && <Alert kind={notice.kind}>{notice.text}</Alert>}
      <div className="grid gap-4 sm:grid-cols-2">
        {fields.map((f) => (
          <Field key={f} label={labels[f]} htmlFor={`ci-${f}`}>
            <Input id={`ci-${f}`} value={form[f]} disabled={!editable}
                   maxLength={f === "country_code" ? 2 : undefined}
                   onChange={(e) => setForm({ ...form, [f]: f === "country_code" ? e.target.value.toUpperCase() : e.target.value })} />
          </Field>
        ))}
        <Field label="Référentiel" htmlFor="ci-fw" hint="Fixé à la création de l'entreprise.">
          <Input id="ci-fw" value={company.framework_name} disabled />
        </Field>
        <Field label="Devise" htmlFor="ci-cur"><Input id="ci-cur" value={company.currency} disabled /></Field>
      </div>
      {editable && (
        <div className="flex justify-between">
          <Button type="button" variant="outline" onClick={toggleArchive}>
            {company.archived_at ? "Restaurer l'entreprise" : "Archiver l'entreprise"}
          </Button>
          <Button type="submit" loading={saving}>Enregistrer</Button>
        </div>
      )}
    </form>
  );
}

export default function CompanyPage() {
  const { companyId } = useParams<{ companyId: string }>();
  const { data: company, error, loading, setData } = useApiResource<Company>(`/companies/${companyId}`);
  const [tab, setTab] = useState<Tab>("fiscal");

  useEffect(() => {
    if (company) rememberOrg(company.organization_id);
  }, [company]);

  if (loading && !company) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  if (!company) return null;

  const tabs: { id: Tab; label: string; visible: boolean }[] = [
    { id: "fiscal", label: "Exercices", visible: true },
    { id: "imports", label: "Importations", visible: true },
    { id: "access", label: "Accès", visible: true },
    { id: "info", label: "Informations", visible: true },
    { id: "audit", label: "Journal d'audit", visible: company.my_permissions.includes("audit.read") },
  ];

  return (
    <>
      <Link href={`/organizations/${company.organization_id}/companies`}
            className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ChevronLeft className="h-4 w-4" /> Entreprises
      </Link>
      <PageHeader
        title={company.name}
        actions={
          <>
            <Button asChild variant="outline" size="sm"><Link href={`/companies/${company.id}/multi-year`}>Analyse pluriannuelle</Link></Button>
            <Button asChild variant="outline" size="sm"><Link href={`/companies/${company.id}/grand-livre`}>Grand livre</Link></Button>
            <Button asChild variant="outline" size="sm"><Link href={`/companies/${company.id}/cartographie`}>Cartographie des risques</Link></Button>
            <Button asChild variant="outline" size="sm"><Link href={`/companies/${company.id}/controle-interne`}>Contrôle interne</Link></Button>
            <Button asChild variant="outline" size="sm"><Link href={`/companies/${company.id}/comptabilite`}>Comptabilité générale</Link></Button>
            <Button asChild variant="outline" size="sm"><Link href={`/companies/${company.id}/assistant`}>Assistant IA</Link></Button>
            <Button asChild variant="outline" size="sm"><Link href={`/companies/${company.id}/rapports`}>Rapports</Link></Button>
            <Button asChild size="sm"><Link href={`/companies/${company.id}/gestion`}><Gauge className="h-4 w-4" /> Contrôle de gestion</Link></Button>
          </>
        }
        description={
          <span className="flex flex-wrap items-center gap-2">
            <Badge tone="blue">{company.framework_name}</Badge>
            <span>{company.currency}</span>
            {company.country_code && <span>· {company.country_code}</span>}
            {company.my_role && <span>· Votre rôle : {COMPANY_ROLE_LABELS[company.my_role]}</span>}
            {company.is_demo && <Badge tone="amber">Démonstration</Badge>}
            {company.archived_at && <Badge>Archivée</Badge>}
          </span>
        }
      />
      <div role="tablist" className="mb-5 flex gap-1 overflow-x-auto border-b">
        {tabs.filter((t) => t.visible).map((t) => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)}
                  className={cn("-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
                    tab === t.id ? "border-primary font-medium text-foreground"
                      : "border-transparent text-muted-foreground hover:text-foreground")}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === "fiscal" && <FiscalYears company={company} />}
      {tab === "imports" && <ImportsTab company={company} />}
      {tab === "access" && <CompanyAccess company={company} />}
      {tab === "info" && <CompanyInfo company={company} onSaved={setData} />}
      {tab === "audit" && <AuditLogTable basePath={`/companies/${company.id}`} />}
    </>
  );
}
