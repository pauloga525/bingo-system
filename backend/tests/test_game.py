from __future__ import annotations

import io
import json
import os
import time
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient
from pymongo.errors import ServerSelectionTimeoutError

from bingo.config import Settings
from bingo.db import Collections
from bingo.domain.cards import MAX_CARDS, generate_unique_cards
from bingo.services.game import GameService
from bingo.services.pdf_extract import extraer_matrices_pdf
from bingo.services.pdf_render import render_cards_pdf

from .conftest import Seed, board_login, login_as, register


@pytest.fixture(autouse=True)
def _tablero_admin(client: FlaskClient, cols: Collections) -> None:
    """Todas las pruebas del juego corren con la sesión del tablero de un administrador."""
    assert board_login(client, cols).status_code == 200


def _numbers(cols: Collections, serial: str) -> list[int]:
    tabla = cols.tables.find_one({"serial": serial})
    assert tabla is not None
    return [n for row in tabla["matrix"] for n in row if n is not None]


def test_reset_plays_only_assigned_non_winner_tables(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    register(client, seed.ana, "0101", ["CARD00001", "CARD00002"])
    cols.tables.update_one({"serial": "CARD00002"}, {"$set": {"won": True}})
    resp = client.post("/reset").json
    assert resp["active_count"] == 1
    assert resp["removed_winners"] == 1
    assert [c["serial"] for c in client.get("/get_cards").json] == ["CARD00001"]


def test_full_game_flow_marks_and_persists_winner(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    register(client, seed.ana, "0101", ["CARD00001"])
    client.post("/reset")
    numbers = _numbers(cols, "CARD00001")
    for n in numbers[:-1]:
        assert client.post("/mark", json={"num": n, "marcado": True}).json["success"]
    progreso = client.get("/progress").json
    assert progreso["top3"][0] == {"serial": "CARD00001", "aciertos": 24, "won": False}
    assert progreso["ganadores"] == []

    client.post("/mark", json={"num": numbers[-1]})
    progreso = client.get("/progress").json
    assert progreso["ganadores"] == [{"serial": "CARD00001", "aciertos": 25, "won": True}]
    ganador = cols.winners.find_one({"serial": "CARD00001"})
    assert ganador is not None
    first_ts = ganador["timestamp"]
    client.get("/progress")
    assert cols.winners.find_one({"serial": "CARD00001"})["timestamp"] == first_ts  # type: ignore[index]
    assert cols.tables.find_one({"serial": "CARD00001"})["won"] is True  # type: ignore[index]
    assert client.get("/tabla_ganadora").json["count"] == 1


def test_mark_and_progress_use_the_same_active_file(
    client: FlaskClient, cols: Collections, seed: Seed, settings: Settings
) -> None:
    register(client, seed.ana, "0101", ["CARD00001"])
    client.post("/reset")
    # Un JSON subido/generado más reciente ya no debe reemplazar la partida.
    other = settings.json_dir / "bingo_cards_uploaded_99999999999.json"
    other.write_text("[]", encoding="utf-8")
    future = time.time() + 60
    os.utime(other, (future, future))
    client.post("/mark", json={"num": _numbers(cols, "CARD00001")[0]})
    assert client.get("/progress").json["top3"][0]["aciertos"] == 2
    assert json.loads(other.read_text(encoding="utf-8")) == []


def test_mark_without_cards_returns_400(client: FlaskClient) -> None:
    assert client.post("/mark", json={"num": 5}).status_code == 400


def test_reset_prunes_old_snapshots(app: object, client: FlaskClient, seed: Seed, settings: Settings) -> None:
    for _ in range(settings.active_json_keep + 3):
        client.post("/reset")
    assert len(list(settings.json_dir.glob("bingo_cards_active_*.json"))) == settings.active_json_keep


def test_winner_pdf_sanitizes_filename(client: FlaskClient, seed: Seed, cols: Collections, settings: Settings) -> None:
    matrix = cols.tables.find_one({"serial": "CARD00001"})["matrix"]  # type: ignore[index]
    marks = [[True] * 5 for _ in range(5)]
    resp = client.post("/winner_pdf", json={"serial": "../../evil", "matrix": matrix, "marks": marks})
    assert resp.status_code == 200
    path = Path(resp.json["pdf_path"])
    assert path.parent == settings.winners_dir
    assert path.read_bytes().startswith(b"%PDF")
    assert client.post("/winner_pdf", json={}).json == {"error": "Faltan datos"}
    assert client.post("/winner_pdf", json={"serial": "NOPE"}).status_code == 404


def test_generate_refuses_to_overwrite_existing_tables(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    register(client, seed.ana, "0101", ["CARD00001"])
    assert client.post("/generate", json={"num_cards": 3}).status_code == 409
    assert client.post("/generate", json={"num_cards": 3, "force": True}).status_code == 409  # hay asignadas
    login_as(client, "admin")
    client.delete(
        f"/api/participante/{cols.participants.find_one({})['_id']}/1",  # type: ignore[index]
        json={"usuario_id": str(seed.admin)},
    )
    assert client.post("/generate", json={"num_cards": 3}).status_code == 409
    assert client.post("/generate", json={"num_cards": 3, "force": True}).status_code == 200


def test_generate_on_empty_db(client: FlaskClient, cols: Collections, settings: Settings) -> None:
    resp = client.post("/generate", json={"num_cards": 6})
    assert resp.status_code == 200, resp.json
    assert resp.json["cartones_duplicados"] == 0
    assert cols.tables.count_documents({"stateAsigned": False}) == 6
    assert Path(resp.json["pdf_path"]).read_bytes().startswith(b"%PDF")


def test_pdf_roundtrip_render_then_extract(tmp_path: Path) -> None:
    cards = generate_unique_cards(6)
    pdf = tmp_path / "cartones.pdf"
    pdf.write_bytes(render_cards_pdf(cards))
    extracted = {c["serial"]: c["matrix"] for c in extraer_matrices_pdf(pdf)}
    for card in cards:
        assert extracted[card["serial"]] == card["matrix"]


def test_upload_does_not_reset_assigned_or_won_tables(
    client: FlaskClient, cols: Collections, seed: Seed, settings: Settings
) -> None:
    register(client, seed.ana, "0101", ["CARD00001"])
    cols.tables.update_one({"serial": "CARD00002"}, {"$set": {"won": True}})
    cards = [
        {"serial": t["serial"], "matrix": t["matrix"]}
        for t in cols.tables.find({"serial": {"$in": ["CARD00001", "CARD00002", "CARD00003"]}}).sort("serial", 1)
    ]
    cards[0]["matrix"] = generate_unique_cards(1)[0]["matrix"]  # matriz distinta en tabla asignada
    cards.append({"serial": "CARD00099", "matrix": generate_unique_cards(1)[0]["matrix"]})
    pdf = render_cards_pdf(cards)

    resp = client.post("/upload", data={"pdf": (io.BytesIO(pdf), "c.pdf")}, content_type="multipart/form-data")
    assert resp.status_code == 200, resp.json
    assert (resp.json["insertados_en_mongo"], resp.json["actualizados_en_mongo"]) == (1, 0)
    assert resp.json["conflictos_asignadas"] == ["CARD00001"]
    assert cols.tables.find_one({"serial": "CARD00001"})["stateAsigned"] is True  # type: ignore[index]
    assert cols.tables.find_one({"serial": "CARD00002"})["won"] is True  # type: ignore[index]
    assert list(settings.upload_dir.glob("tmp_upload_*")) == []


def test_upload_without_file(client: FlaskClient) -> None:
    assert client.post("/upload").json == {"error": "No se envió PDF"}


def test_upload_rejects_non_pdf(client: FlaskClient) -> None:
    resp = client.post(
        "/upload", data={"pdf": (io.BytesIO(b"no soy un pdf"), "c.pdf")}, content_type="multipart/form-data"
    )
    assert resp.status_code == 400
    assert resp.json == {"error": "El archivo no es un PDF"}


def test_upload_corrupt_pdf_hides_details(client: FlaskClient) -> None:
    resp = client.post(
        "/upload", data={"pdf": (io.BytesIO(b"%PDF-1.4 roto"), "c.pdf")}, content_type="multipart/form-data"
    )
    assert resp.status_code == 422
    assert resp.json == {"error": "Error al procesar PDF"}


def test_upload_too_large(client: FlaskClient, app: Flask) -> None:
    app.config["MAX_CONTENT_LENGTH"] = 1024
    big = io.BytesIO(b"%PDF-" + b"0" * 4096)
    resp = client.post("/upload", data={"pdf": (big, "c.pdf")}, content_type="multipart/form-data")
    assert resp.status_code == 413


@pytest.mark.parametrize("num_cards", [0, MAX_CARDS + 1])
def test_generate_rejects_out_of_range(client: FlaskClient, num_cards: int) -> None:
    assert client.post("/generate", json={"num_cards": num_cards}).status_code == 400


def test_security_headers(client: FlaskClient) -> None:
    headers = client.get("/").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "SAMEORIGIN"
    assert headers["Referrer-Policy"] == "same-origin"


def test_import_cards_updates_unassigned_matrix(cols: Collections, seed: Seed, settings: Settings) -> None:
    nueva = generate_unique_cards(1)[0]["matrix"]
    result = GameService(cols, settings).import_cards([{"serial": "CARD00005", "matrix": nueva}])
    assert result == {"insertados": 0, "actualizados": 1, "conflictos": []}
    assert cols.tables.find_one({"serial": "CARD00005"})["matrix"] == nueva  # type: ignore[index]


def test_pages_render(client: FlaskClient) -> None:
    assert client.get("/").status_code == 200
    assert client.get("/pages/masterTable.html").status_code == 200
    assert client.get("/no-existe").status_code == 404


def test_health_ok(client: FlaskClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json == {"status": "ok", "database": "ok"}


def test_health_reports_unreachable_database(
    client: FlaskClient, cols: Collections, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise ServerSelectionTimeoutError("sin conexión")

    monkeypatch.setattr(cols.client.admin, "command", fail)
    resp = client.get("/health")
    assert resp.status_code == 503
    assert resp.json == {"status": "error", "database": "unreachable"}
