"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Plus } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import {
  ENGAGEMENT_ROLE_LABELS, ENGAGEMENT_STATUS_LABELS, ENGAGEMENT_STATUS_TONE, ENGAGEMENT_TYPE_LABELS, type Company,
  type Engagement, type EngagementType, type FiscalYear, type Methodology,
} from "@/lib/types";
import { formatDate } from "@/lib/utils";
import { rememberOrg } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading, PageHeader } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

function CreateEngagement({ orgId, onClose }: { orgId: string; onClose: () => void }) {
  const router = useRouter();
  const { data: companies } = useApiResource<Company[]>(`/organizations/${orgId}/companies`);
  const { data: methods } = useApiResource<Methodology[]>(`/methodologies?organization_id=${orgId}`);
  const [f, setF] = useState({ company_id: "", engagement_type: "statutory_audit" as EngagementType, reference: "", name: "",
                               fiscal_year_id: "", methodology_version_id: "", planned_start: "", planned_end: "", objectives: "", scope: "" });
  const { data: years } = useApiResource<FiscalYear[]>(f.company_id ? `/companies/${f.company_id}/fiscal-years` : null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const published = (methods ?? []).filter((m) => m.status === "published");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    const body = Object.fromEntries(Object.entries(f).map(([k, v]) => [k, typeof v === "string" ? (v.trim() || null) : v]));
    try {
      const created = await api.post<Engagement>(`/organizations/${orgId}/engagements`, body);
      router.push(`/missions/${created.id}`);
    } catch (err) {
      setError(errorMessage(err));
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      {error && <Alert>{error}</Alert>}
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Entité auditée" htmlFor="e-company" required>
          <Select id="e-company" value={f.company_id} onChange={(e) => setF({ ...f, company_id: e.target.value, fiscal_year_id: "" })} required>
            <option value="">Choisir…</option>
            {companies?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
        </Field>
        <Field label="Type de mission" htmlFor="e-type">
          <Select id="e-type" value={f.engagement_type} onChange={(e) => setF({ ...f, engagement_type: e.target.value as EngagementType })}>
            {Object.entries(ENGAGEMENT_TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
        </Field>
        <Field label="Référence" htmlFor="e-ref" required><Input id="e-ref" value={f.reference} maxLength={60} onChange={(e) => setF({ ...f, reference: e.target.value })} required /></Field>
        <Field label="Intitulé" htmlFor="e-name" required><Input id="e-name" value={f.name} maxLength={200} onChange={(e) => setF({ ...f, name: e.target.value })} required /></Field>
        <Field label="Exercice audité" htmlFor="e-fy" hint="Donne accès à la balance de l'exercice (instantanés probants).">
          <Select id="e-fy" value={f.fiscal_year_id} onChange={(e) => setF({ ...f, fiscal_year_id: e.target.value })} disabled={!f.company_id}>
            <option value="">Aucun</option>
            {years?.map((y) => <option key={y.id} value={y.id}>{y.label}</option>)}
          </Select>
        </Field>
        <Field label="Méthodologie" htmlFor="e-meth" hint={published.length ? "Version publiée, figée pour la mission." : "Aucune méthodologie publiée."}>
          <Select id="e-meth" value={f.methodology_version_id} onChange={(e) => setF({ ...f, methodology_version_id: e.target.value })}>
            <option value="">Aucune (à choisir en planification)</option>
            {published.map((m) => <option key={m.id} value={m.id}>{m.name} — {m.version_label}</option>)}
          </Select>
        </Field>
        <Field label="Début prévu" htmlFor="e-ps"><Input id="e-ps" type="date" value={f.planned_start} onChange={(e) => setF({ ...f, planned_start: e.target.value })} /></Field>
        <Field label="Fin prévue" htmlFor="e-pe"><Input id="e-pe" type="date" value={f.planned_end} onChange={(e) => setF({ ...f, planned_end: e.target.value })} /></Field>
      </div>
      <Field label="Objectifs" htmlFor="e-obj"><Input id="e-obj" value={f.objectives} onChange={(e) => setF({ ...f, objectives: e.target.value })} /></Field>
      <p className="text-xs text-muted-foreground">Vous deviendrez manager de la mission ; vous devrez confirmer votre indépendance avant d&apos;accéder au dossier.</p>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onClose}>Annuler</Button>
        <Button type="submit" loading={saving} disabled={!f.company_id || !f.reference.trim() || !f.name.trim()}>Créer la mission</Button>
      </div>
    </form>
  );
}

export default function MissionsPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const { data, error, loading } = useApiResource<Engagement[]>(`/organizations/${orgId}/engagements`);
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState<"mine" | "all">("mine");
  useEffect(() => { rememberOrg(orgId); }, [orgId]);
  const list = useMemo(() => (data ?? []).filter((e) => filter === "all" || e.my_role), [data, filter]);

  return (
    <>
      <PageHeader title="Missions" description="Audit légal ou contractuel, audit interne, évaluation du contrôle interne."
                  actions={<Button size="sm" onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> Nouvelle mission</Button>} />
      {error && <Alert>{error}</Alert>}
      {loading && !data && <Loading />}
      {data && (
        <>
          <div className="mb-3 flex gap-2 text-sm">
            <Button size="sm" variant={filter === "mine" ? "secondary" : "ghost"} onClick={() => setFilter("mine")}>Mes missions</Button>
            <Button size="sm" variant={filter === "all" ? "secondary" : "ghost"} onClick={() => setFilter("all")}>Toutes celles que je peux voir</Button>
          </div>
          {list.length === 0 ? (
            <EmptyState title="Aucune mission" description="Les missions auxquelles vous êtes affecté apparaissent ici. Les administrateurs voient aussi les autres (en-tête et équipe seulement)." />
          ) : (
            <Table>
              <THead><tr><TH>Référence</TH><TH>Mission</TH><TH>Entité</TH><TH>Type</TH><TH>Phase</TH><TH>Mon rôle</TH><TH>Créée le</TH></tr></THead>
              <TBody>
                {list.map((e) => (
                  <TR key={e.id}>
                    <TD className="font-medium"><Link className="text-link hover:underline" href={`/missions/${e.id}`}>{e.reference}</Link></TD>
                    <TD>{e.name}</TD><TD>{e.company_name}</TD><TD>{ENGAGEMENT_TYPE_LABELS[e.engagement_type]}</TD>
                    <TD><Badge tone={ENGAGEMENT_STATUS_TONE[e.status]}>{ENGAGEMENT_STATUS_LABELS[e.status]}</Badge></TD>
                    <TD>{e.my_role ? <>{ENGAGEMENT_ROLE_LABELS[e.my_role]}{!e.independent && !["auditee", "observer"].includes(e.my_role) && <Badge tone="amber" className="ml-2">Indépendance à confirmer</Badge>}</> : <span className="text-muted-foreground">Non affecté</span>}</TD>
                    <TD>{formatDate(e.created_at)}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </>
      )}
      <Dialog open={open} onClose={() => setOpen(false)} title="Nouvelle mission">
        {open && <CreateEngagement orgId={orgId} onClose={() => setOpen(false)} />}
      </Dialog>
    </>
  );
}
