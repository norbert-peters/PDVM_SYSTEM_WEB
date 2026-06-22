"""
Phase D: Migration sprachbezogener Daten auf lineares Sprachmodell.

Ziele:
1. Sprachgruppen (z. B. DE-DE) auflösen und Sprache linear als Sprach-Property ablegen.
2. EN-US als zusätzliche Sprache pro Eintrag aufnehmen.
3. sys_dropdowndaten: ein Dropdown pro Datensatz (bei Mehrfachfeldern Split), mit OPTIONS.<key>.<lang>.
4. Mapping-Infos für mögliche Frame/View-Nachkonfiguration erzeugen.

Scope:
- sys_dropdowndaten
- sys_beschreibungen

Usage:
  python backend/tools/phaseD_migrate_infos_to_values_model.py
  python backend/tools/phaseD_migrate_infos_to_values_model.py --apply
  python backend/tools/phaseD_migrate_infos_to_values_model.py --output backend/reports/phaseD_migrate_infos_to_values_model_report.json
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import re
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.connection_manager import ConnectionManager

UID_555 = "55555555-5555-5555-5555-555555555555"
UID_666 = "66666666-6666-6666-6666-666666666666"
DE = "DE-DE"
EN = "EN-US"
SUPPORTED_LANGUAGES = [DE, EN]
MIGRATION_TAG = "phaseD_infos_values_linear_v2"


@dataclass
class TableMeta:
    table_name: str
    columns: List[str] = field(default_factory=list)

    @property
    def has_uid(self) -> bool:
        return "uid" in self.columns

    @property
    def has_daten(self) -> bool:
        return "daten" in self.columns

    @property
    def has_name(self) -> bool:
        return "name" in self.columns

    @property
    def has_historisch(self) -> bool:
        return "historisch" in self.columns

    @property
    def has_link_uid(self) -> bool:
        return "link_uid" in self.columns


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _norm_lang(value: Any) -> str:
    s = str(value or "").strip().upper()
    if re.fullmatch(r"[A-Z]{2}_[A-Z]{2}", s):
        s = s.replace("_", "-")
    return s


def _is_lang_key(key: str) -> bool:
    s = _norm_lang(key)
    return bool(re.fullmatch(r"[A-Z]{2}-[A-Z]{2}", s))


def _norm_key(value: Any) -> str:
    return str(value or "").strip().lower()


def _pick_value(entry: Dict[str, Any]) -> str:
    for k in ("text", "label", "value", "name"):
        v = entry.get(k)
        if v is not None and str(v).strip():
            return str(v)
    return ""


def _infer_text_type(text_key: str, entry: Dict[str, Any]) -> str:
    t = str(entry.get("type") or entry.get("text_type") or "").strip().lower()
    if t:
        return t
    k = text_key.lower()
    if "tooltip" in k:
        return "tooltip"
    if "help" in k or "hilfe" in k:
        return "help"
    if "menu" in k:
        return "menu"
    if "title" in k or "titel" in k:
        return "title"
    if "header" in k:
        return "header"
    return "label"


async def _get_table_meta(conn: asyncpg.Connection) -> Dict[str, TableMeta]:
    rows = await conn.fetch(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position
        """
    )
    by_table: Dict[str, List[str]] = {}
    for row in rows:
        t = str(row.get("table_name"))
        c = str(row.get("column_name"))
        by_table.setdefault(t, []).append(c)
    return {t: TableMeta(table_name=t, columns=cols) for t, cols in by_table.items()}


async def _load_active_rows(conn: asyncpg.Connection, meta: TableMeta) -> List[Dict[str, Any]]:
    where_hist = "WHERE COALESCE(historisch, 0) = 0" if meta.has_historisch else ""
    rows = await conn.fetch(
        f'''
        SELECT uid::text AS uid, name, link_uid::text AS link_uid, daten
        FROM "{meta.table_name}"
        {where_hist}
        '''
    )
    out: List[Dict[str, Any]] = []
    for row in rows:
        uid = str(row.get("uid") or "")
        if uid in {UID_555, UID_666}:
            continue
        out.append(
            {
                "uid": uid,
                "name": str(row.get("name") or ""),
                "link_uid": str(row.get("link_uid") or "") if row.get("link_uid") else None,
                "daten": _as_dict(row.get("daten")),
            }
        )
    return out


