import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { ThemeProvider, themeInitScript } from "@/lib/theme";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });

export const metadata: Metadata = {
  title: { default: "KOFINEX", template: "%s · KOFINEX" },
  description: "KOFINEX — la plateforme intelligente de pilotage financier (SYSCOHADA révisé et SYSCEBNL).",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // la classe « dark » est posée avant hydratation par themeInitScript
    <html lang="fr" className={inter.variable} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body>
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
