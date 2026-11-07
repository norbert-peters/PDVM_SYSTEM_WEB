"""Phase 5 / Schritt 6: sys_framedaten bereinigen (ARCHITECTURE_RULES 1.10b, 1.22).

Aufruf (aus backend/):
    ..\\.venv\\Scripts\\python.exe tools\\phase5_normalize_frames.py --golden <vorher.json>          # Dry-Run
    ..\\.venv\\Scripts\\python.exe tools\\phase5_normalize_frames.py --golden <vorher.json> --apply --confirm-backup

<vorher.json> ist der Golden-Master (tools/phase5_frame_golden.py capture) VOR der Migration. Er liefert die
aufgeloeste Runtime-Ausgabe je Frame-Feld (Control + Frame-Overrides). Daraus werden Controls abgeleitet, damit
die Ausgabe nach der Migration gleich bleibt.

Regeln (Entscheidung 07.11.2026, Variante B):
- Frames tragen je Feld nur Layout (TAB, DISPLAY_ORDER, SOURCE_PATH, SAVE_PATH) und - fuer generische Controls -
  die Kontextbindung GRUPPE/TABLE (GROSS). Control-Semantik (TYPE, LABEL, FIELD, CONFIGS, READ_ONLY) kommt aus
  sys_control_dict.
- Kleinschreib-Layoutschluessel werden GROSS geschrieben.
- Eingebettete Control-Kopien (ROOT/CONTROL im Frame-Feld) und Semantik-Schluessel werden entfernt.
- Felder mit Semantik im Frame (Inline-Felder bzw. Schluessel eines fremden Controls) verweisen danach auf ein
  Control mit gleichem FIELD/TYPE/LABEL/CONFIGS/READ_ONLY; gibt es keins, entsteht ein neues Control
  (Name <PREFIX>_<FIELD>, bei Kollision <PREFIX>_<GRUPPE>_<FIELD>, sonst mit Zaehler).
- Ausnahmen bleiben unveraendert: benannte Struktur-Eintraege (z. B. CONTROL/CONFIGS in element_list-Frames) und
  Felder mit Kleinschreib-Datenschluessel (sys_menudaten.MENU: label, tooltip, ...).
- Verweise auf nicht vorhandene Controls (nur Layout-Schluessel) werden entfernt.
- ROOT.SELF_NAME und Spalte name werden synchronisiert (SELF_NAME ist die Schreibquelle, Regel 1.22).
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.pdvm_datetime import now_pdvm_str  # noqa: E402
from audit_system_data import RESERVED, U666, as_dict, load_env_url  # noqa: E402
from seed_base_records import connect  # noqa: E402

GUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
LAYOUT_UP = {"tab": "TAB", "display_order": "DISPLAY_ORDER", "source_path": "SOURCE_PATH", "save_path": "SAVE_PATH"}
KEEP_UP = {"TAB", "DISPLAY_ORDER", "SOURCE_PATH", "SAVE_PATH", "GRUPPE", "TABLE", "dict_ref"}
SEMANTIC_KEYS = {"feld", "type", "label", "control", "root"}
NS = uuid.UUID("6f1a5b0e-2a0c-4d6b-9b3e-5d1f0c7a9e11")


def table_prefix(table: str) -> str:
    table = str(table or "").strip()
    return table.split("_", 1)[0].upper() if "_" in table else (table[:3].upper() or "SYS")


def norm(value) -> str:
    return str(value or "").strip().upper()


class FramePlan:
    def __init__(self, uid, name, daten):
        self.uid = uid
        self.orig_name = name
        self.name = name
        self.orig_daten = copy.deepcopy(daten)
        self.daten = daten
        self.reasons: list[str] = []

    @property
    def changed(self) -> bool:
        return self.name != self.orig_name or self.daten != self.orig_daten


def build_control(mother_ctrl: dict, desired: dict, name: str, uid: str, stamp: str, raw: dict) -> dict:
    ctrl = copy.deepcopy(mother_ctrl)
    ctrl.pop("FELD", None)  # Alias-Verbot (Regel 1.12b)
    ctrl["NAME"] = name
    ctrl["FIELD"] = norm(desired.get("feld"))
    ctrl["TYPE"] = desired.get("type") or "string"
    if desired.get("label") is not None:
        ctrl["LABEL"] = desired.get("label")
    ctrl["TABLE"] = str(desired.get("table") or "").lower()
    ctrl["GRUPPE"] = desired.get("gruppe") or ""
    ctrl["READ_ONLY"] = bool(desired.get("read_only", False))
    ctrl["HISTORICAL"] = bool(raw.get("historical", False))
    ctrl["ABDATUM"] = bool(raw.get("abdatum", False))
    if isinstance(desired.get("configs"), dict):
        ctrl["CONFIGS"] = copy.deepcopy(desired["configs"])
    return {
        "ROOT": {
            "TABLE": "sys_control_dict",
            "SELF_GUID": uid,
            "SELF_NAME": name,
            "SELF_LINK_UID": uid,
            "SELF_CREATED_AT": stamp,
            "SELF_MODIFIED_AT": stamp,
            "SELF_GILT_BIS": "9999365.99999",
        },
        "CONTROL": ctrl,
    }


def semantics_match(ctrl: dict, desired: dict) -> bool:
    return (
        norm(ctrl.get("FIELD")) == norm(desired.get("feld"))
        and norm(ctrl.get("TYPE")) == norm(desired.get("type") or "string")
        and str(ctrl.get("LABEL") or "") == str(desired.get("label") or "")
        and (ctrl.get("CONFIGS") or {}) == (desired.get("configs") or {})
        and bool(ctrl.get("READ_ONLY", False)) == bool(desired.get("read_only", False))
    )


def plan(frames, controls_rows, golden):
    stamp = now_pdvm_str()
    controls = {str(r["uid"]): r for r in controls_rows}
    mother = as_dict(as_dict(controls[U666]["daten"]).get("CONTROL"))
    by_field: dict[str, list[str]] = {}
    names = {str(r["name"]).upper() for r in controls_rows}
    for uid, r in controls.items():
        if uid in RESERVED:
            continue
        field = norm(as_dict(as_dict(r["daten"]).get("CONTROL")).get("FIELD"))
        if field:
            by_field.setdefault(field, []).append(uid)

    new_controls: dict[str, dict] = {}
    frame_plans: list[FramePlan] = []
    exceptions: list[str] = []

    def control_of(uid):
        if uid in new_controls:
            return new_controls[uid]["daten"]["CONTROL"]
        return as_dict(as_dict(controls[uid]["daten"]).get("CONTROL"))

    for fr in frames:
        uid = str(fr["uid"])
        if uid in RESERVED:
            continue
        fp = FramePlan(uid, fr["name"], copy.deepcopy(as_dict(fr["daten"])))
        fields = as_dict(fp.daten.get("FIELDS"))
        golden_fields = as_dict(as_dict(as_dict(as_dict(golden.get(uid)).get("body")).get("daten")).get("FIELDS"))
        new_fields: dict = {}
        used: set[str] = set()
        for key, value in fields.items():
            item = as_dict(value)
            if not GUID_RE.match(str(key)):
                new_fields[key] = value  # benannte Struktur-Eintraege
                continue
            key = str(key)
            low = {str(k).lower(): v for k, v in item.items()}
            has_semantics = bool(set(low) & SEMANTIC_KEYS)

            if not has_semantics and key not in controls and key not in new_controls:
                fp.reasons.append(f"1.10b: Verweis {key[:8]} auf nicht vorhandenes Control entfernt")
                continue

            if not has_semantics:
                target = key
            else:
                desired = {**low, **as_dict(golden_fields.get(key))}
                feld_raw = str(desired.get("feld") or "").strip()
                if not feld_raw or feld_raw != feld_raw.upper():
                    exceptions.append(f"{fp.orig_name}: Feld '{feld_raw}' (Kleinschreib-Datenschluessel) unveraendert")
                    new_fields[key] = value
                    continue
                candidates = ([key] if key in controls else []) + [c for c in by_field.get(feld_raw.upper(), []) if c != key]
                target = next(
                    (c for c in candidates if c not in used and semantics_match(control_of(c), desired)),
                    None,
                )
                if target is None:
                    prefix = table_prefix(desired.get("table"))
                    name = f"{prefix}_{feld_raw}".upper()
                    if name in names:
                        group = norm(desired.get("gruppe")).replace(".", "_").strip("_")
                        name = f"{prefix}_{group}_{feld_raw}".replace("__", "_").upper() if group else name
                    n = 2
                    base_name = name
                    while name in names:
                        name = f"{base_name}_{n}"
                        n += 1
                    names.add(name)
                    new_uid = key if (key not in controls and key not in new_controls) else str(uuid.uuid5(NS, f"{uid}:{key}"))
                    new_controls[new_uid] = {"name": name, "daten": build_control(mother, desired, name, new_uid, stamp, low)}
                    by_field.setdefault(feld_raw.upper(), []).append(new_uid)
                    target = new_uid
                    fp.reasons.append(f"1.10b: Feld {feld_raw} ({key[:8]}) -> neues Control {name}")
                else:
                    fp.reasons.append(f"1.10b: Feld {feld_raw} ({key[:8]}) -> Control {target[:8]} (Semantik aus dem Frame entfernt)")

            if target in used:
                fp.reasons.append(f"1.10b: Control {target[:8]} doppelt im Frame - Eintrag {key[:8]} unveraendert")
                new_fields[key] = value
                continue
            used.add(target)

            ctrl = control_of(target)
            entry: dict = {}
            for k, v in item.items():
                kl = str(k).lower()
                if kl in LAYOUT_UP:
                    entry[LAYOUT_UP[kl]] = v
                elif k in KEEP_UP:
                    entry[k] = v
            # Kontextbindung (GRUPPE/TABLE) nur behalten, wenn sie vom Control abweicht
            bind_source = {**low, **as_dict(golden_fields.get(key))} if has_semantics else low
            for bind_key in ("gruppe", "table"):
                if bind_key in bind_source or bind_key.upper() in item:
                    raw = bind_source.get(bind_key, item.get(bind_key.upper()))
                    if norm(raw) != norm(ctrl.get(bind_key.upper())):
                        entry[bind_key.upper()] = (raw if bind_key == "gruppe" else str(raw or "").lower()) or ""
                    else:
                        entry.pop(bind_key.upper(), None)
            new_fields[target] = entry

        if new_fields != fields:
            fp.daten["FIELDS"] = new_fields
            fp.reasons.append(f"1.10b: FIELDS {len(fields)} -> {len(new_fields)} Eintraege normalisiert")

        root = fp.daten.get("ROOT") if isinstance(fp.daten.get("ROOT"), dict) else {}
        if root.get("SELF_NAME") and root["SELF_NAME"] != fp.name:
            fp.reasons.append(f"1.22: name '{fp.name}' -> '{root['SELF_NAME']}'")
            fp.name = root["SELF_NAME"]
        if fp.changed and isinstance(fp.daten.get("ROOT"), dict):
            fp.daten["ROOT"]["SELF_MODIFIED_AT"] = stamp
        frame_plans.append(fp)

    return [f for f in frame_plans if f.changed], new_controls, exceptions


async def run(args) -> int:
    golden = json.loads(Path(args.golden).read_text(encoding="utf-8"))
    conn = await connect(load_env_url(), "pdvm_system", read_only=not args.apply)
    try:
        frames = await conn.fetch("select uid, name, daten from sys_framedaten")
        controls = await conn.fetch("select uid, name, daten from sys_control_dict")
        frame_changes, new_controls, exceptions = plan(frames, controls, golden)

        lines = [f"# Phase 5: sys_framedaten bereinigen ({'APPLY' if args.apply else 'Dry-Run'})", ""]
        lines.append(f"{len(frame_changes)} Frames geaendert, {len(new_controls)} neue Controls.")
        lines.append("")
        for c in new_controls.values():
            lines.append(f"- neues Control `{c['name']}`")
        lines.append("")
        for fp in sorted(frame_changes, key=lambda x: x.orig_name or ""):
            lines.append(f"## {fp.orig_name} ({fp.uid[:8]})")
            for r in fp.reasons:
                lines.append(f"- {r}")
        if exceptions:
            lines.append("")
            lines.append("## Dokumentierte Ausnahmen (unveraendert)")
            lines.extend(f"- {e}" for e in exceptions)

        if args.apply and (frame_changes or new_controls):
            snap = BACKEND_DIR / "reports" / f"phase5_frames_snapshot_{datetime.now():%Y%m%d_%H%M%S}.json"
            snap.write_text(json.dumps(
                {"frames": [{"uid": f.uid, "name": f.orig_name, "daten_before": f.orig_daten} for f in frame_changes],
                 "created_controls": list(new_controls)}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
            lines += ["", f"Snapshot: `{snap}`"]
            async with conn.transaction():
                for uid, c in new_controls.items():
                    await conn.execute(
                        "insert into sys_control_dict (uid, name, daten, historisch, link_uid) "
                        "values ($1::uuid, $2, $3::jsonb, 0, $1::uuid)",
                        uid, c["name"], json.dumps(c["daten"], ensure_ascii=False),
                    )
                for f in frame_changes:
                    await conn.execute(
                        "update sys_framedaten set daten = $1::jsonb, name = $2, modified_at = now() where uid = $3::uuid",
                        json.dumps(f.daten, ensure_ascii=False), f.name, f.uid,
                    )
        report = "\n".join(lines) + "\n"
        if args.out:
            Path(args.out).write_text(report, encoding="utf-8")
        print(report if not args.quiet else f"{len(frame_changes)} Frames, {len(new_controls)} neue Controls")
        return 1 if (args.check and (frame_changes or new_controls)) else 0
    finally:
        await conn.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--golden", required=True, help="Golden-Master vor der Migration (phase5_frame_golden.py capture)")
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
