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

| **`block_tabs_std`** | Tabs (Dialog intern) | `.pdvm-tabs__*` | `bar_padding` | `6px` |
| | | | `bar_bg_color` | `transparent` |
| | | | `bar_border_bottom` | `1px solid var(--color-border-light)` |
| | | | `bar_sticky_height` | `44px` |
| | | | `tab_padding` | `8px 12px` |
| | | | `tab_radius` | `var(--border-radius-md)` |
| | | | `tab_bg_color` | `transparent` |
| | | | `tab_text_color` | `var(--color-text-secondary)` |
| | | | `tab_hover_bg_color` | `rgba(0,0,0,0.04)` |
| | | | `tab_active_bg_color` | `var(--color-background-primary)` |
| | | | `tab_active_text_color` | `var(--color-text-primary)` |
| | | | `tab_active_border_color` | `var(--color-border-light)` |

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

### 5.4 Widget Mapping (Komplexe Komponenten)

Komplexe Widgets setzen sich oft aus mehreren Blöcken zusammen. Hier wird definiert, welche Blöcke für welche Teilelemente verwendet werden.

| Widget | Element | Verwendeter Block | CSS Variable (Beispiel) | Beschreibung |
| :--- | :--- | :--- | :--- | :--- |
| **`PdvmDateTimePicker`** | **Input Field** | `block_input_std` | `--block-input-std-bg-color` | Rahmen, Hintergrund und Text des Eingabefeldes. |
|  | **Popover/Calendar** | `block_surface_main` | `--block-surface-main-bg-color` | Hintergrund des aufklappbaren Kalenders. |
|  | **Selected Date** | `block_btn_primary` | `--block-btn-primary-bg-color` | Markierung des ausgewählten Tages (ähnlich Primary Button). |
|  | **Navigation Icons** | `block_input_std` | `--block-input-std-text-color` | Pfeile für Monat/Jahr (erben Textfarbe vom Input-Standard). |

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

### 5.6 Dialog: `edit_json` (Toolbar + JSON Editor)

Der `edit_json` Tab nutzt bewusst vorhandene Standard-Blöcke, damit Kontrast/Look im Hell- und Dunkelmodus sauber über das Theme steuerbar bleibt.

**Toolbar (Buttons + Suchfeld)**
- Buttons: `block_view_btn_std` (CSS: `.pdvm-dialog__toolBtn`)
  - Verwendete Properties: `bg_color`, `text_color`, `border`, `radius`, `hover_bg`
- Primary Action (Speichern): `block_btn_primary` (CSS: `.pdvm-dialog__toolBtn--primary`)
  - Verwendete Properties: `bg_color`, `text_color`, `hover_bg`, `radius`
- Suchfeld: `block_view_input_std` (CSS: `.pdvm-dialog__toolInput`)
  - Verwendete Properties: `bg_color`, `text_color`, `border`, `radius`

**Editor-Surface (JSONEditor / Ace in Textmodus)**
- Editor-Rahmen/Surface: `block_view_table` (CSS: `.pdvm-jsoneditor__frame`)
  - Verwendete Properties: `bg_color`, `border`, `radius`
- Editor-Menüleiste (intern von `jsoneditor`): `block_view_toolbar` (CSS: `.jsoneditor-menu`)
  - Verwendete Properties: `bg_color`, `border`

**Hinweis (Such-Highlight im Textmodus)**
Die Markierung der Treffer in der Textansicht erfolgt über Ace-Marker-Klassen (z.B. `.ace_selected-word`, `.ace_find_highlight`). Die Farben sind in der Komponente bewusst als klare Kontrast-Farben gesetzt (gelb für Treffer), da die Marker in manchen Ace-Themes sonst zu subtil sind.

---

## 5.7 Dialog: `menu` (Menüeditor)

Der Menüeditor verwendet für seine internen Tabs den Block `block_tabs_std`.

Relevante CSS-Variablen (aus `block_tabs_std`):
- `--block-tabs-std-bar-padding`
- `--block-tabs-std-bar-bg-color`
- `--block-tabs-std-bar-border-bottom`
- `--block-tabs-std-bar-sticky-height` (wichtig für Sticky-Stacking: Tab-Bar oben, Toolbar darunter)
- `--block-tabs-std-tab-*` (Padding, Radius, Farben, Active-State)

Hinweis: Die kleinen Text-Buttons im Menüeditor (Quick Actions) nutzen aktuell bewusst einfache Standard-Styles (Border/Background) und sind nicht als eigener Block im Theme-System modelliert. Bei Bedarf kann das später als eigener Block (z.B. `block_menu_editor_btn_std`) ergänzt und in CSS auf `--block-*` umgestellt werden.

---

## 5.8 Menü (Horizontal + Vertikal)

**Status:** Menü nutzt aktuell Legacy-Variablen (`--color-*`, `--surface-*`).
Für V2 ist folgende Block-Zuordnung vorgesehen, damit Theme-Sets das Menü konsistent steuern können.

### Empfohlene Blöcke
| Block Name | UI Element | CSS Klasse | Properties | Default Fallback |
| :--- | :--- | :--- | :--- | :--- |
| **`block_menu_horizontal`** | Top-Menü-Leiste | `.horizontal-menu` | `bg_color`, `border_bottom`, `shadow` | `var(--color-background-primary)` / `var(--color-border-medium)` |
| **`block_menu_vertical`** | Sidebar Menü | `.vertical-menu` | `bg_color`, `border_right` | `var(--surface-primary)` / `var(--border-color)` |
| **`block_menu_button`** | Menü-Button | `.horizontal-menu-button`, `.vertical-menu-button` | `text_color`, `hover_bg`, `active_bg` | `var(--color-text-primary)` / `var(--color-background-secondary)` |
| **`block_menu_dropdown`** | Dropdown-Container | `.horizontal-menu-dropdown`, `.vertical-menu-dropdown` | `bg_color`, `border`, `shadow` | `var(--color-background-primary)` / `var(--color-border-medium)` |
| **`block_menu_separator`** | Separator-Linie | `.horizontal-menu-separator`, `.vertical-menu-separator` | `color`, `opacity` | `currentColor` / `0.3` |
| **`block_menu_icon`** | Icon-Farbe/Größe | `.menu-icon` | `color`, `size` | `currentColor` / `16px` |

### Hinweis Icon-Farbe
Icons werden als SVGs gerendert und nutzen `currentColor`. Dadurch folgt die Farbe der Textfarbe des Buttons.

---

