# PDVM Template 555/666 Strukturmigration V1

Status: Entwurf zur fachlichen Abstimmung  
Datum: 2026-05-18  
Scope: Einheitlicher Neu-/Aenderungs-/Loeschablauf und strukturgefuehrte daten-Bildung pro Tabelle auf Basis 555/666

## 1. Zielbild

Diese Spezifikation beschreibt ein einheitliches Modell, damit:
1. alle Tabellen (so weit moeglich) denselben Neu-, Aenderungs- und Loeschablauf verwenden,
2. jede Tabelle eine klar definierte, maschinell pflegbare daten-Struktur hat,
3. die Struktur ausschliesslich aus den Template-Saetzen 555 und 666 abgeleitet wird,
4. Struktur-Aenderungen kontrolliert in Bestandsdaten uebernommen werden,
5. entfallende Werte additiv in backup_daten erhalten bleiben.

## 2. Grundannahme: macht das Sinn?

Kurzbewertung: Ja, das Modell ist sinnvoll.

Begruendung:
1. Es reduziert Sonderlogik und erleichtert den Betrieb.
2. Es macht Struktur-Aenderungen zentral steuerbar.
3. Es verbessert Konsistenz, Testbarkeit und Migrationen.
4. Es passt zum bestehenden Template/Delta-Ansatz.

Wichtige Einschraenkung:
1. Es braucht ein klares Ausnahmeregister fuer Tabellen, die nicht voll in das Muster passen.

## 3. Verbindliches Strukturmodell

## 3.1 555-Satz (Struktur-Container)

UID: 55555555-5555-5555-5555-555555555555

Pflichtinhalt in daten:
1. ROOT: Eigenschaften/Metadaten (Strukturfuehrung).
2. Weitere fachliche Gruppen nur als Strukturhuelle, ohne Inhalte, z. B. {}.

Regel:
1. 555 beschreibt, welche Gruppen in einem Datensatz strukturell existieren duerfen/muessen.
2. 555 besteht nach Normalisierung nur aus:
- ROOT (Standard-ROOT der Tabelle)
- leeren Gruppenobjekten {} fuer alle fachlichen Gruppen der Tabelle.

Hinweis Standard-ROOT:
1. Enthält immer SELF*-Schluessel (mindestens SELF_GUID, SELF_NAME) und TABLE.
2. Weitere ROOT-Felder sind tabellenspezifisch zu beurteilen und werden in A.0 aus den realen Datensaetzen hergeleitet.

## 3.2 666-Satz (Inhalts-Template)

UID: 66666666-6666-6666-6666-666666666666

Pflichtinhalt in daten:
1. ROOT: identisch zur ROOT-Definition aus 555.
2. TEMPLATES: Feldcontainer fuer Gruppeninhalte.

Regeln:
1. Jede in 555 definierte Gruppe darf ein passendes Template in 666.TEMPLATES besitzen.
2. Weitere maschinelle Teil-Templates (z. B. CONFIGS, TABS, LISTEN-Defaults) liegen ebenfalls in 666.TEMPLATES.
3. TEMPLATES selbst ist Metastruktur und wird nicht als fachliche Gruppe in Instanzdaten persistiert.
4. 666 wird in A.0 auf genau zwei Top-Level-Gruppen normalisiert: ROOT und TEMPLATES.

## 3.3 Instanzbildung fuer neue Saetze

Neuer Datensatz daten wird linear aufgebaut:
1. Struktur aus 555 uebernehmen (ROOT + leere Gruppen).
2. Inhalte aus 666.TEMPLATES fuer passende Gruppen einsetzen.
3. Systemfelder setzen (SELF_GUID, SELF_NAME, SELF_LINK_UID, Zeitfelder).
4. Metagruppen wie TEMPLATES aus der Instanz entfernen.

## 4. Einheitlicher Lebenszyklus (Neu/Aendern/Loeschen)

## 4.1 Neuanlage
1. Nur ueber 555/666-Ableitung.
2. Keine ad-hoc Strukturkopien ausserhalb des Template-Pfads.

