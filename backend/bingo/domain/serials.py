"""Manejo de seriales ``CARDNNNNN``."""

from __future__ import annotations

import re

_DIGITS = re.compile(r"\d+")
_SAFE_SERIAL = re.compile(r"[^A-Za-z0-9_-]")


def serial_number(serial: str) -> int:
    """``"CARD00012" -> 12``; ``0`` si no tiene dígitos."""
    match = _DIGITS.search(serial or "")
    return int(match.group()) if match else 0


def safe_filename_part(serial: str) -> str:
    """Limpia un serial para usarlo dentro de un nombre de archivo."""
    return _SAFE_SERIAL.sub("_", serial)[:64] or "sin_serial"
