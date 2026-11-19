"use client";

import { useState } from "react";
import { useApiResource } from "@/lib/use-api";
import { Button } from "@/components/ui/button";
import { Alert, EmptyState, Loading } from "@/components/ui/feedback";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

interface AuditEntry {
  id: string;
  user_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  changes: Record<string, unknown> | null;
  created_at: string;
}

const ACTION_LABELS: Record<string, string> = {
  INSERT: "Création", UPDATE: "Modification", DELETE: "Suppression",
  "fiscal_year.closed": "Clôture d'exercice", "fiscal_year.reopened": "Réouverture d'exercice",
  "member.invitation_sent": "Invitation envoyée",
};
const ENTITY_LABELS: Record<string, string> = {
  organizations: "Organisation", organization_members: "Membre", companies: "Entreprise",
  company_members: "Attribution", fiscal_years: "Exercice", import_jobs: "Import",
  financial_statements: "État financier", budgets: "Budget", integrations: "Intégration",
  subscriptions: "Abonnement",
};
const PAGE = 50;
const dt = new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "medium" });

export function AuditLogTable({ basePath }: { basePath: string }) {
  const [offset, setOffset] = useState(0);
  const { data, error, loading } =
    useApiResource<{ items: AuditEntry[]; total: number }>(`${basePath}/audit-logs?limit=${PAGE}&offset=${offset}`);

  if (loading && !data) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  if (!data || data.total === 0) return <EmptyState title="Aucun événement journalisé" />;

  return (
    <div className="space-y-3">
      <Table>
        <THead><tr><TH>Date</TH><TH>Action</TH><TH>Objet</TH><TH>Détail</TH></tr></THead>
        <TBody>
          {data.items.map((e) => (
            <TR key={e.id}>
              <TD className="whitespace-nowrap tabular-nums text-muted-foreground">{dt.format(new Date(e.created_at))}</TD>
              <TD>{ACTION_LABELS[e.action] ?? e.action}</TD>
              <TD>{ENTITY_LABELS[e.entity_type] ?? e.entity_type}</TD>
              <TD>
                {e.changes && (
                  <details>
                    <summary className="cursor-pointer text-xs text-link">{Object.keys(e.changes).length} champ(s)</summary>
                    <pre className="mt-1 max-w-xl overflow-x-auto rounded bg-muted p-2 text-xs">
                      {JSON.stringify(e.changes, null, 2)}
                    </pre>
                  </details>
                )}
              </TD>
            </TR>
          ))}
        </TBody>
      </Table>
      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>{offset + 1}–{Math.min(offset + PAGE, data.total)} sur {data.total}</span>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" disabled={offset === 0} onClick={() => setOffset(offset - PAGE)}>Précédent</Button>
          <Button size="sm" variant="outline" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>Suivant</Button>
        </div>
      </div>
    </div>
  );
}