## 4.2 Aenderung
1. Fachliche Aenderungen erfolgen auf Instanzdaten.
2. Bei Strukturabweichungen wird vor Save eine Struktur-Synchronisation ausgefuehrt.

## 4.3 Loeschung
1. Loeschung bleibt fachlich wie bisher (soft/historisch, wo definiert).
2. Strukturregeln beeinflussen Loeschung nicht, aber Validierung vor Loeschung bleibt aktiv.

## 5. Strukturmigration bei Template-Aenderung

## 5.1 Fachregel
Wenn sich 555/666-Struktur aendert, werden Bestandsdatensaetze nachgezogen.

## 5.1.1 Pflicht-Normalisierung vor Projektfortsetzung (A.0 Gate)
Vor jeder weiteren Projektphase muessen 555 und 666 je Tabelle aus den vorhandenen Datensaetzen normalisiert werden.

Verbindlicher linearer Ablauf je Tabelle:
1. Aktive Datensaetze (ohne 555/666) analysieren.
2. Fachgruppen aus den Datensaetzen ermitteln.
3. 555 aufbauen als ROOT + leere Gruppenobjekte.
4. 666 aufbauen als ROOT + TEMPLATES mit aus Datensaetzen hergeleiteten Gruppen-Templates.
5. ROOT-Struktur zwischen 555 und 666 identisch machen.
6. Ergebnisse speichern, dann naechste Tabelle.

Erst wenn alle Tabellen pro Ziel-DB konsistent normalisiert sind, darf mit Folgephasen fortgefahren werden.

## 5.2 Additives Backup
Bei Entfall von Eigenschaften/Feldern:
1. Wert wird nicht verworfen.
2. Wert wird additiv in backup_daten geschrieben, inklusive Pfad und Migrationskontext.

Empfohlenes Backup-Format (Beispiel):
{
  "MIGRATION_BACKUP": {
    "2026-05-18T12:00:00Z": {
      "removed": [
        {"path": "CONFIG.OLD_KEY", "value": "...", "reason": "template_removed"}
      ]
    }
  }
}

## 5.3 Zeitpunkt der Migration
Empfehlung V1 (hybrid):
1. On-Save: betroffener Satz wird synchronisiert.
2. Background-Job: restliche Saetze werden asynchron in Batches nachgezogen.

Damit wird verhindert, dass ein einzelner Save grosse Tabellen voll migrieren muss.

## 5.4 Konflikte und Sperrstrategie
Empfehlung:
1. Keine Tabellenvollsperre als Standard.
2. Satzweise Verarbeitung mit row-level lock (FOR UPDATE) im Updatepfad.
3. Optimistic Concurrency bleibt aktiv.
4. Bei Konflikt: Retry mit Reload fuer den einzelnen Satz.

## 6. Ausnahmen (zu ermitteln und zu benennen)

Diese Tabellenklassen sind voraussichtlich nicht 1:1 templatefaehig und muessen explizit beurteilt werden:
1. Auth-/Benutzernahe Tabellen mit Passwort/Secret-Logik.
2. Rein technische Log-/History-Tabellen.
3. Reine Prozess-/Queue-/Import-Zwischenspeicher.
4. Tabellen mit externer Integrationsbindung und festem Fremdschema.

Pflicht:
1. Ein Ausnahmekatalog pro Tabelle mit Begruendung und Zielmodus:
- voll templatefaehig,
- teiltemplatefaehig,
- ausgenommen.

## 7. Risiken

1. Laufzeitrisiko bei grossen Tabellen (Migrationsdauer).
- Reduktion: Batch-Migration mit Resume (siehe Optimierung 3) ist Pflicht in V1.

2. Konfliktrisiko bei parallelen Writes waehrend Strukturmigration.
- Risiko: Zwischen erstem und letztem migriertem Satz koennen neue Aenderungen eingehen.
- Reduktion: Migrationsfenster je Lauf protokollieren (start_ts, end_ts) und danach Delta-Rerun auf Basis modified_at durchfuehren, bis kein Nachlauf mehr offen ist.

