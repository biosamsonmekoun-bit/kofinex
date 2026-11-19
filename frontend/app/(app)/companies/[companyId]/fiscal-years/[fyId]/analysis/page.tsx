"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { AlertTriangle, CheckCircle2, ChevronLeft, CircleSlash, LineChart, Play, XCircle } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { CATEGORY_LABELS, CATEGORY_ORDER, STATEMENT_LABELS, type Analysis, type CheckResult, type Company,
  type FiscalYear, type IndicatorValue, type StatementLine } from "@/lib/types";
import { cn, formatAmount, formatDate, formatIndicator } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading, PageHeader } from "@/components/ui/feedback";
import { KpiCard, KpiGrid } from "@/components/ui/kpi-card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

type Tab = "bilan" | "resultat" | "indicateurs" | "controles";
const STATUS_TEXT: Record<string, string> = {
  missing_input: "Non calculable", division_by_zero: "Non significatif", error: "Erreur",
};

// ------------------------------------------------------------------ états
function StatementTable({ lines, title, withColumns, onTrace }: {
  lines: StatementLine[]; title: string; withColumns: boolean; onTrace: (l: StatementLine) => void;
}) {
  return (
    <Card>
      <CardHeader><CardTitle>{title}</CardTitle></CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-3 py-2 text-left">Réf.</th>
                <th className="px-3 py-2 text-left">Libellé</th>
                {withColumns && <th className="px-3 py-2 text-right">Brut</th>}
                {withColumns && <th className="px-3 py-2 text-right">Amort. / dépréc.</th>}
                <th className="px-3 py-2 text-right">{withColumns ? "Net N" : "N"}</th>
                <th className="px-3 py-2 text-right">N-1</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {lines.map((l) => (
                <tr key={l.code} className={cn(l.kind === "total" && "bg-muted/40 font-semibold",
                  l.kind === "title" && "bg-muted/20 font-medium", l.role && "border-t-2")}>
                  <td className="px-3 py-1.5 font-mono text-xs text-muted-foreground">{l.code}</td>
                  <td className="px-3 py-1.5" style={{ paddingLeft: `${0.75 + l.level * 0.75}rem` }}>
                    {l.kind === "detail" && l.accounts > 0 ? (
                      <button className="text-left hover:underline" onClick={() => onTrace(l)}
                              title="Voir les comptes ayant produit ce montant">{l.label}</button>
                    ) : l.label}
                  </td>
                  {withColumns && <td className="whitespace-nowrap px-3 py-1.5 text-right tabular-nums">{formatAmount(l.gross, { blankZero: true })}</td>}
                  {withColumns && <td className="whitespace-nowrap px-3 py-1.5 text-right tabular-nums">{formatAmount(l.depreciation, { blankZero: true })}</td>}
                  <td className="whitespace-nowrap px-3 py-1.5 text-right tabular-nums">{formatAmount(l.net, { blankZero: true })}</td>
                  <td className="whitespace-nowrap px-3 py-1.5 text-right tabular-nums text-muted-foreground">{formatAmount(l.previous, { blankZero: true })}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function TraceDialog({ companyId, analysisId, line, onClose }: {
  companyId: string; analysisId: string; line: StatementLine | null; onClose: () => void;
}) {
  const { data, loading, error } = useApiResource<{ trace: { items: { account: string; label: string | null;
    column: string; rule: string; prefix: string; sign: number; amount: string }[]; truncated: boolean } }>(
    line ? `/companies/${companyId}/analyses/${analysisId}/lines/${line.code}` : null);
  const RULES: Record<string, string> = { debit_balance: "solde débiteur", credit_balance: "solde créditeur",
    net_debit: "solde net débiteur", net_credit: "solde net créditeur", debit_movements: "mouvements débit",
    credit_movements: "mouvements crédit" };
  const COLS: Record<string, string> = { gross: "brut", depreciation: "amort.", net: "net" };
  return (
    <Dialog open={!!line} onClose={onClose} title={line ? `${line.code} — ${line.label}` : ""}
            description="Comptes de la balance et correspondances du référentiel ayant produit ce montant.">
      {loading && <Loading />}
      {error && <Alert>{error}</Alert>}
      {data && (
        <div className="max-h-[60vh] overflow-auto">
          <Table>
            <THead><tr><TH>Compte</TH><TH>Règle</TH><TH className="text-right">Montant</TH></tr></THead>
            <TBody>
              {data.trace.items.map((t, k) => (
                <TR key={k}>
                  <TD><span className="font-mono">{t.account}</span> <span className="text-xs text-muted-foreground">{t.label}</span></TD>
                  <TD className="text-xs">racine {t.prefix} · {RULES[t.rule] ?? t.rule} · {COLS[t.column] ?? t.column}{t.sign < 0 ? " · signe −" : ""}</TD>
                  <TD className="text-right tabular-nums">{formatAmount(t.amount)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
          {data.trace.truncated && <p className="mt-2 text-xs text-muted-foreground">Liste tronquée aux 400 premiers comptes.</p>}
        </div>
      )}
    </Dialog>
  );
}

// ------------------------------------------------------------------ indicateurs
function variation(cur: string | null, prev: string | null): string | null {
  if (cur === null || prev === null) return null;
  const c = Number(cur), p = Number(prev);
  if (!Number.isFinite(c) || !Number.isFinite(p) || p === 0) return null;
  return `${(((c - p) / Math.abs(p)) * 100).toLocaleString("fr-FR", { maximumFractionDigits: 1, signDisplay: "always" })} %`;
}

function IndicatorRow({ i, onDetail }: { i: IndicatorValue; onDetail: (i: IndicatorValue) => void }) {
  const ok = i.status === "ok";
  const v = ok ? variation(i.value, i.previous_value) : null;
  return (
    <TR className="cursor-pointer" onClick={() => onDetail(i)}>
      <TD>
        <p className="font-medium">{i.name}{i.custom && <Badge tone="blue" className="ml-2">Personnalisé</Badge>}</p>
        <p className="font-mono text-xs text-muted-foreground">{i.code} v{i.version}</p>
      </TD>
      <TD className="whitespace-nowrap text-right tabular-nums font-medium">
        {ok ? formatIndicator(i.value, i.unit) : <span className="text-xs font-normal text-muted-foreground">{STATUS_TEXT[i.status]}</span>}
      </TD>
      <TD className="whitespace-nowrap text-right tabular-nums text-muted-foreground">
        {i.previous_status === "ok" ? formatIndicator(i.previous_value, i.unit) : "—"}
      </TD>
      <TD className="whitespace-nowrap text-right tabular-nums text-muted-foreground">{v ?? ""}</TD>
    </TR>
  );
}

function IndicatorDialog({ i, onClose }: { i: IndicatorValue | null; onClose: () => void }) {
  return (
    <Dialog open={!!i} onClose={onClose} title={i ? `${i.name} (${i.code} v${i.version})` : ""} description={i?.description ?? undefined}>
      {i && (
        <div className="space-y-3 text-sm">
          <div>
            <p className="text-xs font-medium uppercase text-muted-foreground">Formule</p>
            <pre className="mt-1 whitespace-pre-wrap rounded bg-muted p-2 text-xs">{i.expression}</pre>
          </div>
          {i.convention_notes && <Alert kind="info">{i.convention_notes}</Alert>}
          {i.status !== "ok" && <Alert kind="info">{STATUS_TEXT[i.status]} : {i.message}</Alert>}
          <div>
            <p className="text-xs font-medium uppercase text-muted-foreground">Valeurs utilisées</p>
            <ul className="mt-1 divide-y rounded border">
              {Object.entries(i.inputs).map(([k, v]) => (
                <li key={k} className="flex justify-between gap-4 px-3 py-1.5">
                  <span className="font-mono text-xs">{k}</span>
                  <span className="tabular-nums">{v === null ? "absent (compté 0)" : formatAmount(v)}</span>
                </li>
              ))}
              {Object.keys(i.inputs).length === 0 && <li className="px-3 py-1.5 text-muted-foreground">—</li>}
            </ul>
          </div>
          <p className="text-lg font-semibold">Résultat : {i.status === "ok" ? formatIndicator(i.value, i.unit) : "—"}</p>
        </div>
      )}
    </Dialog>
  );
}

function CheckIcon({ c }: { c: CheckResult }) {
  if (c.status === "passed") return <CheckCircle2 className="h-4 w-4 text-success" aria-label="Réussi" />;
  if (c.status === "skipped") return <CircleSlash className="h-4 w-4 text-muted-foreground" aria-label="Non exécuté" />;
  return c.severity === "critical" ? <XCircle className="h-4 w-4 text-destructive" aria-label="Critique" />
    : <AlertTriangle className="h-4 w-4 text-warning" aria-label="Avertissement" />;
}

const CHECK_TITLES: Record<string, string> = {
  BALANCE_SHEET_EQUILIBRIUM: "Équilibre du bilan", NET_INCOME_CONSISTENCY: "Résultat bilan = compte de résultat",
  UNMAPPED_ACCOUNTS: "Comptes non rattachés aux états",
};

// ------------------------------------------------------------------ page
export default function AnalysisPage() {
  const { companyId, fyId } = useParams<{ companyId: string; fyId: string }>();
  const { data: company } = useApiResource<Company>(`/companies/${companyId}`);
  const { data: years } = useApiResource<FiscalYear[]>(`/companies/${companyId}/fiscal-years`);
  const { data: history, reload: reloadHistory } = useApiResource<{ id: string; status: string; completed_at: string | null }[]>(
    `/companies/${companyId}/fiscal-years/${fyId}/analyses`);
  const [analysisId, setAnalysisId] = useState<string | null>(null);
  const { data: analysis, loading, error, setData } = useApiResource<Analysis>(
    analysisId ? `/companies/${companyId}/analyses/${analysisId}` : null);
  const [tab, setTab] = useState<Tab>("bilan");
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [traceLine, setTraceLine] = useState<StatementLine | null>(null);
  const [detail, setDetail] = useState<IndicatorValue | null>(null);
  const fy = years?.find((y) => y.id === fyId);
  const canRun = !!company?.my_permissions.includes("analysis.run");

  useEffect(() => {
    if (!analysisId && history && history.length) setAnalysisId(history[0].id);
  }, [history, analysisId]);

  const grouped = useMemo(() => {
    const g: Record<string, IndicatorValue[]> = {};
    for (const i of analysis?.indicators ?? []) (g[i.category] ??= []).push(i);
    return CATEGORY_ORDER.filter((c) => g[c]).map((c) => [c, g[c]] as const);
  }, [analysis]);

  // indicateurs mis en avant (valeurs déjà calculées par le moteur ; rien n'est recalculé ici)
  const highlights = useMemo(() => {
    const byCode = new Map((analysis?.indicators ?? []).map((i) => [i.code, i]));
    return ["RESULTAT_NET", "CAF_ADDITIVE", "FR", "TN"].map((c) => byCode.get(c)).filter((i): i is IndicatorValue => !!i);
  }, [analysis]);

  async function run() {
    setRunning(true);
    setRunError(null);
    try {
      const a = await api.post<Analysis>(`/companies/${companyId}/fiscal-years/${fyId}/analyses`);
      setData(a);
      setAnalysisId(a.id);
      await reloadHistory();
    } catch (err) {
      setRunError(errorMessage(err));
    } finally {
      setRunning(false);
    }
  }

  const failedChecks = [...(analysis?.controls?.statements ?? []), ...(analysis?.controls?.cross_checks ?? [])]
    .filter((c) => c.status === "failed").length;

  return (
    <>
      <Link href={`/companies/${companyId}`} className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ChevronLeft className="h-4 w-4" /> {company?.name ?? "Entreprise"}
      </Link>
      <PageHeader
        title={`Analyse financière${fy ? ` — exercice ${fy.label}` : ""}`}
        description={analysis?.completed_at
          ? <>Analyse du {formatDate(analysis.completed_at)} · moteur {analysis.engine_version} · montants en {company?.currency}</>
          : "États financiers, soldes intermédiaires, CAF, équilibre financier et ratios."}
        actions={
          <>
            <Button asChild variant="outline" size="sm"><Link href={`/companies/${companyId}/multi-year`}><LineChart className="h-4 w-4" /> Pluriannuel</Link></Button>
            {canRun && <Button size="sm" onClick={run} loading={running}><Play className="h-4 w-4" /> {analysis ? "Relancer l'analyse" : "Lancer l'analyse"}</Button>}
          </>
        }
      />
      {runError && <Alert className="mb-4">{runError}</Alert>}
      {history && history.length > 1 && (
        <div className="mb-4 flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">Analyse affichée :</span>
          <select className="rounded-md border border-input bg-card px-2 py-1 text-foreground" value={analysisId ?? ""} onChange={(e) => setAnalysisId(e.target.value)}>
            {history.map((h) => <option key={h.id} value={h.id}>{h.completed_at ? formatDate(h.completed_at) : "—"} ({h.status === "completed" ? "terminée" : "échec"})</option>)}
          </select>
        </div>
      )}
      {history && history.length === 0 && (
        <EmptyState title="Aucune analyse pour cet exercice"
                    description={canRun ? "Lancez l'analyse : les états financiers sont établis à partir de la balance validée et du référentiel publié, puis les indicateurs sont calculés."
                      : "Aucune analyse n'a encore été lancée pour cet exercice."} />
      )}
      {loading && !analysis && <Loading />}
      {error && <Alert>{error}</Alert>}
      {analysis?.status === "failed" && <Alert>Analyse impossible : {analysis.failure_reason}</Alert>}
      {analysis?.status === "completed" && (
        <>
          {failedChecks > 0 && (
            <Alert className="mb-4">{failedChecks} contrôle(s) de cohérence en échec : consultez l&apos;onglet « Contrôles » avant d&apos;exploiter les résultats.</Alert>
          )}
          {!analysis.summary?.has_previous_year && (
            <Alert kind="info" className="mb-4">Pas de balance validée pour l&apos;exercice précédent : colonnes N-1 et indicateurs de croissance non disponibles.</Alert>
          )}
          {highlights.length > 0 && (
            <KpiGrid className="mb-5">
              {highlights.map((i) => {
                const ok = i.status === "ok";
                const delta = ok ? variation(i.value, i.previous_value) : null;
                const trend = delta ? (delta.startsWith("+") ? "up" : delta.startsWith("-") || delta.startsWith("−") ? "down" : "flat") : null;
                return (
                  <KpiCard key={i.code} label={i.name} onClick={() => setDetail(i)}
                           value={ok ? formatIndicator(i.value, i.unit) : <span className="text-base font-medium text-muted-foreground">{STATUS_TEXT[i.status]}</span>}
                           delta={delta} trend={trend} hint={delta ? "vs N-1" : undefined} />
                );
              })}
            </KpiGrid>
          )}
          <div role="tablist" className="mb-4 flex gap-1 overflow-x-auto border-b">
            {([["bilan", "Bilan"], ["resultat", "Compte de résultat"], ["indicateurs", "Indicateurs"], ["controles", `Contrôles${failedChecks ? ` (${failedChecks})` : ""}`]] as const).map(([id, label]) => (
              <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}
                      className={cn("-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring", tab === id ? "border-primary font-medium" : "border-transparent text-muted-foreground hover:text-foreground")}>
                {label}
              </button>
            ))}
          </div>
          {tab === "bilan" && (
            <div className="grid gap-4 2xl:grid-cols-2">
              {analysis.statements.balance_sheet_assets && <StatementTable lines={analysis.statements.balance_sheet_assets} title={STATEMENT_LABELS.balance_sheet_assets} withColumns onTrace={setTraceLine} />}
              {analysis.statements.balance_sheet_liabilities && <StatementTable lines={analysis.statements.balance_sheet_liabilities} title={STATEMENT_LABELS.balance_sheet_liabilities} withColumns={false} onTrace={setTraceLine} />}
            </div>
          )}
          {tab === "resultat" && analysis.statements.income_statement && (
            <StatementTable lines={analysis.statements.income_statement} title={STATEMENT_LABELS.income_statement} withColumns={false} onTrace={setTraceLine} />
          )}
          {tab === "indicateurs" && (
            <div className="space-y-4">
              {(analysis.summary?.concepts_missing?.length ?? 0) > 0 && (
                <Alert kind="info">
                  {analysis.summary!.concepts_missing.length} concept(s) d&apos;analyse ne sont pas encore liés au référentiel :
                  les indicateurs qui en dépendent sont indiqués « non calculables » plutôt qu&apos;estimés.
                </Alert>
              )}
              {grouped.map(([cat, list]) => (
                <Card key={cat}>
                  <CardHeader><CardTitle>{CATEGORY_LABELS[cat] ?? cat}</CardTitle></CardHeader>
                  <CardContent className="p-0">
                    <Table>
                      <THead><tr><TH>Indicateur</TH><TH className="text-right">N</TH><TH className="text-right">N-1</TH><TH className="text-right">Variation</TH></tr></THead>
                      <TBody>{list.map((i) => <IndicatorRow key={i.code} i={i} onDetail={setDetail} />)}</TBody>
                    </Table>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
          {tab === "controles" && (
            <ul className="divide-y rounded-lg border bg-card">
              {[...(analysis.controls?.statements ?? []), ...(analysis.controls?.cross_checks ?? [])].map((c) => (
                <li key={c.code} className="flex gap-3 px-4 py-3">
                  <CheckIcon c={c} />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">{c.title ?? CHECK_TITLES[c.code] ?? c.code}</p>
                    <p className="text-sm text-muted-foreground">{c.message}</p>
                    {c.status === "failed" && c.details && Object.keys(c.details).length > 0 && (
                      <details className="mt-1">
                        <summary className="cursor-pointer text-xs text-link">Détail</summary>
                        <pre className="mt-1 max-h-64 overflow-auto rounded bg-muted p-2 text-xs">{JSON.stringify(c.details, null, 2)}</pre>
                      </details>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-4 text-xs text-muted-foreground">
            Base N-1 : {analysis.parameters.previous_year_basis}. Tous les montants et ratios sont calculés en arithmétique décimale par le moteur ; cliquez sur un indicateur pour voir sa formule et les valeurs utilisées.
          </p>
          <TraceDialog companyId={companyId} analysisId={analysis.id} line={traceLine} onClose={() => setTraceLine(null)} />
          <IndicatorDialog i={detail} onClose={() => setDetail(null)} />
        </>
      )}
    </>
  );
}
