# PDVM Theming System V2: Block-basiertes Design-System

Spezifikation für das mandanten- und benutzergesteuerte Design-System (Farben, Blöcke, Strukturvarianten). Stand: Phasen P0 bis P7 umgesetzt (Plan: `docs/PDVM_PLAN_DESIGN_SYSTEM_V1.md`).

**Lesehinweis:** Abschnitte 1 bis 4 beschreiben Ziel und Datenmodell, 5 die Blöcke und Tokens, 6 bis 9 das Schichtmodell, den Editor, die Strukturvarianten und die Kontrast-Durchsetzung. Bei Widersprüchen gelten die späteren Abschnitte (6 bis 9) und der Code (`theme_schema.py`, `theme_service.py`, `layout_schema.py`).

## 1. Übersicht & Ziele

Das System ermöglicht eine flexible Gestaltung der Benutzeroberfläche ohne CSS-Code-Anpassungen.
*   **Trennung:** Struktur (CSS im Code) vs. Design/Farben (Datenbank). Es gibt kein freies CSS in der Datenbank.
*   **Granularität:** Styling auf Block-Ebene (`block_header_std`, `block_input_std` ...) zusätzlich zu den globalen Farben (`color.*`).
*   **Wiederverwendbarkeit:** Ein Block gilt für alle Elemente, die ihn nutzen; fehlt ein Wert, greift die Fallback-Kette im CSS.
*   **Personalisierung:** Das Theme-Paket kommt aus `sys_layout`; der Mandant legt Standard-Varianten, ein Overlay und Freigaben fest; der Benutzer ändert nur Freigegebenes.
*   **Lesbarkeit:** Pflicht-Kontraste (WCAG AA) werden beim Speichern erzwungen (Abschnitt 9).

## 2. Datenbank-Architektur

### 2.1 Mandanten-Ebene (`asy_mandanten`)
Der Mandant definiert, welches **Theme-Paket (Datensatz)** grundsätzlich geladen wird.

*   **Tabelle:** `asy_mandanten` (Auth-DB)
*   **Ort:** Gruppe `CONFIG`, Feld `THEME_GUID`.
*   **Wert:** UUID eines Datensatzes in `sys_layout` (Standard-Paket); je Mandant liegt eine Kopie in `msy_layout` (Abschnitt 6).
*   **Mehrere Pakete:** `CONFIG.THEME_ALLOWED` = Liste weiterer `sys_layout`-UUIDs, die Benutzer wählen dürfen (das Standard-Paket ist immer wählbar). Pakete werden beim Login geladen (`PdvmCentralSystemsteuerung.layout_packages`); fehlende Kopien werden wie beim Standard-Paket aus `sys_layout` übernommen. Struktur (Layout-Varianten, Abschnitt 8) und Mandanten-Overlay sind für alle Pakete gleich; Pakete liefern nur Farbschemen.

### 2.2 Benutzer-Ebene (`msy_systemsteuerung`)
**Aktualisiert (siehe Abschnitt 6):** Die Variantenwahl liegt nicht mehr in `asy_benutzer.CONFIG`, sondern mandantenbezogen in `msy_systemsteuerung` (Gruppe = Benutzer-GUID). Der Mandant gibt mit `THEME_LIGHT`/`THEME_DARK` (in `asy_mandanten.CONFIG`) die Standard-Varianten vor.

*   **Felder (Benutzer):** `THEME_CHOICE` (Paket-GUID, leer = Standard-Paket), `THEME_MODE`, `THEME_VARIANT_LIGHT`, `THEME_VARIANT_DARK`, `THEME_OVERRIDES`
*   **Felder (Mandant, `CONFIG`):** `THEME_GUID`, `THEME_ALLOWED`, `THEME_LIGHT`, `THEME_DARK`, `THEME_DEFAULT_MODE`, `USER_THEME_EDIT`, `LAYOUT_DEFAULT`, `LAYOUT_ALLOWED` (Strukturvarianten, Abschnitt 8)
*   **Felder (Benutzer) zusätzlich:** `LAYOUT_CHOICE`

### 2.3 Theme-Paket (`sys_layout` / `msy_layout`)
Ein Datensatz ist ein **Theme-Paket** und enthält mehrere Varianten als **Gruppen**.

*   **Tabellen:** `sys_layout` (global), `msy_layout` (Kopie je Mandanten-DB plus Overlay-Zeile)
*   **Struktur:**
    *   **Datensatz (UUID):** das Paket (z. B. "Orange Theme").
    *   **Gruppe (Key):** Name der Variante (`light`, `dark`, `Orange_Light`, `Orange_Dark` ...); die Auswahl steht in Abschnitt 6.
    *   **Untergruppen:** `color` (globale Farben), `font`, `block_*` (Style Blocks).
