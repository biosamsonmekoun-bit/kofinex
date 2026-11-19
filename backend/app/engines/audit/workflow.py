"""Règles de circuit et de supervision d'une mission (miroir des triggers de la migration 0007).

Elles servent à l'API (messages clairs avant l'appel à la base) et à l'interface (actions proposées) ;
la base reste l'autorité : une règle contournée ici serait refusée par elle.
"""

from __future__ import annotations

from dataclasses import dataclass, field

ROLES = ("partner", "manager", "in_charge", "staff", "quality_reviewer", "auditee", "observer")
ROLE_LABELS = {"partner": "Associé", "manager": "Manager", "in_charge": "Chef de mission", "staff": "Auditeur",
               "quality_reviewer": "Réviseur qualité", "auditee": "Audité", "observer": "Observateur"}
STATUSES = ("planning", "fieldwork", "review", "reporting", "issued", "archived")
STATUS_LABELS = {"planning": "Planification", "fieldwork": "Travaux", "review": "Revue", "reporting": "Rapport",
                 "issued": "Émise", "archived": "Archivée"}
LEAD = ("partner", "manager")

# (de, vers) -> rôles autorisés
TRANSITIONS: dict[tuple[str, str], tuple[str, ...]] = {
    ("planning", "fieldwork"): LEAD,
    ("fieldwork", "review"): ("partner", "manager", "in_charge"),
    ("review", "fieldwork"): ("partner", "manager", "in_charge"),
    ("review", "reporting"): LEAD,
    ("reporting", "review"): LEAD,
    ("reporting", "issued"): ("partner",),
    ("issued", "archived"): LEAD,
    ("issued", "reporting"): ("partner",),      # réouverture motivée
    ("archived", "reporting"): ("partner",),    # réouverture motivée
}

# action -> rôles (indépendance confirmée requise, sauf audité / observateur)
CAPABILITIES: dict[str, tuple[str, ...]] = {
    "read_dossier": ("partner", "manager", "in_charge", "staff", "quality_reviewer", "observer"),
    "manage_team": LEAD,
    "edit_header": ("partner", "manager", "in_charge"),
    "plan": ("partner", "manager", "in_charge"),           # risques, programmes
    "edit_procedures": ("partner", "manager", "in_charge", "staff"),
    "edit_workpapers": ("partner", "manager", "in_charge", "staff"),
    "add_evidence": ("partner", "manager", "in_charge", "staff"),
    "write_review_notes": ("partner", "manager", "in_charge", "quality_reviewer"),
    "answer_review_notes": ("partner", "manager", "in_charge", "staff", "quality_reviewer"),
    "sign_preparer": ("partner", "manager", "in_charge", "staff"),
    "sign_reviewer": ("partner", "manager", "in_charge"),
    "sign_approver": LEAD,
    "sign_quality": ("quality_reviewer",),
    "approve_engagement": ("partner",),
    # audit financier (lot 7)
    "approve_materiality": LEAD,
    "decide_misstatements": ("partner", "manager", "in_charge"),
    "conclude_misstatements": LEAD,
    # audit interne (lot 8)
    "read_findings": ("partner", "manager", "in_charge", "staff", "quality_reviewer", "observer", "auditee"),
    "edit_findings": ("partner", "manager", "in_charge", "staff"),
    "validate_findings": LEAD,
    "communicate_findings": ("partner", "manager", "in_charge"),
    "respond_findings": ("partner", "manager", "in_charge", "auditee"),
    "follow_up": ("partner", "manager", "in_charge", "staff", "auditee"),
    "verify_actions": ("partner", "manager", "in_charge"),
    "edit_report": ("partner", "manager", "in_charge"),
    "issue_report": ("partner",),
    # contrôle interne (lot 9) : approbation des évaluations, réouverture motivée d'un test revu
    "approve_ic": LEAD,
    "close_findings": ("partner", "manager", "in_charge"),
}
# après l'émission, seuls la lecture et le suivi des plans d'action restent possibles
AFTER_ISSUE = ("read_dossier", "read_findings", "follow_up", "verify_actions", "close_findings")
FROZEN = ("issued", "archived")


