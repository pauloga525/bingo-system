"""Cursos de los animadores (uno por paralelo), alumnos del curso y acceso al tablero."""

from __future__ import annotations

from typing import Any

import pytest
from flask.testing import FlaskClient

from bingo.db import Collections

from .conftest import Seed, board_login, login_as

CURSO_A = {"curso": "BACHILLERATO", "especialidad": "Ciencias", "nivel": 1, "paralelo": "A"}  # de ANA
CURSO_B = {**CURSO_A, "paralelo": "B"}  # de BETO
SIN_CURSO = dict.fromkeys(CURSO_A, "")


def _alumno(cols: Collections, cedula: str, apellido: str, curso: dict[str, Any] = CURSO_A) -> Any:
    return cols.students.insert_one(
        {
            "Primer Apellido": apellido,
            "Segundo Apellido": "X",
            "Nombre": "ALUMNO",
            "Num documento": cedula,
            "Curso": curso["curso"],
            "Especialidad": curso["especialidad"],
            "Nivel": curso["nivel"],
            "Paralelo": curso["paralelo"],
        }
    ).inserted_id


def _animador(cols: Collections, correo: str) -> dict[str, Any]:
    doc = cols.animators.find_one({"correo": correo})
    assert doc is not None
    return doc


@pytest.fixture
def admin(client: FlaskClient, seed: Seed) -> FlaskClient:
    login_as(client, "admin")
    return client


# --------------------------------------------------- un curso, un animador
def test_course_taken_by_other_animator_is_rejected(admin: FlaskClient, cols: Collections) -> None:
    beto = _animador(cols, "beto@uets.edu.ec")
    resp = admin.put(f"/api/animadores/{beto['_id']}", json=CURSO_A)
    assert resp.status_code == 409
    assert resp.json["curso_ocupado"] is True
    assert resp.json["animador_actual"] == "Nombre ANA"
    assert _animador(cols, "beto@uets.edu.ec")["paralelo"] == "B"  # sin cambios

    nuevo = admin.post("/api/animadores", json={"nombre": "Carla", **CURSO_A})
    assert nuevo.status_code == 409


def test_reassign_moves_course_and_frees_previous_holder(admin: FlaskClient, cols: Collections, seed: Seed) -> None:
    beto = _animador(cols, "beto@uets.edu.ec")
    resp = admin.put(f"/api/animadores/{beto['_id']}", json={**CURSO_A, "reasignar": True})
    assert resp.status_code == 200, resp.json
    assert resp.json["animador"]["paralelo"] == "A"

    ana = _animador(cols, "ana@uets.edu.ec")
    assert "curso" not in ana and "paralelo" not in ana
    user_ana = cols.users.find_one({"_id": seed.ana})
    assert user_ana is not None and "paralelo" not in user_ana
    user_beto = cols.users.find_one({"_id": seed.beto})
    assert user_beto is not None and user_beto["paralelo"] == "A"

    lista = {a["nombre"]: a for a in admin.get("/api/animadores").json["animadores"]}
    assert lista["Nombre ANA"]["curso_asignado"] is False
    assert lista["Nombre BETO"]["curso_asignado"] is True


def test_unassign_course_and_create_without_course(admin: FlaskClient, cols: Collections) -> None:
    ana = _animador(cols, "ana@uets.edu.ec")
    resp = admin.put(f"/api/animadores/{ana['_id']}", json=SIN_CURSO)
    assert resp.status_code == 200, resp.json
    assert resp.json["animador"]["curso_asignado"] is False

    # Ya libre, otro animador puede tomarlo sin reasignar.
    creado = admin.post("/api/animadores", json={"nombre": "Carla Ruiz", **CURSO_A})
    assert creado.status_code == 201, creado.json
    sin_curso = admin.post("/api/animadores", json={"nombre": "Dario"})
    assert sin_curso.status_code == 201, sin_curso.json
    assert sin_curso.json["animador"]["curso_asignado"] is False

    assert admin.post("/api/animadores", json={"nombre": "Eva", "curso": "BACHILLERATO"}).status_code == 400


def test_same_paralelo_in_other_level_is_a_different_course(admin: FlaskClient) -> None:
    resp = admin.post("/api/animadores", json={"nombre": "Fabio", **CURSO_A, "nivel": 2})
    assert resp.status_code == 201, resp.json


def test_courses_list_shows_students_and_holder(admin: FlaskClient, cols: Collections) -> None:
    _alumno(cols, "0101", "PEREZ")
    _alumno(cols, "0102", "LOPEZ")
    _alumno(cols, "0103", "MORA", {**CURSO_A, "paralelo": "C"})
    cursos = admin.get("/api/cursos").json["cursos"]
    por_paralelo = {c["paralelo"]: c for c in cursos}
    assert por_paralelo["A"]["estudiantes"] == 2 and por_paralelo["A"]["animador"] == "Nombre ANA"
    assert por_paralelo["B"]["estudiantes"] == 0 and por_paralelo["B"]["animador"] == "Nombre BETO"
    assert por_paralelo["C"]["estudiantes"] == 1 and por_paralelo["C"]["animador"] is None


def test_courses_list_is_admin_only(client: FlaskClient, seed: Seed) -> None:
    assert client.get("/api/cursos").status_code == 403  # sesión de ANA


