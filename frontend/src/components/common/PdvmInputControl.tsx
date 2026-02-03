import { useMemo, useState } from 'react'
import { PdvmDialogModal } from './PdvmDialogModal'
import './PdvmInputControl.css'

export type PdvmInputType = 'string' | 'text' | 'dropdown' | 'multi_dropdown' | 'true_false'

export type PdvmDropdownOption = { value: string; label: string }

export function PdvmInputControl(props: {
  id?: string
  label: string
  tooltip?: string | null
  type: PdvmInputType
  value: any
  onChange: (value: any) => void
  readOnly?: boolean
  disabled?: boolean
  placeholder?: string
  options?: PdvmDropdownOption[]
  helpText?: string | null
  helpEnabled?: boolean
}) {
  const [helpOpen, setHelpOpen] = useState(false)

  const disabled = !!props.disabled || !!props.readOnly
  const helpEnabled = props.helpEnabled ?? true

  const helpText = useMemo(() => {
    const s = String(props.helpText || '').trim()
    return s || null
  }, [props.helpText])

  const showHelpButton = helpEnabled

  return (
    <div className="pdvm-pic" title={props.tooltip || undefined}>
      <div className="pdvm-pic__labelRow">
        <label className="pdvm-pic__label" htmlFor={props.id}>
          {props.label}
        </label>
        {showHelpButton ? (
          <button
            type="button"
            className="pdvm-pic__helpBtn"
            title="Hilfe"
            aria-label="Hilfe"
            onClick={() => setHelpOpen(true)}
            disabled={false}
          >
            ?
          </button>
        ) : null}
      </div>

      <div className="pdvm-pic__control">
        {props.type === 'string' ? (
          <input
            id={props.id}
            className="pdvm-pic__input"
            type="text"
            value={String(props.value ?? '')}
            placeholder={props.placeholder}
            disabled={disabled}
            onChange={(e) => props.onChange(e.target.value)}
          />
        ) : null}

        {props.type === 'text' ? (
          <textarea
            id={props.id}
            className="pdvm-pic__textarea"
            value={String(props.value ?? '')}
            placeholder={props.placeholder}
            disabled={disabled}
            rows={3}
            onChange={(e) => props.onChange(e.target.value)}
          />
        ) : null}

        {props.type === 'dropdown' ? (
          <select
            id={props.id}
            className="pdvm-pic__select"
            value={String(props.value ?? '')}
            disabled={disabled}
            onChange={(e) => props.onChange(e.target.value)}
          >
            <option value="">(bitte auswählen)</option>
            {(props.options || []).map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        ) : null}

        {props.type === 'multi_dropdown' ? (
          <select
            id={props.id}
            className="pdvm-pic__select"
            multiple
            value={Array.isArray(props.value) ? props.value.map((v) => String(v)) : []}
            disabled={disabled}
            onChange={(e) => {
              const selected = Array.from(e.target.selectedOptions).map((o) => String(o.value))
              props.onChange(selected)
            }}
          >
            {(props.options || []).map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        ) : null}

        {props.type === 'true_false' ? (
          <label className="pdvm-pic__checkbox">
            <input
              id={props.id}
              type="checkbox"
              checked={!!props.value}
              disabled={disabled}
              onChange={(e) => props.onChange(e.target.checked)}
            />
            <span>{!!props.value ? 'Ja' : 'Nein'}</span>
          </label>
        ) : null}
      </div>

      <PdvmDialogModal
        open={helpOpen}
        kind="info"
        title={`Hilfe: ${props.label}`}
        message={helpText || 'Noch keine Hilfe hinterlegt.'}
        confirmLabel="OK"
        onCancel={() => setHelpOpen(false)}
        onConfirm={() => setHelpOpen(false)}
      />
    </div>
  )
}
