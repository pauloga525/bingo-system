"""Acceso a MongoDB: colecciones tipadas e índices."""

from __future__ import annotations

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


# (colección, campos, opciones). ``cedula`` NO es único porque existen datos
# históricos duplicados; la unicidad se valida en el servicio.
_INDEXES: tuple[tuple[str, list[tuple[str, int]], dict[str, Any]], ...] = (
    ("tables", [("serial", ASCENDING)], {"unique": True, "name": "serial_unique"}),
    ("tables", [("stateAsigned", ASCENDING)], {"name": "stateAsigned"}),
    ("participants", [("cedula", ASCENDING)], {"name": "cedula"}),
    ("participants", [("registrado_por", ASCENDING)], {"name": "registrado_por"}),
    ("participants", [("tablas", ASCENDING)], {"name": "tablas"}),
    ("users", [("usuario", ASCENDING)], {"name": "usuario"}),
    ("animators", [("correo", ASCENDING)], {"name": "correo"}),
    ("students", [("correo", ASCENDING)], {"name": "correo"}),
    ("students", [("Num documento", ASCENDING)], {"name": "num_documento"}),
    ("winners", [("serial", ASCENDING)], {"unique": True, "name": "serial_unique"}),
)


def ensure_indexes(cols: Collections) -> None:
    """Crea los índices necesarios. Si alguno falla solo se registra un aviso."""
    for attr, keys, options in _INDEXES:
        collection: Collection[Doc] = getattr(cols, attr)
        try:
            collection.create_index(keys, **options)
        except PyMongoError as exc:
            logger.warning("No se pudo crear el índice %s en %s: %s", options.get("name"), collection.name, exc)
