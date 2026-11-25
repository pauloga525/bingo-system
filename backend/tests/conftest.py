from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mongomock
import pytest
from bson import ObjectId
from flask import Flask
from flask.testing import FlaskClient

from bingo import create_app
from bingo.config import Settings
from bingo.db import Collections
from bingo.domain.cards import format_serial, generate_bingo_card
from bingo.services.mailer import MemoryMailer

# mongomock 4.3 no acepta el argumento ``sort`` que pymongo>=4.11 pasa en bulk_write.
_original_add_update = mongomock.collection.BulkOperationBuilder.add_update


def _add_update_compat(self: Any, *args: Any, sort: Any = None, **kwargs: Any) -> Any:
    return _original_add_update(self, *args, **kwargs)


mongomock.collection.BulkOperationBuilder.add_update = _add_update_compat


@dataclass
class Seed:
    admin: ObjectId
    ana: ObjectId  # animadora con CARD00001..CARD00010
    beto: ObjectId  # animador con CARD00011..CARD00020
    tables: dict[str, ObjectId]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        json_dir=tmp_path / "jsons",
        winners_dir=tmp_path / "winners",
        upload_dir=tmp_path / "upload",
        backup_dir=tmp_path / "backups",
        debug=False,
        google_client_id="test-client-id",
        secret_key="clave-de-pruebas",
        admin_emails="admin@uets.edu.ec",
        admin_usuario="ADM",
        mail_async=False,  # el correo se envía dentro de la petición (MemoryMailer)
    )


def fake_google_verifier(token: str, client_id: str) -> dict[str, Any]:
    """Doble del verificador de Google: el "token" es ``correo`` o ``correo|hd``.

    ``"invalido"`` simula un token con firma o audiencia incorrecta.
    """
    if token == "invalido" or client_id != "test-client-id":
        raise ValueError("Token used too late")
    email, _, hd = token.partition("|")
    domain = email.rsplit("@", 1)[-1]
    return {"email": email, "email_verified": True, "hd": hd or domain}


@pytest.fixture
def mongo() -> Iterator[mongomock.MongoClient]:
    client: mongomock.MongoClient = mongomock.MongoClient()
    yield client
    client.close()


@pytest.fixture
def app(settings: Settings, mongo: mongomock.MongoClient) -> Flask:
    application = create_app(settings, mongo, fake_google_verifier, MemoryMailer())
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()


@pytest.fixture
def cols(app: Flask) -> Collections:
    collections: Collections = app.extensions["bingo_db"]
    return collections


def _user(cols: Collections, usuario: str, tipo: int, **extra: Any) -> ObjectId:
    doc = {
        "usuario": usuario,
        "nombres_completos": f"Nombre {usuario}",
        "tipo_usuario": tipo,
        **extra,
    }
    inserted: ObjectId = cols.users.insert_one(doc).inserted_id
    return inserted


@pytest.fixture
def seed(cols: Collections, client: FlaskClient) -> Seed:
    """Datos base. Deja el cliente con la sesión de ANA iniciada."""
    tables = {}
    for i in range(1, 21):
        serial = format_serial(i)
        tables[serial] = cols.tables.insert_one(
            {"serial": serial, "matrix": generate_bingo_card(), "won": False, "stateAsigned": False}
        ).inserted_id

    def reserva(desde: int, hasta: int) -> dict[str, Any]:
        ids = [tables[format_serial(i)] for i in range(desde, hasta + 1)]
        return {
            "totalTables": len(ids),
            "usedTables": 0,
            "fromSerial": format_serial(desde),
            "toSerial": format_serial(hasta),
            "reserved_table_ids": ids,
        }

    seed = Seed(
        admin=ensure_admin(cols),
        ana=_user(cols, "ANA", 1, **reserva(1, 10)),
        beto=_user(cols, "BETO", 1, **reserva(11, 20)),
        tables=tables,
    )
    # Animadores con correo (así inician sesión con Google), enlazados a su cuenta de Users.
    # Cada uno con su propio curso (un curso = un animador): ANA en 1° A, BETO en 1° B.
    for usuario, oid, paralelo in (("ANA", seed.ana, "A"), ("BETO", seed.beto, "B")):
        cols.animators.insert_one(
            {
                "profesor": f"Nombre {usuario}",
                "curso": "BACHILLERATO",
                "especialidad": "Ciencias",
                "nivel": 1,
                "paralelo": paralelo,
                "correo": f"{usuario.lower()}@uets.edu.ec",
                "usuario_id": oid,
            }
        )
        _EMAIL_BY_ID[oid] = f"{usuario.lower()}@uets.edu.ec"
    _EMAIL_BY_ID[seed.admin] = EMAILS["admin"]
    login_as(client, "ana")
    return seed


_EMAIL_BY_ID: dict[ObjectId, str] = {}
EMAILS = {"admin": "admin@uets.edu.ec", "ana": "ana@uets.edu.ec", "beto": "beto@uets.edu.ec"}


def login_as(client: FlaskClient, who: str) -> str:
    """Inicia sesión con Google (verificador falso) y deja el token en el cliente.

    ``who`` es ``"admin"``, ``"ana"``, ``"beto"`` o un correo.
    """
    email = EMAILS.get(who, who)
    resp = client.post("/api/auth/google", json={"credential": email})
    assert resp.status_code == 200, resp.json
    token: str = resp.json["token"]
    client.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    return token


def ensure_admin(cols: Collections) -> ObjectId:
    """Cuenta ``ADM`` del administrador (la crea si no existe)."""
    admin = cols.users.find_one({"usuario": "ADM"})
    return admin["_id"] if admin else _user(cols, "ADM", 0)


def board_login(client: FlaskClient, cols: Collections, email: str = "admin@uets.edu.ec") -> Any:
    """Abre la sesión del tablero del juego (cookie) con el login de Google del tablero."""
    ensure_admin(cols)
    return client.post("/tablero/login", json={"credential": email})


def logout(client: FlaskClient) -> None:
    client.environ_base.pop("HTTP_AUTHORIZATION", None)


def register(client: FlaskClient, seller: ObjectId, cedula: str, tablas: list[str]) -> Any:
    """Registra un participante de ``seller`` con tablas específicas y deja iniciada la sesión del vendedor.

    Elegir seriales solo lo puede hacer el administrador (los vendedores venden en
    cola), así que el registro se hace con la sesión del admin.
    """
    login_as(client, "admin")
    resp = client.post(
        "/api/registrarParticipante",
        json={
            "nombre": "Juan",
            "apellido": "Pérez",
            "cedula": cedula,
            "correo": f"c{cedula}@correo.com",
            "tipo": "externo",
            "tablas": tablas,
            "registrado_por": str(seller),
        },
    )
    if seller in _EMAIL_BY_ID:
        login_as(client, _EMAIL_BY_ID[seller])
    return resp
