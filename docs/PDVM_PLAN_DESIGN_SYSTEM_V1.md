# PDVM Plan: Design-System (Farben, Layout-Strukturen, Personalisierung) (V1)

Status: Phase P0 bis P7 abgeschlossen (10.11.2026). Das System ist noch nicht produktiv, es gibt keine Zeitvorgaben.
Verbindliche Grundlage: [ARCHITECTURE_RULES.md](../ARCHITECTURE_RULES.md) (insbesondere 1.1, 1.11-1.13, 2.1, 2.14, 4.2).
Fachliche Spezifikation des Theming-Systems: [specs/THEMING_SYSTEM.md](specs/THEMING_SYSTEM.md) (Abschnitt 6 = Schichtmodell und Resolver).

## 1. Anforderung (08.11.2026)
1. Wesentliche UI-Elemente (Farben, Blöcke) sind in der Datenbank mit **vorgegebenen Strukturen** steuerbar. Änderungen erfolgen über PDVM-Inputcontrols (ggf. erweitern).
2. Layoutstrukturen (Header, Aufbau, Form-Inputcontrols usw.) werden hinterlegt; je Mandant werden nur ausgewählte Strukturen angeboten.
3. Je Mandant gibt es ein Default-Farbschema (hell/dunkel); der Benutzer kann es persönlich anpassen. Der Wechsel hell/dunkel erfolgt über das Mond/Sonne-Symbol im Header.
4. Kontrast der heutigen Farben ist nicht überall gut - **zweiter Schritt** (P6), nicht Teil von P0/P1.

## 2. Analyse Ist-Stand
Datenfluss vor P0/P1: `asy_mandanten.CONFIG.THEME_GUID` -> Paket in `sys_layout` (Blue/Green/Orange mit Gruppen `light`, `dark`, `info`) -> Kopie nach `msy_layout` beim Login -> `GET /api/layout/active` -> Hook `useTheme` setzt CSS-Variablen. Hell/Dunkel-Modus des Benutzers in `msy_systemsteuerung.THEME_MODE`.

Befunde:
| # | Befund | Status |
|---|---|---|
| 1 | Nur 10 Blöcke (Header, Sidebar, Input, Button, Stichtag, Surface ...); Menü, Dialog, Tabelle, Tabs, Views fehlen. Harte Farben in CSS (z. B. Dashboard 20, PdvmDialogModal 22, ServiceManager 26) und Inline-Farben in 7 TSX-Dateien (Verstoß Regel 4.2) | erledigt (P2) |
| 2 | Kontrast: Orange-Light Text `#e65100` auf Weiß 3,8:1; Button-Text Weiß auf `#ff9800` 2,2:1; `text-on-secondary` 1,4:1; Dark-Button Weiß auf `#ffb74d` 1,7:1 (Ziel 4,5:1) | offen (P6) |
| 3 | `useTheme()` wurde je Komponente einzeln aufgerufen (mehrere State-Instanzen, Verstoß Regel 2.1) | erledigt (P0) |
| 4 | `THEME_LIGHT`/`THEME_DARK` doppelt gepflegt (Mandant und `asy_benutzer.CONFIG`, global über Mandanten); bei "Filiale Test 1" vertauscht | erledigt (P0/P1) |
| 5 | Legacy-Endpunkte `PUT /{mandant_uid}/{theme}` u. a. suchten `daten.mandant_uid` (existiert nicht), ohne Rechteprüfung | erledigt (P0) |
| 6 | `data-theme` wurde nie gesetzt, daher griffen alle `:root[data-theme="dark"]`-Regeln im CSS nie (Mitursache der Kontrastprobleme im Dunkelmodus) | erledigt (P0) |
| 7 | Vorlagen 555/666 von `sys_layout` leer (keine vorgegebene Struktur in der DB) | siehe Abweichung A |

## 3. Zielarchitektur
Serverseitiger Resolver mit Schichten (spätere überschreibt frühere):

```
1 Code-Fallback (variables.css, nur neutral)
2 Theme-Paket          msy_layout (Kopie aus sys_layout)   Systemadmin, global
3 Mandanten-Overlay    msy_layout (eigene Zeile)           Mandanten-Admin, nur Abweichungen
4 Benutzer-Overlay     msy_systemsteuerung                 nur freigegebene Tokens
        -> theme_service.resolve_theme()
GET /api/layout/resolved  (Tokens, layers, contrast_issues, warnings)
```

