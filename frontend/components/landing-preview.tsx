"use client";

import { DemoFrame } from "@/components/demo-frame";
import { DashboardView } from "@/components/dashboard-view";
import { demoDashboard } from "@/lib/demo-dashboard";

const W = 1240;   // largeur de rendu du tableau de bord avant réduction
const H = 1180;
const S = 0.34;   // facteur de réduction dans l'écran de l'ordinateur

/** Illustration de la page d'accueil : le tableau de bord réel, réduit, alimenté par les données FICTIVES de démonstration. */
export function LaptopPreview() {
  return (
    <figure className="relative mx-auto w-fit max-w-full lg:mr-0" aria-label="Aperçu du tableau de bord KOFINEX avec des données fictives">
      <div className="rotate-[-1.5deg] rounded-t-[14px] border-[9px] border-b-[12px] border-foreground/90 bg-foreground/90 shadow-2xl ring-1 ring-sidebar-foreground/20">
        <div className="relative overflow-hidden rounded-[4px] bg-background" style={{ height: H * S, width: W * S }} aria-hidden>
          <div className="pointer-events-none absolute left-0 top-0 origin-top-left select-none" style={{ width: W, height: H, transform: `scale(${S})` }} inert>
            <DemoFrame><DashboardView data={demoDashboard()} compact /></DemoFrame>
          </div>
        </div>
      </div>
      <div className="relative mx-[-6%] h-3.5 rounded-b-[14px] bg-gradient-to-b from-sidebar-muted to-foreground/80 shadow-xl" aria-hidden>
        <div className="mx-auto h-1.5 w-20 rounded-b-md bg-foreground/40" />
      </div>
      <figcaption className="mt-3 text-center text-[11.5px] text-sidebar-foreground/70">Aperçu — données fictives de démonstration</figcaption>
    </figure>
  );
}
