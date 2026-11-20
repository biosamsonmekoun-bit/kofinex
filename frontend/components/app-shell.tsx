"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  BarChart3, Bell, ClipboardCheck, ClipboardList, ChevronDown, CircleDollarSign, Cpu, FileText, Gauge, House, Landmark, LogOut,
  Menu, Network, Package, Receipt, Settings, ShieldCheck, ShoppingBag, ShoppingCart, UserRound, Wallet, X,
} from "lucide-react";
import { Logo } from "@/components/brand";
import { ThemeToggle } from "@/components/theme-toggle";
import { getSupabaseBrowser } from "@/lib/supabase/client";
import { useApiResource } from "@/lib/use-api";
import { WorkspaceProvider, useWorkspace } from "@/lib/workspace";
import { actionableCount } from "@/lib/dashboard-types";
import { ORG_ROLE_LABELS, type Profile } from "@/lib/types";
import { Alert, Badge } from "@/components/ui/feedback";
import { cn } from "@/lib/utils";

const LAST_ORG_KEY = "kofinex.lastOrg";

export function rememberOrg(orgId: string) {
  try { localStorage.setItem(LAST_ORG_KEY, orgId); } catch { /* stockage indisponible */ }
  window.dispatchEvent(new CustomEvent<string>("kofinex:org", { detail: orgId }));
}

type Sub = { label: string; href: string | null; hint?: string; exact?: boolean; also?: string | null };
type Item = { key: string; label: string; icon: React.ElementType; href?: string; subs?: Sub[]; unavailable?: boolean };

const UNAVAILABLE = "Module non disponible dans cette version";

