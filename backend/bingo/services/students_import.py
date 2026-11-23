"""Reemplazo de la colección ``Estudiantes`` con el Excel de secretaría.

Plantilla: el Excel de alumnos del sistema académico (p. ej. ``Alumnos(2026-2027).xlsx``),
primera hoja, una fila por estudiante. Solo se usan las columnas ``Nombre``,
``Primer Apellido``, ``Segundo Apellido``, ``Curso`` y ``Num documento``; datos de
padres, direcciones, etc. **no** se guardan.

``Curso`` trae todo junto ("EDUCACIÓN GENERAL BÁSICA Básica Media 7 A",
"BACHILLERATO Ciencias 2 BGUC F1") y se separa en Curso, Especialidad, Nivel y
Paralelo, con el mismo formato que ya usa la colección.

Al reemplazar se conserva el ``correo`` que cada estudiante ya registró (por cédula)
y se guarda un respaldo de la colección anterior en ``backup_dir``.
"""

from __future__ import annotations

import io
import re
import threading
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from bson import json_util

from ..db import Collections, Doc
from ..errors import ApiError, Conflict
from .animators import course_of, student_course_query

# Columnas del Excel que se usan (se buscan por nombre, no por posición).
COLUMNS = ("Nombre", "Primer Apellido", "Segundo Apellido", "Curso", "Num documento")
# "EDUCACIÓN GENERAL BÁSICA Básica Media 7 A" / "BACHILLERATO Ciencias 2 BGUC F1"
COURSE_RE = re.compile(r"^(BACHILLERATO|EDUCACI[ÓO]N GENERAL B[ÁA]SICA)\s+(.+?)\s+(\d+)\s+(?:[A-Z]+\s+)?([A-Z]\d?)$")
# Mismo formato que ya usaba la colección Estudiantes.
COURSE_NAME = {"BACHILLERATO": "BACHILLERATO", "EGB": "Educación General Básica"}
CONFIRMATION = "REEMPLAZAR ESTUDIANTES"
MAX_ERRORS_SHOWN = 50
_LOCK = threading.Lock()


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _cedula(raw: Any) -> str:
    """Cédula como texto. Si Excel la guardó como número perdió el 0 inicial: se repone."""
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        digits = str(int(raw))
        return digits.zfill(10) if len(digits) == 9 else digits
    return _text(raw)


def parse_course(curso: str) -> dict[str, Any] | None:
    m = COURSE_RE.match(_text(curso))
    if not m:
        return None
    nivel_educativo, especialidad, nivel, paralelo = m.groups()
    key = "BACHILLERATO" if nivel_educativo == "BACHILLERATO" else "EGB"
    return {"Curso": COURSE_NAME[key], "Especialidad": especialidad, "Nivel": int(nivel), "Paralelo": paralelo}


def read_students(source: Path | bytes) -> tuple[list[Doc], list[str]]:
    """Devuelve ``(estudiantes, errores)``. Una fila con error no se importa.

    Lanza ``ApiError`` si el archivo no es un Excel ``.xlsx`` o le faltan columnas.
    """
    import openpyxl

    try:
        data = source if isinstance(source, bytes) else source.read_bytes()
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except (zipfile.BadZipFile, KeyError, ValueError, OSError) as exc:
        raise ApiError("El archivo no es un Excel .xlsx válido.") from exc
    rows = wb.worksheets[0].iter_rows(values_only=True)
    header = [_text(h) for h in next(rows, ())]
    missing = [c for c in COLUMNS if c not in header]
    if missing:
        raise ApiError(f"Al Excel le faltan las columnas: {', '.join(missing)}. Use la plantilla de secretaría.")
    idx = {c: header.index(c) for c in COLUMNS}  # primera aparición (hay columnas repetidas)

    students: list[Doc] = []
    errors: list[str] = []
    for n, row in enumerate(rows, start=2):
        if not any(row):
            continue
        value = {c: _text(row[i]) if i < len(row) else "" for c, i in idx.items()}
        course = parse_course(value["Curso"])
        cedula = _cedula(row[idx["Num documento"]] if idx["Num documento"] < len(row) else "")
        if course is None:
            errors.append(f"Fila {n}: curso no reconocido ({value['Curso'] or 'vacío'})")
            continue
        if not cedula or not value["Nombre"] or not value["Primer Apellido"]:
            errors.append(f"Fila {n}: falta cédula, nombre o primer apellido")
            continue
        students.append(
            {
                "Primer Apellido": value["Primer Apellido"].upper(),
                "Segundo Apellido": value["Segundo Apellido"].upper(),
                "Nombre": value["Nombre"].upper(),
                **course,
                "Num documento": cedula,
            }
        )
    wb.close()
    return students, errors


