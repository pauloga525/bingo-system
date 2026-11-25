"""Roles de los vendedores (personal con cuenta en ``Animadores``/``Users``).

Todos los roles tienen los mismos permisos en el panel que un animador. La
diferencia: ``animador`` puede tener un curso y vender a alumnos, docentes y
externos; los demás roles no tienen curso y **solo venden a externos**.
El administrador es aparte (``tipo_usuario`` 0) y aparece como ``admin``.
"""

from __future__ import annotations

from typing import Any

from ..errors import ApiError

ADMIN_ROL = "admin"
ANIMADOR_ROL = "animador"
ROLES: dict[str, str] = {
    ANIMADOR_ROL: "Animador",
    "secretaria": "Secretaría",
    "financiero": "Financiero",
    "parroquia": "Parroquia",
    "oratorio": "Oratorio",
}
# Roles que solo pueden registrar participantes de tipo externo.
SOLO_EXTERNOS = frozenset(ROLES) - {ANIMADOR_ROL}
# Roles que, además del administrador, pueden ver la sección Reportes.
VEN_REPORTES = frozenset({"financiero"})
EXTERNO = "externo"
ETIQUETAS: dict[str, str] = {ADMIN_ROL: "Administrador", **ROLES}


def clean_rol(raw: Any) -> str:
    """Rol validado; vacío equivale a ``animador`` (los documentos antiguos no lo tienen)."""
    rol = str(raw or "").strip().lower() or ANIMADOR_ROL
    if rol not in ROLES:
        raise ApiError(f"Rol no válido. Use uno de: {', '.join(ROLES)}.")
    return rol


def rol_de(doc: dict[str, Any] | None) -> str:
    """Rol guardado en un animador o cuenta de ``Users`` (``admin`` si es administrador)."""
    if not doc:
        return ANIMADOR_ROL
    if str(doc.get("tipo_usuario")) == "0":
        return ADMIN_ROL
    rol = str(doc.get("rol") or "").strip().lower()
    return rol if rol in ROLES else ANIMADOR_ROL


def solo_externos(rol: str) -> bool:
    return rol in SOLO_EXTERNOS
