"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ChevronLeft, Upload } from "lucide-react";
import { ApiError, api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { VERSION_STATUS, type FrameworkVersion, type LoadReport, type Profile } from "@/lib/types";
import { cn, formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, Badge, EmptyState, Loading, PageHeader } from "@/components/ui/feedback";
import { Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const NATURES: Record<string, string> = {
  asset: "Actif", liability: "Passif", equity: "Capitaux propres", income: "Produit", expense: "Charge",
  off_balance: "Hors bilan", mixed: "Mixte",
};
const RULES: Record<string, string> = {
  debit_balance: "Solde débiteur", credit_balance: "Solde créditeur", net_debit: "Solde net débiteur",
  net_credit: "Solde net créditeur", debit_movements: "Mouvements débit", credit_movements: "Mouvements crédit",
};
const COLUMNS: Record<string, string> = { gross: "Brut", depreciation: "Amort./dépréc.", net: "Net" };

function ReportView({ report }: { report: LoadReport }) {
  if (!report.issues.length) return <Alert kind="success">Aucune anomalie.</Alert>;
  return (
    <div className="space-y-2">
      <p className="text-sm">{report.errors} erreur(s) bloquante(s), {report.warnings} avertissement(s).</p>
      <ul className="max-h-72 divide-y overflow-auto rounded-md border text-sm">
        {report.issues.map((i, k) => (
          <li key={k} className={cn("px-3 py-1.5", i.severity === "error" ? "text-destructive-strong" : "text-warning-strong")}>
            {i.row ? <span className="font-mono">ligne {i.row} · </span> : null}{i.message}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Accounts({ versionId }: { versionId: string }) {
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [cls, setCls] = useState("");
  useEffect(() => { const t = setTimeout(() => setDebounced(q), 300); return () => clearTimeout(t); }, [q]);
  const params = new URLSearchParams({ limit: "300" });
  if (debounced.trim()) params.set("q", debounced.trim());
  if (cls) params.set("account_class", cls);
  const { data, error, loading } = useApiResource<{ total: number; items: {
    account_number: string; label: string; nature: string | null; normal_balance: string | null; is_postable: boolean;
    parent_number: string | null; }[] }>(`/framework-versions/${versionId}/accounts?${params.toString()}`);

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <Input className="w-72" placeholder="Numéro ou intitulé…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Rechercher" />
        <Select className="w-40" value={cls} onChange={(e) => setCls(e.target.value)} aria-label="Classe">
          <option value="">Toutes classes</option>
          {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((c) => <option key={c} value={c}>Classe {c}</option>)}
        </Select>
      </div>
      {loading && !data && <Loading />}
      {error && <Alert>{error}</Alert>}
      {data && data.total === 0 && <EmptyState title="Aucun compte" />}
      {data && data.total > 0 && (
        <>
          <Table>
            <THead><tr><TH>N°</TH><TH>Intitulé</TH><TH>Nature</TH><TH>Sens</TH><TH>Imputable</TH></tr></THead>
            <TBody>
              {data.items.map((a) => (
                <TR key={a.account_number}>
                  <TD className="font-mono" style={{ paddingLeft: `${0.5 + Math.min(a.account_number.length - 1, 6) * 0.6}rem` }}>{a.account_number}</TD>
                  <TD className={cn(!a.is_postable && "font-medium")}>{a.label}</TD>
                  <TD>{a.nature ? NATURES[a.nature] ?? a.nature : "—"}</TD>
                  <TD>{a.normal_balance === "debit" ? "Débit" : a.normal_balance === "credit" ? "Crédit" : a.normal_balance ? "Indifférent" : "—"}</TD>
                  <TD>{a.is_postable ? "Oui" : "Non"}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
          {data.total > data.items.length && <p className="text-xs text-muted-foreground">{data.items.length} comptes affichés sur {data.total} : affinez la recherche.</p>}
        </>
      )}
    </div>
  );
}

function Mappings({ versionId }: { versionId: string }) {
  const { data, error, loading } = useApiResource<{
    statement_label: string; line_code: string; line_label: string; account_prefix: string; excluded_prefixes: string[];
    balance_rule: string; amount_column: string; sign: number; priority: number; source_reference: string | null }[]>(
    `/framework-versions/${versionId}/mappings`);
  if (loading && !data) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  if (!data || data.length === 0) return <EmptyState title="Aucune correspondance chargée" />;
  return (
    <Table>
      <THead><tr><TH>État</TH><TH>Rubrique</TH><TH>Racine</TH><TH>Exclusions</TH><TH>Règle</TH><TH>Colonne</TH><TH>Signe</TH><TH>Source</TH></tr></THead>
      <TBody>
        {data.map((m, k) => (
          <TR key={k}>
            <TD className="whitespace-nowrap">{m.statement_label}</TD>
            <TD><span className="font-mono">{m.line_code}</span> {m.line_label}</TD>
            <TD className="font-mono">{m.account_prefix}</TD>
            <TD className="font-mono text-xs">{m.excluded_prefixes.join(", ")}</TD>
            <TD>{RULES[m.balance_rule] ?? m.balance_rule}</TD>
            <TD>{COLUMNS[m.amount_column] ?? m.amount_column}</TD>
            <TD>{m.sign > 0 ? "+" : "−"}</TD>
            <TD className="text-xs text-muted-foreground">{m.source_reference}</TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}

function Structure({ versionId }: { versionId: string }) {
  const { data, error, loading } = useApiResource<{ statement_label: string; code: string; label: string; kind: string;
    formula: string | null; role: string | null; level: number }[]>(`/framework-versions/${versionId}/structure`);
  if (loading && !data) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  if (!data || data.length === 0) return <EmptyState title="Structure des états non chargée" />;
  return (
    <Table>
      <THead><tr><TH>État</TH><TH>Réf.</TH><TH>Libellé</TH><TH>Type</TH><TH>Formule de total</TH><TH>Rôle</TH></tr></THead>
      <TBody>
        {data.map((l) => (
          <TR key={l.code} className={cn(l.kind === "total" && "font-semibold")}>
            <TD className="whitespace-nowrap text-xs">{l.statement_label}</TD>
            <TD className="font-mono">{l.code}</TD>
            <TD style={{ paddingLeft: `${1 + l.level * 0.75}rem` }}>{l.label}</TD>
            <TD>{l.kind === "detail" ? "Détail" : l.kind === "total" ? "Total" : "Titre"}</TD>
            <TD className="font-mono text-xs">{l.formula}</TD>
            <TD className="text-xs">{l.role}</TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}

function Concepts({ versionId }: { versionId: string }) {
  const { data, error, loading } = useApiResource<{ code: string; label: string; definition: string;
    expression: string | null; source_reference: string | null }[]>(`/framework-versions/${versionId}/concepts`);
  if (loading && !data) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  return (
    <Table>
      <THead><tr><TH>Concept d&apos;analyse</TH><TH>Définition</TH><TH>Lien dans ce référentiel</TH><TH>Source</TH></tr></THead>
      <TBody>
        {(data ?? []).map((c) => (
          <TR key={c.code}>
            <TD><p className="font-medium">{c.label}</p><p className="font-mono text-xs text-muted-foreground">{c.code}</p></TD>
            <TD className="max-w-sm text-xs text-muted-foreground">{c.definition}</TD>
            <TD className="font-mono text-xs">{c.expression ?? <span className="font-sans text-warning-strong">Non lié</span>}</TD>
            <TD className="text-xs text-muted-foreground">{c.source_reference}</TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}

export default function VersionPage() {
  const { versionId } = useParams<{ versionId: string }>();
  const router = useRouter();
  const { data: v, error, loading, setData, reload } = useApiResource<FrameworkVersion>(`/framework-versions/${versionId}`);
  const { data: me } = useApiResource<Profile>("/me");
  const [tab, setTab] = useState<"accounts" | "mappings" | "structure" | "concepts">("accounts");
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [report, setReport] = useState<LoadReport | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  if (loading && !v) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  if (!v) return null;
  const isAdmin = !!me?.is_platform_admin;
  const draft = v.status === "draft";

  async function run(key: string, fn: () => Promise<unknown>, success: string) {
    setBusy(key);
    setNotice(null);
    setReport(null);
    try {
      const res = await fn();
      if (res && typeof res === "object" && "issues" in (res as object)) setReport(res as LoadReport);
      setNotice({ kind: "success", text: success });
      await reload();
      setRefreshKey((k) => k + 1);
    } catch (err) {
      if (err instanceof ApiError && err.details && "issues" in err.details) setReport(err.details as unknown as LoadReport);
      setNotice({ kind: "error", text: errorMessage(err) });
    } finally {
      setBusy(null);
    }
  }

  const UPLOAD_LABELS = { chart: "Plan de comptes chargé.", mappings: "Correspondances chargées.",
    structure: "Structure des états chargée.", concepts: "Concepts d'analyse chargés." } as const;
  function upload(kind: keyof typeof UPLOAD_LABELS, file: File | undefined) {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    void run(kind, () => api.upload(`/framework-versions/${v!.id}/${kind}`, form), UPLOAD_LABELS[kind]);
  }

  return (
    <>
      <Link href="/referentiels" className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ChevronLeft className="h-4 w-4" /> Référentiels
      </Link>
      <PageHeader
        title={`${v.framework_name} — ${v.version_label}`}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <Badge tone={VERSION_STATUS[v.status].tone}>{VERSION_STATUS[v.status].label}</Badge>
            <span>Applicable du {formatDate(v.effective_from)}{v.effective_to ? ` au ${formatDate(v.effective_to)} (exclu)` : ""}</span>
            {v.published_at && <span>· publiée le {formatDate(v.published_at)}</span>}
          </span>
        }
      />
      <div className="space-y-4">
        <Card>
          <CardHeader><CardTitle>Source</CardTitle></CardHeader>
          <CardContent className="space-y-1 text-sm">
            <p>{v.source_reference}</p>
            {v.source_url && <a href={v.source_url} target="_blank" rel="noopener noreferrer" className="text-link underline">{v.source_url}</a>}
            <p className="text-muted-foreground">
              Plan de comptes : {v.account_count} compte(s){v.chart_sha256 ? ` · empreinte ${v.chart_sha256.slice(0, 12)}…` : ""} ·
              Correspondances : {v.mapping_count}{v.mappings_sha256 ? ` · empreinte ${v.mappings_sha256.slice(0, 12)}…` : ""} ·
              Structure : {v.structure_line_count} ligne(s) · Concepts liés : {v.concept_count}/{v.concept_total}
            </p>
          </CardContent>
        </Card>

        {isAdmin && (draft || v.status === "published") && (
          <Card>
            <CardHeader>
              <CardTitle>Administration</CardTitle>
              <CardDescription>
                {draft ? "Chargez les fichiers transcrits du texte officiel (CSV ou XLSX, modèles disponibles sur la page Référentiels). Recharger le plan de comptes efface les correspondances."
                       : "Une version publiée est figée. Elle peut seulement être retirée."}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {notice && <Alert kind={notice.kind}>{notice.text}</Alert>}
              {report && <ReportView report={report} />}
              {draft ? (
                <div className="flex flex-wrap gap-2">
                  <label className={cn("inline-flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm hover:bg-muted", busy && "pointer-events-none opacity-50")}>
                    <Upload className="h-4 w-4" /> Plan de comptes
                    <input type="file" accept=".csv,.xlsx" className="sr-only" onChange={(e) => { upload("chart", e.target.files?.[0]); e.target.value = ""; }} />
                  </label>
                  <label className={cn("inline-flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm hover:bg-muted", (busy || !v.account_count) && "pointer-events-none opacity-50")}>
                    <Upload className="h-4 w-4" /> Correspondances
                    <input type="file" accept=".csv,.xlsx" className="sr-only" disabled={!v.account_count}
                           onChange={(e) => { upload("mappings", e.target.files?.[0]); e.target.value = ""; }} />
                  </label>
                  <label className={cn("inline-flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm hover:bg-muted", busy && "pointer-events-none opacity-50")}>
                    <Upload className="h-4 w-4" /> Structure des états
                    <input type="file" accept=".csv,.xlsx" className="sr-only" onChange={(e) => { upload("structure", e.target.files?.[0]); e.target.value = ""; }} />
                  </label>
                  <label className={cn("inline-flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm hover:bg-muted", (busy || !v.structure_line_count) && "pointer-events-none opacity-50")}>
                    <Upload className="h-4 w-4" /> Concepts d&apos;analyse
                    <input type="file" accept=".csv,.xlsx" className="sr-only" disabled={!v.structure_line_count}
                           onChange={(e) => { upload("concepts", e.target.files?.[0]); e.target.value = ""; }} />
                  </label>
                  <Button variant="outline" loading={busy === "validate"}
                          onClick={() => run("validate", async () => { const r = await api.post<FrameworkVersion>(`/framework-versions/${v.id}/validate`); setData(r); return r.validation; }, "Vérification effectuée.")}>
                    Vérifier
                  </Button>
                  <Button loading={busy === "publish"} disabled={!v.account_count || !v.mapping_count || !v.structure_line_count}
                          onClick={() => {
                            if (!window.confirm("Publier cette version ? Elle deviendra applicable aux exercices de sa période et ne pourra plus jamais être modifiée.")) return;
                            void run("publish", () => api.post(`/framework-versions/${v.id}/publish`), "Version publiée.");
                          }}>
                    Publier
                  </Button>
                  <Button variant="ghost" className="text-destructive" loading={busy === "delete"}
                          onClick={async () => {
                            if (!window.confirm("Supprimer ce brouillon et son contenu ?")) return;
                            setBusy("delete");
                            try { await api.del(`/framework-versions/${v.id}`); router.replace("/referentiels"); }
                            catch (err) { setNotice({ kind: "error", text: errorMessage(err) }); setBusy(null); }
                          }}>
                    Supprimer le brouillon
                  </Button>
                </div>
              ) : (
                <Button variant="outline" loading={busy === "deprecate"}
                        onClick={() => {
                          if (!window.confirm("Retirer cette version ? Elle ne sera plus proposée pour les nouveaux imports.")) return;
                          void run("deprecate", () => api.post(`/framework-versions/${v.id}/deprecate`, {}), "Version retirée.");
                        }}>
                  Retirer la version
                </Button>
              )}
              {draft && v.validation && !report && <ReportView report={v.validation} />}
            </CardContent>
          </Card>
        )}

        <div role="tablist" className="flex gap-1 border-b">
          {(["accounts", "mappings", "structure", "concepts"] as const).map((t) => (
            <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
                    className={cn("-mb-px border-b-2 px-3 py-2 text-sm", tab === t ? "border-primary font-medium" : "border-transparent text-muted-foreground")}>
              {t === "accounts" ? `Plan de comptes (${v.account_count})` : t === "mappings" ? `Correspondances (${v.mapping_count})`
                : t === "structure" ? `Structure des états (${v.structure_line_count})` : `Concepts (${v.concept_count}/${v.concept_total})`}
            </button>
          ))}
        </div>
        <div key={refreshKey}>
          {tab === "accounts" && <Accounts versionId={v.id} />}
          {tab === "mappings" && <Mappings versionId={v.id} />}
          {tab === "structure" && <Structure versionId={v.id} />}
          {tab === "concepts" && <Concepts versionId={v.id} />}
        </div>
      </div>
    </>
  );
}
