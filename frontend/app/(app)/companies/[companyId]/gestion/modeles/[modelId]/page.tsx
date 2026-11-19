"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Calculator, CheckCircle2, ChevronLeft, CopyPlus, Save, Trash2 } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { MODEL_TYPE_LABELS, type Company, type CostingModel } from "@/lib/types";
import { formatAmount, formatDate, formatPct } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, Badge, Loading, PageHeader } from "@/components/ui/feedback";
import { Field, Input } from "@/components/ui/form";
import { KpiCard, KpiGrid } from "@/components/ui/kpi-card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import {
  type CvpForm, type FullForm, InputError, RowsEditor, type StdForm, cvpFromParams, cvpToParams, fullFromParams, fullToParams,
  stdFromParams, stdToParams,
} from "./editors";

type R = Record<string, unknown>;
const s = (v: unknown): string | null => (v === null || v === undefined ? null : String(v));
const fmtNum = (v: unknown, d = 2) => (v === null || v === undefined ? "—" : Number(v).toLocaleString("fr-FR", { maximumFractionDigits: d }));

// ------------------------------------------------------------------ résultats
function CvpResults({ r }: { r: R }) {
  return (
    <div className="space-y-4">
      <KpiGrid>
        <KpiCard label="Marge sur coût variable" value={formatAmount(s(r.contribution_margin))} hint={`Taux : ${formatPct(s(r.contribution_rate_pct))}`} />
        <KpiCard label="Seuil de rentabilité" value={r.breakeven === null ? "Non significatif" : formatAmount(s(r.breakeven))} />
        <KpiCard label="Point mort" value={r.breakeven_date ? formatDate(s(r.breakeven_date)) : "Non atteint"} hint={r.breakeven_days ? `${fmtNum(r.breakeven_days, 1)} jours sur ${fmtNum(r.fiscal_year_days, 0)}` : undefined} />
        <KpiCard label="Indice de sécurité" value={formatPct(s(r.safety_index_pct))} hint={`Levier opérationnel : ${fmtNum(r.operating_leverage)}`} />
      </KpiGrid>
      {((r.notes as string[]) ?? []).map((n) => <Alert key={n} kind="warning">{n}</Alert>)}
      {Number(r.unclassified_charges) !== 0 && (
        <Alert kind="warning">Charges de la balance non classées : {formatAmount(s(r.unclassified_charges))}. Elles ne sont pas prises en compte : le résultat du modèle diffère d&apos;autant du résultat comptable.</Alert>
      )}
      <Table>
        <THead><tr><TH>Racine</TH><TH>Libellé</TH><TH className="text-right">Montant</TH><TH className="text-right">Part variable</TH><TH className="text-right">Variable</TH><TH className="text-right">Fixe</TH></tr></THead>
        <TBody>
          {((r.charges as R[]) ?? []).map((c) => (
            <TR key={String(c.prefix)}>
              <TD>{String(c.prefix)}</TD><TD>{s(c.label) ?? ""}</TD><TD className="text-right">{formatAmount(s(c.amount))}</TD>
              <TD className="text-right">{formatPct(s(c.variable_pct), 0)}</TD><TD className="text-right">{formatAmount(s(c.variable))}</TD><TD className="text-right">{formatAmount(s(c.fixed))}</TD>
            </TR>
          ))}
        </TBody>
        <tfoot className="border-t-2 bg-muted/40 font-semibold">
          <tr><td className="px-4 py-2" colSpan={4}>Chiffre d&apos;affaires {formatAmount(s(r.revenue))} — résultat du modèle</td>
              <td className="px-4 py-2 text-right" colSpan={2}>{formatAmount(s(r.result))}</td></tr>
        </tfoot>
      </Table>
    </div>
  );
}

