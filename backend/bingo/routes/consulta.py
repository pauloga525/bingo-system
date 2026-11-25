"""Consulta de las tablas propias: estudiante (Google) o comprador externo (código por correo).

La antigua consulta pública por cédula se eliminó: dejaba ver las tablas de
cualquier persona sabiendo su cédula.
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, Response, current_app, jsonify

from ..auth import EXTERNO, current_identity
from ..db import Doc, get_db
from ..errors import Forbidden
from ..services.students import StudentService, full_name

bp = Blueprint("consulta", __name__, url_prefix="/api")


def _public_table(t: Doc) -> dict[str, Any]:
    return {"serial": t.get("serial", ""), "matrix": t.get("matrix", []), "won": t.get("won", False)}


def _purchase_tables(cedula: str) -> tuple[str, list[Doc]]:
    cols = get_db()
    registros = list(cols.participants.find({"cedula": cedula}, {"nombre": 1, "apellido": 1, "tablas": 1}))
    ids = [tid for p in registros for tid in p.get("tablas") or []]
    tablas = list(cols.tables.find({"_id": {"$in": ids}}).sort("serial", 1)) if ids else []
    nombre = f"{registros[0].get('nombre', '')} {registros[0].get('apellido', '')}".strip() if registros else ""
    return nombre, tablas


@bp.get("/mis-tablas")
def mis_tablas() -> Response:
    """Tablas de quien inició sesión: el estudiante (por su cédula) o el comprador externo."""
    identity = current_identity()
    if identity.rol == EXTERNO:
        nombre, tablas = _purchase_tables(identity.cedula)
        titular = {"nombre": nombre, "cedula": identity.cedula}
    elif identity.student is not None:
        svc = StudentService(get_db(), current_app.config["SETTINGS"].student_domains)
        tablas = svc.tables_of(identity.student)
        titular = {"nombre": full_name(identity.student), "cedula": identity.student.get("Num documento", "")}
    else:
        raise Forbidden("Esta consulta es solo para estudiantes y compradores.")
    return jsonify({"success": True, "titular": titular, "tablas": [_public_table(t) for t in tablas]})
