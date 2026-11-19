"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Check, ChevronLeft, ShieldCheck } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { ENGAGEMENT_STATUS_LABELS, ENGAGEMENT_STATUS_TONE, type Engagement, type EngagementStatus } from "@/lib/types";
import { cn, formatDate } from "@/lib/utils";
import { rememberOrg } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, Loading, PageHeader } from "@/components/ui/feedback";
import { Field, Input } from "@/components/ui/form";
import { AiTab } from "./ai-tab";
import { DocumentsTab } from "./documents-tab";
import { EvidenceTab } from "./evidence-tab";
import { FinancialAuditTab } from "./fa-tab";
import { FindingsTab } from "./findings-tab";
import { IcTab } from "./ic-tab";
import { LedgerTab } from "./ledger-tab";
import { ReportTab } from "./report-tab";
import { NotesTab } from "./notes-tab";
import { ProgramTab } from "./program-tab";
import { RisksTab } from "./risks-tab";
import { SupervisionTab } from "./supervision-tab";
import { TeamTab } from "./team-tab";
import { WorkpapersTab } from "./workpapers-tab";

const PHASES: EngagementStatus[] = ["planning", "fieldwork", "review", "reporting", "issued", "archived"];
const TABS = [["supervision", "Supervision"], ["team", "Équipe"], ["risks", "Risques"], ["program", "Programme"],
  ["fa", "Audit financier"], ["ic", "Contrôle interne"], ["ledger", "Grand livre"], ["findings", "Constats et recommandations"], ["report", "Rapport"],
  ["workpapers", "Feuilles de travail"], ["evidence", "Éléments probants"], ["notes", "Notes de revue"], ["documents", "Documents"], ["ai", "Assistant IA"]] as const;
const FA_TYPES = ["statutory_audit", "contractual_audit"];
const IA_TYPES = ["internal_audit", "ic_assessment"];
const FINDINGS_TABS = ["findings", "report"];
type Tab = (typeof TABS)[number][0];

function Stepper({ status }: { status: EngagementStatus }) {
  const idx = PHASES.indexOf(status);
  return (
    <ol className="mb-5 flex flex-wrap items-center gap-1 text-xs" aria-label="Phases de la mission">
      {PHASES.map((p, i) => (
        <li key={p} className="flex items-center gap-1">
          <span className={cn("flex items-center gap-1 rounded-full border px-2.5 py-1",
            i < idx && "border-success/30 bg-success/10 text-success-strong",
            i === idx && "border-primary bg-primary text-primary-foreground",
            i > idx && "text-muted-foreground")} aria-current={i === idx ? "step" : undefined}>
            {i < idx && <Check className="h-3 w-3" aria-hidden />}{ENGAGEMENT_STATUS_LABELS[p]}
          </span>
          {i < PHASES.length - 1 && <span className="h-px w-3 bg-border" aria-hidden />}
        </li>
      ))}
    </ol>
  );
}

function Independence({ e, onDone }: { e: Engagement; onDone: (x: Engagement) => void }) {
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    setBusy(true);
    setError(null);
    try { onDone(await api.post<Engagement>(`/engagements/${e.id}/independence`, { statement: text })); }
    catch (err) { setError(errorMessage(err)); } finally { setBusy(false); }
  }
  return (
    <Card className="mb-5 border-warning/40">
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-warning" aria-hidden /> Déclaration d&apos;indépendance</CardTitle>
        <CardDescription>Vous êtes {e.my_role_label?.toLowerCase()} de cette mission. L&apos;accès au dossier et les signatures sont ouverts une fois votre indépendance déclarée, par vous-même ; la déclaration est horodatée et journalisée.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-3">
          {error && <Alert>{error}</Alert>}
          <Field label="Déclaration" htmlFor="ind" hint="Rédigez votre déclaration selon les règles de votre cabinet (10 caractères minimum).">
            <textarea id="ind" value={text} onChange={(x) => setText(x.target.value)} rows={3} maxLength={4000}
                      className="w-full rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30" />
          </Field>
          <Button type="submit" loading={busy} disabled={text.trim().length < 10}>Je confirme mon indépendance</Button>
        </form>
      </CardContent>
    </Card>
  );
}

