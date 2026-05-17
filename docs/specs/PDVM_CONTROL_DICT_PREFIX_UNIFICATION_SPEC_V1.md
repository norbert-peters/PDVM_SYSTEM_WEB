# PDVM Control Dict Prefix Unification Spezifikation V1

Status: Festgelegt zur Umsetzung
Datum: 2026-05-16
Scope: Angleichung von sys_control_dict und Mandanten-Control-Dictionary, präfixgesteuertes Routing und Migrationsplan

## 1. Ziel und Nicht-Ziele

### 1.1 Ziel
Diese Spezifikation definiert ein konsistentes Modell, um:
- Steuerelemente für Felder/Eigenschaften in DB-Datensätzen zu beschreiben,
- diese Control-Definitionen in der DB zu bearbeiten,
- Tabellen nur über Präfix dem richtigen DB-Kontext zuzuordnen,
- unterschiedliche Dictionary-Tabellennamen zu entfernen,
- Historie und UI-Rendering stabil zu halten (UID-basiert),
- künftiges App-Onboarding in der Mandanten-DB parametrisch und maschinenfreundlich zu machen.

### 1.2 Nicht-Ziele
Diese Spezifikation ersetzt nicht das Central-Database-Gesetz, den Draft-Flow oder das History-Modell. Sie erweitert diese.

## 2. Architektur-Constraints (verbindlich)

Diese Spezifikation ist mit ARCHITECTURE_RULES ausgerichtet:
- kein direkter SQL-Zugriff im Router unter Umgehung der Business-Logik,
- Write-Pfad nur über central_write_service,
- Tabellen-Routing zentral in PdvmDatabase,
- Dictionary-Datensätze bleiben linear in der Datenform (ROOT + CONTROL),
- UID/LINK_UID-Regeln bleiben gültig.

Wichtige Konsequenz:
- eine fixe LINK_UID in sys_systemsteuerung für Tabellenmetadaten ist nicht kompatibel mit der aktuellen LINK_UID-Regel für sys_systemsteuerung (user_guid-gebunden).

## 3. Präfix-Modell (Zielbild)

### 3.1 Präfix-Klassen

Auth-DB:
- asy_ (Auth-Systemtabellen)

System-DB:
- sys_ (Systemtabellen)
- dev_ (Entwicklertabellen)

Mandanten-DB:
- msy_ (mandantenlokale Systemtabellen)
- tst_ (Testtabellen)
- applikationsspezifische Präfixe (zum Beispiel crm_, hrm_, pps_)

Regel:
- asy_ wird immer in der Auth-DB beschrieben.
- sys_ und dev_ werden immer in der System-DB beschrieben.
- msy_ und alle nicht-sys/dev/asy_ Applikationspräfixe werden immer in der Mandanten-DB beschrieben.

### 3.2 Warum msy_

Die aktuelle Überlappung von sys_ in beiden DB-Kontexten erzeugt Mehrdeutigkeit.
Durch Umstellung mandantenlokaler Systemtabellen von sys_ auf msy_ wird Lookup linear:
- Präfix -> DB-Kontext -> Metadatenquelle.

## 4. Vereinheitlichung der Dictionary-Tabellennamen

Aktuell:
- System-DB: sys_control_dict
- Mandanten-DB: sys_contr_dict_man bzw. msy_control_dict (legacy/rollout)

Ziel (ab Phase 7):
- genau eine kanonische Dictionary-Tabelle: sys_control_dict in der System-DB
- keine produktive Control-Dictionary-Tabelle mehr in Mandanten-DBs

Audit-Tabellen:
- keine separate sys_control_dict_audit/msy_control_dict_audit als Pflichtbestandteil
- Feldhistorie erfolgt ueber msy_feld_aenderungshistorie (bereits eingefuehrt)

Regel:
- Control-Definitionen sind systemweit zentral und von allen Mandanten lesbar.
- Mandantenspezifische Unterschiede werden nicht durch zweite Dictionary-Tabellen, sondern durch Ueberschreibungen in Frame/View-Kontexten abgebildet.

## 5. Modell für Tabellenmetadaten

### 5.1 Metadatenquelle in der System-DB

Verwendung von sys_systemdaten mit genau einem Satz pro Tabelle:
- gruppe: TABLE_META
- name: exakter Tabellenname
- link_uid: table_uid (stabile technische ID für diesen Metadatensatz)
- daten: Metadaten-Payload

