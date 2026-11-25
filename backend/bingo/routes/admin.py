"""CRUD de animadores y estudiantes, vaciado de participantes y nuevo juego (solo administrador)."""

from __future__ import annotations

import logging

from flask import Blueprint, Response, current_app, jsonify, request, send_file

from ..auth import current_identity, require_admin
from ..config import Settings
from ..db import get_db
from ..errors import ApiError, NotFound
from ..services.animators import AnimatorService
from ..services.animators_import import AnimatorImport
from ..services.new_game import NewGameService
from ..services.purge import ParticipantPurge
from ..services.students import StudentService, serialize_student
from ..services.students_import import StudentImport
from ..utils import json_body, safe_int

logger = logging.getLogger(__name__)
bp = Blueprint("admin", __name__, url_prefix="/api")


def _settings() -> Settings:
    settings: Settings = current_app.config["SETTINGS"]
    return settings


def _animators() -> AnimatorService:
    return AnimatorService(get_db(), _settings().staff_domain)


def _students() -> StudentService:
    return StudentService(get_db(), _settings().student_domains)


# ------------------------------------------------------------ animadores
@bp.get("/animadores")
@require_admin
def listar_animadores() -> Response:
    animadores = _animators().list_all(request.args.get("search", "").strip())
    return jsonify({"success": True, "animadores": animadores, "total": len(animadores)})


@bp.get("/animadores/<animador_id>")
@require_admin
def obtener_animador(animador_id: str) -> Response:
    svc = _animators()
    return jsonify({"success": True, "animador": svc.serialize(svc.get(animador_id))})


@bp.get("/cursos")
@require_admin
def listar_cursos() -> Response:
    """Cursos (paralelos) con su número de alumnos y el animador asignado, si tiene."""
    cursos = _animators().courses()
    return jsonify({"success": True, "cursos": cursos, "total": len(cursos)})


@bp.post("/animadores")
@require_admin
def crear_animador() -> tuple[Response, int]:
    data = json_body()
    animador = _animators().create(data, reassign=bool(data.get("reasignar")))
    return jsonify({"success": True, "message": "Animador creado.", "animador": animador}), 201


@bp.put("/animadores/<animador_id>")
@require_admin
def actualizar_animador(animador_id: str) -> Response:
    data = json_body()
    animador = _animators().update(animador_id, data, reassign=bool(data.get("reasignar")))
    return jsonify({"success": True, "message": "Animador actualizado.", "animador": animador})


@bp.post("/animadores/lote")
@require_admin
def crear_vendedores_lote() -> tuple[Response, int]:
    """Alta de varios vendedores solo con su correo (el nombre se completa en su primer ingreso)."""
    data = json_body()
    result = _animators().create_batch(data.get("correos"), data.get("rol"))
    message = f"Se crearon {len(result['creados'])} vendedores."
    return jsonify({"success": True, "message": message, **result}), 201


def _upload() -> tuple[bytes, str]:
    file = request.files.get("archivo")
    if file is None or not file.filename:
        raise ApiError("Seleccione el PDF del DECE o un Excel (.xlsx) con los animadores.")
    data: bytes = file.read()
    return data, file.filename


def _animator_import() -> AnimatorImport:
    s = _settings()
    return AnimatorImport(get_db(), s.staff_domain, s.backup_dir)


@bp.post("/animadores/importar/vista-previa")
@require_admin
def vista_previa_animadores() -> Response:
    """Analiza la lista oficial sin guardar nada: nuevos, cambios, quiénes pierden acceso y errores."""
    data, nombre = _upload()
    return jsonify({"success": True, **_animator_import().preview(data, nombre)})


@bp.post("/animadores/importar")
@require_admin
def importar_animadores() -> Response:
    """Aplica la lista oficial: correo y curso de cada animador (con respaldo previo)."""
    data, nombre = _upload()
    result = _animator_import().apply(data, request.form.get("confirmacion"), nombre)
    logger.warning(
        "Animadores importados por %s: %s nuevos, %s actualizados, %s sin acceso, respaldo %s",
        current_identity().email,
        result["nuevos"],
        result["actualizados"],
        result["pierden_acceso"],
        result["respaldo"],
    )
    message = f"Lista aplicada: {result['validas']} animadores con acceso."
    return jsonify({"success": True, "message": message, **result})


@bp.get("/accesos-rechazados")
@require_admin
def accesos_rechazados() -> Response:
    """Correos del personal que intentaron entrar sin estar autorizados (para habilitarlos)."""
    intentos = [
        {k: d.get(k) for k in ("correo", "nombre", "intentos", "ultimo")}
        for d in get_db().access_log.find().sort("ultimo", -1).limit(200)
    ]
    return jsonify({"success": True, "intentos": intentos})


@bp.delete("/accesos-rechazados")
@require_admin
def descartar_acceso_rechazado() -> Response:
    get_db().access_log.delete_one({"correo": str(request.args.get("correo", "")).strip().lower()})
    return jsonify({"success": True})


