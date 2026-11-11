/**
 * Kontrastpruefung der Pflichtpaare im Editor (Spiegel von theme_service.contrast_violations).
 * Die Paare samt CSS-Fallback-Ketten kommen aus dem Katalog (GET /api/layout/catalog -> contrast_pairs).
 * Massgeblich bleibt die Serverpruefung; hier entsteht die direkte Rueckmeldung und der Vorschlag.
 */
import { contrastRatio } from './themeTokens'
import { suggestCompliantColor } from './themeColor'
import type { ThemeTokens } from './themeVars'

export interface ContrastPair {
  fg: string
  bg: string
  min: number
  fg_chain: string[]
  bg_chain: string[]
}

export interface ContrastSuggestion {
  ref: string
  value: string
  ratio: number
}

export interface PairEvaluation {
  pair: ContrastPair
  ratio: number
  fgValue: string
  bgValue: string
  fgSource: string
  bgSource: string
  /** Seite wird durch das Overlay veraendert (wirksamer Wert stammt aus einem Overlay-Token) */
  fgChanged: boolean
  bgChanged: boolean
  suggestions: ContrastSuggestion[]
}

function tokenValue(tokens: ThemeTokens, ref: string): string {
  const [group, ...rest] = ref.split('.')
  return tokens[group]?.[rest.join('.')] ?? ''
}

/** Wirksamer Wert entlang der Fallback-Kette und das Token, aus dem er stammt. */
export function effectiveTokenValue(tokens: ThemeTokens, chain: string[]): { value: string; source: string } {
  for (const ref of chain) {
    const value = tokenValue(tokens, ref)
    if (value.trim()) return { value, source: ref }
  }
  return { value: '', source: chain[0] }
}

/** Alle Paare unter dem Mindestkontrast; `touched` = Tokens, die das Overlay setzt. */
export function evaluatePairs(tokens: ThemeTokens, pairs: ContrastPair[], touched: Set<string>): PairEvaluation[] {
  const result: PairEvaluation[] = []
  pairs.forEach((pair) => {
    const fg = effectiveTokenValue(tokens, pair.fg_chain)
    const bg = effectiveTokenValue(tokens, pair.bg_chain)
    const ratio = contrastRatio(fg.value, bg.value)
    if (ratio === null || ratio >= pair.min) return
    const fgChanged = touched.has(fg.source)
    const bgChanged = touched.has(bg.source)
    const suggestions: ContrastSuggestion[] = []
    ;([[fgChanged, fg, bg], [bgChanged, bg, fg]] as const).forEach(([changed, side, other]) => {
      if (!changed) return
      const s = suggestCompliantColor(side.value, other.value, pair.min)
      if (s) suggestions.push({ ref: side.source, value: s.color, ratio: s.ratio })
    })
    result.push({ pair, ratio, fgValue: fg.value, bgValue: bg.value, fgSource: fg.source, bgSource: bg.source, fgChanged, bgChanged, suggestions })
  })
  return result
}