*   **Token-Schema:** Welche Tokens es gibt (Typ, Benutzer-Anpassbarkeit, Kontrastpaare), steht in `backend/app/core/theme_schema.py`; die Basissätze 000/555/666 bleiben unberührt (Abweichung A im Plan).

```json
{
  "Orange_Light": {
    "color": { "primary-500": "#ff9800", "text-primary": "#212121", "background-primary": "#ffffff" },
    "font": { "primary": "Inter, sans-serif", "scale": "1" },
    "block_input_std": { "bg_color": "#ffffff", "border": "1px solid #ff9800", "radius": "4px" },
    "block_btn_primary": { "text_color": "#212121" }
  }
}
```

Nicht gesetzte Tokens fallen im CSS auf die semantischen Tokens zurück (Abschnitt 5.3). Freie Eigenschaften (z. B. `backdropFilter`) und Komponenten-Zuweisungen per Name (`"DateTimePicker": "block_input_std"`) gibt es nicht; Zuordnung und Eigenschaften legt das Schema fest.

## 3. Implementierung

### 3.1 Backend
*   `PdvmCentralSystemsteuerung` hält Paket (`self.layout`), Mandanten-Overlay und Benutzerwerte und löst das aktive Theme über `theme_service.resolve_theme` auf (`resolve_active_theme`).
*   Router (`/api/layout`) enthalten kein SQL; Schreibwege laufen über `central_write_service` (Abschnitt 7).
*   Es wird immer nur die aufgelöste Variante des aktuellen Modus geliefert (`GET /resolved`).

### 3.2 Frontend
*   `contexts/ThemeContext.tsx` (`ThemeProvider`, `useTheme`) ist die einzige Instanz (Abschnitt 6): setzt für jedes Token `--<gruppe>-<token>` auf `:root` (Namenskonvention in `utils/themeVars.ts`), z. B. `block_header_std.bg_color` → `--block-header-std-bg-color`, `color.primary-500` → `--color-primary-500`.
*   Es gibt keine Parser-Logik für Referenzen oder `--comp-*`-Variablen mehr.

### 3.3 CSS-Anpassung
UI-Komponenten nutzen die Block-Variable mit Fallback auf ein semantisches Token; Farbliterale stehen nur in `variables.css` (Guard-Test, Abschnitt 5.9):
```css
.form-input {
  background: var(--block-input-std-bg-color, var(--color-background-primary));
  color: var(--block-input-std-text-color, var(--color-text-primary));
  border: var(--block-input-std-border, 1px solid var(--color-border-medium));
}
```

## 4. Migrationspfad (Status: abgeschlossen)

1.  **Backend:** Resolver, Overlays, Editor-Endpunkte (P0/P1/P4, Abschnitt 6 und 7).
2.  **Frontend:** `ThemeContext` statt mehrerer `useTheme`-Instanzen, alle CSS/TSX auf Tokens (P0/P2); Guard-Test verhindert Rückfälle.
3.  **Editor, Strukturvarianten, Kontrast:** P3 bis P6 (Abschnitte 5.10, 7, 8, 9).
4.  **Daten:** Standard-Themes sind kontrastgeprüft (`tools/fix_theme_contrast_v1.py`, Dry-Run meldet keine Verstöße).

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

| **`block_view_table_row_selected`** | Selected Row | `.pdvm-view-row-selected` | `bg_color` | `var(--state-selected)` |

| **`block_view_group_row`** | Group Header Row | `.pdvm-view-group-row` | `bg_color` | `var(--state-subtle)` |
| | | | `text_color` | `var(--color-text-primary)` |

| **`block_view_total_row`** | Grand Total Row | `.pdvm-view-total-row` | `bg_color` | `var(--state-hover)` |
| | | | `text_color` | `var(--color-text-primary)` |

| **`block_tabs_std`** | Tabs (Dialog intern) | `.pdvm-tabs__*` | `bar_padding` | `6px` |
| | | | `bar_bg_color` | `transparent` |
| | | | `bar_border_bottom` | `1px solid var(--color-border-light)` |
| | | | `bar_sticky_height` | `44px` |
| | | | `tab_padding` | `8px 12px` |
| | | | `tab_radius` | `var(--border-radius-md)` |
| | | | `tab_bg_color` | `transparent` |
| | | | `tab_text_color` | `var(--color-text-secondary)` |
| | | | `tab_hover_bg_color` | `var(--state-hover)` |
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
| | | | `field_bg_color` | `var(--block-pic-std-bg-color)` → `var(--color-background-primary)` |
| | | | `field_text_color` | `var(--block-pic-std-text-color)` → `var(--color-text-primary)` |

