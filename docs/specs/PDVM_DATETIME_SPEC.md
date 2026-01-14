# Spezifikation: PdvmDateTime & Stichtagsbar

## 1. Einführung
Diese Spezifikation beschreibt die Implementierung des zentralen Datumsformats `PdvmDateTime` und des dazugehörigen UI-Controls `PdvmDateTimePicker` für die Web-Applikation. Ziel ist es, die bewährte Logik der Desktop-Applikation (speziell das Verhalten "Änderung nur bei Save") in die Web-Architektur (FastAPI + React) zu übertragen, unter Einhaltung der `ARCHITECTURE_RULES.md`.

## 2. Kern-Konzept: PdvmDateTime

### 2.1 Backend (Python)
In der Business-Logik (Backend) ist `PdvmDateTime` das führende Format. Obwohl die Datenbank native Zeitstempel (`datetime`) speichert, kapselt die Applikationslogik diese Werte.

**Klasse:** `backend/app/core/pdvm_datetime.py`

*   **Verantwortlichkeit:**
    *   Konvertierung zwischen nativem Python `datetime` und dem `Pdvm`-Logik-Objekt.
    *   Bereitstellung von Formatierungsfunktionen (z.B. "05.06.2025 12:00:00").
    *   (Optional) Legacy-Support für das interne Float-Format (`YYYYDDD.TimeFraction`), falls für Berechnungen benötigt.
    *   **Serialisierung:** Für die Kommunikation via API wird das Objekt standardmäßig nach **ISO-8601** (`YYYY-MM-DDTHH:mm:ss`) serialisiert, um maximale Kompatibilität mit dem Frontend zu gewährleisten.

**Datenbank-Schicht:**
*   Spalten-Typ: `TIMESTAMP` (PostgreSQL) / `DATETIME` (SQLite).
*   ORM: SQLAlchemy nutzt Python `datetime`.
*   Regel: Die `PdvmCentralDatabase` liest `datetime` aus der DB und wrappt es bei Bedarf in `PdvmDateTime` für die Business-Logik-Verarbeitung.

### 2.2 Frontend (TypeScript/React)
Im Frontend wird das Datum primär als ISO-String oder JavaScript `Date`-Objekt behandelt. Wir erstellen *keine* komplexe 1:1 Kopie der Python-Klasse mit mathematischer Logik (Prozentfaktoren), sondern nutzen moderne Web-Standards für die Darstellung.

*   **Transportschicht:** ISO-String ohne explizite Zeitzone (z.B. `"2025-06-05T12:00:00"`).
    *   **Wichtig:** Keine automatische UTC-Konvertierung im Picker (`toISOString()`), da sonst Uhrzeiten „springen“.
*   **Anzeige:** Formatierung gemäß Locale (z.B. `de-DE`).

---

## 3. Komponente: PdvmDateTimePicker

Ein spezialisiertes React-Widget, das das Verhalten des Desktop-Pendants nachbildet.

### 3.1 UX-Verhalten (Desktop-Parität)
1.  **Anzeige:** Ein Textfeld zeigt das formatierte Datum an (Read-Only oder direkt editierbar, je nach Konfig).
2.  **Editier-Modus:** Ein Klick auf das Kalender-Icon (oder das Feld) öffnet ein Popover/Modal.
3.  **Draft-State (Wichtig!):**
    *   Änderungen im Popover (Datum wählen, Zeit ändern) verändern **nicht** sofort den Wert in der Applikation (Stichtag).
    *   Der neue Wert wird temporär ("Draft") gehalten.
4.  **Save/Apply:**
    *   Erst ein expliziter Klick auf "Übernehmen" (Save Button) oder "OK" feuert das `onChange` Event und aktualisiert den globalen Zustand.
    *   "Abbrechen" oder Klick außerhalb verwirft die Änderungen.

### 3.2 Technische Umsetzung (React)

**Datei:** `frontend/src/components/common/PdvmDateTimePicker.tsx`

#### 3.2.1 Value-Format (Wichtig)
*   `value` ist ein ISO-String **ohne Zeitzonen-Suffix** (timezone-naiv), z.B. `2026-01-14T10:30:00`.
*   Der Picker gibt bei "Übernehmen" ebenfalls einen timezone-naiven ISO-String zurück.
        *   Es wird **kein** `toISOString()` verwendet, damit Zeiten nicht in UTC „springen“.

#### 3.2.2 Props (vollständig)
Minimal:
*   `value: string | null | undefined` – aktueller Wert
*   `onChange: (newValue: string) => void` – feuert nur bei "Übernehmen"

Optional:
*   `label?: string` – Tooltip/Header im Popover
*   `readOnly?: boolean` – Popover deaktiviert
*   `mode?: 'datetime' | 'date' | 'time'`
        *   `datetime`: Datum + Zeit
        *   `date`: nur Datum
        *   `time`: nur Zeit
