"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Plus } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { BUDGET_STATUS_LABELS, type Budget, type FiscalYear, type BudgetKind } from "@/lib/types";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const STATUS_TONE = { draft: "neutral", submitted: "blue", approved: "green", archived: "neutral" } as const;

export function BudgetsTab({ companyId, fy, canWrite }: {
  companyId: string; fy: FiscalYear; years: FiscalYear[]; canWrite: boolean;
}) {
  const router = useRouter();
  const { data, error, loading } = useApiResource<Budget[]>(`/companies/${companyId}/fiscal-years/${fy.id}/budgets`);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [scenario, setScenario] = useState<"budget" | "forecast">("budget");
  const [kind, setKind] = useState("general");
  const { data: kinds } = useApiResource<BudgetKind[]>(`/companies/${companyId}/budget-kinds`);
  const selectedKind = kinds?.find((k) => k.key === kind);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setFormError(null);
    try {
      const b = await api.post<Budget>(`/companies/${companyId}/fiscal-years/${fy.id}/budgets`, { name, scenario, budget_kind: kind });
      router.push(`/companies/${companyId}/gestion/budgets/${b.id}`);
    } catch (err) {
      setFormError(errorMessage(err));
      setSaving(false);
    }
  }

  if (loading && !data) return <Loading />;
  if (error) return <Alert>{error}</Alert>;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          Un budget suit le circuit brouillon → soumis → approuvé ; il est approuvé par une autre personne que son auteur,
          puis figé. Une prévision part du réalisé d&apos;un exercice et d&apos;hypothèses saisies.
        </p>
        {canWrite && <Button size="sm" onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> Nouveau budget</Button>}
      </div>
      {data && data.length === 0 ? (
        <EmptyState title="Aucun budget pour cet exercice"
                    description="Créez un budget (montants saisis) ou une prévision (réalisé d'un exercice et taux d'évolution)." />
      ) : (
        <Table>
          <THead><tr><TH>Nom</TH><TH>Type</TH><TH>Version</TH><TH>Statut</TH><TH className="text-right">Lignes</TH><TH>Créé le</TH><TH /></tr></THead>
          <TBody>
            {data?.map((b) => (
              <TR key={b.id}>
                <TD className="font-medium">{b.name}</TD>
                <TD>{b.scenario === "forecast" ? "Prévision" : "Budget"}</TD>
                <TD>v{b.version}</TD>
                <TD><Badge tone={STATUS_TONE[b.status]}>{BUDGET_STATUS_LABELS[b.status]}</Badge></TD>
                <TD className="text-right">{b.total_lines}</TD>
                <TD>{formatDate(b.created_at)}</TD>
                <TD className="text-right">
                  <Button asChild variant="outline" size="sm"><Link href={`/companies/${companyId}/gestion/budgets/${b.id}`}>Ouvrir</Link></Button>
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}

      <Dialog open={open} onClose={() => setOpen(false)} title="Nouveau budget" description={`Exercice ${fy.label}`}>
        <form onSubmit={create} className="space-y-4">
          {formError && <Alert>{formError}</Alert>}
          <Field label="Nom" htmlFor="b-name" required>
            <Input id="b-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={200} required autoFocus />
          </Field>
          <Field label="Type" htmlFor="b-scenario">
            <Select id="b-scenario" value={scenario} onChange={(e) => setScenario(e.target.value as "budget" | "forecast")}>
              <option value="budget">Budget</option>
              <option value="forecast">Prévision</option>
            </Select>
          </Field>
          <Field label="Type de budget" htmlFor="b-kind"
                 hint={selectedKind ? `Comptes admis : racines ${selectedKind.allowed_prefixes.join(", ")}${selectedKind.status === "to_validate" ? " (répartition à valider)" : ""}. Le type est figé dès la première ligne.` : undefined}>
            <Select id="b-kind" value={kind} onChange={(e) => setKind(e.target.value)}>
              {(kinds ?? []).map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}
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
