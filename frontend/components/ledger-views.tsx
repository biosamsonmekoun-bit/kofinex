"use client";

// Vues du grand livre, partagées par la page de l'entreprise et par les missions d'audit (base d'URL différente).
import { useState } from "react";
import { Download, Search } from "lucide-react";
import { api } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import type { LedgerAccount, LedgerAnalytics, LedgerJournal, LedgerLineRow, LedgerPage } from "@/lib/ledger-types";
import { formatAmount, formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, Loading } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const PAGE = 200;

function EntryDialog({ base, entry, onClose }: { base: string; entry: { journal: string | null; number: string }; onClose: () => void }) {
  const { data } = useApiResource<LedgerLineRow[]>(`${base}/entry?number=${encodeURIComponent(entry.number)}${entry.journal ? `&journal=${encodeURIComponent(entry.journal)}` : ""}`);
  const d = (data ?? []).reduce((a, l) => a + Number(l.debit), 0);
  const c = (data ?? []).reduce((a, l) => a + Number(l.credit), 0);
  return (
    <Dialog open onClose={onClose} title={`Écriture ${entry.journal ? `${entry.journal} / ` : ""}${entry.number}`}>
      {!data ? <Loading /> : (
        <Table>
          <THead><tr><TH>Compte</TH><TH>Libellé</TH><TH className="text-right">Débit</TH><TH className="text-right">Crédit</TH></tr></THead>
          <TBody>
            {data.map((l) => <TR key={l.source_row}><TD>{l.account_number} <span className="text-xs text-muted-foreground">{l.account_label}</span>{l.auxiliary_account && <p className="text-xs">{l.auxiliary_account} {l.auxiliary_label}</p>}</TD><TD>{l.label}</TD><TD className="text-right tabular-nums">{formatAmount(l.debit, { blankZero: true })}</TD><TD className="text-right tabular-nums">{formatAmount(l.credit, { blankZero: true })}</TD></TR>)}
            <TR><TD className="font-medium">Total</TD><TD>{data[0] && `${formatDate(data[0].entry_date)} · pièce ${data[0].document_ref ?? "—"}`}</TD><TD className="text-right font-medium tabular-nums">{formatAmount(d.toFixed(2))}</TD><TD className="text-right font-medium tabular-nums">{formatAmount(c.toFixed(2))}</TD></TR>
          </TBody>
        </Table>
      )}
    </Dialog>
  );
}

