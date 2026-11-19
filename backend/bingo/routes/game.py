"""Páginas web y endpoints de la partida (cartones, bolas, ganadores)."""

from __future__ import annotations

import logging
import time
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, render_template, request
from pymongo.errors import PyMongoError

from ..db import get_db
from ..domain.cards import internal_repeats, validar_duplicados
from ..errors import ApiError
from ..services.game import GameService
from ..services.pdf_extract import extraer_matrices_pdf
from ..utils import json_body, safe_int, stringify_keys

logger = logging.getLogger(__name__)
bp = Blueprint("game", __name__)
PDF_MAGIC = b"%PDF-"


def _game() -> GameService:
    return GameService(get_db(), current_app.config["SETTINGS"])


@bp.get("/")
def index() -> str:
    has_tables = get_db().tables.count_documents({}, limit=1) > 0
    return render_template("index.html", has_tables=has_tables)


@bp.get("/pages/masterTable.html")
def master_table() -> str:
    return render_template("pages/masterTable.html")


@bp.get("/test_mongo")
def test_mongo() -> Response:
    get_db().client.admin.command("ping")
    return jsonify({"success": True, "message": "Conexión exitosa a MongoDB."})


@bp.get("/health")
def health() -> tuple[Response, int]:
    """Estado del servicio para monitoreo: 200 si MongoDB responde, 503 si no."""
    try:
        get_db().client.admin.command("ping")
    except PyMongoError:
        logger.warning("Health check: MongoDB no responde", exc_info=True)
        return jsonify({"status": "error", "database": "unreachable"}), 503
    return jsonify({"status": "ok", "database": "ok"}), 200


@bp.get("/get_cards")
def get_cards() -> Response:
    return jsonify(_game().current_cards())


@bp.post("/mark")
def mark_number() -> Response:
    data = json_body()
    num = data.get("num")
    if num is None:
        raise ApiError("Falta el número a marcar.")
    _game().mark_number(safe_int(num, -1), bool(data.get("marcado", True)))
    return jsonify({"success": True, "ganadores": []})


@bp.get("/progress")
def progress() -> Response:
    return jsonify(_game().progress())


@bp.post("/winner_pdf")
def winner_pdf() -> Response:
    data = json_body()
    serial = data.get("serial")
    if not serial:
        raise ApiError("Faltan datos", payload={"error": "Faltan datos"})
    path = _game().winner_pdf(str(serial), data.get("matrix"), data.get("marks"))
    return jsonify({"success": True, "pdf_path": str(path), "message": f"PDF ganador guardado en: {path}"})


@bp.post("/reset")
def reset() -> Response:
    return jsonify(_game().rebuild_active_json())


@bp.post("/generate")
def generate_cards() -> Response:
    data = json_body()
    return jsonify(_game().generate_cards(safe_int(data.get("num_cards"), 1), bool(data.get("force", False))))


@bp.get("/tabla_ganadora")
def tabla_ganadora() -> tuple[Response, int]:
    ganadoras = list(get_db().winners.find({}, {"_id": 0}))
    if not ganadoras:
        return jsonify({"success": False, "message": "No hay tablas ganadoras registradas en la base de datos."}), 404
    return jsonify({"success": True, "count": len(ganadoras), "type": "ganadores", "cards": ganadoras}), 200


@bp.post("/upload")
def upload_pdf() -> Response:
    """Sube un PDF, extrae los cartones, los guarda en MongoDB y en un JSON."""
    file = request.files.get("pdf")
    if not file:
        raise ApiError("No se envió PDF", payload={"error": "No se envió PDF"})

    if file.stream.read(len(PDF_MAGIC)) != PDF_MAGIC:
        raise ApiError("El archivo no es un PDF", payload={"error": "El archivo no es un PDF"})
    file.stream.seek(0)

    settings = current_app.config["SETTINGS"]
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.time_ns()
    temp_pdf = settings.upload_dir / f"tmp_upload_{timestamp}.pdf"
    file.save(temp_pdf)
    try:
        cards = extraer_matrices_pdf(temp_pdf)
    except Exception as exc:
        logger.exception("No se pudo extraer cartones del PDF subido")
        raise ApiError("Error al procesar PDF", 422, {"error": "Error al procesar PDF"}) from exc
    finally:
        temp_pdf.unlink(missing_ok=True)

    game = _game()
    resultado: dict[str, Any] = game.import_cards(cards)
    json_path = settings.json_dir / f"bingo_cards_uploaded_{timestamp}.json"
    game.write_json(json_path, cards)

    validacion = stringify_keys(validar_duplicados(cards))
    insertados, actualizados = resultado["insertados"], resultado["actualizados"]
    message = f"✅ Cartones procesados y guardados en MongoDB ({insertados} nuevos, {actualizados} actualizados)"
    if resultado["conflictos"]:
        message += f" — {len(resultado['conflictos'])} tablas asignadas con matriz distinta NO se modificaron"
    return jsonify(
        {
            "success": True,
            "cards": cards,
            "json_path": str(json_path),
            "total_cartones": validacion["total"],
            "cartones_unicos": validacion["unicos"],
            "cartones_duplicados": validacion["duplicados"],
            "duplicados_seriales": validacion["duplicados_seriales"],
            "repetidos_internos": internal_repeats(cards),
            "insertados_en_mongo": insertados,
            "actualizados_en_mongo": actualizados,
            "conflictos_asignadas": resultado["conflictos"],
            "message": message,
        }
    )
