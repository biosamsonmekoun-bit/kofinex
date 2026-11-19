"use client";

import { useState } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import type { Engagement, EngagementRisk, MethodologyItem, RiskScale } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

type Form = { code: string; title: string; description: string; cycle_code: string; assertion_codes: string[];
              likelihood: string; impact: string; is_significant: boolean; planned_response: string };
const EMPTY: Form = { code: "", title: "", description: "", cycle_code: "", assertion_codes: [], likelihood: "", impact: "",
                      is_significant: false, planned_response: "" };

export function RisksTab({ e }: { e: Engagement }) {
  const { data, error, loading, reload } = useApiResource<{ risks: EngagementRisk[]; scale: RiskScale | null }>(`/engagements/${e.id}/risks`);
  const { data: items } = useApiResource<MethodologyItem[]>(`/engagements/${e.id}/methodology-items`);
  const [editing, setEditing] = useState<EngagementRisk | "new" | null>(null);
  const [f, setF] = useState<Form>(EMPTY);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const canPlan = (e.capabilities ?? []).includes("plan");
  const assertions = (items ?? []).filter((i) => i.item_type === "assertion");
  const cycles = (items ?? []).filter((i) => i.item_type === "cycle");
  const scale = data?.scale ?? null;

  function open(r: EngagementRisk | "new") {
    setErr(null);
    setEditing(r);
    setF(r === "new" ? EMPTY : { code: r.code, title: r.title, description: r.description ?? "", cycle_code: r.cycle_code ?? "",
      assertion_codes: r.assertion_codes, likelihood: r.likelihood ? String(r.likelihood) : "", impact: r.impact ? String(r.impact) : "",
      is_significant: r.is_significant, planned_response: r.planned_response ?? "" });
  }

  async function save(ev: React.FormEvent) {
    ev.preventDefault();
    setBusy(true);
    setErr(null);
    const body = { ...f, description: f.description || null, cycle_code: f.cycle_code || null, planned_response: f.planned_response || null,
                   likelihood: f.likelihood ? Number(f.likelihood) : null, impact: f.impact ? Number(f.impact) : null };
    try {
      if (editing === "new") await api.post(`/engagements/${e.id}/risks`, body);
      else await api.patch(`/engagements/${e.id}/risks/${(editing as EngagementRisk).id}`, body);
      setEditing(null);
      await reload();
    } catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }

  async function remove(r: EngagementRisk) {
    try { await api.del(`/engagements/${e.id}/risks/${r.id}`); await reload(); } catch (x) { setErr(errorMessage(x)); }
  }

  if (loading && !data) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  return (
    <div className="space-y-4">
      {err && !editing && <Alert>{err}</Alert>}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          {scale ? <>Cotation = probabilité × impact selon la grille de la méthodologie{scale.significant_from ? ` (significatif à partir de ${scale.significant_from})` : ""}. Le jugement « significatif » reste le vôtre.</>
            : "Aucune grille de cotation : choisissez une méthodologie pour la mission afin de coter les risques."}
        </p>
        {canPlan && <Button size="sm" onClick={() => open("new")}><Plus className="h-4 w-4" /> Risque</Button>}
      </div>
      {data && data.risks.length === 0 ? <EmptyState title="Aucun risque identifié" description="Identifiez les risques de la mission puis rattachez-y des procédures du programme." /> : (
        <Table>
          <THead><tr><TH>Code</TH><TH>Risque</TH><TH>Assertions</TH><TH className="text-right">Cotation</TH><TH>Significatif</TH><TH className="text-right">Procédures</TH><TH /></tr></THead>
          <TBody>
            {data?.risks.map((r) => (
              <TR key={r.id}>
                <TD className="font-medium">{r.code}{r.origin === "ai_suggestion" && <Badge tone="gold" className="ml-1">Suggestion IA</Badge>}</TD>
                <TD>{r.title}{r.planned_response && <p className="text-xs text-muted-foreground">Réponse : {r.planned_response}</p>}</TD>
                <TD>{r.assertion_codes.join(", ")}</TD>
                <TD className="text-right">{r.score ?? "—"}{r.likelihood && <span className="text-xs text-muted-foreground"> ({r.likelihood}×{r.impact})</span>}</TD>
                <TD>{r.is_significant ? <Badge tone="red">Oui</Badge> : r.scale_significant ? <Badge tone="amber">Au-dessus du seuil</Badge> : "Non"}</TD>
                <TD className="text-right">{r.procedures === 0 ? <Badge tone="amber">0</Badge> : r.procedures}</TD>
                <TD className="whitespace-nowrap text-right">
                  {canPlan && <>
                    <Button variant="ghost" size="icon" aria-label={`Modifier ${r.code}`} onClick={() => open(r)}><Pencil className="h-4 w-4" /></Button>
                    <Button variant="ghost" size="icon" aria-label={`Supprimer ${r.code}`} onClick={() => remove(r)}><Trash2 className="h-4 w-4" /></Button>
                  </>}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
      <Dialog open={editing !== null} onClose={() => setEditing(null)} title={editing === "new" ? "Nouveau risque" : "Modifier le risque"}>
        <form onSubmit={save} className="space-y-3">
          {err && <Alert>{err}</Alert>}
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Code" htmlFor="r-code" required><Input id="r-code" value={f.code} onChange={(x) => setF({ ...f, code: x.target.value })} required /></Field>
            <div className="sm:col-span-2"><Field label="Intitulé" htmlFor="r-title" required><Input id="r-title" value={f.title} onChange={(x) => setF({ ...f, title: x.target.value })} required /></Field></div>
          </div>
          <Field label="Description" htmlFor="r-desc"><Input id="r-desc" value={f.description} onChange={(x) => setF({ ...f, description: x.target.value })} /></Field>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Cycle" htmlFor="r-cycle">
              <Select id="r-cycle" value={f.cycle_code} onChange={(x) => setF({ ...f, cycle_code: x.target.value })}>
                <option value="">—</option>{cycles.map((c) => <option key={c.code} value={c.code}>{c.code} — {c.label}</option>)}
              </Select>
            </Field>
            <Field label="Probabilité" htmlFor="r-lik">
              <Select id="r-lik" value={f.likelihood} onChange={(x) => setF({ ...f, likelihood: x.target.value })} disabled={!scale}>
                <option value="">—</option>{scale?.likelihood.map((l) => <option key={l.score} value={l.score}>{l.score} — {l.label}</option>)}
              </Select>
            </Field>
            <Field label="Impact" htmlFor="r-imp">
              <Select id="r-imp" value={f.impact} onChange={(x) => setF({ ...f, impact: x.target.value })} disabled={!scale}>
                <option value="">—</option>{scale?.impact.map((l) => <option key={l.score} value={l.score}>{l.score} — {l.label}</option>)}
              </Select>
            </Field>
          </div>
          {assertions.length > 0 && (
            <fieldset>
              <legend className="mb-1 text-sm font-medium">Assertions</legend>
              <div className="flex flex-wrap gap-3">
                {assertions.map((a) => (
                  <label key={a.code} className="flex items-center gap-1.5 text-sm">
                    <input type="checkbox" checked={f.assertion_codes.includes(a.code)} className="h-4 w-4"
                           onChange={(x) => setF({ ...f, assertion_codes: x.target.checked ? [...f.assertion_codes, a.code] : f.assertion_codes.filter((c) => c !== a.code) })} />
                    {a.label}
                  </label>
                ))}
              </div>
            </fieldset>
          )}
          <Field label="Réponse prévue" htmlFor="r-resp"><Input id="r-resp" value={f.planned_response} onChange={(x) => setF({ ...f, planned_response: x.target.value })} /></Field>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="h-4 w-4" checked={f.is_significant} onChange={(x) => setF({ ...f, is_significant: x.target.checked })} /> Risque jugé significatif</label>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setEditing(null)}>Annuler</Button>
            <Button type="submit" loading={busy}>Enregistrer</Button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}
