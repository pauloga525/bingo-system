from __future__ import annotations

from dataclasses import replace

import mongomock
import pytest
from flask.testing import FlaskClient

from bingo import create_app
from bingo.config import Settings
from bingo.db import Collections

from .conftest import Seed, fake_google_verifier, login_as, logout, register


def _google(client: FlaskClient, credential: object) -> tuple[int, dict]:  # type: ignore[type-arg]
    resp = client.post("/api/auth/google", json={"credential": credential})
    return resp.status_code, resp.json or {}


def _student(cols: Collections, correo: str | None = "pepe@est.uets.edu.ec", cedula: str = "0101") -> None:
    doc = {
        "Primer Apellido": "PEREZ",
        "Segundo Apellido": "LOPEZ",
        "Nombre": "PEPE",
        "Curso": "BACHILLERATO",
        "Especialidad": "Ciencias",
        "Nivel": 2,
        "Paralelo": "B",
        "Num documento": cedula,
    }
    if correo:
        doc["correo"] = correo
    cols.students.insert_one(doc)


# ------------------------------------------------------------------ login
def test_admin_and_animator_login(client: FlaskClient, seed: Seed) -> None:
    status, body = _google(client, "ADMIN@uets.edu.ec")
    assert status == 200
    assert body["usuario"]["rol"] == "admin"
    assert body["usuario"]["tipo_usuario"] == 0
    assert body["usuario"]["id"] == str(seed.admin)
    assert body["token"]

    status, body = _google(client, "ana@uets.edu.ec")
    assert status == 200
    assert (body["usuario"]["rol"], body["usuario"]["id"]) == ("animador", str(seed.ana))


