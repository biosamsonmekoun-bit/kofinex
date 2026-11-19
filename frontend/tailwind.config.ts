import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

// Couleurs : uniquement des tokens définis dans app/globals.css (aucun code HEX ici ni dans les composants).
const token = (name: string) => `hsl(var(--${name}))`;

const config: Config = {
  darkMode: ["class"],
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: token("border"),
        input: token("input"),
        ring: token("ring"),
        background: token("background"),
        foreground: token("foreground"),
        link: token("link"),
        selection: "var(--selection)",
        primary: { DEFAULT: token("primary"), foreground: token("primary-foreground") },
        secondary: { DEFAULT: token("secondary"), foreground: token("secondary-foreground") },
        muted: { DEFAULT: token("muted"), foreground: token("muted-foreground") },
        accent: { DEFAULT: token("accent"), foreground: token("accent-foreground") },
        popover: { DEFAULT: token("popover"), foreground: token("popover-foreground") },
        card: { DEFAULT: token("card"), foreground: token("card-foreground") },
        success: { DEFAULT: token("success"), strong: token("success-strong") },
        warning: { DEFAULT: token("warning"), strong: token("warning-strong") },
        destructive: {
          DEFAULT: token("destructive"), strong: token("destructive-strong"),
          foreground: token("destructive-foreground"),
        },
        info: { DEFAULT: token("info"), strong: token("info-strong") },
        violet: token("violet"),
        sidebar: {
          DEFAULT: token("sidebar"), foreground: token("sidebar-foreground"), muted: token("sidebar-muted"),
          active: "var(--sidebar-active)", hover: "var(--sidebar-hover)", border: "var(--sidebar-border)",
        },
        chart: {
          1: token("chart-1"), 2: token("chart-2"), 3: token("chart-3"), 4: token("chart-4"), 5: token("chart-5"),
          blue: token("chart-blue"), orange: token("chart-orange"), green: token("chart-green"), violet: token("chart-violet"),
        },
      },
      borderRadius: { lg: "var(--radius)", md: "calc(var(--radius) - 2px)", sm: "calc(var(--radius) - 4px)" },
      boxShadow: { card: "var(--shadow-card)" },
      fontFamily: { sans: ["var(--font-sans)", "system-ui", "sans-serif"] },
    },
  },
  plugins: [animate],
};

export default config;