function StdResults({ r }: { r: R }) {
  const t = (r.totals as R) ?? {};
  return (
    <div className="space-y-4">
      <KpiGrid>
        <KpiCard label="Coût préétabli de la production réelle" value={formatAmount(s(t.standard_cost))} />
        <KpiCard label="Coût réel" value={formatAmount(s(t.actual_cost))} />
        <KpiCard label="Écart sur quantités" value={formatAmount(s(t.quantity))} hint="Positif = défavorable" />
        <KpiCard label="Écart sur prix" value={formatAmount(s(t.price))} hint="Positif = défavorable" />
      </KpiGrid>
      <Table>
        <THead><tr><TH>Élément</TH><TH className="text-right">Qté préétablie</TH><TH className="text-right">Qté réelle</TH><TH className="text-right">Coût préétabli</TH><TH className="text-right">Coût réel</TH><TH className="text-right">É/quantité</TH><TH className="text-right">É/prix</TH><TH className="text-right">Écart global</TH></tr></THead>
        <TBody>
          {((r.elements as R[]) ?? []).map((e) => (
            <TR key={String(e.label)}>
              <TD>{String(e.label)} <span className="text-xs text-muted-foreground">{s(e.unit) ?? ""}</span></TD>
              <TD className="text-right">{fmtNum(e.standard_quantity, 4)}</TD><TD className="text-right">{fmtNum(e.actual_quantity, 4)}</TD>
              <TD className="text-right">{formatAmount(s(e.standard_cost))}</TD><TD className="text-right">{formatAmount(s(e.actual_cost))}</TD>
              <TD className="text-right">{formatAmount(s(e.quantity_variance))}</TD><TD className="text-right">{formatAmount(s(e.price_variance))}</TD>
              <TD className={Number(e.total_variance) > 0 ? "text-right font-medium text-destructive-strong" : "text-right font-medium text-success-strong"}>{formatAmount(s(e.total_variance))}</TD>
            </TR>
          ))}
        </TBody>
      </Table>
    </div>
  );
}

