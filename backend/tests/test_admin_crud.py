from __future__ import annotations

from typing import Any

import pytest
from flask.testing import FlaskClient

from bingo.db import Collections

from .conftest import Seed, login_as, register

NUEVO = {
    "nombre": "chuchuca  saquinaula diego andres",
    "curso": "EDUCACIÓN GENERAL BÁSICA",
    "especialidad": "Básica Media",
    "nivel": 5,
    "paralelo": "B",
    "correo": "Diego.Chuchuca@uets.edu.ec",
}

ESTUDIANTE = {
    "primer_apellido": "perez",
    "segundo_apellido": "lopez",
    "nombre": "pepe",
    "cedula": "0912345678",
    "curso": "BACHILLERATO",
    "especialidad": "Ciencias",
    "nivel": 2,
    "paralelo": "B",
    "correo": "pepe@est.uets.edu.ec",
}


@pytest.fixture
def admin(client: FlaskClient, seed: Seed) -> FlaskClient:
    login_as(client, "admin")
    return client


# ------------------------------------------------------------ animadores
def test_create_animator_creates_linked_user_and_allows_login(admin: FlaskClient, cols: Collections) -> None:
    resp = admin.post("/api/animadores", json=NUEVO)
    assert resp.status_code == 201, resp.json
    animador = resp.json["animador"]
    assert animador["nombre"] == "CHUCHUCA SAQUINAULA DIEGO ANDRES"
    assert animador["correo"] == "diego.chuchuca@uets.edu.ec"
    assert animador["usuario"] == "CSDA"

    user = cols.users.find_one({"usuario": "CSDA"})
    assert user is not None
    assert (user["tipo_usuario"], user["nivel"], user["paralelo"]) == (1, 5, "B")
    assert "password" not in user

    login_as(admin, "diego.chuchuca@uets.edu.ec")
    assert admin.get("/api/auth/me").json["usuario"]["id"] == str(user["_id"])


def test_create_animator_validations(admin: FlaskClient) -> None:
    assert admin.post("/api/animadores", json={**NUEVO, "correo": "x@gmail.com"}).status_code == 400
    assert admin.post("/api/animadores", json={**NUEVO, "correo": "ana@uets.edu.ec"}).status_code == 409
    assert admin.post("/api/animadores", json={**NUEVO, "nivel": "x"}).status_code == 400
    assert admin.post("/api/animadores", json={**NUEVO, "paralelo": " "}).status_code == 400
    assert admin.post("/api/animadores", json={k: v for k, v in NUEVO.items() if k != "nombre"}).status_code == 400
    # Sin correo se crea igual (aún no podrá iniciar sesión) y el usuario no choca con otro igual.
    sin_correo = {k: v for k, v in NUEVO.items() if k != "correo"}
    assert admin.post("/api/animadores", json=sin_correo).json["animador"]["usuario"] == "CSDA"
    # Mismo nombre en otro curso (un curso solo admite un animador).
    otro = admin.post("/api/animadores", json={**sin_correo, "paralelo": "C"}).json["animador"]
    assert (otro["usuario"], otro["correo"]) == ("CSDA2", "")


def test_list_get_and_search_animators(admin: FlaskClient) -> None:
    admin.post("/api/animadores", json=NUEVO)
    todos = admin.get("/api/animadores").json
    assert todos["total"] == 3
    encontrados = admin.get("/api/animadores", query_string={"search": "chuchuca"}).json["animadores"]
    assert [a["usuario"] for a in encontrados] == ["CSDA"]
    one = admin.get(f"/api/animadores/{encontrados[0]['_id']}").json["animador"]
    assert one["curso"] == NUEVO["curso"]
    assert admin.get("/api/animadores/xx").status_code == 400
    assert admin.get("/api/animadores/" + "0" * 24).status_code == 404


