"""Vaciado de participantes (solo administrador).

Borra **todos** los documentos de ``Participantes`` y deja la base coherente con
los invariantes de :mod:`bingo.services.participants`:

- sus tablas quedan libres (``stateAsigned=False``) para volver a venderse;
- ``Users.usedTables`` y ``Users.total_vendido`` se recalculan con lo que quede
  (normalmente cero);
- las reservas de los animadores (``totalTables``, rango de seriales) y el
  historial de ganadores (``tablas_ganadoras``) **no** se tocan.

Antes de borrar se guarda un respaldo JSON (formato extendido de MongoDB) en
``Settings.backup_dir`` para poder restaurarlo con ``mongoimport``.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from bson import ObjectId, json_util

from ..db import Collections, Doc
from ..domain.pricing import calcular_total
from ..errors import ApiError
from ..utils import safe_int, try_object_id

# Texto que el administrador debe escribir para confirmar el vaciado.
CONFIRMATION = "BORRAR PARTICIPANTES"


def _table_ids(participant: Doc) -> list[ObjectId]:
    return [t for t in (try_object_id(t) for t in participant.get("tablas") or []) if t is not None]


class ParticipantPurge:
    def __init__(self, cols: Collections, backup_dir: Path) -> None:
        self.cols = cols
        self.backup_dir = backup_dir

    def summary(self) -> dict[str, Any]:
        """Lo que se borraría, para mostrarlo antes de confirmar."""
        participantes = list(self.cols.participants.find({}, {"tablas": 1, "tipo": 1, "registrado_por": 1}))
        por_tipo = Counter(str(p.get("tipo") or "sin tipo") for p in participantes)
        return {
            "participantes": len(participantes),
            "por_tipo": dict(por_tipo),
            "tablas_asignadas": sum(len(_table_ids(p)) for p in participantes),
            "vendedores": len({p.get("registrado_por") for p in participantes if p.get("registrado_por")}),
            "confirmacion": CONFIRMATION,
        }

    def _backup(self, participants: list[Doc]) -> Path:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        path = self.backup_dir / f"participantes_{datetime.now():%Y-%m-%d_%H%M%S}.json"
        # Una línea por documento: se restaura con ``mongoimport --collection Participantes``.
        lines = (json_util.dumps(p, json_options=json_util.CANONICAL_JSON_OPTIONS) for p in participants)
        path.write_text("\n".join(lines) + ("\n" if participants else ""), encoding="utf-8")
        return path

    def _recount_sellers(self, sellers: set[Any]) -> int:
        """Recalcula ``usedTables`` y ``total_vendido`` de los vendedores afectados."""
        updated = 0
        for seller in sellers:
            restantes = list(self.cols.participants.find({"registrado_por": seller}, {"tablas": 1, "total_pagar": 1}))
            usadas = sum(len(_table_ids(p)) for p in restantes)
            vendido = sum(safe_int(p.get("total_pagar"), calcular_total(len(_table_ids(p)))) for p in restantes)
            result = self.cols.users.update_one(
                {"_id": seller}, {"$set": {"usedTables": usadas, "total_vendido": vendido}}
            )
            updated += result.modified_count
        return updated

    def purge(self, confirmation: Any) -> dict[str, Any]:
        if str(confirmation or "").strip() != CONFIRMATION:
            raise ApiError(f"Para confirmar escriba exactamente: {CONFIRMATION}")
        participants = list(self.cols.participants.find({}))
        if not participants:
            return {"participantes_borrados": 0, "tablas_liberadas": 0, "vendedores_actualizados": 0, "respaldo": None}

        backup = self._backup(participants)
        ids = [p["_id"] for p in participants]
        table_ids = [t for p in participants for t in _table_ids(p)]
        sellers = {p.get("registrado_por") for p in participants if p.get("registrado_por")}

        # Solo los participantes respaldados: uno registrado durante el vaciado no se pierde.
        borrados = self.cols.participants.delete_many({"_id": {"$in": ids}}).deleted_count
        liberadas = self.cols.tables.update_many(
            {"$or": [{"_id": {"$in": table_ids}}, {"assignedToParticipant": {"$in": ids}}]},
            {"$set": {"stateAsigned": False}, "$unset": {"assignedToParticipant": ""}},
        ).modified_count
        return {
            "participantes_borrados": borrados,
            "tablas_liberadas": liberadas,
            "vendedores_actualizados": self._recount_sellers(sellers),
            "respaldo": backup.name,
        }
