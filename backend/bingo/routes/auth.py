"""Endpoints de sesión: inicio de sesión con Google y datos del usuario actual."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, Response, current_app, jsonify

from ..auth import (
    ESTUDIANTE,
    Identity,
    NotRegistered,
    current_identity,
    issue_registration_token,
    issue_token,
    read_registration_token,
    resolve_identity,
    verify_google_credential,
)
from ..config import Settings
from ..db import get_db
from ..services.students import StudentService, full_name
from ..utils import json_body

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# tipo_usuario que entiende el frontend: 0 admin, 1 animador, 2 estudiante.
_TIPO = {"admin": 0, "animador": 1, ESTUDIANTE: 2}


def _settings() -> Settings:
    settings: Settings = current_app.config["SETTINGS"]
    return settings


def _profile(identity: Identity) -> dict[str, Any]:
    base: dict[str, Any] = {"rol": identity.rol, "correo": identity.email, "tipo_usuario": _TIPO[identity.rol]}
    if identity.student is not None:
        s = identity.student
        return {
            **base,
            "id": None,
            "nombres": full_name(s),
            "cedula": s.get("Num documento"),
            "curso": s.get("Curso"),
            "especialidad": s.get("Especialidad"),
            "nivel": s.get("Nivel"),
            "paralelo": s.get("Paralelo"),
        }
    user = identity.user or {}
    return {
        **base,
        "id": identity.user_id,
        "usuario": user.get("usuario"),
        "nombres": user.get("nombres_completos"),
        "curso": user.get("curso"),
        "especialidad": user.get("especialidad"),
        "nivel": user.get("nivel"),
        "paralelo": user.get("paralelo"),
    }


@bp.get("/config")
def auth_config() -> Response:
    """Datos públicos que necesita el frontend para mostrar el botón de Google."""
    s = _settings()
    return jsonify({"google_client_id": s.google_client_id, "dominios": list(s.student_domains)})


def _session(identity: Identity, message: str) -> Response:
    return jsonify(
        {
            "message": message,
            "token": issue_token(identity),
            "expira_en_horas": _settings().session_hours,
            "usuario": _profile(identity),
        }
    )


@bp.post("/google")
def google_login() -> Response | tuple[Response, int]:
    email = verify_google_credential(json_body().get("credential"))
    try:
        identity = resolve_identity(get_db(), _settings(), email)
    except NotRegistered as exc:
        # Estudiante sin registrar: token corto ligado a su correo ya verificado por Google.
        body = {
            "success": False,
            "message": exc.message,
            "registro_requerido": True,
            "registro_token": issue_registration_token(email),
            "correo": email,
        }
        return jsonify(body), 403
    return _session(identity, "Inicio de sesión exitoso")


@bp.post("/registro")
def registro() -> Response:
    """Autorregistro del estudiante: cruza cédula y nombres con la BD y guarda su correo."""
    data = json_body()
    email = read_registration_token(data.get("registro_token"))
    if not _settings().student_email_regex.match(email):
        raise NotRegistered()  # pragma: no cover - el token solo se emite a correos estudiantiles
    StudentService(get_db(), _settings().student_domains).register_email(
        email, data.get("cedula"), data.get("nombres"), data.get("apellidos")
    )
    return _session(resolve_identity(get_db(), _settings(), email), "Registro completado")


@bp.get("/me")
def me() -> Response:
    return jsonify({"success": True, "usuario": _profile(current_identity())})