def test_update_animator_syncs_user_and_can_remove_email(admin: FlaskClient, cols: Collections, seed: Seed) -> None:
    ana = cols.animators.find_one({"correo": "ana@uets.edu.ec"})
    assert ana is not None
    resp = admin.put(f"/api/animadores/{ana['_id']}", json={"nivel": 3, "paralelo": "C", "nombre": "Ana Nueva"})
    assert resp.status_code == 200, resp.json
    user = cols.users.find_one({"_id": seed.ana})
    assert user is not None
    assert (user["nivel"], user["paralelo"], user["nombres_completos"]) == (3, "C", "ANA NUEVA")
    assert user["totalTables"] == 10  # no toca la reserva

    assert admin.put(f"/api/animadores/{ana['_id']}", json={"correo": "beto@uets.edu.ec"}).status_code == 409
    assert admin.put(f"/api/animadores/{ana['_id']}", json={"correo": ""}).json["animador"]["correo"] == ""
    assert "correo" not in (cols.animators.find_one({"_id": ana["_id"]}) or {})
    assert admin.post("/api/auth/google", json={"credential": "ana@uets.edu.ec"}).status_code == 403


def test_legacy_animator_is_linked_by_name_and_keeps_tutor_field(
    admin: FlaskClient, cols: Collections, seed: Seed
) -> None:
    legacy_id = cols.animators.insert_one(
        {"tutor": "Nombre BETO", "curso": "X", "especialidad": "Y", "nivel": 1, "paralelo": "Z"}
    ).inserted_id
    resp = admin.put(f"/api/animadores/{legacy_id}", json={"correo": "beto2@uets.edu.ec", "nombre": "Nombre Beto"})
    assert resp.json["animador"]["usuario_id"] == str(seed.beto)
    doc = cols.animators.find_one({"_id": legacy_id})
    assert doc is not None
    assert (doc["tutor"], doc["usuario_id"]) == ("NOMBRE BETO", seed.beto)
    assert "profesor" not in doc


def test_delete_animator(admin: FlaskClient, cols: Collections, seed: Seed) -> None:
    register(admin, seed.ana, "0101", ["CARD00001"])
    login_as(admin, "admin")
    ana = cols.animators.find_one({"correo": "ana@uets.edu.ec"})
    assert ana is not None
    assert admin.delete(f"/api/animadores/{ana['_id']}").status_code == 409  # tiene participantes

    nuevo: dict[str, Any] = admin.post("/api/animadores", json=NUEVO).json["animador"]
    assert admin.delete(f"/api/animadores/{nuevo['_id']}").status_code == 200
    assert cols.users.find_one({"usuario": "CSDA"}) is None
    assert cols.animators.count_documents({"correo": NUEVO["correo"].lower()}) == 0

    huerfano = cols.animators.insert_one({"profesor": "SIN CUENTA"}).inserted_id
    assert admin.delete(f"/api/animadores/{huerfano}").status_code == 200


# ----------------------------------------------------------- estudiantes
def test_student_crud(admin: FlaskClient, cols: Collections) -> None:
    resp = admin.post("/api/estudiantes", json=ESTUDIANTE)
    assert resp.status_code == 201, resp.json
    est = resp.json["estudiante"]
    assert (est["primer_apellido"], est["nombre"], est["nivel"]) == ("PEREZ", "PEPE", 2)
    doc = cols.students.find_one({"Num documento": "0912345678"})
    assert doc is not None
    assert (doc["Primer Apellido"], doc["correo"]) == ("PEREZ", "pepe@est.uets.edu.ec")

    assert admin.get(f"/api/estudiantes/{est['_id']}").json["estudiante"]["cedula"] == "0912345678"
    upd = admin.put(f"/api/estudiantes/{est['_id']}", json={"paralelo": "C", "nivel": 3}).json["estudiante"]
    assert (upd["paralelo"], upd["nivel"], upd["correo"]) == ("C", 3, "pepe@est.uets.edu.ec")
    upd = admin.put(f"/api/estudiantes/{est['_id']}", json={"correo": None}).json["estudiante"]
    assert upd["correo"] == ""

    assert admin.delete(f"/api/estudiantes/{est['_id']}").status_code == 200
    assert admin.get(f"/api/estudiantes/{est['_id']}").status_code == 404


