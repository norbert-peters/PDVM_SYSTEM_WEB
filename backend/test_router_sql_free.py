"""
Guardrail (ARCHITECTURE_RULES.md 1.1): Router enthalten keinen direkten Datenbankzugriff.

Prueft per Quelltext-Scan (ohne Datenbank), dass admin.py und mandanten.py weder
asyncpg noch SQL-Ausfuehrung enthalten, und testet die reinen Helfer des
db_admin_service.
"""
import ast
import asyncio
import io
import tokenize
from pathlib import Path

import pytest

from app.core import db_admin_service as svc

API_DIR = Path(__file__).parent / "app" / "api"
ROUTER_FILES = ["admin.py", "mandanten.py"]

FORBIDDEN = [
    "asyncpg",
    ".fetch(",
    ".fetchrow(",
    ".fetchval(",
    ".execute(",
    "CREATE DATABASE",
    "DROP DATABASE",
]


def _code_without_comments(path: Path) -> str:
    source = path.read_text(encoding="utf-8-sig")
    tokens = [
        tok for tok in tokenize.generate_tokens(io.StringIO(source).readline)
        if tok.type != tokenize.COMMENT
    ]
    return tokenize.untokenize(tokens)


@pytest.mark.parametrize("filename", ROUTER_FILES)
@pytest.mark.parametrize("forbidden", FORBIDDEN)
def test_router_has_no_direct_db_access(filename, forbidden):
    code = _code_without_comments(API_DIR / filename)
    assert forbidden not in code, f"{filename} enthaelt '{forbidden}' (Router duerfen keinen DB-Zugriff haben)"


@pytest.mark.parametrize("filename", ROUTER_FILES)
def test_router_does_not_import_legacy_pdvm_database(filename):
    tree = ast.parse((API_DIR / filename).read_text(encoding="utf-8-sig"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("core.database"):
            assert "PdvmDatabase" not in [alias.name for alias in node.names]


def test_build_mandant_db_name():
    assert svc.build_mandant_db_name("Neue Firma") == "mandant_neue_firma"
    assert svc.build_mandant_db_name("A-B c") == "mandant_a_b_c"


@pytest.mark.parametrize("name,expected", [
    ("mandant_abc_1", True),
    ("mandant_a-b", False),
    ('mandant_"x"', False),
    ("mandant_a b", False),
    ("mandant_a;drop", False),
])
def test_is_valid_db_name(name, expected):
    assert svc.is_valid_db_name(name) is expected


@pytest.mark.parametrize("name,expected", [
    ("asy_table", True),
    ("tab1", True),
    ("", False),
    ("a-b", False),
    ("a'b", False),
    ("a b", False),
])
def test_is_valid_table_name(name, expected):
    assert svc.is_valid_table_name(name) is expected


def test_is_mandant_db_name():
    assert svc.is_mandant_db_name("mandant_x")
    assert not svc.is_mandant_db_name("pdvm_system")
    assert not svc.is_mandant_db_name("mandant")


def test_create_mandant_database_rejects_invalid_name_before_connecting():
    with pytest.raises(svc.InvalidDatabaseNameError):
        asyncio.run(svc.create_mandant_database('bad"name'))


def test_create_table_rejects_invalid_table_name_before_connecting():
    with pytest.raises(svc.InvalidTableNameError):
        asyncio.run(svc.create_table("bad-name", "mandant"))


def test_delete_database_only_allows_mandant_databases():
    with pytest.raises(svc.DatabaseDeletionNotAllowedError):
        asyncio.run(svc.delete_database("pdvm_system"))
