"""Conexión compartida por los scripts de mantenimiento.

Usa la misma configuración que la app (``MONGO_URI`` y ``MONGO_DB``), así los
scripts no quedan apuntando a ``bingo_db`` cuando se configura otra base.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pymongo import MongoClient
from pymongo.database import Database

from bingo.config import Settings

TIMEOUT_MS = 5000


def get_client() -> MongoClient[dict[str, Any]]:
    return MongoClient(Settings.from_env().mongo_uri, serverSelectionTimeoutMS=TIMEOUT_MS)


def get_database() -> Database[dict[str, Any]]:
    return get_client()[Settings.from_env().mongo_db]
