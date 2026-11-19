"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useApiResource } from "@/lib/use-api";
import type { Company } from "@/lib/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, EmptyState, Loading, PageHeader } from "@/components/ui/feedback";

/** Point d'entrée du module : le dispositif de contrôle interne est propre à chaque entité. */
export default function OrgIcPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const { data, error, loading } = useApiResource<Company[]>(`/organizations/${orgId}/companies`);
  return (
    <>
      <PageHeader title="Contrôle interne" description="Choisissez l'entité dont vous pilotez ou consultez le dispositif : référentiels, domaines, risques, contrôles, tests, déficiences et rapports." />
      {error && <Alert>{error}</Alert>}
      {loading && !data && <Loading />}
      {data && data.length === 0 && <EmptyState title="Aucune entreprise" description="Créez d'abord une entreprise dans l'organisation."
                                                action={<Link className="text-sm text-link underline" href={`/organizations/${orgId}/companies`}>Ouvrir les entreprises</Link>} />}
      {data && data.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((c) => (
            <Link key={c.id} href={`/companies/${c.id}/controle-interne`} className="rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
              <Card className="h-full transition-colors hover:border-primary/40">
                <CardHeader><CardTitle>{c.name}</CardTitle><CardDescription>{c.legal_name ?? c.legal_form ?? "Dispositif de contrôle interne"}</CardDescription></CardHeader>
                <CardContent className="text-sm text-link">Ouvrir le tableau de bord →</CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
