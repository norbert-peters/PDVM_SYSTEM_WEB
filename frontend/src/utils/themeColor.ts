/**
 * Vorschlag der naechstgelegenen Farbe mit ausreichendem Kontrast (Spiegel von backend/app/core/theme_color.py).
 *
 * Nur die Helligkeit (OKLab-L) wird veraendert, Farbton und -- soweit im sRGB-Gamut moeglich -- die Saettigung
 * bleiben erhalten. Gesucht wird in beide Richtungen die kleinste Aenderung, die den Kontrast erreicht.
 */
import { parseCssColor } from './themeTokens'

const STEP = 0.0025

type Rgb = [number, number, number]

function luminance([r, g, b]: Rgb): number {
  const ch = (c: number) => {
    const s = c / 255
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4)
  }
  return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)
}

function ratio(a: Rgb, b: Rgb): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

const toLinear = (c: number) => {
  const s = c / 255
  return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4)
}

const fromLinear = (x: number) => {
  const v = Math.min(1, Math.max(0, x))
  return v <= 0.0031308 ? 12.92 * v : 1.055 * Math.pow(v, 1 / 2.4) - 0.055
}

function rgbToOklab([r, g, b]: Rgb): [number, number, number] {
  const lr = toLinear(r)
  const lg = toLinear(g)
  const lb = toLinear(b)
  const l = Math.cbrt(0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb)
  const m = Math.cbrt(0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb)
  const s = Math.cbrt(0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb)
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ]
}

function oklabToLinear(L: number, a: number, b: number): Rgb {
  const l = Math.pow(L + 0.3963377774 * a + 0.2158037573 * b, 3)
  const m = Math.pow(L - 0.1055613458 * a - 0.0638541728 * b, 3)
  const s = Math.pow(L - 0.0894841775 * a - 1.291485548 * b, 3)
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ]
}

const inGamut = (rgb: Rgb) => rgb.every((c) => c >= -1e-6 && c <= 1 + 1e-6)

/** Python rundet "halb zu gerade", JS "halb nach oben"; fuer identische Ergebnisse wie dort rechnen. */
function roundHalfEven(x: number): number {
  const f = Math.floor(x)
  const d = x - f
  if (d < 0.5) return f
  if (d > 0.5) return f + 1
  return f % 2 === 0 ? f : f + 1
}

function lchToRgb(L: number, C: number, h: number): Rgb {
  const a = Math.cos(h)
  const b = Math.sin(h)
  let lin = oklabToLinear(L, C * a, C * b)
  if (!inGamut(lin)) {
    let lo = 0
    let hi = C
    for (let i = 0; i < 24; i += 1) {
      const mid = (lo + hi) / 2
      if (inGamut(oklabToLinear(L, mid * a, mid * b))) lo = mid
      else hi = mid
    }
    lin = oklabToLinear(L, lo * a, lo * b)
  }
  return lin.map((c) => roundHalfEven(fromLinear(c) * 255)) as Rgb
}

const toHex = (rgb: Rgb) => `#${rgb.map((c) => c.toString(16).padStart(2, '0')).join('')}`

function opaque(value: unknown): Rgb | null {
  const c = parseCssColor(value)
  return c && c.a >= 1 ? [c.r, c.g, c.b] : null
}

export type ColorSuggestion = { color: string; ratio: number }

/** Naechstgelegene Farbe mit Kontrast >= min zu `against`; null, wenn nicht auswertbar oder nicht erreichbar. */
export function suggestCompliantColor(color: unknown, against: unknown, min: number): ColorSuggestion | null {
  const fg = opaque(color)
  const bg = opaque(against)
  if (!fg || !bg) return null
  const current = ratio(fg, bg)
  if (current >= min) return { color: toHex(fg), ratio: Math.round(current * 100) / 100 }

  const [L0, a0, b0] = rgbToOklab(fg)
  const C = Math.hypot(a0, b0)
  const h = Math.atan2(b0, a0)

  let best: { dist: number; rgb: Rgb } | null = null
  for (const direction of [1, -1]) {
    const steps = Math.floor(1 / STEP) + 1
    for (let i = 1; i < steps; i += 1) {
      const L = L0 + direction * i * STEP
      if (L < 0 || L > 1) break
      const rgb = lchToRgb(L, C, h)
      if (ratio(rgb, bg) >= min) {
        if (!best || Math.abs(L - L0) < best.dist) best = { dist: Math.abs(L - L0), rgb }
        break
      }
    }
  }

  if (!best) {
    const candidates: Rgb[] = [[0, 0, 0], [255, 255, 255]]
    const rgb = candidates.sort((x, y) => ratio(y, bg) - ratio(x, bg))[0]
    if (ratio(rgb, bg) < min) return null
    best = { dist: 0, rgb }
  }
  return { color: toHex(best.rgb), ratio: Math.round(ratio(best.rgb, bg) * 100) / 100 }
}

/** Unterschied der OKLab-Helligkeit (Mass fuer die Staerke der Aenderung). */
export function lightnessDistance(a: unknown, b: unknown): number {
  const ca = opaque(a)
  const cb = opaque(b)
  if (!ca || !cb) return Infinity
  return Math.abs(rgbToOklab(ca)[0] - rgbToOklab(cb)[0])
}
