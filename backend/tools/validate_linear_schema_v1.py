"""Validiert PDVM Linear Schema V1 für Kern-Tabellen.

Scope (Schritt 2 aus PDVM_LINEAR_SCHEMA_V1):
- Schema-/Pflichtfelder prüfen
- Namenskonventionen prüfen
- ROOT/CONTROL/TEMPLATES Key-Konventionen prüfen

Usage:
  python backend/tools/validate_linear_schema_v1.py
  python backend/tools/validate_linear_schema_v1.py --tables sys_control_dict,sys_dialogdaten
  python backend/tools/validate_linear_schema_v1.py --include-historisch
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
	sys.path.insert(0, str(BACKEND_DIR))

import asyncpg

from app.core.connection_manager import ConnectionManager

DEFAULT_TABLES = [
	"sys_control_dict",
	"sys_contr_dict_man",
	"sys_dialogdaten",
	"sys_viewdaten",
	"sys_framedaten",
]

REQUIRED_BOOTSTRAP_CONTROLS = {
	"SYS_SELF_GUID",
	"SYS_SELF_NAME",
	"SYS_TABLE",
	"SYS_GRUPPE",
	"SYS_FIELD",
	"SYS_TYPE",
	"SYS_LABEL",
	"SYS_DISPLAY_SHOW",
	"SYS_DISPLAY_ORDER",
	"SYS_EXPERT_ORDER",
	"SYS_FILTER_TYPE",
	"SYS_SORTABLE",
	"SYS_SEARCHABLE",
	"SYS_READ_ONLY",
	"SYS_HISTORICAL",
	"SYS_CONFIGS_ELEMENTS",
	"SYS_FIELDS_ELEMENTS",
	"SYS_TAB_ELEMENTS",
	"SYS_MODULE",
	"SYS_GUID",
	"SYS_EDIT_TYPE",
	"SYS_OPEN_EDIT",
}


@dataclass
class ValidationResult:
	table_name: str
	checked: int = 0
	errors: List[str] = field(default_factory=list)
	warnings: List[str] = field(default_factory=list)


def _as_dict(value: Any) -> Dict[str, Any]:
	return value if isinstance(value, dict) else {}


def _is_upper_key(key: str) -> bool:
	return key == key.upper()


def _looks_like_tab_key(key: str) -> bool:
	return re.match(r"^TAB_\d{2}$", str(key).upper()) is not None


def _extract_tab_elements(value: Any) -> Dict[int, Dict[str, Any]]:
	out: Dict[int, Dict[str, Any]] = {}

	if isinstance(value, dict):
		for key, row in value.items():
			if not isinstance(row, dict):
				continue
			idx = None
			match = re.match(r"^TAB[_\-]?0*(\d+)$", str(key), flags=re.IGNORECASE)
			if match:
				idx = int(match.group(1))
			elif isinstance(row.get("TAB"), int):
				idx = int(row.get("TAB"))
			if not idx or idx < 1 or idx > 20:
				continue
			out[idx] = row
		return out

	if isinstance(value, list):
		for pos, row in enumerate(value, start=1):
			if not isinstance(row, dict):
				continue
			raw_idx = row.get("TAB") or row.get("index") or pos
			try:
				idx = int(raw_idx)
			except Exception:
				continue
			if idx < 1 or idx > 20:
				continue
			out[idx] = row

	return out


def _validate_upper_dict_keys(
	result: ValidationResult,
	row_ref: str,
	container: Dict[str, Any],
	container_name: str,
) -> None:
	for key in container.keys():
		if isinstance(key, str) and not _is_upper_key(key):
			result.warnings.append(
				f"{row_ref}: {container_name}-Key '{key}' ist nicht GROSS (Soll: {key.upper()})"
			)


def _validate_single_row(
	result: ValidationResult,
	*,
	uid: uuid.UUID,
	name: str,
	daten: Dict[str, Any],
) -> None:
	row_ref = f"uid={uid}"
	result.checked += 1

	if not isinstance(daten, dict):
		result.errors.append(f"{row_ref}: daten ist kein Objekt")
		return

	_validate_upper_dict_keys(result, row_ref, daten, "Top-Level")

	root = _as_dict(daten.get("ROOT"))
	if not root:
		result.errors.append(f"{row_ref}: ROOT fehlt oder ist kein Objekt")
		return

	_validate_upper_dict_keys(result, row_ref, root, "ROOT")

	self_guid = str(root.get("SELF_GUID") or "").strip()
	self_name = str(root.get("SELF_NAME") or "").strip()

	if not self_guid:
		result.errors.append(f"{row_ref}: ROOT.SELF_GUID fehlt")
	elif self_guid != str(uid):
		result.errors.append(
			f"{row_ref}: ROOT.SELF_GUID ({self_guid}) passt nicht zu uid-Spalte ({uid})"
		)

	if not self_name:
		result.errors.append(f"{row_ref}: ROOT.SELF_NAME fehlt")
	elif name and self_name != name:
		result.warnings.append(
			f"{row_ref}: ROOT.SELF_NAME ({self_name}) != name-Spalte ({name})"
		)

	control = _as_dict(daten.get("CONTROL"))
	if control:
		_validate_upper_dict_keys(result, row_ref, control, "CONTROL")

	templates = _as_dict(daten.get("TEMPLATES"))
	if templates:
		_validate_upper_dict_keys(result, row_ref, templates, "TEMPLATES")

	if result.table_name == "sys_dialogdaten":
		tab_elements_raw = root.get("TAB_ELEMENTS")
		if tab_elements_raw is None:
			result.warnings.append(f"{row_ref}: ROOT.TAB_ELEMENTS fehlt")
			return

		tab_elements = _extract_tab_elements(tab_elements_raw)
		if not tab_elements:
			result.warnings.append(f"{row_ref}: ROOT.TAB_ELEMENTS ist leer/ungültig")
			return

		if isinstance(tab_elements_raw, dict):
			for key in tab_elements_raw.keys():
				if isinstance(key, str) and not _looks_like_tab_key(key):
					result.warnings.append(
						f"{row_ref}: TAB_ELEMENTS-Key '{key}' ist nicht im Format TAB_01..TAB_20"
					)

		for idx, tab in tab_elements.items():
			for req in ("GUID", "MODULE", "TABLE"):
				val = str(tab.get(req) or "").strip()
				if not val:
					result.errors.append(
						f"{row_ref}: TAB_ELEMENTS TAB_{idx:02d} hat Pflichtfeld {req} nicht gesetzt"
					)


async def _find_relation(conn: asyncpg.Connection, table_name: str) -> str | None:
	for relation in (f"pdvm_system.{table_name}", f"public.{table_name}", table_name):
		exists = await conn.fetchval("SELECT to_regclass($1)", relation)
		if exists:
			return relation
	return None


async def _validate_table(
	conn: asyncpg.Connection,
	table_name: str,
	*,
	include_historisch: bool,
) -> ValidationResult:
	result = ValidationResult(table_name=table_name)

	relation = await _find_relation(conn, table_name)
	if not relation:
		result.errors.append(f"Tabelle nicht gefunden: {table_name}")
		return result

	where_clause = "" if include_historisch else "WHERE historisch = 0"
	rows = await conn.fetch(
		f"""
		SELECT uid, name, daten
		FROM {relation}
		{where_clause}
		"""
	)

	for row in rows:
		data = row.get("daten")
		if isinstance(data, str):
			try:
				data = json.loads(data)
			except Exception:
				data = None
		_validate_single_row(
			result,
			uid=row["uid"],
			name=str(row.get("name") or ""),
			daten=data,
		)

	if table_name == "sys_control_dict":
		names = {
			str(r.get("name") or "").strip().upper()
			for r in rows
			if str(r.get("name") or "").strip()
		}
		missing = sorted(REQUIRED_BOOTSTRAP_CONTROLS - names)
		if missing:
			result.warnings.append(
				"Bootstrap-Controls fehlen: " + ", ".join(missing)
			)

	return result


async def main() -> int:
	parser = argparse.ArgumentParser(description="Validate PDVM_LINEAR_SCHEMA_V1")
	parser.add_argument(
		"--tables",
		default=",".join(DEFAULT_TABLES),
		help="Comma-separated Tabellenliste",
	)
	parser.add_argument(
		"--include-historisch",
		action="store_true",
		help="Validiert auch historisch=1 Datensätze",
	)
	parser.add_argument("--db-url", default=None, help="Optionale DB-URL")
	args = parser.parse_args()

	table_names = [t.strip() for t in args.tables.split(",") if t.strip()]

	if args.db_url:
		db_url = args.db_url
	else:
		cfg = await ConnectionManager.get_system_config("pdvm_system")
		db_url = cfg.to_url()

	conn = await asyncpg.connect(db_url)
	try:
		results = [
			await _validate_table(
				conn,
				table_name,
				include_historisch=args.include_historisch,
			)
			for table_name in table_names
		]
	finally:
		await conn.close()

	total_errors = 0
	total_warnings = 0
	total_rows = 0

	print("=== PDVM_LINEAR_SCHEMA_V1 Validator ===")
	for result in results:
		total_errors += len(result.errors)
		total_warnings += len(result.warnings)
		total_rows += result.checked

		print(f"\n[{result.table_name}] checked={result.checked} errors={len(result.errors)} warnings={len(result.warnings)}")
		for err in result.errors[:25]:
			print(f"  ERROR: {err}")
		if len(result.errors) > 25:
			print(f"  ... {len(result.errors) - 25} weitere Fehler")

		for warn in result.warnings[:25]:
			print(f"  WARN: {warn}")
		if len(result.warnings) > 25:
			print(f"  ... {len(result.warnings) - 25} weitere Warnungen")

	print("\n=== SUMMARY ===")
	print(f"Rows checked: {total_rows}")
	print(f"Errors:       {total_errors}")
	print(f"Warnings:     {total_warnings}")

	return 1 if total_errors else 0


if __name__ == "__main__":
	raise SystemExit(asyncio.run(main()))