3. Semantik-/UI-Risiko bei entfallenen Feldern.
- Ist-Verhalten: Nicht vorhandene Felder werden leer angezeigt.
- Erweiterung V1: Optionaler UI-Hinweis "Feld entfallen".
- Historie: Wegfallende Felder/Eigenschaften koennen als explizite Aenderung auf null in die Aenderungshistorie geschrieben werden (Mandant/User/Context vorhanden).

4. Operatives Risiko durch Backup-Wachstum.
- Bewertung: In Produktion eher gering, da Feldentfall selten ist.
- Einordnung: Hauptsaechlich Entwicklungsphase/Pre-GoLive; bei finalen App-Staenden koennen obsolete Strukturen gezielt bereinigt werden (Praefix-basiert).

## 8. Optimierungen

1. Strukturversion pro Tabelle von Anfang an.
- Ablage in sys_systemdaten je Tabelle (inkl. manuellem Reset fuer Erstauslieferung/Rollout-Faelle).

2. Satzmarker fuer letzte migrierte Strukturversion von Anfang an.
- Ablage im jeweiligen Satz unter ROOT (z. B. ROOT.STRUCT_VERSION_APPLIED).

3. Batch-Migration mit konfigurierbarer Groesse und Resume-Faehigkeit.
- Wird direkt mit umgesetzt (nicht erst spaeter), auch wenn produktive Last erst spaeter relevant wird.

4. Dry-Run-Analyzer vor Apply (Delta/Entfall/Backup-Menge).

5. Monitoring.
- Empfehlung: Neue mandantenweite Monitoring-Tabelle in der Mandanten-DB als generische Basis fuer Batch/Job-Ablaufe (Migration, Abrechnung, Buchung, Verteilung etc.).

## 9. Offene Entscheidungen

1. KANONISCHE Strukturversion liegt in 555.ROOT.

2. ROOT-Identitaet 555 vs 666 wird technisch erzwungen.
- Ziel: Durchgehend gleiche ROOT-Struktur je Tabelle; nicht gesetzte Werte sind leer/null, aber Schluesselstruktur bleibt gleich.

3. Initiale Ausnahmen (bekannt):
- dev_workflow_draft
- dev_workflow_draft_item
- asy_benutzer als Teilausnahme (Passwort-/Benutzer-Sonderregeln; daten-Anteil folgt grundsaetzlich den Regeln)
- Weitere Ausnahmen werden in Phase A durch Analyse identifiziert.
- Kennzeichnung je Tabelle in sys_systemdaten: voll_templatefaehig | teiltemplatefaehig | ausgenommen.

4. Batch-Groessen/Zeitfenster sind initial nicht hart festgelegt (fehlende Erfahrungswerte).
- V1 liefert konfigurierbare Parameter; Betriebswerte werden aus Monitoringdaten abgeleitet.

5. Keine Archivierung von backup_daten in V1 vorgesehen.

6. Kreis nicht migrierbarer Felder wird eng gehalten.
- Vorlaeufig ausgeschlossen: SELF*-Eigenschaften (insbesondere SELF_GUID, SELF_LINK_UID und technisch abgeleitete SELF-Metafelder).

7. Zusatz-Metadaten auf Satzebene sind erlaubt und gewuenscht.
- RECORD_TYPE wird als zusaetzlicher Strukturanker verwendet (insbesondere fuer infos-nahe Datenbewegungen).

8. Referenzpolitik in der Basisentwicklung ist streng.
- Verbleibende Alt-Verweise auf nicht mehr zulaessige Datenquellen werden als harte Fehler behandelt (kein stiller Laufzeit-Fallback).

9. Fuer Dropdown-Extraktion aus sys_systemdaten gilt Big-Bang.
- Kein Parallelbetrieb alter und neuer Dropdown-Quelle.
- Daten werden einmalig migriert und Referenzen muessen danach konsistent sein.

