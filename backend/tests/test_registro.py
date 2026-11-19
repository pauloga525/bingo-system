from __future__ import annotations

from typing import Any

import pytest
from flask.testing import FlaskClient

from bingo.db import Collections

from .conftest import Seed, logout, register

CORREO = "martin.abadc.est@uets.edu.ec"
DATOS = {"cedula": "0151343134", "nombres": "Martín", "apellidos": "abad cárdenas"}


@pytest.fixture
def alumno(cols: Collections) -> None:
    cols.students.insert_one(
        {
            "Primer Apellido": "ABAD",
            "Segundo Apellido": "CARDENAS",
            "Nombre": "MARTIN ALEJANDRO",
            "Curso": "Educación General Básica",
            "Especialidad": "Básica Media",
            "Nivel": 7,
            "Paralelo": "A",
            "Num documento": "0151343134",
        }
    )


def _login(client: FlaskClient, correo: str = CORREO) -> tuple[int, dict[str, Any]]:
    resp = client.post("/api/auth/google", json={"credential": correo})
    return resp.status_code, resp.json or {}


def _registrar(client: FlaskClient, token: str, **datos: Any) -> tuple[int, dict[str, Any]]:
    resp = client.post("/api/auth/registro", json={"registro_token": token, **DATOS, **datos})
    return resp.status_code, resp.json or {}


def test_unregistered_student_must_register_then_logs_in(
    client: FlaskClient, cols: Collections, seed: Seed, alumno: None
) -> None:
    register(client, seed.ana, "0151343134", ["CARD00001"])
    logout(client)

    status, body = _login(client)
    assert status == 403
    assert body["registro_requerido"] is True
    assert body["correo"] == CORREO

    status, sesion = _registrar(client, body["registro_token"])
    assert status == 200, sesion
    assert (sesion["usuario"]["rol"], sesion["usuario"]["cedula"]) == ("estudiante", "0151343134")
    assert cols.students.find_one({"Num documento": "0151343134"})["correo"] == CORREO  # type: ignore[index]

    client.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {sesion['token']}"
    assert [t["serial"] for t in client.get("/api/mis-tablas").json["tablas"]] == ["CARD00001"]
    # Desde ahora entra directo, sin registrarse otra vez.
    assert _login(client)[0] == 200


@pytest.mark.parametrize(
    "datos",
    [
        {"cedula": "0999999999"},  # cédula inexistente
        {"nombres": "Pedro"},  # el nombre no coincide
        {"apellidos": "Cardenas Abad"},  # el primer apellido no coincide
    ],
)
def test_registration_requires_matching_cedula_and_names(
    client: FlaskClient, cols: Collections, alumno: None, datos: dict[str, str]
) -> None:
    token = _login(client)[1]["registro_token"]
    status, body = _registrar(client, token, **datos)
    assert status == 400
    assert "no coinciden" in body["message"]
    assert cols.students.count_documents({"correo": {"$exists": True}}) == 0


def test_registration_validations(client: FlaskClient, alumno: None) -> None:
    token = _login(client)[1]["registro_token"]
    assert _registrar(client, token, cedula="01-51")[0] == 400
    assert _registrar(client, token, nombres=" ")[0] == 400
    assert _registrar(client, "token-falso")[0] == 401


def test_cedula_already_registered_with_another_email(client: FlaskClient, cols: Collections, alumno: None) -> None:
    cols.students.update_one({"Num documento": "0151343134"}, {"$set": {"correo": "otro.est@uets.edu.ec"}})
    token = _login(client)[1]["registro_token"]
    status, body = _registrar(client, token)
    assert status == 409
    assert "otro correo" in body["message"]


def test_email_already_used_by_another_student(client: FlaskClient, cols: Collections, alumno: None) -> None:
    token = _login(client)[1]["registro_token"]
    cols.students.insert_one({"Primer Apellido": "X", "Nombre": "Y", "Num documento": "1", "correo": CORREO})
    assert _registrar(client, token)[0] == 409


@pytest.mark.parametrize(
    ("correo", "puede_registrarse"),
    [
        ("martin.abadc.est@uets.edu.ec", True),
        ("bguzmanp_estudiante@uets.edu.ec", True),
        ("jdekrioestudiante@uets.edu.ec", True),
        ("alguien@est.uets.edu.ec", True),
        ("profesor.juan@uets.edu.ec", False),  # correo del personal: no es estudiantil
        ("estudiante.falso@uets.edu.ec", False),
    ],
)
def test_only_student_emails_can_register(client: FlaskClient, correo: str, puede_registrarse: bool) -> None:
    status, body = _login(client, correo)
    assert status == 403
    assert bool(body.get("registro_requerido")) is puede_registrarse
    assert ("registro_token" in body) is puede_registrarse
