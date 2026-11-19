// Reporting (lot 11) : types partagés.
import type { PersonRef } from "@/lib/types";

export type DocFormat = "pdf" | "xlsx" | "docx";
export type DocumentType = "financial_report" | "budget_report" | "ic_report" | "internal_audit_report" | "fa_summary";
export interface SourceRef { type: string; id: string | null; label?: string; [k: string]: unknown }
export interface GeneratedDoc {
  id: string; company_id: string; analysis_id: string | null; engagement_id: string | null; template_id: string | null;
  template_version: number | null; document_type: DocumentType; document_label: string; subtype: string | null; title: string | null;
  format: DocFormat; status: "ready" | "failed"; filename: string | null; size_bytes: number | null; sha256: string | null;
  data_sha256: string | null; source_refs: SourceRef[]; parameters: Record<string, unknown>; contains_ai_drafts: boolean;
  generator_version: string | null; failure_reason: string | null; created_at: string; requested_by_user?: PersonRef | null;
}
export interface ReportTemplate {
  id: string; organization_id: string | null; name: string; document_type: DocumentType; version: number;
  status: "draft" | "published" | "archived"; sections: string[]; content: Record<string, string>; branding: { primary_color?: string };
  published_at: string | null; created_at: string; updated_at: string;
}
export const FORMAT_LABELS: Record<DocFormat, string> = { pdf: "PDF", xlsx: "Excel", docx: "Word" };
export const DOC_TYPE_LABELS: Record<DocumentType, string> = {
  financial_report: "Rapport financier", budget_report: "Suivi budgétaire", ic_report: "Rapport de contrôle interne",
  internal_audit_report: "Rapport d'audit interne émis", fa_summary: "Synthèse des anomalies (audit financier)",
};
export const FINANCIAL_SECTION_LABELS: Record<string, string> = {
  controls: "Contrôles de l'analyse", statements: "États financiers", indicators: "Indicateurs", alerts: "Alertes", commentary: "Commentaires",
};
export const TEMPLATE_STATUS: Record<string, [string, "amber" | "green" | "neutral"]> = {
  draft: ["Brouillon", "amber"], published: ["Publié", "green"], archived: ["Archivé", "neutral"],
};
