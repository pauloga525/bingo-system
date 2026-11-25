"""Cola única de tablas: cada venta toma las siguientes tablas libres, en orden de serial.

Ya no hay rangos reservados por vendedor. Si un animador vende 4 tablas se
lleva ``CARD00001``..``CARD00004``; si después otro vende 2, se lleva
``CARD00005`` y ``CARD00006``, y así sucesivamente. Si se libera una tabla
(se quita a un participante), vuelve a la cola y la toma la próxima venta.

Para que cada venta reciba un bloque seguido aunque dos vendedores guarden a
la vez, la elección y la asignación se hacen dentro de un candado del
proceso (el servidor corre en un solo proceso con varios hilos). La
asignación de cada tabla además es condicional (``stateAsigned != True``),
así que, aunque hubiera otro proceso, una tabla nunca queda en dos
participantes: en ese caso se reintenta con las siguientes libres.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from bson import ObjectId

from ..db import Collections, Doc
from ..errors import ApiError

_LOCK = threading.Lock()
_ATTEMPTS = 3
_FREE: dict[str, Any] = {"stateAsigned": {"$ne": True}}

Claim = Callable[[list[ObjectId], ObjectId], None]


class TableQueue:
    def __init__(self, cols: Collections) -> None:
        self.cols = cols

    def _next_free(self, cantidad: int) -> list[Doc]:
        return list(self.cols.tables.find(_FREE, {"serial": 1}).sort("serial", 1).limit(cantidad))

    @staticmethod
    def _check(cantidad: int) -> None:
        if cantidad <= 0:
            raise ApiError("La cantidad de tablas debe ser mayor a 0.")

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
            raise ApiError(f"Solo quedan {len(libres)} tablas disponibles.")
        return libres

    def take(self, cantidad: int, participant_id: ObjectId, claim: Claim) -> list[ObjectId]:
        """Asigna a ``participant_id`` las siguientes ``cantidad`` tablas libres, en orden.

        ``claim`` marca las tablas como asignadas (todas o ninguna) y lanza
        ``ApiError`` si alguna ya fue tomada.
        """
        self._check(cantidad)
        with _LOCK:
            for intento in range(_ATTEMPTS):
                libres = self._next_free(cantidad)
                if len(libres) < cantidad:
                    raise ApiError(f"Solo quedan {len(libres)} tablas disponibles.")
                ids: list[ObjectId] = [t["_id"] for t in libres]
                try:
                    claim(ids, participant_id)
                except ApiError:
                    if intento == _ATTEMPTS - 1:
                        raise
                    continue
                return ids
        raise ApiError("No se pudieron asignar las tablas, intente nuevamente.")  # pragma: no cover