function useNav(): Item[] {
  const { org, company, fy } = useWorkspace();
  const { data: me } = useApiResource<Profile>("/me");
  const isManager = org?.my_role === "owner" || org?.my_role === "admin";
  const o = org ? `/organizations/${org.id}` : null;
  const c = company ? `/companies/${company.id}` : null;
  const f = c && fy ? `${c}/fiscal-years/${fy.id}` : null;
  const needCo = "Sélectionnez une entreprise";
  const needFy = "Sélectionnez un exercice";
  const needOrg = "Sélectionnez une organisation";
  const off = (key: string, label: string, icon: React.ElementType): Item => ({ key, label, icon, unavailable: true });
  return [
    { key: "dashboard", label: "Tableau de bord", icon: House, href: "/tableau-de-bord" },
    { key: "compta", label: "Comptabilité", icon: ClipboardList, subs: [
      { label: "Nouvelle écriture", href: c && `${c}/comptabilite/nouvelle`, hint: needCo },
      { label: "Écritures : saisie, validation, historique", href: c && `${c}/comptabilite`, hint: needCo, exact: true, also: c && `${c}/comptabilite/ecritures` },
      { label: "Grand livre", href: c && `${c}/comptabilite/grand-livre`, hint: needCo },
      { label: "Balance", href: c && `${c}/comptabilite/balance`, hint: needCo },
      { label: "Lettrage", href: c && `${c}/comptabilite/lettrage`, hint: needCo },
      { label: "Journaux", href: c && `${c}/comptabilite/journaux`, hint: needCo },
      { label: "Plan comptable", href: c && `${c}/comptabilite/plan-comptable`, hint: needCo },
      { label: "Plan tiers", href: c && `${c}/comptabilite/tiers`, hint: needCo },
      { label: "Paramètres comptables", href: c && `${c}/comptabilite/parametres`, hint: needCo },
      { label: "Entreprises", href: o && `${o}/companies`, hint: needOrg },
      { label: "Entreprise et exercices", href: c, hint: needCo, exact: true },
      { label: "Balance importée", href: f && `${f}/balance`, hint: needFy },
      { label: "Grand livre importé", href: c && `${c}/grand-livre`, hint: needCo },
      { label: "Référentiels comptables", href: "/referentiels" },
    ] },
    off("achats", "Achats", ShoppingCart),
    off("ventes", "Ventes", ShoppingBag),
    off("tresorerie", "Trésorerie", CircleDollarSign),
    off("stocks", "Stocks", Package),
    off("immo", "Immobilisations", Landmark),
    off("paie", "Paie", Wallet),
    off("fisc", "Fiscalité", Receipt),
    { key: "analyse", label: "Analyse financière", icon: BarChart3, subs: [
      { label: "Analyse de l'exercice", href: f && `${f}/analysis`, hint: needFy },
      { label: "Analyse pluriannuelle", href: c && `${c}/multi-year`, hint: needCo },
      { label: "Formules", href: "/formules" },
    ] },
    { key: "gestion", label: "Contrôle de gestion", icon: Gauge, subs: [
      { label: "Budgets, coûts et pilotage", href: c && `${c}/gestion`, hint: needCo },
    ] },
    { key: "audit", label: "Audit financier", icon: ClipboardCheck, subs: [
      { label: "Missions", href: o && `${o}/missions`, hint: needOrg },
      { label: "Méthodologies", href: "/methodologies" },
    ] },
    { key: "ci", label: "Contrôle interne", icon: ShieldCheck, subs: [
      { label: "Vue de l'organisation", href: o && `${o}/controle-interne`, hint: needOrg },
      { label: "Contrôle interne de l'entreprise", href: c && `${c}/controle-interne`, hint: needCo },
      { label: "Cartographie des risques", href: c && `${c}/cartographie`, hint: needCo },
      { label: "Plan d'audit interne", href: o && `${o}/plan-audit`, hint: needOrg },
      { label: "Suivi des recommandations", href: o && `${o}/suivi-recommandations`, hint: needOrg },
    ] },
    { key: "ai", label: "KOFINEX AI", icon: Cpu, subs: [
      { label: "Assistant financier", href: c && `${c}/assistant`, hint: needCo },
    ] },
    { key: "reporting", label: "Reporting", icon: FileText, subs: [
      { label: "Rapports de l'entreprise", href: c && `${c}/rapports`, hint: needCo },
      { label: "Modèles de rapports", href: o && `${o}/modeles-rapports`, hint: needOrg },
    ] },
    { key: "settings", label: "Paramètres", icon: Settings, subs: [
      { label: "Organisation", href: o && `${o}/settings`, hint: needOrg },
      { label: "Membres", href: o && `${o}/members`, hint: needOrg },
      { label: "Abonnement", href: o && `${o}/abonnement`, hint: needOrg },
      ...(me?.is_platform_admin ? [{ label: "Offres et tarifs (plateforme)", href: "/admin/offres" }] : []),
      ...(isManager ? [{ label: "Journal d'audit", href: o && `${o}/audit`, hint: needOrg }] : []),
      { label: "Organisations", href: "/organizations" },
      { label: "Mon profil", href: "/profile" },
    ] },
  ];
}

const isUnder = (pathname: string, href: string | null) => !!href && (pathname === href || pathname.startsWith(`${href}/`));
const subActive = (pathname: string, s: Sub) =>
  s.exact ? !!s.href && (pathname === s.href || (!!s.also && isUnder(pathname, s.also))) : isUnder(pathname, s.href);

