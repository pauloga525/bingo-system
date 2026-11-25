"""Vendedores con varios roles, ventas a alumnos de roles sin curso, borrado solo admin y paginación."""

from __future__ import annotations

from typing import Any

import pytest
from bson import ObjectId
from flask.testing import FlaskClient

from bingo.db import Collections
from bingo.domain.roles import clean_roles, rol_para_venta, roles_de, tipos_venta
from bingo.errors import ApiError
from tests.conftest import Seed, login_as

ALUMNO_CORREO = "pepe.perez.est@uets.edu.ec"


@pytest.fixture
def admin(client: FlaskClient, seed: Seed) -> FlaskClient:
    login_as(client, "admin")
    return client


def _vendedor(admin: FlaskClient, correo: str, roles: Any, **extra: Any) -> dict[str, Any]:
    login_as(admin, "admin")
    resp = admin.post(
        "/api/animadores", json={"nombre": correo.split("@")[0], "correo": correo, "roles": roles, **extra}
    )
    assert resp.status_code == 201, resp.json
    vendedor: dict[str, Any] = resp.json["animador"]
    return vendedor


def _alumno(cols: Collections, cedula: str = "0101") -> None:
    cols.students.insert_one(
        {
            "Num documento": cedula,
            "Nombre": "PEPE",
            "Primer Apellido": "PEREZ",
            "Curso": "BACHILLERATO",
            "Especialidad": "Ciencias",
            "Nivel": 1,
            "Paralelo": "A",
        }
    )


def _venta(client: FlaskClient, uid: Any, cantidad: int, **extra: Any) -> Any:
    body = {
        "nombre": "PEPE",
        "apellido": "PEREZ",
        "cedula": "0101",
        "correo": ALUMNO_CORREO,
        "tipo": "alumno",
        "registrado_por": str(uid),
        "cantidad_tablas": cantidad,
        **extra,
    }
    return client.post("/api/registrarParticipante", json=body)


def _user(cols: Collections, oid: Any) -> dict[str, Any]:
    user = cols.users.find_one({"_id": ObjectId(str(oid))})
    assert user is not None
    return user


def test_roles_helpers_multirol() -> None:
    assert clean_roles(["Financiero", "animador", "financiero"]) == ["financiero", "animador"]
    assert clean_roles("secretaria, tecniclub") == ["secretaria", "tecniclub"]
    with pytest.raises(ApiError):
        clean_roles([])
    with pytest.raises(ApiError):
        clean_roles(["jefe"])
    assert roles_de({"roles": ["oratorio", "x"], "rol": "animador"}) == ["oratorio"]
    assert roles_de({"roles": [], "rol": "parroquia"}) == ["parroquia"]
    assert roles_de({"tipo_usuario": 0, "roles": ["financiero"]}) == ["admin"]
    assert tipos_venta(["secretaria"]) == ["alumno", "externo"]
    assert "docente" in tipos_venta(["financiero", "animador"])
    # Sin rol pedido: alumnos con animador si lo tiene; externos con el rol principal.
    assert rol_para_venta(["financiero", "animador"], "alumno") == "animador"
    assert rol_para_venta(["financiero", "animador"], "externo") == "financiero"
    assert rol_para_venta(["financiero", "animador"], "alumno", "financiero") == "financiero"
    assert rol_para_venta(["admin"], "externo", "secretaria") == "admin"
    with pytest.raises(ApiError):
        rol_para_venta(["secretaria"], "externo", "financiero")  # no es su rol
    with pytest.raises(ApiError):
        rol_para_venta(["secretaria"], "docente")
    with pytest.raises(ApiError):
        rol_para_venta(["animador"], "alumno", permitidos=["secretaria"])


