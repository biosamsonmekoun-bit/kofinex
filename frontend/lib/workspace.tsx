"use client";

/**
 * Contexte de travail partagé par la barre supérieure et les pages : organisation, entreprise, exercice et période.
 * La sélection est mémorisée dans le navigateur (simple confort) et se recale sur l'URL ; les droits restent vérifiés
 * par l'API et la RLS. Aucune valeur n'est inventée : sans entreprise ou sans exercice, la sélection reste vide.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useApiResource } from "@/lib/use-api";
import type { Company, FiscalYear, Organization } from "@/lib/types";
import type { DashboardData, DashPeriod } from "@/lib/dashboard-types";

const KEY = "kofinex.workspace";
const LAST_ORG_KEY = "kofinex.lastOrg";
const MONTHS = ["Janv.", "Févr.", "Mars", "Avr.", "Mai", "Juin", "Juil.", "Août", "Sept.", "Oct.", "Nov.", "Déc."];

interface Stored { orgId?: string | null; companyId?: string | null; fyId?: string | null; period?: string }

function readStored(): Stored {
  try { return JSON.parse(localStorage.getItem(KEY) ?? "{}") as Stored; } catch { return {}; }
}
function writeStored(s: Stored) {
  try { localStorage.setItem(KEY, JSON.stringify(s)); if (s.orgId) localStorage.setItem(LAST_ORG_KEY, s.orgId); } catch { /* ignoré */ }
}

/** Mêmes périodes que l'API (exercice, semestres et trimestres si 12 mois, puis mois) ; l'API reste la référence. */
export function fiscalPeriods(fy: Pick<FiscalYear, "label" | "start_date" | "end_date">): DashPeriod[] {
  const [sy, sm] = fy.start_date.split("-").map(Number);
  const [ey, em] = fy.end_date.split("-").map(Number);
  const months: [number, number][] = [];
  for (let y = sy, m = sm; y < ey || (y === ey && m <= em); m === 12 ? (y++, m = 1) : m++) months.push([y, m]);
  const lab = (a: number, b: number) => {
    const [ya, ma] = months[a - 1]; const [yb, mb] = months[b - 1];
    return ya === yb ? `${MONTHS[ma - 1]} – ${MONTHS[mb - 1]} ${yb}` : `${MONTHS[ma - 1]} ${ya} – ${MONTHS[mb - 1]} ${yb}`;
  };
  const n = months.length;
  const out: DashPeriod[] = [{ key: "year", label: `Exercice ${fy.label}`, from: 1, to: n }];
  if (n === 12) {
    out.push({ key: "s1", label: `S1 · ${lab(1, 6)}`, from: 1, to: 6 }, { key: "s2", label: `S2 · ${lab(7, 12)}`, from: 7, to: 12 });
    for (let q = 1; q <= 4; q++) out.push({ key: `t${q}`, label: `T${q} · ${lab(3 * q - 2, 3 * q)}`, from: 3 * q - 2, to: 3 * q });
  }
  months.forEach(([y, m], i) => out.push({ key: `m${i + 1}`, label: `${MONTHS[m - 1]} ${y}`, from: i + 1, to: i + 1 }));
  return out;
}

interface Workspace {
  orgs: Organization[] | null; org: Organization | null;
  companies: Company[] | null; company: Company | null;
  years: FiscalYear[] | null; fy: FiscalYear | null;
  periods: DashPeriod[]; period: string;
  setOrg: (id: string) => void; setCompany: (id: string) => void; setFy: (id: string) => void; setPeriod: (key: string) => void;
  dashboard: { data: DashboardData | null; error: string | null; loading: boolean; reload: () => Promise<void> };
  reloadOrgs: () => Promise<void>;
}

const Ctx = createContext<Workspace | null>(null);

export function useWorkspace(): Workspace {
  const v = useContext<Workspace | null>(Ctx);
  if (!v) throw new Error("useWorkspace hors de WorkspaceProvider");
  return v;
}

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const params = useParams<{ orgId?: string; companyId?: string; fyId?: string }>();
  const [sel, setSel] = useState<Stored>({});
  const [ready, setReady] = useState(false);

  useEffect(() => { setSel(readStored()); setReady(true); }, []);
  const update = useCallback((patch: Stored) => setSel((s) => { const n = { ...s, ...patch }; writeStored(n); return n; }), []);

  // organisation choisie ailleurs (pages existantes : rememberOrg)
  useEffect(() => {
    const onOrg = (e: Event) => { const id = (e as CustomEvent<string>).detail; setSel((s) => (s.orgId === id ? s : { ...s, orgId: id, companyId: null, fyId: null })); };
    window.addEventListener("kofinex:org", onOrg);
    return () => window.removeEventListener("kofinex:org", onOrg);
  }, []);

  const { data: orgs, reload: reloadOrgs } = useApiResource<Organization[]>("/organizations");
  // entreprise ouverte par l'URL : on recale l'organisation sur la sienne
  const { data: urlCompany } = useApiResource<Company>(params.companyId ? `/companies/${params.companyId}` : null);
  useEffect(() => { if (params.orgId && params.orgId !== sel.orgId) update({ orgId: params.orgId }); }, [params.orgId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (urlCompany && (urlCompany.id !== sel.companyId || urlCompany.organization_id !== sel.orgId))
      update({ orgId: urlCompany.organization_id, companyId: urlCompany.id, fyId: params.fyId ?? (urlCompany.id === sel.companyId ? sel.fyId : null) });
  }, [urlCompany]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (params.fyId && params.fyId !== sel.fyId) update({ fyId: params.fyId }); }, [params.fyId]); // eslint-disable-line react-hooks/exhaustive-deps

  const org = orgs?.find((o) => o.id === sel.orgId) ?? (ready && orgs ? orgs[0] ?? null : null);
  const { data: companies } = useApiResource<Company[]>(org ? `/organizations/${org.id}/companies` : null);
  const company = companies?.find((c) => c.id === sel.companyId) ?? (companies && companies[0]) ?? null;
  const { data: yearsRaw } = useApiResource<FiscalYear[]>(company ? `/companies/${company.id}/fiscal-years` : null);
  const years = useMemo(() => (yearsRaw ? [...yearsRaw].sort((a, b) => b.end_date.localeCompare(a.end_date)) : null), [yearsRaw]);
  const fy = years?.find((y) => y.id === sel.fyId) ?? (years && years[0]) ?? null;
  const periods = useMemo(() => (fy ? fiscalPeriods(fy) : []), [fy]);
  const period = periods.some((p) => p.key === sel.period) ? sel.period! : "year";

  const dash = useApiResource<DashboardData>(company && fy && fy.company_id === company.id
    ? `/companies/${company.id}/fiscal-years/${fy.id}/dashboard?period=${encodeURIComponent(period)}` : null);

  const value: Workspace = {
    orgs, org, companies, company, years, fy, periods, period,
    setOrg: (id) => update({ orgId: id, companyId: null, fyId: null }),
    setCompany: (id) => update({ orgId: org?.id ?? sel.orgId, companyId: id, fyId: null }),
    setFy: (id) => update({ companyId: company?.id ?? sel.companyId, fyId: id }),
    setPeriod: (key) => update({ period: key }),
    dashboard: { data: dash.data, error: dash.error, loading: dash.loading, reload: dash.reload },
    reloadOrgs,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
