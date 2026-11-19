"""Reglas puras del cartón de bingo (sin I/O)."""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Any, TypedDict

GRID = 5
CENTER = (2, 2)
# Rango de números por columna B-I-N-G-O.
COLUMN_RANGES = (range(1, 16), range(16, 31), range(31, 46), range(46, 61), range(61, 76))

Matrix = list[list[int | None]]
Marks = list[list[bool]]


class CardDict(TypedDict, total=False):
    serial: str
    matrix: Matrix
    marks: Marks
    won: bool
    aciertos: int


# El serial tiene 5 dígitos, así que no puede haber más de 99999 cartones.
MAX_CARDS = 99_999


def format_serial(index: int) -> str:
    """``1 -> "CARD00001"``."""
    return f"CARD{index:05d}"


def generate_bingo_card(rng: random.Random | None = None) -> Matrix:
    """Genera una matriz 5x5 con el centro libre (``None``)."""
    rnd = rng or random
    columns = [rnd.sample(COLUMN_RANGES[col], GRID) for col in range(GRID)]
    card: Matrix = [list(row) for row in zip(*columns, strict=True)]
    card[2][2] = None
    return card


def generate_unique_cards(count: int, rng: random.Random | None = None) -> list[CardDict]:
    """Genera ``count`` cartones sin matrices repetidas, con seriales consecutivos."""
    seen: set[tuple[tuple[int | None, ...], ...]] = set()
    cards: list[CardDict] = []
    while len(cards) < count:
        matrix = generate_bingo_card(rng)
        signature = matrix_signature(matrix)
        if signature in seen:
            continue
        seen.add(signature)
        cards.append({"serial": format_serial(len(cards) + 1), "matrix": matrix})
    return cards


def matrix_signature(matrix: Matrix) -> tuple[tuple[int | None, ...], ...]:
    return tuple(tuple(row) for row in matrix)


def empty_marks() -> Marks:
    """Marcas vacías con el centro libre marcado."""
    marks = [[False] * GRID for _ in range(GRID)]
    marks[2][2] = True
    return marks


def count_hits(matrix: Matrix, marks: Marks) -> int:
    """Casillas acertadas: marcadas o libres (``None``)."""
    return sum(1 for r in range(GRID) for c in range(GRID) if marks[r][c] or matrix[r][c] is None)


def is_full_card(matrix: Matrix, marks: Marks) -> bool:
    """Regla de victoria del juego: tabla llena (25 aciertos)."""
    return count_hits(matrix, marks) == GRID * GRID


def has_line(marks: Marks) -> bool:
    """Fila, columna o diagonal completa (no es la regla de victoria actual)."""
    if any(all(row) for row in marks):
        return True
    if any(all(marks[r][c] for r in range(GRID)) for c in range(GRID)):
        return True
    if all(marks[i][i] for i in range(GRID)):
        return True
    return all(marks[i][GRID - 1 - i] for i in range(GRID))


def apply_number(card: CardDict, number: int, marked: bool) -> None:
    """Marca/desmarca ``number`` en el cartón y recalcula ``won``."""
    matrix = card["matrix"]
    marks = card.get("marks") or empty_marks()
    for r in range(GRID):
        for c in range(GRID):
            if matrix[r][c] == number:
                marks[r][c] = marked
    marks[2][2] = True
    card["marks"] = marks
    card["won"] = is_full_card(matrix, marks)


def validar_duplicados(cards: list[CardDict] | list[dict[str, Any]]) -> dict[str, Any]:
    """Resumen de matrices duplicadas entre cartones."""
    by_matrix: defaultdict[tuple[tuple[int | None, ...], ...], list[str]] = defaultdict(list)
    for card in cards:
        by_matrix[matrix_signature(card["matrix"])].append(card["serial"])
    return {
        "total": len(cards),
        "unicos": len(by_matrix),
        "duplicados": len(cards) - len(by_matrix),
        "duplicados_seriales": {k: v for k, v in by_matrix.items() if len(v) > 1},
    }


def internal_repeats(cards: list[dict[str, Any]]) -> dict[str, dict[str, list[int]]]:
    """Cartones que tienen un mismo número repetido dentro de su matriz."""
    result: dict[str, dict[str, list[int]]] = {}
    for card in cards:
        nums = [n for row in card["matrix"] for n in row if n is not None]
        if len(nums) != len(set(nums)):
            result[card["serial"]] = {
                "nums": nums,
                "duplicates": sorted({n for n in nums if nums.count(n) > 1}),
            }
    return result
