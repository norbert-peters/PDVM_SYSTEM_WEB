import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  dialogsAPI,
  systemdatenAPI,
  usersAPI,
  type DialogRow,
  type DialogDefinitionResponse,
  type DialogRecordResponse,
  type DialogUiStateResponse,
} from '../../api/client'
import { PdvmViewPageContent } from '../views/PdvmViewPage'
import { PdvmMenuEditor } from './PdvmMenuEditor'
import { PdvmJsonEditor, type PdvmJsonEditorHandle, type PdvmJsonEditorMode } from '../common/PdvmJsonEditor'
import { PdvmDialogModal } from '../common/PdvmDialogModal'
import { PdvmInputControl, type PdvmDropdownOption } from '../common/PdvmInputControl'
import { PdvmLookupSelect } from '../common/PdvmLookupSelect'
import '../../styles/components/dialog.css'

type ActiveTab = 'view' | 'edit'

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

function normalizePicType(value: any): 'string' | 'text' | 'dropdown' | 'multi_dropdown' | 'true_false' | 'go_select_view' | 'action' {
  const t = String(value || '').trim().toLowerCase()
  if (t === 'text') return 'text'
  if (t === 'dropdown') return 'dropdown'
  if (t === 'multi_dropdown') return 'multi_dropdown'
  if (t === 'true_false' || t === 'bool' || t === 'boolean') return 'true_false'
  if (t === 'go_select_view' || t === 'selected_view' || t === 'lookup') return 'go_select_view'
  if (t === 'action') return 'action'
  return 'string'
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
  const groupObj = asObject(daten[gruppe])
  if (!feld.includes('.')) return groupObj[feld]
  return feld.split('.').reduce((acc: any, part: string) => {
    if (!acc || typeof acc !== 'object') return undefined
    return acc[part]
  }, groupObj as any)
}

