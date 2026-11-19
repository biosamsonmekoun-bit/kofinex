"use client";

import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/form";

/* Éditeurs de paramètres des modèles de coûts. Les lignes sont conservées sous forme de textes saisis ;
   la conversion vers les paramètres du moteur (et les erreurs de saisie) est faite par toParams*. Les
   contrôles de fond (clés = 100 %, chevauchements, nature des comptes) sont faits par le moteur. */

export type Rows = Record<string, string>[];
interface Col { key: string; label: string; width?: string; options?: [string, string][]; align?: "right"; placeholder?: string }

export function RowsEditor({ title, description, cols, rows, onChange, readOnly }: {
  title: string; description?: string; cols: Col[]; rows: Rows; onChange: (r: Rows) => void; readOnly: boolean;
}) {
  const set = (i: number, k: string, v: string) => onChange(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent className="space-y-2">
        <div className="w-full overflow-x-auto rounded-md border">
          <table className="w-full text-sm tabular-nums">
            <thead className="border-b bg-muted/70 text-left text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              <tr>{cols.map((c) => <th key={c.key} className="px-2 py-2">{c.label}</th>)}{!readOnly && <th className="w-10" />}</tr>
            </thead>
            <tbody className="divide-y">
              {rows.length === 0 && (
                <tr><td colSpan={cols.length + 1} className="px-3 py-4 text-center text-sm text-muted-foreground">Aucune ligne.</td></tr>
              )}
              {rows.map((r, i) => (
                <tr key={i}>
                  {cols.map((c) => (
                    <td key={c.key} className="px-2 py-1.5">
                      {readOnly ? <span className={c.align === "right" ? "block text-right" : ""}>{c.options ? (c.options.find(([v]) => v === r[c.key])?.[1] ?? r[c.key]) : r[c.key]}</span>
                        : c.options ? (
                          <Select aria-label={c.label} value={r[c.key] ?? ""} onChange={(e) => set(i, c.key, e.target.value)} className={c.width}>
                            {c.options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                          </Select>
                        ) : (
                          <Input aria-label={c.label} value={r[c.key] ?? ""} placeholder={c.placeholder}
                                 className={`${c.width ?? ""} ${c.align === "right" ? "text-right" : ""}`}
                                 onChange={(e) => set(i, c.key, e.target.value)} />
                        )}
                    </td>
                  ))}
                  {!readOnly && (
                    <td className="px-1 text-right">
                      <Button variant="ghost" size="icon" aria-label="Supprimer la ligne" onClick={() => onChange(rows.filter((_, j) => j !== i))}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!readOnly && (
          <Button variant="outline" size="sm" onClick={() => onChange([...rows, Object.fromEntries(cols.map((c) => [c.key, c.options?.[0]?.[0] ?? ""]))])}>
            <Plus className="h-4 w-4" /> Ajouter
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------ conversions
export class InputError extends Error {}
const num = (v: string | undefined, what: string): string => {
  const s = (v ?? "").replace(/[\s  ]/g, "").replace(",", ".");
  if (!/^-?\d+(\.\d+)?$/.test(s)) throw new InputError(`${what} : nombre invalide « ${v ?? ""} ».`);
  return s;
};
const prefix = (v: string | undefined, what: string): string => {
  const s = (v ?? "").trim();
  if (!/^\d{1,20}$/.test(s)) throw new InputError(`${what} : racine de compte invalide « ${v ?? ""} ».`);
  return s;
};
const list = (v: string | undefined): string[] => (v ?? "").split(/[,;\s]+/).map((x) => x.trim()).filter(Boolean);

/** « A1=40 ; M1=60 » -> { A1: "40", M1: "60" } */
export function parseKeys(v: string | undefined, what: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const part of (v ?? "").split(";").map((x) => x.trim()).filter(Boolean)) {
    const m = part.match(/^([^=:]+)[=:]\s*(.+)$/);
    if (!m) throw new InputError(`${what} : clé « ${part} » illisible (format CODE=pourcentage).`);
    out[m[1].trim().toUpperCase()] = num(m[2], `${what}, clé ${m[1].trim()}`);
  }
  return out;
}
export const keysText = (k: Record<string, unknown> | undefined) => Object.entries(k ?? {}).map(([c, p]) => `${c}=${p}`).join(" ; ");

// --- coût-volume-profit
export interface CvpForm { revenue: string; charges: Rows }
export const cvpFromParams = (p: Record<string, unknown>): CvpForm => ({
  revenue: ((p.revenue_prefixes as string[]) ?? []).join(", "),
  charges: ((p.charges as Record<string, unknown>[]) ?? []).map((c) => ({ prefix: String(c.prefix ?? ""), label: String(c.label ?? ""), variable_pct: String(c.variable_pct ?? "") })),
});
export const cvpToParams = (f: CvpForm) => ({
  revenue_prefixes: list(f.revenue).map((p) => prefix(p, "Chiffre d'affaires")),
  charges: f.charges.map((c, i) => ({ prefix: prefix(c.prefix, `Charge ${i + 1}`), label: c.label || null,
                                      variable_pct: num(c.variable_pct, `Charge ${c.prefix} : part variable`) })),
});

// --- coûts préétablis
export interface StdForm { actual_output: string; budgeted_output: string; elements: Rows }
export const stdFromParams = (p: Record<string, unknown>): StdForm => ({
  actual_output: String(p.actual_output ?? ""), budgeted_output: String(p.budgeted_output ?? ""),
  elements: ((p.elements as Record<string, unknown>[]) ?? []).map((e) => Object.fromEntries(
    ["label", "unit", "standard_quantity_per_unit", "standard_unit_cost", "actual_quantity", "actual_unit_cost"].map((k) => [k, String(e[k] ?? "")]))),
});
export const stdToParams = (f: StdForm) => ({
  actual_output: num(f.actual_output, "Production réelle"),
  budgeted_output: f.budgeted_output.trim() ? num(f.budgeted_output, "Production prévue") : null,
  elements: f.elements.map((e, i) => ({
    label: e.label || `Élément ${i + 1}`, unit: e.unit || null,
    standard_quantity_per_unit: num(e.standard_quantity_per_unit, `${e.label} : quantité standard`),
    standard_unit_cost: num(e.standard_unit_cost, `${e.label} : coût standard`),
    actual_quantity: num(e.actual_quantity, `${e.label} : quantité réelle`),
    actual_unit_cost: num(e.actual_unit_cost, `${e.label} : coût réel`),
  })),
});

// --- coûts complets
export interface FullForm { centers: Rows; objects: Rows; charges: Rows; supplementary: Rows; secondary: Rows; usage: Rows }
type P = Record<string, unknown>;
export const fullFromParams = (p: P): FullForm => ({
  centers: ((p.centers as P[]) ?? []).map((c) => {
    const a = (c.allocation as P) ?? {};
    return { code: String(c.code ?? ""), name: String(c.name ?? ""), kind: String(c.kind ?? "main"), alloc: String(a.type ?? "work_unit"),
             unit: String(a.unit ?? ""), volume: String(a.volume ?? ""), keys: keysText(a.keys as P) };
  }),
  objects: ((p.objects as P[]) ?? []).map((o) => ({ code: String(o.code ?? ""), name: String(o.name ?? ""), quantity: String(o.quantity ?? ""),
                                                   sold_quantity: String(o.sold_quantity ?? ""), revenue: String(o.revenue ?? ""), revenue_prefix: String(o.revenue_prefix ?? "") })),
  charges: ((p.charges as P[]) ?? []).map((c) => ({ prefix: String(c.prefix ?? ""), exclusions: ((c.exclusions as string[]) ?? []).join(", "),
                                                    label: String(c.label ?? ""), keys: keysText(c.keys as P) })),
  supplementary: ((p.supplementary as P[]) ?? []).map((s) => ({ label: String(s.label ?? ""), amount: String(s.amount ?? ""), keys: keysText(s.keys as P) })),
  secondary: ((p.secondary as P[]) ?? []).map((s) => ({ from: String(s.from ?? ""), keys: keysText(s.keys as P) })),
  usage: ((p.usage as P[]) ?? []).map((u) => ({ object: String(u.object ?? ""), center: String(u.center ?? ""), quantity: String(u.quantity ?? "") })),
});
export const fullToParams = (f: FullForm) => ({
  centers: f.centers.map((c) => ({
    code: c.code.trim().toUpperCase(), name: c.name, kind: c.kind,
    ...(c.kind === "main" ? { allocation: c.alloc === "keys"
      ? { type: "keys", keys: parseKeys(c.keys, `Centre ${c.code} : imputation`) }
      : { type: "work_unit", unit: c.unit || null, volume: num(c.volume, `Centre ${c.code} : volume d'unités d'œuvre`) } } : {}),
  })),
  objects: f.objects.map((o) => ({
    code: o.code.trim().toUpperCase(), name: o.name, quantity: num(o.quantity, `Objet ${o.code} : quantité`),
    ...(o.sold_quantity.trim() ? { sold_quantity: num(o.sold_quantity, `Objet ${o.code} : quantité vendue`) } : {}),
    ...(o.revenue_prefix.trim() ? { revenue_prefix: prefix(o.revenue_prefix, `Objet ${o.code} : racine du CA`) }
      : o.revenue.trim() ? { revenue: num(o.revenue, `Objet ${o.code} : chiffre d'affaires`) } : {}),
  })),
  charges: f.charges.map((c, i) => ({ prefix: prefix(c.prefix, `Charge ${i + 1}`), exclusions: list(c.exclusions).map((x) => prefix(x, `Charge ${c.prefix} : exclusion`)),
                                       label: c.label || null, keys: parseKeys(c.keys, `Charge ${c.prefix}`) })),
  supplementary: f.supplementary.map((s) => ({ label: s.label, amount: num(s.amount, `Supplétive ${s.label}`), keys: parseKeys(s.keys, `Supplétive ${s.label}`) })),
  secondary: f.secondary.map((s) => ({ from: s.from.trim().toUpperCase(), keys: parseKeys(s.keys, `Centre ${s.from} : répartition secondaire`) })),
  usage: f.usage.map((u) => ({ object: u.object.trim().toUpperCase(), center: u.center.trim().toUpperCase(),
                               quantity: num(u.quantity, `UO ${u.object}/${u.center}`) })),
});
