import { useMemo, useState } from 'react'
import { PdvmDialogModal } from './PdvmDialogModal'
import './PdvmInputControl.css'

export type PdvmInputType = 'string' | 'number' | 'text' | 'dropdown' | 'multi_dropdown' | 'true_false' | 'element_list' | 'elemente_list' | 'group_list'

export type PdvmDropdownOption = { value: string; label: string }
export type PdvmElementField = {
  name: string
  label: string
  type?: 'text' | 'textarea' | 'number' | 'dropdown'
  placeholder?: string
  required?: boolean
  options?: PdvmDropdownOption[]
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
  const [elementModalInitial, setElementModalInitial] = useState<Record<string, string> | null>(null)
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
  const controlDebugPayload = useMemo(() => {
    return {
      label: props.label,
      input_type_raw: String((props as any).type || ''),
      input_type_effective: effectiveType,
      read_only: !!props.readOnly,
      disabled: !!props.disabled,
      value: props.value,
      options: props.options || [],
      control: props.controlDebug || null,
    }
  }, [props, effectiveType])

  const elementLabelKeys = useMemo(() => {
    const keys = props.elementLabelKeys && props.elementLabelKeys.length ? props.elementLabelKeys : ['label', 'name', 'feld']
    return keys.map((k) => String(k)).filter(Boolean)
  }, [props.elementLabelKeys])

  const elementMap = useMemo(() => {
    const v = props.value
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      return v as Record<string, any>
    }
    return {}
  }, [props.value])

  const elementEntries = useMemo(() => {
    const out = Object.entries(elementMap).map(([uid, cfg]) => ({ uid, cfg }))
    out.sort((a, b) => {
      const al = elementLabelKeys.map((k) => String(a.cfg?.[k] ?? '')).find((x) => x.trim()) || a.uid
      const bl = elementLabelKeys.map((k) => String(b.cfg?.[k] ?? '')).find((x) => x.trim()) || b.uid
      return al.toLowerCase().localeCompare(bl.toLowerCase())
    })
    return out
  }, [elementMap, elementLabelKeys])

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
    if (elementFields && elementFields.length) {
      const initial: Record<string, string> = {}
      elementFields.forEach((f) => {
        const raw = base[f.name]
        initial[f.name] = raw == null ? '' : String(raw)
      })
      setElementModalInitial(initial)
    } else {
      const json = cfg && typeof cfg === 'object' ? JSON.stringify(cfg, null, 2) : '{}'
      setElementModalInitial({ json })
    }
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
          </>
        ) : null}
      </div>

      <div className="pdvm-pic__control">
        {isElementList ? (
          <div className="pdvm-dialog__elementList">
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
            value={String(props.value ?? '')}
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
            value={String(props.value ?? '')}
            placeholder={props.placeholder}
            disabled={disabled}
              onBlur={() => {
                props.onBlur?.()
                if (!String(props.value ?? '').trim()) {
                  setNumberInputError(null)
                }
              }}
            onChange={(e) => {
                const raw = String(e.target.value || '')
                const digitsOnly = raw.replace(/[^1-9]+/g, '')
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
            value={String(props.value ?? '')}
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
            value={Array.isArray(props.value) ? props.value.map((v) => String(v)) : []}
            disabled={disabled}
            onBlur={props.onBlur}
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

        {effectiveType === 'true_false' ? (
          <label className="pdvm-pic__checkbox">
            <input
              id={props.id}
              type="checkbox"
              checked={!!props.value}
              disabled={disabled}
              onBlur={props.onBlur}
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
        kind="form"
        title={elementModalTitle}
        message={elementFields && elementFields.length ? 'Element bearbeiten' : 'Element als JSON bearbeiten'}
        fields={
          elementFields && elementFields.length
            ? elementFields.map((f) => ({
                name: f.name,
                label: f.label,
                type: f.type || 'text',
                placeholder: f.placeholder,
                required: f.required,
                options: f.options,
              }))
            : [{ name: 'json', label: 'Element', type: 'textarea', required: true, autoFocus: true }]
        }
        initialValues={elementModalInitial || undefined}
        error={elementModalError}
        confirmLabel="Speichern"
        cancelLabel="Abbrechen"
        onCancel={() => {
          setElementModalOpen(false)
          setElementModalError(null)
          setElementModalUid(null)
          setElementModalBase(null)
        }}
        onConfirm={(values) => {
          const uid = elementModalUid
          if (!uid) return
          if (elementFields && elementFields.length) {
            const base = elementModalBase ? JSON.parse(JSON.stringify(elementModalBase)) : {}
            elementFields.forEach((f) => {
              const raw = values[f.name]
              if ((f.type || 'text') === 'number') {
                const n = Number(raw)
                base[f.name] = Number.isFinite(n) ? n : 0
              } else {
                base[f.name] = raw
              }
            })
            const next = { ...elementMap, [uid]: base }
            props.onChange(next)
            setElementModalOpen(false)
            setElementModalError(null)
            setElementModalUid(null)
            setElementModalBase(null)
            return
          }

          try {
            const parsed = JSON.parse(String(values.json || '{}'))
            if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
              setElementModalError('Element muss ein JSON-Objekt sein.')
              return
            }
            const next = { ...elementMap, [uid]: parsed }
            props.onChange(next)
            setElementModalOpen(false)
            setElementModalError(null)
            setElementModalUid(null)
            setElementModalBase(null)
          } catch {
            setElementModalError('Ungueltiges JSON')
          }
        }}
      />
    </div>
  )
}
