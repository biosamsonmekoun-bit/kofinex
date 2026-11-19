"use client";

import { useParams } from "next/navigation";
import { AuditLogTable } from "@/components/audit-log-table";
import { PageHeader } from "@/components/ui/feedback";

export default function OrgAuditPage() {
  const { orgId } = useParams<{ orgId: string }>();
  return (
    <>
      <PageHeader title="Journal d'audit"
                  description="Historique non modifiable des opérations effectuées dans l'organisation." />
      <AuditLogTable basePath={`/organizations/${orgId}`} />
    </>
  );
}