| **`block_view_btn_std`** | View Buttons (Spalten/Reset/Gruppierung) | `.pdvm-view-btn` | `bg_color` | `var(--color-background-primary)` |
| | | | `text_color` | `var(--color-text-primary)` |
| | | | `border` | `1px solid var(--color-border-medium)` |
| | | | `radius` | `var(--border-radius-md)` |
| | | | `hover_bg` | `var(--state-hover)` |

| **`block_view_input_std`** | View Filter/Input | `.pdvm-view-input` | `bg_color` | `var(--color-background-primary)` |
| | | | `text_color` | `var(--color-text-primary)` |
| | | | `border` | `1px solid var(--color-border-medium)` |
| | | | `radius` | `var(--border-radius-md)` |

### 5.3 Implementation Details

1. **Injection:** Der `ThemeProvider` konvertiert Block-Namen wie `block_header_std` in CSS Variablen wie `--block-header-std-bg-color`.
2. **Usage:** CSS verwendet `var(--block-name-prop, FALLBACK)`.
3. **Fallback:** Die Fallbacks referenzieren semantische Variablen aus `variables.css` (z.B. `--color-primary-500`, `--state-hover`), welche aus der Untergruppe `color` des Themes befüllt bzw. per `color-mix` abgeleitet werden (5.9).
4. **Resilience:** Wenn ein Theme keine Blöcke definiert, greift das System auf die globalen Farben zurück, solange die CSS-Dateien korrekte Fallbacks definiert haben.

### 5.4 Widget Mapping (Komplexe Komponenten)

Komplexe Widgets setzen sich oft aus mehreren Blöcken zusammen. Hier wird definiert, welche Blöcke für welche Teilelemente verwendet werden.

| Widget | Element | Verwendeter Block | CSS Variable (Beispiel) | Beschreibung |
| :--- | :--- | :--- | :--- | :--- |
| **`PdvmDateTimePicker`** | **Eingabefeld** | `block_pic_std` (in der Stichtagsleiste: `block_stichtag_std.field_*`) | `--block-pic-std-bg-color`, `--block-stichtag-std-field-bg-color` | Rahmen, Hintergrund und Text des Feldes. |
|  | **Popover** | `block_pic_popover` | `--block-pic-popover-bg-color` | Hintergrund, Text, Rahmen, Radius und Schatten des Auswahlfensters; `field_bg_color`/`field_text_color` für Datums-/Zeitfelder. |
|  | **Buttons im Popover** | Palette | `--color-primary-500`, `--color-text-inverse` | „Übernehmen“ (Primärfläche), „Jetzt“ (Feldfarben), „Abbrechen“/„Leeren“ (Popover-Textfarbe). |
|  | **Native Felder** | Modus | `color-scheme` | Kalender-/Uhr-Symbol und Auswahlfenster des Browsers folgen `data-theme` (`variables.css`). |
| **`StichtagsBar`** | **Beschriftung, Wert, Titel** | `block_stichtag_std` | `--block-stichtag-std-text-color` | Textfarbe wird direkt gesetzt; die globalen `--color-text-*` werden in der Leiste nicht überschrieben. |
|  | **„Jetzt“-Button** | `block_stichtag_std` | `--block-stichtag-std-field-bg-color` | Setzt den Stichtag sofort auf aktuelles Datum und Uhrzeit. |

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

**Status:** Menü nutzt seit P2 die Block-Variablen (`--block-menu-*`) mit Fallback auf die semantischen Tokens (`--color-*`, `--state-*`); Legacy-Variablen (`--surface-*`, `--border-color`) sind entfernt.
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

## 5.9 Weitere Blocks (P2) und abgeleitete Tokens

Neu im Token-Schema (`theme_schema.TOKEN_SCHEMA`), im CSS mit der Kette `var(--block-<name>-<prop>, var(--<semantisches Token>))`:

| Block | Verwendung | Properties |
| :--- | :--- | :--- |
| `block_dialog_modal` | `PdvmDialogModal` | `bg_color`, `text_color`, `border`, `radius`, `shadow`, `overlay_color`, `divider_color` |
| `block_pic_std` | `PdvmInputControl`, `PdvmDateTimePicker` (Feld) | `bg_color`, `text_color`, `border`, `radius`, `label_color`, `readonly_bg`, `focus_color` |
| `block_pic_popover` | Auswahlfenster des `PdvmDateTimePicker` (Datum/Zeit, auch Stichtag) | `bg_color`, `text_color`, `border`, `radius`, `shadow`, `field_bg_color`, `field_text_color` |
| `block_stichtag_std` | Stichtagsleiste | zusätzlich `field_bg_color`, `field_text_color` (Eingabefeld und „Jetzt“-Button in der Leiste) |
| `block_card_std` | Karten (Dashboard, Service-Manager, Login) | `bg_color`, `text_color`, `border`, `radius`, `shadow` |
| `block_menu_horizontal/vertical/button/dropdown` | Menüs (5.8) | siehe 5.8 |
| `block_view_*`, `block_tabs_std` | Views, Tabs (5.1, 5.2, 5.5) | siehe dort |
| `block_btn_primary` | Primärbutton | zusätzlich `border` |

