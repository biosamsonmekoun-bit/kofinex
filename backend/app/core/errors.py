"""Erreurs applicatives et traduction des erreurs PostgreSQL en réponses HTTP lisibles."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, IntegrityError

logger = logging.getLogger(__name__)


class AppError(Exception):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "bad_request"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFound(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class Forbidden(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class Conflict(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class Unauthorized(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"


class ServiceUnavailable(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "service_unavailable"


# SQLSTATE -> (HTTP, code, message)
_PG_ERRORS: dict[str, tuple[int, str, str]] = {
    "23505": (409, "duplicate", "Cet enregistrement existe déjà."),
    "23503": (409, "invalid_reference", "Référence invalide ou enregistrement encore utilisé."),
    "23514": (422, "constraint_violation", "Les données ne respectent pas une règle de gestion."),
    "23P01": (409, "overlap", "La période chevauche un enregistrement existant."),
    "42501": (403, "forbidden", "Action non autorisée."),
}


def _error_body(code: str, message: str, request: Request, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {},
                      "request_id": getattr(request.state, "request_id", None)}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code,
                            content=_error_body(exc.code, exc.message, request, exc.details))

    @app.exception_handler(DBAPIError)
    async def _db_error(request: Request, exc: DBAPIError) -> JSONResponse:
        sqlstate = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
        if sqlstate in _PG_ERRORS:
            http, code, default_msg = _PG_ERRORS[sqlstate]
            message = default_msg
            # Les triggers métier lèvent des messages destinés à l'utilisateur (check_violation)
            diag = getattr(getattr(exc.orig, "diag", None), "message_primary", None)
            if sqlstate == "23514" and diag and not diag.startswith("new row"):
                message = diag
            if sqlstate == "42501" and diag:
                # refus de la RLS : message générique ; refus d'un trigger métier : son message explicite
                message = ("Vous n'avez pas les droits nécessaires pour cette action."
                           if "row-level security" in diag else diag)
            return JSONResponse(status_code=http, content=_error_body(code, message, request))
        if isinstance(exc, IntegrityError):
            return JSONResponse(status_code=409, content=_error_body(
                "integrity_error", "Opération refusée par une contrainte d'intégrité.", request))
        logger.exception("Erreur base de données", extra={"request_id": request.state.request_id})
        return JSONResponse(status_code=500, content=_error_body(
            "database_error", "Erreur interne de la base de données.", request))