def test_vendedor_con_varios_roles(admin: FlaskClient, cols: Collections) -> None:
    v = _vendedor(
        admin,
        "multi@uets.edu.ec",
        ["animador", "financiero"],
        curso="BACHILLERATO",
        especialidad="Ciencias",
        nivel=3,
        paralelo="C",
    )
    assert v["roles"] == ["animador", "financiero"] and v["rol"] == "animador"
    assert v["rol_nombre"] == "Animador, Financiero" and v["curso_asignado"]
    user = _user(cols, v["usuario_id"])
    assert user["roles"] == ["animador", "financiero"]

    # Al quitarle el rol animador pierde el curso; Tecniclub es un rol válido.
    resp = admin.put(f"/api/animadores/{v['_id']}", json={"roles": ["financiero", "tecniclub"]})
    assert resp.status_code == 200, resp.json
    assert resp.json["animador"]["roles"] == ["financiero", "tecniclub"]
    assert not resp.json["animador"]["curso_asignado"]
    assert _user(cols, v["usuario_id"])["roles"] == ["financiero", "tecniclub"]
    resp = admin.put(f"/api/animadores/{v['_id']}", json={"roles": ["financiero", "animador"]})
    assert resp.status_code == 200

    # Perfil: todos sus roles; ve reportes por ser financiero; vende a alumnos, docentes y externos.
    login_as(admin, "multi@uets.edu.ec")
    perfil = admin.get("/api/auth/me").json["usuario"]
    assert perfil["cargos"] == ["financiero", "animador"] and perfil["cargo"] == "financiero"
    assert perfil["ve_reportes"] is True and perfil["solo_externos"] is False
    assert perfil["tipos_venta"] == ["alumno", "docente", "externo"]
    assert admin.get("/api/reportes").status_code == 200

    # Lote con varios roles.
    login_as(admin, "admin")
    resp = admin.post("/api/animadores/lote", json={"correos": "lote@uets.edu.ec", "rol": ["oratorio", "parroquia"]})
    assert resp.status_code == 201
    doc = cols.animators.find_one({"correo": "lote@uets.edu.ec"})
    assert doc is not None and doc["roles"] == ["oratorio", "parroquia"]


def test_secretaria_vende_a_alumno_como_venta_externa(admin: FlaskClient, cols: Collections, seed: Seed) -> None:
    _alumno(cols)
    v = _vendedor(admin, "secre@uets.edu.ec", "secretaria")
    login_as(admin, "secre@uets.edu.ec")
    perfil = admin.get("/api/auth/me").json["usuario"]
    assert perfil["tipos_venta"] == ["alumno", "externo"] and perfil["ve_reportes"] is False

    resp = _venta(admin, v["usuario_id"], 2, nivelCurso="Primero de Bachillerato", paralelo="A")
    assert resp.status_code == 201, resp.json
    p = cols.participants.find_one({"cedula": "0101"})
    assert p is not None and p["tipo"] == "alumno" and p["rol_vendedor"] == "secretaria"
    assert [(x["rol"], x["cantidad"], x["monto"]) for x in p["ventas"]] == [("secretaria", 2, 5)]
    # El alumno puede entrar con su correo institucional.
    assert cols.students.find_one({"Num documento": "0101"})["correo"] == ALUMNO_CORREO  # type: ignore[index]

    login_as(admin, "admin")
    rep = admin.get("/api/reportes").json["reportes"]
    roles = {r["rol"]: r for r in rep["ventas_por_rol"]}
    assert roles["secretaria"]["tablas"] == 2 and roles["animador"]["tablas"] == 0
    # No suma al curso: es venta externa del rol.
    assert rep["conteo_por_curso"] == {}