**Abgeleitete Tokens** (`styles/base/variables.css`, berechnet per `color-mix` aus den Theme-Farben, folgen Hell/Dunkel automatisch):
- Zustände: `--state-hover`, `--state-hover-strong`, `--state-subtle`, `--state-selected`, `--state-selected-border`, `--state-focus-ring`, `--state-focus-border`
- Status: `--color-<success|warning|error|info>-bg|-border|-text`. Der Hintergrund `-bg` ist **deckend** (Mischung der Statusfarbe mit `--color-background-primary`), damit die Textfarbe `-text` nicht von dem abhängt, was hinter der Meldung liegt (z. B. Verläufe); `-border` bleibt transparent. Hell: Text = Statusfarbe mit Schwarz gemischt, Dunkel: mit Weiß. `test_theme_color.py::test_status_message_colors_are_readable_in_default_themes` rechnet die Formeln aus `variables.css` nach (≥ 4,5:1, Defaults und Pakete liegen bei 5,6 bis 9,3:1).
- Sonstige: `--color-overlay`, `--color-overlay-strong`, `--color-divider`, `--color-highlight`, `--color-highlight-border`

**Regeln (durch `backend/test_frontend_theme_guard.py` erzwungen):**
- Farbliterale (`#hex`, `rgb()`, `hsl()`, benannte Farben in Inline-Styles) stehen nur in `variables.css`; auch keine Literale als `var()`-Fallback.
- Keine Legacy-Variablen (`--surface-*`, `--border-color`, `--primary-color`, `--text-primary|secondary`, `--color-error-dark`) und kein `.dark`-Selektor (Modus steht in `:root[data-theme]`).
- Jede im CSS/TSX verwendete `--block-*`-Variable muss im Token-Schema existieren.
- Text auf gefüllten Primärflächen (Buttons) nutzt `--color-text-inverse`, nicht `--color-text-on-primary` (das ist die Textfarbe auf der Fläche `background-primary`).
- Markenfarben-Stufen (`--color-primary-*`, `--color-secondary-*`) sind **keine Textfarbe** (Orange auf Weiß 2,2:1); Text/Links auf der Seitenfläche nutzen `--color-text-on-primary` (Pflichtpaar auf `background-primary`). Die hellen Stufen 50 bis 200 bleiben im Dunkelmodus hell und sind **keine Fläche**; Tönungen entstehen per `color-mix` aus `--color-primary-500` und dem Hintergrund bzw. über `--state-*`. Beides prüfen `test_brand_colors_are_not_used_as_text_color` und `test_light_color_scale_is_not_used_as_surface`.

## 5.10 Editor-Controls aus dem Token-Schema (P3)

`GET /api/layout/catalog` liefert das Token-Schema mit **generierten Control-Definitionen**. Je Token:

| Feld | Bedeutung |
| :--- | :--- |
| `label`, Gruppen-`label` | deutsche Beschriftung (`theme_schema.token_label`, `GROUP_LABELS`, `PROP_LABELS`) |
| `type` | Schema-Typ (`color`, `length`, `border`, `shadow`, `font`, `number`) |
| `control_type` | Typ des `PdvmInputControl`: `color`, `css_length`, `css_border`, `font_family`, `string` (Schatten), `dropdown` (Skalierung, mit `options`) |
| `user_editable`, `min`, `max`, `options` | Anpassbarkeit und Wertegrenzen |
| `contrast_against` | Gegenfarben aus den Kontrast-Pflichtpaaren (`[{ref: "<gruppe>.<token>", min}]`, in beide Richtungen) |

Die Controls werden bewusst **nicht** als `sys_control_dict`-Zeilen gepflegt: Die Variantengruppe eines Themes (`light`, `dark`, `Orange_Light` ...) ist zur Laufzeit variabel und die Token-Tiefe (`Gruppe.Block.Token`) passt nicht auf das statische `GRUPPE`/`FELD`-Modell der Frames. Das Schema bleibt die einzige Quelle; Editoren rendern die Katalogeintraege direkt mit `PdvmInputControl` (Typen siehe `PDVM_EDIT_CONTROL_SPEC.md`, Abschnitt 8).

