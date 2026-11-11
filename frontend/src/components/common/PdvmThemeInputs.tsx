/**
 * Theme-Eingabecontrols fuer PdvmInputControl (Typen: color, css_length, css_border, font_family).
 * Die Controls sind reine Wertkomponenten (value/onChange); Rahmen, Label und Hilfe liefert PdvmInputControl.
 * Leerer Wert bedeutet "nicht ueberschrieben" (Overlay-Prinzip).
 */
import { useEffect, useState } from 'react'
import {
  contrastRatio,
  isValidBorder,
  isValidColor,
  isValidFontFamily,
  isValidLength,
  parseBorder,
  toHexColor,
} from '../../utils/themeTokens'
import { suggestCompliantColor } from '../../utils/themeColor'
import './PdvmThemeInputs.css'

type BaseProps = {
  id?: string
  value: string
  onChange: (value: string) => void
  onBlur?: () => void
  disabled?: boolean
  placeholder?: string
}

/** Textfeld mit lokalem Entwurf: gueltige Werte (und leer) gehen sofort nach oben, ungueltige zeigen eine Meldung. */
function useValidatedDraft(value: string, validate: (v: string) => boolean, onChange: (v: string) => void, message: string) {
  const invalidInitially = (v: string) => (v.trim() && !validate(v) ? message : null)
  const [draft, setDraft] = useState(value)
  const [error, setError] = useState<string | null>(invalidInitially(value))

  useEffect(() => {
    setDraft(value)
    setError(invalidInitially(value))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])

  const update = (next: string) => {
    setDraft(next)
    if (!next.trim()) {
      setError(null)
      onChange('')
    } else if (validate(next)) {
      setError(null)
      onChange(next.trim())
    } else {
      setError(message)
    }
  }
  return { draft, error, update }
}

export function PdvmColorInput(props: BaseProps & {
  contrast?: { against: string; min: number; label?: string } | null
}) {
  const { draft, error, update } = useValidatedDraft(props.value, isValidColor, props.onChange, 'Ungültige Farbe (Hex-Wert wie in der Palette oder rgb-Angabe)')
  // Das native Farbfeld verlangt zwingend einen Hex-Wert, auch wenn noch nichts gesetzt ist.
  const swatchValue = toHexColor(draft) || toHexColor(props.placeholder) || toHexColor(props.contrast?.against) || '#000000' // guard-allow-color
  const ratio = props.contrast && !error ? contrastRatio(draft, props.contrast.against) : null
  const contrastOk = ratio !== null && props.contrast ? ratio >= props.contrast.min : null
  // Nur eigene Eingaben bekommen einen Vorschlag; Werte aus dem Theme (Platzhalter) sind nicht Gegenstand der Eingabe.
  const suggestion = contrastOk === false && props.contrast && draft.trim()
    ? suggestCompliantColor(draft, props.contrast.against, props.contrast.min)
    : null

  return (
    <div className="pdvm-theme-input">
      <div className="pdvm-theme-input__row">
        <input
          type="color"
          className="pdvm-theme-input__swatch"
          aria-label="Farbe wählen"
          value={swatchValue}
          disabled={props.disabled}
          onChange={(e) => update(e.target.value)}
        />
        <input
          id={props.id}
          type="text"
          className="pdvm-pic__input"
          value={draft}
          placeholder={props.placeholder || '(vom Theme übernommen)'}
          disabled={props.disabled}
          spellCheck={false}
          onChange={(e) => update(e.target.value)}
          onBlur={props.onBlur}
        />
        {ratio !== null ? (
          <span
            className={`pdvm-theme-input__badge ${contrastOk ? 'pdvm-theme-input__badge--ok' : 'pdvm-theme-input__badge--fail'}`}
            title={`Kontrast zu ${props.contrast?.label || 'Gegenfarbe'}: ${ratio}:1 (mind. ${props.contrast?.min}:1)`}
          >
            {ratio}:1 {contrastOk ? 'AA ✓' : `< ${props.contrast?.min}`}
          </span>
        ) : null}
      </div>
      {suggestion ? (
        <button
          type="button"
          className="pdvm-theme-input__suggest"
          disabled={props.disabled}
          title={`Nächstgelegene Farbe mit ausreichendem Kontrast (${suggestion.ratio}:1)`}
          onClick={() => update(suggestion.color)}
        >
          <span className="pdvm-theme-input__suggestSwatch" style={{ background: suggestion.color }} />
          Vorschlag übernehmen: {suggestion.color} ({suggestion.ratio}:1)
        </button>
      ) : null}
      {error ? <div className="pdvm-theme-input__error">{error}</div> : null}
    </div>
  )
}

export function PdvmLengthInput(props: BaseProps) {
  const { draft, error, update } = useValidatedDraft(props.value, isValidLength, props.onChange, 'Ungültige Länge (z. B. 8px, 0.5rem oder 4px 8px)')
  return (
    <div className="pdvm-theme-input">
      <input
        id={props.id}
        type="text"
        className="pdvm-pic__input"
        value={draft}
        placeholder={props.placeholder || '(vom Theme übernommen)'}
        disabled={props.disabled}
        spellCheck={false}
        onChange={(e) => update(e.target.value)}
        onBlur={props.onBlur}
      />
      {error ? <div className="pdvm-theme-input__error">{error}</div> : null}
    </div>
  )
}

