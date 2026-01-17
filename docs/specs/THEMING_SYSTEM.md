# PDVM Theming System V2: Component-Based Architecture

Detaillierte Spezifikation für das dynamische, mandanten- und benutzergesteuerte Design-System basierend auf "Style Blocks" und Komponenten-Mapping.

## 1. Übersicht & Ziele

Das System ermöglicht eine hochflexible Gestaltung der Benutzeroberfläche ohne CSS-Code-Anpassungen.
*   **Trennung:** Layout/Struktur (CSS) vs. Design/Farben (Datenbank).
*   **Granularität:** Styling auf Komponenten-Ebene (`Header`, `StichtagsBar`, `DateTimePicker`) statt nur globaler Farben.
*   **Wiederverwendbarkeit:** Definition von "Style Blocks" (z.B. "Standard Input"), die mehreren Elementen zugewiesen werden.
*   **Personalisierung:** Mandanten geben Theme-Sets vor, Benutzer wählen ihre bevorzugte Variante (Hell/Dunkel).

## 2. Datenbank-Architektur

### 2.1 Mandanten-Ebene (`sys_mandanten`)
Der Mandant definiert, welches **Theme-Paket (Datensatz)** grundsätzlich geladen wird.

*   **Tabelle:** `sys_mandanten`
*   **Ort:** Gruppe `CONFIG`, Feld `THEME_GUID`.
*   **Wert:** UUID eines Datensatzes in `sys_layout`.

### 2.2 Benutzer-Ebene (`sys_benutzer`)
Der Benutzer wählt innerhalb des Pakets seine bevorzugten Varianten für Hell- und Dunkelmodus. Diese Information wird beim Login übermittelt.

*   **Tabelle:** `sys_benutzer`
*   **Ort:** Gruppe `CONFIG`.
*   **Felder:**
    *   `THEME_LIGHT`: Name der Layout-Gruppe für den Hell-Modus (z.B. "Orange_Light").
    *   `THEME_DARK`: Name der Layout-Gruppe für den Dunkel-Modus (z.B. "Orange_Dark").

### 2.3 Layout-Definition (`sys_layout`)
Ein Datensatz enthält mehrere Style-Varianten als **Gruppen**.

*   **Tabelle:** `sys_layout`
*   **Struktur:**
    *   **Datensatz (UUID):** Das "Theme Paket" (z.B. Corporate Design 2026).
    *   **Gruppe (Key):** Der Name des Themes (z.B. "Orange_Dark" - korrespondiert mit User-Wahl/Fallback).
    *   **Felder (Key/Value):** Definition von Style-Blöcken und Komponenten-Mappings.

#### JSON-Struktur einer Gruppe (z.B. "Orange_Dark")
Innerhalb einer Gruppe können zwei Arten von Feldern definiert werden:
1.  **Style Blocks:** Wiederverwendbare Definitionen (Vorlagen).
2.  **Components:** Konkrete Zuweisung zu UI-Elementen (via Referenz oder direkt).

```json
{
  "Orange_Dark": {
    // === 1. Style Blocks (Vorlagen) ===
    "block_input_std": {
      "background": "#1e1e1e",
      "text": "#ffffff",
      "border": "1px solid #ff9800",
      "radius": "4px"
    },
    "block_card_glass": {
      "background": "rgba(30,30,30, 0.8)",
      "backdropFilter": "blur(10px)",
      "shadow": "0 4px 6px rgba(0,0,0,0.1)"
    },

    // === 2. Component Mapping ===
    
    // Referenz auf Block (Sehr flexibel!)
    "DateTimePicker": "block_input_std",
    "SearchField": "block_input_std",
    
    // Direkte Definition (Spezialfälle)
    "AppHeader": {
      "background": "linear-gradient(135deg, #e65100, #ff9800)",
      "text": "#ffffff",
      "height": "64px"
    },
    
    "StichtagsBar": {
      "background": "#ff9800",
      "text": "#000000", // On-Color Hardcoded
      "border_radius": "8px"
    }
  }
}
```

## 3. Implementierung

### 3.1 Backend (`PdvmCentralSystemsteuerung`)
*   Lädt beim Start `user_data` und `mandant_data`.
*   Extrahiert `THEME_GUID` aus Mandantendaten.
*   Extrahiert `THEME_LIGHT` / `THEME_DARK` aus Benutzerdaten.
*   Lädt den `sys_layout` Datensatz vollständig in den Speicher (`self.layout`).
*   Bietet API-Endpunkt, der *nur* die aktuell benötigte Gruppe liefert (z.B. User ist im Dark Mode -> liefere Gruppe "Orange_Dark").

### 3.2 Frontend (`useTheme` Hook)
*   **Parser-Logik:**
    1.  Erhält das JSON der aktiven Gruppe.
    2.  Iteriert durch alle Keys.
    3.  Löst Referenzen auf (wenn Value == String -> suche Block mit diesem Namen).
    4.  Generiert CSS Custom Properties für jede Eigenschaft.
    
