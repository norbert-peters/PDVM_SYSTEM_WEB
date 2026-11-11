/**
 * Clientseitige Pruefung/Berechnung fuer Theme-Tokens (Spiegel von backend/app/core/theme_service.py).
 * Massgeblich bleibt die Serverpruefung; diese Funktionen dienen der direkten Rueckmeldung in den Controls.
 */

const HEX = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/
const RGB = /^rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(?:,\s*(0|1|0?\.\d+|1\.0+)\s*)?\)$/
const HSL = /^hsla?\(\s*\d{1,3}(?:\.\d+)?\s*,\s*\d{1,3}%\s*,\s*\d{1,3}%\s*(?:,\s*(?:0|1|0?\.\d+)\s*)?\)$/
const VAR = /^var\(--[a-z0-9-]+\)$/
const COLOR_KEYWORDS = new Set(['transparent', 'inherit', 'currentcolor'])
const LENGTH_ATOM = '(?:0|\\d+(?:\\.\\d+)?(?:px|rem|em|%))'
const LENGTH = new RegExp(`^${LENGTH_ATOM}(?:\\s+${LENGTH_ATOM}){0,3}$`)
const BORDER = /^(\d+(?:\.\d+)?px)\s+(solid|dashed|dotted|double)\s+(.+)$/
const FONT_CHARS = /^[A-Za-z0-9 _,'"-]+$/
const FORBIDDEN = /[;{}<>\\]|url\s*\(|expression\s*\(|@import|\/\*/i

export type Rgba = { r: number; g: number; b: number; a: number }

export function parseCssColor(value: unknown): Rgba | null {
  if (typeof value !== 'string') return null
  const text = value.trim()
  if (HEX.test(text)) {
    let h = text.slice(1)
    if (h.length === 3 || h.length === 4) h = h.split('').map((c) => c + c).join('')
    const r = parseInt(h.slice(0, 2), 16)
    const g = parseInt(h.slice(2, 4), 16)
    const b = parseInt(h.slice(4, 6), 16)
    const a = h.length === 8 ? parseInt(h.slice(6, 8), 16) / 255 : 1
    return { r, g, b, a }
  }
  const m = RGB.exec(text)
  if (m) {
    const [r, g, b] = [Number(m[1]), Number(m[2]), Number(m[3])]
    if (Math.max(r, g, b) > 255) return null
    return { r, g, b, a: m[4] !== undefined ? Number(m[4]) : 1 }
  }
  return null
}

function luminance({ r, g, b }: Rgba): number {
  const channel = (c: number) => {
    const s = c / 255
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4)
  }
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
}

/** WCAG-Kontrastverhaeltnis; null bei nicht auswertbaren oder transparenten Farben. */
export function contrastRatio(fg: unknown, bg: unknown): number | null {
  const a = parseCssColor(fg)
  const b = parseCssColor(bg)
  if (!a || !b || a.a < 1 || b.a < 1) return null
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return Math.round(((hi + 0.05) / (lo + 0.05)) * 100) / 100
}

/** #rrggbb fuer das native Farbfeld (Alpha wird verworfen); null, wenn nicht umrechenbar. */
export function toHexColor(value: unknown): string | null {
  const c = parseCssColor(value)
  if (!c) return null
  const hex = (n: number) => n.toString(16).padStart(2, '0')
  return `#${hex(c.r)}${hex(c.g)}${hex(c.b)}`
}

function isSafe(text: string): boolean {
  return text.length > 0 && text.length <= 200 && !FORBIDDEN.test(text)
}

export function isValidColor(value: string): boolean {
  const text = value.trim()
  if (!isSafe(text)) return false
  if (HEX.test(text) || HSL.test(text) || VAR.test(text) || COLOR_KEYWORDS.has(text.toLowerCase())) return true
  return RGB.test(text) && parseCssColor(text) !== null
}

export function isValidLength(value: string): boolean {
  const text = value.trim()
  return isSafe(text) && LENGTH.test(text)
}

export function parseBorder(value: string): { width: string; style: string; color: string } | null {
  const text = value.trim()
  if (text.toLowerCase() === 'none') return { width: '0px', style: 'none', color: '' }
  const m = BORDER.exec(text)
  return m ? { width: m[1], style: m[2], color: m[3] } : null
}

export function isValidBorder(value: string): boolean {
  const text = value.trim()
  if (!isSafe(text)) return false
  const parsed = parseBorder(text)
  return !!parsed && (parsed.style === 'none' || isValidColor(parsed.color))
}

export function isValidFontFamily(value: string): boolean {
  const text = value.trim()
  return isSafe(text) && FONT_CHARS.test(text)
}

/** Pattern der Mandanten-Freigabe (``color.primary-*``): '*' = beliebige Zeichen, sonst exakt */
export function refMatchesPattern(ref: string, pattern: string): boolean {
  const escaped = pattern.trim().replace(/[.+?^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*')
  return new RegExp(`^${escaped}$`).test(ref)
}

/** Liest den aktuellen Wert einer CSS-Variable vom Wurzelelement (z. B. '--color-background-primary'). */
export function readRootCssVar(name: string): string {
  if (typeof document === 'undefined') return ''
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}
