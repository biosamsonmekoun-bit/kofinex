"""Agrégation des droits d'une organisation (docs/LOT12_SAAS_CONCEPTION.md, § 8.1).

Droits = version d'offre souscrite + options actives (quantités) ; l'état de l'abonnement fixe ensuite l'accès.
Les limites viennent du catalogue publié : aucune valeur n'est codée ici. Une limite `None` signifie « illimité »."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.engines.billing.lifecycle import access

# Grandeurs de quota (§ 3.3). Unités retenues (décision du 20 novembre 2026) : IA en jetons ; sociétés non
# archivées ; utilisateurs = membres de l'organisation.
QUOTA_KEYS = ("users", "companies", "engagements", "storage_mb", "imports_per_period", "reports_per_period",
              "ai_tokens_per_period")


class EntitlementError(ValueError):
    pass


@dataclass(frozen=True)
class Grant:
    kind: str               # 'module' | 'quota'
    key: str
    limit: int | None = None


@dataclass(frozen=True)
class Entitlements:
    access: str
    modules: list[str] = field(default_factory=list)
    quotas: dict[str, int | None] = field(default_factory=dict)


def missing_dependencies(modules: set[str], requires: dict[str, tuple[str, ...]]) -> dict[str, list[str]]:
    """Modules dont une dépendance manque (ex. audit financier sans socle d'audit)."""
    unknown = sorted(m for m in modules if m not in requires)
    if unknown:
        raise EntitlementError(f"Modules inconnus : {', '.join(unknown)}")
    out = {m: sorted(d for d in requires[m] if d not in modules) for m in sorted(modules)}
    return {m: d for m, d in out.items() if d}


def validate_plan(grants: list[Grant], requires: dict[str, tuple[str, ...]], core: set[str]) -> list[str]:
    """Anomalies bloquantes avant publication d'une version d'offre de base."""
    issues: list[str] = []
    modules = {g.key for g in grants if g.kind == "module"}
    quotas = {g.key: g for g in grants if g.kind == "quota"}
    for c in sorted(core - modules):
        issues.append(f"Module de base absent : {c}")
    try:
        for m, deps in missing_dependencies(modules, requires).items():
            issues.append(f"Module {m} : dépendance absente ({', '.join(deps)})")
    except EntitlementError as exc:
        issues.append(str(exc))
    for k in QUOTA_KEYS:
        if k not in quotas:
            issues.append(f"Quota non défini : {k} (saisir une limite ou « illimité »)")
    for k, g in quotas.items():
        if k not in QUOTA_KEYS:
            issues.append(f"Quota inconnu : {k}")
        elif g.limit is not None and g.limit < 0:
            issues.append(f"Quota {k} : limite négative")
    return issues


def validate_addon(grants: list[Grant]) -> list[str]:
    """Une option ajoute des modules ou des quantités (jamais « illimité » : un incrément chiffré)."""
    issues: list[str] = []
    if not grants:
        issues.append("Option vide : aucun module ni quota")
    for g in grants:
        if g.kind == "quota":
            if g.key not in QUOTA_KEYS:
                issues.append(f"Quota inconnu : {g.key}")
            elif g.limit is None or g.limit <= 0:
                issues.append(f"Quota {g.key} : incrément positif requis")
    return issues


def aggregate(plan: list[Grant], addons: list[tuple[list[Grant], int]], state: str | None, has_data: bool,
              requires: dict[str, tuple[str, ...]]) -> Entitlements:
    acc = access(state, has_data)
    if acc == "none" or not plan:
        return Entitlements(acc)
    modules = {g.key for g in plan if g.kind == "module"}
    quotas: dict[str, int | None] = {g.key: g.limit for g in plan if g.kind == "quota"}
    for grants, qty in addons:
        if qty < 1:
            raise EntitlementError("Quantité d'option invalide")
        for g in grants:
            if g.kind == "module":
                modules.add(g.key)
            elif g.kind == "quota":
                current = quotas.get(g.key, 0)
                if current is not None:          # illimité le reste
                    quotas[g.key] = current + (g.limit or 0) * qty
    missing = missing_dependencies(modules, requires)
    # un module dont la dépendance manque n'est pas accordé (aucun accès partiel incohérent)
    granted = sorted(m for m in modules if m not in missing)
    return Entitlements(acc, granted, {k: quotas.get(k, 0) for k in QUOTA_KEYS})
