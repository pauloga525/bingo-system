"""Errores de negocio y manejadores HTTP centralizados."""

from __future__ import annotations

import logging
from typing import Any

from flask import Flask, Response, jsonify
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """Error controlado que se traduce a una respuesta JSON.

    Por defecto la respuesta es ``{"success": False, "message": ...}``, que es
    el formato que consume el frontend. ``payload`` permite reemplazar el
    cuerpo completo para endpoints con formato histórico distinto (p. ej.
    ``{"error": ...}`` en login).
    """

    def __init__(self, message: str, status: int = 400, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.payload = payload

    def to_response(self) -> tuple[Response, int]:
        body = self.payload if self.payload is not None else {"success": False, "message": self.message}
        return jsonify(body), self.status


class NotFound(ApiError):
    def __init__(self, message: str, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message, 404, payload)


class Forbidden(ApiError):
    def __init__(self, message: str) -> None:
        super().__init__(message, 403)


class Conflict(ApiError):
    def __init__(self, message: str, **extra: Any) -> None:
        """``extra`` se agrega al cuerpo JSON (p. ej. datos para que el cliente ofrezca reasignar)."""
        super().__init__(message, 409, {"success": False, "message": message, **extra} if extra else None)


def register_error_handlers(app: Flask) -> None:
    """Convierte excepciones en JSON y evita filtrar trazas en producción."""

    @app.errorhandler(ApiError)
    def _api_error(exc: ApiError) -> tuple[Response, int]:
        return exc.to_response()

    @app.errorhandler(HTTPException)
    def _http_error(exc: HTTPException) -> tuple[Response, int]:
        return jsonify({"success": False, "message": exc.description}), exc.code or 500

    @app.errorhandler(Exception)
    def _unexpected(exc: Exception) -> tuple[Response, int]:
        logger.exception("Error no controlado")
        body: dict[str, Any] = {"success": False, "message": "Error interno del servidor."}
        if app.debug:
            body["error"] = str(exc)
        return jsonify(body), 500
