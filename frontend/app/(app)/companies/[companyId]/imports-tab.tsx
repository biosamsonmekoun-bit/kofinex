"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Upload } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { IMPORT_STATUS_LABELS, type Company, type FiscalYear, type ImportJob, type ImportListItem,
  type ImportStatus } from "@/lib/types";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const ACCEPT = ".xlsx,.xls,.csv,.pdf";
const METHOD_LABELS: Record<string, string> = {
  spreadsheet: "Tableur", csv: "CSV", pdf_text: "PDF", pdf_ocr: "PDF numérisé (OCR)", pdf_mixed: "PDF (dont OCR)",
};

export function statusTone(s: ImportStatus): "neutral" | "blue" | "green" | "amber" | "red" {
  if (s === "completed") return "green";
  if (s === "failed") return "red";
  if (s === "awaiting_confirmation" || s === "awaiting_mapping") return "amber";
  if (s === "parsing" || s === "validating" || s === "pending") return "blue";
  return "neutral";
}

function NewImportForm({ company, onCreated }: { company: Company; onCreated: (job: ImportJob) => void }) {
  const { data: years } = useApiResource<FiscalYear[]>(`/companies/${company.id}/fiscal-years`);
  const openYears = (years ?? []).filter((y) => y.status === "open");
  const [fy, setFy] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setSaving(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    form.append("fiscal_year_id", fy || openYears[0]?.id || "");
    try {
      onCreated(await api.upload<ImportJob>(`/companies/${company.id}/imports`, form));
    } catch (err) {
      setError(errorMessage(err));
      setSaving(false);
    }
  }

  if (years && openYears.length === 0) {
    return <Alert kind="info">Aucun exercice ouvert : créez d&apos;abord un exercice dans l&apos;onglet « Exercices ».</Alert>;
  }
  return (
    <form onSubmit={submit} className="space-y-4">
      {error && <Alert>{error}</Alert>}
      <Field label="Exercice" htmlFor="imp-fy" required>
        <Select id="imp-fy" value={fy || openYears[0]?.id || ""} onChange={(e) => setFy(e.target.value)}>
          {openYears.map((y) => <option key={y.id} value={y.id}>{y.label} ({formatDate(y.start_date)} → {formatDate(y.end_date)})</option>)}
        </Select>
      </Field>
      <Field label="Balance générale" htmlFor="imp-file" required
             hint="Excel (.xlsx, .xls), CSV ou PDF — y compris PDF numérisé (lecture par OCR). Le fichier original est conservé tel quel.">
        <Input id="imp-file" type="file" accept={ACCEPT} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </Field>
      <div className="flex justify-end">
        <Button type="submit" loading={saving} disabled={!file || !(fy || openYears[0])}>
          <Upload className="h-4 w-4" /> Déposer et analyser
        </Button>
      </div>
    </form>
  );
}

export function ImportsTab({ company }: { company: Company }) {
  const router = useRouter();
  const { data: jobs, error, loading } = useApiResource<ImportListItem[]>(`/companies/${company.id}/imports`);
  const [open, setOpen] = useState(false);
  const canImport = company.my_permissions.includes("import.write");

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <p className="text-sm text-muted-foreground">
          Chaque import est contrôlé (équilibres, totaux, doublons, plan de comptes) avant de devenir la balance de
          l&apos;exercice. Les imports précédents restent consultables.
        </p>
        {canImport && <Button size="sm" onClick={() => setOpen(true)}><Upload className="h-4 w-4" /> Nouvelle importation</Button>}
      </div>
      {loading && !jobs && <Loading />}
      {error && <Alert>{error}</Alert>}
      {jobs && jobs.length === 0 && (
        <EmptyState title="Aucune importation" description="Déposez la balance générale d'un exercice pour commencer." />
      )}
      {jobs && jobs.length > 0 && (
        <Table>
          <THead><tr><TH>Fichier</TH><TH>Exercice</TH><TH>Lecture</TH><TH>Lignes</TH><TH>Statut</TH><TH>Déposé le</TH></tr></THead>
          <TBody>
            {jobs.map((j) => (
              <TR key={j.id} className="cursor-pointer" onClick={() => router.push(`/companies/${company.id}/imports/${j.id}`)}>
                <TD><Link href={`/companies/${company.id}/imports/${j.id}`} className="font-medium hover:underline">{j.filename ?? "—"}</Link></TD>
                <TD>{j.fiscal_year_label ?? "—"}</TD>
                <TD>{j.method ? METHOD_LABELS[j.method] ?? j.method : "—"}</TD>
                <TD className="tabular-nums">
                  {j.valid_rows ?? "—"}{j.error_rows ? <span className="text-destructive"> · {j.error_rows} en erreur</span> : null}
                </TD>
                <TD>
                  <Badge tone={statusTone(j.status)}>{IMPORT_STATUS_LABELS[j.status]}</Badge>
                  {j.blocking && j.status === "awaiting_confirmation" && <Badge tone="red" className="ml-1">Bloquant</Badge>}
                </TD>
                <TD className="text-muted-foreground">{formatDate(j.created_at)}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
      <Dialog open={open} onClose={() => setOpen(false)} title="Nouvelle importation"
              description="Le fichier est vérifié (format réel, taille, macros) puis analysé.">
        <NewImportForm company={company} onCreated={(job) => router.push(`/companies/${company.id}/imports/${job.id}`)} />
      </Dialog>
    </div>
  );
}

export { METHOD_LABELS };
