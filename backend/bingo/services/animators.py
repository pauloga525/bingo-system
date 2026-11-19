"""CRUD de animadores (colección ``Animadores``) sincronizado con su cuenta en ``Users``.

``Animadores`` guarda los datos del curso y el correo con el que el animador
inicia sesión con Google. ``Users`` es la cuenta operativa: de ahí salen las
tablas reservadas, los contadores y el ``registrado_por`` de los participantes,
por eso cada animador queda enlazado a su usuario mediante ``usuario_id``.

Los documentos históricos guardan el nombre en ``profesor`` o en ``tutor``; se
respeta el campo que ya exista.
"""

from __future__ import annotations

import re
from typing import Any

from bson import ObjectId

from ..db import Collections, Doc
from ..errors import ApiError, Conflict, NotFound
from ..utils import require_object_id, safe_int, set_or_unset

ANIMADOR = 1
_TEXT_FIELDS = ("curso", "especialidad", "paralelo")


def _clean_field(key: str, raw: Any) -> Any:
    """Normaliza y valida un campo obligatorio del animador."""
    if key == "nivel":
        nivel = safe_int(raw, 0)
        if nivel <= 0:
            raise ApiError("El nivel debe ser un número mayor a 0.")
        return nivel
    value = " ".join(str(raw or "").split())
    if not value:
        raise ApiError(f"El campo '{key}' es obligatorio.")
    return value.upper() if key == "nombre" else value


def _reservation(user: Doc | None) -> dict[str, Any] | None:
    total = safe_int((user or {}).get("totalTables"), 0)
    if not user or total <= 0:
        return None
    return {
        "total": total,
        "usadas": safe_int(user.get("usedTables"), 0),
        "desde": user.get("fromSerial"),
        "hasta": user.get("toSerial"),
    }


def animator_name(doc: Doc) -> str:
    return str(doc.get("profesor") or doc.get("tutor") or "").strip()


def normalize_email(value: Any) -> str:
    return str(value or "").strip().lower()


def validate_domain_email(value: Any, domain: str | tuple[str, ...], required: bool = False) -> str | None:
    """Devuelve el correo en minúsculas, ``None`` si viene vacío, o lanza ``ApiError``."""
    domains = (domain,) if isinstance(domain, str) else domain
    email = normalize_email(value)
    if not email:
        if required:
            raise ApiError("El correo es obligatorio.")
        return None
    if not re.fullmatch(r"[^@\s]+@[^@\s]+", email) or email.rsplit("@", 1)[1] not in domains:
        raise ApiError(f"El correo debe pertenecer al dominio {' o '.join('@' + d for d in domains)}.")
    return email


