"""Punto de entrada del Sistema de Bingo.

Uso:
    python app.py              Reconstruye la partida desde MongoDB e inicia el servidor.
    python app.py 100          Genera 100 cartones en ``bingo_cards.json`` (sin tocar la BD).
    python app.py cartones.pdf Extrae los cartones del PDF a ``bingo_cards.json``.

La configuración se toma de variables de entorno (ver ``.env.example``).
Sin ``FLASK_DEBUG`` se sirve con waitress (servidor WSGI de producción).
"""

from __future__ import annotations

import json
import logging
import socket
import sys
from pathlib import Path
from typing import Any

from bingo import create_app
from bingo.db import get_db
from bingo.domain.cards import generate_unique_cards, validar_duplicados
from bingo.services.game import GameService
from bingo.services.pdf_extract import extraer_matrices_pdf

logger = logging.getLogger("bingo")

app = create_app()


def _print_summary(verb: str, cards: list[dict[str, Any]], output: Path) -> None:
    validacion = validar_duplicados(cards)
    print(f"Se {verb} {validacion['total']} cartones en {output}.")
    print(f"Cartones únicos: {validacion['unicos']}")
    print(f"Cartones duplicados: {validacion['duplicados']}")
    if validacion["duplicados_seriales"]:
        print("Cartones duplicados encontrados (seriales):")
        for serials in validacion["duplicados_seriales"].values():
            print(serials)
    else:
        print("No se encontraron duplicados.")


def _cli(arg: str) -> int:
    output = Path("bingo_cards.json")
    if arg.lower().endswith(".pdf"):
        cards = extraer_matrices_pdf(arg)
        verb = "extrajeron"
    elif arg.isdigit():
        cards = [dict(c) for c in generate_unique_cards(int(arg))]
        verb = "generaron"
    else:
        print("Argumento no reconocido. Usa un número de tablas o un PDF.")
        return 2
    output.write_text(json.dumps(cards, indent=2, ensure_ascii=False), encoding="utf-8")
    _print_summary(verb, cards, output)
    return 0


def _browser_urls(host: str, port: int) -> list[str]:
    """URLs que se pueden abrir en el navegador (``0.0.0.0`` solo indica "todas las interfaces")."""
    if host not in ("0.0.0.0", "::"):  # noqa: S104
        return [f"http://{host}:{port}/"]
    urls = [f"http://localhost:{port}/"]
    try:
        # No envía nada: solo pregunta al sistema qué IP local usaría para salir a la red.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            urls.append(f"http://{s.getsockname()[0]}:{port}/  (desde otras computadoras de la red)")
    except OSError:
        pass
    return urls


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        return _cli(argv[1])

    settings = app.config["SETTINGS"]
    with app.app_context():
        try:
            result = GameService(get_db(), settings).rebuild_active_json()
            logger.info(result["message"])
        except Exception:
            logger.exception("No se pudo reconstruir el JSON inicial desde la BD")
    if settings.debug:
        app.run(host=settings.host, port=settings.port, debug=True)
    else:
        # El servidor de desarrollo de Flask no es apto para producción.
        from waitress import serve

        for url in _browser_urls(settings.host, settings.port):
            logger.info("Abra el tablero en: %s", url)
        serve(app, host=settings.host, port=settings.port, threads=settings.threads)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
