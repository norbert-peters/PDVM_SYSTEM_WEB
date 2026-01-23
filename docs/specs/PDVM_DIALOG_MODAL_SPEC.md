# PDVM Dialog Modal – Spec v0

## Ziel
`PdvmDialogModal` ist das **Standard-Modal** für einfache Benutzer-Interaktionen im Frontend:

- **Info** (Hinweis anzeigen)
- **Confirm** (Bestätigen/Abbrechen)
- **Form** (1..n Felder abfragen, inkl. Validierung)

Es ersetzt bewusst die Browser-Dialoge (`window.alert/confirm/prompt`), damit:
- Styling/Theming konsistent bleibt
- Validierung und Fehler sauber in der UI erfolgen
- Busy-/Async-Zustände möglich sind
- Verhalten plattformübergreifend gleich ist

---

## Ort im Code
- Component: [frontend/src/components/common/PdvmDialogModal.tsx](../../frontend/src/components/common/PdvmDialogModal.tsx)
- Styles: [frontend/src/components/common/PdvmDialogModal.css](../../frontend/src/components/common/PdvmDialogModal.css)

---

## API (Props)

### Pflicht
- `open: boolean` – steuert Sichtbarkeit
- `title: string` – Titelzeile
- `onCancel: () => void` – schließt das Modal (Cancel/Overlay/Escape)

### Optional
- `kind?: 'info' | 'confirm' | 'form'` (Default: `confirm`)
- `message?: ReactNode` – Text/Content im Body
- `fields?: PdvmDialogModalField[]` – Formfelder (nur relevant für `form`)
- `initialValues?: Record<string,string>` – Default-Werte pro Feldname

- `confirmLabel?: string` (Default: `OK`/`Erstellen` je Usecase)
- `cancelLabel?: string` (Default: `Abbrechen`)

- `busy?: boolean` – sperrt UI (Buttons/Inputs)
- `error?: string | null` – Error-Text vom Caller (z.B. API-Fehler)

- `onConfirm?: (values: Record<string,string>) => void | Promise<void>`
  - Bei `kind='info'` kann `onConfirm` auch einfach schließen.
  - Bei `kind='form'` enthält `values` die String-Werte der Felder.

---

## Fields (Form)
`fields` ist ein Array von Feld-Definitionen:

- `name: string` – Key im `values`
- `label: string` – UI Label
- `type?: 'text' | 'textarea' | 'number'` (Default: `text`)
- `placeholder?: string`
- `required?: boolean`
- `minLength?: number`
- `maxLength?: number`
- `autoFocus?: boolean` – setzt initialen Fokus

Validierung:
- passiert **im Modal**, bevor `onConfirm` aufgerufen wird
- Fehler werden im Modal angezeigt

---

## UX/Interaktion
- Klick auf Overlay schließt (wie `Cancel`), außer `busy=true`
- `Escape` schließt (wie `Cancel`), außer `busy=true`
- `Enter` bestätigt (außer wenn Fokus auf `<textarea>`)

---

## Best Practices

### 1) Keine Browser-Dialoge
❌ `window.alert(...)`, `window.confirm(...)`, `window.prompt(...)`

✅ Stattdessen immer `PdvmDialogModal` nutzen (Theming, Busy, Errors).

### 2) Async confirm
Wenn `onConfirm` async ist:
- `busy` über den Caller setzen (z.B. React Query Mutation `isPending`)
- API-Fehler via `error` anzeigen

### 3) Wiederverwendbarkeit
- **Info**: Meldungen/Hinweise
- **Confirm**: destructive actions (z.B. „Änderungen verwerfen?“)
- **Form**: einfache Eingaben (z.B. „Name für neuen Datensatz“)
