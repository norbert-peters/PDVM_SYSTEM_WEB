import { useEffect, useMemo, useRef, useState } from 'react'
import { PdvmDialogModal } from './PdvmDialogModal'
import { PdvmLookupSelect } from './PdvmLookupSelect'
import { PdvmDateTimePicker } from './PdvmDateTimePicker'
import { dateToPdvmFloat, pdvmFloatToDate, pdvmNowFloat } from '../../utils/pdvmDateTime'
import './PdvmInputControl.css'

export type PdvmInputType = 'string' | 'number' | 'text' | 'dropdown' | 'multi_dropdown' | 'true_false' | 'datetime' | 'date' | 'time' | 'go_select_view' | 'element_list' | 'elemente_list' | 'group_list'

export type PdvmDropdownOption = { value: string; label: string; disabled?: boolean }
export type PdvmElementDefinition = {
  uid: string
  label: string
  template?: Record<string, any>
  frameGuid?: string
  noFields?: boolean
  sourcePath?: string
}
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

function asObject(value: any): Record<string, any> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, any>) : {}
}

function readCfgValue(cfg: any, keys: string[]): any {
  const obj = asObject(cfg)
  for (const key of keys) {
    if (!key) continue
    if (Object.prototype.hasOwnProperty.call(obj, key)) return (obj as any)[key]
    const upper = key.toUpperCase()
    if (Object.prototype.hasOwnProperty.call(obj, upper)) return (obj as any)[upper]
    const lower = key.toLowerCase()
    if (Object.prototype.hasOwnProperty.call(obj, lower)) return (obj as any)[lower]
  }
  return undefined
}

function normalizeSourcePath(raw: any): string {
  const path = String(raw || '').trim()
  return path || 'root'
}

function isRootSourcePath(pathRaw: any): boolean {
  const path = String(pathRaw || '').trim().toLowerCase()
  return !path || path === 'root' || path === '__root__' || path === '__top__'
}

function resolveGoSelectTableV11(params: {
  resolvedConfigs: any
  legacyLookupTable?: string
  sourceContext?: Record<string, any> | null
  sourcePath?: string
}): string {
  const cfg = asObject(params.resolvedConfigs)
  const goSelect = asObject(readCfgValue(cfg, ['go_select_view']))

  const modeRaw = String(readCfgValue(goSelect, ['table_mode']) || '').trim().toLowerCase()
  const staticTable = String(readCfgValue(goSelect, ['table']) || '').trim()
  const tablePath = String(readCfgValue(goSelect, ['table_path']) || '').trim()
  const mode = modeRaw === 'static' || modeRaw === 'from_path'
    ? modeRaw
    : (staticTable ? 'static' : (tablePath ? 'from_path' : ''))

  if (mode === 'static') {
    return staticTable || String(params.legacyLookupTable || '').trim()
  }

  if (mode === 'from_path') {
    const context = asObject(params.sourceContext)
    const sourcePath = normalizeSourcePath(params.sourcePath)

    const resolveSourceRoot = (): Record<string, any> => {
      if (isRootSourcePath(sourcePath)) return context

      const direct = getValueByPathCaseInsensitive(context, sourcePath)
      if (direct && typeof direct === 'object' && !Array.isArray(direct)) return asObject(direct)

      // Falls der Context bereits auf SOURCE_PATH zeigt, pruefen wir den abgeschnittenen Root-Pfad.
      const stripped = sourcePath.replace(/^root\.?/i, '')
      if (stripped) {
        const nested = getValueByPathCaseInsensitive(context, stripped)
        if (nested && typeof nested === 'object' && !Array.isArray(nested)) return asObject(nested)
      }

      return context
    }

    const sourceRoot = resolveSourceRoot()
    const tableRaw = tablePath
      ? getValueByPathCaseInsensitive(sourceRoot, tablePath)
      : undefined
    const table = String(tableRaw || '').trim()
    if (table) return table

    // Relative/absolute Fallback fuer TABLE_PATH.
    if (tablePath) {
      const absoluteTry = String(getValueByPathCaseInsensitive(context, tablePath) || '').trim()
      if (absoluteTry) return absoluteTry
    }

    return String(params.legacyLookupTable || '').trim()
  }

  return String(params.legacyLookupTable || '').trim()
}

