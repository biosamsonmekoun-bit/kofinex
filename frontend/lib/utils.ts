import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const dateFmt = new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "short", year: "numeric" });

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return dateFmt.format(new Date(iso.length === 10 ? `${iso}T00:00:00` : iso));
}

/** Montant décimal transmis en texte par l'API (« 17800000.50 ») -> « 17 800 000,50 », sans passer
 *  par un nombre flottant. */
export function formatAmount(value: string | null | undefined, { blankZero = false } = {}): string {
  if (value === null || value === undefined || value === "") return "";
  const negative = value.startsWith("-");
  const [intPart, frac = ""] = value.replace("-", "").split(".");
  if (blankZero && /^0*$/.test(intPart) && /^0*$/.test(frac)) return "";
  const grouped = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, "\u202f");
  return `${negative ? "−" : ""}${grouped},${(frac + "00").slice(0, 2)}`;
}

function decimalFr(value: string, digits: number): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return value;
  return n.toLocaleString("fr-FR", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** Valeur d'indicateur selon son unité (les montants restent formatés sans passer par un flottant). */
export function formatIndicator(value: string | null | undefined, unit: string): string {
  if (value === null || value === undefined) return "—";
  switch (unit) {
    case "amount": return formatAmount(value);
    case "percent": return `${decimalFr(value, 2)} %`;
    case "ratio": return decimalFr(value, 2);
    case "days": return `${decimalFr(value, 0)} j`;
    case "years": return `${decimalFr(value, 1)} an(s)`;
    case "times": return `${decimalFr(value, 2)} ×`;
    default: return value;
  }
}

/** Nombre décimal transmis en texte -> pourcentage français (« 87.5 » -> « 87,5 % »). Affichage uniquement. */
export function formatPct(value: string | null | undefined, digits = 1): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return value;
  return `${n.toLocaleString("fr-FR", { minimumFractionDigits: digits, maximumFractionDigits: digits })} %`;
}

/** Montant arrondi à l'unité pour les tableaux de bord (la valeur exacte reste disponible en infobulle). */
export function formatAmountShort(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return value;
  return n.toLocaleString("fr-FR", { maximumFractionDigits: 0 });
}