# ------------------------------------------------------- alumnos del curso
def test_animator_sees_only_students_of_own_course(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    _alumno(cols, "0101", "PEREZ")
    _alumno(cols, "0102", "LOPEZ")
    _alumno(cols, "0201", "OTRO", CURSO_B)
    data = client.get("/api/mi-curso").json
    assert data["curso"]["paralelo"] == "A"
    assert [e["primer_apellido"] for e in data["estudiantes"]] == ["LOPEZ", "PEREZ"]
    assert client.get("/api/mi-curso", query_string={"search": "per"}).json["total"] == 1


def test_animator_student_crud_is_scoped_to_course(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    ajeno = _alumno(cols, "0201", "OTRO", CURSO_B)
    nuevo = {"primer_apellido": "nuevo", "nombre": "luis", "cedula": "0999", **CURSO_B}
    resp = client.post("/api/mi-curso/estudiantes", json=nuevo)
    assert resp.status_code == 201, resp.json
    creado = resp.json["estudiante"]
    assert creado["paralelo"] == "A"  # el curso lo pone el servidor, no el cliente

    edit = client.put(f"/api/mi-curso/estudiantes/{creado['_id']}", json={"nombre": "Luis Alberto", "paralelo": "B"})
    assert edit.status_code == 200, edit.json
    assert (edit.json["estudiante"]["nombre"], edit.json["estudiante"]["paralelo"]) == ("LUIS ALBERTO", "A")

    assert client.put(f"/api/mi-curso/estudiantes/{ajeno}", json={"nombre": "X"}).status_code == 404
    assert client.delete(f"/api/mi-curso/estudiantes/{ajeno}").status_code == 404
    assert client.delete(f"/api/mi-curso/estudiantes/{creado['_id']}").status_code == 200
    assert cols.students.count_documents({}) == 1


def test_animator_without_course_gets_404(admin: FlaskClient, client: FlaskClient, cols: Collections) -> None:
    ana = _animador(cols, "ana@uets.edu.ec")
    admin.put(f"/api/animadores/{ana['_id']}", json=SIN_CURSO)
    login_as(client, "ana")
    assert client.get("/api/mi-curso").status_code == 404


def test_reassigned_animator_sees_new_course(admin: FlaskClient, client: FlaskClient, cols: Collections) -> None:
    _alumno(cols, "0201", "DE_B", CURSO_B)
    ana = _animador(cols, "ana@uets.edu.ec")
    assert admin.put(f"/api/animadores/{ana['_id']}", json={**CURSO_B, "reasignar": True}).status_code == 200
    login_as(client, "ana")
    assert [e["primer_apellido"] for e in client.get("/api/mi-curso").json["estudiantes"]] == ["DE_B"]
    login_as(client, "beto")
    assert client.get("/api/mi-curso").status_code == 404


def test_students_cannot_use_my_course(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    oid = _alumno(cols, "0101", "PEREZ")
    cols.students.update_one({"_id": oid}, {"$set": {"correo": "pepe@est.uets.edu.ec"}})
    login_as(client, "pepe@est.uets.edu.ec")
    assert client.get("/api/mi-curso").status_code == 403


# ------------------------------------------------- tablero: solo admin
def test_board_pages_redirect_to_login_without_session(client: FlaskClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 302
    assert resp.headers["Location"].startswith("/tablero/login")
    assert client.get("/pages/masterTable.html").status_code == 302
    assert client.get("/tablero/login").status_code == 200
    assert client.get("/health").status_code in (200, 503)  # monitoreo sigue público


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/get_cards"),
        ("post", "/mark"),
        ("get", "/progress"),
        ("post", "/reset"),
        ("post", "/generate"),
        ("post", "/upload"),
        ("post", "/winner_pdf"),
        ("get", "/tabla_ganadora"),
        ("get", "/test_mongo"),
    ],
)
def test_board_api_requires_admin_session(client: FlaskClient, method: str, path: str) -> None:
    assert getattr(client, method)(path).status_code == 401


def test_animator_cannot_open_board(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    resp = board_login(client, cols, "ana@uets.edu.ec")
    assert resp.status_code == 403
    assert client.get("/get_cards").status_code == 401


def test_admin_google_login_opens_board_and_logout_closes_it(client: FlaskClient, cols: Collections) -> None:
    resp = board_login(client, cols)
    assert resp.status_code == 200 and resp.json["next"] == "/"
    assert client.get("/").status_code == 200
    assert client.get("/get_cards").status_code != 401
    assert client.post("/tablero/salir").status_code == 303
    assert client.get("/get_cards").status_code == 401


def test_panel_handoff_with_admin_token(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    ana_token = login_as(client, "ana")
    assert client.post("/tablero/sesion", data={"token": ana_token}).status_code == 403
    assert client.post("/tablero/sesion", data={"token": "falso"}).status_code == 401
    # Abierto sin formulario (GET): lleva al login normal.
    assert client.get("/tablero/sesion").headers["Location"].startswith("/tablero/login")

    admin_token = login_as(client, "admin")
    resp = client.post("/tablero/sesion", data={"token": admin_token, "next": "https://malo.example"})
    assert resp.status_code == 303 and resp.headers["Location"] == "/"
    assert client.get("/progress").status_code != 401


def test_board_session_is_revoked_when_admin_loses_access(client: FlaskClient, cols: Collections, app: Any) -> None:
    assert board_login(client, cols).status_code == 200
    app.config["SETTINGS"].__dict__["admin_emails"] = "otro@uets.edu.ec"
    assert client.get("/get_cards").status_code == 401
