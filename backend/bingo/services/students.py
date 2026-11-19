"""CRUD de estudiantes (colección ``Estudiantes``) y consulta de sus tablas.

La colección conserva sus nombres de campo históricos (``"Primer Apellido"``,
``"Num documento"``, ...). La API expone nombres sin espacios y los traduce.
La cédula (``Num documento``) enlaza al estudiante con ``Participantes.cedula``.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from bson import ObjectId

from ..db import Collections, Doc
from ..errors import ApiError, Conflict, NotFound
from ..utils import require_object_id, safe_int, set_or_unset
from .animators import validate_domain_email

# campo de la API -> campo en Mongo
FIELD_MAP: dict[str, str] = {
    "primer_apellido": "Primer Apellido",
    "segundo_apellido": "Segundo Apellido",
    "nombre": "Nombre",
    "cedula": "Num documento",
    "curso": "Curso",
    "especialidad": "Especialidad",
    "nivel": "Nivel",
    "paralelo": "Paralelo",
}
_REQUIRED = ("primer_apellido", "nombre", "cedula", "curso", "nivel", "paralelo")
_UPPER = ("primer_apellido", "segundo_apellido", "nombre")
MAX_PER_PAGE = 100


def _clean_field(api_key: str, raw: Any) -> Any:
    """Normaliza y valida un campo del estudiante."""
    if api_key == "nivel":
        nivel = safe_int(raw, 0)
        if nivel <= 0:
            raise ApiError("El nivel debe ser un número mayor a 0.")
        return nivel
    value = " ".join(str(raw or "").split())
    if api_key in _UPPER:
        value = value.upper()
    if api_key in _REQUIRED and not value:
        raise ApiError(f"El campo '{api_key}' es obligatorio.")
    if api_key == "cedula" and not value.isdigit():
        raise ApiError("La cédula debe contener solo números.")
    return value


def serialize_student(doc: Doc) -> dict[str, Any]:
    data: dict[str, Any] = {"_id": str(doc["_id"])}
    for api_key, mongo_key in FIELD_MAP.items():
        data[api_key] = doc.get(mongo_key, "")
    data["correo"] = doc.get("correo", "")
    return data


def normalize_words(text: Any) -> list[str]:
    """Palabras en mayúsculas y sin tildes, para comparar nombres escritos a mano."""
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9 ]", " ", plain.upper()).split()


def names_match(doc: Doc, nombres: Any, apellidos: Any) -> bool:
    """El primer nombre escrito está entre los nombres y los apellidos empiezan por el primer apellido."""
    given, surnames = normalize_words(nombres), normalize_words(apellidos)
    first_surname = normalize_words(doc.get("Primer Apellido"))
    return (
        bool(given and first_surname)
        and given[0] in normalize_words(doc.get("Nombre"))
        and surnames[: len(first_surname)] == first_surname
    )


NO_MATCH = "Los datos no coinciden con ningún estudiante. Revisa tu cédula, nombres y apellidos."
TAKEN = "Esta cédula ya fue registrada con otro correo. Comunícate con el administrador."


def full_name(doc: Doc) -> str:
    parts = (doc.get("Nombre"), doc.get("Primer Apellido"), doc.get("Segundo Apellido"))
    return " ".join(str(p) for p in parts if p)


class StudentService:
    def __init__(self, cols: Collections, domains: tuple[str, ...]) -> None:
        self.cols = cols
        self.domains = domains

    def get(self, student_id: Any) -> Doc:
        doc = self.cols.students.find_one({"_id": require_object_id(student_id, "ID de estudiante inválido.")})
        if not doc:
            raise NotFound("Estudiante no encontrado.")
        return doc

    def by_email(self, email: str) -> Doc | None:
        return self.cols.students.find_one({"correo": email.strip().lower()})

    def register_email(self, email: str, cedula: Any, nombres: Any, apellidos: Any) -> Doc:
        """Autorregistro: guarda ``email`` en el estudiante cuya cédula y nombres coinciden.

        El correo viene verificado por Google; la cédula y los nombres los escribe el
        estudiante y deben coincidir con lo cargado desde secretaría.
        """
        cedula = str(cedula or "").strip()
        if not cedula.isdigit():
            raise ApiError("Ingresa tu número de cédula (solo números).")
        if not normalize_words(nombres) or not normalize_words(apellidos):
            raise ApiError("Ingresa tus nombres y apellidos.")
        doc = self.cols.students.find_one({"Num documento": cedula})
        if not doc or not names_match(doc, nombres, apellidos):
            raise ApiError(NO_MATCH)
        if doc.get("correo") and doc["correo"] != email:
            raise Conflict(TAKEN)
        if self.cols.students.find_one({"correo": email, "_id": {"$ne": doc["_id"]}}, {"_id": 1}):
            raise Conflict("Tu correo ya está registrado con otra cédula. Comunícate con el administrador.")
        # Condicional: si otro registro tomó la cédula a la vez, no se pisa.
        result = self.cols.students.update_one(
            {"_id": doc["_id"], "$or": [{"correo": {"$exists": False}}, {"correo": email}]},
            {"$set": {"correo": email}},
        )
        if not result.matched_count:
            raise Conflict(TAKEN)
        return self.get(doc["_id"])

    def search(self, q: str, page: int, per_page: int) -> dict[str, Any]:
        per_page = min(max(per_page, 1), MAX_PER_PAGE)
        page = max(page, 1)
        query: dict[str, Any] = {}
        if q:
            pattern = {"$regex": re.escape(q), "$options": "i"}
            fields = ("Num documento", "Primer Apellido", "Segundo Apellido", "Nombre", "correo")
            query = {"$or": [{f: pattern} for f in fields]}
        total = self.cols.students.count_documents(query)
        docs = (
            self.cols.students.find(query)
            .sort([("Primer Apellido", 1), ("Segundo Apellido", 1), ("Nombre", 1)])
            .skip((page - 1) * per_page)
            .limit(per_page)
        )
        return {"estudiantes": [serialize_student(d) for d in docs], "total": total, "page": page, "per_page": per_page}

    def _clean(self, data: dict[str, Any], partial: bool) -> dict[str, Any]:
        fields = {
            mongo_key: _clean_field(api_key, data.get(api_key))
            for api_key, mongo_key in FIELD_MAP.items()
            if api_key in data or not partial
        }
        if "correo" in data:
            fields["correo"] = validate_domain_email(data.get("correo"), self.domains)
        return fields

    def _ensure_unique(self, fields: dict[str, Any], exclude: ObjectId | None = None) -> None:
        not_self: dict[str, Any] = {"_id": {"$ne": exclude}} if exclude is not None else {}
        cedula = fields.get("Num documento")
        if cedula and self.cols.students.find_one({"Num documento": cedula, **not_self}, {"_id": 1}):
            raise Conflict(f"Ya existe un estudiante con la cédula {cedula}.")
        correo = fields.get("correo")
        if correo and self.cols.students.find_one({"correo": correo, **not_self}, {"_id": 1}):
            raise Conflict(f"El correo {correo} ya está asignado a otro estudiante.")

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        fields = self._clean(data, partial=False)
        self._ensure_unique(fields)
        if not fields.get("correo"):
            fields.pop("correo", None)
        fields["_id"] = self.cols.students.insert_one(fields).inserted_id
        return serialize_student(fields)

    def update(self, student_id: Any, data: dict[str, Any]) -> dict[str, Any]:
        doc = self.get(student_id)
        fields = self._clean(data, partial=True)
        self._ensure_unique(fields, exclude=doc["_id"])
        if fields:
            self.cols.students.update_one({"_id": doc["_id"]}, set_or_unset(fields))
        return serialize_student(self.get(doc["_id"]))

    def delete(self, student_id: Any) -> None:
        doc = self.get(student_id)
        self.cols.students.delete_one({"_id": doc["_id"]})

    def tables_of(self, doc: Doc) -> list[Doc]:
        """Tablas de todos los registros de ``Participantes`` con la cédula del estudiante."""
        cedula = doc.get("Num documento")
        if not cedula:
            return []
        ids = [
            tid for p in self.cols.participants.find({"cedula": cedula}, {"tablas": 1}) for tid in p.get("tablas") or []
        ]
        if not ids:
            return []
        return list(self.cols.tables.find({"_id": {"$in": ids}}).sort("serial", 1))
