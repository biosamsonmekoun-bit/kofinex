"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { ORG_TYPE_LABELS, type Organization } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Loading, PageHeader } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { AiSettingsCard } from "@/components/ai-common";

export default function OrganizationSettingsPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const router = useRouter();
  const { data: org, error, loading, setData } = useApiResource<Organization>(`/organizations/${orgId}`);
  const [form, setForm] = useState({ name: "", org_type: "company", country_code: "", default_currency: "XOF" });
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [confirm, setConfirm] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    if (org) setForm({ name: org.name, org_type: org.org_type, country_code: org.country_code ?? "",
                       default_currency: org.default_currency });
  }, [org]);

  if (loading && !org) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  if (!org) return null;

  const canEdit = org.my_role === "owner" || org.my_role === "admin";
  const canDelete = org.my_role === "owner";

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setNotice(null);
    try {
      setData(await api.patch<Organization>(`/organizations/${orgId}`, {
        name: form.name.trim(), org_type: form.org_type,
        country_code: form.country_code || null, default_currency: form.default_currency,
      }));
      setNotice({ kind: "success", text: "Paramètres enregistrés." });
    } catch (err) {
      setNotice({ kind: "error", text: errorMessage(err) });
    } finally {
      setSaving(false);
    }
  }

  async function destroy(e: React.FormEvent) {
    e.preventDefault();
    setDeleting(true);
    setDeleteError(null);
    try {
      await api.del(`/organizations/${orgId}`, { confirm_slug: confirm });
      try { localStorage.removeItem("kofinex.lastOrg"); } catch { /* ignoré */ }
      router.replace("/organizations");
    } catch (err) {
      setDeleteError(errorMessage(err));
      setDeleting(false);
    }
  }

  return (
    <>
      <PageHeader title="Paramètres de l'organisation" description={`Identifiant : ${org.slug}`} />
      <div className="max-w-2xl space-y-4">
        <Card>
          <CardHeader><CardTitle>Informations générales</CardTitle></CardHeader>
          <CardContent>
            <form onSubmit={save} className="space-y-4">
              {notice && <Alert kind={notice.kind}>{notice.text}</Alert>}
              {!canEdit && <Alert kind="info">Seuls les propriétaires et administrateurs peuvent modifier ces paramètres.</Alert>}
              <Field label="Nom" htmlFor="o-name" required>
                <Input id="o-name" value={form.name} disabled={!canEdit} maxLength={200}
                       onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </Field>
              <Field label="Type" htmlFor="o-type">
                <Select id="o-type" value={form.org_type} disabled={!canEdit}
                        onChange={(e) => setForm({ ...form, org_type: e.target.value })}>
                  {Object.entries(ORG_TYPE_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </Select>
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Pays (code ISO)" htmlFor="o-country">
                  <Input id="o-country" value={form.country_code} maxLength={2} disabled={!canEdit}
                         onChange={(e) => setForm({ ...form, country_code: e.target.value.toUpperCase() })} />
                </Field>
                <Field label="Devise par défaut" htmlFor="o-cur">
                  <Select id="o-cur" value={form.default_currency} disabled={!canEdit}
                          onChange={(e) => setForm({ ...form, default_currency: e.target.value })}>
                    {["XOF", "XAF", "GNF", "KMF", "CDF", "EUR", "USD"].map((c) => <option key={c}>{c}</option>)}
                  </Select>
                </Field>
              </div>
              {canEdit && <Button type="submit" loading={saving} disabled={form.name.trim().length < 2}>Enregistrer</Button>}
            </form>
          </CardContent>
        </Card>

        <AiSettingsCard orgId={orgId} />

        {canDelete && (
          <Card className="border-destructive/30">
            <CardHeader>
              <CardTitle className="text-destructive-strong">Supprimer l&apos;organisation</CardTitle>
              <CardDescription>
                Supprime définitivement toutes les entreprises, exercices, balances, analyses et rapports.
                Le journal d&apos;audit est conservé. Action irréversible.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button variant="destructive" onClick={() => { setConfirm(""); setDeleteError(null); setDeleteOpen(true); }}>
                Supprimer l&apos;organisation
              </Button>
            </CardContent>
          </Card>
        )}
      </div>

      <Dialog open={deleteOpen} onClose={() => setDeleteOpen(false)} title="Confirmer la suppression"
              description={`Saisissez l'identifiant « ${org.slug} » pour confirmer.`}>
        <form onSubmit={destroy} className="space-y-4">
          {deleteError && <Alert>{deleteError}</Alert>}
          <Input aria-label="Identifiant de l'organisation" value={confirm} autoComplete="off"
                 onChange={(e) => setConfirm(e.target.value)} />
          <div className="flex justify-end">
            <Button type="submit" variant="destructive" loading={deleting} disabled={confirm !== org.slug}>
              Supprimer définitivement
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
