"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronLeft } from "lucide-react";
import { useApiResource } from "@/lib/use-api";
import { useWorkspace } from "@/lib/workspace";
import type { Company, FiscalYear } from "@/lib/types";
import type { AccSettings } from "@/lib/accounting-types";
import { cn } from "@/lib/utils";
import { Alert, Badge, EmptyState, Loading, PageHeader } from "@/components/ui/feedback";

/** Espaces de la comptabilité native réellement disponibles (étapes A et B du lot 3B). */
export const ACC_SPACES: [string, string][] = [
  ["", "Écritures"], ["nouvelle", "Nouvelle écriture"], ["grand-livre", "Grand livre"], ["balance", "Balance"], ["lettrage", "Lettrage"],
  ["journaux", "Journaux"], ["plan-comptable", "Plan comptable"], ["tiers", "Tiers"], ["fec", "FEC"], ["parametres", "Paramètres"],
];

export interface AccContext { cid: string; settings: AccSettings; fy: FiscalYear | null; years: FiscalYear[] }

/** Cadre des écrans de la comptabilité native : entreprise, exercice choisi dans la barre supérieure, droits, navigation. */
export function AccountingShell({ cid, title, description, actions, needFy = false, children }: {
  cid: string; title: string; description?: React.ReactNode; actions?: React.ReactNode; needFy?: boolean;
  children: (ctx: AccContext) => React.ReactNode;
}) {
  const pathname = usePathname();
  const base = `/companies/${cid}/comptabilite`;
  const ws = useWorkspace();
  const { data: settings, error } = useApiResource<AccSettings>(`/companies/${cid}/accounting/settings`);
  const { data: company } = useApiResource<Company>(`/companies/${cid}`);
  const { data: yearsRaw } = useApiResource<FiscalYear[]>(`/companies/${cid}/fiscal-years`);
  if (error) return <Alert>{error}</Alert>;
  if (!settings || !yearsRaw) return <Loading />;
  const years = [...yearsRaw].sort((a, b) => b.end_date.localeCompare(a.end_date));
  const fy = (ws.fy && ws.fy.company_id === cid ? ws.fy : null) ?? years[0] ?? null;
  return (
    <>
      <Link href={`/companies/${cid}`} className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ChevronLeft className="h-4 w-4" aria-hidden /> {company?.name ?? "Entreprise"}
      </Link>
      <PageHeader title={title} actions={actions} description={
        <span className="flex flex-wrap items-center gap-2">
          <span>Comptabilité générale{company ? ` · ${company.name}` : ""}{fy ? ` · exercice ${fy.label}` : ""}</span>
          {fy && fy.status !== "open" && <Badge tone="amber">Exercice clôturé : lecture seule</Badge>}
          {!settings.permissions.write && <Badge>Lecture seule</Badge>}
          {settings.review_required && <Badge tone="blue">Revue avant validation</Badge>}
          {description && <span className="w-full">{description}</span>}
        </span>
      } />
      <nav aria-label="Espaces de la comptabilité" className="mb-5 flex gap-1 overflow-x-auto border-b">
        {ACC_SPACES.filter(([seg]) => seg !== "fec" || settings.permissions.fec).map(([seg, label]) => {
          const href = seg ? `${base}/${seg}` : base;
          const active = seg ? pathname.startsWith(href) : pathname === base || pathname.startsWith(`${base}/ecritures`);
          return (
            <Link key={seg} href={href} aria-current={active ? "page" : undefined}
                  className={cn("-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
                    active ? "border-primary font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground")}>
              {label}
            </Link>
          );
        })}
      </nav>
      {needFy && !fy
        ? <EmptyState title="Aucun exercice" description="Créez un exercice pour cette entreprise avant de saisir ou de consulter des écritures."
                      action={<Link className="text-sm font-medium text-link underline" href={`/companies/${cid}`}>Ouvrir l&apos;entreprise</Link>} />
        : children({ cid, settings, fy, years })}
    </>
  );
}