### 5.2 Metadatenquelle in der Mandanten-DB

Keine fixe LINK_UID in sys_systemsteuerung (kollidiert mit Architekturregel 1.14).
Stattdessen eine der regelkonformen Optionen:
- bevorzugt: neue Tabelle msy_systemdaten mit gleichem Muster wie sys_systemdaten, oder
- alternativ: dedizierte msy_table_catalog Tabelle.

Entscheidung in dieser Spezifikation:
- Einführung von msy_systemdaten und Speicherung der Mandanten-Tabellenmetadaten dort mit einem Satz je Tabelle.

### 5.3 Metadaten-Payload (Minimum)

Beispiel für daten-Payload:
{
  "ROOT": {
    "TABLE": "tst_persondaten",
    "PREFIX": "tst_",
    "DOMAIN": "mandant",
    "CONTROL_DICT_TABLE": "sys_control_dict",
    "DICT_AUDIT_TABLE": "",
    "FRAME_DEFAULT_GUID": "...",
    "APP_KEY": "core",
    "IS_ACTIVE": true
  },
  "FIELDS": {
    "uid": {"type": "uuid", "group": "SYSTEM", "readonly": true},
    "name": {"type": "string", "group": "SYSTEM", "readonly": false}
  }
}

## 6. Control-Dict-Regeln (aktualisiert)

### 6.1 UID-Verwendung

- UI-Rendering referenziert immer die Control-UID.
- Änderungshistorie speichert die Feld-/Control-UID als stabilen Identifier.
- CONTROL.FIELD bleibt semantischer Feld-Identifier (uppercase).

### 6.2 Konvention fuer NAME und SELF_NAME

Verbindliche Regel (ab Phase 7):
- SQL-Name und ROOT.SELF_NAME entsprechen exakt dem Referenznamen ohne zusaetzlichen Tabellenpraefix.
- Beispiele: table, GEBURTSDATUM, read_only, LABEL
- CONTROL.LABEL bleibt die reine Anzeige-/Sprachbezeichnung.

Begruendung:
- Controls beschreiben nicht nur Tabellenfelder, sondern allgemein Eigenschaften (Properties + Felder).
- Ein universelles systemweites Control-Set ist linearer und einfacher wiederverwendbar.

### 6.3 Geltungsbereich und Ueberschreibung

Fuer Control-Dictionaries gilt:
- sys_control_dict enthaelt universelle Basis-Controls (systemweit).
- Ableitungen pro Tabelle/Modul/Use-Case erfolgen durch Ueberschreibungen in sys_framedaten/sys_viewdaten.
- UIDs bleiben die stabile Referenz im Rendering und in Beziehungen.

Prioritaetsregel bei Aufloesung:
1. Frame/View-Ueberschreibung (kontextspezifisch)
2. sys_control_dict (systemweite Basisdefinition)

Hinweis:
- Eine harte Bindung link_uid = table_uid fuer jeden Control-Satz ist in diesem Zielbild nicht mehr verpflichtend.

### 6.4 Entscheidung Name-vs-UID-Speicherung

Entscheidung:
- Hybrid-Modell behalten, kein UID-only.

Warum:
- UID-only erhöht Mapping-Aufwand bei Debugging und Migration.
- semantische Felder bleiben lesbar und wartbar.

Verbindlich:
- Referenzen zwischen Entitaeten: UID
- semantische Feld-/Property-Identitaet in Payload: CONTROL.FIELD (uppercase) bzw. entsprechender Referenzname

### 6.5 Eindeutigkeit ohne CONTROL_KEY und ohne harte DB-Sonder-Constraints

Festlegung:
- Es wird kein zusaetzlicher CONTROL_KEY als Pflichtfeld eingefuehrt.
- Es werden keine neuen harten DB-Unique-Sonder-Constraints nur fuer control_dict eingefuehrt.

Stattdessen:
- Eindeutigkeit und Konsistenz werden ueber Migrations-/Validierungswerkzeuge sichergestellt.
- Verstoesse (Duplikate, fehlende Controls, verwaiste Referenzen) werden durch Pflicht-Reports erkannt und bereinigt.

## 7. Runtime-Cache-Strategie für Dialog/Frame-Controls

Adressierte Frage: vorgelagerte Ablage aufgelöster Control-Definitionen für schnellere Dialog-Darstellung.

Entscheidung:
- kanonische Quelle bleibt in den Control-Dict-Tabellen,
- aufgelöste Control-Sets dürfen benutzer-/sessionnah gecacht werden,
- Cache-Invalidierung über modified_at-Fingerprint.

