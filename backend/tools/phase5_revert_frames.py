"""Rollback der Frame-Migration aus dem Snapshot von phase5_normalize_frames.py.

Aufruf (aus backend/):
    ..\\.venv\\Scripts\\python.exe tools\\phase5_revert_frames.py <snapshot.json>
Loescht die dabei angelegten Controls und stellt daten/name der Frames wieder her.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_system_data import load_env_url  # noqa: E402
from seed_base_records import connect  # noqa: E402


async def main(path: str) -> None:
    snap = json.loads(Path(path).read_text(encoding="utf-8"))
    conn = await connect(load_env_url(), "pdvm_system", False)
    try:
        async with conn.transaction():
            for uid in snap["created_controls"]:
                await conn.execute("delete from sys_control_dict where uid = $1::uuid", uid)
            for frame in snap["frames"]:
                await conn.execute(
                    "update sys_framedaten set daten = $1::jsonb, name = $2 where uid = $3::uuid",
                    json.dumps(frame["daten_before"], ensure_ascii=False), frame["name"], frame["uid"],
                )
        print(f"zurueckgesetzt: {len(snap['frames'])} Frames, {len(snap['created_controls'])} Controls entfernt")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
