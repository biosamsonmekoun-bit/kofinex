/**
 * DONNÉES DE DÉMONSTRATION — FICTIVES.
 * Jeu de données statique, utilisé exclusivement par la page publique /demonstration et l'illustration de la page
 * d'accueil. Il n'est jamais envoyé à l'API, jamais enregistré en base et jamais mélangé aux données d'une entreprise.
 * Les montants reprennent la maquette de référence ; ils ne correspondent à aucune entreprise réelle.
 */
import type { DashboardData } from "@/lib/dashboard-types";

const M = (x: number) => String(Math.round(x * 1e6));

function at(daysAgo: number, h: number, m: number) {
  const d = new Date(); d.setDate(d.getDate() - daysAgo); d.setHours(h, m, 0, 0);
  return d.toISOString();
}

export function demoDashboard(): DashboardData {
  const months: [string, number, number][] = [["Janv.", 11.2, 7.1], ["Févr.", 13.4, 10.2], ["Mars", 12.9, 7.8], ["Avr.", 17.1, 12.3], ["Mai", 17.8, 13.0], ["Juin", 21.4, 13.6]];
  return {
    company: { id: "demo", name: "Entreprise de démonstration", currency: "XOF", is_demo: true },
    fiscal_year: { id: "demo-2025", label: "2025", start_date: "2025-01-01", end_date: "2025-12-31" },
    previous_label: "Janv. – Juin 2024",
    period: { key: "demo", label: "Janv. – Juin 2025", from: 1, to: 6 },
    periods: [],
    analysis: { id: "demo", completed_at: at(0, 8, 0) },
    kpis: {
      revenue: { code: "CA", name: "Chiffre d'affaires", available: true, value: M(125.8), variation: "12.5" },
      net_income: { code: "RESULTAT_NET", name: "Résultat net", available: true, value: M(18.4), variation: "8.2" },
      cash: { code: "TN", name: "Trésorerie nette", available: true, value: M(32.6) },
    },
    expenses: { total: M(87.2), unclassified_accounts: 0, groups: [
      { key: "66", label: "Personnel", amount: M(34.97), share: "40.1" },
      { key: "60", label: "Achats", amount: M(27.99), share: "32.1" },
      { key: "62", label: "Services extérieurs", amount: M(15.0), share: "17.2" },
      { key: "autres", label: "Autres", amount: M(9.24), share: "10.6" },
    ] },
    income: { total: M(125.8), unclassified_accounts: 0, groups: [
      { key: "701", label: "Ventes de biens", amount: M(73.34), share: "58.3" },
      { key: "706", label: "Prestations de services", amount: M(31.07), share: "24.7" },
      { key: "autres", label: "Autres produits", amount: M(21.39), share: "17.0" },
    ] },
    breakdown_source: "ledger",
    breakdown_note: null,
    indicators: [
      { code: "MARGE_COMMERCIALE", name: "Marge commerciale", available: true, value: M(38.6), variation: "11.9" },
      { code: "EBE", name: "EBE", available: true, value: M(24.1), variation: "9.7" },
      { code: "RESULTAT_EXPLOITATION", name: "Résultat d'exploitation", available: true, value: M(20.3), variation: "8.5" },
      { code: "RESULTAT_NET", name: "Résultat net", available: true, value: M(18.4), variation: "8.2" },
      { code: "CAF_ADDITIVE", name: "Capacité d'autofinancement", available: true, value: M(23.9), variation: "10.1" },
    ],
    monthly: { available: true, months: months.map(([label, i, e], k) => ({ period: k + 1, label, year: 2025, income: M(i), expense: M(e) })) },
    alerts: [
      { key: "imports", title: "Imports en attente", detail: "2 imports à valider", state: "todo", count: 2 },
      { key: "analysis_alerts", title: "Alertes de l'analyse", detail: "3 alertes à examiner", state: "progress", count: 3 },
      { key: "last_analysis", title: "Dernière analyse financière", detail: "Analyse disponible", state: "done", count: 0 },
    ],
    activities: [
      { id: "a1", action: "ledger.imported", label: "Import du grand livre (journal VTE)", entity_type: "import_job", at: at(0, 10, 24), user: null },
      { id: "a2", action: "import.validated", label: "Validation de la balance générale", entity_type: "import_job", at: at(0, 9, 17), user: null },
      { id: "a3", action: "report.generate", label: "Génération du rapport financier", entity_type: "generated_report", at: at(1, 17, 32), user: null },
    ],
  };
}
