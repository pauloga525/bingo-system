"""Roles de vendedores (secretaría, financiero, parroquia, oratorio), promociones y reportes."""

from __future__ import annotations

from typing import Any

import pytest
from bson import ObjectId
from flask.testing import FlaskClient

from bingo.db import Collections
from bingo.domain.pricing import calcular_total, desglose
from bingo.domain.roles import clean_rol, rol_de, solo_externos
from bingo.errors import ApiError
from tests.conftest import Seed, login_as


@pytest.mark.parametrize(
    ("n", "total", "promos"),
    [
        (0, 0, (0, 0, 0)),
        (1, 3, (0, 0, 1)),
        (2, 5, (0, 1, 0)),
        (3, 8, (0, 1, 1)),
        (4, 10, (0, 2, 0)),
        (5, 10, (1, 0, 0)),
        (6, 13, (1, 0, 1)),
        (7, 15, (1, 1, 0)),
        (10, 20, (2, 0, 0)),
        (12, 25, (2, 1, 0)),
    ],
)
def test_promociones(n: int, total: int, promos: tuple[int, int, int]) -> None:
    d = desglose(n)
    assert calcular_total(n) == total
    assert (d["paquete_5"], d["paquete_2"], d["suelta"]) == promos
    assert d["paquete_5"] * 10 + d["paquete_2"] * 5 + d["suelta"] * 3 == total


def test_roles_helpers() -> None:
    assert clean_rol("") == "animador"
    assert clean_rol(" Secretaria ") == "secretaria"
    with pytest.raises(ApiError):
        clean_rol("gerente")
    assert rol_de(None) == "animador"
    assert rol_de({"tipo_usuario": 0}) == "admin"
    assert rol_de({"rol": "oratorio"}) == "oratorio"
    assert rol_de({"rol": "desconocido"}) == "animador"
    assert solo_externos("parroquia") and not solo_externos("animador")


def _crear_vendedor(admin: FlaskClient, rol: str, correo: str, **extra: Any) -> dict[str, Any]:
    resp = admin.post("/api/animadores", json={"nombre": f"vendedor {rol}", "correo": correo, "rol": rol, **extra})
    assert resp.status_code == 201, resp.json
    animador: dict[str, Any] = resp.json["animador"]
    return animador


@pytest.fixture
def admin(client: FlaskClient, seed: Seed) -> FlaskClient:
    login_as(client, "admin")
    return client


def test_crear_vendedor_con_rol(admin: FlaskClient, cols: Collections) -> None:
    v = _crear_vendedor(admin, "secretaria", "secre@uets.edu.ec")
    assert v["rol"] == "secretaria" and v["rol_nombre"] == "Secretaría" and not v["curso_asignado"]
    user = cols.users.find_one({"_id": ObjectId(v["usuario_id"])})
    assert user is not None and user["rol"] == "secretaria"

    # Otros roles no pueden tener curso.
    resp = admin.post(
        "/api/animadores",
        json={"nombre": "x", "rol": "financiero", "curso": "BACHILLERATO", "nivel": 2, "paralelo": "C"},
    )
    assert resp.status_code == 400 and "Solo los animadores" in resp.json["message"]
    assert admin.post("/api/animadores", json={"nombre": "x", "rol": "jefe"}).status_code == 400

    # Buscar por rol.
    assert [a["nombre"] for a in admin.get("/api/animadores?search=secretaria").json["animadores"]] == [
        "VENDEDOR SECRETARIA"
    ]


def test_cambiar_animador_a_otro_rol_quita_su_curso(admin: FlaskClient, cols: Collections, seed: Seed) -> None:
    ana = cols.animators.find_one({"usuario_id": seed.ana})
    assert ana is not None
    resp = admin.put(f"/api/animadores/{ana['_id']}", json={"rol": "parroquia"})
    assert resp.status_code == 200, resp.json
    assert resp.json["animador"]["rol"] == "parroquia" and not resp.json["animador"]["curso_asignado"]
    user = cols.users.find_one({"_id": seed.ana})
    assert user is not None and user["rol"] == "parroquia" and "curso" not in user
    # Y de vuelta a animador con curso.
    resp = admin.put(
        f"/api/animadores/{ana['_id']}",
        json={"rol": "animador", "curso": "BACHILLERATO", "especialidad": "Ciencias", "nivel": 1, "paralelo": "A"},
    )
    assert resp.status_code == 200 and resp.json["animador"]["curso_asignado"]


