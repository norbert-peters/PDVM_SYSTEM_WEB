/**
 * Sprache der Oberflaeche vor und nach der Anmeldung.
 *
 * Vor der Anmeldung sind weder Benutzer noch Mandant bekannt. Deshalb merkt sich der Browser die zuletzt benutzte
 * Sitzungssprache (Antwort von `/mandanten/select`: `USER.SETTINGS.LANGUAGE`, sonst `CONFIG.DEFAULT_LANGUAGE`) und
 * verwendet sie fuer die naechste Anmeldemaske; ohne gemerkte Sprache gilt die Browsersprache. Bleibt beim Abmelden erhalten.
 */
const LAST_LANGUAGE_KEY = 'pdvm_last_language'

export type UiLanguage = 'de' | 'en'

export function rememberLanguage(value: string | null | undefined): void {
  const language = String(value ?? '').trim()
  if (language) localStorage.setItem(LAST_LANGUAGE_KEY, language)
}

/** Gemerkte Sprache, sonst Browsersprache (z. B. `EN-US`, `de-DE`); `undefined`, wenn beides fehlt. */
export function preferredLanguage(): string | undefined {
  const stored = typeof localStorage !== 'undefined' ? localStorage.getItem(LAST_LANGUAGE_KEY) : null
  return stored || (typeof navigator !== 'undefined' ? navigator.language : undefined) || undefined
}

/** Sprache fuer die festen Texte; ohne Woerterbuch fuer die Sprache gilt Deutsch. */
export function uiLanguage(): UiLanguage {
  return String(preferredLanguage() ?? '').toLowerCase().startsWith('en') ? 'en' : 'de'
}
