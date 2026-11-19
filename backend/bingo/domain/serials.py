"""Manejo de seriales ``CARDNNNNN`` y rangos asignados a usuarios."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_DIGITS = re.compile(r"\d+")
_SAFE_SERIAL = re.compile(r"[^A-Za-z0-9_-]")


def serial_number(serial: str) -> int:
    """``"CARD00012" -> 12``; ``0`` si no tiene dígitos."""
    match = _DIGITS.search(serial or "")
    return int(match.group()) if match else 0


def safe_filename_part(serial: str) -> str:
    """Limpia un serial para usarlo dentro de un nombre de archivo."""
    return _SAFE_SERIAL.sub("_", serial)[:64] or "sin_serial"


@dataclass(frozen=True)
class SerialRange:
    """Rango ``fromSerial``..``toSerial`` de un usuario (puede ser descendente).

    Los administradores reservan desde el final, por eso ``from`` puede ser
    mayor que ``to``.
    """

    from_serial: str
    to_serial: str

    @classmethod
    def of_user(cls, user: dict[str, Any]) -> SerialRange | None:
        from_serial, to_serial = user.get("fromSerial"), user.get("toSerial")
        if not from_serial or not to_serial:
            return None
        return cls(str(from_serial), str(to_serial))

    @property
    def low(self) -> str:
        return min(self.from_serial, self.to_serial)

    @property
    def high(self) -> str:
        return max(self.from_serial, self.to_serial)

    def contains(self, serial: str) -> bool:
        return self.low <= serial <= self.high

    def mongo_filter(self) -> dict[str, Any]:
        return {"$gte": self.low, "$lte": self.high}

    def __str__(self) -> str:
        return f"{self.from_serial} a {self.to_serial}"
