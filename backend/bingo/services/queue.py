"""Cola única de tablas: cada venta toma las siguientes tablas libres, en orden de serial.

Ya no hay rangos reservados por vendedor. Si un animador vende 4 tablas se
lleva ``CARD00001``..``CARD00004``; si después otro vende 2, se lleva
``CARD00005`` y ``CARD00006``, y así sucesivamente. Si se libera una tabla
(se quita a un participante), vuelve a la cola y la toma la próxima venta.

Concurrencia (dos o más vendedores guardando al mismo tiempo):

1. **Nunca se entrega una tabla a dos participantes.** Cada tabla se toma con
   un único ``find_one_and_update`` atómico de MongoDB: "la primera tabla con
   ``stateAsigned != True``, ordenada por serial, pásala a asignada a este
   participante". Dos peticiones simultáneas no pueden obtener el mismo
   documento, aunque vengan de procesos o servidores distintos.
2. **Cada venta recibe un bloque seguido.** Dentro del proceso del servidor
   (waitress: un proceso, varios hilos) las ventas se atienden de a una con un
   candado, así que una venta de 4 recibe 4 seriales consecutivos. Si algún
   día se corrieran varios procesos, el punto 1 sigue garantizando que no hay
   repetidas; solo podría ocurrir que un bloque quede intercalado.
3. **Todo o nada.** Si no alcanzan las tablas, se devuelven a la cola las que
   ya se habían tomado para esa venta y no se registra nada.
"""

from __future__ import annotations

import threading
from typing import Any

from bson import ObjectId
from pymongo import ASCENDING

from ..db import Collections, Doc
from ..errors import ApiError, Conflict

_LOCK = threading.Lock()
_FREE: dict[str, Any] = {"stateAsigned": {"$ne": True}}
_ORDER = [("serial", ASCENDING)]


class TableQueue:
    def __init__(self, cols: Collections) -> None:
        self.cols = cols

    def _next_free(self, cantidad: int) -> list[Doc]:
        return list(self.cols.tables.find(_FREE, {"serial": 1}).sort(_ORDER).limit(cantidad))

    @staticmethod
    def _check(cantidad: int) -> None:
        if cantidad <= 0:
            raise ApiError("La cantidad de tablas debe ser mayor a 0.")

    def _not_enough(self) -> Conflict:
        """409: otra venta se llevó las tablas (o se agotaron). El cliente debe refrescar la cola."""
        disponibles = self.cols.tables.count_documents(_FREE)
        return Conflict(f"Solo quedan {disponibles} tablas disponibles.", sin_tablas=True, disponibles=disponibles)

    def status(self) -> dict[str, Any]:
        """Tablas en la cola: total, vendidas, disponibles y la próxima que se entregará."""
        total = self.cols.tables.count_documents({})
        disponibles = self.cols.tables.count_documents(_FREE)
        siguiente = self._next_free(1)
        return {
            "total": total,
            "vendidas": total - disponibles,
            "disponibles": disponibles,
            "siguiente": siguiente[0]["serial"] if siguiente else None,
        }

    def peek(self, cantidad: int) -> list[str]:
        """Seriales que recibiría hoy una venta de ``cantidad`` tablas (no asigna nada)."""
        self._check(cantidad)
        libres = [t["serial"] for t in self._next_free(cantidad)]
        if len(libres) < cantidad:
            raise self._not_enough()
        return libres

    def _pop(self, participant_id: ObjectId) -> ObjectId | None:
        """Toma atómicamente la primera tabla libre para ``participant_id`` (``None`` si no hay)."""
        doc = self.cols.tables.find_one_and_update(
            _FREE,
            {"$set": {"stateAsigned": True, "assignedToParticipant": participant_id}},
            sort=_ORDER,
            projection={"_id": 1},
        )
        return doc["_id"] if doc else None

    def give_back(self, table_ids: list[ObjectId], participant_id: ObjectId) -> None:
        """Devuelve a la cola tablas tomadas para ``participant_id`` (solo si siguen siendo suyas)."""
        if table_ids:
            self.cols.tables.update_many(
                {"_id": {"$in": table_ids}, "assignedToParticipant": participant_id},
                {"$set": {"stateAsigned": False}, "$unset": {"assignedToParticipant": ""}},
            )

    def take(self, cantidad: int, participant_id: ObjectId) -> list[ObjectId]:
        """Asigna a ``participant_id`` las siguientes ``cantidad`` tablas libres (todas o ninguna)."""
        self._check(cantidad)
        with _LOCK:
            if self.cols.tables.count_documents(_FREE, limit=cantidad) < cantidad:
                raise self._not_enough()
            ids: list[ObjectId] = []
            for _ in range(cantidad):
                tid = self._pop(participant_id)
                if tid is None:  # otro proceso tomó las últimas: no se vende a medias
                    self.give_back(ids, participant_id)
                    raise self._not_enough()
                ids.append(tid)
            return ids
