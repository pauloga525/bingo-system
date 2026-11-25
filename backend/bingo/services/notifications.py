"""Correo al comprador con sus tablas (después de cada venta o al añadir tablas).

El envío corre en segundo plano: la venta responde enseguida y el resultado
queda en el participante (``correo_estado``: ``pendiente``, ``enviado``,
``error`` o ``sin_configurar``, más ``correo_enviado_at`` / ``correo_error``),
para mostrarlo en el panel y poder **reenviar**.
"""

from __future__ import annotations

import html
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

from bson import ObjectId

from ..db import Collections, Doc
from ..domain.pricing import calcular_total
from ..errors import NotFound
from .mailer import Attachment, Mail, Mailer, MailNotConfigured
from .pdf_render import render_cards_pdf

logger = logging.getLogger(__name__)
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="correo")

PENDIENTE, ENVIADO, ERROR, SIN_CONFIGURAR = "pendiente", "enviado", "error", "sin_configurar"


def _send_logged(mailer: Mailer, mail: Mail) -> None:
    try:
        mailer.send(mail)
    except Exception as exc:  # un fallo de correo no debe tumbar la petición
        logger.warning("No se pudo enviar el correo a %s: %s", mail.to, exc)


def send_mail_async(mailer: Mailer, mail: Mail, run_async: bool = True) -> None:
    """Envía un correo suelto (p. ej. el código de acceso) sin bloquear la petición."""
    if run_async:
        _EXECUTOR.submit(_send_logged, mailer, mail)
    else:
        _send_logged(mailer, mail)


class TablesMailer:
    def __init__(self, cols: Collections, mailer: Mailer, panel_url: str, run_async: bool = True) -> None:
        self.cols = cols
        self.mailer = mailer
        self.panel_url = panel_url.rstrip("/")
        self.run_async = run_async

    def _tables(self, participante: Doc) -> list[Doc]:
        ids = participante.get("tablas") or []
        return list(self.cols.tables.find({"_id": {"$in": ids}}).sort("serial", 1)) if ids else []

    def build(self, participante: Doc, tablas: list[Doc]) -> Mail:
        nombre = f"{participante.get('nombre', '')} {participante.get('apellido', '')}".strip() or "participante"
        seriales = [str(t.get("serial", "")) for t in tablas]
        total = calcular_total(len(seriales))
        alumno = participante.get("tipo") == "alumno"
        como_ver = (
            f"Para verlas en línea ingresa a {self.panel_url} con tu correo institucional ({participante['correo']})."
            if alumno
            else (
                f"Para verlas en línea ingresa a {self.panel_url}, elige «Público general» y escribe tu "
                "cédula y este correo: te enviaremos un código de acceso."
            )
        )
        text = (
            f"Hola {nombre},\n\n"
            f"Gracias por participar en el Bingo UETS. Tus tablas ({len(seriales)}):\n"
            + "\n".join(f"  - {s}" for s in seriales)
            + f"\n\nTotal: ${total}\n{como_ver}\n\nAdjuntamos el PDF con tus tablas.\n\n"
            "Este es un correo automático, por favor no respondas.\nUnidad Educativa Técnico Salesiano"
        )
        filas = "".join(f"<li><strong>{html.escape(s)}</strong></li>" for s in seriales)
        html_body = (
            f"<p>Hola {html.escape(nombre)},</p>"
            f"<p>Gracias por participar en el <strong>Bingo UETS</strong>. Tus tablas ({len(seriales)}):</p>"
            f"<ul>{filas}</ul><p>Total: <strong>${total}</strong></p>"
            f"<p>{html.escape(como_ver)}</p><p>Adjuntamos el PDF con tus tablas.</p>"
            "<p style='color:#888;font-size:12px'>Correo automático, por favor no respondas.<br>"
            "Unidad Educativa Técnico Salesiano</p>"
        )
        cedula = str(participante.get("cedula", "")).strip() or "tablas"
        pdf = Attachment(f"tablas_bingo_{cedula}.pdf", render_cards_pdf(tablas))
        return Mail(
            to=str(participante["correo"]),
            subject=f"Tus tablas del Bingo UETS ({len(seriales)})",
            text=text,
            html=html_body,
            attachments=(pdf,),
        )

    def _set_status(self, participant_id: ObjectId, estado: str, error: str = "") -> None:
        campos: dict[str, Any] = {"correo_estado": estado, "correo_error": error}
        if estado == ENVIADO:
            campos["correo_enviado_at"] = datetime.now().isoformat(timespec="seconds")
        self.cols.participants.update_one({"_id": participant_id}, {"$set": campos})

    def send_now(self, participant_id: ObjectId) -> str:
        """Envía el correo y guarda el resultado. Nunca lanza: devuelve el estado final."""
        participante = self.cols.participants.find_one({"_id": participant_id})
        if not participante or not participante.get("correo"):
            return ERROR
        try:
            self.mailer.send(self.build(participante, self._tables(participante)))
        except MailNotConfigured as exc:
            self._set_status(participant_id, SIN_CONFIGURAR, str(exc))
            return SIN_CONFIGURAR
        except Exception as exc:  # el error del servidor de correo no debe tumbar nada
            logger.warning("No se pudo enviar el correo de tablas a %s: %s", participante["correo"], exc)
            self._set_status(participant_id, ERROR, str(exc)[:300])
            return ERROR
        self._set_status(participant_id, ENVIADO)
        return ENVIADO

    def notify(self, participant_id: ObjectId) -> None:
        """Marca el correo como pendiente y lo envía (en segundo plano en producción)."""
        if not self.cols.participants.find_one({"_id": participant_id}, {"_id": 1}):
            raise NotFound("Participante no encontrado.")
        self._set_status(participant_id, PENDIENTE)
        if self.run_async:
            _EXECUTOR.submit(self.send_now, participant_id)
        else:
            self.send_now(participant_id)
