"""Vérification des JWT émis par Supabase Auth.

Module volontairement indépendant de FastAPI pour être testé isolément.
Deux modes :
  * HS256 avec le secret JWT du projet (SUPABASE_JWT_SECRET) ;
  * clés asymétriques (ES256/RS256) publiées sur SUPABASE_JWKS_URL.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import jwt

ALLOWED_ASYMMETRIC_ALGS = ("ES256", "RS256")
LEEWAY_SECONDS = 30


class AuthError(Exception):
    """Jeton absent, invalide ou expiré."""


@dataclass(frozen=True)
class AuthenticatedUser:
    id: uuid.UUID
    email: str | None
    role: str
    claims: dict[str, Any] = field(repr=False)


class TokenVerifier:
    def __init__(self, *, audience: str, hs256_secret: str = "", jwks_url: str = "",
                 issuer: str | None = None) -> None:
        if not hs256_secret and not jwks_url:
            raise ValueError("Un secret HS256 ou une URL JWKS est requis")
        self._audience = audience
        self._secret = hs256_secret
        self._issuer = issuer
        self._jwks = jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=3600) if jwks_url else None

    def verify(self, token: str) -> AuthenticatedUser:
        if not token:
            raise AuthError("Jeton manquant")
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise AuthError("Jeton mal formé") from exc

        alg = header.get("alg")
        options = {"require": ["exp", "sub", "aud"]}
        try:
            if alg == "HS256" and self._secret:
                claims = jwt.decode(token, self._secret, algorithms=["HS256"], audience=self._audience,
                                    issuer=self._issuer, leeway=LEEWAY_SECONDS, options=options)
            elif alg in ALLOWED_ASYMMETRIC_ALGS and self._jwks is not None:
                key = self._jwks.get_signing_key_from_jwt(token).key
                claims = jwt.decode(token, key, algorithms=list(ALLOWED_ASYMMETRIC_ALGS),
                                    audience=self._audience, issuer=self._issuer,
                                    leeway=LEEWAY_SECONDS, options=options)
            else:
                # refuse notamment alg=none et toute confusion d'algorithme
                raise AuthError(f"Algorithme de signature non accepté : {alg}")
        except jwt.ExpiredSignatureError as exc:
            raise AuthError("Session expirée") from exc
        except jwt.PyJWTError as exc:
            raise AuthError("Jeton invalide") from exc

        if claims.get("role") != "authenticated":
            raise AuthError("Rôle de jeton non autorisé")
        try:
            user_id = uuid.UUID(str(claims["sub"]))
        except ValueError as exc:
            raise AuthError("Identifiant utilisateur invalide") from exc

        return AuthenticatedUser(id=user_id, email=claims.get("email"), role=claims["role"], claims=claims)
