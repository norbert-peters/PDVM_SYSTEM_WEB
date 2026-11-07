"""Golden-Master fuer Frame-Definitionen (Phase 5, sys_framedaten-Migration).

Liest ueber die API (im selben Prozess) die aufgeloeste Runtime-Ausgabe ALLER Frames und speichert sie bzw.
vergleicht sie mit einem frueheren Stand. So ist nachweisbar, dass eine Datenmigration die Ausgabe nicht aendert.

Aufruf (aus backend/), Zugangsdaten per PDVM_USER / PDVM_PASSWORD:
    ..\\.venv\\Scripts\\python.exe tools\\phase5_frame_golden.py capture <datei.json>
    ..\\.venv\\Scripts\\python.exe tools\\phase5_frame_golden.py compare <alt.json> <neu.json> [--ignore key1,key2]
"""
import asyncio
import json
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_system_data import load_env_url  # noqa: E402
from seed_base_records import connect  # noqa: E402


async def frame_uids() -> list[str]:
    conn = await connect(load_env_url(), "pdvm_system", True)
    try:
        rows = await conn.fetch("select uid from sys_framedaten order by name, uid")
        return [str(r["uid"]) for r in rows if str(r["uid"])[:2] not in ("00", "55", "66")]
    finally:
        await conn.close()


def capture(path: str) -> None:
    from fastapi.testclient import TestClient
    from app.main import app

    uids = asyncio.run(frame_uids())
    result = {}
    with TestClient(app) as client:
        r = client.post("/api/auth/login", data={"username": os.environ["PDVM_USER"], "password": os.environ["PDVM_PASSWORD"]})
        token = r.json()["access_token"]
        mandant = r.json()["mandanten"][0]["id"]
        headers = {"Authorization": f"Bearer {token}"}
        client.post("/api/mandanten/select", json={"mandant_id": mandant}, headers=headers)
        for uid in uids:
            resp = client.get(f"/api/dialogs/frame/{uid}", headers=headers)
            result[uid] = {"status": resp.status_code, "body": resp.json() if resp.status_code == 200 else resp.text[:200]}
    Path(path).write_text(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    ok = sum(1 for v in result.values() if v["status"] == 200)
    print(f"{ok}/{len(result)} Frames gespeichert nach {path}")


def _diff(old, new, path, ignore, out):
    if isinstance(old, dict) and isinstance(new, dict):
        for key in sorted(set(old) | set(new)):
            if key in ignore:
                continue
            if key not in old:
                out.append(f"+ {path}/{key} = {json.dumps(new[key], ensure_ascii=False)[:100]}")
            elif key not in new:
                out.append(f"- {path}/{key} = {json.dumps(old[key], ensure_ascii=False)[:100]}")
            else:
                _diff(old[key], new[key], f"{path}/{key}", ignore, out)
    elif old != new:
        out.append(f"~ {path}: {json.dumps(old, ensure_ascii=False)[:80]} -> {json.dumps(new, ensure_ascii=False)[:80]}")


def compare(old_path: str, new_path: str, ignore: set[str]) -> int:
    old = json.loads(Path(old_path).read_text(encoding="utf-8"))
    new = json.loads(Path(new_path).read_text(encoding="utf-8"))
    total = 0
    for uid in sorted(set(old) | set(new)):
        out: list[str] = []
        _diff(old.get(uid), new.get(uid), uid[:8], ignore, out)
        if out:
            name = (old.get(uid) or {}).get("body", {}).get("name") if isinstance((old.get(uid) or {}).get("body"), dict) else ""
            print(f"== Frame {name} ({uid[:8]}): {len(out)} Abweichungen")
            for line in out[:40]:
                print("  ", line)
            total += len(out)
    print(f"Abweichungen gesamt: {total}")
    return 1 if total else 0


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "capture":
        capture(sys.argv[2])
    elif len(sys.argv) >= 4 and sys.argv[1] == "compare":
        ign = set()
        if "--ignore" in sys.argv:
            ign = set(sys.argv[sys.argv.index("--ignore") + 1].split(","))
        sys.exit(compare(sys.argv[2], sys.argv[3], ign))
    else:
        print(__doc__)
        sys.exit(2)
