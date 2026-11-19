"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { FRAMEWORK_CATEGORY } from "@/lib/ic-types";
import { formatDate } from "@/lib/utils";
import { AREA, IcShell } from "@/components/ic-shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

type Item = { id: string; item_type: string; code: string; label: string; parent_code: string | null };
type Version = {
  id: string; organization_id: string | null; name: string; version_label: string; status: "draft" | "published" | "archived"; framework_category: string | null;
  issuing_body: string | null; published_on: string | null; effective_from: string | null; source_reference: string; source_document: string | null; items: Item[];
};
type Mapping = { id: string; organization_id: string | null; source_item_id: string; target_item_id: string; relation: string; rationale: string; source_reference: string | null; created_at: string };
const TYPES: Record<string, string> = {
  ic_component: "Composantes", ic_principle: "Principes", ic_requirement: "Exigences", ic_criterion: "Critères",
  control_level_scale: "Échelle de niveau de maîtrise", deficiency_scale: "Échelle des déficiences",
};
const RELATION: Record<string, string> = { equivalent: "Équivalent", partial: "Correspondance partielle", related: "En rapport" };
const STATUS: Record<string, [string, "neutral" | "green" | "amber"]> = { draft: ["Brouillon", "amber"], published: ["Publié", "green"], archived: ["Archivé", "neutral"] };

