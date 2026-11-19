"use client";

import * as React from "react";

export type ThemeChoice = "light" | "dark" | "system";
const STORAGE_KEY = "kofinex.theme";

/**
 * Script exécuté dans <head> avant le premier rendu : applique le thème mémorisé
 * (ou celui du système) pour éviter le flash du mauvais thème au chargement.
 */
export const themeInitScript = `(function(){try{var t=localStorage.getItem("${STORAGE_KEY}");if(t!=="light"&&t!=="dark")t="system";var d=t==="dark"||(t==="system"&&window.matchMedia("(prefers-color-scheme: dark)").matches);var e=document.documentElement;e.classList.toggle("dark",d);e.style.colorScheme=d?"dark":"light";}catch(_){}})();`;

type ThemeContextValue = { theme: ThemeChoice; resolved: "light" | "dark"; setTheme: (t: ThemeChoice) => void };
const ThemeContext = React.createContext<ThemeContextValue | null>(null);

function systemPrefersDark() {
  return typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function apply(resolved: "light" | "dark") {
  const root = document.documentElement;
  root.classList.toggle("dark", resolved === "dark");
  root.style.colorScheme = resolved;
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = React.useState<ThemeChoice>("system");
  const [resolved, setResolved] = React.useState<"light" | "dark">("light");

  // lecture du choix mémorisé (le script de <head> l'a déjà appliqué)
  React.useEffect(() => {
    let stored: string | null = null;
    try { stored = localStorage.getItem(STORAGE_KEY); } catch { /* stockage indisponible */ }
    const choice: ThemeChoice = stored === "light" || stored === "dark" ? stored : "system";
    setThemeState(choice);
    setResolved(choice === "system" ? (systemPrefersDark() ? "dark" : "light") : choice);
  }, []);

  // mode automatique : suit les changements de préférence du système
  React.useEffect(() => {
    if (theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => { const r = mq.matches ? "dark" : "light"; setResolved(r); apply(r); };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [theme]);

  const setTheme = React.useCallback((t: ThemeChoice) => {
    try { localStorage.setItem(STORAGE_KEY, t); } catch { /* stockage indisponible */ }
    const r = t === "system" ? (systemPrefersDark() ? "dark" : "light") : t;
    setThemeState(t);
    setResolved(r);
    apply(r);   // immédiat, sans rechargement
  }, []);

  const value = React.useMemo(() => ({ theme, resolved, setTheme }), [theme, resolved, setTheme]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = React.useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme doit être utilisé dans <ThemeProvider>.");
  return ctx;
}
