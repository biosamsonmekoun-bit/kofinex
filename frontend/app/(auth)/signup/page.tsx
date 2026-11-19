"use client";

import { useState } from "react";
import Link from "next/link";
import { getSupabaseBrowser } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { Alert } from "@/components/ui/feedback";
import { MIN_PASSWORD, passwordIssue as checkPassword } from "@/lib/password";

export default function SignupPage() {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const passwordIssue = checkPassword(password, confirm);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (passwordIssue) return;
    setLoading(true);
    setError(null);
    const { error } = await getSupabaseBrowser().auth.signUp({
      email,
      password,
      options: {
        data: { full_name: fullName.trim() },
        emailRedirectTo: `${window.location.origin}/auth/callback`,
      },
    });
    setLoading(false);
    if (error) setError(error.message);
    else setDone(true);
  }

  if (done) {
    return (
      <div className="w-full max-w-sm space-y-4">
        <h1 className="text-xl font-semibold">Vérifiez votre messagerie</h1>
        <Alert kind="success">
          Un e-mail de confirmation a été envoyé à <strong>{email}</strong>. Cliquez sur le lien pour activer votre compte.
        </Alert>
        <Link href="/login" className="text-sm font-medium text-link hover:underline">Retour à la connexion</Link>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="w-full max-w-sm space-y-5" noValidate>
      <div>
        <h1 className="text-xl font-semibold">Créer un compte</h1>
        <p className="mt-1 text-sm text-muted-foreground">Vous pourrez ensuite créer votre organisation.</p>
      </div>
      {error && <Alert>{error}</Alert>}
      <Field label="Nom complet" htmlFor="name" required>
        <Input id="name" autoComplete="name" required value={fullName} onChange={(e) => setFullName(e.target.value)} />
      </Field>
      <Field label="Adresse e-mail professionnelle" htmlFor="email" required>
        <Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      </Field>
      <Field label="Mot de passe" htmlFor="password" required hint={`${MIN_PASSWORD} caractères minimum, avec minuscule, majuscule et chiffre.`}>
        <Input id="password" type="password" autoComplete="new-password" required value={password}
               onChange={(e) => setPassword(e.target.value)} />
      </Field>
      <Field label="Confirmer le mot de passe" htmlFor="confirm" required>
        <Input id="confirm" type="password" autoComplete="new-password" required value={confirm}
               onChange={(e) => setConfirm(e.target.value)} />
      </Field>
      {passwordIssue && <p className="text-sm text-destructive">{passwordIssue}</p>}
      <Button type="submit" className="w-full" loading={loading}
              disabled={!fullName.trim() || !email || !password || !confirm || !!passwordIssue}>
        Créer mon compte
      </Button>
      <p className="text-center text-sm text-muted-foreground">
        Déjà inscrit ? <Link href="/login" className="font-medium text-link hover:underline">Se connecter</Link>
      </p>
    </form>
  );
}