const BORDER_STYLES = ['solid', 'dashed', 'dotted', 'double', 'none'] as const

export function PdvmBorderInput(props: BaseProps) {
  const parsed = props.value.trim() ? parseBorder(props.value) : null
  const unparsable = !!props.value.trim() && !parsed
  const width = parsed && parsed.style !== 'none' ? parsed.width.replace('px', '') : '1'
  const style = parsed?.style || 'solid'
  const color = parsed?.color || ''

  const compose = (nextWidth: string, nextStyle: string, nextColor: string) => {
    if (nextStyle === 'none') return props.onChange('none')
    const w = Number(nextWidth)
    if (!Number.isFinite(w) || w < 0 || !nextColor.trim()) return
    props.onChange(`${w}px ${nextStyle} ${nextColor.trim()}`)
  }

  if (unparsable) {
    return (
      <div className="pdvm-theme-input">
        <input
          id={props.id}
          type="text"
          className="pdvm-pic__input"
          value={props.value}
          disabled={props.disabled}
          spellCheck={false}
          onChange={(e) => (isValidBorder(e.target.value) || !e.target.value.trim()) && props.onChange(e.target.value.trim())}
        />
        <div className="pdvm-theme-input__error">Wert nicht darstellbar - bitte als „Breite Stil Farbe“ eingeben (z. B. 1px solid und ein Farbwert).</div>
      </div>
    )
  }

  return (
    <div className="pdvm-theme-input pdvm-theme-input--border">
      <input
        id={props.id}
        type="number"
        min={0}
        step={1}
        className="pdvm-pic__input pdvm-theme-input__width"
        aria-label="Breite in px"
        value={width}
        disabled={props.disabled || style === 'none'}
        onChange={(e) => compose(e.target.value, style, color || 'currentColor')}
        onBlur={props.onBlur}
      />
      <select
        className="pdvm-pic__select pdvm-theme-input__style"
        aria-label="Linienstil"
        value={props.value.trim() ? style : ''}
        disabled={props.disabled}
        onChange={(e) => {
          if (!e.target.value) return props.onChange('')
          compose(width, e.target.value, color || 'currentColor')
        }}
      >
        <option value="">(vom Theme)</option>
        {BORDER_STYLES.map((s) => (
          <option key={s} value={s}>{s}</option>
        ))}
      </select>
      <div className="pdvm-theme-input__grow">
        <PdvmColorInput
          value={color}
          disabled={props.disabled || style === 'none' || !props.value.trim()}
          onChange={(c) => compose(width, style, c)}
        />
      </div>
    </div>
  )
}

export const DEFAULT_FONT_STACKS: Array<{ value: string; label: string }> = [
  { value: "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif", label: 'Inter / System' },
  { value: "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif", label: 'Segoe UI' },
  { value: "Roboto, 'Helvetica Neue', Arial, sans-serif", label: 'Roboto' },
  { value: 'Georgia, serif', label: 'Georgia (Serif)' },
  { value: "'Fira Code', 'Courier New', monospace", label: 'Fira Code (Festbreite)' },
  { value: "'Courier New', monospace", label: 'Courier New (Festbreite)' },
]

export function PdvmFontInput(props: BaseProps & { options?: Array<{ value: string; label: string }> }) {
  const stacks = props.options && props.options.length ? props.options : DEFAULT_FONT_STACKS
  const known = stacks.some((s) => s.value === props.value)
  const [custom, setCustom] = useState(!!props.value.trim() && !known)
  const { draft, error, update } = useValidatedDraft(props.value, isValidFontFamily, props.onChange, 'Ungültige Schriftfamilie (nur Namen, Komma, Anführungszeichen)')

  return (
    <div className="pdvm-theme-input">
      <select
        id={props.id}
        className="pdvm-pic__select"
        value={custom ? '__custom__' : props.value}
        disabled={props.disabled}
        onBlur={props.onBlur}
        onChange={(e) => {
          if (e.target.value === '__custom__') {
            setCustom(true)
            return
          }
          setCustom(false)
          props.onChange(e.target.value)
        }}
      >
        <option value="">(vom Theme übernommen)</option>
        {stacks.map((s) => (
          <option key={s.value} value={s.value}>{s.label}</option>
        ))}
        <option value="__custom__">Eigene Schriftfamilie …</option>
      </select>
      {custom ? (
        <input
          type="text"
          className="pdvm-pic__input"
          aria-label="Eigene Schriftfamilie"
          value={draft}
          disabled={props.disabled}
          spellCheck={false}
          onChange={(e) => update(e.target.value)}
        />
      ) : null}
      {error ? <div className="pdvm-theme-input__error">{error}</div> : null}
    </div>
  )
}