**Frontend-Bausteine:** `components/common/PdvmThemeInputs.tsx` (`PdvmColorInput`, `PdvmLengthInput`, `PdvmBorderInput`, `PdvmFontInput`), `PdvmThemePreview.tsx`, `utils/themeTokens.ts` (Validierung und WCAG-Kontrast, Spiegel von `theme_service`), `utils/themeVars.ts` (Variablennamen `--<gruppe>-<token>`, einzige Stelle der Namenskonvention). Die Vorschau berechnet die abgeleiteten Tokens (`--state-*`, `--color-<status>-*`) im Container neu (`.pdvm-theme-preview` in `variables.css`).

---

## 6. Schichtmodell und Resolver (P0/P1, Stand 11/2026)

Das aktive Theme wird **serverseitig** aus drei Schichten aufgeloest; das Frontend setzt nur das Ergebnis.

| Schicht | Ort | Inhalt |
| :--- | :--- | :--- |
| 1. Theme-Paket | `msy_layout` (Kopie aus `sys_layout`, Mandant `CONFIG.THEME_GUID`) | Variante je Gruppe (`light`/`dark`/`Orange_Light` ...) mit `color`, `font`, `block_*` |
| 2. Mandanten-Overlay | `msy_layout`, eigene Zeile mit `link_uid` = Mandant und `ROOT.LAYER = "OVERLAY"` | nur Abweichungen, Gruppen `light`/`dark` (Modus, nicht Variantenname) |
| 3. Benutzer-Overlay | `msy_systemsteuerung`, Gruppe = Benutzer-GUID, Feld `THEME_OVERRIDES` | wie Overlay, nur fuer vom Mandanten freigegebene und `user_editable` Tokens |

**Auswahl des Pakets** (`get_user_theme_package_guid`): Benutzer `THEME_CHOICE` (nur wenn freigegeben, d. h. Standard-Paket oder in `THEME_ALLOWED`) -> Mandant `CONFIG.THEME_GUID`. Das Mandanten-Overlay (eine Zeile je Mandant) und das Benutzer-Overlay gelten unabhängig vom Paket; so behält der Benutzer seine persönlichen Farben beim Paketwechsel.
**Auswahl der Variante** (`PdvmCentralSystemsteuerung.get_user_theme_group`): Benutzer `THEME_VARIANT_LIGHT|DARK` (msy_systemsteuerung) -> Mandant `CONFIG.THEME_LIGHT|THEME_DARK` -> Modus-Name; Kandidaten, die im aktiven Paket nicht existieren (z. B. nach Paketwechsel), werden übersprungen. `asy_benutzer.CONFIG.THEME_*` wird nicht mehr gelesen.
**Auswahl des Modus** (`get_user_theme_mode`): Benutzer `THEME_MODE` -> Mandant `CONFIG.THEME_DEFAULT_MODE` -> `light`.
**Freigabe fuer Benutzer:** `asy_mandanten.CONFIG.USER_THEME_EDIT` = Liste von Mustern (`color.primary-*`, `color.background-primary`). Ohne Eintrag darf kein Benutzer Tokens ueberschreiben. Textfarben (`color.text-*`) und Blocks sind nie benutzeranpassbar.

**Token-Schema:** `backend/app/core/theme_schema.py` (Gruppen, Typen `color|length|border|shadow|font|number`, `user_editable`, Kontrast-Pflichtpaare). `backend/app/core/theme_service.py` validiert Werte restriktiv (kein `url()`, `;`, `{}`; Overlay-Werte mit Fehlern werden verworfen und als `warnings` gemeldet) und prueft die Pflichtpaare nach WCAG AA (4,5:1): `contrast_issues` im Resolver (Bericht) und Durchsetzung beim Speichern (Abschnitt 9).
Tokennamen in `color`/`font` sind bindestrich-normalisiert (`text-on_primary` == `text-on-primary`).

**API (`/api/layout`):**
- `GET /resolved?mode=light|dark` - aufgeloestes Theme (`blocks`, `layers`, `contrast_issues`, `warnings`); ohne `mode` gilt die Benutzer-Praeferenz
- `GET /catalog` - Token-Schema inkl. generierter Control-Definitionen (Beschriftung, `control_type`, Kontrast-Gegenfarben; siehe 5.10) und `contrast_pairs` (Abschnitt 9)
- `GET|POST /preferences/theme` - Hell/Dunkel-Praeferenz
- Entfernt: `GET /active`, `GET /{mandant_uid}`, `GET|PUT /{mandant_uid}/{theme}`, `GET /current/theme`, `GET /api/gcs/theme`

