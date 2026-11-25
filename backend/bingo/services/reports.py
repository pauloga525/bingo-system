"""Reporte general de ventas y participación.

Las ventas se cuentan por cada venta registrada en el participante
(``Participantes.ventas``): al vendedor que la hizo y con el rol con que la
hizo. Así, si secretaría agrega tablas a un alumno, esas tablas cuentan para
secretaría y no para el curso del alumno. Los conteos por curso, nivel y
paralelo solo incluyen participantes con alguna venta del rol animador.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from ..db import Collections
from ..domain.pricing import PROMOCIONES, calcular_total, desglose
from ..domain.roles import ADMIN_ROL, ANIMADOR_ROL, ETIQUETAS, ROLES, etiquetas, rol_de, roles_de
from ..utils import safe_int, try_object_id
from .participants import sales_of

_USER_FIELDS = {
    "nombres_completos": 1,
    "usuario": 1,
    "curso": 1,
    "especialidad": 1,
    "nivel": 1,
    "paralelo": 1,
    "tipo_usuario": 1,
    "rol": 1,
    "roles": 1,
}
_PROMOS = tuple(PROMOCIONES)


def _ventas_vacias() -> dict[str, Any]:
    return {"participantes": 0, "tablas": 0, "monto": 0, "promociones": dict.fromkeys(_PROMOS, 0)}


def _sumar(destino: dict[str, Any], tablas: int, monto: int, promos: dict[str, int], nuevo: bool = True) -> None:
    destino["participantes"] += 1 if nuevo else 0
    destino["tablas"] += tablas
    destino["monto"] += monto
    for k, n in promos.items():
        destino["promociones"][k] += n


def _contar_ventas(
    p: dict[str, Any],
    usuarios: dict[str, dict[str, Any]],
    por_vendedor: dict[str, dict[str, Any]],
    por_rol: dict[str, dict[str, Any]],
    ventas_por_usuario: Counter[str],
) -> dict[str, Any] | None:
    """Suma cada venta del participante a su vendedor y al rol con que se hizo.

    Las ventas antiguas toman el rol actual del vendedor. Devuelve el usuario
    animador que le vendió (para los conteos por curso) o ``None`` si ninguno.
    """
    registrador = usuarios.get(str(try_object_id(p.get("registrado_por"))), {})
    vistos_vendedor: set[str] = set()
    vistos_rol: set[str] = set()
    u_curso: dict[str, Any] | None = None
    for venta in sales_of(p, str(registrador.get("rol") or ANIMADOR_ROL)):
        n = len(venta.get("tablas") or [])
        monto = safe_int(venta.get("monto"), calcular_total(n))
        promos = desglose(n)
        uid = str(venta.get("vendedor") or "")
        u = usuarios.get(uid, {})
        rol = str(venta.get("rol") or u.get("rol") or ANIMADOR_ROL)
        if uid in por_vendedor:
            _sumar(por_vendedor[uid], n, monto, promos, uid not in vistos_vendedor)
            vistos_vendedor.add(uid)
        _sumar(por_rol.setdefault(rol, _ventas_vacias()), n, monto, promos, rol not in vistos_rol)
        vistos_rol.add(rol)
        ventas_por_usuario[str(u.get("nombre", "Desconocido"))] += monto
        if rol == ANIMADOR_ROL and u_curso is None:
            u_curso = u
    return u_curso


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
                    "rol_vendedor": 1,
                    "ventas": 1,
                    "total_pagar": 1,
                },
            )
        )
        user_ids = {oid for p in participantes if (oid := try_object_id(p.get("registrado_por")))}
        user_ids |= {v.get("vendedor") for p in participantes for v in p.get("ventas") or [] if v.get("vendedor")}
        usuarios: dict[str, dict[str, Any]] = {}
        # Todos los vendedores (aunque no hayan vendido) más quienes registraron participantes.
        for u in self.cols.users.find(
            {"$or": [{"tipo_usuario": {"$ne": 0}}, {"_id": {"$in": list(user_ids)}}]}, _USER_FIELDS
        ):
            usuarios[str(u["_id"])] = {
                "nombre": u.get("nombres_completos") or u.get("usuario") or "Desconocido",
                "rol": rol_de(u),
                "roles": roles_de(u),
                **{k: u.get(k) for k in ("usuario", "curso", "especialidad", "nivel", "paralelo")},
            }
        por_vendedor: dict[str, dict[str, Any]] = {uid: _ventas_vacias() for uid in usuarios}
        por_rol: dict[str, dict[str, Any]] = {rol: _ventas_vacias() for rol in (*ROLES, ADMIN_ROL)}
        promociones_total: dict[str, int] = dict.fromkeys(_PROMOS, 0)
        dinero = 0

        tablas_vendidas = 0
        ventas_por_usuario: Counter[str] = Counter()
        ventas_por_grupo: Counter[str] = Counter()
        por_nivel: Counter[str] = Counter()
        por_curso: Counter[str] = Counter()
        por_paralelo: Counter[str] = Counter()
        por_especialidad: Counter[str] = Counter()

        for p in participantes:
            num_tablas = len(p.get("tablas") or [])
            # Totales del participante: misma regla de cobro que al registrar.
            tablas_vendidas += num_tablas
            dinero += calcular_total(num_tablas)
            for k, n in desglose(num_tablas).items():
                promociones_total[k] += n
            ventas_por_grupo[str(p.get("grupoAdetitss") or p.get("grupoAdetiss") or "Sin grupo")] += calcular_total(
                num_tablas
            )

            u_curso = _contar_ventas(p, usuarios, por_vendedor, por_rol, ventas_por_usuario)
            if u_curso is None:
                continue  # venta externa de un rol sin curso: no cuenta para cursos
            u = u_curso

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
        vendedores = [
            {
                "id": uid,
                "nombre": usuarios[uid]["nombre"],
                "usuario": usuarios[uid].get("usuario"),
                "rol": usuarios[uid]["rol"],
                "roles": usuarios[uid]["roles"],
                "rol_nombre": etiquetas(usuarios[uid]["roles"]),
                **ventas,
            }
            for uid, ventas in por_vendedor.items()
        ]
        vendedores.sort(key=lambda v: (-v["tablas"], v["nombre"]))
        roles = [
            {
                "rol": rol,
                "nombre": ETIQUETAS.get(rol, rol),
                "vendedores": sum(1 for u in usuarios.values() if rol in u["roles"]),
                **ventas,
            }
            for rol, ventas in por_rol.items()
        ]
        return {
            # Ventas reales (dinero con las promociones aplicadas).
            "tablas_vendidas": tablas_vendidas,
            "dinero_recaudado": dinero,
            "promociones": {
                k: {
                    **PROMOCIONES[k],
                    "cantidad": n,
                    "tablas_en_promocion": n * PROMOCIONES[k]["tablas"],
                    "monto": n * PROMOCIONES[k]["precio"],
                }
                for k, n in promociones_total.items()
            },
            "ventas_por_rol": roles,
            "ventas_por_vendedor": vendedores,
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
