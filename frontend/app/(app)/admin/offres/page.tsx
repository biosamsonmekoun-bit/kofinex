"use client";

import { useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import type { Profile } from "@/lib/types";
import {
  COUNTRY_NAMES, CURRENCIES, CURRENCY_LABELS, INTERVAL_LABELS, QUOTA_LABELS, formatMoney,
  type AdminProduct, type AdminVersion, type BillingModule, type BillingSettings, type Currency, type Interval,
  type Promotion, type Quotas,
} from "@/lib/billing-types";
import { formatDate } from "@/lib/utils";
import { QuotaList } from "@/components/billing";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading, PageHeader } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const A = "/admin/billing";
const VSTATUS: Record<AdminVersion["status"], { label: string; tone: "neutral" | "green" | "amber" }> = {
  draft: { label: "Brouillon", tone: "amber" }, published: { label: "Publiée", tone: "green" }, retired: { label: "Retirée", tone: "neutral" },
};
type QuotaMode = "none" | "limit" | "unlimited";
const QUOTA_KEYS = Object.keys(QUOTA_LABELS);

// ------------------------------------------------------------------ éditeur d'un brouillon
function DraftEditor({ product, version, modules, onDone }: {
  product: AdminProduct; version: AdminVersion; modules: BillingModule[]; onDone: () => void;
}) {
  const [label, setLabel] = useState(version.label);
  const [description, setDescription] = useState(version.description ?? "");
  const [trial, setTrial] = useState(version.trial_days?.toString() ?? "");
  const [prices, setPrices] = useState(version.prices.map((p) => ({ ...p })));
  const [mods, setMods] = useState<string[]>(version.modules);
  const [quotas, setQuotas] = useState<Record<string, { mode: QuotaMode; value: string }>>(
    Object.fromEntries(QUOTA_KEYS.map((k) => [k, k in version.quotas
      ? (version.quotas[k] === null ? { mode: "unlimited" as QuotaMode, value: "" } : { mode: "limit" as QuotaMode, value: String(version.quotas[k]) })
      : { mode: "none" as QuotaMode, value: "" }])));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const q: Quotas = {};
      for (const k of QUOTA_KEYS) {
        const { mode, value } = quotas[k];
        if (mode === "unlimited") q[k] = null;
        if (mode === "limit") {
          if (!/^\d+$/.test(value)) throw new Error(`${QUOTA_LABELS[k]} : nombre entier attendu`);
          q[k] = Number(value);   // quantité entière (pas un montant)
        }
      }
      await api.patch(`${A}/versions/${version.id}`, { label: label.trim(), description: description.trim() || null,
                                                        trial_days: product.kind === "plan" && trial ? Number(trial) : null });
      await api.put(`${A}/versions/${version.id}/prices`, { prices });
      await api.put(`${A}/versions/${version.id}/entitlements`, { modules: mods, quotas: q });
      onDone();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-4 text-sm">
      {error && <Alert>{error}</Alert>}
      <div className="grid gap-3 md:grid-cols-3">
        <Field label="Libellé de la version" htmlFor="ve-label" required><Input id="ve-label" value={label} onChange={(e) => setLabel(e.target.value)} /></Field>
        {product.kind === "plan" && (
          <Field label="Essai gratuit (jours)" htmlFor="ve-trial" hint="Vide : pas d'essai.">
            <Input id="ve-trial" inputMode="numeric" value={trial} onChange={(e) => setTrial(e.target.value.replace(/\D/g, ""))} />
          </Field>
        )}
        <Field label="Description" htmlFor="ve-desc"><Input id="ve-desc" value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
      </div>

      <fieldset className="space-y-2">
        <legend className="font-semibold">Prix hors taxes (XOF, XAF, GNF, KMF : entiers ; CDF : deux décimales)</legend>
        {prices.map((p, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2">
            <Select aria-label="Périodicité" value={p.billing_interval} className="w-36"
                    onChange={(e) => setPrices(prices.map((x, j) => (j === i ? { ...x, billing_interval: e.target.value as Interval } : x)))}>
              <option value="month">Mensuel</option><option value="year">Annuel</option>
            </Select>
            <Select aria-label="Devise" value={p.currency} className="w-40"
                    onChange={(e) => setPrices(prices.map((x, j) => (j === i ? { ...x, currency: e.target.value as Currency } : x)))}>
              {CURRENCIES.map((c) => <option key={c} value={c}>{CURRENCY_LABELS[c]}</option>)}
            </Select>
            {/* saisie en texte : le montant n'est jamais converti en nombre flottant */}
            <Input aria-label="Montant" inputMode="decimal" value={p.amount} className="w-40"
                   onChange={(e) => setPrices(prices.map((x, j) => (j === i ? { ...x, amount: e.target.value.replace(",", ".").replace(/[^\d.]/g, "") } : x)))} />
            <Button variant="ghost" size="sm" aria-label="Retirer ce prix" onClick={() => setPrices(prices.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4" /></Button>
          </div>
        ))}
        <Button variant="outline" size="sm" onClick={() => setPrices([...prices, { billing_interval: "month", currency: "XOF", amount: "" }])}>
          <Plus className="h-4 w-4" /> Ajouter un prix
        </Button>
      </fieldset>

      <fieldset>
        <legend className="font-semibold">Modules</legend>
        <div className="mt-2 grid gap-1 md:grid-cols-2">
          {modules.map((m) => (
            <label key={m.key} className="flex items-start gap-2">
              <input type="checkbox" checked={mods.includes(m.key)} className="mt-1"
                     onChange={(e) => setMods(e.target.checked ? [...mods, m.key] : mods.filter((x) => x !== m.key))} />
              <span>{m.label}{m.is_core ? " (socle)" : ""}{m.requires.length > 0 && <span className="text-muted-foreground"> — exige {m.requires.join(", ")}</span>}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset>
        <legend className="font-semibold">{product.kind === "plan" ? "Quotas (tous requis pour publier)" : "Quotas ajoutés par unité d'option"}</legend>
        <div className="mt-2 grid gap-2 md:grid-cols-2">
          {QUOTA_KEYS.map((k) => (
            <div key={k} className="flex items-center gap-2">
              <span className="w-48 shrink-0">{QUOTA_LABELS[k]}</span>
              <Select aria-label={`Mode ${QUOTA_LABELS[k]}`} value={quotas[k].mode} className="w-36"
                      onChange={(e) => setQuotas({ ...quotas, [k]: { ...quotas[k], mode: e.target.value as QuotaMode } })}>
                <option value="none">Non accordé</option>
                <option value="limit">{product.kind === "plan" ? "Limite" : "Incrément"}</option>
                {product.kind === "plan" && <option value="unlimited">Illimité</option>}
              </Select>
              {quotas[k].mode === "limit" && (
                <Input aria-label={`Valeur ${QUOTA_LABELS[k]}`} inputMode="numeric" value={quotas[k].value} className="w-28"
                       onChange={(e) => setQuotas({ ...quotas, [k]: { ...quotas[k], value: e.target.value.replace(/\D/g, "") } })} />
              )}
            </div>
          ))}
        </div>
      </fieldset>
      <div className="flex justify-end"><Button loading={saving} disabled={!label.trim()} onClick={save}>Enregistrer le brouillon</Button></div>
    </div>
  );
}

// ------------------------------------------------------------------ offres
function ProductCard({ p, modules, onChange }: { p: AdminProduct; modules: BillingModule[]; onChange: () => void }) {
  const [editing, setEditing] = useState<AdminVersion | null>(null);
  const [issues, setIssues] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function run(key: string, fn: () => Promise<unknown>) {
    setBusy(key);
    setError(null);
    setIssues(null);
    try {
      await fn();
      onChange();
    } catch (e) {
      const details = (e as { details?: { issues?: string[] } }).details;
      if (details?.issues) setIssues(details.issues);
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }
  const latest = p.versions[0];
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-4">
        <div>
          <CardTitle className="flex items-center gap-2">{p.name} <Badge>{p.kind === "plan" ? "Offre" : "Option"}</Badge></CardTitle>
          <CardDescription>{p.code}{p.description ? ` — ${p.description}` : ""}</CardDescription>
        </div>
        <Button size="sm" variant="outline" loading={busy === "new"}
                onClick={() => run("new", () => api.post(`${A}/products/${p.id}/versions`, {
                  label: `v${(latest?.version_no ?? 0) + 1}`, trial_days: latest?.trial_days ?? null, copy_from: latest?.id ?? null }))}>
          <Plus className="h-4 w-4" /> Nouvelle version{latest ? " (copie)" : ""}
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        {error && <Alert>{error}</Alert>}
        {issues && <ul className="list-disc pl-5 text-sm text-destructive-strong">{issues.map((i) => <li key={i}>{i}</li>)}</ul>}
        {p.versions.length === 0 ? <p className="text-sm text-muted-foreground">Aucune version.</p> : (
          <Table>
            <THead><tr><TH>Version</TH><TH>Statut</TH><TH>Prix</TH><TH>Droits</TH><TH /></tr></THead>
            <TBody>
              {p.versions.map((v) => (
                <TR key={v.id}>
                  <TD className="whitespace-nowrap font-medium">{v.label}<p className="text-xs text-muted-foreground">n° {v.version_no}{v.trial_days ? ` · essai ${v.trial_days} j` : ""}</p></TD>
                  <TD><Badge tone={VSTATUS[v.status].tone}>{VSTATUS[v.status].label}</Badge>
                    {v.published_at && <p className="text-xs text-muted-foreground">{formatDate(v.published_at)}</p>}</TD>
                  <TD className="text-xs tabular-nums">{v.prices.length === 0 ? "—" : v.prices.map((x) => (
                    <div key={`${x.billing_interval}${x.currency}`}>{formatMoney(x.amount, x.currency)} {INTERVAL_LABELS[x.billing_interval]}</div>))}</TD>
                  <TD className="text-xs">{v.modules.length} module(s)<QuotaList quotas={v.quotas} /></TD>
                  <TD className="whitespace-nowrap text-right">
                    {v.status === "draft" && (
                      <div className="flex justify-end gap-1">
                        <Button size="sm" variant="outline" onClick={() => setEditing(v)}>Modifier</Button>
                        <Button size="sm" variant="outline" loading={busy === `val${v.id}`}
                                onClick={() => run(`val${v.id}`, async () => {
                                  const r = await api.post<{ issues: string[] }>(`${A}/versions/${v.id}/validate`);
                                  setIssues(r.issues.length ? r.issues : ["Aucune anomalie : la version est publiable."]);
                                })}>Vérifier</Button>
                        <Button size="sm" loading={busy === `pub${v.id}`} onClick={() => run(`pub${v.id}`, () => api.post(`${A}/versions/${v.id}/publish`))}>Publier</Button>
                        <Button size="sm" variant="ghost" aria-label="Supprimer le brouillon" loading={busy === `del${v.id}`}
                                onClick={() => run(`del${v.id}`, () => api.del(`${A}/versions/${v.id}`))}><Trash2 className="h-4 w-4" /></Button>
                      </div>
                    )}
                    {v.status === "published" && (
                      <Button size="sm" variant="outline" loading={busy === `ret${v.id}`}
                              onClick={() => run(`ret${v.id}`, () => api.post(`${A}/versions/${v.id}/retire`))}>Retirer</Button>
                    )}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </CardContent>
      <Dialog open={!!editing} onClose={() => setEditing(null)} title={`Brouillon — ${p.name}`}
              description="Une version publiée est figée : prix, modules, quotas et essai ne changent plus. Les abonnés restent sur leur version.">
        {editing && <DraftEditor product={p} version={editing} modules={modules} onDone={() => { setEditing(null); onChange(); }} />}
      </Dialog>
    </Card>
  );
}

function NewProduct({ onCreated }: { onCreated: () => void }) {
  const [f, setF] = useState({ code: "", kind: "plan", name: "", description: "" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await api.post(`${A}/products`, { ...f, code: f.code.trim().toUpperCase(), name: f.name.trim(), description: f.description.trim() || null });
      onCreated();
    } catch (err) {
      setError(errorMessage(err));
      setSaving(false);
    }
  }
  return (
    <form onSubmit={submit} className="space-y-3">
      {error && <Alert>{error}</Alert>}
      <Field label="Code" htmlFor="np-code" required hint="Majuscules, chiffres et _ (ex. ESSENTIEL). Non modifiable.">
        <Input id="np-code" value={f.code} onChange={(e) => setF({ ...f, code: e.target.value.toUpperCase() })} />
      </Field>
      <Field label="Nature" htmlFor="np-kind" required>
        <Select id="np-kind" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
          <option value="plan">Offre de base</option><option value="addon">Option</option>
        </Select>
      </Field>
      <Field label="Nom affiché" htmlFor="np-name" required><Input id="np-name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
      <Field label="Description" htmlFor="np-desc"><Input id="np-desc" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
      <div className="flex justify-end"><Button type="submit" loading={saving} disabled={!/^[A-Z0-9_]{2,40}$/.test(f.code) || !f.name.trim()}>Créer</Button></div>
    </form>
  );
}

// ------------------------------------------------------------------ promotions
function Promotions() {
  const { data, error, reload } = useApiResource<Promotion[]>(`${A}/promotions`);
  const [f, setF] = useState({ code: "", label: "", discount_type: "percent", percent: "", fixed_amount: "", fixed_currency: "XOF",
                               duration: "once", duration_periods: "", valid_until: "", max_redemptions: "" });
  const [msg, setMsg] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  async function create(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMsg(null);
    try {
      await api.post(`${A}/promotions`, {
        code: f.code.trim().toUpperCase(), label: f.label.trim(), discount_type: f.discount_type,
        percent: f.discount_type === "percent" ? f.percent : null,
        fixed_amount: f.discount_type === "fixed" ? f.fixed_amount : null,
        fixed_currency: f.discount_type === "fixed" ? f.fixed_currency : null,
        duration: f.duration, duration_periods: f.duration === "repeating" ? Number(f.duration_periods) : null,
        valid_until: f.valid_until ? new Date(`${f.valid_until}T23:59:59`).toISOString() : null,
        max_redemptions: f.max_redemptions ? Number(f.max_redemptions) : null,
      });
      setF({ ...f, code: "", label: "" });
      void reload();
    } catch (err) {
      setMsg(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }
  async function toggle(p: Promotion) {
    try {
      await api.patch(`${A}/promotions/${p.id}`, { status: p.status === "active" ? "disabled" : "active" });
      void reload();
    } catch (err) {
      setMsg(errorMessage(err));
    }
  }
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader><CardTitle>Nouvelle promotion</CardTitle>
          <CardDescription>Les conditions sont figées à la création ; seuls le libellé, le statut, la fin de validité et le plafond changent ensuite.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={create} className="grid gap-3 md:grid-cols-4">
            {msg && <div className="md:col-span-4"><Alert>{msg}</Alert></div>}
            <Field label="Code" htmlFor="pr-code" required><Input id="pr-code" value={f.code} onChange={(e) => setF({ ...f, code: e.target.value.toUpperCase() })} /></Field>
            <Field label="Libellé" htmlFor="pr-label" required><Input id="pr-label" value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} /></Field>
            <Field label="Type" htmlFor="pr-type">
              <Select id="pr-type" value={f.discount_type} onChange={(e) => setF({ ...f, discount_type: e.target.value })}>
                <option value="percent">Pourcentage</option><option value="fixed">Montant fixe</option>
              </Select>
            </Field>
            {f.discount_type === "percent" ? (
              <Field label="Pourcentage" htmlFor="pr-pct" required><Input id="pr-pct" inputMode="decimal" value={f.percent}
                     onChange={(e) => setF({ ...f, percent: e.target.value.replace(",", ".").replace(/[^\d.]/g, "") })} /></Field>
            ) : (
              <div className="flex gap-2">
                <Field label="Montant" htmlFor="pr-amt" required><Input id="pr-amt" inputMode="decimal" value={f.fixed_amount}
                       onChange={(e) => setF({ ...f, fixed_amount: e.target.value.replace(",", ".").replace(/[^\d.]/g, "") })} /></Field>
                <Field label="Devise" htmlFor="pr-cur"><Select id="pr-cur" value={f.fixed_currency} onChange={(e) => setF({ ...f, fixed_currency: e.target.value })}>
                  {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}</Select></Field>
              </div>
            )}
            <Field label="Durée" htmlFor="pr-dur">
              <Select id="pr-dur" value={f.duration} onChange={(e) => setF({ ...f, duration: e.target.value })}>
                <option value="once">Une fois</option><option value="repeating">N périodes</option><option value="forever">Permanente</option>
              </Select>
            </Field>
            {f.duration === "repeating" && (
              <Field label="Nombre de périodes" htmlFor="pr-n" required><Input id="pr-n" inputMode="numeric" value={f.duration_periods}
                     onChange={(e) => setF({ ...f, duration_periods: e.target.value.replace(/\D/g, "") })} /></Field>
            )}
            <Field label="Valable jusqu'au" htmlFor="pr-until"><Input id="pr-until" type="date" value={f.valid_until} onChange={(e) => setF({ ...f, valid_until: e.target.value })} /></Field>
            <Field label="Utilisations maximales" htmlFor="pr-max"><Input id="pr-max" inputMode="numeric" value={f.max_redemptions}
                   onChange={(e) => setF({ ...f, max_redemptions: e.target.value.replace(/\D/g, "") })} /></Field>
            <div className="flex items-end justify-end md:col-span-4"><Button type="submit" loading={saving} disabled={!f.code || !f.label.trim()}>Créer la promotion</Button></div>
          </form>
        </CardContent>
      </Card>
      {error && <Alert>{error}</Alert>}
      {data && data.length === 0 && <EmptyState title="Aucune promotion" description="Les codes créés ici sont vérifiés un par un lors d'un devis ; ils ne sont jamais listés aux clients." />}
      {data && data.length > 0 && (
        <Table>
          <THead><tr><TH>Code</TH><TH>Remise</TH><TH>Durée</TH><TH>Validité</TH><TH>Statut</TH><TH /></tr></THead>
          <TBody>
            {data.map((p) => (
              <TR key={p.id}>
                <TD className="font-medium">{p.code}<p className="text-xs text-muted-foreground">{p.label}</p></TD>
                <TD className="tabular-nums">{p.discount_type === "percent" ? `${p.percent} %` : formatMoney(p.fixed_amount, p.fixed_currency ?? "XOF")}</TD>
                <TD>{p.duration === "once" ? "une fois" : p.duration === "forever" ? "permanente" : `${p.duration_periods} périodes`}</TD>
                <TD className="text-xs">{formatDate(p.valid_from)} → {p.valid_until ? formatDate(p.valid_until) : "sans fin"}{p.max_redemptions ? ` · ${p.max_redemptions} max.` : ""}</TD>
                <TD><Badge tone={p.status === "active" ? "green" : "neutral"}>{p.status === "active" ? "Active" : "Désactivée"}</Badge></TD>
                <TD className="text-right"><Button size="sm" variant="outline" onClick={() => toggle(p)}>{p.status === "active" ? "Désactiver" : "Réactiver"}</Button></TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ paramètres
function SettingsForm() {
  const { data, error, setData } = useApiResource<BillingSettings>(`${A}/settings`);
  const [f, setF] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (data) setF({
      grace_days: String(data.grace_days), suspension_to_cancel_days: data.suspension_to_cancel_days?.toString() ?? "",
      renewal_notice_days: data.renewal_notice_days?.toString() ?? "", reminder_days: data.reminder_days.join(", "),
      max_orgs_per_user: data.max_orgs_per_user?.toString() ?? "", seller_name: data.seller_name ?? "",
      seller_tax_id: data.seller_tax_id ?? "", seller_address: data.seller_address ?? "",
    });
  }, [data]);
  const int = (v: string) => (v.trim() === "" ? null : Number(v));
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setNotice(null);
    try {
      setData(await api.put<BillingSettings>(`${A}/settings`, {
        grace_days: Number(f.grace_days), suspension_to_cancel_days: int(f.suspension_to_cancel_days),
        renewal_notice_days: int(f.renewal_notice_days), max_orgs_per_user: int(f.max_orgs_per_user),
        reminder_days: f.reminder_days.split(",").map((x) => x.trim()).filter(Boolean).map(Number),
        seller_name: f.seller_name.trim() || null, seller_tax_id: f.seller_tax_id.trim() || null, seller_address: f.seller_address.trim() || null,
      }));
      setNotice({ kind: "success", text: "Paramètres enregistrés (modification journalisée)." });
    } catch (err) {
      setNotice({ kind: "error", text: errorMessage(err) });
    } finally {
      setSaving(false);
    }
  }
  if (error) return <Alert>{error}</Alert>;
  if (!data) return <Loading />;
  const num = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value.replace(/\D/g, "") });
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader><CardTitle>Impayés, relances et vendeur</CardTitle>
          <CardDescription>Délai avant résiliation vide : aucune résiliation automatique. Relances : nombres de jours, séparés par des virgules.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={save} className="grid gap-3 md:grid-cols-3">
            {notice && <div className="md:col-span-3"><Alert kind={notice.kind}>{notice.text}</Alert></div>}
            <Field label="Période de grâce (jours)" htmlFor="st-grace" required><Input id="st-grace" inputMode="numeric" value={f.grace_days ?? ""} onChange={num("grace_days")} /></Field>
            <Field label="Suspension → résiliation (jours)" htmlFor="st-cancel"><Input id="st-cancel" inputMode="numeric" value={f.suspension_to_cancel_days ?? ""} onChange={num("suspension_to_cancel_days")} /></Field>
            <Field label="Avis de renouvellement (jours avant)" htmlFor="st-renew"><Input id="st-renew" inputMode="numeric" value={f.renewal_notice_days ?? ""} onChange={num("renewal_notice_days")} /></Field>
            <Field label="Relances (jours)" htmlFor="st-rem"><Input id="st-rem" value={f.reminder_days ?? ""} onChange={(e) => setF({ ...f, reminder_days: e.target.value.replace(/[^\d,\s]/g, "") })} /></Field>
            <Field label="Organisations par utilisateur (max.)" htmlFor="st-max"><Input id="st-max" inputMode="numeric" value={f.max_orgs_per_user ?? ""} onChange={num("max_orgs_per_user")} /></Field>
            <div />
            <Field label="Entité vendeuse" htmlFor="st-sname"><Input id="st-sname" value={f.seller_name ?? ""} onChange={(e) => setF({ ...f, seller_name: e.target.value })} /></Field>
            <Field label="IFU du vendeur" htmlFor="st-stax"><Input id="st-stax" value={f.seller_tax_id ?? ""} onChange={(e) => setF({ ...f, seller_tax_id: e.target.value })} /></Field>
            <Field label="Adresse du vendeur" htmlFor="st-saddr"><Input id="st-saddr" value={f.seller_address ?? ""} onChange={(e) => setF({ ...f, seller_address: e.target.value })} /></Field>
            <div className="flex justify-end md:col-span-3"><Button type="submit" loading={saving} disabled={!f.grace_days}>Enregistrer</Button></div>
          </form>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Pays de facturation ouverts</CardTitle>
          <CardDescription>Vendeur : {COUNTRY_NAMES[data.seller_country] ?? data.seller_country}. Liste arrêtée au § 16 (17 États de l&apos;OHADA).</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-1 text-sm md:grid-cols-3">
          {Object.entries(data.country_currencies).sort((a, b) => (COUNTRY_NAMES[a[0]] ?? a[0]).localeCompare(COUNTRY_NAMES[b[0]] ?? b[0], "fr")).map(([c, cur]) => (
            <p key={c}>{COUNTRY_NAMES[c] ?? c} — {CURRENCY_LABELS[cur]}</p>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ page
export default function AdminOffresPage() {
  const { data: me, loading: meLoading } = useApiResource<Profile>("/me");
  const isAdmin = !!me?.is_platform_admin;
  const products = useApiResource<AdminProduct[]>(isAdmin ? `${A}/products` : null);
  const modules = useApiResource<BillingModule[]>(isAdmin ? `${A}/modules` : null);
  const [tab, setTab] = useState<"offres" | "promotions" | "parametres">("offres");
  const [creating, setCreating] = useState(false);

  if (meLoading && !me) return <Loading />;
  if (!isAdmin) return <Alert>Réservé aux administrateurs de la plateforme.</Alert>;
  const TABS = [["offres", "Offres et options"], ["promotions", "Promotions"], ["parametres", "Paramètres"]] as const;
  return (
    <>
      <PageHeader title="Offres et tarifs" description="Catalogue commercial versionné. Aucun prix ni quota n'est prédéfini : tout est saisi ici."
                  actions={tab === "offres" && <Button size="sm" onClick={() => setCreating(true)}><Plus className="h-4 w-4" /> Nouvelle offre ou option</Button>} />
      <div role="tablist" className="mb-6 flex gap-1 border-b">
        {TABS.map(([k, l]) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
                  className={`-mb-px border-b-2 px-3 py-2 text-sm ${tab === k ? "border-primary font-semibold" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
            {l}
          </button>
        ))}
      </div>
      {tab === "offres" && (
        <div className="space-y-6">
          {products.error && <Alert>{products.error}</Alert>}
          {!products.data && !products.error && <Loading />}
          {products.data?.length === 0 && <EmptyState title="Aucune offre" description="Créez une offre de base, puis sa première version : prix, modules, quotas et essai." />}
          {products.data?.map((p) => <ProductCard key={p.id} p={p} modules={modules.data ?? []} onChange={() => void products.reload()} />)}
        </div>
      )}
      {tab === "promotions" && <Promotions />}
      {tab === "parametres" && <SettingsForm />}
      <Dialog open={creating} onClose={() => setCreating(false)} title="Nouvelle offre ou option">
        {creating && <NewProduct onCreated={() => { setCreating(false); void products.reload(); }} />}
      </Dialog>
    </>
  );
}
