"""Acceso del público externo con cédula + correo + código por correo."""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

import pytest
from flask.testing import FlaskClient
from itsdangerous import URLSafeTimedSerializer

from bingo.db import Collections
from bingo.services.external_access import MAX_ATTEMPTS, ExternalAccess, utc_now
from bingo.services.mailer import MemoryMailer

from .conftest import Seed, logout, register

CEDULA, CORREO = "0912345678", "c0912345678@correo.com"  # el helper register usa ese correo


@pytest.fixture
def mailer(client: FlaskClient) -> MemoryMailer:
    m: MemoryMailer = client.application.extensions["mailer"]
    return m


@pytest.fixture
def compra(client: FlaskClient, seed: Seed, mailer: MemoryMailer) -> FlaskClient:
    assert register(client, seed.ana, CEDULA, ["CARD00002", "CARD00001"]).status_code == 201
    mailer.sent.clear()
    logout(client)
    return client


def _codigo(mailer: MemoryMailer) -> str:
    m = re.search(r"\b(\d{6})\b", mailer.sent[-1].text)
    assert m
    return m.group(1)


def test_externo_recibe_codigo_y_ve_solo_sus_tablas(compra: FlaskClient, mailer: MemoryMailer) -> None:
    resp = compra.post("/api/auth/externo/codigo", json={"cedula": CEDULA, "correo": CORREO.upper()})
    assert resp.status_code == 200 and "Si los datos coinciden" in resp.json["message"]
    assert mailer.sent[-1].to == CORREO and "Código de acceso" in mailer.sent[-1].subject
    codigo = _codigo(mailer)

    malo = "000000" if codigo != "000000" else "111111"
    assert (
        compra.post(
            "/api/auth/externo/verificar", json={"cedula": CEDULA, "correo": CORREO, "codigo": malo}
        ).status_code
        == 400
    )
    resp = compra.post("/api/auth/externo/verificar", json={"cedula": CEDULA, "correo": CORREO, "codigo": codigo})
    assert resp.status_code == 200, resp.json
    assert resp.json["usuario"]["rol"] == "externo" and resp.json["usuario"]["nombres"] == "Juan Pérez"
    compra.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {resp.json['token']}"

    data = compra.get("/api/mis-tablas").json
    assert data["titular"]["cedula"] == CEDULA
    assert [t["serial"] for t in data["tablas"]] == ["CARD00001", "CARD00002"]
    assert compra.get("/api/auth/me").json["usuario"]["tipo_usuario"] == 3
    # Nada más de la API: ni participantes ni tablas de otros.
    for url in ("/api/participantes", "/api/tablas", "/api/participante/cedula/0912345678", "/api/cola-tablas"):
        assert compra.get(url).status_code == 403, url
    # El código ya no sirve una segunda vez.
    again = {"cedula": CEDULA, "correo": CORREO, "codigo": codigo}
    assert compra.post("/api/auth/externo/verificar", json=again).status_code == 400


def test_datos_que_no_coinciden_no_revelan_nada(compra: FlaskClient, mailer: MemoryMailer, cols: Collections) -> None:
    for body in ({"cedula": CEDULA, "correo": "otro@correo.com"}, {"cedula": "0999999999", "correo": CORREO}):
        resp = compra.post("/api/auth/externo/codigo", json=body)
        assert resp.status_code == 200 and "Si los datos coinciden" in resp.json["message"]
    assert mailer.sent == []  # no se envía nada
    assert (
        compra.post(
            "/api/auth/externo/verificar", json={"cedula": CEDULA, "correo": "otro@correo.com", "codigo": "123456"}
        ).status_code
        == 400
    )
    assert compra.post("/api/auth/externo/codigo", json={"cedula": "abc", "correo": CORREO}).status_code == 400
    assert compra.post("/api/auth/externo/codigo", json={"cedula": CEDULA, "correo": "x"}).status_code == 400


def test_limites_de_envio_e_intentos(compra: FlaskClient, cols: Collections, mailer: MemoryMailer) -> None:
    acceso = ExternalAccess(cols, "s", mailer, run_async=False)
    t0 = utc_now()  # hora real: el índice TTL borra los códigos vencidos
    acceso.request_code(CEDULA, CORREO, now=t0)
    with pytest.raises(Exception, match="Espera un minuto"):
        acceso.request_code(CEDULA, CORREO, now=t0 + timedelta(seconds=30))
    for i in range(1, 5):
        acceso.request_code(CEDULA, CORREO, now=t0 + timedelta(minutes=2 * i))
    with pytest.raises(Exception, match="una hora"):
        acceso.request_code(CEDULA, CORREO, now=t0 + timedelta(minutes=11))

    ahora = t0 + timedelta(minutes=9)
    for _ in range(MAX_ATTEMPTS):
        with pytest.raises(Exception, match="incorrecto"):
            acceso.verify(CEDULA, CORREO, "abcdef", now=ahora)
    with pytest.raises(Exception, match="Demasiados intentos"):
        acceso.verify(CEDULA, CORREO, _codigo(mailer), now=ahora)
    # Vencido a los 10 minutos.
    with pytest.raises(Exception, match="venció"):
        acceso.verify(CEDULA, CORREO, _codigo(mailer), now=t0 + timedelta(minutes=30))
    resp = compra.post("/api/auth/externo/codigo", json={"cedula": CEDULA, "correo": CORREO})
    assert resp.status_code in (200, 429)


def test_sesion_externa_vence_y_se_revoca(compra: FlaskClient, cols: Collections, mailer: MemoryMailer) -> None:
    compra.post("/api/auth/externo/codigo", json={"cedula": CEDULA, "correo": CORREO})
    token = compra.post(
        "/api/auth/externo/verificar", json={"cedula": CEDULA, "correo": CORREO, "codigo": _codigo(mailer)}
    ).json["token"]
    compra.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    assert compra.get("/api/mis-tablas").status_code == 200
    # Token de hace 3 horas (dentro de la sesión del personal, fuera de la del externo).
    viejo = _token_con_edad(compra, {"email": CORREO, "rol": "externo", "cedula": CEDULA}, horas=3)
    compra.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {viejo}"
    assert compra.get("/api/mis-tablas").status_code == 401
    # Si se borra la compra, la sesión deja de servir.
    compra.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    cols.participants.update_one({"cedula": CEDULA}, {"$set": {"correo": "cambiado@correo.com"}})
    assert compra.get("/api/mis-tablas").status_code == 401


def _token_con_edad(client: FlaskClient, data: dict[str, Any], horas: int) -> str:
    import time
    from unittest import mock

    serializer: URLSafeTimedSerializer = client.application.extensions["session_serializer"]
    with mock.patch.object(time, "time", return_value=time.time() - horas * 3600):
        token: str = serializer.dumps(data)
    return token


def test_correo_de_venta_externa_explica_como_entrar(client: FlaskClient, seed: Seed, mailer: MemoryMailer) -> None:
    register(client, seed.ana, "0101", ["CARD00001"])
    assert "Público general" in mailer.sent[-1].text
