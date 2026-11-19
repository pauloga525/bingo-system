from __future__ import annotations

from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

from bingo.config import Settings
from bingo.services.pdf_extract import cluster_positions, extraer_matrices_pdf, nearest_index
from bingo.utils import safe_int, serialize_mongo_doc, try_object_id


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MONGO_URI", "mongodb://db:27017/")
    monkeypatch.setenv("FLASK_DEBUG", "true")
    monkeypatch.setenv("FLASK_PORT", "abc")
    monkeypatch.setenv("CORS_ORIGINS", "http://a.com, http://b.com")
    monkeypatch.setenv("BINGO_JSON_DIR", "otra")
    s = Settings.from_env()
    assert s.mongo_uri == "mongodb://db:27017/"
    assert s.debug is True
    assert s.port == 5000
    assert s.cors_origin_list == ["http://a.com", "http://b.com"]
    assert s.json_dir.name == "otra"
    assert Settings().cors_origin_list == "*"
    assert Settings().debug is False  # nunca debug por defecto (el debugger de Werkzeug permite ejecutar código)


def test_utils() -> None:
    assert safe_int("7") == 7
    assert safe_int("x", 3) == 3
    assert safe_int(None, 2) == 2
    assert try_object_id("no") is None
    oid = try_object_id("507f1f77bcf86cd799439011")
    assert serialize_mongo_doc({"a": [oid, {"b": oid}]}) == {
        "a": ["507f1f77bcf86cd799439011", {"b": "507f1f77bcf86cd799439011"}]
    }


def test_cluster_helpers() -> None:
    assert cluster_positions([]) == []
    assert cluster_positions([1, 2, 50, 52], max_gap=5) == [1.5, 51.0]
    assert nearest_index([], 3) is None
    assert nearest_index([0, 10, 20], 12) == 1


def test_fallback_extraction_for_foreign_layout(tmp_path: Path) -> None:
    """PDF sin el layout propio (sin "BINGO"/"CARD"): se reconstruye por coordenadas."""
    pdf = tmp_path / "otro.pdf"
    c = canvas.Canvas(str(pdf))
    n = 1
    for r in range(5):
        for col in range(5):
            if (r, col) != (2, 2):
                c.drawString(100 + col * 60, 700 - r * 40, str(n))
                n += 1
    c.save()
    [card] = extraer_matrices_pdf(pdf)
    assert card["serial"] == "PAGE1_AUTO"
    assert card["matrix"][0] == [1, 2, 3, 4, 5]
    assert card["matrix"][2][2] is None