Empfohlene Ablage:
- user-scope Cache in sys_systemsteuerung mit link_uid=user_guid,
- Key-Muster: CACHE.CONTROL_DICT::<table>::<edit_type>::<frame_guid>
- Payload enthält source_modified_at_max.

Invalidierung:
- wenn max(modified_at) in Source-Dict/Frame > Cache-Stamp, wird Cache neu aufgebaut.

Das bleibt konform zu Architekturregel 1.14.

## 8. Präfixgesteuerter Routing-Algorithmus

Linearer Algorithmus (ohne feste Tabellen-Map):
1. Präfix aus Tabellenname extrahieren,
2. DB-Kontext routen:
  - asy_ -> Auth-DB
  - sys_/dev_ -> System-DB
  - msy_/tst_/app_* -> Mandanten-DB
3. Metadatenquelle auflösen:
  - Auth-DB -> asy_systemdaten (TABLE_META)
   - System-DB -> sys_systemdaten (TABLE_META)
   - Mandanten-DB -> msy_systemdaten (TABLE_META)
4. Control-Definitionen aus sys_control_dict laden (systemweit zentral).

Fallback-Policy:
- kein stiller Fallback in falsche DB.
- unbekanntes Präfix liefert expliziten Konfigurationsfehler.

## 9. Migrations- und Konsistenzplan (linear)

### Phase 0: Vorbereitung
- Vollbackup von auth/system/mandant-DBs,
- Schema-ändernde Writes einfrieren,
- aktuelles Präfix-Inventar exportieren.

Ergebnisartefakte (pflicht):
- Backup-Protokoll je DB-Kontext,
- Präfix-Inventarreport mit Tabellenliste,
- Migrations-Readiness-Liste (unklare/konfliktäre Tabellen).

### Phase 1: neue Präfixe einführen (auth + mandant)
- asy_* Tabellen in Auth-DB anlegen,
- msy_* Tabellen in Mandanten-DB anlegen,
- Daten aus alten mandantenlokalen sys_* Tabellen nach msy_* migrieren.

Mindestsatz auth rename/migrate:
- sys_benutzer -> asy_benutzer
- sys_mandanten -> asy_mandanten

Empfohlene auth-Metatabellen:
- asy_systemdaten
- asy_table_catalog (optional, wenn asy_systemdaten nicht reicht)

Mindestsatz zu rename/migrate:
- sys_systemsteuerung -> msy_systemsteuerung
- sys_anwendungsdaten -> msy_anwendungsdaten
- sys_security -> msy_security
- sys_error_log -> msy_error_log
- sys_error_acknowledgments -> msy_error_acknowledgments
- sys_contr_dict_man -> msy_control_dict
- sys_contr_dict_man_audit -> msy_control_dict_audit

Kompatibilitätsfenster:
- optional read-only Kompatibilitätsviews mit alten Namen,
- Entfernung nach Umstellung aller Caller.

### Phase 2: Metadaten-Katalog ausrollen
- sys_systemdaten TABLE_META-Sätze für alle sys_/dev_-Tabellen anlegen,
- msy_systemdaten TABLE_META-Sätze für alle msy_/tst_/app_*-Tabellen anlegen,
- stabile table_uid-Werte vergeben.

### Phase 3: Control-Dict normalisieren
- ROOT + CONTROL-only Payload erzwingen,
- FIELD uppercase erzwingen,
- name/SELF_NAME aus Referenzname ohne Tabellenpraefix erzwingen,
- universelle Basis-Controls in sys_control_dict konsolidieren.

### Phase 4: Routing umschalten
- statische Table-Map durch Präfix-Parser in PdvmDatabase ersetzen,
- temporäre Allowlist während Rollout,
- Logging bei unbekannten Präfixen.

### Phase 5: Cache aktivieren
- optionales Caching von Control-Sets in sys_systemsteuerung aktivieren,
- Invalidierung über modified_at-Fingerprint aktivieren,
- Hit-Rate und Stale-Rebuild-Zähler monitoren.

### Phase 6: Cleanup
- Kompatibilitätsviews/Aliase entfernen,
- Legacy-Pfade für sys_contr_dict_man entfernen,
- neue Namensregeln mit Validierungstests absichern.

