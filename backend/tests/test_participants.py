from __future__ import annotations

from flask.testing import FlaskClient

from bingo.db import Collections

from .conftest import Seed, login_as, register


def _user(cols: Collections, oid: object) -> dict:  # type: ignore[type-arg]
    doc = cols.users.find_one({"_id": oid})
    assert doc is not None
    return doc


def test_register_assigns_tables_and_updates_counters(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    resp = register(client, seed.ana, "0101", ["CARD00001", "CARD00002", "CARD00003"])
    assert resp.status_code == 201, resp.json
    body = resp.json["participante"]
    assert body["total_pagar"] == 8
    assert len(body["tablas"]) == 3
    assert cols.tables.count_documents({"stateAsigned": True}) == 3
    ana = _user(cols, seed.ana)
    assert ana["usedTables"] == 3
    assert ana["total_vendido"] == 8


def test_register_rejects_duplicate_cedula(client: FlaskClient, seed: Seed) -> None:
    assert register(client, seed.ana, "0101", ["CARD00001"]).status_code == 201
    resp = register(client, seed.beto, "0101", ["CARD00011"])
    assert resp.status_code == 409
    assert "Nombre ANA" in resp.json["message"]


def test_register_rejects_out_of_range_table(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    resp = register(client, seed.ana, "0101", ["CARD00015"])
    assert resp.status_code == 400
    assert "fuera del rango" in resp.json["message"]
    assert cols.participants.count_documents({}) == 0


def test_register_rejects_already_assigned_and_rolls_back(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    assert register(client, seed.ana, "0101", ["CARD00002"]).status_code == 201
    resp = register(client, seed.ana, "0202", ["CARD00001", "CARD00002"])
    assert resp.status_code == 400
    # CARD00001 se tomó y luego se liberó (compensación).
    assert cols.tables.find_one({"serial": "CARD00001"})["stateAsigned"] is False  # type: ignore[index]
    assert _user(cols, seed.ana)["usedTables"] == 1


def test_register_rejects_more_than_quota(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    cols.users.update_one({"_id": seed.ana}, {"$set": {"usedTables": 9}})
    resp = register(client, seed.ana, "0101", ["CARD00001", "CARD00002"])
    assert resp.status_code == 400
    assert "Solo tienes 1" in resp.json["message"]


def test_register_validations(client: FlaskClient, seed: Seed) -> None:
    assert client.post("/api/registrarParticipante", json={}).status_code == 400
    # Un animador no puede registrar a nombre de otro; el admin sí llega a la validación del id.
    assert client.post("/api/CreateParticipantes", json={"nombre": "x", "registrado_por": "nope"}).status_code == 403
    login_as(client, "admin")
    resp = client.post("/api/CreateParticipantes", json={"nombre": "x", "registrado_por": "nope"})
    assert resp.status_code == 400
    assert "ID de usuario válido" in resp.json["message"]


def test_consecutive_tables_skip_assigned(client: FlaskClient, seed: Seed) -> None:
    register(client, seed.ana, "0101", ["CARD00001", "CARD00003"])
    resp = client.post("/api/obtenerTablasConsecutivas", json={"usuario_id": str(seed.ana), "cantidad_tablas": 3})
    assert resp.status_code == 200
    assert resp.json["tablas_consecutivas"] == ["CARD00002", "CARD00004", "CARD00005"]

    resp = client.post("/api/obtenerTablasConsecutivas", json={"usuario_id": str(seed.ana), "cantidad_tablas": 20})
    assert resp.status_code == 400


def _participant_id(client: FlaskClient, seller: object, cedula: str, tablas: list[str]) -> str:
    resp = register(client, seller, cedula, tablas)  # type: ignore[arg-type]
    assert resp.status_code == 201, resp.json
    return str(resp.json["participante"]["_id"])


def test_add_tables_recomputes_total_and_counters(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    pid = _participant_id(client, seed.ana, "0101", ["CARD00001", "CARD00002", "CARD00003", "CARD00004"])
    resp = client.post(f"/api/participante/{pid}/tablas/1", json={"tablas": ["CARD00005"], "usuario_id": str(seed.ana)})
    assert resp.status_code == 200, resp.json
    participante = cols.participants.find_one({})
    assert participante is not None
    assert len(participante["tablas"]) == 5
    assert participante["total_pagar"] == 10  # paquete de 5
    ana = _user(cols, seed.ana)
    assert ana["usedTables"] == 5
    assert ana["total_vendido"] == 10


def test_url_tipo_usuario_no_longer_grants_admin(client: FlaskClient, seed: Seed) -> None:
    pid = _participant_id(client, seed.ana, "0101", ["CARD00001"])
    # Beto intenta hacerse pasar por admin poniendo 0 en la URL.
    resp = client.post(
        f"/api/participante/{pid}/tablas/0", json={"tablas": ["CARD00011"], "usuario_id": str(seed.beto)}
    )
    assert resp.status_code == 403
    resp = client.delete(f"/api/participante/{pid}/0", json={"usuario_id": str(seed.beto)})
    assert resp.status_code == 403


def test_admin_can_manage_any_participant(client: FlaskClient, seed: Seed) -> None:
    pid = _participant_id(client, seed.ana, "0101", ["CARD00001"])
    login_as(client, "admin")
    resp = client.post(
        f"/api/participante/{pid}/tablas/1", json={"tablas": ["CARD00015"], "usuario_id": str(seed.admin)}
    )
    assert resp.status_code == 200, resp.json


def test_animator_cannot_add_tables_outside_range(client: FlaskClient, seed: Seed) -> None:
    pid = _participant_id(client, seed.ana, "0101", ["CARD00001"])
    resp = client.post(f"/api/participante/{pid}/tablas/1", json={"tablas": ["CARD00015"], "usuario_id": str(seed.ana)})
    assert resp.status_code == 400


def test_remove_table_updates_everything(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    pid = _participant_id(client, seed.ana, "0101", ["CARD00001", "CARD00002"])
    tid = seed.tables["CARD00002"]
    resp = client.delete(f"/api/participante/{pid}/tabla/{tid}/1", json={"usuario_id": str(seed.ana)})
    assert resp.status_code == 200, resp.json
    assert cols.tables.find_one({"_id": tid})["stateAsigned"] is False  # type: ignore[index]
    assert cols.participants.find_one({})["total_pagar"] == 3  # type: ignore[index]
    ana = _user(cols, seed.ana)
    assert (ana["usedTables"], ana["total_vendido"]) == (1, 3)


def test_eliminar_tabla_asignada_by_serial_now_works(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    pid = _participant_id(client, seed.ana, "0101", ["CARD00001", "CARD00002"])
    resp = client.post(
        "/api/eliminarTablaAsignada", json={"participante_id": pid, "serial": "CARD00001", "usuario_id": str(seed.ana)}
    )
    assert resp.status_code == 200, resp.json
    assert _user(cols, seed.ana)["usedTables"] == 1


def test_delete_participant_releases_tables(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    pid = _participant_id(client, seed.ana, "0101", ["CARD00001", "CARD00002"])
    resp = client.delete(f"/api/participante/{pid}/1", json={"usuario_id": str(seed.ana)})
    assert resp.status_code == 200
    assert resp.json["tablas_liberadas"] == 2
    assert cols.tables.count_documents({"stateAsigned": True}) == 0
    ana = _user(cols, seed.ana)
    assert (ana["usedTables"], ana["total_vendido"]) == (0, 0)


def test_register_auto_picks_free_reserved_tables(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    pid = _participant_id(client, seed.ana, "0101", ["CARD00001", "CARD00002"])
    client.delete(f"/api/participante/{pid}/tabla/{seed.tables['CARD00001']}/1", json={"usuario_id": str(seed.ana)})
    resp = client.post(
        "/api/registrarParticipanteAuto",
        json={"nombre": "Eva", "cedula": "0303", "registrado_por": str(seed.ana), "cantidad_tablas": 2},
    )
    assert resp.status_code == 201, resp.json
    nuevo = cols.participants.find_one({"cedula": "0303"})
    assert nuevo is not None
    serials = sorted(cols.tables.find_one({"_id": t})["serial"] for t in nuevo["tablas"])  # type: ignore[index]
    assert serials == ["CARD00001", "CARD00003"]
    assert nuevo["total_pagar"] == 5


def test_listings(client: FlaskClient, seed: Seed) -> None:
    _participant_id(client, seed.ana, "0101", ["CARD00001"])
    _participant_id(client, seed.beto, "0202", ["CARD00011"])

    login_as(client, "ana")
    resp = client.get(f"/api/participantes/por-usuario/{seed.ana}")
    assert resp.json["total_participantes"] == 1
    assert "password" not in resp.json["usuario"]
    # Un animador no puede ver los datos de otro usuario ni todos los participantes.
    assert client.get(f"/api/participantes/por-usuario/{seed.beto}").status_code == 403
    assert client.get("/api/participantes", query_string={"usuario_id": str(seed.beto)}).status_code == 403
    assert client.get("/api/participantes", query_string={"tipo_usuario": "0"}).json["count"] == 1
    assert client.get("/api/participantes/todos/admin", query_string={"usuario_id": str(seed.ana)}).status_code == 403

    login_as(client, "admin")
    assert client.get(f"/api/participantes/por-usuario/{seed.admin}").json["total_participantes"] == 2
    assert client.get("/api/participantes", query_string={"usuario_id": str(seed.beto)}).json["count"] == 1
    assert client.get("/api/participantes", query_string={"tipo_usuario": "0"}).json["count"] == 2
    assert client.get("/api/participantes").json["count"] == 2
    assert client.get("/api/participantes/todos/admin").status_code == 400
    ok = client.get("/api/participantes/todos/admin", query_string={"usuario_id": str(seed.admin)})
    assert ok.json["total_participantes"] == 2


def test_participant_by_cedula_and_pdf(client: FlaskClient, seed: Seed) -> None:
    _participant_id(client, seed.ana, "0101", ["CARD00001", "CARD00002"])
    resp = client.get("/api/participante/cedula/0101")
    assert [t["serial"] for t in resp.json["participante"]["tablas"]] == ["CARD00001", "CARD00002"]
    assert client.get("/api/participante/cedula/9999").status_code == 404
    pdf = client.get("/api/participante/cedula/0101/tablas_pdf")
    assert pdf.status_code == 200
    assert pdf.data.startswith(b"%PDF")
