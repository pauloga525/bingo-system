from __future__ import annotations

import random

import pytest

from bingo.domain.cards import (
    apply_number,
    count_hits,
    empty_marks,
    generate_bingo_card,
    generate_unique_cards,
    has_line,
    internal_repeats,
    is_full_card,
    validar_duplicados,
)
from bingo.domain.pricing import calcular_total
from bingo.domain.serials import safe_filename_part, serial_number


@pytest.mark.parametrize(
    ("tablas", "total"),
    [(0, 0), (-1, 0), (1, 3), (2, 5), (3, 8), (4, 10), (5, 10), (6, 13), (7, 15), (10, 20), (11, 23)],
)
def test_calcular_total(tablas: int, total: int) -> None:
    assert calcular_total(tablas) == total


def test_generate_bingo_card_respects_columns_and_free_center() -> None:
    card = generate_bingo_card(random.Random(1))
    assert card[2][2] is None
    for col, (low, high) in enumerate([(1, 15), (16, 30), (31, 45), (46, 60), (61, 75)]):
        values = [card[r][col] for r in range(5) if (r, col) != (2, 2)]
        assert all(v is not None and low <= v <= high for v in values)
        assert len(set(values)) == len(values)


def test_generate_unique_cards_has_consecutive_serials_and_no_duplicates() -> None:
    cards = generate_unique_cards(50, random.Random(7))
    assert [c["serial"] for c in cards[:3]] == ["CARD00001", "CARD00002", "CARD00003"]
    assert validar_duplicados(cards)["duplicados"] == 0


def test_validar_duplicados_reports_serials() -> None:
    matrix = generate_bingo_card(random.Random(3))
    result = validar_duplicados([{"serial": "A", "matrix": matrix}, {"serial": "B", "matrix": matrix}])
    assert result["total"] == 2
    assert result["unicos"] == 1
    assert list(result["duplicados_seriales"].values()) == [["A", "B"]]


def test_full_card_is_the_win_rule() -> None:
    card = {"serial": "X", "matrix": generate_bingo_card(random.Random(5))}
    numbers = [n for row in card["matrix"] for n in row if n is not None]
    for n in numbers[:-1]:
        apply_number(card, n, True)  # type: ignore[arg-type]
    assert has_line(card["marks"])  # type: ignore[typeddict-item]
    assert card["won"] is False  # type: ignore[typeddict-item]
    apply_number(card, numbers[-1], True)  # type: ignore[arg-type]
    assert card["won"] is True  # type: ignore[typeddict-item]
    apply_number(card, numbers[0], False)  # type: ignore[arg-type]
    assert card["won"] is False  # type: ignore[typeddict-item]


def test_count_hits_counts_free_center() -> None:
    matrix = generate_bingo_card(random.Random(2))
    assert count_hits(matrix, [[False] * 5 for _ in range(5)]) == 1
    assert not is_full_card(matrix, empty_marks())


def test_internal_repeats() -> None:
    matrix = [[1, 1, 3, 4, 5]] + [[None] * 5 for _ in range(4)]
    assert internal_repeats([{"serial": "S", "matrix": matrix}])["S"]["duplicates"] == [1]


def test_serial_helpers() -> None:
    assert serial_number("CARD00012") == 12
    assert serial_number("") == 0
    assert safe_filename_part("../../etc/passwd") == "______etc_passwd"
