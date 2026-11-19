"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Plus } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { MODEL_TYPE_LABELS, type CostingModel, type FiscalYear, type ModelType } from "@/lib/types";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const DESCRIPTIONS: Record<ModelType, string> = {
  full_cost: "Répartition des charges de la balance entre centres (primaire, secondaire avec prestations réciproques), imputation par unités d'œuvre, coût de revient et marge par produit ou activité.",
  cvp: "Classement des charges en variables et fixes : marge sur coût variable, seuil de rentabilité, point mort, marge et indice de sécurité, levier opérationnel.",
  standard_cost: "Comparaison des coûts réels aux coûts préétablis : écarts sur quantités et sur prix, élément par élément.",
};

export function ModelsTab({ companyId, fy, canWrite }: { companyId: string; fy: FiscalYear; canWrite: boolean; canApprove: boolean }) {
  const router = useRouter();
  const { data, error, loading } = useApiResource<CostingModel[]>(`/companies/${companyId}/fiscal-years/${fy.id}/costing-models`);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [type, setType] = useState<ModelType>("cvp");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setFormError(null);
    try {
      const m = await api.post<CostingModel>(`/companies/${companyId}/fiscal-years/${fy.id}/costing-models`, { name, model_type: type });
      router.push(`/companies/${companyId}/gestion/modeles/${m.id}`);
    } catch (err) {
      setFormError(errorMessage(err));
      setSaving(false);
    }
  }

  if (loading && !data) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-3">
        {(Object.keys(MODEL_TYPE_LABELS) as ModelType[]).map((t) => (
          <div key={t} className="rounded-lg border bg-card p-4 shadow-card">
            <p className="text-sm font-semibold">{MODEL_TYPE_LABELS[t]}</p>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{DESCRIPTIONS[t]}</p>
          </div>
        ))}
      </div>
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">Les clés de répartition, parts variables et standards sont vos paramètres : rien n&apos;est présumé.</p>
        {canWrite && <Button size="sm" onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> Nouveau modèle</Button>}
      </div>
      {data && data.length === 0 ? (
        <EmptyState title="Aucun modèle pour cet exercice" description="Créez un modèle de coûts complets, de seuil de rentabilité ou de coûts préétablis." />
      ) : (
        <Table>
          <THead><tr><TH>Nom</TH><TH>Méthode</TH><TH>Version</TH><TH>Statut</TH><TH>Calculé le</TH><TH /></tr></THead>
          <TBody>
            {data?.map((m) => (
              <TR key={m.id}>
                <TD className="font-medium">{m.name}</TD><TD>{MODEL_TYPE_LABELS[m.model_type]}</TD><TD>v{m.version}</TD>
                <TD>{m.status === "validated" ? <Badge tone="green">Validé</Badge> : <Badge>Brouillon</Badge>}</TD>
                <TD>{m.computed_at ? formatDate(m.computed_at) : "—"}</TD>
                <TD className="text-right"><Button asChild variant="outline" size="sm"><Link href={`/companies/${companyId}/gestion/modeles/${m.id}`}>Ouvrir</Link></Button></TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
      <Dialog open={open} onClose={() => setOpen(false)} title="Nouveau modèle" description={`Exercice ${fy.label}`}>
        <form onSubmit={create} className="space-y-4">
          {formError && <Alert>{formError}</Alert>}
          <Field label="Nom" htmlFor="m-name" required><Input id="m-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={200} required autoFocus /></Field>
          <Field label="Méthode" htmlFor="m-type">
            <Select id="m-type" value={type} onChange={(e) => setType(e.target.value as ModelType)}>
              {(Object.keys(MODEL_TYPE_LABELS) as ModelType[]).map((t) => <option key={t} value={t}>{MODEL_TYPE_LABELS[t]}</option>)}
            </Select>
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>Annuler</Button>
            <Button type="submit" loading={saving} disabled={!name.trim()}>Créer</Button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}
