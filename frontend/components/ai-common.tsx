"use client";

import { useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import type { AiSettings, AiSnapshot, AiStatus, AiValidation } from "@/lib/ai-types";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, Badge, Loading } from "@/components/ui/feedback";
import { Field } from "@/components/ui/form";

const AREA = "w-full rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30";

/** Résultat du contrôle « chaque chiffre cité existe dans le contexte ». */
export function NumberCheck({ v }: { v: AiValidation | null | undefined }) {
  if (!v) return null;
  if (v.status === "verified") return <Badge tone="green">{v.checked ? `${v.checked} chiffre(s) vérifié(s) dans le contexte` : "Aucun chiffre cité"}</Badge>;
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <Badge tone="amber">{v.untraceable.length} chiffre(s) non traçable(s)</Badge>
      <span className="text-xs text-muted-foreground">absent(s) du contexte transmis : {v.untraceable.map((u) => u.text).join(", ")} — à vérifier avant tout usage</span>
    </span>
  );
}

export function AiDraftBadge() {
  return <Badge tone="gold">Brouillon IA</Badge>;
}

/** Contexte exact transmis au modèle. */
export function ContextView({ s }: { s: AiSnapshot | null | undefined }) {
  const [open, setOpen] = useState(false);
  if (!s) return null;
  return (
    <div className="text-xs">
      <button type="button" className="text-link hover:underline" onClick={() => setOpen(!open)}>
        {open ? "Masquer" : "Voir"} le contexte transmis ({s.facts.length} valeur(s) calculée(s))
      </button>
      {open && (
        <div className="mt-1 max-h-64 overflow-y-auto rounded-md border bg-muted/40 p-2">
          {s.facts.map((f) => <p key={f.ref}><span className="font-medium">[{f.ref}]</span> {f.label}{f.period && ` (${f.period})`} : {f.value ?? "—"}</p>)}
          {s.facts.length === 0 && <p className="text-muted-foreground">Aucune valeur chiffrée ; données descriptives uniquement.</p>}
        </div>
      )}
    </div>
  );
}

export function AiUnavailable({ status }: { status: AiStatus | null | undefined }) {
  if (!status || status.configured) return null;
  return <Alert kind="info">IA indisponible sur cette installation : {status.reason} Aucune réponse n&apos;est simulée ; les autres fonctions restent utilisables.</Alert>;
}

/** Réglages de l'organisation : activation explicite, usage par usage. */
export function AiSettingsCard({ orgId }: { orgId: string }) {
  const { data, error, setData } = useApiResource<AiSettings>(`/organizations/${orgId}/ai-settings`);
  const [f, setF] = useState<{ enabled: boolean; uses: string[]; note: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (error) return <Alert>{error}</Alert>;
  if (!data) return <Loading />;
  const v = f ?? { enabled: data.enabled, uses: data.allowed_uses, note: data.acceptance_note ?? "" };
  async function save() {
    setBusy(true); setErr(null);
    try { const r = await api.put<AiSettings>(`/organizations/${orgId}/ai-settings`, { enabled: v.enabled, allowed_uses: v.uses, acceptance_note: v.note.trim() || null }); setData(r); setF(null); }
    catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>Intelligence artificielle</CardTitle>
        <CardDescription>
          L&apos;IA reçoit des données calculées de l&apos;organisation et les transmet au fournisseur configuré ({data.status.configured ? `${data.status.provider}, modèle ${data.status.model}` : "aucun"}).
          Elle propose ; chaque décision reste humaine. Désactivée par défaut.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <AiUnavailable status={data.status} />
        {err && <Alert>{err}</Alert>}
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" className="h-4 w-4" disabled={!data.can_edit} checked={v.enabled} onChange={(x) => setF({ ...v, enabled: x.target.checked })} /> IA activée pour l&apos;organisation
        </label>
        <fieldset className="space-y-1">
          <legend className="text-sm font-medium">Usages autorisés</legend>
          {Object.entries(data.status.uses).map(([k, l]) => (
            <label key={k} className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="h-4 w-4" disabled={!data.can_edit} checked={v.uses.includes(k)}
                     onChange={(x) => setF({ ...v, uses: x.target.checked ? [...v.uses, k] : v.uses.filter((u) => u !== k) })} /> {l}
            </label>
          ))}
        </fieldset>
        <Field label="Accord de l'organisation sur la transmission des données (requis pour activer)" htmlFor="ai-note">
          <textarea id="ai-note" rows={2} className={AREA} disabled={!data.can_edit} value={v.note} onChange={(x) => setF({ ...v, note: x.target.value })} />
        </Field>
        {data.updated_at && <p className="text-xs text-muted-foreground">Dernière modification le {formatDate(data.updated_at)}.</p>}
        {data.can_edit ? <div className="flex justify-end"><Button loading={busy} disabled={!f} onClick={save}>Enregistrer</Button></div>
          : <p className="text-xs text-muted-foreground">Réglages modifiables par les propriétaires et administrateurs.</p>}
      </CardContent>
    </Card>
  );
}
