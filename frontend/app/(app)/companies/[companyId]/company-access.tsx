"use client";

import { useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { COMPANY_ROLE_LABELS, type Company, type CompanyMember, type Member } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Alert, EmptyState, Loading } from "@/components/ui/feedback";
import { Field, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const ASSIGNABLE = ["accountant", "controller", "analyst", "auditor", "viewer"] as const;
const ROLE_SCOPE: Record<(typeof ASSIGNABLE)[number], string> = {
  accountant: "Exercices, imports, balances, analyses, rapports",
  controller: "Budgets, centres de coûts, analyses, rapports",
  analyst: "Analyses, assistant IA, rapports",
  auditor: "Lecture et journal d'audit",
  viewer: "Lecture seule",
};

export function CompanyAccess({ company }: { company: Company }) {
  const canManage = company.my_permissions.includes("company.manage_members");
  const { data: members, error, loading, reload } =
    useApiResource<CompanyMember[]>(`/companies/${company.id}/members`);
  const { data: orgMembers } =
    useApiResource<Member[]>(canManage ? `/organizations/${company.organization_id}/members` : null);
  const [userId, setUserId] = useState("");
  const [role, setRole] = useState<(typeof ASSIGNABLE)[number]>("accountant");
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  // owner/admin ont déjà accès à toutes les entreprises : inutile de les attribuer
  const candidates = (orgMembers ?? []).filter(
    (m) => (m.role === "member" || m.role === "viewer") && !members?.some((cm) => cm.user_id === m.user_id));

  async function assign(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setNotice(null);
    try {
      await api.post(`/companies/${company.id}/members`, { user_id: userId, role });
      setUserId("");
      setNotice({ kind: "success", text: "Accès attribué." });
      await reload();
    } catch (err) {
      setNotice({ kind: "error", text: errorMessage(err) });
    } finally {
      setSaving(false);
    }
  }

  async function revoke(m: CompanyMember) {
    if (!window.confirm(`Retirer l'accès de ${m.email} à ${company.name} ?`)) return;
    setNotice(null);
    try {
      await api.del(`/companies/${company.id}/members/${m.id}`);
      setNotice({ kind: "success", text: `Accès de ${m.email} retiré.` });
      await reload();
    } catch (err) {
      setNotice({ kind: "error", text: errorMessage(err) });
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Les propriétaires et administrateurs de l&apos;organisation ont accès à toutes les entreprises.
        Les autres membres n&apos;accèdent qu&apos;aux entreprises qui leur sont attribuées ci-dessous.
      </p>
      {notice && <Alert kind={notice.kind}>{notice.text}</Alert>}

      {canManage && (
        <form onSubmit={assign} className="grid gap-3 rounded-lg border bg-card p-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
          <Field label="Membre" htmlFor="acc-user">
            <Select id="acc-user" value={userId} onChange={(e) => setUserId(e.target.value)}>
              <option value="">{candidates.length ? "Choisir un membre…" : "Aucun membre à attribuer"}</option>
              {candidates.map((m) => <option key={m.user_id} value={m.user_id}>{m.full_name || m.email}</option>)}
            </Select>
          </Field>
          <Field label="Rôle sur l'entreprise" htmlFor="acc-role" hint={ROLE_SCOPE[role]}>
            <Select id="acc-role" value={role} onChange={(e) => setRole(e.target.value as typeof role)}>
              {ASSIGNABLE.map((r) => <option key={r} value={r}>{COMPANY_ROLE_LABELS[r]}</option>)}
            </Select>
          </Field>
          <Button type="submit" loading={saving} disabled={!userId} className="sm:mb-5">Attribuer</Button>
        </form>
      )}

      {loading && !members && <Loading />}
      {error && <Alert>{error}</Alert>}
      {members && members.length === 0 && <EmptyState title="Aucune attribution individuelle" />}
      {members && members.length > 0 && (
        <Table>
          <THead><tr><TH>Membre</TH><TH>Rôle</TH>{canManage && <TH className="text-right">Actions</TH>}</tr></THead>
          <TBody>
            {members.map((m) => (
              <TR key={m.id}>
                <TD><p className="font-medium">{m.full_name || m.email}</p>
                  {m.full_name && <p className="text-xs text-muted-foreground">{m.email}</p>}</TD>
                <TD>{COMPANY_ROLE_LABELS[m.role]}</TD>
                {canManage && (
                  <TD className="text-right">
                    <Button size="sm" variant="ghost" className="text-destructive" onClick={() => revoke(m)}>Retirer</Button>
                  </TD>
                )}
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </div>
  );
}
