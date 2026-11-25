"""Caminos de error: validaciones de entrada, permisos y recursos inexistentes."""

from __future__ import annotations

from typing import Any

import pytest
from bson import ObjectId
from flask import Flask
from flask.testing import FlaskClient

from bingo.db import Collections

from .conftest import Seed, login_as, register

MISSING = str(ObjectId())


def _participant(client: FlaskClient, seed: Seed, cedula: str = "0101", tablas: list[str] | None = None) -> str:
    resp = register(client, seed.ana, cedula, tablas or ["CARD00001"])
    assert resp.status_code == 201, resp.json
    participant_id: str = resp.json["participante"]["_id"]
    return participant_id


# ------------------------------------------------------------------ registro
@pytest.mark.parametrize(
    ("tablas", "status"),
    [
        (["CARD00009"], 201),
        (["CARD00099"], 404),  # serial inexistente
        ([MISSING], 404),  # ObjectId inexistente
    ],
)
def test_register_table_references(client: FlaskClient, seed: Seed, tablas: list[str], status: int) -> None:
    assert register(client, seed.ana, "0101", tablas).status_code == status


def test_register_unknown_serial_in_range(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    cols.tables.delete_one({"serial": "CARD00005"})
    assert register(client, seed.ana, "0101", ["CARD00005"]).status_code == 404


def test_register_rejects_non_list_and_unknown_seller(client: FlaskClient, seed: Seed) -> None:
    body = {"nombre": "J", "cedula": "1", "registrado_por": str(seed.ana), "tablas": "CARD00001"}
    assert client.post("/api/registrarParticipante", json=body).status_code == 400
    login_as(client, "admin")
    assert register(client, ObjectId(), "0101", ["CARD00001"]).status_code == 404


def test_register_requires_quantity(client: FlaskClient, seed: Seed) -> None:
    body = {"nombre": "J", "cedula": "0101", "registrado_por": str(seed.ana)}
    resp = client.post("/api/registrarParticipante", json=body)
    assert resp.status_code == 400
    assert resp.json["message"] == "Debe asignarse al menos una tabla al participante."
    assert client.post("/api/registrarParticipante", json={**body, "tablas": "x"}).status_code == 400


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"nombre": "J", "cedula": "1"}, 400),  # falta registrado_por
        ({"nombre": "J", "cedula": "1", "registrado_por": "x", "cantidad_tablas": 0}, 400),
        ({"nombre": "J", "cedula": "1", "registrado_por": "x"}, 400),  # id inválido
        ({"nombre": "J", "cedula": "1", "registrado_por": MISSING}, 404),
        ({"nombre": "J", "cedula": "1", "registrado_por": "SEED", "cantidad_tablas": 21}, 400),  # solo hay 20
    ],
)
def test_register_auto_validations(client: FlaskClient, seed: Seed, body: dict[str, Any], status: int) -> None:
    login_as(client, "admin")  # el admin puede indicar cualquier vendedor y llega a las validaciones
    if body.get("registrado_por") == "SEED":
        body = {**body, "registrado_por": str(seed.ana)}
    assert client.post("/api/registrarParticipanteAuto", json=body).status_code == status


