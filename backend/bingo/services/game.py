"""Estado de la partida en curso.

La partida se juega sobre un snapshot JSON (``jsons/bingo_cards_active_*.json``)
reconstruido desde MongoDB con las tablas asignadas y no ganadoras.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from pymongo import UpdateOne

from ..config import Settings
from ..db import Collections
from ..domain.cards import (
    GRID,
    MAX_CARDS,
    apply_number,
    count_hits,
    empty_marks,
    generate_unique_cards,
    validar_duplicados,
)
from ..domain.serials import safe_filename_part
from ..errors import ApiError, Conflict, NotFound
from .pdf_render import render_cards_pdf, render_winner_pdf

logger = logging.getLogger(__name__)

ACTIVE_PREFIX = "bingo_cards_active_"


class GameService:
    def __init__(self, cols: Collections, settings: Settings) -> None:
        self.cols = cols
        self.settings = settings

    # ------------------------------------------------------------------ JSON
    def active_cards_path(self) -> Path | None:
        """Snapshot activo: el ``bingo_cards_active_*`` más reciente.

        Si no existe ninguno se usa el JSON más reciente de la carpeta
        (comportamiento anterior). Así ``/generate`` y ``/upload`` ya no
        reemplazan la partida en curso con *todos* los cartones.
        """
        folder = self.settings.json_dir
        if not folder.is_dir():
            return None
        files = [f for f in folder.glob("*.json") if f.is_file()]
        active = [f for f in files if f.name.startswith(ACTIVE_PREFIX)]
        candidates = active or files
        if not candidates:
            return None
        return max(candidates, key=lambda f: f.stat().st_mtime)

    def current_cards(self) -> list[dict[str, Any]]:
        path = self.active_cards_path()
        if path is None:
            return []
        cards: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
        return cards

    @staticmethod
    def write_json(path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    # --------------------------------------------------------------- partida
    def mark_number(self, number: int, marked: bool) -> None:
        path = self.active_cards_path()
        if path is None:
            raise ApiError("No hay cartones")
        cards = json.loads(path.read_text(encoding="utf-8"))
        for card in cards:
            apply_number(card, number, marked)
        self.write_json(path, cards)

    def progress(self) -> dict[str, Any]:
        """Aciertos por cartón, top 3 y ganadores (tabla llena)."""
        progreso: list[dict[str, Any]] = []
        for card in self.current_cards():
            matrix = card.get("matrix") or [[None] * GRID for _ in range(GRID)]
            marks = card.get("marks") or [[False] * GRID for _ in range(GRID)]
            aciertos = count_hits(matrix, marks)
            won = aciertos == GRID * GRID
            if won:
                self._persist_winner(card["serial"], matrix)
            progreso.append({"serial": card["serial"], "aciertos": aciertos, "won": won})
        progreso.sort(key=lambda p: p["aciertos"], reverse=True)
        return {"top3": progreso[:3], "ganadores": [p for p in progreso if p["won"]]}

    def _persist_winner(self, serial: str, matrix: list[Any]) -> None:
        try:
            self.cols.winners.update_one(
                {"serial": serial},
                {
                    "$set": {"serial": serial, "matrix": matrix, "won": True},
                    # La fecha es la del primer registro, no la del último sondeo.
                    "$setOnInsert": {"timestamp": time.time()},
                },
                upsert=True,
            )
            self.cols.tables.update_one({"serial": serial}, {"$set": {"won": True}})
        except Exception:
            logger.exception("Error al guardar el ganador %s", serial)

    def winner_pdf(self, serial: str, matrix: Any, marks: Any) -> Path:
        if not matrix or not marks:
            card = next((c for c in self.current_cards() if c.get("serial") == serial), None)
            if card is None:
                raise NotFound("Cartón no encontrado", payload={"error": "Cartón no encontrado"})
            matrix = card["matrix"]
            marks = card.get("marks") or [[False] * GRID for _ in range(GRID)]
        self.settings.winners_dir.mkdir(parents=True, exist_ok=True)
        path = self.settings.winners_dir / f"ganador_{safe_filename_part(serial)}.pdf"
        render_winner_pdf(path, serial, matrix, marks)
        return path

    def rebuild_active_json(self) -> dict[str, Any]:
        """Reinicia la partida con las tablas asignadas que aún no ganaron."""
        rows = list(
            self.cols.tables.find(
                {"won": {"$ne": True}, "stateAsigned": True},
                {"serial": 1, "matrix": 1},
            )
        )
        cards = []
        for row in rows:
            matrix = row.get("matrix") or [[None] * GRID for _ in range(GRID)]
            matrix[2][2] = None
            cards.append(
                {"serial": row.get("serial"), "matrix": matrix, "marks": empty_marks(), "won": False, "aciertos": 0}
            )

        output = self.settings.json_dir / f"{ACTIVE_PREFIX}{time.time_ns()}.json"
        self.write_json(output, cards)
        self._prune_active_snapshots()

        if not cards:
            return {
                "success": True,
                "message": "No hay cartones activos (ninguna tabla asignada pendiente de ganar)",
                "removed_winners": 0,
                "json_path": str(output),
            }

        winners_count = self.cols.tables.count_documents({"won": True})
        message = f"Juego reiniciado — JSON reconstruido desde DB. Cartones activos: {len(cards)}"
        if winners_count:
            message += f" — cartones ganadores detectados en DB: {winners_count}"
        return {
            "success": True,
            "message": message,
            "removed_winners": winners_count,
            "json_path": str(output),
            "active_count": len(cards),
        }

    def _prune_active_snapshots(self) -> None:
        keep = max(self.settings.active_json_keep, 1)
        snapshots = sorted(
            self.settings.json_dir.glob(f"{ACTIVE_PREFIX}*.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        for old in snapshots[keep:]:
            try:
                old.unlink()
            except OSError:
                logger.warning("No se pudo borrar el snapshot %s", old)

    # ---------------------------------------------------- generación / carga
    def generate_cards(self, num_cards: int, force: bool = False) -> dict[str, Any]:
        """Genera cartones nuevos (PDF + JSON) y los guarda en MongoDB.

        Los seriales siempre son ``CARD00001..N``. Si ya existen en la base,
        regenerarlos cambiaría cartones que ya se imprimieron, así que se exige
        ``force`` y nunca se permite pisar tablas asignadas a participantes.
        """
        if not 0 < num_cards <= MAX_CARDS:
            raise ApiError(f"num_cards debe estar entre 1 y {MAX_CARDS}.")
        cards = generate_unique_cards(num_cards)
        serials = [c["serial"] for c in cards]

        assigned = self.cols.tables.count_documents({"serial": {"$in": serials}, "stateAsigned": True})
        if assigned:
            raise Conflict(f"No se puede regenerar: {assigned} de esos seriales ya están asignados a participantes.")
        existing = self.cols.tables.count_documents({"serial": {"$in": serials}})
        if existing and not force:
            raise Conflict(
                f"Ya existen {existing} tablas con esos seriales en la base. "
                'Regenerarlas cambiaría cartones ya impresos; envía "force": true para confirmar.'
            )

        self.settings.upload_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = self.settings.upload_dir / f"bingo_cards_{num_cards}.pdf"
        pdf_path.write_bytes(render_cards_pdf(cards))
        json_path = self.settings.json_dir / f"bingo_cards_{num_cards}.json"
        self.write_json(json_path, cards)

        now = time.time()
        self.cols.tables.bulk_write(
            [
                UpdateOne(
                    {"serial": c["serial"]},
                    {
                        "$set": {
                            "serial": c["serial"],
                            "matrix": c["matrix"],
                            "timestamp": now,
                            "won": False,
                            "stateAsigned": False,
                        }
                    },
                    upsert=True,
                )
                for c in cards
            ],
            ordered=False,
        )

        validacion = validar_duplicados(cards)
        return {
            "success": True,
            "pdf_path": str(pdf_path),
            "json_path": str(json_path),
            "total_cartones": validacion["total"],
            "cartones_unicos": validacion["unicos"],
            "cartones_duplicados": validacion["duplicados"],
            "duplicados_seriales": validacion["duplicados_seriales"],
            "message": f"PDF guardado en: {pdf_path}, JSON en: {json_path}",
        }

    def import_cards(self, cards: list[dict[str, Any]]) -> dict[str, int | list[str]]:
        """Inserta/actualiza cartones leídos de un PDF sin romper el estado del juego.

        - Seriales nuevos: se insertan sin asignar.
        - Existentes con la misma matriz: no se tocan.
        - Existentes con matriz distinta: se actualiza la matriz solo si la
          tabla no está asignada; si lo está se reporta como conflicto.
        Nunca se reinicia ``won`` ni ``stateAsigned`` de tablas existentes.
        """
        serials = [c["serial"] for c in cards]
        existing = {
            doc["serial"]: doc
            for doc in self.cols.tables.find(
                {"serial": {"$in": serials}}, {"serial": 1, "matrix": 1, "stateAsigned": 1}
            )
        }
        now = time.time()
        ops: list[UpdateOne] = []
        inserted = updated = 0
        conflicts: list[str] = []
        for card in cards:
            current = existing.get(card["serial"])
            if current is None:
                ops.append(
                    UpdateOne(
                        {"serial": card["serial"]},
                        {
                            "$setOnInsert": {
                                "serial": card["serial"],
                                "matrix": card["matrix"],
                                "timestamp": now,
                                "won": False,
                                "stateAsigned": False,
                            }
                        },
                        upsert=True,
                    )
                )
                inserted += 1
            elif current.get("matrix") != card["matrix"]:
                if current.get("stateAsigned"):
                    conflicts.append(card["serial"])
                    continue
                ops.append(UpdateOne({"_id": current["_id"]}, {"$set": {"matrix": card["matrix"], "timestamp": now}}))
                updated += 1
        if ops:
            self.cols.tables.bulk_write(ops, ordered=False)
        return {"insertados": inserted, "actualizados": updated, "conflictos": conflicts}
