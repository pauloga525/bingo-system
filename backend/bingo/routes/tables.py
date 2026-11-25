"""Endpoints ``/api`` de tablas, búsqueda de personas y reportes."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from ..auth import require_reports
from ..db import get_db
from ..services.queue import TableQueue
from ..services.reports import ReportService
from ..services.tables import PeopleService, TableService
from ..utils import json_body, safe_int

bp = Blueprint("tables", __name__, url_prefix="/api")


@bp.get("/tablas")
def obtener_tablas() -> Response:
    """Tablas filtradas. Con ``?page=`` (y ``per_page``, máx. 200) devuelve una sola página."""
    args = request.args
    svc = TableService(get_db())
    filtros = (args.get("disponible"), args.get("serial"), args.get("search", "").strip())
    if args.get("page"):
        pagina = svc.page(*filtros, safe_int(args.get("page"), 1), safe_int(args.get("per_page"), 50))
        return jsonify({"success": True, **pagina, "count": len(pagina["tablas"])})
    tablas = svc.list_tables(*filtros)
    return jsonify({"success": True, "tablas": tablas, "count": len(tablas)})


@bp.get("/tablas/<tabla_id>")
def obtener_tabla(tabla_id: str) -> Response:
    return jsonify({"success": True, "tabla": TableService(get_db()).get_table(tabla_id)})


@bp.get("/validarTabla/<serial>")
def validar_tabla_serial(serial: str) -> Response:
    return jsonify({"success": True, "tabla": TableService(get_db()).validate_serial(serial)})


@bp.post("/obtenerTablasConsecutivas")
def obtener_tablas_consecutivas() -> Response:
    """Vista previa: las tablas que recibiría ahora una venta de ``cantidad_tablas`` (no asigna)."""
    seriales = TableQueue(get_db()).peek(safe_int(json_body().get("cantidad_tablas"), 0))
    return jsonify(
        {
            "success": True,
            "message": "Siguientes tablas de la cola.",
            "tablas_consecutivas": seriales,
            "cantidad": len(seriales),
        }
    )


@bp.get("/cola-tablas")
def cola_tablas() -> Response:
    """Estado de la cola de venta: total, vendidas, disponibles y próxima tabla."""
    return jsonify({"success": True, **TableQueue(get_db()).status()})


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
@require_reports
def obtener_reportes() -> Response:
    return jsonify({"success": True, "reportes": ReportService(get_db()).build()})