def test_secretaria_agrega_tablas_a_alumno_de_un_animador(admin: FlaskClient, cols: Collections, seed: Seed) -> None:
    _alumno(cols)
    v = _vendedor(admin, "secre@uets.edu.ec", ["secretaria"])
    login_as(admin, "ana")
    resp = _venta(admin, seed.ana, 2)
    assert resp.status_code == 201, resp.json
    pid = resp.json["participante"]["_id"]

    # Otro animador (sin rol sin curso) no puede tocar al alumno ajeno.
    login_as(admin, "beto")
    assert admin.get(f"/api/participante/{pid}").status_code == 403
    resp = admin.post(f"/api/participante/{pid}/tablas/1", json={"cantidad": 1, "usuario_id": str(seed.beto)})
    assert resp.status_code == 403

    # Secretaría lo encuentra por cédula, puede agregarle tablas y la venta es suya.
    login_as(admin, "secre@uets.edu.ec")
    info = admin.get("/api/participante/cedula/0101").json["participante"]
    assert info["puede_agregar"] is True and info["tipo"] == "alumno"
    assert [(x["rol"], x["cantidad"]) for x in info["ventas"]] == [("animador", 2)]
    resp = admin.post(
        f"/api/participante/{pid}/tablas/1",
        json={"cantidad": 1, "usuario_id": v["usuario_id"], "rol_venta": "animador"},
    )
    assert resp.status_code == 403  # no tiene el rol animador
    resp = admin.post(f"/api/participante/{pid}/tablas/1", json={"cantidad": 1, "usuario_id": v["usuario_id"]})
    assert resp.status_code == 200, resp.json

    p = cols.participants.find_one({"_id": ObjectId(pid)})
    assert p is not None and p["total_pagar"] == 8
    assert [(x["rol"], x["cantidad"], x["monto"]) for x in p["ventas"]] == [("animador", 2, 5), ("secretaria", 1, 3)]
    assert (_user(cols, seed.ana)["usedTables"], _user(cols, seed.ana)["total_vendido"]) == (2, 5)
    secre = _user(cols, v["usuario_id"])
    assert (secre["usedTables"], secre["total_vendido"]) == (1, 3)

    # Ahora lo ve en su lista y en su ficha (con quién vendió qué).
    lista = admin.get(f"/api/participantes/por-usuario/{v['usuario_id']}").json["participantes"]
    assert [x["_id"] for x in lista] == [pid]
    ficha = admin.get(f"/api/participante/{pid}").json["participante"]
    assert [x["vendedor_nombre"] for x in ficha["ventas"]] == ["Nombre ANA", "SECRE"]
    assert admin.post(f"/api/participante/{pid}/correo", json={}).status_code == 200

    # Pero no puede borrar tablas ni al participante.
    tid = p["tablas"][0]
    resp = admin.delete(f"/api/participante/{pid}/tabla/{tid}/1", json={"usuario_id": v["usuario_id"]})
    assert resp.status_code == 403

    # Reportes: cada venta a su vendedor y rol; el curso cuenta por la venta del animador.
    login_as(admin, "admin")
    rep = admin.get("/api/reportes").json["reportes"]
    roles = {r["rol"]: r for r in rep["ventas_por_rol"]}
    assert (roles["animador"]["tablas"], roles["animador"]["monto"]) == (2, 5)
    assert (roles["secretaria"]["tablas"], roles["secretaria"]["monto"]) == (1, 3)
    assert rep["tablas_vendidas"] == 3 and rep["dinero_recaudado"] == 8
    vendedores = {x["id"]: x for x in rep["ventas_por_vendedor"]}
    assert vendedores[v["usuario_id"]]["participantes"] == 1
    assert sum(rep["conteo_por_curso"].values()) == 1

    # El admin quita la tabla de secretaría: se descuenta a ella, no al animador.
    tabla_secre = p["ventas"][1]["tablas"][0]
    resp = admin.delete(f"/api/participante/{pid}/tabla/{tabla_secre}/1", json={"usuario_id": str(seed.admin)})
    assert resp.status_code == 200, resp.json
    secre = _user(cols, v["usuario_id"])
    assert (secre["usedTables"], secre["total_vendido"]) == (0, 0)
    p = cols.participants.find_one({"_id": ObjectId(pid)})
    assert p is not None and [x["rol"] for x in p["ventas"]] == ["animador"]

    # Al eliminarlo se descuenta a cada vendedor.
    admin.post(f"/api/participante/{pid}/tablas/1", json={"cantidad": 1, "usuario_id": str(seed.admin)})
    assert admin.delete(f"/api/participante/{pid}/1", json={"usuario_id": str(seed.admin)}).status_code == 200
    for oid in (seed.ana, seed.admin):
        assert (_user(cols, oid).get("usedTables"), _user(cols, oid).get("total_vendido")) == (0, 0)


