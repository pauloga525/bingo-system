"""Configuración de la aplicación, leída desde variables de entorno."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "si", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).resolve() if value else default


@dataclass(frozen=True)
class Settings:
    """Parámetros de ejecución.

    Todos los valores tienen un default compatible con el comportamiento
    histórico (MongoDB local, carpetas ``jsons/``, ``winners/`` y ``upload/``).
    """

    mongo_uri: str = "mongodb://localhost:27017/"
    mongo_db: str = "bingo_db"
    json_dir: Path = BASE_DIR / "jsons"
    winners_dir: Path = BASE_DIR / "winners"
    upload_dir: Path = BASE_DIR / "upload"
    # Respaldos JSON que genera el servidor antes de borrados masivos (datos personales: no versionar).
    backup_dir: Path = BASE_DIR / "backups"
    cors_origins: str = "*"
    # Escucha en toda la red porque el frontend y la mesa de juego están en otros equipos.
    # Usa FLASK_HOST=127.0.0.1 si solo se accede desde esta máquina.
    host: str = "0.0.0.0"  # noqa: S104
    port: int = 5000
    debug: bool = False
    # Cantidad de snapshots ``bingo_cards_active_*.json`` que se conservan al reiniciar.
    active_json_keep: int = 10
    # Si es False no se intentan crear índices al arrancar.
    create_indexes: bool = True
    # Tamaño máximo de una petición (p. ej. el PDF de /upload), en MB.
    max_upload_mb: int = 50
    # Hilos de waitress (peticiones atendidas en paralelo).
    threads: int = 8
    # --- Autenticación con Google (OAuth 2.0 / OpenID Connect) ---
    # ID de cliente OAuth de Google; el token de Google debe estar emitido para este cliente.
    google_client_id: str = ""
    # Clave para firmar los tokens de sesión propios. Si está vacía se genera una al
    # arrancar (las sesiones se pierden al reiniciar el servidor).
    secret_key: str = ""
    # Duración de la sesión, en horas.
    session_hours: int = 8
    # Correos con rol administrador (separados por comas) y el usuario de ``Users`` que representan.
    admin_emails: str = "admin@uets.edu.ec"
    admin_usuario: str = "ADMIN"
    # Dominio del personal (administrador/animadores) y dominio adicional de estudiantes.
    # Los correos de estudiantes 2026 son ``nombre.apellido.est@uets.edu.ec`` (dominio del
    # personal); ``student_domain`` se acepta además por compatibilidad.
    staff_domain: str = "uets.edu.ec"
    student_domain: str = "est.uets.edu.ec"

    @classmethod
    def from_env(cls) -> Settings:
        """Construye la configuración a partir de variables de entorno."""
        return cls(
            mongo_uri=os.environ.get("MONGO_URI", cls.mongo_uri),
            mongo_db=os.environ.get("MONGO_DB", cls.mongo_db),
            json_dir=_env_path("BINGO_JSON_DIR", BASE_DIR / "jsons"),
            winners_dir=_env_path("BINGO_WINNERS_DIR", BASE_DIR / "winners"),
            upload_dir=_env_path("BINGO_UPLOAD_DIR", BASE_DIR / "upload"),
            backup_dir=_env_path("BINGO_BACKUP_DIR", BASE_DIR / "backups"),
            cors_origins=os.environ.get("CORS_ORIGINS", cls.cors_origins),
            host=os.environ.get("FLASK_HOST", cls.host),
            port=_env_int("FLASK_PORT", cls.port),
            debug=_env_bool("FLASK_DEBUG", cls.debug),
            active_json_keep=_env_int("BINGO_ACTIVE_JSON_KEEP", cls.active_json_keep),
            create_indexes=_env_bool("BINGO_CREATE_INDEXES", cls.create_indexes),
            max_upload_mb=_env_int("BINGO_MAX_UPLOAD_MB", cls.max_upload_mb),
            threads=_env_int("BINGO_THREADS", cls.threads),
            google_client_id=os.environ.get("GOOGLE_CLIENT_ID", cls.google_client_id),
            secret_key=os.environ.get("BINGO_SECRET_KEY", cls.secret_key),
            session_hours=_env_int("BINGO_SESSION_HOURS", cls.session_hours),
            admin_emails=os.environ.get("BINGO_ADMIN_EMAILS", cls.admin_emails),
            admin_usuario=os.environ.get("BINGO_ADMIN_USUARIO", cls.admin_usuario),
            staff_domain=os.environ.get("BINGO_STAFF_DOMAIN", cls.staff_domain),
            student_domain=os.environ.get("BINGO_STUDENT_DOMAIN", cls.student_domain),
        )

    @property
    def cors_origin_list(self) -> str | list[str]:
        """Orígenes CORS: ``"*"`` o una lista separada por comas."""
        if self.cors_origins.strip() == "*":
            return "*"
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def student_email_regex(self) -> re.Pattern[str]:
        """Correo estudiantil: ``...est@`` o ``..._estudiante@`` del dominio, o el dominio de estudiantes."""
        staff, student = re.escape(self.staff_domain), re.escape(self.student_domain)
        return re.compile(rf"^[^@\s]+(\.est|_?estudiante)@{staff}$|^[^@\s]+@{student}$")

    @property
    def student_domains(self) -> tuple[str, ...]:
        """Dominios válidos para correos de estudiantes."""
        return tuple(dict.fromkeys((self.staff_domain, self.student_domain)))

    @property
    def admin_email_set(self) -> frozenset[str]:
        """Correos de administrador, en minúsculas."""
        return frozenset(e.strip().lower() for e in self.admin_emails.split(",") if e.strip())
