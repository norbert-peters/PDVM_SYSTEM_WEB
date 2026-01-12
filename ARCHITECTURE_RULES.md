# PDVM System Web - Architekturregeln

Dieses Dokument definiert die verbindlichen Architektur-Regeln für die Weiterentwicklung des PDVM Systems. Ziel ist die Stabilität und Wartbarkeit bei wachsender Komplexität.

## 1. Backend Architektur

### 1.1 Das "Central Database" Gesetz
**Regel:** Es gibt keinen direkten Datenbank-Zugriff in den API-Endpunkten (Routers).

*   ❌ **VERBOTEN:** SQL-Queries (`SELECT...`) oder direkter Zugriff auf JSON-Strukturen (`row['daten']['GRUND']`) im Router.
*   ✅ **PFLICHT:** Nutzung der Business-Logic Klasse `PdvmCentralDatabase`.

```python
# Richtig:
menu = await PdvmCentralDatabase.load("sys_menudaten", guid, system_pool)
items = menu.get_value_by_group("GRUND")

# Falsch:
row = await db.fetch_row(query)
items = row["daten"]["GRUND"]  # Umgeht Historisierung und Logik!
```

### 1.2 Single Source of Configuration
**Regel:** Es gibt keine hardcodierten Verbindungsdaten für Mandanten- oder System-Datenbanken (`config.py`).

*   Die einzige statisch bekannte Datenbank ist die **AUTH-DB**.
*   Alle anderen Verbindungen (System, Mandant) **MÜSSEN** dynamisch über den `ConnectionManager` und die Tabelle `sys_mandanten` bezogen werden.
*   **Warum?** Mandanten können auf verschiedenen Servern liegen. Hardcoded URLs in `config.py` (wie `DATABASE_URL_MANDANT`) sind veraltet und dürfen nicht genutzt werden.

### 1.3 Factory Pattern für Datensätze
**Regel:** Instanzierung von Business-Objekten immer über die asynchrone Factory-Methode `.load()`.

*   ❌ `obj = PdvmCentralDatabase(...)` (Lädt keine Daten, fehleranfällig)
*   ✅ `obj = await PdvmCentralDatabase.load(...)` (Erzeugt Instanz UND lädt Daten korrekt)

---

## 2. Frontend Architektur (React)

### 2.1 Context over Props
**Regel:** Globale Zustände (Auth, Mandant, Theme) gehören in React Context Provider.

*   ❌ **VERBOTEN:** "Prop-Drilling" von `token` oder `mandantId` durch mehr als 2 Ebenen.
*   ✅ **PFLICHT:** Nutzung von `useAuth()` für Benutzerkontext und `useMenu()` für App-Steuerung.

### 2.2 Strikte Menü-Struktur
**Regel:** Das UI-Layout akzeptiert nur definierte Menü-Gruppen.

*   **GRUND:** Horizontale Menüleiste oben (App-Umschaltung, Tools).
*   **VERTIKAL:** Sidebar links (Navigation innerhalb der App).
*   ❌ **VERBOTEN:** Erfindung neuer Gruppen (z.B. "ZUSATZ", "FOOTER") ohne Anpassung des `MenuRenderer`.
*   Das Frontend ist "dumm" und rendert generisch, was die API liefert, aber nur in diesen zwei Containern.

### 2.3 API-Layer Separierung
**Regel:** Keine direkten HTTP-Calls (`fetch`, `axios`) in Komponenten.

*   Alle Netzwerk-Anfragen müssen in `src/api/client.ts` oder entsprechenden API-Modulen definiert sein.
*   Dies sichert konsistentes Error-Handling (z.B. 401 Redirects) und Token-Injection.

---

## 3. Legacy Code
Code, der als `DEPRECATED` markiert ist (insb. in `config.py`), darf nicht für neue Features verwendet werden. Bei Berührung mit solchem Code ist Refactoring (Anpassung an neue Regeln) vorzuziehen.
