"""Envío de correos por SMTP (cuenta ``noreply@uets.edu.ec``).

La configuración sale del ``.env`` (``SMTP_HOST``, ``SMTP_PORT``, ``SMTP_USER``,
``SMTP_PASS`` y ``MAIL_FROM``); la contraseña nunca se versiona. Con el puerto 465
se usa SSL directo y con 587 STARTTLS. Si falta la configuración el envío se
marca como "no configurado" en lugar de fallar la venta.

Los tests inyectan :class:`MemoryMailer`, que guarda los mensajes en memoria.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Protocol

logger = logging.getLogger(__name__)
_TIMEOUT = 30


@dataclass(frozen=True)
class Attachment:
    filename: str
    content: bytes
    maintype: str = "application"
    subtype: str = "pdf"


@dataclass(frozen=True)
class Mail:
    to: str
    subject: str
    text: str
    html: str = ""
    attachments: tuple[Attachment, ...] = ()


class MailNotConfigured(RuntimeError):
    """No hay servidor SMTP configurado."""


class Mailer(Protocol):
    def send(self, mail: Mail) -> None: ...


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    user: str
    password: str
    sender: str

    @property
    def login_password(self) -> str:
        """Google muestra la contraseña de aplicación en grupos con espacios: se envía sin ellos."""
        return self.password.replace(" ", "")

    @property
    def ready(self) -> bool:
        return bool(self.host and self.user and self.password and self.sender)


def build_message(mail: Mail, sender: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = mail.to
    msg["Subject"] = mail.subject
    msg.set_content(mail.text)
    if mail.html:
        msg.add_alternative(mail.html, subtype="html")
    for a in mail.attachments:
        msg.add_attachment(a.content, maintype=a.maintype, subtype=a.subtype, filename=a.filename)
    return msg


class SmtpMailer:
    def __init__(self, config: SmtpConfig) -> None:
        self.config = config

    def send(self, mail: Mail) -> None:  # pragma: no cover - requiere un servidor SMTP real
        cfg = self.config
        if not cfg.ready:
            raise MailNotConfigured("El envío de correos no está configurado (SMTP_* en el .env).")
        msg = build_message(mail, cfg.sender)
        context = ssl.create_default_context()
        if cfg.port == 465:
            with smtplib.SMTP_SSL(cfg.host, cfg.port, context=context, timeout=_TIMEOUT) as smtp:
                smtp.login(cfg.user, cfg.login_password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(cfg.host, cfg.port, timeout=_TIMEOUT) as smtp:
                smtp.starttls(context=context)
                smtp.login(cfg.user, cfg.login_password)
                smtp.send_message(msg)


@dataclass
class MemoryMailer:
    """Doble para tests y para la demo local: guarda los correos en lugar de enviarlos."""

    sent: list[Mail] = field(default_factory=list)
    fail_with: str = ""

    def send(self, mail: Mail) -> None:
        if self.fail_with:
            raise RuntimeError(self.fail_with)
        build_message(mail, "Prueba <noreply@example.com>")  # valida que el mensaje se arme bien
        self.sent.append(mail)
        logger.info("Correo (memoria) para %s: %s", mail.to, mail.subject)
