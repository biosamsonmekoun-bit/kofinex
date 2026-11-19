"use client";

import { useState } from "react";
import Link from "next/link";
import { getSupabaseBrowser } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { Alert } from "@/components/ui/feedback";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const { error } = await getSupabaseBrowser().auth.resetPasswordForEmail(email.trim(), {
      redirectTo: `${window.location.origin}/auth/callback?next=/reset-password`,
    });
    setLoading(false);
    if (error) setError(error.message);
    else setSent(true);
  }

  return (
    <form onSubmit={submit} className="w-full max-w-sm space-y-5" noValidate>
      <div>
        <h1 className="text-xl font-semibold">Mot de passe oublié</h1>
        <p className="mt-1 text-sm text-muted-foreground">Recevez un lien pour définir un nouveau mot de passe.</p>
      </div>
      {error && <Alert>{error}</Alert>}
      {sent ? (
        <Alert kind="success">
          Si un compte existe pour <strong>{email}</strong>, un e-mail de réinitialisation vient d&apos;être envoyé.
        </Alert>
      ) : (
        <>
          <Field label="Adresse e-mail" htmlFor="email" required>
            <Input id="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Button type="submit" className="w-full" loading={loading} disabled={!email.includes("@")}>
            Envoyer le lien
          </Button>
        </>
      )}
      <Link href="/login" className="block text-center text-sm font-medium text-link hover:underline">
        Retour à la connexion
      </Link>
    </form>
  );
}
