"""Nuevo juego desde cero (solo administrador).

Deja el sistema como recién instalado, conservando estudiantes y animadores:

1. Genera ``cantidad`` tablas nuevas (``CARD00001..N``) y su PDF. Si algo falla
   aquí, todavía no se borró nada.
2. Guarda un respaldo JSON de lo que se va a borrar en ``backup_dir``.
3. Borra todas las tablas, las tablas ganadoras y todos los participantes, y
   pone en cero las reservas y contadores de ventas de las cuentas (``Users``).
4. Inserta las tablas nuevas y reinicia la partida del tablero (vacía hasta que
   se asignen tablas).

**No** se tocan ``Estudiantes``, ``Animadores``, ``Docentes`` ni las cuentas de
``Users`` (solo sus campos de reserva). Es la misma limpieza que hace
``scripts/nueva_temporada.py``, pero sin reemplazar los estudiantes.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from bson import json_util

from ..config import Settings
from ..db import Collections, Doc
from ..domain.cards import MAX_CARDS, generate_unique_cards, validar_duplicados
from ..errors import ApiError, Conflict
from ..utils import safe_int
from .game import GameService
from .pdf_render import render_cards_pdf

CONFIRMATION = "NUEVO JUEGO"
RESERVATION_FIELDS = ("totalTables", "usedTables", "fromSerial", "toSerial", "reserved_table_ids", "total_vendido")
PDF_PREFIX = "tablas_"
# Un reinicio a la vez (dos administradores pulsando a la vez no deben mezclar tablas).
_LOCK = threading.Lock()


def _dump(path: Path, docs: list[Doc]) -> None:
    """Un documento por línea (se restaura con ``mongoimport``)."""
    lines = (json_util.dumps(d, json_options=json_util.CANONICAL_JSON_OPTIONS) for d in docs)
    path.write_text("\n".join(lines) + ("\n" if docs else ""), encoding="utf-8")


class NewGameService:
    def __init__(self, cols: Collections, settings: Settings) -> None:
        self.cols = cols
        self.settings = settings

    def summary(self) -> dict[str, Any]:
        """Lo que se borraría, para mostrarlo antes de confirmar."""
        pdf = self.latest_pdf()
        return {
            "tablas": self.cols.tables.count_documents({}),
            "tablas_asignadas": self.cols.tables.count_documents({"stateAsigned": True}),
            "tablas_ganadoras": self.cols.winners.count_documents({}),
            "participantes": self.cols.participants.count_documents({}),
            "cuentas_con_reserva": self.cols.users.count_documents({"totalTables": {"$gt": 0}}),
            "estudiantes": self.cols.students.count_documents({}),
            "animadores": self.cols.animators.count_documents({}),
            "maximo": MAX_CARDS,
            "confirmacion": CONFIRMATION,
            "pdf_actual": pdf.name if pdf else None,
        }

    # ---------------------------------------------------------------- PDF
    def latest_pdf(self) -> Path | None:
        folder = self.settings.upload_dir
        pdfs = sorted(folder.glob(f"{PDF_PREFIX}*.pdf")) if folder.exists() else []
        return pdfs[-1] if pdfs else None

    def _save_pdf(self, data: bytes, stamp: str) -> Path:
        folder = self.settings.upload_dir
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{PDF_PREFIX}{stamp}.pdf"
        tmp = path.with_suffix(".pdf.tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
        return path

    # ------------------------------------------------------------ reinicio
    def _backup(self, stamp: str) -> Path:
        folder = self.settings.backup_dir / f"nuevo_juego_{stamp}"
        folder.mkdir(parents=True, exist_ok=True)
        _dump(folder / "Participantes.json", list(self.cols.participants.find({})))
        _dump(folder / "tablas.json", list(self.cols.tables.find({})))
        _dump(folder / "tablas_ganadoras.json", list(self.cols.winners.find({})))
        reserved = {f: {"$exists": True} for f in RESERVATION_FIELDS}
        users = self.cols.users.find({"$or": [{k: v} for k, v in reserved.items()]}, {f: 1 for f in RESERVATION_FIELDS})
        _dump(folder / "Users_reservas.json", list(users))
        return folder

    def _wipe(self) -> dict[str, int]:
        return {
            "tablas_borradas": self.cols.tables.delete_many({}).deleted_count,
            "ganadoras_borradas": self.cols.winners.delete_many({}).deleted_count,
            "participantes_borrados": self.cols.participants.delete_many({}).deleted_count,
            "reservas_en_cero": self.cols.users.update_many(
                {}, {"$unset": dict.fromkeys(RESERVATION_FIELDS, "")}
            ).modified_count,
        }

    def start(self, cantidad: Any, confirmation: Any) -> dict[str, Any]:
        if str(confirmation or "").strip() != CONFIRMATION:
            raise ApiError(f"Para confirmar escriba exactamente: {CONFIRMATION}")
        n = safe_int(cantidad, 0)
        if not 0 < n <= MAX_CARDS:
            raise ApiError(f"La cantidad de tablas debe estar entre 1 y {MAX_CARDS}.")
        if not _LOCK.acquire(blocking=False):
            raise Conflict("Ya hay un reinicio en curso. Espere a que termine.")
        try:
            return self._start(n)
        finally:
            _LOCK.release()

    def _start(self, n: int) -> dict[str, Any]:
        stamp = f"{datetime.now():%Y-%m-%d_%H%M%S}"
        # 1) Tablas y PDF primero: si algo falla aquí todavía no se ha borrado nada.
        cards = generate_unique_cards(n)
        if validar_duplicados(cards)["duplicados"]:
            raise ApiError("Se generaron tablas repetidas; vuelva a intentarlo.", 500)
        pdf = self._save_pdf(render_cards_pdf(cards), stamp)

        # 2) Respaldo y 3) limpieza.
        backup = self._backup(stamp)
        result: dict[str, Any] = self._wipe()

        # 4) Tablas nuevas y partida en blanco.
        now = time.time()
        self.cols.tables.insert_many(
            [
                {"serial": c["serial"], "matrix": c["matrix"], "timestamp": now, "won": False, "stateAsigned": False}
                for c in cards
            ]
        )
        GameService(self.cols, self.settings).rebuild_active_json()
        result.update(
            {
                "tablas_generadas": n,
                "desde": cards[0]["serial"],
                "hasta": cards[-1]["serial"],
                "pdf": pdf.name,
                "respaldo": backup.name,
            }
        )
        return result
