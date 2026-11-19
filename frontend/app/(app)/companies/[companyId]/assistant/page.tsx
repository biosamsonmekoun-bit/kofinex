"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ChevronLeft } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { personName, type Company, type FiscalYear } from "@/lib/types";
import { REPORT_STATUS, type AiConversation, type AiMessage, type AiReport, type AiStatus } from "@/lib/ai-types";
import { cn, formatDate } from "@/lib/utils";
import { AiDraftBadge, AiUnavailable, ContextView, NumberCheck } from "@/components/ai-common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, Badge, EmptyState, Loading, PageHeader } from "@/components/ui/feedback";
import { Input, Select } from "@/components/ui/form";

type AnalysisRef = { id: string; status: string; completed_at: string | null };
const AREA = "w-full rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30";

export default function AssistantPage() {
  const { companyId: cid } = useParams<{ companyId: string }>();
  const { data: company } = useApiResource<Company>(`/companies/${cid}`);
  const { data: status } = useApiResource<AiStatus>("/ai/status");
  const { data: years } = useApiResource<FiscalYear[]>(`/companies/${cid}/fiscal-years`);
  const [fy, setFy] = useState("");
  const [tab, setTab] = useState<"chat" | "comments">("chat");
  useEffect(() => { if (!fy && years?.length) setFy(years[years.length - 1].id); }, [years, fy]);
  const { data: analyses } = useApiResource<AnalysisRef[]>(fy ? `/companies/${cid}/fiscal-years/${fy}/analyses` : null);
  const done = analyses?.filter((a) => a.status === "completed") ?? [];
  return (
    <>
      <Link href={`/companies/${cid}`} className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ChevronLeft className="h-4 w-4" /> {company?.name ?? "Entreprise"}
      </Link>
      <PageHeader title="Assistant IA" description="Questions et commentaires sur les analyses financières déjà calculées. Chaque chiffre cité est rapproché du contexte transmis ; l'IA ne calcule ni ne décide rien." />
      <AiUnavailable status={status} />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Select aria-label="Exercice" className="w-48" value={fy} onChange={(x) => setFy(x.target.value)}>
          {years?.map((y) => <option key={y.id} value={y.id}>Exercice {y.label}</option>)}
        </Select>
        <div role="tablist" className="flex gap-1 border-b">
          {([["chat", "Conversations"], ["comments", "Commentaires d'analyse"]] as const).map(([k, l]) => (
            <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
                    className={cn("-mb-px border-b-2 px-3 py-2 text-sm", tab === k ? "border-primary font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground")}>{l}</button>
          ))}
        </div>
      </div>
      {years && years.length === 0 && <EmptyState title="Aucun exercice" description="Créez un exercice, importez la balance et lancez l'analyse." />}
      {fy && analyses && done.length === 0 && (
        <Alert kind="info">Aucune analyse terminée pour cet exercice : l&apos;assistant ne s&apos;appuie que sur des valeurs calculées.{" "}
          <Link className="underline" href={`/companies/${cid}/fiscal-years/${fy}/analysis`}>Ouvrir l&apos;analyse</Link></Alert>
      )}
      {fy && done.length > 0 && tab === "chat" && <Chat cid={cid} fy={fy} />}
      {fy && done.length > 0 && tab === "comments" && <Comments cid={cid} analysis={done[0]} />}
    </>
  );
}

function Chat({ cid, fy }: { cid: string; fy: string }) {
  const { data: convs, reload } = useApiResource<AiConversation[]>(`/companies/${cid}/ai/conversations`);
  const mine = convs?.filter((c) => c.fiscal_year_id === fy) ?? [];
  const [open, setOpen] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { setOpen(null); }, [fy]);
  async function create() {
    setErr(null);
    try { const c = await api.post<AiConversation>(`/companies/${cid}/ai/conversations`, { fiscal_year_id: fy }); await reload(); setOpen(c.id); }
    catch (x) { setErr(errorMessage(x)); }
  }
  return (
    <div className="grid gap-4 lg:grid-cols-[16rem_minmax(0,1fr)]">
      <Card>
        <CardHeader><CardTitle>Conversations</CardTitle><CardDescription>Privées : visibles de vous seul.</CardDescription></CardHeader>
        <CardContent className="space-y-2">
          {err && <Alert>{err}</Alert>}
          <Button size="sm" className="w-full" onClick={create}>Nouvelle conversation</Button>
          {mine.map((c) => (
            <button key={c.id} type="button" onClick={() => setOpen(c.id)}
                    className={cn("block w-full rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted", open === c.id && "bg-muted font-medium")}>
              {c.title ?? "Sans titre"}<span className="block text-xs text-muted-foreground">{formatDate(c.updated_at)}</span>
            </button>
          ))}
          {convs && mine.length === 0 && <p className="text-xs text-muted-foreground">Aucune conversation pour cet exercice.</p>}
        </CardContent>
      </Card>
      {open ? <Thread cid={cid} id={open} onChanged={reload} /> : <EmptyState title="Choisissez ou ouvrez une conversation" description="Le contexte est la dernière analyse terminée de l'exercice." />}
    </div>
  );
}

