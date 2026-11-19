"use client";

import { useParams } from "next/navigation";
import { AccountingShell } from "@/components/accounting-shell";
import { EntryEditor } from "@/components/entry-editor";
import { Alert } from "@/components/ui/feedback";

export default function NewEntryPage() {
  const { companyId: cid } = useParams<{ companyId: string }>();
  return (
    <AccountingShell cid={cid} title="Nouvelle écriture" needFy>
      {({ fy, settings }) => settings.permissions.write
        ? <EntryEditor cid={cid} fy={fy!} />
        : <Alert kind="warning">Votre rôle sur cette entreprise ne permet pas la saisie (comptables et administrateurs).</Alert>}
    </AccountingShell>
  );
}
