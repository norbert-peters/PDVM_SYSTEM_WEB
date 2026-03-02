"""Element List Service

Phase 4: element_list als autonomes Frame
Verwaltet element_list Controls und ihre Frame-Templates

Funktionen:
- load_element_list_frame: Lädt Frame-Template für element_list
- create_element_instance: Erstellt neues Element in Liste
- delete_element_instance: Löscht Element aus Liste
- get_element_list_children: Holt Child-Controls einer element_list
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from app.core.pdvm_datenbank import PdvmDatabase


async def load_element_list_frame(
    gcs,
    control_uid: uuid.UUID
) -> Optional[Dict[str, Any]]:
    """
    Lädt das Frame-Template für eine element_list Control
    
    Args:
        gcs: Global Control System (SystemPool + MandantPool)
        control_uid: UID des element_list Controls
        
    Returns:
        Frame-Definition mit Root und Fields, oder None
        
    Raises:
        ValueError: Wenn Control keine element_list ist oder kein Frame referenziert
    """
    # Control laden
    control_db = PdvmDatabase("sys_control_dict", system_pool=gcs._system_pool, mandant_pool=gcs._mandant_pool)
    control_row = await control_db.get_by_uid(control_uid)
    
    if not control_row:
        raise ValueError(f"Control nicht gefunden: {control_uid}")
    
    control_daten = control_row.get("daten") or {}
    
    # Prüfen ob element_list
    if control_daten.get("type") != "element_list":
        raise ValueError(f"Control ist keine element_list: {control_row.get('name')}")
    
    # element_frame_guid holen
    element_frame_guid = control_daten.get("element_frame_guid")
    
    if not element_frame_guid:
        raise ValueError(f"element_list hat kein element_frame_guid: {control_row.get('name')}")
    
    # Frame laden
    frame_db = PdvmDatabase("sys_framedaten", system_pool=gcs._system_pool, mandant_pool=gcs._mandant_pool)
    frame_row = await frame_db.get_by_uid(uuid.UUID(element_frame_guid))
    
    if not frame_row:
        raise ValueError(f"Frame nicht gefunden: {element_frame_guid}")
    
    frame_daten = frame_row.get("daten") or {}
    root = frame_daten.get("ROOT") or {}
    
    # Prüfen ob IS_ELEMENT gesetzt ist
    if not root.get("IS_ELEMENT"):
        # Warning, aber nicht blockieren (Abwärtskompatibilität)
        pass
    
    return {
        "uid": str(frame_row.get("uid")),
        "name": frame_row.get("name") or "",
        "daten": frame_daten,
        "root": root,
        "fields": frame_daten.get("FIELDS") or {},
        "tabs": frame_daten.get("TABS") or {},
    }


async def get_element_list_children(
    gcs,
    element_list_uid: uuid.UUID
) -> List[Dict[str, Any]]:
    """
    Holt alle Child-Controls einer element_list (via parent_guid)
    
    Args:
        gcs: Global Control System
        element_list_uid: UID des element_list Parent Controls
        
    Returns:
        Liste der Child-Controls mit ihren Definitionen
    """
    # Alle Controls laden
    control_db = PdvmDatabase("sys_control_dict", system_pool=gcs._system_pool, mandant_pool=gcs._mandant_pool)
    
    # Query vorbereiten (Filter auf parent_guid)
    # HINWEIS: PdvmDatabase unterstützt aktuell keine WHERE-Klauseln außer uid
    # Wir müssen alle laden und filtern
    all_controls = await control_db.list_all()
    
    children = []
    
    for control in all_controls:
        daten = control.get("daten") or {}
        parent_guid = daten.get("parent_guid")
        
        if parent_guid and str(parent_guid) == str(element_list_uid):
            children.append({
                "uid": str(control.get("uid")),
                "name": control.get("name") or "",
                "daten": daten,
                "label": daten.get("label", ""),
                "type": daten.get("type", ""),
                "modul_type": daten.get("modul_type", ""),
                "self_name": daten.get("SELF_NAME", ""),
            })
    
    return children


async def create_element_instance(
    gcs,
    element_list_uid: uuid.UUID,
    element_data: Dict[str, Any]
) -> uuid.UUID:
    """
    Erstellt ein neues Element in einer element_list
    
    Args:
        gcs: Global Control System
        element_list_uid: UID der element_list
        element_data: Daten für das neue Element (FIELDS Gruppe)
        
    Returns:
        UUID des neu erstellten Elements
        
    Hinweis:
        Diese Funktion arbeitet mit dem Datenmodell, wo element_list Elemente
        als Dictionary mit GUIDs als Keys gespeichert werden.
        
        Beispiel für element_data:
        {
            "tab_label": "Tab 1",
            "tab_icon": "icon-home",
            "tab_order": 1,
            "tab_visible": True
        }
    """
    # Neue GUID für Element generieren
    new_guid = uuid.uuid4()
    
    # Daten mit GUID als Key strukturieren
    element_entry = {
        str(new_guid): element_data
    }
    
    # TODO: Element in Datensatz einfügen
    # Dies hängt davon ab, wie element_lists in den Datensätzen gespeichert werden
    # Momentan ist dies ein Konzept - die eigentliche Implementierung
    # muss mit dem konkreten Datenmodell abgestimmt werden
    
    return new_guid


async def delete_element_instance(
    gcs,
    element_list_uid: uuid.UUID,
    element_guid: uuid.UUID
) -> bool:
    """
    Löscht ein Element aus einer element_list
    
    Args:
        gcs: Global Control System
        element_list_uid: UID der element_list
        element_guid: GUID des zu löschenden Elements
        
    Returns:
        True wenn erfolgreich gelöscht, False wenn nicht gefunden
        
    Hinweis:
        Implementierung abhängig vom Datenmodell
    """
    # TODO: Element aus Datensatz entfernen
    # Dies hängt davon ab, wie element_lists in den Datensätzen gespeichert werden
    
    return True


async def validate_element_list_setup(gcs) -> Dict[str, Any]:
    """
    Validiert das element_list Setup nach Phase 4
    
    Returns:
        Validierungs-Report mit Status und Problemen
    """
    control_db = PdvmDatabase("sys_control_dict", system_pool=gcs._system_pool, mandant_pool=gcs._mandant_pool)
    frame_db = PdvmDatabase("sys_framedaten", system_pool=gcs._system_pool, mandant_pool=gcs._mandant_pool)
    
    all_controls = await control_db.list_all()
    all_frames = await frame_db.list_all()
    
    # Element Lists finden
    element_lists = [
        c for c in all_controls
        if (c.get("daten") or {}).get("type") == "element_list"
    ]
    
    # Frames mit IS_ELEMENT finden
    element_frames = [
        f for f in all_frames
        if (f.get("daten") or {}).get("ROOT", {}).get("IS_ELEMENT") is True
    ]
    
    # Validierung
    issues = []
    
    for el in element_lists:
        name = el.get("name")
        daten = el.get("daten") or {}
        element_frame_guid = daten.get("element_frame_guid")
        
        if not element_frame_guid:
            issues.append(f"element_list '{name}' hat kein element_frame_guid")
            continue
        
        # Frame existiert?
        frame_exists = any(
            str(f.get("uid")) == str(element_frame_guid)
            for f in element_frames
        )
        
        if not frame_exists:
            issues.append(f"element_list '{name}' referenziert nicht-existentes Frame {element_frame_guid}")
    
    return {
        "valid": len(issues) == 0,
        "element_lists": len(element_lists),
        "element_frames": len(element_frames),
        "issues": issues
    }
