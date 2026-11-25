"""Endpoints ``/api`` de participantes.

Las rutas que reciben ``<tipo_usuario>`` lo conservan por compatibilidad con
el frontend, pero los permisos se calculan con el usuario guardado en la BD.
"""

from __future__ import annotations

from collections.abc import Iterable
from io import BytesIO
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, request, send_file

from ..auth import current_identity
from ..config import Settings
from ..db import Doc, get_db
from ..domain.roles import ETIQUETAS
from ..errors import ApiError, Forbidden
from ..services.notifications import TablesMailer
from ..services.participants import ParticipantService, is_admin, sales_of, table_summary
from ..services.pdf_render import render_cards_pdf
from ..utils import json_body, require_object_id, safe_int, serialize_mongo_doc, try_object_id

bp = Blueprint("participants", __name__, url_prefix="/api")


def _settings() -> Settings:
    settings: Settings = current_app.config["SETTINGS"]
    return settings


def _svc() -> ParticipantService:
    return ParticipantService(get_db(), _settings().student_email_regex)


def _mail() -> TablesMailer:
    s = _settings()
    return TablesMailer(get_db(), current_app.extensions["mailer"], s.panel_url, run_async=s.mail_async)


@bp.post("/registrarParticipante")
@bp.post("/CreateParticipantes")
def registrar_participante() -> tuple[Response, int]:
    participante = _svc().register(json_body(), allow_serials=current_identity().is_admin)
    _mail().notify(require_object_id(participante["_id"], "ID inválido."))
    return jsonify(
        {"success": True, "message": "Participante registrado exitosamente.", "participante": participante}
    ), 201


@bp.post("/registrarParticipanteAuto")
def registrar_participante_auto() -> tuple[Response, int]:
    participante_id = _svc().register_auto(json_body())
    _mail().notify(participante_id)
    return jsonify(
        {"success": True, "message": "Participante registrado correctamente", "participante_id": str(participante_id)}
    ), 201


@bp.post("/participante/<participante_id>/correo")
def reenviar_correo(participante_id: str) -> Response:
    """Reenvía las tablas por correo; con ``correo`` en el cuerpo, antes lo corrige."""
    pid = require_object_id(participante_id, "ID de participante inválido.")
    _svc().change_email(pid, json_body().get("correo"), current_identity().user_id)
    _mail().notify(pid)
    estado = get_db().participants.find_one({"_id": pid}, {"correo": 1, "correo_estado": 1}) or {}
    return jsonify(
        {
            "success": True,
            "message": f"Enviando las tablas a {estado.get('correo')}.",
            "correo": estado.get("correo"),
            "correo_estado": estado.get("correo_estado"),
        }
    )


@bp.get("/obtenerTablasParticipante/<string:participante_id>")
def obtener_tablas_participante(participante_id: str) -> Response:
    svc = _svc()
    participante = svc.get_participant(require_object_id(participante_id, "ID de participante inválido."))
    tablas = [table_summary(t) for t in svc.tables_of(participante)]
    if not tablas:
        return jsonify({"success": True, "message": "El participante no tiene tablas asignadas.", "tablas": []})
    return jsonify({"success": True, "message": "Tablas recuperadas correctamente.", "tablas": tablas})


def _sellers_of(p: Doc) -> list[dict[str, Any]]:
    """Ventas del participante con el nombre de cada vendedor (para mostrar quién vendió qué)."""
    ventas = sales_of(p)
    ids = [v.get("vendedor") for v in ventas if v.get("vendedor")]
    nombres = {
        u["_id"]: u.get("nombres_completos") or u.get("usuario") or "Desconocido"
        for u in get_db().users.find({"_id": {"$in": ids}}, {"nombres_completos": 1, "usuario": 1})
    }
    return [
        {
            "vendedor": str(v.get("vendedor") or ""),
            "vendedor_nombre": nombres.get(v.get("vendedor"), "Desconocido"),
            "rol": v.get("rol"),
            "rol_nombre": ETIQUETAS.get(str(v.get("rol")), str(v.get("rol"))),
            "cantidad": len(v.get("tablas") or []),
            "monto": v.get("monto", 0),
            "fecha": v.get("fecha", ""),
        }
        for v in ventas
    ]


