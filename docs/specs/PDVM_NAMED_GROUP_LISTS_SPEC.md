# PDVM Named Group Lists Spec (V1)

Stand: 2026-02-27  
Status: verbindlich fuer lineare Neuanlage in Dialogen

## 1. Ziel
Ergaenzung zur bestehenden `element_list`-Logik:
- Neben klassischen `ELEMENTS` soll das System mehrere benannte Gruppen auf derselben Ebene einfuegen koennen.
- Beispiel in `sys_framedaten`: `PER_PERSONEN`, `FIN_BASIS` als gleichrangige Gruppen mit eigenen Feldern.

## 2. Entscheidung: eigener Typ statt Ueberladung von element_list
Fuer lineare Verarbeitung wird ein eigener fachlicher Typ verwendet:
- `group_list` (fachlich)

Begruendung:
- `element_list` bleibt fuer Listen von Elementen (z. B. Tabs, Tabellenzeilen).
- `group_list` steht fuer das Einfuegen kompletter Gruppenbloecke auf Top-Level.
- Keine verschachtelte Mehrdeutigkeit, klare lineare Ausfuehrung.

## 3. Datenquelle (Template 555...)
Benannte Gruppenlisten liegen in:
- `sys_control_dict.uid = 55555555-5555-5555-5555-555555555555`
- `daten.ELEMENTS.GROUP_LISTS`

Struktur:
```json
{
  "ELEMENTS": {
    "GROUP_LISTS": {
      "PER_PERSONEN": {
        "GROUP_NAME": "PER_PERSONEN",
        "GROUP_TEMPLATE": {
          "ANZEIGE": true,
          "DISPLAY_ORDER": 10
        },
        "AUTO_APPLY": true,
        "TYPE": "group_list"
      },
      "FIN_BASIS": {
        "GROUP_TEMPLATE": {
          "ANZEIGE": true,
          "DISPLAY_ORDER": 20
        },
        "AUTO_APPLY": false,
        "TYPE": "group_list"
      }
    }
  }
}
```

Hinweise:
- `GROUP_NAME` optional; wenn leer, wird der Key (`PER_PERSONEN`) verwendet.
- `GROUP_TEMPLATE` ist Pflicht und muss Objekt sein.
- `TYPE` ist semantisch (fuer UI/Editor), aktuell optional in der Laufzeit.

## 4. Auswahl der einzufuegenden Gruppen
Steuerung im Zieldatensatz ueber:
- `ROOT.GROUP_LISTS` als Liste von Namen

Beispiel:
```json
{
  "ROOT": {
    "SELF_GUID": "...",
    "SELF_NAME": "...",
    "GROUP_LISTS": ["PER_PERSONEN", "FIN_BASIS"]
  }
}
```

Regel:
1. Wenn `ROOT.GROUP_LISTS` gesetzt ist -> exakt diese Eintraege anwenden.
2. Sonst -> alle Eintraege mit `AUTO_APPLY=true` anwenden.

## 5. Linearer Merge-Ablauf (verbindlich)
Neuanlage aus Dialog-Template:
1. Basis aus `666...` laden.
2. Fuer jede in `666...` vorhandene Gruppe (ausser ROOT/TEMPLATES/ELEMENTS) passende Defaults aus `555...daten.TEMPLATES` anwenden.
3. Benannte Gruppenlisten aus `555...daten.ELEMENTS.GROUP_LISTS` anwenden.
4. Optionaler MODUL-Merge (`MODUL`) anwenden.
5. `ROOT.SELF_GUID` / `ROOT.SELF_NAME` setzen.
6. Template-Metagruppen `TEMPLATES` und `ELEMENTS` aus dem Ergebnis entfernen.

Merge-Prioritaet innerhalb einer Zielgruppe:
- Default = `GROUP_TEMPLATE`
- vorhandene Basiswerte der Zielgruppe ueberschreiben Defaults

Damit gilt: Template liefert Standardwerte, bestehende Basisdefinition bleibt fuehrend.

Identity-Regel:
- `ROOT.SELF_GUID` und `ROOT.SELF_NAME` werden in der Neuanlage final gesetzt.
- Diese beiden Felder duerfen nicht durch `root_patch` ueberschrieben werden.

## 6. Abgrenzung zu element_list
- `element_list`: Listen-Elemente innerhalb einer Gruppe/Feld-Konfiguration.
- `group_list`: Erzeugung gleichrangiger Gruppenbloecke auf Top-Level.

Beide duerfen parallel eingesetzt werden.

## 7. Kompatibilitaet
- Bestehende Dialoge ohne `ELEMENTS.GROUP_LISTS` bleiben unveraendert.
- Bestehende `element_list`-Funktion bleibt unveraendert.

## 8. UI/Validierungs-Contract (Querverweis)
Auch fuer Felder aus `group_list` gilt der zentrale InputControl-Contract unveraendert:
- Frontend rendert generisch aus Control-Metadaten und darf nur UX-Vorpruefung machen.
- Backend ist verbindlich fuer finale Normalisierung/Validierung bei Leave/Commit.
- Commit-Logik nutzt die Klassen `ok`, `hint_*` (nicht blockierend), `error_*` (blockierend).

Verbindliche Details sind in der Edit-Control-Spezifikation definiert:
- `docs/specs/PDVM_EDIT_CONTROL_SPEC.md` (Abschnitt "7. Verbindlicher InputControl-Contract")

## 9. Implementierungsstatus
Backend umgesetzt in:
- `backend/app/core/dialog_service.py`
  - `_resolve_groups_from_templates` (nur Basis-Gruppen + Template-Defaults, Basis-Override)
  - `_resolve_named_group_lists_from_elements` (neuer Schritt fuer benannte Gruppenlisten)
  - `_strip_template_meta_groups` (entfernt TEMPLATES/ELEMENTS aus Instanzen)
  - `_apply_root_identity` (schuetzt SELF_GUID/SELF_NAME vor Patch-Override)
  - Aufruf in `build_dialog_draft_from_template` und `create_dialog_record_from_template`
