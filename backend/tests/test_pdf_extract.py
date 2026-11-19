"""Rutas alternativas de lectura de PDF (páginas que no vienen de ``/generate``)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bingo.services.pdf_extract import _extract_clustered, _extract_sequential, _place_numbers, _read_cell

NUMBERS = list(range(1, 25))  # 24 números = un cartón sin el centro


@dataclass
class FakePage:
    """Lo mínimo de ``pdfplumber.Page`` que usan las funciones de extracción."""

    text: str = ""
    words: list[dict[str, Any]] = field(default_factory=list)

    def within_bbox(self, _bbox: tuple[float, float, float, float]) -> FakePage:
        return self

    def extract_text(self) -> str:
        return self.text

    def extract_words(self) -> list[dict[str, Any]]:
        return self.words


def _grid_words(spacing: float = 40) -> list[dict[str, Any]]:
    numbers = iter(NUMBERS)
    return [
        {"text": str(next(numbers)), "x0": c * spacing, "top": r * spacing}
        for r in range(5)
        for c in range(5)
        if (r, c) != (2, 2)
    ]


def test_sequential_builds_cards_and_ignores_serial_number() -> None:
    text = "CARD00099 99 " + " ".join(map(str, NUMBERS))
    [card] = _extract_sequential(1, text)
    assert card["serial"] == "CARD00099"
    assert card["matrix"][2][2] is None
    assert card["matrix"][0] == [1, 2, 3, 4, 5]


def test_sequential_without_serial_uses_page_name() -> None:
    [card] = _extract_sequential(3, " ".join(map(str, NUMBERS)))
    assert card["serial"] == "PAGE3_SEQ1"


def test_clustered_reconstructs_grid() -> None:
    [card] = _extract_clustered(FakePage(text="CARD00042", words=_grid_words()), 1, "CARD00042")
    assert card["serial"] == "CARD00042"
    assert card["matrix"][0] == [1, 2, 3, 4, 5]
    assert card["matrix"][2] == [11, 12, None, 13, 14]


def test_clustered_falls_back_to_sequential_and_handles_empty_page() -> None:
    few = [{"text": "1", "x0": 0, "top": 0}, {"text": "2", "x0": 0, "top": 0}]
    assert _extract_clustered(FakePage(words=few), 2, " ".join(map(str, NUMBERS)))[0]["serial"] == "PAGE2_SEQ1"
    assert _extract_clustered(FakePage(words=[{"text": "BINGO"}]), 2, "") == []


def test_place_numbers_keeps_first_occurrence_and_frees_center() -> None:
    grid = _place_numbers([(5, 0, 0), (9, 0, 0), (13, 2, 2)], [0, 1, 2, 3, 4], [0, 1, 2, 3, 4])
    assert grid[0][0] == 5
    assert grid[2][2] is None
    assert _place_numbers([(1, 0, 0)], [], [])[0][0] is None


def test_read_cell_from_text_or_nearest_word() -> None:
    bbox = (0.0, 0.0, 10.0, 10.0)
    assert _read_cell(FakePage(text=" 17 "), bbox) == 17
    assert _read_cell(FakePage(text="sin números"), bbox) is None
    assert _read_cell(FakePage(), bbox) is None
    words = [{"text": "3", "x0": 0}, {"text": "8", "x0": 5}]
    assert _read_cell(FakePage(words=words), bbox) == 8
    assert _read_cell(FakePage(words=[{"text": "x", "x0": 5}]), bbox) is None
