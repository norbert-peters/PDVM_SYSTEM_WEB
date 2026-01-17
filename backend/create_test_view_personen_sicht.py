"""\
Create a reusable test View definition in pdvm_system.sys_viewdaten.

Creates a new record with:
- name = 'Personen Sicht'
- daten = the provided desktop-like structure (ROOT + PERSONDATEN controls)

The script auto-detects the schema (public vs pdvm_system) and the PK column
(uid vs uuid) to match the current database state.

Usage:
  python backend/create_test_view_personen_sicht.py
  python backend/create_test_view_personen_sicht.py --uid <uuid>
  python backend/create_test_view_personen_sicht.py --replace-by-name

Notes:
- Safe defaults: does not overwrite existing records unless --replace-by-name is used.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from typing import Any, Dict, Iterable, Set, Tuple

import asyncpg

DEFAULT_DB_URL = "postgresql://postgres:Polari$55@localhost:5432/pdvm_system"


PERSONEN_SICHT_DATEN: Dict[str, Any] = {
    "ROOT": {
        "NO_DATA": False,
        "VIEW_NAME": "",
        "VIEW_GUID": "",
        "HEADER_TEXT": "",
        "PROJECTION_MODE": "standard",
        "ALLOW_FILTER": True,
        "ALLOW_SORT": True,
        "DEFAULT_SORT_COLUMN": "",
        "DEFAULT_SORT_REVERSE": False,
        "TABLE": "persondaten",
    },
    "PERSONDATEN": {
        "a602ca3c-726d-4bb3-902b-fd00d23b9fa2": {
            "gruppe": "PERSDATEN",
            "feld": "FAMILIENNAME",
            "label": "Familienname",
            "type": "string",
            "default": "",
            "dropdown": None,
            "control_type": "base",
            "expert_mode": True,
            "show": True,
            "display_order": 1,
            "expert_order": 1,
            "searchable": True,
            "sortable": True,
            "sortDirection": "asc",
            "sortByOriginal": False,
            "filterType": "contains",
            "table": "persondaten",
        },
        "6e1c2e64-a871-47fb-bd60-f4655daa8387": {
            "gruppe": "PERSDATEN",
            "feld": "VORNAME",
            "label": "Vorname",
            "type": "string",
            "default": "",
            "dropdown": None,
            "control_type": "base",
            "expert_mode": True,
            "show": True,
            "display_order": 2,
            "expert_order": 2,
            "searchable": True,
            "sortable": True,
            "sortDirection": "asc",
            "sortByOriginal": False,
            "filterType": "contains",
            "table": "persondaten",
        },
        "e6ab3d84-2477-4846-8241-a7e48e331ec3": {
            "gruppe": "PERSDATEN",
            "feld": "GEBURTSDATUM",
            "label": "Geburtsdatum",
            "type": "date",
            "default": None,
            "dropdown": None,
            "control_type": "base",
            "expert_mode": True,
            "show": True,
            "display_order": 3,
            "expert_order": 3,
            "searchable": True,
            "sortable": True,
            "sortDirection": "desc",
            "sortByOriginal": True,
            "filterType": "dateRange",
            "table": "persondaten",
        },
        "da773a33-1fe3-4bbe-8663-8fb92984d230": {
            "gruppe": "PERSDATEN",
            "feld": "ANREDE",
            "label": "Anrede",
            "type": "dropdown",
            "default": "",
            "control_type": "dropdown",
            "expert_mode": True,
            "show": False,
            "display_order": 0,
            "expert_order": 4,
            "searchable": True,
            "sortable": True,
            "sortDirection": "asc",
            "sortByOriginal": False,
            "filterType": "dropdown",
            "table": "persondaten",
            "configs": {
                "dropdown": {
                    "table": "dropdowndaten",
                    "key": "ddaa6590-6d08-461b-a061-75faec26f4ba",
                    "feld": "anrede",
                }
            },
        },
        "3d6a44e8-8e2b-48f5-894a-ae8c0aeb8c25": {
            "gruppe": "PERSDATEN",
            "feld": "EMAIL",
            "label": "Email",
            "type": "string",
            "default": "",
            "dropdown": None,
            "control_type": "base",
            "expert_mode": True,
            "show": True,
            "display_order": 5,
            "expert_order": 5,
            "searchable": True,
            "sortable": True,
            "sortDirection": "asc",
            "sortByOriginal": False,
            "filterType": "contains",
            "table": "persondaten",
        },
        "ab92f9e8-f019-4e7f-ba1e-fdb135f37c35": {
            "type": "string",
            "default": "",
            "dropdown": None,
            "control_type": "base",
            "expert_mode": True,
            "show": True,
            "searchable": True,
            "sortable": True,
            "sortDirection": "asc",
            "sortByOriginal": False,
            "filterType": "contains",
            "display_order": 3,
            "gruppe": "ANSCHRIFT_PERSON",
            "feld": "ORT",
            "label": "Wohnort",
            "table": "persondaten",
        },
        "35ae6f54-d62c-459e-a52e-9e497eb2e773": {
            "gruppe": "SYSTEM",
            "feld": "uid",
            "label": "Identifikation",
            "type": "string",
            "default": "",
            "dropdown": None,
            "control_type": "base",
            "expert_mode": True,
            "show": False,
            "display_order": 0,
            "expert_order": 0,
            "searchable": True,
            "sortable": True,
            "sortDirection": "asc",
            "sortByOriginal": False,
            "filterType": "contains",
            "table": "persondaten",
        },
        "8332d37c-ac7d-440c-996c-a871f4d8cbee": {
            "gruppe": "SYSTEM",
            "feld": "name",
            "label": "Name DB",
            "type": "string",
            "default": "keine Daten",
            "dropdown": None,
            "control_type": "base",
            "expert_mode": True,
            "show": False,
            "display_order": 99,
            "expert_order": 99,
            "searchable": True,
            "sortable": True,
            "sortDirection": "asc",
            "sortByOriginal": False,
            "filterType": "contains",
        },
    },
}


async def _first_existing_relation(conn: asyncpg.Connection, candidates: Iterable[str]) -> str:
    for rel in candidates:
        found = await conn.fetchval("SELECT to_regclass($1)", rel)
        if found:
            return rel
    raise RuntimeError(f"Could not find sys_viewdaten table. Tried: {', '.join(candidates)}")


async def _get_columns(conn: asyncpg.Connection, schema: str, table: str) -> Set[str]:
    rows = await conn.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = $1 AND table_name = $2
        """,
        schema,
        table,
    )
    return {r["column_name"] for r in rows}


