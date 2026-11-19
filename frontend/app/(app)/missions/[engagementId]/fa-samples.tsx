"use client";

import { useState } from "react";
import { BookOpen, ChevronLeft, Database, FileSpreadsheet, Plus, RotateCcw, Shuffle, Trash2 } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import type { Engagement, EvidenceItem } from "@/lib/types";
import {
  METHOD_LABELS, REASON_LABELS, toDecimal, type FaPopItem, type FaPopulation, type FaSample, type FaSampleItem, type SampleMethod,
} from "@/lib/fa-types";
import { formatAmount, formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const AREA = "w-full rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30";
const COLS = [["reference", "Référence", true], ["date", "Date", false], ["label", "Libellé / tiers", false], ["account", "Compte", false],
  ["amount", "Montant", true]] as const;

type Issue = { severity: string; row: number; message: string };

function PopulationDialog({ e, open, onClose, onCreated }: { e: Engagement; open: boolean; onClose: () => void; onCreated: () => void }) {
  const base = `/engagements/${e.id}/fa`;
  const { data: evidence } = useApiResource<EvidenceItem[]>(open ? `/engagements/${e.id}/evidence` : null);
  const [src, setSrc] = useState<"balance" | "ledger" | "file">("ledger");
  const [f, setF] = useState({ name: "", description: "", prefixes: "", evidence_id: "", header_row: "0", decimal_separator: "" });
  const [lg, setLg] = useState({ journals: "", date_from: "", date_to: "", min_abs_amount: "", side: "all" });
  const [cols, setCols] = useState<Record<string, string>>({ reference: "", date: "", label: "", account: "", amount: "" });
  const [preview, setPreview] = useState<{ rows: (string | number | null)[][]; total_rows: number } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const files = (evidence ?? []).filter((x) => x.kind === "file" && /\.(csv|txt|xlsx)$/i.test(x.original_filename ?? ""));
  const fileBody = () => ({
    name: f.name || "Population", description: f.description || null, evidence_id: f.evidence_id, header_row: Number(f.header_row) || 0,
    decimal_separator: f.decimal_separator || null,
    columns: Object.fromEntries(Object.entries(cols).map(([k, v]) => [k, v === "" ? null : Number(v)])),
  });

  async function run(key: string, fn: () => Promise<void>) {
    setBusy(key); setErr(null);
    try { await fn(); } catch (x) {
      setErr(errorMessage(x));
      const d = (x as { details?: { issues?: Issue[] } }).details;
      if (d?.issues) setIssues(d.issues);
    } finally { setBusy(null); }
  }

  const headers = preview?.rows[Number(f.header_row) || 0] ?? [];
  return (
    <Dialog open={open} onClose={onClose} title="Nouvelle population" description="Ensemble d'éléments dans lequel l'échantillon est tiré. Elle est figée (empreinte SHA-256) dès le premier tirage.">
      <div className="space-y-3">
        {err && <Alert>{err}</Alert>}
        {issues.length > 0 && <ul className="max-h-32 overflow-y-auto text-xs">{issues.map((i, k) => <li key={k}>Ligne {i.row} : {i.message}</li>)}</ul>}
        <div className="flex gap-2">
          <Button size="sm" variant={src === "ledger" ? "default" : "outline"} onClick={() => setSrc("ledger")}><BookOpen className="h-4 w-4" /> Écritures du grand livre</Button>
          <Button size="sm" variant={src === "balance" ? "default" : "outline"} onClick={() => setSrc("balance")}><Database className="h-4 w-4" /> Comptes de la balance</Button>
          <Button size="sm" variant={src === "file" ? "default" : "outline"} onClick={() => setSrc("file")}><FileSpreadsheet className="h-4 w-4" /> Fichier probant</Button>
        </div>
        <Field label="Nom" htmlFor="po-name" required><Input id="po-name" value={f.name} onChange={(x) => setF({ ...f, name: x.target.value })} /></Field>
        {src === "ledger" ? (
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">Une ligne d&apos;écriture du grand livre validé de l&apos;exercice audité par élément (montant = débit − crédit). La base vérifie chaque montant.</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Racines de comptes (facultatif)" htmlFor="po-lp"><Input id="po-lp" placeholder="ex. 60, 61" value={f.prefixes} onChange={(x) => setF({ ...f, prefixes: x.target.value })} /></Field>
              <Field label="Journaux (facultatif)" htmlFor="po-lj"><Input id="po-lj" placeholder="ex. AC, OD" value={lg.journals} onChange={(x) => setLg({ ...lg, journals: x.target.value })} /></Field>
              <Field label="Du" htmlFor="po-ld"><Input id="po-ld" type="date" value={lg.date_from} onChange={(x) => setLg({ ...lg, date_from: x.target.value })} /></Field>
              <Field label="Au" htmlFor="po-la"><Input id="po-la" type="date" value={lg.date_to} onChange={(x) => setLg({ ...lg, date_to: x.target.value })} /></Field>
              <Field label="Montant minimal (valeur absolue)" htmlFor="po-lm"><Input id="po-lm" inputMode="decimal" value={lg.min_abs_amount} onChange={(x) => setLg({ ...lg, min_abs_amount: x.target.value })} /></Field>
              <Field label="Sens" htmlFor="po-ls">
                <Select id="po-ls" value={lg.side} onChange={(x) => setLg({ ...lg, side: x.target.value })}><option value="all">Débits et crédits</option><option value="debit">Débits</option><option value="credit">Crédits</option></Select>
              </Field>
            </div>
          </div>
        ) : src === "balance" ? (
          <Field label="Préfixes de comptes (séparés par des virgules)" htmlFor="po-pre" required>
            <Input id="po-pre" placeholder="ex. 411, 416" value={f.prefixes} onChange={(x) => setF({ ...f, prefixes: x.target.value })} />
          </Field>
        ) : (
          <>
            <p className="text-xs text-muted-foreground">Déposez d&apos;abord le fichier (grand livre, liste de factures, relevé…) dans l&apos;onglet « Éléments probants » : la population garde le lien vers ce fichier et son empreinte.</p>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="sm:col-span-2">
                <Field label="Fichier (CSV ou XLSX)" htmlFor="po-ev">
                  <Select id="po-ev" value={f.evidence_id} onChange={(x) => { setF({ ...f, evidence_id: x.target.value }); setPreview(null); }}>
                    <option value="">Choisir…</option>{files.map((x) => <option key={x.id} value={x.id}>{x.title} ({x.original_filename})</option>)}
                  </Select>
                </Field>
              </div>
              <Field label="Ligne d'en-tête (0 = 1re)" htmlFor="po-h"><Input id="po-h" inputMode="numeric" value={f.header_row} onChange={(x) => setF({ ...f, header_row: x.target.value })} /></Field>
            </div>
            <Button size="sm" variant="outline" disabled={!f.evidence_id} loading={busy === "preview"}
                    onClick={() => run("preview", async () => setPreview(await api.post(`${base}/populations/preview`, fileBody())))}>Lire le fichier</Button>
            {preview && (
              <>
                <div className="max-h-48 overflow-auto rounded border text-xs">
                  <table className="w-full"><tbody>{preview.rows.map((r, i) => (
                    <tr key={i} className={i === (Number(f.header_row) || 0) ? "bg-muted font-medium" : undefined}>
                      <td className="px-1 text-muted-foreground">{i}</td>{r.map((c, j) => <td key={j} className="whitespace-nowrap px-1">{c === null ? "" : String(c)}</td>)}
                    </tr>))}</tbody></table>
                </div>
                <p className="text-xs text-muted-foreground">{preview.total_rows} ligne(s) dans la feuille.</p>
                <div className="grid gap-2 sm:grid-cols-3">
                  {COLS.map(([k, label, req]) => (
                    <Field key={k} label={label} htmlFor={`po-c-${k}`} required={req}>
                      <Select id={`po-c-${k}`} value={cols[k]} onChange={(x) => setCols({ ...cols, [k]: x.target.value })}>
                        <option value="">—</option>{headers.map((h, j) => <option key={j} value={j}>{j} · {h === null ? "" : String(h)}</option>)}
                      </Select>
                    </Field>
                  ))}
                  <Field label="Séparateur décimal" htmlFor="po-sep">
                    <Select id="po-sep" value={f.decimal_separator} onChange={(x) => setF({ ...f, decimal_separator: x.target.value })}>
                      <option value="">Détection</option><option value=",">Virgule</option><option value=".">Point</option>
                    </Select>
                  </Field>
                </div>
              </>
            )}
          </>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>Annuler</Button>
          <Button loading={busy === "create"} disabled={src === "file" ? !preview || !cols.reference || !cols.amount : src === "balance" && !f.prefixes.trim()}
                  onClick={() => run("create", async () => {
                    setIssues([]);
                    const split = (v: string) => v.split(/[,;\s]+/).filter(Boolean);
                    if (src === "ledger") {
                      await api.post(`${base}/populations/from-ledger`, { name: f.name || "Écritures", description: f.description || null,
                        account_prefixes: split(f.prefixes), journals: split(lg.journals), date_from: lg.date_from || null, date_to: lg.date_to || null,
                        min_abs_amount: toDecimal(lg.min_abs_amount), side: lg.side });
                    } else if (src === "balance") {
                      await api.post(`${base}/populations/from-balance`, { name: f.name || "Population", description: f.description || null,
                        account_prefixes: f.prefixes.split(/[,;\s]+/).filter(Boolean) });
                    } else {
                      await api.post(`${base}/populations/from-file`, fileBody());
                    }
                    onCreated();
                  })}>Créer la population</Button>
        </div>
      </div>
    </Dialog>
  );
}

function SampleDialog({ e, pop, onClose, onCreated }: { e: Engagement; pop: FaPopulation | null; onClose: () => void; onCreated: (s: FaSample) => void }) {
  const base = `/engagements/${e.id}/fa`;
  const { data: items } = useApiResource<FaPopItem[]>(pop ? `${base}/populations/${pop.id}/items?limit=1000` : null);
  const [f, setF] = useState({ reference: "", objective: "", method: "random" as SampleMethod, size: "", size_basis: "", threshold: "" });
  const [picked, setPicked] = useState<string[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const statistical = ["random", "systematic", "mus"].includes(f.method);

  async function create(ev: React.FormEvent) {
    ev.preventDefault();
    if (!pop) return;
    setBusy(true); setErr(null);
    try {
      const s = await api.post<FaSample>(`${base}/samples`, {
        population_id: pop.id, reference: f.reference, objective: f.objective, method: f.method, size_basis: f.size_basis,
        size: statistical ? Number(f.size) : null, threshold: f.method === "key_items" ? toDecimal(f.threshold) : null,
        item_ids: f.method === "judgmental" ? picked : null });
      onCreated(s);
    } catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }

  return (
    <Dialog open={pop !== null} onClose={onClose} title="Tirer un échantillon" description={pop ? `${pop.name} : ${pop.item_count} éléments, ${formatAmount(pop.absolute_total)} en valeur absolue` : undefined}>
      <form onSubmit={create} className="space-y-3">
        {err && <Alert>{err}</Alert>}
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Référence" htmlFor="sa-ref" required><Input id="sa-ref" required value={f.reference} onChange={(x) => setF({ ...f, reference: x.target.value })} /></Field>
          <div className="sm:col-span-2"><Field label="Objectif du test (assertion visée)" htmlFor="sa-obj" required><Input id="sa-obj" required value={f.objective} onChange={(x) => setF({ ...f, objective: x.target.value })} /></Field></div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Méthode de sélection" htmlFor="sa-m">
            <Select id="sa-m" value={f.method} onChange={(x) => setF({ ...f, method: x.target.value as SampleMethod })}>
              {Object.entries(METHOD_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </Select>
          </Field>
          {statistical && <Field label="Taille de l'échantillon" htmlFor="sa-n" required><Input id="sa-n" inputMode="numeric" required value={f.size} onChange={(x) => setF({ ...f, size: x.target.value.replace(/\D/g, "") })} /></Field>}
          {f.method === "key_items" && <Field label="Seuil (|montant| ≥)" htmlFor="sa-t" required><Input id="sa-t" inputMode="decimal" required value={f.threshold} onChange={(x) => setF({ ...f, threshold: x.target.value })} /></Field>}
        </div>
        {f.method === "mus" && <p className="text-xs text-muted-foreground">Intervalle = valeur absolue de la population / taille ; départ aléatoire. Tout élément d&apos;un montant supérieur ou égal à l&apos;intervalle est sélectionné.</p>}
        {f.method === "judgmental" && (
          <div className="max-h-48 overflow-y-auto rounded border p-2 text-sm">
            {items?.map((i) => (
              <label key={i.id} className="flex items-center gap-2">
                <input type="checkbox" className="h-4 w-4" checked={picked.includes(i.id)} onChange={(x) => setPicked(x.target.checked ? [...picked, i.id] : picked.filter((p) => p !== i.id))} />
                <span>{i.reference} {i.label && <span className="text-muted-foreground">{i.label}</span>}</span><span className="ml-auto tabular-nums">{formatAmount(i.amount)}</span>
              </label>
            ))}
          </div>
        )}
        <Field label="Fondement de la taille ou de la sélection (paramètre de la méthodologie, jugement)" htmlFor="sa-b" required>
          <textarea id="sa-b" rows={2} className={AREA} required minLength={10} value={f.size_basis} onChange={(x) => setF({ ...f, size_basis: x.target.value })} />
        </Field>
        <p className="text-xs text-muted-foreground">Le tirage est fait par KOFINEX avec une graine aléatoire conservée : il est reproductible et ne peut pas être modifié ensuite.</p>
        <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={onClose}>Annuler</Button><Button type="submit" loading={busy}><Shuffle className="h-4 w-4" /> Tirer</Button></div>
      </form>
    </Dialog>
  );
}

function TestRow({ e, s, it, onSaved, editable }: { e: Engagement; s: FaSample; it: FaSampleItem; onSaved: () => void; editable: boolean }) {
  const [f, setF] = useState({ result: it.result, audited: it.audited_amount ?? "", comment: it.comment ?? "" });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const dirty = f.result !== it.result || f.audited !== (it.audited_amount ?? "") || f.comment !== (it.comment ?? "");
  async function save() {
    setBusy(true); setErr(null);
    try {
      await api.patch(`/engagements/${e.id}/fa/samples/${s.id}/items/${it.id}`, {
        result: f.result, audited_amount: f.result === "exception" ? toDecimal(f.audited) : null, comment: f.comment || null });
      onSaved();
    } catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }
  return (
    <TR>
      <TD><span className="font-medium">{it.item.reference}</span> <span className="text-xs text-muted-foreground">{it.item.label}</span>
        <p className="text-xs text-muted-foreground">{REASON_LABELS[it.selection_reason]}{it.item.item_date && ` · ${formatDate(it.item.item_date)}`}{it.item.account_number && ` · ${it.item.account_number}`}</p></TD>
      <TD className="text-right tabular-nums">{formatAmount(it.book_amount)}</TD>
      <TD>
        <Select aria-label="Résultat" value={f.result} disabled={!editable} className="w-40" onChange={(x) => setF({ ...f, result: x.target.value as FaSampleItem["result"] })}>
          <option value="pending">À tester</option><option value="no_exception">Sans anomalie</option><option value="exception">Anomalie</option>
        </Select>
      </TD>
      <TD>{f.result === "exception" ? <Input aria-label="Montant audité" inputMode="decimal" className="w-32" disabled={!editable} value={f.audited} onChange={(x) => setF({ ...f, audited: x.target.value })} />
        : <span className="text-xs text-muted-foreground">{f.result === "no_exception" ? formatAmount(it.book_amount) : "—"}</span>}</TD>
      <TD className="text-right tabular-nums">{it.misstatement && it.misstatement !== "0" ? formatAmount(it.misstatement) : "—"}</TD>
      <TD>
        <Input aria-label="Commentaire" disabled={!editable} value={f.comment} placeholder={f.result === "exception" ? "Description requise" : ""} onChange={(x) => setF({ ...f, comment: x.target.value })} />
        {err && <p className="mt-1 text-xs text-destructive">{err}</p>}
      </TD>
      <TD>{editable && dirty && <Button size="sm" variant="outline" loading={busy} onClick={save}>Enregistrer</Button>}</TD>
    </TR>
  );
}

function SampleDetail({ e, id, onBack, onChanged }: { e: Engagement; id: string; onBack: () => void; onChanged: () => void }) {
  const base = `/engagements/${e.id}/fa/samples/${id}`;
  const { data: s, error, reload } = useApiResource<FaSample>(base);
  const [conclusion, setConclusion] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const caps = e.capabilities ?? [];
  if (error) return <Alert>{error}</Alert>;
  if (!s) return <Loading />;
  const editable = caps.includes("edit_procedures") && s.status === "testing";
  const proj = s.status === "concluded" ? s.projection : s.preview;
  async function act(key: string, fn: () => Promise<unknown>) {
    setBusy(key); setErr(null);
    try { await fn(); await reload(); onChanged(); } catch (x) { setErr(errorMessage(x)); } finally { setBusy(null); }
  }
  return (
    <div className="space-y-4">
      <Button variant="ghost" size="sm" onClick={onBack}><ChevronLeft className="h-4 w-4" /> Échantillons</Button>
      {err && <Alert>{err}</Alert>}
      <Card>
        <CardHeader className="flex-row items-start justify-between gap-3">
          <div>
            <CardTitle>{s.reference} — {s.objective}</CardTitle>
            <CardDescription>
              {METHOD_LABELS[s.method]} dans « {s.population?.name} » · {s.selected_count} élément(s){s.requested_size && ` (taille demandée ${s.requested_size})`}
              {s.parameters.interval && ` · intervalle ${s.method === "mus" ? formatAmount(String(s.parameters.interval)) : String(s.parameters.interval).replace(".", ",")}`}
              {s.seed !== null && ` · graine ${s.seed}`}
            </CardDescription>
            <p className="mt-1 text-xs text-muted-foreground">Fondement : {s.size_basis}</p>
          </div>
          {s.status === "concluded" ? <Badge tone="green">Conclu</Badge> : <Badge tone="blue">{s.tested}/{s.selected_count} testé(s)</Badge>}
        </CardHeader>
      </Card>
      <Table>
        <THead><tr><TH>Élément</TH><TH className="text-right">Montant comptable</TH><TH>Résultat</TH><TH>Montant audité</TH><TH className="text-right">Anomalie</TH><TH>Commentaire</TH><TH /></tr></THead>
        <TBody>{s.items?.map((it) => <TestRow key={`${it.id}-${it.result}-${it.audited_amount}`} e={e} s={s} it={it} editable={editable} onSaved={() => void reload()} />)}</TBody>
      </Table>
      {proj && (
        <Card>
          <CardHeader><CardTitle>{s.status === "concluded" ? "Résultat" : "Résultat provisoire"}</CardTitle><CardDescription>{proj.explanation}</CardDescription></CardHeader>
          <CardContent>
            <dl className="grid gap-3 text-sm sm:grid-cols-3">
              <div><dt className="text-muted-foreground">Anomalie constatée</dt><dd className="text-lg font-semibold tabular-nums">{formatAmount(proj.actual)}</dd></div>
              <div><dt className="text-muted-foreground">Anomalie extrapolée</dt><dd className="text-lg font-semibold tabular-nums">{proj.projected !== null ? formatAmount(proj.projected) : "Sans objet"}</dd></div>
              <div><dt className="text-muted-foreground">Éléments à tester</dt><dd className="text-lg font-semibold">{proj.pending}</dd></div>
            </dl>
            <p className="mt-2 text-xs text-muted-foreground">Estimation ponctuelle : la limite supérieure d&apos;anomalie dépend des facteurs de confiance de votre méthodologie et n&apos;est pas calculée.</p>
            {s.conclusion && <p className="mt-3 whitespace-pre-wrap text-sm"><span className="text-muted-foreground">Conclusion : </span>{s.conclusion}</p>}
          </CardContent>
        </Card>
      )}
      {editable && (
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input aria-label="Conclusion" placeholder="Conclusion du test…" value={conclusion} onChange={(x) => setConclusion(x.target.value)} />
          <Button loading={busy === "conclude"} disabled={conclusion.trim().length < 3 || s.tested < s.selected_count}
                  onClick={() => act("conclude", () => api.post(`${base}/conclude`, { conclusion }))}>Conclure</Button>
        </div>
      )}
      {s.status === "concluded" && caps.includes("plan") && (
        <Button variant="outline" size="sm" loading={busy === "reopen"} onClick={() => act("reopen", () => api.post(`${base}/reopen`, {}))}><RotateCcw className="h-4 w-4" /> Rouvrir</Button>
      )}
    </div>
  );
}

export function FaSamplesPanel({ e, onChanged }: { e: Engagement; onChanged: () => void }) {
  const base = `/engagements/${e.id}/fa`;
  const { data: pops, reload: reloadPops } = useApiResource<FaPopulation[]>(`${base}/populations`);
  const { data, error, loading, reload } = useApiResource<FaSample[]>(`${base}/samples`);
  const [popOpen, setPopOpen] = useState(false);
  const [drawFrom, setDrawFrom] = useState<FaPopulation | null>(null);
  const [detail, setDetail] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const canEdit = (e.capabilities ?? []).includes("edit_procedures");

  if (detail) return <SampleDetail e={e} id={detail} onBack={() => { setDetail(null); void reload(); }} onChanged={onChanged} />;
  if (loading && !data) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  return (
    <div className="space-y-5">
      {err && <Alert>{err}</Alert>}
      <div>
        <div className="mb-2 flex items-center justify-between gap-3">
          <h3 className="font-semibold">Populations</h3>
          {canEdit && <Button size="sm" variant="outline" onClick={() => setPopOpen(true)}><Plus className="h-4 w-4" /> Population</Button>}
        </div>
        {pops && pops.length === 0 ? <EmptyState title="Aucune population" description="Créez-la depuis les comptes de la balance validée ou depuis un fichier déposé en élément probant." /> : (
          <Table>
            <THead><tr><TH>Population</TH><TH>Origine</TH><TH className="text-right">Éléments</TH><TH className="text-right">Total</TH><TH>Empreinte</TH><TH /></tr></THead>
            <TBody>{pops?.map((p) => (
              <TR key={p.id}>
                <TD className="font-medium">{p.name}</TD>
                <TD>{p.source === "balance" ? `Balance (${p.account_prefixes.join(", ")})` : p.source === "ledger" ? `Grand livre${p.account_prefixes.length ? ` (${p.account_prefixes.join(", ")})` : ""}` : "Fichier probant"}</TD>
                <TD className="text-right">{p.item_count}</TD><TD className="text-right tabular-nums">{formatAmount(p.total_amount)}</TD>
                <TD><code className="text-xs" title={p.sha256}>{p.sha256.slice(0, 10)}…</code>{p.frozen && <Badge className="ml-1">Figée</Badge>}</TD>
                <TD className="whitespace-nowrap text-right">
                  {canEdit && <Button size="sm" variant="outline" onClick={() => setDrawFrom(p)}><Shuffle className="h-4 w-4" /> Échantillon</Button>}
                  {canEdit && !p.frozen && <Button size="icon" variant="ghost" aria-label={`Supprimer ${p.name}`} onClick={async () => {
                    try { await api.del(`${base}/populations/${p.id}`); await reloadPops(); } catch (x) { setErr(errorMessage(x)); } }}><Trash2 className="h-4 w-4" /></Button>}
                </TD>
              </TR>))}
            </TBody>
          </Table>
        )}
      </div>
      <div>
        <h3 className="mb-2 font-semibold">Échantillons</h3>
        {data && data.length === 0 ? <EmptyState title="Aucun échantillon" /> : (
          <Table>
            <THead><tr><TH>Référence</TH><TH>Méthode</TH><TH>Population</TH><TH className="text-right">Testés</TH><TH className="text-right">Anomalies</TH><TH className="text-right">Constatée</TH><TH className="text-right">Extrapolée</TH><TH>Statut</TH></tr></THead>
            <TBody>{data?.map((s) => (
              <TR key={s.id} className="cursor-pointer" onClick={() => setDetail(s.id)}>
                <TD className="font-medium text-link">{s.reference}</TD><TD>{METHOD_LABELS[s.method]}</TD><TD>{s.population?.name}</TD>
                <TD className="text-right">{s.tested}/{s.selected_count}</TD><TD className="text-right">{s.exceptions || "—"}</TD>
                <TD className="text-right tabular-nums">{formatAmount(s.actual_misstatement)}</TD><TD className="text-right tabular-nums">{formatAmount(s.projected_misstatement)}</TD>
                <TD>{s.status === "concluded" ? <Badge tone="green">Conclu</Badge> : <Badge tone="blue">En test</Badge>}</TD>
              </TR>))}
            </TBody>
          </Table>
        )}
      </div>
      <PopulationDialog e={e} open={popOpen} onClose={() => setPopOpen(false)} onCreated={() => { setPopOpen(false); void reloadPops(); }} />
      <SampleDialog e={e} pop={drawFrom} onClose={() => setDrawFrom(null)} onCreated={(s) => { setDrawFrom(null); void reloadPops(); void reload(); onChanged(); setDetail(s.id); }} />
    </div>
  );
}
