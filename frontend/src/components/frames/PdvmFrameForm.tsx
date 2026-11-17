import { useMemo, useState } from 'react'
import type { FrameRuntime } from '../../api/client'
import { PdvmInputControl } from '../common/PdvmInputControl'
import { IMMUTABLE_LOCK_HINT, isImmutableLocked, readFieldValue, unsupportedTypeMessage, writeFieldValue } from './frameRuntime'
import { uiText } from '../../i18n/uiTexts'

export type FrameFormError = { group: string; field: string; message: string }

/**
 * Rendert ein Frame (Runtime-Modell aus GET /api/frames/{uid}/runtime) ausschliesslich ueber PdvmInputControl.
 * Welche Felder erscheinen, bestimmt das Frame; Typ, Label und Konfiguration kommen aus sys_control_dict.
 * Regel 2.15 (ARCHITECTURE_RULES.md).
 */
export function PdvmFrameForm(props: {
  frame: FrameRuntime
  data: Record<string, any>
  onChange: (next: Record<string, any>) => void
  errors?: FrameFormError[]
  disabled?: boolean
  /** `edit`: unveraenderliche Felder (IMMUTABLE) mit gespeichertem Wert sind schreibgeschuetzt (verbindlich im Backend). */
  mode?: 'create' | 'edit'
  /** Gespeicherter Stand als Basis der Sperre im Modus `edit` (nicht der Entwurf in `data`). */
  savedData?: Record<string, any>
}) {
  const { frame, data, onChange, errors = [], disabled, mode = 'create', savedData } = props
  const firstTab = frame.tabs[0]?.index ?? 1
  const [activeTab, setActiveTab] = useState<number>(firstTab)

  const fields = useMemo(() => frame.fields.filter((f) => f.tab === activeTab), [frame.fields, activeTab])
  const errorByField = useMemo(() => {
    const map = new Map<string, string>()
    errors.forEach((e) => map.set(`${e.group}.${e.field}`, e.message))
    return map
  }, [errors])
  const tabsWithErrors = useMemo(() => {
    const tabs = new Set<number>()
    frame.fields.forEach((f) => {
      if (errorByField.has(`${f.gruppe}.${f.feld}`)) tabs.add(f.tab)
    })
    return tabs
  }, [frame.fields, errorByField])

  return (
    <div className="pdvm-tabs">
      {frame.tabs.length > 1 ? (
        <div className="pdvm-tabs__bar">
          <div className="pdvm-tabs__list" role="tablist" aria-label={frame.name}>
            {frame.tabs.map((tab) => (
              <button
                key={tab.index}
                type="button"
                role="tab"
                aria-selected={activeTab === tab.index}
                className={`pdvm-tabs__tab ${activeTab === tab.index ? 'pdvm-tabs__tab--active' : ''}`}
                onClick={() => setActiveTab(tab.index)}
              >
                {tab.head}
                {tabsWithErrors.has(tab.index) ? ' !' : ''}
              </button>
            ))}
          </div>
        </div>
      ) : null}
      <div
        className="pdvm-tabs__panel"
        style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', alignItems: 'start' }}
      >
        {fields.map((field) => {
          // Aktionen/Hinweise (Regel 2.17) brauchen eine Mandanten-Sitzung und einen gespeicherten Satz; hier nicht darstellbar
          if (field.type === 'action' || field.type === 'info') return null
          const problem = field.resolution_warning || unsupportedTypeMessage(field)
          const error = errorByField.get(`${field.gruppe}.${field.feld}`)
          if (problem) {
            return (
              <div key={field.key} style={{ color: 'var(--color-error-text)' }}>
                {field.label}: {problem}
              </div>
            )
          }
          const raw = readFieldValue(data, field)
          // password_input mit CONFIGS.password_input.confirm_with: Abweichung zum Bestaetigungsfeld anzeigen (der Server prueft ebenfalls)
          const confirmWith = String(((field.configs?.password_input as Record<string, any> | undefined)?.confirm_with) || '').trim()
          const other = confirmWith ? frame.fields.find((f) => f.gruppe === field.gruppe && f.feld === confirmWith) : undefined
          const otherValue = other ? readFieldValue(data, other) : undefined
          const mismatch =
            field.type === 'password_input' && other && String(raw ?? '') !== '' && String(otherValue ?? '') !== '' && String(raw) !== String(otherValue)
              ? uiText('form.passwordMismatch')
              : undefined
          const fieldError = error || mismatch
          const locked = isImmutableLocked(field.immutable, mode, readFieldValue(savedData ?? {}, field), {
            after: field.immutable_after,
            data: savedData,
          })
          return (
            <PdvmInputControl
              key={field.key}
              label={field.label}
              tooltip={field.tooltip}
              type={field.type as 'string' | 'text' | 'text_popup' | 'number' | 'true_false' | 'password' | 'password_input' | 'dropdown'}
              value={raw ?? field.default ?? ''}
              onChange={(value) => onChange(writeFieldValue(data, field, value))}
              readOnly={field.read_only || locked}
              readOnlyHint={locked ? IMMUTABLE_LOCK_HINT : undefined}
              disabled={disabled}
              resolvedConfigs={field.configs}
              options={field.options}
              helpText={fieldError ? `${fieldError}${field.tooltip ? ` · ${field.tooltip}` : ''}` : field.tooltip}
            />
          )
        })}
      </div>
    </div>
  )
}
