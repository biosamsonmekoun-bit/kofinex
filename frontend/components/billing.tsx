"use client";

import { Check } from "lucide-react";
import {
  COUNTRY_NAMES, CURRENCY_LABELS, INTERVAL_LABELS, QUOTA_LABELS, formatMoney, priceFor,
  type BillingModule, type CatalogItem, type Currency, type Interval, type Quotas,
} from "@/lib/billing-types";
import { Select } from "@/components/ui/form";
import { cn } from "@/lib/utils";

export function quotaText(key: string, limit: number | null | undefined): string {
  const label = QUOTA_LABELS[key] ?? key;
  if (limit === null) return `${label} : illimité`;
  if (limit === undefined) return `${label} : non inclus`;
  return `${label} : ${limit.toLocaleString("fr-FR")}`;
}

/** Choix de la devise (par pays de facturation) et de la périodicité. */
export function CurrencyIntervalPicker({ countries, country, onCountry, interval, onInterval }: {
  countries: Record<string, Currency>; country: string; onCountry: (c: string) => void;
  interval: Interval; onInterval: (i: Interval) => void;
}) {
  const names: Record<string, string> = COUNTRY_NAMES;   // noms affichés ; la liste des pays ouverts vient du serveur
  return (
    <div className="flex flex-wrap items-center gap-3">
      <label className="text-sm text-muted-foreground" htmlFor="pays">Pays de facturation</label>
      <Select id="pays" value={country} onChange={(e) => onCountry(e.target.value)} className="w-56">
        {Object.keys(countries).sort((a, b) => (names[a] ?? a).localeCompare(names[b] ?? b, "fr")).map((c) => (
          <option key={c} value={c}>{names[c] ?? c} — {CURRENCY_LABELS[countries[c]]}</option>
        ))}
      </Select>
      <div role="tablist" aria-label="Périodicité" className="inline-flex rounded-md border p-0.5">
        {(["month", "year"] as Interval[]).map((i) => (
          <button key={i} type="button" role="tab" aria-selected={interval === i} onClick={() => onInterval(i)}
                  className={cn("rounded px-3 py-1 text-sm", interval === i ? "bg-primary text-primary-foreground" : "hover:bg-muted")}>
            {i === "month" ? "Mensuel" : "Annuel"}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Carte d'une offre publiée : prix dans la devise choisie (ou absence de prix, dite clairement), modules, quotas. */
export function PlanCard({ plan, modules, currency, interval, children }: {
  plan: CatalogItem; modules: BillingModule[]; currency: Currency; interval: Interval; children?: React.ReactNode;
}) {
  const price = priceFor(plan.prices, interval, currency);
  const labels = Object.fromEntries(modules.map((m) => [m.key, m.label]));
  const order = Object.fromEntries(modules.map((m) => [m.key, m.display_order]));   // ordre du catalogue (socle en tête)
  return (
    <div className="flex flex-col rounded-xl border bg-card p-5 text-card-foreground shadow-sm">
      <p className="text-lg font-bold">{plan.name}</p>
      {plan.description && <p className="mt-1 text-sm text-muted-foreground">{plan.description}</p>}
      <p className="mt-4 text-2xl font-extrabold tabular-nums">
        {price ? formatMoney(price.amount, currency) : <span className="text-base font-medium text-muted-foreground">Prix non publié dans cette devise</span>}
      </p>
      {price && <p className="text-xs text-muted-foreground">{INTERVAL_LABELS[interval]}, hors taxes</p>}
      {plan.trial_days && <p className="mt-2 text-sm font-medium text-link">Essai gratuit de {plan.trial_days} jours, sans moyen de paiement</p>}
      <ul className="mt-4 space-y-1.5 text-sm">
        {[...plan.modules].sort((x, y) => (order[x] ?? 999) - (order[y] ?? 999)).map((m) => (
          <li key={m} className="flex gap-2"><Check className="mt-0.5 h-4 w-4 shrink-0 text-success-strong" aria-hidden />{labels[m] ?? m}</li>
        ))}
      </ul>
      <QuotaList quotas={plan.quotas} className="mt-4" />
      {children && <div className="mt-auto pt-5">{children}</div>}
    </div>
  );
}

export function QuotaList({ quotas, className }: { quotas: Quotas; className?: string }) {
  const keys = Object.keys(QUOTA_LABELS).filter((k) => k in quotas);
  if (keys.length === 0) return null;
  return (
    <ul className={cn("space-y-1 text-xs text-muted-foreground", className)}>
      {keys.map((k) => <li key={k}>{quotaText(k, quotas[k])}</li>)}
    </ul>
  );
}
