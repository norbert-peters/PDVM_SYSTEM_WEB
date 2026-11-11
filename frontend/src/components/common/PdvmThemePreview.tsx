/**
 * Live-Vorschau eines Themes. Die Tokens werden nur auf dem Container gesetzt (nicht auf :root),
 * damit Entwuerfe im Editor die laufende Anwendung nicht veraendern.
 */
import { useMemo } from 'react'
import type { CSSProperties } from 'react'
import { themeTokensToCssVars, type ThemeTokens } from '../../utils/themeVars'
import './PdvmThemeInputs.css'

export function PdvmThemePreview(props: { tokens: ThemeTokens | null | undefined; mode?: 'light' | 'dark' }) {
  const style = useMemo(() => themeTokensToCssVars(props.tokens) as CSSProperties, [props.tokens])

  return (
    <div className="pdvm-theme-preview" data-theme={props.mode} style={style} aria-label="Theme-Vorschau">
      <div className="pdvm-theme-preview__header">
        <strong>PDVM System</strong>
        <span className="pdvm-theme-preview__muted">Mandant Beispiel</span>
      </div>
      <div className="pdvm-theme-preview__stichtag">
        <span>Angewendeter Stichtag: 10.11.2026 15:30</span>
        <span className="pdvm-theme-preview__stichtagField">10.11.2026 15:30 📅</span>
      </div>
      <div className="pdvm-theme-preview__body">
        <nav className="pdvm-theme-preview__sidebar">
          <div className="pdvm-theme-preview__navItem pdvm-theme-preview__navItem--active">Übersicht</div>
          <div className="pdvm-theme-preview__navItem">Personen</div>
          <div className="pdvm-theme-preview__navItem">Auswertungen</div>
        </nav>
        <main className="pdvm-theme-preview__main">
          <div className="pdvm-theme-preview__card">
            <h4 className="pdvm-theme-preview__title">Karte</h4>
            <p className="pdvm-theme-preview__muted">Beispieltext mit Zusatzinformation.</p>
            <input className="pdvm-theme-preview__input" readOnly value="Eingabefeld" aria-label="Beispiel-Eingabe" />
            <div className="pdvm-theme-preview__actions">
              <button type="button" className="pdvm-theme-preview__btn pdvm-theme-preview__btn--primary">Speichern</button>
              <button type="button" className="pdvm-theme-preview__btn">Abbrechen</button>
            </div>
          </div>
          <div className="pdvm-theme-preview__popover">
            <strong>Datum &amp; Zeit ändern</strong>
            <span className="pdvm-theme-preview__popoverField">10.11.2026</span>
            <span className="pdvm-theme-preview__popoverField">15:30</span>
          </div>
          <div className="pdvm-theme-preview__status">
            <span className="pdvm-theme-preview__chip pdvm-theme-preview__chip--success">Erfolg</span>
            <span className="pdvm-theme-preview__chip pdvm-theme-preview__chip--warning">Warnung</span>
            <span className="pdvm-theme-preview__chip pdvm-theme-preview__chip--error">Fehler</span>
            <span className="pdvm-theme-preview__chip pdvm-theme-preview__chip--info">Info</span>
          </div>
        </main>
      </div>
    </div>
  )
}