export function LedgerBrowser({ base, initialAccount }: { base: string; initialAccount?: string }) {
  const [f, setF] = useState({ account: initialAccount ?? "", account_prefix: "", journal: "", date_from: "", date_to: "", q: "", min_amount: "", lettered: "" });
  const [applied, setApplied] = useState(f);
  const [offset, setOffset] = useState(0);
  const [entry, setEntry] = useState<{ journal: string | null; number: string } | null>(null);
  const qs = new URLSearchParams(Object.entries(applied).filter(([, v]) => v !== "").map(([k, v]) => [k, k === "min_amount" ? v.replace(",", ".") : v]));
  const { data, error, loading } = useApiResource<LedgerPage>(`${base}?${qs.toString()}&limit=${PAGE}&offset=${offset}`);
  const set = (k: keyof typeof f) => (x: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: x.target.value });
  return (
    <div className="space-y-3">
      <form className="grid gap-2 sm:grid-cols-4 lg:grid-cols-8" onSubmit={(x) => { x.preventDefault(); setOffset(0); setApplied(f); }}>
        <Input aria-label="Compte exact" placeholder="Compte exact" inputMode="numeric" value={f.account} onChange={set("account")} />
        <Input aria-label="Racine de comptes" placeholder="Racine (ex. 41)" inputMode="numeric" value={f.account_prefix} onChange={set("account_prefix")} />
        <Input aria-label="Journal" placeholder="Journal" value={f.journal} onChange={set("journal")} />
        <Input aria-label="Du" type="date" value={f.date_from} onChange={set("date_from")} />
        <Input aria-label="Au" type="date" value={f.date_to} onChange={set("date_to")} />
        <Input aria-label="Recherche" placeholder="Libellé, pièce, n°" value={f.q} onChange={set("q")} />
        <Input aria-label="Montant minimal" placeholder="Montant ≥" inputMode="decimal" value={f.min_amount} onChange={set("min_amount")} />
        <div className="flex gap-2">
          <Select aria-label="Lettrage" value={f.lettered} onChange={set("lettered")}><option value="">Lettrage</option><option value="true">Lettrées</option><option value="false">Non lettrées</option></Select>
          <Button type="submit" size="icon" aria-label="Filtrer"><Search className="h-4 w-4" /></Button>
        </div>
      </form>
      {error && <Alert>{error}</Alert>}
      {loading && !data && <Loading />}
      {data && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <span>{data.total_count} ligne(s) · débit {formatAmount(data.totals.debit)} · crédit {formatAmount(data.totals.credit)} · solde {formatAmount(data.totals.net)}
              {data.running_balance ? (data.opening_balance && data.opening_balance !== "0" ? ` · solde antérieur ${formatAmount(data.opening_balance)}` : "") : applied.account ? " · solde progressif indisponible avec ces filtres" : ""}</span>
            <Button size="sm" variant="outline" onClick={() => api.download(`${base}.csv?${qs.toString()}`, "grand-livre.csv")}><Download className="h-4 w-4" /> CSV</Button>
          </div>
          {!applied.account && <p className="text-xs text-muted-foreground">Indiquez un compte exact pour afficher le solde progressif.</p>}
          <Table>
            <THead><tr><TH>Date</TH><TH>Journal</TH><TH>Écriture</TH><TH>Pièce</TH><TH>Compte</TH><TH>Libellé</TH><TH className="text-right">Débit</TH><TH className="text-right">Crédit</TH>{data.running_balance && <TH className="text-right">Solde</TH>}<TH>Let.</TH></tr></THead>
            <TBody>{data.items.map((l) => (
              <TR key={l.id ?? l.source_row}>
                <TD className="whitespace-nowrap">{formatDate(l.entry_date)}</TD><TD>{l.journal_code}</TD>
                <TD>{l.entry_number ? <button className="text-link hover:underline" onClick={() => setEntry({ journal: l.journal_code, number: l.entry_number! })}>{l.entry_number}</button> : "—"}</TD>
                <TD>{l.document_ref}</TD>
                <TD className="whitespace-nowrap">{l.account_number}{l.auxiliary_account && <span className="block text-xs text-muted-foreground">{l.auxiliary_account}</span>}</TD>
                <TD>{l.label}</TD>
                <TD className="text-right tabular-nums">{formatAmount(l.debit, { blankZero: true })}</TD><TD className="text-right tabular-nums">{formatAmount(l.credit, { blankZero: true })}</TD>
                {data.running_balance && <TD className="text-right tabular-nums">{formatAmount(l.running_balance)}</TD>}
                <TD>{l.lettering}</TD>
              </TR>))}
            </TBody>
          </Table>
          {data.total_count > PAGE && (
            <div className="flex items-center justify-end gap-2 text-sm">
              <Button size="sm" variant="outline" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Précédent</Button>
              <span>{offset + 1}–{Math.min(offset + PAGE, data.total_count)} sur {data.total_count}</span>
              <Button size="sm" variant="outline" disabled={offset + PAGE >= data.total_count} onClick={() => setOffset(offset + PAGE)}>Suivant</Button>
            </div>
          )}
        </>
      )}
      {entry && <EntryDialog base={base} entry={entry} onClose={() => setEntry(null)} />}
    </div>
  );
}