**Frontend:** `contexts/ThemeContext.tsx` (`ThemeProvider`, `useTheme`) ist die einzige Instanz. Setzt `--<gruppe>-<token>` auf `:root`, `data-theme` und Klasse `dark`, entfernt nicht mehr vorhandene Variablen und cached je Mandant/Modus in `localStorage` (kein Flackern beim Umschalten).

## 7. Theme-Editor und Schreibwege (P4)

**Rolle `overlay`:** Wer in `asy_benutzer.PERMISSIONS.ROLES` (auch `SECURITY.ROLES`) die Rolle `overlay` hat, darf Mandanten-Overlay und Theme-Einstellungen des Mandanten ändern. Die Rolle ist unabhängig von `admin` und wird ausdrücklich vergeben (`security.has_overlay_rights`, Dependency `require_overlay_user`).

**Seite `/design`** (`components/design/ThemeEditorPage.tsx`, Link im Header neben dem Hell/Dunkel-Schalter):
- Tab **Mein Design** (jeder Benutzer): Farbschema (Theme-Paket, nur bei mehr als einem freigegebenen Paket), Variante Hell/Dunkel wählen und die vom Mandanten freigegebenen Tokens überschreiben.
- Tab **Mandant** (nur Rolle `overlay`): Standard-Paket, weitere Pakete für Benutzer, Standard-Varianten, Standard-Modus (`THEME_DEFAULT_MODE`), Freigaben für Benutzer (`USER_THEME_EDIT`, Presets aus `GET /catalog` → `user_edit_presets`) und das Mandanten-Overlay aller Tokens (gilt für alle Pakete).
- Alle Felder sind `PdvmInputControl` mit dem `control_type` aus dem Katalog; Platzhalter = Wert der Basis, leer = nicht überschrieben. Live-Vorschau (`theme_preview`) zeigt Basis + Entwurf; Kontrast-Verstöße (WCAG AA) werden beim Speichern abgelehnt, mit Vorschlägen (siehe Abschnitt 9).
- Server-Antworten: 422 mit allen Fehlern (`detail.errors`), 409 bei Schreibkonflikt, 403 ohne Rolle.

**API (`/api/layout`):**
- `GET /editor/{user|mandant}` - Basis je Modus, bestehendes Overlay, Einstellungen, Varianten, `packages` (freigegebene Pakete), `allowed_patterns` (Benutzer), `can_edit_overlay`; `?package=<guid>` (Benutzer) liefert Basis/Varianten eines anderen freigegebenen Pakets als Vorschau
- `GET /packages` (Rolle `overlay`) - alle `sys_layout`-Pakete (ohne 000/555/666) zur Freigabe
- `PUT /overlay/mandant` (Rolle `overlay`) - schreibt die `msy_layout`-Zeile (`link_uid` = Mandant, `ROOT.LAYER = "OVERLAY"`, `ROOT.BASE_THEME_GUID`) über `central_write_service`; Update mit `expected_snapshot_daten`. Das Overlay gilt für alle freigegebenen Pakete; die Kontrastprüfung läuft gegen jedes Paket (Fehlertext mit Präfix `[Paketname]`, `detail.contrast[].package`)
- `PUT /settings/mandant` (Rolle `overlay`) - `THEME_GUID` (`theme_default`), `THEME_ALLOWED` (`theme_allowed`), `THEME_LIGHT`, `THEME_DARK`, `THEME_DEFAULT_MODE`, `USER_THEME_EDIT` in `asy_mandanten.CONFIG` (Pakete müssen in `sys_layout` existieren, Varianten im (neuen) Standard-Paket, Freigaben müssen benutzeranpassbare Tokens treffen); Update mit `expected_snapshot_daten`; Pakete werden danach in der Session neu geladen
- `PUT /settings/user` - `THEME_CHOICE` (`theme_choice`, nur freigegebene Pakete), `THEME_OVERRIDES`, `THEME_VARIANT_LIGHT|DARK` in `msy_systemsteuerung`; strikt geprüft (Varianten gegen das gewählte Paket, nur freigegebene, `user_editable` Tokens)

**Prüfung beim Speichern** (`theme_service.validate_overlay_payload`) ist strikt: jede unbekannte/ungültige/nicht freigegebene Angabe liefert einen Fehler. Der Resolver bleibt tolerant (verwirft still, siehe Abschnitt 6).

**Hinweise:** Änderungen wirken in der eigenen Sitzung sofort (Overlay/Config werden in der GCS-Session aktualisiert, das Frontend lädt das Theme neu); andere laufende Sitzungen übernehmen sie beim nächsten Login. Das Paket selbst (`sys_layout`/`msy_layout`-Kopie) ist nicht über den Editor änderbar.

