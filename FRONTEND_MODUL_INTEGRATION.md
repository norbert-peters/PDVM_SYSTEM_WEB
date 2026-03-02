# Frontend Integration: Automatische MODUL-Auswahl

## Problem gelöst

**Vorher:** User bekommt Fehlermeldung "modul_type wurde nicht übergeben"

**Jetzt:** Backend gibt strukturierte Response mit verfügbaren Modulen → Frontend zeigt Dialog

## Flow

```typescript
// 1. User klickt "Neuer Satz"
async function handleNeuerSatz() {
  const name = await promptForName(); // "test_field"
  
  // 2. Versuche Create (OHNE modul_type)
  try {
    const response = await fetch(`/api/dialogs/${dialogGuid}/record`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name })
    });
    
    // 3. Check Status Code
    if (response.status === 428) {
      // MODUL-Auswahl erforderlich!
      const error = await response.json();
      const { available_moduls, modul_group_key } = error.detail;
      
      // 4. Zeige Modul-Dialog
      const selectedModul = await showModulSelectionDialog(available_moduls);
      
      // 5. Retry mit modul_type
      const retryResponse = await fetch(`/api/dialogs/${dialogGuid}/record`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, modul_type: selectedModul })
      });
      
      if (retryResponse.ok) {
        const record = await retryResponse.json();
        console.log('✅ Control erstellt:', record);
      }
    } else if (response.ok) {
      // Kein MODUL → Normaler Flow
      const record = await response.json();
      console.log('✅ Record erstellt:', record);
    } else {
      throw new Error(`HTTP ${response.status}`);
    }
  } catch (error) {
    console.error('❌ Fehler:', error);
  }
}

// Modul-Auswahl-Dialog
function showModulSelectionDialog(moduls: string[]): Promise<string> {
  return new Promise((resolve) => {
    // UI mit Buttons für jeden Modul-Typ
    // z.B. "edit", "view", "tabs"
    
    const dialog = createDialog({
      title: 'MODUL-Typ wählen',
      buttons: moduls.map(mod => ({
        label: mod,
        onClick: () => {
          dialog.close();
          resolve(mod);
        }
      }))
    });
    
    dialog.show();
  });
}
```

## Response-Format

### Status 428: Modul-Auswahl erforderlich

```json
{
  "detail": {
    "error": "modul_selection_required",
    "message": "Template enthält Gruppe 'MODUL' in 'CONTROL', aber modul_type wurde nicht übergeben...",
    "available_moduls": ["edit", "view", "tabs"],
    "modul_group_key": "CONTROL",
    "help": "Rufe GET /api/dialogs/{guid}/modul-selection auf oder übergebe modul_type im Body"
  }
}
```

### Status 200: Erfolg

```json
{
  "uid": "...",
  "name": "test_field",
  "daten": {
    "ROOT": {
      "SELF_GUID": "...",
      "SELF_NAME": "test_field",
      "MODUL_TYPE": "edit"
    },
    "CONTROL": {
      "MODUL": {
        "feld": "test_field",
        "name": "test_field",
        "type": "string",
        ...
      }
    }
  }
}
```

## Alternative: Proaktive Prüfung

**Optional:** Frontend kann VORHER prüfen, ob Modul-Auswahl nötig ist:

```typescript
async function handleNeuerSatz() {
  // 1. Prüfe ob Modul-Auswahl nötig ist
  const checkResponse = await fetch(
    `/api/dialogs/${dialogGuid}/modul-selection`
  );
  const { requires_modul_selection, available_moduls } = await checkResponse.json();
  
  // 2. Wenn ja → Modul-Dialog zuerst
  let modul_type = null;
  if (requires_modul_selection) {
    modul_type = await showModulSelectionDialog(available_moduls);
  }
  
  // 3. Create mit oder ohne modul_type
  const name = await promptForName();
  const response = await fetch(`/api/dialogs/${dialogGuid}/record`, {
    method: 'POST',
    body: JSON.stringify({ name, modul_type })
  });
  
  if (response.ok) {
    console.log('✅ Record erstellt');
  }
}
```

**Vorteil:** Kein Error-Handling nötig, klarer Flow

**Nachteil:** Ein zusätzlicher API-Call

## Empfehlung

**Optimistischer Ansatz (bevorzugt):**
1. Versuche CREATE ohne modul_type
2. Bei 428 → Modul-Dialog zeigen und retry
3. Spart einen API-Call wenn kein MODUL vorhanden

**Konservativer Ansatz:**
1. Prüfe mit GET /modul-selection
2. Wenn required → Modul-Dialog
3. Dann CREATE mit modul_type
4. Klarer, aber langsamer

## UI/UX

### Modul-Dialog Design

```
┌─────────────────────────────────────┐
│  MODUL-Typ wählen                   │
│                                     │
│  Wähle den Typ für das neue Control:│
│                                     │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐│
│  │   📝    │ │   👁️    │ │   📑    ││
│  │         │ │         │ │         ││
│  │  edit   │ │  view   │ │  tabs   ││
│  │         │ │         │ │         ││
│  │ Editier-│ │ Tabellen-│ │ Element-││
│  │ bare    │ │ spalten │ │ Listen  ││
│  │ Felder  │ │         │ │         ││
│  └─────────┘ └─────────┘ └─────────┘│
│                                     │
│              [Abbrechen]            │
└─────────────────────────────────────┘
```

### Beschreibungen

```typescript
const MODUL_DESCRIPTIONS = {
  edit: {
    icon: '📝',
    title: 'Edit',
    description: 'Editierbare Felder in Dialogen (Text, Dropdown, Datum, etc.)'
  },
  view: {
    icon: '👁️',
    title: 'View',
    description: 'Spalten in Tabellen und Listen mit Sortierung/Filter'
  },
  tabs: {
    icon: '📑',
    title: 'Tabs',
    description: 'Element-Listen (Tabs, Buttons, dynamische Arrays)'
  }
};
```

## Testing

```bash
# Backend Test
python backend/test_modul_error_handling.py

# Expected Output:
# 1️⃣ POST ohne modul_type → 428 mit available_moduls ✅
# 2️⃣ POST mit modul_type → 200 Success ✅
# 3️⃣ POST mit falschem modul_type → 400 Error ✅
```

## Error-Codes

| Status | Bedeutung | Aktion |
|--------|-----------|--------|
| 200 | Success | Record erstellt |
| 400 | Bad Request | Ungültiger modul_type |
| 404 | Not Found | Dialog/Template nicht gefunden |
| 428 | Precondition Required | Modul-Auswahl fehlt → Dialog zeigen |

## Zusammenfassung

✅ **Problem gelöst:**
- User bekommt keine kryptische Fehlermeldung mehr
- Backend liefert strukturierte Info über verfügbare Module
- Frontend kann darauf reagieren (Modul-Dialog)

✅ **Ablauf:**
1. POST /record ohne modul_type
2. Bei 428 → available_moduls aus Response lesen
3. Modul-Dialog zeigen
4. POST /record erneut mit modul_type

✅ **Funktioniert für ALLE Tabellen:**
- sys_control_dict ✅
- sys_framedaten ✅
- Jede Tabelle mit MODUL im Template ✅
