import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import './PdvmDialogModal.css'
import './PdvmTextEditorModal.css'

/**
 * Grosses Fenster zum Lesen und Bearbeiten langer Texte (PdvmInputControl, Typ `text` und `text_popup`).
 * Arbeitet auf einem Entwurf: erst "Uebernehmen" schreibt den Text zurueck, "Abbrechen" verwirft ihn.
 * Die HTML-Vorschau rendert in einer abgeschotteten Flaeche (sandbox ohne Skripte, ohne Netzzugriff durch CSP).
 */
export function PdvmTextEditorModal(props: {
  open: boolean
  title: string
  value: string
  readOnly?: boolean
  mono?: boolean
  htmlPreview?: boolean
  onApply: (value: string) => void
  onCancel: () => void
}) {
  const { open, title, value, readOnly = false, mono = false, htmlPreview = false, onApply, onCancel } = props
  const [draft, setDraft] = useState(value)
  const [tab, setTab] = useState<'edit' | 'preview'>('edit')
  const areaRef = useRef<HTMLTextAreaElement | null>(null)
  const dirty = draft !== value

  useEffect(() => {
    if (!open) return
    setDraft(value)
    setTab('edit')
    const timer = window.setTimeout(() => areaRef.current?.focus({ preventScroll: true }), 0)
    return () => window.clearTimeout(timer)
    // Entwurf nur beim Oeffnen setzen, nicht bei jeder Wertaenderung von aussen
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const stats = useMemo(() => {
    const lines = draft ? draft.split('\n').length : 0
    return `${draft.length} Zeichen · ${lines} Zeilen`
  }, [draft])

  // Mail-Vorschau: bewusst heller Grund wie beim Empfaenger, unabhaengig vom Theme
  const previewDoc = useMemo(
    () =>
      `<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:"><body style="font-family:sans-serif;font-size:14px;margin:12px;background:#ffffff;color:#1a1a1a">${draft}</body>`, // guard-allow-color
    [draft]
  )

  if (!open) return null

  const cancel = () => onCancel()
  const apply = () => {
    if (!readOnly && dirty) onApply(draft)
    else onCancel()
  }

  // Portal in den Body: position:fixed bezieht sich sonst auf einen Vorfahren mit transform/contain/overflow
  // und nicht auf das Browserfenster (Fensterrahmen oben abgeschnitten).
  return createPortal(
    <div
      className="pdvm-modal__overlay pdvm-texteditor__overlay"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onMouseDown={(e) => {
        // Klick neben das Fenster schliesst nur, wenn nichts verloren geht
        if (e.target === e.currentTarget && !dirty) cancel()
      }}
      onKeyDown={(e) => {
        if (e.key === 'Escape') {
          e.preventDefault()
          e.stopPropagation()
          cancel()
        } else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && !readOnly) {
          e.preventDefault()
          e.stopPropagation()
          apply()
        }
      }}
    >
      <div className="pdvm-modal pdvm-texteditor">
        <div className="pdvm-modal__header">
          <div className="pdvm-modal__title">{title}</div>
          {readOnly ? <span className="pdvm-texteditor__badge">🔒 schreibgeschützt</span> : null}
          <button type="button" className="pdvm-modal__close" onClick={cancel} aria-label="Schließen" title="Schließen (Esc)">
            ×
          </button>
        </div>

        {htmlPreview ? (
          <div className="pdvm-texteditor__tabs" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'edit'}
              className={`pdvm-texteditor__tab ${tab === 'edit' ? 'pdvm-texteditor__tab--active' : ''}`}
              onClick={() => setTab('edit')}
            >
              {readOnly ? 'Quelltext' : 'Bearbeiten'}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'preview'}
              className={`pdvm-texteditor__tab ${tab === 'preview' ? 'pdvm-texteditor__tab--active' : ''}`}
              onClick={() => setTab('preview')}
            >
              Vorschau
            </button>
          </div>
        ) : null}

        <div className="pdvm-texteditor__body">
          {tab === 'edit' ? (
            <textarea
              ref={areaRef}
              className={`pdvm-texteditor__area ${mono ? 'pdvm-texteditor__area--mono' : ''}`}
              value={draft}
              readOnly={readOnly}
              spellCheck={!mono}
              onChange={(e) => setDraft(e.target.value)}
            />
          ) : (
            <iframe className="pdvm-texteditor__preview" title="Vorschau" sandbox="" srcDoc={previewDoc} />
          )}
        </div>

        <div className="pdvm-modal__footer pdvm-texteditor__footer">
          <span className="pdvm-texteditor__stats">
            {stats}
            {!readOnly ? ' · Strg+Enter übernimmt' : ''}
          </span>
          {readOnly ? (
            <button type="button" className="pdvm-modal__btn pdvm-modal__btn--primary" onClick={cancel}>
              Schließen
            </button>
          ) : (
            <>
              <button type="button" className="pdvm-modal__btn" onClick={cancel}>
                Abbrechen
              </button>
              <button type="button" className="pdvm-modal__btn pdvm-modal__btn--primary" onClick={apply}>
                Übernehmen
              </button>
            </>
          )}
        </div>
      </div>
    </div>,
    document.body
  )
}
