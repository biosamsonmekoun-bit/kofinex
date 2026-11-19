"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { personName, type PersonRef } from "@/lib/types";
import { IC_ROLES } from "@/lib/ic-types";
import { formatDate } from "@/lib/utils";
import { IcShell } from "@/components/ic-shell";
import { useIcRefs } from "@/components/ic-forms";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, Badge, Loading } from "@/components/ui/feedback";
import { Field, Select } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

type Member = { id: string; user_id: string; role: string; role_label: string; domain_id: string | null; created_at: string; user: PersonRef | null };
const DOMAIN_ROLES = ["domain_owner", "process_owner"];
const ENTITY_ROLES = ["ic_manager", "daf", "observer"];

const PERMISSIONS: [string, string][] = [
  ["Administrateur de l'organisation, responsable du contrôle interne, DAF", "Pilotent le dispositif : rôles, domaines, référentiels, correspondances, tout le registre ; lancent les évaluations dans les missions où ils sont membres."],
  ["Responsable de domaine, responsable de processus", "Gèrent processus, risques, contrôles et liens de leur domaine ; supervisent les exécutions de ses contrôles."],
  ["Exécutant du contrôle", "Documente les exécutions (preuve facultative) des contrôles qui lui sont attribués ou de son domaine ; ne supervise jamais sa propre exécution."],
  ["Superviseur", "Approuve ou rejette les exécutions documentées par une autre personne."],
  ["Auditeur interne, auditeur financier", "Rôles de mission (lot 6) : testent, revoient et décident dans leur dossier ; lisent le dispositif de l'entité auditée sans modifier ses données opérationnelles."],
  ["Audité", "Ne voit que les déficiences communiquées et y répond ; aucun accès aux tests ni aux dossiers."],
  ["Observateur", "Lecture seule du dispositif de l'entité."],
];

export default function IcRolesPage() {
  const { companyId: cid } = useParams<{ companyId: string }>();
  const refs = useIcRefs(cid);
  const { data, error, reload } = useApiResource<Member[]>(`/companies/${cid}/ic/members`);
  return (
    <IcShell cid={cid} title="Rôles du contrôle interne" description="Rôles propres à l'entité, éventuellement limités à un domaine. Les droits sont appliqués par l'API et par la base de données (RLS et déclencheurs).">
      {(access) => (
        <div className="space-y-5">
          {error && <Alert>{error}</Alert>}
          <Card>
            <CardHeader><CardTitle>Attributions</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {!data ? <Loading /> : data.length === 0 ? <p className="text-sm text-muted-foreground">Aucun rôle attribué.</p> : (
                <Table>
                  <THead><tr><TH>Personne</TH><TH>Rôle</TH><TH>Domaine</TH><TH>Depuis</TH><TH /></tr></THead>
                  <TBody>{data.map((m) => (
                    <TR key={m.id}>
                      <TD>{personName(m.user)}</TD><TD><Badge>{m.role_label}</Badge></TD>
                      <TD>{m.domain_id ? refs.domains.find((d) => d.id === m.domain_id)?.name ?? "—" : "Toute l'entité"}</TD>
                      <TD>{formatDate(m.created_at)}</TD>
                      <TD className="text-right">{access.is_admin && <Revoke cid={cid} id={m.id} onDone={reload} />}</TD>
                    </TR>
                  ))}</TBody>
                </Table>
              )}
              {access.is_admin && <Grant cid={cid} domains={refs.domains} onDone={reload} />}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Matrice des permissions</CardTitle><CardDescription>Résumé des règles appliquées ; la séparation préparateur / réviseur et exécutant / superviseur est contrôlée par la base.</CardDescription></CardHeader>
            <CardContent>
              <Table><THead><tr><TH>Rôle</TH><TH>Actions</TH></tr></THead>
                <TBody>{PERMISSIONS.map(([r, a]) => <TR key={r}><TD className="font-medium">{r}</TD><TD>{a}</TD></TR>)}</TBody></Table>
            </CardContent>
          </Card>
        </div>
      )}
    </IcShell>
  );
}

function Revoke({ cid, id, onDone }: { cid: string; id: string; onDone: () => void }) {
  const [err, setErr] = useState<string | null>(null);
  return (
    <>
      {err && <span className="block text-xs text-destructive">{err}</span>}
      <Button size="sm" variant="ghost" onClick={async () => { setErr(null); try { await api.del(`/companies/${cid}/ic/members/${id}`); onDone(); } catch (x) { setErr(errorMessage(x)); } }}>Retirer</Button>
    </>
  );
}

function Grant({ cid, domains, onDone }: { cid: string; domains: { id: string; code: string; name: string }[]; onDone: () => void }) {
  const { data: people } = useApiResource<PersonRef[]>(`/companies/${cid}/ic/candidates`);
  const [f, setF] = useState({ user_id: "", role: "control_performer", domain_id: "" });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function save(ev: React.FormEvent) {
    ev.preventDefault(); setBusy(true); setErr(null);
    try { await api.post(`/companies/${cid}/ic/members`, { ...f, domain_id: f.domain_id || null }); setF({ ...f, user_id: "" }); onDone(); }
    catch (x) { setErr(errorMessage(x)); } finally { setBusy(false); }
  }
  return (
    <form onSubmit={save} className="space-y-2 rounded-md border p-3">
      {err && <Alert>{err}</Alert>}
      <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_16rem_16rem_auto] sm:items-end">
        <Field label="Membre de l'organisation" htmlFor="g-u" required><Select id="g-u" required value={f.user_id} onChange={(x) => setF({ ...f, user_id: x.target.value })}>
          <option value="">—</option>{people?.map((p) => <option key={p.id} value={p.id}>{personName(p)}</option>)}</Select></Field>
        <Field label="Rôle" htmlFor="g-r"><Select id="g-r" value={f.role} onChange={(x) => setF({ ...f, role: x.target.value, domain_id: ENTITY_ROLES.includes(x.target.value) ? "" : f.domain_id })}>
          {Object.entries(IC_ROLES).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select></Field>
        <Field label="Domaine" htmlFor="g-d" required={DOMAIN_ROLES.includes(f.role)}><Select id="g-d" value={f.domain_id} disabled={ENTITY_ROLES.includes(f.role)} required={DOMAIN_ROLES.includes(f.role)}
          onChange={(x) => setF({ ...f, domain_id: x.target.value })}><option value="">{ENTITY_ROLES.includes(f.role) ? "Toute l'entité" : "—"}</option>
          {domains.map((d) => <option key={d.id} value={d.id}>{d.code} — {d.name}</option>)}</Select></Field>
        <Button type="submit" loading={busy}>Attribuer</Button>
      </div>
    </form>
  );
}