### Phase 7: Universelles Control-Modell finalisieren (neu)
- sys_control_dict als einzige produktive Control-Quelle festschreiben,
- msy_control_dict/msy_control_dict_audit aus produktivem Pfad entfernen,
- Aufloesungsreihenfolge implementieren: Frame/View-Override vor sys_control_dict,
- bestehende Frame/View/Dialog-Verwendungen gegen sys_control_dict abgleichen,
- Pflichtreport erzeugen:
  - fehlende Controls,
  - doppelte Referenznamen,
  - verwaiste UID-Referenzen,
- optionales Bereinigungswerkzeug bereitstellen (auto-fix nur fuer sichere Faelle).

## 10. Datenkonsistenz-Checks (pflicht)

Checks nach Migration:
- jede Tabelle hat genau einen TABLE_META-Satz im korrekten Katalog,
- jeder Dictionary-Satz hat nur ROOT + CONTROL,
- jeder Dictionary-Satz hat CONTROL.FIELD uppercase,
- name und SELF_NAME entsprechen dem Referenznamen ohne zusaetzlichen Tabellenpraefix,
- History-Sätze lösen weiterhin auf Control-UID auf,
- Dialog-Rendering löst Controls ohne Legacy-Fallback auf.

Checks fuer Phase 7 zusaetzlich:
- sys_control_dict deckt alle in Frame/View/Dialog verwendeten Controls ab,
- jeder Referenzname ist in der aktiven Menge eindeutig,
- keine produktiven Reads/Writes mehr auf msy_control_dict/msy_control_dict_audit,
- feld_aenderungshistorie erfasst Control-Aenderungen vollstaendig.

## 11. Automatisierungsziel (Onboarding neuer Apps)

Zielmodell:
- neue App in Mandanten-DB wird über Präfix und Metadaten parametrisisiert,
- Dialoge/Views/Frames können aus TABLE_META + Control-Templates erzeugt werden.

Maschineller Erzeugungspfad:
1. App-Präfix registrieren,
2. Tabellenmetadaten in msy_systemdaten anlegen,
3. initiale sys_control_dict-Saetze aus Template-Set erzeugen,
4. Basis-Sätze in sys_dialogdaten/sys_viewdaten/sys_framedaten erzeugen,
5. in pdvm_edit zur manuellen Feinbearbeitung öffnen.

Damit wird manuelle Arbeit minimal und reproduzierbar.

## 12. Phase-7-Ergaenzungen aus Architektur-Review

Festlegungen aus dem Review:
1. Controls sind universell (nicht nur tabellenfeldbezogen), also sowohl fuer allgemeine Properties (z. B. table) als auch fuer Fachfelder (z. B. GEBURTSDATUM).
2. Basisdefinitionen liegen ausschliesslich zentral in sys_control_dict.
3. Unterschiede pro Tabelle/Modul/Use-Case werden im jeweiligen Frame/View-Kontext ueberschrieben.
4. Separate control_dict_audit-Tabellen sind nicht erforderlich, solange feld_aenderungshistorie den Aenderungspfad vollstaendig abdeckt.
5. Keine neue Sonderausnahme in ARCHITECTURE_RULES durch CONTROL_KEY oder harte control_dict-spezifische DB-Constraints.
6. Da der aktuelle Stand ein Entwicklungsdatenbestand ist, wird die Umstellung als vollstaendige strukturelle Bereinigung in Phase 7 umgesetzt.

## 13. Festlegungen (freigegeben)

1. Auth-Domain-Präfixe
- Keine Sonderbehandlung mehr für Auth-Tabellen.
- Auth-Präfix wird auf asy_ festgelegt.
- Zieltabellen: asy_benutzer, asy_mandanten.

2. Dauer des Kompatibilitätsfensters
- Festgelegt auf 1 Release-Zyklus mit Kompatibilitätsviews.

3. Schema von msy_systemdaten
- Immer PDVM-Standardtabellenform mit ROOT/TABLE_META-Payload.
- Gleiches gilt analog für asy_systemdaten und sys_systemdaten.

## 14. Empfohlene Umsetzungsreihenfolge

Empfohlene Reihenfolge:
1. Phase 0 und Phase 1 (Präfix-Split)
2. Phase 2 (Metadaten-Kataloge)
3. Phase 3 (Control-Dict-Normalisierung)
4. Phase 4 (Routing-Umschaltung)
5. Phase 5 und 6 (Cache und Cleanup)

Keine Phase darf für dieselbe Tabellenfamilie parallel zu einer anderen Phase laufen.
