"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import type { Profile } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, Loading, PageHeader } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";

export default function ProfilePage() {
  const { data: profile, error, loading, setData } = useApiResource<Profile>("/me");
  const [form, setForm] = useState({ full_name: "", phone: "", locale: "fr" });
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    if (profile) setForm({ full_name: profile.full_name ?? "", phone: profile.phone ?? "", locale: profile.locale });
  }, [profile]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setNotice(null);
    try {
      setData(await api.patch<Profile>("/me", {
        full_name: form.full_name.trim() || null, phone: form.phone.trim() || null, locale: form.locale,
      }));
      setNotice({ kind: "success", text: "Profil enregistré." });
    } catch (err) {
      setNotice({ kind: "error", text: errorMessage(err) });
    } finally {
      setSaving(false);
    }
  }

  if (loading && !profile) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  if (!profile) return null;

  return (
    <>
      <PageHeader title="Mon profil" description={profile.email} />
      <div className="grid max-w-4xl gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Informations personnelles</CardTitle></CardHeader>
          <CardContent>
            <form onSubmit={save} className="space-y-4">
              {notice && <Alert kind={notice.kind}>{notice.text}</Alert>}
              <Field label="Nom complet" htmlFor="p-name">
                <Input id="p-name" value={form.full_name} maxLength={200}
                       onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
              </Field>
              <Field label="Téléphone" htmlFor="p-phone">
                <Input id="p-phone" type="tel" value={form.phone} maxLength={40}
                       onChange={(e) => setForm({ ...form, phone: e.target.value })} />
              </Field>
              <Field label="Langue" htmlFor="p-locale">
                <Select id="p-locale" value={form.locale} onChange={(e) => setForm({ ...form, locale: e.target.value })}>
                  <option value="fr">Français</option>
                  <option value="en">English</option>
                </Select>
              </Field>
              <Button type="submit" loading={saving}>Enregistrer</Button>
            </form>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Sécurité</CardTitle>
            <CardDescription>L&apos;adresse e-mail sert d&apos;identifiant et n&apos;est pas modifiable ici.</CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild variant="outline"><Link href="/reset-password">Changer de mot de passe</Link></Button>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