class AnimatorService:
    def __init__(self, cols: Collections, staff_domain: str) -> None:
        self.cols = cols
        self.staff_domain = staff_domain

    # ------------------------------------------------------------- lectura
    def get(self, animator_id: Any) -> Doc:
        doc = self.cols.animators.find_one({"_id": require_object_id(animator_id, "ID de animador inválido.")})
        if not doc:
            raise NotFound("Animador no encontrado.")
        return doc

    def by_email(self, email: str) -> Doc | None:
        return self.cols.animators.find_one({"correo": normalize_email(email)})

    def list_all(self, search: str = "") -> list[dict[str, Any]]:
        query: dict[str, Any] = {}
        if search:
            pattern = {"$regex": re.escape(search), "$options": "i"}
            query = {"$or": [{"profesor": pattern}, {"tutor": pattern}, {"correo": pattern}, {"curso": pattern}]}
        docs = list(self.cols.animators.find(query))
        docs.sort(key=lambda d: (str(d.get("curso", "")), safe_int(d.get("nivel")), str(d.get("paralelo", ""))))
        return [self.serialize(d) for d in docs]

    def serialize(self, doc: Doc) -> dict[str, Any]:
        user = self.linked_user(doc)
        return {
            "_id": str(doc["_id"]),
            "nombre": animator_name(doc),
            "curso": doc.get("curso", ""),
            "especialidad": doc.get("especialidad", ""),
            "nivel": doc.get("nivel", ""),
            "paralelo": doc.get("paralelo", ""),
            "correo": doc.get("correo", ""),
            "usuario_id": str(user["_id"]) if user else None,
            "usuario": user.get("usuario") if user else None,
            # Rango de tablas reservado a su cuenta (None si aún no tiene).
            "reserva": _reservation(user),
        }

    def linked_user(self, doc: Doc) -> Doc | None:
        """Cuenta de ``Users`` del animador. Enlaza por nombre los documentos antiguos sin ``usuario_id``."""
        if doc.get("usuario_id"):
            user = self.cols.users.find_one({"_id": doc["usuario_id"]})
            if user:
                return user
        name = animator_name(doc)
        user = self.cols.users.find_one({"nombres_completos": name}) if name else None
        if user:
            self.cols.animators.update_one({"_id": doc["_id"]}, {"$set": {"usuario_id": user["_id"]}})
        return user

    # ---------------------------------------------------------- escritura
    def _clean(self, data: dict[str, Any], partial: bool) -> dict[str, Any]:
        fields = {
            key: _clean_field(key, data.get(key))
            for key in ("nombre", *_TEXT_FIELDS, "nivel")
            if key in data or not partial
        }
        if "correo" in data:
            fields["correo"] = validate_domain_email(data.get("correo"), self.staff_domain)
        return fields

    def _ensure_email_free(self, email: str | None, exclude: ObjectId | None = None) -> None:
        if not email:
            return
        query: dict[str, Any] = {"correo": email}
        if exclude is not None:
            query["_id"] = {"$ne": exclude}
        if self.cols.animators.find_one(query, {"_id": 1}):
            raise Conflict(f"El correo {email} ya está asignado a otro animador.")

    def _unique_username(self, nombre: str) -> str:
        base = "".join(p[0] for p in nombre.split()).upper() or "ANIM"
        usuario, n = base, 1
        while self.cols.users.find_one({"usuario": usuario}, {"_id": 1}):
            n += 1
            usuario = f"{base}{n}"
        return usuario

    def _create_user(self, nombre: str, data: Doc) -> ObjectId:
        """Crea la cuenta operativa (``Users``, tipo animador, sin contraseña)."""
        user_id: ObjectId = self.cols.users.insert_one(
            {
                "usuario": self._unique_username(nombre),
                "nombres_completos": nombre,
                "tipo_usuario": ANIMADOR,
                **{k: data.get(k) for k in (*_TEXT_FIELDS, "nivel")},
            }
        ).inserted_id
        return user_id

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        fields = self._clean(data, partial=False)
        self._ensure_email_free(fields.get("correo"))
        nombre = fields.pop("nombre")
        user_id = self._create_user(nombre, fields)
        doc = {"profesor": nombre, **fields, "usuario_id": user_id}
        if not doc.get("correo"):
            doc.pop("correo", None)
        doc["_id"] = self.cols.animators.insert_one(doc).inserted_id
        return self.serialize(doc)

    def update(self, animator_id: Any, data: dict[str, Any]) -> dict[str, Any]:
        doc = self.get(animator_id)
        fields = self._clean(data, partial=True)
        self._ensure_email_free(fields.get("correo"), exclude=doc["_id"])

        changes: dict[str, Any] = {k: v for k, v in fields.items() if k != "nombre"}
        if "nombre" in fields:
            changes["tutor" if "tutor" in doc and "profesor" not in doc else "profesor"] = fields["nombre"]
        user = self.linked_user(doc)
        if changes:
            self.cols.animators.update_one({"_id": doc["_id"]}, set_or_unset(changes))

        updated = self.get(doc["_id"])
        if user is None:
            # Animador histórico sin cuenta en Users: se le crea para que pueda operar.
            user_id = self._create_user(animator_name(updated), updated)
            self.cols.animators.update_one({"_id": doc["_id"]}, {"$set": {"usuario_id": user_id}})
            return self.serialize(self.get(doc["_id"]))

        user_fields = {k: v for k, v in fields.items() if k in (*_TEXT_FIELDS, "nivel")}
        if "nombre" in fields:
            user_fields["nombres_completos"] = fields["nombre"]
        if user_fields:
            self.cols.users.update_one({"_id": user["_id"]}, {"$set": user_fields})
        return self.serialize(updated)

    def delete(self, animator_id: Any) -> None:
        """Elimina el animador y su cuenta, salvo que ya tenga participantes o tablas reservadas."""
        doc = self.get(animator_id)
        user = self.linked_user(doc)
        if user:
            if self.cols.participants.count_documents({"registrado_por": user["_id"]}, limit=1):
                raise Conflict("El animador tiene participantes registrados; quite su correo en lugar de eliminarlo.")
            if safe_int(user.get("totalTables"), 0) > 0:
                raise Conflict("El animador tiene tablas reservadas; quite su correo en lugar de eliminarlo.")
            if safe_int(user.get("tipo_usuario"), 1) == ANIMADOR:
                self.cols.users.delete_one({"_id": user["_id"]})
        self.cols.animators.delete_one({"_id": doc["_id"]})
