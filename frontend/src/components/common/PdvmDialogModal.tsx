import { useEffect, useMemo, useRef, useState } from 'react'
import './PdvmDialogModal.css'

export type PdvmDialogModalKind = 'info' | 'confirm' | 'form'
export type PdvmDialogModalFieldType = 'text' | 'textarea' | 'number' | 'dropdown'

export interface PdvmDialogModalField {
  name: string
  label: string
  type?: PdvmDialogModalFieldType
  placeholder?: string
  required?: boolean
  minLength?: number
  maxLength?: number
  autoFocus?: boolean
  options?: Array<{ value: string; label: string }>
}

export interface PdvmDialogModalProps {
  open: boolean
  kind?: PdvmDialogModalKind
  title: string
  message?: React.ReactNode
  fields?: PdvmDialogModalField[]
  initialValues?: Record<string, string>

  confirmLabel?: string
  cancelLabel?: string

  busy?: boolean
  error?: string | null

  onConfirm?: (values: Record<string, string>) => void | Promise<void>
  onCancel: () => void
}

function clampInt(value: any, fallback: number): number {
  const n = Number(value)
  return Number.isFinite(n) ? Math.trunc(n) : fallback
}

export function PdvmDialogModal(props: PdvmDialogModalProps) {
  const {
    open,
    kind = 'confirm',
    title,
    message,
    fields = [],
    initialValues,
    confirmLabel,
    cancelLabel,
    busy = false,
    error,
    onConfirm,
    onCancel,
  } = props

  const isInfo = kind === 'info'
  const isForm = kind === 'form'

  const [localError, setLocalError] = useState<string | null>(null)
  const [values, setValues] = useState<Record<string, string>>({})
  const confirmBtnRef = useRef<HTMLButtonElement | null>(null)

  const computedConfirmLabel = useMemo(() => {
    if (confirmLabel) return confirmLabel
    if (isInfo) return 'OK'
    if (isForm) return 'OK'
    return 'OK'
  }, [confirmLabel, isInfo, isForm])

  const computedCancelLabel = useMemo(() => {
    if (cancelLabel) return cancelLabel
    return 'Abbrechen'
  }, [cancelLabel])

  useEffect(() => {
    if (!open) return

    setLocalError(null)

    const next: Record<string, string> = {}
    const src = initialValues || {}
    for (const f of fields) {
      const s = src[f.name]
      next[f.name] = s != null ? String(s) : ''
    }
    setValues(next)

    // Focus the first autoFocus field (or confirm button)
    const focusTimer = window.setTimeout(() => {
      try {
        const auto = fields.find((x) => x.autoFocus)
        if (auto) {
          const el = document.querySelector(`[data-pdvm-modal-field="${auto.name}"]`) as any
          if (el && typeof el.focus === 'function') {
            el.focus({ preventScroll: true })
            return
          }
        }
        confirmBtnRef.current?.focus({ preventScroll: true })
      } catch {
        // ignore
      }
    }, 0)

    return () => window.clearTimeout(focusTimer)
  }, [open])

  if (!open) return null

  const validate = (): string | null => {
    if (!isForm) return null

    for (const f of fields) {
      const v = String(values[f.name] ?? '').trim()
      if (f.required && !v) {
        return `${f.label}: Pflichtfeld`
      }
      const min = clampInt(f.minLength, 0)
      const max = clampInt(f.maxLength, 0)
      if (min > 0 && v.length < min) {
        return `${f.label}: mindestens ${min} Zeichen`
      }
      if (max > 0 && v.length > max) {
        return `${f.label}: maximal ${max} Zeichen`
      }
    }

    return null
  }

  const doConfirm = async () => {
    if (busy) return

    const v = validate()
    if (v) {
      setLocalError(v)
      return
    }

    setLocalError(null)
    if (!onConfirm) {
      onCancel()
      return
    }

    await onConfirm(values)
  }

  const doCancel = () => {
    if (busy) return
    onCancel()
  }

  return (
    <div
      className="pdvm-modal__overlay"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) doCancel()
      }}
      onKeyDown={(e) => {
        if (e.key === 'Escape') {
          e.preventDefault()
          e.stopPropagation()
          doCancel()
          return
        }

        if (e.key === 'Enter') {
          const t = e.target as any
          const isTextArea = t && String(t.tagName || '').toLowerCase() === 'textarea'
          if (!isTextArea) {
            e.preventDefault()
            e.stopPropagation()
            void doConfirm()
          }
        }
      }}
    >
      <div className="pdvm-modal">
        <div className="pdvm-modal__header">
          <div className="pdvm-modal__title">{title}</div>
          <button
            type="button"
            className="pdvm-modal__close"
            onClick={doCancel}
            disabled={busy}
            aria-label="Schließen"
            title="Schließen"
          >
            ×
          </button>
        </div>

        <div className="pdvm-modal__body">
          {message ? <div className="pdvm-modal__message">{message}</div> : null}

          {fields.length > 0 ? (
            <div className="pdvm-modal__fields">
              {fields.map((f) => {
                const type = f.type || 'text'
                const value = values[f.name] ?? ''
                const commonProps = {
                  'data-pdvm-modal-field': f.name,
                  value,
                  placeholder: f.placeholder || '',
                  disabled: busy,
                  onChange: (e: any) => {
                    const next = String(e?.target?.value ?? '')
                    setValues((prev) => ({ ...prev, [f.name]: next }))
                  },
                } as const

                return (
                  <label key={f.name} className="pdvm-modal__field">
                    <div className="pdvm-modal__label">
                      {f.label}
                      {f.required ? <span className="pdvm-modal__required">*</span> : null}
                    </div>
                    {type === 'textarea' ? (
                      <textarea
                        {...(commonProps as any)}
                        rows={4}
                        className="pdvm-modal__textarea"
                        spellCheck={false}
                      />
                    ) : type === 'dropdown' ? (
                      <select {...(commonProps as any)} className="pdvm-modal__input">
                        {(f.options || []).map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        {...(commonProps as any)}
                        type={type === 'number' ? 'number' : 'text'}
                        className="pdvm-modal__input"
                        spellCheck={false}
                      />
                    )}
                  </label>
                )
              })}
            </div>
          ) : null}

          {error ? <div className="pdvm-modal__error">{error}</div> : null}
          {localError ? <div className="pdvm-modal__error">{localError}</div> : null}
        </div>

        <div className="pdvm-modal__footer">
          {!isInfo ? (
            <button type="button" onClick={doCancel} className="pdvm-modal__btn" disabled={busy}>
              {computedCancelLabel}
            </button>
          ) : null}

          <button
            ref={confirmBtnRef}
            type="button"
            onClick={() => void doConfirm()}
            className="pdvm-modal__btn pdvm-modal__btn--primary"
            disabled={busy}
          >
            {computedConfirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
