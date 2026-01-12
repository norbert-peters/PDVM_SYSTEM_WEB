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

*   **Transportschicht:** ISO-String (z.B. `"2025-06-05T12:00:00"`).
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

```typescript
interface PdvmDateTimePickerProps {
  // Der "echte" Wert (aus der Datenbank/System)
  value: string; // ISO String
  
  // Callback erst NACH Bestätigung
  onChange: (newValue: string) => void;
  
  // Darstellungsoptionen
  format?: string; // z.B. "dd.MM.yyyy HH:mm"
  readOnly?: boolean;
}
```

**Interne States:**
*   `isOpen`: Boolean (Popover sichtbar?)
*   `draftValue`: Date | null (Zwischenspeicher für Bearbeitung)

---

## 4. Integration: Stichtagsbar

Die Stichtagsbar ist eine globale Komponente (meist im Header oder direkt darunter), die den systemweiten Referenz-Zeitpunkt ("Stichtag") steuert.

*   **Globaler State:** Der Stichtag wird im React Context (`Store`) gehalten.
*   **API:** Änderungen am Stichtag werden an das Backend gesendet (z.B. `POST /api/gcs/stichtag`).
*   **Verwendung:** Alle Datenlade-Vorgänge (Views) nutzen diesen Stichtag als Filter, um den korrekten historischen Stand der Daten anzuzeigen.

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