*   `showTime?: boolean` – Legacy/Kompatibilität (intern wird daraus `mode` abgeleitet)
*   `showSeconds?: boolean` – Sekunden in der Zeit-Eingabe
*   `showMilliseconds?: boolean` – Millisekunden (impliziert Sekunden)
*   `showNowButton?: boolean` – "Jetzt" Button (Default: `true` bei `mode='time'`, sonst `false`)
*   `allowClear?: boolean` – aktiviert "Leeren" (explizite Aktion wie "Übernehmen")
*   `onClear?: () => void` – Parent setzt dann `value` auf null/undefined
*   `clearPlacement?: 'inside' | 'popover' | 'both' | 'none'` – steuert, wo "Leeren" angezeigt wird (Default: `both` wenn `allowClear=true`)
*   `popoverAlign?: 'start' | 'end' | 'auto'`
        *   `start`: linksbündig
        *   `end`: rechtsbündig (öffnet nach links)
        *   `auto`: versucht Overflow zu vermeiden

#### 3.2.3 UX-Verhalten (verbindlich)
*   Änderungen passieren im Draft-State und werden erst bei "Übernehmen" committed.
*   "Abbrechen" oder Click-outside verwirft den Draft.
*   "Jetzt" setzt nur den Draft (bis "Übernehmen").
*   "Leeren" ist eine explizite Aktion:
        *   `allowClear=true` und `onClear` gesetzt → Button erscheint → `onClear()` wird aufgerufen und Popover schließt.
    *   Anzeigeort ist per `clearPlacement` steuerbar (✕ im Feld, "Leeren" im Popover, beides oder keines).

#### 3.2.4 Beispiele

Nur Datum:
```tsx
<PdvmDateTimePicker
    mode="date"
    value={dateIso}
    onChange={(iso) => setDateIso(iso)}
    allowClear
    onClear={() => setDateIso(null)}
/>
```

Nur Zeit (mit "Jetzt" und Sekunden):
```tsx
<PdvmDateTimePicker
    mode="time"
    showSeconds
    value={timeIso}
    onChange={(iso) => setTimeIso(iso)}
/>
```

Datetime rechts am Rand (Popover soll nach links öffnen):
```tsx
<PdvmDateTimePicker
    mode="datetime"
    value={dtIso}
    onChange={(iso) => setDtIso(iso)}
    popoverAlign="end"
/>
```

---

## 4. Integration: Stichtagsbar

Die Stichtagsbar ist die **einzige** Stelle, an der der systemweite Referenz-Zeitpunkt ("Stichtag") geändert werden darf.

### 4.1 Source of Truth (Backend)
*   **Führend:** `PdvmCentralSystemsteuerung.stichtag`.
*   **Persistenz:** `sys_systemsteuerung` mit
    *   `uid = user_guid`
    *   `gruppe = user_guid`
    *   `feld = STICHTAG`
*   **Initialisierung:** Beim Laden der Systemsteuerung wird `STICHTAG` gelesen; falls nicht vorhanden, wird `now_pdvm()` gesetzt und **sofort persistiert**.

### 4.2 API-Kontrakt
*   `GET /api/gcs/stichtag` → liefert
    *   `stichtag`: PDVM-float (YYYYDDD.Fraction)
    *   `iso`: ISO-String (timezone-naiv)
    *   `display`: Anzeigeformat (z.B. `DD.MM.YYYY HH:MM`)
*   `POST /api/gcs/stichtag`
    *   akzeptiert `{ "iso": "YYYY-MM-DDTHH:mm:ss" }` (empfohlen) oder `{ "stichtag": 2025356.12345 }` (legacy)
    *   persistiert sofort in `sys_systemsteuerung`

### 4.3 Frontend-Integration
*   **Layout:** Stichtagsbar ist eine eigene Zeile **direkt unter dem Header** (nicht im Header selbst).
*   **UI:** Read-only Anzeige des angewendeten Stichtags + `PdvmDateTimePicker` zum Ändern.
*   **Flow:** `Übernehmen` im Picker → `POST /api/gcs/stichtag` → Anzeige wird aktualisiert.

---

## 5. Implementierungs-Plan

1.  **Backend:**
    *   Prüfen/Erstellen von `backend/app/core/pdvm_datetime.py`.
    *   Implementieren der Pydantic-Modelle für API-Request/Response.

2.  **Frontend:**
    *   Implementieren der `PdvmDateTimePicker` Komponente (`src/components/common/PdvmDateTimePicker.tsx`).
    *   Implementieren der UI mit "Draft State" Logik.
    *   Integration in die Top-Bar (`StichtagsBar`).

3.  **System-Link:**
    *   Verbindung via Context API (`useSystemContext` o.ä.), um den Stichtag global verfügbar zu machen.
