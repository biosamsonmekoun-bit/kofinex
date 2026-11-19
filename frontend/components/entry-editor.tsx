"use client";

/**
 * Saisie d'une écriture native : en-tête, lignes, totaux et écart calculés au centime (entiers), contrôles du serveur.
 * Les montants partent en chaînes décimales ; l'API et la base refont tous les contrôles (équilibre, comptes, tiers).
 * Raccourcis : Alt+N ajoute une ligne (préremplie de l'écart restant), Ctrl+S enregistre le brouillon.
 */

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Copy, Plus, Trash2 } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import type { CostCenter, FiscalYear } from "@/lib/types";
import type { CompanyAccount, EntryDetail, Journal, ThirdParty } from "@/lib/accounting-types";
import { amount, fromCents, isAmount, toCents } from "@/lib/accounting-types";
import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/form";
import { Alert, Badge } from "@/components/ui/feedback";
import { cn } from "@/lib/utils";

interface Row { key: number; account_number: string; third_party_id: string; label: string; debit: string; credit: string; cost_center_id: string; currency: string; currency_amount: string }
let seq = 0;
const blank = (p: Partial<Row> = {}): Row => ({ key: ++seq, account_number: "", third_party_id: "", label: "", debit: "", credit: "", cost_center_id: "", currency: "", currency_amount: "", ...p });

