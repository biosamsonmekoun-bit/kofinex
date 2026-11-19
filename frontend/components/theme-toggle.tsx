"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme, type ThemeChoice } from "@/lib/theme";
import { cn } from "@/lib/utils";

const OPTIONS: { value: ThemeChoice; label: string; icon: React.ElementType }[] = [
  { value: "light", label: "Clair", icon: Sun },
  { value: "dark", label: "Sombre", icon: Moon },
  { value: "system", label: "Automatique", icon: Monitor },
];

/** Sélecteur clair / sombre / automatique. `onSidebar` : variante pour fond bleu nuit. */
export function ThemeToggle({ onSidebar = false, className }: { onSidebar?: boolean; className?: string }) {
  const { theme, setTheme } = useTheme();
  return (
    <div role="radiogroup" aria-label="Thème d'affichage"
         className={cn("inline-flex rounded-md p-0.5",
           onSidebar ? "bg-sidebar-hover" : "border bg-muted", className)}>
      {OPTIONS.map(({ value, label, icon: Icon }) => {
        const active = theme === value;
        return (
          <button key={value} type="button" role="radio" aria-checked={active} title={label}
                  onClick={() => setTheme(value)}
                  className={cn(
                    "flex h-7 flex-1 items-center justify-center gap-1.5 rounded px-2 text-xs transition-colors",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    onSidebar
                      ? active ? "bg-sidebar-active text-sidebar-foreground" : "text-sidebar-muted hover:text-sidebar-foreground"
                      : active ? "bg-card text-foreground shadow-card" : "text-muted-foreground hover:text-foreground",
                  )}>
            <Icon className="h-3.5 w-3.5" aria-hidden />
            <span className="sr-only sm:not-sr-only">{label}</span>
          </button>
        );
      })}
    </div>
  );
}
