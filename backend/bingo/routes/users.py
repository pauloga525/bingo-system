"""Endpoints ``/api`` de usuarios: auditoría de contadores de ventas.

El inicio de sesión está en ``routes/auth.py`` (Google) y el alta de
animadores en ``routes/admin.py`` (CRUD de ``Animadores``).
"""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from ..auth import require_admin
from ..db import get_db
from ..services.users import UserService

bp = Blueprint("users", __name__, url_prefix="/api")


@bp.route("/validar-tablas/<usuario_id>", methods=["GET", "POST"])
@require_admin
def validar_tablas_usuario(usuario_id: str) -> Response:
    """GET solo diagnostica; POST además corrige los contadores."""
    return jsonify(UserService(get_db()).audit_counters(usuario_id, apply=request.method == "POST"))
