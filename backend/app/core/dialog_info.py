"""Standard-Info-Frame fuer Dialoge (Info-Fenster hinter der Dialog-Ueberschrift).

Das Frame liegt in `sys_framedaten` und wird mit `backend/tools/seed_dialog_info_frame_v1.py` angelegt. Es gibt
genau ein Standard-Frame fuer alle Dialoge; der Dialog liefert nur die Laufzeitwerte (Gruppe `INFO`).
"""
from __future__ import annotations

import uuid

DIALOG_INFO_NAMESPACE = uuid.UUID("5c1d3e0a-7f4b-4a8e-9b21-6d0c4f3a9e17")
DIALOG_INFO_GROUP = "INFO"
DIALOG_INFO_FRAME_GUID = uuid.uuid5(DIALOG_INFO_NAMESPACE, "frame:dialog_info")


def dialog_info_control_uid(field: str) -> uuid.UUID:
    """Deterministische UID eines Info-Controls (`sys_control_dict`)."""
    return uuid.uuid5(DIALOG_INFO_NAMESPACE, f"control:{DIALOG_INFO_GROUP}:{field}")
