"""Nuevo juego desde cero: borra tablas, ganadoras, participantes y reservas; genera tablas y PDF."""

from __future__ import annotations

from typing import Any

import pytest
from bson import json_util
from flask import Flask
from flask.testing import FlaskClient

from bingo.config import Settings
from bingo.db import Collections
from bingo.domain.cards import MAX_CARDS
from bingo.services import new_game
from bingo.services.game import GameService
from bingo.services.new_game import CONFIRMATION

from .conftest import Seed, login_as, register

URL = "/api/juego/nuevo"
OK = {"cantidad": 25, "confirmacion": CONFIRMATION}


@pytest.fixture
def jugado(client: FlaskClient, cols: Collections, seed: Seed) -> FlaskClient:
    """Sistema con ventas, una ganadora, un estudiante y la sesión del admin iniciada."""
    assert register(client, seed.ana, "0101", ["CARD00001", "CARD00002"]).status_code == 201
    assert register(client, seed.beto, "0201", ["CARD00011"]).status_code == 201
    cols.tables.update_one({"serial": "CARD00001"}, {"$set": {"won": True}})
    cols.winners.insert_one({"serial": "CARD00001"})
    cols.students.insert_one({"Nombre": "PEPE", "Num documento": "0999"})
    login_as(client, "admin")
    return client


def test_summary(jugado: FlaskClient) -> None:
    data = jugado.get(URL).json
    assert (data["tablas"], data["tablas_asignadas"], data["tablas_ganadoras"]) == (20, 3, 1)
    assert (data["participantes"], data["cuentas_con_reserva"], data["estudiantes"]) == (2, 2, 1)
    assert data["animadores"] == 2 and data["confirmacion"] == CONFIRMATION and data["pdf_actual"] is None


def test_new_game_resets_everything_but_students_and_animators(
    jugado: FlaskClient, cols: Collections, seed: Seed, settings: Settings
) -> None:
    resp = jugado.post(URL, json=OK)
    assert resp.status_code == 200, resp.json
    body = resp.json
    assert (body["tablas_generadas"], body["desde"], body["hasta"]) == (25, "CARD00001", "CARD00025")
    assert (body["tablas_borradas"], body["participantes_borrados"], body["ganadoras_borradas"]) == (20, 2, 1)

    assert cols.tables.count_documents({}) == 25
    assert cols.tables.count_documents({"$or": [{"stateAsigned": True}, {"won": True}]}) == 0
    assert cols.participants.count_documents({}) == 0
    assert cols.winners.count_documents({}) == 0
    for uid in (seed.ana, seed.beto):
        user = cols.users.find_one({"_id": uid})
        assert user is not None
        assert not {"totalTables", "usedTables", "fromSerial", "reserved_table_ids", "total_vendido"} & set(user)
    # Se conservan estudiantes, animadores y sus cuentas.
    assert cols.students.count_documents({}) == 1
    assert cols.animators.count_documents({}) == 2
    assert cols.users.count_documents({}) == 3

    # El tablero queda sin cartones hasta que se asignen tablas nuevas.
    assert GameService(cols, settings).current_cards() == []

    # Respaldo de lo borrado, restaurable con mongoimport.
    folder = settings.backup_dir / body["respaldo"]
    participantes = [json_util.loads(x) for x in (folder / "Participantes.json").read_text("utf-8").splitlines()]
    assert sorted(p["cedula"] for p in participantes) == ["0101", "0201"]
    assert len((folder / "tablas.json").read_text("utf-8").splitlines()) == 20
    assert len((folder / "Users_reservas.json").read_text("utf-8").splitlines()) == 2


def test_pdf_download(jugado: FlaskClient) -> None:
    assert jugado.get("/api/juego/tablas.pdf").status_code == 404
    nombre = jugado.post(URL, json=OK).json["pdf"]
    resp = jugado.get("/api/juego/tablas.pdf")
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert resp.data.startswith(b"%PDF")
    assert f"bingo-{nombre}" in resp.headers["Content-Disposition"]
    assert jugado.get(URL).json["pdf_actual"] == nombre


def test_new_tables_can_be_reserved_and_sold(jugado: FlaskClient, cols: Collections, seed: Seed) -> None:
    jugado.post(URL, json=OK)
    resp = jugado.post(
        f"/api/users/{seed.ana}/assign_tables", json={"totalTables": 5, "requesting_user_id": str(seed.admin)}
    )
    assert resp.status_code == 200, resp.json
    desde = resp.json["from"]
    assert register(jugado, seed.ana, "0101", [desde]).status_code == 201


@pytest.mark.parametrize(
    "body",
    [
        {"cantidad": 25},
        {"cantidad": 25, "confirmacion": "nuevo juego"},
        {"cantidad": 0, "confirmacion": CONFIRMATION},
        {"cantidad": "x", "confirmacion": CONFIRMATION},
        {"cantidad": MAX_CARDS + 1, "confirmacion": CONFIRMATION},
    ],
)
def test_invalid_requests_change_nothing(jugado: FlaskClient, cols: Collections, body: dict[str, Any]) -> None:
    assert jugado.post(URL, json=body).status_code == 400
    assert (cols.tables.count_documents({}), cols.participants.count_documents({})) == (20, 2)


def test_admin_only(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    for path in (URL, "/api/juego/tablas.pdf"):
        assert client.get(path).status_code == 403  # sesión de ANA
    assert client.post(URL, json=OK).status_code == 403
    assert cols.tables.count_documents({}) == 20


def test_pdf_failure_deletes_nothing(
    jugado: FlaskClient, cols: Collections, monkeypatch: pytest.MonkeyPatch, app: Flask
) -> None:
    def falla(_cards: Any) -> bytes:
        raise RuntimeError("disco lleno")

    monkeypatch.setattr(new_game, "render_cards_pdf", falla)
    assert jugado.post(URL, json=OK).status_code == 500
    assert (cols.tables.count_documents({}), cols.participants.count_documents({})) == (20, 2)
    assert cols.winners.count_documents({}) == 1


def test_only_one_reset_at_a_time(jugado: FlaskClient, cols: Collections) -> None:
    assert new_game._LOCK.acquire(blocking=False)
    try:
        assert jugado.post(URL, json=OK).status_code == 409
    finally:
        new_game._LOCK.release()
    assert cols.tables.count_documents({}) == 20
