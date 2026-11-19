"use client";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { DemoFrame } from "@/components/demo-frame";
import { DashboardView } from "@/components/dashboard-view";
import { demoDashboard } from "@/lib/demo-dashboard";

/** Démonstration publique du tableau de bord : données FICTIVES et statiques, aucune connexion à l'API. */
export default function DemonstrationPage() {
  return (
    <div className="min-h-screen">
      <div className="flex flex-wrap items-center justify-between gap-3 bg-warning/15 px-6 py-2.5 text-sm">
        <p className="font-semibold text-warning-strong">Démonstration — toutes les données affichées sont fictives et ne proviennent d&apos;aucune entreprise réelle.</p>
        <div className="flex items-center gap-4">
          <Link href="/" className="inline-flex items-center gap-1 font-medium text-link hover:underline"><ArrowLeft className="h-4 w-4" aria-hidden /> Accueil</Link>
          <Link href="/signup" className="rounded-md bg-accent px-3 py-1.5 font-semibold text-accent-foreground hover:bg-accent/90">Démarrer gratuitement</Link>
        </div>
      </div>
      <div className="overflow-x-auto">
        <div className="min-w-[1180px]"><DemoFrame><DashboardView data={demoDashboard()} demo /></DemoFrame></div>
      </div>
    </div>
  );
}