### 3.1 Token-Modell
- **Basis** (ca. 12-15 Werte je Variante): Primär, Sekundär, Hintergrund, Fläche, Text, Rahmen, Erfolg/Warnung/Fehler/Info. Skalen (`primary-50..900`) und "on"-Farben sollen später daraus berechnet werden (P6).
- **Semantisch:** `surface`, `text`, `border`, `focus`.
- **Blöcke:** vorhandene `block_*` plus neue (`menu`, `dialog`, `tabs`, `view_*`, `form`); Hartwerte nur im Expertenmodus.
- Pflichtpaare für den Kontrast (WCAG AA 4,5:1) sind im Schema hinterlegt; der Resolver meldet Verstöße als `contrast_issues` (P6: Durchsetzung beim Speichern).

### 3.2 Datenmodell
| Ebene | Ort | Inhalt |
|---|---|---|
| Token-Schema | `backend/app/core/theme_schema.py` | Gruppen, Typen (`color`, `length`, `border`, `shadow`, `font`, `number`), `user_editable`, Kontrast-Pflichtpaare |
| Theme-Pakete | `sys_layout` / `msy_layout` | Varianten als Gruppen (`light`, `dark`, `Orange_Light` ...) |
| Strukturkatalog (P5, neu) | `sys_layout_struktur` (System-DB) | Gruppen `HEADER`, `SHELL`, `FORM`, `DICHTE`, `TABELLE`; je Eintrag Guid, Pflicht-`label` (Regel 2.13), Dimensions-Tokens, `data-layout-*`-Attribut; **kein freies CSS in der DB** |
| Mandant | `asy_mandanten.CONFIG` | `THEME_GUID`, `THEME_LIGHT`, `THEME_DARK`, `THEME_DEFAULT_MODE`, `USER_THEME_EDIT`; P5: `LAYOUT_ALLOWED`, `LAYOUT_DEFAULT` |
| Mandanten-Overlay | `msy_layout`, `link_uid` = Mandant, `ROOT.LAYER = "OVERLAY"` | nur Abweichungen, Gruppen `light`/`dark` (Modus) |
| Benutzer | `msy_systemsteuerung` (Gruppe = Benutzer-GUID) | `THEME_MODE`, `THEME_VARIANT_LIGHT/DARK`, `THEME_OVERRIDES`; P5: `LAYOUT_CHOICE` |

### 3.3 Layout-Strukturen je Mandant (P5)
Frontend rendert über `data-layout-header="..."`, `data-layout-shell="..."` usw.; das CSS bleibt im Code, die Werte kommen aus der DB. Der Mandant legt eine Allow-Liste fest, der Benutzer sieht nur diese. Auswahl über `PdvmInputControl` (`dropdown`/`multi_dropdown`, Regel 2.14).

### 3.4 Input-Controls und Editor-Dialoge (P3/P4)
Neue Typen in der Type-Registry von `PdvmInputControl` und im zentralen Typ-Mapper ([PDVM_EDIT_CONTROL_SPEC](specs/PDVM_EDIT_CONTROL_SPEC.md)):
- `color` (Picker + Hex + Kontrast-Badge), `css_length`, `font_family`, `theme_preview` (read-only Live-Vorschau; Variablen nur im Container, nicht auf `:root`).
- `sys_control_dict`-Einträge und Frames werden aus dem Token-Schema per Tool generiert, nicht von Hand gepflegt.
- Drei Dialoge mit demselben Frame, unterschiedlichen Rechten: Systemadmin (Paket), Mandanten-Admin (Overlay, Allow-Liste, Defaults), Benutzer ("Mein Design").

### 3.5 Sicherheit
Tokenwerte werden gegen eine Typ-Whitelist geprüft (kein `url()`, `;`, `{}`, `@import`, Kommentare; max. 200 Zeichen). Ungültige Overlay-Werte werden verworfen und als `warnings` gemeldet, die Auflösung bricht nie ab. Textfarben und Blöcke sind nie benutzeranpassbar; der Mandant gibt Benutzer-Tokens per Muster frei (`USER_THEME_EDIT`, z. B. `color.primary-*`).

## 4. Entscheidungen (08.11.2026)
- Mandanten-Anpassung als **Delta-Overlay** in `msy_layout` (keine volle Kopie pro Mandant).
- Benutzer-Anpassung: Variante/Modus wählen **und** vom Mandanten freigegebene Farb-Tokens ändern.
- Start mit P0 + P1.

