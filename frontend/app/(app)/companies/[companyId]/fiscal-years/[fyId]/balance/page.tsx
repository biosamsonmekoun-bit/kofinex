"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ChevronLeft, Download } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { AMOUNT_FIELDS, type Company, type FiscalYear } from "@/lib/types";
import { cn, formatAmount, formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Alert, EmptyState, Loading, PageHeader } from "@/components/ui/feedback";
import { Input } from "@/components/ui/form";

interface Entry {
  account_number: string;
  account_label: string | null;
  opening_debit: string; opening_credit: string; movement_debit: string; movement_credit: string;
  closing_debit: string; closing_credit: string;
  source_row: number | null; source_page: number | null; closing_computed: boolean; ocr_confidence: string | null;
}
interface TrialBalance {
  import: { id: string; validated_at: string; document_id: string; filename: string | null; method: string | null } | null;
  items: Entry[];
  total_count: number;
  totals: Record<string, string> | null;
}

const PAGE = 200;
const HEADERS = ["Ouverture débit", "Ouverture crédit", "Mvts débit", "Mvts crédit", "Solde débiteur", "Solde créditeur"];

export default function BalancePage() {
  const { companyId, fyId } = useParams<{ companyId: string; fyId: string }>();
  const { data: company } = useApiResource<Company>(`/companies/${companyId}`);
  const { data: years } = useApiResource<FiscalYear[]>(`/companies/${companyId}/fiscal-years`);
  const fy = years?.find((y) => y.id === fyId);
  const [cls, setCls] = useState<string>("");
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [offset, setOffset] = useState(0);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => { setDebounced(q); setOffset(0); }, 300);
    return () => clearTimeout(t);
  }, [q]);

  const params = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
  if (cls) params.set("account_class", cls);
  if (debounced.trim()) params.set("q", debounced.trim());
  const { data, error, loading } = useApiResource<TrialBalance>(
    `/companies/${companyId}/fiscal-years/${fyId}/trial-balance?${params.toString()}`);

  async function downloadOriginal() {
    try {
      const { url } = await api.get<{ url: string }>(`/companies/${companyId}/documents/${data!.import!.document_id}/download`);
      window.open(url, "_blank", "noopener");
    } catch (err) {
      setActionError(errorMessage(err));
    }
  }

  return (
    <>
      <Link href={`/companies/${companyId}`} className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ChevronLeft className="h-4 w-4" /> {company?.name ?? "Entreprise"}
      </Link>
      <PageHeader
        title={`Balance générale${fy ? ` — exercice ${fy.label}` : ""}`}
        description={data?.import
          ? <>Import validé le {formatDate(data.import.validated_at)} · fichier « {data.import.filename ?? "—"} » · montants en {company?.currency ?? ""}</>
          : undefined}
        actions={data?.import && (
          <>
            <Button variant="outline" size="sm" onClick={downloadOriginal}><Download className="h-4 w-4" /> Fichier original</Button>
            <Button asChild variant="outline" size="sm">
              <Link href={`/companies/${companyId}/imports/${data.import.id}`}>Détail de l&apos;import</Link>
            </Button>
          </>
        )}
      />
      {actionError && <Alert className="mb-4">{actionError}</Alert>}

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="flex overflow-hidden rounded-md border" role="group" aria-label="Filtrer par classe">
          {["", "1", "2", "3", "4", "5", "6", "7", "8", "9"].map((c) => (
            <button key={c || "all"} onClick={() => { setCls(c); setOffset(0); }}
                    aria-pressed={cls === c}
                    className={cn("px-3 py-1.5 text-sm transition-colors", cls === c ? "bg-primary text-primary-foreground" : "bg-card hover:bg-muted")}>
              {c ? `Classe ${c}` : "Toutes"}
            </button>
          ))}
        </div>
        <Input className="w-64" placeholder="N° de compte ou libellé…" value={q} onChange={(e) => setQ(e.target.value)}
               aria-label="Rechercher un compte" />
      </div>

      {loading && !data && <Loading />}
      {error && <Alert>{error}</Alert>}
      {data && !data.import && (
        <EmptyState title="Aucune balance validée pour cet exercice"
                    description="Déposez et validez une balance depuis l'onglet « Importations » de l'entreprise."
                    action={<Button asChild><Link href={`/companies/${companyId}`}>Aller à l&apos;entreprise</Link></Button>} />
      )}
      {data?.import && (
        <>
          <div className="overflow-x-auto rounded-lg border bg-card">
            <table className="w-full text-sm">
              <thead className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 text-left">Compte</th>
                  <th className="px-3 py-2 text-left">Libellé</th>
                  {HEADERS.map((h) => <th key={h} className="whitespace-nowrap px-3 py-2 text-right">{h}</th>)}
                </tr>
              </thead>
              <tbody className="divide-y">
                {data.items.map((e) => (
                  <tr key={e.account_number} className="hover:bg-muted/40">
                    <td className="px-3 py-2 font-mono">{e.account_number}</td>
                    <td className="max-w-xs truncate px-3 py-2" title={e.account_label ?? ""}>
                      {e.account_label}
                      {e.ocr_confidence && Number(e.ocr_confidence) < 80 && (
                        <span className="ml-1 text-xs text-warning-strong" title="Lu par OCR avec une confiance faible">(OCR)</span>
                      )}
                    </td>
                    {AMOUNT_FIELDS.map((f) => (
                      <td key={f} className={cn("whitespace-nowrap px-3 py-2 text-right tabular-nums",
                        f.startsWith("closing") && "font-medium")}
                          title={f.startsWith("closing") && e.closing_computed ? "Solde calculé (ouverture + mouvements)" : undefined}>
                        {formatAmount(e[f], { blankZero: true })}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
              {data.totals && (
                <tfoot className="border-t-2 bg-muted/40 font-semibold">
                  <tr>
                    <td className="px-3 py-2" colSpan={2}>
                      Total {cls ? `classe ${cls}` : "général"}{debounced ? " (filtré)" : ""} — {data.total_count} compte(s)
                    </td>
                    {AMOUNT_FIELDS.map((f) => (
                      <td key={f} className="whitespace-nowrap px-3 py-2 text-right tabular-nums">{formatAmount(data.totals![f])}</td>
                    ))}
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
          {data.total_count > PAGE && (
            <div className="mt-3 flex items-center justify-between text-sm text-muted-foreground">
              <span>{offset + 1}–{Math.min(offset + PAGE, data.total_count)} sur {data.total_count}</span>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" disabled={offset === 0} onClick={() => setOffset(offset - PAGE)}>Précédent</Button>
                <Button size="sm" variant="outline" disabled={offset + PAGE >= data.total_count} onClick={() => setOffset(offset + PAGE)}>Suivant</Button>
              </div>
            </div>
          )}
        </>
      )}
    </>
  );
}