export function LedgerAccounts({ base, onOpen }: { base: string; onOpen: (account: string) => void }) {
  const [prefix, setPrefix] = useState("");
  const { data, error, loading } = useApiResource<{ accounts: LedgerAccount[]; opening_journals: string[]; balance_available: boolean; balance_accounts_without_lines: string[] }>(`${base}/accounts${prefix ? `?prefix=${prefix}` : ""}`);
  if (loading && !data) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  if (!data) return null;
  const gaps = data.accounts.filter((a) => a.tb && (a.tb.movement_gap || a.tb.opening_gap)).length;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <Input aria-label="Racine" className="w-40" placeholder="Racine (ex. 6)" inputMode="numeric" value={prefix} onChange={(x) => setPrefix(x.target.value.replace(/\D/g, ""))} />
        <p className="text-sm text-muted-foreground">
          {data.balance_available ? `Rapprochement avec la balance validée : ${gaps} compte(s) en écart` : "Aucune balance validée : rapprochement indisponible"}
          {data.opening_journals.length ? ` · à-nouveaux : journaux ${data.opening_journals.join(", ")}` : " · aucun journal d'à-nouveaux désigné (les à-nouveaux éventuels sont comptés dans les mouvements)"}
        </p>
      </div>
      {data.balance_accounts_without_lines.length > 0 && <Alert kind="warning">Comptes mouvementés dans la balance sans écriture au grand livre : {data.balance_accounts_without_lines.join(", ")}</Alert>}
      <Table>
        <THead><tr><TH>Compte</TH><TH className="text-right">Lignes</TH><TH className="text-right">À-nouveaux</TH><TH className="text-right">Débit</TH><TH className="text-right">Crédit</TH><TH className="text-right">Solde</TH><TH>Balance</TH></tr></THead>
        <TBody>{data.accounts.map((a) => (
          <TR key={a.account_number} className="cursor-pointer" onClick={() => onOpen(a.account_number)}>
            <TD><span className="font-medium">{a.account_number}</span> <span className="text-xs text-muted-foreground">{a.label}</span></TD>
            <TD className="text-right">{a.lines}</TD><TD className="text-right tabular-nums">{formatAmount(a.opening, { blankZero: true })}</TD>
            <TD className="text-right tabular-nums">{formatAmount(a.debit)}</TD><TD className="text-right tabular-nums">{formatAmount(a.credit)}</TD>
            <TD className="text-right font-medium tabular-nums">{formatAmount(a.balance)}</TD>
            <TD>{!a.tb ? <Badge tone="amber">Absent de la balance</Badge> : a.tb.movement_gap || a.tb.opening_gap
              ? <Badge tone="red" >Écart {a.tb.movement_gap ? `mouvements (balance D ${formatAmount(a.tb.movement_debit)} / C ${formatAmount(a.tb.movement_credit)})` : `à-nouveaux (balance ${formatAmount(a.tb.opening)})`}</Badge>
              : <Badge tone="green">Concorde</Badge>}</TD>
          </TR>))}
        </TBody>
      </Table>
    </div>
  );
}

export function LedgerJournals({ base }: { base: string }) {
  const { data, error, loading } = useApiResource<{ journals: LedgerJournal[] }>(`${base}/journals`);
  if (loading && !data) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  if (!data) return null;
  const periods = Array.from(new Set<number>(data.journals.flatMap((j: LedgerJournal) => j.months.map((m) => m.period)))).sort((a, b) => a - b);
  const monthOf = new Map(data.journals.flatMap((j) => j.months.map((m) => [m.period, m.month] as const)));
  const monthLabel = (p: number) => new Date(`${monthOf.get(p)}T00:00:00`).toLocaleDateString("fr-FR", { month: "short", year: "2-digit" });
  return (
    <div className="overflow-x-auto">
      <p className="mb-2 text-sm text-muted-foreground">Débit par journal et par mois de l&apos;exercice (le crédit est égal pour des écritures équilibrées). Nombre d&apos;écritures entre parenthèses.</p>
      <Table>
        <THead><tr><TH>Journal</TH>{periods.map((p) => <TH key={p} className="text-right">{monthLabel(p)}</TH>)}<TH className="text-right">Total</TH></tr></THead>
        <TBody>{data.journals.map((j) => (
          <TR key={j.journal}>
            <TD><span className="font-medium">{j.journal || "—"}</span> <span className="text-xs text-muted-foreground">{j.label}</span></TD>
            {periods.map((p) => { const m = j.months.find((x) => x.period === p); return <TD key={p} className="whitespace-nowrap text-right tabular-nums">{m ? <>{formatAmount(m.debit)} <span className="text-xs text-muted-foreground">({m.entries})</span></> : ""}</TD>; })}
            <TD className="text-right font-medium tabular-nums">{formatAmount(j.debit)}</TD>
          </TR>))}
        </TBody>
      </Table>
    </div>
  );
}

