"use client";

import { useState } from "react";
import type { Engagement } from "@/lib/types";
import { cn } from "@/lib/utils";
import { LedgerAccounts, LedgerAnalyticsPanel, LedgerBrowser, LedgerJournals } from "@/components/ledger-views";

const SUB = [["lines", "Consultation"], ["accounts", "Comptes"], ["journals", "Centralisation"], ["analytics", "Analyses"]] as const;

export function LedgerTab({ e }: { e: Engagement }) {
  const [tab, setTab] = useState<(typeof SUB)[number][0]>("lines");
  const [account, setAccount] = useState<string | undefined>();
  const base = `/engagements/${e.id}/ledger`;
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Grand livre validé de l&apos;exercice audité{e.fiscal_year_label ? ` (${e.fiscal_year_label})` : ""}, en lecture seule. Pour tester des écritures,
        créez une population « grand livre » dans l&apos;onglet Audit financier.
      </p>
      <div role="tablist" className="flex gap-1">
        {SUB.map(([id, label]) => (
          <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}
                  className={cn("rounded-md px-3 py-1.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    tab === id ? "bg-muted font-medium text-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground")}>{label}</button>
        ))}
      </div>
      {tab === "lines" && <LedgerBrowser key={account ?? ""} base={base} initialAccount={account} />}
      {tab === "accounts" && <LedgerAccounts base={base} onOpen={(a) => { setAccount(a); setTab("lines"); }} />}
      {tab === "journals" && <LedgerJournals base={base} />}
      {tab === "analytics" && <LedgerAnalyticsPanel base={base} />}
    </div>
  );
}
