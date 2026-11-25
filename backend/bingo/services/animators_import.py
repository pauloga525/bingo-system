"""Importación de la lista oficial de animadores (reporte del DECE en PDF o Excel).

Cada fila trae: docente, correo, nivel (EGB/Bachillerato), curso (1.º..10.º),
especialidad/subnivel y paralelo. La lista **reemplaza** la asignación actual de
animadores (solo el rol ``animador``; los demás roles de cada vendedor se conservan):

- quien está en la lista queda con ese correo (puede iniciar sesión) y ese curso;
- se reconoce a los animadores existentes por correo o, si no, por nombre, para
  conservar su cuenta, ventas e historial;
- los nuevos se crean con su cuenta en ``Users``;
- los animadores que **no** están en la lista pierden el acceso (se les quita el
  correo y el curso) pero no se borran.

Primero se muestra una vista previa; para aplicar hay que escribir la
confirmación. Antes de aplicar se guarda un respaldo en ``backups/``.
"""

from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import openpyxl
import pdfplumber
from bson import json_util

from ..db import Collections, Doc
from ..domain.roles import ANIMADOR_ROL, roles_de
from ..errors import ApiError
from .animators import COURSE_FIELDS, AnimatorService, animator_name, course_key, course_of, normalize_email

CONFIRMATION = "IMPORTAR ANIMADORES"
EGB = "Educación General Básica"
BACHILLERATO = "BACHILLERATO"
_MAX_ERRORS = 30


