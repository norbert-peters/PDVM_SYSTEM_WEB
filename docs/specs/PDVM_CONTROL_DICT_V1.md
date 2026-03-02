# PDVM Control Dictionary V1 (Spezifikation)

## 1. Ziel
Zentrale, konsistente Control-Definitionen fuer Edit-Frames. Controls werden ueber die `feld_guid` referenziert und bei Bedarf lokal ueberschrieben. Damit wird Duplikation reduziert und die Pflege stabilisiert.

## 2. Geltungsbereich (V1)
- Nur fuer `edit_frame`.
- Dictionary-Quelle ist eine eigene Tabelle.
- Mandantenspezifische Controls liegen zusaetzlich in der Mandantendatenbank.
- Direkte Referenz ueber die `feld_guid` (kein Pflicht-`dict_ref`).
- Datenbank-Routing erfolgt zentral ueber `PdvmDatabase` (System vs. Mandant ist bekannt).
- Begriffe: Wir sprechen ausschliesslich von `feld_guid` (Control-GUID == Feld-GUID).
- Zeitwerte in JSONB verwenden Pdvm-Format (siehe ARCHITECTURE_RULES).

## 3. Tabellen (System + Mandant)

### 3.1 Systemdatenbank
- `sys_control_dict`
- `sys_control_dict_audit`

### 3.2 Mandantendatenbank
- `sys_contr_dict_man`
- `sys_contr_dict_man_audit`

## 4. Datenmodell

**Architekturregel (verbindlich):**
Alle neuen Tabellen folgen der einheitlichen PDVM-Tabellenstruktur
(`uid`, `name`, `daten`, `historisch`, `created_at`, `modified_at`).
Einzige Ausnahme bleibt `sys_benutzer`.

### 4.1 sys_control_dict (Systemdatenbank)
Ein Datensatz pro Control-Definition (GUID = `feld_guid`).
Die Control-Beschreibung liegt in `daten` (JSONB).

### 4.2 sys_contr_dict_man (Mandantendatenbank)
Analog zu `sys_control_dict`, aber mandantenspezifische Controls.

### 4.3 Audit-Tabellen
- `sys_control_dict_audit`
- `sys_contr_dict_man_audit`

Audit-Tabellen folgen ebenfalls der einheitlichen Tabellenstruktur.
Die Audit-Informationen liegen in `daten` (JSONB), z.B.:
```json
{
  "feld_guid": "00000000-0000-0000-0000-000000000000",
  "action": "update",
  "user_guid": "00000000-0000-0000-0000-000000000000",
  "timestamp": "2025-01-01T12:00:00Z",
  "payload_before": { "name": "NAME" },
  "payload_after": { "name": "NAME", "label": "Name" },
  "comment": "optional"
}
```

Hinweis (Variante):
Audit kann alternativ ueber die PDVM-Historisierung abgelegt werden.
Dabei werden die Audit-Datensaetze in den Audit-Tabellen mit `historisch=1`
gespeichert, so dass die Historienstruktur einheitlich bleibt.

## 5. Control-Definition (JSONB in daten)
Beispielstruktur (nicht abschliessend):
```json
{
  "name": "NAME",
  "label": "Name",
  "type": "string",
  "table": "sys_personen",
  "gruppe": "ROOT",
  "read_only": false,
  "display_order": 10,
  "configs": {
    "help": { "key": "", "feld": "", "table": "", "gruppe": "" },
    "dropdown": { "key": "", "feld": "", "table": "", "gruppe": "" }
  }
}
```

## 6. Referenzierung in Frames
**Primar-Logik:** Die `feld_guid` ist die Referenz.
Wenn ein Feld in `sys_framedaten` die GUID `X` hat und in der Dictionary-Tabelle
ein Control mit GUID `X` existiert, wird dieses als Basis geladen.

Lokale Felddaten dienen als Overrides.

Beispiel (Frame-Feld mit Override):
```json
{
  "label": "Name (lokal)",
  "display_order": 20
}
```

**Optional (Alias-Fall):** Falls ein Feld bewusst auf eine andere Basis-GUID zeigen
soll, kann `dict_ref` gesetzt werden. Wenn `dict_ref` vorhanden ist, wird diese GUID
als Basis verwendet.

## 7. Merge-Regeln (V1)
1. Basis-GUID bestimmen:
  - wenn `dict_ref` gesetzt ist: `dict_ref`
  - sonst: `feld_guid`
2. Wenn Dictionary-Control gefunden:
  - Ergebnis = `{...dict_control, ...local_overrides}`.
3. Wenn kein Dictionary-Control gefunden:
  - lokale Definition wie bisher.
4. Ungueltige Referenz:
  - Warnung in der UI.
  - Protokoll in `sys_error_log`.

## 8. Lookup-Reihenfolge
Lookup erfolgt ueber `PdvmDatabase` (Routing ist bekannt):
1. Mandantendatenbank (`sys_contr_dict_man`)
2. Systemdatenbank (`sys_control_dict`)

Audit wird analog in der jeweiligen Datenbank protokolliert.

## 9. Validierungsregeln
- Pflichtfelder muessen im finalen Control vorhanden sein (z.B. `name`, `type`, `table`).
- Nur definierte Fallbacks sind erlaubt, sonst Fehler.

## 10. Elemente-Listen
`element_list` referenziert Controls ueber `feld_guid` (mehrere GUIDs).
Optional kann je Element ein `dict_ref` gesetzt werden.
Die einzelnen Controls werden wie in Abschnitt 7 gemergt.

## 11. Logging und Fehlerbehandlung
- Ungueltige Referenz fuehrt zu einer UI-Warnung und Eintrag in `sys_error_log`.
- Audit in den Audit-Tabellen bei Create/Update/Delete der Dictionary-Controls.
- Perspektive: Audit-Mechanismus kann spaeter fuer alle Tabellen generalisiert werden.

## 12. Rollout (V1)
- Globales Ziel: Alle Editoren nutzen Dictionary-Controls.
- Einstieg: `edit_frame` und als erstes die Eingabeframes fuer `sys_framedaten`.
- Control-Eintraege koennen initial ueber `edit_json` gepflegt werden.

## 13. Migrationshinweise (V1)
- Bestehende Frames bleiben kompatibel.
- Neue Frames koennen Schritt fuer Schritt ueber `feld_guid` arbeiten; `dict_ref` bleibt optional.

## 14. Offene Punkte (V2)
- Konfigurierbare Schluessel fuer `dict_ref` und Override-Block.
- Governance (Freigabeprozess fuer globale Controls).
- Automatisierte Migration bestehender Controls in Dictionary-Tabellen.
- Ausweitung auf weitere Edit-Typen (globaler Einsatz von Dictionary-Controls).

## 15. Update V1.1 (Template+Delta)
- Ab 2026-03-01 gilt fuer `sys_control_dict` und `sys_framedaten`: **effective on read, delta on write**.
- Details und Migrationsablauf: `docs/specs/PDVM_TEMPLATE_DELTA_STORAGE_V1.md`.
