"""Reporte general de ventas y participación."""

from __future__ import annotations

from collections import Counter
from typing import Any

from ..db import Collections
from ..domain.pricing import calcular_total
from ..utils import try_object_id

_USER_FIELDS = {"nombres_completos": 1, "usuario": 1, "curso": 1, "especialidad": 1, "nivel": 1, "paralelo": 1}


def _top(counter: Counter[str]) -> str | None:
    return counter.most_common(1)[0][0] if counter else None


class ReportService:
    def __init__(self, cols: Collections) -> None:
        self.cols = cols

    def build(self) -> dict[str, Any]:
        total_tablas = self.cols.tables.count_documents({})
        ganadoras_ids = [t["_id"] for t in self.cols.tables.find({"won": True}, {"_id": 1})]
        total_participantes = self.cols.participants.count_documents({})
        participantes_con_ganadores = (
            self.cols.participants.count_documents({"tablas": {"$in": ganadoras_ids}}) if ganadoras_ids else 0
        )

        participantes = list(
            self.cols.participants.find(
                {},
                {
                    "tablas": 1,
                    "registrado_por": 1,
                    "grupoAdetitss": 1,
                    "grupoAdetiss": 1,
                    "nivelCurso": 1,
                    "curso": 1,
                    "paralelo": 1,
                    "especialidad": 1,
                },
            )
        )
        user_ids = {oid for p in participantes if (oid := try_object_id(p.get("registrado_por")))}
        usuarios: dict[str, dict[str, Any]] = {}
        if user_ids:
            for u in self.cols.users.find({"_id": {"$in": list(user_ids)}}, _USER_FIELDS):
                usuarios[str(u["_id"])] = {
                    "nombre": u.get("nombres_completos") or u.get("usuario") or "Desconocido",
                    **{k: u.get(k) for k in ("usuario", "curso", "especialidad", "nivel", "paralelo")},
                }

        tablas_vendidas = 0
        ventas_por_usuario: Counter[str] = Counter()
        ventas_por_grupo: Counter[str] = Counter()
        por_nivel: Counter[str] = Counter()
        por_curso: Counter[str] = Counter()
        por_paralelo: Counter[str] = Counter()
        por_especialidad: Counter[str] = Counter()

        for p in participantes:
            num_tablas = len(p.get("tablas") or [])
            # Misma regla de cobro que al registrar (antes el reporte usaba otra).
            monto = calcular_total(num_tablas)
            tablas_vendidas += num_tablas

            uid = try_object_id(p.get("registrado_por"))
            u = usuarios.get(str(uid), {}) if uid else {}
            ventas_por_usuario[str(u.get("nombre", "Desconocido"))] += monto
            ventas_por_grupo[str(p.get("grupoAdetitss") or p.get("grupoAdetiss") or "Sin grupo")] += monto

            # Las claves se pasan a str: hay datos con nivelCurso numérico y de texto
            # mezclados, y eso hacía fallar el reporte (500) al serializar.
            por_nivel[str(p.get("nivelCurso") or u.get("nivel") or "Sin nivel")] += 1
            por_curso[str(p.get("curso") or u.get("curso") or "Sin curso")] += 1
            por_paralelo[str(p.get("paralelo") or u.get("paralelo") or "Sin paralelo")] += 1
            por_especialidad[str(p.get("especialidad") or u.get("especialidad") or "Sin especialidad")] += 1

        usuario_top = None
        if ventas_por_usuario:
            nombre, total = ventas_por_usuario.most_common(1)[0]
            uid_top = next((k for k, v in usuarios.items() if v["nombre"] == nombre), None)
            usuario_top = {"id": uid_top, "nombre": nombre, "total": total}
        grupo_top = None
        if ventas_por_grupo:
            nombre, total = ventas_por_grupo.most_common(1)[0]
            grupo_top = {"nombre": nombre, "total": total}

        tablas_ganadoras = len(ganadoras_ids)
        return {
            "total_tablas": total_tablas,
            "tablas_ganadoras": tablas_ganadoras,
            "total_participantes": total_participantes,
            "participantes_con_ganadores": participantes_con_ganadores,
            "tasa_ganadores": round(tablas_ganadoras / total_tablas * 100, 2) if total_tablas else 0,
            # Nombre histórico: es la cantidad de TABLAS vendidas, no dinero.
            "total_vendido": tablas_vendidas,
            "ventas_por_usuario": dict(ventas_por_usuario),
            "usuario_top": usuario_top,
            "ventas_por_grupo": dict(ventas_por_grupo),
            "grupo_top": grupo_top,
            "conteo_por_nivel": dict(por_nivel),
            "conteo_por_curso": dict(por_curso),
            "conteo_por_paralelo": dict(por_paralelo),
            "conteo_por_especialidad": dict(por_especialidad),
            "top_nivel": _top(por_nivel),
            "top_curso": _top(por_curso),
            "top_paralelo": _top(por_paralelo),
            "top_especialidad": _top(por_especialidad),
        }
