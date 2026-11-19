"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { AccountingShell } from "@/components/accounting-shell";
import { api, errorMessage } from "@/lib/api";
import type { AccSettings } from "@/lib/accounting-types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert } from "@/components/ui/feedback";

export default function AccountingSettingsPage() {
  const { companyId: cid } = useParams<{ companyId: string }>();
  return <AccountingShell cid={cid} title="Paramètres comptables">{({ settings }) => <SettingsForm cid={cid} initial={settings} />}</AccountingShell>;
}

function SettingsForm({ cid, initial }: { cid: string; initial: AccSettings }) {
  const [s, setS] = useState({ review_required: initial.review_required, segregation_required: initial.segregation_required });
  const [msg, setMsg] = useState<{ kind: "error" | "success"; text: string } | null>(null);
  const can = initial.permissions.settings;
  async function save() {
    setMsg(null);
    try { await api.put(`/companies/${cid}/accounting/settings`, s); setMsg({ kind: "success", text: "Paramètres enregistrés." }); }
    catch (e) { setMsg({ kind: "error", text: errorMessage(e) }); }
  }
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader><CardTitle>Circuit de validation</CardTitle></CardHeader>
        <CardContent className="space-y-3 text-sm">
          {!can && <Alert kind="info">Ces paramètres sont réservés aux administrateurs de l&apos;organisation.</Alert>}
          {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}
          <label className="flex items-start gap-2"><input type="checkbox" className="mt-1" disabled={!can} checked={s.review_required} onChange={(e) => setS({ ...s, review_required: e.target.checked })} />
            <span><span className="font-medium">Étape de revue avant la validation</span><br /><span className="text-muted-foreground">Brouillon → soumise → en revue → validée.</span></span></label>
          <label className="flex items-start gap-2"><input type="checkbox" className="mt-1" disabled={!can} checked={s.segregation_required} onChange={(e) => setS({ ...s, segregation_required: e.target.checked })} />
            <span><span className="font-medium">Séparation des tâches</span><br /><span className="text-muted-foreground">Le réviseur et le validateur sont différents de l&apos;auteur de l&apos;écriture (recommandé).</span></span></label>
          {can && <Button onClick={() => void save()}>Enregistrer</Button>}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Règles appliquées par KOFINEX</CardTitle></CardHeader>
        <CardContent className="text-sm">
          <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
            <li>Une écriture est soumise seulement si elle est équilibrée, porte au moins deux lignes, des comptes ouverts et actifs, et un tiers sur chaque compte collectif.</li>
            <li>Le numéro définitif (préfixe du journal + numéro d&apos;ordre par exercice) est attribué à la validation, sans trou ni doublon.</li>
            <li>Une écriture validée est immuable : toute correction passe par une extourne puis une nouvelle écriture.</li>
            <li>Un exercice clôturé n&apos;accepte plus aucune écriture.</li>
            <li>Ces règles sont imposées par la base de données, pas seulement par l&apos;écran.</li>
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