def test_perfil_y_venta_solo_externos(admin: FlaskClient, cols: Collections, seed: Seed) -> None:
    v = _crear_vendedor(admin, "oratorio", "orat@uets.edu.ec")
    uid = v["usuario_id"]

    login_as(admin, "orat@uets.edu.ec")
    perfil = admin.get("/api/auth/me").json["usuario"]
    assert perfil["rol"] == "animador" and perfil["cargo"] == "oratorio"
    assert perfil["cargo_nombre"] == "Oratorio" and perfil["solo_externos"] is True
    # Sin curso: Mi curso no aplica.
    assert admin.get("/api/mi-curso").status_code == 404

    body = {
        "nombre": "Ext",
        "cedula": "0999999991",
        "correo": "ext@correo.com",
        "registrado_por": uid,
        "cantidad_tablas": 2,
    }
    resp = admin.post("/api/registrarParticipante", json={**body, "tipo": "alumno"})
    assert resp.status_code == 403 and "externos" in resp.json["message"]
    resp = admin.post("/api/registrarParticipante", json={**body, "tipo": "externo"})
    assert resp.status_code == 201, resp.json
    p = cols.participants.find_one({"cedula": "0999999991"})
    assert p is not None and p["tipo"] == "externo" and p["rol_vendedor"] == "oratorio" and p["total_pagar"] == 5

    # Registro automático: sin tipo se asume externo; con otro tipo se rechaza.
    auto = {
        "nombre": "Ext2",
        "cedula": "0999999992",
        "correo": "ext2@correo.com",
        "registrado_por": uid,
        "cantidad_tablas": 1,
    }
    assert admin.post("/api/registrarParticipanteAuto", json={**auto, "tipo": "docente"}).status_code == 403
    assert admin.post("/api/registrarParticipanteAuto", json=auto).status_code == 201
    p2 = cols.participants.find_one({"cedula": "0999999992"})
    assert p2 is not None and p2["tipo"] == "externo" and p2["total_pagar"] == 3


def test_animador_sigue_vendiendo_a_alumnos(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    cols.students.insert_one({"Num documento": "0911", "Nombre": "A", "Primer Apellido": "B"})
    perfil = client.get("/api/auth/me").json["usuario"]
    assert perfil["cargo"] == "animador" and perfil["solo_externos"] is False
    resp = client.post(
        "/api/registrarParticipante",
        json={
            "nombre": "A",
            "cedula": "0911",
            "registrado_por": str(seed.ana),
            "cantidad_tablas": 1,
            "correo": "a.b.est@uets.edu.ec",
            "tipo": "alumno",
        },
    )
    assert resp.status_code == 201
    p = cols.participants.find_one({"cedula": "0911"})
    assert p is not None and p["rol_vendedor"] == "animador"


def test_reportes_por_rol_vendedor_y_promociones(admin: FlaskClient, cols: Collections, seed: Seed) -> None:
    secre = _crear_vendedor(admin, "secretaria", "secre@uets.edu.ec")
    # ANA (animadora) vende 7 tablas = 1 paquete de 5 + 1 par ($15).
    login_as(admin, "ana")
    assert (
        admin.post(
            "/api/registrarParticipante",
            json={
                "nombre": "P1",
                "cedula": "01",
                "correo": "ext@correo.com",
                "tipo": "externo",
                "registrado_por": str(seed.ana),
                "cantidad_tablas": 7,
            },
        ).status_code
        == 201
    )
    # Venta antigua de BETO sin rol_vendedor (toma el rol actual): 1 tabla suelta ($3).
    cols.participants.insert_one(
        {"nombre": "Viejo", "cedula": "02", "registrado_por": seed.beto, "tablas": [seed.tables["CARD00011"]]}
    )

    login_as(admin, "admin")
    rep = admin.get("/api/reportes").json["reportes"]
    assert rep["tablas_vendidas"] == 8 and rep["dinero_recaudado"] == 18
    promos = rep["promociones"]
    assert promos["paquete_5"]["cantidad"] == 1 and promos["paquete_5"]["monto"] == 10
    assert promos["paquete_2"]["cantidad"] == 1 and promos["paquete_2"]["tablas_en_promocion"] == 2
    assert promos["suelta"]["cantidad"] == 1 and promos["suelta"]["precio"] == 3

    roles = {r["rol"]: r for r in rep["ventas_por_rol"]}
    assert set(roles) == {"animador", "secretaria", "financiero", "parroquia", "oratorio", "admin"}
    assert roles["animador"]["tablas"] == 8 and roles["animador"]["monto"] == 18
    assert roles["animador"]["participantes"] == 2 and roles["animador"]["vendedores"] == 2
    assert roles["secretaria"]["tablas"] == 0 and roles["secretaria"]["vendedores"] == 1

    vendedores = {v["usuario"]: v for v in rep["ventas_por_vendedor"]}
    assert vendedores["ANA"]["tablas"] == 7 and vendedores["ANA"]["monto"] == 15
    assert vendedores["ANA"]["promociones"] == {"paquete_5": 1, "paquete_2": 1, "suelta": 0}
    assert vendedores["BETO"]["promociones"]["suelta"] == 1
    # Los vendedores sin ventas también aparecen.
    sin_ventas = next(v for v in rep["ventas_por_vendedor"] if v["id"] == secre["usuario_id"])
    assert sin_ventas["tablas"] == 0 and sin_ventas["rol_nombre"] == "Secretaría"
    assert rep["ventas_por_vendedor"][0]["usuario"] == "ANA"  # ordenado por tablas