export default function IcFrameworksPage() {
  const { companyId: cid } = useParams<{ companyId: string }>();
  const { data, error, loading, reload } = useApiResource<{ versions: Version[]; mappings: Mapping[] }>(`/companies/${cid}/ic/frameworks`);
  const [open, setOpen] = useState<string | null>(null);
  const itemIndex = new Map<string, { item: Item; v: Version }>();
  data?.versions.forEach((v) => v.items.forEach((i) => itemIndex.set(i.id, { item: i, v })));
  const label = (id: string) => { const x = itemIndex.get(id); return x ? `${x.v.name} ${x.v.version_label} · ${x.item.code} — ${x.item.label}` : "élément non visible"; };
  return (
    <IcShell cid={cid} title="Référentiels et méthodologies"
             description="COSO, IIA, IFACI, OHADA ou méthodologie interne : chaque référentiel est une méthodologie versionnée, importée avec sa source et figée à la publication. Aucun contenu normatif n'est fourni ni déduit par KOFINEX.">
      {(access) => (
        <div className="space-y-5">
          <Alert kind="info">
            Un cadre de contrôle interne, un référentiel professionnel d&apos;audit et une exigence juridique ou comptable n&apos;ont pas la même nature ; la catégorie est indiquée pour chacun.
            Les éléments détaillés (composantes, principes, exigences, critères, échelles) sont chargés par fichier depuis les{" "}
            <Link className="underline" href="/methodologies">méthodologies</Link>, à partir des documents dont votre organisation dispose. Aucune conformité n&apos;est calculée automatiquement.
          </Alert>
          {error && <Alert>{error}</Alert>}
          {loading && !data && <Loading />}
          {data && data.versions.length === 0 && (
            <EmptyState title="Aucun référentiel de contrôle interne" description="Créez une méthodologie de type « contrôle interne », renseignez sa nature et son document source, chargez ses éléments puis publiez-la."
                        action={<Link className="text-sm text-link underline" href="/methodologies">Ouvrir les méthodologies</Link>} />
          )}
          {data?.versions.map((v) => {
            const byType = Object.keys(TYPES).map((t) => [t, v.items.filter((i) => i.item_type === t)] as const).filter(([, l]) => l.length);
            return (
              <Card key={v.id}>
                <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-2">
                  <div>
                    <CardTitle>{v.name} — {v.version_label}</CardTitle>
                    <CardDescription>
                      {v.framework_category ? FRAMEWORK_CATEGORY[v.framework_category] : "Catégorie non renseignée"}
                      {v.issuing_body && ` · ${v.issuing_body}`}{v.published_on && ` · publié le ${formatDate(v.published_on)}`}
                      {v.effective_from && ` · applicable au ${formatDate(v.effective_from)}`} · {v.organization_id ? "propre à l'organisation" : "plateforme"}
                    </CardDescription>
                    <p className="mt-1 text-xs text-muted-foreground">Source : {v.source_reference}{v.source_document && ` · document : ${v.source_document}`}</p>
                  </div>
                  <span className="flex items-center gap-2">
                    <Badge tone={STATUS[v.status][1]}>{STATUS[v.status][0]}</Badge>
                    <Button size="sm" variant="ghost" onClick={() => setOpen(open === v.id ? null : v.id)}>{open === v.id ? "Masquer" : `Éléments (${v.items.length})`}</Button>
                  </span>
                </CardHeader>
                {open === v.id && (
                  <CardContent className="space-y-4">
                    {byType.length === 0 && <p className="text-sm text-muted-foreground">Aucun élément de contrôle interne chargé.</p>}
                    {byType.map(([t, list]) => (
                      <div key={t}>
                        <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{TYPES[t]}</p>
                        <ul className="space-y-0.5 text-sm">{list.map((i) => (
                          <li key={i.id} className={i.parent_code ? "pl-5" : ""}><span className="font-medium">{i.code}</span> {i.label}{i.parent_code && <span className="text-xs text-muted-foreground"> · rattaché à {i.parent_code}</span>}</li>
                        ))}</ul>
                      </div>
                    ))}
                  </CardContent>
                )}
              </Card>
            );
          })}
          {data && (
            <Card>
              <CardHeader><CardTitle>Correspondances entre référentiels</CardTitle>
                <CardDescription>Déclarées et motivées par un utilisateur, jamais déduites. Elles permettent de combiner plusieurs référentiels sans les confondre.</CardDescription></CardHeader>
              <CardContent className="space-y-3">
                {data.mappings.length === 0 ? <p className="text-sm text-muted-foreground">Aucune correspondance.</p> : (
                  <Table>
                    <THead><tr><TH>Élément</TH><TH>Relation</TH><TH>Élément correspondant</TH><TH>Motivation</TH><TH /></tr></THead>
                    <TBody>{data.mappings.map((m) => (
                      <TR key={m.id}>
                        <TD className="text-xs">{label(m.source_item_id)}</TD><TD><Badge>{RELATION[m.relation]}</Badge></TD><TD className="text-xs">{label(m.target_item_id)}</TD>
                        <TD className="text-xs">{m.rationale}{m.source_reference && <span className="block text-muted-foreground">{m.source_reference}</span>}</TD>
                        <TD className="text-right">{access.is_admin && m.organization_id && <DeleteMapping cid={cid} id={m.id} onDone={reload} />}</TD>
                      </TR>
                    ))}</TBody>
                  </Table>
                )}
                {access.is_admin && <NewMapping cid={cid} versions={data.versions.filter((v) => v.status === "published")} onDone={reload} />}
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </IcShell>
  );
}

function DeleteMapping({ cid, id, onDone }: { cid: string; id: string; onDone: () => void }) {
  const [err, setErr] = useState<string | null>(null);
  return (
    <>
      {err && <span className="block text-xs text-destructive">{err}</span>}
      <Button size="sm" variant="ghost" onClick={async () => { setErr(null); try { await api.del(`/companies/${cid}/ic/framework-mappings/${id}`); onDone(); } catch (x) { setErr(errorMessage(x)); } }}>Supprimer</Button>
    </>
  );
}

function NewMapping({ cid, versions, onDone }: { cid: string; versions: Version[]; onDone: () => void }) {
  const [f, setF] = useState({ sv: "", source_item_id: "", tv: "", target_item_id: "", relation: "related", rationale: "", source_reference: "" });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const items = (vid: string) => versions.find((v) => v.id === vid)?.items.filter((i) => i.item_type.startsWith("ic_")) ?? [];
  if (versions.length < 2) return <p className="text-xs text-muted-foreground">Deux référentiels publiés au moins sont nécessaires pour déclarer une correspondance.</p>;
  async function save(ev: React.FormEvent) {
    ev.preventDefault(); setBusy(true); setErr(null);
    try {
      await api.post(`/companies/${cid}/ic/framework-mappings`, { source_item_id: f.source_item_id, target_item_id: f.target_item_id, relation: f.relation,
        rationale: f.rationale, source_reference: f.source_reference.trim() || null });
      setF({ sv: "", source_item_id: "", tv: "", target_item_id: "", relation: "related", rationale: "", source_reference: "" }); onDone();
    } catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }
  const pick = (vk: "sv" | "tv", ik: "source_item_id" | "target_item_id", label: string) => (
    <div className="grid gap-2 sm:grid-cols-2">
      <Field label={`${label} — référentiel`} htmlFor={`mp-${vk}`}><Select id={`mp-${vk}`} value={f[vk]} onChange={(x) => setF({ ...f, [vk]: x.target.value, [ik]: "" })}>
        <option value="">—</option>{versions.map((v) => <option key={v.id} value={v.id}>{v.name} {v.version_label}</option>)}</Select></Field>
      <Field label={`${label} — élément`} htmlFor={`mp-${ik}`}><Select id={`mp-${ik}`} required value={f[ik]} disabled={!f[vk]} onChange={(x) => setF({ ...f, [ik]: x.target.value })}>
        <option value="">—</option>{items(f[vk]).map((i) => <option key={i.id} value={i.id}>{i.code} — {i.label}</option>)}</Select></Field>
    </div>
  );
  return (
    <form onSubmit={save} className="space-y-3 rounded-md border p-3">
      <p className="text-sm font-medium">Déclarer une correspondance</p>
      {err && <Alert>{err}</Alert>}
      {pick("sv", "source_item_id", "Élément")}
      {pick("tv", "target_item_id", "Correspondant")}
      <div className="grid gap-2 sm:grid-cols-2">
        <Field label="Relation" htmlFor="mp-r"><Select id="mp-r" value={f.relation} onChange={(x) => setF({ ...f, relation: x.target.value })}>
          {Object.entries(RELATION).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select></Field>
        <Field label="Référence de la source" htmlFor="mp-s"><Input id="mp-s" value={f.source_reference} onChange={(x) => setF({ ...f, source_reference: x.target.value })} /></Field>
      </div>
      <Field label="Motivation" htmlFor="mp-m" required><textarea id="mp-m" required rows={2} className={AREA} value={f.rationale} onChange={(x) => setF({ ...f, rationale: x.target.value })} /></Field>
      <div className="flex justify-end"><Button type="submit" size="sm" loading={busy}>Déclarer</Button></div>
    </form>
  );
}
