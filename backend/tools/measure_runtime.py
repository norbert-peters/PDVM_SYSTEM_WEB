"""Laufzeitmessung (read-only) gegen ein laufendes Backend.

Zugangsdaten ausschliesslich ueber Umgebungsvariablen:
  PDVM_USER, PDVM_PASSWORD, optional PDVM_BASE_URL (Default http://127.0.0.1:8000; "localhost" kostet unter Windows ~0,2 s je neuer Verbindung)

Aufruf:
  python tools/measure_runtime.py [--runs 5] [--mandant <uid>]
"""
import argparse
import json
import os
import statistics
import sys
import time

import httpx


def timed(client, method, url, **kw):
    t0 = time.perf_counter()
    r = client.request(method, url, **kw)
    return (time.perf_counter() - t0) * 1000.0, r


def collect_commands(node, out):
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, str) and k.upper() in ("COMMAND", "DIALOG", "DIALOG_GUID", "GO_DIALOG"):
                out.append((k, v))
            collect_commands(v, out)
    elif isinstance(node, list):
        for v in node:
            collect_commands(v, out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--mandant", default=None)
    ap.add_argument("--dump-menu", action="store_true")
    args = ap.parse_args()

    base = os.environ.get("PDVM_BASE_URL", "http://127.0.0.1:8000")
    user = os.environ["PDVM_USER"]
    pw = os.environ["PDVM_PASSWORD"]
    results = {}

    def rec(name, ms, status):
        results.setdefault(name, {"ms": [], "status": status})["ms"].append(ms)
        results[name]["status"] = status

    with httpx.Client(base_url=base, timeout=60) as c:
        ms, r = timed(c, "POST", "/api/auth/login", data={"username": user, "password": pw})
        rec("login", ms, r.status_code)
        if r.status_code != 200:
            print("Login fehlgeschlagen:", r.status_code, r.text[:200])
            sys.exit(1)
        login = r.json()
        c.headers["Authorization"] = f"Bearer {login['access_token']}"
        mandant = args.mandant or login.get("auto_select_mandant")
        if not mandant and login.get("mandanten"):
            mandant = login["mandanten"][0]["id"]
        print("Mandanten:", [(m["id"], m["name"]) for m in login.get("mandanten", [])], "-> gewaehlt:", mandant)

        ms, r = timed(c, "POST", "/api/mandanten/select", json={"mandant_id": mandant})
        rec("mandant_select", ms, r.status_code)

        for _ in range(args.runs):
            ms, r = timed(c, "GET", "/api/menu/start")
            rec("menu_start", ms, r.status_code)
        menu = r.json() if r.status_code == 200 else {}
        if args.dump_menu:
            print(json.dumps(menu, indent=1, ensure_ascii=False)[:6000])

        cmds = []
        collect_commands(menu, cmds)
        print("Menue-Kommandos (Auszug):", cmds[:10])

        for _ in range(args.runs):
            ms, r = timed(c, "GET", "/api/auth/me")
            rec("auth_me", ms, r.status_code)

        # Dialoge aus den App-Menues sammeln (go_pdvm_dialog), je Dialog+Tabelle einmal
        dialogs = {}
        for app in ("ADMINISTRATION", "BENUTZERDATEN", "TESTBEREICH", "PERSONALWESEN", "FINANZWESEN"):
            ms, r = timed(c, "GET", f"/api/menu/app/{app}")
            rec("menu_app", ms, r.status_code)
            md = (r.json() or {}).get("menu_data") or {} if r.status_code == 200 else {}
            for grp in ("GRUND", "VERTIKAL"):
                for item in (md.get(grp) or {}).values():
                    cmd = item.get("command") or {}
                    if cmd.get("handler") == "go_pdvm_dialog":
                        p = cmd.get("params") or {}
                        if p.get("dialog_guid"):
                            dialogs[(p["dialog_guid"], p.get("table") or "")] = item.get("label")
        print(f"{len(dialogs)} Dialog-Einstiege gefunden")

        per_dialog = []
        for (dguid, table), label in dialogs.items():
            q = {"dialog_table": table} if table else {}
            for _ in range(args.runs):
                ms_d, rd = timed(c, "GET", f"/api/dialogs/{dguid}", params=q)
                rec("dialog_definition", ms_d, rd.status_code)
            ms_r, rr = timed(c, "POST", f"/api/dialogs/{dguid}/rows", params=q, json={"limit": 200, "offset": 0})
            rec("dialog_rows", ms_r, rr.status_code)
            ms_m, rm, nrows = None, None, None
            view_guid = rd.json().get("view_guid") if rd.status_code == 200 else None
            if view_guid:
                for _ in range(args.runs):
                    ms_m, rm = timed(
                        c, "POST", f"/api/views/{view_guid}/matrix",
                        params={"table": table} if table else {},
                        json={"include_historisch": True, "limit": 200, "offset": 0},
                    )
                    rec("view_matrix", ms_m, rm.status_code)
                if rm.status_code == 200:
                    nrows = len(rm.json().get("rows") or [])
            per_dialog.append((label, table, rd.status_code, ms_d, rr.status_code, ms_r,
                               None if rm is None else rm.status_code, ms_m, nrows))

        print(f"\n{'Dialog':<32}{'Tabelle':<24}{'Def':>10}{'Rows':>10}{'Matrix':>10}{'Zeilen':>8}  (letzter Lauf, ms)")
        for lab, tab, sd, md_, sr, mr, sm, mm, n in per_dialog:
            print(f"{str(lab)[:30]:<32}{tab[:22]:<24}{sd:>4}/{md_:>5.0f}{sr:>4}/{mr:>5.0f}"
                  f"{(str(sm) + '/' + format(mm, '.0f')) if mm is not None else '-':>10}{n if n is not None else '-':>8}")

    print(f"\n{'Messung':<22}{'HTTP':>6}{'min':>9}{'median':>9}{'max':>9}  (ms, n={args.runs})")
    for name, v in results.items():
        m = v["ms"]
        print(f"{name:<22}{v['status']:>6}{min(m):>9.0f}{statistics.median(m):>9.0f}{max(m):>9.0f}")


if __name__ == "__main__":
    main()
