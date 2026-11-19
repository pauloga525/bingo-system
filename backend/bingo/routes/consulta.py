"""Consulta de tablas: pública por cédula y la del estudiante que inició sesión."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, Response, current_app, jsonify

from ..auth import current_identity
from ..db import Doc, get_db
from ..errors import ApiError, Forbidden, NotFound
from ..services.students import StudentService, full_name

bp = Blueprint("consulta", __name__, url_prefix="/api")


def _public_table(t: Doc) -> dict[str, Any]:
    return {"serial": t.get("serial", ""), "matrix": t.get("matrix", []), "won": t.get("won", False)}


@bp.get("/consulta/<string:cedula>")
def consulta_cedula(cedula: str) -> Response:
    """Tablas compradas por la persona con esa cédula (sin sesión).

    Solo devuelve el nombre y las tablas; ningún otro dato personal.
    """
    cedula = cedula.strip()
    if not cedula.isdigit() or not 6 <= len(cedula) <= 13:
        raise ApiError("Ingrese un número de cédula válido.")
    cols = get_db()
    registros = list(cols.participants.find({"cedula": cedula}, {"nombre": 1, "apellido": 1, "tablas": 1}))
    if not registros:
        raise NotFound("No se encontraron tablas para esa cédula.")
    ids = [tid for p in registros for tid in p.get("tablas") or []]
    tablas = list(cols.tables.find({"_id": {"$in": ids}}).sort("serial", 1)) if ids else []
    primero = registros[0]
    return jsonify(
        {
            "success": True,
            "participante": {
                "nombre": primero.get("nombre", ""),
                "apellido": primero.get("apellido", ""),
                "tablas": [_public_table(t) for t in tablas],
            },
        }
    )


@bp.get("/mis-tablas")
def mis_tablas() -> Response:
    """Tablas del estudiante que inició sesión (se enlaza por su cédula)."""
    student = current_identity().student
    if student is None:
        raise Forbidden("Esta consulta es solo para estudiantes.")
    svc = StudentService(get_db(), current_app.config["SETTINGS"].student_domains)
    tablas = [_public_table(t) for t in svc.tables_of(student)]
    return jsonify(
        {
            "success": True,
            "estudiante": {"nombre": full_name(student), "cedula": student.get("Num documento", "")},
            "tablas": tablas,
        }
    )
