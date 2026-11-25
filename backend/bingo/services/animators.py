"""CRUD de animadores (colección ``Animadores``) sincronizado con su cuenta en ``Users``.

``Animadores`` guarda los datos del curso y el correo con el que el animador
inicia sesión con Google. ``Users`` es la cuenta operativa: de ahí salen las
tablas reservadas, los contadores y el ``registrado_por`` de los participantes,
por eso cada animador queda enlazado a su usuario mediante ``usuario_id``.

Los documentos históricos guardan el nombre en ``profesor`` o en ``tutor``; se
respeta el campo que ya exista.

Cada animador tiene como máximo **un curso** (curso + especialidad + nivel +
paralelo) y cada curso tiene como máximo **un animador**. Un animador puede
quedar sin curso (campos ausentes) hasta que se le asigne uno. El curso se
copia también en su cuenta de ``Users`` (lo usan los reportes y el perfil).

Además de animadores, la colección guarda a los demás vendedores (secretaría,
financiero, parroquia, oratorio; ver ``domain/roles.py``) en el campo ``rol``.
Esos roles no tienen curso y solo venden a externos. Sin ``rol`` = animador.
"""

from __future__ import annotations

import re
from typing import Any

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from ..db import Collections, Doc
from ..domain.roles import ANIMADOR_ROL, ETIQUETAS, clean_rol, rol_de
from ..errors import ApiError, Conflict, NotFound
from ..utils import require_object_id, safe_int, set_or_unset

ANIMADOR = 1
COURSE_FIELDS = ("curso", "especialidad", "nivel", "paralelo")
Course = dict[str, Any]


def _text(raw: Any) -> str:
    return " ".join(str(raw or "").split())


def clean_name(raw: Any) -> str:
    value = _text(raw).upper()
    if not value:
        raise ApiError("El campo 'nombre' es obligatorio.")
    return value


def clean_course(data: dict[str, Any]) -> Course | None:
    """Curso normalizado o ``None`` si todos sus campos vienen vacíos (sin curso).

    ``curso``, ``nivel`` y ``paralelo`` son obligatorios; ``especialidad`` puede ir vacía.
    """
    curso, especialidad, paralelo = (_text(data.get(k)) for k in ("curso", "especialidad", "paralelo"))
    raw_nivel = data.get("nivel")
    if not (curso or especialidad or paralelo or _text(raw_nivel)):
        return None
    nivel = safe_int(raw_nivel, 0)
    if not curso or not paralelo:
        raise ApiError("Para asignar un curso indique curso, nivel y paralelo.")
    if nivel <= 0:
        raise ApiError("El nivel debe ser un número mayor a 0.")
    return {"curso": curso, "especialidad": especialidad, "nivel": nivel, "paralelo": paralelo}


def course_of(doc: Doc | None) -> Course | None:
    """Curso guardado en un animador, o ``None`` si no tiene."""
    if not doc or not doc.get("curso") or not doc.get("paralelo"):
        return None
    return {
        "curso": doc["curso"],
        "especialidad": doc.get("especialidad") or "",
        "nivel": doc.get("nivel"),
        "paralelo": doc["paralelo"],
    }


def course_key(course: Course) -> tuple[str, str, int, str]:
    return (str(course["curso"]), str(course["especialidad"] or ""), safe_int(course["nivel"]), str(course["paralelo"]))


def course_label(course: Course) -> str:
    parts = (course.get("curso"), course.get("especialidad"), f"{course.get('nivel')}°", course.get("paralelo"))
    return " · ".join(str(p) for p in parts if p)


def _empty_or_missing(value: Any) -> Any:
    return value if value else {"$in": [None, ""]}


def animator_course_query(course: Course) -> dict[str, Any]:
    """Filtro de ``Animadores`` para un curso exacto (``especialidad`` vacía o ausente es lo mismo)."""
    return {
        "curso": course["curso"],
        "especialidad": _empty_or_missing(course["especialidad"]),
        "nivel": course["nivel"],
        "paralelo": course["paralelo"],
    }