*   **Naming Convention:**
    `--comp-[ComponentName]-[Property]`

    *Beispiel Output:*
    ```css
    :root {
      /* Aus DateTimePicker -> block_input_std */
      --comp-DateTimePicker-background: #1e1e1e;
      --comp-DateTimePicker-text: #ffffff;
      --comp-DateTimePicker-border: 1px solid #ff9800;
      
      /* Aus AppHeader */
      --comp-AppHeader-background: linear-gradient(...);
    }
    ```

### 3.3 CSS-Anpassung
UI-Komponenten nutzen *nur noch* ihre spezifischen Variablen, mit generischen Fallbacks.

*Beispiel `PdvmDateTimePicker.css`:*
```css
.pdvm-datetime-input-wrapper {
  /* Nutze Component-Variable oder Fallback auf globalen Standard */
  background: var(--comp-DateTimePicker-background, var(--color-background-primary));
  color: var(--comp-DateTimePicker-text, var(--color-text-primary));
  border: var(--comp-DateTimePicker-border, 1px solid var(--color-border-medium));
}
```

## 4. Migrationspfad (Status: In Progress)

1.  **Backend:** API `get_mandant_theme` anpassen, damit sie User-Präferenz berücksichtigt (✅ Erledigt).
2.  **Datenbank:** Beispieldatensatz in `sys_layout` erstellen, der die neue Struktur spiegelt (✅ JSON generiert).
3.  **Frontend:** `useTheme.ts` erweitern um "Block Resolution Engine" (✅ Erledigt).
4.  **Refactoring:** CSS-Dateien (`header.css`, etc.) auf `--block-*` Variablen umstellen (Teilweise).

## 5. Block Reference & Defaults

Die folgende Tabelle definiert die implementierten Standard-Blöcke (V2), ihre Verwendung und das Fallback-Verhalten, falls ein Block im Layout-Datensatz fehlt.

### 5.1 Layout Blocks

| Block Name | UI Element | CSS Klasse | Properties | Default Fallback (variables.css) |
| :--- | :--- | :--- | :--- | :--- |
| **`block_header_std`** | Main App Header | `.app-header` | `bg_color` | `var(--color-background-primary)` |
| | | | `text_color` | `inherit` |
| | | | `border_bottom` | `1px solid var(--color-border-light)` |
| | | | `shadow` | `var(--shadow-sm)` |
| **`block_header_mandant_std`** | Header Mandant (Center) | `.header-mandant-*` | `text_color` | `var(--color-text-primary)` |
| | | | `subtext_color` | `var(--color-text-secondary)` |
| **`block_header_user_std`** | Header User (Right) | `.user-*` | `text_color` | `var(--color-text-primary)` |
| | | | `subtext_color` | `var(--color-text-secondary)` |
| **`block_sidebar_std`** | Navigation Sidebar | `.app-sidebar` | `bg_color` | `var(--color-background-secondary)` |
| | | | `text_color` | `var(--color-text-primary)` |
| | | | `border_right` | `1px solid var(--color-border-light)` |
| **`block_surface_main`** | Main Content Area | `.app-main`, `.surface-card` | `bg_color` | `var(--color-background-primary)` |
| | | | `text_color` | `var(--color-text-primary)` |

| **`block_view_toolbar`** | View Header/Toolbar | `.pdvm-view-toolbar` | `bg_color` | `var(--block-surface-main-bg-color)` |
| | | | `text_color` | `var(--color-text-primary)` |
| | | | `border` | `1px solid var(--color-border-light)` |
| | | | `radius` | `var(--border-radius-md)` |

| **`block_view_panel`** | View Panels (Spalten/Gruppierung) | `.pdvm-view-panel` | `bg_color` | `var(--color-background-secondary)` |
| | | | `text_color` | `var(--color-text-primary)` |
| | | | `border` | `1px solid var(--color-border-light)` |
| | | | `radius` | `var(--border-radius-md)` |

| **`block_view_table`** | View Table Surface | `.pdvm-view-table` | `bg_color` | `var(--block-surface-main-bg-color)` |
| | | | `border` | `1px solid var(--color-border-light)` |
| | | | `radius` | `var(--border-radius-md)` |

| **`block_view_table_header`** | Table Header Row | `.pdvm-view-table thead` | `bg_color` | `var(--block-surface-main-bg-color)` |
| | | | `text_color` | `var(--color-text-primary)` |
| | | | `border_bottom` | `1px solid var(--color-border-light)` |

| **`block_view_table_row_selected`** | Selected Row | `.pdvm-view-row-selected` | `bg_color` | `rgba(0, 120, 212, 0.10)` |

| **`block_view_group_row`** | Group Header Row | `.pdvm-view-group-row` | `bg_color` | `rgba(0,0,0,0.03)` |
| | | | `text_color` | `var(--color-text-primary)` |

