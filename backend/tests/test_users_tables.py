from __future__ import annotations

from flask.testing import FlaskClient

from bingo.db import Collections
from bingo.domain.cards import format_serial

from .conftest import Seed, login_as, register


def test_queue_preview_validations(client: FlaskClient, seed: Seed) -> None:
    assert client.post("/api/obtenerTablasConsecutivas", json={"cantidad_tablas": 0}).status_code == 400
    resp = client.post("/api/obtenerTablasConsecutivas", json={"cantidad_tablas": 21})
    assert resp.status_code == 400 and resp.json["message"] == "Solo quedan 20 tablas disponibles."


def test_validar_tablas_get_is_read_only_and_post_fixes(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    register(client, seed.ana, "0101", ["CARD00001", "CARD00002"])
    cols.users.update_one({"_id": seed.ana}, {"$set": {"usedTables": 7, "total_vendido": 99}})
    assert client.get(f"/api/validar-tablas/{seed.ana}").status_code == 403  # solo admin
    login_as(client, "admin")

    dry = client.get(f"/api/validar-tablas/{seed.ana}").json
    assert (dry["diferencia"], dry["corregido"]) == (5, False)
    assert cols.users.find_one({"_id": seed.ana})["usedTables"] == 7  # type: ignore[index]

    fixed = client.post(f"/api/validar-tablas/{seed.ana}").json
    assert fixed["corregido"] is True
    ana = cols.users.find_one({"_id": seed.ana})
    assert ana is not None
    assert (ana["usedTables"], ana["total_vendido"]) == (2, 5)


def test_tables_listing_with_owner_and_search(client: FlaskClient, seed: Seed) -> None:
    register(client, seed.ana, "0101", ["CARD00001"])
    resp = client.get("/api/tablas", query_string={"disponible": "false"})
    assert resp.json["count"] == 1
    assert resp.json["tablas"][0]["participante"]["cedula"] == "0101"
    assert client.get("/api/tablas", query_string={"disponible": "true"}).json["count"] == 19
    assert client.get("/api/tablas", query_string={"search": "0101"}).json["count"] == 1
    assert client.get("/api/tablas", query_string={"serial": "CARD0001"}).json["count"] == 10
    # Caracteres especiales de regex ya no rompen la consulta.
    assert client.get("/api/tablas", query_string={"search": "(["}).status_code == 200


def test_single_table_and_validation(client: FlaskClient, seed: Seed) -> None:
    register(client, seed.ana, "0101", ["CARD00001"])
    by_id = client.get(f"/api/tablas/{seed.tables['CARD00001']}").json["tabla"]
    by_serial = client.get("/api/tablas/CARD00001").json["tabla"]
    assert by_id["participante"]["cedula"] == by_serial["participante"]["cedula"] == "0101"
    assert client.get("/api/tablas/CARD99999").status_code == 404
    assert client.get("/api/validarTabla/CARD00001").json["tabla"]["disponible"] is False
    assert client.get("/api/validarTabla/CARD00002").json["tabla"]["disponible"] is True


def test_people_search(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    cols.students.insert_one(
        {"Num documento": "0911", "Primer Apellido": "PEREZ", "Segundo Apellido": "LOPEZ", "Nombre": "ANA MARIA"}
    )
    cols.teachers.insert_one(
        {"Cedula": "0922", "Primer Apellido": "RUIZ", "Segundo Apellido": "DIAZ", "Nombre": "LUIS"}
    )
    assert client.get("/api/estudiante/0911").json["estudiante"]["Nombre"] == "ANA MARIA"
    assert client.get("/api/estudiante/perez lopez ana maria").status_code == 200
    assert client.get("/api/estudiante/perez").status_code == 400
    assert client.post("/api/validarTabla/0911").json["success"] is True
    assert client.get("/api/docente/0922").json["docente"]["Nombre"] == "LUIS"
    assert client.get("/api/docente/0000").status_code == 404


def test_reports_use_single_pricing_rule(client: FlaskClient, seed: Seed) -> None:
    register(client, seed.ana, "0101", [format_serial(i) for i in range(1, 6)])
    register(client, seed.beto, "0202", ["CARD00011"])
    assert client.get("/api/reportes").status_code == 403  # solo admin
    login_as(client, "admin")
    rep = client.get("/api/reportes").json["reportes"]
    assert rep["total_vendido"] == 6
    assert rep["ventas_por_usuario"] == {"Nombre ANA": 10, "Nombre BETO": 3}
    assert rep["usuario_top"]["id"] == str(seed.ana)
    assert rep["total_tablas"] == 20


def test_reports_with_mixed_key_types(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    register(client, seed.ana, "0101", ["CARD00001"])
    register(client, seed.ana, "0202", ["CARD00002"])
    cols.participants.update_one({"cedula": "0101"}, {"$set": {"nivelCurso": 8}})
    cols.participants.update_one({"cedula": "0202"}, {"$set": {"nivelCurso": "BACHILLERATO"}})
    login_as(client, "admin")
    resp = client.get("/api/reportes")
    assert resp.status_code == 200  # antes: 500 al ordenar claves int y str
    assert resp.json["reportes"]["conteo_por_nivel"] == {"8": 1, "BACHILLERATO": 1}
