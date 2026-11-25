"""Roles de los vendedores (personal con cuenta en ``Animadores``/``Users``).

Un vendedor puede tener **varios roles** (``roles``, lista; ``rol`` guarda el
primero por compatibilidad). Todos comparten los permisos del animador en el
panel. Diferencias:

- ``animador``: puede tener un curso y vende a alumnos, docentes y externos.
  Sus ventas a alumnos cuentan para el curso.
- Los demás roles (secretaría, financiero, parroquia, oratorio, tecniclub) no
  tienen curso; venden a externos y también a alumnos, pero esas ventas cuentan
  como **venta externa del rol** que vende, no del curso del alumno.

Cada venta guarda el rol con el que se hizo (``rol`` en el registro de la
venta). El administrador es aparte (``tipo_usuario`` 0) y aparece como ``admin``.
"""

from __future__ import annotations

from typing import Any

from ..errors import ApiError, Forbidden

ADMIN_ROL = "admin"
ANIMADOR_ROL = "animador"
ROLES: dict[str, str] = {
    ANIMADOR_ROL: "Animador",
    "secretaria": "Secretaría",
    "financiero": "Financiero",
    "parroquia": "Parroquia",
    "oratorio": "Oratorio",
    "tecniclub": "Tecniclub",
}
# Roles sin curso: sus ventas son externas del rol (aunque el comprador sea alumno).
SOLO_EXTERNOS = frozenset(ROLES) - {ANIMADOR_ROL}
# Roles que, además del administrador, pueden ver la sección Reportes.
VEN_REPORTES = frozenset({"financiero"})
EXTERNO = "externo"
ALUMNO = "alumno"
DOCENTE = "docente"
ETIQUETAS: dict[str, str] = {ADMIN_ROL: "Administrador", **ROLES}


def _norm(raw: Any) -> str:
    return str(raw or "").strip().lower()


def clean_rol(raw: Any) -> str:
    """Rol validado; vacío equivale a ``animador`` (los documentos antiguos no lo tienen)."""
    rol = _norm(raw) or ANIMADOR_ROL
    if rol not in ROLES:
        raise ApiError(f"Rol no válido. Use uno de: {', '.join(ROLES)}.")
    return rol


def clean_roles(raw: Any) -> list[str]:
    """Lista de roles validada y sin repetir (acepta lista o texto separado por comas)."""
    items = raw if isinstance(raw, (list, tuple)) else str(raw or "").split(",")
    roles = list(dict.fromkeys(clean_rol(r) for r in items if _norm(r)))
    if not roles:
        raise ApiError("Indique al menos un rol.")
    return roles


def roles_de(doc: dict[str, Any] | None) -> list[str]:
    """Roles de un animador o cuenta de ``Users`` (``["admin"]`` si es administrador)."""
    if not doc:
        return [ANIMADOR_ROL]
    if str(doc.get("tipo_usuario")) == "0":
        return [ADMIN_ROL]
    guardados = doc.get("roles")
    if isinstance(guardados, list):
        roles = [r for r in dict.fromkeys(_norm(x) for x in guardados) if r in ROLES]
        if roles:
            return roles
    rol = _norm(doc.get("rol"))
    return [rol if rol in ROLES else ANIMADOR_ROL]


def rol_de(doc: dict[str, Any] | None) -> str:
    """Rol principal (el primero de :func:`roles_de`)."""
    return roles_de(doc)[0]


def etiquetas(roles: list[str]) -> str:
    return ", ".join(ETIQUETAS.get(r, r) for r in roles)


def solo_externos(rol: str) -> bool:
    return rol in SOLO_EXTERNOS


def tipos_venta(roles: list[str]) -> list[str]:
    """Tipos de participante que puede registrar quien tiene esos roles."""
    if ADMIN_ROL in roles or ANIMADOR_ROL in roles:
        return [ALUMNO, DOCENTE, EXTERNO]
    return [ALUMNO, EXTERNO]


def rol_para_venta(roles: list[str], tipo: str, pedido: Any = None, permitidos: list[str] | None = None) -> str:
    """Rol con el que se registra una venta.

    ``pedido`` (opcional) debe ser uno de los roles del vendedor. Sin él, se usa
    ``animador`` para alumnos/docentes si lo tiene; si no, su rol principal.
    ``permitidos`` restringe los roles aceptables (p. ej. solo los sin curso).
    """
    if ADMIN_ROL in roles:
        return ADMIN_ROL
    opciones = [r for r in roles if permitidos is None or r in permitidos]
    if not opciones:
        raise Forbidden("Ninguno de sus roles puede realizar esta venta.")
    rol = _norm(pedido)
    if rol:
        if rol not in opciones:
            raise Forbidden(f"No puede vender con el rol {ETIQUETAS.get(rol, rol)}.")
    elif tipo != EXTERNO and ANIMADOR_ROL in opciones:
        rol = ANIMADOR_ROL
    else:
        rol = opciones[0]
    if tipo == DOCENTE and rol != ANIMADOR_ROL:
        raise Forbidden(f"El rol {ETIQUETAS[rol]} vende solo a alumnos y externos.")
    return rol