def test_student_validations(admin: FlaskClient) -> None:
    assert admin.post("/api/estudiantes", json={**ESTUDIANTE, "correo": "pepe@gmail.com"}).status_code == 400
    assert admin.post("/api/estudiantes", json={**ESTUDIANTE, "cedula": "09-12"}).status_code == 400
    assert admin.post("/api/estudiantes", json={**ESTUDIANTE, "nivel": 0}).status_code == 400
    assert admin.post("/api/estudiantes", json={**ESTUDIANTE, "nombre": ""}).status_code == 400
    sin_correo = {k: v for k, v in ESTUDIANTE.items() if k != "correo"}
    first = admin.post("/api/estudiantes", json=sin_correo).json["estudiante"]
    assert first["correo"] == ""
    assert admin.post("/api/estudiantes", json=ESTUDIANTE).status_code == 409  # cédula repetida
    otro = admin.post("/api/estudiantes", json={**ESTUDIANTE, "cedula": "0999"}).json["estudiante"]
    assert admin.put(f"/api/estudiantes/{first['_id']}", json={"correo": ESTUDIANTE["correo"]}).status_code == 409
    assert admin.put(f"/api/estudiantes/{otro['_id']}", json={}).status_code == 200


def test_student_search_and_pagination(admin: FlaskClient) -> None:
    for i in range(30):
        admin.post("/api/estudiantes", json={**ESTUDIANTE, "cedula": f"09{i:08d}", "correo": None})
    page = admin.get("/api/estudiantes", query_string={"per_page": 25}).json
    assert (page["total"], len(page["estudiantes"]), page["page"]) == (30, 25, 1)
    page2 = admin.get("/api/estudiantes", query_string={"per_page": 25, "page": 2}).json
    assert len(page2["estudiantes"]) == 5
    found = admin.get("/api/estudiantes", query_string={"search": "0900000007"}).json
    assert found["total"] == 1
    assert admin.get("/api/estudiantes", query_string={"per_page": 999}).json["per_page"] == 100


def test_update_legacy_animator_without_user_creates_account(admin: FlaskClient, cols: Collections) -> None:
    legacy_id = cols.animators.insert_one(
        {
            "profesor": "MOGROVEJO ERICK",
            "curso": "BACHILLERATO",
            "especialidad": "Ciencias",
            "nivel": 1,
            "paralelo": "F1",
        }
    ).inserted_id
    resp = admin.put(f"/api/animadores/{legacy_id}", json={"correo": "erick@uets.edu.ec"})
    animador = resp.json["animador"]
    assert animador["usuario"] == "ME"
    user = cols.users.find_one({"usuario": "ME"})
    assert user is not None
    assert (user["tipo_usuario"], user["paralelo"], user["nombres_completos"]) == (1, "F1", "MOGROVEJO ERICK")
    login_as(admin, "erick@uets.edu.ec")
    assert admin.get("/api/auth/me").json["usuario"]["rol"] == "animador"


def test_student_email_in_staff_domain(admin: FlaskClient) -> None:
    """Los correos de estudiantes 2026 son ``nombre.apellido.est@uets.edu.ec``."""
    body = {**ESTUDIANTE, "correo": "Pepe.PerezL.est@uets.edu.ec"}
    assert admin.post("/api/estudiantes", json=body).json["estudiante"]["correo"] == "pepe.perezl.est@uets.edu.ec"


def test_new_animator_starts_without_sales(admin: FlaskClient, seed: Seed) -> None:
    nuevo = admin.post("/api/animadores", json=NUEVO).json["animador"]
    assert nuevo["ventas"] == {"tablas": 0, "monto": 0}
    # Ya no existen las reservas de tablas por vendedor.
    assert admin.post(f"/api/users/{nuevo['usuario_id']}/assign_tables", json={}).status_code == 404
