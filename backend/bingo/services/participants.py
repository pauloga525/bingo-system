"""Participantes y asignación de tablas.

Invariantes que este servicio mantiene en todos los flujos:

- Una tabla asignada tiene ``stateAsigned=True`` y está en ``tablas`` de
  exactamente un participante.
- ``Participantes.ventas`` es el registro de cada venta al participante:
  ``{vendedor, rol, tablas, cantidad, monto, fecha}``. Un participante puede
  tener ventas de varios vendedores (p. ej. el animador del curso y luego
  secretaría agrega tablas al mismo alumno). Los documentos antiguos sin
  ``ventas`` se leen como una sola venta de ``registrado_por``.
- ``Users.usedTables`` / ``Users.total_vendido`` = tablas y monto de las
  ventas hechas por ese usuario.
- ``Participantes.total_pagar`` = ``calcular_total(len(tablas))``; cada venta
  posterior cobra solo la diferencia.
- Los roles sin curso (secretaría, financiero, ...) venden a externos y a
  alumnos; esas ventas quedan con su rol (venta externa del rol, no del curso).
  Pueden agregar tablas a cualquier alumno. Ver ``domain/roles.py``.
- Solo el administrador quita tablas o elimina participantes.
- Toda venta lleva el **correo** del comprador (obligatorio): ahí se le envían
  sus tablas. Si es alumno debe ser su correo institucional y se guarda también
  en su ficha de ``Estudiantes`` (con él inicia sesión y ve sus tablas).
- Las tablas se venden **en cola** (``services/queue.py``): cada venta toma
  las siguientes tablas libres en orden de serial. No hay rangos ni cupos por
  vendedor. Solo el administrador puede elegir seriales específicos.

MongoDB standalone no ofrece transacciones, así que la asignación se hace
tabla por tabla con un filtro condicional (``stateAsigned != True``) y, si
algo falla, se liberan las tablas ya tomadas (compensación).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from ..db import Collections, Doc
from ..domain.pricing import calcular_total
from ..domain.roles import ADMIN_ROL, ALUMNO, ANIMADOR_ROL, SOLO_EXTERNOS, rol_de, rol_para_venta, roles_de
from ..errors import ApiError, Conflict, Forbidden, NotFound
from ..utils import require_object_id, safe_int, serialize_mongo_doc, try_object_id
from .queue import TableQueue

ADMIN = 0
_NOT_ASSIGNED = {"$ne": True}
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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


def sales_of(participante: Doc, default_rol: str = ANIMADOR_ROL) -> list[Doc]:
    """Ventas del participante; los documentos antiguos se leen como una sola venta."""
    ventas = participante.get("ventas")
    if isinstance(ventas, list):
        return [dict(v) for v in ventas]
    tablas = list(participante.get("tablas") or [])
    if not tablas:
        return []
    return [
        {
            "vendedor": participante.get("registrado_por"),
            "rol": participante.get("rol_vendedor") or default_rol,
            "tablas": tablas,
            "cantidad": len(tablas),
            "monto": safe_int(participante.get("total_pagar"), calcular_total(len(tablas))),
            "fecha": participante.get("fecha_registro", ""),
        }
    ]


def sold_by(participante: Doc, user_id: Any) -> bool:
    """``True`` si ``user_id`` registró al participante o le vendió tablas."""
    if user_id is None:
        return False
    if participante.get("registrado_por") == user_id:
        return True
    return any(v.get("vendedor") == user_id for v in participante.get("ventas") or [])


def _sale(seller_id: Any, rol: str, table_ids: list[ObjectId], monto: int) -> Doc:
    return {
        "vendedor": seller_id,
        "rol": rol,
        "tablas": list(table_ids),
        "cantidad": len(table_ids),
        "monto": monto,
        "fecha": datetime.now().isoformat(),
    }


def _partition_refs(refs: list[Any]) -> tuple[list[ObjectId], list[str]]:
    """Separa las referencias en ObjectIds y seriales."""
    oids: list[ObjectId] = []
    serials: list[str] = []
    for ref in refs:
        oid = try_object_id(ref)
        if oid is not None:
            oids.append(oid)
            continue
        serials.append(str(ref).strip())
    return oids, serials


class ParticipantService:
    def __init__(self, cols: Collections, student_email: re.Pattern[str] | None = None) -> None:
        self.cols = cols
        # Formato del correo estudiantil (``Settings.student_email_regex``); None = no se valida.
        self.student_email = student_email

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
        """Valida que ``usuario_id`` pueda atender al participante (ver :meth:`can_attend`).

        El tipo de usuario se lee de la base de datos; el ``tipo_usuario`` que
        llega en la URL ya no se usa para autorizar (cualquiera podía enviar 0).
        """
        actor_id = require_object_id(usuario_id, "ID de usuario inválido.")
        actor = self.get_user(actor_id)
        if not self.can_attend(actor, participante):
            raise Forbidden(f"No tiene permiso para {accion} este participante.")
        return actor

    @staticmethod
    def can_attend(actor: Doc, participante: Doc) -> bool:
        """Admin, quien le vendió, o un rol sin curso si el participante es alumno."""
        if is_admin(actor) or sold_by(participante, actor.get("_id")):
            return True
        return participante.get("tipo") == ALUMNO and any(r in SOLO_EXTERNOS for r in roles_de(actor))

    def _require_admin(self, usuario_id: Any) -> Doc:
        if not usuario_id:
            raise ApiError("Debe proporcionar el ID del usuario.")
        actor = self.get_user(require_object_id(usuario_id, "ID de usuario inválido."))
        if not is_admin(actor):
            raise Forbidden("Solo el administrador puede borrar tablas o participantes.")
        return actor

    # ------------------------------------------------------ tablas (bajo nivel)
    def resolve_tables(self, refs: list[Any]) -> list[ObjectId]:
        """Convierte seriales u ObjectIds en ``_id`` de tablas existentes (sin repetir)."""
        oids, serials = _partition_refs(refs)
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
                TableQueue(self.cols).give_back(claimed, participant_id)
                raise Conflict("Una o más tablas ya están asignadas.", tabla_ocupada=True)
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
        if existente:
            raise self._cedula_taken(cedula, existente)

    def _cedula_taken(self, cedula: str, existente: Doc | None) -> Conflict:
        animador = "desconocido"
        if existente and existente.get("registrado_por"):
            reg = self.cols.users.find_one({"_id": existente["registrado_por"]}, {"nombres_completos": 1})
            if reg and reg.get("nombres_completos"):
                animador = reg["nombres_completos"]
        return Conflict(
            f"El participante con cédula {cedula} ya fue registrado por {animador}.", cedula_registrada=True
        )

    @staticmethod
    def _sale_type(seller: Doc, tipo: Any, rol_pedido: Any = None) -> tuple[str, str]:
        """``(tipo de participante, rol de la venta)``; valida que el vendedor pueda venderle."""
        roles = roles_de(seller)
        sin_curso = ADMIN_ROL not in roles and ANIMADOR_ROL not in roles
        valor = str(tipo or "").strip().lower() or ("externo" if sin_curso else ALUMNO)
        return valor, rol_para_venta(roles, valor, rol_pedido)

    def _rol_to_add(self, actor: Doc, participante: Doc, rol_pedido: Any) -> str:
        """Rol con el que ``actor`` agrega tablas a un participante existente.

        Quien ya le vendió usa cualquiera de sus roles; un rol sin curso que
        atiende a un alumno ajeno vende con ese rol (venta externa, no del curso).
        """
        roles = roles_de(actor)
        tipo = str(participante.get("tipo") or "")
        if is_admin(actor) or sold_by(participante, actor["_id"]):
            return rol_para_venta(roles, tipo, rol_pedido)
        if not self.can_attend(actor, participante):
            raise Forbidden("No tiene permiso para modificar este participante.")
        return rol_para_venta(roles, tipo, rol_pedido, permitidos=sorted(SOLO_EXTERNOS))

    # ------------------------------------------------------------- correo
    def clean_sale_email(self, raw: Any, tipo: str, cedula: str) -> str:
        """Correo del comprador validado. Alumno: institucional y no usado por otro estudiante."""
        correo = str(raw or "").strip().lower()
        if not correo:
            raise ApiError("El correo es obligatorio: ahí se envían las tablas.")
        if not _EMAIL.match(correo):
            raise ApiError(f"El correo {correo} no es válido.")
        if tipo != ALUMNO:
            return correo
        if self.student_email is not None and not self.student_email.match(correo):
            raise ApiError("El correo del alumno debe ser el institucional (nombre.apellido.est@uets.edu.ec).")
        if not self.cols.students.find_one({"Num documento": cedula}, {"_id": 1}):
            raise ApiError(f"La cédula {cedula} no está en la lista de estudiantes; regístrelo como externo.")
        otro = self.cols.students.find_one({"correo": correo, "Num documento": {"$ne": cedula}}, {"Nombre": 1})
        if otro:
            raise Conflict(f"El correo {correo} ya pertenece a otro estudiante.", correo_ocupado=True)
        return correo

    def save_student_email(self, tipo: str, cedula: str, correo: str) -> None:
        """Guarda (o corrige) el correo en la ficha del estudiante para que pueda iniciar sesión."""
        if tipo == ALUMNO:
            self.cols.students.update_one({"Num documento": cedula}, {"$set": {"correo": correo}})

    def change_email(self, participant_id: ObjectId, correo: Any, usuario_id: Any) -> Doc:
        """Corrige el correo de un participante (y del estudiante si es alumno).

        Con ``correo`` vacío solo valida el permiso (para reenviar al mismo correo).
        """
        participante = self.get_participant(participant_id)
        self._authorize(usuario_id, participante, "modificar")
        if not correo:
            return participante
        tipo = str(participante.get("tipo") or "")
        cedula = str(participante.get("cedula") or "")
        nuevo = self.clean_sale_email(correo, tipo, cedula)
        self.cols.participants.update_one({"_id": participant_id}, {"$set": {"correo": nuevo}})
        self.save_student_email(tipo, cedula, nuevo)
        return {**participante, "correo": nuevo}

    # ----------------------------------------------------------- registro
    def _take_tables(self, allow_serials: bool, refs: Any, cantidad: Any, participant_id: ObjectId) -> list[ObjectId]:
        """Asigna tablas a ``participant_id``: de la cola o, solo el admin, por serial."""
        if refs:
            if not isinstance(refs, list):
                raise ApiError("El campo 'tablas' debe ser una lista.")
            if not allow_serials:
                raise Forbidden("Las tablas se asignan en orden de la cola: indique solo la cantidad.")
            table_ids = self.resolve_tables(refs)
            self.claim_tables(table_ids, participant_id)
            return table_ids
        n = safe_int(cantidad, 0)
        if n <= 0:
            raise ApiError("Indique cuántas tablas vende (cantidad mayor a 0).")
        return TableQueue(self.cols).take(n, participant_id)

    def register(self, data: dict[str, Any], allow_serials: bool = False) -> Doc:
        """Registra un participante con ``cantidad_tablas`` tomadas de la cola.

        Con ``allow_serials`` (sesión de administrador) se aceptan en su lugar
        ``tablas`` específicas (seriales u ObjectIds).
        """
        if not data:
            raise ApiError("No se proporcionaron datos del participante.")
        nombre = data.get("nombre")
        cedula = str(data.get("cedula") or "").strip()
        if not data.get("registrado_por"):
            raise ApiError("Debe incluir el campo 'registrado_por' (usuario que realiza el registro).")
        seller_id = require_object_id(
            data["registrado_por"], "El campo 'registrado_por' debe ser un ID de usuario válido."
        )
        seller = self.get_user(seller_id)
        tipo, rol = self._sale_type(seller, data.get("tipo"), data.get("rol_venta"))
        if not nombre:
            raise ApiError("El campo 'nombre' es obligatorio.")
        if not cedula:
            raise ApiError("El campo 'cedula' es obligatorio.")
        refs = data.get("tablas") or []
        if not refs and safe_int(data.get("cantidad_tablas"), 0) <= 0:
            raise ApiError("Debe asignarse al menos una tabla al participante.")
        correo = self.clean_sale_email(data.get("correo"), tipo, cedula)
        self._ensure_cedula_free(cedula)

        participant_id = ObjectId()
        table_ids = self._take_tables(allow_serials, refs, data.get("cantidad_tablas"), participant_id)
        total_pagar = calcular_total(len(table_ids))
        doc: Doc = {
            "_id": participant_id,
            "nombre": nombre,
            "apellido": data.get("apellido", ""),
            "cedula": cedula,
            "correo": correo,
            "celular": data.get("celular", ""),
            "telefono": data.get("telefono", data.get("celular", "")),
            "tipo": tipo,
            "rol_vendedor": rol,
            "nivelCurso": data.get("nivelCurso", ""),
            "paralelo": data.get("paralelo", ""),
            "animador": data.get("animador", ""),
            "tablas": table_ids,
            "ventas": [_sale(seller_id, rol, table_ids, calcular_total(len(table_ids)))],
            "grupoAdetitss": data.get("grupoAdetitss", ""),
            "fecha_registro": datetime.now().isoformat(),
            "registrado_por": seller_id,
            "total_pagar": total_pagar,
        }
        try:
            self.cols.participants.insert_one(doc)
        except DuplicateKeyError as exc:
            # Dos registros simultáneos de la misma cédula (doble clic o dos vendedores):
            # el índice único deja pasar solo uno; las tablas del otro vuelven a la cola.
            TableQueue(self.cols).give_back(table_ids, participant_id)
            existente = self.cols.participants.find_one({"cedula": cedula}, {"registrado_por": 1})
            raise self._cedula_taken(cedula, existente) from exc
        except Exception:
            TableQueue(self.cols).give_back(table_ids, participant_id)
            raise
        self._update_seller(seller_id, len(table_ids), total_pagar)
        self.save_student_email(tipo, cedula, correo)
        return {**serialize_mongo_doc(doc), "seriales": self._serials(table_ids)}

    def register_auto(self, data: dict[str, Any]) -> ObjectId:
        """Igual que :meth:`register` tomando de la cola (``cantidad_tablas``, 1 por defecto)."""
        cantidad = safe_int(data.get("cantidad_tablas"), 1)
        if cantidad <= 0:
            raise ApiError("La cantidad de tablas debe ser mayor a 0.")
        doc = self.register({**data, "tablas": [], "cantidad_tablas": cantidad})
        return ObjectId(doc["_id"])

    def _serials(self, table_ids: list[ObjectId]) -> list[str]:
        found = {t["_id"]: t["serial"] for t in self.cols.tables.find({"_id": {"$in": table_ids}}, {"serial": 1})}
        return sorted(found[t] for t in table_ids if t in found)

    # ------------------------------------------------------ modificaciones
    def _legacy_rol(self, participante: Doc) -> str:
        seller = self.cols.users.find_one(
            {"_id": participante.get("registrado_por")}, {"rol": 1, "roles": 1, "tipo_usuario": 1}
        )
        return rol_de(seller)

    def add_tables(
        self,
        participant_id: ObjectId,
        refs: list[Any],
        usuario_id: Any,
        cantidad: Any = 0,
        allow_serials: bool = False,
        rol_venta: Any = None,
    ) -> list[str]:
        """Agrega tablas a un participante (de la cola; el admin puede indicar seriales).

        La venta se anota a quien agrega las tablas (``usuario_id``) con su rol.
        Devuelve los seriales agregados.
        """
        if not refs and safe_int(cantidad, 0) <= 0:
            raise ApiError("Debe proporcionar al menos una tabla.")
        if not usuario_id:
            raise ApiError("Debe proporcionar el ID del usuario.")
        participante = self.get_participant(participant_id)
        actor_id = require_object_id(usuario_id, "ID de usuario inválido.")
        rol = self._rol_to_add(self.get_user(actor_id), participante, rol_venta)

        table_ids = self._take_tables(allow_serials, refs, cantidad, participant_id)
        old_count = len(participante.get("tablas") or [])
        old_total = safe_int(participante.get("total_pagar"), calcular_total(old_count))
        new_total = calcular_total(old_count + len(table_ids))
        venta = _sale(actor_id, rol, table_ids, new_total - old_total)
        update: dict[str, Any] = {"$addToSet": {"tablas": {"$each": table_ids}}, "$set": {"total_pagar": new_total}}
        if isinstance(participante.get("ventas"), list):
            update["$push"] = {"ventas": venta}
        else:  # documento antiguo: se guarda su venta original y la nueva
            update["$set"]["ventas"] = [*sales_of(participante, self._legacy_rol(participante)), venta]
        self.cols.participants.update_one({"_id": participant_id}, update)
        self._update_seller(actor_id, len(table_ids), new_total - old_total)
        return self._serials(table_ids)

    def remove_table(self, participant_id: ObjectId, table_id: ObjectId, usuario_id: Any) -> None:
        """Quita una tabla al participante (solo administrador) y la descuenta a quien la vendió."""
        self._require_admin(usuario_id)
        participante = self.get_participant(participant_id)
        tablas = participante.get("tablas") or []
        if table_id not in tablas:
            raise NotFound("La tabla no pertenece a este participante.")

        old_total = safe_int(participante.get("total_pagar"), calcular_total(len(tablas)))
        new_total = calcular_total(len(tablas) - 1)
        delta = new_total - old_total
        ventas = sales_of(participante, self._legacy_rol(participante))
        vendedor = participante.get("registrado_por")
        for venta in ventas:
            if table_id in venta["tablas"]:
                venta["tablas"] = [t for t in venta["tablas"] if t != table_id]
                venta["cantidad"] = len(venta["tablas"])
                venta["monto"] = safe_int(venta.get("monto"), 0) + delta
                vendedor = venta.get("vendedor")
                break
        self.cols.participants.update_one(
            {"_id": participant_id},
            {
                "$pull": {"tablas": table_id},
                "$set": {"total_pagar": new_total, "ventas": [v for v in ventas if v["tablas"]]},
            },
        )
        self.release_tables([table_id])
        self._update_seller(vendedor, -1, delta)

    def remove_table_by_serial(self, participant_id: ObjectId, serial: str, usuario_id: Any) -> None:
        tabla = self.cols.tables.find_one({"serial": serial}, {"_id": 1})
        participante = self.get_participant(participant_id)
        if not tabla or tabla["_id"] not in (participante.get("tablas") or []):
            raise ApiError(f"La tabla {serial} no está asignada a este participante.")
        self.remove_table(participant_id, tabla["_id"], usuario_id)

    def delete(self, participant_id: ObjectId, usuario_id: Any) -> int:
        """Elimina al participante (solo administrador), libera sus tablas y ajusta los
        contadores de cada vendedor. Devuelve las tablas liberadas."""
        self._require_admin(usuario_id)
        participante = self.get_participant(participant_id)
        tablas = [t for t in (try_object_id(t) for t in participante.get("tablas") or []) if t is not None]

        self.release_tables(tablas)
        for venta in sales_of(participante):
            self._update_seller(venta.get("vendedor"), -len(venta["tablas"]), -safe_int(venta.get("monto"), 0))
        self.cols.participants.delete_one({"_id": participant_id})
        return len(tablas)
