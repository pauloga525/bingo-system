"""Utilidades transversales: conversión de tipos y serialización de Mongo."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from flask import request

from .errors import ApiError


def safe_int(val: Any, default: int = 0) -> int:
    """Convierte a ``int``; si ``val`` es ``None`` o inválido devuelve ``default``."""
    if val is None:
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def try_object_id(value: Any) -> ObjectId | None:
    """Devuelve un ``ObjectId`` o ``None`` si ``value`` no es un id válido."""
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


def require_object_id(value: Any, message: str) -> ObjectId:
    """Como :func:`try_object_id` pero lanza ``ApiError(400)`` si es inválido."""
    oid = try_object_id(value)
    if oid is None:
        raise ApiError(message)
    return oid


def json_body() -> dict[str, Any]:
    """Cuerpo JSON de la petición como dict (vacío si no es un objeto JSON)."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def serialize_mongo_doc(doc: Any) -> Any:
    """Convierte recursivamente ``ObjectId`` en ``str`` para poder hacer ``jsonify``."""
    if isinstance(doc, ObjectId):
        return str(doc)
    if isinstance(doc, dict):
        return {key: serialize_mongo_doc(value) for key, value in doc.items()}
    if isinstance(doc, list):
        return [serialize_mongo_doc(v) for v in doc]
    return doc


def stringify_keys(obj: Any) -> Any:
    """Convierte claves no-string a ``str`` (p. ej. tuplas) para poder serializar."""
    if isinstance(obj, dict):
        return {str(k): stringify_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [stringify_keys(i) for i in obj]
    return obj


def ids_to_str(ids: Iterable[Any]) -> list[Any]:
    return [str(i) if isinstance(i, ObjectId) else i for i in ids]


def set_or_unset(fields: dict[str, Any]) -> dict[str, Any]:
    """Operación ``update`` de Mongo: ``$set`` para los valores y ``$unset`` para ``None``/``""``."""
    update: dict[str, Any] = {}
    to_set = {k: v for k, v in fields.items() if v not in (None, "")}
    to_unset = {k: "" for k, v in fields.items() if v in (None, "")}
    if to_set:
        update["$set"] = to_set
    if to_unset:
        update["$unset"] = to_unset
    return update
