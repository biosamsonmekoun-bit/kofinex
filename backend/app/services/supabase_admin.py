"""Appels à l'API d'administration Supabase Auth (clé service role, backend uniquement)."""

from __future__ import annotations

import uuid

import httpx

from app.core.config import get_settings
from app.core.errors import AppError, ServiceUnavailable


class InvitationError(AppError):
    code = "invitation_failed"


def invite_user_by_email(email: str, redirect_to: str | None = None) -> uuid.UUID:
    """Crée le compte (statut « invité ») et envoie l'e-mail d'invitation Supabase.

    Retourne l'identifiant du nouvel utilisateur. Le profil est créé par le
    trigger ``on_auth_user_created``.
    """
    s = get_settings()
    if not s.supabase_service_role_key:
        raise ServiceUnavailable("Invitations indisponibles : SUPABASE_SERVICE_ROLE_KEY non configurée")

    payload: dict = {"email": email}
    params = {"redirect_to": redirect_to} if redirect_to else None
    try:
        resp = httpx.post(
            f"{s.supabase_url.rstrip('/')}/auth/v1/invite",
            json=payload,
            params=params,
            headers={"apikey": s.supabase_service_role_key,
                     "Authorization": f"Bearer {s.supabase_service_role_key}"},
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        raise ServiceUnavailable("Service d'authentification injoignable") from exc

    if resp.status_code >= 400:
        try:
            msg = resp.json().get("msg") or resp.json().get("message") or resp.text
        except ValueError:
            msg = resp.text
        raise InvitationError(f"Invitation refusée par le service d'authentification : {msg}")

    data = resp.json()
    user_id = data.get("id") or (data.get("user") or {}).get("id")
    if not user_id:
        raise InvitationError("Réponse inattendue du service d'authentification")
    return uuid.UUID(user_id)
