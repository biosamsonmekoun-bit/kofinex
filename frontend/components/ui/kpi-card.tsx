import * as React from "react";
import { ArrowDownRight, ArrowRight, ArrowUpRight } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Carte KPI : libellé, valeur (chiffres tabulaires), comparaison facultative.
 * La valeur est déjà formatée par l'appelant ; la carte n'effectue aucun calcul.
 * `trend` indique seulement le sens de la variation : le composant ne juge pas si elle est favorable.
 */
export function KpiCard({ label, value, hint, delta, trend, onClick, className }: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  delta?: string | null;
  trend?: "up" | "down" | "flat" | null;
  onClick?: () => void;
  className?: string;
}) {
  const TrendIcon = trend === "up" ? ArrowUpRight : trend === "down" ? ArrowDownRight : ArrowRight;
  const body = (
    <>
      <p className="truncate text-xs font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className="mt-2 truncate text-2xl font-semibold tabular-nums tracking-tight">{value}</p>
      {(delta || hint) && (
        <div className="mt-1.5 flex items-center gap-2 text-xs text-muted-foreground">
          {delta && (
            <span className="inline-flex items-center gap-0.5 font-medium tabular-nums text-foreground">
              {trend && <TrendIcon className="h-3.5 w-3.5" aria-hidden />}{delta}
            </span>
          )}
          {hint && <span className="truncate">{hint}</span>}
        </div>
      )}
    </>
  );
  const base = "relative overflow-hidden rounded-lg border bg-card p-4 text-left text-card-foreground shadow-card";
  return onClick ? (
    <button type="button" onClick={onClick}
            className={cn(base, "transition-colors hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring", className)}>
      {body}
    </button>
  ) : (
    <div className={cn(base, className)}>{body}</div>
  );
}

export function KpiGrid({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("grid gap-3 sm:grid-cols-2 xl:grid-cols-4", className)}>{children}</div>;
}
