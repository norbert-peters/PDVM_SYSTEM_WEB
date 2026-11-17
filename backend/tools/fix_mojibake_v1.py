"""
Repariert doppelt kodierte UTF-8-Zeichen in Quelldateien (z. B. `zurÃ¼cksetzen` -> `zurücksetzen`).

Ursache: UTF-8-Text wurde als Windows-1252 gelesen und erneut als UTF-8 gespeichert. Repariert werden nur Folgen, die
sich eindeutig als UTF-8-Bytes (je Zeichen ein cp1252-/Latin-1-Byte) dekodieren lassen; alle anderen Zeichen bleiben.
Zeilenenden und BOM bleiben unveraendert. Mehrfach doppelt kodierte Stellen werden wiederholt repariert.

Aufruf aus backend/ (Standard ist Dry-Run, Standardpfad: app):
  ..\\.venv\\Scripts\\python.exe tools\\fix_mojibake_v1.py [Pfad ...]
  ..\\.venv\\Scripts\\python.exe tools\\fix_mojibake_v1.py --apply
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _byte(ch: str) -> int | None:
    try:
        return ch.encode("cp1252")[0]
    except UnicodeEncodeError:
        return ord(ch) if ord(ch) < 0x100 else None  # unbelegte cp1252-Stellen (0x81, 0x8D, ...) als Latin-1


def _need(lead: int) -> int:
    if 0xC2 <= lead <= 0xDF:
        return 2
    if 0xE0 <= lead <= 0xEF:
        return 3
    if 0xF0 <= lead <= 0xF4:
        return 4
    return 0


def repair(text: str) -> tuple[str, int]:
    out, i, fixed = [], 0, 0
    while i < len(text):
        lead = _byte(text[i]) if ord(text[i]) > 127 else None
        n = _need(lead) if lead is not None else 0
        if n and i + n <= len(text):
            raw = [_byte(c) for c in text[i : i + n]]
            if all(b is not None and 0x80 <= b <= 0xBF for b in raw[1:]):
                try:
                    out.append(bytes([lead, *raw[1:]]).decode("utf-8"))
                    i += n
                    fixed += 1
                    continue
                except UnicodeDecodeError:
                    pass
        out.append(text[i])
        i += 1
    return "".join(out), fixed


def repair_fully(text: str) -> tuple[str, int]:
    total = 0
    while True:
        text, fixed = repair(text)
        if not fixed:
            return text, total
        total += fixed


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", default=["app"])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--glob", default="*.py")
    args = ap.parse_args()

    changed = 0
    for base in args.paths:
        root = (BACKEND_DIR / base) if not Path(base).is_absolute() else Path(base)
        files = [root] if root.is_file() else sorted(root.rglob(args.glob))
        for path in files:
            raw = path.read_bytes()
            bom = raw.startswith(b"\xef\xbb\xbf")
            text = raw[3:].decode("utf-8") if bom else raw.decode("utf-8")
            new, fixed = repair_fully(text)
            if not fixed:
                continue
            changed += 1
            print(f"{path.relative_to(BACKEND_DIR)}: {fixed} Stelle(n)")
            if args.apply:
                data = new.encode("utf-8")
                path.write_bytes((b"\xef\xbb\xbf" + data) if bom else data)
    print(f"{changed} Datei(en) {'repariert' if args.apply else 'betroffen (Dry-Run)'}")
    sys.exit(0)


if __name__ == "__main__":
    main()