def test_student_login_with_staff_domain_email(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    _student(cols, correo="pepe.perezl.est@uets.edu.ec")
    status, body = _google(client, "Pepe.PerezL.est@uets.edu.ec")
    assert status == 200
    assert (body["usuario"]["rol"], body["usuario"]["cedula"]) == ("estudiante", "0101")


def test_student_login(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    _student(cols)
    status, body = _google(client, "pepe@est.uets.edu.ec")
    assert status == 200
    assert body["usuario"]["rol"] == "estudiante"
    assert body["usuario"]["cedula"] == "0101"
    assert body["usuario"]["nombres"] == "PEPE PEREZ LOPEZ"


@pytest.mark.parametrize(
    ("credential", "status"),
    [
        (None, 400),
        ("invalido", 401),  # firma/audiencia incorrecta
        ("otro@uets.edu.ec", 403),  # del dominio pero no está en la lista
        ("nadie@est.uets.edu.ec", 403),  # estudiante sin correo registrado
        ("ana@gmail.com", 403),  # fuera de los dominios
        ("ana@uets.edu.ec|gmail.com", 403),  # cuenta personal de Google con correo del dominio
    ],
)
def test_login_rejections(client: FlaskClient, seed: Seed, credential: object, status: int) -> None:
    assert _google(client, credential)[0] == status


def test_unverified_email_is_rejected(settings: Settings, mongo: mongomock.MongoClient, seed: Seed) -> None:
    def verifier(token: str, client_id: str) -> dict[str, object]:
        return {**fake_google_verifier(token, client_id), "email_verified": False}

    app = create_app(settings, mongo, verifier)
    assert _google(app.test_client(), "ana@uets.edu.ec")[0] == 403


def test_login_requires_configuration(settings: Settings, mongo: mongomock.MongoClient) -> None:
    app = create_app(replace(settings, google_client_id="", secret_key=""), mongo, fake_google_verifier)
    client = app.test_client()
    assert _google(client, "ana@uets.edu.ec")[0] == 503
    assert client.get("/api/auth/config").json["google_client_id"] == ""


def test_admin_email_without_admin_user(client: FlaskClient, cols: Collections) -> None:
    assert _google(client, "admin@uets.edu.ec")[0] == 403
    cols.users.insert_one({"usuario": "ADM", "tipo_usuario": 1})  # existe pero no es admin
    assert _google(client, "admin@uets.edu.ec")[0] == 403


def test_auth_config_is_public(client: FlaskClient) -> None:
    body = client.get("/api/auth/config").json
    assert body == {"google_client_id": "test-client-id", "dominios": ["uets.edu.ec", "est.uets.edu.ec"]}


# ----------------------------------------------------------------- sesión
def test_api_requires_a_valid_session(client: FlaskClient, seed: Seed) -> None:
    logout(client)
    assert client.get("/api/tablas").status_code == 401
    assert client.get("/api/tablas", headers={"Authorization": "Bearer manipulado"}).status_code == 401
    assert client.get("/api/tablas", headers={"Authorization": "Basic abc"}).status_code == 401
    # Preflight CORS y rutas de la mesa de juego no requieren sesión.
    assert client.options("/api/tablas").status_code != 401
    assert client.get("/health").status_code == 200


def test_me_and_revoked_access(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    assert client.get("/api/auth/me").json["usuario"]["usuario"] == "ANA"
    cols.animators.update_one({"correo": "ana@uets.edu.ec"}, {"$unset": {"correo": ""}})
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401
    assert "revocado" in resp.json["message"]


def test_expired_session(client: FlaskClient, seed: Seed, monkeypatch: pytest.MonkeyPatch) -> None:
    import time

    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + 9 * 3600)
    assert client.get("/api/auth/me").status_code == 401


def test_animator_cannot_act_as_another_user(client: FlaskClient, seed: Seed) -> None:
    body = {"usuario_id": str(seed.beto), "cantidad_tablas": 1}
    assert client.post("/api/obtenerTablasConsecutivas", json=body).status_code == 403
    assert register(client, seed.ana, "0101", ["CARD00001"]).status_code == 201
    login_as(client, "ana")
    body = {"nombre": "J", "cedula": "2", "registrado_por": str(seed.beto), "tablas": ["CARD00011"]}
    assert client.post("/api/registrarParticipante", json=body).status_code == 403


def test_animator_cannot_use_admin_endpoints(client: FlaskClient, seed: Seed) -> None:
    assert client.get("/api/animadores").status_code == 403
    assert client.get("/api/estudiantes").status_code == 403
    assert client.get("/api/reportes").status_code == 403
    assert client.get(f"/api/validar-tablas/{seed.beto}").status_code == 403


# ------------------------------------------------------------- estudiante
def test_student_sees_only_their_tables(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    register(client, seed.ana, "0101", ["CARD00002", "CARD00001"])
    register(client, seed.ana, "0202", ["CARD00003"])
    _student(cols)
    login_as(client, "pepe@est.uets.edu.ec")

    resp = client.get("/api/mis-tablas")
    assert resp.status_code == 200
    assert resp.json["estudiante"]["cedula"] == "0101"
    assert [t["serial"] for t in resp.json["tablas"]] == ["CARD00001", "CARD00002"]
    assert len(resp.json["tablas"][0]["matrix"]) == 5

    # El resto de la API no está disponible para estudiantes.
    for url in ("/api/tablas", "/api/participantes", "/api/participante/cedula/0202", "/api/estudiante/0101"):
        assert client.get(url).status_code == 403, url


def test_student_without_purchases_and_staff_on_student_endpoint(
    client: FlaskClient, cols: Collections, seed: Seed
) -> None:
    assert client.get("/api/mis-tablas").status_code == 403  # sesión de ANA (animadora)
    _student(cols, cedula="")
    login_as(client, "pepe@est.uets.edu.ec")
    assert client.get("/api/mis-tablas").json["tablas"] == []


# ---------------------------------------------------------- consulta pública
def test_public_consulta_by_cedula(client: FlaskClient, seed: Seed) -> None:
    register(client, seed.ana, "0912345678", ["CARD00002", "CARD00001"])
    logout(client)
    resp = client.get("/api/consulta/0912345678")
    assert resp.status_code == 200
    participante = resp.json["participante"]
    assert participante["nombre"] == "Juan"
    assert [t["serial"] for t in participante["tablas"]] == ["CARD00001", "CARD00002"]
    # Solo nombre y tablas: nada de celular, cédula, animador, etc.
    assert set(participante) == {"nombre", "apellido", "tablas"}
    assert set(participante["tablas"][0]) == {"serial", "matrix", "won"}

    assert client.get("/api/consulta/0999999999").status_code == 404
    assert client.get("/api/consulta/abc").status_code == 400
    assert client.get("/api/consulta/123").status_code == 400


def test_public_consulta_participant_without_tables(client: FlaskClient, cols: Collections) -> None:
    cols.participants.insert_one({"nombre": "Sin", "apellido": "Tablas", "cedula": "0911111111", "tablas": []})
    assert client.get("/api/consulta/0911111111").json["participante"]["tablas"] == []
