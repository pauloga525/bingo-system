"""Lista oficial de animadores (DECE), alta por correo, primer ingreso, desactivar e intentos rechazados."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import openpyxl
import pytest
from flask.testing import FlaskClient
from reportlab.pdfgen import canvas

from bingo.config import Settings
from bingo.db import Collections
from bingo.services.animators_import import read_animators

from .conftest import Seed, login_as, logout

HEADER = ["N.º", "DOCENTE ANIMADOR", "CORREO", "NIVEL", "CURSO", "ESPECIALIDAD / SUBNIVEL", "PARALELO"]


def _xlsx(rows: list[list[Any]]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(["Docentes animadores de curso"])
    ws.append(HEADER)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _pdf(rows: list[list[str]]) -> bytes:
    """PDF con el mismo formato de columnas que el reporte del DECE."""
    xs = [47, 72, 264, 426, 548, 588, 772]
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(842, 595))
    y = 595 - 40
    c.drawString(56, y + 20, "Educación General Básica")
    for x, h in zip(
        xs, ["N.º", "DOCENTE ANIMADOR", "CORREO", "NIVEL", "CURSO", "ESPECIALIDAD", "PARALELO"], strict=True
    ):
        c.drawString(x if h != "CURSO" else 541, y, h)
    for r in rows:
        y -= 18
        for x, v in zip(xs, r, strict=True):
            c.drawString(x, y, v)
    c.drawString(56, 30, "Sistema DECE · Docentes animadores de curso")
    c.save()
    return buf.getvalue()


@pytest.fixture
def admin(client: FlaskClient, seed: Seed, cols: Collections) -> FlaskClient:
    # Cursos con alumnos: 1.° A y 1.° B de Ciencias (los de ANA y BETO) y 2.° C.
    for par, nivel in (("A", 1), ("B", 1), ("C", 2)):
        cols.students.insert_one(
            {
                "Num documento": f"09{par}{nivel}",
                "Curso": "BACHILLERATO",
                "Especialidad": "Ciencias",
                "Nivel": nivel,
                "Paralelo": par,
            }
        )
    login_as(client, "admin")
    return client


def _subir(client: FlaskClient, url: str, data: bytes, nombre: str, **form: str) -> Any:
    return client.post(url, data={"archivo": (io.BytesIO(data), nombre), **form}, content_type="multipart/form-data")


LISTA = [
    [1, "Nombre ANA", "ana@uets.edu.ec", "Bachillerato", "1.º", "Ciencias", "A"],
    [2, "NUEVA PROFE", "nueva@uets.edu.ec", "Bachillerato", "1.º", "Ciencias", "B"],
    [3, "OTRA PERSONA", "otra@gmail.com", "Bachillerato", "2.º", "Ciencias", "C"],
    [4, "SIN CURSO", "sin@uets.edu.ec", "Bachillerato", "3.º", "Ciencias", "Z"],
    [5, "SIN NUMERO", "x@uets.edu.ec", "Bachillerato", "", "Ciencias", "C"],
]


def test_import_preview_and_apply(admin: FlaskClient, cols: Collections, settings: Settings) -> None:
    data = _xlsx(LISTA)
    vista = _subir(admin, "/api/animadores/importar/vista-previa", data, "lista.xlsx").json
    assert (vista["filas"], vista["validas"], vista["nuevos"], vista["actualizados"]) == (5, 2, 1, 0)
    assert vista["sin_cambios"] == 1  # ANA ya tiene ese correo y curso
    assert vista["pierden_acceso"] == 1 and vista["pierden_acceso_nombres"] == ["Nombre BETO"]
    assert vista["con_error"] == 3 and vista["cursos_sin_animador"] == 1
    assert cols.animators.count_documents({"correo": "nueva@uets.edu.ec"}) == 0  # no guarda nada

    assert _subir(admin, "/api/animadores/importar", data, "lista.xlsx", confirmacion="no").status_code == 400
    res = _subir(admin, "/api/animadores/importar", data, "lista.xlsx", confirmacion="IMPORTAR ANIMADORES").json
    assert res["validas"] == 2 and (settings.backup_dir / res["respaldo"]).exists()
    nueva = cols.animators.find_one({"correo": "nueva@uets.edu.ec"})
    assert nueva is not None and (nueva["nivel"], nueva["paralelo"]) == (1, "B")
    beto = cols.animators.find_one({"profesor": "Nombre BETO"})
    assert beto is not None and "correo" not in beto and "curso" not in beto
    # BETO ya no entra; su intento queda registrado para el administrador.
    logout(admin)
    assert admin.post("/api/auth/google", json={"credential": "beto@uets.edu.ec"}).status_code == 403
    login_as(admin, "admin")
    intentos = admin.get("/api/accesos-rechazados").json["intentos"]
    assert [i["correo"] for i in intentos] == ["beto@uets.edu.ec"] and intentos[0]["intentos"] == 1
    # Volver a importar la misma lista no cambia nada.
    otra = _subir(admin, "/api/animadores/importar/vista-previa", data, "lista.xlsx").json
    assert (otra["nuevos"], otra["actualizados"], otra["sin_cambios"], otra["pierden_acceso"]) == (0, 0, 2, 0)


def test_import_reads_dece_pdf_format() -> None:
    filas, errores = read_animators(
        _pdf(
            [
                ["1", "QUITO QUITO DIANA", "dianaqq@uets.edu.ec", "EGB", "1.º", "Preparatoria", "C"],
                ["2", "PAUTA LOPEZ EDGAR", "edgarpl@uets.edu.ec", "Bachillerato", "10.º", "Ciencias", "A1"],
            ]
        ),
        "dece.pdf",
    )
    assert errores == []
    assert [(f.nombre, f.curso, f.nivel, f.especialidad, f.paralelo) for f in filas] == [
        ("QUITO QUITO DIANA", "Educación General Básica", 1, "Preparatoria", "C"),
        ("PAUTA LOPEZ EDGAR", "BACHILLERATO", 10, "Ciencias", "A1"),
    ]


def test_import_rejects_unreadable_files(admin: FlaskClient) -> None:
    assert (
        admin.post("/api/animadores/importar/vista-previa", data={}, content_type="multipart/form-data").status_code
        == 400
    )
    assert _subir(admin, "/api/animadores/importar/vista-previa", b"no es excel", "x.xlsx").status_code == 400
    vacio = _subir(admin, "/api/animadores/importar/vista-previa", _xlsx([]), "x.xlsx")
    assert vacio.status_code == 400 and "tabla de docentes" in vacio.json["message"]


def test_batch_by_email_onboarding_and_deactivate(admin: FlaskClient, cols: Collections) -> None:
    resp = admin.post(
        "/api/animadores/lote",
        json={
            "rol": "financiero",
            "correos": "mishellns@uets.edu.ec, veronicam@uets.edu.ec\nana@uets.edu.ec x@gmail.com",
        },
    )
    assert resp.status_code == 201
    assert resp.json["creados"] == ["mishellns@uets.edu.ec", "veronicam@uets.edu.ec"]
    assert resp.json["existentes"] == ["ana@uets.edu.ec"] and resp.json["invalidos"] == ["x@gmail.com"]
    assert admin.post("/api/animadores/lote", json={"correos": " "}).status_code == 400
    lista = {a["correo"]: a for a in admin.get("/api/animadores").json["animadores"]}
    v = lista["mishellns@uets.edu.ec"]
    assert (v["rol"], v["estado"], v["nombre_pendiente"]) == ("financiero", "pendiente", True)

    # Primer ingreso: el panel pide confirmar el nombre.
    login_as(admin, "mishellns@uets.edu.ec")
    perfil = admin.get("/api/auth/me").json["usuario"]
    assert perfil["onboarding_pendiente"] is True and perfil["cargo"] == "financiero"
    assert admin.post("/api/auth/onboarding", json={"nombre": " "}).status_code == 400
    ok = admin.post("/api/auth/onboarding", json={"nombre": "Mishell Narváez"}).json["usuario"]
    assert ok["onboarding_pendiente"] is False and ok["nombres"] == "MISHELL NARVÁEZ"

    login_as(admin, "admin")
    assert admin.post("/api/auth/onboarding", json={"nombre": "x"}).status_code == 403  # el admin no
    v = next(a for a in admin.get("/api/animadores").json["animadores"] if a["correo"] == "mishellns@uets.edu.ec")
    assert v["estado"] == "activo" and v["primer_ingreso"] and v["ultimo_ingreso"] and not v["nombre_pendiente"]

    # Desactivar corta el acceso sin borrar; reactivar lo devuelve.
    assert admin.put(f"/api/animadores/{v['_id']}", json={"activo": False}).json["animador"]["estado"] == "sin_acceso"
    logout(admin)
    assert admin.post("/api/auth/google", json={"credential": "mishellns@uets.edu.ec"}).status_code == 403
    login_as(admin, "admin")
    assert admin.put(f"/api/animadores/{v['_id']}", json={"activo": True}).json["animador"]["estado"] == "activo"
    login_as(admin, "mishellns@uets.edu.ec")


def test_rejected_attempts_list_dismiss_and_enable(admin: FlaskClient, cols: Collections) -> None:
    logout(admin)
    for correo in ("intruso@uets.edu.ec", "intruso@uets.edu.ec", "nadie.x.est@uets.edu.ec"):
        admin.post("/api/auth/google", json={"credential": correo})
    login_as(admin, "admin")
    intentos = admin.get("/api/accesos-rechazados").json["intentos"]
    # Solo el personal (los estudiantes van al registro por cédula).
    assert [(i["correo"], i["intentos"]) for i in intentos] == [("intruso@uets.edu.ec", 2)]
    # Al darle acceso desaparece de la lista.
    admin.post("/api/animadores", json={"nombre": "INTRUSO", "correo": "intruso@uets.edu.ec", "rol": "parroquia"})
    assert admin.get("/api/accesos-rechazados").json["intentos"] == []
    cols.access_log.insert_one({"correo": "otro@uets.edu.ec", "intentos": 1})
    assert admin.delete("/api/accesos-rechazados?correo=otro@uets.edu.ec").status_code == 200
    assert cols.access_log.count_documents({}) == 0


def test_import_ignores_other_roles_and_reports_conflicts(
    admin: FlaskClient, cols: Collections, tmp_path: Path
) -> None:
    admin.post("/api/animadores", json={"nombre": "SECRE", "correo": "nueva@uets.edu.ec", "rol": "secretaria"})
    vista = _subir(admin, "/api/animadores/importar/vista-previa", _xlsx(LISTA[:2]), "l.xlsx").json
    assert any("otro rol" in e for e in vista["errores"]) and vista["validas"] == 1
    sin_validas = _xlsx([LISTA[2]])
    resp = _subir(admin, "/api/animadores/importar", sin_validas, "l.xlsx", confirmacion="IMPORTAR ANIMADORES")
    assert resp.status_code == 400 and "filas válidas" in resp.json["message"]
