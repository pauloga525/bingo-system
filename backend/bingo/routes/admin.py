"""CRUD de animadores y estudiantes (solo administrador)."""

from __future__ import annotations

from flask import Blueprint, Response, current_app, jsonify, request

from ..auth import require_admin
from ..config import Settings
from ..db import get_db
from ..services.animators import AnimatorService
from ..services.students import StudentService, serialize_student
from ..utils import json_body, safe_int

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


@bp.post("/animadores")
@require_admin
def crear_animador() -> tuple[Response, int]:
    animador = _animators().create(json_body())
    return jsonify({"success": True, "message": "Animador creado.", "animador": animador}), 201


@bp.put("/animadores/<animador_id>")
@require_admin
def actualizar_animador(animador_id: str) -> Response:
    animador = _animators().update(animador_id, json_body())
    return jsonify({"success": True, "message": "Animador actualizado.", "animador": animador})


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
    )
    return jsonify({"success": True, **result})


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
