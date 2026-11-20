import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight, BarChart3, BookOpen, Building, Building2, CalendarDays, Check, CheckCircle2, ChevronDown, ChevronRight, CircleDollarSign,
  Cloud, CreditCard, Cpu, Play, ShieldCheck, Target, User, Users,
} from "lucide-react";
import { BRAND, Logo } from "@/components/brand";
import { LaptopPreview } from "@/components/landing-preview";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
  title: { absolute: "KOFINEX — Pilotez vos finances. Maîtrisez vos performances." },
  description: BRAND.tagline,
};

const NAV = [
  { href: "#accueil", label: "Accueil" },
  { href: "#fonctionnalites", label: "Fonctionnalités" },
];

const BENEFITS: [React.ElementType, string, string][] = [
  [CalendarDays, "Essai gratuit", "30 jours"],
  [CreditCard, "Paiement sécurisé", "via SASPay"],
  [CircleDollarSign, "Devise", "FCFA"],
  [Cloud, "SaaS (Cloud)", "Accessible partout"],
  [ShieldCheck, "Données sécurisées", "et sauvegardées"],
];

const FEATURES: [React.ElementType, string, string, string][] = [
  [BookOpen, "Comptabilité", "Saisie des écritures, journaux, grand livre, balances et états financiers (SYSCOHADA).", "bg-primary"],
  [BarChart3, "Analyse financière", "Ratios, indicateurs, diagnostic financier et évaluation de la performance.", "bg-primary"],
  [Target, "Contrôle de gestion", "Budgets, réalisations, écarts et tableaux de bord de pilotage.", "bg-violet"],
  [ShieldCheck, "Audit et contrôle interne", "Missions d'audit, cartographie des risques, contrôles et recommandations.", "bg-primary"],
];

const AUDIENCES: [React.ElementType, string, string][] = [
  [Building2, "Entreprises", "Pilotez vos finances et votre croissance."],
  [User, "DAF / Directions financières", "Disposez d'une vision complète et fiable."],
  [Users, "Experts-comptables", "Gérez vos dossiers clients efficacement."],
  [Building, "Cabinets comptables", "Centralisez, collaborez et produisez plus vite."],
];

function GoldButton({ href, children, className }: { href: string; children: React.ReactNode; className?: string }) {
  return (
    <Link href={href} className={cn("inline-flex items-center justify-center gap-2 rounded-md bg-accent px-5 py-3 text-[15px] font-semibold text-accent-foreground shadow-sm transition-colors hover:bg-accent/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2", className)}>
      {children}
    </Link>
  );
}

