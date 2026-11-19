"use client";

import { useState } from "react";
import Link from "next/link";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { personName, type Engagement, type ReviewNote } from "@/lib/types";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Input, Select } from "@/components/ui/form";

const STATUS = { open: ["Ouverte", "amber"], answered: ["Répondue", "blue"], closed: ["Close", "green"] } as const;

export function NoteCard({ e, n, onChanged }: { e: Engagement; n: ReviewNote; onChanged: () => void }) {
  const [answer, setAnswer] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const caps = e.capabilities ?? [];
  async function act(action: "answer" | "close" | "reopen") {
    setBusy(true);
    setErr(null);
    try { await api.post(`/engagements/${e.id}/review-notes/${n.id}`, { action, response: action === "answer" ? answer : null }); onChanged(); }
    catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }
  return (
    <div className="rounded-md border bg-card p-3 text-sm shadow-card">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground">{personName(n.author)} · {formatDate(n.created_at)}{n.assignee ? ` · pour ${personName(n.assignee)}` : ""}
          {n.object_type === "workpaper" && n.object_label && <> · feuille <Link className="text-link hover:underline" href={`/missions/${e.id}/feuilles/${n.object_id}`}>{n.object_label}</Link></>}</span>
        <Badge tone={STATUS[n.status][1]}>{STATUS[n.status][0]}</Badge>
      </div>
      <p className="mt-2 whitespace-pre-wrap">{n.body}</p>
      {n.response && <p className="mt-2 whitespace-pre-wrap border-l-2 border-primary/40 pl-3 text-muted-foreground">{n.response}</p>}
      {err && <Alert className="mt-2">{err}</Alert>}
      {n.status !== "closed" && caps.includes("answer_review_notes") && (
        <div className="mt-3 flex flex-col gap-2 sm:flex-row">
          {n.status === "open" && <>
            <Input aria-label="Réponse" placeholder="Réponse…" value={answer} onChange={(x) => setAnswer(x.target.value)} />
            <Button size="sm" variant="outline" onClick={() => act("answer")} loading={busy} disabled={!answer.trim()}>Répondre</Button>
          </>}
          <Button size="sm" variant="outline" onClick={() => act("close")} loading={busy}>Clore</Button>
          {n.status === "answered" && <Button size="sm" variant="ghost" onClick={() => act("reopen")} loading={busy}>Rouvrir</Button>}
        </div>
      )}
    </div>
  );
}

export function NotesTab({ e }: { e: Engagement }) {
  const [filter, setFilter] = useState<"open" | "answered" | "closed" | "all">("open");
  const { data, error, loading, reload } = useApiResource<ReviewNote[]>(`/engagements/${e.id}/review-notes?status_filter=${filter}`);
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">Une note se répond puis se clôt (par son auteur, le manager ou l&apos;associé) ; elle ne se supprime pas. Toutes les notes doivent être closes avant l&apos;émission.</p>
        <Select aria-label="Filtrer" className="w-40" value={filter} onChange={(x) => setFilter(x.target.value as typeof filter)}>
          <option value="open">Ouvertes</option><option value="answered">Répondues</option><option value="closed">Closes</option><option value="all">Toutes</option>
        </Select>
      </div>
      {loading && !data && <Loading />}
      {error && <Alert>{error}</Alert>}
      {data && data.length === 0 && <EmptyState title="Aucune note" description="Les notes se rédigent depuis une feuille de travail." />}
      {data?.map((n) => <NoteCard key={n.id} e={e} n={n} onChanged={reload} />)}
    </div>
  );
}
