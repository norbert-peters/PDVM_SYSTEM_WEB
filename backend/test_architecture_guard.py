"""Architektur-Waechter (ARCHITECTURE_RULES 1.1, 1.7, Phase 3 Plan).

Statische Pruefung ohne Datenbank:
- Router (app/api) enthalten kein SQL und keinen direkten asyncpg-Zugriff.
- Die alte CRUD-Klasse aus app.core.database ist stillgelegt.
- Schreiboperationen (create/update/delete) laufen ueber app.core.central_write_service.
"""
import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent / "app"
API_DIR = APP_DIR / "api"

SQL_IN_ROUTER = re.compile(
    r"\.(fetch|fetchrow|fetchval|execute|executemany)\(|\bimport asyncpg\b|\basyncpg\.connect\b|"
    r"\b(SELECT\s.+\sFROM|INSERT\s+INTO|DELETE\s+FROM|CREATE\s+(DATABASE|TABLE)|DROP\s+DATABASE)\b",
    re.IGNORECASE,
)
DIRECT_WRITE = re.compile(r"\b(?:db|database|\w+_db)\.(create|update|delete)\(")
WRITE_GATEWAY_FILES = {"central_write_service.py", "pdvm_datenbank.py"}


def _code_lines(path: Path):
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        yield number, line


def test_routers_contain_no_sql_or_direct_asyncpg():
    offenders = []
    for path in sorted(API_DIR.glob("*.py")):
        for number, line in _code_lines(path):
            if SQL_IN_ROUTER.search(line):
                offenders.append(f"{path.name}:{number}: {line.strip()}")
    assert not offenders, "SQL/asyncpg im Router (Regel 1.1):\n" + "\n".join(offenders)


def test_legacy_crud_class_is_retired():
    offenders = []
    for path in sorted(APP_DIR.rglob("*.py")):
        for number, line in _code_lines(path):
            if re.search(r"from\s+(app\.core|\.\.core|\.)\.?database\s+import\s+.*\bPdvmDatabase\b", line):
                offenders.append(f"{path.relative_to(APP_DIR)}:{number}")
    assert not offenders, "Import der stillgelegten Klasse core.database.PdvmDatabase:\n" + "\n".join(offenders)
    assert "class PdvmDatabase" not in (APP_DIR / "core" / "database.py").read_text(encoding="utf-8")


def test_writes_go_through_central_write_service():
    offenders = []
    for path in sorted(APP_DIR.rglob("*.py")):
        if path.name in WRITE_GATEWAY_FILES:
            continue
        for number, line in _code_lines(path):
            if DIRECT_WRITE.search(line):
                offenders.append(f"{path.relative_to(APP_DIR)}:{number}: {line.strip()}")
    assert not offenders, "Direkter db.create/update/delete ausserhalb des Gateways:\n" + "\n".join(offenders)
