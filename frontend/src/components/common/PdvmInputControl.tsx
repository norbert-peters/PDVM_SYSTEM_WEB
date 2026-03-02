import { useMemo, useState } from 'react'
import { PdvmDialogModal } from './PdvmDialogModal'
import './PdvmInputControl.css'

export type PdvmInputType = 'string' | 'number' | 'text' | 'dropdown' | 'multi_dropdown' | 'true_false' | 'element_list' | 'elemente_list' | 'group_list'

export type PdvmDropdownOption = { value: string; label: string }
export type PdvmElementField = {
  name: string
  label: string
  type?: 'string' | 'text' | 'textarea' | 'number' | 'dropdown' | 'multi_dropdown' | 'true_false'
  placeholder?: string
  required?: boolean
  options?: PdvmDropdownOption[]
  tooltip?: string
  help_text?: string
  control_debug?: Record<string, any> | null
  EXPERT_MODE?: boolean
  SAVE_PATH?: string
  display_order?: number
}

function getValueByPath(source: Record<string, any> | null | undefined, path: string): any {
  const obj = source && typeof source === 'object' ? source : {}
  const parts = String(path || '')
    .split('.')
    .map((p) => p.trim())
    .filter(Boolean)
  if (!parts.length) return undefined
  let cursor: any = obj
  for (const part of parts) {
    if (!cursor || typeof cursor !== 'object') return undefined
    cursor = cursor[part]
  }
  return cursor
}

function setValueByPath(target: Record<string, any>, path: string, value: any): Record<string, any> {
  const parts = String(path || '')
    .split('.')
    .map((p) => p.trim())
    .filter(Boolean)
  if (!parts.length) return target
  const out = { ...target }
  let cursor: any = out
  parts.forEach((part, idx) => {
    if (idx === parts.length - 1) {
      cursor[part] = value
      return
    }
    const next = cursor[part]
    if (!next || typeof next !== 'object' || Array.isArray(next)) {
      cursor[part] = {}
    } else {
      cursor[part] = { ...next }
    }
    cursor = cursor[part]
  })
  return out
}

function mapElementFieldTypeToInputType(value: PdvmElementField['type']): PdvmInputType {
  const t = String(value || 'text').trim().toLowerCase()
  if (t === 'number') return 'number'
  if (t === 'textarea') return 'text'
  if (t === 'dropdown') return 'dropdown'
  if (t === 'multi_dropdown') return 'multi_dropdown'
  if (t === 'true_false') return 'true_false'
  if (t === 'text') return 'text'
  return 'string'
}

function normalizeInputType(value: any): PdvmInputType {
  const t = String(value || '').trim().toLowerCase()
  if (t === 'number') return 'number'
  if (t === 'text') return 'text'
  if (t === 'dropdown') return 'dropdown'
  if (t === 'multi_dropdown') return 'multi_dropdown'
  if (t === 'true_false') return 'true_false'
  if (t === 'element_list') return 'element_list'
  if (t === 'elemente_list') return 'elemente_list'
  if (t === 'group_list') return 'group_list'
  return 'string'
}

function normalizeMultiDropdownValue(value: any): string[] {
  if (Array.isArray(value)) {
    const unique = new Set(value.map((v) => String(v)).map((v) => v.trim()).filter(Boolean))
    return Array.from(unique)
  }

  if (value == null) return []

  if (typeof value === 'string') {
    const items = value
      .split(/[;,|]/g)
      .map((s) => s.trim())
      .filter(Boolean)
    return Array.from(new Set(items))
  }

  return []
}

function normalizeTrueFalseValue(value: any): boolean {
  if (typeof value === 'boolean') return value
  if (typeof value === 'number') return value !== 0
  if (typeof value === 'string') {
    const v = value.trim().toLowerCase()
    if (!v) return false
    if (['true', '1', 'ja', 'yes', 'y', 'on'].includes(v)) return true
    if (['false', '0', 'nein', 'no', 'n', 'off'].includes(v)) return false
  }
  return !!value
}