def norm(value: Any) -> str:
    """Mayúsculas sin tildes ni signos (para comparar nombres)."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^A-Z0-9 ]", " ", text.upper()).split())


@dataclass
class Fila:
    numero: int
    nombre: str
    correo: str
    curso: str
    nivel: int
    especialidad: str
    paralelo: str

    def course(self) -> dict[str, Any]:
        return {"curso": self.curso, "especialidad": self.especialidad, "nivel": self.nivel, "paralelo": self.paralelo}


def _texto(value: Any) -> str:
    return " ".join(str(value or "").split())


def _fila(numero: int, nombre: Any, correo: Any, nivel: Any, curso: Any, especialidad: Any, paralelo: Any) -> Fila:
    grado = re.search(r"\d+", _texto(curso))
    if not grado:
        raise ValueError(f"curso '{_texto(curso)}' sin número")
    return Fila(
        numero=numero,
        nombre=_texto(nombre).upper(),
        correo=normalize_email(correo),
        curso=BACHILLERATO if norm(nivel).startswith("BACH") else EGB,
        nivel=int(grado.group()),
        especialidad=_texto(especialidad),
        paralelo=_texto(paralelo).upper(),
    )


# ---------------------------------------------------------------- lectura PDF
_HEADERS = ("CORREO", "NIVEL", "CURSO", "ESPECIALIDAD", "PARALELO")


def _pdf_rows(data: bytes) -> list[list[str]]:
    """Filas ``[n, docente, correo, nivel, curso, especialidad, paralelo]`` del reporte del DECE.

    Usa la posición horizontal de cada palabra respecto a los encabezados de la tabla;
    los nombres o especialidades partidos en dos líneas se unen a su fila.
    """
    filas: list[list[str]] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            heads = {w["text"]: w for w in words if w["text"] in _HEADERS}
            if len(heads) < len(_HEADERS):
                continue
            corte = [heads[h]["x0"] - 8 for h in _HEADERS]  # inicio de cada columna
            corte[2] = heads["CURSO"]["x0"] - 20  # el número del curso va alineado a la derecha
            header_tops = {round(w["top"]) for w in words if w["text"] == "CORREO"}
            actual: list[str] | None = None
            top_fila = 0.0
            for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
                top = w["top"]
                if round(top) in header_tops or top < min(header_tops) - 2:
                    continue
                x = w["x0"]
                if x < heads["CORREO"]["x0"] - 200 and w["text"].isdigit() and x < 65:
                    actual = [w["text"], "", "", "", "", "", ""]
                    filas.append(actual)
                    top_fila = top
                    continue
                if actual is None or top - top_fila > 16 or x < 65:
                    continue  # títulos de sección, pie de página
                col = 1 + sum(1 for c in corte if x >= c)
                actual[col] = f"{actual[col]} {w['text']}".strip()
    return filas


_XLSX_COLS = ("DOCENTE", "NOMBRE", "CORREO", "NIVEL", "CURSO", "ESPECIALIDAD", "PARALELO")


def _xlsx_header(celdas: list[str]) -> dict[str, int] | None:
    """Posición de cada columna si la fila es el encabezado (tiene CORREO y PARALELO)."""
    claves = [norm(c) for c in celdas]
    if "CORREO" not in claves or not any(k.startswith("PARALELO") for k in claves):
        return None
    idx: dict[str, int] = {}
    for i, k in enumerate(claves):
        for col in _XLSX_COLS:
            if k.startswith(col):
                idx.setdefault(col, i)
    return idx


def _cell(celdas: list[str], idx: dict[str, int], col: str) -> str:
    i = idx.get(col)
    return celdas[i] if i is not None and i < len(celdas) else ""


def _xlsx_rows(data: bytes) -> list[list[str]]:
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    filas: list[list[str]] = []
    for ws in wb.worksheets:
        idx: dict[str, int] | None = None
        for raw in ws.iter_rows(values_only=True):
            celdas = [str(c or "").strip() for c in raw]
            if idx is None:
                idx = _xlsx_header(celdas)
            elif any(celdas):
                nombre = _cell(celdas, idx, "DOCENTE") or _cell(celdas, idx, "NOMBRE")
                resto = [_cell(celdas, idx, c) for c in ("CORREO", "NIVEL", "CURSO", "ESPECIALIDAD", "PARALELO")]
                filas.append([str(len(filas) + 1), nombre, *resto])
    return filas


def read_animators(data: bytes, filename: str = "") -> tuple[list[Fila], list[str]]:
    """Lee el PDF del DECE o un Excel con las mismas columnas. Devuelve filas válidas y errores."""
    es_pdf = data[:5] == b"%PDF-" or filename.lower().endswith(".pdf")
    try:
        crudas = _pdf_rows(data) if es_pdf else _xlsx_rows(data)
    except Exception as exc:
        raise ApiError("No se pudo leer el archivo. Use el PDF del DECE o un Excel (.xlsx).") from exc
    filas: list[Fila] = []
    errores: list[str] = []
    for r in crudas:
        try:
            fila = _fila(int(r[0]), *r[1:])
        except (ValueError, IndexError) as exc:
            errores.append(f"Fila {r[0]}: {exc}")
            continue
        if not fila.nombre or not fila.correo or not fila.paralelo:
            errores.append(f"Fila {fila.numero}: falta nombre, correo o paralelo")
            continue
        filas.append(fila)
    if not filas and not errores:
        raise ApiError("El archivo no tiene la tabla de docentes animadores (columnas CORREO ... PARALELO).")
    return filas, errores


# --------------------------------------------------------------- aplicación
class AnimatorImport:
    def __init__(self, cols: Collections, staff_domain: str, backup_dir: Path) -> None:
        self.cols = cols
        self.staff_domain = staff_domain
        self.backup_dir = backup_dir
        self.svc = AnimatorService(cols, staff_domain)

    def _student_courses(self) -> dict[tuple[str, str, int, str], dict[str, Any]]:
        return {course_key(c): c for c in self.svc.courses()}

    def _align_course(self, fila: Fila, cursos: dict[tuple[str, str, int, str], dict[str, Any]]) -> str | None:
        """Ajusta la especialidad al nombre que usa secretaría; devuelve un error si el curso no existe."""
        if course_key(fila.course()) in cursos:
            return None
        mismos = [k for k in cursos if (k[0], k[2], k[3]) == (fila.curso, fila.nivel, fila.paralelo)]
        if len(mismos) == 1:
            fila.especialidad = mismos[0][1]
            return None
        return f"Fila {fila.numero}: el curso {fila.nivel}.º {fila.paralelo} ({fila.especialidad}) no tiene estudiantes"

    def _validate(self, filas: list[Fila], errores: list[str], cursos: dict[Any, Any]) -> list[Fila]:
        """Filas con correo del personal, curso existente y sin repetir correo ni curso."""
        validas: list[Fila] = []
        vistos: set[Any] = set()
        for f in filas:
            error = None
            if f.correo.rsplit("@", 1)[-1] != self.staff_domain:
                error = f"Fila {f.numero}: el correo {f.correo} no es @{self.staff_domain}"
            else:
                error = self._align_course(f, cursos)
            if error is None and (f.correo in vistos or course_key(f.course()) in vistos):
                error = f"Fila {f.numero}: correo o curso repetido en el archivo"
            if error:
                errores.append(error)
                continue
            vistos.update({f.correo, course_key(f.course())})
            validas.append(f)
        return validas

    @staticmethod
    def _unchanged(doc: Doc, f: Fila) -> bool:
        actual = course_of(doc)
        return (
            normalize_email(doc.get("correo")) == f.correo
            and norm(animator_name(doc)) == norm(f.nombre)
            and actual is not None
            and course_key(actual) == course_key(f.course())
        )

    def plan(self, filas: list[Fila], errores: list[str]) -> dict[str, Any]:
        cursos = self._student_courses()
        leidas = len(filas) + len(errores)
        errores = list(errores)
        validas = self._validate(filas, errores, cursos)

        todos = list(self.cols.animators.find())
        animadores = [a for a in todos if ANIMADOR_ROL in roles_de(a)]
        # Por correo se busca entre todos: un vendedor de otro rol que está en la lista suma el rol animador.
        por_correo = {normalize_email(a.get("correo")): a for a in todos if a.get("correo")}
        por_nombre = {norm(animator_name(a)): a for a in animadores}

        acciones: list[tuple[Fila, Doc | None]] = []
        cuenta = {"nuevos": 0, "actualizados": 0, "sin_cambios": 0}
        usados: set[Any] = set()
        for f in validas:
            doc = por_correo.get(f.correo) or por_nombre.get(norm(f.nombre))
            if doc is not None and doc["_id"] in usados:
                doc = None
            if doc is None:
                cuenta["nuevos"] += 1
            else:
                usados.add(doc["_id"])
                cuenta["sin_cambios" if self._unchanged(doc, f) else "actualizados"] += 1
            acciones.append((f, doc))
        quitar = [a for a in animadores if a["_id"] not in usados and (a.get("correo") or course_of(a))]
        return {
            "acciones": acciones,
            "quitar": quitar,
            "resumen": {
                "filas": leidas,
                "validas": len(acciones),
                **cuenta,
                "pierden_acceso": len(quitar),
                "pierden_acceso_nombres": sorted(animator_name(a) for a in quitar)[:50],
                "errores": errores[:_MAX_ERRORS],
                "con_error": len(errores),
                "cursos_sin_animador": len(set(cursos) - {course_key(f.course()) for f, _ in acciones}),
                "confirmacion": CONFIRMATION,
                "puede_importar": bool(acciones),
            },
        }

    def preview(self, data: bytes, filename: str = "") -> dict[str, Any]:
        filas, errores = read_animators(data, filename)
        resumen: dict[str, Any] = self.plan(filas, errores)["resumen"]
        return resumen

    def _backup(self) -> str:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        nombre = f"animadores_{datetime.now():%Y-%m-%d_%H%M%S}.json"
        contenido = {"animadores": list(self.cols.animators.find()), "usuarios": list(self.cols.users.find())}
        (self.backup_dir / nombre).write_text(
            json_util.dumps(contenido, json_options=json_util.CANONICAL_JSON_OPTIONS), encoding="utf-8"
        )
        return nombre

    def _release(self, quitar: list[Doc]) -> None:
        """1) Libera los cursos (índice único) y quita el rol animador a quien no está en la lista.

        Si tiene otros roles conserva el acceso por ellos; si no, se le quita el correo.
        """
        for doc in self.cols.animators.find():
            if ANIMADOR_ROL in roles_de(doc) and course_of(doc):
                self.svc.set_course(doc, None)
        for doc in quitar:
            otros = [r for r in roles_de(doc) if r != ANIMADOR_ROL]
            if otros:
                self.svc.update(doc["_id"], {"roles": otros})
            else:
                self.cols.animators.update_one({"_id": doc["_id"]}, {"$unset": {"correo": ""}})

    def apply(self, data: bytes, confirmation: Any, filename: str = "") -> dict[str, Any]:
        if str(confirmation or "").strip() != CONFIRMATION:
            raise ApiError(f"Escriba exactamente {CONFIRMATION} para confirmar.")
        filas, errores = read_animators(data, filename)
        plan = self.plan(filas, errores)
        if not plan["acciones"]:
            raise ApiError("El archivo no tiene filas válidas para importar.")
        respaldo = self._backup()
        sin_curso = dict.fromkeys(COURSE_FIELDS)
        self._release(plan["quitar"])
        # 2) Se crea o actualiza cada animador de la lista con su correo y curso.
        for fila, doc in plan["acciones"]:
            if doc is None:
                self.svc.create({"nombre": fila.nombre, "correo": fila.correo, "rol": ANIMADOR_ROL, **fila.course()})
            else:
                roles = roles_de(doc)
                if ANIMADOR_ROL not in roles:
                    roles = [ANIMADOR_ROL, *roles]
                self.cols.animators.update_one({"_id": doc["_id"]}, {"$unset": {"correo": ""}})
                self.svc.update(
                    doc["_id"],
                    {"nombre": fila.nombre, "correo": fila.correo, "roles": roles, **sin_curso, **fila.course()},
                )
        resumen: dict[str, Any] = plan["resumen"]
        return {**resumen, "respaldo": respaldo}