## 5. Phasen
| Phase | Inhalt | Ergebnis | Status |
|---|---|---|---|
| P0 | Datenfix vertauschtes Light/Dark, Legacy-Endpunkte entfernen, `ThemeProvider` | stabile Basis | erledigt |
| P1 | Token-Schema, `theme_service`, Resolver, Overlay-Lesen, `GET /resolved`, `/catalog` | aufgelöstes Theme mit Tests | erledigt |
| P2 | Alle CSS/TSX auf Tokens umstellen, Blöcke ergänzen (Menü, Dialog, Tabelle, Tabs, Views, Form), Guard-Test "Hex/rgb nur in `variables.css`", Legacy-Variablen (`--surface-*`, `--border-color`) bereinigen, globales `* { transition }` begrenzen | keine harten Farben mehr | erledigt |
| P3 | Neue Input-Typen, Controls aus dem Token-Schema generieren | Controls in der Registry | erledigt (Abweichung E) |
| P4 | Editor-Dialoge (Mandant, Benutzer) mit Vorschau, **Schreibpfad** für Overlays über `central_write_service`, Rechteprüfung (Rolle `overlay`) | Farben über die Oberfläche änderbar | erledigt (Paket-Editor nicht enthalten, Abweichung F) |
| P5 | Strukturkatalog (Kopfzeile, Navigation, Dichte, Formulare, Tabellen), Allow-Liste je Mandant, Benutzerwahl | Layout je Mandant steuerbar | erledigt (Katalog im Code, Abweichung G) |
| P6 | Kontrast: Validator mit Durchsetzung beim Speichern, Vorschlag der nächsten konformen Farbe, Standard-Themes korrigieren | WCAG AA | erledigt (Abweichung D ersetzt) |
| P7 | Doku abschließen (THEMING_SYSTEM.md, Regel 4.2, EDIT_CONTROL_SPEC) | Specs aktuell | erledigt |

## 6. Stand P0/P1 (08.11.2026)
Umgesetzt:
- Datenfix: `backend/tools/fix_mandant_theme_config_v1.py` (Dry-Run Standard, `--apply`); "Filiale Test 1" korrigiert (`THEME_LIGHT=light`, `THEME_DARK=dark`).
- Backend: `app/core/theme_schema.py`, `app/core/theme_service.py`; in `PdvmCentralSystemsteuerung` `layout_overlay`, `get_user_theme_group` (Benutzer -> Mandant -> Modus-Name), `get_user_theme_mode`, `resolve_active_theme`; `app/api/layout.py` neu (`/resolved`, `/catalog`, `/preferences/theme`); entfernt: `/layout/active`, `/layout/{mandant_uid}`, `/layout/{mandant_uid}/{theme}`, `/layout/current/theme`, `/gcs/theme`.
- Frontend: `contexts/ThemeContext.tsx` (einziger Provider, `localStorage`-Cache je Mandant/Modus, setzt `data-theme`, Klasse `dark`, entfernt veraltete Variablen), `api/layout.ts` neu, `api/theme.ts` entfernt, `hooks/useTheme.ts` als Re-Export.
- Tests: `backend/test_theme_service.py` (13 Tests: Schichten, Validierung, Kontrast, Variantenpriorität, Router). Gesamtstand Backend: 108 bestanden, 4 bekannte Fehlschläge (Dialog-Guardrails, Passwort-Tests; auch ohne diese Änderung vorhanden). `tsc --noEmit` und `vite build` laufen durch.
- Verifikation gegen die echte DB (Mandant "Filiale Test 1"): `resolve_active_theme` liefert für hell/dunkel das Blue-Paket (10 Blöcke).

Beobachtungen für P6 (in P6 behoben; Blue-Paket, Hellmodus): Stichtag-Text 2,65:1, Button-Text 3,12:1, Sidebar-Text 3,6:1; Dunkelmodus: Stichtag-Text 2,65:1.

