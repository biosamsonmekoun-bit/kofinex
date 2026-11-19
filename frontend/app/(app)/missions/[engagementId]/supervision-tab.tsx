"use client";

import { useState } from "react";
import { CheckCircle2, CircleAlert } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { PROCEDURE_STATUS_LABELS, SIGNOFF_LABELS, WORKPAPER_STATUS_LABELS, personName, type Engagement, type Supervision } from "@/lib/types";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, Badge, Loading } from "@/components/ui/feedback";
import { KpiCard, KpiGrid } from "@/components/ui/kpi-card";

export function SupervisionTab({ e, onSigned }: { e: Engagement; onSigned: () => void }) {
  const { data: s, error, loading } = useApiResource<Supervision>(`/engagements/${e.id}/supervision`);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const caps = e.capabilities ?? [];

  async function sign(role: "quality_reviewer" | "approver") {
    setBusy(role);
    setErr(null);
    try { await api.post(`/engagements/${e.id}/sign`, { role }); onSigned(); }
    catch (x) { setErr(errorMessage(x)); } finally { setBusy(null); }
  }

  if (loading && !s) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  if (!s) return null;
  const totalWp = Object.values(s.workpapers).reduce((a, b) => a + b, 0);
  const totalPr = Object.values(s.procedures).reduce((a, b) => a + b, 0);
  const active = s.engagement_signoffs.filter((x) => !x.revoked_at);

  return (
    <div className="space-y-5">
      <KpiGrid>
        <KpiCard label="Feuilles approuvées" value={`${s.workpapers.approved} / ${totalWp}`}
                 hint={`${s.workpapers.draft} brouillon · ${s.workpapers.prepared} préparée(s) · ${s.workpapers.reviewed} revue(s)`} />
        <KpiCard label="Procédures réalisées" value={`${s.procedures.done + s.procedures.not_applicable} / ${totalPr}`}
                 hint={`${s.procedures.in_progress} en cours · ${s.overdue_procedures.length} en retard`} />
        <KpiCard label="Notes de revue à traiter" value={String(s.open_notes + s.answered_notes)} hint={`${s.open_notes} ouverte(s) · ${s.answered_notes} répondue(s)`} />
        <KpiCard label="Risques sans procédure" value={`${s.risks_uncovered.length} / ${s.risks_total}`}
                 hint={s.significant_uncovered ? `dont ${s.significant_uncovered} significatif(s)` : "Couverture du programme"} />
      </KpiGrid>
      {err && <Alert>{err}</Alert>}
      <div className="grid gap-5 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Conditions d&apos;émission</CardTitle>
            <CardDescription>Vérifiées aussi par la base de données au moment de l&apos;émission.</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm">
              {s.issuance_checks.map((c) => (
                <li key={c.code} className="flex items-start gap-2">
                  {c.passed ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-label="Rempli" />
                    : <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-label="Non rempli" />}
                  <span>{c.label}{c.detail && <span className="block text-xs text-muted-foreground">{c.detail}</span>}</span>
                </li>
              ))}
            </ul>
            {e.status === "reporting" && (
              <div className="mt-4 flex flex-wrap gap-2">
                {caps.includes("sign_quality") && !active.some((x) => x.signoff_role === "quality_reviewer") && (
                  <Button size="sm" variant="outline" onClick={() => sign("quality_reviewer")} loading={busy === "quality_reviewer"}>Signer la revue qualité</Button>
                )}
                {caps.includes("approve_engagement") && !active.some((x) => x.signoff_role === "approver") && (
                  <Button size="sm" onClick={() => sign("approver")} loading={busy === "approver"}>Approuver la mission</Button>
                )}
              </div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Signatures de la mission</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            {s.engagement_signoffs.length === 0 && <p className="text-muted-foreground">Aucune signature (revue qualité et approbation se font en phase de rapport).</p>}
            {s.engagement_signoffs.map((x) => (
              <div key={x.id} className="flex flex-wrap items-center justify-between gap-2 border-b pb-2">
                <span>{SIGNOFF_LABELS[x.signoff_role]} <strong>{personName(x.user)}</strong> — {formatDate(x.signed_at)}</span>
                {x.revoked_at ? <Badge tone="neutral">Révoquée : {x.revoked_reason}</Badge> : <Badge tone="green">Active</Badge>}
              </div>
            ))}
            {s.members_pending_independence.length > 0 && (
              <Alert kind="warning">Indépendance non déclarée : {s.members_pending_independence.join(", ")}.</Alert>
            )}
          </CardContent>
        </Card>
      </div>
      {(s.risks_uncovered.length > 0 || s.overdue_procedures.length > 0) && (
        <div className="grid gap-5 xl:grid-cols-2">
          {s.risks_uncovered.length > 0 && (
            <Card>
              <CardHeader><CardTitle>Risques non couverts</CardTitle></CardHeader>
              <CardContent className="space-y-1 text-sm">
                {s.risks_uncovered.map((r) => <p key={r.id}><span className="font-medium">{r.code}</span> {r.title} {r.is_significant && <Badge tone="red">Significatif</Badge>}</p>)}
              </CardContent>
            </Card>
          )}
          {s.overdue_procedures.length > 0 && (
            <Card>
              <CardHeader><CardTitle>Procédures en retard</CardTitle></CardHeader>
              <CardContent className="space-y-1 text-sm">
                {s.overdue_procedures.map((p) => <p key={p.id}><span className="font-medium">{p.code}</span> {p.title} — échéance {formatDate(p.due_date)} ({PROCEDURE_STATUS_LABELS[p.status as keyof typeof PROCEDURE_STATUS_LABELS]})</p>)}
              </CardContent>
            </Card>
          )}
        </div>
      )}
      <p className="text-xs text-muted-foreground">Statuts des feuilles : {Object.entries(WORKPAPER_STATUS_LABELS).map(([k, v]) => `${v} ${s.workpapers[k as keyof Supervision["workpapers"]]}`).join(" · ")}</p>
    </div>
  );
}