export function LedgerAnalyticsPanel({ base }: { base: string }) {
  const [multiple, setMultiple] = useState("");
  const [bmin, setBmin] = useState("");
  const [params, setParams] = useState({ m: "", b: "" });
  const qs = new URLSearchParams();
  if (params.m) qs.set("round_multiple", params.m.replace(",", "."));
  if (params.b) qs.set("benford_min", params.b.replace(",", "."));
  const { data, error, loading } = useApiResource<LedgerAnalytics>(`${base}/analytics?${qs.toString()}`);
  return (
    <div className="space-y-4">
      <form className="flex flex-wrap items-end gap-3" onSubmit={(x) => { x.preventDefault(); setParams({ m: multiple, b: bmin }); }}>
        <Field label="Montants ronds : multiple de" htmlFor="an-m"><Input id="an-m" className="w-40" inputMode="decimal" value={multiple} onChange={(x) => setMultiple(x.target.value)} placeholder="ex. 100000" /></Field>
        <Field label="Benford : montant minimal" htmlFor="an-b"><Input id="an-b" className="w-40" inputMode="decimal" value={bmin} onChange={(x) => setBmin(x.target.value)} placeholder="0" /></Field>
        <Button type="submit" variant="outline">Analyser</Button>
      </form>
      {error && <Alert>{error}</Alert>}
      {loading && !data && <Loading />}
      {data && (
        <>
          <Alert kind="info">{data.notes.join(" ")}</Alert>
          <div className="grid gap-3 sm:grid-cols-4">
            {[["Écritures datées un samedi ou un dimanche", data.weekend_entries.count], ["Doublons possibles", data.possible_duplicates.length],
              ["Lignes sans libellé", data.lines_without_label], ["Validées après la fin de l'exercice", data.validated_after_year_end ?? "date de validation absente"]].map(([l, v]) => (
              <Card key={String(l)}><CardContent className="pt-4"><p className="text-xs text-muted-foreground">{l}</p><p className="text-xl font-semibold tabular-nums">{v}</p></CardContent></Card>
            ))}
          </div>
          <Card>
            <CardHeader><CardTitle>Premier chiffre des montants (loi de Benford)</CardTitle><CardDescription>{data.benford.count} montant(s) analysé(s){data.benford.min_amount !== "0" && `, à partir de ${formatAmount(data.benford.min_amount)}`}.</CardDescription></CardHeader>
            <CardContent>
              <div className="space-y-1">
                {data.benford.digits.map((d) => (
                  <div key={d.digit} className="grid grid-cols-[1.5rem_minmax(0,1fr)_7rem] items-center gap-2 text-xs">
                    <span className="font-medium">{d.digit}</span>
                    <div className="relative h-4 rounded bg-muted" aria-hidden>
                      <div className="absolute inset-y-0 left-0 rounded bg-primary/70" style={{ width: `${Math.min(100, Number(d.observed_pct ?? 0) * 2)}%` }} />
                      <div className="absolute inset-y-0 w-0.5 bg-foreground" style={{ left: `${Math.min(100, Number(d.expected_pct) * 2)}%` }} />
                    </div>
                    <span className="tabular-nums">{d.observed_pct ?? "—"} % / {d.expected_pct} %</span>
                  </div>
                ))}
              </div>
              <p className="mt-2 text-xs text-muted-foreground">Barre : fréquence observée ; trait : fréquence attendue. Échelle : 50 % = largeur totale.</p>
            </CardContent>
          </Card>
          {data.round_amounts && (
            <Card>
              <CardHeader><CardTitle>Montants multiples de {formatAmount(data.round_amounts.multiple)}</CardTitle><CardDescription>{data.round_amounts.count} ligne(s){data.round_amounts.count > data.round_amounts.lines.length && ` (les ${data.round_amounts.lines.length} plus élevées affichées)`}.</CardDescription></CardHeader>
              <CardContent><Table><THead><tr><TH>Date</TH><TH>Écriture</TH><TH>Compte</TH><TH>Libellé</TH><TH className="text-right">Montant</TH></tr></THead>
                <TBody>{data.round_amounts.lines.map((l, i) => <TR key={i}><TD>{formatDate(l.entry_date)}</TD><TD>{l.journal}/{l.entry_number}</TD><TD>{l.account_number}</TD><TD>{l.label}</TD><TD className="text-right tabular-nums">{formatAmount(Number(l.debit) ? l.debit : l.credit)}</TD></TR>)}</TBody></Table></CardContent>
            </Card>
          )}
          {data.possible_duplicates.length > 0 && (
            <Card>
              <CardHeader><CardTitle>Doublons possibles</CardTitle></CardHeader>
              <CardContent><Table><THead><tr><TH>Compte</TH><TH>Date</TH><TH>Libellé</TH><TH className="text-right">Débit</TH><TH className="text-right">Crédit</TH><TH className="text-right">Écritures</TH></tr></THead>
                <TBody>{data.possible_duplicates.map((d, i) => <TR key={i}><TD>{d.account_number}</TD><TD>{formatDate(d.entry_date)}</TD><TD>{d.label}</TD><TD className="text-right tabular-nums">{formatAmount(d.debit, { blankZero: true })}</TD><TD className="text-right tabular-nums">{formatAmount(d.credit, { blankZero: true })}</TD><TD className="text-right">{d.entries}</TD></TR>)}</TBody></Table></CardContent>
            </Card>
          )}
          <Card>
            <CardHeader><CardTitle>Numérotation des écritures</CardTitle></CardHeader>
            <CardContent className="space-y-1 text-sm">
              {data.numbering_gaps.length === 0 && <p className="text-muted-foreground">Aucun numéro d&apos;écriture.</p>}
              {data.numbering_gaps.map((g) => (
                <p key={g.journal}><span className="font-medium">{g.journal || "—"}</span> : {g.numeric}/{g.total} numéros numériques ·{" "}
                  {g.gaps.length ? `trous : ${g.gaps.map((x) => (x.from === x.to ? x.from : `${x.from}–${x.to}`)).join(", ")}` : "aucun trou"}</p>
              ))}
            </CardContent>
          </Card>
          {data.weekend_entries.entries.length > 0 && (
            <Card>
              <CardHeader><CardTitle>Écritures datées un samedi ou un dimanche</CardTitle></CardHeader>
              <CardContent><Table><THead><tr><TH>Date</TH><TH>Jour</TH><TH>Écriture</TH><TH className="text-right">Lignes</TH><TH className="text-right">Débit</TH></tr></THead>
                <TBody>{data.weekend_entries.entries.map((w, i) => <TR key={i}><TD>{formatDate(w.entry_date)}</TD><TD>{w.weekday}</TD><TD>{w.journal}/{w.entry_number ?? "—"}</TD><TD className="text-right">{w.lines}</TD><TD className="text-right tabular-nums">{formatAmount(w.debit)}</TD></TR>)}</TBody></Table></CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}

