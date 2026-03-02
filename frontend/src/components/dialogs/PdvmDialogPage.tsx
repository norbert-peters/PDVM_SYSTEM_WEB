import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  controlDictAPI,
  dialogsAPI,
  systemdatenAPI,
  usersAPI,
  type DialogRow,
  type DialogDefinitionResponse,
  type DialogRecordResponse,
  type DialogDraftResponse,
  type DialogUiStateResponse,
  type DialogValidationIssue,
} from '../../api/client'
import { PdvmViewPageContent } from '../views/PdvmViewPage'
import { PdvmMenuEditor } from './PdvmMenuEditor'
import { PdvmImportDataEditor, PdvmImportDataSteps } from './PdvmImportDataEditor'
import { PdvmJsonEditor, type PdvmJsonEditorHandle, type PdvmJsonEditorMode } from '../common/PdvmJsonEditor'
import { PdvmDialogModal } from '../common/PdvmDialogModal'
import { PdvmInputControl, type PdvmDropdownOption } from '../common/PdvmInputControl'
import { PdvmLookupSelect } from '../common/PdvmLookupSelect'
import '../../styles/components/dialog.css'

type ActiveTab = number

function isUuidString(value: any): boolean {
  const s = String(value || '').trim()
  if (!s) return false
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(s)
}

function safeJsonPretty(value: any): string {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

type PicDef = {
  key?: string
  tab?: number
  name?: string
  label?: string
  tooltip?: string | null
  type?: string
  table?: string
  gruppe?: string
  feld?: string
  display_order?: number
  read_only?: boolean
  historical?: boolean
  abdatum?: boolean
  source_path?: string
  configs?: Record<string, any>
}

function asObject(value: any): Record<string, any> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, any>) : {}
}

function normalizePicType(
  value: any
): 'string' | 'number' | 'text' | 'dropdown' | 'multi_dropdown' | 'true_false' | 'go_select_view' | 'action' | 'element_list' | 'group_list' {
  const t = String(value || '').trim().toLowerCase()
  if (t === 'number' || t === 'int' || t === 'integer') return 'number'
  if (t === 'text') return 'text'
  if (t === 'dropdown') return 'dropdown'
  if (t === 'multi_dropdown') return 'multi_dropdown'
  if (t === 'true_false' || t === 'bool' || t === 'boolean') return 'true_false'
  if (t === 'go_select_view' || t === 'selected_view' || t === 'lookup') return 'go_select_view'
  if (t === 'action') return 'action'
  if (t === 'element_list' || t === 'elemente_list') return 'element_list'
  if (t === 'group_list') return 'group_list'
  return 'string'
}

function buildElementFieldsFromCollectionValue(value: any): Array<{ name: string; label: string; type: 'text' | 'textarea' | 'number' | 'dropdown' }> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return []
  const first = Object.values(value).find((row) => row && typeof row === 'object' && !Array.isArray(row)) as Record<string, any> | undefined
  if (!first) return []
  return Object.keys(first)
    .filter((k) => String(k || '').trim())
    .map((k) => ({ name: k, label: k, type: 'text' as const }))
}

type ControlEditModel = {
  tabs: Array<{ index: number; head: string; group: string }>
  defs: PicDef[]
}

type UnifiedControlSource = 'frame_fields' | 'record_groups'

function extractControlEditModel(daten: Record<string, any> | null | undefined): ControlEditModel {
  const obj = asObject(daten)
  const groupKeys = Object.keys(obj)
    .filter((k) => String(k || '').trim())
    .sort((a, b) => {
      const au = String(a).toUpperCase()
      const bu = String(b).toUpperCase()
      if (au === 'ROOT' && bu !== 'ROOT') return -1
      if (au !== 'ROOT' && bu === 'ROOT') return 1
      return String(a).toLowerCase().localeCompare(String(b).toLowerCase())
    })

  const tabs: Array<{ index: number; head: string; group: string }> = []
  const defs: PicDef[] = []

  let tabIndex = 1
  for (const groupKey of groupKeys) {
    const groupName = String(groupKey || '').trim()
    if (!groupName) continue

    const groupValue = obj[groupKey]
    if (!groupValue || typeof groupValue !== 'object' || Array.isArray(groupValue)) {
      continue
    }

    tabs.push({ index: tabIndex, head: groupName, group: groupName })

    const groupObj = asObject(groupValue)
    let order = 10
    for (const [fieldKey, raw] of Object.entries(groupObj)) {
      const fieldName = String(fieldKey || '').trim()
      if (!fieldName) continue

      const base: PicDef = {
        key: `CTRL.${groupName}.${fieldName}`,
        tab: tabIndex,
        name: fieldName,
        label: fieldName,
        gruppe: groupName,
        feld: fieldName,
        display_order: order,
        read_only: false,
        tooltip: undefined,
        configs: {},
      }
      order += 10

      if (typeof raw === 'boolean') {
        base.type = 'true_false'
        defs.push(base)
        continue
      }

      if (typeof raw === 'number') {
        base.type = 'number'
        defs.push(base)
        continue
      }

      if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
        const nestedType = String((raw as any).TYPE ?? (raw as any).type ?? '').trim().toLowerCase()
        if (nestedType === 'element_list' || nestedType === 'group_list') {
          base.type = nestedType as any
          base.configs = {
            ...(base.configs || {}),
            element_template: {},
            element_fields: buildElementFieldsFromCollectionValue(raw),
          }
          defs.push(base)
          continue
        }

        base.type = 'action'
        base.read_only = true
        base.tooltip = 'Objekt ohne TYPE=element_list/group_list. Bitte in der Definition ergänzen.'
        defs.push(base)
        continue
      }

      if (Array.isArray(raw)) {
        base.type = 'action'
        base.read_only = true
        base.tooltip = 'Liste ohne TYPE=element_list/group_list. Bitte in der Definition ergänzen.'
        defs.push(base)
        continue
      }

      base.type = 'string'
      defs.push(base)
    }

    tabIndex += 1
  }

  return { tabs, defs }
}

function buildUnifiedControlMatrix(
  source: UnifiedControlSource,
  opts: {
    frameDaten?: Record<string, any> | null
    currentDaten?: Record<string, any> | null
  }
): ControlEditModel {
  if (source === 'frame_fields') {
    const defs = extractPicDefs(opts.frameDaten || null)
    const tabsMap = new Map<number, { index: number; head: string; group: string }>()

    defs.forEach((d) => {
      const tabIndex = Number(d.tab || 1) || 1
      if (tabsMap.has(tabIndex)) return

      const group = String(d.gruppe || '').trim()
      const head = group || `Tab ${tabIndex}`
      tabsMap.set(tabIndex, { index: tabIndex, head, group: group || `TAB_${String(tabIndex).padStart(2, '0')}` })
    })

    const tabs = Array.from(tabsMap.values()).sort((a, b) => a.index - b.index)
    if (!tabs.length && defs.length) {
      tabs.push({ index: 1, head: 'Tab 1', group: 'TAB_01' })
    }

    return { tabs, defs }
  }

  return extractControlEditModel(opts.currentDaten || null)
}

function extractPicDefs(frameDaten: Record<string, any> | null | undefined): PicDef[] {
  const fd = asObject(frameDaten)
  const fields = asObject(fd.FIELDS)
  const out: PicDef[] = []
  for (const [key, value] of Object.entries(fields)) {
    const item = asObject(value)
    out.push({ key, ...(item as PicDef) })
  }
  out.sort((a, b) => {
    const ao = Number(a.display_order ?? 0)
    const bo = Number(b.display_order ?? 0)
    if (ao !== bo) return ao - bo
    const al = String(a.label || a.name || '').toLowerCase()
    const bl = String(b.label || b.name || '').toLowerCase()
    return al.localeCompare(bl)
  })
  return out
}

function getFieldValue(daten: Record<string, any>, gruppe: string, feld: string) {
  const isTopLevel = gruppe === '__ROOT__' || gruppe === '__TOP__'
  const baseObj = isTopLevel ? asObject(daten) : asObject(daten[gruppe])
  if (!feld.includes('.')) return baseObj[feld]
  return feld.split('.').reduce((acc: any, part: string) => {
    if (!acc || typeof acc !== 'object') return undefined
    return acc[part]
  }, baseObj as any)
}

function setFieldValue(daten: Record<string, any>, gruppe: string, feld: string, value: any) {
  const out = { ...daten }
  const isTopLevel = gruppe === '__ROOT__' || gruppe === '__TOP__'
  const groupObj = isTopLevel ? asObject(out) : asObject(out[gruppe])
  if (!feld.includes('.')) {
    const next = { ...groupObj, [feld]: value }
    if (isTopLevel) {
      return next
    }
    out[gruppe] = next
    return out
  }
  const parts = feld.split('.').filter(Boolean)
  let cursor: any = { ...groupObj }
  const root = cursor
  parts.forEach((part, idx) => {
    if (idx === parts.length - 1) {
      cursor[part] = value
      return
    }
    const next = cursor[part]
    cursor[part] = asObject(next)
    cursor = cursor[part]
  })
  if (isTopLevel) {
    return root
  }
  out[gruppe] = root
  return out
}

function buildValidationErrorMap(issues: DialogValidationIssue[] | null | undefined): Record<string, string> {
  const out: Record<string, string> = {}
  if (!Array.isArray(issues)) return out
  issues.forEach((issue) => {
    const group = String(issue?.group || '').trim()
    const field = String(issue?.field || '').trim()
    const message = String(issue?.message || '').trim()
    if (!group || !field || !message) return
    const key = `${group}.${field}`
    if (!out[key]) out[key] = message
  })
  return out
}

function readControlType(controlData: Record<string, any> | null | undefined): string {
  const obj = asObject(controlData)
  return String(obj.type ?? obj.TYPE ?? '').trim()
}

function defaultValueForControlType(controlTypeRaw: string): any {
  const t = String(controlTypeRaw || '').trim().toLowerCase()
  if (t === 'number' || t === 'int' || t === 'integer' || t === 'float') return ''
  if (t === 'true_false' || t === 'bool' || t === 'boolean') return false
  if (t === 'multi_dropdown') return []
  if (t === 'element_list' || t === 'elemente_list' || t === 'group_list') return {}
  return ''
}

