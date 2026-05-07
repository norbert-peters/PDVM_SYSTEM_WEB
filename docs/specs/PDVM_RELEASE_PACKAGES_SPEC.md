# PDVM Release-Pakete Spezifikation (V1)

Status: Vorschlag (Review)
Scope: Ausrollen von Systemdaten fuer `sys_*` Tabellen in der Systemdatenbank (derzeit `pdvm_system`)

## 1. Ziel

Definition eines reproduzierbaren und auditierbaren Rollout-Prozesses fuer Applikationsdaten (Menues, Dialoge, Views, Control-Metadaten, Systemtexte/-konfiguration) vom Entwicklungssystem auf Zielinstallationen.

Diese Spezifikation umfasst:
1. Paketformat in GitHub
2. Release-Registrierung in der Entwicklungsdatenbank
3. Installationsstatus in der Zieldatenbank
4. Aenderungsprotokollierung
5. Login-nahen Update-Check-Fluss (Updates verfuegbar)

## 2. Architekturvorgaben (verbindlich)

Diese Spezifikation folgt den Architekturregeln:
1. Kein direktes SQL in Routern
2. Dynamische DB-Verbindungen ueber Auth + Mandantenkonfiguration
3. Business-Logik ueber Service-Layer (Wrapper auf `PdvmCentralDatabase` und `PdvmDatabase`)
4. Stabiler Rollback und Nachvollziehbarkeit

## 3. Datenmodell

Alle Tabellen folgen der PDVM-Standardstruktur (`uid`, `daten`, `name`, `historisch`, `created_at`, `modified_at`, ...).

### 3.1 Zielsystem-Tabellen (in `pdvm_system`)

#### `sys_release_state`
Ein Datensatz pro angewendetem Release-Paket.

Verpflichtende `daten` Schluessel:
1. `ROOT.RELEASE_ID` (string, eindeutige Paket-ID)
2. `ROOT.APP_ID` (string, z. B. `SYSTEM`, `PERSONALWESEN`)
3. `ROOT.VERSION` (semver-aehnlicher string)
4. `ROOT.PACKAGE_HASH` (sha256)
5. `ROOT.SOURCE_COMMIT` (git commit)
6. `ROOT.APPLIED_AT` (PdvmDateTime string)
7. `ROOT.APPLIED_BY` (user/email/system)
8. `ROOT.STATUS` (`applied`, `failed`, `rolled_back`)
9. `ROOT.DURATION_MS` (number)
10. `ROOT.ERROR_SUMMARY` (optional string)
11. `ROOT.TARGET_SYSTEM_DB` (string)

`name` Konvention:
`<APP_ID>:<VERSION>`

#### `sys_release_log`
Append-only technisches Log fuer Rollout-Laufereignisse.

Verpflichtende `daten` Schluessel:
1. `ROOT.RELEASE_ID`
2. `ROOT.STEP` (`preflight`, `download`, `validate`, `apply_item`, `commit`, `rollback`)
3. `ROOT.LEVEL` (`info`, `warning`, `error`)
4. `ROOT.MESSAGE`
5. `ROOT.EVENT_AT` (PdvmDateTime)
6. `ROOT.DETAILS` (object, optional)

### 3.2 Entwicklungstabellen (in Entwicklungs-Systemdatenbank)

#### `dev_release`
Release-Kopftabelle (ein Datensatz pro Release-Kandidat/Paket).

Verpflichtende `daten` Schluessel:
1. `ROOT.RELEASE_ID`
2. `ROOT.APP_ID`
3. `ROOT.VERSION`
4. `ROOT.STATUS` (`draft`, `ready`, `published`, `withdrawn`)
5. `ROOT.CREATED_BY`
6. `ROOT.CREATED_AT`
7. `ROOT.PACKAGE_HASH` (wird beim Paketbau gesetzt)
8. `ROOT.SOURCE_COMMIT` (wird beim Paketbau gesetzt)
9. `ROOT.NOTES` (optional)

#### `dev_release_item`
Release-Positionstabelle (ein Datensatz pro enthaltenem Record).

Verpflichtende `daten` Schluessel:
1. `ROOT.RELEASE_ID`
2. `ROOT.APP_ID`
3. `ROOT.TABLE_NAME` (muss `sys_*` sein)
4. `ROOT.RECORD_UID`
5. `ROOT.OPERATION` (`upsert`, `delete`)
6. `ROOT.SOURCE_MODIFIED_AT`
7. `ROOT.CHECKSUM_AFTER`
8. `ROOT.CHECKSUM_BEFORE` (optional)
9. `ROOT.ORDER_NO` (integer fuer deterministisches Apply)

`name` Konvention:
`<TABLE_NAME>:<RECORD_UID>`

### 3.3 Aenderungslog-Tabelle (entwicklungseitig verpflichtend)

#### `sys_change_log`
Append-only Audit-Tabelle (Quell-UID nicht als Primaer-UID wiederverwenden).

