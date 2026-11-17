# PDVM Mandant anlegen: Menüpunkt und geführter Ablauf V1

Status: **freigegeben und umgesetzt (2026-11-16)**, offener Punkt G der Rendering-Spec (Abschnitt 7, Nr. 5). Umgesetzt wie in Abschnitt 8 entschieden; Abweichung: Rollen am Menüeintrag heißen `roles` (Liste), die Mandantenliste nach dem Anlegen wird nicht nachgeladen, sondern die Sitzung beendet. Betrifft Regel 2.2 (Menü), 2.4 (keine nativen Dialoge), 2.15/2.17 (Frames, Aktionen) und die Rollenprüfung für Mandanten (zweite Welle der Frame-Aktionen). Die Abschnitte 1 und 5 beschreiben den Stand **vor** der Umsetzung.

## 1. Ausgangslage

| Thema | Heute |
|---|---|
| Einstiege | Schaltfläche „Neuer Mandant“ im alten Dashboard (`/dashboard`, eigene Farben, `--color-success`), Link in der Mandantenauswahl; im Dialog „Mandanten bearbeiten“ ist „Neuer Satz“ gesperrt. |
| Ablauf | Drei getrennte Schritte: (1) `POST /api/mandanten/save`, (2) im Dialog „Mandanten bearbeiten“ die Aktion `mandant.setup` (Datenbank), (3) erster Login des Mandanten legt die Tabellen an. Dazwischen ein `alert` bzw. ein Hinweisfenster. |
| Mandantenliste | Wird beim Login in den `localStorage` geladen und danach nicht mehr aktualisiert; das JWT enthält einen Schnappschuss der Benutzerdaten. Der neue Mandant (seit 2026-11-16 in `MANDANTEN.LIST` des Anlegers) erscheint erst nach neuer Anmeldung. |
| Rechte | Backend: `superadmin` (`require_superadmin_user`). Frontend: Schaltfläche nur für Superadmin. Menüs kennen keine Rollen (nur App-Zuordnung `MEINEAPPS`). |
| Doppelter Code | `POST /api/mandanten/create` (Satz plus Datenbank mit Schema-Logik) wird vom Frontend nicht aufgerufen und überschneidet sich mit `/save` und `mandant.setup`. |

## 2. Bewertung: Menüpunkt statt Dashboard-Schaltfläche

**Empfehlung: ja, als Menüpunkt.**

- **Ein Einstieg, die vorgesehene Navigation.** Alle anderen Pflegefunktionen sind Menüpunkte (Regel 2.2). Eine Sonderschaltfläche im Dashboard ist ein zweiter Weg mit eigenem Stil. Das Dashboard ist nicht Teil des Menülayouts, liegt außerhalb von Theme-Overlays und Stichtag-Leiste und hat die Kontrastprobleme (feste Farbe `--color-success`, Inline-Styles).
- **Die Maske wird eine normale Seite im `AppLayout`** (Theme, Dark Mode, Kopfzeile, Sitzung). Vorher lief sie als Vollbild ohne Layout; das erklärt die abweichenden Farben.
- **Rollenkonzept gehört an den Menüpunkt.** Wer später festlegt, welche Rolle welche Menüpunkte sieht, braucht das Attribut ohnehin; „Neuer Mandant“ ist der erste Anwendungsfall und kann es klein einführen.
- **Der Link in der Mandantenauswahl entfällt.** Ein Superadmin ohne Mandant in `MANDANTEN.LIST` kann sich nicht anmelden (Login verlangt eine Zulassung, `auth.py`), die Auswahl ist ohne Mandant also nie der Startpunkt für das erste Anlegen. Ein Notweg wäre nur für den allerersten Mandanten nötig; das ist Setup (Seed-Tool), nicht UI.

**Voraussetzung (klein): Rollen an Menüeinträgen.** Heute gibt es dafür kein Attribut. Vorschlag:

- Optionales Feld `roles` (Liste) am Menüeintrag. Leer oder fehlend = für alle Benutzer der App sichtbar (heutiges Verhalten). Sonst nur sichtbar, wenn der Benutzer mindestens eine der Rollen hat (`security.normalized_roles`); `superadmin` sieht alle Einträge.
- Gefiltert wird **serverseitig** in `GET /api/menu/start` und `/api/menu/app/{name}`; ausgeblendete Einträge werden nicht ausgeliefert. Das Frontend bleibt „dumm“ (Regel 2.2). Autorität bleibt der Endpunkt (Rollenprüfung im Backend, wie bisher).
- Das spätere Rollenkonzept (wer pflegt `roles`, Vorlagen je Rolle) kann darauf aufsetzen, ohne dass etwas zurückgebaut wird. Bis dahin pflegt der Seed `roles` für diesen einen Eintrag; die Eingabe im Menü-Editor folgt mit dem Konzept (Control in `sys_control_dict`, Dropdown der Rollen aus `sys_dropdowndaten`).

