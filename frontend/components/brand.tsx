import { cn } from "@/lib/utils";

export const BRAND = {
  name: "KOFINEX",
  signature: "Financial Intelligence",
  tagline: "La plateforme intelligente de pilotage financier.",
} as const;

/** Emblème KOFINEX : barres montantes et flèche de croissance, or. */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 40 36" className={cn("h-9 w-10 shrink-0", className)} aria-hidden focusable="false">
      <rect x="2" y="24" width="6" height="10" rx="1" className="fill-accent" />
      <rect x="11" y="18" width="6" height="16" rx="1" className="fill-accent" />
      <rect x="20" y="12" width="6" height="22" rx="1" className="fill-accent" />
      <rect x="29" y="6" width="6" height="28" rx="1" className="fill-accent" />
      <path d="M2 19 13 10l6 4L33 2" fill="none" className="stroke-accent" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M27 2h6.5v6.5" fill="none" className="stroke-accent" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** Logo complet (emblème + nom, signature « Financial Intelligence » facultative). Hérite de la couleur du texte. */
export function Logo({ withSignature = false, size = "md", className }: {
  withSignature?: boolean; size?: "md" | "lg"; className?: string;
}) {
  return (
    <span className={cn("flex items-center gap-2.5", className)}>
      <BrandMark className={size === "lg" ? "h-10 w-11" : undefined} />
      <span className="flex flex-col leading-none">
        <span className={cn("font-extrabold tracking-[0.02em]", size === "lg" ? "text-[26px]" : "text-[22px]")}>{BRAND.name}</span>
        {withSignature && <span className="mt-1 text-[11px] font-medium tracking-[0.01em] opacity-90">{BRAND.signature}</span>}
      </span>
    </span>
  );
}
