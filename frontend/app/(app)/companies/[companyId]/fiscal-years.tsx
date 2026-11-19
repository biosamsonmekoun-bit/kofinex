"use client";

import { useState } from "react";
import Link from "next/link";
import { BarChart3, Lock, LockOpen, Plus, Table2, Trash2 } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import type { Company, FiscalYear } from "@/lib/types";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Field, Input } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const iso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

/** Exercice suivant le dernier connu (ou l'exercice en cours), sur 12 mois. */
function suggestNext(company: Company, years: FiscalYear[]) {
  let start: Date;
  if (years.length > 0) {
    const last = years.reduce((a, b) => (a.end_date > b.end_date ? a : b));
    start = new Date(`${last.end_date}T00:00:00`);
    start.setDate(start.getDate() + 1);
  } else {
    const now = new Date();
    const m = company.fiscal_year_start_month - 1;
    start = new Date(now.getMonth() >= m ? now.getFullYear() : now.getFullYear() - 1, m, 1);
  }
  const end = new Date(start.getFullYear(), start.getMonth() + 12, 0);
  const label = start.getMonth() === 0 ? String(start.getFullYear()) : `${start.getFullYear()}-${end.getFullYear()}`;
  return { label, start_date: iso(start), end_date: iso(end) };
}

type Action =
  | { kind: "create" }
  | { kind: "close"; fy: FiscalYear }
  | { kind: "reopen"; fy: FiscalYear }
  | null;