Offen (nächste Phasen): keine; Kontrast siehe Abschnitt 9.

---

## 8. Strukturkatalog / Layout-Varianten (P5)

Der Strukturkatalog (`backend/app/core/layout_schema.py`) legt fest, welche Strukturvarianten es je Bereich gibt. Eine Variante ist **nur ein Kennzeichen** (`data-layout-<bereich>="<id>"` auf `<html>`); das Aussehen kommt aus dem CSS im Code (`frontend/src/styles/layouts/variants.css`). Es gibt kein freies CSS in der Datenbank.

| Bereich | Varianten (id) | Wirkung |
| :--- | :--- | :--- |
| `header` Kopfzeile | `standard`, `kompakt` | Höhe 64 → 48 px, ohne Adresszeile/Rolle, kleineres Logo |
| `shell` Navigation | `standard`, `schmal`, `breit` | Seitenleiste 240/200/280 px, Menüleiste 48/40/52 px |
| `dichte` Dichte | `standard`, `kompakt`, `luftig` | Abstandsskala (`--spacing-*`) und `--density-*` für Formularfelder und Tabellenzellen |
| `form` Formulare | `standard` (Karte), `flach`, `label-links` | Darstellung von `PdvmInputControl` |
| `tabelle` Tabellen | `standard`, `zebra`, `linien` | Darstellung der View-Tabelle |

**Daten und Auflösung** (spätere Ebene gewinnt, solange freigegeben):
1. Schema-Standard (`standard`)
2. Mandanten-Vorgabe `asy_mandanten.CONFIG.LAYOUT_DEFAULT` = `{bereich: id}`
3. Benutzerwahl `msy_systemsteuerung.<user>.LAYOUT_CHOICE` = `{bereich: id}`; wählbar sind nur die Mandanten-Vorgabe und die Freigaben `CONFIG.LAYOUT_ALLOWED` = `{bereich: [id, ...]}` (Opt-in wie `USER_THEME_EDIT`; ohne Eintrag gilt nur die Vorgabe).

`GET /api/layout/resolved` liefert zusätzlich `layout` (wirksame Varianten) und `layout_warnings`; der `ThemeProvider` setzt die Attribute (`utils/layoutAttributes.ts`) und cached sie mit dem Theme. `GET /editor/{scope}` liefert `layout` (Bereiche, Optionen mit Beschreibung, `available`, `mandant_default`); `PUT /settings/mandant` nimmt `layout_default` und `layout_allowed` (Rolle `overlay`), `PUT /settings/user` nimmt `layout_choice` (nur freigegeben). Fehler wie bei den Tokens: 422 mit Liste.

**Editor** (`/design`): Abschnitt "Layout". Benutzer sehen nur Bereiche mit mindestens zwei wählbaren Varianten; der Mandant legt je Bereich Vorgabe und Freigaben fest. Die Auswahl wird sofort als Vorschau auf `<html>` angewendet und beim Verlassen ohne Speichern zurückgesetzt.

**Neue Variante hinzufügen:** Eintrag in `LAYOUT_SCHEMA` (Label, Beschreibung) **und** CSS-Regeln in `variants.css`; `test_frontend_theme_guard.py` prüft, dass beides zusammenpasst (jede Nicht-Standard-Option hat CSS, jedes CSS-Attribut einen Katalogeintrag).

---

## 9. Kontrast-Durchsetzung (P6)

**Regel:** Ein Overlay (Mandant oder Benutzer) wird nicht gespeichert, wenn es ein Pflichtpaar unter WCAG AA (Text 4,5:1) bringt. So bleibt immer alles sichtbar.

**Pflichtpaare** (`theme_schema.CONTRAST_PAIRS`, 21 Stück): Text primär/sekundär auf Hintergrund primär/sekundär, `text-inverse` auf `primary-500`, die `text-on-*`-Farben sowie Text/Hintergrund der Blöcke `surface_main`, `header_std`, `sidebar_std`, `input_std`, `btn_primary`, `stichtag_std`, `card_std`, `dialog_modal`, `pic_std`, dazu Feld-Text/-Hintergrund der Stichtagsleiste (`stichtag_std.field_*`) und Text/Hintergrund sowie Feld-Text/-Hintergrund des Datum/Zeit-Popovers (`pic_popover`). Hat ein Block-Token keinen eigenen Wert, gilt der CSS-Fallback (`CONTRAST_FALLBACKS`, z. B. `block_btn_primary.bg_color` → `color.primary-500`); `GET /catalog` liefert dazu `contrast_pairs` (mit `fg_chain`/`bg_chain`), damit das Frontend dieselbe Regel auswertet.