| **`block_view_total_row`** | Grand Total Row | `.pdvm-view-total-row` | `bg_color` | `rgba(0,0,0,0.05)` |
| | | | `text_color` | `var(--color-text-primary)` |

### 5.2 Component Blocks

| Block Name | UI Element | CSS Klasse | Properties | Default Fallback |
| :--- | :--- | :--- | :--- | :--- |
| **`block_input_std`** | Text Input, Select | `.form-input` | `bg_color` | `var(--color-background-primary)` |
| | | | `border` | `1px solid var(--color-border-medium)` |
| | | | `text_color` | `var(--color-text-primary)` |
| | | | `radius` | `var(--border-radius-sm)` |
| **`block_btn_primary`** | Primary Action Button | `.btn-primary` | `bg_color` | `var(--color-primary-500)` |
| | | | `text_color` | `var(--color-text-inverse)` |
| | | | `hover_bg` | `var(--color-primary-600)` |
| | | | `radius` | `var(--border-radius-md)` |
| **`block_stichtag_std`** | Stichtags-Container | `.stichtags-bar` | `bg_color` | `var(--color-primary-500)` |
| | | | `text_color` | `var(--color-text-inverse)` |
| | | | `border` | `1px solid var(--color-primary-600)` |
| | | | `radius` | `var(--border-radius-md)` |

| **`block_view_btn_std`** | View Buttons (Spalten/Reset/Gruppierung) | `.pdvm-view-btn` | `bg_color` | `var(--color-background-primary)` |
| | | | `text_color` | `var(--color-text-primary)` |
| | | | `border` | `1px solid var(--color-border-medium)` |
| | | | `radius` | `var(--border-radius-md)` |
| | | | `hover_bg` | `rgba(0,0,0,0.06)` |

| **`block_view_input_std`** | View Filter/Input | `.pdvm-view-input` | `bg_color` | `var(--color-background-primary)` |
| | | | `text_color` | `var(--color-text-primary)` |
| | | | `border` | `1px solid var(--color-border-medium)` |
| | | | `radius` | `var(--border-radius-md)` |

### 5.3 Implementation Details

1. **Injection:** Der `useTheme` Hook konvertiert Block-Namen wie `block_header_std` in CSS Variablen wie `--block-header-std-bg-color`.
2. **Usage:** CSS verwendet `var(--block-name-prop, FALLBACK)`.
3. **Fallback:** Die Fallbacks referenzieren semantische Variablen aus `variables.css` (z.B. `--color-primary-500`), welche wiederum über das Legacy-Color-Mapping (Gruppe `colors`) befüllt werden.
4. **Resilience:** Wenn ein Theme keine Blöcke definiert, greift das System auf die globalen Farben zurück, solange die CSS-Dateien korrekte Fallbacks definiert haben.

### 5.5 View: Block-Zuordnung (Neu)

Für die generische View (`PdvmViewPage` / später `PdvmView`) werden folgende Blöcke empfohlen:

1. **Toolbar**
  - `block_view_toolbar` für den Headerbereich (Titel + Buttons)
  - `block_view_btn_std` für Buttons

2. **Panels** (Spalten/Gruppierung)
  - `block_view_panel` für Panel-Hintergrund
  - `block_view_input_std` für Filter- und Zahleninputs

3. **Table**
  - `block_view_table` für den Table-Container
  - `block_view_table_header` für Header + Filter-Row
  - `block_view_table_row_selected` für selektierte Zeilen
  - `block_view_group_row` für Gruppen-Header
  - `block_view_total_row` für Gesamtsumme

Hinweis: Aktuell verwendet die View noch Inline-Styles (MVP). Der nächste Schritt ist, diese Bereiche auf CSS-Klassen (`.pdvm-view-*`) umzustellen, damit die oben genannten Blocks direkt greifen.

### 5.4 Widget Mapping (Komplexe Komponenten)

Komplexe Widgets setzen sich oft aus mehreren Blöcken zusammen. Hier wird definiert, welche Blöcke für welche Teilelemente verwendet werden.

| Widget | Element              | Verwendeter Block    | CSS Variable (Beispiel)         | 
            | Beschreibung                                                               |
| :---   | :---                 | :---                 | :---                            |
            | :---                                                                       |
| **`PdvmDateTimePicker`** 
|        | **Input Field**      | `block_input_std`    | `--block-input-std-bg-color`    |
            | Der Rahmen Hintergrund und Text des Eingabefeldes.                         |
|        | **Popover/Calendar** | `block_surface_main` | `--block-surface-main-bg-color` |
            | Der Hintergrund des aufklappbaren Kalenders.                               |
|        | **Selected Date**    | `block_btn_primary`  | `--block-btn-primary-bg-color`  |
            | Die Markierung des ausgewählten Tages (ähnlich einem Primary Button).      |
|        | **Navigation Icons** | `block_input_std`    | `--block-input-std-text-color`  |
            | Pfeile für Monat/Jahr (erben Textfarbe vom Input-Standard).                |

