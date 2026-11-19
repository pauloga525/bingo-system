"""Consultas de tablas (cartones) y búsqueda de personas."""

from __future__ import annotations

import re
from typing import Any

from bson import ObjectId
from pymongo.collection import Collection

from ..db import Collections, Doc
from ..domain.serials import SerialRange
from ..errors import ApiError, NotFound
from ..utils import require_object_id, try_object_id

_PARTICIPANT_FIELDS = {"nombre": 1, "apellido": 1, "cedula": 1, "nivelCurso": 1, "paralelo": 1, "tablas": 1}


def _participant_brief(p: Doc) -> dict[str, Any]:
    return {
        "_id": str(p["_id"]),
        "nombre": p.get("nombre", ""),
        "apellido": p.get("apellido", ""),
        "cedula": p.get("cedula", ""),
        "nivelCurso": p.get("nivelCurso", ""),
        "paralelo": p.get("paralelo", ""),
    }


def _table_full(t: Doc) -> dict[str, Any]:
    return {
        "_id": str(t["_id"]),
        "serial": t.get("serial", ""),
        "matrix": t.get("matrix", []),
        "won": t.get("won", False),
        "stateAsigned": t.get("stateAsigned", False),
        "timestamp": t.get("timestamp", 0),
    }


class TableService:
    def __init__(self, cols: Collections) -> None:
        self.cols = cols

    def _owners_by_table(self, table_ids: list[ObjectId]) -> dict[ObjectId, Doc]:
        """Mapa ``tabla_id -> participante`` con una sola consulta (antes era una por tabla)."""
        owners: dict[ObjectId, Doc] = {}
        if not table_ids:
            return owners
        for p in self.cols.participants.find({"tablas": {"$in": table_ids}}, _PARTICIPANT_FIELDS):
            for tid in p.get("tablas") or []:
                owners.setdefault(tid, p)
        return owners

    def list_tables(self, disponible: str | None, serial: str | None, search: str) -> list[dict[str, Any]]:
        query: dict[str, Any] = {}
        if disponible == "true":
            query["stateAsigned"] = {"$ne": True}
        elif disponible == "false":
            query["stateAsigned"] = True
        if serial:
            query["serial"] = {"$regex": re.escape(serial), "$options": "i"}

        tablas = list(self.cols.tables.find(query).sort("serial", 1))

        if search:
            pattern = {"$regex": re.escape(search), "$options": "i"}
            matching_ids = {
                tid
                for p in self.cols.participants.find({"$or": [{"nombre": pattern}, {"cedula": pattern}]}, {"tablas": 1})
                for tid in p.get("tablas") or []
            }
            needle = search.lower()
            tablas = [t for t in tablas if needle in t.get("serial", "").lower() or t["_id"] in matching_ids]

        owners = self._owners_by_table([t["_id"] for t in tablas if t.get("stateAsigned")])
        result = []
        for t in tablas:
            item = _table_full(t)
            owner = owners.get(t["_id"]) if t.get("stateAsigned") else None
            if owner:
                item["participante"] = _participant_brief(owner)
            result.append(item)
        return result

    def get_table(self, tabla_id: str) -> dict[str, Any]:
        oid = try_object_id(tabla_id)
        tabla = self.cols.tables.find_one({"_id": oid} if oid else {"serial": tabla_id})
        if not tabla:
            raise NotFound("Tabla no encontrada.")
        item = _table_full(tabla)
        if tabla.get("stateAsigned"):
            owner = self.cols.participants.find_one({"tablas": tabla["_id"]}, _PARTICIPANT_FIELDS)
            if owner:
                item["participante"] = _participant_brief(owner)
        return item

    def validate_serial(self, serial: str) -> dict[str, Any]:
        tabla = self.cols.tables.find_one({"serial": serial})
        if not tabla:
            raise NotFound(f"Tabla con serial '{serial}' no encontrada.")
        return {
            "_id": str(tabla["_id"]),
            "serial": tabla.get("serial", ""),
            "disponible": not tabla.get("stateAsigned", False),
            "won": tabla.get("won", False),
        }

    def consecutive_available(self, usuario_id: Any, cantidad: int) -> list[str]:
        """Primeros ``cantidad`` seriales libres (en orden) del rango del usuario. No asigna nada."""
        if not usuario_id:
            raise ApiError("usuario_id es obligatorio.")
        if cantidad <= 0:
            raise ApiError("La cantidad de tablas debe ser mayor a 0.")
        oid = require_object_id(usuario_id, "usuario_id inválido.")
        usuario = self.cols.users.find_one({"_id": oid})
        if not usuario:
            raise NotFound("Usuario no encontrado.")
        rango = SerialRange.of_user(usuario)
        if rango is None:
            raise ApiError("El usuario no tiene un rango de tablas asignado.")

        in_range = {"serial": rango.mongo_filter()}
        if not self.cols.tables.count_documents(in_range, limit=1):
            raise ApiError("No hay tablas en el rango asignado al usuario.")
        libres = [
            t["serial"]
            for t in self.cols.tables.find({**in_range, "stateAsigned": {"$ne": True}}, {"serial": 1})
            .sort("serial", 1)
            .limit(cantidad)
        ]
        if len(libres) < cantidad:
            raise ApiError(
                f"No hay suficientes tablas disponibles. Se encontraron {len(libres)} de {cantidad} solicitadas."
            )
        return libres


class PeopleService:
    """Búsqueda de estudiantes y docentes por cédula o nombre completo exacto."""

    def __init__(self, cols: Collections) -> None:
        self.cols = cols

    @staticmethod
    def _find(collection: Collection[Doc], cedula_field: str, busqueda: str, etiqueta: str) -> Doc:
        busqueda = busqueda.strip()
        if busqueda.isdigit():
            doc = collection.find_one({cedula_field: busqueda}, {"_id": 0})
            if not doc:
                raise NotFound(f"No se encontró ningún {etiqueta} con la cédula: {busqueda}")
            return doc

        palabras = busqueda.upper().split()
        if len(palabras) < 3:
            raise ApiError("Debes ingresar el nombre completo: Primer Apellido, Segundo Apellido y Nombre(s).")
        doc = collection.find_one(
            {"Primer Apellido": palabras[0], "Segundo Apellido": palabras[1], "Nombre": " ".join(palabras[2:])},
            {"_id": 0},
        )
        if not doc:
            raise NotFound(f"No se encontró ningún {etiqueta} con el nombre completo: {busqueda}")
        return doc

    def student(self, busqueda: str) -> Doc:
        return self._find(self.cols.students, "Num documento", busqueda, "estudiante")

    def teacher(self, busqueda: str) -> Doc:
        return self._find(self.cols.teachers, "Cedula", busqueda, "docente")
