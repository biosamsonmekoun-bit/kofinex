import * as React from "react";
import { AlertCircle, AlertTriangle, CheckCircle2, Info, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export function Badge({ className, tone = "neutral", ...props }:
  React.HTMLAttributes<HTMLSpanElement> & { tone?: "neutral" | "blue" | "green" | "amber" | "red" | "gold" }) {
  // tons : neutre, information (bleu), succès, avertissement, risque, prestige (or, avec modération)
  const tones = {
    neutral: "border-border bg-muted text-muted-foreground",
    blue: "border-primary/20 bg-primary/10 text-link",
    green: "border-success/25 bg-success/10 text-success-strong",
    amber: "border-warning/30 bg-warning/10 text-warning-strong",
    red: "border-destructive/25 bg-destructive/10 text-destructive-strong",
    gold: "border-accent/40 bg-accent/10 text-foreground",
  };
  return <span className={cn("inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium", tones[tone], className)} {...props} />;
}

export function Alert({ kind = "error", children, className }:
  { kind?: "error" | "success" | "info" | "warning"; children: React.ReactNode; className?: string }) {
  const styles = {
    error: "border-destructive/30 bg-destructive/10 [&_svg]:text-destructive",
    success: "border-success/30 bg-success/10 [&_svg]:text-success",
    info: "border-info/30 bg-info/10 [&_svg]:text-info",
    warning: "border-warning/40 bg-warning/10 [&_svg]:text-warning",
  };
  const Icon = { error: AlertCircle, success: CheckCircle2, info: Info, warning: AlertTriangle }[kind];
  return (
    <div role={kind === "error" ? "alert" : "status"}
         className={cn("flex items-start gap-2 rounded-md border px-3 py-2 text-sm text-foreground", styles[kind], className)}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div>{children}</div>
    </div>
  );
}

export function Loading({ label = "Chargement…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-10 text-sm text-muted-foreground" role="status" aria-live="polite">
      <Loader2 className="h-4 w-4 animate-spin text-primary" aria-hidden /> {label}
    </div>
  );
}

export function EmptyState({ title, description, action }:
  { title: string; description?: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed bg-card px-6 py-12 text-center">
      <div className="mb-3 h-px w-8 bg-accent" aria-hidden />
      <p className="font-semibold">{title}</p>
      {description && <p className="mt-1 max-w-md text-sm text-muted-foreground">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function PageHeader({ title, description, actions }:
  { title: string; description?: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        {description && <div className="mt-1 text-sm text-muted-foreground">{description}</div>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}