/** Illustration de la bande finale : barres montantes et flèche (décorative). */
function GrowthArt() {
  return (
    <svg viewBox="0 0 96 64" className="h-16 w-24 shrink-0" aria-hidden focusable="false">
      {[10, 18, 28, 40].map((h, i) => <rect key={i} x={8 + i * 18} y={60 - h} width="12" height={h} rx="2" className={i % 2 ? "fill-primary" : "fill-primary/70"} />)}
      <path d="M6 40 30 26l16 8L86 6" fill="none" className="stroke-primary-foreground" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M76 6h10v10" fill="none" className="stroke-primary-foreground" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** Illustration de l'assistant : silhouette abstraite (décorative, originale). */
function AssistantArt() {
  return (
    <svg viewBox="0 0 120 100" className="h-24 w-28 shrink-0" aria-hidden focusable="false">
      <ellipse cx="62" cy="98" rx="46" ry="10" className="fill-primary/15" />
      <path d="M30 100c2-20 14-32 32-32s30 12 32 32Z" className="fill-primary/25" />
      <circle cx="62" cy="40" r="28" className="fill-card stroke-primary/30" strokeWidth="2" />
      <path d="M40 38c0-12 10-20 22-20s22 8 22 20v6c0 4-3 6-7 6H47c-4 0-7-2-7-6Z" className="fill-foreground" />
      <rect x="47" y="34" width="30" height="8" rx="4" className="fill-primary" />
      <circle cx="88" cy="40" r="5" className="fill-primary/60" />
    </svg>
  );
}

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* ---------------------------------------------------------------- en-tête + hero */}
      <div id="accueil" className="relative overflow-hidden bg-sidebar text-sidebar-foreground">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_75%_35%,hsl(var(--primary)/0.55),transparent_60%)]" aria-hidden />
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-primary/20" aria-hidden />
        <header className="relative mx-auto flex max-w-6xl items-center gap-6 px-5 py-4">
          <Link href="/" aria-label="KOFINEX — accueil"><Logo size="lg" /></Link>
          <nav className="ml-auto hidden items-center gap-7 text-[14px] font-medium lg:flex" aria-label="Navigation du site">
            {NAV.map((l, i) => (
              <a key={l.href} href={l.href} className={cn("py-1 hover:text-accent", i === 0 && "border-b-2 border-accent text-accent")}>{l.label}</a>
            ))}
            <details className="group relative">
              <summary className="flex cursor-pointer list-none items-center gap-1 py-1 hover:text-accent [&::-webkit-details-marker]:hidden">
                Solutions <ChevronDown className="h-4 w-4 transition-transform group-open:rotate-180" aria-hidden />
              </summary>
              <div className="absolute left-0 top-9 z-20 w-60 rounded-lg border bg-popover p-2 text-popover-foreground shadow-lg">
                {AUDIENCES.map(([, t]) => <a key={t} href="#pour-qui" className="block rounded px-3 py-2 text-sm hover:bg-muted">{t}</a>)}
              </div>
            </details>
            <Link href="/tarifs" className="py-1 hover:text-accent">Tarifs</Link>
            <a href="#a-propos" className="py-1 hover:text-accent">À propos</a>
          </nav>
          <div className="ml-auto flex items-center gap-3 lg:ml-2">
            <Link href="/login" className="rounded-md border border-sidebar-foreground/80 px-4 py-2 text-[14px] font-semibold hover:bg-sidebar-hover">Connexion</Link>
            <GoldButton href="/signup" className="hidden px-4 py-2 text-[14px] sm:inline-flex">Démarrer gratuitement</GoldButton>
          </div>
        </header>

        <section className="relative mx-auto grid max-w-6xl items-center gap-10 px-5 pb-14 pt-8 lg:grid-cols-[1.05fr_1fr] lg:pb-16">
          <div>
            <p className="inline-block rounded-md border-2 border-accent px-3 py-1 text-[14px] font-bold uppercase tracking-wide text-accent">La finance, enfin sous contrôle</p>
            <h1 className="mt-5 text-[40px] font-extrabold leading-[1.08] tracking-tight sm:text-[48px]">
              Pilotez vos finances.<br />Maîtrisez vos <span className="text-accent">performances.</span>
            </h1>
            <p className="mt-5 max-w-xl text-[17px] leading-relaxed text-sidebar-foreground/90">
              KOFINEX centralise votre comptabilité, votre analyse financière, votre contrôle de gestion et votre audit dans une seule plateforme intelligente.
            </p>
            <ul className="mt-6 flex flex-wrap gap-3 text-[13px] font-semibold">
              <li className="inline-flex items-center gap-1.5 rounded-md border border-success/70 bg-success/15 px-3 py-1.5"><CheckCircle2 className="h-4 w-4 text-success" aria-hidden /> Comptabilité OHADA</li>
              <li className="inline-flex items-center gap-1.5 rounded-md border border-primary/80 bg-primary/20 px-3 py-1.5"><CheckCircle2 className="h-4 w-4 text-primary" aria-hidden /> Analyse financière</li>
              <li className="inline-flex items-center gap-1.5 rounded-md border border-violet/80 bg-violet/20 px-3 py-1.5"><CheckCircle2 className="h-4 w-4 text-violet" aria-hidden /> Intelligence artificielle</li>
            </ul>
            <div className="mt-9 flex flex-wrap gap-4">
              <GoldButton href="/signup"><Play className="h-4 w-4" aria-hidden /> Démarrer gratuitement (30 jours)</GoldButton>
              <Link href="/demonstration" className="inline-flex items-center gap-2 rounded-md border border-sidebar-foreground/80 px-5 py-3 text-[15px] font-semibold hover:bg-sidebar-hover">
                <Play className="h-4 w-4" aria-hidden /> Voir la démonstration
              </Link>
            </div>
          </div>
          <LaptopPreview />
        </section>
      </div>

      {/* ---------------------------------------------------------------- avantages */}
      <section className="border-b bg-card" aria-label="Avantages">
        <ul className="mx-auto grid max-w-6xl grid-cols-2 gap-y-4 px-5 py-5 sm:grid-cols-3 lg:grid-cols-5 lg:divide-x">
          {BENEFITS.map(([Icon, t, s]) => (
            <li key={t} className="flex items-center gap-3 px-4">
              <Icon className="h-8 w-8 shrink-0 text-primary" strokeWidth={1.8} aria-hidden />
              <span className="leading-tight"><span className="block text-[14px] font-semibold">{t}</span><span className="text-[13px] text-muted-foreground">{s}</span></span>
            </li>
          ))}
        </ul>
      </section>

      {/* ---------------------------------------------------------------- fonctionnalités */}
      <section id="fonctionnalites" className="mx-auto max-w-6xl scroll-mt-6 px-5 pt-12">
        <h2 className="text-center text-[30px] font-extrabold tracking-tight">Les fonctionnalités clés de <span className="text-primary">KOFINEX</span></h2>
        <p className="mt-2 text-center text-[16px] text-muted-foreground">Une suite complète pour la performance financière de votre organisation.</p>
        <div className="mt-8 grid gap-5 md:grid-cols-2">
          {FEATURES.map(([Icon, t, d, bg]) => (
            <Link key={t} href="/demonstration" className="group flex items-center gap-5 rounded-xl border bg-card p-6 shadow-card transition-shadow hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
              <span className={cn("flex h-14 w-14 shrink-0 items-center justify-center rounded-xl text-primary-foreground", bg)}><Icon className="h-7 w-7" aria-hidden /></span>
              <span className="min-w-0 flex-1">
                <span className="block text-[19px] font-bold">{t}</span>
                <span className="mt-1 block text-[14px] leading-snug text-muted-foreground">{d}</span>
              </span>
              <ChevronRight className="h-5 w-5 shrink-0 text-primary transition-transform group-hover:translate-x-0.5" aria-hidden />
            </Link>
          ))}
        </div>

        {/* ---------------------------------------------------------------- KOFINEX AI */}
        <div className="mt-8 flex flex-col gap-6 rounded-xl border bg-gradient-to-r from-primary/10 via-card to-primary/15 px-8 py-5 shadow-card md:flex-row md:items-center">
          <div className="flex items-center gap-5">
            <Cpu className="h-16 w-16 shrink-0 text-primary" strokeWidth={1.4} aria-hidden />
            <div>
              <p className="text-[26px] font-extrabold text-foreground">KOFINEX AI</p>
              <p className="text-[15px]">Votre assistant financier intelligent</p>
            </div>
          </div>
          <div className="hidden h-14 w-px bg-border md:block" aria-hidden />
          <ul className="flex-1 space-y-1 text-[14px]">
            {["Analyse automatique des données", "Détection des anomalies", "Recommandations de performance"].map((x) => (
              <li key={x} className="flex items-center gap-2"><Check className="h-4 w-4 text-primary" aria-hidden /> {x}</li>
            ))}
          </ul>
          <AssistantArt />
        </div>
      </section>

      {/* ---------------------------------------------------------------- publics */}
      <section id="pour-qui" className="mx-auto max-w-6xl scroll-mt-6 px-5 pt-12">
        <h2 className="text-center text-[28px] font-extrabold tracking-tight">Pour qui est conçu <span className="text-primary">KOFINEX</span> ?</h2>
        <div className="mt-7 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {AUDIENCES.map(([Icon, t, d]) => (
            <div key={t} className="flex flex-col items-center rounded-xl border bg-card px-5 py-6 text-center shadow-card">
              <Icon className="h-10 w-10 text-primary" strokeWidth={1.8} aria-hidden />
              <p className="mt-3 text-[16px] font-bold">{t}</p>
              <p className="mt-1.5 text-[14px] leading-snug text-muted-foreground">{d}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ---------------------------------------------------------------- bandeau final */}
      <section className="mx-auto max-w-6xl px-5 py-10">
        <div className="relative flex flex-col items-start gap-6 overflow-hidden rounded-xl bg-sidebar px-8 py-6 text-sidebar-foreground md:flex-row md:items-center">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_10%_100%,hsl(var(--primary)/0.45),transparent_55%)]" aria-hidden />
          <GrowthArt />
          <div className="relative flex-1">
            <p className="text-[26px] font-extrabold">Essayez KOFINEX dès aujourd&apos;hui !</p>
            <p className="text-[15px] text-sidebar-foreground/90">30 jours gratuits, sans moyen de paiement. Sans engagement.</p>
          </div>
          <GoldButton href="/signup" className="relative">Démarrer mon essai gratuit <ArrowRight className="h-4 w-4" aria-hidden /></GoldButton>
        </div>
      </section>

      {/* ---------------------------------------------------------------- tarifs, à propos */}
      <footer className="border-t bg-card">
        <div className="mx-auto grid max-w-6xl gap-8 px-5 py-10 text-[14px] md:grid-cols-3">
          <div>
            <Logo className="text-foreground" />
            <p className="mt-3 text-muted-foreground">{BRAND.tagline}</p>
          </div>
          <div id="tarifs" className="scroll-mt-6">
            <p className="font-semibold">Tarifs</p>
            <p className="mt-2 text-muted-foreground">Offres et prix en FCFA et dans la devise de chaque pays de l'OHADA, hors taxes.</p>
            <Link href="/tarifs" className="mt-2 inline-flex items-center gap-1 font-semibold text-link hover:underline">Voir la grille tarifaire <ArrowRight className="h-4 w-4" aria-hidden /></Link>
          </div>
          <div id="a-propos" className="scroll-mt-6">
            <p className="font-semibold">À propos</p>
            <p className="mt-2 text-muted-foreground">
              KOFINEX est conçu pour les référentiels SYSCOHADA révisé et SYSCEBNL : imports de balance et de grand livre, analyse financière,
              contrôle de gestion, audit, contrôle interne et reporting, dans un espace sécurisé par organisation.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
