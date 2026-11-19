"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { AlertTriangle, CheckCircle2, ChevronLeft, CircleSlash, Info, XCircle } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { IMPORT_STATUS_LABELS, type ControlResult } from "@/lib/types";
import type { ComplementSummary, LedgerJob, LedgerLineRow, LedgerOptions } from "@/lib/ledger-types";
import { cn, formatAmount, formatDate } from "@/lib/utils";
import { statusTone } from "../../../imports-tab";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, Badge, Loading, PageHeader } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const RUNNING = new Set(["pending", "parsing", "validating"]);
const DEFAULTS: LedgerOptions = { decimal_separator: null, amount_sign: null, negative_amounts: "error", opening_journals: [], skip_zero_lines: true, mode: "replace" };
const colName = (j: number) => (j < 26 ? String.fromCharCode(65 + j) : `${String.fromCharCode(64 + Math.floor(j / 26))}${String.fromCharCode(65 + (j % 26))}`);

function MappingStep({ job, onSubmitted }: { job: LedgerJob; onSubmitted: (j: LedgerJob) => void }) {
  const sheets = job.sheets ?? [];
  const [sheetName, setSheetName] = useState(job.sheet_name ?? sheets[0]?.name ?? "");
  const sheet = sheets.find((s) => s.name === sheetName);
  const [headerRow, setHeaderRow] = useState(job.header_row ?? sheet?.header_row ?? 0);
  const [cm, setCm] = useState<Record<string, number>>(job.column_map ?? sheet?.suggested_mapping ?? {});
  const [o, setO] = useState<LedgerOptions>({ ...DEFAULTS, ...job.options });
  const [journals, setJournals] = useState((job.options.opening_journals ?? []).join(", "));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fieldOf = useMemo(() => Object.fromEntries(Object.entries(cm).map(([f, c]) => [c, f])), [cm]);
  if (!sheet) return <Alert>Aucune feuille lisible dans ce fichier.</Alert>;
  const width = Math.max(sheet.columns, ...sheet.preview.map((r) => r.length));
  const signed = "amount" in cm && !("direction" in cm);

  function assign(col: number, field: string) {
    const next = Object.fromEntries(Object.entries(cm).filter(([f, c]) => c !== col && f !== field));
    if (field) next[field] = col;
    setCm(next);
  }
  async function submit() {
    setSaving(true); setError(null);
    try {
      onSubmitted(await api.post<LedgerJob>(`/companies/${job.company_id}/ledger-imports/${job.id}/configure`, {
        sheet_name: sheetName, header_row: headerRow, column_map: cm,
        options: { ...o, amount_sign: signed ? o.amount_sign : null, opening_journals: journals.split(/[,;\s]+/).filter(Boolean) } }));
    } catch (x) { setError(errorMessage(x)); } finally { setSaving(false); }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>1. Feuille, en-tête et colonnes</CardTitle>
        <CardDescription>Associez chaque colonne à un champ. Requis : date d&apos;écriture, n° de compte, et soit Débit et Crédit, soit Montant (avec Sens ou une convention de signe). Le numéro d&apos;écriture permet de contrôler l&apos;équilibre de chaque écriture.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Feuille" htmlFor="l-sheet">
            <Select id="l-sheet" value={sheetName} onChange={(x) => { const s = sheets.find((y) => y.name === x.target.value); setSheetName(x.target.value); setHeaderRow(s?.header_row ?? 0); setCm(s?.suggested_mapping ?? {}); }}>
              {sheets.map((s) => <option key={s.name} value={s.name}>{s.name} ({s.rows} lignes)</option>)}
            </Select>
          </Field>
          <Field label="Ligne d'en-tête" htmlFor="l-h"><Input id="l-h" type="number" min={1} value={headerRow + 1} onChange={(x) => setHeaderRow(Math.max(0, Number(x.target.value) - 1))} /></Field>
        </div>
        {[...sheet.warnings, ...sheet.notes].map((w) => <Alert key={w} kind="info">{w}</Alert>)}
        <div className="overflow-x-auto rounded-lg border">
          <table className="min-w-full text-xs">
            <thead className="bg-muted/60">
              <tr>
                <th className="w-12 px-2 py-2 text-left text-muted-foreground">Ligne</th>
                {Array.from({ length: width }, (_, j) => (
                  <th key={j} className="min-w-[140px] px-2 py-2 text-left align-bottom">
                    <div className="mb-1 font-mono text-muted-foreground">{colName(j)}</div>
                    <Select aria-label={`Champ de la colonne ${colName(j)}`} className={cn("h-8 text-xs", fieldOf[j] && "border-primary")} value={fieldOf[j] ?? ""} onChange={(x) => assign(j, x.target.value)}>
                      <option value="">— ignorer —</option>
                      {job.fields.map((f) => <option key={f} value={f}>{job.field_labels[f]}</option>)}
                    </Select>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sheet.preview.map((r, i) => {
                const idx = sheet.preview_start + i;
                return (
                  <tr key={idx} className={cn("border-t", idx === headerRow && "bg-primary/10 font-medium", idx < headerRow && "text-muted-foreground")}>
                    <td className="px-2 py-1"><button className="font-mono hover:underline" onClick={() => setHeaderRow(idx)} aria-label={`Ligne ${idx + 1} comme en-tête`}>{idx + 1}</button></td>
                    {Array.from({ length: width }, (_, j) => <td key={j} className="whitespace-nowrap px-2 py-1">{r[j] === null || r[j] === undefined ? "" : String(r[j])}</td>)}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Séparateur décimal" htmlFor="l-sep">
            <Select id="l-sep" value={o.decimal_separator ?? ""} onChange={(x) => setO({ ...o, decimal_separator: (x.target.value || null) as LedgerOptions["decimal_separator"] })}>
              <option value="">Déduit des données</option><option value=",">Virgule</option><option value=".">Point</option>
            </Select>
          </Field>
          {signed && (
            <Field label="Montant signé : un montant positif est un…" htmlFor="l-sign" required>
              <Select id="l-sign" value={o.amount_sign ?? ""} onChange={(x) => setO({ ...o, amount_sign: (x.target.value || null) as LedgerOptions["amount_sign"] })}>
                <option value="">Choisir…</option><option value="debit_positive">débit</option><option value="credit_positive">crédit</option>
              </Select>
            </Field>
          )}
          <Field label="Montants négatifs dans Débit / Crédit" htmlFor="l-neg">
            <Select id="l-neg" value={o.negative_amounts} onChange={(x) => setO({ ...o, negative_amounts: x.target.value as LedgerOptions["negative_amounts"] })}>
              <option value="error">Signaler en erreur</option><option value="move_to_other_side">Reporter sur l&apos;autre colonne</option>
            </Select>
          </Field>
          <Field label="Effet de l'import" htmlFor="l-mode" hint="Complément : seules les lignes nouvelles sont ajoutées au grand livre validé ; les doublons sont écartés et une écriture modifiée est refusée (utilisez alors un remplacement).">
            <Select id="l-mode" value={o.mode ?? "replace"} onChange={(x) => setO({ ...o, mode: x.target.value as LedgerOptions["mode"] })}>
              <option value="replace">Remplacer le grand livre validé (fichier complet ou correctif)</option>
              <option value="complement">Compléter le grand livre validé (fichier complémentaire)</option>
            </Select>
          </Field>
          <Field label="Journaux d'à-nouveaux (codes)" htmlFor="l-an" hint="Séparés par des virgules ; servent au rapprochement avec les soldes d'ouverture de la balance.">
            <Input id="l-an" value={journals} onChange={(x) => setJournals(x.target.value)} placeholder="ex. AN" />
          </Field>
        </div>
        <div className="flex justify-end"><Button onClick={submit} loading={saving}>Lire et contrôler</Button></div>
      </CardContent>
    </Card>
  );
}

function ControlIcon({ r }: { r: ControlResult }) {
  if (r.status === "passed") return <CheckCircle2 className="h-4 w-4 text-success" aria-label="Réussi" />;
  if (r.status === "skipped") return <CircleSlash className="h-4 w-4 text-muted-foreground" aria-label="Non exécuté" />;
  if (r.severity === "error") return <XCircle className="h-4 w-4 text-destructive" aria-label="Bloquant" />;
  if (r.severity === "warning") return <AlertTriangle className="h-4 w-4 text-warning" aria-label="Avertissement" />;
  return <Info className="h-4 w-4 text-info" aria-label="Information" />;
}

function Details({ r }: { r: ControlResult }) {
  const d = r.details as Record<string, unknown>;
  const list = (d.rows ?? d.entries ?? d.accounts) as Record<string, unknown>[] | string[] | undefined;
  if (!list || !list.length) return null;
  return (
    <ul className="mt-1 max-h-40 overflow-y-auto text-xs text-muted-foreground">
      {list.map((x, i) => <li key={i}>{typeof x === "string" ? x : Object.entries(x).map(([k, v]) => `${k} : ${Array.isArray(v) ? v.join(" ; ") : String(v)}`).join(" · ")}</li>)}
    </ul>
  );
}

function ControlsStep({ job, onConfirmed }: { job: LedgerJob; onConfirmed: (j: LedgerJob) => void }) {
  const c = job.controls!;
  const { data: errs } = useApiResource<{ total: number; items: LedgerLineRow[] }>(`/companies/${job.company_id}/ledger-imports/${job.id}/lines?status_filter=error&limit=200`);
  const [ack, setAck] = useState(false);
  const [saveAs, setSaveAs] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const done = ["completed", "superseded"].includes(job.status);
  async function confirm() {
    setSaving(true); setError(null);
    try { onConfirmed(await api.post<LedgerJob>(`/companies/${job.company_id}/ledger-imports/${job.id}/confirm`, { acknowledge_warnings: ack, save_mapping_as: saveAs || null })); }
    catch (x) { setError(errorMessage(x)); } finally { setSaving(false); }
  }
  const t = c.totals.ledger;
  return (
    <Card>
      <CardHeader>
        <CardTitle>2. Contrôles</CardTitle>
        <CardDescription>{job.valid_rows} ligne(s) valides, {job.error_rows} en erreur sur {job.total_rows}{t && ` · débit ${formatAmount(t.debit)} · crédit ${formatAmount(t.credit)}`}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && <Alert>{error}</Alert>}
        {c.complement && (() => {
          const k: ComplementSummary = c.complement;
          return (
            <Alert kind={k.conflicts ? "warning" : "info"}>
              Import complémentaire : {k.carried} ligne(s) reprises du grand livre validé, {k.added} ligne(s) nouvelles ajoutées,
              {" "}{k.duplicates} doublon(s) écartés{k.conflicts ? `, ${k.conflicts} ligne(s) d'écritures modifiées refusées (import de remplacement nécessaire)` : ""}.
              {k.added_months.length > 0 && ` Mois complétés : ${k.added_months.join(", ")}.`}
              {k.overlapping_months.length > 0 && ` Attention : des lignes nouvelles portent sur des mois déjà importés (${k.overlapping_months.join(", ")}).`}
            </Alert>
          );
        })()}
        <ul className="space-y-2">
          {c.results.map((r) => (
            <li key={r.code} className="flex gap-2 text-sm"><ControlIcon r={r} /><div><p className="font-medium">{r.title}</p><p className="text-muted-foreground">{r.message}</p><Details r={r} /></div></li>
          ))}
        </ul>
        {errs && errs.total > 0 && (
          <Table>
            <THead><tr><TH>Ligne</TH><TH>Anomalies</TH></tr></THead>
            <TBody>{errs.items.map((l) => <TR key={l.source_row}><TD>{l.source_row}</TD><TD>{l.issues?.map((i) => i.message).join(" ; ")}</TD></TR>)}</TBody>
          </Table>
        )}
        {!done && (c.blocking ? <Alert>Des contrôles bloquants ont échoué : corrigez le fichier ou l&apos;association des colonnes, puis relancez la lecture.</Alert> : (
          <div className="space-y-3 border-t pt-4">
            {c.requires_acknowledgment && (
              <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-0.5 h-4 w-4" checked={ack} onChange={(x) => setAck(x.target.checked)} />
                J&apos;ai examiné les avertissements (comptes hors plan, écarts avec la balance) et je valide ce grand livre en connaissance de cause.</label>
            )}
            <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
              <Field label="Enregistrer l'association des colonnes (facultatif)" htmlFor="l-save"><Input id="l-save" value={saveAs} onChange={(x) => setSaveAs(x.target.value)} placeholder="ex. Export logiciel comptable" /></Field>
              <Button onClick={confirm} loading={saving} disabled={c.requires_acknowledgment && !ack}>Valider le grand livre de l&apos;exercice</Button>
            </div>
          </div>
        ))}
        {done && <Alert kind="success">Grand livre validé le {formatDate(job.validated_at)}{job.status === "superseded" && " — remplacé depuis par un import plus récent"}.</Alert>}
      </CardContent>
    </Card>
  );
}

export default function LedgerImportPage() {
  const { companyId, jobId } = useParams<{ companyId: string; jobId: string }>();
  const { data: job, error, loading, reload, setData } = useApiResource<LedgerJob>(`/companies/${companyId}/ledger-imports/${jobId}`);
  const [reconfigure, setReconfigure] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (!job || !RUNNING.has(job.status)) return;
    const t = setTimeout(() => void reload(), 2000);
    return () => clearTimeout(t);
  }, [job, reload]);
  if (loading && !job) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  if (!job) return null;
  const showMapping = job.status === "awaiting_mapping" || (job.status === "failed" && !!job.sheets) || reconfigure;
  const showControls = !!job.controls && !reconfigure && ["awaiting_confirmation", "completed", "superseded"].includes(job.status);
  const filename = String((job.extraction ?? {}).filename ?? "Grand livre");
  return (
    <>
      <Link href={`/companies/${companyId}/grand-livre`} className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ChevronLeft className="h-4 w-4" /> Grand livre</Link>
      <PageHeader title={`Import du grand livre — ${filename}`}
                  description={<Badge tone={statusTone(job.status)}>{IMPORT_STATUS_LABELS[job.status]}</Badge>}
                  actions={<>
                    {job.status === "awaiting_confirmation" && !reconfigure && <Button size="sm" variant="outline" onClick={() => setReconfigure(true)}>Modifier l&apos;association</Button>}
                    {!["completed", "superseded", "cancelled"].includes(job.status) && <Button size="sm" variant="ghost" onClick={async () => {
                      try { setData(await api.post<LedgerJob>(`/companies/${companyId}/ledger-imports/${jobId}/cancel`)); } catch (x) { setErr(errorMessage(x)); } }}>Annuler l&apos;import</Button>}
                  </>} />
      {err && <Alert className="mb-4">{err}</Alert>}
      {job.failure_reason && <Alert className="mb-4">{job.failure_reason}</Alert>}
      {RUNNING.has(job.status) && <Loading label="Lecture et contrôles en cours…" />}
      <div className="space-y-5">
        {showMapping && <MappingStep job={job} onSubmitted={(j) => { setData(j); setReconfigure(false); }} />}
        {showControls && <ControlsStep job={job} onConfirmed={setData} />}
      </div>
    </>
  );
}

