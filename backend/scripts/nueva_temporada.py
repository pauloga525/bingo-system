"""Prepara una temporada nueva del Bingo.

1. Lee el Excel de alumnos (una fila por estudiante) y guarda en ``Estudiantes``
   solo lo necesario: nombres, apellidos, cédula, curso, especialidad,
   nivel y paralelo. No se copian datos de padres, direcciones, etc.
2. Genera ``--tablas`` cartones nuevos (CARD00001..N) y su PDF.
3. Limpia la temporada anterior:
   - borra todas las tablas y las tablas ganadoras;
   - borra los participantes alumnos y externos;
   - deja a los participantes docentes sin tablas (total 0);
   - pone en cero las reservas y contadores de los animadores (``Users``);
   - reemplaza la colección ``Estudiantes`` por la del Excel.
4. Reinicia la partida (snapshot JSON vacío hasta que se asignen tablas).

Por defecto SOLO MUESTRA lo que haría. Para aplicar los cambios use ``--ejecutar``
(haga antes un respaldo con mongodump).

Uso:
    python scripts/nueva_temporada.py "Alumnos(2026-2027).xlsx" --tablas 11000 --pdf "upload/tablas 2026.pdf"
    python scripts/nueva_temporada.py "Alumnos(2026-2027).xlsx" --tablas 11000 --pdf "upload/tablas 2026.pdf" --ejecutar
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

from _common import get_database

from bingo.config import Settings
from bingo.db import Collections
from bingo.domain.cards import MAX_CARDS, generate_unique_cards, validar_duplicados
from bingo.errors import ApiError
from bingo.services.game import GameService
from bingo.services.pdf_render import render_cards_pdf
from bingo.services.students_import import read_students, repeated_cedulas

CAMPOS_RESERVA = ("totalTables", "usedTables", "fromSerial", "toSerial", "reserved_table_ids", "total_vendido")


def leer_estudiantes(excel: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Devuelve ``(estudiantes, errores)`` con el mismo lector que usa el panel."""
    try:
        estudiantes, errores = read_students(excel)
    except ApiError as exc:
        raise SystemExit(exc.message) from exc
    repetidos = repeated_cedulas(estudiantes)
    if repetidos:
        errores.append(f"Num documento repetido en el Excel: {repetidos[:10]}")
    return estudiantes, errores


def resumen_actual(cols: Collections) -> dict[str, Any]:
    return {
        "tablas": cols.tables.count_documents({}),
        "tablas_asignadas": cols.tables.count_documents({"stateAsigned": True}),
        "tablas_ganadoras": cols.winners.count_documents({}),
        "participantes_alumnos_externos": cols.participants.count_documents({"tipo": {"$in": ["alumno", "externo"]}}),
        "participantes_docentes": cols.participants.count_documents({"tipo": "docente"}),
        "participantes_otro_tipo": cols.participants.count_documents(
            {"tipo": {"$nin": ["alumno", "externo", "docente"]}}
        ),
        "animadores_con_reserva": cols.users.count_documents({"totalTables": {"$gt": 0}}),
        "estudiantes": cols.students.count_documents({}),
    }


def limpiar_temporada(cols: Collections) -> dict[str, int]:
    res = {
        "tablas_borradas": cols.tables.delete_many({}).deleted_count,
        "ganadoras_borradas": cols.winners.delete_many({}).deleted_count,
        "participantes_borrados": cols.participants.delete_many({"tipo": {"$in": ["alumno", "externo"]}}).deleted_count,
        "docentes_sin_tablas": cols.participants.update_many(
            {"tipo": "docente"}, {"$set": {"tablas": [], "total_pagar": 0}}
        ).modified_count,
        "animadores_en_cero": cols.users.update_many(
            {}, {"$unset": {campo: "" for campo in CAMPOS_RESERVA}}
        ).modified_count,
        "estudiantes_borrados": cols.students.delete_many({}).deleted_count,
    }
    return res


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("excel", type=Path, help="Excel de alumnos de la temporada")
    parser.add_argument("--tablas", type=int, default=11000, help="Cantidad de tablas nuevas (default 11000)")
    parser.add_argument("--pdf", type=Path, default=Path("upload/tablas 2026.pdf"), help="Ruta del PDF de tablas")
    parser.add_argument("--ejecutar", action="store_true", help="Aplica los cambios (sin esto solo simula)")
    args = parser.parse_args()

    if not 0 < args.tablas <= MAX_CARDS:
        raise SystemExit(f"--tablas debe estar entre 1 y {MAX_CARDS}")

    estudiantes, errores = leer_estudiantes(args.excel)
    print(f"Excel: {len(estudiantes)} estudiantes válidos, {len(errores)} con problemas.")
    for e in errores[:20]:
        print("  -", e)
    print("  Ejemplo:", estudiantes[0] if estudiantes else "-")
    if any("repetido" in e for e in errores):
        raise SystemExit("Hay cédulas repetidas en el Excel; corríjalo antes de continuar.")

    db = get_database()
    cols = Collections.from_client(db.client, db.name)
    print("Estado actual:", resumen_actual(cols))

    if not args.ejecutar:
        print("\nSIMULACIÓN: no se modificó nada. Agregue --ejecutar para aplicar.")
        return 0

    # 1) Tablas y PDF primero: si algo falla aquí todavía no se ha borrado nada.
    inicio = time.time()
    cards = generate_unique_cards(args.tablas)
    validacion = validar_duplicados(cards)
    if validacion["duplicados"]:
        raise SystemExit("Se generaron tablas duplicadas; vuelva a ejecutar.")
    args.pdf.parent.mkdir(parents=True, exist_ok=True)
    args.pdf.write_bytes(render_cards_pdf(cards))
    print(f"PDF con {len(cards)} tablas: {args.pdf.resolve()} ({time.time() - inicio:.0f} s)")

    # 2) Limpieza de la temporada anterior.
    print("Limpieza:", limpiar_temporada(cols))

    # 3) Carga de lo nuevo.
    ahora = time.time()
    cols.tables.insert_many(
        [
            {"serial": c["serial"], "matrix": c["matrix"], "timestamp": ahora, "won": False, "stateAsigned": False}
            for c in cards
        ]
    )
    cols.students.insert_many(estudiantes)
    print(f"Insertadas {len(cards)} tablas y {len(estudiantes)} estudiantes.")

    # 4) Partida en blanco (se llenará a medida que se asignen tablas).
    print(GameService(cols, Settings.from_env()).rebuild_active_json()["message"])
    print("Estado final:", resumen_actual(cols))
    return 0


if __name__ == "__main__":
    sys.exit(main())
