"""Endpoints ``/api`` de usuarios: reservas de tablas y contadores.

El inicio de sesión está en ``routes/auth.py`` (Google) y el alta de
animadores en ``routes/admin.py`` (CRUD de ``Animadores``).
"""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from ..auth import require_admin
from ..db import get_db
from ..errors import ApiError
from ..services.users import UserService
from ..utils import json_body, safe_int

bp = Blueprint("users", __name__, url_prefix="/api")


@bp.post("/users/<user_id>/assign_tables")
@require_admin
def assign_tables(user_id: str) -> Response:
    data = json_body()
    if data.get("totalTables") is None:
        raise ApiError("Se requiere totalTables en el body")
    if not data.get("requesting_user_id"):
        raise ApiError("Se requiere el ID del usuario solicitante")
    total = safe_int(data.get("totalTables"), 0)
    if total <= 0:
        raise ApiError("Debe ingresar una cantidad válida")
    rango = UserService(get_db()).assign_tables(user_id, total, data["requesting_user_id"])
    return jsonify({"success": True, "message": "Tablas reservadas exitosamente", **rango})


@bp.route("/validar-tablas/<usuario_id>", methods=["GET", "POST"])
@require_admin
def validar_tablas_usuario(usuario_id: str) -> Response:
    """GET solo diagnostica; POST además corrige los contadores."""
    return jsonify(UserService(get_db()).audit_counters(usuario_id, apply=request.method == "POST"))