## 7. Stand P2 (09.11.2026)
Umgesetzt:
- `variables.css`: abgeleitete Tokens per `color-mix` (Zustände `--state-*`, Status `--color-<status>-bg|-border|-text`, `--color-overlay*`, `--color-divider`, `--color-highlight*`); Dark-Overrides nur für Overlay und Status-Text. Das globale `* { transition }` ist auf interaktive Elemente (`a`, `button`, `input`, `select`, `textarea`) begrenzt. Unterstriche in `--color-text-on-*` korrigiert.
- Token-Schema: neue Blocks `block_menu_horizontal|vertical|button|dropdown`, `block_dialog_modal`, `block_card_std`, `block_pic_std`, `block_view_*`, `block_tabs_std`; `block_btn_primary.border`; Längen akzeptieren 1-4 Werte (`8px 12px`).
- Alle CSS- und TS/TSX-Dateien ohne Farbliterale (Dashboard, Login, ServiceManager, Menüs, Views, Dialog, Tabs, PdvmInputControl, DateTimePicker, JsonEditor, Layouts u. a.). Legacy-Variablen und `.dark`-Regeln entfernt, redundante `:root[data-theme="dark"]`-Overrides gelöscht, weil die Tokens den Modus selbst abbilden.
- Guard: `backend/test_frontend_theme_guard.py` (5 Tests: keine Farbliterale in CSS und TS/TSX, keine Legacy-Variablen, kein `.dark`, `--block-*` nur aus dem Schema).
- Verifikation: Backend 113 bestanden (4 bekannte Fehlschläge unverändert), `tsc --noEmit` und `vite build` ok, Login-Seite im Browser geprüft.

Sichtbare Änderungen (Absicht): Fehlerboxen sind jetzt getönt statt voll rot (`.menu-error`); Einstellungs-Panel der View nutzt den Panel-Hintergrund (`background-secondary`); Login und Karten nutzen die Primärfarbe des Themes statt festem Violett; Login-Button-Text ist `--color-text-inverse`.
Hinweis: `components/Login.css` wird von `Login.tsx` nicht verwendet (Inline-Styles); die Datei ist toter Code und kann entfernt werden.
Offen für P6: `meta_opacity` in den Tabs ist fest `0.85` (kein Schema-Token); neutrale/deaktivierte Button-Hintergründe nutzen `--color-text-secondary`/`--color-text-disabled` als Ersatz; weißer Text auf Orange bleibt zu kontrastarm (in P6 behoben).

## 8. Stand P3 (09.11.2026)
Umgesetzt:
- Neue `PdvmInputControl`-Typen `color` (Farbfeld + Hex-Feld + Kontrast-Badge gegen eine Gegenfarbe), `css_length`, `css_border` (Breite/Stil/Farbe), `font_family` (Auswahl + eigene Eingabe), `theme_preview` (Live-Vorschau, Tokens nur im Container). Leerer Wert = "nicht überschrieben". Bausteine: `components/common/PdvmThemeInputs.tsx`, `PdvmThemePreview.tsx`, `utils/themeTokens.ts` (Validierung + WCAG, Spiegel des Servers), `utils/themeVars.ts` (Variablennamen, auch vom `ThemeProvider` genutzt). Typ-Mapper in `PdvmInputControl` und `PdvmDialogPage` kennen die Typen; Konfiguration über `resolved_configs.theme_token`.
- Backend: `theme_schema` ergänzt um deutsche Beschriftungen (`GROUP_LABELS`, `PROP_LABELS`, `token_label`), `CONTROL_TYPE_BY_TOKEN_TYPE` und `contrast_partners`; `GET /api/layout/catalog` liefert jetzt je Gruppe `label` + `tokens` mit `label`, `control_type`, `contrast_against`, `options`.
- Tests: Katalogvollständigkeit (jeder Token hat Label und gültigen Control-Typ, Kontrastpartner existieren), Guard ergänzt um die Markierung `guard-allow-color` für begründete Einzelfälle (natives Farbfeld braucht einen Hex-Startwert).
- Verifiziert im Browser mit einer temporären Testseite (inzwischen gelöscht): Farbe/Länge/Rahmen/Schrift/Vorschau rendern, Eingabe `12px` wird übernommen, ungültige Startwerte zeigen eine Meldung, Kontrast-Badge zeigt `2.16:1 < 4.5` für Weiß auf `#ff9800`.
- Doku: `PDVM_EDIT_CONTROL_SPEC.md` Abschnitt 8, `THEMING_SYSTEM.md` Abschnitt 5.10.

## 9. Stand P4 (09.11.2026)
Entscheidung: Die Rolle **`overlay`** in `asy_benutzer.PERMISSIONS.ROLES` berechtigt zum Ändern der Overlays und Theme-Einstellungen des Mandanten (unabhängig von `admin`; im Bestand bei `Norbert Peters` und `admin@super.de` eingetragen).

