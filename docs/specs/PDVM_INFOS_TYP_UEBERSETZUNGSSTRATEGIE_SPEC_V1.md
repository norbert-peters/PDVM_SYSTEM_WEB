# PDVM Infos-Typ Uebersetzungsstrategie V1

Status: Entscheidungs-Spezifikation (Merker)  
Datum: 2026-05-18
Scope: Tabellentyp infos mit Starttabellen sys_beschreibungen und sys_dropdowndaten

## 1. Ausgangslage

Fuer den Tabellentyp infos soll die Datenstruktur langfristig stabil und sprachfaehig sein.
Betroffene Inhalte:
1. Dropdown-Werte
2. Beschreibungen
3. Hilfe-Texte
4. Label

Starttabellen:
1. sys_beschreibungen
2. sys_dropdowndaten

## 2. Machbarkeitspruefung gesteuerte Uebersetzung

Frage: Kann das System bei Browser-Sprache DE eine englische/italienische Darstellung gesteuert liefern?

Antwort: Ja, ist machbar.

Technisch vorhanden im Ist-Stand:
1. Sprachparameter in API-Endpunkten fuer Texte und Dropdowns.
2. Sprachfallback ueber DEFAULT_LANGUAGE.
3. Backend-Services fuer sprachaufgeloeste Daten (systemdaten/dropdown).

Bewertung Browser-Auto-Uebersetzung allein:
1. Positiv: Schnell, wenig Initialaufwand.
2. Negativ: Nicht deterministisch, keine Terminologie-Kontrolle, schwierig fuer fachliche Konsistenz.

Entscheidungsempfehlung:
1. Gesteuerte Uebersetzung im System als Primarmodus.
2. Browser-Uebersetzung nur optionaler Notfall-/Komfortfallback, nicht fachlich fuehrend.

## 3. Zielprinzip fuer infos-Tabellen

1. Sprache ist Laufzeitparameter, nicht Strukturtreiber.
2. Datensaetze enthalten stabile fachliche Schluessel.
3. Sprachtexte werden je Schluessel als Sprachmapping gefuehrt.
4. Fehlende Sprache faellt deterministisch auf DEFAULT_LANGUAGE zurueck.

## 4. Strukturtyp infos (Zielbild)

## 4.1 555 fuer infos

555 enthaelt:
1. ROOT (inkl. SELF* und TABLE sowie sprachrelevante Meta-Felder)
2. Leere Fachgruppen

Beispielgruppen:
1. DATAS
2. TABLE_INFO

Wichtig:
1. Keine sprachspezifischen Top-Level-Gruppen im 555.

## 4.2 666 fuer infos

666 enthaelt genau:
1. ROOT
2. TEMPLATES

In TEMPLATES liegen sprachfaehige Vorlagen je Fachgruppe.

## 4.3 Datenmodell fuer Eintraege

Beispiel fuer Text/Label/Hilfe:
{
  "key": "MENU.FILE.SAVE",
  "type": "label",
  "values": {
    "DE-DE": "Speichern",
    "EN-US": "Save",
    "IT-IT": "Salva"
  }
}

Beispiel fuer Dropdown-Option:
{
  "field": "anrede",
  "options": [
    {
      "key": "1",
      "values": {
        "DE-DE": "Herr",
        "EN-US": "Mr",
        "IT-IT": "Signor"
      }
    }
  ]
}

## 5. Uebersetzungsmodi

## 5.1 Modus MANUAL (Standard fuer Fachsicherheit)
1. Sprachtexte werden fachlich gepflegt.
2. Voll kontrollierte Terminologie.

## 5.2 Modus MACHINE_ASSISTED
1. Basistext in DEFAULT_LANGUAGE.
2. Zielsprachen werden maschinell vorbefuellt.
3. Fachliche Freigabe/Review bleibt Pflicht.

## 5.3 Modus BROWSER_FALLBACK (optional)
1. Nur Anzeige-Fallback, wenn keine gepflegte Sprache verfuegbar ist.
2. Nicht als kanonische Datenquelle verwenden.

## 6. Entscheidungsrahmen fuer Datenstruktur

