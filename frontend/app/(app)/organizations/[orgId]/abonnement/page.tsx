"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import type { Organization } from "@/lib/types";
import {
  ACCESS_LABELS, COUNTRY_NAMES, CURRENCY_LABELS, INTERVAL_LABELS, QUOTA_LABELS, SUB_STATUS, formatMoney,
  type BillingAccount, type Catalog, type Entitlements, type Interval, type Quote, type Subscription, type Usage,
} from "@/lib/billing-types";
import { formatDate } from "@/lib/utils";
import { CurrencyIntervalPicker, PlanCard } from "@/components/billing";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, Loading, PageHeader } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const EMPTY_ACCOUNT = { legal_name: "", tax_id: "", address: "", city: "", country_code: "BJ", billing_email: "" };

function Overview({ sub, isOwner, base, onChange }: {
  sub: Subscription | null; isOwner: boolean; base: string; onChange: (s: Subscription | null) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [reason, setReason] = useState("");
  async function act(path: string, body?: unknown) {
    setBusy(true);
    setError(null);
    try {
      onChange((await api.post<{ subscription: Subscription | null }>(`${base}/subscription/${path}`, body)).subscription);
      setCancelOpen(false);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  if (!sub) {
    return (
      <Card>
        <CardHeader><CardTitle>Abonnement</CardTitle>
          <CardDescription>Aucun abonnement. Choisissez une offre ci-dessous pour démarrer l&apos;essai gratuit.</CardDescription>
        </CardHeader>
      </Card>
    );
  }
  const st = SUB_STATUS[sub.effective_status] ?? { label: sub.effective_status, tone: "neutral" as const };
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-4">
        <div>
          <CardTitle className="flex items-center gap-2">{sub.plan?.name ?? "Abonnement"} <Badge tone={st.tone}>{st.label}</Badge></CardTitle>
          <CardDescription>
            {sub.plan && <>Version {sub.plan.version_label}{sub.plan.version_status === "retired" ? " (retirée du catalogue, conservée pour votre abonnement)" : ""} · </>}
            {sub.billing_interval && INTERVAL_LABELS[sub.billing_interval]}{sub.currency && ` · ${CURRENCY_LABELS[sub.currency]}`}
          </CardDescription>
        </div>
        {isOwner && (
          <div className="flex gap-2">
            {sub.can_cancel && <Button variant="outline" size="sm" onClick={() => setCancelOpen(true)}>Demander la résiliation</Button>}
            {sub.can_reactivate && <Button size="sm" loading={busy} onClick={() => act("reactivate")}>Annuler la résiliation</Button>}
          </div>
        )}
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        {error && <Alert>{error}</Alert>}
        {sub.status === "trialing" && sub.trial_end && <p>Essai gratuit jusqu&apos;au <strong>{formatDate(sub.trial_end)}</strong>.</p>}
        {sub.cancel_at && <Alert kind="warning">Résiliation demandée : effet le {formatDate(sub.cancel_at)}. Vos données restent consultables et exportables.</Alert>}
        {sub.pending_transition && (
          <Alert kind="warning">Échéance dépassée : l&apos;abonnement est traité comme « {SUB_STATUS[sub.pending_transition]?.label ?? sub.pending_transition} ».</Alert>
        )}
        {sub.status === "trialing" && (
          <p className="text-muted-foreground">
            Le passage à l&apos;abonnement payant ouvrira avec le paiement en ligne (SASPay). Aucun paiement n&apos;est demandé pendant l&apos;essai.
          </p>
        )}
      </CardContent>
      <Dialog open={cancelOpen} onClose={() => setCancelOpen(false)} title="Demander la résiliation"
              description="La résiliation prend effet à la fin de l'essai ou de la période en cours. Vous pouvez l'annuler d'ici là.">
        <div className="space-y-4">
          <Field label="Motif (facultatif)" htmlFor="motif">
            <Input id="motif" value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} />
          </Field>
          <div className="flex justify-end"><Button loading={busy} onClick={() => act("cancel", { reason: reason.trim() || null })}>Confirmer</Button></div>
        </div>
      </Dialog>
    </Card>
  );
}

function UsageCard({ base }: { base: string }) {
  const { data, error } = useApiResource<Usage>(`${base}/usage`);
  if (error) return <Alert>{error}</Alert>;
  if (!data) return <Loading />;
  return (
    <Card>
      <CardHeader><CardTitle>Utilisation</CardTitle>
        <CardDescription>Période du {formatDate(data.period_start)} au {formatDate(data.period_end)} ; mesures faites par le serveur.</CardDescription>
      </CardHeader>
      <CardContent>
        <Table>
          <THead><tr><TH>Grandeur</TH><TH className="text-right">Utilisé</TH><TH className="text-right">Limite</TH></tr></THead>
          <TBody>
            {data.quotas.map((q) => (
              <TR key={q.key}>
                <TD>{QUOTA_LABELS[q.key] ?? q.key}</TD>
                <TD className="text-right tabular-nums">{q.used.toLocaleString("fr-FR")}</TD>
                <TD className="text-right tabular-nums">{q.unlimited ? "illimité" : (q.limit ?? 0).toLocaleString("fr-FR")}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function AccountCard({ base, isOwner, account, onSaved }: {
  base: string; isOwner: boolean; account: BillingAccount | null; onSaved: (a: BillingAccount) => void;
}) {
  const [form, setForm] = useState(EMPTY_ACCOUNT);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  useEffect(() => {
    if (account) setForm({ legal_name: account.legal_name, tax_id: account.tax_id ?? "", address: account.address,
                           city: account.city ?? "", country_code: account.country_code, billing_email: account.billing_email });
  }, [account]);
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setNotice(null);
    try {
      const r = await api.put<{ account: BillingAccount }>(`${base}/billing-account`, {
        ...form, tax_id: form.tax_id.trim() || null, city: form.city.trim() || null });
      onSaved(r.account);
      setNotice({ kind: "success", text: "Informations de facturation enregistrées." });
    } catch (err) {
      setNotice({ kind: "error", text: errorMessage(err) });
    } finally {
      setSaving(false);
    }
  }
  const set = (k: keyof typeof EMPTY_ACCOUNT) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm({ ...form, [k]: e.target.value });
  return (
    <Card>
      <CardHeader><CardTitle>Informations de facturation</CardTitle>
        <CardDescription>Le pays fixe la devise de l&apos;abonnement. {isOwner ? "" : "Modifiables par le propriétaire de l'organisation."}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={save} className="grid gap-3 md:grid-cols-2">
          {notice && <div className="md:col-span-2"><Alert kind={notice.kind}>{notice.text}</Alert></div>}
          <Field label="Raison sociale" htmlFor="ba-name" required><Input id="ba-name" value={form.legal_name} onChange={set("legal_name")} disabled={!isOwner} /></Field>
          <Field label="Identifiant fiscal (IFU, NIU…)" htmlFor="ba-tax"><Input id="ba-tax" value={form.tax_id} onChange={set("tax_id")} disabled={!isOwner} /></Field>
          <Field label="Adresse" htmlFor="ba-addr" required><Input id="ba-addr" value={form.address} onChange={set("address")} disabled={!isOwner} /></Field>
          <Field label="Ville" htmlFor="ba-city"><Input id="ba-city" value={form.city} onChange={set("city")} disabled={!isOwner} /></Field>
          <Field label="Pays de facturation" htmlFor="ba-country" required>
            <Select id="ba-country" value={form.country_code} onChange={set("country_code")} disabled={!isOwner}>
              {Object.entries(COUNTRY_NAMES).sort((a, b) => a[1].localeCompare(b[1], "fr")).map(([c, n]) => <option key={c} value={c}>{n}</option>)}
            </Select>
          </Field>
          <Field label="E-mail de facturation" htmlFor="ba-mail" required>
            <Input id="ba-mail" type="email" value={form.billing_email} onChange={set("billing_email")} disabled={!isOwner} />
          </Field>
          {isOwner && (
            <div className="flex justify-end md:col-span-2">
              <Button type="submit" loading={saving} disabled={!form.legal_name.trim() || !form.address.trim() || !form.billing_email.trim()}>Enregistrer</Button>
            </div>
          )}
        </form>
      </CardContent>
    </Card>
  );
}

function Offers({ base, isOwner, account, sub, onStarted }: {
  base: string; isOwner: boolean; account: BillingAccount | null; sub: Subscription | null; onStarted: (s: Subscription | null) => void;
}) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [interval, setInterval] = useState<Interval>("month");
  const [country, setCountry] = useState(account?.country_code ?? "BJ");
  const [promo, setPromo] = useState("");
  const [quote, setQuote] = useState<{ name: string; data: Quote } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => { api.get<Catalog>("/billing/catalog").then(setCatalog).catch((e) => setError(errorMessage(e))); }, []);
  useEffect(() => { if (account) setCountry(account.country_code); }, [account]);
  const currency = catalog?.countries[country] ?? "XOF";

  async function preview(versionId: string, name: string) {
    setBusy(`quote:${versionId}`);
    setError(null);
    try {
      const data = await api.post<Quote>(`${base}/subscription/quote`, { version_id: versionId, billing_interval: interval,
                                                                          promotion_code: promo.trim() || null });
      setQuote({ name, data });
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }
  async function trial(versionId: string) {
    setBusy(`trial:${versionId}`);
    setError(null);
    try {
      onStarted((await api.post<{ subscription: Subscription }>(`${base}/subscription/trial`,
                                                               { version_id: versionId, billing_interval: interval })).subscription);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }
  if (!catalog) return error ? <Alert>{error}</Alert> : <Loading />;
  return (
    <Card>
      <CardHeader><CardTitle>Offres</CardTitle>
        <CardDescription>Prix hors taxes, calculés par le serveur. {account ? "" : "Renseignez les informations de facturation pour obtenir un devis ou démarrer l'essai."}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="flex flex-wrap items-end gap-4">
          {account
            ? <p className="text-sm">Devise de facturation : <strong>{CURRENCY_LABELS[currency]}</strong> ({COUNTRY_NAMES[country] ?? country})</p>
            : <CurrencyIntervalPicker countries={catalog.countries} country={country} onCountry={setCountry} interval={interval} onInterval={setInterval} />}
          {account && (
            <Select aria-label="Périodicité" value={interval} onChange={(e) => setInterval(e.target.value as Interval)} className="w-40">
              <option value="month">Mensuel</option><option value="year">Annuel</option>
            </Select>
          )}
          <Field label="Code promotionnel" htmlFor="promo"><Input id="promo" value={promo} onChange={(e) => setPromo(e.target.value.toUpperCase())} className="w-48" /></Field>
        </div>
        {error && <Alert>{error}</Alert>}
        {catalog.plans.length === 0 && <Alert kind="info">Aucune offre n&apos;est encore publiée.</Alert>}
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {catalog.plans.map((p) => (
            <PlanCard key={p.version_id} plan={p} modules={catalog.modules} currency={currency} interval={interval}>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" size="sm" disabled={!account} loading={busy === `quote:${p.version_id}`}
                        onClick={() => preview(p.version_id, p.name)}>Devis</Button>
                {isOwner && !sub && p.trial_days && (
                  <Button size="sm" disabled={!account} loading={busy === `trial:${p.version_id}`} onClick={() => trial(p.version_id)}>
                    Démarrer l&apos;essai ({p.trial_days} jours)
                  </Button>
                )}
              </div>
            </PlanCard>
          ))}
        </div>
      </CardContent>
      <Dialog open={!!quote} onClose={() => setQuote(null)} title={`Devis — ${quote?.name ?? ""}`}
              description="Aperçu calculé par le serveur ; aucune commande n'est créée.">
        {quote && (
          <div className="space-y-3 text-sm">
            <Table>
              <THead><tr><TH>Ligne</TH><TH className="text-right">Montant</TH><TH className="text-right">Remise</TH></tr></THead>
              <TBody>
                {quote.data.lines.map((l) => (
                  <TR key={l.label}><TD>{l.label}{l.quantity > 1 ? ` × ${l.quantity}` : ""}</TD>
                    <TD className="text-right tabular-nums">{formatMoney(l.amount, quote.data.currency)}</TD>
                    <TD className="text-right tabular-nums">{formatMoney(l.discount, quote.data.currency)}</TD></TR>
                ))}
              </TBody>
            </Table>
            <p className="flex justify-between font-semibold"><span>Total hors taxes {INTERVAL_LABELS[quote.data.interval]}</span>
              <span className="tabular-nums">{formatMoney(quote.data.total, quote.data.currency)}</span></p>
            {quote.data.notes.map((n) => <p key={n} className="text-xs text-muted-foreground">{n}</p>)}
          </div>
        )}
      </Dialog>
    </Card>
  );
}

export default function AbonnementPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const base = `/organizations/${orgId}`;
  const { data: org } = useApiResource<Organization>(base);
  const isManager = org?.my_role === "owner" || org?.my_role === "admin";
  const isOwner = org?.my_role === "owner";
  const ent = useApiResource<Entitlements>(`${base}/entitlements`);
  const [moduleLabels, setModuleLabels] = useState<Record<string, string>>({});
  useEffect(() => {
    api.get<Catalog>("/billing/catalog")
      .then((c) => setModuleLabels(Object.fromEntries(c.modules.map((m) => [m.key, m.label]))))
      .catch(() => setModuleLabels({}));
  }, []);
  const subRes = useApiResource<{ subscription: Subscription | null }>(isManager ? `${base}/subscription` : null);
  const accRes = useApiResource<{ account: BillingAccount | null }>(isManager ? `${base}/billing-account` : null);
  const sub = subRes.data?.subscription ?? null;

  function refresh(s: Subscription | null) {
    subRes.setData({ subscription: s });
    void ent.reload();
  }

  return (
    <>
      <PageHeader title="Abonnement" description="Offre, essai, droits et informations de facturation de l'organisation." />
      {!org && <Loading />}
      <div className="space-y-6">
        {ent.data && (
          <Card>
            <CardHeader><CardTitle>Vos droits</CardTitle><CardDescription>{ACCESS_LABELS[ent.data.access]}</CardDescription></CardHeader>
            {ent.data.modules.length > 0 && (
              <CardContent className="flex flex-wrap gap-2">
                {ent.data.modules.map((m) => <Badge key={m} tone="blue">{moduleLabels[m] ?? m}</Badge>)}
              </CardContent>
            )}
          </Card>
        )}
        {org && !isManager && <Alert kind="info">Le détail de l&apos;abonnement est réservé au propriétaire et aux administrateurs de l&apos;organisation.</Alert>}
        {isManager && subRes.error && <Alert>{subRes.error}</Alert>}
        {isManager && subRes.data && <Overview sub={sub} isOwner={isOwner} base={base} onChange={refresh} />}
        {isManager && sub && <UsageCard base={base} />}
        {isManager && accRes.data && (
          <AccountCard base={base} isOwner={isOwner} account={accRes.data.account} onSaved={(a) => accRes.setData({ account: a })} />
        )}
        {isManager && subRes.data && accRes.data && (
          <Offers base={base} isOwner={isOwner} account={accRes.data.account} sub={sub} onStarted={refresh} />
        )}
      </div>
    </>
  );
}
