"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Download, FileCheck2, FileText, ShieldCheck } from "lucide-react";
import { AccountingShell } from "@/components/accounting-shell";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import type { FecAnomaly, FecCheck, FecDashboard, FecExport, FecSpec } from "@/lib/fec-types";
import { COMPLIANCE } from "@/lib/fec-types";
import { formatAmount, formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, Badge, EmptyState, Loading } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { KpiCard, KpiGrid } from "@/components/ui/kpi-card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

/** Montant renvoyé au format du FEC (« 1180,00 ») → affichage groupé, sans nombre flottant. */
const fecAmount = (v: string) => formatAmount(v.replace(",", "."));

/** Rubrique « Fichier des Écritures Comptables (FEC) » — DGI Bénin, arrêté n° 1085 du 23 avril 2020. */
export default function FecPage() {
  const { companyId: cid } = useParams<{ companyId: string }>();
  return (
    <AccountingShell cid={cid} title="Fichier des Écritures Comptables (FEC)" needFy
      description="Contrôle, génération et archivage du FEC remis à l'administration fiscale (DGI Bénin).">
      {({ fy, settings }) => settings.permissions.fec
        ? <Fec cid={cid} fyId={fy!.id} fyStart={fy!.start_date} fyEnd={fy!.end_date} />
        : <Alert kind="info">Le FEC contient toutes les écritures de l&apos;entreprise : il est réservé aux comptables et aux administrateurs.</Alert>}
    </AccountingShell>
  );
}

interface Params {
  period_start: string; period_end: string; file_format: "" | "txt" | "csv"; encoding: "" | "ascii" | "iso-8859-15";
  record_separator: "" | "crlf" | "lf" | "cr"; accounting_type: "accrual" | "cash"; split: boolean; max_lines_per_file: string;
}

