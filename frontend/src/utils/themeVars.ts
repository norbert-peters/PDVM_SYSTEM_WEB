/**
 * Theme-Variablen: Benennung der CSS-Variablen und Umwandlung von Tokens in Style-Objekte.
 * Einzige Stelle fuer die Namenskonvention --<gruppe>-<token> (ThemeContext und Vorschau nutzen sie).
 */

export type ThemeTokens = Record<string, Record<string, string>>

export function themeVarName(group: string, token: string): string {
  return `--${group.replace(/_/g, '-')}-${token.replace(/_/g, '-')}`
}

/** {gruppe: {token: wert}} -> {'--gruppe-token': wert} */
export function themeTokensToCssVars(tokens: ThemeTokens | null | undefined): Record<string, string> {
  const vars: Record<string, string> = {}
  Object.entries(tokens || {}).forEach(([group, entries]) => {
    Object.entries(entries || {}).forEach(([token, value]) => {
      vars[themeVarName(group, token)] = String(value)
    })
  })
  return vars
}
