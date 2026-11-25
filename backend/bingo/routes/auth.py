"""Endpoints de sesión: inicio de sesión con Google y datos del usuario actual."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from flask import Blueprint, Response, current_app, g, jsonify

from ..auth import (
    ESTUDIANTE,
    EXTERNO,
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
from ..domain.roles import ANIMADOR_ROL, ETIQUETAS, VEN_REPORTES, etiquetas, tipos_venta
from ..errors import Forbidden
from ..services.animators import AnimatorService
from ..services.external_access import GENERIC, ExternalAccess
from ..services.students import StudentService, full_name
from ..utils import json_body

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# tipo_usuario que entiende el frontend: 0 admin, 1 animador, 2 estudiante.
_TIPO = {"admin": 0, "animador": 1, ESTUDIANTE: 2, EXTERNO: 3}


def _settings() -> Settings:
    settings: Settings = current_app.config["SETTINGS"]
    return settings


def _profile(identity: Identity) -> dict[str, Any]:
    base: dict[str, Any] = {"rol": identity.rol, "correo": identity.email, "tipo_usuario": _TIPO[identity.rol]}
    if identity.rol == EXTERNO:
        compra = get_db().participants.find_one({"cedula": identity.cedula}, {"nombre": 1, "apellido": 1}) or {}
        nombres = f"{compra.get('nombre', '')} {compra.get('apellido', '')}".strip()
        return {**base, "id": None, "cedula": identity.cedula, "nombres": nombres}
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
    cargos = identity.cargos or (identity.cargo,)
    vendedor = _animators().by_email(identity.email) if identity.rol == "animador" else None
    return {
        **base,
        # Primer ingreso: el vendedor confirma su nombre antes de usar el panel.
        "onboarding_pendiente": bool(vendedor and not vendedor.get("onboarding_at")),
        # Nombre de su cuenta de Google, para proponerlo cuando se creó solo con el correo.
        "nombre_google": (vendedor or {}).get("nombre_google", "") if (vendedor or {}).get("nombre_pendiente") else "",
        # Roles del vendedor (animador, secretaria, financiero, ...; o admin). ``cargo`` = principal.
        "cargo": identity.cargo,
        "cargos": list(cargos),
        "cargo_nombre": etiquetas(list(cargos)),
        "cargos_nombres": {c: ETIQUETAS.get(c, c) for c in cargos},
        # Sin rol animador: no tiene curso (vende a externos y a alumnos como venta del rol).
        "solo_externos": not identity.is_admin and ANIMADOR_ROL not in cargos,
        "tipos_venta": tipos_venta(list(cargos)),
        "ve_reportes": identity.is_admin or bool(VEN_REPORTES.intersection(cargos)),
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


def _animators() -> AnimatorService:
    return AnimatorService(get_db(), _settings().staff_domain)


def _log_rejected(email: str) -> None:
    """Guarda el intento de un correo del personal sin acceso (el admin lo ve en Vendedores)."""
    s = _settings()
    if email.rsplit("@", 1)[-1] != s.staff_domain or s.student_email_regex.match(email):
        return
    get_db().access_log.update_one(
        {"correo": email},
        {
            "$set": {"nombre": g.get("google_name", ""), "ultimo": datetime.now().isoformat(timespec="seconds")},
            "$inc": {"intentos": 1},
        },
        upsert=True,
    )


@bp.post("/google")
def google_login() -> Response | tuple[Response, int]:
    email = verify_google_credential(json_body().get("credential"))
    try:
        identity = resolve_identity(get_db(), _settings(), email)
    except NotRegistered as exc:
        return _registration_required(email, exc)
    except Forbidden:
        _log_rejected(email)
        raise
    if identity.rol == "animador":
        _animators().record_login(email, g.get("google_name", ""))
    return _session(identity, "Inicio de sesión exitoso")


def _registration_required(email: str, exc: NotRegistered) -> tuple[Response, int]:
    """Estudiante sin registrar: token corto ligado a su correo ya verificado por Google."""
    body = {
        "success": False,
        "message": exc.message,
        "registro_requerido": True,
        "registro_token": issue_registration_token(email),
        "correo": email,
    }
    return jsonify(body), 403


@bp.post("/onboarding")
def onboarding() -> Response:
    """Primer ingreso del vendedor: confirma su nombre y queda activo."""
    identity = current_identity()
    if identity.rol != "animador":
        raise Forbidden("Solo los vendedores completan el primer ingreso.")
    _animators().complete_onboarding(identity.email, json_body().get("nombre"))
    refreshed = resolve_identity(get_db(), _settings(), identity.email)
    return jsonify({"success": True, "message": "¡Bienvenido!", "usuario": _profile(refreshed)})


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


def _external() -> ExternalAccess:
    s = _settings()
    return ExternalAccess(
        get_db(), str(current_app.secret_key), current_app.extensions["mailer"], run_async=s.mail_async
    )


@bp.post("/externo/codigo")
def externo_codigo() -> Response:
    """Público externo: envía un código al correo si la cédula y el correo coinciden con una compra."""
    data = json_body()
    _external().request_code(data.get("cedula"), data.get("correo"))
    return jsonify({"success": True, "message": GENERIC})


@bp.post("/externo/verificar")
def externo_verificar() -> Response:
    """Público externo: con el código correcto entrega una sesión de solo lectura (2 horas)."""
    data = json_body()
    compra = _external().verify(data.get("cedula"), data.get("correo"), data.get("codigo"))
    identity = Identity(EXTERNO, str(compra["correo"]), cedula=str(compra["cedula"]))
    return _session(identity, "Acceso concedido")


@bp.get("/me")
def me() -> Response:
    return jsonify({"success": True, "usuario": _profile(current_identity())})
