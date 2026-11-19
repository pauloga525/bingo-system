"""Generación de PDFs con reportlab.

El layout (4 cartones por hoja carta) debe coincidir con el que espera
:mod:`bingo.services.pdf_extract`; por eso las medidas viven en
:class:`CardLayout` y las comparten ambos módulos.
"""

from __future__ import annotations

import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from ..domain.cards import CENTER, GRID, Marks, Matrix

LETTERS = ("B", "I", "N", "G", "O")
TITLE = "BINGO UETS"
# Espacio entre la fila de letras B-I-N-G-O y la primera fila de números.
GRID_LABEL_SPACE = 15


@dataclass(frozen=True)
class CardLayout:
    """Geometría de una hoja con 2x2 cartones."""

    page_width: float = letter[0]
    page_height: float = letter[1]
    margin_x: float = 0.5 * inch
    margin_y: float = 0.5 * inch
    cards_per_page: int = 4

    @property
    def card_width(self) -> float:
        return (self.page_width - 2 * self.margin_x) / 2

    @property
    def card_height(self) -> float:
        return (self.page_height - 2 * self.margin_y) / 2

    def origin(self, row: int, col: int) -> tuple[float, float]:
        """Esquina inferior izquierda del cartón en la posición ``(row, col)``."""
        x = self.margin_x + col * self.card_width
        y = self.page_height - self.margin_y - (row + 1) * self.card_height
        return x, y

    def grid(self, x: float, y: float) -> tuple[float, float, float, float]:
        """``(grid_top, grid_left, cell_w, cell_h)`` de un cartón."""
        return (
            y + self.card_height - 55,
            x + 10,
            (self.card_width - 20) / 5,
            (self.card_height - 60) / 6,
        )

    def cell_rect(self, x: float, y: float, row: int, col: int) -> tuple[float, float, float, float]:
        """Celda ``(row, col)`` como ``(left, bottom, width, height)`` en coordenadas de reportlab."""
        grid_top, grid_left, cell_w, cell_h = self.grid(x, y)
        return grid_left + col * cell_w, grid_top - GRID_LABEL_SPACE - (row + 1) * cell_h, cell_w, cell_h

    def header_rect(self, x: float, y: float) -> tuple[float, float, float, float]:
        """Franja del título y el serial como ``(left, bottom, width, height)``."""
        return x, y + self.card_height - 45, self.card_width, 35


LAYOUT = CardLayout()


def render_cards_pdf(cards: Sequence[Mapping[str, Any]], layout: CardLayout = LAYOUT) -> bytes:
    """Dibuja los cartones (``serial`` + ``matrix``) y devuelve el PDF en bytes."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(layout.page_width, layout.page_height))
    for idx, card in enumerate(cards):
        matrix: Matrix = card.get("matrix") or [[None] * GRID for _ in range(GRID)]
        serial = str(card.get("serial", ""))
        page_pos = idx % layout.cards_per_page
        x, y = layout.origin(page_pos // 2, page_pos % 2)

        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(x + layout.card_width / 2, y + layout.card_height - 15, TITLE)
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(x + layout.card_width / 2, y + layout.card_height - 30, serial)

        grid_top, grid_left, cell_w, _ = layout.grid(x, y)
        c.setFont("Helvetica-Bold", 10)
        for i, letter_ in enumerate(LETTERS):
            c.drawCentredString(grid_left + i * cell_w + cell_w / 2, grid_top, letter_)

        c.setFont("Helvetica", 8)
        for r in range(GRID):
            for col in range(GRID):
                left, bottom, width, height = layout.cell_rect(x, y, r, col)
                c.rect(left, bottom, width, height)
                val = matrix[r][col]
                c.drawCentredString(left + width / 2, bottom + height / 2 - 3, str(val) if val is not None else " ")

        if page_pos == layout.cards_per_page - 1 or idx == len(cards) - 1:
            c.showPage()
    c.save()
    return buffer.getvalue()


def render_winner_pdf(path: Path, serial: str, matrix: Matrix, marks: Marks) -> None:
    """Comprobante de cartón ganador con los números marcados tachados en rojo."""
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(200, 750, f"Cartón ganador #{serial}")
    x0, y0, size = 100, 650, 40
    c.setFont("Helvetica-Bold", 12)
    for i, letter_ in enumerate(LETTERS):
        c.drawString(x0 + i * size + 10, y0 + 20, letter_)
    for r in range(GRID):
        for col in range(GRID):
            x = x0 + col * size
            y = y0 - r * size
            num = matrix[r][col]
            text = "FREE" if (r, col) == CENTER else (str(num) if num else "")
            c.rect(x, y, size, size)
            if marks[r][col]:
                c.setFillColorRGB(1, 0, 0)
                c.setFont("Helvetica-Bold", 12)
                c.drawString(x + 12, y + 12, text)
                c.setLineWidth(2)
                c.line(x + 5, y + size / 2, x + size - 5, y + size / 2)
                c.setLineWidth(1)
            else:
                c.setFillColorRGB(0, 0, 0)
                c.setFont("Helvetica", 10)
                c.drawString(x + 12, y + 12, text)
    c.save()