**Menü-Handler:** `go_mandant_create` (Route `/mandant/new`). Bewusst kein allgemeines `go_route`: Menüdaten stammen aus der Datenbank, ein freier Pfad wäre ein Navigationsziel aus Daten (Allowlist-Prinzip wie bei den Aktions-IDs, Regel 2.17). `restoreLastNavigation` stellt diesen Handler **nicht** wieder her (Neuanlage nicht automatisch erneut öffnen, wie bei Aktionen).

**Platzierung:** im Zweig neben „Mandanten bearbeiten“ (Verwaltung), nicht unter „Systemtabellen pflegen“ (dort stehen Tabellen, keine Abläufe).

## 3. Ablauf: ein Schritt statt drei

```
Menü „Neuer Mandant“  ->  Seite /mandant/new (Frame „Mandanten Edit“, wie heute)
   [Mandant anlegen]  ->  POST /api/mandanten/create
        Server:  1. validieren (validate_new_mandant)        -> 422 mit Feldfehlern
                 2. Satz speichern (Gateway)                  -> Fehler: nichts angelegt
                 3. Mandant in MANDANTEN.LIST des Anlegers    (idempotent)
                 4. Datenbank einrichten (setup_mandant_database)
        Antwort: Status je Teilschritt {saved, access_granted, database}
   Ergebnisfenster: „Mandant X angelegt, Datenbank eingerichtet. Bitte neu anmelden.“
   [Zur Anmeldung]       ->  Abmelden (Sitzung schließen) -> Login
```

- **Reihenfolge Satz vor Datenbank.** Der Satz ist billig und reparabel; schlägt die Datenbank fehl (Host, Rechte, Name vergeben), bleibt der Satz mit `needs_setup = true`, und die Aktion `mandant.setup` im Dialog „Mandanten bearbeiten“ wiederholt nur Schritt 4. Ein Rollback (Satz löschen) wäre ein Datenverlust-Risiko und liefe am Gateway vorbei. Das Ergebnisfenster nennt den Teilfehler im Klartext und sagt, wie es weitergeht.
- **Tabellen** entstehen weiterhin beim ersten Login des Mandanten (Mandanten-Wartung, wie bei `mandant.setup`), nicht im Request.
- **Ein Endpunkt.** `POST /api/mandanten/create` (nur `superadmin`) ersetzt `/save` und die vorhandene, ungenutzte Schema-Logik. Orchestrierung in `mandant_setup_service` (`create_mandant`), der Router bleibt ohne SQL (Regel 1.1). Optionaler Query-Parameter `setup_database` (Standard `true`).
- **Erfolgs- und Fehlermeldungen** über `PdvmDialogModal` (Regel 2.4), kein `alert`.

## 4. Sitzung beenden und neu anmelden

**Empfehlung: ja, nach erfolgreichem Anlegen, mit Bestätigung.**

Gründe (technisch, nicht nur „sauber“):
1. Die Mandantenliste im Browser (`localStorage`) und der JWT-Schnappschuss (`user_data`) stammen aus dem Login; ohne neuen Login ist der neue Mandant dort nicht enthalten. Das ist dieselbe Regel wie bei Rollenänderungen („wirkt nach erneutem Login“).
2. Die GCS-Sitzung gehört zum alten Mandanten (Pools, Menü, Stichtag). Ein Wechsel ohne Abmeldung erzeugt zwei Zustände, die geprüft und synchron gehalten werden müssten.
3. Der Aufwand der Alternative (Liste und Token nachladen) ist höher und fehleranfälliger als die Abmeldung.

Ausgestaltung:
- Erst das Ergebnisfenster, dann Abmeldung über „Zur Anmeldung“ (kein automatisches, hartes Abmelden: die Meldung soll gelesen werden können).
- Bei Teilfehler (Datenbank nicht eingerichtet) **keine** Abmeldung; der Benutzer bleibt in der Sitzung und wiederholt die Aktion `mandant.setup`.
- Die Abmeldung nutzt den vorhandenen Logout (`AuthContext.logout`, schließt die GCS-Sitzung, entfernt `token`, `user_data`, `mandanten`, `mandant_id`).
- Hinweis im Fenster: Weitere Benutzer erhalten den Mandanten nicht automatisch; die Zuweisung (`MANDANTEN.LIST`) erfolgt im Benutzersatz (heute manuell, siehe offene Punkte).

## 5. Auswirkungen auf bestehenden Code