function FullResults({ r }: { r: R }) {
  const diffs = (r.imputation_differences as R) ?? {};
  return (
    <div className="space-y-4">
      <KpiGrid>
        <KpiCard label="Charges incorporées" value={formatAmount(s(r.total_incorporated))} hint={`dont supplétives ${formatAmount(s(r.supplementary))}`} />
        <KpiCard label="Charges non incorporées" value={formatAmount(s(r.non_incorporated))} hint="Charges de la balance non reprises" />
        <KpiCard label="Différences d'imputation" value={formatAmount(s(r.imputation_differences_total))} hint="Coût de la sous-activité (si positif)" />
        <KpiCard label="Résultat analytique" value={r.analytical_result === null ? "—" : formatAmount(s(r.analytical_result))} />
      </KpiGrid>
      {r.check_passed
        ? <Alert kind="success">Contrôle : charges incorporées = coûts imputés aux objets + différences d&apos;imputation.</Alert>
        : <Alert>Contrôle en échec : écart de {String(r.check_difference)}.</Alert>}
      <Card>
        <CardHeader><CardTitle>Centres d&apos;analyse</CardTitle></CardHeader>
        <CardContent className="p-0">
          <Table>
            <THead><tr><TH>Centre</TH><TH>Type</TH><TH className="text-right">Répartition primaire</TH><TH className="text-right">Total après secondaire</TH><TH className="text-right">Unités d&apos;œuvre</TH><TH className="text-right">Coût de l&apos;UO</TH><TH className="text-right">Différence d&apos;imputation</TH></tr></THead>
            <TBody>
              {((r.centers as R[]) ?? []).map((c) => (
                <TR key={String(c.code)}>
                  <TD><span className="font-medium">{String(c.code)}</span> <span className="text-muted-foreground">{String(c.name)}</span></TD>
                  <TD>{c.kind === "auxiliary" ? "Auxiliaire" : "Principal"}</TD>
                  <TD className="text-right">{formatAmount(s(c.primary))}</TD><TD className="text-right">{formatAmount(s(c.total))}</TD>
                  <TD className="text-right">{c.volume ? `${fmtNum(c.volume)} ${s(c.unit) ?? ""}` : "—"}</TD>
                  <TD className="text-right">{c.cost_per_unit ? fmtNum(c.cost_per_unit, 4) : "—"}</TD>
                  <TD className="text-right">{c.kind === "auxiliary" ? "" : formatAmount(s(diffs[String(c.code)]))}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Coûts de revient et marges</CardTitle>
          <CardDescription>Coût des unités vendues = coût unitaire de l&apos;exercice × quantité vendue ; la production non vendue est valorisée à part.</CardDescription></CardHeader>
        <CardContent className="p-0">
          <Table>
            <THead><tr><TH>Objet</TH><TH className="text-right">Directs</TH><TH className="text-right">Indirects</TH><TH className="text-right">Coût de revient</TH><TH className="text-right">Coût unitaire</TH><TH className="text-right">Coût des ventes</TH><TH className="text-right">CA</TH><TH className="text-right">Marge</TH></tr></THead>
            <TBody>
              {((r.objects as R[]) ?? []).map((o) => (
                <TR key={String(o.code)}>
                  <TD><span className="font-medium">{String(o.code)}</span> <span className="text-muted-foreground">{String(o.name)}</span></TD>
                  <TD className="text-right">{formatAmount(s(o.direct))}</TD><TD className="text-right">{formatAmount(s(o.indirect))}</TD>
                  <TD className="text-right font-medium">{formatAmount(s(o.cost))}</TD><TD className="text-right">{fmtNum(o.unit_cost, 4)}</TD>
                  <TD className="text-right">{formatAmount(s(o.cost_of_sales))}</TD><TD className="text-right">{o.revenue === null ? "—" : formatAmount(s(o.revenue))}</TD>
                  <TD className={Number(o.margin) < 0 ? "text-right font-medium text-destructive-strong" : "text-right font-medium"}>{o.margin === null ? "—" : formatAmount(s(o.margin))}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ page
export default function ModelPage() {
  const { companyId, modelId } = useParams<{ companyId: string; modelId: string }>();
  const router = useRouter();
  const base = `/companies/${companyId}`;
  const { data: company } = useApiResource<Company>(base);
  const { data: model, error, loading, setData } = useApiResource<CostingModel>(`${base}/costing-models/${modelId}`);
  const [form, setForm] = useState<CvpForm | StdForm | FullForm | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ kind: "error" | "success"; text: string } | null>(null);

  if (loading && !model) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  if (!model || !company) return <Loading />;

  const params = (model.parameters ?? {}) as R;
  const f = form ?? (model.model_type === "cvp" ? cvpFromParams(params) : model.model_type === "standard_cost" ? stdFromParams(params) : fullFromParams(params));
  const canWrite = company.my_permissions.includes("budget.write");
  const canApprove = company.my_permissions.includes("budget.approve");
  const readOnly = model.status !== "draft" || !canWrite;

  function toParams() {
    if (model!.model_type === "cvp") return cvpToParams(f as CvpForm);
    if (model!.model_type === "standard_cost") return stdToParams(f as StdForm);
    return fullToParams(f as FullForm);
  }

  async function run(action: "save" | "compute" | "validate" | "new-version" | "delete") {
    setBusy(action);
    setMsg(null);
    try {
      if (action === "delete") { await api.del(`${base}/costing-models/${model!.id}`); router.replace(`${base}/gestion?tab=models&fy=${model!.fiscal_year_id}`); return; }
      if (action === "new-version") { const m = await api.post<CostingModel>(`${base}/costing-models/${model!.id}/new-version`); router.push(`${base}/gestion/modeles/${m.id}`); return; }
      if (action === "save" || (action === "compute" && form)) {
        const saved = await api.put<CostingModel>(`${base}/costing-models/${model!.id}/parameters`, toParams());
        setData(saved);
        setForm(null);
      }
      if (action === "compute") setData(await api.post<CostingModel>(`${base}/costing-models/${model!.id}/compute`));
      if (action === "validate") setData(await api.post<CostingModel>(`${base}/costing-models/${model!.id}/validate`));
      setMsg({ kind: "success", text: action === "save" ? "Paramètres enregistrés." : action === "compute" ? "Calcul effectué." : "Modèle validé et figé." });
    } catch (e) {
      setMsg({ kind: "error", text: e instanceof InputError ? e.message : errorMessage(e) });
    } finally {
      setBusy(null);
    }
  }

  const upd = (patch: Partial<CvpForm & StdForm & FullForm>) => setForm({ ...(f as object), ...patch } as CvpForm | StdForm | FullForm);
  const r = model.results as R | null | undefined;

  return (
    <>
      <Link href={`${base}/gestion?tab=models&fy=${model.fiscal_year_id}`} className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ChevronLeft className="h-4 w-4" /> Contrôle de gestion
      </Link>
      <PageHeader
        title={`${model.name} — v${model.version}`}
        description={<span className="flex flex-wrap items-center gap-2">{model.status === "validated" ? <Badge tone="green">Validé le {formatDate(model.validated_at)}</Badge> : <Badge>Brouillon</Badge>}<span>{MODEL_TYPE_LABELS[model.model_type]}</span></span>}
        actions={
          <>
            {!readOnly && <Button size="sm" variant="outline" onClick={() => run("save")} loading={busy === "save"} disabled={!form}><Save className="h-4 w-4" /> Enregistrer</Button>}
            {!readOnly && <Button size="sm" onClick={() => run("compute")} loading={busy === "compute"}><Calculator className="h-4 w-4" /> Calculer</Button>}
            {model.status === "draft" && canApprove && <Button size="sm" variant="outline" onClick={() => run("validate")} loading={busy === "validate"} disabled={!model.results_current || !!form}><CheckCircle2 className="h-4 w-4" /> Valider</Button>}
            {canWrite && <Button size="sm" variant="outline" onClick={() => run("new-version")} loading={busy === "new-version"}><CopyPlus className="h-4 w-4" /> Nouvelle version</Button>}
            {!readOnly && <Button size="sm" variant="destructive" onClick={() => run("delete")} loading={busy === "delete"}><Trash2 className="h-4 w-4" /> Supprimer</Button>}
          </>
        }
      />
      {msg && <Alert kind={msg.kind} className="mb-4">{msg.text}</Alert>}
      {form && <Alert kind="info" className="mb-4">Modifications non enregistrées : « Calculer » les enregistre avant le calcul.</Alert>}
      {r && !model.results_current && !form && (
        <Alert kind="warning" className="mb-4">Résultats périmés : paramètres ou balance modifiés depuis le dernier calcul.</Alert>
      )}

      <div className="grid gap-5 2xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="space-y-4">
          {model.model_type === "cvp" && (
            <>
              <Card>
                <CardHeader><CardTitle>Chiffre d&apos;affaires</CardTitle><CardDescription>Racines de comptes de produits, séparées par des virgules (montants tirés de la balance validée).</CardDescription></CardHeader>
                <CardContent><Input aria-label="Racines du chiffre d'affaires" value={(f as CvpForm).revenue} disabled={readOnly} onChange={(e) => upd({ revenue: e.target.value })} placeholder="70" /></CardContent>
              </Card>
              <RowsEditor title="Classement des charges" description="Pour chaque racine de charges, la part variable en % (0 = entièrement fixe). Une racine non classée est signalée."
                          readOnly={readOnly} rows={(f as CvpForm).charges} onChange={(rows) => upd({ charges: rows })}
                          cols={[{ key: "prefix", label: "Racine", width: "w-24" }, { key: "label", label: "Libellé" }, { key: "variable_pct", label: "Part variable %", width: "w-28", align: "right" }]} />
            </>
          )}
          {model.model_type === "standard_cost" && (
            <>
              <Card>
                <CardHeader><CardTitle>Production</CardTitle></CardHeader>
                <CardContent className="grid gap-3 sm:grid-cols-2">
                  <Field label="Production réelle (unités)" htmlFor="std-out" required><Input id="std-out" value={(f as StdForm).actual_output} disabled={readOnly} onChange={(e) => upd({ actual_output: e.target.value })} /></Field>
                  <Field label="Production prévue (information)" htmlFor="std-bud"><Input id="std-bud" value={(f as StdForm).budgeted_output} disabled={readOnly} onChange={(e) => upd({ budgeted_output: e.target.value })} /></Field>
                </CardContent>
              </Card>
              <RowsEditor title="Éléments de coût" description="Standards par unité produite et réalisations de la période."
                          readOnly={readOnly} rows={(f as StdForm).elements} onChange={(rows) => upd({ elements: rows })}
                          cols={[{ key: "label", label: "Élément" }, { key: "unit", label: "Unité", width: "w-20" },
                                 { key: "standard_quantity_per_unit", label: "Qté std / unité", width: "w-24", align: "right" },
                                 { key: "standard_unit_cost", label: "Coût std", width: "w-24", align: "right" },
                                 { key: "actual_quantity", label: "Qté réelle", width: "w-24", align: "right" },
                                 { key: "actual_unit_cost", label: "Coût réel", width: "w-24", align: "right" }]} />
            </>
          )}
          {model.model_type === "full_cost" && (
            <>
              <Alert kind="info">Clés : <span className="font-mono">CODE=pourcentage</span> séparées par « ; » (ex. <span className="font-mono">A1=40 ; M1=60</span>), totalisant 100 %. Les codes désignent un centre ou un objet de coût.</Alert>
              <RowsEditor title="1. Centres d'analyse" readOnly={readOnly} rows={(f as FullForm).centers} onChange={(rows) => upd({ centers: rows })}
                          description="Centres principaux : imputation par unités d'œuvre (volume total) ou par clés vers les objets."
                          cols={[{ key: "code", label: "Code", width: "w-20" }, { key: "name", label: "Nom" },
                                 { key: "kind", label: "Type", options: [["main", "Principal"], ["auxiliary", "Auxiliaire"]], width: "w-32" },
                                 { key: "alloc", label: "Imputation", options: [["work_unit", "Unités d'œuvre"], ["keys", "Clés"]], width: "w-36" },
                                 { key: "unit", label: "Unité d'œuvre", width: "w-32" }, { key: "volume", label: "Volume", width: "w-24", align: "right" },
                                 { key: "keys", label: "Clés (si imputation par clés)" }]} />
              <RowsEditor title="2. Objets de coût" readOnly={readOnly} rows={(f as FullForm).objects} onChange={(rows) => upd({ objects: rows })}
                          description="Produits, services ou activités. Chiffre d'affaires saisi, ou racine de produits de la balance."
                          cols={[{ key: "code", label: "Code", width: "w-20" }, { key: "name", label: "Nom" },
                                 { key: "quantity", label: "Qté produite", width: "w-24", align: "right" }, { key: "sold_quantity", label: "Qté vendue", width: "w-24", align: "right" },
                                 { key: "revenue", label: "CA saisi", width: "w-32", align: "right" }, { key: "revenue_prefix", label: "ou racine CA", width: "w-24" }]} />
              <RowsEditor title="3. Charges incorporées (balance)" readOnly={readOnly} rows={(f as FullForm).charges} onChange={(rows) => upd({ charges: rows })}
                          description="Racines de charges de la balance, réparties vers des centres (répartition primaire) ou directement vers des objets (charges directes). Les charges non citées sont non incorporées."
                          cols={[{ key: "prefix", label: "Racine", width: "w-24" }, { key: "exclusions", label: "Sauf", width: "w-28" }, { key: "label", label: "Libellé" }, { key: "keys", label: "Clés" }]} />
              <RowsEditor title="4. Charges supplétives" readOnly={readOnly} rows={(f as FullForm).supplementary} onChange={(rows) => upd({ supplementary: rows })}
                          cols={[{ key: "label", label: "Libellé" }, { key: "amount", label: "Montant", width: "w-32", align: "right" }, { key: "keys", label: "Clés" }]} />
              <RowsEditor title="5. Répartition secondaire" readOnly={readOnly} rows={(f as FullForm).secondary} onChange={(rows) => upd({ secondary: rows })}
                          description="Une ligne par centre auxiliaire ; les prestations réciproques sont résolues exactement."
                          cols={[{ key: "from", label: "Centre auxiliaire", width: "w-28" }, { key: "keys", label: "Clés vers les centres" }]} />
              <RowsEditor title="6. Consommations d'unités d'œuvre" readOnly={readOnly} rows={(f as FullForm).usage} onChange={(rows) => upd({ usage: rows })}
                          cols={[{ key: "object", label: "Objet", width: "w-24" }, { key: "center", label: "Centre", width: "w-24" }, { key: "quantity", label: "Unités consommées", width: "w-32", align: "right" }]} />
            </>
          )}
        </div>
        <div>
          {r ? (
            <Card>
              <CardHeader>
                <CardTitle>Résultats</CardTitle>
                <CardDescription>Calculés le {formatDate(model.computed_at)}{model.model_type !== "standard_cost" && " à partir de la balance validée de l'exercice"}.</CardDescription>
              </CardHeader>
              <CardContent>
                {model.model_type === "cvp" && <CvpResults r={r} />}
                {model.model_type === "standard_cost" && <StdResults r={r} />}
                {model.model_type === "full_cost" && <FullResults r={r} />}
              </CardContent>
            </Card>
          ) : (
            <Alert kind="info">Renseignez les paramètres puis lancez le calcul.</Alert>
          )}
        </div>
      </div>
    </>
  );
}
