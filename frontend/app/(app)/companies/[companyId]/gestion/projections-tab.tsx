"use client";

import { useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, errorMessage } from "@/lib/api";
import { formatAmount, formatPct } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, EmptyState } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

interface Method { unavailable?: string; projections?: string[]; slope?: string; intercept?: string; r2?: string | null; rate_pct?: string }
interface Projection {
  prefix: string; nature: string; horizon: number; points: { fiscal_year_id: string; label: string; value: string }[];
  methods: { linear_trend: Method; cagr: Method }; notes: string[];
}

const COLORS = { actual: "hsl(var(--chart-1))", linear: "hsl(var(--chart-3))", cagr: "hsl(var(--chart-4))" };
const AXIS = { tick: { fill: "hsl(var(--muted-foreground))", fontSize: 12 }, tickLine: false };

export function ProjectionsTab({ companyId }: { companyId: string }) {
  const [prefix, setPrefix] = useState("");
  const [horizon, setHorizon] = useState("2");
  const [data, setData] = useState<Projection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setData(await api.get<Projection>(`/companies/${companyId}/projections?prefix=${encodeURIComponent(prefix)}&horizon=${horizon}`));
    } catch (err) {
      setError(errorMessage(err));
      setData(null);
    } finally {
      setBusy(false);
    }
  }

  const chart = data ? [
    ...data.points.map((p) => ({ label: p.label, Réalisé: Number(p.value) })),
    ...Array.from({ length: data.horizon }, (_, h) => ({
      label: `+${h + 1}`,
      Tendance: data.methods.linear_trend.projections ? Number(data.methods.linear_trend.projections[h]) : undefined,
      TCAM: data.methods.cagr.projections ? Number(data.methods.cagr.projections[h]) : undefined,
    })),
  ] : [];
  // relier la dernière valeur réalisée aux projections
  if (data && chart.length > data.points.length) {
    const last = chart[data.points.length - 1] as Record<string, number | string | undefined>;
    if (data.methods.linear_trend.projections) last.Tendance = last.Réalisé;
    if (data.methods.cagr.projections) last.TCAM = last.Réalisé;
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Projection statistique d&apos;une racine de compte</CardTitle>
          <CardDescription>
            Extrapolation des réalisés des exercices validés (tendance linéaire par moindres carrés, taux de croissance annuel
            moyen). C&apos;est un point de départ pour une prévision, pas une prévision validée.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={run} className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <Field label="Racine de compte (charges ou produits)" htmlFor="pr-prefix" required>
              <Input id="pr-prefix" value={prefix} inputMode="numeric" className="w-40" onChange={(e) => setPrefix(e.target.value.trim())} required />
            </Field>
            <Field label="Horizon" htmlFor="pr-h">
              <Select id="pr-h" value={horizon} onChange={(e) => setHorizon(e.target.value)} className="w-32">
                {[1, 2, 3, 4, 5].map((h) => <option key={h} value={h}>{h} exercice{h > 1 ? "s" : ""}</option>)}
              </Select>
            </Field>
            <Button type="submit" loading={busy} disabled={!/^\d{1,20}$/.test(prefix)}>Projeter</Button>
          </form>
        </CardContent>
      </Card>
      {error && <Alert>{error}</Alert>}
      {!data && !error && <EmptyState title="Choisissez une racine" description="Par exemple la racine des ventes ou d'un poste de charges." />}
      {data && (
        <Card>
          <CardHeader>
            <CardTitle>Racine {data.prefix} <span className="text-sm font-normal text-muted-foreground">({data.nature})</span></CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {data.notes.map((n) => <p key={n} className="text-xs text-muted-foreground">{n}</p>)}
            <div className="h-72" role="img" aria-label="Réalisés et projections">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chart}>
                  <CartesianGrid stroke="hsl(var(--border))" vertical={false} />
                  <XAxis dataKey="label" {...AXIS} axisLine={{ stroke: "hsl(var(--border))" }} />
                  <YAxis width={88} {...AXIS} axisLine={false} tickFormatter={(v: number) => v.toLocaleString("fr-FR", { notation: "compact", maximumFractionDigits: 1 })} />
                  <Tooltip formatter={(v: number) => v.toLocaleString("fr-FR", { maximumFractionDigits: 0 })}
                           contentStyle={{ background: "hsl(var(--popover))", border: "1px solid hsl(var(--border))", borderRadius: 6, color: "hsl(var(--popover-foreground))" }} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Line type="linear" dataKey="Réalisé" stroke={COLORS.actual} strokeWidth={2} dot={{ r: 4 }} connectNulls={false} />
                  {data.methods.linear_trend.projections && <Line type="linear" dataKey="Tendance" stroke={COLORS.linear} strokeWidth={2} strokeDasharray="5 4" dot={{ r: 3 }} />}
                  {data.methods.cagr.projections && <Line type="linear" dataKey="TCAM" stroke={COLORS.cagr} strokeWidth={2} strokeDasharray="2 3" dot={{ r: 3 }} />}
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <Table>
                <THead><tr><TH>Exercice</TH><TH className="text-right">Réalisé</TH></tr></THead>
                <TBody>{data.points.map((p) => <TR key={p.fiscal_year_id}><TD>{p.label}</TD><TD className="text-right">{formatAmount(p.value)}</TD></TR>)}</TBody>
              </Table>
              <div className="space-y-3 text-sm">
                <div className="rounded-md border p-3">
                  <p className="font-medium">Tendance linéaire</p>
                  {data.methods.linear_trend.unavailable ? <p className="text-muted-foreground">{data.methods.linear_trend.unavailable}</p> : (
                    <>
                      <p className="text-muted-foreground">Pente par exercice : {formatAmount(Number(data.methods.linear_trend.slope).toFixed(2))} — R² : {data.methods.linear_trend.r2 === null ? "—" : Number(data.methods.linear_trend.r2).toLocaleString("fr-FR", { maximumFractionDigits: 3 })}</p>
                      <p className="tabular-nums">{data.methods.linear_trend.projections!.map((v, i) => `+${i + 1} : ${formatAmount(Number(v).toFixed(2))}`).join("  ·  ")}</p>
                    </>
                  )}
                </div>
                <div className="rounded-md border p-3">
                  <p className="font-medium">Taux de croissance annuel moyen</p>
                  {data.methods.cagr.unavailable ? <p className="text-muted-foreground">{data.methods.cagr.unavailable}</p> : (
                    <>
                      <p className="text-muted-foreground">Taux : {formatPct(data.methods.cagr.rate_pct, 2)}</p>
                      <p className="tabular-nums">{data.methods.cagr.projections!.map((v, i) => `+${i + 1} : ${formatAmount(Number(v).toFixed(2))}`).join("  ·  ")}</p>
                    </>
                  )}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
