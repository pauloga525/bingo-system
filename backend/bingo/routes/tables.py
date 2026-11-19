"""Endpoints ``/api`` de tablas, búsqueda de personas y reportes."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from ..auth import require_admin
from ..db import get_db
from ..services.reports import ReportService
from ..services.tables import PeopleService, TableService
from ..utils import json_body, safe_int

bp = Blueprint("tables", __name__, url_prefix="/api")


@bp.get("/tablas")
def obtener_tablas() -> Response:
    tablas = TableService(get_db()).list_tables(
        request.args.get("disponible"), request.args.get("serial"), request.args.get("search", "").strip()
    )
    return jsonify({"success": True, "tablas": tablas, "count": len(tablas)})


@bp.get("/tablas/<tabla_id>")
def obtener_tabla(tabla_id: str) -> Response:
    return jsonify({"success": True, "tabla": TableService(get_db()).get_table(tabla_id)})


@bp.get("/validarTabla/<serial>")
def validar_tabla_serial(serial: str) -> Response:
    return jsonify({"success": True, "tabla": TableService(get_db()).validate_serial(serial)})


@bp.post("/obtenerTablasConsecutivas")
def obtener_tablas_consecutivas() -> Response:
    data = json_body()
    seriales = TableService(get_db()).consecutive_available(
        data.get("usuario_id"), safe_int(data.get("cantidad_tablas"), 0)
    )
    return jsonify(
        {
            "success": True,
            "message": "Tablas disponibles obtenidas correctamente.",
            "tablas_consecutivas": seriales,
            "cantidad": len(seriales),
        }
    )


@bp.get("/estudiante/<busqueda>")
def buscar_estudiante(busqueda: str) -> Response:
    return jsonify({"success": True, "estudiante": PeopleService(get_db()).student(busqueda)})


@bp.post("/validarTabla/<cedula>")
def validar_tabla_cedula(cedula: str) -> Response:
    """Histórico: pese al nombre, busca un estudiante por cédula."""
    return buscar_estudiante(cedula)


@bp.get("/docente/<busqueda>")
def buscar_docente(busqueda: str) -> Response:
    return jsonify({"success": True, "docente": PeopleService(get_db()).teacher(busqueda)})


@bp.get("/reportes")
@require_admin
def obtener_reportes() -> Response:
    return jsonify({"success": True, "reportes": ReportService(get_db()).build()})