def capabilities(role: str | None, independent: bool, status: str) -> list[str]:
    if role is None:
        return []
    if role not in ("auditee", "observer") and not independent:
        return ["confirm_independence"]
    caps = [c for c, roles in CAPABILITIES.items() if role in roles]
    if status in FROZEN:
        caps = [c for c in caps if c in AFTER_ISSUE]
    return caps


def next_statuses(status: str, role: str | None) -> list[str]:
    return [to for (frm, to), roles in TRANSITIONS.items() if frm == status and role in roles]


def reviewer_allowed(preparer_role: str, reviewer_role: str) -> bool:
    """Le réviseur a un rôle supérieur à celui du préparateur (un chef de mission ne revoit pas un chef de mission)."""
    if reviewer_role not in ("partner", "manager", "in_charge"):
        return False
    if reviewer_role == "in_charge":
        return preparer_role == "staff"
    return True


@dataclass
class Check:
    code: str
    label: str
    passed: bool
    detail: str | None = None


@dataclass
class Supervision:
    workpapers: dict[str, int]
    procedures: dict[str, int]
    open_notes: int
    answered_notes: int
    risks_total: int
    risks_uncovered: list[dict]
    significant_uncovered: int
    members_pending_independence: list[str]
    issuance_checks: list[Check] = field(default_factory=list)

    @property
    def ready_to_issue(self) -> bool:
        return all(c.passed for c in self.issuance_checks)


def supervise(*, workpapers: list[dict], procedures: list[dict], notes: list[dict], risks: list[dict],
              coverage: dict[str, int], members: list[dict], engagement_signoffs: list[dict]) -> Supervision:
    """workpapers : {status} ; procedures : {status} ; notes : {status} ; risks : {id, code, title, is_significant} ;
    coverage : id de risque -> nombre de procédures ; members : {role, independent, name} ;
    engagement_signoffs : signatures actives de la mission {signoff_role}."""
    wp = {s: 0 for s in ("draft", "prepared", "reviewed", "approved")}
    for w in workpapers:
        wp[w["status"]] = wp.get(w["status"], 0) + 1
    pr = {s: 0 for s in ("not_started", "in_progress", "done", "not_applicable")}
    for p in procedures:
        pr[p["status"]] = pr.get(p["status"], 0) + 1
    open_n = sum(1 for n in notes if n["status"] == "open")
    answered = sum(1 for n in notes if n["status"] == "answered")
    uncovered = [r for r in risks if coverage.get(str(r["id"]), 0) == 0]
    pending = [m["name"] for m in members if m["role"] not in ("auditee", "observer") and not m["independent"]]
    roles_signed = {s["signoff_role"] for s in engagement_signoffs}
    has_qr = any(m["role"] == "quality_reviewer" for m in members)
    total_wp = sum(wp.values())
    checks = [
        Check("WORKPAPERS_APPROVED", "Toutes les feuilles de travail sont approuvées",
              total_wp > 0 and wp["approved"] == total_wp,
              f"{wp['approved']} / {total_wp} approuvées"),
        Check("REVIEW_NOTES_CLOSED", "Toutes les notes de revue sont closes", open_n + answered == 0,
              f"{open_n} ouverte(s), {answered} répondue(s) non close(s)"),
        Check("RISKS_COVERED", "Chaque risque identifié est couvert par au moins une procédure", not uncovered,
              f"{len(uncovered)} risque(s) sans procédure"),
        Check("PROCEDURES_DONE", "Toutes les procédures sont réalisées ou motivées « non applicable »",
              pr["not_started"] + pr["in_progress"] == 0,
              f"{pr['not_started'] + pr['in_progress']} en cours ou non commencée(s)"),
        Check("INDEPENDENCE", "Toute l'équipe a confirmé son indépendance", not pending,
              ", ".join(pending) if pending else None),
        Check("QUALITY_REVIEW", "Revue qualité de la mission signée", (not has_qr) or "quality_reviewer" in roles_signed,
              None if has_qr else "Pas de réviseur qualité dans l'équipe"),
        Check("PARTNER_APPROVAL", "Mission approuvée (signée) par l'associé", "approver" in roles_signed),
    ]
    return Supervision(wp, pr, open_n, answered, len(risks), uncovered,
                       sum(1 for r in uncovered if r.get("is_significant")), pending, checks)
