"""Phase 5 / Restbefunde in pdvm_system (Regeln 1.21, 1.22, 1.10, Menue-Tabellennamen).

Aufruf (aus backend/):
    ..\\.venv\\Scripts\\python.exe tools\\phase5_fix_misc.py                      # Dry-Run
    ..\\.venv\\Scripts\\python.exe tools\\phase5_fix_misc.py --apply --confirm-backup

1. Menue-/Frame-Daten: Verweise auf nicht (mehr) vorhandene Legacy-Tabellen werden auf die heutigen Namen
   umgestellt (sys_security -> msy_security, sys_benutzer -> asy_benutzer, ...).
2. SYS_PRENT_GUID (Tippfehler-Duplikat von SYS_PARENT_GUID): Frames verweisen auf SYS_PARENT_GUID, das Duplikat
   wird geloescht.
3. sys_viewdaten ohne Datengruppe neben ROOT (Regel 1.21): leere Gruppe `**SYSTEM` ergaenzen.
4. sys_dropdowndaten ohne Namen: bei fehlender Referenz loeschen, sonst name := ROOT.SELF_NAME.
Alle Aenderungen in einer Transaktion, vorher Snapshot der betroffenen Zeilen nach backend/reports/.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.pdvm_datetime import now_pdvm_str  # noqa: E402
from audit_system_data import as_dict, load_env_url  # noqa: E402
from seed_base_records import connect  # noqa: E402

TABLE_RENAMES = {
    "sys_security": "msy_security",
    "sys_error_log": "msy_error_log",
    "sys_systemsteuerung": "msy_systemsteuerung",
    "sys_ext_table_man": "msy_ext_table",
    "sys_anwendungsdaten": "msy_anwendungsdaten",
    "sys_benutzer": "asy_benutzer",
    "sys_mandanten": "asy_mandanten",
    "sys_error_acknowledgements": "msy_error_acknowledgments",
    "sys_error_acknowledgments": "msy_error_acknowledgments",
}
PRENT_PREFIX, PARENT_PREFIX = "458b92e5", "8e19dd43"


def rename_tables(obj, path=""):
    """Ersetzt exakte Stringwerte von Legacy-Tabellennamen; liefert (neu, Anzahl)."""
    count = 0
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            nv, n = rename_tables(v)
            out[k] = nv
            count += n
        return out, count
    if isinstance(obj, list):
        out = []
        for v in obj:
            nv, n = rename_tables(v)
            out.append(nv)
            count += n
        return out, count
    if isinstance(obj, str) and obj.strip().lower() in TABLE_RENAMES:
        return TABLE_RENAMES[obj.strip().lower()], 1
    return obj, 0


async def run(args) -> int:
    conn = await connect(load_env_url(), "pdvm_system", read_only=not args.apply)
    stamp = now_pdvm_str()
    lines = [f"# Phase 5: Restbefunde pdvm_system ({'APPLY' if args.apply else 'Dry-Run'})", ""]
    updates: list[tuple[str, str, str, dict, str | None]] = []  # (table, uid, name, daten, new_name)
    deletes: list[tuple[str, str]] = []
    before: list[dict] = []
    try:
        # 1) Tabellennamen in Menues/Frames
        for table in ("sys_menudaten", "sys_framedaten", "sys_dialogdaten", "sys_viewdaten"):
            for r in await conn.fetch(f"select uid, name, daten from {table}"):
                old = as_dict(r["daten"])
                new, n = rename_tables(old)
                if n:
                    updates.append((table, str(r["uid"]), r["name"], new, None))
                    before.append({"table": table, "uid": str(r["uid"]), "name": r["name"], "daten_before": old})
                    lines.append(f"- `{table}` {r['name']} ({str(r['uid'])[:8]}): {n} Tabellenverweise umgestellt")

        # 2) SYS_PRENT_GUID
        prent = await conn.fetchrow("select uid, name, daten from sys_control_dict where uid::text like $1", PRENT_PREFIX + "%")
        parent = await conn.fetchrow("select uid from sys_control_dict where uid::text like $1", PARENT_PREFIX + "%")
        if prent and parent:
            pu, qu = str(prent["uid"]), str(parent["uid"])
            for r in await conn.fetch("select uid, name, daten from sys_framedaten where daten::text like $1", f"%{pu}%"):
                d = as_dict(r["daten"])
                fields = as_dict(d.get("FIELDS"))
                if pu in fields:
                    if qu in fields:
                        lines.append(f"- Frame {r['name']}: enthaelt bereits SYS_PARENT_GUID - Duplikat-Eintrag entfernt")
                        fields.pop(pu)
                    else:
                        fields = {(qu if k == pu else k): v for k, v in fields.items()}
                        lines.append(f"- Frame {r['name']}: SYS_PRENT_GUID -> SYS_PARENT_GUID")
                    nd = copy.deepcopy(d)
                    nd["FIELDS"] = fields
                    updates.append(("sys_framedaten", str(r["uid"]), r["name"], nd, None))
                    before.append({"table": "sys_framedaten", "uid": str(r["uid"]), "name": r["name"], "daten_before": d})
            deletes.append(("sys_control_dict", pu))
            before.append({"table": "sys_control_dict", "uid": pu, "name": prent["name"], "daten_before": as_dict(prent["daten"]), "deleted": True})
            lines.append(f"- Control SYS_PRENT_GUID ({pu[:8]}) geloescht")

        # 3) Views ohne Datengruppe
        for r in await conn.fetch("select uid, name, daten from sys_viewdaten"):
            d = as_dict(r["daten"])
            if str(r["uid"])[:2] in ("00", "55", "66"):
                continue
            if set(d) <= {"ROOT"}:
                nd = copy.deepcopy(d)
                nd["**SYSTEM"] = {}
                updates.append(("sys_viewdaten", str(r["uid"]), r["name"], nd, None))
                before.append({"table": "sys_viewdaten", "uid": str(r["uid"]), "name": r["name"], "daten_before": d})
                lines.append(f"- View {r['name']}: leere Gruppe **SYSTEM ergaenzt")

        # 4) Dropdown ohne Namen
        for r in await conn.fetch("select uid, name, daten from sys_dropdowndaten where coalesce(name,'') = ''"):
            uid = str(r["uid"])
            d = as_dict(r["daten"])
            used = False
            for t in ("sys_framedaten", "sys_control_dict", "sys_viewdaten", "sys_dialogdaten", "sys_dropdowndaten"):
                cnt = await conn.fetchval(
                    f'select count(*) from "{t}" where daten::text like $1 and uid <> $2::uuid', f"%{uid}%", uid)
                used = used or cnt > 0
            sn = as_dict(d.get("ROOT")).get("SELF_NAME")
            if used and sn:
                updates.append(("sys_dropdowndaten", uid, r["name"], d, sn))
                lines.append(f"- Dropdown {uid[:8]}: name := SELF_NAME")
            else:
                deletes.append(("sys_dropdowndaten", uid))
                before.append({"table": "sys_dropdowndaten", "uid": uid, "name": r["name"], "daten_before": d, "deleted": True})
                lines.append(f"- Dropdown {uid[:8]} (leer, ohne Namen, nirgends referenziert) geloescht")

        # 5) Dialoge: Test-Dialoge ohne Tabs loeschen, Pflichtfelder der Tabs/Typen korrigieren
        views = {str(r["uid"]): as_dict(as_dict(r["daten"]).get("ROOT")).get("TABLE") for r in await conn.fetch("select uid, daten from sys_viewdaten")}
        frames = {str(r["uid"]): as_dict(as_dict(r["daten"]).get("ROOT")).get("TABLE") for r in await conn.fetch("select uid, daten from sys_framedaten")}
        for r in await conn.fetch("select uid, name, daten from sys_dialogdaten"):
            uid = str(r["uid"])
            if uid[:2] in ("00", "55", "66"):
                continue
            d = as_dict(r["daten"])
            root = as_dict(d.get("ROOT"))
            tabs = as_dict(root.get("TAB_ELEMENTS"))
            if not tabs:
                refs = 0
                for t in ("sys_menudaten", "sys_dialogdaten", "sys_framedaten", "sys_viewdaten", "sys_systemdaten"):
                    refs += await conn.fetchval(f'select count(*) from "{t}" where daten::text like $1 and uid <> $2::uuid', f"%{uid}%", r["uid"])
                if refs == 0:
                    deletes.append(("sys_dialogdaten", uid))
                    before.append({"table": "sys_dialogdaten", "uid": uid, "name": r["name"], "daten_before": d, "deleted": True})
                    lines.append(f"- Dialog {r['name']} ({uid[:8]}): keine Tabs, nirgends referenziert - geloescht")
                continue
            nd = copy.deepcopy(d)
            nroot = nd["ROOT"]
            reasons = []
            if nroot.get("DIALOG_TYPE") not in ("norm", "work", "acti"):
                reasons.append(f"DIALOG_TYPE '{nroot.get('DIALOG_TYPE')}' -> 'norm'")
                nroot["DIALOG_TYPE"] = "norm"
            for tab_key, tab in as_dict(nroot.get("TAB_ELEMENTS")).items():
                module = str(tab.get("MODULE") or "")
                if not tab.get("TABLE"):
                    source = views if module == "view" else frames
                    table = source.get(str(tab.get("GUID") or ""))
                    if table:
                        tab["TABLE"] = table
                        reasons.append(f"{tab_key}.TABLE := {table}")
                if module == "edit" and tab.get("EDIT_TYPE") == "edit":
                    reasons.append(f"{tab_key}.EDIT_TYPE '{tab.get('EDIT_TYPE')}' -> 'pdvm_edit'")
                    tab["EDIT_TYPE"] = "pdvm_edit"
                if tab.get("OPEN_EDIT") == "doubleClick":
                    tab["OPEN_EDIT"] = "double_click"
                    reasons.append(f"{tab_key}.OPEN_EDIT -> double_click")
            if reasons:
                updates.append(("sys_dialogdaten", uid, r["name"], nd, None))
                before.append({"table": "sys_dialogdaten", "uid": uid, "name": r["name"], "daten_before": d})
                lines.append(f"- Dialog {r['name']} ({uid[:8]}): " + "; ".join(reasons))

        if args.apply and (updates or deletes):
            snap = BACKEND_DIR / "reports" / f"phase5_misc_snapshot_{datetime.now():%Y%m%d_%H%M%S}.json"
            snap.write_text(json.dumps(before, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
            lines += ["", f"Snapshot: `{snap}`"]
            async with conn.transaction():
                for table, uid, name, daten, new_name in updates:
                    root = daten.get("ROOT") if isinstance(daten.get("ROOT"), dict) else None
                    if root is not None:
                        root["SELF_MODIFIED_AT"] = stamp
                    await conn.execute(
                        f'update "{table}" set daten = $1::jsonb, name = coalesce($2, name), modified_at = now() where uid = $3::uuid',
                        json.dumps(daten, ensure_ascii=False), new_name, uid,
                    )
                for table, uid in deletes:
                    await conn.execute(f'delete from "{table}" where uid = $1::uuid', uid)
        report = "\n".join(lines) + "\n"
        if args.out:
            Path(args.out).write_text(report, encoding="utf-8")
        total = len(updates) + len(deletes)
        print(report if not args.quiet else f"{total} Aenderungen")
        return 1 if (args.check and total) else 0
    finally:
        await conn.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--confirm-backup", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--out")
    args = ap.parse_args()
    if args.apply and not args.confirm_backup:
        raise SystemExit("--apply verlangt --confirm-backup")
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