async def _update_row(conn: asyncpg.Connection, meta: TableMeta, *, uid: str, name: str, link_uid: Optional[str], daten: Dict[str, Any]) -> None:
    if meta.has_link_uid:
        await conn.execute(
            f'UPDATE "{meta.table_name}" SET daten = $1::jsonb, name = $2, link_uid = $3::uuid WHERE uid::text = $4',
            json.dumps(daten, ensure_ascii=False),
            name,
            uuid.UUID(link_uid) if link_uid else None,
            uid,
        )
    else:
        await conn.execute(
            f'UPDATE "{meta.table_name}" SET daten = $1::jsonb, name = $2 WHERE uid::text = $3',
            json.dumps(daten, ensure_ascii=False),
            name,
            uid,
        )


async def _insert_row(conn: asyncpg.Connection, meta: TableMeta, *, uid: str, name: str, link_uid: Optional[str], daten: Dict[str, Any]) -> None:
    cols: List[str] = ["uid", "daten"]
    vals: List[Any] = [uuid.UUID(uid), json.dumps(daten, ensure_ascii=False)]
    if meta.has_name:
        cols.append("name")
        vals.append(name)
    if meta.has_historisch:
        cols.append("historisch")
        vals.append(0)
    if meta.has_link_uid:
        cols.append("link_uid")
        vals.append(uuid.UUID(link_uid) if link_uid else None)

    placeholders = ", ".join(f"${i+1}" for i in range(len(cols)))
    col_sql = ", ".join(f'"{c}"' for c in cols)
    await conn.execute(f'INSERT INTO "{meta.table_name}" ({col_sql}) VALUES ({placeholders})', *vals)