## 10. Vorschlag Umsetzungsphasen

1. Phase A.0: Template-Roundmaking (neu, Pflicht vor Phase A)
- Annahme: 555/666 sind aktuell nicht konsistent gepflegt.
- Ziel: 555/666 je Tabelle auf einen validen Startzustand bringen (ROOT-Identitaet, Gruppenstruktur, TEMPLATES-Struktur).
- Ergebnisartefakt: Korrekturliste je Tabelle + Freigabe "Template-Basis migrationstauglich".
- Erweiterung (verbindlich): Normalisierung erfolgt pro Tabelle auf Basis realer Datensaetze (nicht nur Template-zu-Template-Abgleich).

2. Phase A: Analyse
- Tabelleninventar, 555/666-Health-Check, Ausnahmekandidaten.
- Delta-Ermittlung fuer notwendige Strukturmigration in Bestandsdaten.

3. Phase B: Spezifikations-Fixierung
- Ausnahmekatalog freigeben, Strukturversionierung festlegen.
- Pflicht-Zwischenschritt: Strukturtyp infos und Uebersetzungsstrategie festlegen (siehe PDVM_INFOS_TYP_UEBERSETZUNGSSTRATEGIE_SPEC_V1.md).
- Pflicht-Zwischenschritt: TabellenTyp-Taxonomie fuer Sprachinhalte finalisieren (siehe PDVM_TABELLENTYPEN_UND_I18N_STRUKTUR_SPEC_V1.md).

4. Phase C: Technische Migration V1
- On-Save-Sync + Background-Batch-Runner + Dry-Run-Report.

5. Phase D: Rollout
- zuerst kleine Tabellen, dann grosse Tabellen; Monitoring und Korrekturschleife.

6. Phase E: Verbindlichkeit
- neue Saetze nur noch 555/666-konform; Legacy-Pfade abschalten.

## 11. Abnahmekriterien V1

1. Neuanlage pro freigegebener Tabelle nutzt ausschliesslich 555/666.
2. Strukturabweichungen in Bestandsdaten werden erkannt und korrigiert.
3. Entfallene Werte landen nachvollziehbar in backup_daten.
4. Kein regressiver Einfluss auf bestehende Save-/View-Prozesse.
5. Ausnahmetabellen sind benannt, begruendet und dokumentiert.
6. 555/666 je Tabelle sind vor produktiver Migration formal validiert und freigegeben.

## 12. Ausnahmekatalog V1 (Ist-Stand 2026-05-20)

Der maschinenlesbare Ausnahmekatalog wurde erzeugt:
1. backend/reports/phaseB_exception_catalog_v1.json

Summary:
1. db_count: 3
2. table_count: 27
3. mode_counts:
- voll_templatefaehig: 21
- teiltemplatefaehig: 1
- ausgenommen: 5
- nicht_im_scope: 0
4. open_decisions_count: 6
5. review_required_count: 7

Wichtige Katalogregel:
1. Es werden nur BASE TABLES klassifiziert (keine Views).
2. In auth werden damit nur asy_* Tabellen im Katalog gefuehrt.

Tabellen mit target_mode != voll_templatefaehig:
1. system.dev_workflow_draft -> ausgenommen (explicit_excluded_dev_workflow)
2. system.dev_workflow_draft_item -> ausgenommen (explicit_excluded_dev_workflow)
3. system.sys_feld_aenderungshistorie -> ausgenommen (audit_or_history_table)
4. auth.asy_benutzer -> teiltemplatefaehig (user_auth_special_handling)
5. auth.asy_feld_aenderungshistorie -> ausgenommen (audit_or_history_table)
6. mandant_main.msy_feld_aenderungshistorie -> ausgenommen (audit_or_history_table)

Hinweis zur Abnahme:
1. Diese 6 Tabellen bilden den offenen Entscheidungsumfang fuer Punkt "Ausnahmekatalog final je Tabelle".
2. Alle anderen Tabellen sind aktuell als voll_templatefaehig klassifiziert.
