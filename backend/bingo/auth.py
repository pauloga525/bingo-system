"""Autenticación con Google y control de acceso de la API.

Flujo:

1. El frontend obtiene un *ID token* de Google (Google Identity Services) y lo
   envía a ``POST /api/auth/google``.
2. El backend verifica la firma, la audiencia (``GOOGLE_CLIENT_ID``), el
   dominio de Google Workspace (``hd``) y que el correo esté autorizado:
   administradores (``BINGO_ADMIN_EMAILS``), animadores con ese ``correo`` en
   ``Animadores`` o estudiantes con ese ``correo`` en ``Estudiantes``.
3. Devuelve un token de sesión propio, firmado y con caducidad, que el
   frontend envía en ``Authorization: Bearer <token>``.

En cada petición a ``/api`` el token se valida y la identidad se vuelve a
comprobar contra la BD (si se quita el correo de un animador pierde el acceso).
Los usuarios no administradores solo pueden actuar en su propio nombre: los
campos ``usuario_id``, ``requesting_user_id`` y ``registrado_por`` deben ser
su propio id.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import wraps
from typing import Any, TypeVar, cast

from flask import Flask, current_app, g, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import Settings
from .db import Collections, Doc, get_db
from .domain.roles import ADMIN_ROL, rol_de
from .errors import ApiError, Forbidden
from .services.animators import AnimatorService, normalize_email
from .services.participants import is_admin
from .services.students import StudentService

logger = logging.getLogger(__name__)

ADMIN, ANIMADOR, ESTUDIANTE, EXTERNO = "admin", "animador", "estudiante", "externo"
# Sesión del público externo (cédula + correo + código): corta y de solo lectura.
EXTERNO_HOURS = 2
_SALT = "bingo-session"
_VERIFIER_KEY = "google_verifier"
_SERIALIZER_KEY = "session_serializer"
_REGISTRATION_KEY = "registration_serializer"
REGISTRATION_MINUTES = 30

# Endpoints de /api accesibles sin sesión.
PUBLIC_ENDPOINTS = frozenset(
    {"auth.google_login", "auth.auth_config", "auth.registro", "auth.externo_codigo", "auth.externo_verificar"}
)
# Únicos endpoints permitidos a estudiantes y al público externo: ver sus propias tablas.
STUDENT_ENDPOINTS = frozenset({"auth.me", "consulta.mis_tablas"})
# Campos con los que el cliente indica "quién" hace la operación.
_ACTOR_FIELDS = ("usuario_id", "requesting_user_id", "registrado_por")

GoogleVerifier = Callable[[str, str], dict[str, Any]]
F = TypeVar("F", bound=Callable[..., Any])


class Unauthorized(ApiError):
    def __init__(self, message: str = "Sesión no válida o expirada. Inicie sesión nuevamente.") -> None:
        super().__init__(message, 401)


class NotRegistered(Forbidden):
    """Correo estudiantil válido que aún no está enlazado a ningún estudiante."""

    def __init__(self) -> None:
        super().__init__("Tu correo aún no está registrado. Completa tus datos para ver tus tablas.")


@dataclass(frozen=True)
class Identity:
    rol: str
    email: str
    user: Doc | None = None  # cuenta de ``Users`` (admin/animador)
    student: Doc | None = None  # documento de ``Estudiantes``
    # Rol del vendedor (animador, secretaria, financiero, parroquia, oratorio) o ``admin``.
    # ``rol`` es el grupo de permisos; los vendedores comparten los del animador.
    cargo: str = ""
    # Comprador externo: cédula de su compra.
    cedula: str = ""

    @property
    def user_id(self) -> str | None:
        return str(self.user["_id"]) if self.user else None

    @property
    def is_admin(self) -> bool:
        return self.rol == ADMIN


def _google_verifier(token: str, client_id: str) -> dict[str, Any]:  # pragma: no cover - requiere red
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    claims: dict[str, Any] = id_token.verify_oauth2_token(  # type: ignore[no-untyped-call]
        token, google_requests.Request(), client_id
    )
    return claims


def init_auth(app: Flask, settings: Settings, verifier: GoogleVerifier | None = None) -> None:
    secret = settings.secret_key
    if not secret:
        secret = secrets.token_urlsafe(32)
        logger.warning("BINGO_SECRET_KEY no está definida: las sesiones se invalidarán al reiniciar el servidor.")
    app.extensions[_SERIALIZER_KEY] = URLSafeTimedSerializer(secret, salt=_SALT)
    app.extensions[_REGISTRATION_KEY] = URLSafeTimedSerializer(secret, salt="bingo-registro")
    app.extensions[_VERIFIER_KEY] = verifier or _google_verifier
    # Cookie de sesión del tablero del juego (páginas servidas por Flask).
    app.secret_key = secret
    app.config.update(
        SESSION_COOKIE_NAME="bingo_tablero",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=settings.session_hours),
    )
    app.before_request(_guard)


def _settings() -> Settings:
    settings: Settings = current_app.config["SETTINGS"]
    return settings


def _serializer() -> URLSafeTimedSerializer:
    serializer: URLSafeTimedSerializer = current_app.extensions[_SERIALIZER_KEY]
    return serializer


# ------------------------------------------------------------ resolución
def resolve_identity(cols: Collections, settings: Settings, email: str) -> Identity:
    """Identidad del correo o ``Forbidden`` si no tiene acceso."""
    email = normalize_email(email)
    denied = Forbidden("Tu cuenta no tiene acceso al sistema.")
    domain = email.rsplit("@", 1)[1] if "@" in email else ""
    if domain not in settings.student_domains:
        raise denied
    if domain == settings.staff_domain:
        staff = _staff_identity(cols, settings, email)
        if staff is not None:
            return staff
    # Estudiantes: ``nombre.apellido.est@uets.edu.ec`` (o el dominio adicional de estudiantes).
    student = StudentService(cols, settings.student_domains).by_email(email)
    if student:
        return Identity(ESTUDIANTE, email, student=student)
    # Solo un correo estudiantil puede registrarse; cualquier otro queda sin acceso.
    if settings.student_email_regex.match(email):
        raise NotRegistered()
    raise denied


def _staff_identity(cols: Collections, settings: Settings, email: str) -> Identity | None:
    """Administrador o animador con ese correo; ``None`` si no es personal autorizado."""
    if email in settings.admin_email_set:
        admin = cols.users.find_one({"usuario": settings.admin_usuario})
        if not admin or not is_admin(admin):
            logger.error("No existe el usuario administrador %r en Users", settings.admin_usuario)
            raise Forbidden("Tu cuenta no tiene acceso al sistema.")
        return Identity(ADMIN, email, user=admin, cargo=ADMIN_ROL)
    svc = AnimatorService(cols, settings.staff_domain)
    animator = svc.by_email(email)
    user = svc.linked_user(animator) if animator else None
    if not user or animator is None or animator.get("activo") is False:
        return None
    if is_admin(user):
        return Identity(ADMIN, email, user=user, cargo=ADMIN_ROL)
    return Identity(ANIMADOR, email, user=user, cargo=rol_de(animator))


def verify_google_credential(credential: Any) -> str:
    """Valida el ID token de Google y devuelve el correo verificado."""
    settings = _settings()
    if not settings.google_client_id:
        raise ApiError("El inicio de sesión con Google no está configurado (GOOGLE_CLIENT_ID).", 503)
    if not credential or not isinstance(credential, str):
        raise ApiError("Falta el token de Google.")
    verifier: GoogleVerifier = current_app.extensions[_VERIFIER_KEY]
    try:
        claims = verifier(credential, settings.google_client_id)
    except ValueError as exc:
        logger.info("Token de Google rechazado: %s", exc)
        raise Unauthorized("No se pudo validar la cuenta de Google.") from exc
    email = normalize_email(claims.get("email"))
    g.google_name = " ".join(str(claims.get("name") or "").split())
    # ``hd`` solo lo incluyen las cuentas de Google Workspace: evita cuentas
    # personales de Google creadas con un correo del dominio.
    allowed_hd = set(settings.student_domains)
    if not email or not claims.get("email_verified") or claims.get("hd") not in allowed_hd:
        raise Forbidden("Debe ingresar con su cuenta institucional de la UETS.")
    return email


def issue_registration_token(email: str) -> str:
    """Token corto que prueba que el correo fue verificado por Google (para el registro)."""
    serializer: URLSafeTimedSerializer = current_app.extensions[_REGISTRATION_KEY]
    return serializer.dumps({"email": email})


def read_registration_token(token: Any) -> str:
    serializer: URLSafeTimedSerializer = current_app.extensions[_REGISTRATION_KEY]
    try:
        data = serializer.loads(str(token or ""), max_age=REGISTRATION_MINUTES * 60)
    except BadSignature as exc:  # incluye SignatureExpired
        raise Unauthorized("El registro expiró. Vuelve a ingresar con Google.") from exc
    return str(data["email"])


def issue_token(identity: Identity) -> str:
    data = {"email": identity.email, "rol": identity.rol}
    if identity.rol == EXTERNO:
        data["cedula"] = identity.cedula
    return _serializer().dumps(data)


def _identity_from_request() -> Identity:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise Unauthorized("Debe iniciar sesión.")
    return identity_from_token(token)


def identity_from_token(token: str) -> Identity:
    """Identidad de un token de sesión del panel (firma, caducidad y acceso vigente)."""
    try:
        data, emitido = _serializer().loads(token, max_age=_settings().session_hours * 3600, return_timestamp=True)
    except SignatureExpired as exc:
        raise Unauthorized() from exc
    except BadSignature as exc:
        raise Unauthorized() from exc
    if data.get("rol") == EXTERNO:
        return _external_identity(data, emitido)
    try:
        identity = resolve_identity(get_db(), _settings(), str(data.get("email", "")))
    except Forbidden as exc:
        raise Unauthorized("Su acceso fue revocado.") from exc
    return identity


def _external_identity(data: dict[str, Any], emitido: datetime) -> Identity:
    """Sesión del comprador externo: vale 2 horas y mientras siga existiendo su compra."""
    if datetime.now(UTC) - emitido > timedelta(hours=EXTERNO_HOURS):
        raise Unauthorized()
    email, cedula = str(data.get("email", "")), str(data.get("cedula", ""))
    if not get_db().participants.find_one({"cedula": cedula, "correo": email}, {"_id": 1}):
        raise Unauthorized("Ya no hay tablas registradas con esos datos.")
    return Identity(EXTERNO, email, cedula=cedula)


def current_identity() -> Identity:
    identity: Identity | None = g.get("identity")
    if identity is None:
        raise Unauthorized()
    return identity


# ---------------------------------------------------------------- guard
def _actor_values() -> list[str]:
    body = request.get_json(silent=True) if request.is_json else None
    sources: list[Any] = [request.args, request.view_args or {}]
    if isinstance(body, dict):
        sources.append(body)
    return [str(src[field]) for src in sources for field in _ACTOR_FIELDS if src.get(field)]


def _guard() -> None:
    if request.method == "OPTIONS" or not request.path.startswith("/api/"):
        return
    if request.endpoint in PUBLIC_ENDPOINTS:
        return
    identity = _identity_from_request()
    g.identity = identity
    if identity.rol in (ESTUDIANTE, EXTERNO):
        if request.endpoint not in STUDENT_ENDPOINTS:
            raise Forbidden("Esta sección no está disponible para estudiantes.")
        return
    if not identity.is_admin and any(value != identity.user_id for value in _actor_values()):
        raise Forbidden("No puede realizar operaciones en nombre de otro usuario.")


def require_admin(view: F) -> F:
    @wraps(view)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not current_identity().is_admin:
            raise Forbidden("Solo el administrador puede realizar esta acción.")
        return view(*args, **kwargs)

    return cast(F, wrapper)
