"""Sistema de Bingo UETS: fábrica de la aplicación Flask."""

from __future__ import annotations

import logging

from flask import Flask, Response
from flask_cors import CORS
from pymongo import MongoClient

from .auth import GoogleVerifier, init_auth
from .config import BASE_DIR, Settings
from .db import Doc, ensure_indexes, init_db
from .errors import register_error_handlers
from .routes import admin, auth, board, consulta, game, mi_curso, participants, tables, users


def create_app(
    settings: Settings | None = None,
    mongo_client: MongoClient[Doc] | None = None,
    google_verifier: GoogleVerifier | None = None,
) -> Flask:
    """Crea la app. ``mongo_client`` y ``google_verifier`` permiten inyectar dobles en los tests."""
    settings = settings or Settings.from_env()
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app = Flask(__name__, template_folder=str(BASE_DIR / "templates"))
    app.config["SETTINGS"] = settings
    app.config["MAX_CONTENT_LENGTH"] = settings.max_upload_mb * 1024 * 1024

    client = mongo_client or MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=5000)
    cols = init_db(app, client, settings.mongo_db)
    if settings.create_indexes:
        ensure_indexes(cols)

    CORS(app, resources={r"/api/*": {"origins": settings.cors_origin_list}})
    register_error_handlers(app)
    init_auth(app, settings, google_verifier)
    for module in (auth, consulta, admin, mi_curso, board, game, participants, tables, users):
        app.register_blueprint(module.bp)
    app.after_request(_security_headers)
    return app


def _security_headers(response: Response) -> Response:
    """Cabeceras básicas contra MIME sniffing, clickjacking y fuga del Referer."""
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response
