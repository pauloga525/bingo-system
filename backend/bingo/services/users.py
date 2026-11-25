"""Usuarios (vendedores/administradores): auditoría de contadores de ventas.

Las tablas ya no se reservan por usuario: se venden en cola (``services/queue.py``).
"""

from __future__ import annotations

from typing import Any

from ..db import Collections
from ..domain.pricing import calcular_total
from ..errors import NotFound
from ..utils import require_object_id, safe_int
from .participants import sales_of


class UserService:
    def __init__(self, cols: Collections) -> None:
        self.cols = cols

    def audit_counters(self, usuario_id: Any, apply: bool) -> dict[str, Any]:
        """Compara los contadores guardados con lo realmente asignado.

        Si ``apply`` es True corrige ``usedTables`` y ``total_vendido`` del
        usuario y ``total_pagar`` de cada participante.
        """
        oid = require_object_id(usuario_id, "ID de usuario inválido")
        usuario = self.cols.users.find_one({"_id": oid})
        if not usuario:
            raise NotFound("Usuario no encontrado")

        participantes = list(
            self.cols.participants.find(
                {"$or": [{"registrado_por": oid}, {"ventas.vendedor": oid}]},
                {"tablas": 1, "total_pagar": 1, "ventas": 1, "registrado_por": 1},
            )
        )
        reales, vendido_real = 0, 0
        for p in participantes:
            ventas = sales_of(p)
            if all(v.get("vendedor") == oid for v in ventas):  # todo lo vendió este usuario
                reales += len(p.get("tablas") or [])
                vendido_real += calcular_total(len(p.get("tablas") or []))
                continue
            propias = [v for v in ventas if v.get("vendedor") == oid]
            reales += sum(len(v.get("tablas") or []) for v in propias)
            vendido_real += sum(safe_int(v.get("monto"), 0) for v in propias)
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
        }