function NavItem({ item, onNavigate }: { item: Item; onNavigate: () => void }) {
  const pathname = usePathname();
  const subs = item.subs ?? [];
  const activeSub = subs.some((s) => subActive(pathname, s));
  const active = item.href ? isUnder(pathname, item.href) : false;
  const [open, setOpen] = useState(activeSub);
  useEffect(() => { if (activeSub) setOpen(true); }, [activeSub]);
  const base = "group flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-[14px] font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
  const tone = active ? "bg-primary text-primary-foreground shadow-sm"
    : activeSub ? "text-sidebar-foreground bg-sidebar-hover" : "text-sidebar-foreground/90 hover:bg-sidebar-hover hover:text-sidebar-foreground";
  const Icon = item.icon;

  if (item.href) {
    return (
      <Link href={item.href} onClick={onNavigate} aria-current={active ? "page" : undefined} className={cn(base, tone)}>
        <Icon className="h-[18px] w-[18px] shrink-0" aria-hidden /> <span className="flex-1 truncate text-left">{item.label}</span>
      </Link>
    );
  }
  const id = `nav-${item.key}`;
  return (
    <div>
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} aria-controls={id} className={cn(base, tone)}>
        <Icon className="h-[18px] w-[18px] shrink-0" aria-hidden />
        <span className="flex-1 truncate text-left">{item.label}</span>
        <ChevronDown className={cn("h-4 w-4 shrink-0 opacity-80 transition-transform", open && "rotate-180")} aria-hidden />
      </button>
      {open && (
        <ul id={id} className="mb-1 ml-[22px] mt-0.5 space-y-0.5 border-l border-sidebar-border pl-3">
          {item.unavailable && (
            <li className="flex items-center gap-2 px-2 py-1.5 text-[12.5px] text-sidebar-muted">
              <Badge tone="neutral" className="bg-sidebar-hover text-sidebar-muted">Bientôt</Badge> {UNAVAILABLE}
            </li>
          )}
          {subs.map((s) => (
            <li key={s.label}>
              {s.href ? (
                <Link href={s.href} onClick={onNavigate} aria-current={subActive(pathname, s) ? "page" : undefined}
                      className={cn("block truncate rounded px-2 py-1.5 text-[13px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                        subActive(pathname, s) ? "bg-primary/90 font-medium text-primary-foreground" : "text-sidebar-muted hover:bg-sidebar-hover hover:text-sidebar-foreground")}>
                  {s.label}
                </Link>
              ) : (
                <span className="block truncate px-2 py-1.5 text-[13px] text-sidebar-muted/60" title={s.hint}>{s.label} <span className="text-[11px]">· {s.hint}</span></span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Sidebar({ onNavigate }: { onNavigate: () => void }) {
  const items = useNav();
  const settings = items[items.length - 1];
  return (
    <nav className="flex h-full flex-col overflow-y-auto bg-sidebar px-4 pb-6 pt-6 text-sidebar-foreground" aria-label="Navigation principale">
      <Link href="/tableau-de-bord" onClick={onNavigate} className="mb-7 rounded-md px-2 text-sidebar-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <Logo withSignature />
      </Link>
      <div className="space-y-0.5">
        {items.slice(0, -1).map((it) => <NavItem key={it.key} item={it} onNavigate={onNavigate} />)}
      </div>
      <div className="mt-4 border-t border-sidebar-border pt-4">
        <NavItem item={settings} onNavigate={onNavigate} />
      </div>
    </nav>
  );
}

/** Sélecteur de la barre supérieure (libellé au-dessus, liste native : accessible au clavier et sans dépendance). */
function TopSelect({ label, value, onChange, disabled, children, className }: {
  label: string; value: string; onChange: (v: string) => void; disabled?: boolean; children: React.ReactNode; className?: string;
}) {
  return (
    <label className={cn("flex min-w-0 flex-col gap-1", className)}>
      <span className="text-[12px] font-medium text-foreground/80">{label}</span>
      <span className="relative">
        <select value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled}
                className="h-9 w-full min-w-0 appearance-none truncate rounded-md border bg-card pl-3 pr-8 text-[13px] font-semibold text-foreground shadow-sm transition-colors hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60">
          {children}
        </select>
        <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-foreground/70" aria-hidden />
      </span>
    </label>
  );
}

function usePopover() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDown); document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
  }, [open]);
  return { open, setOpen, ref };
}

const STATE_TONE = { todo: "text-warning-strong", progress: "text-primary", done: "text-success-strong", none: "text-muted-foreground" } as const;

function Notifications() {
  const { dashboard, company } = useWorkspace();
  const n = actionableCount(dashboard.data);
  const { open, setOpen, ref } = usePopover();
  return (
    <div className="relative" ref={ref}>
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} aria-haspopup="dialog"
              aria-label={n ? `Notifications : ${n} alerte(s) à traiter` : "Notifications"}
              className="relative rounded-full p-2 text-foreground transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <Bell className="h-[22px] w-[22px]" aria-hidden />
        {n > 0 && (
          <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-bold leading-none text-destructive-foreground ring-2 ring-card">
            {n > 99 ? "99+" : n}
          </span>
        )}
      </button>
      {open && (
        <div role="dialog" aria-label="Alertes" className="absolute right-0 top-11 z-40 w-80 rounded-lg border bg-popover p-3 text-popover-foreground shadow-lg">
          <p className="mb-2 text-sm font-semibold">Alertes {company ? `· ${company.name}` : ""}</p>
          {!dashboard.data ? (
            <p className="text-sm text-muted-foreground">{company ? "Aucune donnée d'exercice disponible." : "Sélectionnez une entreprise."}</p>
          ) : (
            <ul className="space-y-2">
              {dashboard.data.alerts.map((a) => (
                <li key={a.key} className="text-sm">
                  <span className="font-medium">{a.title}</span>
                  <span className={cn("block text-xs", STATE_TONE[a.state])}>{a.detail}</span>
                </li>
              ))}
            </ul>
          )}
          <Link href="/tableau-de-bord" onClick={() => setOpen(false)} className="mt-3 block text-sm font-medium text-link hover:underline">Ouvrir le tableau de bord</Link>
        </div>
      )}
    </div>
  );
}

function AccountMenu({ onSignOut }: { onSignOut: () => void }) {
  const { org } = useWorkspace();
  const { data: me } = useApiResource<Profile>("/me");
  const [email, setEmail] = useState("");
  useEffect(() => { getSupabaseBrowser().auth.getUser().then(({ data }) => setEmail(data.user?.email ?? "")); }, []);
  const name = me?.full_name || me?.email || email;
  const initials = (me?.full_name ? me.full_name.split(/\s+/).map((w) => w[0]).slice(0, 2).join("") : (name || "?").slice(0, 2)).toUpperCase();
  const { open, setOpen, ref } = usePopover();
  return (
    <div className="relative" ref={ref}>
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} aria-haspopup="menu"
              className="flex items-center gap-2 rounded-full py-1 pl-1 pr-2 text-sm font-semibold text-foreground transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary text-[13px] font-semibold text-primary-foreground" aria-hidden>{initials}</span>
        <span className="hidden max-w-[140px] truncate xl:inline">{org?.my_role ? ORG_ROLE_LABELS[org.my_role] : name}</span>
        <ChevronDown className="h-4 w-4" aria-hidden />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 top-12 z-40 w-64 rounded-lg border bg-popover p-2 text-popover-foreground shadow-lg">
          <div className="border-b px-2 pb-2">
            <p className="truncate text-sm font-semibold">{name}</p>
            {org && <p className="truncate text-xs text-muted-foreground">{org.name}{org.my_role ? ` · ${ORG_ROLE_LABELS[org.my_role]}` : ""}</p>}
          </div>
          <Link role="menuitem" href="/profile" onClick={() => setOpen(false)} className="mt-1 flex items-center gap-2 rounded px-2 py-2 text-sm hover:bg-muted"><UserRound className="h-4 w-4" aria-hidden /> Mon profil</Link>
          <Link role="menuitem" href="/organizations" onClick={() => setOpen(false)} className="flex items-center gap-2 rounded px-2 py-2 text-sm hover:bg-muted"><Network className="h-4 w-4" aria-hidden /> Organisations</Link>
          <div className="px-2 py-2"><p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Affichage</p><ThemeToggle className="w-full" /></div>
          <button role="menuitem" type="button" onClick={onSignOut} className="flex w-full items-center gap-2 rounded px-2 py-2 text-sm text-destructive-strong hover:bg-muted"><LogOut className="h-4 w-4" aria-hidden /> Se déconnecter</button>
        </div>
      )}
    </div>
  );
}

function TopBar({ onSignOut }: { onSignOut: () => void }) {
  const ws = useWorkspace();
  return (
    <header className="sticky top-0 z-20 flex flex-wrap items-end gap-x-4 gap-y-2 border-b bg-card/90 px-4 py-3 backdrop-blur supports-[backdrop-filter]:bg-card/80 sm:px-6 lg:px-8">
      {ws.orgs && ws.orgs.length > 1 && (
        <TopSelect label="Organisation" value={ws.org?.id ?? ""} onChange={ws.setOrg} className="w-44 max-md:hidden">
          {ws.orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
        </TopSelect>
      )}
      <TopSelect label="Entreprise" value={ws.company?.id ?? ""} onChange={ws.setCompany} disabled={!ws.companies?.length} className="w-52">
        {!ws.companies?.length && <option value="">{ws.org ? "Aucune entreprise" : "Aucune organisation"}</option>}
        {ws.companies?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
      </TopSelect>
      <TopSelect label="Exercice" value={ws.fy?.id ?? ""} onChange={ws.setFy} disabled={!ws.years?.length} className="w-32">
        {!ws.years?.length && <option value="">Aucun</option>}
        {ws.years?.map((y) => <option key={y.id} value={y.id}>{y.label}</option>)}
      </TopSelect>
      <TopSelect label="Période" value={ws.period} onChange={ws.setPeriod} disabled={!ws.periods.length} className="w-48">
        {!ws.periods.length && <option value="year">—</option>}
        {ws.periods.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
      </TopSelect>
      {(ws.org?.is_demo || ws.company?.is_demo) && <Badge tone="amber" className="mb-2">Démonstration</Badge>}
      <div className="ml-auto flex items-center gap-2 self-center">
        <Notifications />
        <AccountMenu onSignOut={onSignOut} />
      </div>
    </header>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const ws = useWorkspace();
  const [mobileOpen, setMobileOpen] = useState(false);
  const close = () => setMobileOpen(false);

  // organisation créée ou rejointe depuis le dernier chargement
  useEffect(() => {
    if (ws.org === null && ws.orgs) void ws.reloadOrgs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function signOut() {
    await getSupabaseBrowser().auth.signOut();
    try { localStorage.removeItem(LAST_ORG_KEY); localStorage.removeItem("kofinex.workspace"); } catch { /* ignoré */ }
    router.replace("/login");
    router.refresh();
  }

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[264px_1fr]">
      <aside className="sticky top-0 hidden h-screen lg:block"><Sidebar onNavigate={close} /></aside>

      <div className="sticky top-0 z-30 flex items-center justify-between bg-sidebar px-4 py-2.5 text-sidebar-foreground lg:hidden">
        <Logo />
        <button onClick={() => setMobileOpen(true)} aria-label="Ouvrir le menu" aria-expanded={mobileOpen}
                className="rounded-md p-1.5 hover:bg-sidebar-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <Menu className="h-5 w-5" />
        </button>
      </div>
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-sidebar/60 backdrop-blur-[1px]" onClick={close} />
          <div className="absolute inset-y-0 left-0 w-72">
            <button onClick={close} aria-label="Fermer le menu" className="absolute right-3 top-5 z-10 text-sidebar-foreground">
              <X className="h-5 w-5" />
            </button>
            <Sidebar onNavigate={close} />
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-col">
        <TopBar onSignOut={signOut} />
        <main className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-7">
          {ws.org?.is_demo && (
            <Alert kind="warning" className="mb-4">
              Organisation de <strong>démonstration</strong> : les données affichées sont fictives.
            </Alert>
          )}
          {children}
        </main>
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  return <WorkspaceProvider><Shell>{children}</Shell></WorkspaceProvider>;
}

