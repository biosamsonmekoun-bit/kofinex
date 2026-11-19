"use client";

import { useMemo, useState } from "react";
import { Plus } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { CATEGORY_LABELS, CATEGORY_ORDER, type FormulaDef, type Organization } from "@/lib/types";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, Loading, PageHeader } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";

const UNITS: Record<string, string> = { amount: "Montant", ratio: "Ratio", percent: "Pourcentage", days: "Jours",
  times: "Nombre de fois", years: "Années" };

interface Concept { code: string; label: string; definition: string }

function NewFormulaForm({ orgId, onCreated }: { orgId: string; onCreated: () => void }) {
  const { data: concepts } = useApiResource<Concept[]>("/financial-concepts");
  const [form, setForm] = useState({ code: "", name: "", category: "custom", expression: "", unit: "ratio",
    rounding_scale: 2, description: "", convention_notes: "" });
  const [check, setCheck] = useState<{ ok: boolean; text: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function verify() {
    setCheck(null);
    try {
      const r = await api.post<{ normalized: string; references: string[]; warning: string | null }>(
        `/financial-formulas/check?organization_id=${orgId}`, { expression: form.expression });
      setCheck({ ok: true, text: `Formule valide. Références : ${r.references.join(", ") || "aucune"}.${r.warning ? ` ${r.warning}` : ""}` });
    } catch (err) {
      setCheck({ ok: false, text: errorMessage(err) });
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await api.post(`/organizations/${orgId}/financial-formulas`, {
        ...form, code: form.code.trim().toUpperCase(), name: form.name.trim(), rounding_scale: Number(form.rounding_scale),
        convention_notes: form.convention_notes.trim() || null,
      });
      onCreated();
    } catch (err) {
      setError(errorMessage(err));
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      {error && <Alert>{error}</Alert>}
      <div className="grid grid-cols-2 gap-3">
        <Field label="Code" htmlFor="f-code" required hint="Majuscules, chiffres, _. Un code existant crée une nouvelle version.">
          <Input id="f-code" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} />
        </Field>
        <Field label="Nom" htmlFor="f-name" required>
          <Input id="f-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </Field>
        <Field label="Catégorie" htmlFor="f-cat">
          <Select id="f-cat" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
            {CATEGORY_ORDER.map((c) => <option key={c} value={c}>{CATEGORY_LABELS[c]}</option>)}
          </Select>
        </Field>
        <Field label="Unité" htmlFor="f-unit">
          <Select id="f-unit" value={form.unit} onChange={(e) => setForm({ ...form, unit: e.target.value })}>
            {Object.entries(UNITS).map(([u, l]) => <option key={u} value={u}>{l}</option>)}
          </Select>
        </Field>
      </div>
      <Field label="Expression" htmlFor="f-expr" required
             hint='Ex. : ind("TN") / ind("CA") * 100 · concept("capitaux_propres") · prev_ind("CA") · days() · abs(), min(), max(), avg()'>
        <textarea id="f-expr" rows={3} value={form.expression} onChange={(e) => { setForm({ ...form, expression: e.target.value }); setCheck(null); }}
                  className="w-full rounded-md border border-input bg-card px-3 py-2 font-mono text-sm" />
      </Field>
      <div className="flex items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={verify} disabled={!form.expression.trim()}>Vérifier l&apos;expression</Button>
        {concepts && (
          <details className="text-xs">
            <summary className="cursor-pointer text-link">Concepts disponibles</summary>
            <ul className="mt-1 max-h-40 overflow-auto">{concepts.map((c) => <li key={c.code}><code>{c.code}</code> — {c.label}</li>)}</ul>
          </details>
        )}
      </div>
      {check && <Alert kind={check.ok ? "success" : "error"}>{check.text}</Alert>}
      <Field label="Description" htmlFor="f-desc" required>
        <Input id="f-desc" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
      </Field>
      <Field label="Conventions de calcul" htmlFor="f-conv" hint="Base retenue, durée de référence, limites d'interprétation…">
        <textarea id="f-conv" rows={2} value={form.convention_notes} onChange={(e) => setForm({ ...form, convention_notes: e.target.value })}
                  className="w-full rounded-md border border-input bg-card px-3 py-2 text-sm" />
      </Field>
      <div className="flex justify-end">
        <Button type="submit" loading={saving} disabled={!form.code || !form.name || !form.expression || form.description.length < 5}>
          Publier la formule
        </Button>
      </div>
    </form>
  );
}

export default function FormulasPage() {
  const { data: orgs } = useApiResource<Organization[]>("/organizations");
  const managed = (orgs ?? []).filter((o) => o.my_role === "owner" || o.my_role === "admin");
  const [orgId, setOrgId] = useState<string>("");
  const effectiveOrg = orgId || managed[0]?.id || orgs?.[0]?.id || "";
  const { data: formulas, error, loading, reload } = useApiResource<FormulaDef[]>(
    effectiveOrg ? `/financial-formulas?organization_id=${effectiveOrg}` : "/financial-formulas");
  const [open, setOpen] = useState(false);
  const canCreate = managed.some((o) => o.id === effectiveOrg);

  const grouped = useMemo(() => {
    const g: Record<string, FormulaDef[]> = {};
    for (const f of formulas ?? []) (g[f.category] ??= []).push(f);
    return CATEGORY_ORDER.filter((c) => g[c]).map((c) => [c, g[c]] as const);
  }, [formulas]);

  return (
    <>
      <PageHeader
        title="Bibliothèque de formules"
        description="Indicateurs calculés par le moteur : formules versionnées et figées une fois publiées, sur des concepts d'analyse liés à chaque référentiel."
        actions={
          <>
            {(orgs?.length ?? 0) > 1 && (
              <Select aria-label="Organisation" className="h-9 w-56" value={effectiveOrg} onChange={(e) => setOrgId(e.target.value)}>
                {orgs!.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
              </Select>
            )}
            {canCreate && <Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> Formule personnalisée</Button>}
          </>
        }
      />
      {loading && !formulas && <Loading />}
      {error && <Alert>{error}</Alert>}
      <div className="space-y-4">
        {grouped.map(([cat, list]) => (
          <Card key={cat}>
            <CardHeader><CardTitle>{CATEGORY_LABELS[cat] ?? cat}</CardTitle></CardHeader>
            <CardContent className="divide-y p-0">
              {list.map((f) => (
                <div key={f.id} className="px-5 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{f.name}</span>
                    <span className="font-mono text-xs text-muted-foreground">{f.code} v{f.version}</span>
                    <Badge>{UNITS[f.unit] ?? f.unit}</Badge>
                    {f.custom ? <Badge tone="blue">Organisation</Badge> : <Badge>{f.library_version}</Badge>}
                    {f.published_at && <span className="text-xs text-muted-foreground">publiée le {formatDate(f.published_at)}</span>}
                  </div>
                  {f.description && <p className="mt-1 text-sm text-muted-foreground">{f.description}</p>}
                  <code className="mt-1 block whitespace-pre-wrap rounded bg-muted px-2 py-1 text-xs">{f.expression}</code>
                  {f.convention_notes && <p className="mt-1 text-xs text-muted-foreground">Convention : {f.convention_notes}</p>}
                </div>
              ))}
            </CardContent>
          </Card>
        ))}
      </div>
      <Dialog open={open} onClose={() => setOpen(false)} title="Formule personnalisée"
              description="Propre à l'organisation ; prime sur la formule standard de même code. Une fois publiée, elle n'est plus modifiable : une correction crée une nouvelle version.">
        <NewFormulaForm orgId={effectiveOrg} onCreated={async () => { setOpen(false); await reload(); }} />
      </Dialog>
    </>
  );
}

