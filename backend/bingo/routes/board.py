"""Acceso al tablero del juego: solo administradores.

El tablero (``/`` y ``/pages/masterTable.html``) y sus endpoints (``/mark``,
``/reset``, ``/upload``...) los sirve Flask directamente, sin el token del
panel. Para entrar se usa una cookie de sesión firmada (``bingo_tablero``):

* desde el panel: el botón "Tablero" envía el token del administrador por POST
  a ``/tablero/sesion`` (nunca en la URL);
* o directamente en ``/tablero/login`` con el botón de Google.

En cada petición se vuelve a comprobar que el correo siga siendo administrador.
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, Response, current_app, jsonify, redirect, render_template, request, session, url_for
from flask.typing import ResponseReturnValue

from ..auth import Identity, Unauthorized, identity_from_token, resolve_identity, verify_google_credential
from ..config import Settings
from ..db import get_db
from ..errors import ApiError, Forbidden
from ..utils import json_body

bp = Blueprint("tablero", __name__, url_prefix="/tablero")

_SESSION_KEY = "tablero_email"
# Páginas del tablero: sin sesión redirigen al login en vez de responder 401.
_PAGES = {"game.index": "/", "game.master_table": "/pages/masterTable.html"}
_PUBLIC = frozenset({"game.health"})
NOT_ADMIN = "Solo el administrador puede abrir el tablero del juego."


def _settings() -> Settings:
    settings: Settings = current_app.config["SETTINGS"]
    return settings


def _start(identity: Identity) -> None:
    if not identity.is_admin:
        raise Forbidden(NOT_ADMIN)
    session.clear()
    session.permanent = True
    session[_SESSION_KEY] = identity.email


def board_identity() -> Identity | None:
    """Administrador con sesión de tablero vigente, o ``None``."""
    email = session.get(_SESSION_KEY)
    if not email:
        return None
    try:
        identity = resolve_identity(get_db(), _settings(), str(email))
    except ApiError:
        return None
    return identity if identity.is_admin else None


def require_board_admin() -> Any:
    """``before_request`` del blueprint del juego."""
    if request.endpoint in _PUBLIC or board_identity() is not None:
        return None
    if request.method == "GET" and request.endpoint in _PAGES:
        return redirect(url_for("tablero.login_page", next=_PAGES[request.endpoint]))
    raise Unauthorized("Inicie sesión como administrador para usar el tablero.")


def _safe_next(value: Any) -> str:
    return value if value in _PAGES.values() else "/"


@bp.get("/login")
def login_page() -> str:
    return render_template(
        "tablero_login.html",
        google_client_id=_settings().google_client_id,
        next=_safe_next(request.args.get("next")),
        error="",
    )


@bp.post("/login")
def login_google() -> Response:
    """Login directo en el tablero con el botón de Google (responde JSON)."""
    data = json_body()
    email = verify_google_credential(data.get("credential"))
    _start(resolve_identity(get_db(), _settings(), email))
    return jsonify({"success": True, "next": _safe_next(data.get("next"))})


@bp.get("/sesion")
def session_from_panel_get() -> ResponseReturnValue:
    """Si el navegador abrió la dirección sin el formulario (GET), se ofrece el login normal."""
    return redirect(url_for("tablero.login_page"))


@bp.post("/sesion")
def session_from_panel() -> ResponseReturnValue:
    """Entrada desde el panel: recibe el token del administrador en un formulario POST."""
    try:
        _start(identity_from_token(request.form.get("token", "")))
    except ApiError as exc:
        page = render_template(
            "tablero_login.html", google_client_id=_settings().google_client_id, next="/", error=exc.message
        )
        return page, exc.status
    return redirect(_safe_next(request.form.get("next")), code=303)


@bp.post("/salir")
def logout() -> ResponseReturnValue:
    session.clear()
    return redirect(url_for("tablero.login_page"), code=303)
