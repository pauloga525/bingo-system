"""Vaciado de todos los participantes (solo administrador)."""

from __future__ import annotations

from bson import json_util
from flask.testing import FlaskClient

from bingo.config import Settings
from bingo.db import Collections
from bingo.services.purge import CONFIRMATION

from .conftest import Seed, login_as, register

URL = "/api/participantes/vaciar"


def _vender(client: FlaskClient, seed: Seed) -> None:
    assert register(client, seed.ana, "0101", ["CARD00001", "CARD00002", "CARD00003"]).status_code == 201
    assert register(client, seed.ana, "0102", ["CARD00004"]).status_code == 201
    assert register(client, seed.beto, "0201", ["CARD00011", "CARD00012"]).status_code == 201


def test_summary_shows_what_would_be_deleted(client: FlaskClient, seed: Seed) -> None:
    _vender(client, seed)
    login_as(client, "admin")
    data = client.get(URL).json
    assert (data["participantes"], data["tablas_asignadas"], data["vendedores"]) == (3, 6, 2)
    assert data["confirmacion"] == CONFIRMATION


def test_purge_deletes_all_releases_tables_and_resets_counters(
    client: FlaskClient, cols: Collections, seed: Seed, settings: Settings
) -> None:
    _vender(client, seed)
    cols.tables.update_one({"serial": "CARD00004"}, {"$set": {"won": True}})
    login_as(client, "admin")

    resp = client.post(URL, json={"confirmacion": CONFIRMATION})
    assert resp.status_code == 200, resp.json
    assert resp.json["participantes_borrados"] == 3
    assert resp.json["tablas_liberadas"] == 6

    assert cols.participants.count_documents({}) == 0
    assert cols.tables.count_documents({"stateAsigned": True}) == 0
    assert cols.tables.count_documents({"assignedToParticipant": {"$exists": True}}) == 0
    assert cols.tables.find_one({"serial": "CARD00004"})["won"] is True  # el historial de ganadoras se conserva
    for uid in (seed.ana, seed.beto):
        user = cols.users.find_one({"_id": uid})
        assert user is not None
        assert (user["usedTables"], user["total_vendido"]) == (0, 0)
        assert user["totalTables"] == 10  # la reserva del animador se conserva

    # Respaldo con todos los participantes borrados, restaurable con mongoimport.
    backup = settings.backup_dir / resp.json["respaldo"]
    docs = [json_util.loads(line) for line in backup.read_text(encoding="utf-8").splitlines()]
    assert sorted(d["cedula"] for d in docs) == ["0101", "0102", "0201"]


def test_tables_can_be_sold_again_after_purge(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    _vender(client, seed)
    login_as(client, "admin")
    assert client.post(URL, json={"confirmacion": CONFIRMATION}).status_code == 200
    again = register(client, seed.ana, "0101", ["CARD00001", "CARD00002", "CARD00003"])
    assert again.status_code == 201, again.json
    user = cols.users.find_one({"_id": seed.ana})
    assert user is not None and user["usedTables"] == 3


def test_purge_requires_exact_confirmation(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    _vender(client, seed)
    login_as(client, "admin")
    for wrong in (None, "", "borrar", "BORRAR"):
        assert client.post(URL, json={"confirmacion": wrong}).status_code == 400
    assert cols.participants.count_documents({}) == 3


def test_purge_is_admin_only(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    _vender(client, seed)
    login_as(client, "ana")
    assert client.get(URL).status_code == 403
    assert client.post(URL, json={"confirmacion": CONFIRMATION}).status_code == 403
    assert cols.participants.count_documents({}) == 3


def test_purge_with_no_participants(client: FlaskClient, seed: Seed) -> None:
    login_as(client, "admin")
    resp = client.post(URL, json={"confirmacion": CONFIRMATION})
    assert resp.status_code == 200
    assert (resp.json["participantes_borrados"], resp.json["respaldo"]) == (0, None)