def _split_schema_table(relation: str) -> Tuple[str, str]:
    if "." in relation:
        s, t = relation.split(".", 1)
        return s, t
    return "public", relation


async def main() -> int:
    parser = argparse.ArgumentParser(description="Create sys_viewdaten test record: Personen Sicht")
    parser.add_argument("--uid", help="Optional UID/UUID to use for the record")
    parser.add_argument(
        "--replace-by-name",
        action="store_true",
        help="Delete existing records with name='Personen Sicht' before inserting",
    )
    parser.add_argument(
        "--db-url",
        default=DEFAULT_DB_URL,
        help="PostgreSQL URL for pdvm_system database",
    )
    args = parser.parse_args()

    record_id = uuid.UUID(args.uid) if args.uid else uuid.uuid4()

    conn = await asyncpg.connect(args.db_url)
    try:
        relation = await _first_existing_relation(
            conn,
            candidates=[
                "pdvm_system.sys_viewdaten",
                "public.sys_viewdaten",
                "sys_viewdaten",
            ],
        )
        schema, table = _split_schema_table(relation)
        cols = await _get_columns(conn, schema, table)

        pk_col = "uid" if "uid" in cols else ("uuid" if "uuid" in cols else None)
        if not pk_col:
            raise RuntimeError(f"No uid/uuid column found in {relation}")

        if args.replace_by_name:
            await conn.execute(f"DELETE FROM {relation} WHERE name = $1", "Personen Sicht")

        insert_cols = [pk_col, "daten", "name"]
        if "historisch" in cols:
            insert_cols.append("historisch")

        # Optional timestamp columns
        if "created_at" in cols:
            insert_cols.append("created_at")
        if "modified_at" in cols:
            insert_cols.append("modified_at")

        placeholders = []
        values = []

        # pk
        placeholders.append(f"${len(values)+1}")
        values.append(record_id)

        # daten
        placeholders.append(f"${len(values)+1}::jsonb")
        values.append(json.dumps(PERSONEN_SICHT_DATEN))

        # name
        placeholders.append(f"${len(values)+1}")
        values.append("Personen Sicht")

        if "historisch" in cols:
            placeholders.append("0")

        # created_at / modified_at
        if "created_at" in cols:
            placeholders.append("NOW()")
        if "modified_at" in cols:
            placeholders.append("NOW()")

        query = f"""
            INSERT INTO {relation} ({', '.join(insert_cols)})
            VALUES ({', '.join(placeholders)})
        """

        await conn.execute(query, *values)

        print(f"✅ sys_viewdaten inserted: name='Personen Sicht'")
        print(f"   table: {relation}")
        print(f"   {pk_col}: {record_id}")

    finally:
        await conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
