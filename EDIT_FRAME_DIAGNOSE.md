# Edit Frame Diagnose & Lösungsstrategie

**Datum:** 13. Februar 2026  
**Frame-GUID:** `4413571e-6bf6-4f42-b81a-bc898db4880c`  
**Dialog-GUID:** `4413571e-6bf6-4f42-b81a-bc898db4880c`

## ✅ Status: Backend ist KORREKT

### Erfolgreiche Controls (4 von 5)

Die folgenden Controls können ihre Daten korrekt mappen:

| Control | Type | Gruppe | Feld | Wert | Status |
|---------|------|--------|------|------|--------|
| **Dialog-Name** | string | ROOT | SELF_NAME | "Edit Frame" | ✅ |
| **Edit-Type** | string | ROOT | EDIT_TYPE | "edit_frame" | ✅ |
| **Tabs** | element_list | ROOT | TABS | 2 | ✅ |
| **Tabs (Liste)** | element_list | ROOT | TABS_DEF | Dict[2] | ✅ |

### Problematisches Control (1 von 5)

| Control | Type | Problem | Ursache |
|---------|------|---------|---------|
| **Controls (FIELDS)** | element_list | ❌ Feld nicht gefunden | Konzeptproblem: Versucht Meta-Ebene zu bearbeiten |

## 🔍 Problemanalyse

### Das FIELDS-Control Problem

Das `FIELDS` element_list Control versucht, auf `daten.FIELDS.FIELDS` zuzugreifen, aber:
- `daten.FIELDS` ist ein **Dict mit GUID-Keys** (Frame-META-Struktur):
  ```json
  "FIELDS": {
    "9ccb9eb8-...": { "tab": 2, "feld": "FIELDS", ... },
    "a88ee663-...": { "tab": 2, "feld": "TABS_DEF", ... }
  }
  ```
- Es gibt **kein Feld namens "FIELDS"** innerhalb dieser Gruppe
- Das ist ein **konzeptuelles Self-Editing Problem**

**Warum?** Das Frame versucht, seine eigenen Control-Definitionen zu bearbeiten (Meta-Ebene).

## 🎯 Test-Anleitung

### 1. Backend API-Test

```bash
# Terminal 1: Backend starten (falls nicht läuft)
cd backend
uvicorn app.main:app --reload --port 8010

# Terminal 2: API testen
curl http://localhost:8010/api/dialogs/4413571e-6bf6-4f42-b81a-bc898db4880c
curl http://localhost:8010/api/dialogs/4413571e-6bf6-4f42-b81a-bc898db4880c/record/4413571e-6bf6-4f42-b81a-bc898db4880c
```

**Erwartetes Ergebnis:**
- Dialog-Definition mit Frame und 5 Controls
- Record-Response mit `daten.ROOT.SELF_NAME = "Edit Frame"`, etc.

### 2. Frontend-Test

Im Browser öffnen:
```
http://localhost:5173  # oder Frontend-Port
```

**Browser DevTools (F12) öffnen:**
1. **Console-Tab:** Suche nach JavaScript-Fehlern
2. **Network-Tab:** Prüfe API-Requests
   - Request zu `/api/dialogs/.../record/...`
   - Response sollte JSON mit `daten.ROOT` enthalten

**Erwartung:**
- 4 Controls sollten Daten anzeigen:
  - Dialog-Name: "Edit Frame"
  - Edit-Type: "edit_frame"
  - Tabs: "2"
  - Tabs (Liste): [2 Einträge]
  
- 1 Control zeigt keine Daten:
  - Controls (FIELDS): leer oder Fehler

## 🛠️ Lösungsvorschläge

### Kurzfristig (MVP)

**Option A: FIELDS Control entfernen**
```bash
python backend/simplify_frame_for_mvp.py
```
- Entfernt das problematische FIELDS Control
- 4 funktionierende Controls bleiben
- Frame ist editierbar für ROOT-Felder

**Option B: FIELDS Control deaktivieren**
- In Frame-Definition: `read_only: true` setzen
- Warnhinweis im Frontend anzeigen

### Mittelfristig

**Spezieller Edit-Type erstellen:**
- `edit_type: "meta_editor"` für Frame-Metadaten
- Spezielle Logik für GUID-basierte Collections
- Separate UI für Control-Verwaltung

### Langfristig

**Architektur überdenken:**
1. **Trennung:** Meta-Daten vs. Business-Daten
2. **Verschiedene Frames:**
   - `edit_frame_data`: Für Datenwerte (ROOT-Gruppe)
   - `edit_frame_meta`: Für Control-Definitionen (FIELDS-Gruppe)
3. **Hierarchische Frames:**
   - Master-Frame: Für Root-Felder
   - Sub-Frame: Für Control-Liste (eigenes Frame pro Control)

## 📝 Nächste Schritte

### Wenn Frontend keine Daten zeigt (trotz Backend korrekt):

1. **Prüfe Browser Console** auf Fehler
2. **Prüfe Network Tab** auf API-Responses
3. **Prüfe Frontend-Code:**
   - Wie werden `daten[gruppe][feld]` abgerufen?
   - Gibt es Error-Handling für fehlende Werte?
   - Werden Controls korrekt gerendert?

### Wenn Backend angepasst werden muss:

1. **Entferne FIELDS Control** temporär
2. **Teste mit 4 Controls** ob Frontend funktioniert
3. **Implementiere Meta-Editor** später als separate Funktion

## 🧪 Bereitgestellte Test-Skripte

Alle Skripte sind im `backend/` Verzeichnis:

| Skript | Zweck |
|--------|-------|
| `check_frame_4413571e.py` | Prüft Frame-Struktur |
| `check_frame_controls.py` | Prüft Controls in sys_control_dict |
| `test_frame_load.py` | Simuliert Datensatz-Laden |
| `simulate_api_response.py` | Simuliert komplette API |
| `full_api_test.py` | **Vollständiger API-Test** ⭐ |
| `simplify_frame_for_mvp.py` | Entfernt FIELDS Control |

**Empfehlung:** Starte mit `full_api_test.py` - zeigt exakt, was Frontend bekommt.

## ✅ Fazit

**Backend-Status:** ✅ Funktioniert korrekt für 4 von 5 Controls

**Problem-Quelle:** 
- Wahrscheinlich **Frontend** (wenn auch die 4 funktionierenden Controls keine Daten zeigen)
- Oder **konzeptuelles Design-Problem** (Self-Editing von Frames)

**Empfohlene Aktion:**
1. Browser DevTools öffnen und Frontend prüfen
2. Falls Frontend-Problem: Frontend-Code debuggen
3. Falls nur FIELDS-Problem: Control entfernen für MVP