def test_register_auto_without_free_tables(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    body = {"nombre": "J", "cedula": "1", "registrado_por": str(seed.ana), "cantidad_tablas": 2}
    cols.tables.update_many({}, {"$set": {"stateAsigned": True}})
    resp = client.post("/api/registrarParticipanteAuto", json=body)
    assert resp.status_code == 400
    assert resp.json["message"] == "Solo quedan 0 tablas disponibles."
    assert cols.participants.count_documents({}) == 0


# ----------------------------------------------------------- modificaciones
def test_add_tables_validations(client: FlaskClient, seed: Seed) -> None:
    pid = _participant(client, seed)
    url = f"/api/participante/{pid}/tablas/1"
    login_as(client, "admin")
    assert client.post("/api/participante/xx/tablas/1", json={}).status_code == 400
    assert client.post(url, json={"usuario_id": "xx", "tablas": ["CARD00002"]}).status_code == 400
    assert client.post(url, json={"usuario_id": str(seed.ana), "tablas": "CARD00002"}).status_code == 400
    assert client.post(url, json={"usuario_id": str(seed.ana), "tablas": []}).status_code == 400
    assert client.post(url, json={"tablas": ["CARD00002"]}).status_code == 400
    assert client.post(url, json={"usuario_id": MISSING, "tablas": ["CARD00002"]}).status_code == 404


def test_add_tables_beyond_free_tables(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    pid = _participant(client, seed)
    resp = client.post(f"/api/participante/{pid}/tablas/1", json={"usuario_id": str(seed.ana), "cantidad": 30})
    assert resp.status_code == 400
    assert "Solo quedan" in resp.json["message"]


def test_remove_table_validations(client: FlaskClient, seed: Seed) -> None:
    pid = _participant(client, seed)
    other_table = str(seed.tables["CARD00002"])
    url = f"/api/participante/{pid}/tabla/{other_table}/1"
    login_as(client, "admin")
    assert client.delete(url, json={}).status_code == 400
    assert client.delete(url, json={"usuario_id": "xx"}).status_code == 400
    assert client.delete(url, json={"usuario_id": str(seed.ana)}).status_code == 404  # no le pertenece
    assert client.delete(url, json={"usuario_id": str(seed.beto)}).status_code == 403
    assert (
        client.delete(
            f"/api/participante/{MISSING}/tabla/{other_table}/1", json={"usuario_id": str(seed.ana)}
        ).status_code
        == 404
    )


def test_eliminar_tabla_asignada_validations(client: FlaskClient, seed: Seed) -> None:
    pid = _participant(client, seed)
    assert client.post("/api/eliminarTablaAsignada", json={}).status_code == 400
    body = {"participante_id": pid, "serial": "CARD00002", "usuario_id": str(seed.ana)}
    assert client.post("/api/eliminarTablaAsignada", json=body).status_code == 400


def test_delete_participant_validations(client: FlaskClient, seed: Seed) -> None:
    pid = _participant(client, seed)
    assert client.delete(f"/api/participante/{pid}/1", json={}).status_code == 400
    assert client.delete(f"/api/participante/{pid}/1", json={"usuario_id": str(seed.beto)}).status_code == 403
    assert client.delete(f"/api/participante/{MISSING}/1", json={"usuario_id": str(seed.ana)}).status_code == 404


# ------------------------------------------------------------------ lectura
def test_participant_tables_endpoint(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    pid = _participant(client, seed, tablas=["CARD00001", "CARD00002"])
    resp = client.get(f"/api/obtenerTablasParticipante/{pid}")
    assert [t["serial"] for t in resp.json["tablas"]] == ["CARD00001", "CARD00002"]

    cols.participants.update_one({"_id": ObjectId(pid)}, {"$set": {"tablas": []}})
    assert client.get(f"/api/obtenerTablasParticipante/{pid}").json["tablas"] == []
    assert client.get("/api/obtenerTablasParticipante/xx").status_code == 400
    assert client.get(f"/api/obtenerTablasParticipante/{MISSING}").status_code == 404


def test_pdf_for_participant_without_tables(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    pid = _participant(client, seed)
    cols.participants.update_one({"_id": ObjectId(pid)}, {"$set": {"tablas": []}})
    resp = client.get("/api/participante/cedula/0101/tablas_pdf")
    assert resp.status_code == 200
    assert resp.json["tablas"] == []


def test_listings_validations(client: FlaskClient, seed: Seed) -> None:
    login_as(client, "admin")
    assert client.get(f"/api/participantes/por-usuario/{MISSING}").status_code == 404
    assert client.get("/api/participantes/todos/admin").status_code == 400
    assert client.get(f"/api/participantes/todos/admin?usuario_id={MISSING}").status_code == 404
    assert client.get(f"/api/participantes/todos/admin?usuario_id={seed.ana}").status_code == 403


# ------------------------------------------------------------------ errores
def test_unexpected_error_returns_generic_500(app: Flask, client: FlaskClient) -> None:
    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secreto interno")

    resp = client.get("/boom")
    assert resp.status_code == 500
    assert resp.json == {"success": False, "message": "Error interno del servidor."}

    app.debug = True
    assert client.get("/boom").json["error"] == "secreto interno"
