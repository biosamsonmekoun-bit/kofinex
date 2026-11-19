"use client";

import Link from "next/link";
import { useWorkspace } from "@/lib/workspace";
import { DashboardView } from "@/components/dashboard-view";
import { Alert, EmptyState, Loading, PageHeader } from "@/components/ui/feedback";

/** Tableau de bord de l'entreprise, de l'exercice et de la période choisis dans la barre supérieure (données réelles). */
export default function DashboardPage() {
  const ws = useWorkspace();
  const header = <PageHeader title="Tableau de bord" description="Vue synthétique de la situation financière et opérationnelle" />;
  const link = (href: string, label: string) => <Link href={href} className="text-sm font-medium text-link underline">{label}</Link>;

  if (ws.orgs === null) return <Loading />;
  if (!ws.orgs.length)
    return <>{header}<EmptyState title="Aucune organisation" description="Créez votre organisation ou faites-vous inviter pour commencer." action={link("/organizations", "Créer une organisation")} /></>;
  if (!ws.org || ws.companies === null) return <Loading />;
  if (!ws.company)
    return <>{header}<EmptyState title="Aucune entreprise" description={`L'organisation ${ws.org.name} ne compte encore aucune entreprise.`} action={link(`/organizations/${ws.org.id}/companies`, "Ajouter une entreprise")} /></>;
  if (ws.years === null) return <Loading />;
  if (!ws.fy)
    return <>{header}<EmptyState title="Aucun exercice" description={`Créez un exercice pour ${ws.company.name}, puis importez et validez sa balance.`} action={link(`/companies/${ws.company.id}`, "Ouvrir l'entreprise")} /></>;
  if (ws.dashboard.error) return <>{header}<Alert>{ws.dashboard.error}</Alert></>;
  const d = ws.dashboard.data;
  if (!d || d.fiscal_year.id !== ws.fy.id || d.period.key !== ws.period) return <Loading label="Chargement du tableau de bord…" />;

  const isManager = ws.org.my_role === "owner" || ws.org.my_role === "admin";
  const noData = !d.analysis && !d.breakdown_source && !d.monthly.available;
  return (
    <>
      {noData && (
        <Alert kind="info" className="mb-4">
          Aucune donnée validée pour l&apos;exercice {d.fiscal_year.label} : importez et validez la balance (et, pour le suivi mensuel, le grand livre),
          puis lancez l&apos;analyse financière. {link(`/companies/${d.company.id}`, "Ouvrir l'entreprise")}
        </Alert>
      )}
      <DashboardView data={d} links={{
        alerts: d.analysis ? `/companies/${d.company.id}/fiscal-years/${d.fiscal_year.id}/analysis` : `/companies/${d.company.id}`,
        activities: isManager ? `/organizations/${ws.org.id}/audit` : null,
      }} />
    </>
  );
}