Umgesetzt:
- Backend: `security.has_overlay_rights` / `require_overlay_user`; `theme_service` mit `validate_overlay_payload` (strikt, alle Fehler), `validate_user_edit_patterns`, `user_edit_presets`, `compose_base`, `list_variants`, `ThemeValidationError`; `PdvmCentralSystemsteuerung.get_theme_editor_state`, `save_mandant_theme_overlay`, `save_mandant_theme_config`, `save_user_theme_settings` (alle Schreibzugriffe über `central_write_service`, Updates mit `expected_snapshot_daten`); Router `GET /editor/{scope}`, `PUT /overlay/mandant`, `PUT /settings/mandant`, `PUT /settings/user` (422 mit Fehlerliste, 409 bei Schreibkonflikt, 403 ohne Rolle).
- Frontend: Seite `/design` (`ThemeEditorPage`) mit Tabs "Mein Design" / "Mandant", Modus Hell/Dunkel, Suche, Gruppen mit `PdvmInputControl` je Token, Live-Vorschau, Kontrast-Warnung, Verwerfen/Speichern, Bestätigungsdialog (`PdvmDialogModal`); Link im Header. Nach dem Speichern wird das Theme neu aufgelöst.
- Tests: `backend/test_theme_editor.py` (Rolle, Presets, strikte Prüfung, Editor-Zustand, alle drei Schreibwege mit Create/Update-Pfad, Router-Rechte und Fehlerabbildung). Integrationsprüfung gegen die Entwicklungs-DB (Mandant "Filiale Test 1", `admin@super.de`): Overlay anlegen und aktualisieren, Mandanten-Config schreiben, Benutzer-Overlay schreiben, nicht freigegebenes Token wird abgelehnt, anschließend vollständig zurückgesetzt (Overlay-Zeile gelöscht, Config wiederhergestellt).
- Browser-Prüfung der Seite mit einer temporären Testseite und echten Katalog-/Editordaten (inzwischen gelöscht): Rendering, Eingabe, Dirty-Zustand, Payload des Speicherns (`PUT /layout/settings/user` mit `overlay.light.color.primary-500`), Mandanten-Tab mit Freigabe-Auswahl.

Hinweise:
- Die Rolle steht in `asy_benutzer` (nicht `msy_benutzer`); es gibt keinen Benutzer `admin@example.com`, eingetragen ist sie bei `admin@super.de`.
- Das Frontend entscheidet über den Mandanten-Tab anhand `can_edit_overlay` aus der Serverantwort (die lokalen Rollen im `AuthContext` lesen `PERMISSIONS.ROLES` nicht); die Serverprüfung ist maßgeblich.
- Der Login-Fluss selbst ist nicht im Browser getestet (Passwort unbekannt).

## 10. Stand P5 (09.11.2026)
Die Startliste der Varianten ist bewusst klein und leicht erweiterbar (siehe `THEMING_SYSTEM.md` Abschnitt 8): Kopfzeile `standard|kompakt`, Navigation `standard|schmal|breit`, Dichte `standard|kompakt|luftig`, Formulare `standard|flach|label-links`, Tabellen `standard|zebra|linien`.

Umgesetzt:
- Backend: `layout_schema.py` (Katalog, Validierung, Auflösung, Verfügbarkeit); `PdvmCentralSystemsteuerung` löst `layout` in `resolve_active_theme` auf, liefert `layout` im Editor-Zustand und speichert `LAYOUT_DEFAULT`/`LAYOUT_ALLOWED` (Mandant, Rolle `overlay`, in `asy_mandanten.CONFIG`) bzw. `LAYOUT_CHOICE` (Benutzer, nur freigegeben, in `msy_systemsteuerung`); Router-Bodies erweitert.
- Frontend: `variants.css` (Regeln je Variante über `:root[data-layout-*]`), `--density-*` in `variables.css` (genutzt von `PdvmInputControl` und den View-Tabellenzellen), `utils/layoutAttributes.ts`, `ThemeProvider` setzt die Attribute (und räumt beim Logout auf), Editor-Abschnitt "Layout" mit sofortiger Vorschau.
- Tests: `backend/test_layout_schema.py` (Katalog, Validierung, Priorität/Freigabe, Editor-Zustand, Schreibwege) und ein Guard-Test, der Katalog und `variants.css` abgleicht. Gesamtstand Backend: 133 bestanden (4 bekannte Fehlschläge), `tsc` und `vite build` ok.
- Browser-Prüfung mit temporärer Testseite und echten Daten (inzwischen gelöscht): Attribute auf `<html>`, kompakte Kopfzeile, Vorschau von Dichte/Formular/Tabelle beim Umschalten, Mandanten-Abschnitt.