| Bereich | Änderung |
|---|---|
| `Dashboard.tsx` | Schaltfläche „Neuer Mandant“, `MandantCreate`-Einbindung und `alert` entfallen. |
| `MandantSelect.tsx` / `App.tsx` | Link „Neuer Mandant“, `showCreateMandant` und die Variante „Mandant gespeichert“ (Quittungsfenster aus der Zwischenlösung) entfallen. |
| `MandantCreate.tsx` | Wird Seite `/mandant/new` im `AppLayout`: Theme-Klassen statt Inline-Styles, Abbrechen führt nach `/menu-home`, Ergebnisfenster und Abmeldung wie oben. Route nur für Superadmin (sonst Hinweis); das Backend bleibt die Autorität. |
| `menuHandlers.ts` | Neuer Handler `go_mandant_create`; Menü-Editor-Auswahl der Handler ergänzen. |
| `menu.py` | Filter nach `roles` (Abschnitt 2). |
| `mandanten.py` | `/save` und altes `/create` ersetzt durch ein neues `/create`; Orchestrierung im Service. |
| Seed | `seed_mandant_menu_v1.py`: Menüeintrag mit `roles: ["superadmin"]` (idempotent, Dry-Run Standard, Snapshot). |
| Doku | Rendering-Spec (Abschnitt 6/7), Frame-Aktionen-Spec (Abschnitt 3.12), `ARCHITECTURE_RULES.md` (2.2: Attribut `roles`), `SERVICE_ARCHITECTURE`, Tools-README. |

## 6. Tests

- `test_mandant_access.py`: `create` verlangt Superadmin (403 sonst); Antwort enthält Teilschritt-Status; bei Datenbankfehler bleibt der Satz erhalten und `database` meldet den Fehler (gefakter Service); Zuweisung idempotent.
- `test_menu_roles.py` (neu): Eintrag ohne `roles` für alle sichtbar; mit `roles` nur für passende Rolle; `superadmin` sieht alle; Kinder ausgeblendeter Zweige verschwinden mit.
- Frontend: Typprüfung und Build; Theme-Guard (Tokens statt Farben). Kein Browser-Test vorhanden; Ablauf einmal manuell mit einem Testmandanten.

## 7. Befund aus der Prüfung (vorziehen empfohlen)

Die Mandantenwahl ist serverseitig nicht an den Benutzer gebunden: `POST /api/mandanten/select` prüft über `MandantDataManager.check_access` nur `MANDANT.IS_ALLOWED` (die Benutzerprüfung ist ein TODO im Code), und `GET /api/mandanten` sowie `/list` liefern jedem angemeldeten Benutzer alle Mandanten. Ein Benutzer, der eine Mandanten-UID kennt, kann diesen Mandanten wählen, auch wenn sie nicht in seiner `MANDANTEN.LIST` steht. Mit der automatischen Zuweisung beim Anlegen wird `MANDANTEN.LIST` fachlich verbindlich; deshalb sollte `select` gegen `MANDANTEN.LIST` des Benutzers prüfen (Superadmin nicht ausgenommen, er steht in seiner eigenen Liste) und die Listen-Endpunkte danach filtern. Das ist klein und gehört thematisch zu Punkt H (Zugriffsregeln); Vorschlag: als erster Umsetzungsschritt.

## 8. Entscheidungen (zur Freigabe)

1. Menüpunkt statt Dashboard-Schaltfläche, Link in der Mandantenauswahl entfällt.
2. Menüeinträge erhalten optional `roles` (serverseitig gefiltert, `superadmin` sieht alles); Pflege im Menü-Editor folgt mit dem Rollenkonzept.
3. Menü-Handler `go_mandant_create` und feste Route `/mandant/new` statt allgemeinem `go_route`.
4. Ein Endpunkt `POST /api/mandanten/create` (Satz, Zuweisung, Datenbank); `/save` entfällt; Satz vor Datenbank, kein Rollback.
5. Datenbank standardmäßig im selben Schritt einrichten (`setup_database = true`).
6. Nach Erfolg Ergebnisfenster und Abmeldung per Bestätigung; bei Teilfehler keine Abmeldung.
7. Prüfung der Mandantenwahl gegen `MANDANTEN.LIST` wird vorgezogen (Abschnitt 7).

## 9. Umsetzungsschritte

1. `select` gegen `MANDANTEN.LIST` prüfen, Listen-Endpunkte filtern, Tests.
2. `roles` am Menüeintrag: Filter in `menu.py`, Test, Doku (Regel 2.2).
3. `mandant_setup_service.create_mandant`, Endpunkt `/create`, alten Code (`/save`, altes `/create`) entfernen, Tests.
4. Frontend: Seite `/mandant/new`, Handler `go_mandant_create`, Ergebnisfenster mit Abmeldung; Dashboard, Mandantenauswahl und `App.tsx` bereinigen.
5. Seed für den Menüeintrag (Dry-Run, Apply mit Snapshot), Typprüfung, Build, Theme-Guard, Gesamttests.
6. Doku nachziehen; manueller Test mit einem Testmandanten.

## 10. Offen (nicht Teil von G)

- Zuweisung weiterer Benutzer zu einem neuen Mandanten (Pflege von `MANDANTEN.LIST` im Benutzersatz, evtl. Aktion „Mandant zuweisen“).
- Vollständiges Rollenkonzept für Menüeinträge (Pflege, Vorlagen).
- Dashboard (`/dashboard`) insgesamt: noch gebraucht oder durch Menü und Startseite ersetzt.
