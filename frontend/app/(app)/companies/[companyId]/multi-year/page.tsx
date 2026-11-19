"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ChevronLeft } from "lucide-react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useApiResource } from "@/lib/use-api";
import { CATEGORY_LABELS, CATEGORY_ORDER, type Company } from "@/lib/types";
import { cn, formatIndicator } from "@/lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, EmptyState, Loading, PageHeader } from "@/components/ui/feedback";

interface Point { label: string; value: string | null; status: string; variation: string | null; variation_pct: string | null }
interface Serie { code: string; name: string; category: string; unit: string; cagr_pct: string | null; points: Point[] }
interface SeriesResponse { years: { id: string; label: string; analysis_id: string }[]; series: Serie[] }

const LINE_COLOR = "hsl(var(--chart-1))";   // token de graphique (clair et sombre)

function pct(v: string | null): string {
  if (v === null) return "";
  return `${Number(v).toLocaleString("fr-FR", { maximumFractionDigits: 1, signDisplay: "always" })} %`;
}

function SerieChart({ serie }: { serie: Serie }) {
  const data = serie.points.map((p) => ({ label: p.label, value: p.value === null ? null : Number(p.value), raw: p.value, status: p.status }));
  return (
    <Card>
      <CardHeader>
        <CardTitle>{serie.name}</CardTitle>
        <CardDescription>
          Évolution par exercice{serie.cagr_pct !== null ? ` · croissance annuelle moyenne ${pct(serie.cagr_pct)}` : ""}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-72" role="img" aria-label={`Évolution de ${serie.name} : ${serie.points.map((p) => `${p.label} ${formatIndicator(p.value, serie.unit)}`).join(", ")}`}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 16, right: 24, bottom: 4, left: 8 }}>
              <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="0" vertical={false} />
              <XAxis dataKey="label" tickLine={false} axisLine={{ stroke: "hsl(var(--border))" }}
                     tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 12 }} />
              <YAxis width={96} tickLine={false} axisLine={false} tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 12 }}
                     tickFormatter={(v: number) => serie.unit === "amount"
                       ? v.toLocaleString("fr-FR", { notation: "compact", maximumFractionDigits: 1 })
                       : v.toLocaleString("fr-FR", { maximumFractionDigits: 2 })} />
              <Tooltip
                cursor={{ stroke: "hsl(var(--muted-foreground))", strokeWidth: 1 }}
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const d = payload[0].payload as { label: string; raw: string | null; status: string };
                  return (
                    <div className="rounded-md border bg-popover px-3 py-2 text-sm text-popover-foreground shadow-md">
                      <p className="text-xs text-muted-foreground">Exercice {d.label}</p>
                      <p className="font-medium tabular-nums">{d.raw === null ? "Non calculable" : formatIndicator(d.raw, serie.unit)}</p>
                    </div>
                  );
                }} />
              <Line type="linear" dataKey="value" stroke={LINE_COLOR} strokeWidth={2} connectNulls={false}
                    dot={{ r: 4, fill: LINE_COLOR, stroke: "hsl(var(--card))", strokeWidth: 2 }}
                    activeDot={{ r: 6, fill: LINE_COLOR, stroke: "hsl(var(--card))", strokeWidth: 2 }}
                    isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

export default function MultiYearPage() {
  const { companyId } = useParams<{ companyId: string }>();
  const { data: company } = useApiResource<Company>(`/companies/${companyId}`);
  const { data, error, loading } = useApiResource<SeriesResponse>(`/companies/${companyId}/financial-series`);
  const [selected, setSelected] = useState<string>("CA");

  const grouped = useMemo(() => {
    const g: Record<string, Serie[]> = {};
    for (const s of data?.series ?? []) (g[s.category] ??= []).push(s);
    return CATEGORY_ORDER.filter((c) => g[c]).map((c) => [c, g[c]] as const);
  }, [data]);
  const current = data?.series.find((s) => s.code === selected) ?? data?.series[0];

  return (
    <>
      <Link href={`/companies/${companyId}`} className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ChevronLeft className="h-4 w-4" /> {company?.name ?? "Entreprise"}
      </Link>
      <PageHeader title="Analyse pluriannuelle"
                  description="Dernière analyse terminée de chaque exercice. Variations par rapport à l'exercice précédent de la série." />
      {loading && !data && <Loading />}
      {error && <Alert>{error}</Alert>}
      {data && data.years.length === 0 && (
        <EmptyState title="Aucun exercice analysé" description="Lancez l'analyse financière d'au moins un exercice." />
      )}
      {data && data.years.length > 0 && (
        <div className="space-y-6">
          {data.years.length === 1 && <Alert kind="info">Un seul exercice analysé : les variations apparaîtront avec le suivant.</Alert>}
          {current && <SerieChart serie={current} />}
          {grouped.map(([cat, list]) => (
            <Card key={cat}>
              <CardHeader><CardTitle>{CATEGORY_LABELS[cat] ?? cat}</CardTitle></CardHeader>
              <CardContent className="overflow-x-auto p-0">
                <table className="w-full text-sm">
                  <thead className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground">
                    <tr>
                      <th className="px-3 py-2 text-left">Indicateur</th>
                      {data.years.map((y) => <th key={y.id} className="px-3 py-2 text-right">{y.label}</th>)}
                      <th className="px-3 py-2 text-right">TCAM</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {list.map((s) => (
                      <tr key={s.code} onClick={() => setSelected(s.code)}
                          className={cn("cursor-pointer hover:bg-muted/40", current?.code === s.code && "bg-selection")}>
                        <td className="px-3 py-2"><span className="font-medium">{s.name}</span></td>
                        {s.points.map((p) => (
                          <td key={p.label} className="whitespace-nowrap px-3 py-2 text-right tabular-nums">
                            <div>{p.value === null ? <span className="text-xs text-muted-foreground">n.c.</span> : formatIndicator(p.value, s.unit)}</div>
                            {p.variation_pct !== null && <div className="text-xs text-muted-foreground">{pct(p.variation_pct)}</div>}
                          </td>
                        ))}
                        <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-muted-foreground">{s.cagr_pct !== null ? pct(s.cagr_pct) : ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          ))}
          <p className="text-xs text-muted-foreground">
            n.c. : non calculable (donnée absente ou dénominateur nul). TCAM : taux de croissance annuel moyen entre le premier et le dernier exercice
            disponibles, calculé pour les montants strictement positifs. Cliquez sur une ligne pour l&apos;afficher sur le graphique.
          </p>
        </div>
      )}
    </>
  );
}