def _attend(p: Doc) -> bool:
    """El usuario conectado puede ver y venderle tablas a ``p``."""
    user = current_identity().user
    return bool(user) and ParticipantService.can_attend(user or {}, p)


@bp.get("/participante/<participante_id>")
def ver_participante(participante_id: str) -> Response:
    """Ficha del participante con sus ventas (admin, sus vendedores o un rol sin curso si es alumno)."""
    p = _svc().get_participant(require_object_id(participante_id, "ID de participante inválido."))
    if not _attend(p):
        raise Forbidden("No tiene permiso para ver este participante.")
    info = serialize_mongo_doc({k: v for k, v in p.items() if k != "ventas"})
    return jsonify({"success": True, "participante": {**info, "ventas": _sellers_of(p)}})


@bp.get("/participante/cedula/<string:cedula>")
def participante_por_cedula(cedula: str) -> Response:
    svc = _svc()
    p = svc.by_cedula(cedula)
    info = {
        "_id": str(p["_id"]),
        "nombre": p.get("nombre", ""),
        "apellido": p.get("apellido", ""),
        "cedula": p.get("cedula", ""),
        "tipo": p.get("tipo", ""),
        "correo": p.get("correo", "") if _attend(p) else "",
        "nivelCurso": p.get("nivelCurso", ""),
        "paralelo": p.get("paralelo", ""),
        # Si el usuario conectado puede agregarle tablas (los roles sin curso, a cualquier alumno).
        "puede_agregar": _attend(p),
        "ventas": _sellers_of(p),
        "tablas": [table_summary(t) for t in svc.tables_of(p)],
    }
    return jsonify({"success": True, "participante": info})


@bp.get("/participante/cedula/<string:cedula>/tablas_pdf")
def participante_tablas_pdf(cedula: str) -> Response:
    svc = _svc()
    tablas = svc.tables_of(svc.by_cedula(cedula))
    if not tablas:
        return jsonify({"success": True, "message": "El participante no tiene tablas asignadas.", "tablas": []})
    pdf = render_cards_pdf(tablas)
    return send_file(BytesIO(pdf), mimetype="application/pdf", as_attachment=True, download_name=f"tablas_{cedula}.pdf")


@bp.post("/eliminarTablaAsignada")
def eliminar_tabla_asignada() -> Response:
    data = json_body()
    participante_id, serial = data.get("participante_id"), data.get("serial")
    if not participante_id or not serial:
        raise ApiError("Se requieren 'participante_id' y 'serial'.")
    _svc().remove_table_by_serial(
        require_object_id(participante_id, "ID de participante inválido."), str(serial), data.get("usuario_id")
    )
    return jsonify(
        {
            "success": True,
            "message": f"La tabla {serial} fue removida correctamente del participante y su estado actualizado.",
        }
    )


@bp.post("/participante/<participante_id>/tablas/<tipo_usuario>")
def agregar_tablas_participante(participante_id: str, tipo_usuario: str) -> Response:
    data = json_body()
    pid = try_object_id(participante_id)
    if pid is None or (data.get("usuario_id") and try_object_id(data["usuario_id"]) is None):
        raise ApiError("ID inválido.")
    refs = data.get("tablas") or []
    if not isinstance(refs, list):
        raise ApiError("El campo 'tablas' debe ser una lista.")
    seriales = _svc().add_tables(
        pid,
        refs,
        data.get("usuario_id"),
        data.get("cantidad"),
        allow_serials=current_identity().is_admin,
        rol_venta=data.get("rol_venta"),
    )
    _mail().notify(pid)
    return jsonify({"success": True, "message": "Tablas agregadas correctamente.", "seriales": seriales})


