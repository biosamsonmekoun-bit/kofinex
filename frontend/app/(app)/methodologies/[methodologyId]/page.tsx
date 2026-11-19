"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Archive, ChevronLeft, FileUp, Send } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import type { Methodology, MethodologyItem } from "@/lib/types";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, Badge, EmptyState, Loading, PageHeader } from "@/components/ui/feedback";
import { Input } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const STATUS = { draft: ["Brouillon", "neutral"], published: ["Publiée", "green"], archived: ["Archivée", "amber"] } as const;
const TYPE_LABELS: Record<string, string> = {
  assertion: "Assertions", cycle: "Cycles", risk_scale: "Grille de cotation des risques", procedure_template: "Programmes types",
  ic_component: "Composantes du contrôle interne", ic_principle: "Principes", deficiency_scale: "Échelle des déficiences", parameter: "Paramètres", finding_scale: "Échelle des constats",
};
type Issue = { severity: string; row: number; message: string };

export default function MethodologyPage() {
  const { methodologyId } = useParams<{ methodologyId: string }>();
  const { data: m, error, loading, reload } = useApiResource<Methodology & { items: MethodologyItem[] }>(`/methodologies/${methodologyId}`);
  const fileRef = useRef<HTMLInputElement>(null);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [msg, setMsg] = useState<{ kind: "error" | "success"; text: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  if (loading && !m) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  if (!m) return null;
  const items = Array.isArray(m.items) ? m.items : [];
  const groups = Object.keys(TYPE_LABELS).map((t) => [t, items.filter((i) => i.item_type === t)] as const).filter(([, l]) => l.length);

  async function upload(ev: React.FormEvent) {
    ev.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    setBusy("upload");
    setMsg(null);
    try {
      const r = await api.upload<{ loaded: number; issues: Issue[] }>(`/methodologies/${methodologyId}/items`, fd);
      setIssues(r.issues);
      setMsg(r.loaded ? { kind: "success", text: `${r.loaded} éléments chargés (les éléments précédents ont été remplacés).` }
        : { kind: "error", text: "Fichier rejeté : aucun élément chargé. Corrigez les anomalies ci-dessous." });
      await reload();
    } catch (x) { setMsg({ kind: "error", text: errorMessage(x) }); } finally { setBusy(null); }
  }

  async function act(action: "publish" | "archive") {
    setBusy(action);
    setMsg(null);
    try { await api.post(`/methodologies/${methodologyId}/${action}`, {}); await reload(); }
    catch (x) { setMsg({ kind: "error", text: errorMessage(x) }); } finally { setBusy(null); }
  }

  return (
    <>
      <Link href="/methodologies" className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ChevronLeft className="h-4 w-4" /> Méthodologies</Link>
      <PageHeader title={`${m.name} — ${m.version_label}`}
                  description={<span className="flex flex-wrap items-center gap-2"><Badge tone={STATUS[m.status][1]}>{STATUS[m.status][0]}</Badge>
                    <span>Source : {m.source_reference}</span>{m.published_at && <span>· publiée le {formatDate(m.published_at)}</span>}</span>}
                  actions={m.can_manage && <>
                    {m.status === "draft" && <Button size="sm" onClick={() => act("publish")} loading={busy === "publish"} disabled={!items.length}><Send className="h-4 w-4" /> Publier</Button>}
                    {m.status === "published" && <Button size="sm" variant="outline" onClick={() => act("archive")} loading={busy === "archive"}><Archive className="h-4 w-4" /> Archiver</Button>}
                  </>} />
      {m.description && <p className="mb-4 text-sm text-muted-foreground">{m.description}</p>}
      {msg && <Alert kind={msg.kind} className="mb-4">{msg.text}</Alert>}

      {m.can_manage && m.status === "draft" && (
        <Card className="mb-5">
          <CardHeader>
            <CardTitle>Charger les éléments</CardTitle>
            <CardDescription>CSV séparé par « ; » : type;code;libelle;parent;contenu;ordre. Le chargement remplace les éléments existants. Une version publiée est figée : créez une nouvelle version pour la modifier.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={upload} className="flex flex-col gap-2 sm:flex-row">
              <Input ref={fileRef} type="file" accept=".csv,.txt" aria-label="Fichier CSV" />
              <Button type="submit" loading={busy === "upload"}><FileUp className="h-4 w-4" /> Charger</Button>
            </form>
            {issues.length > 0 && (
              <ul className="mt-3 space-y-1 text-sm">
                {issues.map((i, k) => <li key={k}><Badge tone={i.severity === "error" ? "red" : "amber"}>{i.severity === "error" ? "Erreur" : "Avertissement"}</Badge> Ligne {i.row} : {i.message}</li>)}
              </ul>
            )}
          </CardContent>
        </Card>
      )}

      {groups.length === 0 ? <EmptyState title="Aucun élément" description="Chargez le fichier de la méthodologie pour la rendre utilisable." /> : groups.map(([t, list]) => (
        <Card key={t} className="mb-4">
          <CardHeader><CardTitle>{TYPE_LABELS[t]} ({list.length})</CardTitle></CardHeader>
          <CardContent>
            <Table>
              <THead><tr><TH>Code</TH><TH>Libellé</TH><TH>Parent</TH><TH>Contenu</TH></tr></THead>
              <TBody>
                {list.map((i) => (
                  <TR key={i.id}>
                    <TD className="font-medium">{i.code}</TD>
                    <TD>{i.label}</TD>
                    <TD>{i.parent_code ?? "—"}</TD>
                    <TD>{Object.keys(i.content ?? {}).length ? <code className="whitespace-pre-wrap text-xs">{JSON.stringify(i.content)}</code> : "—"}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </CardContent>
        </Card>
      ))}
    </>
  );
}
