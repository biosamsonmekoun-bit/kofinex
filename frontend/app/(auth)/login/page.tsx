"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { getSupabaseBrowser } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { Alert } from "@/components/ui/feedback";

const AUTH_ERRORS: Record<string, string> = {
  "Invalid login credentials": "Adresse e-mail ou mot de passe incorrect.",
  "Email not confirmed": "Adresse e-mail non confirmée : consultez votre messagerie.",
};

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(
    params.get("error") === "lien_invalide" ? "Ce lien est invalide ou a expiré." : null,
  );
  const [info, setInfo] = useState<string | null>(null);

  const next = params.get("next");
  const safeNext = next && next.startsWith("/") && !next.startsWith("//") ? next : "/tableau-de-bord";

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const { error } = await getSupabaseBrowser().auth.signInWithPassword({ email, password });
    setLoading(false);
    if (error) {
      setError(AUTH_ERRORS[error.message] ?? error.message);
      return;
    }
    router.replace(safeNext);
    router.refresh();
  }

  async function onMagicLink() {
    if (!email) {
      setError("Saisissez votre adresse e-mail pour recevoir un lien de connexion.");
      return;
    }
    setLoading(true);
    setError(null);
    const { error } = await getSupabaseBrowser().auth.signInWithOtp({
      email,
      options: { shouldCreateUser: false, emailRedirectTo: `${window.location.origin}/auth/callback?next=${encodeURIComponent(safeNext)}` },
    });
    setLoading(false);
    if (error) setError(error.message);
    else setInfo("Si un compte existe pour cette adresse, un lien de connexion vient d'être envoyé.");
  }

  return (
    <form onSubmit={onSubmit} className="w-full max-w-sm space-y-5" noValidate>
      <div>
        <h1 className="text-xl font-semibold">Connexion</h1>
        <p className="mt-1 text-sm text-muted-foreground">Accédez à votre espace KOFINEX.</p>
      </div>
      {error && <Alert>{error}</Alert>}
      {info && <Alert kind="success">{info}</Alert>}
      <Field label="Adresse e-mail" htmlFor="email" required>
        <Input id="email" type="email" autoComplete="email" required value={email}
               onChange={(e) => setEmail(e.target.value)} />
      </Field>
      <Field label="Mot de passe" htmlFor="password" required>
        <Input id="password" type="password" autoComplete="current-password" required value={password}
               onChange={(e) => setPassword(e.target.value)} />
      </Field>
      <div className="-mt-3 text-right">
        <Link href="/forgot-password" className="text-xs text-link hover:underline">Mot de passe oublié ?</Link>
      </div>
      <Button type="submit" className="w-full" loading={loading} disabled={!email || !password}>
        Se connecter
      </Button>
      <Button type="button" variant="outline" className="w-full" onClick={onMagicLink} disabled={loading}>
        Recevoir un lien de connexion par e-mail
      </Button>
      <p className="text-center text-sm text-muted-foreground">
        Pas encore de compte ? <Link href="/signup" className="font-medium text-link hover:underline">Créer un compte</Link>
      </p>
    </form>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
