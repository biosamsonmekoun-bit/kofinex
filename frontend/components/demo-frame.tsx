/**
 * Cadre d'application statique pour la démonstration publique et l'illustration de la page d'accueil.
 * Il reproduit l'apparence de la barre latérale et de la barre supérieure, sans aucune action : ce ne sont pas des
 * boutons (éléments non interactifs), et la bannière rappelle que les données sont fictives.
 */
import {
  BarChart3, Bell, ChevronDown, CircleDollarSign, ClipboardCheck, ClipboardList, Cpu, FileText, Gauge, House, Landmark,
  Package, Receipt, Settings, ShieldCheck, ShoppingBag, ShoppingCart, Wallet,
} from "lucide-react";
import { Logo } from "@/components/brand";
import { cn } from "@/lib/utils";

const ITEMS: [string, React.ElementType][] = [
  ["Comptabilité", ClipboardList], ["Achats", ShoppingCart], ["Ventes", ShoppingBag], ["Trésorerie", CircleDollarSign],
  ["Stocks", Package], ["Immobilisations", Landmark], ["Paie", Wallet], ["Fiscalité", Receipt], ["Analyse financière", BarChart3],
  ["Contrôle de gestion", Gauge], ["Audit financier", ClipboardCheck], ["Contrôle interne", ShieldCheck], ["KOFINEX AI", Cpu], ["Reporting", FileText],
];

function Fake({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <span className="text-[12px] font-medium text-foreground/80">{label}</span>
      <span className="flex h-9 items-center justify-between rounded-md border bg-card px-3 text-[13px] font-semibold">
        {value} <ChevronDown className="h-4 w-4 text-foreground/70" aria-hidden />
      </span>
    </div>
  );
}

export function DemoFrame({ children, topRight }: { children: React.ReactNode; topRight?: React.ReactNode }) {
  return (
    <div className="grid min-h-full grid-cols-[264px_1fr] bg-background text-foreground">
      <div className="flex flex-col bg-sidebar px-4 pb-6 pt-6 text-sidebar-foreground">
        <div className="mb-7 px-2"><Logo withSignature /></div>
        <div className="space-y-0.5 text-[14px] font-medium">
          <div className="flex items-center gap-3 rounded-md bg-primary px-3 py-2.5 text-primary-foreground shadow-sm">
            <House className="h-[18px] w-[18px]" aria-hidden /> Tableau de bord
          </div>
          {ITEMS.map(([label, Icon]) => (
            <div key={label} className="flex items-center gap-3 px-3 py-2.5 text-sidebar-foreground/90">
              <Icon className="h-[18px] w-[18px]" aria-hidden /> <span className="flex-1">{label}</span>
              <ChevronDown className="h-4 w-4 opacity-80" aria-hidden />
            </div>
          ))}
        </div>
        <div className="mt-4 border-t border-sidebar-border pt-4 text-[14px] font-medium">
          <div className="flex items-center gap-3 px-3 py-2.5"><Settings className="h-[18px] w-[18px]" aria-hidden /> Paramètres</div>
        </div>
      </div>
      <div className="flex min-w-0 flex-col">
        <div className="flex items-end gap-4 border-b bg-card px-8 py-3">
          <Fake label="Entreprise" value="Entreprise démo" className="w-52" />
          <Fake label="Exercice" value="2025" className="w-32" />
          <Fake label="Période" value="Janv. – Juin 2025" className="w-48" />
          <div className="ml-auto flex items-center gap-3 self-center">
            {topRight}
            <span className="relative p-2"><Bell className="h-[22px] w-[22px]" aria-hidden />
              <span className="absolute right-1 top-1 h-2.5 w-2.5 rounded-full bg-destructive ring-2 ring-card" aria-hidden /></span>
            <span className="flex items-center gap-2 text-sm font-semibold">
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-[13px] text-primary-foreground">DÉ</span> Démo
            </span>
          </div>
        </div>
        <div className="min-w-0 flex-1 px-8 py-7">{children}</div>
      </div>
    </div>
  );
}
