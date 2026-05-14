# Datenversionierung Phase B - Rollenmodell (admin + develop)

Status: umgesetzt (Backend-Guards)

## 1. Ziel

Fuer den Datenversionierungs-Workflow wird ein abgestuftes Rollenmodell verwendet:

1. develop darf pruefen/validieren,
2. admin darf anwenden (apply).

So bleibt produktives Schreiben kontrolliert, waehrend develop den kompletten Vorpruefungs-Workflow nutzen kann.

## 2. Zentrale Security-Regeln

Datei:
- backend/app/core/security.py

Neue zentrale Funktionen:
- has_develop_rights(current_user)
- has_admin_or_develop_rights(current_user)
- require_admin_or_develop_user(...)

Unterstuetzte Quellen fuer Rollen:
- user_data.SECURITY.ROLE
- user_data.SECURITY.ROLES (Liste oder CSV)

Admin-Erkennung bleibt unveraendert ueber:
- user_data.SECURITY.IS_ADMIN
- user_data.SECURITY.ROLE in (admin, superadmin)

## 3. Release-API Rechte-Matrix

Datei:
- backend/app/api/releases.py

### 3.1 Operator-Zugriff

`require_release_operator` nutzt zentral `require_admin_or_develop_user`.

### 3.2 Endpunktverhalten

- dry_run in Release-Apply/Import-Endpunkten:
  - admin: erlaubt
  - develop: erlaubt

- apply (produktives Schreiben):
  - admin: erlaubt
  - develop: verboten (HTTP 403)

Damit ist die Trennung "sichtbar/validierbar" vs. "anwenden" serverseitig erzwungen.

## 4. Architekturkonformitaet

1. Keine SQL-Logik in Routern fuer Rollenentscheidungen.
2. Rollenlogik liegt zentral im Security-Layer.
3. Release-Router bleibt schlank und nutzt zentrale Dependencies.

## 5. Auswirkungen auf naechste Schritte

1. Dialog/View-Sichtbarkeit kann auf dieselbe Rollenlogik aufsetzen.
2. UI darf fuer develop Apply-Aktionen deaktivieren.
3. Backend bleibt die letzte Instanz: Apply ohne Admin wird immer abgelehnt.
