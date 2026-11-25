"""Acceso a MongoDB: colecciones tipadas e índices."""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from typing import Any

from flask import Flask, current_app
from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import PyMongoError

logger = logging.getLogger(__name__)

Doc = dict[str, Any]
_EXTENSION_KEY = "bingo_db"


@dataclass(frozen=True)
class Collections:
    """Colecciones usadas por la aplicación (los nombres son los históricos)."""

    client: MongoClient[Doc]
    database: Database[Doc]
    tables: Collection[Doc]
    winners: Collection[Doc]
    students: Collection[Doc]
    teachers: Collection[Doc]
    participants: Collection[Doc]
    users: Collection[Doc]
    animators: Collection[Doc]
    # Códigos de acceso del público externo (vencen solos con un índice TTL).
    codes: Collection[Doc]
    # Correos que intentaron entrar al panel sin estar autorizados.
    access_log: Collection[Doc]

    @classmethod
    def from_client(cls, client: MongoClient[Doc], db_name: str) -> Collections:
        db = client[db_name]
        return cls(
            client=client,
            database=db,
            tables=db["tablas"],
            winners=db["tablas_ganadoras"],
            students=db["Estudiantes"],
            teachers=db["Docentes"],
            participants=db["Participantes"],
            users=db["Users"],
            animators=db["Animadores"],
            codes=db["CodigosAcceso"],
            access_log=db["IntentosAcceso"],
        )


def init_db(app: Flask, client: MongoClient[Doc], db_name: str) -> Collections:
    """Registra las colecciones en la app para usarlas con :func:`get_db`."""
    cols = Collections.from_client(client, db_name)
    app.extensions[_EXTENSION_KEY] = cols
    return cols


def get_db() -> Collections:
    """Devuelve las colecciones de la app activa."""
    cols: Collections = current_app.extensions[_EXTENSION_KEY]
    return cols


# (colección, campos, opciones). La cédula del participante es única (ver
# ``_ensure_unique_cedula``): así dos registros simultáneos no la duplican.
_INDEXES: tuple[tuple[str, list[tuple[str, int]], dict[str, Any]], ...] = (
    ("tables", [("serial", ASCENDING)], {"unique": True, "name": "serial_unique"}),
    ("tables", [("stateAsigned", ASCENDING)], {"name": "stateAsigned"}),
    # Cola de venta: primera tabla libre por serial (services/queue.py).
    ("tables", [("stateAsigned", ASCENDING), ("serial", ASCENDING)], {"name": "cola_venta"}),
    ("participants", [("registrado_por", ASCENDING)], {"name": "registrado_por"}),
    ("participants", [("tablas", ASCENDING)], {"name": "tablas"}),
    ("users", [("usuario", ASCENDING)], {"name": "usuario"}),
    ("animators", [("correo", ASCENDING)], {"name": "correo"}),
    # Un curso (paralelo) solo puede tener un animador.
    (
        "animators",
        [("curso", ASCENDING), ("especialidad", ASCENDING), ("nivel", ASCENDING), ("paralelo", ASCENDING)],
        {"unique": True, "name": "curso_unico", "partialFilterExpression": {"curso": {"$exists": True}}},
    ),
    ("students", [("correo", ASCENDING)], {"name": "correo"}),
    ("students", [("Num documento", ASCENDING)], {"name": "num_documento"}),
    ("winners", [("serial", ASCENDING)], {"unique": True, "name": "serial_unique"}),
    ("codes", [("expira", ASCENDING)], {"expireAfterSeconds": 0, "name": "vence"}),
    ("codes", [("cedula", ASCENDING), ("correo", ASCENDING)], {"name": "cedula_correo"}),
    ("access_log", [("correo", ASCENDING)], {"unique": True, "name": "correo"}),
)


def _ensure_unique_cedula(cols: Collections) -> None:
    """Índice único ``Participantes.cedula``.

    Reemplaza el índice antiguo no único. Si la base tiene cédulas repetidas (datos
    históricos) no se puede crear: se deja el índice normal y se registra un aviso; la
    unicidad la sigue validando el servicio.
    """
    collection: Collection[Doc] = cols.participants
    try:
        actuales = collection.index_information()
        if "cedula" in actuales and not actuales["cedula"].get("unique"):
            collection.drop_index("cedula")
        collection.create_index([("cedula", ASCENDING)], unique=True, name="cedula")
    except PyMongoError as exc:
        logger.warning("Cédulas repetidas en Participantes: no se pudo crear el índice único (%s)", exc)
        with contextlib.suppress(PyMongoError):
            collection.create_index([("cedula", ASCENDING)], name="cedula")


def ensure_indexes(cols: Collections) -> None:
    """Crea los índices necesarios. Si alguno falla solo se registra un aviso."""
    _ensure_unique_cedula(cols)
    for attr, keys, options in _INDEXES:
        collection: Collection[Doc] = getattr(cols, attr)
        try:
            collection.create_index(keys, **options)
        except PyMongoError as exc:
            logger.warning("No se pudo crear el índice %s en %s: %s", options.get("name"), collection.name, exc)
