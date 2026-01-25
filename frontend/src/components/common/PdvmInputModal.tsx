import { useEffect, useMemo, useRef } from 'react'
import './PdvmInputModal.css'
import './PdvmDialogModal.css'

export interface PdvmInputModalProps {
  open: boolean
  title: string
  busy?: boolean
  saveLabel?: string
  cancelLabel?: string
  footerExtra?: React.ReactNode
  onSave?: () => void | Promise<void>
  onClose: () => void
  children?: React.ReactNode
}

export function PdvmInputModal(props: PdvmInputModalProps) {
  const {
    open,
    title,
    busy = false,
    saveLabel,
    cancelLabel,
    footerExtra,
    onSave,
    onClose,
    children,
  } = props

  const saveBtnRef = useRef<HTMLButtonElement | null>(null)

  const computedSaveLabel = useMemo(() => saveLabel || 'Speichern', [saveLabel])
  const computedCancelLabel = useMemo(() => cancelLabel || 'Schließen', [cancelLabel])

  useEffect(() => {
    if (!open) return
    const t = window.setTimeout(() => saveBtnRef.current?.focus({ preventScroll: true }), 0)
    return () => window.clearTimeout(t)
  }, [open])

  if (!open) return null

  const doClose = () => {
    if (busy) return
    onClose()
  }

  const doSave = async () => {
    if (busy || !onSave) return
    await onSave()
  }

  return (
    <div
      className="pdvm-modal__overlay pdvm-input-modal"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) doClose()
      }}
      onKeyDown={(e) => {
        if (e.key === 'Escape') {
          e.preventDefault()
          e.stopPropagation()
          doClose()
          return
        }
      }}
    >
      <div className="pdvm-modal">
        <div className="pdvm-modal__header">
          <div className="pdvm-modal__title">{title}</div>
          <button
            type="button"
            className="pdvm-modal__close"
            onClick={doClose}
            disabled={busy}
            aria-label="Schließen"
            title="Schließen"
          >
            ×
          </button>
        </div>

        <div className="pdvm-modal__body">{children}</div>

        <div className="pdvm-modal__footer">
          {footerExtra}
          <button type="button" onClick={doClose} className="pdvm-modal__btn" disabled={busy}>
            {computedCancelLabel}
          </button>
          <button
            ref={saveBtnRef}
            type="button"
            onClick={() => void doSave()}
            className="pdvm-modal__btn pdvm-modal__btn--primary"
            disabled={busy || !onSave}
          >
            {computedSaveLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
