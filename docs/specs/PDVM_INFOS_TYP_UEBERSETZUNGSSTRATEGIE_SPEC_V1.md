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