function resolveElementAddSelectorConfig(resolvedConfigs: any): { goSelectConfig: Record<string, any>; sourcePath?: string } {
  const cfg = asObject(resolvedConfigs)

  const directAdd = asObject(readCfgValue(cfg, ['element_add', 'ELEMENT_ADD']))
  const directAddGoSelect = asObject(readCfgValue(directAdd, ['go_select_view']))
  if (Object.keys(directAddGoSelect).length) {
    return {
      goSelectConfig: directAddGoSelect,
      sourcePath: String(readCfgValue(directAdd, ['source_path', 'SOURCE_PATH']) || '').trim() || undefined,
    }
  }

  const elementCfg = asObject(readCfgValue(cfg, ['element']))
  const elementAdd = asObject(readCfgValue(elementCfg, ['add_select', 'add_selector', 'element_add']))
  const elementAddGoSelect = asObject(readCfgValue(elementAdd, ['go_select_view']))
  if (Object.keys(elementAddGoSelect).length) {
    return {
      goSelectConfig: elementAddGoSelect,
      sourcePath: String(readCfgValue(elementAdd, ['source_path', 'SOURCE_PATH']) || '').trim() || undefined,
    }
  }

  const legacyElementGoSelect = asObject(readCfgValue(elementCfg, ['go_select_view']))
  if (Object.keys(legacyElementGoSelect).length) {
    return {
      goSelectConfig: legacyElementGoSelect,
      sourcePath: String(readCfgValue(elementCfg, ['source_path', 'SOURCE_PATH']) || '').trim() || undefined,
    }
  }

  return { goSelectConfig: {} }
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

function getValueByPathCaseInsensitive(source: Record<string, any> | null | undefined, path: string): any {
  const obj = source && typeof source === 'object' ? source : {}
  const parts = String(path || '')
    .split('.')
    .map((p) => p.trim())
    .filter(Boolean)
  if (!parts.length) return undefined

  let cursor: any = obj
  for (const part of parts) {
    if (!cursor || typeof cursor !== 'object') return undefined

    if (Object.prototype.hasOwnProperty.call(cursor, part)) {
      cursor = cursor[part]
      continue
    }

    const match = Object.keys(cursor).find((k) => String(k || '').toLowerCase() === part.toLowerCase())
    if (!match) return undefined
    cursor = cursor[match]
  }

  return cursor
}

function setValueByPathPreferExistingCase(target: Record<string, any>, path: string, value: any): Record<string, any> {
  const parts = String(path || '')
    .split('.')
    .map((p) => p.trim())
    .filter(Boolean)
  if (!parts.length) return target

  const out = { ...target }
  let cursor: any = out

  parts.forEach((part, idx) => {
    const existingKey = Object.keys(cursor).find((k) => String(k || '').toLowerCase() === part.toLowerCase())
    const resolvedKey = existingKey || part

    if (idx === parts.length - 1) {
      cursor[resolvedKey] = value
      return
    }

    const next = cursor[resolvedKey]
    if (!next || typeof next !== 'object' || Array.isArray(next)) {
      cursor[resolvedKey] = {}
    } else {
      cursor[resolvedKey] = { ...next }
    }
    cursor = cursor[resolvedKey]
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

function hasMeaningfulElementValue(value: any): boolean {
  if (value === null || value === undefined) return false
  if (typeof value === 'string') return value.trim().length > 0
  if (typeof value === 'number') return Number.isFinite(value)
  if (typeof value === 'boolean') return true
  if (Array.isArray(value)) return value.some((entry) => hasMeaningfulElementValue(entry))
  if (typeof value === 'object') {
    const entries = Object.entries(value)
    if (!entries.length) return false
    return entries.some(([, v]) => hasMeaningfulElementValue(v))
  }
  return true
}

function normalizeOccupiedCollectionValue(value: any): Record<string, any> {
  const raw = normalizeCollectionValue(value)
  const out: Record<string, any> = {}
  Object.entries(raw).forEach(([key, row]) => {
    const uid = String(key || '').trim()
    if (!uid) return
    if (!hasMeaningfulElementValue(row)) return
    out[uid] = row
  })
  return out
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
  resolvedConfigs?: Record<string, any>
  goSelectSourceContext?: Record<string, any> | null
  goSelectSourcePath?: string
  lookupTable?: string
  helpText?: string | null
  helpEnabled?: boolean
  controlDebug?: Record<string, any> | null
  elementTemplate?: Record<string, any> | null
  elementLabelKeys?: string[]
  elementUidLabels?: Record<string, string>
  onElementListCommit?: (nextValue: Record<string, any>) => void | Promise<void>
  elementFields?: PdvmElementField[]
  elementFieldsByUid?: Record<string, PdvmElementField[]>
  elementDefinitions?: PdvmElementDefinition[]
  elementFrameType?: string
  elementValidationError?: string | null
  elementDraftHydrator?: (draft: Record<string, any>, uid?: string | null) => Record<string, any>
  elementDraftNormalizer?: (draft: Record<string, any>, uid?: string | null) => Record<string, any>
  resolutionWarning?: string | null
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
  const [elementListGuardrailError, setElementListGuardrailError] = useState<string | null>(null)
  const [elementAddDefinitionUid, setElementAddDefinitionUid] = useState<string>('')
  const [elementAddLookupUid, setElementAddLookupUid] = useState<string>('')
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
  const effectiveLookupTable = useMemo(() => {
    return resolveGoSelectTableV11({
      resolvedConfigs: props.resolvedConfigs,
      legacyLookupTable: props.lookupTable,
      sourceContext: props.goSelectSourceContext,
      sourcePath: props.goSelectSourcePath,
    })
  }, [props.resolvedConfigs, props.lookupTable, props.goSelectSourceContext, props.goSelectSourcePath])
  const elementAddSelector = useMemo(() => {
    return resolveElementAddSelectorConfig(props.resolvedConfigs)
  }, [props.resolvedConfigs])
  const elementAddLookupTable = useMemo(() => {
    if (!Object.keys(elementAddSelector.goSelectConfig).length) return ''
    return resolveGoSelectTableV11({
      resolvedConfigs: { go_select_view: elementAddSelector.goSelectConfig },
      sourceContext: props.goSelectSourceContext,
      sourcePath: elementAddSelector.sourcePath || props.goSelectSourcePath,
    })
  }, [elementAddSelector, props.goSelectSourceContext, props.goSelectSourcePath])
  const helpEnabled = props.helpEnabled ?? true
  const isElementList = effectiveType === 'element_list' || effectiveType === 'elemente_list' || effectiveType === 'group_list'
  const elementFrameType = useMemo(() => String(props.elementFrameType || '').trim().toLowerCase(), [props.elementFrameType])
  const isElementFrameTypeList = elementFrameType === 'element_list'
  const isElementFrameTypeSingle = elementFrameType === 'element'
  const useElementAddLookupSelector = useMemo(() => {
    return isElementList && !isElementFrameTypeSingle && !!String(elementAddLookupTable || '').trim()
  }, [isElementList, isElementFrameTypeSingle, elementAddLookupTable])
  const elementFields = useMemo(() => {
    return Array.isArray(props.elementFields) ? props.elementFields : null
  }, [props.elementFields])
  const elementDefinitions = useMemo(() => {
    const defs = Array.isArray(props.elementDefinitions) ? props.elementDefinitions : []
    const out: PdvmElementDefinition[] = []
    const seen = new Set<string>()
    defs.forEach((d) => {
      const uid = String(d?.uid || '').trim()
      if (!uid || seen.has(uid)) return
      seen.add(uid)
      out.push({
        uid,
        label: String(d?.label || uid).trim() || uid,
        template: d?.template && typeof d.template === 'object' ? d.template : undefined,
        frameGuid: String((d as any)?.frameGuid || '').trim() || undefined,
      })
    })
    return out
  }, [props.elementDefinitions])
  const elementFieldsByUid = useMemo(() => {
    const source = props.elementFieldsByUid && typeof props.elementFieldsByUid === 'object'
      ? (props.elementFieldsByUid as Record<string, PdvmElementField[]>)
      : {}
    const out: Record<string, PdvmElementField[]> = {}
    Object.entries(source).forEach(([uid, fields]) => {
      const key = String(uid || '').trim()
      if (!key) return
      if (!Array.isArray(fields) || fields.length === 0) return
      out[key] = fields
    })
    return out
  }, [props.elementFieldsByUid])
  const elementListHasDefinitionSource = !isElementFrameTypeList || elementDefinitions.length > 0
  const structuralElementGuardrailError = useMemo(() => {
    const explicit = String(props.elementValidationError || '').trim()
    if (explicit) return explicit
    if (!elementListHasDefinitionSource) {
      return 'Speichern blockiert: FRAME_TYPE=element_list benötigt eine gültige ELEMENTS-Definitionsquelle im Template-Frame.'
    }
    return null
  }, [props.elementValidationError, elementListHasDefinitionSource])
  const effectiveElementGuardrailError = elementListGuardrailError || structuralElementGuardrailError

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
  const optionKeyByLower = useMemo(() => {
    const map = new Map<string, string>()
    ;(props.options || []).forEach((opt) => {
      const key = String(opt.value || '').trim()
      if (!key) return
      const low = key.toLowerCase()
      if (!map.has(low)) map.set(low, key)
    })
    return map
  }, [props.options])
  const dropdownValue = useMemo(() => {
    const raw = String(props.value ?? '').trim()
    if (!raw) return ''
    if (optionMap.has(raw)) return raw
    const normalized = optionKeyByLower.get(raw.toLowerCase())
    return normalized || raw
  }, [props.value, optionMap, optionKeyByLower])
  const availableMultiOptions = useMemo(() => {
    const selected = new Set(multiDropdownValue)
    const selectedLower = new Set(multiDropdownValue.map((v) => String(v || '').trim().toLowerCase()))
    return (props.options || []).filter((opt) => {
      const key = String(opt.value || '').trim()
      if (!key) return false
      return !selected.has(key) && !selectedLower.has(key.toLowerCase())
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
    const keys = props.elementLabelKeys && props.elementLabelKeys.length ? props.elementLabelKeys : ['HEAD', 'label', 'name', 'feld']
    return keys.map((k) => String(k)).filter(Boolean)
  }, [props.elementLabelKeys])

  const elementMap = useMemo(() => normalizeOccupiedCollectionValue(props.value), [props.value])
  const elementCount = Object.keys(elementMap).length
  const usedElementUids = useMemo(() => {
    return new Set(Object.keys(elementMap).map((uid) => String(uid || '').trim()).filter(Boolean))
  }, [elementMap])
  const availableElementDefinitions = useMemo(() => {
    if (!elementDefinitions.length) return [] as PdvmElementDefinition[]
    if (isElementFrameTypeSingle) return elementDefinitions
    return elementDefinitions.filter((d) => !usedElementUids.has(d.uid))
  }, [elementDefinitions, usedElementUids, isElementFrameTypeSingle])

  useEffect(() => {
    if (!elementDefinitions.length) {
      if (elementAddDefinitionUid) setElementAddDefinitionUid('')
      return
    }
    const hasSelected = availableElementDefinitions.some((d) => d.uid === elementAddDefinitionUid)
    if (hasSelected) return
    const fallback = availableElementDefinitions[0]?.uid || ''
    if (fallback !== elementAddDefinitionUid) setElementAddDefinitionUid(fallback)
  }, [elementDefinitions, availableElementDefinitions, elementAddDefinitionUid])

  useEffect(() => {
    if (!useElementAddLookupSelector) {
      if (elementAddLookupUid) setElementAddLookupUid('')
      return
    }

    const selected = String(elementAddLookupUid || '').trim()
    if (!selected) return
    if (isElementFrameTypeSingle) return
    if (!usedElementUids.has(selected)) return
    setElementAddLookupUid('')
  }, [useElementAddLookupSelector, elementAddLookupUid, isElementFrameTypeSingle, usedElementUids])

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
    const activeDefinitionUid = (() => {
      const currentUid = String(elementModalUid || '').trim()
      if (currentUid && elementFieldsByUid[currentUid]?.length) return currentUid
      if (isElementFrameTypeSingle && elementDefinitions.length > 0) {
        const singleUid = String(elementDefinitions[0].uid || '').trim()
        if (singleUid && elementFieldsByUid[singleUid]?.length) return singleUid
      }
      return ''
    })()

    const activeDefinitionFields = activeDefinitionUid ? elementFieldsByUid[activeDefinitionUid] : null
    const baseElementFields = activeDefinitionFields && activeDefinitionFields.length
      ? activeDefinitionFields
      : elementFields

    if (baseElementFields && baseElementFields.length) {
      const ordered = [...baseElementFields]
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
  }, [elementFields, elementFieldsByUid, elementModalBase, elementModalDraft, elementModalUid, isElementFrameTypeSingle, elementDefinitions])

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

    const byDefinition = elementDefinitions.find((d) => d.uid === uid)
    if (byDefinition?.label) return byDefinition.label

    return uid
  }

  const getElementTooltip = (cfg: any, uid: string) => {
    const guid = String(getValueByKeyCaseInsensitive(cfg, 'GUID') ?? '').trim()
    if (guid) return `GUID: ${guid}`
    return `UID: ${uid}`
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
    if (structuralElementGuardrailError) {
      setElementListGuardrailError(structuralElementGuardrailError)
      return
    }
    setElementListGuardrailError(null)

    if (useElementAddLookupSelector) {
      const selectedUid = String(elementAddLookupUid || '').trim()
      if (!selectedUid) {
        setElementListGuardrailError('Element-Auswahl fehlt: Bitte zuerst ein Element aus der konfigurierten Tabelle auswaehlen.')
        return
      }

      if (!isElementFrameTypeSingle && usedElementUids.has(selectedUid)) {
        setElementListGuardrailError(`Element '${selectedUid}' ist bereits vorhanden.`)
        return
      }

      const selectedDef = elementDefinitions.find((d) => String(d.uid || '').trim() === selectedUid)
      const tplSource = selectedDef?.template || props.elementTemplate || {}
      const tpl = tplSource && typeof tplSource === 'object' ? JSON.parse(JSON.stringify(tplSource)) : {}
      const label = selectedDef?.label || selectedUid
      openElementModal(selectedUid, tpl, `Element hinzufuegen: ${label}`)
      return
    }

    if (isElementFrameTypeSingle) {
      const firstDef = elementDefinitions[0]
      const uid = createGuid()
      const tplSource = firstDef?.template || props.elementTemplate || {}
      const tpl = tplSource && typeof tplSource === 'object' ? JSON.parse(JSON.stringify(tplSource)) : {}
      const title = firstDef?.label ? `Element hinzufügen: ${firstDef.label}` : 'Element hinzufügen'
      openElementModal(uid, tpl, title)
      return
    }

    if (elementDefinitions.length || isElementFrameTypeList) {
      const selectedUid = String(elementAddDefinitionUid || '').trim()
      const selectedDef = availableElementDefinitions.find((d) => d.uid === selectedUid) || availableElementDefinitions[0]
      if (!selectedDef) return

      const uid = selectedDef.uid
      const tplSource = selectedDef.template || props.elementTemplate || {}
      const tpl = tplSource && typeof tplSource === 'object' ? JSON.parse(JSON.stringify(tplSource)) : {}
      openElementModal(uid, tpl, `Element hinzufügen: ${selectedDef.label}`)
      return
    }

    const uid = createGuid()
    const tpl = props.elementTemplate ? JSON.parse(JSON.stringify(props.elementTemplate)) : {}
    openElementModal(uid, tpl, 'Element hinzufügen')
  }

  const editElement = (uid: string, cfg: any) => {
    if (disabled) return
    if (structuralElementGuardrailError) {
      setElementListGuardrailError(structuralElementGuardrailError)
      return
    }
    setElementListGuardrailError(null)
    openElementModal(uid, cfg, 'Element bearbeiten')
  }

  const deleteElement = (uid: string) => {
    if (disabled) return
    if (structuralElementGuardrailError) {
      setElementListGuardrailError(structuralElementGuardrailError)
      return
    }
    setElementListGuardrailError(null)
    const next = { ...elementMap }
    delete next[uid]
    props.onChange(next)
    try {
      const pending = props.onElementListCommit?.(next)
      if (pending && typeof (pending as any).catch === 'function') {
        ;(pending as Promise<void>).catch(() => {
          // Best effort background commit.
        })
      }
    } catch {
      // Best effort background commit.
    }
  }

  const saveElementModal = async () => {
    if (structuralElementGuardrailError) {
      setElementModalError(structuralElementGuardrailError)
      return
    }

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
      let raw = getValueByPathCaseInsensitive(draft, savePath)
      if ((raw == null || String(raw).trim() === '') && /^feld$/i.test(savePath) && targetUid) {
        raw = targetUid
      }
      if (raw == null || String(raw).trim() === '') {
        raw = getValueByPathCaseInsensitive(draftRaw, savePath)
      }
      const text = raw == null ? '' : String(raw).trim()
      if (!text) {
        setElementModalError(`${field.label}: Pflichtfeld`)
        return
      }
    }

    const next = { ...elementMap }
    if (targetUid !== uid && Object.prototype.hasOwnProperty.call(next, targetUid)) {
      setElementModalError(`Element '${targetUid}' ist bereits vorhanden.`)
      return
    }
    if (targetUid !== uid) {
      delete next[uid]
    }
    next[targetUid] = draft
    const sanitizedNext = normalizeOccupiedCollectionValue(next)
    setElementListGuardrailError(null)
    props.onChange(sanitizedNext)
    try {
      await props.onElementListCommit?.(sanitizedNext)
    } catch (err: any) {
      const msg = String(err?.response?.data?.detail || err?.message || 'Element konnte nicht gespeichert werden.')
      setElementModalError(msg)
      return
    }
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
        {String(props.resolutionWarning || '').trim() ? (
          <span
            title={String(props.resolutionWarning || '').trim()}
            aria-label="Control-Warnung"
            style={{ color: '#b42318', fontWeight: 700, marginLeft: 6 }}
          >
            !
          </span>
        ) : null}
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
            {effectiveElementGuardrailError ? (
              <div className="pdvm-dialog__elementEmpty">{effectiveElementGuardrailError}</div>
            ) : (
              <>
                <div className="pdvm-dialog__elementMeta">Einträge: {elementCount}</div>
                {elementEntries.length === 0 ? <div className="pdvm-dialog__elementEmpty">Keine Einträge vorhanden.</div> : null}
                {elementEntries.map(({ uid, cfg }) => (
                  <div key={uid} className="pdvm-dialog__elementItem" title={getElementTooltip(cfg, uid)}>
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
                {(useElementAddLookupSelector || (elementDefinitions.length && !isElementFrameTypeSingle)) ? (
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    {useElementAddLookupSelector ? (
                      <div style={{ width: '100%' }}>
                        <PdvmLookupSelect
                          table={elementAddLookupTable}
                          value={elementAddLookupUid ? String(elementAddLookupUid) : null}
                          onChange={(v) => setElementAddLookupUid(String(v || '').trim())}
                          disabled={disabled}
                        />
                      </div>
                    ) : (
                      <select
                        className="pdvm-pic__select"
                        value={elementAddDefinitionUid}
                        disabled={disabled || availableElementDefinitions.length === 0}
                        onChange={(e) => setElementAddDefinitionUid(String(e.target.value || '').trim())}
                      >
                        <option value="">(Element auswählen)</option>
                        {availableElementDefinitions.map((def) => (
                          <option key={def.uid} value={def.uid}>
                            {def.label}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                ) : null}
                <button
                  type="button"
                  className="pdvm-dialog__toolBtn"
                  onClick={addElement}
                  disabled={
                    disabled ||
                    (useElementAddLookupSelector && !String(elementAddLookupUid || '').trim()) ||
                    (!useElementAddLookupSelector && isElementFrameTypeSingle && elementDefinitions.length === 0) ||
                    (!useElementAddLookupSelector && isElementFrameTypeList && availableElementDefinitions.length === 0) ||
                    (!useElementAddLookupSelector && elementDefinitions.length > 0 && !isElementFrameTypeSingle && availableElementDefinitions.length === 0)
                  }
                >
                  + Element hinzufuegen
                </button>
                <div style={{ marginTop: 8, fontSize: 12, opacity: 0.8 }}>
                  Hinweis: "Uebernehmen" aendert nur die Struktur im aktuellen Dialogsatz. Erst "Speichern" im Dialog persistiert in die Datenbank.
                </div>
              </>
            )}
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
            value={dropdownValue}
            disabled={disabled}
            onBlur={props.onBlur}
            onChange={(e) => props.onChange(e.target.value)}
          >
            <option value="">(bitte auswählen)</option>
            {(props.options || []).map((opt) => (
              <option key={opt.value} value={opt.value} disabled={!!opt.disabled}>
                {opt.label}
              </option>
            ))}
          </select>
        ) : null}

        {effectiveType === 'go_select_view' ? (
          <PdvmLookupSelect
            table={effectiveLookupTable}
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
                  const low = String(value || '').trim().toLowerCase()
                  const resolvedKey = optionKeyByLower.get(low) || String(value || '').trim()
                  const label = optionMap.get(resolvedKey) || value
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
                  <option key={opt.value} value={opt.value} disabled={!!opt.disabled}>
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
        title={`${elementModalTitle} (Uebernehmen = lokal, Speichern im Dialog = persistent)`}
        message={
          <div className="pdvm-pic__elementEditor">
            {elementModalFields.length ? (
              elementModalFields.map((field) => {
                const fieldType = mapElementFieldTypeToInputType(field.type)
                const parentExpert = !!((props.controlDebug as any)?.EXPERT_MODE ?? (props.controlDebug as any)?.expert_mode ?? false)
                const fieldExpertRaw = (field as any).EXPERT_MODE ?? (field as any).expert_mode
                const fieldExpert = fieldExpertRaw === undefined || fieldExpertRaw === null ? undefined : !!fieldExpertRaw
                const nestedControlDebug = (field.control_debug && typeof field.control_debug === 'object'
                  ? field.control_debug
                  : {
                      FIELD_KEY: `ELEMENT.${field.name}`,
                    }) as Record<string, any>
                const nestedExpertRaw = nestedControlDebug.EXPERT_MODE ?? nestedControlDebug.expert_mode
                nestedControlDebug.EXPERT_MODE = nestedExpertRaw === undefined || nestedExpertRaw === null
                  ? (fieldExpert === undefined ? parentExpert : fieldExpert)
                  : !!nestedExpertRaw
                const nestedSavePath = String(field.SAVE_PATH || field.name || '').trim()
                const nestedValue = (() => {
                  if (!nestedSavePath || !elementModalDraft || typeof elementModalDraft !== 'object') return ''
                  return getValueByPathCaseInsensitive(elementModalDraft as Record<string, any>, nestedSavePath)
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
                    resolvedConfigs={asObject((field as any).configs)}
                    goSelectSourceContext={asObject(elementModalDraft)}
                    goSelectSourcePath={String((nestedControlDebug as any).SOURCE_PATH || (nestedControlDebug as any).source_path || 'root').trim() || 'root'}
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
                    resolutionWarning={String((field as any).resolution_warning || (field as any)?.control_debug?.RESOLUTION_WARNING || '').trim() || undefined}
                    controlDebug={nestedControlDebug}
                    onChange={(value) => {
                      setElementModalDraft((prev) => {
                        const base = prev && typeof prev === 'object' ? prev : {}
                        const savePath = String(field.SAVE_PATH || field.name || '').trim()
                        if (!savePath) return base
                        const updated = {
                          ...setValueByPathPreferExistingCase(base, savePath, value),
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
        confirmLabel="Übernehmen"
        cancelLabel="Abbrechen"
        onCancel={() => {
          setElementModalOpen(false)
          setElementModalError(null)
          setElementModalUid(null)
          setElementModalBase(null)
          setElementModalDraft(null)
        }}
        onConfirm={() => {
          void saveElementModal()
        }}
      />
    </div>
  )
}
