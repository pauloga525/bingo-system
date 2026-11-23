"""Reemplazo de estudiantes con el Excel de secretaría (solo administrador)."""

from __future__ import annotations

import io
from typing import Any

import openpyxl
import pytest
from bson import json_util
from flask.testing import FlaskClient

from bingo.config import Settings
from bingo.db import Collections
from bingo.services.students_import import CONFIRMATION, parse_course

from .conftest import Seed, login_as

PREVIEW = "/api/estudiantes/importar/vista-previa"
IMPORT = "/api/estudiantes/importar"
# Encabezado como el de la plantilla real (columnas extra y "Tipo documento" repetida).
HEADER = ["Curso Lectivo", "Alumno Id", "Nombre", "Primer Apellido", "Segundo Apellido", "Curso",
          "Tipo documento", "Num documento", "E-mail", "Nombre Padre", "Tipo documento"]  # fmt: skip
CIENCIAS_1A = "BACHILLERATO Ciencias 1 BGUC A"


def _row(nombre: str, ape1: str, ape2: str, curso: str, cedula: Any) -> list[Any]:
    return ["2026-2027", 1, nombre, ape1, ape2, curso, "Cédula", cedula, "x@correo.com", "PADRE", "Cédula"]


def _xlsx(rows: list[list[Any]], header: list[str] = HEADER) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(header)
    for r in rows:
        ws.append(r)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


EXCEL = _xlsx(
    [
        _row("ana maria", "pérez", "lópez", CIENCIAS_1A, "0101"),  # ya existía, con correo
        _row("luis", "mora", "", CIENCIAS_1A, "0102"),  # nuevo
        _row("rosa", "vega", "paz", "EDUCACIÓN GENERAL BÁSICA Básica Media 7 C", 103),  # cédula numérica
        _row("mal", "curso", "", "PRIMARIA 3 A", "0104"),  # curso no reconocido
        _row("", "sin", "nombre", CIENCIAS_1A, "0105"),  # sin nombre
        [None] * len(HEADER),  # fila vacía: se ignora
    ]
)


def _send(client: FlaskClient, url: str, data: bytes, **form: str) -> Any:
    return client.post(
        url, data={"excel": (io.BytesIO(data), "Alumnos.xlsx"), **form}, content_type="multipart/form-data"
    )


@pytest.fixture
def admin(client: FlaskClient, cols: Collections, seed: Seed) -> FlaskClient:
    cols.students.insert_many(
        [
            {
                "Nombre": "ANA",
                "Primer Apellido": "PEREZ",
                "Num documento": "0101",
                "correo": "ana.perez.est@uets.edu.ec",
            },
            {
                "Nombre": "OTRO",
                "Primer Apellido": "VIEJO",
                "Num documento": "0900",
                "correo": "otro.viejo.est@uets.edu.ec",
            },
            {"Nombre": "SIN", "Primer Apellido": "CORREO", "Num documento": "0901"},
        ]
    )
    login_as(client, "admin")
    return client


def test_parse_course() -> None:
    assert parse_course("EDUCACIÓN GENERAL BÁSICA Básica Media 7 A") == {
        "Curso": "Educación General Básica", "Especialidad": "Básica Media", "Nivel": 7, "Paralelo": "A"
    }  # fmt: skip
    assert parse_course("BACHILLERATO Ciencias 2 BGUC F1") == {
        "Curso": "BACHILLERATO", "Especialidad": "Ciencias", "Nivel": 2, "Paralelo": "F1"
    }  # fmt: skip
    assert parse_course("PRIMARIA 3 A") is None


def test_preview_reports_without_changing_anything(admin: FlaskClient, cols: Collections) -> None:
    resp = _send(admin, PREVIEW, EXCEL)
    assert resp.status_code == 200, resp.json
    r = resp.json
    assert (r["validos"], r["con_error"], r["cursos"]) == (3, 2, 2)
    assert r["errores"][0].startswith("Fila 5: curso no reconocido")
    assert (r["actuales"], r["nuevos"], r["se_mantienen"], r["se_eliminan"]) == (3, 2, 1, 2)
    assert (r["correos_conservados"], r["correos_perdidos"]) == (1, 1)
    # ANA tiene BACHILLERATO Ciencias 1° A (hay alumnos); BETO 1° B no tiene alumnos en el Excel.
    assert r["animadores_sin_alumnos"] == ["Nombre BETO"]
    assert r["puede_importar"] is True and r["confirmacion"] == CONFIRMATION
    assert cols.students.count_documents({}) == 3


