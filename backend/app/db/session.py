"""Sessions base de données.

Deux types de sessions :

* ``user_session`` (cas général) : chaque requête s'exécute dans une transaction
  où l'on bascule sur le rôle ``authenticated`` et où l'on injecte les claims du
  JWT. Les policies RLS de Supabase s'appliquent donc AUSSI aux requêtes de
  l'API : une erreur de contrôle applicatif ne peut pas exposer les données
  d'un autre tenant.

* ``service_session`` : rôle de connexion (contourne RLS). Réservé à des
  opérations précises et justifiées (recherche d'un profil par e-mail pour une
  invitation, webhooks de paiement, workers système). Ne jamais l'utiliser
  pour répondre directement à une requête de lecture utilisateur.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.security import AuthenticatedUser

_settings = get_settings()

engine = create_engine(
    _settings.database_url,
    pool_size=_settings.db_pool_size,
    max_overflow=_settings.db_max_overflow,
    pool_pre_ping=True,
    future=True,
)

SessionFactory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _apply_rls_context(session: Session) -> None:
    user: AuthenticatedUser = session.info["rls_user"]
    # SET LOCAL : limité à la transaction, sans fuite vers la connexion du pool
    session.execute(text("SET LOCAL ROLE authenticated"))
    session.execute(
        text("SELECT set_config('request.jwt.claims', :claims, true), "
             "set_config('app.request_id', :rid, true)"),
        {"claims": json.dumps({"sub": str(user.id), "role": "authenticated", "email": user.email}),
         "rid": session.info.get("request_id") or ""},
    )


def commit_preserving_rls(session: Session) -> None:
    """Valide la transaction (par ex. avant d'envoyer une tâche à un worker, qui doit voir les
    données) puis rouvre une transaction avec le même contexte RLS : sans cela, les requêtes
    suivantes s'exécuteraient avec le rôle de connexion, hors RLS."""
    session.commit()
    session.begin()
    _apply_rls_context(session)


@contextmanager
def user_session(user: AuthenticatedUser, request_id: str | None = None) -> Iterator[Session]:
    session = SessionFactory()
    session.info["rls_user"] = user
    session.info["request_id"] = request_id
    try:
        session.begin()
        _apply_rls_context(session)
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def service_session() -> Iterator[Session]:
    session = SessionFactory()
    try:
        session.begin()
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def anon_session() -> Iterator[Session]:
    """Session d'un visiteur non connecté : rôle `anon`, soumis à RLS (lecture du catalogue publié seulement).
    Préférée à la session de service, qui contourne RLS."""
    session = SessionFactory()
    try:
        session.begin()
        session.execute(text("SET LOCAL ROLE anon"))
        session.execute(text("SELECT set_config('request.jwt.claims', '{\"role\": \"anon\"}', true)"))
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
