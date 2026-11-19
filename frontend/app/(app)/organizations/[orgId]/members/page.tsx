"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { UserPlus } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { getSupabaseBrowser } from "@/lib/supabase/client";
import { useApiResource } from "@/lib/use-api";
import { ORG_ROLE_LABELS, type Member, type OrgPermissions, type OrgRole } from "@/lib/types";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Loading, PageHeader } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const ROLE_HINTS: Record<OrgRole, string> = {
  owner: "Tous les droits, y compris l'abonnement et la suppression.",
  admin: "Gère les membres et toutes les entreprises.",
  member: "Accède uniquement aux entreprises qui lui sont attribuées.",
  viewer: "Consultation des entreprises attribuées.",
};

function InviteForm({ orgId, myRole, onDone }: { orgId: string; myRole: OrgRole; onDone: (msg: string) => void }) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<OrgRole>("member");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const roles: OrgRole[] = myRole === "owner" ? ["owner", "admin", "member", "viewer"] : ["admin", "member", "viewer"];

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const res = await api.post<{ invitation_sent: boolean }>(`/organizations/${orgId}/members`,
        { email: email.trim(), role });
      onDone(res.invitation_sent
        ? `Invitation envoyée à ${email}. Le compte sera actif après acceptation.`
        : `${email} a été ajouté à l'organisation.`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      {error && <Alert>{error}</Alert>}
      <Field label="Adresse e-mail" htmlFor="inv-email" required>
        <Input id="inv-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
      </Field>
      <Field label="Rôle" htmlFor="inv-role" hint={ROLE_HINTS[role]}>
        <Select id="inv-role" value={role} onChange={(e) => setRole(e.target.value as OrgRole)}>
          {roles.map((r) => <option key={r} value={r}>{ORG_ROLE_LABELS[r]}</option>)}
        </Select>
      </Field>
      <div className="flex justify-end">
        <Button type="submit" loading={saving} disabled={!email.includes("@")}>Ajouter</Button>
      </div>
    </form>
  );
}

export default function MembersPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const router = useRouter();
  const { data: members, error, loading, reload } = useApiResource<Member[]>(`/organizations/${orgId}/members`);
  const { data: perms } = useApiResource<OrgPermissions>(`/organizations/${orgId}/permissions`);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const canEdit = (m: Member) => perms?.can_manage && (m.role !== "owner" || perms.role === "owner");

  async function changeRole(m: Member, role: OrgRole) {
    setBusyId(m.id);
    setNotice(null);
    try {
      await api.patch(`/organizations/${orgId}/members/${m.id}`, { role });
      setNotice({ kind: "success", text: `Rôle de ${m.email} mis à jour.` });
      await reload();
    } catch (err) {
      setNotice({ kind: "error", text: errorMessage(err) });
    } finally {
      setBusyId(null);
    }
  }

  async function remove(m: Member, isSelf: boolean) {
    const question = isSelf
      ? "Quitter cette organisation ? Vous perdrez l'accès à toutes ses entreprises."
      : `Retirer ${m.email} de l'organisation ? Il perdra l'accès à toutes ses entreprises.`;
    if (!window.confirm(question)) return;
    setBusyId(m.id);
    setNotice(null);
    try {
      await api.del(`/organizations/${orgId}/members/${m.id}`);
      if (isSelf) { router.replace("/organizations"); return; }
      setNotice({ kind: "success", text: `${m.email} a été retiré.` });
      await reload();
    } catch (err) {
      setNotice({ kind: "error", text: errorMessage(err) });
    } finally {
      setBusyId(null);
    }
  }

  const [selfId, setSelfId] = useState<string | null>(null);
  useEffect(() => {
    getSupabaseBrowser().auth.getUser().then(({ data }) => setSelfId(data.user?.id ?? null));
  }, []);

  return (
    <>
      <PageHeader
        title="Membres"
        description="Utilisateurs de l'organisation et leur rôle. L'accès aux entreprises se règle ensuite entreprise par entreprise."
        actions={perms?.can_manage && (
          <Button onClick={() => setInviteOpen(true)}><UserPlus className="h-4 w-4" /> Ajouter un membre</Button>
        )}
      />
      {notice && <Alert kind={notice.kind} className="mb-4">{notice.text}</Alert>}
      {loading && <Loading />}
      {error && <Alert>{error}</Alert>}
      {members && (
        <Table>
          <THead><tr><TH>Utilisateur</TH><TH>Rôle</TH><TH>Membre depuis</TH><TH className="text-right">Actions</TH></tr></THead>
          <TBody>
            {members.map((m) => {
              const isSelf = m.user_id === selfId;
              return (
                <TR key={m.id}>
                  <TD>
                    <p className="font-medium">{m.full_name || m.email}{isSelf && <span className="text-muted-foreground"> (vous)</span>}</p>
                    {m.full_name && <p className="text-xs text-muted-foreground">{m.email}</p>}
                  </TD>
                  <TD>
                    {canEdit(m) && !isSelf ? (
                      <Select aria-label={`Rôle de ${m.email}`} className="h-8 w-44" value={m.role}
                              disabled={busyId === m.id}
                              onChange={(e) => changeRole(m, e.target.value as OrgRole)}>
                        {(perms?.role === "owner" ? ["owner", "admin", "member", "viewer"] as OrgRole[]
                          : ["admin", "member", "viewer"] as OrgRole[]).map((r) =>
                          <option key={r} value={r}>{ORG_ROLE_LABELS[r]}</option>)}
                      </Select>
                    ) : ORG_ROLE_LABELS[m.role]}
                  </TD>
                  <TD className="text-muted-foreground">{formatDate(m.created_at)}</TD>
                  <TD className="text-right">
                    {(isSelf || canEdit(m)) && (
                      <Button size="sm" variant="ghost" className="text-destructive" loading={busyId === m.id}
                              onClick={() => remove(m, isSelf)}>
                        {isSelf ? "Quitter" : "Retirer"}
                      </Button>
                    )}
                  </TD>
                </TR>
              );
            })}
          </TBody>
        </Table>
      )}
      <Dialog open={inviteOpen} onClose={() => setInviteOpen(false)} title="Ajouter un membre"
              description="Si l'adresse n'a pas encore de compte, une invitation lui est envoyée par e-mail.">
        {perms && (
          <InviteForm orgId={orgId} myRole={perms.role} onDone={async (msg) => {
            setInviteOpen(false);
            setNotice({ kind: "success", text: msg });
            await reload();
          }} />
        )}
      </Dialog>
    </>
  );
}