**Geprüft wird nur, was die Änderung berührt** (`theme_service.contrast_violations`): Ein Paar zählt, wenn mindestens eine wirksame Quelle (nach Fallbackkette) aus dem Overlay stammt. Verstöße, die schon im Paket stecken, blockieren nicht, werden im Editor aber als Hinweis angezeigt.

**Antwort beim Speichern:** 422 mit `detail.errors` (Text) und `detail.contrast` (je Verstoß: `mode`, `fg`, `bg`, `ratio`, `min`, `suggestions` mit `ref` und `value`).

**Vorschlag der nächsten konformen Farbe** (`theme_color.suggest_compliant_color`, Spiegel `utils/themeColor.ts`): Die Farbe wird in OKLab nur in der Helligkeit L verschoben (Farbton und Sättigung bleiben, Gamut-Clipping), in beide Richtungen in Schritten von 0,0025 gesucht; die kleinste Verschiebung, die das Minimum erreicht, gewinnt (Rückfall Schwarz/Weiß). Beispiel: `#e65100` auf Weiß → `#d04900` (4,53:1). Bei Paaren schlägt der Editor bevorzugt eine Änderung der Textfarbe vor; Hintergründe werden mit dem Faktor `BG_PENALTY` (4) bestraft. Frontend: `PdvmColorInput` zeigt „Vorschlag übernehmen“, der Editor listet alle Verstöße mit „Alle Vorschläge übernehmen“ und sperrt Speichern, solange Verstöße bestehen.

**Laufzeitschutz:** Ändert sich die Basis (Variantenwechsel, neues Mandanten-Overlay), kann ein altes Benutzer-Overlay ungültig werden. Der Resolver (`enforce_contrast`) ignoriert dann die verursachenden Benutzer-Tokens (je Verstoß eine Seite, bevorzugt den Text) und meldet eine Warnung.

**Reparatur der Pakete:** `backend/tools/fix_theme_contrast_v1.py` (Dry-Run; `--apply --confirm-backup`) korrigiert Paket-Varianten in `sys_layout` und allen `msy_layout` minimal (`theme_service.repair_contrast`), überspringt reservierte Zeilen (000/555/666) und Overlay-Zeilen, schreibt einen Snapshot (`backend/reports/`) und einen Bericht (`docs/reports/`). Verletzte Paare werden mit Komfortziel 7:1 repariert (`comfort`), damit repariertes Grau nicht nur knapp das Minimum erreicht. Rohdaten dürfen Schlüssel mit Unterstrich enthalten (`text-on_tertiary`); Prüfung und Reparatur vergleichen normalisiert. Stand 10.11.2026: zwei Läufe (zuerst 6 Zeilen, dann 6 Zeilen mit den `text-on-*`-Paaren), danach keine Verstöße.

**Standard-Pakete anlegen:** `backend/tools/seed_theme_packages_v1.py` legt „Red Theme“, „Pink Theme“ und „Brown Theme“ in `sys_layout` an (Dry-Run; `--apply --confirm-backup`). Jede Variante wird vor dem Schreiben auf gültige Werte und alle Pflicht-Kontrastpaare geprüft; bei einem Verstoß wird nichts geschrieben. Die UIDs sind deterministisch (uuid5), bestehende Zeilen bleiben unverändert (`--force-update` mit Snapshot). Neue Pakete werden anschließend vom Mandanten im Editor freigegeben.

**Defaults ohne Paket:** Die Hell/Dunkel-Defaults in `variables.css` gelten ohne geladenes Theme (Login) und für Mandanten ohne Paketkopie (z. B. `filiale_test_2`, `ganz_neu1`). Sie bestehen alle Pflichtpaare (`CONTRAST_PAIRS`); `test_theme_color.py::test_css_default_themes_pass_required_contrast` hält das fest.

**Ungültige Paketwerte:** Werte bekannter Tokens, die dem Typ nicht entsprechen (z. B. Farbe `000000` ohne `#`), würden als CSS-Variable gesetzt und die Darstellung eines Blocks brechen (die Deklaration wird ungültig, der Text fällt auf geerbte Farben zurück). Der Resolver (`sanitize_package_variant`) verwirft solche Werte mit Warnung `Paket: ungueltiger Wert ...`, dann greift der CSS-Fallback. Das Reparatur-Tool ergänzt fehlende `#` (`normalize_package_values`) und meldet nicht behebbare Werte. Stand 10.11.2026: `block_stichtag_std.text_color = "000000"` im Orange-Paket (Dunkel, `sys_layout` und eine Kopie) korrigiert.

---

