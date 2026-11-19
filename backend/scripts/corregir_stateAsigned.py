#!/usr/bin/env python3
"""
Script para corregir el campo stateAsigned en la colección tablas.
Las tablas que están asignadas a participantes deben tener stateAsigned: True
Las tablas que NO están asignadas deben tener stateAsigned: False
"""

import sys

from _common import get_database
from bson import ObjectId

# Conexión a MongoDB
mongo_db = get_database()
mongo_collection_participantes = mongo_db["Participantes"]
mongo_collection_tables = mongo_db["tablas"]


def corregir_stateAsigned(usuario_id_str=None):
    """Corrige el campo stateAsigned para todas las tablas."""

    print(f"\n{'=' * 70}")
    print("🔧 CORRECCIÓN DE stateAsigned EN TABLAS")
    print(f"{'=' * 70}")

    # Obtener todos los IDs de tablas asignadas a participantes
    participantes = list(mongo_collection_participantes.find({}))

    print(f"\n👥 Procesando {len(participantes)} participantes...")

    tablas_asignadas = set()
    for p in participantes:
        tablas = p.get("tablas", [])
        for t in tablas:
            # Convertir a string para comparar
            if isinstance(t, ObjectId):
                tablas_asignadas.add(str(t))
            else:
                tablas_asignadas.add(t)

    print(f"✓ Total de tabla IDs asignadas encontradas: {len(tablas_asignadas)}")

    # Obtener todas las tablas
    todas_tablas = list(mongo_collection_tables.find({}))
    print(f"✓ Total de tablas en colección: {len(todas_tablas)}")

    # Contar cuántas necesitan corrección
    tablas_a_marcar_asignadas = []
    tablas_a_marcar_libres = []

    for tabla in todas_tablas:
        tabla_id = str(tabla["_id"])
        tabla_serial = tabla.get("serial", "DESCONOCIDA")
        esta_asignada = tabla_id in tablas_asignadas
        estado_actual = tabla.get("stateAsigned", False)

        # Si debería estar asignada pero no lo está
        if esta_asignada and not estado_actual:
            tablas_a_marcar_asignadas.append((tabla_id, tabla_serial))
        # Si no debería estar asignada pero lo está
        elif not esta_asignada and estado_actual:
            tablas_a_marcar_libres.append((tabla_id, tabla_serial))

    print("\n📊 RESUMEN DE CORRECCIONES:")
    print(f"  - Tablas que deben estar ASIGNADAS pero están LIBRES: {len(tablas_a_marcar_asignadas)}")
    print(f"  - Tablas que deben estar LIBRES pero están ASIGNADAS: {len(tablas_a_marcar_libres)}")

    if tablas_a_marcar_asignadas:
        print("\n📋 Tablas a marcar como ASIGNADAS:")
        for _tabla_id, serial in tablas_a_marcar_asignadas[:10]:
            print(f"    {serial}")
        if len(tablas_a_marcar_asignadas) > 10:
            print(f"    ... y {len(tablas_a_marcar_asignadas) - 10} más")

    if tablas_a_marcar_libres:
        print("\n📋 Tablas a marcar como LIBRES:")
        for _tabla_id, serial in tablas_a_marcar_libres[:10]:
            print(f"    {serial}")
        if len(tablas_a_marcar_libres) > 10:
            print(f"    ... y {len(tablas_a_marcar_libres) - 10} más")

    # Preguntar si desea corregir
    if tablas_a_marcar_asignadas or tablas_a_marcar_libres:
        print(f"\n{'=' * 70}")
        respuesta = input("¿Deseas CORREGIR estos estados? (S/N): ").strip().upper()

        if respuesta == "S":
            # Marcar como asignadas
            if tablas_a_marcar_asignadas:
                ids_a_asignar = [ObjectId(t[0]) for t in tablas_a_marcar_asignadas]
                resultado = mongo_collection_tables.update_many(
                    {"_id": {"$in": ids_a_asignar}}, {"$set": {"stateAsigned": True}}
                )
                print(f"\n✅ {resultado.modified_count} tablas marcadas como ASIGNADAS")

            # Marcar como libres
            if tablas_a_marcar_libres:
                ids_a_liberar = [ObjectId(t[0]) for t in tablas_a_marcar_libres]
                resultado = mongo_collection_tables.update_many(
                    {"_id": {"$in": ids_a_liberar}}, {"$set": {"stateAsigned": False}}
                )
                print(f"✅ {resultado.modified_count} tablas marcadas como LIBRES")

            print("\n✅ ¡CORRECCIÓN COMPLETADA!")
        else:
            print("\n⏸️  Corrección cancelada.")
    else:
        print("\n✅ No hay correcciones necesarias. Todos los estados están correctos.")

    print(f"\n{'=' * 70}\n")


if __name__ == "__main__":
    usuario_id = sys.argv[1] if len(sys.argv) > 1 else None
    corregir_stateAsigned(usuario_id)
