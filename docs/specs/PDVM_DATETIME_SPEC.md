# Spezifikation: PdvmDateTime & Stichtagsbar

## 1. Einführung
Diese Spezifikation beschreibt die Implementierung des zentralen Datumsformats `PdvmDateTime` und des dazugehörigen UI-Controls `PdvmDateTimePicker` für die Web-Applikation. Ziel ist es, die bewährte Logik der Desktop-Applikation (speziell das Verhalten "Änderung nur bei Save") in die Web-Architektur (FastAPI + React) zu übertragen, unter Einhaltung der `ARCHITECTURE_RULES.md`.

## 2. Kern-Konzept: PdvmDateTime

Normative Definition (verbindlich):
- PdvmDateTime ist immer `YYYYDDD.FRACTION`.
- `FRACTION` ist der Bruchteil des Tages (`0.5 = 12:00:00`).
- Diese Definition ist verbindlich fuer Backend, Frontend und Persistenz in JSONB-Feldern.
- Normative Referenzimplementierung ist `backend/app/core/pdvm_datetime.py`.

### 2.1 Backend (Python)
In der Business-Logik (Backend) ist `PdvmDateTime` das führende Format.

**Klasse:** `backend/app/core/pdvm_datetime.py`

*   **Verantwortlichkeit:**
    *   Konvertierung zwischen nativem Python `datetime` und PDVM-Float `YYYYDDD.FRACTION`.
    *   Bereitstellung von Formatierungsfunktionen (z.B. "05.06.2025 12:00:00").
    *   Einheitliche Mathe-Logik fuer den Tagesbruchteil.

**Datenbank-Schicht:**
*   In JSONB-Daten werden Zeitwerte als PDVM-Float gespeichert.
*   Nur systemeigene SQL-Spalten wie `created_at`/`modified_at` bleiben SQL-Timestamps.

### 2.2 Frontend (TypeScript/React)
Im Frontend werden PDVM-Werte formatgleich zum Backend verarbeitet.

*   **Transportschicht:** PDVM-Float `YYYYDDD.FRACTION`.
*   **Anzeige:** Aus PDVM abgeleitetes Datums-/Zeitformat (z.B. `de-DE`).
*   Keine alternativen/legacy Zeitkodierungen im Nachkommateil.

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
*   `showNowButton?: boolean` – "Jetzt" Button im Popover (Default: `true` in allen Modi; `date` setzt nur das Datum, `time` nur die Zeit, `datetime` beides)
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
*   "Jetzt" setzt nur den Draft (bis "Übernehmen"), sowohl Datum als auch Uhrzeit in einem Schritt.
*   Eingabefehler (kein Datum, ungültiger Wert) erscheinen als Hinweis im Popover (`role="alert"`), kein `alert()`.
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

#### 3.2.5 Einbindung als Input-Control und Darstellung (Theme)

*   Der Picker ist das gemeinsame Widget für alle Datums-/Zeitfelder: `PdvmInputControl` nutzt ihn für die Typen `datetime`, `date` und `time` (Wert wird dort in das PDVM-Format umgerechnet). Die Stichtagsleiste nutzt ihn direkt, weil der Stichtag kein Datensatzfeld ist, sondern über `/api/gcs/stichtag` gesetzt wird.
*   Farben kommen aus dem Theme (Details: `THEMING_SYSTEM.md`, 5.4, 5.9, 9): Feld = `block_pic_std`, in der Stichtagsleiste `block_stichtag_std.field_*`; Auswahlfenster = `block_pic_popover` (`bg_color`, `text_color`, `border`, `radius`, `shadow`, `field_bg_color`, `field_text_color`). Alle diese Paare unterliegen der Kontrastprüfung. Im Editor `/design` sind die Blöcke unter „Stichtagsleiste“ und „Datum/Zeit-Auswahl (Popover)“ einstellbar, die Vorschau zeigt beide.
*   Der Picker setzt keine Farbwerte inline; native Felder folgen dem Modus über `color-scheme` (`variables.css`).
*   `nowLocalIso()` (exportiert) liefert die aktuelle lokale Zeit als naiven ISO-String, z. B. für die „Jetzt“-Schaltfläche der Stichtagsleiste.

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
    *   `display`: Anzeigeformat (z.B. `DD.MM.YYYY HH:MM`)
*   `POST /api/gcs/stichtag`
    *   akzeptiert `{ "stichtag": 2025356.12345 }`
    *   persistiert sofort in `sys_systemsteuerung`

### 4.3 Frontend-Integration
*   **Layout:** Stichtagsbar ist eine eigene Zeile **direkt unter dem Header** (nicht im Header selbst).
*   **UI:** Read-only Anzeige des angewendeten Stichtags + Button "Jetzt" (setzt den Stichtag sofort auf aktuelles Datum und aktuelle Uhrzeit) + `PdvmDateTimePicker` zum Ändern (Popover mit eigenem "Jetzt" für den Draft).
*   **Farben:** Die Leiste überschreibt die globalen `--color-text-*` nicht; Beschriftung/Wert nutzen `block_stichtag_std.text_color`, Feld und Button `block_stichtag_std.field_*`.
*   **Flow:** `Übernehmen` im Picker (oder "Jetzt" in der Leiste) → `POST /api/gcs/stichtag` → Anzeige wird aktualisiert, Event `pdvm:stichtag-changed`.
*   **Schmale Fenster:** Unter 1024 px Breite wird die Leiste ausgeblendet (Responsive-Regel in `header.css`).

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
