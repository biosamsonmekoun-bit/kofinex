"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronLeft } from "lucide-react";
import { useApiResource } from "@/lib/use-api";
import type { Company } from "@/lib/types";
import type { IcAccess } from "@/lib/ic-types";
import { cn } from "@/lib/utils";
import { Alert, Badge, Loading, PageHeader } from "@/components/ui/feedback";

export const AREA = "w-full rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30";

const SPACES: [string, string][] = [
  ["", "Tableau de bord"], ["referentiels", "Référentiels"], ["domaines", "Domaines et processus"], ["risques", "Registre des risques"],
  ["controles", "Contrôles"], ["matrice", "Matrice risques-contrôles"], ["programmes", "Programmes"], ["tests", "Tests et évaluations"],
  ["deficiences", "Déficiences"], ["recommandations", "Recommandations"], ["remediation", "Plans de remédiation"],
  ["suivi", "Suivi des actions"], ["rapports", "Rapports"], ["roles", "Rôles"],
];

/** Cadre commun des espaces du contrôle interne : en-tête de l'entité, droits, navigation entre espaces. */
export function IcShell({ cid, title, description, actions, children }: {
  cid: string; title: string; description?: React.ReactNode; actions?: React.ReactNode;
  children: (access: IcAccess) => React.ReactNode;
}) {
  const pathname = usePathname();
  const base = `/companies/${cid}/controle-interne`;
  const { data: access, error } = useApiResource<IcAccess>(`/companies/${cid}/ic/access`);
  const { data: company } = useApiResource<Company>(`/companies/${cid}`);
  if (error) return <Alert>{error}</Alert>;
  if (!access) return <Loading />;
  return (
    <>
      <Link href={`/companies/${cid}`} className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ChevronLeft className="h-4 w-4" /> {company?.name ?? "Entreprise"}
      </Link>
      <PageHeader title={title} description={
        <span className="flex flex-wrap items-center gap-2">
          <span>Contrôle interne{company ? ` · ${company.name}` : ""}</span>
          {access.is_admin && <Badge tone="blue">Pilote du dispositif</Badge>}
          {access.roles.map((r, i) => <Badge key={i}>{r.role_label}</Badge>)}
          {access.audits && <Badge>Équipe de mission (lecture)</Badge>}
          {description && <span className="w-full">{description}</span>}
        </span>
      } actions={actions} />
      <nav aria-label="Espaces du contrôle interne" className="mb-5 flex gap-1 overflow-x-auto border-b">
        {SPACES.map(([seg, label]) => {
          const href = seg ? `${base}/${seg}` : base;
          const active = seg ? pathname.startsWith(href) : pathname === base;
          return (
            <Link key={seg} href={href} aria-current={active ? "page" : undefined}
                  className={cn("-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
                    active ? "border-primary font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground")}>
              {label}
            </Link>
          );
        })}
      </nav>
      {children(access)}
    </>
  );
}

export function canManage(access: IcAccess, domainId: string | null | undefined) {
  return access.is_admin || (!!domainId && access.managed_domains.includes(domainId));
}