function Thread({ cid, id, onChanged }: { cid: string; id: string; onChanged: () => void }) {
  const path = `/companies/${cid}/ai/conversations/${id}`;
  const { data, error, setData } = useApiResource<AiConversation & { messages: AiMessage[] }>(path);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  async function send(ev: React.FormEvent) {
    ev.preventDefault(); setBusy(true); setErr(null);
    try {
      const pair = await api.post<AiMessage[]>(`${path}/messages`, { content: q });
      if (data) setData({ ...data, messages: [...data.messages, ...pair] });
      setQ(""); onChanged();
    } catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }
  if (error) return <Alert>{error}</Alert>;
  if (!data) return <Loading />;
  return (
    <Card>
      <CardHeader><CardTitle>{data.title ?? "Conversation"}</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        {data.messages.map((m) => (
          <div key={m.id} className={cn("rounded-md border p-3 text-sm", m.role === "user" ? "bg-muted/40" : "bg-card")}>
            <p className="mb-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              {m.role === "user" ? "Vous" : <><AiDraftBadge /> Réponse IA · {m.model} · {formatDate(m.created_at)}</>}
            </p>
            <p className="whitespace-pre-line">{m.content}</p>
            {m.role === "assistant" && <div className="mt-2 space-y-1"><NumberCheck v={m.validation} /><ContextView s={m.context_snapshot} /></div>}
          </div>
        ))}
        {err && <Alert>{err}</Alert>}
        <form onSubmit={send} className="flex gap-2">
          <Input aria-label="Question" className="flex-1" placeholder="Votre question sur l'analyse…" value={q} onChange={(x) => setQ(x.target.value)} />
          <Button type="submit" loading={busy} disabled={q.trim().length < 2}>Envoyer</Button>
        </form>
        <p className="text-xs text-muted-foreground">Les réponses sont des aides à la lecture, à vérifier : elles ne constituent ni un avis professionnel ni une recommandation de gestion.</p>
      </CardContent>
    </Card>
  );
}

function Comments({ cid, analysis }: { cid: string; analysis: AnalysisRef }) {
  const path = `/companies/${cid}/analyses/${analysis.id}/ai-reports`;
  const { data, error, reload } = useApiResource<{ sections: Record<string, string>; items: AiReport[] }>(path);
  const [section, setSection] = useState("executive_summary");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  async function generate() {
    setBusy(true); setErr(null);
    try { await api.post(path, { section }); await reload(); } catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader><CardTitle>Commentaires d&apos;analyse</CardTitle>
          <CardDescription>Analyse du {formatDate(analysis.completed_at)}. Chaque commentaire reste un brouillon IA jusqu&apos;à sa relecture ; son contenu n&apos;est jamais modifié.</CardDescription></CardHeader>
        <CardContent className="flex flex-wrap items-center gap-2">
          {error && <Alert>{error}</Alert>}
          {err && <Alert>{err}</Alert>}
          <Select aria-label="Section" className="w-96" value={section} onChange={(x) => setSection(x.target.value)}>
            {data && Object.entries(data.sections).map(([k, l]) => <option key={k} value={k}>{l.charAt(0).toUpperCase() + l.slice(1)}</option>)}
          </Select>
          <Button loading={busy} onClick={generate}>Demander un commentaire</Button>
        </CardContent>
      </Card>
      {!data ? <Loading /> : data.items.length === 0 ? <p className="text-sm text-muted-foreground">Aucun commentaire.</p>
        : data.items.map((r) => <ReportCard key={r.id} cid={cid} r={r} label={data.sections[r.section] ?? r.section} onDone={reload} />)}
    </div>
  );
}

function ReportCard({ cid, r, label, onDone }: { cid: string; r: AiReport; label: string; onDone: () => void }) {
  const [note, setNote] = useState("");
  const [err, setErr] = useState<string | null>(null);
  async function review(decision: "reviewed" | "rejected") {
    setErr(null);
    try { await api.post(`/companies/${cid}/ai-reports/${r.id}/review`, { decision, note: note.trim() || null }); onDone(); } catch (x) { setErr(errorMessage(x)); }
  }
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-2">
        <div><CardTitle className="first-letter:uppercase">{label}</CardTitle>
          <CardDescription>{r.model} · {r.prompt_version} · demandé par {personName(r.created_by_user)} le {formatDate(r.created_at)}</CardDescription></div>
        <Badge tone={REPORT_STATUS[r.status][1]}>{REPORT_STATUS[r.status][0]}</Badge>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <p className="whitespace-pre-line">{r.content}</p>
        <NumberCheck v={r.validation} />
        <ContextView s={r.context_snapshot} />
        {r.status !== "draft" && <p className="text-xs text-muted-foreground">{r.status === "reviewed" ? "Relu" : "Rejeté"} par {personName(r.reviewed_by_user)} le {formatDate(r.reviewed_at)}{r.review_note && ` — ${r.review_note}`}</p>}
        {err && <Alert>{err}</Alert>}
        {r.status === "draft" && (
          <div className="space-y-2 border-t pt-2">
            <textarea aria-label="Note de relecture" rows={2} className={AREA} placeholder="Note de relecture (requise pour un rejet)" value={note} onChange={(x) => setNote(x.target.value)} />
            <div className="flex gap-2">
              <Button size="sm" onClick={() => review("reviewed")}>Marquer comme relu</Button>
              <Button size="sm" variant="outline" disabled={note.trim().length < 3} onClick={() => review("rejected")}>Rejeter</Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