def test_participante_antiguo_sin_registro_de_ventas(admin: FlaskClient, cols: Collections, seed: Seed) -> None:
    """Los documentos anteriores (sin ``ventas``) se leen como una venta de quien los registró."""
    tablas = [seed.tables["CARD00001"], seed.tables["CARD00002"]]
    cols.tables.update_many({"_id": {"$in": tablas}}, {"$set": {"stateAsigned": True}})
    pid = cols.participants.insert_one(
        {
            "nombre": "VIEJO",
            "cedula": "0777",
            "tipo": "alumno",
            "tablas": tablas,
            "registrado_por": seed.ana,
            "total_pagar": 5,
        }
    ).inserted_id
    cols.users.update_one({"_id": seed.ana}, {"$set": {"usedTables": 2, "total_vendido": 5}})
    v = _vendedor(admin, "fin@uets.edu.ec", "financiero")
    login_as(admin, "fin@uets.edu.ec")
    resp = admin.post(f"/api/participante/{pid}/tablas/1", json={"cantidad": 1, "usuario_id": v["usuario_id"]})
    assert resp.status_code == 200, resp.json
    p = cols.participants.find_one({"_id": pid})
    assert p is not None
    assert [(x["rol"], x["cantidad"], x["monto"]) for x in p["ventas"]] == [("animador", 2, 5), ("financiero", 1, 3)]

    # El admin quita una tabla de la venta original: se descuenta al animador.
    login_as(admin, "admin")
    tabla = seed.tables["CARD00001"]
    assert (
        admin.delete(f"/api/participante/{pid}/tabla/{tabla}/1", json={"usuario_id": str(seed.admin)}).status_code
        == 200
    )
    assert _user(cols, seed.ana)["usedTables"] == 1


def test_auditoria_cuenta_solo_las_ventas_propias(admin: FlaskClient, cols: Collections, seed: Seed) -> None:
    from bingo.services.users import UserService

    _alumno(cols)
    v = _vendedor(admin, "secre@uets.edu.ec", "secretaria")
    login_as(admin, "ana")
    pid = _venta(admin, seed.ana, 2).json["participante"]["_id"]
    login_as(admin, "secre@uets.edu.ec")
    admin.post(f"/api/participante/{pid}/tablas/1", json={"cantidad": 1, "usuario_id": v["usuario_id"]})
    svc = UserService(cols)
    secre = svc.audit_counters(v["usuario_id"], apply=False)
    assert (secre["tablas_reales_asignadas"], secre["total_vendido_real"], secre["diferencia"]) == (1, 3, 0)
    ana = svc.audit_counters(seed.ana, apply=False)
    assert (ana["tablas_reales_asignadas"], ana["total_vendido_real"]) == (2, 5)


def test_tablas_paginadas(admin: FlaskClient, cols: Collections, seed: Seed) -> None:
    resp = admin.get("/api/tablas?page=2&per_page=5").json
    assert (resp["total"], resp["page"], resp["pages"], resp["count"]) == (20, 2, 4, 5)
    assert [t["serial"] for t in resp["tablas"]] == [f"CARD{i:05d}" for i in range(6, 11)]
    # Página fuera de rango: se ajusta a la última.
    assert admin.get("/api/tablas?page=99&per_page=5").json["page"] == 4
    # Búsqueda por serial o por el nombre del participante, también paginada.
    cols.participants.insert_one({"nombre": "LUCIA", "apellido": "MORA", "tablas": [seed.tables["CARD00017"]]})
    cols.tables.update_one({"_id": seed.tables["CARD00017"]}, {"$set": {"stateAsigned": True}})
    resp = admin.get("/api/tablas?page=1&search=mora").json
    assert [t["serial"] for t in resp["tablas"]] == ["CARD00017"]
    assert resp["tablas"][0]["participante"]["nombre"] == "LUCIA"
    assert admin.get("/api/tablas?page=1&search=CARD0001").json["total"] == 10
    # Sin page: lista completa (compatibilidad).
    assert admin.get("/api/tablas").json["count"] == 20
