"""Participantes y asignación de tablas.

Invariantes que este servicio mantiene en todos los flujos:

- Una tabla asignada tiene ``stateAsigned=True`` y está en ``tablas`` de
  exactamente un participante.
- ``Users.usedTables`` = cantidad de tablas en participantes registrados por
  ese usuario.
- ``Participantes.total_pagar`` = ``calcular_total(len(tablas))`` y
  ``Users.total_vendido`` acumula esos montos.
- Los vendedores con rol distinto de animador (secretaría, financiero,
  parroquia, oratorio) solo registran participantes de tipo ``externo``.
  ``rol_vendedor`` guarda el rol de quien vendió (lo usan los reportes).

MongoDB standalone no ofrece transacciones, así que la asignación se hace
tabla por tabla con un filtro condicional (``stateAsigned != True``) y, si
algo falla, se liberan las tablas ya tomadas (compensación).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from bson import ObjectId

from ..db import Collections, Doc
from ..domain.pricing import calcular_total
from ..domain.roles import ETIQUETAS, EXTERNO, rol_de, solo_externos
from ..domain.serials import SerialRange
from ..errors import ApiError, Conflict, Forbidden, NotFound
from ..utils import ids_to_str, require_object_id, safe_int, try_object_id

ADMIN = 0
_NOT_ASSIGNED = {"$ne": True}


def is_admin(user: Doc) -> bool:
    return safe_int(user.get("tipo_usuario"), 1) == ADMIN


def table_summary(tabla: Doc) -> dict[str, Any]:
    return {
        "_id": str(tabla["_id"]),
        "serial": tabla.get("serial", ""),
        "matrix": tabla.get("matrix", []),
        "won": tabla.get("won", False),
        "stateAsigned": tabla.get("stateAsigned", False),
    }


def _partition_refs(refs: list[Any], allowed: SerialRange | None) -> tuple[list[ObjectId], list[str]]:
    """Separa las referencias en ObjectIds y seriales, validando el rango de los seriales."""
    oids: list[ObjectId] = []
    serials: list[str] = []
    for ref in refs:
        oid = try_object_id(ref)
        if oid is not None:
            oids.append(oid)
            continue
        serial = str(ref).strip()
        if allowed is not None and not allowed.contains(serial):
            raise ApiError(f"La tabla {serial} está fuera del rango permitido ({allowed}).")
        serials.append(serial)
    return oids, serials


class ParticipantService:
    def __init__(self, cols: Collections) -> None:
        self.cols = cols

    # ------------------------------------------------------------- lectura
    def get_user(self, user_id: ObjectId, message: str = "Usuario no encontrado.") -> Doc:
        user = self.cols.users.find_one({"_id": user_id})
        if not user:
            raise NotFound(message)
        return user

    def get_participant(self, participant_id: ObjectId) -> Doc:
        participante = self.cols.participants.find_one({"_id": participant_id})
        if not participante:
            raise NotFound("Participante no encontrado.")
        return participante

    def tables_of(self, participante: Doc) -> list[Doc]:
        ids = participante.get("tablas") or []
        if not ids:
            return []
        return list(self.cols.tables.find({"_id": {"$in": ids}}).sort("serial", 1))

    def by_cedula(self, cedula: str) -> Doc:
        participante = self.cols.participants.find_one({"cedula": cedula})
        if not participante:
            raise NotFound(f"Participante con cédula {cedula} no encontrado.")
        return participante

    # ----------------------------------------------------------- permisos
    def _authorize(self, usuario_id: Any, participante: Doc, accion: str) -> Doc:
        """Valida que ``usuario_id`` sea admin o quien registró al participante.

        El tipo de usuario se lee de la base de datos; el ``tipo_usuario`` que
        llega en la URL ya no se usa para autorizar (cualquiera podía enviar 0).
        """
        actor_id = require_object_id(usuario_id, "ID de usuario inválido.")
        actor = self.get_user(actor_id)
        if not is_admin(actor) and participante.get("registrado_por") != actor_id:
            raise Forbidden(f"No tiene permiso para {accion} este participante.")
        return actor

    # ------------------------------------------------------ tablas (bajo nivel)
    def resolve_tables(self, refs: list[Any], allowed: SerialRange | None) -> list[ObjectId]:
        """Convierte seriales u ObjectIds en ``_id`` de tablas existentes.

        Si ``allowed`` no es ``None`` los seriales deben estar en ese rango.
        """
        oids, serials = _partition_refs(refs, allowed)
        by_serial = self._ids_by_serial(serials)
        self._ensure_ids_exist(oids)

        ordered: list[ObjectId] = []
        for ref in refs:
            oid = try_object_id(ref) or by_serial[str(ref).strip()]
            if oid not in ordered:
                ordered.append(oid)
        return ordered

    def _ids_by_serial(self, serials: list[str]) -> dict[str, ObjectId]:
        """``{serial: _id}``; lanza ``NotFound`` si algún serial no existe."""
        if not serials:
            return {}
        found = self.cols.tables.find({"serial": {"$in": serials}}, {"serial": 1})
        by_serial: dict[str, ObjectId] = {d["serial"]: d["_id"] for d in found}
        for serial in serials:
            if serial not in by_serial:
                raise NotFound(f"Tabla '{serial}' no encontrada.")
        return by_serial

    def _ensure_ids_exist(self, oids: list[ObjectId]) -> None:
        if not oids:
            return
        found = {d["_id"] for d in self.cols.tables.find({"_id": {"$in": oids}}, {"_id": 1})}
        if len(found) != len(set(oids)):
            raise NotFound("Una o más tablas no existen.")

    def claim_tables(self, table_ids: list[ObjectId], participant_id: ObjectId) -> None:
        """Marca las tablas como asignadas de forma atómica (todas o ninguna)."""
        claimed: list[ObjectId] = []
        for tid in table_ids:
            result = self.cols.tables.update_one(
                {"_id": tid, "stateAsigned": _NOT_ASSIGNED},
                {"$set": {"stateAsigned": True, "assignedToParticipant": participant_id}},
            )
            if result.modified_count != 1:
                self.release_tables(claimed)
                raise ApiError("Una o más tablas ya están asignadas.")
            claimed.append(tid)

    def release_tables(self, table_ids: list[ObjectId]) -> None:
        if table_ids:
            self.cols.tables.update_many(
                {"_id": {"$in": table_ids}},
                {"$set": {"stateAsigned": False}, "$unset": {"assignedToParticipant": ""}},
            )

    def _update_seller(self, seller_id: Any, tables_delta: int, money_delta: int) -> None:
        if seller_id:
            self.cols.users.update_one(
                {"_id": seller_id}, {"$inc": {"usedTables": tables_delta, "total_vendido": money_delta}}
            )

    def _ensure_cedula_free(self, cedula: str) -> None:
        existente = self.cols.participants.find_one({"cedula": cedula}, {"registrado_por": 1})
        if not existente:
            return
        animador = "desconocido"
        if existente.get("registrado_por"):
            reg = self.cols.users.find_one({"_id": existente["registrado_por"]}, {"nombres_completos": 1})
            if reg and reg.get("nombres_completos"):
                animador = reg["nombres_completos"]
        raise Conflict(f"El participante con cédula {cedula} ya fue registrado por {animador}.")

    @staticmethod
    def _remaining(user: Doc) -> int:
        return safe_int(user.get("totalTables"), 0) - safe_int(user.get("usedTables"), 0)

    def _check_quota(self, seller: Doc, requested: int) -> None:
        """Valida que el vendedor tenga cupo para ``requested`` tablas más."""
        remaining = self._remaining(seller)
        if safe_int(seller.get("totalTables"), 0) > 0 and remaining <= 0:
            raise ApiError("Ya no tienes tablas disponibles.")
        if requested > remaining:
            raise ApiError(f"No puedes asignar {requested} tablas. Solo tienes {remaining} disponibles.")

    def _insert_with_tables(self, doc: Doc, table_ids: list[ObjectId]) -> Doc:
        doc["_id"] = ObjectId()
        self.claim_tables(table_ids, doc["_id"])
        try:
            self.cols.participants.insert_one(doc)
        except Exception:
            self.release_tables(table_ids)
            raise
        return doc

    @staticmethod
    def _sale_type(seller: Doc, tipo: Any, default: str = "alumno") -> tuple[str, str]:
        """``(tipo de participante, rol del vendedor)``; valida que el rol pueda venderle."""
        rol = rol_de(seller)
        valor = str(tipo or "").strip().lower() or (EXTERNO if solo_externos(rol) else default)
        if solo_externos(rol) and valor != EXTERNO:
            raise Forbidden(f"El rol {ETIQUETAS[rol]} solo puede vender tablas a participantes externos.")
        return valor, rol

    # ----------------------------------------------------------- registro
    def register(self, data: dict[str, Any]) -> Doc:
        """Registra un participante con tablas elegidas (seriales u ObjectIds)."""
        if not data:
            raise ApiError("No se proporcionaron datos del participante.")
        nombre = data.get("nombre")
        cedula = str(data.get("cedula") or "").strip()
        refs = data.get("tablas") or []
        if not isinstance(refs, list):
            raise ApiError("El campo 'tablas' debe ser una lista.")

        if not data.get("registrado_por"):
            raise ApiError("Debe incluir el campo 'registrado_por' (usuario que realiza el registro).")
        seller_id = require_object_id(
            data["registrado_por"], "El campo 'registrado_por' debe ser un ID de usuario válido."
        )
        seller = self.get_user(seller_id)
        tipo, rol = self._sale_type(seller, data.get("tipo"))

        self._check_quota(seller, len(refs))
        if not nombre:
            raise ApiError("El campo 'nombre' es obligatorio.")
        if not cedula:
            raise ApiError("El campo 'cedula' es obligatorio.")
        if not refs:
            raise ApiError("Debe asignarse al menos una tabla al participante.")
        self._ensure_cedula_free(cedula)

        table_ids = self.resolve_tables(refs, SerialRange.of_user(seller))
        total_pagar = calcular_total(len(table_ids))
        doc = self._insert_with_tables(
            {
                "nombre": nombre,
                "apellido": data.get("apellido", ""),
                "cedula": cedula,
                "celular": data.get("celular", ""),
                "telefono": data.get("telefono", data.get("celular", "")),
                "tipo": tipo,
                "rol_vendedor": rol,
                "nivelCurso": data.get("nivelCurso", ""),
                "paralelo": data.get("paralelo", ""),
                "animador": data.get("animador", ""),
                "tablas": table_ids,
                "grupoAdetitss": data.get("grupoAdetitss", ""),
                "fecha_registro": datetime.now().isoformat(),
                "registrado_por": seller_id,
                "total_pagar": total_pagar,
            },
            table_ids,
        )
        self._update_seller(seller_id, len(table_ids), total_pagar)
        return {**doc, "_id": str(doc["_id"]), "registrado_por": str(seller_id), "tablas": ids_to_str(table_ids)}

    def register_auto(self, data: dict[str, Any]) -> ObjectId:
        """Registra un participante tomando automáticamente tablas libres de la reserva del usuario."""
        nombre = data.get("nombre")
        cedula = str(data.get("cedula") or "").strip()
        cantidad = safe_int(data.get("cantidad_tablas"), 1)
        if not nombre or not cedula or not data.get("registrado_por"):
            raise ApiError("Nombre, cédula y registrado_por son obligatorios")
        if cantidad <= 0:
            raise ApiError("La cantidad de tablas debe ser mayor a 0.")
        seller_id = require_object_id(data["registrado_por"], "ID de usuario inválido")
        seller = self.get_user(seller_id, "Usuario no encontrado")
        tipo, rol = self._sale_type(seller, data.get("tipo"))

        remaining = self._remaining(seller)
        if remaining <= 0:
            raise ApiError("Ya no tienes tablas disponibles")
        if cantidad > remaining:
            raise ApiError(f"Sólo quedan {remaining} tablas disponibles")
        self._ensure_cedula_free(cedula)

        # Antes se tomaba reserved_ids[used:used+n], que falla en cuanto se
        # libera una tabla. Ahora se eligen las libres respetando el orden de la reserva.
        reserved: list[ObjectId] = seller.get("reserved_table_ids") or []
        free = {
            d["_id"]
            for d in self.cols.tables.find({"_id": {"$in": reserved}, "stateAsigned": _NOT_ASSIGNED}, {"_id": 1})
        }
        table_ids = [tid for tid in reserved if tid in free][:cantidad]
        if len(table_ids) < cantidad:
            raise ApiError(f"Sólo quedan {len(table_ids)} tablas disponibles")

        total_pagar = calcular_total(cantidad)
        doc = self._insert_with_tables(
            {
                "nombre": nombre,
                "apellido": data.get("apellido", ""),
                "cedula": cedula,
                "celular": data.get("celular", ""),
                "tipo": tipo,
                "rol_vendedor": rol,
                "tablas": table_ids,
                "registrado_por": seller_id,
                "fecha_registro": datetime.now().isoformat(),
                "total_pagar": total_pagar,
            },
            table_ids,
        )
        self._update_seller(seller_id, cantidad, total_pagar)
        participant_id: ObjectId = doc["_id"]
        return participant_id

    # ------------------------------------------------------ modificaciones
    def add_tables(self, participant_id: ObjectId, refs: list[Any], usuario_id: Any) -> None:
        if not refs:
            raise ApiError("Debe proporcionar al menos una tabla.")
        if not usuario_id:
            raise ApiError("Debe proporcionar el ID del usuario.")
        participante = self.get_participant(participant_id)
        actor = self._authorize(usuario_id, participante, "modificar")

        seller_id = participante.get("registrado_por")
        seller = self.cols.users.find_one({"_id": seller_id}) if seller_id else None
        allowed = None if is_admin(actor) or seller is None else SerialRange.of_user(seller)
        table_ids = self.resolve_tables(refs, allowed)
        if seller is not None and not is_admin(actor) and len(table_ids) > self._remaining(seller):
            raise ApiError(
                f"No puedes asignar {len(table_ids)} tablas. Solo tienes {self._remaining(seller)} disponibles."
            )

        self.claim_tables(table_ids, participant_id)
        old_count = len(participante.get("tablas") or [])
        old_total = safe_int(participante.get("total_pagar"), calcular_total(old_count))
        new_total = calcular_total(old_count + len(table_ids))
        self.cols.participants.update_one(
            {"_id": participant_id},
            {"$addToSet": {"tablas": {"$each": table_ids}}, "$set": {"total_pagar": new_total}},
        )
        self._update_seller(seller_id, len(table_ids), new_total - old_total)

    def remove_table(self, participant_id: ObjectId, table_id: ObjectId, usuario_id: Any) -> None:
        if not usuario_id:
            raise ApiError("Debe proporcionar el ID del usuario.")
        participante = self.get_participant(participant_id)
        self._authorize(usuario_id, participante, "modificar")
        tablas = participante.get("tablas") or []
        if table_id not in tablas:
            raise NotFound("La tabla no pertenece a este participante.")

        old_total = safe_int(participante.get("total_pagar"), calcular_total(len(tablas)))
        new_total = calcular_total(len(tablas) - 1)
        self.cols.participants.update_one(
            {"_id": participant_id}, {"$pull": {"tablas": table_id}, "$set": {"total_pagar": new_total}}
        )
        self.release_tables([table_id])
        self._update_seller(participante.get("registrado_por"), -1, new_total - old_total)

    def remove_table_by_serial(self, participant_id: ObjectId, serial: str, usuario_id: Any) -> None:
        tabla = self.cols.tables.find_one({"serial": serial}, {"_id": 1})
        participante = self.get_participant(participant_id)
        if not tabla or tabla["_id"] not in (participante.get("tablas") or []):
            raise ApiError(f"La tabla {serial} no está asignada a este participante.")
        self.remove_table(participant_id, tabla["_id"], usuario_id)

    def delete(self, participant_id: ObjectId, usuario_id: Any) -> int:
        """Elimina al participante, libera sus tablas y ajusta contadores. Devuelve tablas liberadas."""
        if not usuario_id:
            raise ApiError("Debe proporcionar el ID del usuario.")
        participante = self.get_participant(participant_id)
        self._authorize(usuario_id, participante, "eliminar")
        tablas = [t for t in (try_object_id(t) for t in participante.get("tablas") or []) if t is not None]
        total = safe_int(participante.get("total_pagar"), calcular_total(len(tablas)))

        self.release_tables(tablas)
        self._update_seller(participante.get("registrado_por"), -len(tablas), -total)
        self.cols.participants.delete_one({"_id": participant_id})
        return len(tablas)