def student_course_query(course: Course) -> dict[str, Any]:
    """Filtro de ``Estudiantes`` (campos históricos con mayúscula) para un curso."""
    return {
        "Curso": course["curso"],
        "Especialidad": _empty_or_missing(course["especialidad"]),
        "Nivel": course["nivel"],
        "Paralelo": course["paralelo"],
    }


def _reservation(user: Doc | None) -> dict[str, Any] | None:
    total = safe_int((user or {}).get("totalTables"), 0)
    if not user or total <= 0:
        return None
    return {
        "total": total,
        "usadas": safe_int(user.get("usedTables"), 0),
        "desde": user.get("fromSerial"),
        "hasta": user.get("toSerial"),
    }


def animator_name(doc: Doc) -> str:
    return str(doc.get("profesor") or doc.get("tutor") or "").strip()


def normalize_email(value: Any) -> str:
    return str(value or "").strip().lower()


def validate_domain_email(value: Any, domain: str | tuple[str, ...], required: bool = False) -> str | None:
    """Devuelve el correo en minúsculas, ``None`` si viene vacío, o lanza ``ApiError``."""
    domains = (domain,) if isinstance(domain, str) else domain
    email = normalize_email(value)
    if not email:
        if required:
            raise ApiError("El correo es obligatorio.")
        return None
    if not re.fullmatch(r"[^@\s]+@[^@\s]+", email) or email.rsplit("@", 1)[1] not in domains:
        raise ApiError(f"El correo debe pertenecer al dominio {' o '.join('@' + d for d in domains)}.")
    return email


