"""Read-only Audit der PDVM-Systemdaten gegen ARCHITECTURE_RULES.md.

Aufruf (aus backend/):
    ..\\.venv\\Scripts\\python.exe tools\\audit_system_data.py [--db pdvm_system --db pdvm_standard ...] [--out ..\\docs\\reports\\AUDIT.md]

Es werden ausschliesslich SELECTs ausgefuehrt (Session ist read-only).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import unquote, urlparse

import asyncpg

U000 = "00000000-0000-0000-0000-000000000000"
U555 = "55555555-5555-5555-5555-555555555555"
U666 = "66666666-6666-6666-6666-666666666666"
RESERVED = {U000, U555, U666}
OPEN_SENTINEL = "9999365.99999"
PDVM_TIME = re.compile(r"^\d{7}\.\d+$")
ROOT_SELF_TIME = ("SELF_CREATED_AT", "SELF_MODIFIED_AT", "SELF_GILT_BIS")
PREFIXES = ("sys_", "msy_", "dev_", "tst_", "crm_", "pps_")
GUID_KEY = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def load_env_url() -> urlparse:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("DATABASE_URL_AUTH="):
            return urlparse(line.split("=", 1)[1].strip().strip('"'))
    raise SystemExit("DATABASE_URL_AUTH nicht in backend/.env gefunden")


def as_dict(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


class Report:
    def __init__(self) -> None:
        self.findings: list[tuple[str, str, str, str]] = []  # (db, rule, table, text)
        self.stats: dict[str, dict[str, int]] = defaultdict(dict)

    def add(self, db: str, rule: str, table: str, text: str) -> None:
        self.findings.append((db, rule, table, text))


async def audit_generic(conn, db: str, table: str, rep: Report) -> list:
    rows = await conn.fetch(
        f'select uid, link_uid, name, gilt_bis, daten from "{table}"'
    )
    rep.stats[db][table] = len(rows)
    by_uid = {str(r["uid"]): r for r in rows}

    for res in (U000, U555, U666):
        if res not in by_uid:
            rep.add(db, "1.12", table, f"Basissatz {res[:2]}... fehlt")

    r666 = by_uid.get(U666)
    if r666 is not None:
        d = as_dict(r666["daten"])
        if "TABLE_INFO" in d:
            rep.add(db, "1.12a", table, "666: daten.TABLE_INFO ist ungueltig (gehoert nach daten.TEMPLATES.TABLE_INFO)")
        if "TEMPLATES" not in d and "TEMPLATE" not in d:
            rep.add(db, "1.12a", table, "666: Gruppe TEMPLATES fehlt")
        elif "TABLE_INFO" not in as_dict(d.get("TEMPLATES") or d.get("TEMPLATE")):
            rep.add(db, "1.12c", table, "666: TEMPLATES.TABLE_INFO fehlt")
    r555 = by_uid.get(U555)
    if r555 is not None and not as_dict(r555["daten"]):
        rep.add(db, "1.13", table, "555: daten leer (Basis fuer Neuanlage)")

    for r in rows:
        uid = str(r["uid"])
        if uid in RESERVED:
            continue
        d = as_dict(r["daten"])
        root = as_dict(d.get("ROOT"))
        label = f"{r['name']} ({uid[:8]})"
        if not root:
            rep.add(db, "1.12b", table, f"{label}: ROOT fehlt")
            continue
        if "TABLE_INFO" in d:
            rep.add(db, "1.12c", table, f"{label}: TABLE_INFO in Fachdatensatz")
        self_name = root.get("SELF_NAME")
        if self_name and self_name != r["name"]:
            rep.add(db, "1.22", table, f"{label}: SELF_NAME '{self_name}' != name '{r['name']}'")
        if r["link_uid"] is None:
            rep.add(db, "1.14", table, f"{label}: link_uid fehlt")
        elif root.get("SELF_LINK_UID") and root["SELF_LINK_UID"] != str(r["link_uid"]):
            rep.add(db, "1.14", table, f"{label}: ROOT.SELF_LINK_UID != link_uid")
        guid = root.get("SELF_GUID")
        if guid and guid != uid:
            rep.add(db, "1.14", table, f"{label}: ROOT.SELF_GUID != uid")
        for key in ROOT_SELF_TIME:
            val = root.get(key)
            if val is not None and not (isinstance(val, str) and PDVM_TIME.match(val)):
                rep.add(db, "1.9", table, f"{label}: ROOT.{key}='{val}' nicht im PDVM-Format")
        sg = root.get("SELF_GILT_BIS")
        if sg and sg == OPEN_SENTINEL and r["gilt_bis"] is not None and r["gilt_bis"].year != 9999:
            rep.add(db, "1.23", table, f"{label}: SELF_GILT_BIS offen, Spalte gilt_bis={r['gilt_bis']}")
    return rows


def control_allowed(rows) -> set[str]:
    for r in rows:
        if str(r["uid"]) == U666:
            d = as_dict(r["daten"])
            ctrl = as_dict(d.get("CONTROL")) or as_dict(as_dict(d.get("TEMPLATES")).get("CONTROL"))
            return {k.upper() for k in ctrl}
    return set()


def audit_control_dict(db: str, rows, rep: Report) -> None:
    allowed = control_allowed(rows)
    r666 = next((r for r in rows if str(r["uid"]) == U666), None)
    if r666 is not None:
        d666 = as_dict(r666["daten"])
        tmpl_ctrl = as_dict(as_dict(d666.get("TEMPLATES")).get("CONTROL"))
        if "CONTROL" not in d666:
            rep.add(db, "1.10a", "sys_control_dict", "Muttercontrol: daten.CONTROL fehlt im 666-Satz")
        elif as_dict(d666.get("CONTROL")) != tmpl_ctrl:
            rep.add(db, "1.10a", "sys_control_dict", "Muttercontrol: daten.CONTROL und daten.TEMPLATES.CONTROL nicht identisch")
    unknown_props: Counter = Counter()
    for r in rows:
        uid = str(r["uid"])
        if uid in RESERVED:
            continue
        d = as_dict(r["daten"])
        label = f"{r['name']} ({uid[:8]})"
        extra = set(d) - {"ROOT", "CONTROL"}
        if extra:
            rep.add(db, "1.10", "sys_control_dict", f"{label}: unerlaubte Gruppen {sorted(extra)}")
        ctrl = as_dict(d.get("CONTROL"))
        if not ctrl:
            rep.add(db, "1.10", "sys_control_dict", f"{label}: CONTROL fehlt")
            continue
        field = ctrl.get("FIELD") or ctrl.get("FELD")
        if not field:
            rep.add(db, "1.10", "sys_control_dict", f"{label}: FIELD/FELD fehlt")
        elif field != str(field).upper():
            rep.add(db, "1.10", "sys_control_dict", f"{label}: FIELD '{field}' nicht GROSS")
        if "FIELD" in ctrl and "FELD" in ctrl:
            rep.add(db, "1.12b", "sys_control_dict", f"{label}: FIELD und FELD parallel (Alias-Verbot)")
        table = str(ctrl.get("TABLE") or "")
        if field and table:
            prefix = table.split("_")[0].upper()
            group = str(ctrl.get("GRUPPE") or "").replace(".", "_").strip("_").upper()
            base_name = f"{prefix}_{field}".upper()
            name = str(r["name"] or "").upper()
            # Regel 1.10: <PREFIX>_<FIELD>; bei gleichem FIELD in anderer Gruppe <PREFIX>_<GRUPPE>_<FIELD>, ggf. mit Zaehler
            ok = (
                name == base_name
                or bool(re.fullmatch(re.escape(base_name) + r"_\d+", name))
                or (group and (name == f"{prefix}_{group}_{field}".upper()
                               or bool(re.fullmatch(re.escape(f"{prefix}_{group}_{field}".upper()) + r"_\d+", name))))
            )
            if not ok:
                rep.add(db, "1.10", "sys_control_dict", f"{label}: name '{r['name']}' != '{base_name}'")
        for key in ctrl:
            if allowed and key.upper() not in allowed:
                unknown_props[key] += 1
    for key, n in unknown_props.most_common():
        rep.add(db, "1.10a", "sys_control_dict", f"Eigenschaft '{key}' ({n}x) nicht im Muttercontrol")


def audit_frames(db: str, rows, control_uids: set[str], allowed: set[str], rep: Report) -> None:
    legacy_keys: Counter = Counter()
    missing_ref = 0
    total_fields = 0
    for r in rows:
        uid = str(r["uid"])
        if uid in RESERVED:
            continue
        fields = as_dict(as_dict(r["daten"]).get("FIELDS"))
        for fkey, fval in fields.items():
            if not GUID_KEY.match(str(fkey)):
                continue  # benannte Struktur-Eintraege (element_list-Frames) sind keine Controls
            fv = as_dict(fval)
            feld = fv.get("feld") or fv.get("FELD")
            if isinstance(feld, str) and feld and feld != feld.upper():
                continue  # dokumentierte Ausnahme: Kleinschreib-Datenschluessel (sys_menudaten.MENU)
            total_fields += 1
            if control_uids and fkey not in control_uids:
                missing_ref += 1
            for k in fv:
                if k != k.upper() and k != "dict_ref":
                    legacy_keys[k] += 1
    rep.stats[db]["sys_framedaten.FIELDS"] = total_fields
    if missing_ref:
        rep.add(db, "1.10b", "sys_framedaten", f"{missing_ref} FIELDS-Eintraege verweisen auf keine vorhandene sys_control_dict-UID")
    if legacy_keys:
        top = ", ".join(f"{k}:{n}" for k, n in legacy_keys.most_common(12))
        rep.add(db, "1.10b", "sys_framedaten", f"FIELDS mit Kleinschreib-Legacy-Eigenschaften (Control-Semantik im Frame statt in sys_control_dict): {top}")


def audit_dialogs(db: str, rows, frame_uids: set[str], view_uids: set[str], rep: Report) -> None:
    for r in rows:
        uid = str(r["uid"])
        if uid in RESERVED:
            continue
        root = as_dict(as_dict(r["daten"]).get("ROOT"))
        tabs = as_dict(root.get("TAB_ELEMENTS"))
        label = f"{r['name']} ({uid[:8]})"
        ordered = sorted(tabs.values(), key=lambda t: as_dict(t).get("TAB", 0))
        if str(root.get("DIALOG_TYPE", "")).lower() == "work" and ordered:
            if str(as_dict(ordered[-1]).get("MODULE", "")).lower() != "acti":
                rep.add(db, "2.10", "sys_dialogdaten", f"{label}: work-Dialog ohne acti-Endtab")
        for t in ordered:
            t = as_dict(t)
            guid, module = t.get("GUID"), str(t.get("MODULE", "")).lower()
            if not guid:
                continue
            if module == "view" and view_uids and guid not in view_uids:
                rep.add(db, "2.7", "sys_dialogdaten", f"{label}: Tab {t.get('TAB')} view-GUID {guid[:8]} nicht in sys_viewdaten")
            if module == "edit" and t.get("EDIT_TYPE") == "pdvm_edit" and frame_uids and guid not in frame_uids:
                rep.add(db, "2.7", "sys_dialogdaten", f"{label}: Tab {t.get('TAB')} frame-GUID {guid[:8]} nicht in sys_framedaten")


def audit_views(db: str, rows, rep: Report) -> None:
    for r in rows:
        uid = str(r["uid"])
        if uid in RESERVED:
            continue
        d = as_dict(r["daten"])
        table = str(as_dict(d.get("ROOT")).get("TABLE", "")).upper()
        groups = set(d) - {"ROOT"}
        allowed = {table, "**SYSTEM", "SYSTEM"}
        label = f"{r['name']} ({uid[:8]})"
        if not groups:
            rep.add(db, "1.21", "sys_viewdaten", f"{label}: keine Datengruppe neben ROOT")
        bad = groups - allowed
        if bad:
            rep.add(db, "1.21", "sys_viewdaten", f"{label}: unerlaubte Gruppen {sorted(bad)}")


async def audit_db(host_url, db: str, rep: Report) -> None:
    conn = await asyncpg.connect(
        host=host_url.hostname, port=host_url.port, user=host_url.username,
        password=unquote(host_url.password), database=db,
        server_settings={"default_transaction_read_only": "on"},
    )
    try:
        tables = [
            r["table_name"] for r in await conn.fetch(
                "select table_name from information_schema.tables where table_schema='public' and table_type='BASE TABLE' order by 1"
            )
        ]
        data: dict[str, list] = {}
        for t in tables:
            cols = {r["column_name"] for r in await conn.fetch(
                "select column_name from information_schema.columns where table_schema='public' and table_name=$1", t)}
            if not {"uid", "daten", "name"} <= cols:
                rep.add(db, "1.1", t, "Tabelle folgt nicht dem einheitlichen Layout (uid/daten/name)")
                continue
            if "_" not in t:
                rep.add(db, "1.7a", t, "Tabelle ohne Praefix")
            if t.endswith("_feld_aenderungshistorie"):
                rep.stats[db][t] = await conn.fetchval(f'select count(*) from "{t}"')
                continue
            if "link_uid" not in cols:
                rep.add(db, "1.14", t, "Spalte link_uid fehlt")
            if not any(t.startswith(p) for p in PREFIXES):
                rep.add(db, "1.7a", t, "unbekannter Praefix")
            sel = "uid, link_uid, name, gilt_bis, daten" if "link_uid" in cols else "uid, null::uuid link_uid, name, gilt_bis, daten"
            rows = await conn.fetch(f'select {sel} from "{t}"')
            data[t] = rows
            await audit_generic_rows(conn, db, t, rows, rep)
        if "sys_control_dict" in data:
            audit_control_dict(db, data["sys_control_dict"], rep)
        if "sys_framedaten" in data:
            control_uids = {str(r["uid"]) for r in data.get("sys_control_dict", [])}
            audit_frames(db, data["sys_framedaten"], control_uids, control_allowed(data.get("sys_control_dict", [])), rep)
        if "sys_dialogdaten" in data:
            audit_dialogs(db, data["sys_dialogdaten"],
                          {str(r["uid"]) for r in data.get("sys_framedaten", [])},
                          {str(r["uid"]) for r in data.get("sys_viewdaten", [])}, rep)
        if "sys_viewdaten" in data:
            audit_views(db, data["sys_viewdaten"], rep)
    finally:
        await conn.close()


async def audit_generic_rows(conn, db: str, table: str, rows, rep: Report) -> None:
    rep.stats[db][table] = len(rows)
    by_uid = {str(r["uid"]): r for r in rows}
    for res in (U000, U555, U666):
        if res not in by_uid:
            rep.add(db, "1.12", table, f"Basissatz {res[:2]}... fehlt")
    r666 = by_uid.get(U666)
    if r666 is not None:
        d = as_dict(r666["daten"])
        if "TABLE_INFO" in d:
            rep.add(db, "1.12a", table, "666: daten.TABLE_INFO ist ungueltig (gehoert nach daten.TEMPLATES.TABLE_INFO)")
        tmpl = as_dict(d.get("TEMPLATES") or d.get("TEMPLATE"))
        if not tmpl:
            rep.add(db, "1.12a", table, "666: Gruppe TEMPLATES fehlt")
        elif "TABLE_INFO" not in tmpl:
            rep.add(db, "1.12c", table, "666: TEMPLATES.TABLE_INFO fehlt")
    r555 = by_uid.get(U555)
    if r555 is not None and not as_dict(r555["daten"]):
        rep.add(db, "1.13", table, "555: daten leer")
    for r in rows:
        uid = str(r["uid"])
        if uid in RESERVED:
            continue
        d = as_dict(r["daten"])
        root = as_dict(d.get("ROOT"))
        label = f"{r['name']} ({uid[:8]})"
        if not root:
            rep.add(db, "1.12b", table, f"{label}: ROOT fehlt")
            continue
        if "TABLE_INFO" in d:
            rep.add(db, "1.12c", table, f"{label}: TABLE_INFO in Fachdatensatz")
        sn = root.get("SELF_NAME")
        if sn and sn != r["name"]:
            rep.add(db, "1.22", table, f"{label}: SELF_NAME '{sn}' != name '{r['name']}'")
        if r["link_uid"] is None:
            rep.add(db, "1.14", table, f"{label}: link_uid fehlt")
        elif root.get("SELF_LINK_UID") and root["SELF_LINK_UID"] != str(r["link_uid"]):
            rep.add(db, "1.14", table, f"{label}: ROOT.SELF_LINK_UID != link_uid")
        guid = root.get("SELF_GUID")
        if guid and guid != uid:
            rep.add(db, "1.14", table, f"{label}: ROOT.SELF_GUID != uid")
        for key in ROOT_SELF_TIME:
            val = root.get(key)
            if val is not None and not (isinstance(val, str) and PDVM_TIME.match(val)):
                rep.add(db, "1.9", table, f"{label}: ROOT.{key}='{val}' nicht im PDVM-Format")


def render(rep: Report, dbs: list[str]) -> str:
    out = ["# Audit Systemdaten (read-only)", ""]
    out.append("Pruefgrundlage: ARCHITECTURE_RULES.md. Erzeugt von `backend/tools/audit_system_data.py`.")
    out.append("")
    out.append("## Bestand")
    for db in dbs:
        out.append(f"- **{db}**: " + ", ".join(f"{t}={n}" for t, n in sorted(rep.stats[db].items())))
    out.append("")
    out.append("## Zusammenfassung je Regel")
    counts = Counter((db, rule) for db, rule, _, _ in rep.findings)
    for (db, rule), n in sorted(counts.items()):
        out.append(f"- {db} / Regel {rule}: {n}")
    out.append("")
    out.append("## Befunde")
    grouped: dict[tuple, list[str]] = defaultdict(list)
    for db, rule, table, text in rep.findings:
        grouped[(db, rule, table)].append(text)
    for (db, rule, table), texts in sorted(grouped.items()):
        out.append(f"### {db} / {table} / Regel {rule} ({len(texts)})")
        for t in texts[:15]:
            out.append(f"- {t}")
        if len(texts) > 15:
            out.append(f"- ... {len(texts) - 15} weitere")
        out.append("")
    return "\n".join(out)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", action="append")
    ap.add_argument("--out")
    args = ap.parse_args()
    dbs = args.db or ["pdvm_system", "pdvm_standard", "mandant"]
    url = load_env_url()
    rep = Report()
    for db in dbs:
        await audit_db(url, db, rep)
    text = render(rep, dbs)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)


if __name__ == "__main__":
    asyncio.run(main())
