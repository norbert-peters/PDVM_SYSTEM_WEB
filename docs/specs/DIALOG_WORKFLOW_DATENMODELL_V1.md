# Dialog Workflow Datenmodell V1

Status: verbindlicher Architekturvorschlag (Basis fuer Umsetzung)

Ergaenzende Spezifikation:

1. Laufende Workflow-Entwuerfe (Draft-Container) sind beschrieben in DATENVERSIONIERUNG_WORKFLOW_DRAFT_CONTAINER_V1.md.

## 1. Ziel

Ein einheitliches Datenmodell fuer Dialoge und Workflow-Dialoge, damit:

1. Dialoge komplett in der Datenbank beschrieben sind,
2. neue Applikationsdialoge aus Templates erzeugt werden koennen,
3. Updates ueber Datenpakete (Release-Pakete) ausgerollt werden koennen.

## 2. Leitentscheidung

### 2.1 Ein Frame je Tab (edit/acti)

Entscheidung: pro `edit`- oder `acti`-Tab wird genau ein eigener Frame in `sys_framedaten` verwendet.

Begruendung:

1. klare Verantwortung je Tab,
2. einfachere Wiederverwendung,
3. saubere GUID-Referenzierung im Dialog,
4. bessere Diffbarkeit in Datenpaketen.

### 2.2 View bleibt in sys_viewdaten

`view`-Tabs referenzieren immer `sys_viewdaten`.
`edit`/`acti`-Tabs referenzieren immer `sys_framedaten`.

## 3. Verbindliche Tabellen-Rollen

### 3.1 sys_dialogdaten

Fuehrende Dialogdefinition.

Pflicht in `ROOT`:

1. `DIALOG_TYPE` in `norm|work|acti`,
2. `TAB_ELEMENTS` als einzige fuehrende Tab-Quelle,
3. je Tab: `MODULE`, `GUID`, optional `EDIT_TYPE`, optional `TABLE`.

Tab-Regel:

1. `MODULE=view` -> GUID aus `sys_viewdaten`,
2. `MODULE=edit|acti` -> GUID aus `sys_framedaten`.

### 3.2 sys_framedaten

Frame je Tab fuer `edit|acti`.

Pflicht:

1. `ROOT` mit Tab- und Gruppenkontext,
2. `FIELDS` als konkrete Feldliste im Tab,
3. Feldreihenfolge ueber `display_order`.

Verbindliche Workflow-Regel:

1. Bei Workflow-Frames muessen editierbare Controls unter `daten.FIELDS` liegen.
2. Jede Felddefinition in `daten.FIELDS` muss `gruppe = FIELDS` verwenden.
3. `gruppe = ROOT` ist fuer Workflow-Inputcontrols unzulaessig.

Wichtig:

1. Frames enthalten Feldanordnung und tab-spezifische Ueberschreibungen,
2. Frames sind keine globale Feldquelle.

### 3.3 sys_control_dict

Single Source of Truth fuer wiederverwendbare Controls/Properties.

Pflicht:

1. Standard-Controls zentral hier,
2. neue Controls werden hier angelegt,
3. Frames referenzieren/uebernehmen Controls aus diesem Pool.

### 3.4 sys_viewdaten

View-Definition fuer den View-Tab.

Pflicht:

1. Tabelle,
2. Filter,
3. Sort,
4. Projektion.

## 4. Dictionary-Strategie

Entscheidung: eigener Dictionary-Tab bleibt sinnvoll und wird beibehalten.

Begruendung:

1. zentrale Auswahl/Anlage von Controls ohne Kontextbruch,
2. verhindert Duplikate in mehreren Frames,
3. Frames bleiben schlank (nur Auswahl, Reihenfolge, tab-spezifische Ueberschreibung).

Umsetzung:

1. Dictionary-Tab direkt hinter Dialog-Tab,
2. dort Prefix-Suche, Auswahl und Neuanlage in `sys_control_dict`,
3. Frame-Tabs nutzen nur den ausgewaehlten Control-Pool und ordnen ihn.

## 5. Erstellungsablauf fuer einen Workflow-Dialog

1. Dialog aus Template in `sys_dialogdaten` erzeugen.
2. `TAB_ELEMENTS` mit finalen GUID-Referenzen fuellen.
3. Pro `edit|acti`-Tab einen Frame in `sys_framedaten` erzeugen.
4. Dictionary-Tab: benoetigte Controls auswaehlen oder neu anlegen (`sys_control_dict`).
5. In jedem Frame FIELDS aus dem Pool platzieren, Reihenfolge setzen, ggf. Properties ueberschreiben.
6. View-Tab: Tabelle waehlen, Gruppen/Felder uebernehmen, Projektion/Filter/Sort in `sys_viewdaten` speichern.
7. Menuepunkt in `sys_menudaten` mit `go_pdvm_dialog` + `dialog_guid` setzen.

## 6. Ueberschreibungsregeln (wichtig)

1. Basisdefinition eines Controls liegt in `sys_control_dict`.
2. Tab-spezifische Abweichungen duerfen im Frame stehen.
3. Bei Konflikt gilt fuer Rendern: Frame-Wert vor Control-Dict-Wert.
4. Rueckschreiben neuer globaler Standards erfolgt explizit in `sys_control_dict`, nicht implizit aus dem Frame.

## 7. Release- und Paketfaehigkeit

Damit Updates sauber als Datenpaket laufen, muessen gelten:

1. deterministische GUIDs fuer Templates/Factory-Artefakte,
2. idempotente Erzeugung (create/update/skipped),
3. klare Trennung der Verantwortungen je Tabelle,
4. keine manuellen SQL-Sonderwege ausserhalb Service/Tools.

## 8. Akzeptanzkriterien

1. Ein Workflow-Dialog hat pro `edit|acti`-Tab genau einen Frame.
2. View-Tab bezieht sich immer auf `sys_viewdaten`.
3. Dictionary-Tab kann Controls suchen, auswaehlen und neu anlegen.
4. Frames koennen Controls auswaehlen, sortieren und tab-spezifisch ueberschreiben.
5. Der erzeugte Dialog ist direkt ueber Menue (`go_pdvm_dialog`) startbar.
6. Alle Artefakte sind paketierbar und updatefaehig.