function Fec({ cid, fyId, fyStart, fyEnd }: { cid: string; fyId: string; fyStart: string; fyEnd: string }) {
  const F = `/companies/${cid}/accounting/fec`;
  const { data: dash, error: dashError, reload: reloadDash } = useApiResource<FecDashboard>(`${F}/dashboard?fiscal_year_id=${fyId}`);
  const { data: spec } = useApiResource<FecSpec>(`${F}/spec`);
  const { data: history, reload: reloadHistory } = useApiResource<FecExport[]>(`${F}/exports?fiscal_year_id=${fyId}`);
  // aucune valeur par défaut pour le format, l'encodage et la fin d'enregistrement : choix explicite de l'utilisateur
  const [p, setP] = useState<Params>({ period_start: fyStart, period_end: fyEnd, file_format: "", encoding: "", record_separator: "",
    accounting_type: "accrual", split: false, max_lines_per_file: "" });
  const [check, setCheck] = useState<FecCheck | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [onlyBlocking, setOnlyBlocking] = useState(false);

  const ready = p.file_format && p.encoding && p.record_separator && (!p.split || Number(p.max_lines_per_file) >= 1);
  const body = () => ({
    fiscal_year_id: fyId, period_start: p.period_start, period_end: p.period_end, file_format: p.file_format, encoding: p.encoding,
    record_separator: p.record_separator, field_separator: "tab", accounting_type: p.accounting_type,
    max_lines_per_file: p.split ? Number(p.max_lines_per_file) : null,
  });
  const set = (patch: Partial<Params>) => { setP({ ...p, ...patch }); setCheck(null); setNotice(null); };

  async function runCheck() {
    setBusy("check"); setErr(null); setNotice(null);
    try { setCheck(await api.post<FecCheck>(`${F}/check`, body())); } catch (e) { setErr(errorMessage(e)); } finally { setBusy(null); }
  }
  async function generate(kind: "final" | "working") {
    setBusy(kind); setErr(null);
    try {
      const ex = await api.post<FecExport>(`${F}/exports`, { ...body(), kind });
      setNotice(`Version ${ex.version_no} générée et archivée : ${ex.parts.map((x) => x.filename).join(", ")}.`);
      reloadHistory(); reloadDash();
    } catch (e) { setErr(errorMessage(e)); } finally { setBusy(null); }
  }
  const download = (path: string, name: string) => api.download(path, name).catch((e) => setErr(errorMessage(e)));

  if (dashError) return <Alert>{dashError}</Alert>;
  if (!dash || !spec) return <Loading />;
  const last = dash.last_export;
  const shown = (check?.anomalies ?? []).filter((a) => !onlyBlocking || a.severity === "blocking");

  return (
    <div className="space-y-5">
      {!spec.confirmed && (
        <Alert kind="warning">
          <p className="font-medium">Aucun fichier n&apos;est déclaré « conforme » tant que les points suivants ne sont pas confirmés.</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5">
            {spec.unconfirmed.map((u) => <li key={u.key}><span className="font-medium">{u.label}</span> : {u.detail}</li>)}
          </ul>
        </Alert>
      )}

      {/* A. Tableau de bord */}
      <KpiGrid className="xl:grid-cols-6">
        <KpiCard label="Écritures de l'exercice" value={dash.entries_total} />
        <KpiCard label="Écritures validées" value={dash.entries_validated} hint="Seules reprises dans le FEC" />
        <KpiCard label="Écritures éligibles" value={dash.entries_eligible} hint="Validées, sans anomalie bloquante propre" />
        <KpiCard label="Anomalies" value={`${dash.anomalies_blocking} · ${dash.anomalies_warning}`} hint="Bloquantes · avertissements (données)" />
        <KpiCard label="Dernière génération" value={last ? formatDate(last.generated_at) : "—"} hint={last ? `Version ${last.version_no}` : "Aucune"} />
        <KpiCard label="Statut du dernier fichier" value={last ? <Badge tone={COMPLIANCE[last.compliance].tone}>{COMPLIANCE[last.compliance].label}</Badge> : "—"} />
      </KpiGrid>

      {/* B. Paramètres de génération */}
      <Card>
        <CardHeader>
          <CardTitle>Paramètres de génération</CardTitle>
          <CardDescription>
            {dash.company.name} · IFU {dash.company.ifu || <span className="text-destructive">non renseigné</span>} · exercice {dash.fiscal_year.label}
            {" "}(clôture le {formatDate(dash.fiscal_year.end_date)}). L&apos;entreprise et l&apos;exercice se changent dans la barre supérieure.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" onSubmit={(e) => { e.preventDefault(); if (ready) runCheck(); }}>
            <Field label="Du" htmlFor="ps" required><Input id="ps" type="date" min={fyStart} max={fyEnd} value={p.period_start} onChange={(e) => set({ period_start: e.target.value })} /></Field>
            <Field label="Au" htmlFor="pe" required><Input id="pe" type="date" min={fyStart} max={fyEnd} value={p.period_end} onChange={(e) => set({ period_end: e.target.value })} /></Field>
            <Field label="Format" htmlFor="ff" required hint="Fichier plat (art. 4)">
              <Select id="ff" value={p.file_format} onChange={(e) => set({ file_format: e.target.value as Params["file_format"] })}>
                <option value="">Choisir…</option><option value="txt">TXT</option><option value="csv">CSV</option>
              </Select>
            </Field>
            <Field label="Jeu de caractères" htmlFor="enc" required hint="EBCDIC : page de code non précisée par l'arrêté">
              <Select id="enc" value={p.encoding} onChange={(e) => set({ encoding: e.target.value as Params["encoding"] })}>
                <option value="">Choisir…</option>
                {Object.entries(spec.encodings).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                <option value="ebcdic" disabled>EBCDIC (non proposé)</option>
              </Select>
            </Field>
            <Field label="Séparateur des zones" htmlFor="fs" hint="Seul séparateur lisible dans l'arrêté (art. 4)">
              <Select id="fs" value="tab" disabled>{Object.entries(spec.separators).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select>
            </Field>
            <Field label="Fin d'enregistrement" htmlFor="rs" required hint="Retour chariot et/ou fin de ligne (art. 4)">
              <Select id="rs" value={p.record_separator} onChange={(e) => set({ record_separator: e.target.value as Params["record_separator"] })}>
                <option value="">Choisir…</option>
                {Object.entries(spec.record_separators).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </Select>
            </Field>
            <Field label="Type de comptabilité" htmlFor="at" hint="Trésorerie : champs 19 à 21 (contribuables à l'impôt sur le revenu)">
              <Select id="at" value={p.accounting_type} onChange={(e) => set({ accounting_type: e.target.value as Params["accounting_type"] })}>
                <option value="accrual">Engagement (18 champs)</option><option value="cash">Trésorerie (21 champs)</option>
              </Select>
            </Field>
            <div className="space-y-1.5">
              <label className="flex items-center gap-2 text-sm font-medium">
                <input type="checkbox" checked={p.split} onChange={(e) => set({ split: e.target.checked })} /> Scinder le fichier (art. 6)
              </label>
              {p.split && <Input aria-label="Nombre maximal de lignes par fichier" inputMode="numeric" placeholder="Lignes par fichier"
                value={p.max_lines_per_file} onChange={(e) => set({ max_lines_per_file: e.target.value.replace(/[^0-9]/g, "") })} />}
              <p className="text-xs text-muted-foreground">Noms {p.split ? spec.split_pattern : spec.filename_pattern}</p>
            </div>
            <div className="flex flex-wrap items-end gap-2 sm:col-span-2 lg:col-span-4">
              <Button type="submit" disabled={!ready} loading={busy === "check"}><ShieldCheck className="h-4 w-4" aria-hidden /> Contrôler</Button>
              <Button type="button" disabled={!ready || !check?.can_generate_final} loading={busy === "final"} onClick={() => generate("final")}>
                <FileCheck2 className="h-4 w-4" aria-hidden /> Générer le fichier définitif
              </Button>
              {check && !check.can_generate_final && check.can_generate_working && (
                <Button type="button" variant="outline" loading={busy === "working"} onClick={() => generate("working")}>
                  Générer un fichier de travail (non conforme)
                </Button>
              )}
              {!ready && <span className="text-sm text-muted-foreground">Choisissez le format, le jeu de caractères et la fin d&apos;enregistrement.</span>}
            </div>
          </form>
        </CardContent>
      </Card>

      {err && <Alert>{err}</Alert>}
      {notice && <Alert kind="success">{notice}</Alert>}

      {/* C et D. Contrôle de conformité et rapport des anomalies */}
      {check && (
        <Card>
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center gap-2">
              Contrôle de conformité <Badge tone={COMPLIANCE[check.compliance].tone}>{COMPLIANCE[check.compliance].label}</Badge>
            </CardTitle>
            <CardDescription>
              Du {formatDate(check.period_start)} au {formatDate(check.period_end)} : {check.entries} écriture(s) validée(s), {check.lines} ligne(s),
              {" "}{check.eligible} écriture(s) éligible(s) · débit {fecAmount(check.total_debit)} · crédit {fecAmount(check.total_credit)}
              {check.filenames && <> · fichier(s) {check.filenames.join(", ")}</>}. Aucune écriture validée n&apos;est modifiée par le contrôle.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="mb-3 flex flex-wrap items-center gap-3 text-sm">
              <Badge tone={check.blocking ? "red" : "green"}>{check.blocking} bloquante(s)</Badge>
              <Badge tone={check.warnings ? "amber" : "neutral"}>{check.warnings} avertissement(s)</Badge>
              <label className="flex items-center gap-2"><input type="checkbox" checked={onlyBlocking} onChange={(e) => setOnlyBlocking(e.target.checked)} /> Bloquantes seulement</label>
            </div>
            {!shown.length ? <EmptyState title="Aucune anomalie" description="Aucune anomalie sur cette sélection." /> : <Anomalies cid={cid} rows={shown} />}
          </CardContent>
        </Card>
      )}

      {/* Historique et archivage */}
      <Card>
        <CardHeader>
          <CardTitle>Historique des générations</CardTitle>
          <CardDescription>Chaque génération est une nouvelle version, archivée et non modifiable, avec son empreinte SHA-256.</CardDescription>
        </CardHeader>
        <CardContent>
          {!history ? <Loading /> : !history.length ? <EmptyState title="Aucune génération" description="Contrôlez puis générez le FEC de l'exercice." /> : (
            <Table>
              <THead><tr><TH>Version</TH><TH>Générée le</TH><TH>Par</TH><TH>Période</TH><TH>Fichier(s)</TH><TH>Format</TH>
                <TH className="text-right">Lignes</TH><TH>Résultat du contrôle</TH><TH>Empreinte</TH><TH>Documents</TH></tr></THead>
              <TBody>
                {history.map((h) => (
                  <TR key={h.id}>
                    <TD className="font-medium">v{h.version_no}{h.kind === "working" && <span className="block text-xs text-muted-foreground">travail</span>}</TD>
                    <TD className="text-xs">{formatDate(h.generated_at)}</TD>
                    <TD className="text-xs">{h.generated_by_name ?? "—"}</TD>
                    <TD className="text-xs">{formatDate(h.period_start)} – {formatDate(h.period_end)}</TD>
                    <TD className="text-xs">
                      {h.parts.map((x) => (
                        <button key={x.filename} type="button" className="flex items-center gap-1 text-link underline-offset-2 hover:underline"
                          onClick={() => download(`${F}/exports/${h.id}/file${x.part ? `?part=${x.part}` : ""}`, x.filename)}>
                          <Download className="h-3.5 w-3.5" aria-hidden /> {x.filename}
                        </button>
                      ))}
                    </TD>
                    <TD className="text-xs">{h.file_format.toUpperCase()} · {spec.encodings[h.encoding] ?? h.encoding} · {spec.record_separators[h.record_separator]?.split(" (")[0]}</TD>
                    <TD className="text-right">{h.line_count}</TD>
                    <TD><Badge tone={COMPLIANCE[h.compliance].tone}>{COMPLIANCE[h.compliance].label}</Badge>
                      <span className="block text-xs text-muted-foreground">{h.blocking_count} bloquante(s) · {h.warning_count} avert.</span></TD>
                    <TD><code className="text-xs" title={h.sha256}>{h.sha256.slice(0, 12)}…</code></TD>
                    <TD className="space-y-1 text-xs">
                      <button type="button" className="flex items-center gap-1 text-link hover:underline"
                        onClick={() => download(`${F}/exports/${h.id}/documentation`, `DOCUMENTATION_${h.filename.replace(/\.(txt|csv)$/, ".txt")}`)}>
                        <FileText className="h-3.5 w-3.5" aria-hidden /> Documentation
                      </button>
                      <button type="button" className="flex items-center gap-1 text-link hover:underline"
                        onClick={() => download(`${F}/exports/${h.id}/anomalies.csv`, `anomalies_v${h.version_no}.csv`)}>
                        <Download className="h-3.5 w-3.5" aria-hidden /> Anomalies
                      </button>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Structure réglementaire */}
      <Card>
        <CardHeader>
          <CardTitle>Structure du fichier (art. 5)</CardTitle>
          <CardDescription>{spec.version}</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <THead><tr><TH>N°</TH><TH>Champ</TH><TH>Information portée</TH><TH>Type</TH><TH>Obligatoire</TH><TH>Format</TH><TH>Origine KOFINEX</TH></tr></THead>
            <TBody>
              {[...spec.fields, ...(p.accounting_type === "cash" ? spec.cash_fields : [])].map((f) => (
                <TR key={f.order}>
                  <TD>{f.order}</TD><TD className="font-medium">{f.name}</TD><TD className="text-xs">{f.information}</TD><TD className="text-xs">{f.type}</TD>
                  <TD>{f.mandatory ? "Oui" : "Non"}</TD><TD className="text-xs">{f.format}</TD><TD className="text-xs text-muted-foreground">{f.source}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <ul className="mt-3 list-disc space-y-0.5 pl-5 text-xs text-muted-foreground">
            {spec.applied.map((a) => <li key={a.key}><span className="font-medium text-foreground">{a.label}</span> : {a.detail}</li>)}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}

function Anomalies({ cid, rows }: { cid: string; rows: FecAnomaly[] }) {
  return (
    <Table>
      <THead><tr><TH>Gravité</TH><TH>N° écriture</TH><TH>Date</TH><TH>Journal</TH><TH>Compte</TH><TH>Nature</TH><TH>Description</TH><TH>Action recommandée</TH></tr></THead>
      <TBody>
        {rows.map((a, i) => (
          <TR key={`${a.code}-${a.entry_id ?? a.journal ?? ""}-${a.account ?? ""}-${i}`}>
            <TD><Badge tone={a.severity === "blocking" ? "red" : "amber"}>{a.severity === "blocking" ? "Bloquante" : "Avertissement"}</Badge></TD>
            <TD className="whitespace-nowrap text-xs">
              {a.entry_id
                ? <Link className="text-link underline-offset-2 hover:underline" href={`/companies/${cid}/comptabilite/ecritures/${a.entry_id}`}>{a.number ?? "Écriture"}</Link>
                : "—"}
            </TD>
            <TD className="text-xs">{a.entry_date ? formatDate(a.entry_date) : "—"}</TD>
            <TD className="text-xs">{a.journal ?? "—"}</TD>
            <TD className="text-xs">{a.account ?? "—"}</TD>
            <TD className="text-xs font-medium">{a.nature}</TD>
            <TD className="text-xs">{a.description}</TD>
            <TD className="text-xs text-muted-foreground">{a.action}</TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}
