"use client";

import { useState } from "react";
import { CheckCircle2, CircleDashed } from "lucide-react";
import { useApiResource } from "@/lib/use-api";
import type { Engagement } from "@/lib/types";
import type { FaOverview } from "@/lib/fa-types";
import { cn } from "@/lib/utils";
import { Alert, Loading } from "@/components/ui/feedback";
import { FaMaterialityPanel } from "./fa-materiality";
import { FaAccountsPanel } from "./fa-accounts";
import { FaSamplesPanel } from "./fa-samples";
import { FaConfirmationsPanel } from "./fa-confirmations";
import { FaMisstatementsPanel } from "./fa-misstatements";

const SECTIONS = [["materiality", "Seuils"], ["accounts", "Comptes et cycles"], ["samples", "Échantillons et tests"],
  ["confirmations", "Circularisations"], ["misstatements", "Anomalies et ajustements"]] as const;
type Section = (typeof SECTIONS)[number][0];

export function FinancialAuditTab({ e }: { e: Engagement }) {
  const [section, setSection] = useState<Section>("materiality");
  const [version, setVersion] = useState(0);
  const { data, error, loading, reload } = useApiResource<FaOverview>(`/engagements/${e.id}/fa?v=${version}`);
  const changed = () => { setVersion((v) => v + 1); void reload(); };

  if (loading && !data) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  return (
    <div className="grid gap-5 lg:grid-cols-[13rem_minmax(0,1fr)]">
      <nav aria-label="Audit financier" className="space-y-4">
        <ul className="space-y-1">
          {SECTIONS.map(([id, label]) => (
            <li key={id}>
              <button onClick={() => setSection(id)} aria-current={section === id ? "page" : undefined}
                      className={cn("w-full rounded-md px-3 py-2 text-left text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                        section === id ? "bg-muted font-medium text-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground")}>
                {label}
              </button>
            </li>
          ))}
        </ul>
        {data && (
          <div className="rounded-lg border bg-card p-3 text-xs shadow-card">
            <p className="mb-2 font-semibold">Conditions d&apos;émission</p>
            <ul className="space-y-1.5">
              {data.checks.map((c) => (
                <li key={c.code} className="flex items-start gap-1.5">
                  {c.passed ? <CheckCircle2 className="mt-px h-3.5 w-3.5 shrink-0 text-success" aria-label="Rempli" />
                    : <CircleDashed className="mt-px h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-label="Non rempli" />}
                  <span>{c.label}{c.detail && <span className="text-muted-foreground"> — {c.detail}</span>}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </nav>
      <section>
        {section === "materiality" && <FaMaterialityPanel e={e} onChanged={changed} />}
        {section === "accounts" && <FaAccountsPanel e={e} onChanged={changed} hasMateriality={!!data?.materiality} />}
        {section === "samples" && <FaSamplesPanel e={e} onChanged={changed} />}
        {section === "confirmations" && <FaConfirmationsPanel e={e} onChanged={changed} />}
        {section === "misstatements" && <FaMisstatementsPanel e={e} onChanged={changed} />}
      </section>
    </div>
  );
}
