"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { AlertTriangle, CheckCircle2, ChevronLeft, CircleSlash, Download, Info, XCircle } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { IMPORT_STATUS_LABELS, type ControlResult, type ImportJob, type SheetMeta, type StagingRow } from "@/lib/types";
import { cn, formatAmount } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, Badge, Loading, PageHeader } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { METHOD_LABELS, statusTone } from "../../imports-tab";

const RUNNING = new Set(["pending", "parsing", "validating"]);
const GROUP_LABELS: Record<string, string> = { opening: "Ouverture", movement: "Mouvements", closing: "Clôture" };
const colName = (j: number) => (j < 26 ? String.fromCharCode(65 + j) : `${String.fromCharCode(64 + Math.floor(j / 26))}${String.fromCharCode(65 + (j % 26))}`);

interface Options {
  signed_balance_convention: "debit_positive" | "credit_positive";
  decimal_separator: "" | "," | ".";
  negative_amounts: "error" | "move_to_other_side";
  skip_zero_rows: boolean;
  exclude_aggregate_accounts: boolean;
  balance_tolerance: string;
}
const DEFAULT_OPTIONS: Options = {
  signed_balance_convention: "debit_positive", decimal_separator: "", negative_amounts: "error",
  skip_zero_rows: true, exclude_aggregate_accounts: false, balance_tolerance: "0",
};