class AnimatorService:
    def __init__(self, cols: Collections, staff_domain: str) -> None:
        self.cols = cols
        self.staff_domain = staff_domain

    # ------------------------------------------------------------- lectura
    def get(self, animator_id: Any) -> Doc:
        doc = self.cols.animators.find_one({"_id": require_object_id(animator_id, "ID de animador inválido.")})
        if not doc:
            raise NotFound("Animador no encontrado.")
        return doc

    def by_email(self, email: str) -> Doc | None:
        return self.cols.animators.find_one({"correo": normalize_email(email)})

    def list_all(self, search: str = "") -> list[dict[str, Any]]:
        query: dict[str, Any] = {}
        if search:
            pattern = {"$regex": re.escape(search), "$options": "i"}
            query = {
                "$or": [
                    {"profesor": pattern},
                    {"tutor": pattern},
                    {"correo": pattern},
                    {"rol": pattern},
                    {"curso": pattern},
                    {"especialidad": pattern},
                    {"paralelo": pattern},
                ]
            }
        docs = list(self.cols.animators.find(query))
        docs.sort(key=lambda d: (course_of(d) is None, course_key(course_of(d) or dict.fromkeys(COURSE_FIELDS, ""))))
        return [self.serialize(d) for d in docs]

    def serialize(self, doc: Doc) -> dict[str, Any]:
        user = self.linked_user(doc)
        course = course_of(doc)
        rol = rol_de(doc)
        return {
            "_id": str(doc["_id"]),
            "nombre": animator_name(doc),
            "rol": rol,
            "rol_nombre": ETIQUETAS[rol],
            **(course or dict.fromkeys(COURSE_FIELDS, "")),
            "curso_asignado": course is not None,
            "correo": doc.get("correo", ""),
            "usuario_id": str(user["_id"]) if user else None,
            "usuario": user.get("usuario") if user else None,
            # Rango de tablas reservado a su cuenta (None si aún no tiene).
            "reserva": _reservation(user),
        }

    def linked_user(self, doc: Doc) -> Doc | None:
        """Cuenta de ``Users`` del animador. Enlaza por nombre los documentos antiguos sin ``usuario_id``."""
        if doc.get("usuario_id"):
            user = self.cols.users.find_one({"_id": doc["usuario_id"]})
            if user:
                return user
        name = animator_name(doc)
        user = self.cols.users.find_one({"nombres_completos": name}) if name else None
        if user:
            self.cols.animators.update_one({"_id": doc["_id"]}, {"$set": {"usuario_id": user["_id"]}})
        return user

    def holder_of(self, course: Course, exclude: ObjectId | None = None) -> Doc | None:
        """Animador que tiene asignado ``course`` (sin contar a ``exclude``)."""
        query = animator_course_query(course)
        if exclude is not None:
            query["_id"] = {"$ne": exclude}
        return self.cols.animators.find_one(query)

    def courses(self) -> list[dict[str, Any]]:
        """Cursos existentes en ``Estudiantes`` (y los que tenga algún animador), con alumnos y animador."""
        found: dict[tuple[str, str, int, str], dict[str, Any]] = {}
        grouped = self.cols.students.aggregate(
            [
                {
                    "$group": {
                        "_id": {
                            "curso": "$Curso",
                            "especialidad": "$Especialidad",
                            "nivel": "$Nivel",
                            "paralelo": "$Paralelo",
                        },
                        "n": {"$sum": 1},
                    }
                }
            ]
        )
        for row in grouped:
            try:
                course = clean_course(row["_id"])
            except ApiError:
                continue  # alumnos con curso incompleto
            if course is None:
                continue
            entry = found.setdefault(
                course_key(course), {**course, "estudiantes": 0, "animador": None, "animador_id": None}
            )
            entry["estudiantes"] += row["n"]
        for doc in self.cols.animators.find({"curso": {"$exists": True}}):
            course = course_of(doc)
            if course is None:
                continue
            entry = found.setdefault(course_key(course), {**course, "estudiantes": 0})
            entry.update({"animador": animator_name(doc), "animador_id": str(doc["_id"])})
        return [found[k] for k in sorted(found)]

    # ---------------------------------------------------------- escritura
    def _clean(self, data: dict[str, Any], partial: bool, current_rol: str = ANIMADOR_ROL) -> dict[str, Any]:
        """Campos a guardar. El curso va como un todo: todos sus campos en ``None`` = sin curso.

        Solo el rol ``animador`` tiene curso: con otro rol el curso se quita.
        """
        fields: dict[str, Any] = {}
        if "nombre" in data or not partial:
            fields["nombre"] = clean_name(data.get("nombre"))
        if "correo" in data:
            fields["correo"] = validate_domain_email(data.get("correo"), self.staff_domain)
        if "rol" in data or not partial:
            fields["rol"] = clean_rol(data.get("rol"))
        rol = fields.get("rol", current_rol)
        if rol != ANIMADOR_ROL:
            if clean_course(data) is not None and any(k in data for k in COURSE_FIELDS):
                raise ApiError(f"Solo los animadores tienen curso; el rol {ETIQUETAS[rol]} vende solo a externos.")
            fields.update(dict.fromkeys(COURSE_FIELDS))
        elif not partial or any(k in data for k in COURSE_FIELDS):
            fields.update(clean_course(data) or dict.fromkeys(COURSE_FIELDS))
        return fields

    def _ensure_email_free(self, email: str | None, exclude: ObjectId | None = None) -> None:
        if not email:
            return
        query: dict[str, Any] = {"correo": email}
        if exclude is not None:
            query["_id"] = {"$ne": exclude}
        if self.cols.animators.find_one(query, {"_id": 1}):
            raise Conflict(f"El correo {email} ya está asignado a otro animador.")

    def _claim_course(self, fields: dict[str, Any], exclude: ObjectId | None, reassign: bool) -> None:
        """Verifica que el curso esté libre; con ``reassign`` se lo quita a su animador actual."""
        course = course_of(fields)
        holder = self.holder_of(course, exclude) if course else None
        if course is None or holder is None:
            return
        if not reassign:
            name = animator_name(holder) or "otro animador"
            raise Conflict(
                f"El curso {course_label(course)} ya está asignado a {name}.",
                curso_ocupado=True,
                animador_actual=name,
            )
        self.set_course(holder, None)

    def set_course(self, doc: Doc, course: Course | None) -> None:
        """Asigna (o quita, con ``None``) el curso en el animador y en su cuenta de ``Users``."""
        values = course or dict.fromkeys(COURSE_FIELDS)
        self.cols.animators.update_one({"_id": doc["_id"]}, set_or_unset(values))
        user = self.linked_user(doc)
        if user is not None:
            self.cols.users.update_one({"_id": user["_id"]}, set_or_unset(values))

    def _unique_username(self, nombre: str) -> str:
        base = "".join(p[0] for p in nombre.split()).upper() or "ANIM"
        usuario, n = base, 1
        while self.cols.users.find_one({"usuario": usuario}, {"_id": 1}):
            n += 1
            usuario = f"{base}{n}"
        return usuario

    def _create_user(self, nombre: str, course: Course | None, rol: str = ANIMADOR_ROL) -> ObjectId:
        """Crea la cuenta operativa (``Users``, tipo animador, sin contraseña)."""
        user_id: ObjectId = self.cols.users.insert_one(
            {
                "usuario": self._unique_username(nombre),
                "nombres_completos": nombre,
                "tipo_usuario": ANIMADOR,
                "rol": rol,
                **{k: v for k, v in (course or {}).items() if v not in (None, "")},
            }
        ).inserted_id
        return user_id

    def create(self, data: dict[str, Any], reassign: bool = False) -> dict[str, Any]:
        fields = self._clean(data, partial=False)
        self._ensure_email_free(fields.get("correo"))
        self._claim_course(fields, None, reassign)
        nombre = fields.pop("nombre")
        course = course_of(fields)
        user_id = self._create_user(nombre, course, fields["rol"])
        doc: Doc = {"profesor": nombre, "usuario_id": user_id}
        doc.update({k: v for k, v in fields.items() if v not in (None, "")})
        try:
            doc["_id"] = self.cols.animators.insert_one(doc).inserted_id
        except DuplicateKeyError as exc:  # otro administrador tomó el curso al mismo tiempo
            self.cols.users.delete_one({"_id": user_id})
            raise Conflict("El curso acaba de ser asignado a otro animador.") from exc
        return self.serialize(doc)

    def update(self, animator_id: Any, data: dict[str, Any], reassign: bool = False) -> dict[str, Any]:
        doc = self.get(animator_id)
        if any(k in data for k in COURSE_FIELDS):
            # Cambio parcial del curso (p. ej. solo el paralelo): el resto se toma del actual.
            data = {**{k: doc.get(k) for k in COURSE_FIELDS}, **data}
        fields = self._clean(data, partial=True, current_rol=rol_de(doc))
        self._ensure_email_free(fields.get("correo"), exclude=doc["_id"])
        self._claim_course(fields, doc["_id"], reassign)

        changes: dict[str, Any] = {k: v for k, v in fields.items() if k != "nombre"}
        if "nombre" in fields:
            changes["tutor" if "tutor" in doc and "profesor" not in doc else "profesor"] = fields["nombre"]
        user = self.linked_user(doc)
        if changes:
            try:
                self.cols.animators.update_one({"_id": doc["_id"]}, set_or_unset(changes))
            except DuplicateKeyError as exc:
                raise Conflict("El curso acaba de ser asignado a otro animador.") from exc

        updated = self.get(doc["_id"])
        if user is None:
            # Animador histórico sin cuenta en Users: se le crea para que pueda operar.
            user_id = self._create_user(animator_name(updated), course_of(updated), rol_de(updated))
            self.cols.animators.update_one({"_id": doc["_id"]}, {"$set": {"usuario_id": user_id}})
            return self.serialize(self.get(doc["_id"]))

        user_fields = {k: v for k, v in fields.items() if k in (*COURSE_FIELDS, "rol")}
        if "nombre" in fields:
            user_fields["nombres_completos"] = fields["nombre"]
        if user_fields:
            self.cols.users.update_one({"_id": user["_id"]}, set_or_unset(user_fields))
        return self.serialize(updated)

    def delete(self, animator_id: Any) -> None:
        """Elimina el animador y su cuenta, salvo que ya tenga participantes o tablas reservadas."""
        doc = self.get(animator_id)
        user = self.linked_user(doc)
        if user:
            if self.cols.participants.count_documents({"registrado_por": user["_id"]}, limit=1):
                raise Conflict("El animador tiene participantes registrados; quite su correo en lugar de eliminarlo.")
            if safe_int(user.get("totalTables"), 0) > 0:
                raise Conflict("El animador tiene tablas reservadas; quite su correo en lugar de eliminarlo.")
            if safe_int(user.get("tipo_usuario"), 1) == ANIMADOR:
                self.cols.users.delete_one({"_id": user["_id"]})
        self.cols.animators.delete_one({"_id": doc["_id"]})