def repeated_cedulas(students: list[Doc]) -> list[str]:
    counts = Counter(s["Num documento"] for s in students)
    return sorted(c for c, k in counts.items() if k > 1)


class StudentImport:
    def __init__(self, cols: Collections, backup_dir: Path) -> None:
        self.cols = cols
        self.backup_dir = backup_dir

    def _analyze(self, data: bytes) -> tuple[list[Doc], dict[str, Any]]:
        students, errors = read_students(data)
        repeated = repeated_cedulas(students)
        new_ids = {s["Num documento"] for s in students}
        current = {d.get("Num documento"): d for d in self.cols.students.find({}, {"Num documento": 1, "correo": 1})}
        courses = {(s["Curso"], s["Especialidad"], s["Nivel"], s["Paralelo"]) for s in students}

        animators_without_students = []
        for a in self.cols.animators.find({"curso": {"$exists": True}}):
            course = course_of(a)
            if course is None:
                continue
            q = student_course_query(course)
            if not any(all(_matches(s, k, v) for k, v in q.items()) for s in students):
                animators_without_students.append(str(a.get("profesor") or a.get("tutor") or ""))

        summary = {
            "validos": len(students),
            "con_error": len(errors),
            "errores": errors[:MAX_ERRORS_SHOWN],
            "cedulas_repetidas": repeated[:MAX_ERRORS_SHOWN],
            "cursos": len(courses),
            "actuales": len(current),
            "nuevos": len(new_ids - current.keys()),
            "se_mantienen": len(new_ids & current.keys()),
            "se_eliminan": len(current.keys() - new_ids),
            "correos_conservados": sum(1 for c, d in current.items() if c in new_ids and d.get("correo")),
            "correos_perdidos": sum(1 for c, d in current.items() if c not in new_ids and d.get("correo")),
            "animadores_sin_alumnos": sorted(n for n in animators_without_students if n),
            "confirmacion": CONFIRMATION,
            "puede_importar": bool(students) and not repeated,
        }
        return students, summary

    def preview(self, data: bytes) -> dict[str, Any]:
        return self._analyze(data)[1]

    def _backup(self) -> Path:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        path = self.backup_dir / f"estudiantes_{datetime.now():%Y-%m-%d_%H%M%S}.json"
        docs = self.cols.students.find({})
        lines = (json_util.dumps(d, json_options=json_util.CANONICAL_JSON_OPTIONS) for d in docs)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def replace(self, data: bytes, confirmation: Any) -> dict[str, Any]:
        if str(confirmation or "").strip() != CONFIRMATION:
            raise ApiError(f"Para confirmar escriba exactamente: {CONFIRMATION}")
        if not _LOCK.acquire(blocking=False):
            raise Conflict("Ya hay una importación en curso. Espere a que termine.")
        try:
            students, summary = self._analyze(data)
            if summary["cedulas_repetidas"]:
                raise ApiError("Hay cédulas repetidas en el Excel; corríjalo antes de importar.")
            if not students:
                raise ApiError("El Excel no tiene ningún estudiante válido.")
            emails = {
                d["Num documento"]: d["correo"]
                for d in self.cols.students.find({"correo": {"$exists": True}}, {"Num documento": 1, "correo": 1})
                if d.get("Num documento") and d.get("correo")
            }
            for s in students:
                if s["Num documento"] in emails:
                    s["correo"] = emails[s["Num documento"]]
            backup = self._backup()
            deleted = self.cols.students.delete_many({}).deleted_count
            self.cols.students.insert_many(students)
        finally:
            _LOCK.release()
        return {**summary, "borrados": deleted, "insertados": len(students), "respaldo": backup.name}


def _matches(student: Doc, key: str, expected: Any) -> bool:
    """Evalúa un filtro de :func:`student_course_query` sobre un documento en memoria."""
    value = student.get(key)
    if isinstance(expected, dict):  # {"$in": [None, ""]}: especialidad vacía o ausente
        return value in expected["$in"]
    return bool(value == expected)