Nicht enthalten: Die Menüstruktur selbst (Gruppen `GRUND`/`VERTIKAL`) bleibt unverändert (Regel 2.2); die Varianten ändern nur Maße und Darstellung. Eine Variante "ohne Seitenleiste" gibt es bewusst nicht.

## 11. Stand P6 (10.11.2026)
Entscheidung: Schlechter Kontrast wird **nicht gespeichert**, damit immer alles lesbar bleibt; stattdessen bietet das System die nächstgelegene konforme Farbe an. Die Regeln stehen in `THEMING_SYSTEM.md` Abschnitt 9.

Umgesetzt:
- Backend: `theme_color.py` (Farbrechnung, `suggest_compliant_color`: ändert nur die Helligkeit in OKLab, Farbton und Sättigung bleiben); 17 Pflichtpaare (seit dem Nachtrag zur Stichtagsleiste 21) in `theme_schema.CONTRAST_PAIRS` samt CSS-Fallbackketten (`CONTRAST_FALLBACKS`); `theme_service`: `contrast_violations`, `enforce_contrast`, `contrast_errors`, `repair_contrast`. `save_mandant_theme_overlay` und `save_user_theme_settings` lehnen Verstöße mit 422 ab (`detail.errors` und `detail.contrast` mit Vorschlägen). Der Resolver ignoriert Benutzer-Tokens, die den Kontrast verletzen (mit Warnung).
- Frontend: `utils/themeColor.ts` (Spiegel mit identischen Ergebnissen, an 12 Vektoren gegen Python geprüft), `utils/themeContrastPairs.ts`; `PdvmColorInput` zeigt „Vorschlag übernehmen“; im Editor sind Speichern gesperrt, Einzel- und „Alle Vorschläge übernehmen“ verfügbar; geerbte Verstöße des Pakets werden nur als Hinweis gezeigt.
- Datenreparatur: `backend/tools/fix_theme_contrast_v1.py` (Dry-Run, `--apply --confirm-backup`, Snapshot in `backend/reports/`, Bericht in `docs/reports/`). Angewendet am 10.11.2026 auf 6 Paketzeilen (Orange/Blue/Green in `sys_layout`, je eine Kopie in `filale_test_1`, `pdvm_standard`, `mandant`); danach meldet der Dry-Run keine Verstöße mehr. Der Reparaturalgorithmus bevorzugt Textfarben (Markenfarben bleiben), Hintergrundänderungen werden mit Faktor 4 bestraft (`BG_PENALTY`).
- Tests: `backend/test_theme_color.py` (Referenzvektoren, Verstoß-Erkennung, Fallbackkette, Resolver, Reparatur, Katalog), ergänzt in `test_theme_editor.py` (Router 422 mit `contrast`, Benutzer-Speichern blockiert). Gesamtstand Backend: 153 bestanden (4 bekannte Fehlschläge), `tsc` und `vite build` ok.

Bewusst nicht umgesetzt: Berechnete „on“-Farben und Skalen (`primary-50..900`) aus wenigen Basisfarben; die Pakete behalten ihre expliziten Werte.

Nachtrag (Dark-Mode-Defaults, 10.11.2026): Die Prüfung der Dunkel-Defaults ergab, dass Paare mit Rohschlüsseln wie `text-on_tertiary` übersehen wurden (Fehler in `theme_service._lookup`, behoben, mit Test). Dadurch waren in den Dunkel-Varianten `text-on-secondary`/`text-on-tertiary` (1,1 bis 1,3:1) und im Hellmodus von Blue/Green `text-on-secondary` unlesbar. Ein zweiter Reparaturlauf hat 6 Paketzeilen korrigiert. Die CSS-Dunkel-Defaults bestanden schon; die Hell-Defaults (`--color-text-primary`, `-on-primary`, `-on-secondary`, `-inverse`) sind angepasst. Alle Mandanten mit Paket: Hell und Dunkel ohne Verstöße. Die ungenutzte `Login.css` wurde gelöscht.

