"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { getSupabaseBrowser } from "@/lib/supabase/client";
import { MIN_PASSWORD, passwordIssue } from "@/lib/password";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/form";
import { Alert, PageHeader } from "@/components/ui/feedback";

/** Atteinte via le lien e-mail de réinitialisation (session ouverte par /auth/callback),
 *  ou depuis le profil pour changer son mot de passe. */
export default function ResetPasswordPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const issue = passwordIssue(password, confirm);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (issue) return;
    setLoading(true);
    setError(null);
    const { error } = await getSupabaseBrowser().auth.updateUser({ password });
    setLoading(false);
    if (error) setError(error.message);
    else {
      setDone(true);
      setTimeout(() => router.replace("/organizations"), 1500);
    }
  }

  return (
    <>
      <PageHeader title="Nouveau mot de passe" />
      <Card className="max-w-md">
        <CardHeader><CardTitle>Définir un nouveau mot de passe</CardTitle></CardHeader>
        <CardContent>
          {done ? <Alert kind="success">Mot de passe mis à jour.</Alert> : (
            <form onSubmit={submit} className="space-y-4" noValidate>
              {error && <Alert>{error}</Alert>}
              <Field label="Nouveau mot de passe" htmlFor="pw" required
                     hint={`${MIN_PASSWORD} caractères minimum, avec minuscule, majuscule et chiffre.`}>
                <Input id="pw" type="password" autoComplete="new-password" value={password}
                       onChange={(e) => setPassword(e.target.value)} />
              </Field>
              <Field label="Confirmer" htmlFor="pw2" required>
                <Input id="pw2" type="password" autoComplete="new-password" value={confirm}
                       onChange={(e) => setConfirm(e.target.value)} />
              </Field>
              {issue && <p className="text-sm text-destructive">{issue}</p>}
              <Button type="submit" loading={loading} disabled={!password || !confirm || !!issue}>Enregistrer</Button>
            </form>
          )}
        </CardContent>
      </Card>
    </>
  );
}
