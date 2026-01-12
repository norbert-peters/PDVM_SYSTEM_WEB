# PDVM Menü-System

Das Menü-System des PDVM folgt dem Desktop-Vorbild und wird vollständig datengetrieben aus der Tabelle `sys_menudaten` generiert.

## 1. Datenstruktur

### 1.1 Root-Struktur
Jedes Menü ist ein JSONB-Objekt mit drei Hauptgruppen:

```json
{
  "ROOT": {
    "NAME": "Startmenü",
    "GRUND": "hori",    // Ausrichtung GRUND-Menü ("hori" | "vert")
    "VERTIKAL": "vert"  // Ausrichtung VERTIKAL-Menü ("hori" | "vert")
  },
  "GRUND": { ... },    // Items für horizontales Hauptmenü
  "VERTIKAL": { ... }  // Items für vertikale Sidebar
}
```

### 1.2 Item-Typen
Jeder Eintrag wird durch seine GUID als Key identifiziert.

| Typ | Beschreibung | Wichtige Felder |
|-----|--------------|-----------------|
| `BUTTON` | Ausführbare Aktion | `command`, `label`, `icon` |
| `SUBMENU` | Container für Unterelemente | `label`, `icon` |
| `SEPARATOR` | Trennlinie | `sort_order` |
| `SPACER` | Platzhalter für Templates | `template_guid` |

### 1.3 Item-Eigenschaften
Alle Items teilen sich folgende Basis-Eigenschaften:

```json
"GUID": {
  "type": "BUTTON",
  "label": "Beschriftung",
  "icon": "icon_name",      // Optional
  "parent_guid": "GUID",    // Null für Root-Level
  "sort_order": 1,          // Sortierung innerhalb der Ebene
  "visible": true,
  "enabled": true,
  "tooltip": "Hilfetext",
  "command": {              // Nur bei BUTTON
    "handler": "action_name",
    "params": { ... }
  },
  "template_guid": null     // Nur bei SPACER (verweist auf anderes Menü)
}
```

## 2. Rendering Logik

Das Rendering erfolgt zentral durch einen generischen `MenuRenderer`, der für beide Menü-Bereiche (GRUND und VERTIKAL) identisch funktioniert.

### 2.1 Hierarchie-Auflösung
1.  **Filterung:** Items werden nach `parent_guid` gruppiert.
2.  **Sortierung:** Innerhalb einer Gruppe wird nach `sort_order` sortiert.
3.  **Rekursion:**
    *   Items ohne `parent_guid` bilden die Root-Ebene des jeweiligen Bereichs (GRUND oder VERTIKAL).
    *   Items vom Typ `SUBMENU` rendern ihre Kinder rekursiv.

### 2.2 Template-Expansion (Backend)
Templates (`SPACER` Items) werden **vor** der Auslieferung an das Frontend im Backend aufgelöst.
1.  API findet `SPACER` Item mit `template_guid`.
2.  Lädt das referenzierte Menü aus `sys_menudaten`.
3.  Extrahiert die Items der entsprechenden Gruppe (z.B. GRUND).
4.  Ersetzt den SPACER durch die Items des Templates.

## 3. Architektur-Integration

*   **Datenquelle:** `sys_menudaten` (im `pdvm_system` Schema).
*   **Zugriff:** Über `PdvmCentralDatabase.load()`.
*   **API:** `menu.py` liefert fertig expandierte JSON-Struktur.
*   **Frontend:**
    *   `AppLayout` platziert die Container.
    *   `HorizontalMenu` (GRUND) und `VerticalMenu` (VERTIKAL) nutzen denselben `MenuRenderer`.
    *   Unterschied ist nur das CSS/Styling der Root-Ebene (Horizontal vs. Vertikal).

## 4. Commands
Aktionen werden als JSON-Objekt im `command` Feld definiert und vom `MenuHandler` im Frontend interpretiert.

```json
"command": {
  "handler": "open_view",
  "params": { "view_guid": "..." }
}
```