@bp.delete("/participante/<participante_id>/tabla/<tabla_id>/<tipo_usuario>")
def eliminar_tabla_de_participante(participante_id: str, tabla_id: str, tipo_usuario: str) -> Response:
    data = json_body()
    if not data.get("usuario_id"):
        raise ApiError("Debe proporcionar el ID del usuario.")
    message = "ID de participante, tabla o usuario inválido."
    _svc().remove_table(
        require_object_id(participante_id, message),
        require_object_id(tabla_id, message),
        require_object_id(data["usuario_id"], message),
    )
    return jsonify({"success": True, "message": "Tabla eliminada correctamente del participante."})


@bp.delete("/participante/<participante_id>/<tipo_usuario>")
def eliminar_participante(participante_id: str, tipo_usuario: str) -> Response:
    data = json_body()
    if not data.get("usuario_id"):
        raise ApiError("Debe proporcionar el ID del usuario.")
    message = "ID de usuario o participante inválido."
    liberadas = _svc().delete(
        require_object_id(participante_id, message), require_object_id(data["usuario_id"], message)
    )
    return jsonify(
        {
            "success": True,
            "message": "Participante eliminado correctamente. Tablas liberadas.",
            "tablas_liberadas": liberadas,
        }
    )


def _serialize_all(docs: Iterable[Doc]) -> list[dict[str, Any]]:
    return [serialize_mongo_doc(p) for p in docs]


def _sold_by_query(oid: Any) -> dict[str, Any]:
    """Participantes que registró el usuario o a los que les vendió tablas."""
    return {"$or": [{"registrado_por": oid}, {"ventas.vendedor": oid}]}


@bp.get("/participantes/por-usuario/<usuario_id>")
def participantes_por_usuario(usuario_id: str) -> Response:
    """Participantes del usuario (o todos si el usuario es administrador)."""
    oid = require_object_id(usuario_id, "El ID del usuario no es válido.")
    cols = get_db()
    usuario = cols.users.find_one({"_id": oid}, {"password": 0})
    if not usuario:
        raise ApiError("Usuario no encontrado.", 404)
    admin = is_admin(usuario)
    participantes = _serialize_all(cols.participants.find({} if admin else _sold_by_query(oid)))
    return jsonify(
        {
            "success": True,
            "usuario": serialize_mongo_doc(usuario),
            "participantes": participantes,
            "es_admin": admin,
            "tipo_usuario": safe_int(usuario.get("tipo_usuario"), 1),
            "total_participantes": len(participantes),
        }
    )


@bp.get("/participantes/todos/admin")
def todos_participantes_admin() -> Response:
    """Todos los participantes. Requiere ``?usuario_id=`` de un administrador."""
    usuario_id = request.args.get("usuario_id")
    if not usuario_id:
        raise ApiError("Debe proporcionar usuario_id de un administrador.")
    cols = get_db()
    usuario = cols.users.find_one(
        {"_id": require_object_id(usuario_id, "ID de usuario inválido.")}, {"tipo_usuario": 1}
    )
    if not usuario:
        raise ApiError("Usuario no encontrado.", 404)
    if not is_admin(usuario):
        raise Forbidden("Acceso denegado. Solo administradores pueden ver todos los participantes.")
    participantes = _serialize_all(cols.participants.find({}))
    return jsonify({"success": True, "participantes": participantes, "total_participantes": len(participantes)})


@bp.get("/participantes")
def obtener_participantes() -> Response:
    """Participantes de ``usuario_id``; el administrador ve todos si no filtra.

    Un animador solo ve los suyos, aunque envíe ``tipo_usuario=0``.
    """
    identity = current_identity()
    usuario_id = request.args.get("usuario_id") or identity.user_id
    query: dict[str, Any] = {}
    if not identity.is_admin or (request.args.get("tipo_usuario") != "0" and request.args.get("usuario_id")):
        query = _sold_by_query(require_object_id(usuario_id, "ID de usuario inválido."))
    participantes = _serialize_all(get_db().participants.find(query))
    return jsonify({"success": True, "participantes": participantes, "count": len(participantes)})
