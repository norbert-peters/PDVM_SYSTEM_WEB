# Datenversionierung Phase C - UI Sichtbarkeit und Action-Gating

Status: umgesetzt (Frontend)

## 1. Ziel

Phase C setzt das Rollenmodell aus Phase B in der UI durch:

1. develop darf Workflow sehen und validieren,
2. apply-aehnliche Aktionen sind nur fuer admin freigegeben.

Backend-Guards bleiben weiterhin die letzte Instanz.

## 2. Umgesetzte Stellen

### 2.1 Rollen-Capabilities im Auth-Context

Datei:
- frontend/src/contexts/AuthContext.tsx

Neu:
- Rollen werden aus user_data.SECURITY.ROLE und user_data.SECURITY.ROLES normalisiert.
- IS_ADMIN wird als admin-Rolle interpretiert.
- Context liefert:
  - canReleaseValidate
  - canReleaseApply

### 2.2 Workflow Action-Control Gating

Datei:
- frontend/src/components/dialogs/PdvmDialogPage.tsx

Neu:
- apply-aehnliche Action-Controls werden ueber Label/Config/Control-Tokens erkannt.
- In Workflow-Dialogen (work/acti) gilt:
  - develop (validate ja, apply nein): Apply-Action ist disabled.
  - admin: Apply-Action bleibt aktiv.

### 2.3 Import-Editor Apply-Gating

Datei:
- frontend/src/components/dialogs/PdvmImportDataEditor.tsx

Neu:
- Props fuer Rollensteuerung:
  - canApplyWrite
  - applyDeniedMessage
- Speichern/Apply ist disabled, wenn canApplyWrite=false.
- UI zeigt Hinweistext fuer gesperrte Apply-Aktion.

Datei:
- frontend/src/components/dialogs/PdvmDialogPage.tsx

Integration:
- Workflow-Rollenstatus wird in den Import-Editor durchgereicht.

## 3. Verbindliche Regeln fuer Folgearbeiten

1. Rollenlogik nicht duplizieren
- Rollen-Capabilities aus Auth-Context oder zentralen Guards nutzen.

2. UI ist Komfort, Backend ist Autoritaet
- Auch wenn UI disabled ist, muss Backend-Guard Apply weiterhin hart pruefen.

3. Workflow-spezifische Restriktionen nur im Workflow-Kontext
- Apply-Sperre fuer develop gilt in work/acti-Dialogen.

4. Aktionen semantisch klassifizieren
- Apply-relevante Actions muessen eindeutig benannt/konfiguriert werden, damit Gating stabil bleibt.

## 4. Test-Checkliste

1. Login mit develop-Rolle:
- Workflow sichtbar
- Apply-aehnliche Action disabled
- Dry-run/Validierung erreichbar

2. Login mit admin-Rolle:
- Apply-Aktionen aktiv
- Release-Apply-Endpunkte nutzbar

3. Direktes API-Apply mit develop:
- Muss serverseitig mit 403 abgelehnt werden (Phase B).