Vor finaler infos-Struktur sind folgende Punkte zu entscheiden:
1. Welche Sprachen sind offiziell unterstuetzt (SUPPORTED_LANGUAGES)?
2. Welche Inhalte sind pflicht-uebersetzt (Label/Hilfe/Dropdown/Text)?
3. Welcher Uebersetzungsmodus gilt je Tabelle (MANUAL/MACHINE_ASSISTED)?
4. Wie wird Freigabeversion je Sprache dokumentiert?

## 7. Konkreter Start fuer sys_beschreibungen und sys_dropdowndaten

1. Beide Tabellen als Typ infos in sys_systemdaten markieren.
2. 555/666 dieser Tabellen auf infos-Zielbild normalisieren.
3. Vorhandene sprachbezogene Bestandsdaten in values-Mappings ueberfuehren.
4. API-Aufloesung vereinheitlichen: angeforderte Sprache -> Fallback DEFAULT_LANGUAGE.

## 8. Entscheidung

Die Einfuehrung einer gesteuerten Uebersetzung ist technisch moeglich und fuer stabile Datenstrukturen sinnvoll.

Empfohlen:
1. infos-Typ als eigener Strukturtyp festlegen.
2. Gesteuerte Uebersetzung als Standard definieren.
3. Browser-Autouebertragung nur als optionalen Fallback behandeln.
4. Sprachbezogene TabellenTypen trennen nach Dropdown/Text/Uebersetzung (Details siehe PDVM_TABELLENTYPEN_UND_I18N_STRUKTUR_SPEC_V1.md).

## 9. Umsetzungsstand (2026-05-20)

Folgende Schritte sind bereits technisch umgesetzt und validiert:
1. Phase D Migration auf values-Modell fuer infos-Tabellen.
2. sys_dropdowndaten: ein Dropdown pro Datensatz (Split bei Mehrfachfeldern), DE-DE + EN-US in values.
3. sys_beschreibungen: Umstellung auf ROOT + TEXTS mit values je Sprache.
4. Runtime-Dropdown-Aufloesung erweitert auf neues OPTIONS-Modell (mit Legacy-Fallback).

Folgende Hartergebnisse wurden validiert:
1. Phase D Apply: rows_scanned=10, rows_updated=8, rows_inserted=6, rows_split_created=6.
2. Phase E Retarget Frame/View: rows_scanned=29, rows_updated=1, ref_updates=1, unresolved_refs=0.
3. Strict Integritaetscheck: legacy_ref_count=0 (keine Legacy-Referenzen auf alte Quellen).

Operativer Hinweis:
1. Für Retargeting-Nachweise und UID-Mapping gilt der Apply-Report als technische Quelle.
2. Neue Splits muessen weiterhin ueber Mapping + strict-Validierung in Frame/View nachgezogen werden.

## 10. Offene Punkte Checkliste

Fuer die sequentielle Abarbeitung der offenen Entscheidungs- und Governance-Punkte gilt:
1. docs/specs/PDVM_STRUKTURMIGRATION_INFOS_OFFENE_PUNKTE_CHECKLISTE_V1.md

## 11. Punkt 6 Umsetzungsstand (SUPPORTED_LANGUAGES + DEFAULT_LANGUAGE)

Status: umgesetzt am 2026-05-20.

Finale V1-Definition:
1. DEFAULT_LANGUAGE = DE-DE
2. SUPPORTED_LANGUAGES = [DE-DE, EN-US, IT-IT]

Technische Verankerung:
1. backend/config/i18n_policy_v1.json
2. backend/app/core/i18n_policy.py
3. backend/app/core/dropdown_service.py (zentrale Normalisierung)
4. backend/app/core/systemdaten_service.py (zentrale Normalisierung)

Alias-Normalisierung (Auszug):
1. US-EN -> EN-US
2. DEU -> DE-DE
3. ENG -> EN-US
4. ITA -> IT-IT

Nachweis:
1. backend/reports/phaseC_finalize_supported_languages_v1.json
2. observed normalized languages = [DE-DE, EN-US]
3. unsupported_observed_count = 0

## 12. Punkt 7 Umsetzungsstand (Pflicht-Uebersetzungsumfang)

Status: umgesetzt am 2026-05-20.

