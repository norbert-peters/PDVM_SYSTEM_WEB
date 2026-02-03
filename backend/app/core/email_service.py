"""
Email Service (SMTP)

Verwendet SEND_EMAIL Konfiguration aus sys_mandanten.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import Dict, Any

logger = logging.getLogger(__name__)


def _truthy(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, (int, float)):
        try:
            return float(value) != 0.0
        except Exception:
            return False
    s = str(value).strip().lower()
    return s in {"1", "true", "yes", "y", "on"}


def build_smtp_config(raw: Dict[str, Any]) -> Dict[str, Any]:
    cfg = raw or {}
    smtp_tls = _truthy(cfg.get("SMTP_TLS"))
    if not smtp_tls:
        smtp_tls = _truthy(cfg.get("SMTP_STARTTLS"))
    return {
        "mail": str(cfg.get("MAIL") or "").strip(),
        "smtp_host": str(cfg.get("SMTP_HOST") or "").strip(),
        "smtp_port": int(cfg.get("SMTP_PORT") or 0) if str(cfg.get("SMTP_PORT") or "").strip() else 0,
        "smtp_user": str(cfg.get("SMTP_USER") or "").strip(),
        "smtp_pass": str(cfg.get("SMTP_PASS") or ""),
        "smtp_tls": smtp_tls,
        "smtp_ssl": _truthy(cfg.get("SMTP_SSL")),
        "reply_to": str(cfg.get("REPLY_TO") or "").strip(),
        "sender_name": str(cfg.get("SENDER_NAME") or "").strip(),
    }


def send_email(config: Dict[str, Any], to_email: str, subject: str, body: str) -> None:
    cfg = build_smtp_config(config)

    if not cfg["mail"]:
        raise ValueError("SEND_EMAIL.MAIL fehlt")
    if not cfg["smtp_host"]:
        raise ValueError("SEND_EMAIL.SMTP_HOST fehlt")
    if not cfg["smtp_port"]:
        raise ValueError("SEND_EMAIL.SMTP_PORT fehlt")

    msg = EmailMessage()
    sender = cfg["mail"]
    if cfg["sender_name"]:
        msg["From"] = f"{cfg['sender_name']} <{sender}>"
    else:
        msg["From"] = sender
    msg["To"] = to_email
    msg["Subject"] = subject
    if cfg["reply_to"]:
        msg["Reply-To"] = cfg["reply_to"]
    msg.set_content(body)

    try:
        if cfg["smtp_ssl"]:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(cfg["smtp_host"], cfg["smtp_port"], context=context) as server:
                if cfg["smtp_user"]:
                    server.login(cfg["smtp_user"], cfg["smtp_pass"])
                server.send_message(msg)
        else:
            with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"]) as server:
                server.ehlo()
                if cfg["smtp_tls"]:
                    context = ssl.create_default_context()
                    server.starttls(context=context)
                    server.ehlo()
                if cfg["smtp_user"]:
                    server.login(cfg["smtp_user"], cfg["smtp_pass"])
                server.send_message(msg)
        logger.info("✅ E-Mail gesendet an %s", to_email)
    except Exception as e:
        logger.error("❌ E-Mail-Versand fehlgeschlagen: %s", e)
        raise
