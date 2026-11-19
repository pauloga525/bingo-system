"""Extracción de matrices de bingo desde un PDF.

Primero intenta leer el layout generado por ``/generate`` (4 cartones por
hoja, coordenadas fijas). Si la página no parece de ese layout, cae a un
agrupamiento por coordenadas y, como último recurso, a lectura secuencial.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pdfplumber

from ..domain.cards import GRID, Matrix
from .pdf_render import CardLayout

SERIAL_PATTERN = re.compile(r"CARD\d{5}")
NUMBER_PATTERN = re.compile(r"^\d+$")
NUMBERS_PER_CARD = GRID * GRID - 1


def cluster_positions(positions: list[float], max_gap: float = 15) -> list[float]:
    """Agrupa coordenadas cercanas y devuelve el centro de cada grupo."""
    if not positions:
        return []
    ordered = sorted(positions)
    clusters = [[ordered[0]]]
    for p in ordered[1:]:
        if abs(p - clusters[-1][-1]) <= max_gap:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    return [sum(c) / len(c) for c in clusters]


def nearest_index(centers: list[float], value: float) -> int | None:
    if not centers:
        return None
    return min(range(len(centers)), key=lambda i: abs(centers[i] - value))


def _first_int(text: str) -> int | None:
    match = re.search(r"\d+", text)
    return int(match.group()) if match else None


def _read_cell(page: Any, bbox: tuple[float, float, float, float]) -> int | None:
    cropped = page.within_bbox(bbox)
    text = (cropped.extract_text() or "").strip()
    if text:
        return _first_int(text)
    words = cropped.extract_words()
    if not words:
        return None
    center_x = (bbox[0] + bbox[2]) / 2
    best = min(words, key=lambda w: abs(float(w.get("x0", 0)) - center_x))
    try:
        return int(str(best.get("text", "")).strip())
    except ValueError:
        return None


def _to_plumber_bbox(rect: tuple[float, float, float, float], page_height: float) -> tuple[float, float, float, float]:
    """``(left, bottom, w, h)`` de reportlab (origen abajo) -> bbox de pdfplumber (origen arriba)."""
    left, bottom, width, height = rect
    return left, page_height - (bottom + height), left + width, page_height - bottom


def _extract_structured(page: Any, page_number: int, page_text: str, layout: CardLayout) -> list[dict[str, Any]]:
    """Lee los 4 cartones de una hoja usando la misma geometría con la que se dibujan.

    La versión anterior usaba coordenadas de reportlab directamente en
    pdfplumber (ejes Y invertidos): leía números de otra zona y asignaba a los
    4 cartones de la hoja el mismo serial.
    """
    cards: list[dict[str, Any]] = []
    for card_row in range(2):
        for card_col in range(2):
            x, y = layout.origin(card_row, card_col)
            matrix: Matrix = [
                [
                    None
                    if (r, c) == (2, 2)
                    else _read_cell(page, _to_plumber_bbox(layout.cell_rect(x, y, r, c), layout.page_height))
                    for c in range(GRID)
                ]
                for r in range(GRID)
            ]
            header = page.within_bbox(_to_plumber_bbox(layout.header_rect(x, y), layout.page_height))
            match = SERIAL_PATTERN.search(header.extract_text() or "")
            if match is None and not any(any(v is not None for v in row) for row in matrix):
                continue  # posición vacía (última hoja incompleta)
            serial = match.group() if match else f"PAGE{page_number}_R{card_row}C{card_col}"
            cards.append({"serial": serial, "matrix": matrix})
    return cards


def _extract_sequential(page_number: int, page_text: str) -> list[dict[str, Any]]:
    """Toma los números del texto en orden y arma cartones de 24 números."""
    numbers = [int(n) for n in re.findall(r"\b\d+\b", page_text)]
    serials = SERIAL_PATTERN.findall(page_text)
    if serials:
        serial_num = int(serials[0].replace("CARD", ""))
        numbers = [n for n in numbers if n != serial_num]
    cards: list[dict[str, Any]] = []
    for i in range(len(numbers) // NUMBERS_PER_CARD):
        nums = iter(numbers[i * NUMBERS_PER_CARD : (i + 1) * NUMBERS_PER_CARD])
        matrix: Matrix = [[None if (r, c) == (2, 2) else next(nums, None) for c in range(GRID)] for r in range(GRID)]
        serial = serials[i] if i < len(serials) else f"PAGE{page_number}_SEQ{i + 1}"
        cards.append({"serial": serial, "matrix": matrix})
    return cards


def _grid_centers(values: list[float], tight_gap: float, loose_gap: float) -> list[float]:
    """Centros de columnas/filas; si con ``tight_gap`` salen menos de 5 se reintenta con ``loose_gap``."""
    centers = cluster_positions(values, max_gap=tight_gap)
    return centers if len(centers) >= GRID else cluster_positions(values, max_gap=loose_gap)


def _place_numbers(num_words: list[tuple[int, float, float]], x_centers: list[float], y_centers: list[float]) -> Matrix:
    """Ubica cada número en la celda más cercana (la primera ocurrencia gana; el centro queda libre)."""
    grid: Matrix = [[None] * GRID for _ in range(GRID)]
    for num, x, y in num_words:
        col_idx = nearest_index(x_centers, x)
        row_idx = nearest_index(y_centers, y)
        if col_idx is None or row_idx is None:
            continue
        if 0 <= row_idx < GRID and 0 <= col_idx < GRID and grid[row_idx][col_idx] is None:
            grid[row_idx][col_idx] = num
    grid[2][2] = None
    return grid


def _extract_clustered(page: Any, page_number: int, page_text: str) -> list[dict[str, Any]]:
    """Reconstruye una grilla 5x5 agrupando coordenadas de las palabras numéricas."""
    num_words: list[tuple[int, float, float]] = []  # (número, x, y)
    for w in page.extract_words():
        text = str(w.get("text", "")).strip()
        if NUMBER_PATTERN.match(text):
            num_words.append((int(text), float(w.get("x0", 0)), float(w.get("top", 0))))
    if not num_words:
        return []

    x_centers = _grid_centers([x for _, x, _ in num_words], tight_gap=18, loose_gap=30)
    y_centers = _grid_centers([y for _, _, y in num_words], tight_gap=12, loose_gap=20)
    if len(x_centers) < GRID or len(y_centers) < GRID:
        return _extract_sequential(page_number, page_text)

    grid = _place_numbers(num_words, x_centers, y_centers)
    serials = SERIAL_PATTERN.findall(page_text)
    return [{"serial": serials[0] if serials else f"PAGE{page_number}_AUTO", "matrix": grid}]


def extraer_matrices_pdf(pdf_path: str | Path) -> list[dict[str, Any]]:
    """Extrae ``[{"serial", "matrix"}, ...]`` de todas las páginas del PDF."""
    cards: list[dict[str, Any]] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""
            upper = page_text.upper()
            if "BINGO" in upper or "CARD" in upper:
                layout = CardLayout(page_width=float(page.width), page_height=float(page.height))
                cards.extend(_extract_structured(page, page_number, page_text, layout))
            else:
                cards.extend(_extract_clustered(page, page_number, page_text))
    return cards
