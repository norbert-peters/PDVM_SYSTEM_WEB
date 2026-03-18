import { useEffect, useMemo, useRef, useState } from 'react'
import { PdvmDialogModal } from './PdvmDialogModal'
import { PdvmLookupSelect } from './PdvmLookupSelect'
import { PdvmDateTimePicker } from './PdvmDateTimePicker'
import { dateToPdvmFloat, pdvmFloatToDate, pdvmNowFloat } from '../../utils/pdvmDateTime'
import './PdvmInputControl.css'

export type PdvmInputType = 'string' | 'number' | 'text' | 'dropdown' | 'multi_dropdown' | 'true_false' | 'datetime' | 'date' | 'time' | 'go_select_view' | 'element_list' | 'elemente_list' | 'group_list'

export type PdvmDropdownOption = { value: string; label: string }
export type PdvmElementField = {
  name: string
  label: string
  type?: 'string' | 'text' | 'textarea' | 'number' | 'dropdown' | 'multi_dropdown' | 'true_false' | 'go_select_view'
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

function getValueByKeyCaseInsensitive(source: Record<string, any> | null | undefined, key: string): any {
  const obj = source && typeof source === 'object' ? source : {}
  const k = String(key || '').trim()
  if (!k) return undefined
  if (Object.prototype.hasOwnProperty.call(obj, k)) return (obj as any)[k]
  const up = k.toUpperCase()
  if (Object.prototype.hasOwnProperty.call(obj, up)) return (obj as any)[up]
  const low = k.toLowerCase()
  if (Object.prototype.hasOwnProperty.call(obj, low)) return (obj as any)[low]
  return undefined
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
  if (t === 'go_select_view') return 'go_select_view'
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
  if (t === 'datetime') return 'datetime'
  if (t === 'date') return 'date'
  if (t === 'time') return 'time'
  if (t === 'go_select_view' || t === 'selected_view' || t === 'lookup') return 'go_select_view'
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

function toIsoLocalString(date: Date): string {
  const yyyy = String(date.getFullYear()).padStart(4, '0')
  const mm = String(date.getMonth() + 1).padStart(2, '0')
  const dd = String(date.getDate()).padStart(2, '0')
  const hh = String(date.getHours()).padStart(2, '0')
  const mi = String(date.getMinutes()).padStart(2, '0')
  const ss = String(date.getSeconds()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}T${hh}:${mi}:${ss}`
}

function parsePdvmTimeOnlyToDate(value: any): Date | null {
  const n = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(n)) return null
  const fraction = Math.abs(n)
  if (fraction <= 0 || fraction >= 1) return null
  const base = new Date(2000, 0, 1, 0, 0, 0, 0)
  const totalSeconds = Math.round(fraction * 86400)
  base.setSeconds(totalSeconds)
  return base
}

function toPickerIsoValue(value: any, mode: 'datetime' | 'date' | 'time'): string | null {
  if (value === null || value === undefined || value === '') return null

  const asDateFromPdvm = pdvmFloatToDate(value)
  if (asDateFromPdvm) return toIsoLocalString(asDateFromPdvm)

  if (mode === 'time') {
    const timeOnlyDate = parsePdvmTimeOnlyToDate(value)
    if (timeOnlyDate) return toIsoLocalString(timeOnlyDate)
  }

  if (typeof value === 'string') {
    const s = value.trim()
    if (!s) return null
    const fromIso = new Date(s)
    if (!Number.isNaN(fromIso.getTime())) return toIsoLocalString(fromIso)
  }

  return null
}

function fromPickerIsoToPdvm(value: string, mode: 'datetime' | 'date' | 'time'): number | null {
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return null

  if (mode === 'datetime') {
    return dateToPdvmFloat(dt)
  }

  if (mode === 'date') {
    dt.setHours(0, 0, 0, 0)
    return dateToPdvmFloat(dt)
  }

  // mode === 'time': interner Tag immer 0, nur Zeit-Fraction speichern
  const seconds = dt.getHours() * 3600 + dt.getMinutes() * 60 + dt.getSeconds()
  const fraction = seconds / 86400
  return Number(fraction.toFixed(5))
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

function cloneAny<T>(value: T): T {
  if (value == null) return value
  try {
    return JSON.parse(JSON.stringify(value)) as T
  } catch {
    return value
  }
}

function stableStringify(value: any): string {
  if (value === undefined) return '__PDVM_UNDEFINED__'
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function normalizeDebugValueEnvelope(debugValue: any, fallbackValue: any): Record<string, any> {
  const obj = debugValue && typeof debugValue === 'object' && !Array.isArray(debugValue) ? { ...(debugValue as Record<string, any>) } : {}
  const hasOriginal = Object.prototype.hasOwnProperty.call(obj, 'ORIGINAL')
  const originalValue = hasOriginal ? obj.ORIGINAL : undefined
  const originalIsEmpty = !hasOriginal || originalValue === null || originalValue === undefined
  const originalIsTransientEmptyString = typeof originalValue === 'string' && originalValue.length === 0
  const fallbackExists = fallbackValue !== undefined && fallbackValue !== null
  const fallbackIsMeaningful =
    fallbackExists &&
    (typeof fallbackValue !== 'string' || fallbackValue.length > 0)

  if (!hasOriginal || (originalIsEmpty && fallbackExists) || (originalIsTransientEmptyString && fallbackIsMeaningful)) {
    obj.ORIGINAL = cloneAny(fallbackValue)
  }
  return obj
}

function sortTimelineKeys(keys: string[]): string[] {
  const unique = Array.from(new Set(keys.map((k) => String(k || '').trim()).filter(Boolean)))
  const originals = unique.filter((k) => k.toUpperCase() === 'ORIGINAL')
  const others = unique.filter((k) => k.toUpperCase() !== 'ORIGINAL')

  others.sort((a, b) => {
    const an = Number(a)
    const bn = Number(b)
    const aIsNum = Number.isFinite(an)
    const bIsNum = Number.isFinite(bn)
    if (aIsNum && bIsNum) return an - bn
    if (aIsNum && !bIsNum) return -1
    if (!aIsNum && bIsNum) return 1
    return a.localeCompare(b)
  })

  return [...originals, ...others]
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
  lookupTable?: string
  helpText?: string | null
  helpEnabled?: boolean
  controlDebug?: Record<string, any> | null
  elementTemplate?: Record<string, any> | null
  elementLabelKeys?: string[]
  elementUidLabels?: Record<string, string>
  elementFields?: PdvmElementField[]
  elementDraftHydrator?: (draft: Record<string, any>, uid?: string | null) => Record<string, any>
  elementDraftNormalizer?: (draft: Record<string, any>, uid?: string | null) => Record<string, any>
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
  const [multiAddValue, setMultiAddValue] = useState<string>('')

  const controlDebugRaw = props.controlDebug && typeof props.controlDebug === 'object' ? (props.controlDebug as Record<string, any>) : null
  const controlDebugFieldKey = String(controlDebugRaw?.FIELD_KEY || '').trim() || props.id || props.label
  const initialTimeline = useMemo(
    () => normalizeDebugValueEnvelope(controlDebugRaw?.VALUE, props.value),
    [controlDebugRaw, props.value]
  )
  const initialTimeKey = useMemo(() => {
    const rawKey = String(controlDebugRaw?.VALUE_TIME_KEY || '').trim()
    if (rawKey && Object.prototype.hasOwnProperty.call(initialTimeline, rawKey)) return rawKey
    return 'ORIGINAL'
  }, [controlDebugRaw, initialTimeline])
  const [debugTimeline, setDebugTimeline] = useState<Record<string, any>>(initialTimeline)
  const [debugTimeKey, setDebugTimeKey] = useState<string>(initialTimeKey)
  const timelineKeys = useMemo(() => sortTimelineKeys(Object.keys(debugTimeline)), [debugTimeline])
  const activeTimelineIndex = useMemo(() => {
    const idx = timelineKeys.indexOf(debugTimeKey)
    return idx >= 0 ? idx : 0
  }, [timelineKeys, debugTimeKey])
  const lastValueSnapshotRef = useRef<string>(stableStringify(props.value))
  const debugFieldRef = useRef<string>(controlDebugFieldKey)
  const pendingNavigateRef = useRef<string | null>(null)

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
  const showControlButton = useMemo(() => {
    const ctrl = controlDebugRaw || null
    if (!ctrl || typeof ctrl !== 'object') return false
    const hasData = Object.keys(ctrl).length > 0
    if (!hasData) return false
    const forceDebug = (ctrl as any).FORCE_DEBUG_BUTTON ?? false
    const raw = (ctrl as any).EXPERT_MODE ?? (ctrl as any).expert_mode ?? false
    return !!forceDebug || !!raw
  }, [controlDebugRaw])
  const multiDropdownValue = useMemo(() => normalizeMultiDropdownValue(props.value), [props.value])
  const optionMap = useMemo(() => {
    const map = new Map<string, string>()
    ;(props.options || []).forEach((opt) => {
      const key = String(opt.value || '').trim()
      if (!key) return
      map.set(key, String(opt.label || opt.value || '').trim() || key)
    })
    return map
  }, [props.options])
  const availableMultiOptions = useMemo(() => {
    const selected = new Set(multiDropdownValue)
    return (props.options || []).filter((opt) => {
      const key = String(opt.value || '').trim()
      return key && !selected.has(key)
    })
  }, [props.options, multiDropdownValue])
  const trueFalseValue = useMemo(() => normalizeTrueFalseValue(props.value), [props.value])
  const textValue = useMemo(() => normalizeTextValue(props.value), [props.value])
  const stringValue = useMemo(() => normalizeStringValue(props.value), [props.value])
  const numberValue = useMemo(() => normalizeNumberValue(props.value), [props.value])
  const dateTimeMode = useMemo(() => {
    if (effectiveType === 'date') return 'date' as const
    if (effectiveType === 'time') return 'time' as const
    return 'datetime' as const
  }, [effectiveType])
  const pickerIsoValue = useMemo(() => {
    if (effectiveType !== 'datetime' && effectiveType !== 'date' && effectiveType !== 'time') return null
    return toPickerIsoValue(props.value, dateTimeMode)
  }, [effectiveType, props.value, dateTimeMode])

  useEffect(() => {
    if (debugFieldRef.current === controlDebugFieldKey) return

    debugFieldRef.current = controlDebugFieldKey
    const nextTimeline = normalizeDebugValueEnvelope(controlDebugRaw?.VALUE, props.value)
    const nextRawTimeKey = String(controlDebugRaw?.VALUE_TIME_KEY || '').trim()
    const nextTimeKey = nextRawTimeKey && Object.prototype.hasOwnProperty.call(nextTimeline, nextRawTimeKey) ? nextRawTimeKey : 'ORIGINAL'

    setDebugTimeline(nextTimeline)
    setDebugTimeKey(nextTimeKey)
    lastValueSnapshotRef.current = stableStringify(props.value)
    pendingNavigateRef.current = null
  }, [controlDebugFieldKey, controlDebugRaw, props.value])

  useEffect(() => {
    const currentSnapshot = stableStringify(props.value)
    const previousSnapshot = lastValueSnapshotRef.current
    if (currentSnapshot === previousSnapshot) return

    const pendingKey = pendingNavigateRef.current
    if (pendingKey) {
      pendingNavigateRef.current = null
      setDebugTimeKey(pendingKey)
      lastValueSnapshotRef.current = currentSnapshot
      return
    }

    setDebugTimeline((prev) => {
      const next = normalizeDebugValueEnvelope(prev, props.value)
      const activeKey = Object.prototype.hasOwnProperty.call(next, debugTimeKey) ? debugTimeKey : 'ORIGINAL'
      const activeSnapshot = stableStringify(next[activeKey])

      if (activeSnapshot === currentSnapshot) {
        lastValueSnapshotRef.current = currentSnapshot
        return next
      }

      const tsKey = String(pdvmNowFloat())
      next[tsKey] = cloneAny(props.value)
      setDebugTimeKey(tsKey)
      lastValueSnapshotRef.current = currentSnapshot
      return next
    })
  }, [props.value, debugTimeKey])

  useEffect(() => {
    if (!multiAddValue) return
    const exists = availableMultiOptions.some((opt) => String(opt.value || '').trim() === multiAddValue)
    if (!exists) setMultiAddValue('')
  }, [multiAddValue, availableMultiOptions])

  useEffect(() => {
    if (!elementModalOpen) return
    if (!props.elementDraftHydrator) return
    if (!elementModalDraft || typeof elementModalDraft !== 'object') return

    const hydrated = props.elementDraftHydrator(elementModalDraft, elementModalUid)
    const before = stableStringify(elementModalDraft)
    const after = stableStringify(hydrated)
    if (before === after) return
    setElementModalDraft(hydrated)
  }, [elementModalOpen, props.elementDraftHydrator, elementModalDraft, elementModalUid])

  const controlDebugPayload = useMemo(() => {
    const base = controlDebugRaw ? { ...controlDebugRaw } : {}
    const sourcePath = String((base as any).SOURCE_PATH ?? (base as any).source_path ?? '').trim()
    if (!sourcePath) {
      ;(base as any).SOURCE_PATH = 'root'
    }

    return {
      ...base,
      FIELD_KEY: String((base as any).FIELD_KEY || controlDebugFieldKey).trim() || controlDebugFieldKey,
      VALUE: normalizeDebugValueEnvelope(debugTimeline, props.value),
      VALUE_TIME_KEY: debugTimeKey,
    }
  }, [controlDebugRaw, controlDebugFieldKey, debugTimeline, debugTimeKey, props.value])

  const goTimeline = (direction: -1 | 1) => {
    if (!timelineKeys.length) return
    const targetIndex = activeTimelineIndex + direction
    if (targetIndex < 0 || targetIndex >= timelineKeys.length) return

    const nextKey = timelineKeys[targetIndex]
    setDebugTimeKey(nextKey)

    const nextValue = (controlDebugPayload.VALUE || {})[nextKey]
    if (disabled) return

    pendingNavigateRef.current = nextKey
    props.onChange(cloneAny(nextValue))
  }

  const debugSourcePath = String((controlDebugPayload as any)?.SOURCE_PATH ?? (controlDebugPayload as any)?.source_path ?? '').trim()
  const debugFieldKey = String((controlDebugPayload as any)?.FIELD_KEY ?? '').trim()
  const debugActiveValue = (controlDebugPayload as any)?.VALUE?.[debugTimeKey]
  const debugActiveType = Array.isArray(debugActiveValue) ? 'array' : typeof debugActiveValue
  const debugDropdownTableToken = String((controlDebugPayload as any)?.DROPDOWN_TABLE_TOKEN ?? '').trim()
  const debugDropdownTableResolved = String((controlDebugPayload as any)?.DROPDOWN_TABLE_RESOLVED ?? '').trim()
  const debugDropdownTableWarning = String((controlDebugPayload as any)?.DROPDOWN_TABLE_WARNING ?? '').trim()
  const debugMultiDropdownTableToken = String((controlDebugPayload as any)?.MULTI_DROPDOWN_TABLE_TOKEN ?? '').trim()
  const debugMultiDropdownTableResolved = String((controlDebugPayload as any)?.MULTI_DROPDOWN_TABLE_RESOLVED ?? '').trim()
  const debugMultiDropdownTableWarning = String((controlDebugPayload as any)?.MULTI_DROPDOWN_TABLE_WARNING ?? '').trim()
  const debugDateTimeMode = String((controlDebugPayload as any)?.DATETIME_MODE ?? '').trim()
  const debugDateTimeRaw = (controlDebugPayload as any)?.DATETIME_PDVM_RAW

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

      const existing = new Set(ordered.map((f) => String(f.name || '').trim().toUpperCase()).filter(Boolean))
      const draftObj = elementModalDraft && typeof elementModalDraft === 'object' ? elementModalDraft : {}
      let order = (Math.max(0, ...ordered.map((f) => Number(f.display_order || 0))) || 0) + 10

      Object.keys(draftObj)
        .map((k) => String(k || '').trim())
        .filter(Boolean)
        .forEach((key) => {
          const keyUpper = key.toUpperCase()
          if (existing.has(keyUpper)) return
          const raw = (draftObj as any)[key]
          let inferredType: PdvmElementField['type'] = 'string'
          if (typeof raw === 'number') inferredType = 'number'
          else if (typeof raw === 'boolean') inferredType = 'true_false'
          else if (Array.isArray(raw)) inferredType = 'multi_dropdown'

          ordered.push({
            name: keyUpper,
            label: keyUpper,
            type: inferredType,
            SAVE_PATH: keyUpper,
            display_order: order,
          })
          existing.add(keyUpper)
          order += 10
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
  }, [elementFields, elementModalBase, elementModalDraft])

  const getElementLabel = (cfg: any, uid: string) => {
    for (const key of elementLabelKeys) {
      const v = getValueByKeyCaseInsensitive(cfg, key)
      const s = v != null ? String(v).trim() : ''
      if (key.toUpperCase() === 'FIELD' && s && props.elementUidLabels) {
        const byFieldUid = String(props.elementUidLabels[s] || '').trim()
        if (byFieldUid) return byFieldUid
      }
      if (s) return s
    }
    const byUid = props.elementUidLabels ? String(props.elementUidLabels[uid] || '').trim() : ''
    if (byUid) return byUid
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
    const source = cfg && typeof cfg === 'object' ? JSON.parse(JSON.stringify(cfg)) : {}
    const base = props.elementDraftHydrator ? props.elementDraftHydrator(source, uid) : source
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

    const draftRaw = elementModalDraft && typeof elementModalDraft === 'object' ? JSON.parse(JSON.stringify(elementModalDraft)) : {}
    let draft = draftRaw
    try {
      draft = props.elementDraftNormalizer ? props.elementDraftNormalizer(draftRaw, uid) : draftRaw
    } catch (err: any) {
      const msg = String(err?.message || 'Element konnte nicht gespeichert werden.')
      setElementModalError(msg)
      return
    }

    let targetUid = uid
    if (draft && typeof draft === 'object') {
      const normalizedUid = String((draft as any).__ELEMENT_UID || '').trim()
      if (normalizedUid) targetUid = normalizedUid
      if (Object.prototype.hasOwnProperty.call(draft, '__ELEMENT_UID')) {
        const nextDraft = { ...(draft as any) }
        delete nextDraft.__ELEMENT_UID
        draft = nextDraft
      }
    }

    for (const field of elementModalFields) {
      if (!field.required) continue
      const savePath = String(field.SAVE_PATH || field.name || '').trim()
      let raw = getValueByPath(draft, savePath)
      if ((raw == null || String(raw).trim() === '') && /^feld$/i.test(savePath) && targetUid) {
        raw = targetUid
      }
      if (raw == null || String(raw).trim() === '') {
        raw = getValueByPath(draftRaw, savePath)
      }
      const text = raw == null ? '' : String(raw).trim()
      if (!text) {
        setElementModalError(`${field.label}: Pflichtfeld`)
        return
      }
    }

    const next = { ...elementMap }
    if (targetUid !== uid) {
      delete next[uid]
    }
    next[targetUid] = draft
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

        {effectiveType === 'go_select_view' ? (
          <PdvmLookupSelect
            table={String(props.lookupTable || '').trim()}
            value={props.value ? String(props.value) : null}
            onChange={(v) => props.onChange(v)}
            disabled={disabled}
          />
        ) : null}

        {(effectiveType === 'datetime' || effectiveType === 'date' || effectiveType === 'time') ? (
          <PdvmDateTimePicker
            value={pickerIsoValue}
            onChange={(newIso) => {
              const pdvmValue = fromPickerIsoToPdvm(newIso, dateTimeMode)
              props.onChange(pdvmValue)
            }}
            onClear={() => props.onChange(null)}
            allowClear
            mode={dateTimeMode}
            showTime={effectiveType !== 'date'}
            label={props.placeholder || props.label}
            readOnly={disabled}
            popoverAlign="auto"
          />
        ) : null}

        {effectiveType === 'multi_dropdown' ? (
          <div className="pdvm-pic__multiSelect">
            <div className="pdvm-pic__multiSelected">
              {multiDropdownValue.length ? (
                multiDropdownValue.map((value) => {
                  const label = optionMap.get(value) || value
                  return (
                    <span key={value} className="pdvm-pic__chip">
                      <span className="pdvm-pic__chipLabel">{label}</span>
                      <button
                        type="button"
                        className="pdvm-pic__chipRemove"
                        disabled={disabled}
                        onClick={() => {
                          const next = multiDropdownValue.filter((v) => v !== value)
                          props.onChange(next)
                        }}
                        aria-label={`Auswahl ${label} entfernen`}
                        title="Auswahl entfernen"
                      >
                        x
                      </button>
                    </span>
                  )
                })
              ) : (
                <div className="pdvm-pic__multiHint">Keine Auswahl</div>
              )}
            </div>

            <div className="pdvm-pic__multiAddRow">
              <select
                id={props.id}
                className="pdvm-pic__select"
                value={multiAddValue}
                disabled={disabled || availableMultiOptions.length === 0}
                onBlur={props.onBlur}
                onChange={(e) => setMultiAddValue(String(e.target.value || '').trim())}
              >
                <option value="">(Wert auswählen)</option>
                {availableMultiOptions.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="pdvm-dialog__toolBtn"
                disabled={disabled || !multiAddValue}
                onClick={() => {
                  if (!multiAddValue) return
                  const next = Array.from(new Set([...multiDropdownValue, multiAddValue]))
                  props.onChange(next)
                  setMultiAddValue('')
                }}
              >
                Hinzufuegen
              </button>
            </div>
          </div>
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
        message={
          <div style={{ display: 'grid', gap: 8 }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', justifyContent: 'flex-end' }}>
              <button
                type="button"
                className="pdvm-dialog__toolBtn"
                onClick={() => goTimeline(-1)}
                disabled={activeTimelineIndex <= 0}
                title="Zurück"
                aria-label="Zurück"
              >
                {'<'}
              </button>
              <div style={{ fontSize: 12, opacity: 0.8 }}>
                {timelineKeys.length ? `${activeTimelineIndex + 1}/${timelineKeys.length}` : '0/0'} · {debugTimeKey}
              </div>
              <button
                type="button"
                className="pdvm-dialog__toolBtn"
                onClick={() => goTimeline(1)}
                disabled={activeTimelineIndex >= timelineKeys.length - 1}
                title="Vor"
                aria-label="Vor"
              >
                {'>'}
              </button>
            </div>
            <div style={{ fontSize: 12, opacity: 0.82, lineHeight: 1.45 }}>
              <div><strong>SOURCE_PATH:</strong> {debugSourcePath || 'root'}</div>
              <div><strong>FIELD_KEY:</strong> {debugFieldKey || '-'}</div>
              <div><strong>ACTIVE_TYPE:</strong> {debugActiveType}</div>
              {debugDateTimeMode ? <div><strong>DATETIME_MODE:</strong> {debugDateTimeMode}</div> : null}
              {debugDateTimeMode ? <div><strong>DATETIME_PDVM_RAW:</strong> {String(debugDateTimeRaw ?? '')}</div> : null}
              {debugDropdownTableToken ? <div><strong>DROPDOWN.TABLE:</strong> {debugDropdownTableToken}</div> : null}
              {debugDropdownTableResolved ? <div><strong>DROPDOWN.TABLE_RESOLVED:</strong> {debugDropdownTableResolved}</div> : null}
              {debugMultiDropdownTableToken ? <div><strong>MULTI_DROPDOWN.TABLE:</strong> {debugMultiDropdownTableToken}</div> : null}
              {debugMultiDropdownTableResolved ? <div><strong>MULTI_DROPDOWN.TABLE_RESOLVED:</strong> {debugMultiDropdownTableResolved}</div> : null}
            </div>
            {debugDropdownTableWarning || debugMultiDropdownTableWarning ? (
              <div
                style={{
                  fontSize: 12,
                  color: '#b42318',
                  border: '1px solid rgba(180,35,24,0.35)',
                  background: 'rgba(180,35,24,0.08)',
                  borderRadius: 6,
                  padding: '6px 8px',
                }}
              >
                ⚠️ {debugDropdownTableWarning || debugMultiDropdownTableWarning}
              </div>
            ) : null}
            <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{JSON.stringify(controlDebugPayload, null, 2)}</pre>
          </div>
        }
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
                const nestedSavePath = String(field.SAVE_PATH || field.name || '').trim()
                const nestedValue = (() => {
                  if (!nestedSavePath || !elementModalDraft || typeof elementModalDraft !== 'object') return ''
                  return getValueByPath(elementModalDraft as Record<string, any>, nestedSavePath)
                })()
                nestedControlDebug.SOURCE_PATH = String(nestedControlDebug.SOURCE_PATH || nestedControlDebug.source_path || `root.${String(props.id || props.label || 'ELEMENT').replace(/\s+/g, '_')}`)
                nestedControlDebug.FIELD_KEY = String(nestedControlDebug.FIELD_KEY || `ELEMENT.${field.name}`)
                nestedControlDebug.VALUE = normalizeDebugValueEnvelope(nestedControlDebug.VALUE, nestedValue)
                nestedControlDebug.VALUE_TIME_KEY = String(nestedControlDebug.VALUE_TIME_KEY || 'ORIGINAL').trim() || 'ORIGINAL'
                return (
                  <PdvmInputControl
                    key={`element-modal-${field.name}`}
                    label={field.required ? `${field.label} *` : field.label}
                    tooltip={field.tooltip || null}
                    type={fieldType}
                    value={nestedValue}
                    options={field.options || []}
                    lookupTable={
                      fieldType === 'go_select_view'
                        ? String(
                            (field as any).lookupTable ||
                              (field as any).LOOKUP_TABLE ||
                              (field as any)?.configs?.go_select_view?.table ||
                              ''
                          ).trim() || undefined
                        : undefined
                    }
                    placeholder={field.placeholder}
                    helpEnabled={true}
                    helpText={field.help_text || field.tooltip || null}
                    controlDebug={nestedControlDebug}
                    onChange={(value) => {
                      setElementModalDraft((prev) => {
                        const base = prev && typeof prev === 'object' ? prev : {}
                        const savePath = String(field.SAVE_PATH || field.name || '').trim()
                        if (!savePath) return base
                        const updated = {
                          ...setValueByPath(base, savePath, value),
                        }
                        return props.elementDraftHydrator ? props.elementDraftHydrator(updated, elementModalUid) : updated
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
