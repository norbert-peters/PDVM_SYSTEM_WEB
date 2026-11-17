/**
 * Feste Oberflaechentexte des Renderers (Schluessel -> Text je Sprache, Deutsch ist Rueckfall).
 *
 * Einziger Einstiegspunkt fuer Texte, die nicht aus den Daten (Controls, Frames) stammen; Aufrufer verwenden `uiText(key)`.
 * Die Sprache kommt aus `uiLanguage.ts` (zuletzt benutzte Sitzungssprache, sonst Browsersprache). Weitere Sprachen: Woerterbuch
 * ergaenzen und `UiLanguage` erweitern (Rendering-Spec, Abschnitt 7, Nr. 8).
 */
import { uiLanguage, type UiLanguage } from './uiLanguage'

const TEXTS = {
  'action.cancel': 'Abbrechen',
  'action.confirm': 'Ausführen',
  'action.confirmAnyway': 'Trotzdem ausführen',
  'action.running': 'Läuft…',
  'action.dirtyWarning':
    'Es gibt ungespeicherte Änderungen. Die Aktion wirkt auf den gespeicherten Stand; lädt sie den Datensatz neu, gehen die Änderungen verloren. Abbrechen, um zuerst zu speichern.',
  'action.resultTitle': 'Ergebnis',
  'action.failedTitle': 'Aktion fehlgeschlagen',
  'action.failedFallback': 'Aktion fehlgeschlagen',
  'action.relogin': 'Zur Anmeldung',
  'form.passwordMismatch': 'Die Passwörter stimmen nicht überein',
  'login.title': 'PDVM System',
  'login.subtitle': 'Business Management Platform',
  'login.submit': 'Anmelden',
  'login.submitBusy': 'Anmeldung läuft…',
  'login.forgotLink': 'Passwort vergessen?',
  'login.loading': 'Anmeldemaske wird geladen…',
  'login.failed': 'Anmeldung fehlgeschlagen',
  'login.back': 'Zurück zur Anmeldung',
  'login.forgot.title': 'Passwort vergessen',
  'login.forgot.hint': 'Bitte geben Sie Ihren Benutzer und die dort hinterlegte E-Mail-Adresse ein. Stimmen beide, wird ein maschinelles Passwort per E-Mail gesendet; das bisherige Passwort wird dabei ungültig und beim nächsten Login muss ein neues vergeben werden.',
  'login.forgot.submit': 'Senden',
  'login.forgot.sent': 'Falls die Angaben stimmen, wurde ein maschinelles Passwort versendet.',
  'login.forgot.failed': 'E-Mail konnte nicht gesendet werden',
  'login.change.title': 'Passwort ändern',
  'login.change.hint': 'Sie müssen ein neues Passwort vergeben.',
  'login.change.submit': 'Speichern',
  'login.change.failed': 'Passwortänderung fehlgeschlagen',
  'login.fallback.email': 'E-Mail',
  'login.fallback.benutzer': 'Benutzer',
  'login.fallback.storedEmail': 'Hinterlegte E-Mail-Adresse',
  'login.fallback.password': 'Passwort',
} as const

export type UiTextKey = keyof typeof TEXTS

const TEXTS_EN: Record<UiTextKey, string> = {
  'action.cancel': 'Cancel',
  'action.confirm': 'Run',
  'action.confirmAnyway': 'Run anyway',
  'action.running': 'Running…',
  'action.dirtyWarning':
    'There are unsaved changes. The action works on the saved state; if it reloads the record, the changes are lost. Cancel to save first.',
  'action.resultTitle': 'Result',
  'action.failedTitle': 'Action failed',
  'action.failedFallback': 'Action failed',
  'action.relogin': 'Back to sign-in',
  'form.passwordMismatch': 'The passwords do not match',
  'login.title': 'PDVM System',
  'login.subtitle': 'Business Management Platform',
  'login.submit': 'Sign in',
  'login.submitBusy': 'Signing in…',
  'login.forgotLink': 'Forgot password?',
  'login.loading': 'Loading sign-in form…',
  'login.failed': 'Sign-in failed',
  'login.back': 'Back to sign-in',
  'login.forgot.title': 'Forgot password',
  'login.forgot.hint': 'Please enter your user name and the email address stored for it. If both match, a machine-generated password is sent by email; your previous password becomes invalid and you must set a new one at the next sign-in.',
  'login.forgot.submit': 'Send',
  'login.forgot.sent': 'If the details are correct, a machine-generated password has been sent.',
  'login.forgot.failed': 'The email could not be sent',
  'login.change.title': 'Change password',
  'login.change.hint': 'You must set a new password.',
  'login.change.submit': 'Save',
  'login.change.failed': 'Password change failed',
  'login.fallback.email': 'Email',
  'login.fallback.benutzer': 'User',
  'login.fallback.storedEmail': 'Stored email address',
  'login.fallback.password': 'Password',
}

const DICTIONARIES: Record<UiLanguage, Record<UiTextKey, string>> = { de: TEXTS, en: TEXTS_EN }

export function uiText(key: UiTextKey): string {
  return DICTIONARIES[uiLanguage()][key] ?? TEXTS[key]
}