@bp.delete("/animadores/<animador_id>")
@require_admin
def eliminar_animador(animador_id: str) -> Response:
    _animators().delete(animador_id)
    return jsonify({"success": True, "message": "Animador eliminado."})


# ----------------------------------------------------------- estudiantes
@bp.get("/estudiantes")
@require_admin
def listar_estudiantes() -> Response:
    result = _students().search(
        request.args.get("search", "").strip(),
        safe_int(request.args.get("page"), 1),
        safe_int(request.args.get("per_page"), 25),
        {k: request.args.get(k, "").strip() for k in ("curso", "especialidad", "nivel", "paralelo", "correo")},
    )
    return jsonify({"success": True, **result})


def _excel_bytes() -> bytes:
    file = request.files.get("excel")
    if file is None or not file.filename:
        raise ApiError("Seleccione el archivo Excel de alumnos (.xlsx).")
    data: bytes = file.read()
    return data


@bp.post("/estudiantes/importar/vista-previa")
@require_admin
def vista_previa_importacion() -> Response:
    """Analiza el Excel sin guardar nada: válidos, errores, altas, bajas y correos conservados."""
    return jsonify({"success": True, **StudentImport(get_db(), _settings().backup_dir).preview(_excel_bytes())})


@bp.post("/estudiantes/importar")
@require_admin
def importar_estudiantes() -> Response:
    """Reemplaza TODOS los estudiantes por los del Excel (con respaldo y conservando correos)."""
    result = StudentImport(get_db(), _settings().backup_dir).replace(_excel_bytes(), request.form.get("confirmacion"))
    logger.warning(
        "Estudiantes reemplazados por %s: %s insertados, %s borrados, respaldo %s",
        current_identity().email,
        result["insertados"],
        result["borrados"],
        result["respaldo"],
    )
    message = f"Se cargaron {result['insertados']} estudiantes."
    return jsonify({"success": True, "message": message, **result})


@bp.get("/estudiantes/<estudiante_id>")
@require_admin
def obtener_estudiante(estudiante_id: str) -> Response:
    return jsonify({"success": True, "estudiante": serialize_student(_students().get(estudiante_id))})


@bp.post("/estudiantes")
@require_admin
def crear_estudiante() -> tuple[Response, int]:
    estudiante = _students().create(json_body())
    return jsonify({"success": True, "message": "Estudiante creado.", "estudiante": estudiante}), 201


@bp.put("/estudiantes/<estudiante_id>")
@require_admin
def actualizar_estudiante(estudiante_id: str) -> Response:
    estudiante = _students().update(estudiante_id, json_body())
    return jsonify({"success": True, "message": "Estudiante actualizado.", "estudiante": estudiante})


@bp.delete("/estudiantes/<estudiante_id>")
@require_admin
def eliminar_estudiante(estudiante_id: str) -> Response:
    _students().delete(estudiante_id)
    return jsonify({"success": True, "message": "Estudiante eliminado."})


# ------------------------------------------------------- participantes
@bp.get("/participantes/vaciar")
@require_admin
def resumen_vaciado() -> Response:
    """Cuántos participantes y tablas se borrarían, y el texto de confirmación."""
    return jsonify({"success": True, **ParticipantPurge(get_db(), _settings().backup_dir).summary()})


@bp.post("/participantes/vaciar")
@require_admin
def vaciar_participantes() -> Response:
    """Borra TODOS los participantes (con respaldo previo) y libera sus tablas."""
    result = ParticipantPurge(get_db(), _settings().backup_dir).purge(json_body().get("confirmacion"))
    n = result["participantes_borrados"]
    logger.warning("Vaciado de participantes por %s: %s", current_identity().email, result)
    return jsonify({"success": True, "message": f"Se eliminaron {n} participantes.", **result})


# ------------------------------------------------------------ nuevo juego
def _new_game() -> NewGameService:
    return NewGameService(get_db(), _settings())


@bp.get("/juego/nuevo")
@require_admin
def resumen_nuevo_juego() -> Response:
    """Lo que se borrará al empezar un juego desde cero, y el texto de confirmación."""
    return jsonify({"success": True, **_new_game().summary()})


@bp.post("/juego/nuevo")
@require_admin
def nuevo_juego() -> Response:
    """Borra tablas, ganadoras, participantes y reservas; genera tablas nuevas y su PDF."""
    data = json_body()
    result = _new_game().start(data.get("cantidad"), data.get("confirmacion"))
    logger.warning("Nuevo juego desde cero por %s: %s", current_identity().email, result)
    n = result["tablas_generadas"]
    return jsonify({"success": True, "message": f"Juego reiniciado con {n} tablas nuevas.", **result})


@bp.get("/juego/tablas.pdf")
@require_admin
def descargar_tablas_pdf() -> Response:
    """PDF de las tablas del último juego generado desde el panel."""
    pdf = _new_game().latest_pdf()
    if pdf is None:
        raise NotFound("Todavía no se ha generado un PDF de tablas desde el panel.")
    return send_file(pdf, mimetype="application/pdf", as_attachment=True, download_name=f"bingo-{pdf.name}")