export default function MissionPage() {
  const { engagementId } = useParams<{ engagementId: string }>();
  const search = useSearchParams();
  const router = useRouter();
  const { data: e, error, loading, setData } = useApiResource<Engagement>(`/engagements/${engagementId}`);
  const requested = TABS.some(([t]) => t === search.get("tab")) ? search.get("tab") : null;
  const [transition, setTransition] = useState<EngagementStatus | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => { if (e) rememberOrg(e.organization_id); }, [e]);
  if (loading && !e) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  if (!e) return null;

  const caps = e.capabilities ?? [];
  const canRead = caps.includes("read_dossier");
  const canFindings = caps.includes("read_findings") && IA_TYPES.includes(e.engagement_type);
  const visible = (id: string) => id === "team"
    || ((FINDINGS_TABS.includes(id) ? canFindings : canRead) && (id !== "fa" || FA_TYPES.includes(e.engagement_type))
        && (id !== "ledger" || !!e.fiscal_year_id)
        && (id !== "ic" || [...IA_TYPES, ...FA_TYPES].includes(e.engagement_type)));
  const tab = (requested && visible(requested) ? requested : canRead ? "supervision" : canFindings ? "findings" : "team") as Tab;
  const needsIndependence = caps.includes("confirm_independence");
  const reopening = transition !== null && ["issued", "archived"].includes(e.status) && transition === "reporting";

  async function move() {
    if (!transition) return;
    setBusy(true);
    setActionError(null);
    try {
      setData(await api.post<Engagement>(`/engagements/${e!.id}/status`, { to: transition, reopen_reason: reopening ? reason : null }));
      setTransition(null);
      setReason("");
      setRefresh((x) => x + 1);
    } catch (err) {
      setActionError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Link href={`/organizations/${e.organization_id}/missions`} className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ChevronLeft className="h-4 w-4" /> Missions
      </Link>
      <PageHeader
        title={`${e.reference} — ${e.name}`}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <Badge tone={ENGAGEMENT_STATUS_TONE[e.status]}>{ENGAGEMENT_STATUS_LABELS[e.status]}</Badge>
            <span>{e.type_label} · {e.company_name}{e.fiscal_year_label ? ` · exercice ${e.fiscal_year_label}` : ""}</span>
            {e.my_role_label ? <Badge tone="blue">{e.my_role_label}</Badge> : <Badge>Non affecté</Badge>}
            {e.methodology && <span className="text-xs">Méthodologie : {e.methodology.name} {e.methodology.version_label}</span>}
          </span>
        }
        actions={(e.next_statuses ?? []).map((s) => (
          <Button key={s} size="sm" variant={s === "issued" ? "default" : "outline"} onClick={() => { setTransition(s); setActionError(null); }}>
            {["issued", "archived"].includes(e.status) && s === "reporting" ? "Rouvrir" : `Passer en « ${ENGAGEMENT_STATUS_LABELS[s]} »`}
          </Button>
        ))}
      />
      <Stepper status={e.status} />
      {e.issued_at && <Alert kind="success" className="mb-4">Mission émise le {formatDate(e.issued_at)} : le dossier est figé.</Alert>}
      {e.reopen_reason && e.reopened_at && <Alert kind="info" className="mb-4">Rouverte le {formatDate(e.reopened_at)} : {e.reopen_reason}</Alert>}
      {needsIndependence && <Independence e={e} onDone={(x) => { setData(x); setRefresh((r) => r + 1); }} />}
      {!e.my_role && <Alert kind="info" className="mb-4">Vous n&apos;êtes pas membre de cette mission : seuls l&apos;en-tête et l&apos;équipe sont visibles. {e.is_org_admin && "En tant qu'administrateur, vous pouvez composer l'équipe (onglet Équipe) ; toute affectation est journalisée."}</Alert>}
      {e.my_role === "auditee" && <Alert kind="info" className="mb-4">Vous êtes l&apos;interlocuteur audité : le dossier de travail de l&apos;équipe d&apos;audit ne vous est pas accessible.{canFindings && " Les constats qui vous sont communiqués, vos réponses et vos plans d'action figurent dans l'onglet « Constats et recommandations »."}</Alert>}

      <div role="tablist" className="mb-5 flex gap-1 overflow-x-auto border-b">
        {TABS.filter(([id]) => visible(id)).map(([id, label]) => (
          <button key={id} role="tab" aria-selected={tab === id}
                  onClick={() => router.replace(`/missions/${e.id}?tab=${id}`, { scroll: false })}
                  className={cn("-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
                    tab === id ? "border-primary font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground")}>
            {label}
          </button>
        ))}
      </div>
      <div key={refresh}>
        {tab === "team" && <TeamTab e={e} onChanged={(members) => setData({ ...e, members })} />}
        {canRead && tab === "supervision" && <SupervisionTab e={e} onSigned={() => setRefresh((x) => x + 1)} />}
        {canRead && tab === "risks" && <RisksTab e={e} />}
        {canRead && tab === "program" && <ProgramTab e={e} />}
        {canRead && tab === "fa" && FA_TYPES.includes(e.engagement_type) && <FinancialAuditTab e={e} />}
        {canRead && tab === "ic" && <IcTab e={e} />}
        {canRead && tab === "ledger" && e.fiscal_year_id && <LedgerTab e={e} />}
        {canFindings && tab === "findings" && <FindingsTab e={e} />}
        {canFindings && tab === "report" && <ReportTab e={e} />}
        {canRead && tab === "workpapers" && <WorkpapersTab e={e} />}
        {canRead && tab === "evidence" && <EvidenceTab e={e} />}
        {canRead && tab === "notes" && <NotesTab e={e} />}
        {canRead && tab === "documents" && <DocumentsTab e={e} />}
        {canRead && tab === "ai" && <AiTab e={e} />}
        {!canRead && !FINDINGS_TABS.includes(tab) && tab !== "team" && !needsIndependence && e.my_role && e.my_role !== "auditee" && <Alert kind="info">Dossier non accessible.</Alert>}
      </div>

      <Dialog open={transition !== null} onClose={() => setTransition(null)}
              title={transition ? (reopening ? "Rouvrir la mission" : `Passer en « ${ENGAGEMENT_STATUS_LABELS[transition]} »`) : ""}
              description={transition === "issued" ? "L'émission fige le dossier : feuilles, éléments probants et notes ne seront plus modifiables." : undefined}>
        <div className="space-y-3">
          {actionError && <Alert>{actionError}</Alert>}
          {reopening && (
            <Field label="Motif de réouverture" htmlFor="reopen" required hint="Obligatoire ; conservé avec la mission et au journal.">
              <Input id="reopen" value={reason} onChange={(x) => setReason(x.target.value)} maxLength={2000} />
            </Field>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setTransition(null)}>Annuler</Button>
            <Button onClick={move} loading={busy} disabled={reopening && reason.trim().length < 10}>Confirmer</Button>
          </div>
        </div>
      </Dialog>
    </>
  );
}
