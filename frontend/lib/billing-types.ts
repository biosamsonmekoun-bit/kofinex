/** Lot 12A — catalogue et abonnements. Les montants arrivent en texte exact : jamais convertis en nombre. */

export type Interval = "month" | "year";
export type Currency = "XOF" | "XAF" | "GNF" | "KMF" | "CDF";

export interface Price { billing_interval: Interval; currency: Currency; amount: string }
export type Quotas = Record<string, number | null>;

export interface CatalogItem {
  product_id: string; version_id: string; code: string; name: string; description: string | null; label: string;
  trial_days: number | null; prices: Price[]; modules: string[]; quotas: Quotas;
}
export interface BillingModule { key: string; label: string; description: string | null; requires: string[]; is_core: boolean; display_order: number }
export interface Catalog { plans: CatalogItem[]; addons: CatalogItem[]; modules: BillingModule[]; countries: Record<string, Currency>; quota_keys: string[] }

export interface BillingAccount {
  legal_name: string; tax_id: string | null; address: string; city: string | null; country_code: string;
  billing_email: string; currency: Currency | null; updated_at: string;
}
export interface Subscription {
  id: string; status: string; effective_status: string; pending_transition: string | null;
  product_version_id: string | null; billing_interval: Interval | null; currency: Currency | null;
  trial_end: string | null; cancel_at: string | null; current_period_start: string | null; current_period_end: string | null;
  created_at: string;
  plan: { code: string; name: string; version_label: string; version_status: string } | null;
  items: { product_version_id: string; kind: "plan" | "addon"; quantity: number }[];
  can_cancel: boolean; can_reactivate: boolean;
}
export interface Entitlements { access: "full" | "read_only" | "none"; modules: string[]; quotas: Quotas; display_only: boolean }
export interface Usage { period_start: string; period_end: string; quotas: { key: string; used: number; limit: number | null; unlimited: boolean }[] }
export interface QuoteLine { label: string; unit_amount: string; quantity: number; amount: string; discount: string }
export interface Quote {
  currency: Currency; interval: Interval; promotion_code: string | null; lines: QuoteLine[];
  subtotal: string; discount: string; credit: string; total: string; taxes: null; notes: string[];
}

export interface AdminVersion {
  id: string; product_id: string; version_no: number; label: string; description: string | null;
  status: "draft" | "published" | "retired"; trial_days: number | null; published_at: string | null; retired_at: string | null;
  created_at: string; prices: Price[]; modules: string[]; quotas: Quotas;
}
export interface AdminProduct {
  id: string; code: string; kind: "plan" | "addon"; name: string; description: string | null; display_order: number;
  created_at: string; versions: AdminVersion[];
}
export interface Promotion {
  id: string; code: string; label: string; discount_type: "percent" | "fixed"; percent: string | null;
  fixed_amount: string | null; fixed_currency: Currency | null; product_ids: string[] | null; billing_interval: Interval | null;
  duration: "once" | "repeating" | "forever"; duration_periods: number | null; valid_from: string; valid_until: string | null;
  max_redemptions: number | null; status: "active" | "disabled"; created_at: string;
}
export interface BillingSettings {
  grace_days: number; suspension_to_cancel_days: number | null; renewal_notice_days: number | null; reminder_days: number[];
  max_orgs_per_user: number | null; seller_name: string | null; seller_country: string; seller_tax_id: string | null;
  seller_address: string | null; country_currencies: Record<string, Currency>; updated_at: string;
}

export const CURRENCIES: Currency[] = ["XOF", "XAF", "GNF", "KMF", "CDF"];
/** Décimales ISO 4217 (contrôlées aussi par le serveur et la base). */
export const CURRENCY_DECIMALS: Record<Currency, number> = { XOF: 0, XAF: 0, GNF: 0, KMF: 0, CDF: 2 };
export const CURRENCY_LABELS: Record<Currency, string> = { XOF: "FCFA (XOF)", XAF: "FCFA (XAF)", GNF: "GNF", KMF: "KMF", CDF: "CDF" };
export const INTERVAL_LABELS: Record<Interval, string> = { month: "par mois", year: "par an" };

export const COUNTRY_NAMES: Record<string, string> = {
  BJ: "Bénin", BF: "Burkina Faso", CI: "Côte d'Ivoire", GW: "Guinée-Bissau", ML: "Mali", NE: "Niger", SN: "Sénégal",
  TG: "Togo", CM: "Cameroun", CF: "Centrafrique", CG: "Congo", GA: "Gabon", GQ: "Guinée équatoriale", TD: "Tchad",
  GN: "Guinée", KM: "Comores", CD: "RD Congo",
};

export const QUOTA_LABELS: Record<string, string> = {
  users: "Utilisateurs", companies: "Sociétés", engagements: "Missions d'audit", storage_mb: "Stockage (Mo)",
  imports_per_period: "Imports par période", reports_per_period: "Rapports par période",
  ai_tokens_per_period: "IA : jetons par période",
};

export const SUB_STATUS: Record<string, { label: string; tone: "neutral" | "blue" | "green" | "amber" | "red" }> = {
  trialing: { label: "Essai gratuit", tone: "blue" },
  incomplete: { label: "En attente de paiement", tone: "amber" },
  active: { label: "Actif", tone: "green" },
  past_due: { label: "Impayé (période de grâce)", tone: "amber" },
  suspended: { label: "Suspendu (lecture seule)", tone: "red" },
  canceled: { label: "Résilié", tone: "neutral" },
  expired: { label: "Expiré", tone: "neutral" },
};

export const ACCESS_LABELS: Record<Entitlements["access"], string> = {
  full: "Accès complet", read_only: "Lecture seule (consultation et export)", none: "Aucun accès aux modules",
};

/** Montant texte (« 15000 », « 12.5 ») formaté selon la devise, sans passer par un nombre flottant. */
export function formatMoney(value: string | null | undefined, currency: Currency): string {
  if (value === null || value === undefined || value === "") return "—";
  const [int, frac = ""] = value.replace("-", "").split(".");
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  const d = CURRENCY_DECIMALS[currency];
  const label = currency === "XOF" || currency === "XAF" ? "FCFA" : currency;
  return `${value.startsWith("-") ? "−" : ""}${grouped}${d ? `,${(frac + "00").slice(0, d)}` : ""} ${label}`;
}

export function priceFor(prices: Price[], interval: Interval, currency: Currency): Price | undefined {
  return prices.find((p) => p.billing_interval === interval && p.currency === currency);
}
