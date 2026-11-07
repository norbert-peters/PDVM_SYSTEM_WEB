"""Phase 5 / Schritt 3: sys_control_dict bereinigen (ARCHITECTURE_RULES 1.10, 1.10a, 1.12b, 1.22).

Aufruf (aus backend/):
    ..\\.venv\\Scripts\\python.exe tools\\phase5_normalize_control_dict.py                # Dry-Run
    ..\\.venv\\Scripts\\python.exe tools\\phase5_normalize_control_dict.py --apply --confirm-backup

Aenderungen (alle in einer Transaktion, Snapshot der betroffenen Zeilen vorher nach backend/reports/):
1. Nicht verwendete Test-Controls (FIELD 'eingeben', in keiner anderen Tabelle referenziert) werden geloescht.
2. FELD-Alias entfernen, FIELD ist die Wahrheit (GROSS). Bei Konflikt FIELD != FELD gilt FIELD, ausser fuer
   die in FELD_WINS genannten Controls (dort stimmt FELD mit dem Datenpfad ueberein).
3. name und ROOT.SELF_NAME = <TABELLENPREFIX>_<FIELD> (GROSS), sofern der Name nicht schon vergeben ist.
4. Tippfehler-Eigenschaft DISPLAY_ODER -> DISPLAY_ORDER (bzw. entfernen, falls DISPLAY_ORDER vorhanden).
5. Muttercontrol (666): FELD entfernen, FIELDS_ELEMENTS und CONFIGS_ELEMENTS (LINEAR_SCHEMA 8.2) ergaenzen,
   daten.CONTROL und daten.TEMPLATES.CONTROL bleiben identisch (1.10a).
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
from audit_system_data import RESERVED, U666, as_dict, load_env_url  # noqa: E402
from seed_base_records import connect  # noqa: E402

DB = "pdvm_system"
TABLE = "sys_control_dict"
# uid-Praefix -> bei FIELD != FELD gewinnt FELD (user.CONFIG.THEME_LIGHT ist der echte Datenpfad)
FELD_WINS = {"ef6a4b8a"}
MOTHER_NEW_PROPS = {"FIELDS_ELEMENTS": {}, "CONFIGS_ELEMENTS": {}}
USAGE_TABLES = ("sys_framedaten", "sys_viewdaten", "sys_dialogdaten", "sys_dropdowndaten", "sys_menudaten")


def table_prefix(table: str) -> str:
    return table.split("_", 1)[0].upper() if "_" in table else table[:3].upper()


class Change:
    def __init__(self, uid, name, daten):
        self.uid = uid
        self.orig_name = name
        self.name = name
        self.orig_daten = copy.deepcopy(daten)
        self.daten = daten
        self.delete = False
        self.reasons: list[str] = []

    @property
    def changed(self) -> bool:
        return self.delete or self.name != self.orig_name or self.daten != self.orig_daten


def plan(rows, used_uids: set[str]) -> list[Change]:
    changes = {str(r["uid"]): Change(str(r["uid"]), r["name"], copy.deepcopy(as_dict(r["daten"]))) for r in rows}
    stamp = now_pdvm_str()

    # 1) Test-Controls loeschen
    for c in changes.values():
        if c.uid in RESERVED:
            continue
        ctrl = as_dict(c.daten.get("CONTROL"))
        if ctrl.get("FIELD") == "eingeben" and c.uid not in used_uids:
            c.delete = True
            c.reasons.append("1.10: Test-Control (FIELD 'eingeben', nirgends referenziert) geloescht")

    live = {u: c for u, c in changes.items() if not c.delete}

    # 2) + 4) FELD-Alias, Tippfehler-Eigenschaft
    for c in live.values():
        ctrl = c.daten.get("CONTROL")
        if not isinstance(ctrl, dict):
            continue
        if c.uid in RESERVED:
            if c.uid == U666:
                continue  # Muttercontrol separat (Schritt 5)
            if "FELD" in ctrl:
                del ctrl["FELD"]
                c.reasons.append("1.12b: FELD entfernt")
            continue
        field = ctrl.get("FIELD")
        feld = ctrl.get("FELD")
        chosen = feld if (c.uid[:8] in FELD_WINS and feld) else (field or feld)
        if chosen:
            chosen = str(chosen).strip().upper()
            if ctrl.get("FIELD") != chosen:
                c.reasons.append(f"1.12b/1.10: FIELD '{ctrl.get('FIELD')}' -> '{chosen}'")
            ctrl["FIELD"] = chosen
        if "FELD" in ctrl:
            del ctrl["FELD"]
            c.reasons.append("1.12b: FELD entfernt")
        if "DISPLAY_ODER" in ctrl:
            typo = ctrl.pop("DISPLAY_ODER")
            if "DISPLAY_ORDER" not in ctrl:
                ctrl["DISPLAY_ORDER"] = typo
            c.reasons.append("1.10a: DISPLAY_ODER -> DISPLAY_ORDER")

    # 5) Muttercontrol
    mother = live.get(U666)
    if mother is not None:
        d = mother.daten
        tmpl = d.get("TEMPLATES") if isinstance(d.get("TEMPLATES"), dict) else {}
        for holder, label in ((d, "daten.CONTROL"), (tmpl, "daten.TEMPLATES.CONTROL")):
            ctrl = holder.get("CONTROL") if isinstance(holder.get("CONTROL"), dict) else None
            if ctrl is None:
                continue
            if "FELD" in ctrl:
                del ctrl["FELD"]
                mother.reasons.append(f"1.12b: FELD aus {label} entfernt")
            for key, default in MOTHER_NEW_PROPS.items():
                if key not in ctrl:
                    ctrl[key] = copy.deepcopy(default)
                    mother.reasons.append(f"1.10a: {key} in {label} ergaenzt")
        if "CONTROL" in d and isinstance(tmpl.get("CONTROL"), dict):
            d["CONTROL"] = copy.deepcopy(tmpl["CONTROL"])

    # 3) Namen
    taken = {c.name.upper(): c.uid for c in live.values() if c.name}
    for c in live.values():
        if c.uid in RESERVED:
            continue
        ctrl = as_dict(c.daten.get("CONTROL"))
        field, table = ctrl.get("FIELD"), str(ctrl.get("TABLE") or "")
        if not field or not table:
            continue
        expected = f"{table_prefix(table)}_{field}".upper()
        root = c.daten.get("ROOT") if isinstance(c.daten.get("ROOT"), dict) else {}
        if c.name != expected:
            owner = taken.get(expected)
            if owner and owner != c.uid:
                if c.uid not in used_uids:
                    c.delete = True
                    c.reasons.append(
                        f"1.10: Duplikat von '{expected}' (gleiche Tabelle/FIELD), nirgends referenziert - geloescht"
                    )
                    taken.pop(c.name.upper(), None)
                else:
                    c.reasons.append(f"1.10: Name '{c.name}' != '{expected}', aber '{expected}' ist schon vergeben - unveraendert")
            else:
                taken.pop(c.name.upper(), None)
                taken[expected] = c.uid
                c.reasons.append(f"1.10: name '{c.name}' -> '{expected}'")
                c.name = expected
        if root is not None and "SELF_NAME" in root and root["SELF_NAME"] != c.name:
            root["SELF_NAME"] = c.name
            c.daten["ROOT"] = root
            c.reasons.append("1.22: ROOT.SELF_NAME synchronisiert")

    out = []
    for c in changes.values():
        if c.changed:
            if not c.delete and isinstance(c.daten.get("ROOT"), dict):
                c.daten["ROOT"]["SELF_MODIFIED_AT"] = stamp
            out.append(c)
    return out


async def run(args) -> int:
    conn = await connect(load_env_url(), DB, read_only=not args.apply)
    try:
        rows = await conn.fetch(f"select uid, name, daten from {TABLE}")
        used: set[str] = set()
        uids = [str(r["uid"]) for r in rows]
        for t in USAGE_TABLES:
            for r in await conn.fetch(f'select daten::text as d from "{t}"'):
                used.update(u for u in uids if u in r["d"])
        changes = plan(rows, used)

        lines = [f"# Phase 5: sys_control_dict bereinigen ({'APPLY' if args.apply else 'Dry-Run'})", ""]
        lines.append(f"{len(changes)} Datensaetze betroffen ({sum(1 for c in changes if c.delete)} Loeschungen).")
        lines.append("")
        for c in sorted(changes, key=lambda x: x.orig_name or ""):
            lines.append(f"- `{c.orig_name}` ({c.uid[:8]}){' **[reserviert]**' if c.uid in RESERVED else ''}")
            for reason in c.reasons:
                lines.append(f"  - {reason}")

        if args.apply and changes:
            snap = BACKEND_DIR / "reports" / f"phase5_control_dict_snapshot_{datetime.now():%Y%m%d_%H%M%S}.json"
            snap.write_text(
                json.dumps(
                    [{"uid": c.uid, "name": c.orig_name, "daten_before": c.orig_daten, "deleted": c.delete} for c in changes],
                    ensure_ascii=False, indent=1, default=str,
                ),
                encoding="utf-8",
            )
            lines.append("")
            lines.append(f"Snapshot: `{snap}`")
            async with conn.transaction():
                for c in changes:
                    if c.delete:
                        await conn.execute(f"delete from {TABLE} where uid = $1::uuid", c.uid)
                    else:
                        await conn.execute(
                            f"update {TABLE} set daten = $1::jsonb, name = $2, modified_at = now() where uid = $3::uuid",
                            json.dumps(c.daten, ensure_ascii=False), c.name, c.uid,
                        )
        report = "\n".join(lines) + "\n"
        if args.out:
            Path(args.out).write_text(report, encoding="utf-8")
        print(report if not args.quiet else f"{len(changes)} Aenderungen")
        return 1 if (args.check and changes) else 0
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
