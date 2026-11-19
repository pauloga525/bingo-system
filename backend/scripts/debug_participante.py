import json
import sys

from _common import get_database
from bson import ObjectId, json_util
from bson.errors import InvalidId

if len(sys.argv) < 2:
    print("Usage: debug_participante.py <cedula>")
    sys.exit(1)
cedula = sys.argv[1]
db = get_database()
part = db["Participantes"]
t = db["tablas"]
res = part.find_one({"cedula": cedula})
print("--- PARTICIPANTE DOCUMENT ---")
print(json.dumps(res, default=json_util.default, indent=2))
print("\n--- TABLAS FIELD DETAILED ---")
if res:
    tablas = res.get("tablas", [])
    print("tablas raw count:", len(tablas))
    print("tablas raw entries:")
    for i, entry in enumerate(tablas, 1):
        print(i, type(entry), entry)
    # Now fetch table docs for each entry if it's ObjectId or string
    ids = []
    for entry in tablas:
        try:
            # if it's a dict with $oid
            if isinstance(entry, dict) and entry.get("$oid"):
                ids.append(ObjectId(entry["$oid"]))
            elif isinstance(entry, str) and len(entry) == 24:
                ids.append(ObjectId(entry))
            elif isinstance(entry, ObjectId):
                ids.append(entry)
        except InvalidId:
            print(f"Referencia de tabla inválida, se omite: {entry!r}")
    if ids:
        docs = list(t.find({"_id": {"$in": ids}}))
        print("\nFound", len(docs), "tabla docs for ObjectId entries:")
        print(json.dumps(docs, default=json_util.default, indent=2))
    # Also check lookup by serials in participant field if they stored serials instead of ids
    serials = []
    for entry in tablas:
        if isinstance(entry, str) and entry.upper().startswith("CARD"):
            serials.append(entry)
    if serials:
        docs2 = list(t.find({"serial": {"$in": serials}}))
        print("\nFound", len(docs2), "tabla docs for serial strings:")
        print(json.dumps(docs2, default=json_util.default, indent=2))
else:
    print("Participante no encontrado")
