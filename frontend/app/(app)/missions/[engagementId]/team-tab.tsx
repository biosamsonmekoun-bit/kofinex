"use client";

import { useState } from "react";
import { Trash2, UserPlus } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { ENGAGEMENT_ROLE_LABELS, personName, type Engagement, type EngagementMember, type EngagementRole, type PersonRef } from "@/lib/types";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Alert, Badge } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const ROLES = Object.keys(ENGAGEMENT_ROLE_LABELS) as EngagementRole[];

export function TeamTab({ e, onChanged }: { e: Engagement; onChanged: (m: EngagementMember[]) => void }) {
  const canManage = (e.capabilities ?? []).includes("manage_team") || !!e.is_org_admin;
  const frozen = ["issued", "archived"].includes(e.status);
  const { data: candidates, reload } = useApiResource<PersonRef[]>(canManage && !frozen ? `/engagements/${e.id}/candidates` : null);
  const [form, setForm] = useState({ user_id: "", role: "staff" as EngagementRole, planned_hours: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function call(fn: () => Promise<EngagementMember[] | void>) {
    setBusy(true);
    setError(null);
    try {
      const r = await fn();
      if (r) onChanged(r);
      else onChanged((await api.get<Engagement>(`/engagements/${e.id}`)).members ?? []);
      await reload();
    } catch (x) { setError(errorMessage(x)); } finally { setBusy(false); }
  }

  return (
    <div className="space-y-4">
      {error && <Alert>{error}</Alert>}
      <p className="text-sm text-muted-foreground">
        L&apos;accès au dossier est réservé aux membres de l&apos;équipe ayant déclaré leur indépendance ; un changement de rôle appelle une
        nouvelle déclaration. L&apos;audité ne voit pas le dossier de travail.
      </p>
      <Table>
        <THead><tr><TH>Membre</TH><TH>Rôle</TH><TH className="text-right">Heures prévues</TH><TH>Indépendance</TH><TH /></tr></THead>
        <TBody>
          {(e.members ?? []).map((m) => (
            <TR key={m.id}>
              <TD><span className="font-medium">{personName(m.user)}</span> <span className="text-xs text-muted-foreground">{m.user?.email}</span></TD>
              <TD>
                {canManage && !frozen ? (
                  <Select aria-label="Rôle" value={m.role} className="w-44" disabled={busy}
                          onChange={(x) => call(() => api.patch<EngagementMember[]>(`/engagements/${e.id}/members/${m.id}`, { role: x.target.value, planned_hours: m.planned_hours }))}>
                    {ROLES.map((r) => <option key={r} value={r}>{ENGAGEMENT_ROLE_LABELS[r]}</option>)}
                  </Select>
                ) : m.role_label}
              </TD>
              <TD className="text-right">{m.planned_hours ?? "—"}</TD>
              <TD>
                {["auditee", "observer"].includes(m.role) ? <span className="text-xs text-muted-foreground">Non requise</span>
                  : m.independence_confirmed_at ? <Badge tone="green">Déclarée le {formatDate(m.independence_confirmed_at)}</Badge>
                  : <Badge tone="amber">À déclarer</Badge>}
              </TD>
              <TD className="text-right">
                {canManage && !frozen && (
                  <Button variant="ghost" size="icon" aria-label={`Retirer ${personName(m.user)}`} disabled={busy}
                          onClick={() => call(() => api.del(`/engagements/${e.id}/members/${m.id}`))}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                )}
              </TD>
            </TR>
          ))}
        </TBody>
      </Table>
      {canManage && !frozen && (
        <form className="flex flex-col gap-3 rounded-lg border bg-card p-4 shadow-card sm:flex-row sm:items-end"
              onSubmit={(x) => { x.preventDefault(); void call(() => api.post<EngagementMember[]>(`/engagements/${e.id}/members`, {
                user_id: form.user_id, role: form.role, planned_hours: form.planned_hours || null })); setForm({ ...form, user_id: "" }); }}>
          <div className="flex-1">
            <Field label="Membre de l'organisation" htmlFor="tm-user">
              <Select id="tm-user" value={form.user_id} onChange={(x) => setForm({ ...form, user_id: x.target.value })}>
                <option value="">Choisir…</option>
                {candidates?.map((c) => <option key={c.id} value={c.id}>{personName(c)} ({c.email})</option>)}
              </Select>
            </Field>
          </div>
          <Field label="Rôle" htmlFor="tm-role">
            <Select id="tm-role" value={form.role} className="w-44" onChange={(x) => setForm({ ...form, role: x.target.value as EngagementRole })}>
              {ROLES.map((r) => <option key={r} value={r}>{ENGAGEMENT_ROLE_LABELS[r]}</option>)}
            </Select>
          </Field>
          <Field label="Heures prévues" htmlFor="tm-h"><Input id="tm-h" className="w-28" inputMode="decimal" value={form.planned_hours} onChange={(x) => setForm({ ...form, planned_hours: x.target.value })} /></Field>
          <Button type="submit" loading={busy} disabled={!form.user_id}><UserPlus className="h-4 w-4" /> Affecter</Button>
        </form>
      )}
    </div>
  );
}
