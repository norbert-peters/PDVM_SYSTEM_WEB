"""Legt die Theme-Pakete "Red Theme", "Pink Theme" und "Brown Theme" in ``sys_layout`` an.

Aufruf (aus backend/, mit PYTHONUTF8=1):
    ..\\.venv\\Scripts\\python.exe tools\\seed_theme_packages_v1.py                            # Dry-Run (Standard)
    ..\\.venv\\Scripts\\python.exe tools\\seed_theme_packages_v1.py --apply --confirm-backup   # fehlende Pakete anlegen
    ..\\.venv\\Scripts\\python.exe tools\\seed_theme_packages_v1.py --apply --confirm-backup --force-update

- Aufbau wie die bestehenden Pakete (Varianten ``light``/``dark`` mit ``color``, ``font`` und Basis-Blocks).
- Jede Variante wird vor dem Schreiben geprueft: gueltige Werte (``theme_service.sanitize_package_variant``) und alle
  Pflicht-Kontrastpaare nach WCAG AA (``theme_service.check_contrast``). Bei einem Verstoss bricht das Tool ab.
- UIDs sind deterministisch (uuid5); bestehende Zeilen bleiben unveraendert, ausser mit --force-update
  (dann Snapshot nach backend/reports/).
- Die Pakete werden vom Mandanten im Theme-Editor freigegeben (Tab "Mandant": Standard-Paket / weitere Pakete);
  die Kopie in ``msy_layout`` entsteht beim Login.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import unquote

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core import theme_service  # noqa: E402
from app.core.pdvm_datetime import now_pdvm  # noqa: E402

_NAMESPACE = uuid.UUID("5d0e8b0a-7a5e-4d4b-9a57-7e0f3f6f0a11")
STEPS = ("50", "100", "200", "300", "400", "500", "600", "700", "800", "900")

FONT = {
    "primary": "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    "secondary": "Georgia, serif",
    "mono": "'Fira Code', 'Courier New', monospace",
    "scale": "1",
}

NEUTRAL_LIGHT = dict(zip(STEPS, ("#fafafa", "#f5f5f5", "#eeeeee", "#e0e0e0", "#bdbdbd", "#9e9e9e", "#757575", "#616161", "#424242", "#212121")))
NEUTRAL_DARK = dict(zip(STEPS, ("#1a1a1a", "#2a2a2a", "#3a3a3a", "#4a4a4a", "#6a6a6a", "#8a8a8a", "#aaaaaa", "#cacaca", "#e0e0e0", "#f5f5f5")))
STATUS_LIGHT = {"success": "#4caf50", "warning": "#ff9800", "error": "#f44336", "info": "#2196f3"}
STATUS_DARK = {"success": "#66bb6a", "warning": "#ffb74d", "error": "#ef5350", "info": "#42a5f5"}

BLUE_GREY = dict(zip(STEPS, ("#eceff1", "#cfd8dc", "#b0bec5", "#90a4ae", "#78909c", "#607d8b", "#546e7a", "#455a64", "#37474f", "#263238")))
PURPLE = dict(zip(STEPS, ("#f3e5f5", "#e1bee7", "#ce93d8", "#ba68c8", "#ab47bc", "#9c27b0", "#8e24aa", "#7b1fa2", "#6a1b9a", "#4a148c")))
TEAL = dict(zip(STEPS, ("#e0f2f1", "#b2dfdb", "#80cbc4", "#4db6ac", "#26a69a", "#009688", "#00897b", "#00796b", "#00695c", "#004d40")))

# primary-500 ist der Akzent. Hell: dunkel genug fuer weissen Text; Dunkel (``dark_accent``): hell genug fuer dunklen Text.
THEMES: Dict[str, Dict[str, Any]] = {
    "red": {
        "name": "Red Theme",
        "description": "Red Theme color schema",
        "primary": dict(zip(STEPS, ("#ffebee", "#ffcdd2", "#ef9a9a", "#e57373", "#ef5350", "#d32f2f", "#c62828", "#b71c1c", "#9a1717", "#7f1313"))),
        "secondary": BLUE_GREY,
        "dark_accent": "#e57373",
        "light": {"bg2": "#fff5f5", "bg3": "#ffebee", "text": "#8e1b1b", "on_secondary": "#37474f"},
        "dark": {"bg1": "#161010", "bg2": "#221717", "bg3": "#2f1f1f", "border": ("#3a2222", "#4d2c2c", "#6b3a3a")},
    },
    "pink": {
        "name": "Pink Theme",
        "description": "Pink Theme color schema",
        "primary": dict(zip(STEPS, ("#fce4ec", "#f8bbd0", "#f48fb1", "#f06292", "#ec407a", "#c2185b", "#ad1457", "#880e4f", "#6d0b3f", "#52082f"))),
        "secondary": PURPLE,
        "dark_accent": "#f06292",
        "light": {"bg2": "#fff5f8", "bg3": "#fce4ec", "text": "#880e4f", "on_secondary": "#6a1b9a"},
        "dark": {"bg1": "#170f13", "bg2": "#23161c", "bg3": "#301e27", "border": ("#3b2230", "#502d41", "#6e3d58")},
    },
    "brown": {
        "name": "Brown Theme",
        "description": "Brown Theme color schema",
        "primary": dict(zip(STEPS, ("#efebe9", "#d7ccc8", "#bcaaa4", "#a1887f", "#8d6e63", "#6d4c41", "#5d4037", "#4e342e", "#3e2723", "#2b1b17"))),
        "secondary": TEAL,
        "dark_accent": "#bcaaa4",
        "light": {"bg2": "#faf6f4", "bg3": "#efebe9", "text": "#4e342e", "on_secondary": "#00695c"},
        "dark": {"bg1": "#161210", "bg2": "#221b18", "bg3": "#2e2420", "border": ("#3a2e28", "#4d3e36", "#6a574c")},
    },
}


def _ramp(prefix: str, ramp: Dict[str, str]) -> Dict[str, str]:
    return {f"{prefix}-{step}": value for step, value in ramp.items()}


def build_variant(spec: Dict[str, Any], mode: str) -> Dict[str, Any]:
    primary = dict(spec["primary"])
    if mode == "light":
        light = spec["light"]
        accent = primary["500"]
        text, text_secondary, text_inverse = light["text"], "#616161", "#ffffff"
        bg1, bg2, bg3 = "#ffffff", light["bg2"], light["bg3"]
        border = (primary["100"], primary["200"], primary["300"])
        on_secondary, on_tertiary = light["on_secondary"], "#333333"
        neutral, status = NEUTRAL_LIGHT, STATUS_LIGHT
        hover, btn_text, sub_text = primary["600"], "#ffffff", "#616161"
        header_name = accent
    else:
        dark = spec["dark"]
        accent = spec["dark_accent"]
        primary["500"] = accent
        text, text_secondary, text_inverse = "#ffffff", "#b0b0b0", "#212121"
        bg1, bg2, bg3 = dark["bg1"], dark["bg2"], dark["bg3"]
        border = dark["border"]
        on_secondary, on_tertiary = "#e0e0e0", "#e0e0e0"
        neutral, status = NEUTRAL_DARK, STATUS_DARK
        hover, btn_text, sub_text = primary["300"], "#212121", "#b0b0b0"
        header_name = "#ffffff"

    color: Dict[str, str] = {}
    color.update(_ramp("primary", primary))
    color.update(_ramp("secondary", spec["secondary"]))
    color.update(_ramp("neutral", neutral))
    color.update(status)
    color.update({
        "background-primary": bg1, "background-secondary": bg2, "background-tertiary": bg3,
        "border-light": border[0], "border-medium": border[1], "border-dark": border[2],
        "text-primary": text, "text-secondary": text_secondary, "text-disabled": "#bdbdbd" if mode == "light" else "#6a6a6a",
        "text-inverse": text_inverse, "text-on-primary": accent if mode == "light" else "#ffffff",
        "text-on-secondary": on_secondary, "text-on-tertiary": on_tertiary,
    })
    return {
        "font": dict(FONT),
        "color": color,
        "block_surface_main": {"bg_color": bg1, "text_color": text},
        "block_header_std": {
            "bg_color": bg1, "text_color": text, "border_bottom": f"1px solid {border[0]}",
            "shadow": "0 1px 2px 0 rgba(0, 0, 0, 0.05)",
        },
        "block_header_mandant_std": {"text_color": header_name, "subtext_color": sub_text},
        "block_header_user_std": {"text_color": header_name, "subtext_color": sub_text},
        "block_sidebar_std": {"bg_color": bg2, "text_color": text, "border_right": f"1px solid {border[0]}"},
        "block_input_std": {"bg_color": bg1, "text_color": text, "border": f"1px solid {border[1]}", "radius": "0.375rem"},
        "block_btn_primary": {"bg_color": accent, "text_color": btn_text, "hover_bg": hover, "radius": "0.5rem"},
        "block_stichtag_std": {
            "bg_color": accent, "text_color": btn_text, "border": f"1px solid {border[0]}", "radius": "0.5rem",
        },
    }


def build_package(key: str) -> Dict[str, Any]:
    spec = THEMES[key]
    uid = str(uuid.uuid5(_NAMESPACE, key))
    stamp = f"{now_pdvm():.5f}"
    return {
        "ROOT": {
            "SELF_GUID": uid,
            "SELF_GILT_BIS": "9999365.99999",
            "SELF_LINK_UID": uid,
            "SELF_CREATED_AT": stamp,
            "SELF_MODIFIED_AT": stamp,
            "STRUCT_VERSION_APPLIED": 1,
        },
        "info": {
            "name": spec["name"],
            "created": datetime.now().strftime("%Y-%m-%d"),
            "version": "2.0",
            "description": spec["description"],
        },
        "light": build_variant(spec, "light"),
        "dark": build_variant(spec, "dark"),
    }


def verify(key: str, package: Dict[str, Any]) -> List[str]:
    """Fehlerliste: ungueltige Werte oder verletzte Kontrastpaare je Variante."""
    problems: List[str] = []
    for mode in ("light", "dark"):
        clean, invalid = theme_service.sanitize_package_variant(package[mode])
        problems += [f"{key}/{mode}: {msg}" for msg in invalid]
        for issue in theme_service.check_contrast(clean):
            if not issue["ok"]:
                problems.append(f"{key}/{mode}: Kontrast {issue['fg']} auf {issue['bg']} = {issue['ratio']}:1 (min {issue['min']}:1)")
    return problems


async def main(apply: bool, force_update: bool) -> int:
    import asyncpg

    from audit_system_data import load_env_url

    packages = {key: build_package(key) for key in THEMES}
    problems = [p for key, pkg in packages.items() for p in verify(key, pkg)]
    if problems:
        print("Pruefung fehlgeschlagen:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    url = load_env_url()
    conn = await asyncpg.connect(
        host="127.0.0.1" if url.hostname == "localhost" else url.hostname,
        port=url.port or 5432,
        user=url.username,
        password=unquote(url.password or ""),
        database="pdvm_system",
    )
    inserted: List[str] = []
    updated: List[str] = []
    skipped: List[str] = []
    snapshot: List[Dict[str, Any]] = []
    try:
        for key, package in packages.items():
            uid = uuid.UUID(package["ROOT"]["SELF_GUID"])
            name = package["info"]["name"]
            existing = await conn.fetchrow("SELECT uid, name, daten FROM sys_layout WHERE uid = $1", uid)
            if existing:
                if not force_update:
                    skipped.append(name)
                    continue
                snapshot.append({"uid": str(uid), "name": existing["name"], "daten": existing["daten"]})
                updated.append(name)
                if apply:
                    await conn.execute(
                        "UPDATE sys_layout SET daten = $2::jsonb, name = $3, modified_at = NOW() WHERE uid = $1",
                        uid, json.dumps(package, ensure_ascii=False), name,
                    )
                continue

            clash = await conn.fetchval("SELECT uid FROM sys_layout WHERE name = $1 AND historisch = 0", name)
            if clash:
                print(f"Namenskonflikt, uebersprungen: {name} (vorhanden als {clash})")
                skipped.append(name)
                continue
            inserted.append(name)
            if apply:
                await conn.execute(
                    "INSERT INTO sys_layout (uid, link_uid, daten, name, historisch, gilt_bis, created_at, modified_at) "
                    "VALUES ($1, $1, $2::jsonb, $3, 0, '9999-12-31 23:59:59', NOW(), NOW())",
                    uid, json.dumps(package, ensure_ascii=False), name,
                )
    finally:
        await conn.close()

    mode = "APPLY" if apply else "DRY-RUN"
    print(f"=== Theme-Pakete ({mode}) - Pruefung (Werte, Kontrast) bestanden ===")
    print(f"Angelegt: {len(inserted)}  Aktualisiert: {len(updated)}  Unveraendert: {len(skipped)}")
    for item in inserted:
        print(f"  + {item}")
    for item in updated:
        print(f"  ~ {item}")
    if apply and snapshot:
        snap_dir = BACKEND_DIR / "reports"
        snap_dir.mkdir(exist_ok=True)
        path = snap_dir / f"theme_packages_snapshot_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.json"
        path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(f"Snapshot: {path}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Schreiben (Standard: Dry-Run)")
    parser.add_argument("--confirm-backup", action="store_true", help="Bestaetigung, dass ein Backup existiert (Pflicht mit --apply)")
    parser.add_argument("--force-update", action="store_true", help="Bestehende Pakete mit diesen UIDs ueberschreiben (mit Snapshot)")
    args = parser.parse_args()
    if args.apply and not args.confirm_backup:
        raise SystemExit("--apply verlangt --confirm-backup")
    raise SystemExit(asyncio.run(main(args.apply, args.force_update)))
