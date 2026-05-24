from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

BACKEND_DIR = Path(__file__).resolve().parents[2]
I18N_POLICY_PATH = BACKEND_DIR / "config" / "i18n_policy_v1.json"


DEFAULT_POLICY = {
    "version": 1,
    "default_language": "DE-DE",
    "supported_languages": ["DE-DE", "EN-US", "IT-IT"],
    "language_aliases": {
        "DE": "DE-DE",
        "DEU": "DE-DE",
        "DE-DE": "DE-DE",
        "EN": "EN-US",
        "EN-US": "EN-US",
        "US-EN": "EN-US",
        "ENG": "EN-US",
        "IT": "IT-IT",
        "IT-IT": "IT-IT",
        "ITA": "IT-IT",
    },
}


def _load_policy() -> Dict[str, Any]:
    if not I18N_POLICY_PATH.exists():
        return dict(DEFAULT_POLICY)
    try:
        raw = json.loads(I18N_POLICY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return dict(DEFAULT_POLICY)
    if not isinstance(raw, dict):
        return dict(DEFAULT_POLICY)

    policy = dict(DEFAULT_POLICY)
    for key in ("version", "default_language", "supported_languages", "language_aliases"):
        if key in raw:
            policy[key] = raw.get(key)
    return policy


_POLICY = _load_policy()
DEFAULT_LANGUAGE_FALLBACK = str(_POLICY.get("default_language") or "DE-DE").upper()
SUPPORTED_LANGUAGES: List[str] = [str(x).upper() for x in (_POLICY.get("supported_languages") or [])]
LANGUAGE_ALIASES: Dict[str, str] = {
    str(k).upper(): str(v).upper() for k, v in (_POLICY.get("language_aliases") or {}).items()
}


def normalize_language(value: Any) -> str:
    s = str(value or "").strip().upper()
    if not s:
        return DEFAULT_LANGUAGE_FALLBACK
    return LANGUAGE_ALIASES.get(s, s)


def get_i18n_policy_summary() -> Dict[str, Any]:
    return {
        "version": _POLICY.get("version"),
        "default_language": DEFAULT_LANGUAGE_FALLBACK,
        "supported_languages": SUPPORTED_LANGUAGES,
        "alias_count": len(LANGUAGE_ALIASES),
        "policy_path": str(I18N_POLICY_PATH),
    }
