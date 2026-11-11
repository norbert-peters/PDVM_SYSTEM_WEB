/**
 * Layout-Varianten (Strukturkatalog, P5): setzt die aufgeloesten Varianten als Attribute auf <html>.
 * Beispiel: { header: 'kompakt' } -> <html data-layout-header="kompakt">. Das CSS dazu steht in
 * styles/layouts/variants.css; "standard" braucht keine Regeln und wird trotzdem gesetzt.
 */
const PREFIX = 'data-layout-'

export function applyLayoutAttributes(layout: Record<string, string> | null | undefined): void {
  const root = document.documentElement
  const wanted = layout || {}

  Array.from(root.attributes)
    .map((a) => a.name)
    .filter((name) => name.startsWith(PREFIX) && !(name.slice(PREFIX.length) in wanted))
    .forEach((name) => root.removeAttribute(name))

  Object.entries(wanted).forEach(([area, option]) => {
    if (option) root.setAttribute(`${PREFIX}${area}`, option)
  })
}