// ------------------------------------------------------------------ association des colonnes
function MappingStep({ job, onSubmitted }: { job: ImportJob; onSubmitted: (j: ImportJob) => void }) {
  const sheets = job.sheets ?? [];
  const [sheetName, setSheetName] = useState(job.sheet_name ?? sheets[0]?.name ?? "");
  const sheet: SheetMeta | undefined = sheets.find((s) => s.name === sheetName);
  const [headerRow, setHeaderRow] = useState<number>(job.header_row ?? sheet?.header_row ?? 0);
  const [columnMap, setColumnMap] = useState<Record<string, number>>(job.column_map ?? sheet?.suggested_mapping ?? {});
  const [options, setOptions] = useState<Options>({ ...DEFAULT_OPTIONS, ...(job.options as Partial<Options>) });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function selectSheet(name: string) {
    const s = sheets.find((x) => x.name === name);
    setSheetName(name);
    setHeaderRow(s?.header_row ?? 0);
    setColumnMap(s?.suggested_mapping ?? {});
  }

  const fieldOf = useMemo(() => Object.fromEntries(Object.entries(columnMap).map(([f, c]) => [c, f])), [columnMap]);
  const fields = Object.keys(job.field_labels);
  const hasSigned = Object.keys(columnMap).some((f) => f.endsWith("_balance"));

  function assign(col: number, field: string) {
    const next = Object.fromEntries(Object.entries(columnMap).filter(([f, c]) => c !== col && f !== field));
    if (field) next[field] = col;
    setColumnMap(next);
  }

  async function submit() {
    setSaving(true);
    setError(null);
    const opts: Record<string, unknown> = { ...options, decimal_separator: options.decimal_separator || null };
    try {
      onSubmitted(await api.post<ImportJob>(`/companies/${job.company_id}/imports/${job.id}/configure`, {
        sheet_name: sheetName, header_row: headerRow, column_map: columnMap, options: opts,
      }));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  if (!sheet) return <Alert>Aucune feuille lisible dans ce fichier.</Alert>;
  const width = Math.max(sheet.columns, ...sheet.preview.map((r) => r.length));

  return (
    <Card>
      <CardHeader>
        <CardTitle>1. Feuille, en-tête et colonnes</CardTitle>
        <CardDescription>
          Vérifiez l&apos;association proposée : choisissez pour chaque colonne le champ correspondant, ou « ignorer ».
          Cliquez sur un numéro de ligne pour la désigner comme ligne d&apos;en-tête.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Feuille" htmlFor="m-sheet">
            <Select id="m-sheet" value={sheetName} onChange={(e) => selectSheet(e.target.value)}>
              {sheets.map((s) => <option key={s.name} value={s.name}>{s.name} ({s.rows} lignes)</option>)}
            </Select>
          </Field>
          <Field label="Ligne d'en-tête" htmlFor="m-header">
            <Input id="m-header" type="number" min={1} max={sheet.rows} value={headerRow + 1}
                   onChange={(e) => setHeaderRow(Math.max(0, Number(e.target.value) - 1))} />
          </Field>
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
                    <Select aria-label={`Champ de la colonne ${colName(j)}`} className={cn("h-8 text-xs", fieldOf[j] && "border-primary")}
                            value={fieldOf[j] ?? ""} onChange={(e) => assign(j, e.target.value)}>
                      <option value="">— ignorer —</option>
                      {fields.map((f) => <option key={f} value={f}>{job.field_labels[f]}</option>)}
                    </Select>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y">
              {sheet.preview.map((row, i) => {
                const abs = sheet.preview_start + i;
                const isHeader = abs === headerRow;
                return (
                  <tr key={abs} className={cn(isHeader && "bg-selection font-semibold", abs < headerRow && "text-muted-foreground")}>
                    <td className="px-2 py-1.5">
                      <button type="button" onClick={() => setHeaderRow(abs)} title="Désigner comme en-tête"
                              className="rounded px-1 font-mono hover:bg-muted">{abs + 1}</button>
                    </td>
                    {Array.from({ length: width }, (_, j) => {
                      const conf = sheet.preview_confidence?.[i]?.[j];
                      return (
                        <td key={j} className={cn("whitespace-nowrap px-2 py-1.5", conf != null && conf < 80 && "bg-warning/10 text-foreground")}
                            title={conf != null ? `Confiance OCR : ${Math.round(conf)} %` : undefined}>
                          {row[j] === null || row[j] === undefined ? "" : String(row[j])}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {sheet.rows > sheet.preview_start + sheet.preview.length && (
          <p className="text-xs text-muted-foreground">Aperçu des {sheet.preview.length} premières lignes sur {sheet.rows}.</p>
        )}

        <details className="rounded-lg border p-4">
          <summary className="cursor-pointer text-sm font-medium">Options de lecture</summary>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <Field label="Séparateur décimal" htmlFor="o-sep" hint="« Automatique » déduit le séparateur des montants ; en cas d'ambiguïté, la ligne est signalée.">
              <Select id="o-sep" value={options.decimal_separator}
                      onChange={(e) => setOptions({ ...options, decimal_separator: e.target.value as Options["decimal_separator"] })}>
                <option value="">Automatique</option><option value=",">Virgule (1 234,56)</option><option value=".">Point (1,234.56)</option>
              </Select>
            </Field>
            {hasSigned && (
              <Field label="Convention du solde signé" htmlFor="o-sign">
                <Select id="o-sign" value={options.signed_balance_convention}
                        onChange={(e) => setOptions({ ...options, signed_balance_convention: e.target.value as Options["signed_balance_convention"] })}>
                  <option value="debit_positive">Positif = débiteur</option>
                  <option value="credit_positive">Positif = créditeur</option>
                </Select>
              </Field>
            )}
            <Field label="Montants négatifs dans les colonnes débit/crédit" htmlFor="o-neg">
              <Select id="o-neg" value={options.negative_amounts}
                      onChange={(e) => setOptions({ ...options, negative_amounts: e.target.value as Options["negative_amounts"] })}>
                <option value="error">Signaler en erreur</option>
                <option value="move_to_other_side">Reporter dans la colonne opposée</option>
              </Select>
            </Field>
            <Field label="Tolérance d'équilibre" htmlFor="o-tol" hint="0 = contrôle strict. Un écart toléré reste signalé et doit être accepté.">
              <Input id="o-tol" inputMode="decimal" value={options.balance_tolerance}
                     onChange={(e) => setOptions({ ...options, balance_tolerance: e.target.value.replace(",", ".") })} />
            </Field>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={options.skip_zero_rows}
                     onChange={(e) => setOptions({ ...options, skip_zero_rows: e.target.checked })} />
              Ignorer les comptes sans aucun montant
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={options.exclude_aggregate_accounts}
                     onChange={(e) => setOptions({ ...options, exclude_aggregate_accounts: e.target.checked })} />
              Exclure les comptes de regroupement (totaux de sous-comptes)
            </label>
          </div>
        </details>

        <div className="flex justify-end">
          <Button onClick={submit} loading={saving}>Lancer la lecture et les contrôles</Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------ contrôles
function ControlIcon({ r }: { r: ControlResult }) {
  if (r.status === "passed") return <CheckCircle2 className="h-4 w-4 text-success" aria-label="Réussi" />;
  if (r.status === "skipped") return <CircleSlash className="h-4 w-4 text-muted-foreground" aria-label="Non exécuté" />;
  if (r.severity === "error") return <XCircle className="h-4 w-4 text-destructive" aria-label="Bloquant" />;
  if (r.severity === "warning") return <AlertTriangle className="h-4 w-4 text-warning" aria-label="Avertissement" />;
  return <Info className="h-4 w-4 text-info" aria-label="Information" />;
}

function ControlsStep({ job, onConfirmed }: { job: ImportJob; onConfirmed: (j: ImportJob) => void }) {
  const controls = job.controls!;
  const { data: rows } = useApiResource<{ total: number; items: StagingRow[] }>(
    `/companies/${job.company_id}/imports/${job.id}/rows?status_filter=issues&limit=200`);
  const [ack, setAck] = useState(false);
  const [saveAs, setSaveAs] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const editable = job.status === "awaiting_confirmation";

  async function confirm() {
    setSaving(true);
    setError(null);
    try {
      onConfirmed(await api.post<ImportJob>(`/companies/${job.company_id}/imports/${job.id}/confirm`, {
        acknowledge_warnings: ack, save_mapping_as: saveAs.trim() || null,
      }));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  const ordered = [...controls.results].sort((a, b) => {
    const rank = (r: ControlResult) => (r.status === "failed" ? (r.severity === "error" ? 0 : 1) : r.status === "skipped" ? 3 : 2);
    return rank(a) - rank(b);
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>2. Contrôles de cohérence</CardTitle>
        <CardDescription>
          {job.valid_rows} compte(s) lus{job.error_rows ? `, ${job.error_rows} ligne(s) en erreur` : ""} sur {job.total_rows} ligne(s).
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {Object.keys(controls.totals).length > 0 && (
          <Table>
            <THead><tr><TH /><TH className="text-right">Total débit</TH><TH className="text-right">Total crédit</TH><TH className="text-right">Écart</TH></tr></THead>
            <TBody>
              {Object.entries(controls.totals).map(([g, t]) => (
                <TR key={g}>
                  <TD className="font-medium">{GROUP_LABELS[g] ?? g}</TD>
                  <TD className="text-right tabular-nums">{formatAmount(t.debit)}</TD>
                  <TD className="text-right tabular-nums">{formatAmount(t.credit)}</TD>
                  <TD className={cn("text-right tabular-nums", t.difference !== "0.00" && "font-semibold text-destructive")}>{formatAmount(t.difference)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}

        <ul className="divide-y rounded-lg border">
          {ordered.map((r) => (
            <li key={r.code} className="flex gap-3 px-4 py-3">
              <ControlIcon r={r} />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{r.title}</p>
                <p className="text-sm text-muted-foreground">{r.message}</p>
                {r.status === "failed" && Object.keys(r.details).length > 0 && (
                  <details className="mt-1">
                    <summary className="cursor-pointer text-xs text-link">Détail</summary>
                    <pre className="mt-1 max-h-64 overflow-auto rounded bg-muted p-2 text-xs">{JSON.stringify(r.details, null, 2)}</pre>
                  </details>
                )}
              </div>
            </li>
          ))}
        </ul>

        {rows && rows.total > 0 && (
          <div>
            <p className="mb-2 text-sm font-medium">Lignes signalées ({rows.total})</p>
            <Table>
              <THead><tr><TH>Ligne</TH><TH>Compte</TH><TH>Libellé</TH><TH className="text-right">Débit</TH><TH className="text-right">Crédit</TH><TH>Observation</TH></tr></THead>
              <TBody>
                {rows.items.map((r) => (
                  <TR key={r.source_row} className={cn(r.status === "error" && "bg-destructive/5")}>
                    <TD className="font-mono text-xs">{r.source_row}{r.source_page ? ` (p. ${r.source_page})` : ""}</TD>
                    <TD className="font-mono">{r.account_number ?? "—"}</TD>
                    <TD className="max-w-xs truncate">{r.account_label}</TD>
                    <TD className="text-right tabular-nums">{formatAmount(r.closing_debit, { blankZero: true })}</TD>
                    <TD className="text-right tabular-nums">{formatAmount(r.closing_credit, { blankZero: true })}</TD>
                    <TD className="text-xs">{r.issues.map((i) => i.message).join(" ; ")}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </div>
        )}

        {editable && (
          <div className="space-y-3 border-t pt-4">
            {error && <Alert>{error}</Alert>}
            {controls.blocking ? (
              <Alert>Des contrôles bloquants ont échoué : corrigez le fichier ou l&apos;association des colonnes avant de valider.</Alert>
            ) : (
              <>
                {controls.requires_acknowledgment && (
                  <label className="flex items-start gap-2 rounded-md border border-warning/40 bg-warning/10 p-3 text-sm text-foreground">
                    <input type="checkbox" className="mt-0.5" checked={ack} onChange={(e) => setAck(e.target.checked)} />
                    J&apos;ai examiné les avertissements ci-dessus et je confirme que la balance peut être retenue.
                    Cette acceptation est enregistrée dans le journal d&apos;audit.
                  </label>
                )}
                <Field label="Enregistrer cette association comme modèle (facultatif)" htmlFor="c-save"
                       hint="Le modèle sera proposé automatiquement lors des prochains imports de cette entreprise.">
                  <Input id="c-save" value={saveAs} maxLength={120} placeholder="Ex. Export logiciel comptable"
                         onChange={(e) => setSaveAs(e.target.value)} />
                </Field>
                <div className="flex justify-end">
                  <Button onClick={confirm} loading={saving} disabled={controls.requires_acknowledgment && !ack}>
                    Valider la balance de l&apos;exercice
                  </Button>
                </div>
              </>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------ page
export default function ImportWizardPage() {
  const { companyId, jobId } = useParams<{ companyId: string; jobId: string }>();
  const router = useRouter();
  const { data: job, error, loading, reload, setData } = useApiResource<ImportJob>(`/companies/${companyId}/imports/${jobId}`);
  const [reconfigure, setReconfigure] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    if (!job || !RUNNING.has(job.status)) return;
    const t = setTimeout(() => void reload(), 2000);
    return () => clearTimeout(t);
  }, [job, reload]);

  if (loading && !job) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  if (!job) return null;

  async function cancel() {
    if (!window.confirm("Annuler cet import ? Le fichier original reste conservé.")) return;
    setBusy(true);
    try {
      setData(await api.post<ImportJob>(`/companies/${companyId}/imports/${jobId}/cancel`));
    } catch (err) {
      setActionError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function download() {
    try {
      const { url } = await api.get<{ url: string }>(`/companies/${companyId}/documents/${job!.document_id}/download`);
      window.open(url, "_blank", "noopener");
    } catch (err) {
      setActionError(errorMessage(err));
    }
  }

  const ext = job.extraction ?? {};
  const showMapping = job.status === "awaiting_mapping" || (job.status === "failed" && !!job.sheets) || reconfigure;
  const showControls = !!job.controls && !reconfigure && ["awaiting_confirmation", "completed", "superseded"].includes(job.status);

  return (
    <>
      <Link href={`/companies/${companyId}`} className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ChevronLeft className="h-4 w-4" /> Entreprise
      </Link>
      <PageHeader
        title={ext.filename ?? "Importation"}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <Badge tone={statusTone(job.status)}>{IMPORT_STATUS_LABELS[job.status]}</Badge>
            {ext.method && <span>{METHOD_LABELS[ext.method] ?? ext.method}</span>}
            {ext.page_count ? <span>· {ext.page_count} page(s)</span> : null}
            {!job.framework_version_id && <Badge tone="amber">Aucune version de référentiel publiée applicable</Badge>}
          </span>
        }
        actions={
          <>
            {job.document_id && <Button variant="outline" size="sm" onClick={download}><Download className="h-4 w-4" /> Fichier original</Button>}
            {job.status === "awaiting_confirmation" && !reconfigure && (
              <Button variant="outline" size="sm" onClick={() => setReconfigure(true)}>Modifier l&apos;association</Button>
            )}
            {["awaiting_mapping", "awaiting_confirmation", "failed"].includes(job.status) && (
              <Button variant="ghost" size="sm" className="text-destructive" loading={busy} onClick={cancel}>Annuler l&apos;import</Button>
            )}
          </>
        }
      />
      <div className="space-y-4">
        {actionError && <Alert>{actionError}</Alert>}
        {ext.duplicate_of_document && job.status !== "completed" && (
          <Alert kind="info">Ce fichier est identique (même empreinte) à un fichier déjà déposé pour cette entreprise.</Alert>
        )}
        {RUNNING.has(job.status) && <Loading label={IMPORT_STATUS_LABELS[job.status]} />}
        {job.status === "failed" && <Alert>{job.failure_reason ?? "Le traitement a échoué."}</Alert>}
        {job.status === "completed" && (
          <Alert kind="success">
            Balance validée : elle constitue désormais la balance de l&apos;exercice.{" "}
            <Link className="font-medium underline" href={`/companies/${companyId}/fiscal-years/${job.fiscal_year_id}/balance`}>Consulter la balance</Link>
          </Alert>
        )}
        {job.status === "superseded" && <Alert kind="info">Cet import a été remplacé par un import plus récent.</Alert>}
        {showMapping && (
          <MappingStep job={job} onSubmitted={(j) => { setReconfigure(false); setData(j); }} />
        )}
        {showControls && <ControlsStep job={job} onConfirmed={(j) => { setData(j); router.refresh(); }} />}
      </div>
    </>
  );
}
