import { BRAND, Logo } from "@/components/brand";
import { ThemeToggle } from "@/components/theme-toggle";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <aside className="hidden flex-col justify-between bg-sidebar p-10 text-sidebar-foreground lg:flex">
        <Logo withSignature />
        <div className="max-w-md space-y-4">
          <div className="h-px w-12 bg-accent" aria-hidden />
          <p className="text-2xl font-semibold leading-snug">{BRAND.tagline}</p>
          <p className="text-sm leading-relaxed text-sidebar-muted">
            Analyse financière, contrôle de gestion et reporting conformes au SYSCOHADA révisé et au SYSCEBNL.
            Calculs traçables, formules versionnées, données isolées par organisation.
          </p>
        </div>
        <p className="text-xs text-sidebar-muted">© {new Date().getFullYear()} {BRAND.name}</p>
      </aside>
      <main className="relative flex flex-col items-center justify-center gap-8 p-6">
        <div className="flex w-full max-w-sm items-center justify-between lg:hidden">
          <Logo className="text-foreground" />
        </div>
        <ThemeToggle className="absolute right-4 top-4" />
        {children}
      </main>
    </div>
  );
}