Verpflichtende `daten` Schluessel:
1. `ROOT.EVENT_UID` (eigene uid)
2. `ROOT.SOURCE_TABLE`
3. `ROOT.SOURCE_UID`
4. `ROOT.GROUP_NAME`
5. `ROOT.FIELD_NAME`
6. `ROOT.OLD_VALUE`
7. `ROOT.NEW_VALUE`
8. `ROOT.CHANGED_BY`
9. `ROOT.CHANGED_AT`
10. `ROOT.CHANGE_REASON` (optional)
11. `ROOT.RELEASE_ID` (optionale Verknuepfung nach Zuordnung)

## 4. Paketformat (GitHub-Artefakt)

Ordnerstruktur:
1. `manifest.json`
2. `items.jsonl` (eine Release-Position pro Zeile)
3. `data/<table_name>.jsonl` (serialisierte Zielzeilen fuer `upsert`)
4. `checksums.sha256`

### 4.1 `manifest.json`
Verpflichtende Schluessel:
1. `release_id`
2. `app_id`
3. `version`
4. `target_db_role` (`system`)
5. `target_tables` (array)
6. `min_backend_version`
7. `depends_on` (array)
8. `source_commit`
9. `package_hash`
10. `created_at`

## 5. Apply-Strategie

### 5.1 Preflight
1. Paket-Hash verifizieren
2. Erreichbarkeit der Ziel-DB ueber mandantenselektierte Verbindung pruefen (`SYSTEM_DB`/`SYSTEM_DATABASE`)
3. Vorhandensein der Zieltabellen pruefen (oder explizit kontrollierter Create-Pfad)
4. Abhaengigkeiten pruefen
5. Installations-Lock pro `app_id` setzen

### 5.2 Transaktionales Apply
1. Transaktion beginnen
2. Items in `ORDER_NO` verarbeiten
3. `upsert` nach `uid`
4. Loeschung erfolgt fachlich ueber `gilt_bis` (Pdvm-Zeitpunkt), nicht physikalisch
5. `sys_release_state` auf `applied` schreiben
6. Commit

Im Fehlerfall:
1. Rollback der Transaktion
2. `sys_release_state` auf `failed` schreiben
3. `sys_release_log` mit Fehlerdetails schreiben

## 6. Login-nahes Update-UX

Beim Login (nach Auth, vor finalem App-Landing):
1. Aktiven Mandanten + System-DB aufloesen
2. Installierte Versionen (`sys_release_state`) mit verfuegbaren Paketen vergleichen
3. Verfuegbarkeit gruppiert pro App zurueckgeben:
   1. `SYSTEM`
   2. `PERSONALWESEN`
   3. weitere

Frontend-Verhalten:
1. Nicht-blockierenden Dialog anzeigen: `Updates verfuegbar`
2. App-Gruppen mit Zielversion und Notizen anzeigen
3. Anwender kann jetzt anwenden oder spaeter

## 7. Sicherheitsmodell

1. Paketquelle: GitHub Release-Artefakte nur aus vertrauenswuerdigem Repo
2. Verbindliche Checksum-Pruefung vor Apply
3. Optionale Signaturpruefung (Phase 2)
4. Apply-Endpunkt nur fuer Admin-Rolle
5. Vollstaendige Audit-Trail in `sys_release_log`

## 8. Betrieb und Rollback

1. Jedes Apply erzeugt einen unveraenderlichen `sys_release_state` Datensatz
2. Rollback-Paket kann explizit sein (`operation` Items, die den vorherigen Zustand rueckfuehren)
3. Kein destruktives Cleanup ohne Audit-Eintraege

## 9. Minimaler Implementierungsplan (MVP)

### Phase 1
1. Tabellen anlegen: `sys_release_state`, `sys_release_log`, `dev_release`, `dev_release_item`, `sys_change_log`
2. CLI-Exporter (Dev) bauen: `dev_release` + `dev_release_item` lesen, Paket erzeugen
3. Installer-Service (Ziel) bauen: validieren + transaktional anwenden
4. Login-Update-Check-Endpunkt (read-only) ergaenzen

### Phase 2
1. Admin-UI fuer Release-Komposition (`dev_release`/`dev_release_item`)
2. Signaturvalidierung
3. Hintergrund-Scheduler fuer periodische Checks (optional)

## 10. Beschlossene Entscheidungen

1. Loeschstrategie:
Physikalische Loeschung findet vorerst nicht statt. Datensaetze werden ueber `gilt_bis` fachlich beendet und ab entsprechendem Stichtag nicht mehr mitgelesen. Eine spaetere physikalische Bereinigung bleibt ein separater manueller Wartungsschritt.

2. Granularitaet `sys_change_log`:
Zeilenweiser Fallback ist ausreichend. Feldgenaue Deltas sind optional und koennen spaeter erweitert werden.

3. Apply-Ausloesung:
Policy-basierte automatische Anwendung ist erlaubt. Der Login-Flow kann Updates automatisch einspielen, sofern Policy, Integritaetspruefung und Berechtigungen dies erlauben.

## 11. Akzeptanzkriterien

1. Dasselbe Release-Paket ergibt auf zwei Zielen identische Checksums auf Ziel-`sys_*`-Zeilen
2. Fehlgeschlagenes Apply laesst Zieldaten unveraendert
3. Installierte Version ist in `sys_release_state` sichtbar
4. Login-Update-Check meldet Verfuegbarkeit korrekt pro App
5. Kein routerseitiges SQL eingefuehrt
