"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Download, Plus } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { VERSION_STATUS, type FrameworkVersion, type Profile } from "@/lib/types";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Loading, PageHeader } from "@/components/ui/feedback";
import { Field, Input } from "@/components/ui/form";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

interface Framework {
  id: string; code: string; name: string; description: string | null;
  published_versions: number; versions: number; scope: string | null;
  required_statements: string[]; profile_notes: string[];
}


function Versions({ code }: { code: string }) {
  const router = useRouter();
  const { data, error, loading } = useApiResource<FrameworkVersion[]>(`/frameworks/${code}/versions`);
  if (loading && !data) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  if (!data || data.length === 0) {
    return <EmptyState title="Aucune version chargée"
                       description="Le plan de comptes et les correspondances officielles doivent être chargés par un administrateur de la plateforme." />;
  }
  return (
    <Table>
      <THead><tr><TH>Version</TH><TH>Application</TH><TH>Source</TH><TH>Comptes</TH><TH>Correspondances</TH><TH>Statut</TH></tr></THead>
      <TBody>
        {data.map((v) => (
          <TR key={v.id} className="cursor-pointer" onClick={() => router.push(`/referentiels/versions/${v.id}`)}>
            <TD><Link href={`/referentiels/versions/${v.id}`} className="font-medium hover:underline">{v.version_label}</Link></TD>
            <TD className="whitespace-nowrap">{formatDate(v.effective_from)} → {v.effective_to ? formatDate(v.effective_to) : "en vigueur"}</TD>
            <TD className="max-w-sm truncate text-muted-foreground" title={v.source_reference}>{v.source_reference}</TD>
            <TD className="tabular-nums">{v.account_count}</TD>
            <TD className="tabular-nums">{v.mapping_count}</TD>
            <TD><Badge tone={VERSION_STATUS[v.status].tone}>{VERSION_STATUS[v.status].label}</Badge></TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}

function NewVersionForm({ code, onCreated }: { code: string; onCreated: (v: FrameworkVersion) => void }) {
  const [form, setForm] = useState({ version_label: "", effective_from: "", effective_to: "", source_reference: "", source_url: "" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      onCreated(await api.post<FrameworkVersion>(`/frameworks/${code}/versions`, {
        version_label: form.version_label.trim(), effective_from: form.effective_from,
        effective_to: form.effective_to || null, source_reference: form.source_reference.trim(),
        source_url: form.source_url.trim() || null,
      }));
    } catch (err) {
      setError(errorMessage(err));
      setSaving(false);
    }
  }
  return (
    <form onSubmit={submit} className="space-y-4">
      {error && <Alert>{error}</Alert>}
      <Field label="Libellé de la version" htmlFor="v-label" required>
        <Input id="v-label" value={form.version_label} onChange={(e) => setForm({ ...form, version_label: e.target.value })} />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Entrée en vigueur" htmlFor="v-from" required>
          <Input id="v-from" type="date" value={form.effective_from} onChange={(e) => setForm({ ...form, effective_from: e.target.value })} />
        </Field>
        <Field label="Fin d'application" htmlFor="v-to" hint="Vide si toujours en vigueur.">
          <Input id="v-to" type="date" value={form.effective_to} onChange={(e) => setForm({ ...form, effective_to: e.target.value })} />
        </Field>
      </div>
      <Field label="Référence du texte officiel" htmlFor="v-src" required
             hint="Acte, date d'adoption, publication au Journal officiel de l'OHADA…">
        <textarea id="v-src" rows={3} value={form.source_reference}
                  onChange={(e) => setForm({ ...form, source_reference: e.target.value })}
                  className="w-full rounded-md border border-input bg-card px-3 py-2 text-sm" />
      </Field>
      <Field label="Lien vers la source (facultatif)" htmlFor="v-url">
        <Input id="v-url" type="url" value={form.source_url} onChange={(e) => setForm({ ...form, source_url: e.target.value })} />
      </Field>
      <div className="flex justify-end">
        <Button type="submit" loading={saving}
                disabled={!form.version_label.trim() || !form.effective_from || form.source_reference.trim().length < 10}>
          Créer le brouillon
        </Button>
      </div>
    </form>
  );
}

export default function ReferentielsPage() {
  const router = useRouter();
  const { data: frameworks, error, loading } = useApiResource<Framework[]>("/frameworks");
  const { data: me } = useApiResource<Profile>("/me");
  const [creating, setCreating] = useState<string | null>(null);
  const [dlError, setDlError] = useState<string | null>(null);
  const isAdmin = !!me?.is_platform_admin;

  async function template(kind: "chart" | "mappings" | "structure" | "concepts") {
    const names = { chart: "plan-de-comptes", mappings: "correspondances", structure: "structure-des-etats", concepts: "concepts" };
    try {
      await api.download(`/framework-templates/${kind}.csv`, `modele-${names[kind]}.csv`);
    } catch (err) {
      setDlError(errorMessage(err));
    }
  }

  return (
    <>
      <PageHeader
        title="Référentiels comptables"
        description="Versions datées et sourcées des plans de comptes et des correspondances vers les états financiers. Une version publiée est figée."
        actions={isAdmin && (
          <>
            <Button variant="outline" size="sm" onClick={() => template("chart")}><Download className="h-4 w-4" /> Modèle plan de comptes</Button>
            <Button variant="outline" size="sm" onClick={() => template("mappings")}><Download className="h-4 w-4" /> Modèle correspondances</Button>
            <Button variant="outline" size="sm" onClick={() => template("structure")}><Download className="h-4 w-4" /> Modèle structure</Button>
            <Button variant="outline" size="sm" onClick={() => template("concepts")}><Download className="h-4 w-4" /> Modèle concepts</Button>
          </>
        )}
      />
      {dlError && <Alert className="mb-4">{dlError}</Alert>}
      {loading && !frameworks && <Loading />}
      {error && <Alert>{error}</Alert>}
      <div className="space-y-6">
        {frameworks?.map((fw) => (
          <Card key={fw.code}>
            <CardHeader className="flex-row items-start justify-between gap-4">
              <div>
                <CardTitle>{fw.name}</CardTitle>
                <CardDescription>{fw.scope ?? fw.description}</CardDescription>
                {fw.required_statements.length > 0 && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    Publication conditionnée au chargement des correspondances : {fw.required_statements.join(", ")}.
                  </p>
                )}
                {fw.profile_notes.map((n) => <p key={n} className="mt-1 text-xs text-muted-foreground">{n}</p>)}
              </div>
              {isAdmin && <Button size="sm" onClick={() => setCreating(fw.code)}><Plus className="h-4 w-4" /> Nouvelle version</Button>}
            </CardHeader>
            <CardContent><Versions code={fw.code} /></CardContent>
          </Card>
        ))}
      </div>
      <Dialog open={!!creating} onClose={() => setCreating(null)} title="Nouvelle version de référentiel"
              description="La version est créée en brouillon ; chargez ensuite le plan de comptes et les correspondances transcrits du texte officiel.">
        {creating && <NewVersionForm code={creating} onCreated={(v) => router.push(`/referentiels/versions/${v.id}`)} />}
      </Dialog>
    </>
  );
}
