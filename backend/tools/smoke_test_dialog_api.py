"""Smoketest fuer Dialog API (Definition + Draft-Flow).

Usage:
  python backend/tools/smoke_test_dialog_api.py
"""
from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List

import requests

DIALOGS = [
    "9f06711e-4ad8-4ea4-9837-2f40f3a6f101",  # sys_control_dict
    "1f3a0e00-48bb-4a08-9cb8-7a7d52f23001",  # sys_dialogdaten
]


def _json_or_text(response: requests.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return {"raw": response.text[:500]}


def _create_session(*, auth_login_url: str, token: str | None, username: str | None, password: str | None) -> requests.Session:
    session = requests.Session()

    if token:
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session

    if username and password:
        login_resp = session.post(
            auth_login_url,
            data={"username": username, "password": password},
            timeout=15,
        )
        payload = _json_or_text(login_resp)
        if login_resp.status_code != 200:
            raise RuntimeError(f"Login fehlgeschlagen ({login_resp.status_code}): {payload}")
        access_token = payload.get("access_token") if isinstance(payload, dict) else None
        if not access_token:
            raise RuntimeError("Login erfolgreich, aber kein access_token in Response")
        session.headers.update({"Authorization": f"Bearer {access_token}"})

    return session


def _select_mandant(session: requests.Session, *, base_url: str, mandant_id: str | None) -> Dict[str, Any]:
    mandanten_url = f"{base_url}/api/mandanten"
    select_url = f"{base_url}/api/mandanten/select"

    r_list = session.get(mandanten_url, timeout=15)
    list_payload = _json_or_text(r_list)
    if r_list.status_code != 200:
        raise RuntimeError(f"Mandanten-Liste fehlgeschlagen ({r_list.status_code}): {list_payload}")

    if not isinstance(list_payload, list) or not list_payload:
        raise RuntimeError("Mandanten-Liste ist leer")

    selected = None
    if mandant_id:
        selected = next((m for m in list_payload if str(m.get("id")) == str(mandant_id)), None)
        if selected is None:
            raise RuntimeError(f"Mandant nicht gefunden: {mandant_id}")
    else:
        selected = list_payload[0]

    selected_id = str(selected.get("id") or "").strip()
    if not selected_id:
        raise RuntimeError("Mandant ohne id in Mandanten-Liste")

    r_select = session.post(select_url, json={"mandant_id": selected_id}, timeout=20)
    select_payload = _json_or_text(r_select)
    if r_select.status_code != 200:
        raise RuntimeError(f"Mandant-Select fehlgeschlagen ({r_select.status_code}): {select_payload}")

    return {
        "mandant_id": selected_id,
        "mandant_name": selected.get("name"),
        "select_status": r_select.status_code,
        "select_payload": select_payload,
    }


def run(*, base_url: str, token: str | None, username: str | None, password: str | None, mandant_id: str | None) -> Dict[str, Any]:
    auth_login_url = f"{base_url}/api/auth/login"
    dialogs_base = f"{base_url}/api/dialogs"

    session = _create_session(auth_login_url=auth_login_url, token=token, username=username, password=password)
    selected = _select_mandant(session, base_url=base_url, mandant_id=mandant_id)
    results: List[Dict[str, Any]] = []

    for dialog_guid in DIALOGS:
        item: Dict[str, Any] = {"dialog_guid": dialog_guid}
        item["pass_criteria"] = {
            "definition_status_expected": 200,
            "draft_start_status_expected": 200,
        }

        r_def = session.get(f"{dialogs_base}/{dialog_guid}", timeout=15)
        item["definition_status"] = r_def.status_code
        def_json = _json_or_text(r_def)

        if r_def.status_code != 200:
            item["error"] = "definition_failed"
            item["definition_body"] = def_json
            item["passed"] = False
            results.append(item)
            continue

        r_start = session.post(f"{dialogs_base}/{dialog_guid}/draft/start", json={}, timeout=15)
        item["draft_start_status"] = r_start.status_code
        start_json = _json_or_text(r_start)

        if r_start.status_code != 200:
            item["error"] = "draft_start_failed"
            item["draft_start_body"] = start_json
            item["passed"] = False
            results.append(item)
            continue

        draft_id = (start_json or {}).get("draft_id")
        item["draft_id"] = draft_id

        daten = (start_json or {}).get("daten") if isinstance(start_json, dict) else {}
        if not isinstance(daten, dict):
            daten = {}

        root = daten.get("ROOT") if isinstance(daten.get("ROOT"), dict) else {}
        if not root.get("SELF_NAME"):
            root["SELF_NAME"] = f"smoke_{dialog_guid[:8]}"
        daten["ROOT"] = root

        r_update = session.put(
            f"{dialogs_base}/{dialog_guid}/draft/{draft_id}",
            json={"daten": daten},
            timeout=15,
        )
        item["draft_update_status"] = r_update.status_code
        update_json = _json_or_text(r_update)

        if r_update.status_code != 200:
            item["error"] = "draft_update_failed"
            item["draft_update_body"] = update_json
            item["passed"] = False
            results.append(item)
            continue

        issues = update_json.get("validation_issues") if isinstance(update_json, dict) else None
        item["draft_update_issues"] = len(issues) if isinstance(issues, list) else None

        r_commit = session.post(f"{dialogs_base}/{dialog_guid}/draft/{draft_id}/commit", json={}, timeout=15)
        item["draft_commit_status"] = r_commit.status_code
        commit_json = _json_or_text(r_commit)

        if r_commit.status_code == 200:
            item["created_uid"] = commit_json.get("uid") if isinstance(commit_json, dict) else None
            item["created_name"] = commit_json.get("name") if isinstance(commit_json, dict) else None
        else:
            item["draft_commit_body"] = commit_json

        item["passed"] = item.get("definition_status") == 200 and item.get("draft_start_status") == 200

        results.append(item)

    overall_pass = all(bool(x.get("passed")) for x in results)
    return {
        "base_url": base_url,
        "mandant": selected,
        "overall_pass": overall_pass,
        "results": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dialog API Smoke Test")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API Base URL, z.B. http://localhost:8000")
    parser.add_argument("--token", default=None, help="JWT access token (Bearer) fuer API Calls")
    parser.add_argument("--username", default=None, help="Login username/email fuer /api/auth/login")
    parser.add_argument("--password", default=None, help="Login passwort fuer /api/auth/login")
    parser.add_argument("--mandant-id", default=None, help="Optionale Mandant-ID fuer /api/mandanten/select")
    args = parser.parse_args()

    out = run(
        base_url=args.base_url,
        token=args.token,
        username=args.username,
        password=args.password,
        mandant_id=args.mandant_id,
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))
