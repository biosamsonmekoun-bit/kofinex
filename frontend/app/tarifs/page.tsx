"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, errorMessage } from "@/lib/api";
import type { Catalog, Interval } from "@/lib/billing-types";
import { Logo } from "@/components/brand";
import { CurrencyIntervalPicker, PlanCard, QuotaList } from "@/components/billing";
import { Alert, EmptyState, Loading } from "@/components/ui/feedback";
import { formatMoney, priceFor } from "@/lib/billing-types";

/** Grille tarifaire publique, lue dans le catalogue publié (aucun prix dans le code). */
export default function TarifsPage() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [country, setCountry] = useState("BJ");
  const [interval, setInterval] = useState<Interval>("month");

  useEffect(() => {
    api.publicGet<Catalog>("/billing/catalog").then(setCatalog).catch((e) => setError(errorMessage(e)));
  }, []);

  const currency = catalog?.countries[country] ?? "XOF";
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b bg-card">
        <div className="mx-auto flex max-w-6xl items-center gap-4 px-5 py-4">
          <Link href="/" aria-label="Accueil"><Logo className="text-foreground" /></Link>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <Link href="/login" className="rounded-md border px-4 py-2 font-semibold hover:bg-muted">Connexion</Link>
            <Link href="/signup" className="rounded-md bg-primary px-4 py-2 font-semibold text-primary-foreground hover:opacity-90">Créer un compte</Link>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-5 py-10">
        <h1 className="text-3xl font-extrabold tracking-tight">Tarifs</h1>
        <p className="mt-2 max-w-2xl text-muted-foreground">
          Prix hors taxes, dans la devise de votre pays de facturation. Facturation depuis le Bénin ; les taxes applicables seront
          indiquées à la commande.
        </p>
        {error && <Alert className="mt-6">{error}</Alert>}
        {!catalog && !error && <Loading />}
        {catalog && (
          <>
            <div className="mt-6">
              <CurrencyIntervalPicker countries={catalog.countries} country={country} onCountry={setCountry}
                                      interval={interval} onInterval={setInterval} />
            </div>
            {catalog.plans.length === 0 ? (
              <div className="mt-8">
                <EmptyState title="Aucune offre publiée pour le moment"
                            description="La grille tarifaire sera affichée ici dès sa publication. Vous pouvez déjà créer votre compte." />
              </div>
            ) : (
              <div className="mt-8 grid gap-5 md:grid-cols-2 lg:grid-cols-3">
                {catalog.plans.map((p) => (
                  <PlanCard key={p.version_id} plan={p} modules={catalog.modules} currency={currency} interval={interval}>
                    <Link href="/signup" className="block rounded-md bg-primary px-4 py-2 text-center text-sm font-semibold text-primary-foreground hover:opacity-90">
                      {p.trial_days ? `Commencer l'essai de ${p.trial_days} jours` : "Créer un compte"}
                    </Link>
                  </PlanCard>
                ))}
              </div>
            )}
            {catalog.addons.length > 0 && (
              <section className="mt-12">
                <h2 className="text-xl font-bold">Options</h2>
                <div className="mt-4 grid gap-4 md:grid-cols-2">
                  {catalog.addons.map((a) => {
                    const price = priceFor(a.prices, interval, currency);
                    return (
                      <div key={a.version_id} className="rounded-lg border bg-card p-4">
                        <div className="flex items-baseline justify-between gap-3">
                          <p className="font-semibold">{a.name}</p>
                          <p className="tabular-nums">{price ? formatMoney(price.amount, currency) : "Prix non publié dans cette devise"}</p>
                        </div>
                        {a.description && <p className="mt-1 text-sm text-muted-foreground">{a.description}</p>}
                        <QuotaList quotas={a.quotas} className="mt-2" />
                      </div>
                    );
                  })}
                </div>
              </section>
            )}
          </>
        )}
      </main>
    </div>
  );
}
