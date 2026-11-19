#!/usr/bin/env python3
"""Diagnóstico de consistencia de la base (SOLO LECTURA, no modifica nada).

Uso (desde la raíz del proyecto):
    python scripts/diagnostico_consistencia.py

Revisa:
- Tablas que aparecen en más de un participante.
- Tablas referenciadas por un participante pero con stateAsigned != True.
- Tablas con stateAsigned = True que ningún participante tiene.
- Cédulas duplicadas.
- Usuarios cuyo usedTables / total_vendido no coincide con lo real.

Para corregir los contadores de un usuario: POST /api/validar-tablas/<usuario_id>.
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pymongo import MongoClient

from bingo.config import Settings
from bingo.domain.pricing import calcular_total


def main() -> int:
    settings = Settings.from_env()
    db = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=5000)[settings.mongo_db]

    owners: defaultdict[object, list[str]] = defaultdict(list)
    por_usuario: defaultdict[object, list[int]] = defaultdict(list)
    cedulas: Counter[str] = Counter()
    for p in db["Participantes"].find({}, {"tablas": 1, "cedula": 1, "registrado_por": 1}):
        cedulas[str(p.get("cedula"))] += 1
        tablas = p.get("tablas") or []
        por_usuario[p.get("registrado_por")].append(len(tablas))
        for t in tablas:
            owners[t].append(str(p.get("cedula")))

    serial = {t["_id"]: t["serial"] for t in db["tablas"].find({}, {"serial": 1})}
    asignadas = {t["_id"] for t in db["tablas"].find({"stateAsigned": True}, {"_id": 1})}

    compartidas = {serial.get(t, str(t)): ced for t, ced in owners.items() if len(ced) > 1}
    sin_flag = sorted(serial.get(t, str(t)) for t in owners if t not in asignadas)
    huerfanas = sorted(serial[t] for t in asignadas - set(owners))
    cedulas_dup = {c: n for c, n in cedulas.items() if n > 1}

    print(f"Participantes: {sum(cedulas.values())} | refs a tablas: {sum(len(v) for v in owners.values())}")
    print(f"Tablas con stateAsigned=True: {len(asignadas)}")
    print(f"\n[1] Tablas repetidas (mismo u otro participante): {len(compartidas)}")
    for s, ced in sorted(compartidas.items()):
        print(f"    {s}: cédulas {ced}")
    print(f"\n[2] Referenciadas pero stateAsigned != True: {len(sin_flag)} {sin_flag[:20]}")
    print(f"[3] stateAsigned=True sin participante: {len(huerfanas)} {huerfanas[:20]}")
    print(f"[4] Cédulas duplicadas: {cedulas_dup}")

    print("\n[5] Usuarios con contadores desfasados:")
    desfasados = 0
    for u in db["Users"].find({}, {"usuario": 1, "usedTables": 1, "total_vendido": 1}):
        counts = por_usuario.get(u["_id"], [])
        used, vendido = sum(counts), sum(calcular_total(n) for n in counts)
        if u.get("usedTables", 0) != used or u.get("total_vendido", 0) != vendido:
            desfasados += 1
            print(
                f"    {u.get('usuario')} ({u['_id']}): usedTables {u.get('usedTables', 0)} vs real {used} | "
                f"total_vendido {u.get('total_vendido', 0)} vs real {vendido}"
            )
    print(f"    Total: {desfasados}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