## 12. Stand P7 (10.11.2026)
Dokumentation abgeschlossen: `THEMING_SYSTEM.md` beschreibt in den Abschnitten 1 bis 4 jetzt das aktuelle Modell (statt `--comp-*`/Komponenten-Mapping), Fallbacks der Block-Tabellen entsprechen dem CSS, Abschnitt 9 behandelt den Kontrast; `ARCHITECTURE_RULES.md` Regel 4.2 enthält die Guard-, Schema-, Schreib- und Kontrastregeln; `PDVM_EDIT_CONTROL_SPEC.md` Abschnitt 8 nennt den Kontrast-Vorschlag im `color`-Control. Keine Codeänderung.

Nachtrag (Stichtagsleiste und Datum/Zeit-Widget, 10.11.2026): Im Dunkelmodus war der Kontrast in der Leiste schlecht und nicht einstellbar. Ursachen und Maßnahmen:
- Die Leiste überschrieb lokal `--color-text-primary/-secondary` mit der Stichtag-Textfarbe; das erbten Eingabefeld und Popover des Pickers, deren Flächen aber aus anderen Tokens kamen (dunkler Text auf dunklem Feld). Die Überschreibung ist entfernt, Beschriftung/Wert/Titel erhalten die Farbe direkt.
- Fehlende Bereiche: neu `block_stichtag_std.field_bg_color|field_text_color` (Feld und „Jetzt“-Button der Leiste) und der Block `block_pic_popover` (Auswahlfenster, auch für alle `PdvmInputControl`-Datumsfelder). 4 neue Pflichtpaare (jetzt 21), Fallbackketten wie im CSS, die Editor-Vorschau zeigt Stichtagsleiste und Popover.
- Datenfehler: `block_stichtag_std.text_color = "000000"` (ohne `#`) im Orange-Paket (Dunkel) machte die Textfarbe ungültig. Der Resolver verwirft ungültige Paketwerte jetzt mit Warnung (`sanitize_package_variant`); das Reparatur-Tool ergänzt fehlende `#` und meldet nicht behebbare Werte; 2 Zeilen korrigiert.
- Native Datums-/Zeitfelder folgen dem Modus (`color-scheme` in `variables.css`; Kalendersymbol im Dunkelmodus sichtbar).
- „Jetzt“: Der Picker zeigt den Button in allen Modi (setzt Datum und Uhrzeit des Entwurfs). Zusätzlich setzt ein „Jetzt“-Button in der Stichtagsleiste den Stichtag sofort.
- Bereinigung im Picker: kein `alert()` mehr (Hinweis im Popover), keine Inline-Farbe, Klassen `.pdvm-btn*` → `.pdvm-datetime-btn*`, ungenutzte Backdrop-Regel entfernt, Hover ändert die Flächenfarbe nicht mehr (kein ungeprüftes Farbpaar).
- Doku: `THEMING_SYSTEM.md` (5.2/5.4/5.9, 9), `PDVM_DATETIME_SPEC.md` (3.2.2, 3.2.3, 3.2.5, 4.3).
- Beobachtung: Unter 1024 px Fensterbreite blendet `header.css` die Stichtagsleiste aus (bestehende Responsive-Regel, nicht geändert).

Nachtrag (Fehlermeldung im Dunkelmodus, 10.11.2026): Die Meldung im Content-Bereich (`.menu-error`) war schlecht lesbar. Ursachen: (1) die Status-Hintergründe waren transparent und lagen über einem Verlauf mit `--color-primary-50`, der im Dunkelmodus hell bleibt; (2) dieselbe helle Stufe im Logo-Verlauf. Maßnahmen: deckende Status-Hintergründe, Verläufe per `color-mix` aus `--color-primary-500` (dunkel bleibt dunkel), aktive Menüpunkte der Fallback-Navigation und `::selection` über `--state-selected` bzw. transparente Mischung, Logo-Text `--color-text-primary`. Zusätzlich: Login-Link/Demo-Button, „Zurück“-Link der Tabellenansicht und DB-Name im Mandanten-Setup nutzten `--color-primary-500` als Textfarbe (Orange auf Weiß 2,2:1) und verwenden jetzt `--color-text-on-primary`. Zwei neue Guard-Tests verhindern Markenfarbe als Text und helle Stufen 50 bis 200 als Fläche.

