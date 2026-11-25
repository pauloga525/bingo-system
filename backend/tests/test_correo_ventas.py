"""Correo obligatorio en la venta y envío de las tablas por correo."""

from __future__ import annotations

from typing import Any

import pytest
from bson import ObjectId
from flask.testing import FlaskClient

from bingo.db import Collections
from bingo.services import notifications
from bingo.services.mailer import Mail, MailNotConfigured, MemoryMailer, SmtpConfig, SmtpMailer, build_message
from bingo.services.notifications import TablesMailer

from .conftest import Seed, login_as

ALUMNO_CORREO = "pepe.perez.est@uets.edu.ec"


@pytest.fixture
def mailer(client: FlaskClient) -> MemoryMailer:
    m: MemoryMailer = client.application.extensions["mailer"]
    return m


def _vender(client: FlaskClient, seed: Seed, **extra: Any) -> Any:
    body = {
        "nombre": "Pepe",
        "apellido": "Pérez",
        "cedula": "0101",
        "registrado_por": str(seed.ana),
        "cantidad_tablas": 3,
    }
    return client.post("/api/registrarParticipante", json={**body, **extra})


def _alumno(cols: Collections, cedula: str = "0101", **extra: Any) -> None:
    cols.students.insert_one({"Num documento": cedula, "Nombre": "PEPE", "Primer Apellido": "PEREZ", **extra})


def test_sale_requires_valid_email(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    resp = _vender(client, seed, tipo="externo")
    assert resp.status_code == 400 and "correo es obligatorio" in resp.json["message"]
    assert _vender(client, seed, tipo="externo", correo="no-es-correo").status_code == 400
    # El alumno debe existir en Estudiantes y usar su correo institucional.
    resp = _vender(client, seed, tipo="alumno", correo="pepe@gmail.com")
    assert resp.status_code == 400 and "institucional" in resp.json["message"]
    resp = _vender(client, seed, tipo="alumno", correo=ALUMNO_CORREO)
    assert resp.status_code == 400 and "lista de estudiantes" in resp.json["message"]
    _alumno(cols, cedula="0999", correo=ALUMNO_CORREO)  # otro estudiante ya usa ese correo
    _alumno(cols)
    resp = _vender(client, seed, tipo="alumno", correo=ALUMNO_CORREO)
    assert resp.status_code == 409 and resp.json["correo_ocupado"] is True
    assert cols.participants.count_documents({}) == 0
    assert cols.tables.count_documents({"stateAsigned": True}) == 0


def test_student_sale_saves_email_and_sends_tables(
    client: FlaskClient, cols: Collections, seed: Seed, mailer: MemoryMailer
) -> None:
    _alumno(cols, correo="viejo.mal.est@uets.edu.ec")
    resp = _vender(client, seed, tipo="alumno", correo=f"  {ALUMNO_CORREO.upper()} ")
    assert resp.status_code == 201, resp.json
    # El correo corregido queda en la ficha del estudiante (con él inicia sesión).
    assert cols.students.find_one({"Num documento": "0101"})["correo"] == ALUMNO_CORREO  # type: ignore[index]
    p = cols.participants.find_one({"cedula": "0101"})
    assert p is not None and p["correo"] == ALUMNO_CORREO
    assert p["correo_estado"] == "enviado" and p["correo_enviado_at"]

    (mail,) = mailer.sent
    assert mail.to == ALUMNO_CORREO and "(3)" in mail.subject
    assert all(s in mail.text for s in ("CARD00001", "CARD00002", "CARD00003", "$8"))
    assert "https://consultas.uets.edu.ec" in mail.text  # cómo verlas en línea
    (pdf,) = mail.attachments
    assert pdf.filename == "tablas_bingo_0101.pdf" and pdf.content.startswith(b"%PDF")

    # El estudiante ya puede entrar con ese correo y ver sus tablas.
    login_as(client, ALUMNO_CORREO)
    assert [t["serial"] for t in client.get("/api/mis-tablas").json["tablas"]] == [
        "CARD00001",
        "CARD00002",
        "CARD00003",
    ]


def test_adding_tables_sends_the_updated_list(
    client: FlaskClient, cols: Collections, seed: Seed, mailer: MemoryMailer
) -> None:
    pid = _vender(client, seed, tipo="externo", correo="ext@correo.com").json["participante"]["_id"]
    resp = client.post(f"/api/participante/{pid}/tablas/1", json={"cantidad": 2, "usuario_id": str(seed.ana)})
    assert resp.status_code == 200
    assert len(mailer.sent) == 2 and "Público general" in mailer.sent[1].text
    assert "(5)" in mailer.sent[1].subject and "$10" in mailer.sent[1].text


def test_resend_and_fix_email(client: FlaskClient, cols: Collections, seed: Seed, mailer: MemoryMailer) -> None:
    pid = _vender(client, seed, tipo="externo", correo="mal@correo.com").json["participante"]["_id"]
    resp = client.post(f"/api/participante/{pid}/correo", json={"correo": "bien@correo.com"})
    assert resp.status_code == 200 and resp.json["correo"] == "bien@correo.com"
    assert mailer.sent[-1].to == "bien@correo.com"
    assert client.post(f"/api/participante/{pid}/correo", json={}).json["correo_estado"] == "enviado"
    assert len(mailer.sent) == 3
    assert client.post(f"/api/participante/{pid}/correo", json={"correo": "x"}).status_code == 400
    # Otro vendedor no puede tocar el participante.
    login_as(client, "beto")
    assert client.post(f"/api/participante/{pid}/correo", json={}).status_code == 403


def test_send_failures_are_recorded_not_raised(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    mailer: MemoryMailer = client.application.extensions["mailer"]
    mailer.fail_with = "SMTP caído"
    resp = _vender(client, seed, tipo="externo", correo="ext@correo.com")
    assert resp.status_code == 201  # la venta no se pierde por el correo
    p = cols.participants.find_one({})
    assert p is not None and (p["correo_estado"], p["correo_error"]) == ("error", "SMTP caído")

    sin_smtp = TablesMailer(cols, SmtpMailer(SmtpConfig("", 465, "", "", "")), "http://x", run_async=False)
    assert sin_smtp.send_now(p["_id"]) == "sin_configurar"
    assert sin_smtp.send_now(ObjectId()) == "error"  # participante inexistente
    with pytest.raises(Exception, match="no encontrado"):
        sin_smtp.notify(ObjectId())


def test_notify_runs_in_background(cols: Collections, seed: Seed, monkeypatch: pytest.MonkeyPatch) -> None:
    pid = cols.participants.insert_one({"nombre": "X", "correo": "x@correo.com", "tablas": []}).inserted_id
    enviados: list[Any] = []

    class Inmediato:
        def submit(self, fn: Any, *args: Any) -> None:
            enviados.append(args)
            fn(*args)

    monkeypatch.setattr(notifications, "_EXECUTOR", Inmediato())
    memoria = MemoryMailer()
    TablesMailer(cols, memoria, "http://x").notify(pid)
    assert enviados == [(pid,)] and len(memoria.sent) == 1


def test_mail_helpers() -> None:
    assert SmtpConfig("h", 465, "u", "p", "f").ready and not SmtpConfig("", 465, "", "", "").ready
    msg = build_message(Mail("a@b.com", "Asunto", "texto", "<p>html</p>"), "Yo <yo@b.com>")
    assert msg["To"] == "a@b.com" and msg.is_multipart()
    with pytest.raises(MailNotConfigured):
        SmtpMailer(SmtpConfig("", 465, "", "", "")).send(Mail("a@b.com", "s", "t"))