export function EntryEditor({ cid, fy, entry, onSaved }: { cid: string; fy: FiscalYear; entry?: EntryDetail; onSaved?: (e: EntryDetail) => void }) {
  const router = useRouter();
  const A = `/companies/${cid}/accounting`;
  const { data: journals } = useApiResource<Journal[]>(`${A}/journals?active=true`);
  const { data: accounts } = useApiResource<{ items: CompanyAccount[] }>(`${A}/accounts?active=true&limit=5000`);
  const { data: tps } = useApiResource<{ items: ThirdParty[] }>(`${A}/third-parties?active=true&limit=2000`);
  const { data: centers } = useApiResource<CostCenter[]>(`/companies/${cid}/cost-centers`);

  const [head, setHead] = useState({
    journal_id: entry?.journal_id ?? "", entry_date: entry?.entry_date ?? "", piece_ref: entry?.piece_ref ?? "",
    piece_date: entry?.piece_date ?? "", label: entry?.label ?? "", third_party_id: entry?.third_party_id ?? "",
  });
  const [rows, setRows] = useState<Row[]>(entry?.lines.length
    ? entry.lines.map((l) => blank({ account_number: l.account_number, third_party_id: l.third_party?.id ?? "", label: l.label ?? "",
        debit: Number(l.debit) ? l.debit : "", credit: Number(l.credit) ? l.credit : "", cost_center_id: l.cost_center_id ?? "",
        currency: l.currency ?? "", currency_amount: l.currency_amount ?? "" }))
    : [blank(), blank()]);
  const [showCurrency, setShowCurrency] = useState(rows.some((r) => r.currency));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [issues, setIssues] = useState<string[] | null>(entry?.check?.issues ?? null);

  const accMap = useMemo(() => new Map((accounts?.items ?? []).map((a) => [a.account_number, a])), [accounts]);
  const tpList = tps?.items ?? [];
  const totals = useMemo(() => {
    const d = rows.reduce((s, r) => s + toCents(r.debit), BigInt(0));
    const c = rows.reduce((s, r) => s + toCents(r.credit), BigInt(0));
    return { d, c, diff: d - c };
  }, [rows]);
  const badAmounts = rows.some((r) => !isAmount(r.debit) || !isAmount(r.credit) || (showCurrency && !isAmount(r.currency_amount)));

  const set = (k: number, patch: Partial<Row>) => setRows((rs) => rs.map((r) => (r.key === k ? { ...r, ...patch } : r)));
  function addLine() {
    const diff = totals.diff;
    setRows((rs) => [...rs, blank(diff > BigInt(0) ? { credit: fromCents(diff) } : diff < BigInt(0) ? { debit: fromCents(-diff) } : {})]);
  }
  const norm = (v: string) => v.trim().replace(/\s/g, "").replace(",", ".");
  function payload() {
    return {
      ...Object.fromEntries(Object.entries(head).map(([k, v]) => [k, v === "" ? null : v])),
      lines: rows.filter((r) => r.account_number || r.debit || r.credit).map((r) => ({
        account_number: r.account_number.trim(), third_party_id: r.third_party_id || null, label: r.label || null,
        debit: norm(r.debit) || null, credit: norm(r.credit) || null, cost_center_id: r.cost_center_id || null,
        currency: showCurrency && r.currency ? r.currency.toUpperCase() : null,
        currency_amount: showCurrency && r.currency ? norm(r.currency_amount) || null : null,
      })),
    };
  }

  async function preview() {
    setError(null);
    try {
      const res = await api.post<{ issues: string[] }>(`${A}/entries/check`, { ...payload(), fiscal_year_id: fy.id });
      setIssues(res.issues);
    } catch (e) { setError(errorMessage(e)); }
  }

  async function save(submit: boolean) {
    setBusy(true); setError(null);
    try {
      let e: EntryDetail = entry
        ? await api.patch<EntryDetail>(`${A}/entries/${entry.id}`, payload())
        : await api.post<EntryDetail>(`${A}/entries`, { ...payload(), fiscal_year_id: fy.id });
      if (submit) e = await api.post<EntryDetail>(`${A}/entries/${e.id}/transition`, { action: "submit" });
      setIssues(e.check?.issues ?? null);
      if (onSaved) onSaved(e); else router.push(`/companies/${cid}/comptabilite/ecritures/${e.id}`);
    } catch (err) { setError(errorMessage(err)); } finally { setBusy(false); }
  }

  const readonlyFy = fy.status !== "open";
  const canSave = !busy && !readonlyFy && !badAmounts && head.journal_id && head.entry_date && head.label.trim();
  const balanced = totals.diff === BigInt(0) && totals.d > BigInt(0);

  return (
    <form className="space-y-5" onSubmit={(e) => { e.preventDefault(); void save(false); }}
          onKeyDown={(e) => {
            if (e.altKey && (e.key === "n" || e.key === "N")) { e.preventDefault(); addLine(); }
            if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); if (canSave) void save(false); }
          }}>
      {readonlyFy && <Alert kind="warning">Exercice {fy.label} clôturé : aucune saisie possible.</Alert>}
      {error && <Alert>{error}</Alert>}

      <section className="grid gap-4 rounded-lg border bg-card p-4 shadow-card sm:grid-cols-2 lg:grid-cols-6">
        <Field label="Journal" htmlFor="j" required>
          <Select id="j" value={head.journal_id} onChange={(e) => setHead({ ...head, journal_id: e.target.value })} required>
            <option value="">— Choisir —</option>
            {journals?.map((j) => <option key={j.id} value={j.id}>{j.code} · {j.label}</option>)}
          </Select>
        </Field>
        <Field label="Date" htmlFor="d" required hint={`Exercice ${fy.label}`}>
          <Input id="d" type="date" min={fy.start_date} max={fy.end_date} value={head.entry_date} required
                 onChange={(e) => setHead({ ...head, entry_date: e.target.value })} />
        </Field>
        <Field label="Référence de la pièce" htmlFor="pr">
          <Input id="pr" value={head.piece_ref} maxLength={60} onChange={(e) => setHead({ ...head, piece_ref: e.target.value })} />
        </Field>
        <Field label="Date de la pièce" htmlFor="pd">
          <Input id="pd" type="date" value={head.piece_date} onChange={(e) => setHead({ ...head, piece_date: e.target.value })} />
        </Field>
        <Field label="Tiers (facultatif)" htmlFor="tp">
          <Select id="tp" value={head.third_party_id} onChange={(e) => setHead({ ...head, third_party_id: e.target.value })}>
            <option value="">—</option>
            {tpList.map((t) => <option key={t.id} value={t.id}>{t.code} · {t.name}</option>)}
          </Select>
        </Field>
        <div className="sm:col-span-2 lg:col-span-6">
          <Field label="Libellé" htmlFor="lb" required>
            <Input id="lb" value={head.label} maxLength={200} required onChange={(e) => setHead({ ...head, label: e.target.value })} />
          </Field>
        </div>
      </section>

      <datalist id="acc-list">{accounts?.items.map((a) => <option key={a.id} value={a.account_number}>{a.label}</option>)}</datalist>

      <section className="overflow-x-auto rounded-lg border bg-card shadow-card">
        <table className="w-full min-w-[960px] text-sm tabular-nums">
          <thead className="border-b bg-muted/70 text-left text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="w-8 px-2 py-2">#</th><th className="w-40 px-2 py-2">Compte</th><th className="px-2 py-2">Intitulé</th>
              <th className="w-48 px-2 py-2">Tiers</th><th className="px-2 py-2">Libellé</th>
              {!!centers?.length && <th className="w-36 px-2 py-2">Analytique</th>}
              {showCurrency && <th className="w-36 px-2 py-2">Devise / montant</th>}
              <th className="w-32 px-2 py-2 text-right">Débit</th><th className="w-32 px-2 py-2 text-right">Crédit</th><th className="w-20 px-2 py-2" />
            </tr>
          </thead>
          <tbody className="divide-y">
            {rows.map((r, i) => {
              const acc = accMap.get(r.account_number.trim());
              const tpChoices = acc?.third_party_kind ? tpList.filter((t) => t.kind === acc.third_party_kind) : tpList;
              return (
                <tr key={r.key} className="align-top">
                  <td className="px-2 py-2 text-xs text-muted-foreground">{i + 1}</td>
                  <td className="px-2 py-1.5">
                    <Input list="acc-list" aria-label={`Compte, ligne ${i + 1}`} value={r.account_number} inputMode="numeric"
                           className={cn(r.account_number && !acc && "border-destructive")}
                           onChange={(e) => set(r.key, { account_number: e.target.value.replace(/[^0-9]/g, "") })} />
                  </td>
                  <td className="px-2 py-2.5 text-xs text-muted-foreground">
                    {acc ? acc.label : r.account_number ? <span className="text-destructive-strong">Compte non ouvert</span> : ""}
                    {acc?.requires_third_party && <Badge className="ml-1" tone="blue">collectif</Badge>}
                  </td>
                  <td className="px-2 py-1.5">
                    <Select aria-label={`Tiers, ligne ${i + 1}`} value={r.third_party_id} onChange={(e) => set(r.key, { third_party_id: e.target.value })}
                            className={cn(acc?.requires_third_party && !r.third_party_id && "border-warning")}>
                      <option value="">{acc?.requires_third_party ? "— obligatoire —" : "—"}</option>
                      {tpChoices.map((t) => <option key={t.id} value={t.id}>{t.code} · {t.name}</option>)}
                    </Select>
                  </td>
                  <td className="px-2 py-1.5"><Input aria-label={`Libellé, ligne ${i + 1}`} value={r.label} placeholder={head.label} maxLength={200}
                                                     onChange={(e) => set(r.key, { label: e.target.value })} /></td>
                  {!!centers?.length && (
                    <td className="px-2 py-1.5">
                      <Select aria-label={`Centre analytique, ligne ${i + 1}`} value={r.cost_center_id} onChange={(e) => set(r.key, { cost_center_id: e.target.value })}>
                        <option value="">—</option>
                        {centers.filter((c) => c.is_active).map((c) => <option key={c.id} value={c.id}>{c.code}</option>)}
                      </Select>
                    </td>
                  )}
                  {showCurrency && (
                    <td className="px-2 py-1.5">
                      <div className="flex gap-1">
                        <Input aria-label={`Devise, ligne ${i + 1}`} className="w-16 uppercase" maxLength={3} value={r.currency}
                               onChange={(e) => set(r.key, { currency: e.target.value.toUpperCase().replace(/[^A-Z]/g, "") })} />
                        <Input aria-label={`Montant en devise, ligne ${i + 1}`} inputMode="decimal" value={r.currency_amount}
                               onChange={(e) => set(r.key, { currency_amount: e.target.value })} />
                      </div>
                    </td>
                  )}
                  <td className="px-2 py-1.5">
                    <Input aria-label={`Débit, ligne ${i + 1}`} inputMode="decimal" className={cn("text-right", !isAmount(r.debit) && "border-destructive")}
                           value={r.debit} onChange={(e) => set(r.key, { debit: e.target.value, ...(e.target.value ? { credit: "" } : {}) })} />
                  </td>
                  <td className="px-2 py-1.5">
                    <Input aria-label={`Crédit, ligne ${i + 1}`} inputMode="decimal" className={cn("text-right", !isAmount(r.credit) && "border-destructive")}
                           value={r.credit} onChange={(e) => set(r.key, { credit: e.target.value, ...(e.target.value ? { debit: "" } : {}) })}
                           onKeyDown={(e) => { if (e.key === "Enter" && i === rows.length - 1) { e.preventDefault(); addLine(); } }} />
                  </td>
                  <td className="whitespace-nowrap px-1 py-1.5">
                    <Button type="button" variant="ghost" size="icon" aria-label={`Dupliquer la ligne ${i + 1}`}
                            onClick={() => setRows((rs) => [...rs.slice(0, i + 1), { ...r, key: ++seq }, ...rs.slice(i + 1)])}>
                      <Copy className="h-4 w-4" aria-hidden />
                    </Button>
                    <Button type="button" variant="ghost" size="icon" aria-label={`Supprimer la ligne ${i + 1}`} disabled={rows.length <= 1}
                            onClick={() => setRows((rs) => rs.filter((x) => x.key !== r.key))}>
                      <Trash2 className="h-4 w-4" aria-hidden />
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
          <tfoot className="border-t bg-muted/40 font-semibold">
            <tr>
              <td colSpan={5 + (centers?.length ? 1 : 0) + (showCurrency ? 1 : 0)} className="px-2 py-2.5">
                <span className="flex flex-wrap items-center gap-3">
                  <Button type="button" variant="outline" size="sm" onClick={addLine}><Plus className="h-4 w-4" aria-hidden /> Ligne</Button>
                  <label className="flex items-center gap-1.5 text-xs font-normal text-muted-foreground">
                    <input type="checkbox" checked={showCurrency} onChange={(e) => setShowCurrency(e.target.checked)} /> Montants en devise
                  </label>
                  <span className={cn("text-xs", balanced ? "text-success-strong" : "text-warning-strong")} role="status">
                    {balanced ? "Équilibrée" : `Écart : ${amount(fromCents(totals.diff < BigInt(0) ? -totals.diff : totals.diff))} ${totals.diff > BigInt(0) ? "(débit supérieur)" : totals.diff < BigInt(0) ? "(crédit supérieur)" : ""}`}
                  </span>
                </span>
              </td>
              <td className="px-2 py-2.5 text-right">{amount(fromCents(totals.d))}</td>
              <td className="px-2 py-2.5 text-right">{amount(fromCents(totals.c))}</td>
              <td />
            </tr>
          </tfoot>
        </table>
      </section>

      {issues && (issues.length
        ? <Alert kind="warning"><p className="font-medium">Contrôles avant soumission</p><ul className="mt-1 list-disc pl-5">{issues.map((x, i) => <li key={i}>{x}</li>)}</ul></Alert>
        : <Alert kind="success">Contrôles satisfaits : l&apos;écriture peut être soumise.</Alert>)}

      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={!canSave}>Enregistrer le brouillon</Button>
        <Button type="button" variant="secondary" disabled={!canSave} onClick={() => void save(true)}>Enregistrer et soumettre</Button>
        <Button type="button" variant="outline" disabled={busy || badAmounts} onClick={() => void preview()}>Prévisualiser les contrôles</Button>
        <span className="self-center text-xs text-muted-foreground">Alt+N : nouvelle ligne · Ctrl+S : enregistrer</span>
      </div>
    </form>
  );
}
