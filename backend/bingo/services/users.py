"""Usuarios (animadores/administradores): reservas de tablas y contadores."""

from __future__ import annotations

from typing import Any

from ..db import Collections
from ..domain.pricing import calcular_total
from ..domain.serials import SerialRange
from ..errors import ApiError, Forbidden, NotFound
from ..utils import require_object_id, safe_int
from .participants import is_admin


class UserService:
    def __init__(self, cols: Collections) -> None:
        self.cols = cols

    def assign_tables(self, user_id: Any, total: int, requesting_user_id: Any) -> dict[str, str]:
        """Reserva ``total`` tablas libres a un usuario (solo admin, desde el último serial)."""
        user_oid = require_object_id(user_id, "ID de usuario inválido")
        user = self.cols.users.find_one({"_id": user_oid})
        if not user:
            raise NotFound("Usuario no encontrado")
        requester_oid = require_object_id(requesting_user_id, "ID del usuario solicitante inválido")
        requester = self.cols.users.find_one({"_id": requester_oid})
        if not requester:
            raise NotFound("Usuario solicitante no encontrado")
        if not is_admin(requester):
            raise Forbidden("Solo usuario admin puede reservar tablas desde el último código.")
        if user.get("totalTables"):
            raise ApiError("Este usuario ya tiene tablas reservadas.")

        # Antes el filtro era un dict con dos claves "$or" y la primera se
        # perdía, por lo que podían reservarse tablas ya asignadas.
        free_filter = {"stateAsigned": {"$ne": True}, "stateReserved": {"$ne": True}}
        available = list(self.cols.tables.find(free_filter, {"serial": 1}).sort("serial", -1).limit(total))
        if len(available) < total:
            raise ApiError("No hay suficientes tablas disponibles.")
        table_ids = [t["_id"] for t in available]

        result = self.cols.tables.update_many(
            {"_id": {"$in": table_ids}, **free_filter},
            {"$set": {"stateReserved": True, "reservedTo": user_oid}},
        )
        if result.modified_count != len(table_ids):
            # Otra reserva concurrente tomó alguna: deshacer la nuestra.
            self.cols.tables.update_many(
                {"_id": {"$in": table_ids}, "reservedTo": user_oid},
                {"$set": {"stateReserved": False}, "$unset": {"reservedTo": ""}},
            )
            raise ApiError("Las tablas cambiaron durante la reserva, intente nuevamente.", 409)

        from_serial, to_serial = available[0]["serial"], available[-1]["serial"]
        self.cols.users.update_one(
            {"_id": user_oid},
            {
                "$set": {
                    "totalTables": total,
                    "usedTables": 0,
                    "fromSerial": from_serial,
                    "toSerial": to_serial,
                    "reserved_table_ids": table_ids,
                }
            },
        )
        return {"from": from_serial, "to": to_serial}

    def audit_counters(self, usuario_id: Any, apply: bool) -> dict[str, Any]:
        """Compara los contadores guardados con lo realmente asignado.

        Si ``apply`` es True corrige ``usedTables`` y ``total_vendido`` del
        usuario y ``total_pagar`` de cada participante.
        """
        oid = require_object_id(usuario_id, "ID de usuario inválido")
        usuario = self.cols.users.find_one({"_id": oid})
        if not usuario:
            raise NotFound("Usuario no encontrado")

        participantes = list(self.cols.participants.find({"registrado_por": oid}, {"tablas": 1, "total_pagar": 1}))
        reales = sum(len(p.get("tablas") or []) for p in participantes)
        vendido_real = sum(calcular_total(len(p.get("tablas") or [])) for p in participantes)
        used_bd = safe_int(usuario.get("usedTables"), 0)
        diferencia = used_bd - reales
        vendido_bd = usuario.get("total_vendido", 0)
        desfasados = [p for p in participantes if p.get("total_pagar") != calcular_total(len(p.get("tablas") or []))]

        corregido = False
        if apply and (diferencia != 0 or vendido_bd != vendido_real or desfasados):
            self.cols.users.update_one({"_id": oid}, {"$set": {"usedTables": reales, "total_vendido": vendido_real}})
            for p in desfasados:
                self.cols.participants.update_one(
                    {"_id": p["_id"]}, {"$set": {"total_pagar": calcular_total(len(p.get("tablas") or []))}}
                )
            corregido = True

        rango = SerialRange.of_user(usuario)
        disponibles: list[str] = []
        if rango:
            disponibles = [
                t["serial"]
                for t in self.cols.tables.find(
                    {"serial": rango.mongo_filter(), "stateAsigned": {"$ne": True}}, {"serial": 1}
                ).sort("serial", 1)
            ]

        total_tables = safe_int(usuario.get("totalTables"), 0)
        return {
            "success": True,
            "usuario_id": str(oid),
            "usuario": usuario.get("usuario", "N/A"),
            "nombres_completos": usuario.get("nombres_completos", "N/A"),
            "total_participantes": len(participantes),
            "tablas_reales_asignadas": reales,
            "used_tables_bd_anterior": used_bd,
            "used_tables_bd_nuevo": reales if corregido else used_bd,
            "diferencia": diferencia,
            "total_vendido_bd": vendido_bd,
            "total_vendido_real": vendido_real,
            "participantes_con_total_desfasado": len(desfasados),
            "corregido": corregido,
            "totalTables": total_tables,
            "disponibles_ahora": total_tables - reales,
            "rango_tablas": {"desde": usuario.get("fromSerial"), "hasta": usuario.get("toSerial")},
            "tablas_disponibles": disponibles,
        }