def test_replace_keeps_registered_emails_and_backs_up(
    admin: FlaskClient, cols: Collections, settings: Settings
) -> None:
    resp = _send(admin, IMPORT, EXCEL, confirmacion=CONFIRMATION)
    assert resp.status_code == 200, resp.json
    assert (resp.json["insertados"], resp.json["borrados"]) == (3, 3)

    docs = {d["Num documento"]: d for d in cols.students.find({})}
    assert set(docs) == {"0101", "0102", "103"}
    ana = docs["0101"]
    assert (ana["Nombre"], ana["Primer Apellido"], ana["Segundo Apellido"]) == ("ANA MARIA", "PÉREZ", "LÓPEZ")
    assert (ana["Curso"], ana["Especialidad"], ana["Nivel"], ana["Paralelo"]) == ("BACHILLERATO", "Ciencias", 1, "A")
    assert ana["correo"] == "ana.perez.est@uets.edu.ec"  # su correo registrado se conserva
    assert "correo" not in docs["0102"]  # la columna E-mail del Excel no se usa
    assert set(ana) == {"_id", "Nombre", "Primer Apellido", "Segundo Apellido", "Curso", "Especialidad",
                        "Nivel", "Paralelo", "Num documento", "correo"}  # fmt: skip

    backup = settings.backup_dir / resp.json["respaldo"]
    old = [json_util.loads(x) for x in backup.read_text("utf-8").splitlines()]
    assert sorted(d["Num documento"] for d in old) == ["0101", "0900", "0901"]
    assert cols.animators.count_documents({}) == 2  # los animadores no se tocan


def test_imported_student_can_log_in_with_kept_email(admin: FlaskClient) -> None:
    _send(admin, IMPORT, EXCEL, confirmacion=CONFIRMATION)
    login_as(admin, "ana.perez.est@uets.edu.ec")
    assert admin.get("/api/auth/me").json["usuario"]["nombres"] == "ANA MARIA PÉREZ LÓPEZ"


def test_animator_sees_imported_students_of_course(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    login_as(client, "admin")
    _send(client, IMPORT, EXCEL, confirmacion=CONFIRMATION)
    login_as(client, "ana")
    cedulas = sorted(e["cedula"] for e in client.get("/api/mi-curso").json["estudiantes"])
    assert cedulas == ["0101", "0102"]


def test_repeated_cedula_blocks_import(admin: FlaskClient, cols: Collections) -> None:
    data = _xlsx([_row("a", "b", "", CIENCIAS_1A, "0101"), _row("c", "d", "", CIENCIAS_1A, "0101")])
    preview = _send(admin, PREVIEW, data).json
    assert preview["cedulas_repetidas"] == ["0101"] and preview["puede_importar"] is False
    assert _send(admin, IMPORT, data, confirmacion=CONFIRMATION).status_code == 400
    assert cols.students.count_documents({}) == 3


@pytest.mark.parametrize(
    ("data", "form"),
    [
        (EXCEL, {}),  # sin confirmación
        (EXCEL, {"confirmacion": "reemplazar"}),
        (b"esto no es un excel", {"confirmacion": CONFIRMATION}),
        (_xlsx([], header=["Nombre", "Curso"]), {"confirmacion": CONFIRMATION}),  # faltan columnas
        (_xlsx([_row("x", "y", "", "PRIMARIA 1 A", "1")]), {"confirmacion": CONFIRMATION}),  # ninguno válido
    ],
)
def test_invalid_imports_change_nothing(
    admin: FlaskClient, cols: Collections, data: bytes, form: dict[str, str]
) -> None:
    assert _send(admin, IMPORT, data, **form).status_code == 400
    assert cols.students.count_documents({}) == 3


def test_missing_columns_message(admin: FlaskClient) -> None:
    resp = _send(admin, PREVIEW, _xlsx([], header=["Nombre", "Curso"]))
    assert resp.status_code == 400
    assert "Primer Apellido" in resp.json["message"] and "Num documento" in resp.json["message"]


def test_requires_file(admin: FlaskClient) -> None:
    assert admin.post(PREVIEW, data={}, content_type="multipart/form-data").status_code == 400


def test_admin_only(client: FlaskClient, cols: Collections, seed: Seed) -> None:
    assert _send(client, PREVIEW, EXCEL).status_code == 403  # sesión de ANA
    assert _send(client, IMPORT, EXCEL, confirmacion=CONFIRMATION).status_code == 403


def test_numeric_cedula_recovers_leading_zero(admin: FlaskClient, cols: Collections) -> None:
    data = _xlsx([_row("a", "b", "", CIENCIAS_1A, 102030405), _row("c", "d", "", CIENCIAS_1A, 1712345678)])
    assert _send(admin, IMPORT, data, confirmacion=CONFIRMATION).status_code == 200
    assert sorted(d["Num documento"] for d in cols.students.find({})) == ["0102030405", "1712345678"]
