"""Regla única de cobro de tablas."""

from __future__ import annotations

PACK_5_PRICE = 10
PACK_2_PRICE = 5
SINGLE_PRICE = 3


def calcular_total(num_tablas: int) -> int:
    """Total a pagar por ``num_tablas``.

    Paquetes de 5 a $10; del resto, cada par a $5 y una suelta a $3.
    Es la regla que se aplica al registrar participantes y debe usarse en
    todos los flujos (agregar/quitar tablas y reportes).
    """
    if num_tablas <= 0:
        return 0
    packs_5, rest = divmod(num_tablas, 5)
    pairs, singles = divmod(rest, 2)
    return packs_5 * PACK_5_PRICE + pairs * PACK_2_PRICE + singles * SINGLE_PRICE


def desglose(num_tablas: int) -> dict[str, int]:
    """Promociones que se aplican a ``num_tablas`` (misma regla que :func:`calcular_total`).

    ``{"paquete_5": n, "paquete_2": n, "suelta": n}``: paquetes de 5 a $10,
    pares a $5 y tabla suelta a $3.
    """
    if num_tablas <= 0:
        return {"paquete_5": 0, "paquete_2": 0, "suelta": 0}
    packs_5, rest = divmod(num_tablas, 5)
    pairs, singles = divmod(rest, 2)
    return {"paquete_5": packs_5, "paquete_2": pairs, "suelta": singles}


PROMOCIONES: dict[str, dict[str, int]] = {
    "paquete_5": {"tablas": 5, "precio": PACK_5_PRICE},
    "paquete_2": {"tablas": 2, "precio": PACK_2_PRICE},
    "suelta": {"tablas": 1, "precio": SINGLE_PRICE},
}
