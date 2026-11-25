from __future__ import annotations

from typing import Any

from bson import ObjectId
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


def test_animator_cannot_choose_specific_tables(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    resp = client.post(
        "/api/registrarParticipante",
        json={
            "nombre": "J",
            "cedula": "0101",
            "correo": "ext@correo.com",
            "tipo": "externo",
            "registrado_por": str(seed.ana),
            "tablas": ["CARD00015"],
        },
    )
    assert resp.status_code == 403
    assert "cola" in resp.json["message"]
    assert cols.participants.count_documents({}) == 0


def test_register_rejects_already_assigned_and_rolls_back(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    assert register(client, seed.ana, "0101", ["CARD00002"]).status_code == 201
    resp = register(client, seed.ana, "0202", ["CARD00001", "CARD00002"])
    assert resp.status_code == 409
    # CARD00001 se tomó y luego se liberó (compensación).
    assert cols.tables.find_one({"serial": "CARD00001"})["stateAsigned"] is False  # type: ignore[index]
    assert _user(cols, seed.ana)["usedTables"] == 1


def _vender(client: FlaskClient, seller: str, uid: ObjectId, cedula: str, cantidad: int) -> Any:
    login_as(client, seller)
    return client.post(
        "/api/registrarParticipante",
        json={
            "nombre": "J",
            "cedula": cedula,
            "correo": "ext@correo.com",
            "tipo": "externo",
            "registrado_por": str(uid),
            "cantidad_tablas": cantidad,
        },
    )


def test_sales_take_consecutive_tables_from_the_queue(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    assert client.get("/api/cola-tablas").json == {
        "success": True,
        "total": 20,
        "vendidas": 0,
        "disponibles": 20,
        "siguiente": "CARD00001",
    }
    vista = client.post("/api/obtenerTablasConsecutivas", json={"cantidad_tablas": 3}).json
    assert vista["tablas_consecutivas"] == ["CARD00001", "CARD00002", "CARD00003"]

    # ANA vende 4 -> 001..004; BETO vende 2 -> 005..006 (sin rangos por vendedor).
    r1 = _vender(client, "ana", seed.ana, "01", 4)
    assert r1.status_code == 201, r1.json
    assert r1.json["participante"]["seriales"] == [f"CARD0000{i}" for i in range(1, 5)]
    assert r1.json["participante"]["total_pagar"] == 10
    r2 = _vender(client, "beto", seed.beto, "02", 2)
    assert r2.json["participante"]["seriales"] == ["CARD00005", "CARD00006"]

    # El admin puede asignar una tabla específica; la cola la salta.
    login_as(client, "admin")
    assert (
        client.post(
            "/api/registrarParticipante",
            json={
                "nombre": "A",
                "cedula": "03",
                "correo": "ext@correo.com",
                "tipo": "externo",
                "registrado_por": str(seed.admin),
                "tablas": ["CARD00008"],
            },
        ).status_code
        == 201
    )
    r3 = _vender(client, "ana", seed.ana, "04", 2)
    assert r3.json["participante"]["seriales"] == ["CARD00007", "CARD00009"]

    # Si se libera una venta, sus tablas vuelven a la cola.
    login_as(client, "beto")
    pid = r2.json["participante"]["_id"]
    assert client.delete(f"/api/participante/{pid}/1", json={"usuario_id": str(seed.beto)}).status_code == 200
    assert client.get("/api/cola-tablas").json["siguiente"] == "CARD00005"

    # No alcanzan las tablas: no se asigna nada.
    r4 = _vender(client, "ana", seed.ana, "05", 50)
    assert r4.status_code == 409 and "Solo quedan" in r4.json["message"]
    assert r4.json["sin_tablas"] is True and r4.json["disponibles"] == 13
    assert cols.participants.count_documents({"cedula": "05"}) == 0
    assert _user(cols, seed.ana)["usedTables"] == 6


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
    assert resp.status_code == 409


def _participant_id(client: FlaskClient, seller: object, cedula: str, tablas: list[str]) -> str:
    resp = register(client, seller, cedula, tablas)  # type: ignore[arg-type]
    assert resp.status_code == 201, resp.json
    return str(resp.json["participante"]["_id"])


def test_add_tables_recomputes_total_and_counters(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    pid = _participant_id(client, seed.ana, "0101", ["CARD00001", "CARD00002", "CARD00003", "CARD00004"])
    resp = client.post(f"/api/participante/{pid}/tablas/1", json={"cantidad": 1, "usuario_id": str(seed.ana)})
    assert resp.status_code == 200, resp.json
    assert resp.json["seriales"] == ["CARD00005"]
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


def test_animator_cannot_add_specific_tables(client: FlaskClient, seed: Seed) -> None:
    pid = _participant_id(client, seed.ana, "0101", ["CARD00001"])
    resp = client.post(f"/api/participante/{pid}/tablas/1", json={"tablas": ["CARD00015"], "usuario_id": str(seed.ana)})
    assert resp.status_code == 403


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
        json={
            "nombre": "Eva",
            "cedula": "0303",
            "correo": "ext@correo.com",
            "tipo": "externo",
            "registrado_por": str(seed.ana),
            "cantidad_tablas": 2,
        },
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


def test_queue_is_all_or_nothing_when_another_process_takes_the_last_tables(cols: Collections, seed: Seed) -> None:
    from bingo.errors import ApiError
    from bingo.services.queue import TableQueue

    cola = TableQueue(cols)
    pid = ObjectId()
    real_pop = cola._pop
    llamadas = 0

    def pop_con_competencia(participant_id: ObjectId) -> ObjectId | None:
        nonlocal llamadas
        llamadas += 1
        if llamadas == 2:  # otro proceso se lleva todas las libres justo ahora
            cols.tables.update_many({"stateAsigned": {"$ne": True}}, {"$set": {"stateAsigned": True}})
        return real_pop(participant_id)

    cola._pop = pop_con_competencia  # type: ignore[method-assign]
    try:
        cola.take(3, pid)
    except ApiError as exc:
        assert exc.message == "Solo quedan 1 tablas disponibles."  # la devuelta
    else:  # pragma: no cover
        raise AssertionError("debía fallar")
    # La primera tabla que alcanzó a tomar volvió a la cola (no quedó a medias).
    assert cols.tables.count_documents({"assignedToParticipant": pid}) == 0
    assert cols.tables.find_one({"serial": "CARD00001"})["stateAsigned"] is False  # type: ignore[index]


def test_same_cedula_twice_at_once_keeps_one_and_returns_tables(cols: Collections, seed: Seed) -> None:
    """Doble clic o dos vendedores con la misma cédula: el índice único deja solo un registro."""
    from bingo.db import ensure_indexes
    from bingo.errors import Conflict
    from bingo.services.participants import ParticipantService

    ensure_indexes(cols)
    assert cols.participants.index_information()["cedula"]["unique"] is True
    svc = ParticipantService(cols)
    body = {
        "nombre": "J",
        "cedula": "0101",
        "correo": "ext@correo.com",
        "tipo": "externo",
        "registrado_por": str(seed.ana),
        "cantidad_tablas": 2,
    }
    svc.register(body)
    # Simula la carrera: la segunda petición pasó la revisión previa antes de que existiera la primera.
    svc._ensure_cedula_free = lambda cedula: None  # type: ignore[method-assign]
    try:
        svc.register(body)
    except Conflict as exc:
        assert "ya fue registrado por" in exc.message
    else:  # pragma: no cover
        raise AssertionError("debía fallar")
    assert cols.participants.count_documents({"cedula": "0101"}) == 1
    # Las tablas tomadas por el segundo intento volvieron a la cola.
    assert cols.tables.count_documents({"stateAsigned": True}) == 2
    assert cols.tables.find_one({"serial": "CARD00003"})["stateAsigned"] is False  # type: ignore[index]


def test_unique_cedula_index_falls_back_when_old_data_has_duplicates(cols: Collections) -> None:
    from bingo.db import ensure_indexes

    # Base antigua: índice no único y cédulas repetidas.
    cols.participants.drop_index("cedula")
    cols.participants.create_index("cedula", name="cedula")
    cols.participants.insert_many([{"cedula": "1"}, {"cedula": "1"}])
    ensure_indexes(cols)
    info = cols.participants.index_information()["cedula"]
    assert not info.get("unique")