## 13. Abweichungen vom ersten Vorschlag
- **A) Schema im Code statt in 555/666:** Die Basissätze 000/555/666 sind laut Regel 1.11/1.12 manuell gepflegt und für Migrationen tabu. Das Token-Schema liegt daher in `theme_schema.py`. Eine Ablage in `sys_layout` 555/666 ist später mit ausdrücklicher Freigabe möglich (`seed_base_records.py --allow-reserved-changes`).
- **B) Paket-Kopie bleibt in `msy_layout`:** Updates der Pakete laufen über den Mandanten-DB-Update-Mechanismus (Regel 1.20). Das Overlay ist eine eigene Zeile; Zeilen ohne `ROOT.LAYER = "OVERLAY"` (Paket-Kopien) werden vom Overlay-Laden ignoriert.
- **C) Kein System-Modus:** `THEME_DEFAULT_MODE` kennt vorerst nur `light`/`dark`.
- **D) Kontrast zunächst nur als Bericht (ersetzt durch P6):** In P1 meldete der Resolver Verstöße nur. Seit P6 werden sie beim Speichern abgelehnt (siehe Abschnitt 11).
- **E) Controls aus dem Schema statt `sys_control_dict`-Zeilen (P3):** Die Variantengruppe des Themes ist zur Laufzeit variabel (`light`, `dark`, `Orange_Light` ...) und die Token-Tiefe (`Gruppe.Block.Token`) passt nicht auf das statische `GRUPPE`/`FELD`-Modell der Frames; ca. 190 Control-Zeilen wären zudem eine zweite, driftende Quelle neben `theme_schema.py`. Der Katalog erzeugt die Control-Definitionen zur Laufzeit; Editoren nutzen `PdvmInputControl` direkt (Regel 2.14 bleibt erfüllt). Ein späterer Wechsel auf Dict-Zeilen bräuchte laut Regel 1.10a zuerst die Aufnahme neuer Eigenschaften ins Muttercontrol.
- **G) Strukturkatalog im Code statt in `sys_layout_struktur` (P5):** Eine Variante ist nur wirksam, wenn das CSS sie kennt; eine DB-Tabelle könnte keine neue Variante "erfinden" und bräuchte zusätzlich Basissätze 000/555/666, Tabellenanlage in allen Umgebungen und einen Pflegeweg. Der Katalog liegt daher wie das Token-Schema in `layout_schema.py`; in der Datenbank stehen die Entscheidungen (Mandanten-Vorgabe, Freigaben, Benutzerwahl). Ein Test hält Katalog und CSS synchron.
- **F) Kein Editor für das Theme-Paket (P4):** Das Paket liegt als Kopie je Mandant in `msy_layout` und global in `sys_layout`; ein Schreibweg müsste beide Ebenen und die Mandanten-Updates (Regel 1.20) abstimmen. Pakete werden weiter über den bestehenden JSON-Dialog gepflegt; der Editor ändert nur Overlays und Einstellungen.

## 14. Offene Punkte
- Rechtekonzept steht (Rolle `overlay`, P4). Offen: Pflege von `USER_THEME_EDIT`, `THEME_DEFAULT_MODE`, `LAYOUT_*` auch im Mandanten-Dialog (aktuell nur im Design-Editor `/design`).
- Migration bestehender `msy_layout`-Paketkopien in Mandanten-DBs bleibt unverändert; Aufräumen ist nicht nötig.
- Weitere Layout-Varianten (z. B. Menü oben statt Seitenleiste) wären eine Änderung der Menüstruktur und brauchen eine Entscheidung zu Regel 2.2.
- Kontrast: Standard-Themes sind repariert (P6). Neue oder eingespielte Pakete mit `tools\fix_theme_contrast_v1.py` prüfen (Dry-Run).
- Die Mandanten `filiale_test_2` und `ganz_neu1` verweisen auf ein Paket (`THEME_GUID`), haben aber keine Kopie in `msy_layout`; sie laufen auf den CSS-Defaults. Die Kopie wird über den Mandanten-DB-Update-Mechanismus (Regel 1.20) angelegt.

## 15. Verifikation (wiederholbar)
```powershell
cd backend
$env:PYTHONUTF8 = 1
..\.venv\Scripts\python.exe -m pytest test_theme_color.py test_theme_service.py test_theme_editor.py test_layout_schema.py test_frontend_theme_guard.py test_architecture_guard.py test_router_sql_free.py -q
..\.venv\Scripts\python.exe tools\fix_mandant_theme_config_v1.py   # Dry-Run, erwartet: 0 Mandanten
..\.venv\Scripts\python.exe tools\fix_theme_contrast_v1.py          # Dry-Run, erwartet: keine Kontrastverstoesse
cd ..\frontend
npx tsc --noEmit   # mit dem npm/Node-Setup aus SYSTEM_STARTUP_GUIDE.md
```
