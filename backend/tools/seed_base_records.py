"""Seeder und Pruefung fuer die Tabellen-Basissaetze 000/555/666 (ARCHITECTURE_RULES 1.12, 1.12a, 1.12c, 1.10a).

Aufruf (aus backend/):
    ..\\.venv\\Scripts\\python.exe tools\\seed_base_records.py                 # Dry-Run (Standard), nur Lesezugriff
    ..\\.venv\\Scripts\\python.exe tools\\seed_base_records.py --check         # Exit-Code 1, wenn Aenderungen noetig sind
    ..\\.venv\\Scripts\\python.exe tools\\seed_base_records.py --apply --confirm-backup [--allow-reserved-changes]

Regeln der Umsetzung:
- Bestehende Inhalte werden nie ueberschrieben, nur ergaenzt bzw. strukturell verschoben.
- Fehlende Basissaetze werden neu angelegt; Basissaetze mit falscher UID (ROOT.SELF_LINK_UID zeigt auf 000/555/666)
  werden auf die reservierte UID umgeschluesselt.
- Aenderungen an bereits vorhandenen reservierten Saetzen (000/555/666) erfolgen nur mit --allow-reserved-changes.
- --apply verlangt --confirm-backup (Bestaetigung, dass ein Backup existiert) und schreibt vorher einen Snapshot der
  betroffenen Zeilen nach backend/reports/ (Rollback-Grundlage).
- Pro Datenbank wird in genau einer Transaktion geschrieben.
- Das Entfernen von TABLE_INFO aus Fachdatensaetzen (1.12c) ist enthalten.
- FIELD/FELD (1.12b) ist nicht Teil dieses Tools (Phase 5, sys_control_dict).
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.pdvm_datetime import now_pdvm_str  # noqa: E402
from audit_system_data import RESERVED, U000, U555, U666, as_dict, load_env_url  # noqa: E402

DEFAULT_DBS = ["pdvm_system", "pdvm_standard", "mandant"]
OPEN_SENTINEL = "9999365.99999"
OPEN_DATETIME = datetime(9999, 12, 31, 23, 59, 59)
BASE_NAMES = {U000: "Tabellen-Metadaten", U555: "Templates", U666: "Template neuer Satz"}
PDVM_STANDARD_COLUMNS = {
    "uid", "link_uid", "daten", "name", "historisch", "source_hash", "sec_id", "gilt_bis",
    "created_at", "modified_at", "daten_backup", "backup_daten", "gruppe",
}
SKIPPED_NON_STANDARD: list[str] = []


@dataclass
class Work:
    uid: str
    name: str | None
    link_uid: str | None
    gilt_bis: datetime | None
    daten: dict
    exists: bool = True
    orig_uid: str | None = None
    orig_daten: dict | None = None
    orig_link_uid: str | None = None
    rekeyed: bool = False
    reasons: list[tuple[str, str]] = field(default_factory=list)

    @property
    def created(self) -> bool:
        return not self.exists

    @property
    def changed(self) -> bool:
        return self.created or self.rekeyed or self.daten != self.orig_daten

    @property
    def reserved_edit(self) -> bool:
        return self.exists and not self.rekeyed and self.orig_uid in RESERVED and self.daten != self.orig_daten

    def note(self, rule: str, text: str) -> None:
        self.reasons.append((rule, text))


def root_base(table: str, uid: str, name: str, stamp: str) -> dict:
    return {
        "TABLE": table,
        "SELF_GUID": uid,
        "SELF_NAME": name if uid != U666 else "",
        "SELF_LINK_UID": uid,
        "SELF_CREATED_AT": stamp,
        "SELF_MODIFIED_AT": stamp,
        "SELF_GILT_BIS": OPEN_SENTINEL,
    }


def default_table_info(stamp_iso: str) -> dict:
    return {
        "version": "2.0",
        "description": "",
        "created_at": stamp_iso,
        "created_by": "system",
        "schema_migrated": True,
    }


def template_group_key(daten: dict) -> str:
    return "TEMPLATE" if "TEMPLATE" in daten and "TEMPLATES" not in daten else "TEMPLATES"


def plan_table(table: str, rows: list[asyncpg.Record], has_link_uid: bool) -> list[Work]:
    stamp = now_pdvm_str()
    stamp_iso = datetime.now().replace(microsecond=0).isoformat()
    works: dict[str, Work] = {}
    for r in rows:
        uid = str(r["uid"])
        d = as_dict(r["daten"])
        works[uid] = Work(
            uid=uid,
            name=r["name"],
            link_uid=str(r["link_uid"]) if r["link_uid"] is not None else None,
            gilt_bis=r["gilt_bis"],
            daten=copy.deepcopy(d),
            orig_uid=uid,
            orig_daten=copy.deepcopy(d),
            orig_link_uid=str(r["link_uid"]) if r["link_uid"] is not None else None,
        )

    # 1) Basissaetze mit falscher UID auf die reservierte UID umschluesseln
    for res in (U000, U555, U666):
        if res in works:
            continue
        candidates = [
            w for w in works.values()
            if w.uid not in RESERVED and as_dict(w.daten.get("ROOT")).get("SELF_LINK_UID") == res
        ]
        if len(candidates) != 1:
            if len(candidates) > 1:
                for c in candidates:
                    c.note("1.12", f"mehrere Kandidaten fuer {res[:2]}...: keine automatische Umschluesselung")
            continue
        w = candidates[0]
        del works[w.uid]
        w.note("1.12", f"UID {w.uid[:8]} -> {res[:2]}... (Basissatz mit falscher UID)")
        w.uid = res
        w.rekeyed = True
        root = as_dict(w.daten.get("ROOT"))
        root["SELF_GUID"] = res
        root["SELF_LINK_UID"] = res
        w.daten["ROOT"] = root
        w.link_uid = res
        works[res] = w

    # 2) Fehlende Basissaetze neu anlegen
    for res in (U000, U555, U666):
        if res in works:
            continue
        daten: dict = {"ROOT": root_base(table, res, BASE_NAMES[res], stamp)}
        if res == U000:
            daten["TABLE_INFO"] = default_table_info(stamp_iso)
        elif res == U555:
            daten["TEMPLATES"] = {}
        else:
            daten["TEMPLATES"] = {"TABLE_INFO": default_table_info(stamp_iso)}
        w = Work(uid=res, name=BASE_NAMES[res], link_uid=res, gilt_bis=OPEN_DATETIME, daten=daten, exists=False)
        w.note("1.12", f"Basissatz {res[:2]}... fehlt -> anlegen")
        works[res] = w

    # 3) 666: TEMPLATES/TABLE_INFO (1.12a, 1.12c)
    w666 = works[U666]
    if not w666.created:
        d = w666.daten
        meta = as_dict(works[U000].daten.get("TABLE_INFO")) or default_table_info(stamp_iso)
        key = template_group_key(d)
        tmpl = d.get(key) if isinstance(d.get(key), dict) else {}
        touched = False
        if "TABLE_INFO" in d:
            moved = d.pop("TABLE_INFO")
            tmpl.setdefault("TABLE_INFO", moved if isinstance(moved, dict) and moved else meta)
            w666.note("1.12a", "daten.TABLE_INFO -> daten.TEMPLATES.TABLE_INFO")
            touched = True
        if "TABLE_INFO" not in tmpl:
            tmpl["TABLE_INFO"] = copy.deepcopy(meta)
            w666.note("1.12c", "TEMPLATES.TABLE_INFO ergaenzt")
            touched = True
        if touched or key not in d:
            if key not in d or not d.get(key):
                w666.note("1.12a", f"Gruppe {key} ergaenzt")
            d[key] = tmpl

    # 4) 555: TEMPLATES-Gruppe als Struktur-Container sicherstellen (Basis fuer Neuanlage, 1.13)
    w555 = works[U555]
    if not w555.created and not w555.daten:
        w555.daten = {"ROOT": root_base(table, U555, BASE_NAMES[U555], stamp), "TEMPLATES": {}}
        w555.note("1.13", "555: daten war leer -> ROOT/TEMPLATES angelegt")
    if not w555.created and "TABLE_INFO" in w555.daten:
        del w555.daten["TABLE_INFO"]
        w555.note("1.12c", "555: TABLE_INFO entfernt (Neuanlage kopiert die 555 in Fachdatensaetze)")

    # 5) sys_control_dict: Muttercontrol in daten.CONTROL und identisch in daten.TEMPLATES.CONTROL (1.10a)
    if table == "sys_control_dict" and not w666.created:
        d = w666.daten
        tmpl_ctrl = as_dict(as_dict(d.get(template_group_key(d))).get("CONTROL"))
        ctrl = as_dict(d.get("CONTROL"))
        if tmpl_ctrl and ctrl != tmpl_ctrl:
            d["CONTROL"] = copy.deepcopy(tmpl_ctrl)
            w666.note("1.10a", "Muttercontrol: daten.CONTROL aus daten.TEMPLATES.CONTROL synchronisiert")
        elif ctrl and not tmpl_ctrl:
            d.setdefault(template_group_key(d), {})["CONTROL"] = copy.deepcopy(ctrl)
            w666.note("1.10a", "Muttercontrol: daten.TEMPLATES.CONTROL aus daten.CONTROL synchronisiert")

    # 6) TABLE_INFO aus Fachdatensaetzen entfernen (1.12c)
    for w in works.values():
        if w.uid in RESERVED or w.rekeyed or w.created:
            continue
        if "TABLE_INFO" in w.daten:
            del w.daten["TABLE_INFO"]
            w.note("1.12c", "TABLE_INFO aus Fachdatensatz entfernt")

    # ROOT.SELF_MODIFIED_AT fuer geaenderte, bereits vorhandene Saetze nachziehen
    for w in works.values():
        if w.exists and w.changed:
            root = as_dict(w.daten.get("ROOT"))
            if root:
                root["SELF_MODIFIED_AT"] = stamp
                w.daten["ROOT"] = root
    return [w for w in works.values() if w.changed]


async def connect(host_url, db: str, read_only: bool):
    return await asyncpg.connect(
        host=host_url.hostname,
        port=host_url.port,
        user=unquote(host_url.username),
        password=unquote(host_url.password),
        database=db,
        server_settings={"default_transaction_read_only": "on" if read_only else "off"},
    )


async def load_tables(conn) -> dict[str, tuple[list, set[str]]]:
    tables = [
        r["table_name"]
        for r in await conn.fetch(
            "select table_name from information_schema.tables "
            "where table_schema='public' and table_type='BASE TABLE' order by 1"
        )
    ]
    out: dict[str, tuple[list, dict[str, str]]] = {}
    for t in tables:
        cols = {
            r["column_name"]: r["data_type"]
            for r in await conn.fetch(
                "select column_name, data_type from information_schema.columns "
                "where table_schema='public' and table_name=$1", t
            )
        }
        if not {"uid", "daten", "name"} <= set(cols) or t.endswith("_feld_aenderungshistorie"):
            continue
        if set(cols) - PDVM_STANDARD_COLUMNS:
            # Tabellen mit eigenem Layout (z. B. msy_update_history mit Pflichtspalte run_id) haben keine Basissaetze
            SKIPPED_NON_STANDARD.append(t)
            continue
        sel = "uid, name, gilt_bis, daten, " + ("link_uid" if "link_uid" in cols else "null::uuid as link_uid")
        if "gilt_bis" not in cols:
            sel = sel.replace("gilt_bis, ", "null as gilt_bis, ")
        out[t] = (await conn.fetch(f'select {sel} from "{t}"'), cols)
    return out


def open_gilt_bis_value(col_type: str | None):
    """Offenes Gueltigkeitsende passend zum Spaltentyp (Tabellen mit Float-/Text-gilt_bis existieren)."""
    if col_type in ("double precision", "real", "numeric"):
        return 9999365.0
    if col_type in ("text", "character varying"):
        return "9999365.00000"
    return OPEN_DATETIME


async def apply_work(conn, table: str, cols: dict[str, str], w: Work, allow_reserved: bool) -> str:
    if w.reserved_edit and not allow_reserved:
        return "uebersprungen (reservierter Satz, --allow-reserved-changes fehlt)"
    payload = json.dumps(w.daten, ensure_ascii=False)
    if w.created:
        names = ["uid", "name", "daten"]
        vals = [w.uid, w.name, payload]
        casts = ["$1::uuid", "$2", "$3::jsonb"]
        if "gilt_bis" in cols:
            names.append("gilt_bis")
            vals.append(open_gilt_bis_value(cols["gilt_bis"]))
            casts.append(f"${len(vals)}")
        if "historisch" in cols:
            names.append("historisch")
            vals.append(0)
            casts.append(f"${len(vals)}")
        if "link_uid" in cols:
            names.append("link_uid")
            vals.append(w.link_uid)
            casts.append(f"${len(vals)}::uuid")
        await conn.execute(
            f'insert into "{table}" ({", ".join(names)}) values ({", ".join(casts)})', *vals
        )
        return "angelegt"
    sets = ["daten = $1::jsonb"]
    if "modified_at" in cols:
        sets.append("modified_at = now()")
    vals = [payload]
    if w.rekeyed:
        vals.append(w.uid)
        sets.append(f"uid = ${len(vals)}::uuid")
        if "link_uid" in cols:
            vals.append(w.link_uid)
            sets.append(f"link_uid = ${len(vals)}::uuid")
    vals.append(w.orig_uid)
    await conn.execute(f'update "{table}" set {", ".join(sets)} where uid = ${len(vals)}::uuid', *vals)
    return "umgeschluesselt" if w.rekeyed else "aktualisiert"


def snapshot_entry(table: str, w: Work) -> dict:
    return {
        "table": table,
        "uid": w.orig_uid,
        "new_uid": w.uid if w.rekeyed else None,
        "existed": w.exists,
        "link_uid": w.orig_link_uid,
        "daten_before": w.orig_daten,
    }


async def run(args) -> int:
    host_url = load_env_url()
    pending_total = 0
    lines = ["# Seeder Basissaetze 000/555/666", ""]
    lines.append(f"Modus: {'APPLY' if args.apply else 'Dry-Run'}"
                 f"{' (+reservierte Saetze)' if args.apply and args.allow_reserved_changes else ''}. "
                 "Erzeugt von `backend/tools/seed_base_records.py`.")
    lines.append("")
    snapshot: list[dict] = []
    for db in args.db or DEFAULT_DBS:
        conn = await connect(host_url, db, read_only=not args.apply)
        try:
            tables = await load_tables(conn)
            plans = {t: plan_table(t, rows, "link_uid" in cols) for t, (rows, cols) in tables.items()}
            plans = {t: ws for t, ws in plans.items() if ws}
            n = sum(len(ws) for ws in plans.values())
            pending_total += n
            lines.append(f"## {db}: {n} Aenderungen in {len(plans)} Tabellen")
            lines.append("")
            for t, ws in sorted(plans.items()):
                for w in ws:
                    flag = " **[reservierter Satz]**" if w.reserved_edit else ""
                    lines.append(f"- `{t}` {w.orig_uid or w.uid}{flag}")
                    for rule, text in w.reasons:
                        lines.append(f"  - Regel {rule}: {text}")
            lines.append("")
            if args.apply and plans:
                db_snapshot = [
                    {**snapshot_entry(t, w), "db": db} for t, ws in plans.items() for w in ws if w.exists
                ]
                if db_snapshot:
                    # Snapshot vor dem Schreiben je DB sichern (auch wenn eine spaetere DB scheitert)
                    snap_path = BACKEND_DIR / "reports" / f"seed_base_records_snapshot_{db}_{datetime.now():%Y%m%d_%H%M%S}.json"
                    snap_path.write_text(json.dumps(db_snapshot, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
                    lines.append(f"Snapshot {db} (Zeilen vor der Aenderung): `{snap_path}`")
                async with conn.transaction():
                    for t, ws in plans.items():
                        # Anlage/Umschluesselung zuerst, damit Referenzen auf reservierte UIDs stabil sind
                        for w in sorted(ws, key=lambda x: (not x.created, not x.rekeyed)):
                            result = await apply_work(conn, t, tables[t][1], w, args.allow_reserved_changes)
                            lines.append(f"  - {db}/{t}/{w.uid[:8]}: {result}")
        finally:
            await conn.close()

    report = "\n".join(lines) + "\n"
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
    print(report if not args.quiet else f"{pending_total} Aenderungen noetig")
    return 1 if (args.check and pending_total) else 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", action="append", help="Datenbank (mehrfach); Standard: pdvm_system, pdvm_standard, mandant")
    ap.add_argument("--apply", action="store_true", help="Aenderungen schreiben (sonst Dry-Run)")
    ap.add_argument("--confirm-backup", action="store_true", help="Bestaetigt, dass ein Backup vorliegt (Pflicht fuer --apply)")
    ap.add_argument("--allow-reserved-changes", action="store_true",
                    help="Erlaubt Aenderungen an vorhandenen 000/555/666-Saetzen (ausdrueckliche Freigabe)")
    ap.add_argument("--check", action="store_true", help="Exit-Code 1, wenn Aenderungen noetig sind")
    ap.add_argument("--quiet", action="store_true", help="Nur Anzahl ausgeben")
    ap.add_argument("--out", help="Bericht als Markdown-Datei schreiben")
    args = ap.parse_args()
    if args.apply and not args.confirm_backup:
        raise SystemExit("--apply verlangt --confirm-backup (Backup muss vorher vorliegen).")
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
