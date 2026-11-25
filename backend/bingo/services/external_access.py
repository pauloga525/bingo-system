"""Acceso del público externo a sus tablas con cédula + correo + código por correo.

Reemplaza a la consulta pública por cédula (cualquiera podía ver las tablas de
otra persona sabiendo su cédula). Ahora:

1. El comprador escribe su **cédula y el correo** que dio al comprar.
2. Si existe una compra con esos dos datos, se le envía un **código de 6
   dígitos** a ese correo. La respuesta es siempre la misma, exista o no la
   compra, para no revelar qué cédulas compraron.
3. Con el código correcto obtiene una sesión corta de solo lectura.

Protecciones: el código se guarda como HMAC (no en claro), vence a los 10
minutos (índice TTL), admite 5 intentos, y por cédula+correo se puede pedir
uno por minuto y 5 por hora.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from ..db import Collections, Doc
from ..errors import ApiError
from .mailer import Mail, Mailer
from .notifications import send_mail_async

CODE_MINUTES = 10
MAX_ATTEMPTS = 5
RESEND_SECONDS = 60
MAX_PER_HOUR = 5
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
GENERIC = "Si los datos coinciden con una compra, te enviamos un código a tu correo. Revisa también el spam."


def utc_now() -> datetime:
    """Hora UTC sin zona: así la guarda MongoDB y así la compara el índice TTL."""
    return datetime.now(UTC).replace(tzinfo=None)


class TooManyRequests(ApiError):
    def __init__(self, message: str) -> None:
        super().__init__(message, 429)


def clean_credentials(cedula: Any, correo: Any) -> tuple[str, str]:
    cedula_txt = str(cedula or "").strip()
    correo_txt = str(correo or "").strip().lower()
    if not cedula_txt.isdigit() or not 6 <= len(cedula_txt) <= 13:
        raise ApiError("Ingrese un número de cédula válido.")
    if not _EMAIL.match(correo_txt):
        raise ApiError("Ingrese un correo válido.")
    return cedula_txt, correo_txt


class ExternalAccess:
    def __init__(self, cols: Collections, secret: str, mailer: Mailer, run_async: bool = True) -> None:
        self.cols = cols
        self.secret = secret.encode()
        self.mailer = mailer
        self.run_async = run_async

    def _hash(self, cedula: str, correo: str, code: str) -> str:
        return hmac.new(self.secret, f"{cedula}|{correo}|{code}".encode(), hashlib.sha256).hexdigest()

    def purchase(self, cedula: str, correo: str) -> Doc | None:
        """Compra con esa cédula y ese correo (los dos deben coincidir)."""
        return self.cols.participants.find_one({"cedula": cedula, "correo": correo})

    def request_code(self, cedula: Any, correo: Any, now: datetime | None = None) -> None:
        cedula_txt, correo_txt = clean_credentials(cedula, correo)
        now = now or utc_now()
        key = {"cedula": cedula_txt, "correo": correo_txt}
        recientes = list(self.cols.codes.find({**key, "creado": {"$gte": now - timedelta(hours=1)}}, {"creado": 1}))
        if any(r["creado"] > now - timedelta(seconds=RESEND_SECONDS) for r in recientes):
            raise TooManyRequests("Espera un minuto antes de pedir otro código.")
        if len(recientes) >= MAX_PER_HOUR:
            raise TooManyRequests("Pediste demasiados códigos. Intenta de nuevo en una hora.")

        participante = self.purchase(cedula_txt, correo_txt)
        code = f"{secrets.randbelow(10**6):06d}"
        # También se registra cuando no hay compra (sin código válido): así cuenta para el límite.
        self.cols.codes.insert_one(
            {
                **key,
                "hash": self._hash(cedula_txt, correo_txt, code) if participante else None,
                "intentos": 0,
                "creado": now,
                "expira": now + timedelta(minutes=CODE_MINUTES),
            }
        )
        if participante is None:
            return
        nombre = str(participante.get("nombre") or "").strip()
        texto = (
            f"Hola {nombre},\n\nTu código para ver tus tablas del Bingo UETS es: {code}\n\n"
            f"Vence en {CODE_MINUTES} minutos. Si no lo pediste, ignora este correo.\n\n"
            "Este es un correo automático, por favor no respondas.\nUnidad Educativa Técnico Salesiano"
        )
        html = (
            f"<p>Hola {nombre},</p><p>Tu código para ver tus tablas del <strong>Bingo UETS</strong> es:</p>"
            f"<p style='font-size:28px;letter-spacing:6px'><strong>{code}</strong></p>"
            f"<p>Vence en {CODE_MINUTES} minutos. Si no lo pediste, ignora este correo.</p>"
        )
        send_mail_async(
            self.mailer, Mail(correo_txt, f"Código de acceso Bingo UETS: {code}", texto, html), self.run_async
        )

    def verify(self, cedula: Any, correo: Any, codigo: Any, now: datetime | None = None) -> Doc:
        """Valida el código y devuelve la compra. Borra los códigos usados."""
        cedula_txt, correo_txt = clean_credentials(cedula, correo)
        now = now or utc_now()
        key = {"cedula": cedula_txt, "correo": correo_txt}
        doc = self.cols.codes.find_one({**key, "hash": {"$ne": None}, "expira": {"$gt": now}}, sort=[("creado", -1)])
        if doc is None:
            raise ApiError("El código venció o no es válido. Pide uno nuevo.")
        if doc.get("intentos", 0) >= MAX_ATTEMPTS:
            raise TooManyRequests("Demasiados intentos con este código. Pide uno nuevo.")
        esperado = self._hash(cedula_txt, correo_txt, str(codigo or "").strip())
        if not hmac.compare_digest(str(doc["hash"]), esperado):
            self.cols.codes.update_one({"_id": doc["_id"]}, {"$inc": {"intentos": 1}})
            raise ApiError("Código incorrecto.")
        participante = self.purchase(cedula_txt, correo_txt)
        self.cols.codes.delete_many(key)
        if participante is None:  # pragma: no cover - la compra se borró en estos minutos
            raise ApiError("Ya no hay tablas registradas con esos datos.")
        return participante
