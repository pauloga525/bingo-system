"""Muestra el estado de una tabla. Uso: python scripts/check_card.py [SERIAL]"""

import sys

from _common import get_database

serial = sys.argv[1] if len(sys.argv) > 1 else "CARD00087"
print(get_database()["tablas"].find_one({"serial": serial}, {"_id": 0, "serial": 1, "won": 1, "stateAsigned": 1}))
