# PDVM TabellenTypen und I18N Struktur V1

Status: Entscheidungs-Spezifikation  
Datum: 2026-05-19
Scope: Sprachbezogene Inhalte (Dropdown, Beschreibungen, Label, Tooltips, Titel, Header, Menuepunkte)

## 1. Kernfrage

Sollen sprachbezogene Inhalte in einem gemeinsamen Typ bleiben oder nach Strukturtyp getrennt werden?

## 2. Entscheidungsempfehlung

Ja, trennen.

Empfohlene Typen:
1. infos_dropdown
2. infos_text
3. infos_translation

Begruendung:
1. Unterschiedliche Struktur und Lebenszyklus von Dropdowns vs. UI-Texten.
2. Bessere Wartbarkeit, klarere Validierung, gezieltere Tools.
3. Uebersetzungsprozess kann separat gesteuert werden (manuell, machine-assisted, review).

## 3. Typdefinitionen

## 3.1 Typ infos_dropdown

Zweck:
1. Key-Value-Optionen fuer Fachfelder (z. B. Anrede, Status, Kategorien).

Strukturprinzip:
1. Stabiler fachlicher key.
2. values-Mapping je Sprache pro Option.

Beispiel:
{
  "field": "anrede",
  "options": [
    {
      "key": "herr",
      "values": {"DE-DE": "Herr", "EN-US": "Mr", "IT-IT": "Signore"}
    }
  ]
}

Starttabellen:
1. sys_dropdowndaten

## 3.2 Typ infos_text

Zweck:
1. Statische oder semistatische UI-Texte mit stabilem text_key.

Bereiche:
1. Label
2. Tooltip
3. Hilfe
4. Titel
5. Header
6. Menuepunkt-Texte

Strukturprinzip:
1. text_key als fachlich stabiler Identifier.
2. values-Mapping je Sprache.
3. Optional text_type (label, tooltip, help, title, header, menu).

Beispiel:
{
  "text_key": "MENU.FILE.SAVE",
  "text_type": "menu",
  "values": {"DE-DE": "Speichern", "EN-US": "Save", "IT-IT": "Salva"}
}

Starttabellen:
1. sys_beschreibungen

## 3.3 Typ infos_translation

Zweck:
1. Uebersetzungssteuerung, Qualitaet und Review-Lifecycle.
2. Trennung zwischen Quelltext und Zielsprachenfreigabe.

Inhalt (Meta-Ebene):
1. source_language
2. target_language
3. source_hash
4. machine_value
5. reviewed_value
6. status (new, machine, review, approved)
7. approved_by / approved_at

Wichtig:
1. infos_translation ist kein Ersatz fuer infos_text/infos_dropdown.
2. Es ist ein Overlay/Workflow-Typ fuer Uebersetzungsmanagement.

## 4. Brauchen wir eigene Tabellen?

Empfehlung:
1. Ja, fuer saubere Trennung mittel- bis langfristig.

Minimaler Start (ohne Big Bang):
1. Bestehende Tabellen beibehalten und per TabellenType klassifizieren.
2. In sys_systemdaten je Tabelle TABLE_TYPE setzen.
3. Erst danach gezielt neue Tabelle fuer infos_translation einfuehren.

Optionales Zielbild fuer neue Tabellen:
1. sys_i18n_text
2. sys_i18n_dropdown
3. sys_i18n_translation

## 5. Soll vor Darstellung uebersetzt werden?

Antwort:
1. Ja, kontrolliert im Backend-Resolver.

Aufloesungsreihenfolge:
1. requested_language
2. DEFAULT_LANGUAGE
3. definierter Fallback (z. B. EN-US oder DE-DE)

Browser-Autouebertragung:
1. nur optionaler Darstellungsfallback, nicht fachliche Quelle.

## 6. Zuordnung vorhandener Tabellen (V1)

1. sys_dropdowndaten -> infos_dropdown
2. sys_beschreibungen -> infos_text
3. sys_systemdaten (ausgewaehlte Bereiche) -> infos_text oder infos_translation je Datensatzbereich

## 7. Auswirkungen auf andere TabellenTypen

1. Ja, weitere TabellenTypen muessen festgelegt werden.
2. Vorgehen: erst Taxonomie, dann Struktur je Typ.

Vorschlag initiale Obertypen:
1. infos_dropdown
2. infos_text
3. infos_translation
4. config
5. master_data
6. process
7. audit_history

## 8. Empfohlene Reihenfolge

1. Phase B.1: TabellenType-Taxonomie finalisieren und in sys_systemdaten persistieren.
2. Phase B.2: infos_dropdown und infos_text strukturseitig finalisieren.
3. Phase B.3: infos_translation als Workflow-Overlay einführen.
4. Phase B.4: Resolver/API vereinheitlichen fuer alle sprachbezogenen UI-Inhalte.

## 9. Entscheidungsstatus

Diese Spezifikation empfiehlt die Trennung in drei sprachbezogene TabellenTypen und die schrittweise Einfuehrung mit minimal-invasivem Start.