def _build_dropdown_records_from_row(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    data = _as_dict(row.get("daten"))
    root = _as_dict(data.get("ROOT"))
    default_lang = _norm_lang(root.get("DEFAULT_LANGUAGE") or DE) or DE

    # Bereits im Zielmodell? (strict linear)
    if isinstance(data.get("OPTIONS"), dict):
        field_key = _norm_key(root.get("FIELD_KEY") or row.get("name") or row.get("uid"))
        opts = _as_dict(data.get("OPTIONS"))
        options_out: Dict[str, Any] = {}
        for ok, ov in opts.items():
            ovd = _as_dict(ov)
            values = {
                str(k): v
                for k, v in ovd.items()
                if str(k or "").strip().upper() not in {"KEY", "VALUE", "VALUES", "LABEL", "NAME"}
            }
            de_val = str(values.get(DE) or values.get(default_lang) or "")
            en_val = str(values.get(EN) or de_val)
            options_out[str(ok)] = {DE: de_val, EN: en_val}

        payload = {
            "ROOT": {
                **root,
                "SELF_GUID": str(row.get("uid") or ""),
                "SELF_NAME": str(row.get("name") or ""),
                "TABLE": "sys_dropdowndaten",
                "RECORD_TYPE": "dropdown_definition",
                "FIELD_KEY": field_key,
                "DEFAULT_LANGUAGE": DE,
                "SUPPORTED_LANGUAGES": SUPPORTED_LANGUAGES,
                "MIGRATION_TAG": MIGRATION_TAG,
            },
            "OPTIONS": options_out,
        }
        return [payload]

    # Altes Modell mit Sprachgruppen + edit_list.
    field_map: Dict[str, Dict[str, Dict[str, str]]] = {}
    for top_key, top_val in data.items():
        lang = _norm_lang(top_key)
        if not _is_lang_key(lang):
            continue
        lang_obj = _as_dict(top_val)
        for item_key, item_val in lang_obj.items():
            item = _as_dict(item_val)
            edit_list = item.get("edit_list")
            if not isinstance(edit_list, list):
                continue
            field_key = _norm_key(item.get("list_name") or item.get("name") or item_key)
            if not field_key:
                continue
            field_map.setdefault(field_key, {})
            for opt in edit_list:
                od = _as_dict(opt)
                o_key = str(od.get("key") or "").strip()
                if not o_key:
                    continue
                o_val = str(od.get("value") or "")
                field_map[field_key].setdefault(o_key, {})[lang] = o_val

    records: List[Dict[str, Any]] = []
    for field_key, options_by_key in sorted(field_map.items(), key=lambda kv: kv[0]):
        options_out: Dict[str, Any] = {}
        for opt_key, values in sorted(options_by_key.items(), key=lambda kv: kv[0]):
            de_val = str(values.get(DE) or values.get(default_lang) or "")
            en_val = str(values.get(EN) or de_val)
            options_out[opt_key] = {DE: de_val, EN: en_val}

        payload = {
            "ROOT": {
                "SELF_GUID": str(row.get("uid") or ""),
                "SELF_NAME": str(row.get("name") or ""),
                "TABLE": "sys_dropdowndaten",
                "RECORD_TYPE": "dropdown_definition",
                "FIELD_KEY": field_key,
                "DEFAULT_LANGUAGE": DE,
                "SUPPORTED_LANGUAGES": SUPPORTED_LANGUAGES,
                "MIGRATION_TAG": MIGRATION_TAG,
            },
            "OPTIONS": options_out,
        }
        records.append(payload)

    return records


def _build_beschreibungen_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    data = _as_dict(row.get("daten"))
    root_old = _as_dict(data.get("ROOT"))

    texts: Dict[str, Dict[str, Any]] = {}

    # Bereits im Zielmodell?
    if isinstance(data.get("TEXTS"), dict):
        for tk, tv in _as_dict(data.get("TEXTS")).items():
            tentry = _as_dict(tv)
            values = _as_dict(tentry.get("values"))
            de_val = str(values.get(DE) or values.get(root_old.get("DEFAULT_LANGUAGE") or DE) or "")
            en_val = str(values.get(EN) or de_val)
            texts[str(tk)] = {
                "text_key": str(tk),
                "text_type": str(tentry.get("text_type") or _infer_text_type(str(tk), tentry)),
                "values": {DE: de_val, EN: en_val},
            }
    else:
        for top_key, top_val in data.items():
            lang = _norm_lang(top_key)
            if not _is_lang_key(lang):
                continue
            lang_obj = _as_dict(top_val)
            for item_key, item_val in lang_obj.items():
                item = _as_dict(item_val)
                text_key = str(item.get("key") or item.get("name") or item_key)
                if not text_key:
                    continue
                entry = texts.setdefault(
                    text_key,
                    {
                        "text_key": text_key,
                        "text_type": _infer_text_type(text_key, item),
                        "values": {},
                    },
                )
                entry["values"][lang] = _pick_value(item)

        for tk, tv in texts.items():
            values = _as_dict(tv.get("values"))
            de_val = str(values.get(DE) or values.get(root_old.get("DEFAULT_LANGUAGE") or DE) or "")
            en_val = str(values.get(EN) or de_val)
            tv["values"] = {DE: de_val, EN: en_val}

    return {
        "ROOT": {
            **root_old,
            "SELF_GUID": str(row.get("uid") or ""),
            "SELF_NAME": str(row.get("name") or ""),
            "TABLE": "sys_beschreibungen",
            "RECORD_TYPE": "text_definition",
            "DEFAULT_LANGUAGE": DE,
            "SUPPORTED_LANGUAGES": SUPPORTED_LANGUAGES,
            "MIGRATION_TAG": MIGRATION_TAG,
        },
        "TEXTS": texts,
    }


async def build_report(apply: bool) -> Dict[str, Any]:
    cfg = await ConnectionManager.get_system_config()
    conn = await asyncpg.connect(**cfg.to_dict())

    report: Dict[str, Any] = {
        "phase": "phaseD",
        "title": "Migrate infos tables to linear language model",
        "mode": "apply" if apply else "dry-run",
        "database": cfg.database,
        "summary": {
            "tables_total": 2,
            "rows_scanned": 0,
            "rows_updated": 0,
            "rows_inserted": 0,
            "rows_split_created": 0,
            "db_errors": 0,
        },
        "tables": [],
    }

    try:
        metas = await _get_table_meta(conn)

        # sys_dropdowndaten
        dd_meta = metas.get("sys_dropdowndaten")
        dd_entry: Dict[str, Any] = {
            "table": "sys_dropdowndaten",
            "rows_scanned": 0,
            "rows_updated": 0,
            "rows_inserted": 0,
            "rows_split_created": 0,
            "mappings": [],
            "error": None,
        }

        if not dd_meta or not (dd_meta.has_uid and dd_meta.has_daten):
            dd_entry["error"] = "table_missing_or_invalid"
            report["summary"]["db_errors"] += 1
        else:
            dd_rows = await _load_active_rows(conn, dd_meta)
            for row in dd_rows:
                dd_entry["rows_scanned"] += 1
                report["summary"]["rows_scanned"] += 1

                recs = _build_dropdown_records_from_row(row)
                if not recs:
                    continue

                source_uid = str(row.get("uid") or "")
                source_name = str(row.get("name") or "")
                split_group_uid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{MIGRATION_TAG}:split:{source_uid}"))

                for idx, payload in enumerate(recs):
                    field_key = _norm_key(_as_dict(payload.get("ROOT")).get("FIELD_KEY"))
                    if idx == 0:
                        target_uid = source_uid
                        target_name = source_name or field_key
                    else:
                        target_uid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{MIGRATION_TAG}:{source_uid}:{field_key}"))
                        target_name = f"{source_name}::{field_key}" if source_name else field_key

                    root = _as_dict(payload.get("ROOT"))
                    root["SELF_GUID"] = target_uid
                    root["SELF_NAME"] = target_name
                    payload["ROOT"] = root

                    link_uid = split_group_uid if len(recs) > 1 else (row.get("link_uid") or None)

                    if idx == 0:
                        old_data = _as_dict(row.get("daten"))
                        if old_data != payload:
                            dd_entry["rows_updated"] += 1
                            report["summary"]["rows_updated"] += 1
                            if apply:
                                await _update_row(
                                    conn,
                                    dd_meta,
                                    uid=target_uid,
                                    name=target_name,
                                    link_uid=link_uid,
                                    daten=payload,
                                )
                    else:
                        dd_entry["rows_inserted"] += 1
                        dd_entry["rows_split_created"] += 1
                        report["summary"]["rows_inserted"] += 1
                        report["summary"]["rows_split_created"] += 1
                        if apply:
                            await _insert_row(
                                conn,
                                dd_meta,
                                uid=target_uid,
                                name=target_name,
                                link_uid=link_uid,
                                daten=payload,
                            )

                    dd_entry["mappings"].append(
                        {
                            "source_uid": source_uid,
                            "source_name": source_name,
                            "target_uid": target_uid,
                            "target_name": target_name,
                            "field_key": field_key,
                        }
                    )

        report["tables"].append(dd_entry)

        # sys_beschreibungen
        be_meta = metas.get("sys_beschreibungen")
        be_entry: Dict[str, Any] = {
            "table": "sys_beschreibungen",
            "rows_scanned": 0,
            "rows_updated": 0,
            "error": None,
        }

        if not be_meta or not (be_meta.has_uid and be_meta.has_daten):
            be_entry["error"] = "table_missing_or_invalid"
            report["summary"]["db_errors"] += 1
        else:
            be_rows = await _load_active_rows(conn, be_meta)
            for row in be_rows:
                be_entry["rows_scanned"] += 1
                report["summary"]["rows_scanned"] += 1

                payload = _build_beschreibungen_payload(row)
                old_data = _as_dict(row.get("daten"))
                if payload != old_data:
                    be_entry["rows_updated"] += 1
                    report["summary"]["rows_updated"] += 1
                    if apply:
                        await _update_row(
                            conn,
                            be_meta,
                            uid=str(row.get("uid") or ""),
                            name=str(row.get("name") or ""),
                            link_uid=row.get("link_uid"),
                            daten=payload,
                        )

        report["tables"].append(be_entry)

    except Exception as exc:
        report["summary"]["db_errors"] += 1
        report["error"] = f"process_failed: {exc}"
    finally:
        await conn.close()

    return report


def _default_output_path() -> Path:
    return BACKEND_DIR / "reports" / "phaseD_migrate_infos_to_values_model_report.json"


def _print_summary(report: Dict[str, Any]) -> None:
    s = report.get("summary", {})
    print("\n=== Phase D Infos Linear Migration ===")
    print(f"Mode: {report.get('mode')}")
    print(f"Rows scanned: {s.get('rows_scanned', 0)}")
    print(f"Rows updated: {s.get('rows_updated', 0)}")
    print(f"Rows inserted: {s.get('rows_inserted', 0)}")
    print(f"Rows split created: {s.get('rows_split_created', 0)}")
    print(f"DB errors: {s.get('db_errors', 0)}")


async def _run(args: argparse.Namespace) -> int:
    report = await build_report(apply=bool(args.apply))
    _print_summary(report)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nReport geschrieben: {output}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase D migrate infos to linear model")
    parser.add_argument("--apply", action="store_true", help="Änderungen schreiben")
    parser.add_argument("--output", default=str(_default_output_path()), help="Pfad für JSON-Report")
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
