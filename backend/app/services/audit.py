"""Journal des événements métier.

Les INSERT/UPDATE/DELETE des tables sensibles sont déjà journalisés par trigger
(sql/0001_core_schema.sql). Ce service enregistre les événements qui ne sont pas
des modifications de lignes : export de rapport, consultation d'un document
confidentiel, invitation envoyée, échec de connexion à une intégration…
"""

from __future__ import annotations

import ipaddress
import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog


def _client_ip(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    try:
        return str(ipaddress.ip_address(request.client.host))
    except ValueError:  # hôte non IP (client de test, socket Unix…)
        return None


def record_event(
    db: Session,
    *,
    user_id: uuid.UUID,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    company_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    # identifiant fourni par l'application : pas de RETURNING, donc pas besoin du droit de
    # lecture du journal pour y écrire (un analyste journalise sans pouvoir le consulter)
    db.add(AuditLog(
        id=uuid.uuid4(),
        organization_id=organization_id,
        company_id=company_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        changes=details,
        ip_address=_client_ip(request),
        user_agent=(request.headers.get("user-agent", "")[:500] if request else None),
        request_id=(getattr(request.state, "request_id", None) if request else None),
    ))