export function FiscalYears({ company }: { company: Company }) {
  const path = `/companies/${company.id}/fiscal-years`;
  const { data: years, error, loading, reload } = useApiResource<FiscalYear[]>(path);
  const [action, setAction] = useState<Action>(null);
  const [form, setForm] = useState({ label: "", start_date: "", end_date: "", confirm: "", reason: "" });
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  const canWrite = company.my_permissions.includes("fiscal_year.write");
  const canClose = company.my_permissions.includes("fiscal_year.close");
  const isOrgAdmin = company.my_role === "org_admin";

  function open(a: NonNullable<Action>) {
    setFormError(null);
    setForm(a.kind === "create"
      ? { ...suggestNext(company, years ?? []), confirm: "", reason: "" }
      : { label: "", start_date: "", end_date: "", confirm: "", reason: "" });
    setAction(a);
  }

  async function run(fn: () => Promise<unknown>, success: string) {
    setSaving(true);
    setFormError(null);
    try {
      await fn();
      setAction(null);
      setNotice({ kind: "success", text: success });
      await reload();
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function remove(fy: FiscalYear) {
    if (!window.confirm(`Supprimer l'exercice ${fy.label} et toutes les données qui y sont rattachées ? Cette action est irréversible.`)) return;
    setNotice(null);
    try {
      await api.del(`${path}/${fy.id}`);
      setNotice({ kind: "success", text: `Exercice ${fy.label} supprimé.` });
      await reload();
    } catch (err) {
      setNotice({ kind: "error", text: errorMessage(err) });
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Un exercice clôturé est figé : ses balances et états financiers ne peuvent plus être modifiés.
        </p>
        {canWrite && <Button size="sm" onClick={() => open({ kind: "create" })}><Plus className="h-4 w-4" /> Nouvel exercice</Button>}
      </div>
      {notice && <Alert kind={notice.kind}>{notice.text}</Alert>}
      {loading && !years && <Loading />}
      {error && <Alert>{error}</Alert>}
      {years && years.length === 0 && (
        <EmptyState title="Aucun exercice" description="Créez un exercice pour pouvoir y importer une balance générale." />
      )}
      {years && years.length > 0 && (
        <Table>
          <THead><tr><TH>Exercice</TH><TH>Période</TH><TH>Statut</TH><TH className="text-right">Actions</TH></tr></THead>
          <TBody>
            {years.map((fy) => (
              <TR key={fy.id}>
                <TD className="font-medium">{fy.label}</TD>
                <TD className="tabular-nums">{formatDate(fy.start_date)} → {formatDate(fy.end_date)}</TD>
                <TD>
                  {fy.status === "open" ? <Badge tone="green">Ouvert</Badge>
                    : <Badge tone="neutral">Clôturé le {formatDate(fy.closed_at)}</Badge>}
                </TD>
                <TD className="space-x-1 text-right">
                  {fy.active_import_job_id && (
                    <Button asChild size="sm" variant="outline">
                      <Link href={`/companies/${company.id}/fiscal-years/${fy.id}/balance`}><Table2 className="h-3.5 w-3.5" /> Balance</Link>
                    </Button>
                  )}
                  {fy.active_import_job_id && (
                    <Button asChild size="sm" variant="outline">
                      <Link href={`/companies/${company.id}/fiscal-years/${fy.id}/analysis`}><BarChart3 className="h-3.5 w-3.5" /> Analyse</Link>
                    </Button>
                  )}
                  {fy.status === "open" && canClose && (
                    <Button size="sm" variant="outline" onClick={() => open({ kind: "close", fy })}>
                      <Lock className="h-3.5 w-3.5" /> Clôturer
                    </Button>
                  )}
                  {fy.status === "closed" && isOrgAdmin && (
                    <Button size="sm" variant="outline" onClick={() => open({ kind: "reopen", fy })}>
                      <LockOpen className="h-3.5 w-3.5" /> Rouvrir
                    </Button>
                  )}
                  {fy.status === "open" && isOrgAdmin && (
                    <Button size="icon" variant="ghost" className="text-destructive" aria-label={`Supprimer ${fy.label}`}
                            onClick={() => remove(fy)}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  )}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}

      <Dialog open={action?.kind === "create"} onClose={() => setAction(null)} title="Nouvel exercice"
              description="Durée maximale : 18 mois. Les exercices d'une même entreprise ne peuvent pas se chevaucher.">
        <form className="space-y-4" onSubmit={(e) => {
          e.preventDefault();
          void run(() => api.post(path, { label: form.label.trim(), start_date: form.start_date, end_date: form.end_date }),
                   `Exercice ${form.label} créé.`);
        }}>
          {formError && <Alert>{formError}</Alert>}
          <Field label="Libellé" htmlFor="fy-label" required>
            <Input id="fy-label" value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} maxLength={40} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Date de début" htmlFor="fy-start" required>
              <Input id="fy-start" type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
            </Field>
            <Field label="Date de fin" htmlFor="fy-end" required>
              <Input id="fy-end" type="date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} />
            </Field>
          </div>
          {form.start_date && form.end_date && form.end_date <= form.start_date && (
            <p className="text-sm text-destructive">La date de fin doit être postérieure à la date de début.</p>
          )}
          <div className="flex justify-end">
            <Button type="submit" loading={saving}
                    disabled={!form.label.trim() || !form.start_date || !form.end_date || form.end_date <= form.start_date}>
              Créer
            </Button>
          </div>
        </form>
      </Dialog>

      <Dialog open={action?.kind === "close"} onClose={() => setAction(null)} title="Clôturer l'exercice"
              description="Après clôture, les balances, imports et états financiers de l'exercice ne pourront plus être modifiés. Seul un administrateur pourra le rouvrir, avec un motif journalisé.">
        {action?.kind === "close" && (
          <form className="space-y-4" onSubmit={(e) => {
            e.preventDefault();
            void run(() => api.post(`${path}/${action.fy.id}/close`, { confirm_label: form.confirm }),
                     `Exercice ${action.fy.label} clôturé.`);
          }}>
            {formError && <Alert>{formError}</Alert>}
            <Field label={`Saisissez « ${action.fy.label} » pour confirmer`} htmlFor="fy-confirm" required>
              <Input id="fy-confirm" value={form.confirm} onChange={(e) => setForm({ ...form, confirm: e.target.value })} autoComplete="off" />
            </Field>
            <div className="flex justify-end">
              <Button type="submit" variant="destructive" loading={saving} disabled={form.confirm !== action.fy.label}>
                Clôturer définitivement
              </Button>
            </div>
          </form>
        )}
      </Dialog>

      <Dialog open={action?.kind === "reopen"} onClose={() => setAction(null)} title="Rouvrir l'exercice"
              description="La réouverture est tracée dans le journal d'audit avec son motif.">
        {action?.kind === "reopen" && (
          <form className="space-y-4" onSubmit={(e) => {
            e.preventDefault();
            void run(() => api.post(`${path}/${action.fy.id}/reopen`, { reason: form.reason.trim() }),
                     `Exercice ${action.fy.label} rouvert.`);
          }}>
            {formError && <Alert>{formError}</Alert>}
            <Field label="Motif de réouverture" htmlFor="fy-reason" required hint="10 caractères minimum.">
              <textarea id="fy-reason" rows={3} value={form.reason}
                        onChange={(e) => setForm({ ...form, reason: e.target.value })}
                        className="w-full rounded-md border border-input bg-card px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring" />
            </Field>
            <div className="flex justify-end">
              <Button type="submit" loading={saving} disabled={form.reason.trim().length < 10}>Rouvrir</Button>
            </div>
          </form>
        )}
      </Dialog>
    </div>
  );
}