export default function PdvmDialogPage() {
  const { dialogGuid } = useParams<{ dialogGuid: string }>()
  const [searchParams] = useSearchParams()
  const dialogTable = (searchParams.get('dialog_table') || searchParams.get('table') || '').trim() || null
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState<ActiveTab>(1)
  const [pageOffset, setPageOffset] = useState(0)
  const pageLimit = 200

  const [selectedUid, setSelectedUid] = useState<string | null>(null)
  const [selectedUids, setSelectedUids] = useState<string[]>([])
  const ignoredAutoLastCallUidRef = useRef<string>('')
  const [autoLastCallError, setAutoLastCallError] = useState<string | null>(null)
  const suppressPersistRef = useRef<boolean>(true)

  const dialogNewDefaults = {
    dialog_name: '',
    root_table: '',
    view_guid: '',
    frame_guid: '',
    dialog_type: 'norm',
  }

  // Avoid writing last_call for a new dialog_table using an old selection.
  const lastPersistContextKeyRef = useRef<string>('')

  const defQuery = useQuery<DialogDefinitionResponse>({
    queryKey: ['dialog', 'definition', dialogGuid, dialogTable],
    queryFn: () => dialogsAPI.getDefinition(dialogGuid!, { dialog_table: dialogTable }),
    enabled: !!dialogGuid,
  })

  const moduleTabs = useMemo(() => {
    const tabs = defQuery.data?.tab_modules
    return Array.isArray(tabs) ? tabs : []
  }, [defQuery.data?.tab_modules])

  const viewTabIndex = useMemo(() => {
    const t = moduleTabs.find((m) => String(m?.module || '').trim().toLowerCase() === 'view')
    return Number(t?.index || 1) || 1
  }, [moduleTabs])

  const editTabIndex = useMemo(() => {
    const t = moduleTabs.find((m) => String(m?.module || '').trim().toLowerCase() === 'edit')
    return Number(t?.index || 2) || 2
  }, [moduleTabs])

  const activeModule = useMemo(() => {
    return moduleTabs.find((m) => Number(m?.index || 0) === activeTab) || null
  }, [moduleTabs, activeTab])

  const tab1Module = useMemo(() => moduleTabs.find((t) => Number(t?.index || 0) === 1) || null, [moduleTabs])
  const tab2Module = useMemo(() => moduleTabs.find((t) => Number(t?.index || 0) === 2) || null, [moduleTabs])

  const effectiveViewGuid = useMemo(() => {
    const module = String(tab1Module?.module || '').trim().toLowerCase()
    const guid = String(tab1Module?.guid || '').trim()
    if (module === 'view' && guid) return guid
    const fallback = String(defQuery.data?.view_guid || '').trim()
    return fallback || ''
  }, [tab1Module, defQuery.data?.view_guid])

  const effectiveEditType = useMemo(() => {
    const module = String(activeModule?.module || '').trim().toLowerCase()
    const et = String(activeModule?.edit_type || '').trim().toLowerCase()
    if (module === 'edit' && et) return et
    return String(defQuery.data?.edit_type || 'show_json').trim().toLowerCase()
  }, [activeModule, defQuery.data?.edit_type])

  const dialogType = String(defQuery.data?.dialog_type || '').trim().toLowerCase() || 'norm'
  const isWorkflowDialog = dialogType === 'work' || dialogType === 'acti'

  const lastCallScopeKey = useMemo(() => {
    const vg = String(effectiveViewGuid || '').trim()
    const rt = String(defQuery.data?.root_table || defQuery.data?.root?.TABLE || '').trim()
      return vg && rt ? `${vg}::${rt}` : ''
  }, [effectiveViewGuid, defQuery.data?.root_table, defQuery.data?.root])

  const persistContextKey = lastCallScopeKey

  const effectiveDialogTable = useMemo(() => {
    const override = String(dialogTable || '').trim()
    if (override) return override
    const rt = String(defQuery.data?.root_table || defQuery.data?.root?.TABLE || '').trim()
    return rt || null
  }, [dialogTable, defQuery.data?.root_table, defQuery.data?.root])

  // IMPORTANT: When switching to another dialog (route param), this component usually stays mounted.
  // Reset local state so we don't carry over selection/edit-tab from the previous dialog.
  useEffect(() => {
    setActiveTab(1)
    setPageOffset(0)
    setSelectedUid(null)
    setSelectedUids([])
      ignoredAutoLastCallUidRef.current = ''
    setAutoLastCallError(null)
    setJsonError(null)
    setJsonDirty(false)
    setJsonMode('text')
    setJsonSearch('')
    setJsonSearchHits(null)
    setPicActiveTab(1)
    setPicDraft(null)
    setPicDirty(false)
    setActiveDraft(null)
    setDraftValidationIssues([])
    setMenuEditorRefreshToken(0)
    setRefreshModalOpen(false)
    setDialogNewDraft(dialogNewDefaults)
    setDialogNewError(null)
    setDialogNewSuccess(null)
    setDialogNewBusy(false)

    // Mark context switch so the persistence effect can skip one cycle.
    // Important: keep it DIFFERENT from persistContextKey to avoid writing stale selection.
    lastPersistContextKeyRef.current = ''
    suppressPersistRef.current = true
  }, [dialogGuid, dialogTable])

  useEffect(() => {
    // Reset persistence scope on view/table change.
    lastPersistContextKeyRef.current = ''
    suppressPersistRef.current = true
  }, [lastCallScopeKey])

  const openEditMode = String(defQuery.data?.open_edit_mode || 'tab').trim().toLowerCase()
  const editType = effectiveEditType
  const wantsMenuEditor = editType === 'menu'
  const hasEmbeddedView = !!String(effectiveViewGuid || '').trim()
  const isSysMenuTable = String(defQuery.data?.root_table || '').trim().toLowerCase() === 'sys_menudaten'
  const isImportEditor = editType === 'import_data'

  // If the dialog embeds a View (by view_guid), keep selection in sync by listening
  // to the global selection event emitted by PdvmViewPage.
  useEffect(() => {
    const viewGuid = String(effectiveViewGuid || '').trim()
    if (!viewGuid) return

    const handler = (ev: Event) => {
      const detail = (ev as any)?.detail || null
      if (!detail || String(detail.view_guid || '').trim() !== viewGuid) return
      const selected = Array.isArray(detail.selected_uids) ? detail.selected_uids : []
      const next = selected.map((x: any) => String(x))
      setSelectedUids(next)
      if (next.length === 1) setSelectedUid(next[0])

      // Selection belongs to the current view/dialog; allow persisting.
      if (lastCallScopeKey) {
        suppressPersistRef.current = false
      }

      // OPEN_EDIT=auto: jump to edit as soon as a single row is selected.
      if (openEditMode === 'auto' && next.length === 1) {
        setActiveTab(editTabIndex)
      }
    }

    window.addEventListener('pdvm:view-selection-changed', handler as any)
    return () => window.removeEventListener('pdvm:view-selection-changed', handler as any)
  }, [effectiveViewGuid, openEditMode])

  // OPEN_EDIT=double_click: listen to the View activation event.
  useEffect(() => {
    const viewGuid = String(effectiveViewGuid || '').trim()
    if (!viewGuid) return
    if (openEditMode !== 'double_click') return

    const handler = (ev: Event) => {
      const detail = (ev as any)?.detail || null
      if (!detail || String(detail.view_guid || '').trim() !== viewGuid) return
      const uid = String(detail.uid || '').trim()
      if (!uid) return

      setSelectedUid(uid)
      setSelectedUids([uid])
      setActiveTab(editTabIndex)
    }

    window.addEventListener('pdvm:view-row-activated', handler as any)
    return () => window.removeEventListener('pdvm:view-row-activated', handler as any)
  }, [effectiveViewGuid, openEditMode, editTabIndex])

  const systemdatenUid = useMemo(() => {
    const root = (defQuery.data?.root || {}) as Record<string, any>
    const keys = Object.keys(root)
    const k = keys.find((x) => String(x).trim().toLowerCase() === 'systemdaten_uid')
    const v = k ? root[k] : null
    const s = v != null ? String(v).trim() : ''
    return s || null
  }, [defQuery.data?.root])

  const isMenuEditor = wantsMenuEditor
  const isPicEditor = editType === 'edit_user'
  const isPdvmEdit = editType === 'pdvm_edit'
  const isFrameEditor = editType === 'edit_frame'
  const isControlEditor = editType === 'edit_control'
  const usesUnifiedControlMatrix = isPdvmEdit || isControlEditor
  const isFieldEditor = isPicEditor || isFrameEditor || isPdvmEdit || isControlEditor
  const [importStep, setImportStep] = useState(1)

  useEffect(() => {
    if (!isImportEditor) return
    setImportStep(1)
  }, [isImportEditor, selectedUid, effectiveDialogTable])
  const frameDaten = (defQuery.data?.frame?.daten || null) as Record<string, any> | null
  const frameRoot = (defQuery.data?.frame?.root || {}) as Record<string, any>

  const picDefs = useMemo(() => extractPicDefs(frameDaten), [frameDaten])

  const picTabs = useMemo(() => {

    const extractTabsFromElements = (value: any): Array<{ index: number; head: string }> => {
      const out: Array<{ index: number; head: string }> = []

      const pushRow = (row: any, fallbackIndex?: number) => {
        if (!row || typeof row !== 'object') return
        const idxRaw = (row as any).index ?? (row as any).tab ?? (row as any).TAB ?? fallbackIndex
        const idx = Number(idxRaw || 0)
        if (!idx || idx < 1 || idx > 20) return
        const head = String((row as any).HEAD ?? (row as any).head ?? '').trim() || `Tab ${idx}`
        out.push({ index: idx, head })
      }

      if (value && typeof value === 'object' && !Array.isArray(value)) {
        Object.entries(value).forEach(([key, row]) => {
          let fallbackIndex: number | undefined
          const m = /^tab[_-]?0*(\d+)$/i.exec(String(key || '').trim())
          if (m) fallbackIndex = Number(m[1])
          pushRow(row, fallbackIndex)
        })
      } else if (Array.isArray(value)) {
        value.forEach((row, i) => pushRow(row, i + 1))
      }

      const unique = new Map<number, { index: number; head: string }>()
      out
        .sort((a, b) => a.index - b.index)
        .forEach((item) => {
          if (!unique.has(item.index)) unique.set(item.index, item)
        })
      return Array.from(unique.values())
    }

    const rootTabElements = (frameRoot as any).TAB_ELEMENTS ?? (frameRoot as any).tab_elements
    let items = extractTabsFromElements(rootTabElements)

    if (!items.length) {
    const tabsDefRaw = (frameRoot as any).TABS_DEF ?? (frameRoot as any).tabs_def
    const tabsDef = tabsDefRaw && typeof tabsDefRaw === 'object' && !Array.isArray(tabsDefRaw) ? tabsDefRaw : null
    const tabsRaw = frameRoot.TABS ?? frameRoot.tabs
    const tabs = Number(tabsRaw || 0)

    const pickTabBlock = (tabIndex: number): Record<string, any> | null => {
      const rx = new RegExp(`^tab[_-]?0*${tabIndex}$`, 'i')
      for (const key of Object.keys(frameRoot)) {
        if (!rx.test(key)) continue
        const v = (frameRoot as any)[key]
        return v && typeof v === 'object' ? v : null
      }
      return null
    }

      if (tabsDef) {
      for (const value of Object.values(tabsDef)) {
        if (!value || typeof value !== 'object') continue
        const idxRaw = (value as any).index ?? (value as any).tab ?? (value as any).TAB ?? (value as any).tab_index
        const idx = Number(idxRaw || 0)
        if (!idx || idx < 0 || idx > 20) continue
        const head = String((value as any).HEAD ?? (value as any).head ?? '').trim() || `Tab ${idx}`
        items.push({ index: idx, head })
      }
      items.sort((a, b) => a.index - b.index)
      } else {
      const maxTabs = Math.min(20, Math.max(0, tabs || 0))
      for (let i = 1; i <= maxTabs; i++) {
        const block = pickTabBlock(i)
        const head = String((block as any)?.HEAD ?? (block as any)?.head ?? '').trim() || `Tab ${i}`
        items.push({ index: i, head })
      }
      }
    }

    if (isPicEditor) {
      items = items.filter((t) => t.index !== 5)
    }

    return { tabs: items.length, items }
  }, [frameRoot, isPicEditor])

  const [picActiveTab, setPicActiveTab] = useState(1)
  const [picDraft, setPicDraft] = useState<Record<string, any> | null>(null)
  const [picDirty, setPicDirty] = useState(false)
  const [activeDraft, setActiveDraft] = useState<DialogDraftResponse | null>(null)
  const [draftValidationIssues, setDraftValidationIssues] = useState<DialogValidationIssue[]>([])

  const rowsQuery = useQuery<{ dialog_guid: string; table: string; rows: DialogRow[] }>({
    queryKey: ['dialog', 'rows', dialogGuid, dialogTable, pageLimit, pageOffset],
    queryFn: () => dialogsAPI.postRows(dialogGuid!, { limit: pageLimit, offset: pageOffset }, { dialog_table: dialogTable }),
    enabled: !!dialogGuid && defQuery.isSuccess && !effectiveViewGuid,
  })

  const recordQuery = useQuery<DialogRecordResponse>({
    queryKey: ['dialog', 'record', dialogGuid, dialogTable, selectedUid],
    queryFn: () => dialogsAPI.getRecord(dialogGuid!, selectedUid!, { dialog_table: dialogTable }),
    enabled: !!dialogGuid && !!selectedUid && !isMenuEditor && !activeDraft,
  })

  const isDraftMode = !!activeDraft
  const currentDaten = activeDraft?.daten || recordQuery.data?.daten || null
  const currentName = activeDraft?.name || recordQuery.data?.name || ''
  const unifiedControlMatrix = useMemo(() => {
    if (!usesUnifiedControlMatrix) return null
    const source: UnifiedControlSource = isPdvmEdit ? 'frame_fields' : 'record_groups'
    return buildUnifiedControlMatrix(source, {
      frameDaten,
      currentDaten: (picDraft ? picDraft : currentDaten) as Record<string, any> | null,
    })
  }, [usesUnifiedControlMatrix, isPdvmEdit, frameDaten, picDraft, currentDaten])

  const controlEditModel = useMemo(() => {
    if (!isControlEditor) return null
    return unifiedControlMatrix
  }, [isControlEditor, unifiedControlMatrix])
  const effectivePicDefs = useMemo(() => {
    if (usesUnifiedControlMatrix) {
      return unifiedControlMatrix?.defs || []
    }
    return picDefs
  }, [usesUnifiedControlMatrix, unifiedControlMatrix, picDefs])

  const controlResolveListQuery = useQuery({
    queryKey: ['control-dict', 'list', 'resolve', effectiveDialogTable],
    queryFn: () => controlDictAPI.listControls({ limit: 2000, skip: 0 }),
    enabled: isControlEditor,
  })

  const matchedControlRefs = useMemo(() => {
    if (!isControlEditor) return [] as Array<{ uid: string; gruppe: string; feld: string }>

    const rows = controlResolveListQuery.data?.items || []
    const tableNorm = String(effectiveDialogTable || '').trim().toLowerCase()
    const groupFieldMap = new Map<string, string>()
    const fieldCandidatesMap = new Map<string, Array<{ uid: string; gruppe: string }>>()

    rows.forEach((row) => {
      const uid = String(row.uid || '').trim()
      const gruppe = String(row.gruppe || '').trim().toUpperCase()
      const field = String(row.field || '').trim().toUpperCase()
      const table = String(row.table || '').trim().toLowerCase()
      if (!uid || !field) return
      if (tableNorm && table && table !== tableNorm) return

      if (gruppe) {
        const key = `${gruppe}::${field}`
        if (!groupFieldMap.has(key)) groupFieldMap.set(key, uid)
      }

      const existing = fieldCandidatesMap.get(field) || []
      existing.push({ uid, gruppe })
      fieldCandidatesMap.set(field, existing)
    })

    return effectivePicDefs
      .map((d) => {
        const gruppe = String(d.gruppe || '').trim().toUpperCase()
        const feld = String(d.feld || '').trim()
        if (!feld) return null

        const directUid = isUuidString(feld) ? feld : ''
        const fieldUpper = feld.toUpperCase()
        const key = `${gruppe}::${fieldUpper}`

        let mappedUid = groupFieldMap.get(key) || ''

        if (!mappedUid) {
          const candidates = fieldCandidatesMap.get(fieldUpper) || []
          if (candidates.length === 1) {
            mappedUid = candidates[0].uid
          } else if (candidates.length > 1) {
            const sameGroup = candidates.find((c) => c.gruppe === gruppe)
            if (sameGroup?.uid) {
              mappedUid = sameGroup.uid
            } else {
              const emptyGroup = candidates.find((c) => !c.gruppe)
              if (emptyGroup?.uid) mappedUid = emptyGroup.uid
            }
          }
        }

        const uid = directUid || mappedUid
        if (!uid) return null

        return { uid, gruppe, feld: String(d.feld || '').trim() }
      })
      .filter(Boolean) as Array<{ uid: string; gruppe: string; feld: string }>
  }, [isControlEditor, controlResolveListQuery.data, effectivePicDefs, effectiveDialogTable])

  const resolvedControlQueries = useQueries({
    queries: matchedControlRefs.map((entry) => ({
      queryKey: ['control-dict', 'resolved', entry.uid],
      queryFn: () => controlDictAPI.getControl(entry.uid),
      enabled: isControlEditor,
    })),
  })

  const resolvedControlByGroupField = useMemo(() => {
    const out: Record<string, { uid: string; data: Record<string, any> }> = {}
    matchedControlRefs.forEach((entry, idx) => {
      const data = asObject(resolvedControlQueries[idx]?.data?.daten)
      if (!Object.keys(data).length) return
      const key = `${entry.gruppe.toUpperCase()}::${entry.feld.toUpperCase()}`
      out[key] = { uid: entry.uid, data }
    })
    return out
  }, [matchedControlRefs, resolvedControlQueries])

  const effectivePicDefsResolved = useMemo(() => {
    if (!isControlEditor) return effectivePicDefs

    return effectivePicDefs.map((d) => {
      const gruppe = String(d.gruppe || '').trim().toUpperCase()
      const feld = String(d.feld || '').trim().toUpperCase()
      const key = `${gruppe}::${feld}`
      const resolved = resolvedControlByGroupField[key]
      const controlData = asObject(resolved?.data)
      const controlRoot = asObject(controlData.ROOT)
      const controlPayload = asObject(controlData.CONTROL)

      // Wenn kein aufgelöstes Original-Control vorliegt: keine künstliche Struktur aufbauen.
      if (!Object.keys(controlPayload).length) return d

      const name = String(controlPayload.NAME ?? d.name ?? d.feld ?? '').trim()
      const label = String(controlPayload.LABEL ?? name ?? '').trim()
      const typeRaw = String(controlPayload.TYPE ?? d.type ?? '').trim()
      const tooltip = String(controlPayload.TOOLTIP ?? d.tooltip ?? '').trim()
      const readOnly = controlPayload.READ_ONLY
      const configs = asObject(d.configs)
      configs.control_original = controlData
      configs.control_root = controlRoot
      configs.control_payload = controlPayload

      return {
        ...d,
        name: name || d.name,
        label: label || d.label,
        type: typeRaw || d.type,
        tooltip: tooltip || d.tooltip,
        read_only: readOnly ?? d.read_only,
        configs,
      }
    })
  }, [isControlEditor, effectivePicDefs, resolvedControlByGroupField])

  const uiPicDefs = useMemo(() => {
    return isControlEditor ? effectivePicDefsResolved : effectivePicDefs
  }, [isControlEditor, effectivePicDefsResolved, effectivePicDefs])
  const effectivePicTabs = useMemo(() => {
    if (usesUnifiedControlMatrix) {
      const items = (unifiedControlMatrix?.tabs || []).map((t) => ({ index: t.index, head: t.head }))
      return { tabs: items.length, items }
    }
    return picTabs
  }, [usesUnifiedControlMatrix, unifiedControlMatrix, picTabs])
  useEffect(() => {
    if (!effectivePicTabs.items.length) return
    const allowed = new Set(effectivePicTabs.items.map((t) => t.index))
    if (!allowed.has(picActiveTab)) {
      setPicActiveTab(effectivePicTabs.items[0].index)
    }
  }, [effectivePicTabs.items, picActiveTab])
  const draftErrorByField = useMemo(() => buildValidationErrorMap(draftValidationIssues), [draftValidationIssues])

  const activeControlGroup = useMemo(() => {
    if (!isControlEditor) return null
    const tab = controlEditModel?.tabs?.find((t) => Number(t.index || 0) === Number(picActiveTab || 0))
    const group = String(tab?.group || tab?.head || '').trim()
    return group || null
  }, [isControlEditor, controlEditModel, picActiveTab])

  const editInfoParts = useMemo(() => {
    const items: Array<{ label: string; value: string }> = []
    if (effectiveDialogTable) items.push({ label: 'TABLE', value: effectiveDialogTable })
    if (defQuery.data?.edit_type) items.push({ label: 'EDIT_TYPE', value: String(defQuery.data.edit_type) })
    if (selectedUid) items.push({ label: 'UID', value: selectedUid })
    if (currentName) items.push({ label: 'NAME', value: String(currentName) })
    return items
  }, [effectiveDialogTable, defQuery.data?.edit_type, selectedUid, currentName])

  const renderEditInfo = () => {
    if (editInfoParts.length === 0) return null
    return (
      <div className="pdvm-dialog__editInfo">
        {editInfoParts.map((item, idx) => (
          <span key={item.label}>
            {item.label}: <span style={{ fontFamily: 'monospace' }}>{item.value}</span>
            {idx < editInfoParts.length - 1 ? ' | ' : ''}
          </span>
        ))}
      </div>
    )
  }



  // Auto-select last_call (if present) and open edit immediately.
  useEffect(() => {
    if (!dialogGuid) return
    if (!defQuery.isSuccess) return
    const lastCall = (defQuery.data?.meta as any)?.last_call
    const lastCallUid = lastCall != null ? String(lastCall).trim() : ''
    if (!lastCallUid) return

    // Only apply auto-last-call when there's no selection yet.
    if (selectedUid) return

    // Avoid repeating the same missing last_call in a loop.
    if (ignoredAutoLastCallUidRef.current && ignoredAutoLastCallUidRef.current === lastCallUid) return

    setAutoLastCallError(null)
    setSelectedUid(lastCallUid)
    setSelectedUids([lastCallUid])
      setActiveTab(editTabIndex)
    if (lastCallScopeKey) {
      suppressPersistRef.current = false
    }
  }, [dialogGuid, defQuery.isSuccess, defQuery.data?.meta, selectedUid])

  // If auto-last_call load fails (e.g. record deleted), fall back to view.
  useEffect(() => {
    if (!recordQuery.isError) return
    const status = (recordQuery.error as any)?.response?.status
    if (status !== 404) return

    const lastCall = (defQuery.data?.meta as any)?.last_call
    const lastCallUid = lastCall != null ? String(lastCall).trim() : ''
    if (lastCallUid) {
      ignoredAutoLastCallUidRef.current = lastCallUid
    }

    setAutoLastCallError('Letzter Datensatz (last_call) wurde nicht gefunden. Bitte neu auswählen.')
    setSelectedUid(null)
    setSelectedUids([])
      setActiveTab(viewTabIndex)

    // Self-heal: clear persisted last_call so next open starts clean.
    dialogsAPI.putLastCall(dialogGuid!, null, { dialog_table: dialogTable }).catch(() => {
      // Best-effort
    })
  }, [recordQuery.isError, recordQuery.error, defQuery.data?.meta, dialogGuid, dialogTable])

  // Mark selection as belonging to the current dialog context.
  useEffect(() => {
    if (!selectedUid) return
    if (!isUuidString(selectedUid)) return
    if (!persistContextKey) return
    lastPersistContextKeyRef.current = persistContextKey
  }, [selectedUid, persistContextKey])

  // Persist last selection immediately (best-effort), even before loading the record.
  useEffect(() => {
    if (!dialogGuid) return
    if (!selectedUid) return
    if (!isUuidString(selectedUid)) return
    if (!persistContextKey) return
    if (suppressPersistRef.current) return

    // If the dialog context just changed (e.g. new dialog_table), don't persist the previous selection.
    if (lastPersistContextKeyRef.current !== persistContextKey) {
      lastPersistContextKeyRef.current = persistContextKey
      return
    }

    dialogsAPI.putLastCall(dialogGuid, selectedUid, { dialog_table: dialogTable }).catch(() => {
      // Best-effort persistence only.
    })
  }, [dialogGuid, selectedUid, dialogTable, persistContextKey])

  const jsonEditorRef = useRef<PdvmJsonEditorHandle | null>(null)
  const [jsonError, setJsonError] = useState<string | null>(null)
  const [jsonDirty, setJsonDirty] = useState(false)
  const [jsonMode, setJsonMode] = useState<PdvmJsonEditorMode>('text')
  const [jsonSearch, setJsonSearch] = useState('')
  const [jsonSearchHits, setJsonSearchHits] = useState<number | null>(null)
  const jsonSearchInputRef = useRef<HTMLInputElement | null>(null)

  const [menuEditorRefreshToken, setMenuEditorRefreshToken] = useState(0)

  const [addControlFieldOpen, setAddControlFieldOpen] = useState(false)
  const [addControlFieldError, setAddControlFieldError] = useState<string | null>(null)
  const [addControlFieldBusy, setAddControlFieldBusy] = useState(false)

  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [createModalError, setCreateModalError] = useState<string | null>(null)

  const [discardModalOpen, setDiscardModalOpen] = useState(false)
  const [pendingTab, setPendingTab] = useState<ActiveTab | null>(null)

  const [refreshModalOpen, setRefreshModalOpen] = useState(false)

  const [infoModalOpen, setInfoModalOpen] = useState(false)

  const [userActionInfo, setUserActionInfo] = useState<string | null>(null)
  const [userActionError, setUserActionError] = useState<string | null>(null)
  const [userActionBusy, setUserActionBusy] = useState(false)
  const [resetPwConfirmOpen, setResetPwConfirmOpen] = useState(false)
  const [lockAccountOpen, setLockAccountOpen] = useState(false)
  const [unlockAccountOpen, setUnlockAccountOpen] = useState(false)

  useEffect(() => {
    if (!autoLastCallError) return
    setInfoModalOpen(true)
  }, [autoLastCallError])

  useEffect(() => {
    if (!userActionInfo && !userActionError) return
    setInfoModalOpen(true)
  }, [userActionInfo, userActionError])

  useEffect(() => {
    if (!currentDaten) return
    if (editType !== 'edit_json') return

    try {
      jsonEditorRef.current?.setJson(currentDaten)
      jsonEditorRef.current?.setMode(jsonMode)
      setJsonError(null)
      setJsonDirty(false)
      setJsonSearchHits(null)
    } catch (e: any) {
      setJsonError(e?.message || 'Editor konnte JSON nicht laden')
    }
  }, [currentDaten, editType, jsonMode])

  useEffect(() => {
    if (!currentDaten) return
    if (!isFieldEditor) return
    setPicDraft(currentDaten || {})
    setPicDirty(false)
  }, [currentDaten, isFieldEditor])

  const controlFieldLookupQuery = useQuery({
    queryKey: ['control-dict', 'list', 'for-add-field'],
    queryFn: () => controlDictAPI.listControls({ limit: 1000, skip: 0 }),
    enabled: isControlEditor && addControlFieldOpen,
  })

  const availableControlFieldOptions = useMemo(() => {
    const rows = controlFieldLookupQuery.data?.items || []
    const group = String(activeControlGroup || '').trim()
    if (!group) return [] as Array<{ value: string; label: string }>

    const current = (picDraft ? picDraft : currentDaten || {}) as Record<string, any>
    const groupObj = asObject(current[group])
    const existing = new Set(Object.keys(groupObj).map((k) => String(k).trim()).filter(Boolean))

    return rows
      .map((r) => {
        const uid = String(r.uid || '').trim()
        const name = String(r.name || '').trim()
        const label = String(r.label || '').trim()
        const viewLabel = [name, label].filter(Boolean).join(' | ') || uid
        return { value: uid, label: `${viewLabel} | ${uid}` }
      })
      .filter((x) => x.value)
      .filter((x) => !existing.has(x.value))
  }, [controlFieldLookupQuery.data, activeControlGroup, picDraft, currentDaten])

  useEffect(() => {
    if (!isFieldEditor) return
    setPicActiveTab(1)
  }, [selectedUid, isFieldEditor])

  const updateMutation = useMutation({
    mutationFn: async (nextJson: Record<string, any>) => {
      if (activeDraft?.draft_id) {
        const res = await dialogsAPI.updateDraft(
          dialogGuid!,
          activeDraft.draft_id,
          { daten: nextJson },
          { dialog_table: dialogTable }
        )
        setActiveDraft(res)
        setDraftValidationIssues(res.validation_errors || [])
        return {
          uid: activeDraft.draft_id,
          name: res.name,
          daten: res.daten,
          historisch: 0,
          modified_at: null,
        } as DialogRecordResponse
      }
      return dialogsAPI.updateRecord(dialogGuid!, selectedUid!, { daten: nextJson }, { dialog_table: dialogTable })
    },
    onSuccess: async () => {
      if (activeDraft?.draft_id) return
      await queryClient.invalidateQueries({ queryKey: ['dialog', 'record', dialogGuid, dialogTable, selectedUid] })
    },
  })

  const commitDraftMutation = useMutation({
    mutationFn: async (nextJson: Record<string, any>) => {
      if (!activeDraft?.draft_id) {
        throw new Error('Kein aktiver Draft')
      }
      return dialogsAPI.commitDraft(
        dialogGuid!,
        activeDraft.draft_id,
        { daten: nextJson },
        { dialog_table: dialogTable }
      )
    },
    onSuccess: async (created) => {
      setActiveDraft(null)
      setDraftValidationIssues([])
      setSelectedUid(created.uid)
      setSelectedUids([created.uid])
      setPicDirty(false)
      setJsonDirty(false)
      await queryClient.invalidateQueries({ queryKey: ['dialog', 'rows', dialogGuid, dialogTable] })
      const embeddedViewGuid = String(effectiveViewGuid || '').trim()
      if (embeddedViewGuid) {
        await queryClient.invalidateQueries({ queryKey: ['view', 'matrix', embeddedViewGuid] })
      }
      await queryClient.invalidateQueries({ queryKey: ['dialog', 'record', dialogGuid, dialogTable, created.uid] })
    },
  })

  const createMutation = useMutation({
    mutationFn: async (payload: { name: string; is_template?: boolean }) => {
      return dialogsAPI.startDraft(
        dialogGuid!,
        {
          name: payload.name,
          template_uid: '66666666-6666-6666-6666-666666666666',
          is_template: payload.is_template,
        },
        { dialog_table: dialogTable }
      )
    },
    onSuccess: async (draft) => {
      setActiveDraft(draft)
      setDraftValidationIssues(draft.validation_errors || [])
      setSelectedUid(null)
      setSelectedUids([])
      setActiveTab(editTabIndex)
      setJsonDirty(false)
      setJsonSearchHits(null)
      setPicDraft(draft.daten || {})
      setPicDirty(false)
    },
  })

  const createNewRecord = async () => {
    if (!dialogGuid) return

    setCreateModalError(null)
    setCreateModalOpen(true)
  }

  const saveJson = async () => {
    if (editType !== 'edit_json') return
    if (!dialogGuid) return
    if (!selectedUid && !activeDraft?.draft_id) return

    let parsed: any
    try {
      parsed = jsonEditorRef.current?.getJson()
    } catch (e: any) {
      setJsonError(e?.message || 'Ungültiges JSON')
      return
    }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      setJsonError('JSON muss ein Objekt (kein Array/Primitiv) sein.')
      return
    }

    setJsonError(null)
    if (activeDraft?.draft_id) {
      try {
        await commitDraftMutation.mutateAsync(parsed)
      } catch (e: any) {
        const issues = (e?.response?.data?.detail?.validation_errors || []) as DialogValidationIssue[]
        if (Array.isArray(issues) && issues.length > 0) {
          setDraftValidationIssues(issues)
          setJsonError(issues[0]?.message || 'Validierung fehlgeschlagen')
        } else {
          throw e
        }
      }
    } else {
      await updateMutation.mutateAsync(parsed)
    }
    setJsonDirty(false)
  }

  const savePic = async () => {
    if (!isFieldEditor) return
    if (!dialogGuid || !picDraft) return
    if (!selectedUid && !activeDraft?.draft_id) return
    if (activeDraft?.draft_id) {
      try {
        await commitDraftMutation.mutateAsync(picDraft)
      } catch (e: any) {
        const issues = (e?.response?.data?.detail?.validation_errors || []) as DialogValidationIssue[]
        if (Array.isArray(issues) && issues.length > 0) {
          setDraftValidationIssues(issues)
          setJsonError(issues[0]?.message || 'Validierung fehlgeschlagen')
          return
        }
        throw e
      }
    } else {
      await updateMutation.mutateAsync(picDraft)
    }
    setPicDirty(false)
  }

  const addControlFieldToActiveGroup = (fieldGuid: string, controlData?: Record<string, any> | null) => {
    const group = String(activeControlGroup || '').trim()
    const guid = String(fieldGuid || '').trim()
    if (!group || !guid) return

    const normalizedControlData = asObject(controlData)
    const controlType = readControlType(normalizedControlData)
    const preparedValue = defaultValueForControlType(controlType)

    setPicDraft((prev) => {
      const base = (prev || currentDaten || {}) as Record<string, any>
      const groupObj = asObject(base[group])
      if (groupObj[guid] != null) return base

      const nextGroup = {
        ...groupObj,
        [guid]: preparedValue,
      }
      return {
        ...base,
        [group]: nextGroup,
      }
    })
    setPicDirty(true)
  }

  const formatJson = () => {
    if (editType !== 'edit_json') return
    try {
      jsonEditorRef.current?.format()
      setJsonDirty(true)
    } catch (e: any) {
      setJsonError(e?.message || 'Formatieren fehlgeschlagen')
    }
  }

  const doSearch = () => {
    const q = String(jsonSearch || '').trim()
    if (!q) {
      setJsonSearchHits(null)
      return
    }

    // Prefer editor native search (tree mode). If unavailable, fall back to a simple JSON-string scan.
    let hits = 0
    try {
      hits = jsonEditorRef.current?.search(q) ?? 0
    } catch {
      hits = 0
    }

    if (!hits) {
      try {
        const json = jsonEditorRef.current?.getJson()
        const hay = JSON.stringify(json)
        const needle = q.toLowerCase()
        const h = hay.toLowerCase()
        hits = needle ? Math.max(0, h.split(needle).length - 1) : 0
      } catch {
        // If JSON invalid in text mode, just report 0.
        hits = 0
      }
    }

    setJsonSearchHits(hits)

    // Keep the cursor in the search field (important: avoids Enter overwriting editor selection)
    try {
      jsonSearchInputRef.current?.focus({ preventScroll: true })
    } catch {
      // ignore
    }
  }

  const title = useMemo(() => {
    const d = defQuery.data
    if (!d) return 'Dialog'
    return d.name ? `Dialog: ${d.name}` : `Dialog: ${d.uid}`
  }, [defQuery.data])

  const tabs = moduleTabs.length ? moduleTabs.length : Math.max(2, Number(defQuery.data?.meta?.tabs || 2))

  const tabLabel = useMemo(() => {
    const daten = defQuery.data?.daten || {}
    const root = defQuery.data?.root || {}

    const findTabBlock = (container: Record<string, any>, tabIndex: number): Record<string, any> | null => {
      if (!container || typeof container !== 'object') return null
      const rx = new RegExp(`^tab[_-]?0*${tabIndex}$`, 'i')
      for (const key of Object.keys(container)) {
        if (rx.test(String(key))) {
          const v = (container as any)[key]
          if (v && typeof v === 'object' && !Array.isArray(v)) return v
        }
      }
      return null
    }

    const getHead = (tabIndex: number): string | null => {
      const block = findTabBlock(daten as any, tabIndex) || findTabBlock(root as any, tabIndex)
      if (!block) return null
      const head = (block as any).HEAD ?? (block as any).head
      const s = head != null ? String(head).trim() : ''
      return s || null
    }

    const mod1 = tab1Module?.head ? String(tab1Module.head).trim() : ''
    const mod2 = tab2Module?.head ? String(tab2Module.head).trim() : ''
    const t1 = mod1 || getHead(1)
    const t2 = mod2 || getHead(2)
    return {
      tab1: t1 || 'Tab 1: View',
      tab2: t2 || 'Tab 2: Edit',
    }
  }, [defQuery.data?.daten, defQuery.data?.root, tab1Module, tab2Module])

  const dropdownFieldConfigs = useMemo(() => {
    if (!isFieldEditor) return [] as Array<{ fieldKey: string; table: string; datasetUid: string; field: string }>
    const out: Array<{ fieldKey: string; table: string; datasetUid: string; field: string }> = []
    uiPicDefs.forEach((def) => {
      const type = normalizePicType(def.type)
      if (type !== 'dropdown' && type !== 'multi_dropdown') return
      const cfg = asObject(def.configs?.dropdown)
      const datasetUid = String(cfg.key || cfg.dataset_uid || '').trim()
      const field = String(cfg.field || cfg.feld || '').trim()
      const table = String(cfg.table || '').trim()
      if (!datasetUid || !field || !table) return
      const fieldKey = String(def.key || `${def.gruppe || ''}.${def.feld || ''}`)
      out.push({ fieldKey, table, datasetUid, field })
    })
    return out
  }, [isFieldEditor, uiPicDefs])

  const dropdownQueries = useQueries({
    queries: dropdownFieldConfigs.map((cfg) => ({
      queryKey: ['systemdaten', 'dropdown', cfg.table, cfg.datasetUid, cfg.field],
      queryFn: () => systemdatenAPI.getDropdown({ table: cfg.table, dataset_uid: cfg.datasetUid, field: cfg.field }),
      enabled: isFieldEditor && !!cfg.table && !!cfg.datasetUid && !!cfg.field,
    })),
  })

  const dropdownOptionsByFieldKey = useMemo(() => {
    const out: Record<string, PdvmDropdownOption[]> = {}
    dropdownFieldConfigs.forEach((cfg, idx) => {
      const res = dropdownQueries[idx]
      const options = res?.data?.options || []
      out[cfg.fieldKey] = options.map((opt) => ({ value: String(opt.key), label: String(opt.value) }))
    })
    return out
  }, [dropdownFieldConfigs, dropdownQueries])

  // Menu editor tabs come from frame definition (sys_framedaten)
  const menuEditTabs = useMemo(() => {
    const frameRoot = (defQuery.data?.frame?.root || {}) as Record<string, any>

    const tabsRaw = frameRoot.TABS ?? frameRoot.tabs
    const tabs = Number(tabsRaw || 0)

    const pickTabBlock = (tabIndex: number): Record<string, any> | null => {
      const rx = new RegExp(`^tab[_-]?0*${tabIndex}$`, 'i')
      for (const key of Object.keys(frameRoot)) {
        if (!rx.test(String(key))) continue
        const v = (frameRoot as any)[key]
        if (v && typeof v === 'object' && !Array.isArray(v)) return v
      }
      return null
    }

    const normalizeGroup = (g: any): 'GRUND' | 'VERTIKAL' | null => {
      const s = String(g || '').trim().toUpperCase()
      if (s === 'GRUND') return 'GRUND'
      if (s === 'VERTIKAL') return 'VERTIKAL'
      return null
    }

    const out: Array<{ head: string; group: 'GRUND' | 'VERTIKAL' }> = []
    for (let i = 1; i <= Math.max(0, Math.min(10, tabs || 0)); i++) {
      const block = pickTabBlock(i)
      if (!block) continue
      const head = String((block as any).HEAD ?? (block as any).head ?? '').trim() || `Tab ${i}`
      const group = normalizeGroup((block as any).GRUPPE ?? (block as any).gruppe)
      if (!group) continue
      out.push({ head, group })
    }
    return { tabs, items: out }
  }, [defQuery.data?.frame?.root])

  const [menuActiveTab, setMenuActiveTab] = useState<'GRUND' | 'VERTIKAL'>('GRUND')

  const menuTabSkipPersistRef = useRef(false)
  const menuTabRestoredRef = useRef(false)

  const [workflowMaxTab, setWorkflowMaxTab] = useState(1)
  const workflowStateQuery = useQuery<DialogUiStateResponse>({
    queryKey: ['dialog', 'ui-state', 'workflow', dialogGuid, dialogTable],
    queryFn: () => dialogsAPI.getUiState(dialogGuid!, { dialog_table: dialogTable }),
    enabled: !!dialogGuid && defQuery.isSuccess && isWorkflowDialog,
  })

  useEffect(() => {
    if (!isWorkflowDialog) return
    if (!workflowStateQuery.data) return
    const raw = (workflowStateQuery.data.ui_state as any)?.workflow || null
    if (!raw || typeof raw !== 'object') return
    const active = Number((raw as any).active_tab || 1) || 1
    const maxTab = Number((raw as any).max_tab || active) || active
    setActiveTab(active)
    setWorkflowMaxTab(maxTab)
  }, [isWorkflowDialog, workflowStateQuery.data])

  useEffect(() => {
    if (!isWorkflowDialog) return
    if (!dialogGuid) return
    dialogsAPI
      .putUiState(
        dialogGuid,
        {
          ui_state: {
            workflow: {
              active_tab: activeTab,
              max_tab: workflowMaxTab,
            },
          },
        },
        { dialog_table: dialogTable }
      )
      .catch(() => {
        // Best-effort persistence only.
      })
  }, [isWorkflowDialog, dialogGuid, dialogTable, activeTab, workflowMaxTab])

  const activeModuleType = String(activeModule?.module || '').trim().toLowerCase()
  const isDialogNewModule = activeModuleType === 'dialog_new'
  const [dialogNewDraft, setDialogNewDraft] = useState(dialogNewDefaults)
  const [dialogNewBusy, setDialogNewBusy] = useState(false)
  const [dialogNewError, setDialogNewError] = useState<string | null>(null)
  const [dialogNewSuccess, setDialogNewSuccess] = useState<string | null>(null)

  const dialogNewStateQuery = useQuery<DialogUiStateResponse>({
    queryKey: ['dialog', 'ui-state', 'dialog-new', dialogGuid, dialogTable],
    queryFn: () => dialogsAPI.getUiState(dialogGuid!, { dialog_table: dialogTable }),
    enabled: !!dialogGuid && defQuery.isSuccess && isDialogNewModule,
  })

  useEffect(() => {
    if (!isDialogNewModule) return
    if (!dialogNewStateQuery.data) return
    const raw = (dialogNewStateQuery.data.ui_state as any)?.dialog_new
    if (!raw || typeof raw !== 'object') return
    setDialogNewDraft({ ...dialogNewDefaults, ...(raw as any) })
  }, [isDialogNewModule, dialogNewStateQuery.data])

  const persistDialogNew = (patch: Record<string, any>) => {
    if (!dialogGuid) return
    const next = { ...dialogNewDraft, ...patch }
    setDialogNewDraft(next)
    dialogsAPI
      .putUiState(
        dialogGuid,
        {
          ui_state: {
            dialog_new: next,
          },
        },
        { dialog_table: dialogTable }
      )
      .catch(() => {
        // Best-effort persistence only.
      })
  }

  const createDialogFromModule = async () => {
    if (!dialogGuid) return
    setDialogNewError(null)
    setDialogNewSuccess(null)

    const table = String(effectiveDialogTable || '').trim().toLowerCase()
    if (table !== 'sys_dialogdaten') {
      setDialogNewError('Dialog muss auf sys_dialogdaten zeigen, um neue Dialoge zu erstellen.')
      return
    }

    const name = String(dialogNewDraft.dialog_name || '').trim()
    if (!name) {
      setDialogNewError('Dialog-Name fehlt.')
      return
    }

    setDialogNewBusy(true)
    try {
      const created = await dialogsAPI.createRecord(
        dialogGuid,
        {
          name,
          template_uid: '66666666-6666-6666-6666-666666666666',
        },
        { dialog_table: dialogTable }
      )

      const rootTable = String(dialogNewDraft.root_table || '').trim()
      const viewGuid = String(dialogNewDraft.view_guid || '').trim()
      const frameGuid = String(dialogNewDraft.frame_guid || '').trim()
      const dialogType = String(dialogNewDraft.dialog_type || 'norm').trim().toLowerCase()

      const root: Record<string, any> = {
        SELF_GUID: created.uid,
        SELF_NAME: name,
        DIALOG_TYPE: dialogType || 'norm',
        TABLE: rootTable,
        TABS: 2,
        OPEN_EDIT: 'double_click',
        SELECTION_MODE: 'single',
        TAB_01: {
          HEAD: 'View',
          MODULE: 'view',
          GUID: viewGuid,
          TABLE: rootTable,
        },
        TAB_02: {
          HEAD: 'Edit',
          MODULE: 'edit',
          GUID: frameGuid,
          EDIT_TYPE: 'pdvm_edit',
        },
      }

      await dialogsAPI.updateRecord(
        dialogGuid,
        created.uid,
        { daten: { ROOT: root } },
        { dialog_table: dialogTable }
      )

      setDialogNewSuccess(`Dialog erstellt: ${created.uid}`)
    } catch (e: any) {
      setDialogNewError(e?.response?.data?.detail || e?.message || 'Dialog konnte nicht erstellt werden')
    } finally {
      setDialogNewBusy(false)
    }
  }

  const uiStateQuery = useQuery<DialogUiStateResponse>({
    queryKey: ['dialog', 'ui-state', dialogGuid, dialogTable],
    queryFn: () => dialogsAPI.getUiState(dialogGuid!, { dialog_table: dialogTable }),
    enabled: !!dialogGuid && defQuery.isSuccess && wantsMenuEditor,
  })

  useEffect(() => {
    if (!wantsMenuEditor) return
    if (!uiStateQuery.data) return
    if (menuTabRestoredRef.current) return

    const raw = (uiStateQuery.data.ui_state as any)?.menu_active_tab
    const s = String(raw || '').trim().toUpperCase()
    if (s === 'GRUND' || s === 'VERTIKAL') {
      menuTabSkipPersistRef.current = true
      setMenuActiveTab(s as any)
    }
    menuTabRestoredRef.current = true
  }, [wantsMenuEditor, uiStateQuery.data])

  useEffect(() => {
    if (!wantsMenuEditor) return
    if (!dialogGuid) return
    if (!defQuery.isSuccess) return

    if (menuTabSkipPersistRef.current) {
      menuTabSkipPersistRef.current = false
      return
    }

    dialogsAPI
      .putUiState(
        dialogGuid,
        {
          ui_state: {
            menu_active_tab: menuActiveTab,
          },
        },
        { dialog_table: dialogTable }
      )
      .catch(() => {
        // Best-effort persistence only.
      })
  }, [wantsMenuEditor, dialogGuid, dialogTable, defQuery.isSuccess, menuActiveTab])

  const handleMissingMenuGuid = (missingUid: string) => {
    // Only relevant for menu dialogs
    if (!dialogGuid) return
    if (missingUid) {
      ignoredAutoLastCallUidRef.current = missingUid
    }
    setAutoLastCallError(`Letztes Menü (last_call) wurde nicht gefunden: ${missingUid}. Bitte neu auswählen.`)
    setSelectedUid(null)
    setSelectedUids([])
    setActiveTab(viewTabIndex)
    dialogsAPI.putLastCall(dialogGuid, null, { dialog_table: dialogTable }).catch(() => {
      // Best-effort persistence only.
    })
    queryClient.invalidateQueries({ queryKey: ['dialog', 'definition', dialogGuid, dialogTable] }).catch(() => {
      // Best-effort refresh only.
    })
  }

  const handleImportApplied = async () => {
    await queryClient.invalidateQueries({ queryKey: ['dialog', 'rows', dialogGuid, dialogTable] })
    const embeddedViewGuid = String(effectiveViewGuid || '').trim()
    if (embeddedViewGuid) {
      await queryClient.invalidateQueries({ queryKey: ['view', 'matrix', embeddedViewGuid] })
    }
  }

  const performRefreshEdit = async () => {
    if (!dialogGuid) return
    if (!selectedUid && !activeDraft?.draft_id) return

    setAutoLastCallError(null)

    if (activeDraft?.draft_id) {
      setJsonError(null)
      setJsonDirty(false)
      setJsonSearchHits(null)
      setPicDirty(false)
      setPicDraft(activeDraft.daten || null)
      updateMutation.reset()
      commitDraftMutation.reset()
      return
    }

    if (wantsMenuEditor) {
      await queryClient.invalidateQueries({ queryKey: ['menu-editor', 'menu', selectedUid] })
      setMenuEditorRefreshToken((t) => t + 1)
      return
    }

    await queryClient.invalidateQueries({ queryKey: ['dialog', 'record', dialogGuid, dialogTable, selectedUid] })
    try {
      await recordQuery.refetch()
    } catch {
      // ignore
    }

    setJsonError(null)
    setJsonDirty(false)
    setJsonSearchHits(null)
    setPicDirty(false)
    setPicDraft(null)
    updateMutation.reset()
    commitDraftMutation.reset()
  }

  const refreshEdit = async () => {
    if (activeTab !== editTabIndex) return
    if ((editType === 'edit_json' && jsonDirty) || (isFieldEditor && picDirty)) {
      setRefreshModalOpen(true)
      return
    }
    await performRefreshEdit()
  }

  return (
    <div className="pdvm-dialog">
      <PdvmDialogModal
        open={infoModalOpen && !!autoLastCallError}
        kind="info"
        title="Hinweis"
        message={autoLastCallError || ''}
        confirmLabel="OK"
        busy={false}
        onCancel={() => {
          setInfoModalOpen(false)
          setAutoLastCallError(null)
        }}
        onConfirm={() => {
          setInfoModalOpen(false)
          setAutoLastCallError(null)
        }}
      />

      <PdvmDialogModal
        open={infoModalOpen && !!userActionInfo}
        kind="info"
        title="Hinweis"
        message={userActionInfo || ''}
        confirmLabel="OK"
        busy={false}
        onCancel={() => {
          setInfoModalOpen(false)
          setUserActionInfo(null)
          setUserActionError(null)
        }}
        onConfirm={() => {
          setInfoModalOpen(false)
          setUserActionInfo(null)
          setUserActionError(null)
        }}
      />

      <PdvmDialogModal
        open={infoModalOpen && !!userActionError}
        kind="info"
        title="Fehler"
        message={userActionError || ''}
        confirmLabel="OK"
        busy={false}
        onCancel={() => {
          setInfoModalOpen(false)
          setUserActionInfo(null)
          setUserActionError(null)
        }}
        onConfirm={() => {
          setInfoModalOpen(false)
          setUserActionInfo(null)
          setUserActionError(null)
        }}
      />

      <PdvmDialogModal
        open={resetPwConfirmOpen}
        kind="confirm"
        title="Maschinelles Passwort senden"
        message="Ein neues maschinelles Passwort wird erzeugt und per E-Mail versendet. Fortfahren?"
        confirmLabel="Senden"
        cancelLabel="Abbrechen"
        busy={userActionBusy}
        onCancel={() => setResetPwConfirmOpen(false)}
        onConfirm={async () => {
          if (!selectedUid) return
          setUserActionBusy(true)
          setResetPwConfirmOpen(false)
          try {
            const res = await usersAPI.resetPassword(selectedUid)
            if (res.email_sent) {
              setUserActionInfo(`OTP gesendet an ${res.email}. Gültig bis ${res.expires_at}.`)
            } else {
              setUserActionError(`OTP erstellt, E-Mail fehlgeschlagen: ${res.email_error || 'unbekannt'}`)
            }
            await performRefreshEdit()
          } catch (e: any) {
            setUserActionError(e?.response?.data?.detail || e?.message || 'Passwort-Reset fehlgeschlagen')
          } finally {
            setUserActionBusy(false)
          }
        }}
      />

      <PdvmDialogModal
        open={lockAccountOpen}
        kind="form"
        title="Account sperren"
        message="Bitte optionalen Sperrgrund angeben."
        fields={[{ name: 'reason', label: 'Grund', type: 'text', required: false }]}
        confirmLabel="Sperren"
        cancelLabel="Abbrechen"
        busy={userActionBusy}
        onCancel={() => setLockAccountOpen(false)}
        onConfirm={async (values) => {
          if (!selectedUid) return
          setUserActionBusy(true)
          setLockAccountOpen(false)
          try {
            await usersAPI.lockAccount(selectedUid, String(values?.reason || '').trim() || undefined)
            setUserActionInfo('Account wurde gesperrt.')
            await performRefreshEdit()
          } catch (e: any) {
            setUserActionError(e?.response?.data?.detail || e?.message || 'Account-Sperre fehlgeschlagen')
          } finally {
            setUserActionBusy(false)
          }
        }}
      />

      <PdvmDialogModal
        open={unlockAccountOpen}
        kind="confirm"
        title="Account entsperren"
        message="Account wirklich entsperren?"
        confirmLabel="Entsperren"
        cancelLabel="Abbrechen"
        busy={userActionBusy}
        onCancel={() => setUnlockAccountOpen(false)}
        onConfirm={async () => {
          if (!selectedUid) return
          setUserActionBusy(true)
          setUnlockAccountOpen(false)
          try {
            await usersAPI.unlockAccount(selectedUid)
            setUserActionInfo('Account wurde entsperrt.')
            await performRefreshEdit()
          } catch (e: any) {
            setUserActionError(e?.response?.data?.detail || e?.message || 'Account-Entsperrung fehlgeschlagen')
          } finally {
            setUserActionBusy(false)
          }
        }}
      />

      <PdvmDialogModal
        open={discardModalOpen}
        kind="confirm"
        title="Änderungen verwerfen?"
        message="Es gibt ungespeicherte Änderungen. Beim Wechseln gehen diese verloren."
        confirmLabel="Verwerfen"
        cancelLabel="Abbrechen"
        busy={updateMutation.isPending || createMutation.isPending || commitDraftMutation.isPending}
        onCancel={() => {
          setDiscardModalOpen(false)
          setPendingTab(null)
        }}
        onConfirm={() => {
          // Best-effort: reset editor content to last loaded record state.
          try {
            if (currentDaten && editType === 'edit_json') {
              jsonEditorRef.current?.setJson(currentDaten)
              jsonEditorRef.current?.setMode(jsonMode)
            }
          } catch {
            // ignore
          }

          if (currentDaten && isFieldEditor) {
            setPicDraft(currentDaten)
            setPicDirty(false)
          }

          setJsonError(null)
          setJsonDirty(false)
          setJsonSearchHits(null)
          updateMutation.reset()
          commitDraftMutation.reset()

          const next = pendingTab
          setDiscardModalOpen(false)
          setPendingTab(null)
          if (next) setActiveTab(next)
        }}
      />

      <PdvmDialogModal
        open={refreshModalOpen}
        kind="confirm"
        title="Edit neu laden?"
        message="Der Editbereich wird aus der Datenbank neu geladen. Ungespeicherte Änderungen gehen verloren."
        confirmLabel="Neu laden"
        cancelLabel="Abbrechen"
        busy={updateMutation.isPending || createMutation.isPending || commitDraftMutation.isPending}
        onCancel={() => setRefreshModalOpen(false)}
        onConfirm={async () => {
          setRefreshModalOpen(false)
          await performRefreshEdit()
        }}
      />

      <PdvmDialogModal
        open={addControlFieldOpen}
        kind="form"
        title="Feld zur Gruppe hinzufügen"
        message={activeControlGroup ? `Gruppe: ${activeControlGroup}` : 'Bitte Gruppe wählen'}
        fields={[
          {
            name: 'field_guid',
            label: 'Feld (GUID)',
            type: 'dropdown',
            required: true,
            options:
              availableControlFieldOptions.length > 0
                ? availableControlFieldOptions
                : [{ value: '', label: controlFieldLookupQuery.isLoading ? 'Lade...' : 'Keine verfügbaren Felder' }],
          },
        ]}
        initialValues={{ field_guid: availableControlFieldOptions[0]?.value || '' }}
        error={addControlFieldError}
        confirmLabel="Hinzufügen"
        cancelLabel="Abbrechen"
        busy={controlFieldLookupQuery.isLoading || addControlFieldBusy}
        onCancel={() => {
          if (addControlFieldBusy) return
          setAddControlFieldOpen(false)
          setAddControlFieldError(null)
        }}
        onConfirm={async (values) => {
          const guid = String(values?.field_guid || '').trim()
          if (!activeControlGroup) {
            setAddControlFieldError('Keine aktive Gruppe ausgewählt.')
            return
          }
          if (!guid) {
            setAddControlFieldError('Bitte ein Feld auswählen.')
            return
          }

          try {
            setAddControlFieldBusy(true)
            setAddControlFieldError(null)

            const control = await controlDictAPI.getControl(guid)
            const controlDaten = asObject(control?.daten)

            if (!Object.keys(controlDaten).length) {
              throw new Error('Control-Daten sind leer')
            }

            addControlFieldToActiveGroup(guid, controlDaten)
            setAddControlFieldOpen(false)
            setAddControlFieldError(null)
          } catch (e: any) {
            setAddControlFieldError(e?.response?.data?.detail || e?.message || 'Control konnte nicht geladen werden')
          } finally {
            setAddControlFieldBusy(false)
          }
        }}
      />

      <PdvmDialogModal
        open={createModalOpen}
        kind="form"
        title="Neuer Datensatz"
        message={isSysMenuTable ? 'Bitte Name und Menü-Typ auswählen. Es wird zuerst ein Draft erzeugt.' : 'Bitte Name eingeben (Template: 6666... → Draft → Edit → Speichern).'}
        fields={(
          [
            {
              name: 'name',
              label: 'Name',
              type: 'text',
              required: true,
              minLength: 1,
              maxLength: 200,
              autoFocus: true,
              placeholder: 'z.B. Neuer Satz',
            },
          ] as any[]
        ).concat(
          isSysMenuTable
            ? [
                {
                  name: 'menu_type',
                  label: 'Menü-Typ',
                  type: 'dropdown',
                  options: [
                    { value: 'standard', label: 'Standard-Menü' },
                    { value: 'template', label: 'Template-Menü' },
                  ],
                },
              ]
            : []
        )}
        initialValues={isSysMenuTable ? { menu_type: 'standard' } : undefined}
        confirmLabel="Erstellen"
        cancelLabel="Abbrechen"
        busy={createMutation.isPending || updateMutation.isPending || commitDraftMutation.isPending}
        error={createModalError}
        onCancel={() => {
          if (createMutation.isPending || updateMutation.isPending || commitDraftMutation.isPending) return
          setCreateModalOpen(false)
          setCreateModalError(null)
        }}
        onConfirm={async (values) => {
          const name = String(values?.name || '').trim()
          if (!name) return

          const menuType = String(values?.menu_type || '').trim().toLowerCase()
          const isTemplate = menuType === 'template'

          try {
            setAutoLastCallError(null)
            setCreateModalError(null)
            await createMutation.mutateAsync({ name, is_template: isSysMenuTable ? isTemplate : undefined })
            setCreateModalOpen(false)
          } catch (e: any) {
            const detail = e?.response?.data?.detail
            setCreateModalError(String(detail || e?.message || 'Neuer Datensatz konnte nicht angelegt werden'))
          }
        }}
      />

      <div className="pdvm-dialog__header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <h2 style={{ margin: 0 }}>{title}</h2>
          <div style={{ fontSize: 12, opacity: 0.7 }}>
            {defQuery.data?.root_table ? `TABLE: ${defQuery.data.root_table}` : null}
          </div>

          <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
            {isWorkflowDialog && activeTab > 1 ? (
              <button
                type="button"
                onClick={() => {
                  setActiveTab(1)
                  setWorkflowMaxTab(1)
                }}
                className="pdvm-dialog__toolBtn"
                title="Workflow neu starten"
                aria-label="Von vorne"
              >
                Von vorne
              </button>
            ) : null}

            {isWorkflowDialog && activeTab < tabs ? (
              <button
                type="button"
                onClick={() => {
                  const next = Math.min(tabs, activeTab + 1)
                  setActiveTab(next)
                  setWorkflowMaxTab(next)
                }}
                className="pdvm-dialog__toolBtn"
                title="Naechster Schritt"
                aria-label="Weiter"
              >
                Weiter
              </button>
            ) : null}

            <button
              type="button"
              onClick={() => {
                refreshEdit().catch(() => {
                  // ignore
                })
              }}
              disabled={(!selectedUid && !isDraftMode) || activeTab !== editTabIndex || createMutation.isPending || updateMutation.isPending || commitDraftMutation.isPending}
              className="pdvm-dialog__toolBtn"
              title="Editbereich aus DB neu laden"
              aria-label="Refresh Edit"
            >
              Refresh Edit
            </button>

            {isFieldEditor && activeTab === editTabIndex ? (
              <button
                type="button"
                onClick={() => {
                  savePic().catch(() => {
                    // ignore
                  })
                }}
                disabled={!picDirty || (!selectedUid && !isDraftMode) || activeTab !== editTabIndex || createMutation.isPending || updateMutation.isPending || commitDraftMutation.isPending}
                className="pdvm-dialog__toolBtn"
                title="Änderungen speichern"
                aria-label="Speichern"
              >
                Speichern
              </button>
            ) : null}

            {activeTab === viewTabIndex ? (
              <button
                type="button"
                onClick={createNewRecord}
                disabled={createMutation.isPending || updateMutation.isPending || commitDraftMutation.isPending}
                className="pdvm-dialog__toolBtn"
                title="Neuen Datensatz (aus Template 6666...) erstellen"
                aria-label="Neuer Satz"
              >
                Neuer Satz
              </button>
            ) : null}
          </div>
        </div>

        {defQuery.data ? (
          <div style={{ marginTop: 6, fontSize: 12, opacity: 0.75, display: 'flex', gap: 14, flexWrap: 'wrap' }}>
            <div>
              open_edit_mode: <span style={{ fontFamily: 'monospace' }}>{String(defQuery.data.open_edit_mode || '')}</span>
            </div>
            <div>
              last_call: <span style={{ fontFamily: 'monospace' }}>{String((defQuery.data.meta as any)?.last_call || '')}</span>
            </div>
            <div>
              last_call_key: <span style={{ fontFamily: 'monospace' }}>{String((defQuery.data.meta as any)?.last_call_key || '')}</span>
            </div>
          </div>
        ) : null}

        {defQuery.isError ? (
          <div style={{ color: 'crimson', marginTop: 8 }}>
            Fehler: {(defQuery.error as any)?.message || 'Dialog konnte nicht geladen werden'}
          </div>
        ) : null}
      </div>

      <div className="pdvm-tabs pdvm-dialog__tabs">
        <div className="pdvm-tabs__bar pdvm-dialog__tabbar">
          <div className="pdvm-tabs__list" role="tablist" aria-label="Dialog Tabs">
            {moduleTabs.length ? (
              moduleTabs.map((t) => {
                const idx = Number(t?.index || 0) || 0
                if (!idx) return null
                const head = String(t?.head || '').trim() || `Tab ${idx}`
                const disabled = isWorkflowDialog && idx > workflowMaxTab
                return (
                  <button
                    key={idx}
                    type="button"
                    role="tab"
                    aria-selected={activeTab === idx}
                    className={`pdvm-tabs__tab ${activeTab === idx ? 'pdvm-tabs__tab--active' : ''}`}
                    onClick={() => {
                      if (disabled) return
                      if (activeTab === editTabIndex && ((editType === 'edit_json' && jsonDirty) || (isFieldEditor && picDirty))) {
                        setPendingTab(viewTabIndex)
                        setDiscardModalOpen(true)
                        return
                      }
                      setActiveTab(idx)
                      if (isWorkflowDialog && idx < workflowMaxTab) {
                        setWorkflowMaxTab(idx)
                      }
                    }}
                  >
                    {head}
                  </button>
                )
              })
            ) : (
              <>
                <button
                  type="button"
                  role="tab"
                  aria-selected={activeTab === viewTabIndex}
                  className={`pdvm-tabs__tab ${activeTab === viewTabIndex ? 'pdvm-tabs__tab--active' : ''}`}
                  onClick={() => {
                    if (activeTab === editTabIndex && ((editType === 'edit_json' && jsonDirty) || (isFieldEditor && picDirty))) {
                      setPendingTab(viewTabIndex)
                      setDiscardModalOpen(true)
                      return
                    }
                    setActiveTab(viewTabIndex)
                  }}
                >
                  {tabLabel.tab1}
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={activeTab === editTabIndex}
                  className={`pdvm-tabs__tab ${activeTab === editTabIndex ? 'pdvm-tabs__tab--active' : ''}`}
                  onClick={() => setActiveTab(editTabIndex)}
                >
                  {tabLabel.tab2}
                </button>
              </>
            )}
          </div>

          <div className="pdvm-tabs__actions">
            <div className="pdvm-tabs__meta">Tabs (config): {tabs}</div>
          </div>
        </div>

        <div className="pdvm-tabs__panel pdvm-dialog__panel">
          <div
            className={`pdvm-dialog__panelScroll ${activeTab === viewTabIndex && hasEmbeddedView ? 'pdvm-dialog__panelScroll--noScroll' : ''} ${activeTab === editTabIndex ? 'pdvm-dialog__panelScroll--noScroll' : ''}`}
          >
          {/* edit_type=menu nutzt Auswahl im View-Tab; ROOT.MENU_GUID ist optional (Preselect) */}

          {autoLastCallError ? (
            <div style={{ marginBottom: 10, color: 'goldenrod', fontSize: 12 }}>{autoLastCallError}</div>
          ) : null}

          {activeModuleType === 'view' || (!moduleTabs.length && activeTab === viewTabIndex) ? (
            <div className="pdvm-dialog__view">
              {isDialogNewModule ? (
                <div style={{ display: 'grid', gap: 12, maxWidth: 720 }}>
                  <PdvmInputControl
                    label="Dialog-Name"
                    type="string"
                    value={dialogNewDraft.dialog_name}
                    onChange={(v) => setDialogNewDraft((prev) => ({ ...prev, dialog_name: String(v || '') }))}
                    onBlur={() => persistDialogNew({ dialog_name: dialogNewDraft.dialog_name })}
                  />
                  <PdvmInputControl
                    label="Dialog-Typ"
                    type="dropdown"
                    value={dialogNewDraft.dialog_type}
                    onChange={(v) => setDialogNewDraft((prev) => ({ ...prev, dialog_type: String(v || '') }))}
                    onBlur={() => persistDialogNew({ dialog_type: dialogNewDraft.dialog_type })}
                    options={[
                      { value: 'norm', label: 'norm' },
                      { value: 'work', label: 'work' },
                      { value: 'acti', label: 'acti' },
                    ]}
                  />
                  <PdvmInputControl
                    label="Root Table"
                    type="string"
                    value={dialogNewDraft.root_table}
                    onChange={(v) => setDialogNewDraft((prev) => ({ ...prev, root_table: String(v || '') }))}
                    onBlur={() => persistDialogNew({ root_table: dialogNewDraft.root_table })}
                  />
                  <PdvmInputControl
                    label="View GUID"
                    type="string"
                    value={dialogNewDraft.view_guid}
                    onChange={(v) => setDialogNewDraft((prev) => ({ ...prev, view_guid: String(v || '') }))}
                    onBlur={() => persistDialogNew({ view_guid: dialogNewDraft.view_guid })}
                  />
                  <PdvmInputControl
                    label="Frame GUID"
                    type="string"
                    value={dialogNewDraft.frame_guid}
                    onChange={(v) => setDialogNewDraft((prev) => ({ ...prev, frame_guid: String(v || '') }))}
                    onBlur={() => persistDialogNew({ frame_guid: dialogNewDraft.frame_guid })}
                  />

                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <button type="button" className="pdvm-dialog__toolBtn pdvm-dialog__toolBtn--primary" onClick={createDialogFromModule} disabled={dialogNewBusy}>
                      {dialogNewBusy ? 'Erstelle...' : 'Erstellen'}
                    </button>
                    {dialogNewSuccess ? <div style={{ fontSize: 12, opacity: 0.8 }}>{dialogNewSuccess}</div> : null}
                    {dialogNewError ? <div style={{ fontSize: 12, color: 'crimson' }}>{dialogNewError}</div> : null}
                  </div>
                </div>
              ) : effectiveViewGuid ? (
                <PdvmViewPageContent
                  viewGuid={String(effectiveViewGuid)}
                  tableOverride={effectiveDialogTable}
                  editType={editType}
                  embedded
                />
              ) : (
                <>
                  <div style={{ marginBottom: 12, color: 'crimson', fontSize: 12 }}>
                    Dialog hat keine VIEW_GUID. Bitte Dialog/View-Definition prüfen (Zielbild: Dialog arbeitet immer mit einer View).
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                    <div style={{ fontSize: 12, opacity: 0.75 }}>
                      {selectedUids.length > 0 ? `Ausgewählt: ${selectedUids.length}` : selectedUid ? 'Ausgewählt: 1' : 'Ausgewählt: 0'}
                    </div>
                    <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
                      <button onClick={() => setPageOffset((o) => Math.max(0, o - pageLimit))} disabled={pageOffset === 0 || rowsQuery.isLoading}>
                        Zurück
                      </button>
                      <button
                        onClick={() => setPageOffset((o) => o + pageLimit)}
                        disabled={rowsQuery.isLoading || (rowsQuery.data?.rows?.length || 0) < pageLimit}
                      >
                        Weiter
                      </button>
                    </div>
                  </div>

                  {rowsQuery.isLoading ? <div>Lade...</div> : null}
                  {rowsQuery.isError ? (
                    <div style={{ color: 'crimson' }}>Fehler: {(rowsQuery.error as any)?.message || 'Rows konnten nicht geladen werden'}</div>
                  ) : null}
                  <div className="pdvm-dialog__viewList">
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                      <thead>
                        <tr>
                          <th style={{ textAlign: 'left', borderBottom: '1px solid #ccc', padding: 6, width: 360 }}>UID</th>
                          <th style={{ textAlign: 'left', borderBottom: '1px solid #ccc', padding: 6 }}>Name</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(rowsQuery.data?.rows || []).map((r) => {
                          const isSelected = selectedUid === r.uid
                          return (
                            <tr
                              key={r.uid}
                              onClick={() => {
                                setSelectedUid(r.uid)
                                setSelectedUids([r.uid])
                              }}
                              onDoubleClick={() => {
                                if (openEditMode === 'double_click') {
                                  setSelectedUid(r.uid)
                                  setSelectedUids([r.uid])
                                  setActiveTab(editTabIndex)
                                }
                              }}
                              style={{ cursor: 'pointer', background: isSelected ? 'rgba(0, 120, 215, 0.12)' : 'transparent' }}
                              title={isSelected ? 'Ausgewählt' : 'Klicken zum Auswählen'}
                            >
                              <td style={{ borderBottom: '1px solid #eee', padding: 6, fontFamily: 'monospace', fontSize: 12 }}>{r.uid}</td>
                              <td style={{ borderBottom: '1px solid #eee', padding: 6 }}>{r.name}</td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </div>
          ) : null}

          {activeModuleType === 'edit' || (!moduleTabs.length && activeTab === editTabIndex) ? (
            <div className="pdvm-dialog__editArea">
              {isMenuEditor ? (
                <>
                  <div className="pdvm-dialog__editAreaHeader">
                    {renderEditInfo()}
                    {selectedUid && menuEditTabs.tabs >= 2 && menuEditTabs.items.length >= 2 ? (
                      <div className="pdvm-tabs">
                        <div className="pdvm-tabs__bar">
                          <div className="pdvm-tabs__list" role="tablist" aria-label="Menü Edit Tabs">
                            {menuEditTabs.items.map((t) => (
                              <button
                                key={t.group}
                                type="button"
                                role="tab"
                                aria-selected={menuActiveTab === t.group}
                                className={`pdvm-tabs__tab ${menuActiveTab === t.group ? 'pdvm-tabs__tab--active' : ''}`}
                                onClick={() => setMenuActiveTab(t.group)}
                              >
                                {t.head}
                              </button>
                            ))}
                          </div>
                        </div>
                      </div>
                    ) : null}
                  </div>
                  <div className="pdvm-dialog__editAreaContent">
                    {!selectedUid ? <div>Kein Menüdatensatz ausgewählt. Bitte zuerst im View-Tab auswählen.</div> : null}

                    {selectedUid ? (
                      <div>
                        {menuEditTabs.tabs >= 2 && menuEditTabs.items.length >= 2 ? (
                          <div className="pdvm-tabs__panel">
                            <PdvmMenuEditor
                              key={`${selectedUid}|${menuActiveTab}|${menuEditorRefreshToken}`}
                              menuGuid={selectedUid}
                              group={menuActiveTab}
                              systemdatenUid={systemdatenUid}
                              frameDaten={defQuery.data?.frame?.daten || null}
                              onMissingMenuGuid={handleMissingMenuGuid}
                            />
                          </div>
                        ) : (
                          <>
                            <div style={{ marginBottom: 16 }}>
                              <div style={{ fontWeight: 800, marginBottom: 8 }}>GRUND</div>
                              <PdvmMenuEditor
                                key={`${selectedUid}|GRUND|${menuEditorRefreshToken}`}
                                menuGuid={selectedUid}
                                group="GRUND"
                                systemdatenUid={systemdatenUid}
                                frameDaten={defQuery.data?.frame?.daten || null}
                                onMissingMenuGuid={handleMissingMenuGuid}
                              />
                            </div>
                            <div>
                              <div style={{ fontWeight: 800, marginBottom: 8 }}>VERTIKAL</div>
                              <PdvmMenuEditor
                                key={`${selectedUid}|VERTIKAL|${menuEditorRefreshToken}`}
                                menuGuid={selectedUid}
                                group="VERTIKAL"
                                systemdatenUid={systemdatenUid}
                                frameDaten={defQuery.data?.frame?.daten || null}
                                onMissingMenuGuid={handleMissingMenuGuid}
                              />
                            </div>
                          </>
                        )}
                      </div>
                    ) : null}
                  </div>
                </>
              ) : isFieldEditor ? (
                <>
                  <div className="pdvm-dialog__editAreaHeader">
                    {isPicEditor && currentDaten ? (
                      <div style={{ marginBottom: 10, display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' }}>
                        <div style={{ fontSize: 12, opacity: 0.75 }}>
                          Passwortwechsel erforderlich:{' '}
                          <strong>{String(((currentDaten?.SECURITY as any) || {})?.PASSWORD_CHANGE_REQUIRED ? 'JA' : 'NEIN')}</strong>
                        </div>
                        <div style={{ fontSize: 12, opacity: 0.75 }}>
                          Account gesperrt:{' '}
                          <strong>{String(((currentDaten?.SECURITY as any) || {})?.ACCOUNT_LOCKED ? 'JA' : 'NEIN')}</strong>
                        </div>
                        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
                          <button
                            type="button"
                            className="pdvm-dialog__toolBtn"
                            onClick={() => setResetPwConfirmOpen(true)}
                            disabled={!selectedUid || userActionBusy}
                          >
                            Maschinelles Passwort senden
                          </button>
                          {(((currentDaten?.SECURITY as any) || {})?.ACCOUNT_LOCKED ? true : false) ? (
                            <button
                              type="button"
                              className="pdvm-dialog__toolBtn"
                              onClick={() => setUnlockAccountOpen(true)}
                              disabled={!selectedUid || userActionBusy}
                            >
                              Account entsperren
                            </button>
                          ) : (
                            <button
                              type="button"
                              className="pdvm-dialog__toolBtn"
                              onClick={() => setLockAccountOpen(true)}
                              disabled={!selectedUid || userActionBusy}
                            >
                              Account sperren
                            </button>
                          )}
                        </div>
                      </div>
                    ) : null}
                    {renderEditInfo()}
                    {isControlEditor && activeControlGroup ? (
                      <div style={{ marginTop: 8 }}>
                        <button
                          type="button"
                          className="pdvm-dialog__toolBtn"
                          onClick={() => {
                            setAddControlFieldError(null)
                            setAddControlFieldOpen(true)
                          }}
                          disabled={recordQuery.isLoading}
                        >
                          Feld zu Gruppe "{activeControlGroup}" hinzufügen
                        </button>
                      </div>
                    ) : null}
                    {effectivePicTabs.items.length > 1 ? (
                      <div className="pdvm-tabs pdvm-tabs--sticky pdvm-dialog__editUserTabs">
                        <div className="pdvm-tabs__bar">
                          <div className="pdvm-tabs__list" role="tablist" aria-label="Edit Tabs">
                            {effectivePicTabs.items.map((t) => (
                              <button
                                key={t.index}
                                type="button"
                                role="tab"
                                aria-selected={picActiveTab === t.index}
                                className={`pdvm-tabs__tab ${picActiveTab === t.index ? 'pdvm-tabs__tab--active' : ''}`}
                                onClick={() => setPicActiveTab(t.index)}
                              >
                                {t.head}
                              </button>
                            ))}
                          </div>
                        </div>
                      </div>
                    ) : null}
                  </div>
                  <div className="pdvm-dialog__editAreaContent">
                    {!selectedUid && !isDraftMode ? (
                      <div style={{ opacity: 0.75 }}>
                        {isControlEditor
                          ? 'Kein Datensatz ausgewählt. Bitte zuerst im View-Tab auswählen.'
                          : 'Keine FIELDS im Frame definiert.'}
                      </div>
                    ) : null}

                    {selectedUid && !isDraftMode && recordQuery.isLoading ? (
                      <div style={{ opacity: 0.75 }}>Lade Datensatz...</div>
                    ) : null}

                    {(selectedUid || isDraftMode) && !recordQuery.isLoading && effectivePicDefs.length === 0 ? (
                      <div style={{ opacity: 0.75 }}>
                        {isControlEditor
                          ? 'Keine editierbaren Properties im Datensatz gefunden.'
                          : 'Keine FIELDS im Frame definiert.'}
                      </div>
                    ) : null}

                    <div style={{ display: 'grid', gap: 12 }}>
                      {uiPicDefs
                        .filter((d) => Number(d.tab || 1) === picActiveTab)
                        .map((d) => {
                          const gruppe = String(d.gruppe || '').trim()
                          const feld = String(d.feld || '').trim()
                          if (!gruppe || !feld) return null

                          const current = picDraft ? picDraft : currentDaten || {}
                          const rawValue = getFieldValue(current, gruppe, feld)
                          const type = normalizePicType(d.type)
                          const fieldKey = String(d.key || `${gruppe}.${feld}`)
                          const validationKey = `${gruppe}.${feld}`
                          const validationMessage = draftErrorByField[validationKey]
                          const options = dropdownOptionsByFieldKey[fieldKey] || []
                          const elementTemplate = d.configs?.element_template || d.configs?.template || d.configs?.elemente_template || null
                          const elementFields = d.configs?.element_fields || d.configs?.fields || null

                          const onChange = (value: any) => {
                            setPicDraft((prev) => {
                              const base = prev || (currentDaten || {})
                              return setFieldValue(base, gruppe, feld, value)
                            })
                            setPicDirty(true)
                          }

                          if (type === 'go_select_view') {
                            const lookupTable = String(d.configs?.viewtable || d.configs?.table || '').trim()
                            const fallbackTable = feld.endsWith('.MENU') ? 'sys_menudaten' : ''
                            const effectiveTable = lookupTable || fallbackTable
                            return (
                              <div key={fieldKey} className="pdvm-pic" title={d.tooltip || undefined}>
                                <div className="pdvm-pic__labelRow">
                                  <label className="pdvm-pic__label">{d.label || d.name || feld}</label>
                                </div>
                                <div className="pdvm-pic__control">
                                  <PdvmLookupSelect
                                    table={effectiveTable}
                                    value={rawValue ? String(rawValue) : null}
                                    onChange={(v) => onChange(v)}
                                    disabled={!!d.read_only}
                                  />
                                </div>
                              </div>
                            )
                          }

                          if (type === 'action') {
                            return (
                              <div key={fieldKey} className="pdvm-pic" title={d.tooltip || undefined}>
                                <div className="pdvm-pic__labelRow">
                                  <label className="pdvm-pic__label">{d.label || d.name || feld}</label>
                                </div>
                                <div className="pdvm-pic__control">
                                  <button type="button" className="pdvm-dialog__toolBtn" disabled={!!d.read_only}>
                                    {d.label || d.name || feld}
                                  </button>
                                </div>
                              </div>
                            )
                          }

                          return (
                            <PdvmInputControl
                              key={fieldKey}
                              label={d.label || d.name || feld}
                              tooltip={d.tooltip}
                              type={type === 'multi_dropdown' ? 'multi_dropdown' : (type as any)}
                              value={rawValue}
                              onChange={onChange}
                              readOnly={!!d.read_only}
                              options={options}
                              helpText={validationMessage ? `${validationMessage}${d.tooltip ? ` · ${d.tooltip}` : ''}` : (d.tooltip || '')}
                              elementTemplate={elementTemplate}
                              elementFields={elementFields}
                              controlDebug={{
                                field_key: fieldKey,
                                gruppe,
                                feld,
                                pic_def: d,
                                resolved_control: resolvedControlByGroupField[`${gruppe.toUpperCase()}::${feld.toUpperCase()}`] || null,
                              }}
                            />
                          )
                        })}
                    </div>
                  </div>
                </>
              ) : (
                <>
                  <div className="pdvm-dialog__editAreaHeader">
                    {isImportEditor ? <PdvmImportDataSteps step={importStep} onChange={setImportStep} /> : null}
                    {renderEditInfo()}
                  </div>
                  <div
                    className={`pdvm-dialog__editAreaContent ${editType === 'edit_json' ? 'pdvm-dialog__editAreaContent--noScroll' : ''}`.trim()}
                  >

                  {!selectedUid && !isDraftMode ? <div>Kein Datensatz ausgewählt. Bitte zuerst im View-Tab auswählen.</div> : null}

                  {selectedUid && !isDraftMode && recordQuery.isLoading ? <div>Lade Datensatz...</div> : null}
                  {selectedUid && !isDraftMode && recordQuery.isError ? (
                    <div style={{ color: 'crimson' }}>
                      Fehler: {(recordQuery.error as any)?.message || 'Datensatz konnte nicht geladen werden'}
                    </div>
                  ) : null}

                  {(selectedUid || isDraftMode) && currentDaten ? (
                    <div>
                      {!isImportEditor && editType !== 'edit_json' && editType !== 'show_json' ? (
                        <>
                          <div style={{ marginBottom: 8, fontSize: 12, opacity: 0.8 }}>
                            UID: <span style={{ fontFamily: 'monospace' }}>{isDraftMode ? activeDraft?.draft_id : recordQuery.data?.uid}</span>
                          </div>
                          <div style={{ marginBottom: 8, fontSize: 12, opacity: 0.8 }}>
                            Name: <span style={{ fontFamily: 'monospace' }}>{currentName}</span>
                          </div>
                        </>
                      ) : null}

                      {editType === 'edit_json' ? (
                        <div className="pdvm-dialog__jsonEditorWrap">
                          <div
                            className="pdvm-dialog__jsonToolbar"
                            style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', marginBottom: 8 }}
                          >
                            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                              <button
                                type="button"
                                onClick={() => {
                                  setJsonMode('text')
                                  jsonEditorRef.current?.setMode('text')
                                  updateMutation.reset()
                                  commitDraftMutation.reset()
                                }}
                                disabled={updateMutation.isPending}
                                className={`pdvm-dialog__toolBtn ${jsonMode === 'text' ? 'pdvm-dialog__toolBtn--active' : ''}`.trim()}
                                title="Textmodus (Code)"
                                aria-label="Textmodus (Code)"
                              >
                                Text
                              </button>
                              <button
                                type="button"
                                onClick={() => {
                                  setJsonMode('tree')
                                  jsonEditorRef.current?.setMode('tree')
                                  updateMutation.reset()
                                  commitDraftMutation.reset()
                                }}
                                disabled={updateMutation.isPending}
                                className={`pdvm-dialog__toolBtn ${jsonMode === 'tree' ? 'pdvm-dialog__toolBtn--active' : ''}`.trim()}
                                title="Baumansicht (strukturierter Editor)"
                                aria-label="Baumansicht"
                              >
                                Baum
                              </button>
                            </div>

                            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                              <button
                                type="button"
                                onClick={() => jsonEditorRef.current?.expandAll()}
                                disabled={updateMutation.isPending || createMutation.isPending || commitDraftMutation.isPending}
                                className="pdvm-dialog__toolBtn"
                                title="Alle Knoten aufklappen"
                                aria-label="Alle Knoten aufklappen"
                              >
                                Alle auf
                              </button>
                              <button
                                type="button"
                                onClick={() => jsonEditorRef.current?.collapseAll()}
                                disabled={updateMutation.isPending || createMutation.isPending || commitDraftMutation.isPending}
                                className="pdvm-dialog__toolBtn"
                                title="Alle Knoten einklappen"
                                aria-label="Alle Knoten einklappen"
                              >
                                Alle zu
                              </button>
                              <button
                                type="button"
                                onClick={() => {
                                  jsonEditorRef.current?.sort()
                                  updateMutation.reset()
                                  commitDraftMutation.reset()
                                }}
                                disabled={updateMutation.isPending || createMutation.isPending || commitDraftMutation.isPending}
                                className="pdvm-dialog__toolBtn"
                                title="Objekt-Schlüssel sortieren (A–Z)"
                                aria-label="Objekt-Schlüssel sortieren"
                              >
                                Sortieren
                              </button>
                              <button
                                type="button"
                                onClick={formatJson}
                                disabled={updateMutation.isPending || createMutation.isPending || commitDraftMutation.isPending}
                                className="pdvm-dialog__toolBtn"
                                title="JSON formatieren (Pretty Print)"
                                aria-label="JSON formatieren"
                              >
                                Formatieren
                              </button>
                            </div>

                            <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginLeft: 'auto' }}>
                              <input
                                ref={jsonSearchInputRef}
                                value={jsonSearch}
                                onChange={(e) => {
                                  setJsonSearch(e.target.value)
                                  setJsonSearchHits(null)
                                  updateMutation.reset()
                                  commitDraftMutation.reset()
                                }}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter') {
                                    // Important: prevent the key event from reaching the editor
                                    // (Ace can have an active selection from the last search)
                                    e.preventDefault()
                                    e.stopPropagation()
                                    doSearch()
                                  }
                                }}
                                placeholder="Suchen…"
                                spellCheck={false}
                                className="pdvm-dialog__toolInput"
                                title="Suchen (Enter)"
                                aria-label="Suchen"
                              />
                              <button
                                type="button"
                                onClick={doSearch}
                                disabled={updateMutation.isPending || createMutation.isPending || commitDraftMutation.isPending}
                                className="pdvm-dialog__toolBtn"
                                title="Suchen"
                                aria-label="Suchen"
                              >
                                Suchen
                              </button>
                              {jsonSearchHits != null ? (
                                <span style={{ fontSize: 12, opacity: 0.8 }}>{jsonSearchHits} Treffer</span>
                              ) : null}
                            </div>

                            <button
                              type="button"
                              onClick={saveJson}
                              disabled={updateMutation.isPending || createMutation.isPending || commitDraftMutation.isPending || !!jsonError}
                              className="pdvm-dialog__toolBtn pdvm-dialog__toolBtn--primary"
                              title="Speichern"
                              aria-label="Speichern"
                            >
                              Speichern
                            </button>

                            {jsonDirty && !updateMutation.isPending ? (
                              <div style={{ fontSize: 12, opacity: 0.8 }}>Änderungen…</div>
                            ) : null}
                            {createMutation.isPending ? <div style={{ fontSize: 12, opacity: 0.8 }}>Erstelle...</div> : null}
                            {updateMutation.isPending ? <div style={{ fontSize: 12, opacity: 0.8 }}>Speichere...</div> : null}
                            {commitDraftMutation.isPending ? <div style={{ fontSize: 12, opacity: 0.8 }}>Lege Satz an...</div> : null}
                            {updateMutation.isSuccess ? <div style={{ fontSize: 12, opacity: 0.8 }}>Gespeichert</div> : null}
                            {commitDraftMutation.isSuccess ? <div style={{ fontSize: 12, opacity: 0.8 }}>Satz angelegt</div> : null}
                            {createMutation.isError ? (
                              <div style={{ fontSize: 12, color: 'crimson' }}>
                                Fehler: {(createMutation.error as any)?.message || 'Erstellen fehlgeschlagen'}
                              </div>
                            ) : null}
                            {updateMutation.isError ? (
                              <div style={{ fontSize: 12, color: 'crimson' }}>
                                Fehler: {(updateMutation.error as any)?.message || 'Speichern fehlgeschlagen'}
                              </div>
                            ) : null}
                            {commitDraftMutation.isError ? (
                              <div style={{ fontSize: 12, color: 'crimson' }}>
                                Fehler: {(commitDraftMutation.error as any)?.response?.data?.detail?.message || (commitDraftMutation.error as any)?.message || 'Satz anlegen fehlgeschlagen'}
                              </div>
                            ) : null}
                          </div>

                          {jsonError ? (
                            <div style={{ marginBottom: 8, color: 'crimson', fontSize: 12 }}>JSON Fehler: {jsonError}</div>
                          ) : null}

                          <PdvmJsonEditor
                            ref={jsonEditorRef as any}
                            initialMode={jsonMode}
                            initialJson={currentDaten}
                            onDirty={() => {
                              setJsonDirty(true)
                              updateMutation.reset()
                              commitDraftMutation.reset()
                            }}
                            onFocus={() => {
                              // Clicking into the editor should hide the stale "Gespeichert" indicator.
                              updateMutation.reset()
                              commitDraftMutation.reset()
                            }}
                            onValidationMessage={(msg) => setJsonError(msg)}
                          />
                        </div>
                      ) : isFieldEditor ? (
                        <div className="pdvm-dialog__editUser">
                          {effectivePicTabs.items.length > 1 ? (
                            <div className="pdvm-tabs pdvm-tabs--sticky pdvm-dialog__editUserTabs">
                              <div className="pdvm-tabs__bar">
                                <div className="pdvm-tabs__list" role="tablist" aria-label="Edit Tabs">
                                  {effectivePicTabs.items.map((t) => (
                                    <button
                                      key={t.index}
                                      type="button"
                                      role="tab"
                                      aria-selected={picActiveTab === t.index}
                                      className={`pdvm-tabs__tab ${picActiveTab === t.index ? 'pdvm-tabs__tab--active' : ''}`}
                                      onClick={() => setPicActiveTab(t.index)}
                                    >
                                      {t.head}
                                    </button>
                                  ))}
                                </div>
                              </div>
                            </div>
                          ) : null}

                          <div className="pdvm-dialog__editUserContent">
                            {effectivePicDefs.length === 0 ? (
                              <div style={{ opacity: 0.75 }}>Keine FIELDS im Frame definiert.</div>
                            ) : null}

                            <div style={{ display: 'grid', gap: 12 }}>
                              {uiPicDefs
                                .filter((d) => Number(d.tab || 1) === picActiveTab)
                                .map((d) => {
                                  const gruppe = String(d.gruppe || '').trim()
                                  const feld = String(d.feld || '').trim()
                                  if (!gruppe || !feld) return null

                                  const current = picDraft ? picDraft : currentDaten || {}
                                  const rawValue = getFieldValue(current, gruppe, feld)
                                  const type = normalizePicType(d.type)
                                  const fieldKey = String(d.key || `${gruppe}.${feld}`)
                                  const validationKey = `${gruppe}.${feld}`
                                  const validationMessage = draftErrorByField[validationKey]
                                  const options = dropdownOptionsByFieldKey[fieldKey] || []

                                  const onChange = (value: any) => {
                                    setPicDraft((prev) => {
                                      const base = prev || (currentDaten || {})
                                      return setFieldValue(base, gruppe, feld, value)
                                    })
                                    setPicDirty(true)
                                  }

                                  if (type === 'go_select_view') {
                                    const lookupTable = String(d.configs?.viewtable || d.configs?.table || '').trim()
                                    const fallbackTable = feld.endsWith('.MENU') ? 'sys_menudaten' : ''
                                    const effectiveTable = lookupTable || fallbackTable
                                    return (
                                      <div key={fieldKey} className="pdvm-pic" title={d.tooltip || undefined}>
                                        <div className="pdvm-pic__labelRow">
                                          <label className="pdvm-pic__label">{d.label || d.name || feld}</label>
                                        </div>
                                        <div className="pdvm-pic__control">
                                          <PdvmLookupSelect
                                            table={effectiveTable}
                                            value={rawValue ? String(rawValue) : null}
                                            onChange={(v) => onChange(v)}
                                            disabled={!!d.read_only}
                                          />
                                        </div>
                                      </div>
                                    )
                                  }

                                  if (type === 'action') {
                                    return (
                                      <div key={fieldKey} className="pdvm-pic" title={d.tooltip || undefined}>
                                        <div className="pdvm-pic__labelRow">
                                          <label className="pdvm-pic__label">{d.label || d.name || feld}</label>
                                        </div>
                                        <div className="pdvm-pic__control">
                                          <button type="button" className="pdvm-dialog__toolBtn" disabled={!!d.read_only}>
                                            {d.label || d.name || feld}
                                          </button>
                                        </div>
                                      </div>
                                    )
                                  }

                                  return (
                                    <PdvmInputControl
                                      key={fieldKey}
                                      label={d.label || d.name || feld}
                                      tooltip={d.tooltip}
                                      type={type === 'multi_dropdown' ? 'multi_dropdown' : (type as any)}
                                      value={rawValue}
                                      onChange={onChange}
                                      readOnly={!!d.read_only}
                                      options={options}
                                      helpText={validationMessage ? `${validationMessage}${d.tooltip ? ` · ${d.tooltip}` : ''}` : (d.tooltip || '')}
                                      controlDebug={{
                                        field_key: fieldKey,
                                        gruppe,
                                        feld,
                                        pic_def: d,
                                        resolved_control: resolvedControlByGroupField[`${gruppe.toUpperCase()}::${feld.toUpperCase()}`] || null,
                                      }}
                                    />
                                  )
                                })}
                            </div>
                          </div>
                        </div>
                      ) : isImportEditor ? (
                        <PdvmImportDataEditor
                          tableName={effectiveDialogTable}
                          datasetUid={selectedUid}
                          onApplied={handleImportApplied}
                          step={importStep}
                          onStepChange={setImportStep}
                          hideSteps
                        />
                      ) : (
                        <pre
                          style={{
                            whiteSpace: 'pre-wrap',
                            background: '#0b1020',
                            color: '#d6deeb',
                            padding: 12,
                            borderRadius: 8,
                            fontSize: 12,
                            lineHeight: 1.4,
                            overflowX: 'auto',
                          }}
                        >
                          {safeJsonPretty(currentDaten)}
                        </pre>
                      )}
                    </div>
                  ) : null}
                </div>
                </>
              )}
            </div>
          ) : activeModuleType === 'acti' ? (
            <div style={{ padding: 12 }}>
              <div style={{ fontSize: 12, opacity: 0.8, marginBottom: 8 }}>Aktionen-Modul (work/acti)</div>
              <div style={{ fontSize: 12, opacity: 0.8 }}>Ausgewaehlt: {selectedUids.length || (selectedUid ? 1 : 0)}</div>
            </div>
          ) : null}
          </div>
        </div>
      </div>
    </div>
  )
}