function setFieldValue(daten: Record<string, any>, gruppe: string, feld: string, value: any) {
  const out = { ...daten }
  const groupObj = asObject(out[gruppe])
  if (!feld.includes('.')) {
    out[gruppe] = { ...groupObj, [feld]: value }
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
  out[gruppe] = root
  return out
}

export default function PdvmDialogPage() {
  const { dialogGuid } = useParams<{ dialogGuid: string }>()
  const [searchParams] = useSearchParams()
  const dialogTable = (searchParams.get('dialog_table') || '').trim() || null
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState<ActiveTab>('view')
  const [pageOffset, setPageOffset] = useState(0)
  const pageLimit = 200

  const [selectedUid, setSelectedUid] = useState<string | null>(null)
  const [selectedUids, setSelectedUids] = useState<string[]>([])
  const ignoredAutoLastCallUidRef = useRef<string>('')
  const [autoLastCallError, setAutoLastCallError] = useState<string | null>(null)
  const suppressPersistRef = useRef<boolean>(true)

  // Avoid writing last_call for a new dialog_table using an old selection.
  const lastPersistContextKeyRef = useRef<string>('')

  const defQuery = useQuery<DialogDefinitionResponse>({
    queryKey: ['dialog', 'definition', dialogGuid, dialogTable],
    queryFn: () => dialogsAPI.getDefinition(dialogGuid!, { dialog_table: dialogTable }),
    enabled: !!dialogGuid,
  })

  const lastCallScopeKey = useMemo(() => {
    const vg = String(defQuery.data?.view_guid || '').trim()
    const rt = String(defQuery.data?.root_table || defQuery.data?.root?.TABLE || '').trim()
    return vg && rt ? `${vg}::${rt}` : ''
  }, [defQuery.data?.view_guid, defQuery.data?.root_table, defQuery.data?.root])

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
    setActiveTab('view')
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
    setMenuEditorRefreshToken(0)
    setRefreshModalOpen(false)

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
  const editType = String(defQuery.data?.edit_type || 'show_json').trim().toLowerCase()
  const wantsMenuEditor = editType === 'menu'
  const hasEmbeddedView = !!String(defQuery.data?.view_guid || '').trim()
  const isSysMenuTable = String(defQuery.data?.root_table || '').trim().toLowerCase() === 'sys_menudaten'

  // If the dialog embeds a View (by view_guid), keep selection in sync by listening
  // to the global selection event emitted by PdvmViewPage.
  useEffect(() => {
    const viewGuid = String(defQuery.data?.view_guid || '').trim()
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
        setActiveTab('edit')
      }
    }

    window.addEventListener('pdvm:view-selection-changed', handler as any)
    return () => window.removeEventListener('pdvm:view-selection-changed', handler as any)
  }, [defQuery.data?.view_guid, openEditMode])

  // OPEN_EDIT=double_click: listen to the View activation event.
  useEffect(() => {
    const viewGuid = String(defQuery.data?.view_guid || '').trim()
    if (!viewGuid) return
    if (openEditMode !== 'double_click') return

    const handler = (ev: Event) => {
      const detail = (ev as any)?.detail || null
      if (!detail || String(detail.view_guid || '').trim() !== viewGuid) return
      const uid = String(detail.uid || '').trim()
      if (!uid) return

      setSelectedUid(uid)
      setSelectedUids([uid])
      setActiveTab('edit')
    }

    window.addEventListener('pdvm:view-row-activated', handler as any)
    return () => window.removeEventListener('pdvm:view-row-activated', handler as any)
  }, [defQuery.data?.view_guid, openEditMode])

  const menuGuid = useMemo(() => {
    const root = (defQuery.data?.root || {}) as Record<string, any>
    const keys = Object.keys(root)
    const k = keys.find((x) => String(x).trim().toLowerCase() === 'menu_guid')
    const v = k ? root[k] : null
    const s = v != null ? String(v).trim() : ''
    return s || null
  }, [defQuery.data?.root])

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
  const frameDaten = (defQuery.data?.frame?.daten || null) as Record<string, any> | null
  const frameRoot = (defQuery.data?.frame?.root || {}) as Record<string, any>

  const picDefs = useMemo(() => extractPicDefs(frameDaten), [frameDaten])

  const picTabs = useMemo(() => {
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

    let items: Array<{ index: number; head: string }> = []
    const maxTabs = Math.max(1, Math.min(10, tabs || 1))
    for (let i = 1; i <= maxTabs; i++) {
      const block = pickTabBlock(i)
      const head = String((block as any)?.HEAD ?? (block as any)?.head ?? '').trim() || `Tab ${i}`
      items.push({ index: i, head })
    }

    if (isPicEditor) {
      items = items.filter((t) => t.index !== 5)
    }

    return { tabs: items.length, items }
  }, [frameRoot, isPicEditor])

  const [picActiveTab, setPicActiveTab] = useState(1)
  const [picDraft, setPicDraft] = useState<Record<string, any> | null>(null)
  const [picDirty, setPicDirty] = useState(false)

  useEffect(() => {
    if (!picTabs.items.length) return
    const allowed = new Set(picTabs.items.map((t) => t.index))
    if (!allowed.has(picActiveTab)) {
      setPicActiveTab(picTabs.items[0].index)
    }
  }, [picTabs.items, picActiveTab])

  const rowsQuery = useQuery<{ dialog_guid: string; table: string; rows: DialogRow[] }>({
    queryKey: ['dialog', 'rows', dialogGuid, dialogTable, pageLimit, pageOffset],
    queryFn: () => dialogsAPI.postRows(dialogGuid!, { limit: pageLimit, offset: pageOffset }, { dialog_table: dialogTable }),
    enabled: !!dialogGuid && defQuery.isSuccess && !defQuery.data?.view_guid,
  })

  const recordQuery = useQuery<DialogRecordResponse>({
    queryKey: ['dialog', 'record', dialogGuid, dialogTable, selectedUid],
    queryFn: () => dialogsAPI.getRecord(dialogGuid!, selectedUid!, { dialog_table: dialogTable }),
    enabled: !!dialogGuid && !!selectedUid && !isMenuEditor,
  })



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
    setActiveTab('edit')
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
    setActiveTab('view')

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
    if (!recordQuery.data) return
    if (editType !== 'edit_json') return

    try {
      jsonEditorRef.current?.setJson(recordQuery.data.daten)
      jsonEditorRef.current?.setMode(jsonMode)
      setJsonError(null)
      setJsonDirty(false)
      setJsonSearchHits(null)
    } catch (e: any) {
      setJsonError(e?.message || 'Editor konnte JSON nicht laden')
    }
  }, [recordQuery.data?.uid, recordQuery.data?.modified_at, editType, jsonMode])

  useEffect(() => {
    if (!recordQuery.data) return
    if (!isPicEditor) return
    setPicDraft(recordQuery.data.daten || {})
    setPicDirty(false)
  }, [recordQuery.data?.uid, recordQuery.data?.modified_at, isPicEditor])

  useEffect(() => {
    if (!isPicEditor) return
    setPicActiveTab(1)
  }, [selectedUid, isPicEditor])

  const updateMutation = useMutation({
    mutationFn: async (nextJson: Record<string, any>) => {
      return dialogsAPI.updateRecord(dialogGuid!, selectedUid!, { daten: nextJson }, { dialog_table: dialogTable })
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['dialog', 'record', dialogGuid, dialogTable, selectedUid] })
    },
  })

  const createMutation = useMutation({
    mutationFn: async (payload: { name: string; is_template?: boolean }) => {
      return dialogsAPI.createRecord(
        dialogGuid!,
        {
          name: payload.name,
          // Default: PDVM template record (fiktive GUID)
          template_uid: '66666666-6666-6666-6666-666666666666',
          is_template: payload.is_template,
        },
        { dialog_table: dialogTable }
      )
    },
    onSuccess: async (created) => {
      // Refresh list and open the new record.
      await queryClient.invalidateQueries({ queryKey: ['dialog', 'rows', dialogGuid, dialogTable] })

      const embeddedViewGuid = String(defQuery.data?.view_guid || '').trim()
      if (embeddedViewGuid) {
        // Best-effort: refresh embedded View so the new row becomes visible.
        await queryClient.invalidateQueries({ queryKey: ['view', 'matrix', embeddedViewGuid] })
      }

      setSelectedUid(created.uid)
      setSelectedUids([created.uid])
      setActiveTab('edit')
      setJsonDirty(false)
      setJsonSearchHits(null)
    },
  })

  const createNewRecord = async () => {
    if (!dialogGuid) return

    setCreateModalError(null)
    setCreateModalOpen(true)
  }

  const saveJson = async () => {
    if (editType !== 'edit_json') return
    if (!dialogGuid || !selectedUid) return

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
    await updateMutation.mutateAsync(parsed)
    setJsonDirty(false)
  }

  const savePic = async () => {
    if (!isPicEditor) return
    if (!dialogGuid || !selectedUid || !picDraft) return
    await updateMutation.mutateAsync(picDraft)
    setPicDirty(false)
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

  const tabs = Math.max(2, Number(defQuery.data?.meta?.tabs || 2))

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

    const t1 = getHead(1)
    const t2 = getHead(2)
    return {
      tab1: t1 || 'Tab 1: View',
      tab2: t2 || 'Tab 2: Edit',
    }
  }, [defQuery.data?.daten, defQuery.data?.root])

  const dropdownFieldConfigs = useMemo(() => {
    if (!isPicEditor) return [] as Array<{ fieldKey: string; table: string; datasetUid: string; field: string }>
    const out: Array<{ fieldKey: string; table: string; datasetUid: string; field: string }> = []
    picDefs.forEach((def) => {
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
  }, [isPicEditor, picDefs])

  const dropdownQueries = useQueries({
    queries: dropdownFieldConfigs.map((cfg) => ({
      queryKey: ['systemdaten', 'dropdown', cfg.table, cfg.datasetUid, cfg.field],
      queryFn: () => systemdatenAPI.getDropdown({ table: cfg.table, dataset_uid: cfg.datasetUid, field: cfg.field }),
      enabled: isPicEditor && !!cfg.table && !!cfg.datasetUid && !!cfg.field,
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
    setActiveTab('view')
    dialogsAPI.putLastCall(dialogGuid, null, { dialog_table: dialogTable }).catch(() => {
      // Best-effort persistence only.
    })
    queryClient.invalidateQueries({ queryKey: ['dialog', 'definition', dialogGuid, dialogTable] }).catch(() => {
      // Best-effort refresh only.
    })
  }

  const performRefreshEdit = async () => {
    if (!dialogGuid) return
    if (!selectedUid) return

    setAutoLastCallError(null)

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
  }

  const refreshEdit = async () => {
    if (activeTab !== 'edit') return
    if ((editType === 'edit_json' && jsonDirty) || (isPicEditor && picDirty)) {
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
        busy={updateMutation.isPending || createMutation.isPending}
        onCancel={() => {
          setDiscardModalOpen(false)
          setPendingTab(null)
        }}
        onConfirm={() => {
          // Best-effort: reset editor content to last loaded record state.
          try {
            if (recordQuery.data?.daten && editType === 'edit_json') {
              jsonEditorRef.current?.setJson(recordQuery.data.daten)
              jsonEditorRef.current?.setMode(jsonMode)
            }
          } catch {
            // ignore
          }

          if (recordQuery.data?.daten && isPicEditor) {
            setPicDraft(recordQuery.data.daten)
            setPicDirty(false)
          }

          setJsonError(null)
          setJsonDirty(false)
          setJsonSearchHits(null)
          updateMutation.reset()

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
        busy={updateMutation.isPending || createMutation.isPending}
        onCancel={() => setRefreshModalOpen(false)}
        onConfirm={async () => {
          setRefreshModalOpen(false)
          await performRefreshEdit()
        }}
      />

      <PdvmDialogModal
        open={createModalOpen}
        kind="form"
        title="Neuer Datensatz"
        message={isSysMenuTable ? 'Bitte Name und Menü-Typ auswählen.' : 'Bitte Name eingeben (Template: 6666...).'}
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
        busy={createMutation.isPending || updateMutation.isPending}
        error={createModalError}
        onCancel={() => {
          if (createMutation.isPending || updateMutation.isPending) return
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
            <button
              type="button"
              onClick={() => {
                refreshEdit().catch(() => {
                  // ignore
                })
              }}
              disabled={!selectedUid || activeTab !== 'edit' || createMutation.isPending || updateMutation.isPending}
              className="pdvm-dialog__toolBtn"
              title="Editbereich aus DB neu laden"
              aria-label="Refresh Edit"
            >
              Refresh Edit
            </button>

            {isPicEditor && activeTab === 'edit' ? (
              <button
                type="button"
                onClick={() => {
                  savePic().catch(() => {
                    // ignore
                  })
                }}
                disabled={!picDirty || !selectedUid || activeTab !== 'edit' || createMutation.isPending || updateMutation.isPending}
                className="pdvm-dialog__toolBtn"
                title="Änderungen speichern"
                aria-label="Speichern"
              >
                Speichern
              </button>
            ) : null}

            {activeTab === 'view' ? (
              <button
                type="button"
                onClick={createNewRecord}
                disabled={createMutation.isPending || updateMutation.isPending}
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
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'view'}
              className={`pdvm-tabs__tab ${activeTab === 'view' ? 'pdvm-tabs__tab--active' : ''}`}
                onClick={() => {
                    if (activeTab === 'edit' && ((editType === 'edit_json' && jsonDirty) || (isPicEditor && picDirty))) {
                    setPendingTab('view')
                    setDiscardModalOpen(true)
                    return
                  }
                  setActiveTab('view')
                }}
            >
              {tabLabel.tab1}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'edit'}
              className={`pdvm-tabs__tab ${activeTab === 'edit' ? 'pdvm-tabs__tab--active' : ''}`}
                onClick={() => setActiveTab('edit')}
            >
              {tabLabel.tab2}
            </button>
          </div>

          <div className="pdvm-tabs__actions">
            <div className="pdvm-tabs__meta">Tabs (config): {tabs}</div>
          </div>
        </div>

        <div className="pdvm-tabs__panel pdvm-dialog__panel">
          <div
            className={`pdvm-dialog__panelScroll ${activeTab === 'view' && hasEmbeddedView ? 'pdvm-dialog__panelScroll--noScroll' : ''} ${activeTab === 'edit' ? 'pdvm-dialog__panelScroll--noScroll' : ''}`}
          >
          {/* edit_type=menu nutzt Auswahl im View-Tab; ROOT.MENU_GUID ist optional (Preselect) */}

          {autoLastCallError ? (
            <div style={{ marginBottom: 10, color: 'goldenrod', fontSize: 12 }}>{autoLastCallError}</div>
          ) : null}

          {activeTab === 'view' ? (
            <div className="pdvm-dialog__view">
              {defQuery.data?.view_guid ? (
                <PdvmViewPageContent
                  viewGuid={String(defQuery.data.view_guid)}
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
                                  setActiveTab('edit')
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

          {activeTab === 'edit' ? (
            <div className="pdvm-dialog__editArea">
              {isMenuEditor ? (
                <div className="pdvm-dialog__editAreaContent">
                  {!selectedUid ? <div>Kein Menüdatensatz ausgewählt. Bitte zuerst im View-Tab auswählen.</div> : null}

                  {selectedUid ? (
                    <div>
                      <div style={{ marginBottom: 10, fontSize: 12, opacity: 0.8 }}>
                        Menü UID: <span style={{ fontFamily: 'monospace' }}>{selectedUid}</span>
                      </div>

                      {menuEditTabs.tabs >= 2 && menuEditTabs.items.length >= 2 ? (
                        <div className="pdvm-tabs pdvm-tabs--sticky" style={{ marginBottom: 10 }}>
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
              ) : isPicEditor ? (
                <>
                  <div className="pdvm-dialog__editAreaHeader">
                    {recordQuery.data ? (
                      <div style={{ marginBottom: 10, display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' }}>
                        <div style={{ fontSize: 12, opacity: 0.75 }}>
                          Passwortwechsel erforderlich:{' '}
                          <strong>{String((recordQuery.data.daten?.SECURITY as any)?.PASSWORD_CHANGE_REQUIRED ? 'JA' : 'NEIN')}</strong>
                        </div>
                        <div style={{ fontSize: 12, opacity: 0.75 }}>
                          Account gesperrt:{' '}
                          <strong>{String((recordQuery.data.daten?.SECURITY as any)?.ACCOUNT_LOCKED ? 'JA' : 'NEIN')}</strong>
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
                          {((recordQuery.data.daten?.SECURITY as any)?.ACCOUNT_LOCKED ? true : false) ? (
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
                    {picTabs.items.length > 1 ? (
                      <div className="pdvm-tabs pdvm-tabs--sticky pdvm-dialog__editUserTabs">
                        <div className="pdvm-tabs__bar">
                          <div className="pdvm-tabs__list" role="tablist" aria-label="Edit Tabs">
                            {picTabs.items.map((t) => (
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
                    {picDefs.length === 0 ? (
                      <div style={{ opacity: 0.75 }}>Keine FIELDS im Frame definiert.</div>
                    ) : null}

                    <div style={{ display: 'grid', gap: 12 }}>
                      {picDefs
                        .filter((d) => Number(d.tab || 1) === picActiveTab)
                        .map((d) => {
                          const gruppe = String(d.gruppe || '').trim()
                          const feld = String(d.feld || '').trim()
                          if (!gruppe || !feld) return null

                          const current = picDraft ? picDraft : recordQuery.data?.daten || {}
                          const rawValue = getFieldValue(current, gruppe, feld)
                          const type = normalizePicType(d.type)
                          const fieldKey = String(d.key || `${gruppe}.${feld}`)
                          const options = dropdownOptionsByFieldKey[fieldKey] || []

                          const onChange = (value: any) => {
                            setPicDraft((prev) => {
                              const base = prev || (recordQuery.data?.daten || {})
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
                              helpText={d.tooltip || ''}
                            />
                          )
                        })}
                    </div>
                  </div>
                </>
              ) : (
                <div className="pdvm-dialog__editAreaContent">
                  <div style={{ fontSize: 12, opacity: 0.8, marginBottom: 8 }}>
                    EditType: <span style={{ fontFamily: 'monospace' }}>{defQuery.data?.edit_type || 'show_json'}</span>
                  </div>

                  {!selectedUid ? <div>Kein Datensatz ausgewählt. Bitte zuerst im View-Tab auswählen.</div> : null}

                  {selectedUid && recordQuery.isLoading ? <div>Lade Datensatz...</div> : null}
                  {selectedUid && recordQuery.isError ? (
                    <div style={{ color: 'crimson' }}>
                      Fehler: {(recordQuery.error as any)?.message || 'Datensatz konnte nicht geladen werden'}
                    </div>
                  ) : null}

                  {selectedUid && recordQuery.data ? (
                    <div>
                      <div style={{ marginBottom: 8, fontSize: 12, opacity: 0.8 }}>
                        UID: <span style={{ fontFamily: 'monospace' }}>{recordQuery.data.uid}</span>
                      </div>
                      <div style={{ marginBottom: 8, fontSize: 12, opacity: 0.8 }}>
                        Name: <span style={{ fontFamily: 'monospace' }}>{recordQuery.data.name}</span>
                      </div>

                      {editType === 'edit_json' ? (
                        <div>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', marginBottom: 8 }}>
                            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                              <button
                                type="button"
                                onClick={() => {
                                  setJsonMode('text')
                                  jsonEditorRef.current?.setMode('text')
                                  updateMutation.reset()
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
                                disabled={updateMutation.isPending || createMutation.isPending}
                                className="pdvm-dialog__toolBtn"
                                title="Alle Knoten aufklappen"
                                aria-label="Alle Knoten aufklappen"
                              >
                                Alle auf
                              </button>
                              <button
                                type="button"
                                onClick={() => jsonEditorRef.current?.collapseAll()}
                                disabled={updateMutation.isPending || createMutation.isPending}
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
                                }}
                                disabled={updateMutation.isPending || createMutation.isPending}
                                className="pdvm-dialog__toolBtn"
                                title="Objekt-Schlüssel sortieren (A–Z)"
                                aria-label="Objekt-Schlüssel sortieren"
                              >
                                Sortieren
                              </button>
                              <button
                                type="button"
                                onClick={formatJson}
                                disabled={updateMutation.isPending || createMutation.isPending}
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
                                disabled={updateMutation.isPending || createMutation.isPending}
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
                              disabled={updateMutation.isPending || createMutation.isPending || !!jsonError}
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
                            {updateMutation.isSuccess ? <div style={{ fontSize: 12, opacity: 0.8 }}>Gespeichert</div> : null}
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
                          </div>

                          {jsonError ? (
                            <div style={{ marginBottom: 8, color: 'crimson', fontSize: 12 }}>JSON Fehler: {jsonError}</div>
                          ) : null}

                          <PdvmJsonEditor
                            ref={jsonEditorRef as any}
                            initialMode={jsonMode}
                            initialJson={recordQuery.data?.daten}
                            onDirty={() => {
                              setJsonDirty(true)
                              updateMutation.reset()
                            }}
                            onFocus={() => {
                              // Clicking into the editor should hide the stale "Gespeichert" indicator.
                              updateMutation.reset()
                            }}
                            onValidationMessage={(msg) => setJsonError(msg)}
                          />
                        </div>
                      ) : isPicEditor ? (
                        <div className="pdvm-dialog__editUser">
                          {picTabs.items.length > 1 ? (
                            <div className="pdvm-tabs pdvm-tabs--sticky pdvm-dialog__editUserTabs">
                              <div className="pdvm-tabs__bar">
                                <div className="pdvm-tabs__list" role="tablist" aria-label="Edit Tabs">
                                  {picTabs.items.map((t) => (
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
                            {picDefs.length === 0 ? (
                              <div style={{ opacity: 0.75 }}>Keine FIELDS im Frame definiert.</div>
                            ) : null}

                            <div style={{ display: 'grid', gap: 12 }}>
                              {picDefs
                                .filter((d) => Number(d.tab || 1) === picActiveTab)
                                .map((d) => {
                                  const gruppe = String(d.gruppe || '').trim()
                                  const feld = String(d.feld || '').trim()
                                  if (!gruppe || !feld) return null

                                  const current = picDraft ? picDraft : recordQuery.data?.daten || {}
                                  const rawValue = getFieldValue(current, gruppe, feld)
                                  const type = normalizePicType(d.type)
                                  const fieldKey = String(d.key || `${gruppe}.${feld}`)
                                  const options = dropdownOptionsByFieldKey[fieldKey] || []

                                  const onChange = (value: any) => {
                                    setPicDraft((prev) => {
                                      const base = prev || (recordQuery.data?.daten || {})
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
                                      helpText={d.tooltip || ''}
                                    />
                                  )
                                })}
                            </div>
                          </div>
                        </div>
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
                          {safeJsonPretty(recordQuery.data.daten)}
                        </pre>
                      )}
                    </div>
                  ) : null}
                </div>
              )}
            </div>
          ) : null}
          </div>
        </div>
      </div>
    </div>
  )
}
