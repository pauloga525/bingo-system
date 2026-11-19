"""Curso del animador conectado: ver y editar a sus alumnos.

El curso sale de ``Animadores`` (el que inició sesión, por su correo). El
animador solo ve y modifica alumnos de ese curso, y no puede moverlos a otro.
"""

from __future__ import annotations

from flask import Blueprint, Response, current_app, jsonify, request

from ..auth import current_identity
from ..config import Settings
from ..db import get_db
from ..errors import NotFound
from ..services.animators import AnimatorService, Course, course_label, course_of
from ..services.students import StudentService
from ..utils import json_body

bp = Blueprint("mi_curso", __name__, url_prefix="/api/mi-curso")


def _settings() -> Settings:
    settings: Settings = current_app.config["SETTINGS"]
    return settings


def _students() -> StudentService:
    return StudentService(get_db(), _settings().student_domains)


def _my_course() -> Course:
    animator = AnimatorService(get_db(), _settings().staff_domain).by_email(current_identity().email)
    course = course_of(animator)
    if course is None:
        raise NotFound("No tiene un curso asignado. Pida al administrador que le asigne uno.")
    return course


@bp.get("")
def ver_mi_curso() -> Response:
    course = _my_course()
    estudiantes = _students().in_course(course, request.args.get("search", "").strip())
    return jsonify(
        {
            "success": True,
            "curso": {**course, "nombre": course_label(course)},
            "estudiantes": estudiantes,
            "total": len(estudiantes),
        }
    )


@bp.post("/estudiantes")
def crear_alumno() -> tuple[Response, int]:
    estudiante = _students().create_in_course(json_body(), _my_course())
    return jsonify({"success": True, "message": "Estudiante creado.", "estudiante": estudiante}), 201


@bp.put("/estudiantes/<estudiante_id>")
def actualizar_alumno(estudiante_id: str) -> Response:
    estudiante = _students().update_in_course(estudiante_id, json_body(), _my_course())
    return jsonify({"success": True, "message": "Estudiante actualizado.", "estudiante": estudiante})


@bp.delete("/estudiantes/<estudiante_id>")
def eliminar_alumno(estudiante_id: str) -> Response:
    _students().delete_in_course(estudiante_id, _my_course())
    return jsonify({"success": True, "message": "Estudiante eliminado."})