function normalizeTextValue(value: any): string {
  if (value == null) return ''
  return String(value)
}

function normalizeStringValue(value: any): string {
  if (value == null) return ''
  return String(value)
}

function sanitizeNumberInput(value: any): string {
  return String(value ?? '').replace(/[^1-9]+/g, '')
}

function normalizeNumberValue(value: any): string {
  return sanitizeNumberInput(value)
}

function normalizeCollectionValue(value: any): Record<string, any> {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, any>
  }

  if (Array.isArray(value)) {
    const out: Record<string, any> = {}
    value.forEach((entry, idx) => {
      out[String(idx + 1)] = entry
    })
    return out
  }

  if (typeof value === 'string') {
    const raw = value.trim()
    if (!raw) return {}
    try {
      const parsed = JSON.parse(raw)
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        return parsed as Record<string, any>
      }
    } catch {
      // ignore invalid legacy json
    }
  }

  return {}
}

export function PdvmInputControl(props: {
  id?: string
  label: string
  tooltip?: string | null
  type: PdvmInputType
  value: any
  onChange: (value: any) => void
  onBlur?: () => void
  readOnly?: boolean
  disabled?: boolean
  placeholder?: string
  options?: PdvmDropdownOption[]
  helpText?: string | null
  helpEnabled?: boolean
  controlDebug?: Record<string, any> | null
  elementTemplate?: Record<string, any> | null
  elementLabelKeys?: string[]
  elementFields?: PdvmElementField[]
}) {
  const [helpOpen, setHelpOpen] = useState(false)
  const [controlOpen, setControlOpen] = useState(false)
  const [numberInputError, setNumberInputError] = useState<string | null>(null)
  const [elementModalOpen, setElementModalOpen] = useState(false)
  const [elementModalError, setElementModalError] = useState<string | null>(null)
  const [elementModalUid, setElementModalUid] = useState<string | null>(null)
  const [elementModalTitle, setElementModalTitle] = useState<string>('')
  const [elementModalDraft, setElementModalDraft] = useState<Record<string, any> | null>(null)
  const [elementModalBase, setElementModalBase] = useState<Record<string, any> | null>(null)

  const effectiveType = normalizeInputType((props as any).type)
  const disabled = !!props.disabled || !!props.readOnly
  const helpEnabled = props.helpEnabled ?? true
  const isElementList = effectiveType === 'element_list' || effectiveType === 'elemente_list' || effectiveType === 'group_list'
  const elementFields = useMemo(() => {
    return Array.isArray(props.elementFields) ? props.elementFields : null
  }, [props.elementFields])

  const helpText = useMemo(() => {
    const s = String(props.helpText || '').trim()
    return s || null
  }, [props.helpText])

  const showHelpButton = helpEnabled
  const controlDebugPayload = props.controlDebug || null
  const showControlButton = useMemo(() => {
    const ctrl = props.controlDebug || null
    if (!ctrl || typeof ctrl !== 'object') return false
    const raw = (ctrl as any).EXPERT_MODE ?? (ctrl as any).expert_mode ?? false
    return !!raw
  }, [props.controlDebug])
  const multiDropdownValue = useMemo(() => normalizeMultiDropdownValue(props.value), [props.value])
  const trueFalseValue = useMemo(() => normalizeTrueFalseValue(props.value), [props.value])
  const textValue = useMemo(() => normalizeTextValue(props.value), [props.value])
  const stringValue = useMemo(() => normalizeStringValue(props.value), [props.value])
  const numberValue = useMemo(() => normalizeNumberValue(props.value), [props.value])

  const elementLabelKeys = useMemo(() => {
    const keys = props.elementLabelKeys && props.elementLabelKeys.length ? props.elementLabelKeys : ['label', 'name', 'feld']
    return keys.map((k) => String(k)).filter(Boolean)
  }, [props.elementLabelKeys])

  const elementMap = useMemo(() => normalizeCollectionValue(props.value), [props.value])
  const elementCount = Object.keys(elementMap).length

  const elementEntries = useMemo(() => {
    const out = Object.entries(elementMap).map(([uid, cfg]) => ({ uid, cfg }))
    out.sort((a, b) => {
      const al = elementLabelKeys.map((k) => String(a.cfg?.[k] ?? '')).find((x) => x.trim()) || a.uid
      const bl = elementLabelKeys.map((k) => String(b.cfg?.[k] ?? '')).find((x) => x.trim()) || b.uid
      return al.toLowerCase().localeCompare(bl.toLowerCase())
    })
    return out
  }, [elementMap, elementLabelKeys])

  const elementModalFields = useMemo(() => {
    if (elementFields && elementFields.length) {
      const ordered = [...elementFields]
      ordered.sort((a, b) => {
        const ao = Number(a.display_order)
        const bo = Number(b.display_order)
        if (Number.isFinite(ao) && Number.isFinite(bo) && ao !== bo) return ao - bo
        if (Number.isFinite(ao) && !Number.isFinite(bo)) return -1
        if (!Number.isFinite(ao) && Number.isFinite(bo)) return 1
        return String(a.label || a.name || '').localeCompare(String(b.label || b.name || ''))
      })
      return ordered
    }
    const base = elementModalBase && typeof elementModalBase === 'object' ? elementModalBase : {}
    return Object.keys(base)
      .filter((k) => String(k || '').trim())
      .map((key, idx) => {
        const raw = (base as any)[key]
        let inferredType: PdvmElementField['type'] = 'string'
        if (typeof raw === 'number') inferredType = 'number'
        else if (typeof raw === 'boolean') inferredType = 'true_false'
        else if (Array.isArray(raw)) inferredType = 'multi_dropdown'
        return {
          name: key,
          label: key,
          type: inferredType,
          SAVE_PATH: key,
          display_order: (idx + 1) * 10,
        } as PdvmElementField
      })
  }, [elementFields, elementModalBase])

  const getElementLabel = (cfg: any, uid: string) => {
    for (const key of elementLabelKeys) {
      const v = cfg ? cfg[key] : null
      const s = v != null ? String(v).trim() : ''
      if (s) return s
    }
    return uid
  }

  const createGuid = () => {
    try {
      const c = (globalThis as any)?.crypto
      if (c && typeof c.randomUUID === 'function') return c.randomUUID()
    } catch {
      // ignore
    }
    const s4 = () => Math.floor((1 + Math.random()) * 0x10000).toString(16).substring(1)
    return `${s4()}${s4()}-${s4()}-${s4()}-${s4()}-${s4()}${s4()}${s4()}`
  }

  const openElementModal = (uid: string, cfg: any, title: string) => {
    const base = cfg && typeof cfg === 'object' ? JSON.parse(JSON.stringify(cfg)) : {}
    setElementModalUid(uid)
    setElementModalTitle(title)
    setElementModalBase(base)
    setElementModalDraft(base)
    setElementModalError(null)
    setElementModalOpen(true)
  }

  const addElement = () => {
    if (disabled) return
    const uid = createGuid()
    const tpl = props.elementTemplate ? JSON.parse(JSON.stringify(props.elementTemplate)) : {}
    openElementModal(uid, tpl, 'Element hinzufügen')
  }

  const editElement = (uid: string, cfg: any) => {
    if (disabled) return
    openElementModal(uid, cfg, 'Element bearbeiten')
  }

  const deleteElement = (uid: string) => {
    if (disabled) return
    const next = { ...elementMap }
    delete next[uid]
    props.onChange(next)
  }

  const saveElementModal = () => {
    const uid = elementModalUid
    if (!uid) return

    const draft = elementModalDraft && typeof elementModalDraft === 'object' ? JSON.parse(JSON.stringify(elementModalDraft)) : {}

    for (const field of elementModalFields) {
      if (!field.required) continue
      const savePath = String(field.SAVE_PATH || field.name || '').trim()
      const raw = getValueByPath(draft, savePath)
      const text = raw == null ? '' : String(raw).trim()
      if (!text) {
        setElementModalError(`${field.label}: Pflichtfeld`)
        return
      }
    }

    const next = { ...elementMap, [uid]: draft }
    props.onChange(next)
    setElementModalOpen(false)
    setElementModalError(null)
    setElementModalUid(null)
    setElementModalBase(null)
    setElementModalDraft(null)
  }

  return (
    <div className="pdvm-pic" title={props.tooltip || undefined}>
      <div className="pdvm-pic__labelRow">
        <label className="pdvm-pic__label" htmlFor={props.id}>
          {props.label}
        </label>
        {showHelpButton ? (
          <>
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
            {showControlButton ? (
              <button
                type="button"
                className="pdvm-pic__helpBtn"
                title="Control anzeigen"
                aria-label="Control anzeigen"
                onClick={() => setControlOpen(true)}
                disabled={false}
                style={{ marginLeft: 6 }}
              >
                {'{}'}
              </button>
            ) : null}
          </>
        ) : null}
      </div>

      <div className={`pdvm-pic__control ${isElementList ? 'pdvm-pic__control--stack' : ''}`.trim()}>
        {isElementList ? (
          <div className="pdvm-dialog__elementList">
            <div className="pdvm-dialog__elementMeta">Einträge: {elementCount}</div>
            {elementEntries.length === 0 ? <div className="pdvm-dialog__elementEmpty">Keine Einträge vorhanden.</div> : null}
            {elementEntries.map(({ uid, cfg }) => (
              <div key={uid} className="pdvm-dialog__elementItem" title={JSON.stringify(cfg, null, 2)}>
                <div className="pdvm-dialog__elementLabel">{getElementLabel(cfg, uid)}</div>
                <div className="pdvm-dialog__elementActions">
                  <button type="button" className="pdvm-dialog__toolBtn" onClick={() => editElement(uid, cfg)} disabled={disabled}>
                    Bearbeiten
                  </button>
                  <button type="button" className="pdvm-dialog__toolBtn" onClick={() => deleteElement(uid)} disabled={disabled}>
                    Entfernen
                  </button>
                </div>
              </div>
            ))}
            <button type="button" className="pdvm-dialog__toolBtn" onClick={addElement} disabled={disabled}>
              + Element hinzufuegen
            </button>
          </div>
        ) : null}

        {effectiveType === 'string' ? (
          <input
            id={props.id}
            className="pdvm-pic__input"
            type="text"
            value={stringValue}
            placeholder={props.placeholder}
            disabled={disabled}
            onChange={(e) => props.onChange(e.target.value)}
            onBlur={props.onBlur}
          />
        ) : null}

        {effectiveType === 'number' ? (
          <>
            <input
              id={props.id}
              className="pdvm-pic__input"
              type="text"
              inputMode="numeric"
              pattern="[1-9]*"
              value={numberValue}
              placeholder={props.placeholder}
              disabled={disabled}
              onBlur={() => {
                props.onBlur?.()
                if (!numberValue.trim()) {
                  setNumberInputError(null)
                }
              }}
              onChange={(e) => {
                const raw = String(e.target.value || '')
                const digitsOnly = sanitizeNumberInput(raw)
                if (raw !== digitsOnly) {
                  setNumberInputError('Es sind nur die Ziffern 1-9 möglich')
                } else {
                  setNumberInputError(null)
                }
                props.onChange(digitsOnly)
              }}
            />
            {numberInputError ? <div style={{ marginTop: 6, fontSize: 12, color: '#b42318' }}>{numberInputError}</div> : null}
          </>
        ) : null}

        {effectiveType === 'text' ? (
          <textarea
            id={props.id}
            className="pdvm-pic__textarea"
            value={textValue}
            placeholder={props.placeholder}
            disabled={disabled}
            rows={3}
            onBlur={props.onBlur}
            onChange={(e) => props.onChange(e.target.value)}
          />
        ) : null}

        {effectiveType === 'dropdown' ? (
          <select
            id={props.id}
            className="pdvm-pic__select"
            value={String(props.value ?? '')}
            disabled={disabled}
            onBlur={props.onBlur}
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

        {effectiveType === 'multi_dropdown' ? (
          <select
            id={props.id}
            className="pdvm-pic__select"
            multiple
            value={multiDropdownValue}
            disabled={disabled}
            onBlur={props.onBlur}
            onChange={(e) => {
              const selected = Array.from(e.target.selectedOptions).map((o) => String(o.value).trim()).filter(Boolean)
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

        {effectiveType === 'true_false' ? (
          <label className="pdvm-pic__checkbox">
            <input
              id={props.id}
              type="checkbox"
              checked={trueFalseValue}
              disabled={disabled}
              onBlur={props.onBlur}
              onChange={(e) => props.onChange(e.target.checked)}
            />
            <span>{trueFalseValue ? 'Ja' : 'Nein'}</span>
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

      <PdvmDialogModal
        open={controlOpen}
        kind="info"
        title={`Control: ${props.label}`}
        message={<pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{JSON.stringify(controlDebugPayload, null, 2)}</pre>}
        confirmLabel="OK"
        onCancel={() => setControlOpen(false)}
        onConfirm={() => setControlOpen(false)}
      />

      <PdvmDialogModal
        open={elementModalOpen}
        kind="confirm"
        title={elementModalTitle}
        message={
          <div className="pdvm-pic__elementEditor">
            {elementModalFields.length ? (
              elementModalFields.map((field) => {
                const fieldType = mapElementFieldTypeToInputType(field.type)
                const parentExpert = !!((props.controlDebug as any)?.EXPERT_MODE ?? (props.controlDebug as any)?.expert_mode ?? false)
                const fieldExpert = !!((field as any).EXPERT_MODE ?? false)
                const nestedControlDebug = (field.control_debug && typeof field.control_debug === 'object'
                  ? field.control_debug
                  : {
                      FIELD_KEY: `ELEMENT.${field.name}`,
                    }) as Record<string, any>
                nestedControlDebug.EXPERT_MODE = !!(nestedControlDebug.EXPERT_MODE ?? fieldExpert ?? parentExpert)
                return (
                  <PdvmInputControl
                    key={`element-modal-${field.name}`}
                    label={field.required ? `${field.label} *` : field.label}
                    tooltip={field.tooltip || null}
                    type={fieldType}
                    value={(() => {
                      const savePath = String(field.SAVE_PATH || field.name || '').trim()
                      if (!savePath || !elementModalDraft || typeof elementModalDraft !== 'object') return ''
                      return getValueByPath(elementModalDraft as Record<string, any>, savePath)
                    })()}
                    options={field.options || []}
                    placeholder={field.placeholder}
                    helpEnabled={true}
                    helpText={field.help_text || field.tooltip || null}
                    controlDebug={nestedControlDebug}
                    onChange={(value) => {
                      setElementModalDraft((prev) => {
                        const base = prev && typeof prev === 'object' ? prev : {}
                        const savePath = String(field.SAVE_PATH || field.name || '').trim()
                        if (!savePath) return base
                        return {
                          ...setValueByPath(base, savePath, value),
                        }
                      })
                    }}
                  />
                )
              })
            ) : (
              <div className="pdvm-dialog__elementEmpty">Keine Felder für dieses Element definiert.</div>
            )}
          </div>
        }
        error={elementModalError}
        confirmLabel="Speichern"
        cancelLabel="Abbrechen"
        onCancel={() => {
          setElementModalOpen(false)
          setElementModalError(null)
          setElementModalUid(null)
          setElementModalBase(null)
          setElementModalDraft(null)
        }}
        onConfirm={() => saveElementModal()}
      />
    </div>
  )
}
