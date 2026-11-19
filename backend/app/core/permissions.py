"""Rôles et permissions applicatives.

Les mêmes règles sont appliquées en base par les policies RLS
(sql/0002_rls_policies.sql). Ce module sert à produire des refus explicites
(HTTP 403 avec message) avant même d'atteindre la base, et à exposer au
frontend les actions autorisées pour afficher ou masquer les boutons.
"""

from __future__ import annotations

from enum import StrEnum


class OrgRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class CompanyRole(StrEnum):
    ORG_ADMIN = "org_admin"     # rôle effectif d'un owner/admin d'organisation
    ACCOUNTANT = "accountant"
    CONTROLLER = "controller"
    ANALYST = "analyst"
    AUDITOR = "auditor"
    VIEWER = "viewer"


class Permission(StrEnum):
    COMPANY_READ = "company.read"
    COMPANY_UPDATE = "company.update"
    COMPANY_MANAGE_MEMBERS = "company.manage_members"
    FISCAL_YEAR_WRITE = "fiscal_year.write"
    FISCAL_YEAR_CLOSE = "fiscal_year.close"
    IMPORT_WRITE = "import.write"
    BUDGET_WRITE = "budget.write"
    BUDGET_APPROVE = "budget.approve"
    ANALYSIS_RUN = "analysis.run"
    REPORT_GENERATE = "report.generate"
    AUDIT_READ = "audit.read"
    # comptabilité native (lot 3B) : mêmes règles qu'en base (RLS et déclencheurs de la migration 0014)
    ACCOUNTING_SETUP = "accounting.setup"          # plan comptable, tiers, journaux
    ACCOUNTING_SETTINGS = "accounting.settings"    # étape de revue, séparation des tâches
    ENTRY_WRITE = "entry.write"                    # saisie, soumission, extourne
    ENTRY_VALIDATE = "entry.validate"              # revue, validation, rejet
    PAYROLL_DETAIL = "payroll.detail"              # lignes et tiers des comptes de personnel (rémunérations)
    FEC_EXPORT = "fec.export"                      # FEC DGI Bénin : contrôle, génération, téléchargement


_R = CompanyRole
COMPANY_PERMISSIONS: dict[Permission, frozenset[CompanyRole]] = {
    Permission.COMPANY_READ: frozenset(CompanyRole),
    Permission.COMPANY_UPDATE: frozenset({_R.ORG_ADMIN}),
    Permission.COMPANY_MANAGE_MEMBERS: frozenset({_R.ORG_ADMIN}),
    Permission.FISCAL_YEAR_WRITE: frozenset({_R.ORG_ADMIN, _R.ACCOUNTANT}),
    Permission.FISCAL_YEAR_CLOSE: frozenset({_R.ORG_ADMIN, _R.ACCOUNTANT}),
    Permission.IMPORT_WRITE: frozenset({_R.ORG_ADMIN, _R.ACCOUNTANT}),
    Permission.BUDGET_WRITE: frozenset({_R.ORG_ADMIN, _R.ACCOUNTANT, _R.CONTROLLER}),
    # approbation : direction (administrateurs) ou contrôle de gestion ; jamais par l'auteur (contrôle en base)
    Permission.BUDGET_APPROVE: frozenset({_R.ORG_ADMIN, _R.CONTROLLER}),
    Permission.ANALYSIS_RUN: frozenset({_R.ORG_ADMIN, _R.ACCOUNTANT, _R.CONTROLLER, _R.ANALYST}),
    Permission.REPORT_GENERATE: frozenset({_R.ORG_ADMIN, _R.ACCOUNTANT, _R.CONTROLLER, _R.ANALYST}),
    Permission.AUDIT_READ: frozenset({_R.ORG_ADMIN, _R.ACCOUNTANT, _R.AUDITOR}),
    Permission.ACCOUNTING_SETUP: frozenset({_R.ORG_ADMIN, _R.ACCOUNTANT}),
    Permission.ACCOUNTING_SETTINGS: frozenset({_R.ORG_ADMIN}),
    Permission.ENTRY_WRITE: frozenset({_R.ORG_ADMIN, _R.ACCOUNTANT}),
    Permission.ENTRY_VALIDATE: frozenset({_R.ORG_ADMIN, _R.ACCOUNTANT}),
    Permission.PAYROLL_DETAIL: frozenset({_R.ORG_ADMIN, _R.ACCOUNTANT}),
    # le FEC contient toutes les écritures (paie comprise) : mêmes rôles que le détail de la paie ; RLS identique (0016)
    Permission.FEC_EXPORT: frozenset({_R.ORG_ADMIN, _R.ACCOUNTANT}),
}

ORG_MANAGERS = frozenset({OrgRole.OWNER, OrgRole.ADMIN})


def company_role_allows(role: CompanyRole | str | None, permission: Permission) -> bool:
    if role is None:
        return False
    return CompanyRole(role) in COMPANY_PERMISSIONS[permission]


def permissions_for(role: CompanyRole | str | None) -> list[str]:
    return sorted(p.value for p in Permission if company_role_allows(role, p))


def can_assign_org_role(actor: OrgRole | str, target_role: OrgRole | str,
                        current_role: OrgRole | str | None = None) -> bool:
    """Un owner peut tout attribuer ; un admin ne touche jamais au rôle owner."""
    actor, target_role = OrgRole(actor), OrgRole(target_role)
    if actor == OrgRole.OWNER:
        return True
    if actor == OrgRole.ADMIN:
        return target_role != OrgRole.OWNER and current_role != OrgRole.OWNER
    return False