Verbindliche V1-Matrix je Inhaltstyp:
1. dropdown
  required: DE-DE, EN-US
  optional: IT-IT
2. label
  required: DE-DE, EN-US
  optional: IT-IT
3. hilfe
  required: DE-DE
  optional: EN-US, IT-IT
4. text
  required: DE-DE
  optional: EN-US, IT-IT

Technische Verankerung:
1. backend/config/i18n_required_translation_scope_v1.json
2. backend/tools/phaseC_define_required_translation_scope.py

Nachweis:
1. backend/reports/phaseC_define_required_translation_scope_v1.json
2. items_total = 58
3. items_with_missing_required = 0
4. required_scope_fully_covered = true

Hinweis zum Ist-Bestand:
1. Aktuell wurden im Report nur dropdown-Inhalte gezaehlt (58 Eintraege).
2. label/hilfe/text sind in der V1-Matrix bereits verbindlich definiert und gelten fuer kuenftige Inhalte.

## 13. Punkt 8 Umsetzungsstand (Uebersetzungsmodus je Tabelle)

Status: umgesetzt am 2026-05-20.

Verbindliche V1-Entscheidung je Tabelle:
1. sys_dropdowndaten -> MANUAL
  Review-Regel:
  Jede inhaltliche Aenderung an Dropdown-Werten erfordert Fachfreigabe vor produktiver Nutzung.
2. sys_beschreibungen -> MACHINE_ASSISTED
  Review-Regel:
  Machine-Assisted Vorbelegung ist erlaubt; produktive Verwendung nur nach fachlicher Freigabe (approved).

Technische Verankerung:
1. backend/config/i18n_translation_mode_per_table_v1.json
2. backend/tools/phaseC_define_translation_mode_per_table.py

Nachweis:
1. backend/reports/phaseC_define_translation_mode_per_table_v1.json
2. in_scope_tables_count = 2
3. assignments_count = 2
4. invalid_mode_count = 0
5. missing_review_rule_count = 0
6. tables_missing_count = 0
7. open_decisions_count = 0
8. decision_set_complete = true

## 14. Punkt 9 Umsetzungsstand (Freigabeversion je Sprache)

Status: umgesetzt am 2026-05-20.

Verbindliches minimales Freigabemodell V1:
1. Pflichtfelder je Spracheintrag:
  version, status, approved_by, approved_at
2. Statusmodell:
  new, machine, review, approved
3. Produktivregel:
  Nur status=approved ist produktiv gueltig.
4. Freigabepflicht:
  Bei status=approved muessen approved_by (nicht leer) und approved_at (ISO8601) gesetzt sein.
5. Versionsregel:
  version ist Pflicht und folgt Pattern ^v[0-9]+\\.[0-9]+\\.[0-9]+$.

Technische Verankerung:
1. backend/config/i18n_language_release_model_v1.json
2. backend/tools/phaseC_define_language_release_model.py

Nachweis:
1. backend/reports/phaseC_define_language_release_model_v1.json
2. items_total = 58
3. items_with_release_fields = 0
4. items_without_release_fields = 58
5. valid_release_state_count = 0
6. model_definition_complete = true
7. runtime_release_metadata_coverage = false

Hinweis:
1. Punkt 9 liefert die verbindliche Modell-Definition.
2. Die operative Einfuehrung im Laufzeitbestand (Metadata-Coverage) wird in den Folgeschritten adressiert.

## 15. Punkt 10 Umsetzungsstand (infos_translation Overlay)

Status: bewusst vertagt am 2026-05-20.

Entscheidung:
1. Das infos_translation Overlay wird in diesem Zyklus nicht eingefuehrt.

Begruendung:
1. Nach der grossen Migration ist der naechste priorisierte Schritt ein wiederholbares
  Mandanten-DB-Updateverfahren fuer den Transfer auf andere Mandantendatenbanken.
2. Fokus liegt zuerst auf Versionierung und gesteuerten Datenanpassungen in Ziel-Mandanten.

Nachfolge-Spezifikation:
1. docs/specs/PDVM_MANDANT_DB_UPDATE_VERSIONIERUNG_SPEC_V1.md
