import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  viewsAPI,
  type ViewBaseRow,
  type ViewDefinitionResponse,
  type ViewStateResponse,
  type ViewMatrixRow,
  type ViewMatrixResponse,
} from '../../api/client'
import { formatPdvmDateDE } from '../../utils/pdvmDateTime'

import './PdvmViewPage.css'

type SortDirection = 'asc' | 'desc' | null
type TableState = {
  sort: { control_guid: string | null; direction: SortDirection }
  filters: Record<string, string>
  group: { enabled: boolean; by: string | null; sum_control_guid: string | null }
}

type RenderRow =
  | { kind: 'group'; key: string; label: string; count: number; sum: number | null }
  | { kind: 'data'; row: ViewBaseRow; baseIndex: number }

type ViewControl = {
  control_guid: string
  gruppe: string
  feld: string
  label?: string
  type?: string
  control_type?: string
  show?: boolean
  display_order?: number
  width?: number
  sortable?: boolean
  searchable?: boolean
  configs?: any
}

function fallbackUidNameControls(): ViewControl[] {
  return [
    {
      control_guid: '__system_uid',
      gruppe: 'SYSTEM',
      feld: 'uid',
      label: 'UID',
      type: 'string',
      show: true,
      display_order: 0,
      sortable: false,
      searchable: false,
    },
    {
      control_guid: '__system_name',
      gruppe: 'SYSTEM',
      feld: 'name',
      label: 'Name',
      type: 'string',
      show: true,
      display_order: 1,
      sortable: false,
      searchable: false,
    },
  ]
}

function isPlainObject(value: unknown): value is Record<string, any> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}


function resolveFormatType(control: ViewControl): string {
  const t = String(control.type || '').trim().toLowerCase()
  if (t) return t

  // Compatibility fallback: if a view only has control_type, derive a sensible format.
  const ct = String(control.control_type || '').trim().toLowerCase()
  if (ct === 'dropdown') return 'dropdown'
  if (ct === 'datetime') return 'datetime'
  return 'string'
}


function formatValueNormal(control: ViewControl, raw: unknown, dropdowns?: Record<string, any> | null): string {
  if (raw === null || raw === undefined) return ''

  const type = resolveFormatType(control)

  if (type === 'date') {
    return formatPdvmDateDE(raw, false)
  }

  if (type === 'datetime') {
    return formatPdvmDateDE(raw, true)
  }

  if (type === 'number' || type === 'float' || type === 'int') {
    const n = typeof raw === 'number' ? raw : Number(raw)
    if (!Number.isFinite(n)) return String(raw)
    return new Intl.NumberFormat('de-DE').format(n)
  }

  if (type === 'dropdown') {
    const guid = String(control.control_guid || '')
    const resolver = dropdowns && guid ? (dropdowns as any)[guid] : null
    const map = resolver && typeof resolver === 'object' ? (resolver as any).map : null
    const key = String(raw)
    if (map && typeof map === 'object' && map[key] !== undefined && map[key] !== null) {
      return String(map[key])
    }
    return key
  }

  return String(raw)
}

function formatValueExpert(raw: unknown): string {
  if (raw === null || raw === undefined) return ''
  if (typeof raw === 'string') return raw
  if (typeof raw === 'number' || typeof raw === 'boolean') return String(raw)
  try {
    return JSON.stringify(raw)
  } catch {
    return String(raw)
  }
}

function extractControls(definition: ViewDefinitionResponse): ViewControl[] {
  const daten = definition.daten || {}
  const controls: ViewControl[] = []

  for (const [sectionKey, sectionVal] of Object.entries(daten)) {
    if (sectionKey === 'ROOT') continue
    if (!isPlainObject(sectionVal)) continue

    for (const [controlGuid, controlVal] of Object.entries(sectionVal)) {
      if (!isPlainObject(controlVal)) continue

      controls.push({
        control_guid: controlGuid,
        gruppe: String(controlVal.gruppe || ''),
        feld: String(controlVal.feld || ''),
        label: controlVal.label,
        type: controlVal.type,
        control_type: controlVal.control_type,
        show: controlVal.show !== false,
        display_order: Number(controlVal.display_order || 0),
        sortable: !!controlVal.sortable,
        searchable: !!controlVal.searchable,
        configs: controlVal.configs,
      })
    }
  }

  return controls
}

function controlsFromState(state: ViewStateResponse | undefined): ViewControl[] {
  const list = state?.controls_effective || []
  return list
    .filter((c) => c && typeof c === 'object')
    .map((c: any) => ({
      control_guid: String(c.control_guid || ''),
      gruppe: String(c.gruppe || ''),
      feld: String(c.feld || ''),
      label: c.label,
      type: c.type,
      control_type: c.control_type,
      show: c.show !== false,
      display_order: Number(c.display_order || 0),
      width: c.width !== undefined ? Number(c.width) : undefined,
      sortable: !!c.sortable,
      searchable: !!c.searchable,
      configs: c.configs,
    }))
    .filter((c) => !!c.control_guid)
}

function getRawValue(row: ViewBaseRow, control: ViewControl): unknown {
  const gruppe = control.gruppe
  const feld = control.feld
  if (!gruppe || !feld) return undefined

  const groupObj = row.daten?.[gruppe]
  let raw = groupObj?.[feld]

  // Spezialfall: gruppe=SYSTEM referenziert DB-Spaltennamen (kann in sys_viewdaten variieren)
  if (gruppe === 'SYSTEM' && raw === undefined && groupObj && typeof groupObj === 'object') {
    raw = (groupObj as any)[String(feld).toLowerCase()]
    if (raw === undefined) raw = (groupObj as any)[String(feld).toUpperCase()]
  }
  // Stichtag-Auflösung passiert serverseitig; Frontend darf hier NICHT "latest" wählen.
  return raw
}

function getAbdatumTooltip(row: ViewBaseRow, control: ViewControl): string | undefined {
  const gruppe = control.gruppe
  const feld = control.feld
  if (!gruppe || !feld) return undefined

  const groupObj = (row.daten as any)?.[gruppe]
  if (!groupObj || typeof groupObj !== 'object') return undefined

  const formatted = (groupObj as any)[`${feld}__abdatum_formatiert`]
  if (formatted !== null && formatted !== undefined && String(formatted).trim() !== '') {
    return `AB: ${String(formatted)}`
  }

  const raw = (groupObj as any)[`${feld}__abdatum`]
  if (raw !== null && raw !== undefined && String(raw).trim() !== '') {
    return `AB: ${String(raw)}`
  }

  return undefined
}

function applyDraftToControls(base: ViewControl[], draftControlsSource: Record<string, any> | null): ViewControl[] {
  if (!draftControlsSource) return base
  return base.map((c) => {
    const srcEntry = (draftControlsSource as any)[c.control_guid]
    if (!srcEntry || typeof srcEntry !== 'object') return c

    const nextWidth =
      srcEntry.width === undefined || srcEntry.width === null || srcEntry.width === ''
        ? undefined
        : Number(srcEntry.width)

    return {
      ...c,
      show: srcEntry.show !== undefined ? !!srcEntry.show : c.show,
      display_order: srcEntry.display_order !== undefined ? Number(srcEntry.display_order || 0) : c.display_order,
      width: nextWidth !== undefined && Number.isFinite(nextWidth) ? nextWidth : c.width,
    }
  })
}


export default function PdvmViewPage() {
  const { viewGuid } = useParams<{ viewGuid: string }>()

  if (!viewGuid) {
    return <div style={{ padding: 12 }}>Fehler: viewGuid fehlt</div>
  }

  return (
    <div className="pdvm-view-page">
      <PdvmViewPageContent viewGuid={viewGuid} editType="view" />
    </div>
  )
}

export function PdvmViewPageContent({
  viewGuid,
  tableOverride,
  editType,
  embedded,
}: {
  viewGuid: string
  tableOverride?: string | null
  editType?: string | null
  embedded?: boolean
}) {
  const [expertMode, setExpertMode] = useState(false)
  const [showColumns, setShowColumns] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const queryClient = useQueryClient()

  const [pageOffset, setPageOffset] = useState(0)
  const pageLimit = 200

  const [draftControlsSource, setDraftControlsSource] = useState<Record<string, any> | null>(null)
  const [draftTableStateSource, setDraftTableStateSource] = useState<TableState | null>(null)
  const lastSavedJsonRef = useRef<string>('')
  const autosaveTimerRef = useRef<number | null>(null)

  const [showGrouping, setShowGrouping] = useState(false)

  const [collapsedGroupKeys, setCollapsedGroupKeys] = useState<Set<string>>(() => new Set())

  const [selectedUids, setSelectedUids] = useState<Set<string>>(() => new Set())
  const selectionAnchorIndexRef = useRef<number | null>(null)

  const closeSettings = () => {
    setSettingsOpen(false)
    setShowColumns(false)
    setShowGrouping(false)
  }

  // Optional: ESC schließt die Einstellungsbar
  useEffect(() => {
    if (!settingsOpen) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeSettings()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [settingsOpen])

  const defQuery = useQuery({
    queryKey: ['view', 'definition', viewGuid],
    queryFn: () => viewsAPI.getDefinition(viewGuid),
    enabled: !!viewGuid,
  })

  const effectiveEditType = String(editType || 'view').trim().toLowerCase() || 'view'
  const effectiveTableOverride = tableOverride ? String(tableOverride).trim() : ''

  // Stichtag-Änderung -> Base-Daten neu laden (stichtag beeinflusst historische Werte)
  useEffect(() => {
    if (!viewGuid) return
    const handler = () => {
      queryClient.invalidateQueries({ queryKey: ['view', 'matrix', viewGuid] })
    }
    window.addEventListener('pdvm:stichtag-changed', handler as any)
    return () => window.removeEventListener('pdvm:stichtag-changed', handler as any)
  }, [viewGuid, queryClient])

  const stateQuery = useQuery({
    queryKey: ['view', 'state', viewGuid, effectiveTableOverride, effectiveEditType],
    queryFn: () =>
      viewsAPI.getState(viewGuid, {
        table: effectiveTableOverride || undefined,
        edit_type: effectiveEditType,
      }),
    enabled: !!viewGuid && !!defQuery.data,
  })

  const saveStateMutation = useMutation({
    mutationFn: async (payload: { controls_source: Record<string, any>; table_state_source: TableState }) => {
      return viewsAPI.putStateFull(viewGuid, payload, {
        table: effectiveTableOverride || undefined,
        edit_type: effectiveEditType,
      })
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['view', 'state', viewGuid, effectiveTableOverride, effectiveEditType], data)
      // Halte Draft und Autosave-Tracking konsistent
      setDraftControlsSource(data.controls_source || {})
      setDraftTableStateSource((data.table_state_source as any) || { sort: { control_guid: null, direction: null }, filters: {} })
      try {
        lastSavedJsonRef.current = JSON.stringify({
          controls_source: data.controls_source || {},
          table_state_source: (data.table_state_source as any) || { sort: { control_guid: null, direction: null }, filters: {} },
        })
      } catch {
        lastSavedJsonRef.current = ''
      }
    },
  })

  const mutateSaveState = saveStateMutation.mutate

  // Initiale Draft-Synchronisation (nachdem State geladen wurde)
  useEffect(() => {
    if (!stateQuery.data) return
    const src = stateQuery.data.controls_source || {}
    setDraftControlsSource(src)

    const tableState = (stateQuery.data.table_state_source as any) || {
      sort: { control_guid: null, direction: null },
      filters: {},
      group: { enabled: false, by: null, sum_control_guid: null },
    }
    setDraftTableStateSource(tableState)
    try {
      lastSavedJsonRef.current = JSON.stringify({
        controls_source: src,
        table_state_source: tableState,
      })
    } catch {
      lastSavedJsonRef.current = ''
    }
  }, [stateQuery.data])

  // Autosave (debounced) für Draft-Änderungen
  useEffect(() => {
    if (!viewGuid || !stateQuery.data || !draftControlsSource || !draftTableStateSource) return

    let nextJson = ''
    try {
      nextJson = JSON.stringify({
        controls_source: draftControlsSource,
        table_state_source: draftTableStateSource,
      })
    } catch {
      // Wenn es nicht serialisierbar ist, speichern wir nicht.
      return
    }

    // Keine Änderungen
    if (nextJson === lastSavedJsonRef.current) return

    // Debounce
    if (autosaveTimerRef.current) {
      window.clearTimeout(autosaveTimerRef.current)
    }

    autosaveTimerRef.current = window.setTimeout(() => {
      // Vermeide Doppelsaves wenn der User extrem schnell toggelt
      if (saveStateMutation.isPending) return
      mutateSaveState({ controls_source: draftControlsSource, table_state_source: draftTableStateSource })
    }, 600)

    return () => {
      if (autosaveTimerRef.current) {
        window.clearTimeout(autosaveTimerRef.current)
        autosaveTimerRef.current = null
      }
    }
  }, [
    viewGuid,
    stateQuery.data?.view_guid,
    draftControlsSource,
    draftTableStateSource,
    saveStateMutation.isPending,
    mutateSaveState,
  ])

  // UI-Status für Autosave (dirty/saving/saved)
  let draftJson = ''
  if (draftControlsSource && draftTableStateSource) {
    try {
      draftJson = JSON.stringify({
        controls_source: draftControlsSource,
        table_state_source: draftTableStateSource,
      })
    } catch {
      draftJson = ''
    }
  }
  const isDirty = !!draftControlsSource && !!draftTableStateSource && draftJson !== lastSavedJsonRef.current

  const controls = useMemo(() => {
    const fallback = fallbackUidNameControls()
    if (stateQuery.data) {
      const base = applyDraftToControls(controlsFromState(stateQuery.data), draftControlsSource)
        .filter((c) => c.show)
        .sort((a, b) => (a.display_order || 0) - (b.display_order || 0))

      return base.length > 0 ? base : fallback
    }

    if (!defQuery.data) return []
    const base = applyDraftToControls(extractControls(defQuery.data), draftControlsSource)
      .filter((c) => c.show)
      .sort((a, b) => (a.display_order || 0) - (b.display_order || 0))

    return base.length > 0 ? base : fallback
  }, [defQuery.data, stateQuery.data, draftControlsSource])

  const allControls = useMemo(() => {
    const fallback = fallbackUidNameControls()
    if (stateQuery.data) {
      const base = applyDraftToControls(controlsFromState(stateQuery.data), draftControlsSource).sort(
        (a, b) => (a.display_order || 0) - (b.display_order || 0)
      )
      return base.length > 0 ? base : fallback
    }
    if (!defQuery.data) return []
    const base = applyDraftToControls(extractControls(defQuery.data), draftControlsSource).sort(
      (a, b) => (a.display_order || 0) - (b.display_order || 0)
    )
    return base.length > 0 ? base : fallback
  }, [defQuery.data, stateQuery.data, draftControlsSource])

  const matrixKey = useMemo(() => {
    if (!draftControlsSource || !draftTableStateSource) return ''
    try {
      return JSON.stringify({ controls_source: draftControlsSource, table_state_source: draftTableStateSource })
    } catch {
      return ''
    }
  }, [draftControlsSource, draftTableStateSource])

  // When state changes (filters/sort/group/columns), reset paging
  useEffect(() => {
    setPageOffset(0)
  }, [matrixKey])

  const matrixQuery = useQuery<ViewMatrixResponse>({
    queryKey: ['view', 'matrix', viewGuid, effectiveTableOverride, effectiveEditType, matrixKey, pageOffset, pageLimit],
    queryFn: () =>
      viewsAPI.postMatrix(
        viewGuid,
        {
          controls_source: draftControlsSource || undefined,
          table_state_source: (draftTableStateSource as any) || undefined,
          include_historisch: true,
          limit: pageLimit,
          offset: pageOffset,
        },
        {
          ...(effectiveTableOverride ? { table: effectiveTableOverride } : null),
          edit_type: effectiveEditType,
        } as any,
      ),
    enabled: !!viewGuid && !!defQuery.data && !!stateQuery.data && !!draftControlsSource && !!draftTableStateSource,
  })

  const tableStateEffective: TableState =
    draftTableStateSource ||
    ((stateQuery.data?.table_state_effective as any) || {
      sort: { control_guid: null, direction: null },
      filters: {},
      group: { enabled: false, by: null, sum_control_guid: null },
    })

  const serverRows = (matrixQuery.data?.rows || []) as ViewMatrixRow[]
  const dropdowns = (matrixQuery.data?.dropdowns || null) as any

  const dataRowsInOrder = useMemo(() => {
    const out: ViewBaseRow[] = []
    for (const r of serverRows) {
      if ((r as any).kind === 'data') out.push(r as any)
    }
    return out
  }, [serverRows])

  const renderRows: RenderRow[] = useMemo(() => {
    const groupEnabled = !!tableStateEffective.group?.enabled
    const groupByGuid = tableStateEffective.group?.by || null
    const groupControl = groupEnabled && groupByGuid ? allControls.find((c) => c.control_guid === groupByGuid) : undefined

    const out: RenderRow[] = []
    let dataIndex = 0

    for (const r of serverRows) {
      if ((r as any).kind === 'group') {
        const gr = r as any
        const raw = gr.raw
        const key = String(gr.key || '')
        const label = !groupControl
          ? raw === null || raw === undefined
            ? '(leer)'
            : String(raw)
          : raw === null || raw === undefined
            ? '(leer)'
            : formatValueNormal(groupControl, raw, dropdowns)

        out.push({ kind: 'group', key, label, count: Number(gr.count || 0), sum: gr.sum ?? null })
        continue
      }

      if ((r as any).kind === 'data') {
        const dr = r as any as ViewBaseRow & { group_key?: string }
        const baseIndex = dataIndex
        dataIndex += 1
        if (collapsedGroupKeys.has(String((dr as any).group_key || ''))) continue
        out.push({ kind: 'data', row: dr, baseIndex })
      }
    }

    return out
  }, [serverRows, tableStateEffective.group, allControls, collapsedGroupKeys, dropdowns])

  const groupKeys = useMemo(() => {
    const keys: string[] = []
    for (const r of renderRows) {
      if (r.kind === 'group') keys.push(r.key)
    }
    return keys
  }, [renderRows])

  const groupingTotals = useMemo(() => {
    const groupEnabled = !!tableStateEffective.group?.enabled
    const groupByGuid = tableStateEffective.group?.by || null
    if (!groupEnabled || !groupByGuid) return null
    return (matrixQuery.data?.totals as any) || null
  }, [tableStateEffective.group, matrixQuery.data?.totals])

  // Reset collapse state when grouping setup changes
  useEffect(() => {
    setCollapsedGroupKeys(new Set())
  }, [tableStateEffective.group?.enabled, tableStateEffective.group?.by, tableStateEffective.group?.sum_control_guid])

  // Prune selection when base rows change
  useEffect(() => {
    const known = new Set(dataRowsInOrder.map((r) => r.uid))
    setSelectedUids((prev) => {
      const next = new Set<string>()
      for (const uid of prev) {
        if (known.has(uid)) next.add(uid)
      }
      return next.size === prev.size ? prev : next
    })
  }, [dataRowsInOrder])

  // Emit selection-changed event
  useEffect(() => {
    if (!viewGuid) return
    const payload = {
      view_guid: viewGuid,
      selected_uids: Array.from(selectedUids),
    }
    window.dispatchEvent(new CustomEvent('pdvm:view-selection-changed', { detail: payload }))
  }, [viewGuid, selectedUids])

  const handleRowClick = (rowUid: string, rowIndex: number, e: React.MouseEvent) => {
    const isShift = e.shiftKey
    const isToggle = e.ctrlKey || e.metaKey

    setSelectedUids((prev) => {
      const next = new Set(prev)

      if (isShift && selectionAnchorIndexRef.current !== null) {
        const a = selectionAnchorIndexRef.current
        const start = Math.min(a, rowIndex)
        const end = Math.max(a, rowIndex)
        const rangeUids = dataRowsInOrder.slice(start, end + 1).map((r) => r.uid)

        if (!isToggle) next.clear()
        for (const uid of rangeUids) next.add(uid)
        return next
      }

      selectionAnchorIndexRef.current = rowIndex

      if (isToggle) {
        if (next.has(rowUid)) next.delete(rowUid)
        else next.add(rowUid)
        return next
      }

      next.clear()
      next.add(rowUid)
      return next
    })
  }

  if (defQuery.isLoading) return <div style={{ padding: 16 }}>View lädt…</div>
  if (defQuery.error) return <div style={{ padding: 16, color: 'crimson' }}>Fehler beim Laden der ViewDefinition</div>

  const resetFilterSort = () => {
    if (!draftTableStateSource) return
    setDraftTableStateSource({
      sort: { control_guid: null, direction: null },
      filters: {},
      group: draftTableStateSource.group || { enabled: false, by: null, sum_control_guid: null },
    })
  }

  const resetGrouping = () => {
    if (!draftTableStateSource) return
    setDraftTableStateSource({
      ...draftTableStateSource,
      group: { enabled: false, by: null, sum_control_guid: null },
    })
    setCollapsedGroupKeys(new Set())
  }

  const toggleGroupCollapsed = (key: string) => {
    setCollapsedGroupKeys((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const collapseAllGroups = () => {
    setCollapsedGroupKeys(new Set(groupKeys))
  }

  const expandAllGroups = () => {
    setCollapsedGroupKeys(new Set())
  }

  const meta = (matrixQuery.data?.meta || {}) as any
  const totalAfterFilter = Number(meta.total_after_filter || 0)
  const hasMore = !!meta.has_more
  const hasMultiplePages = pageOffset > 0 || hasMore

  const resolveSelectedIndex = (): number | null => {
    if (selectionAnchorIndexRef.current !== null) return selectionAnchorIndexRef.current
    const arr = Array.from(selectedUids)
    if (arr.length !== 1) return null
    const uid = arr[0]
    const idx = dataRowsInOrder.findIndex((r) => r.uid === uid)
    return idx >= 0 ? idx : null
  }

  const selectRowByIndex = (nextIndex: number) => {
    const r = dataRowsInOrder[nextIndex]
    if (!r) return
    selectionAnchorIndexRef.current = nextIndex
    setSelectedUids(new Set([r.uid]))
  }

  const selectedIndex = resolveSelectedIndex()
  const canPrevRecord = selectedIndex !== null && selectedIndex > 0
  const canNextRecord = selectedIndex !== null && selectedIndex < dataRowsInOrder.length - 1

  return (
    <div
      className={`pdvm-view ${embedded ? 'pdvm-view--embedded' : ''}`}
      style={!embedded ? { padding: 12 } : undefined}
    >
      <div className="pdvm-view__fixed">
        <div className="pdvm-view__headerRow">
          <div className="pdvm-view__title">
            <h3 className="pdvm-view__name">{defQuery.data?.name || 'View'}</h3>
            <div className="pdvm-view__meta">
              VIEW_GUID: {viewGuid} · Tabelle: {matrixQuery.data?.table || defQuery.data?.root?.TABLE || ''} · Treffer: {totalAfterFilter}
              {meta?.table_truncated ? <span style={{ marginLeft: 8, color: 'darkorange', fontWeight: 800 }}>(gekürzt)</span> : null}
            </div>
          </div>

          <button
            type="button"
            className="pdvm-view__settingsToggle"
            aria-label={settingsOpen ? 'Einstellungen schließen' : 'Einstellungen öffnen'}
            title={settingsOpen ? 'Einstellungen schließen' : 'Einstellungen öffnen'}
            onClick={() => {
              setSettingsOpen((v) => {
                const next = !v
                if (!next) closeSettings()
                return next
              })
            }}
          >
            ⚙
          </button>
        </div>

        {settingsOpen ? (
          <div className="pdvm-view__settings" aria-label="View Einstellungen">
            <div className="pdvm-view__settingsHeader">
              <div className="pdvm-view__settingsTitle">Einstellungen</div>
              <div className="pdvm-view__settingsButtons">
                <button
                  type="button"
                  className={`pdvm-view__settingsButton ${showColumns ? 'pdvm-view__settingsButton--active' : ''}`}
                  onClick={() => setShowColumns((v) => !v)}
                >
                  <span>Spalten</span>
                  <span style={{ opacity: 0.65 }}>{showColumns ? '▾' : '▸'}</span>
                </button>

                <button
                  type="button"
                  className={`pdvm-view__settingsButton ${showGrouping ? 'pdvm-view__settingsButton--active' : ''}`}
                  onClick={() => setShowGrouping((v) => !v)}
                  disabled={!draftTableStateSource}
                  title="Gruppierung konfigurieren"
                >
                  <span>Gruppierung</span>
                  <span style={{ opacity: 0.65 }}>{showGrouping ? '▾' : '▸'}</span>
                </button>

                <button
                  type="button"
                  className="pdvm-view__settingsButton"
                  onClick={resetFilterSort}
                  disabled={!draftTableStateSource}
                  title="Setzt alle Filter und Sortierung zurück"
                >
                  <span>Filter/Sort reset</span>
                  <span style={{ opacity: 0.65 }}>↺</span>
                </button>

                <button
                  type="button"
                  className={`pdvm-view__settingsButton ${expertMode ? 'pdvm-view__settingsButton--active' : ''}`}
                  onClick={() => setExpertMode((v) => !v)}
                >
                  <span>{expertMode ? 'Expert: Rohdaten' : 'Normal: formatiert'}</span>
                  <span style={{ opacity: 0.65 }}>⚙</span>
                </button>

                <button type="button" className="pdvm-view__settingsButton" onClick={closeSettings}>
                  <span>Schließen</span>
                  <span style={{ opacity: 0.65 }}>✕</span>
                </button>
              </div>
            </div>

            <div className="pdvm-view__settingsBody">
              {!showColumns && !(showGrouping && draftTableStateSource) ? (
                <div className="pdvm-view__settingsEmpty">Bitte oben einen Einstellungsbereich auswählen.</div>
              ) : null}

              {showGrouping && draftTableStateSource ? (
                <div className="pdvm-view__settingsSection">
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                    <div style={{ fontWeight: 800 }}>Gruppierung</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <button type="button" onClick={expandAllGroups} disabled={!groupKeys.length} className="pdvm-view__navButton">
                        Alle aufklappen
                      </button>
                      <button type="button" onClick={collapseAllGroups} disabled={!groupKeys.length} className="pdvm-view__navButton">
                        Alle zuklappen
                      </button>
                      <button type="button" onClick={resetGrouping} className="pdvm-view__navButton">
                        Zurücksetzen
                      </button>
                    </div>
                  </div>

                  <div style={{ marginTop: 10, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
                      <input
                        type="checkbox"
                        checked={!!draftTableStateSource.group?.enabled}
                        onChange={(e) => {
                          setDraftTableStateSource({
                            ...draftTableStateSource,
                            group: {
                              ...(draftTableStateSource.group || { enabled: false, by: null, sum_control_guid: null }),
                              enabled: e.target.checked,
                            },
                          })
                        }}
                      />
                      <span>Gruppierung aktiv</span>
                    </label>

                    <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
                      <span>Gruppe nach</span>
                      <select
                        value={draftTableStateSource.group?.by || ''}
                        onChange={(e) => {
                          const v = e.target.value || null
                          setDraftTableStateSource({
                            ...draftTableStateSource,
                            group: {
                              ...(draftTableStateSource.group || { enabled: false, by: null, sum_control_guid: null }),
                              by: v,
                            },
                          })
                        }}
                        style={{ padding: '6px 8px', borderRadius: 8, border: '1px solid rgba(0,0,0,0.15)', background: 'white' }}
                      >
                        <option value="">(keine)</option>
                        {allControls.map((c) => (
                          <option key={c.control_guid} value={c.control_guid}>
                            {c.label || `${c.gruppe}.${c.feld}`}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
                      <span>Summe</span>
                      <select
                        value={draftTableStateSource.group?.sum_control_guid || ''}
                        onChange={(e) => {
                          const v = e.target.value || null
                          setDraftTableStateSource({
                            ...draftTableStateSource,
                            group: {
                              ...(draftTableStateSource.group || { enabled: false, by: null, sum_control_guid: null }),
                              sum_control_guid: v,
                            },
                          })
                        }}
                        style={{ padding: '6px 8px', borderRadius: 8, border: '1px solid rgba(0,0,0,0.15)', background: 'white' }}
                      >
                        <option value="">(keine)</option>
                        {allControls
                          .filter((c) => ['number', 'float', 'int'].includes((c.type || '').toLowerCase()))
                          .map((c) => (
                            <option key={c.control_guid} value={c.control_guid}>
                              {c.label || `${c.gruppe}.${c.feld}`}
                            </option>
                          ))}
                      </select>
                    </label>
                  </div>
                </div>
              ) : null}

              {showColumns ? (
                <div className="pdvm-view__settingsSection">
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                    <div style={{ fontWeight: 800 }}>Spalten anzeigen</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontSize: 12, opacity: 0.75 }}>
                        {saveStateMutation.isPending
                          ? 'Autosave…'
                          : saveStateMutation.error
                            ? 'Fehler'
                            : isDirty
                              ? 'Änderungen…'
                              : lastSavedJsonRef.current
                                ? 'Gespeichert'
                                : ''}
                      </span>

                      <button
                        type="button"
                        onClick={() => {
                          if (!draftControlsSource || !draftTableStateSource) return
                          mutateSaveState({ controls_source: draftControlsSource, table_state_source: draftTableStateSource })
                        }}
                        disabled={!draftControlsSource || saveStateMutation.isPending || !isDirty}
                        className="pdvm-view__navButton"
                      >
                        Jetzt speichern
                      </button>
                    </div>
                  </div>

                  {!stateQuery.data ? (
                    <div style={{ marginTop: 8, fontSize: 12, opacity: 0.75 }}>
                      {stateQuery.error ? (
                        <span style={{ color: 'crimson', opacity: 1 }}>
                          Fehler beim Laden des States:{' '}
                          {String((stateQuery.error as any)?.response?.data?.detail || (stateQuery.error as any)?.message || stateQuery.error)}
                        </span>
                      ) : (
                        'State lädt… (falls noch kein State existiert, wird er automatisch aus den Defaults gemerged)'
                      )}
                    </div>
                  ) : null}

                  {stateQuery.data ? (
                    <div
                      style={{
                        marginTop: 10,
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                        gap: 10,
                      }}
                    >
                      {allControls.map((c, idx) => {
                      const source = draftControlsSource || stateQuery.data.controls_source || {}
                      const srcEntry = (source as any)[c.control_guid] || {}
                      const checked = srcEntry.show !== undefined ? !!srcEntry.show : c.show !== false
                      const order =
                        srcEntry.display_order !== undefined
                          ? Number(srcEntry.display_order || 0)
                          : Number(c.display_order || 0)
                      const widthStr =
                        srcEntry.width !== undefined && srcEntry.width !== null
                          ? String(srcEntry.width)
                          : c.width !== undefined
                            ? String(c.width)
                            : ''

                      const move = (direction: -1 | 1) => {
                        const neighborIndex = idx + direction
                        if (neighborIndex < 0 || neighborIndex >= allControls.length) return
                        const other = allControls[neighborIndex]

                        const otherSrc = (source as any)[other.control_guid] || {}
                        const otherOrder =
                          otherSrc.display_order !== undefined
                            ? Number(otherSrc.display_order || 0)
                            : Number(other.display_order || 0)

                        const next = { ...(source as any) }
                        next[c.control_guid] = {
                          ...(next[c.control_guid] || {}),
                          show: checked,
                          display_order: otherOrder,
                        }
                        next[other.control_guid] = {
                          ...(next[other.control_guid] || {}),
                          show: otherSrc.show !== undefined ? !!otherSrc.show : other.show !== false,
                          display_order: order,
                        }
                        setDraftControlsSource(next)
                      }

                      return (
                        <div
                          key={c.control_guid}
                          style={{
                            border: '1px solid rgba(0,0,0,0.10)',
                            borderRadius: 10,
                            padding: 10,
                            background: 'white',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: 8,
                          }}
                        >
                          <label style={{ display: 'flex', alignItems: 'flex-start', gap: 8, fontSize: 13 }}>
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={(e) => {
                                const next = { ...(source as any) }
                                next[c.control_guid] = {
                                  ...(next[c.control_guid] || {}),
                                  show: e.target.checked,
                                  display_order: order,
                                }
                                setDraftControlsSource(next)
                              }}
                            />
                            <span style={{ lineHeight: 1.2, wordBreak: 'break-word' }}>{c.label || `${c.gruppe}.${c.feld}`}</span>
                          </label>

                          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                            <button type="button" onClick={() => move(-1)} title="Nach oben" disabled={idx === 0} className="pdvm-view__navButton">
                              ↑
                            </button>
                            <button
                              type="button"
                              onClick={() => move(1)}
                              title="Nach unten"
                              disabled={idx === allControls.length - 1}
                              className="pdvm-view__navButton"
                            >
                              ↓
                            </button>

                            <input
                              type="number"
                              value={Number.isFinite(order) ? order : 0}
                              onChange={(e) => {
                                const n = Number(e.target.value)
                                const nextOrder = Number.isFinite(n) ? n : 0
                                const next = { ...(source as any) }
                                next[c.control_guid] = {
                                  ...(next[c.control_guid] || {}),
                                  show: checked,
                                  display_order: nextOrder,
                                }
                                setDraftControlsSource(next)
                              }}
                              title="Reihenfolge"
                              style={{ width: 70, padding: '4px 6px', borderRadius: 8, border: '1px solid rgba(0,0,0,0.15)' }}
                            />

                            <input
                              type="number"
                              value={widthStr}
                              onChange={(e) => {
                                const raw = e.target.value
                                const next = { ...(source as any) }

                                if (raw === '') {
                                  next[c.control_guid] = {
                                    ...(next[c.control_guid] || {}),
                                    show: checked,
                                    display_order: order,
                                  }
                                  if (next[c.control_guid] && 'width' in next[c.control_guid]) {
                                    delete next[c.control_guid].width
                                  }
                                } else {
                                  const n = Number(raw)
                                  const nextWidth = Number.isFinite(n) ? n : undefined
                                  next[c.control_guid] = {
                                    ...(next[c.control_guid] || {}),
                                    show: checked,
                                    display_order: order,
                                    width: nextWidth,
                                  }
                                }

                                setDraftControlsSource(next)
                              }}
                              title="Breite (px) – leer = auto"
                              placeholder="auto"
                              min={40}
                              style={{ width: 78, padding: '4px 6px', borderRadius: 8, border: '1px solid rgba(0,0,0,0.15)' }}
                            />
                          </div>

                          {draftTableStateSource ? (
                            <div>
                              <input
                                type="text"
                                value={draftTableStateSource.filters?.[c.control_guid] || ''}
                                onChange={(e) => {
                                  const next = {
                                    ...draftTableStateSource,
                                    filters: {
                                      ...(draftTableStateSource.filters || {}),
                                      [c.control_guid]: e.target.value,
                                    },
                                  }
                                  setDraftTableStateSource(next)
                                }}
                                placeholder="Filter enthält…"
                                style={{ width: '100%', padding: '6px 8px', borderRadius: 8, border: '1px solid rgba(0,0,0,0.12)', fontSize: 12 }}
                              />
                            </div>
                          ) : null}
                        </div>
                      )
                    })}
                  </div>
                ) : null}

                  {saveStateMutation.error ? (
                    <div style={{ marginTop: 8, color: 'crimson', fontSize: 12 }}>Fehler beim Speichern der Spalten</div>
                  ) : null}
                </div>
              ) : null}
            </div>
          </div>
        ) : null}

        <div className="pdvm-view__recordNav">
          <div className="pdvm-view__recordNavLeft">
            <button
              type="button"
              className="pdvm-view__navButton"
              onClick={() => {
                if (selectedIndex === null) return
                selectRowByIndex(Math.max(0, selectedIndex - 1))
              }}
              disabled={!canPrevRecord}
            >
              Vorherige
            </button>
            <button
              type="button"
              className="pdvm-view__navButton"
              onClick={() => {
                if (selectedIndex === null) return
                selectRowByIndex(Math.min(dataRowsInOrder.length - 1, selectedIndex + 1))
              }}
              disabled={!canNextRecord}
            >
              Nächste
            </button>
          </div>

          <div style={{ fontSize: 12, opacity: 0.75 }}>
            Seite: {Math.floor(pageOffset / pageLimit) + 1}
            {hasMultiplePages ? '' : ' (nur 1 Seite)'}
          </div>
        </div>
      </div>

      <div className="pdvm-view__scroll">
        {matrixQuery.isLoading ? <div style={{ padding: 8 }}>Daten laden…</div> : null}
        {matrixQuery.error ? <div style={{ padding: 8, color: 'crimson' }}>Fehler beim Laden der Daten</div> : null}

        <div className="pdvm-view__tableWrap">
          <table className="pdvm-view__table" style={{ background: 'var(--block-surface-std-background, white)' as any }}>
            <thead>
              <tr>
                {controls.map((c) => (
                  <th
                    key={c.control_guid}
                    onClick={() => {
                      if (!draftTableStateSource) return
                      const currentGuid = draftTableStateSource.sort?.control_guid || null
                      const currentDir = draftTableStateSource.sort?.direction || null

                      let nextGuid: string | null = c.control_guid
                      let nextDir: SortDirection = 'asc'

                      if (currentGuid === c.control_guid) {
                        if (currentDir === 'asc') nextDir = 'desc'
                        else if (currentDir === 'desc') {
                          nextGuid = null
                          nextDir = null
                        } else nextDir = 'asc'
                      }

                      setDraftTableStateSource({
                        ...draftTableStateSource,
                        sort: { control_guid: nextGuid, direction: nextDir },
                      })
                    }}
                    style={{
                      textAlign: 'left',
                      padding: '10px 12px',
                      fontSize: 12,
                      fontWeight: 700,
                      borderBottom: '1px solid rgba(0,0,0,0.12)',
                      position: 'sticky',
                      top: 0,
                      background: 'var(--block-surface-std-background, white)' as any,
                      zIndex: 1,
                      whiteSpace: 'nowrap',
                      width: c.width ? `${c.width}px` : undefined,
                      cursor: draftTableStateSource ? 'pointer' : 'default',
                    }}
                  >
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                      <span>{c.label || `${c.gruppe}.${c.feld}`}</span>
                      {tableStateEffective.sort?.control_guid === c.control_guid && tableStateEffective.sort?.direction && (
                        <span style={{ fontSize: 11, opacity: 0.65 }}>
                          {tableStateEffective.sort.direction === 'asc' ? '▲' : '▼'}
                        </span>
                      )}
                    </span>
                  </th>
                ))}
              </tr>

              {/* Filter-Row direkt unter Header (nur sichtbare Controls) */}
              {draftTableStateSource && (
                <tr className="pdvm-view__filterRow">
                  {controls.map((c) => (
                    <th
                      key={`${c.control_guid}:filter`}
                      style={{
                        textAlign: 'left',
                        padding: '6px 10px',
                        fontSize: 12,
                        fontWeight: 400,
                        borderBottom: '1px solid rgba(0,0,0,0.08)',
                        background: 'var(--block-surface-std-background, white)' as any,
                      }}
                    >
                      <input
                        type="text"
                        value={draftTableStateSource.filters?.[c.control_guid] || ''}
                        onChange={(e) => {
                          const next = {
                            ...draftTableStateSource,
                            filters: {
                              ...(draftTableStateSource.filters || {}),
                              [c.control_guid]: e.target.value,
                            },
                          }
                          setDraftTableStateSource(next)
                        }}
                        placeholder="Filter…"
                        style={{
                          width: '100%',
                          padding: '4px 6px',
                          borderRadius: 8,
                          border: '1px solid rgba(0,0,0,0.12)',
                          fontSize: 12,
                        }}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </th>
                  ))}
                </tr>
              )}
            </thead>

            <tbody>
              {renderRows.map((item) => {
                if (item.kind === 'group') {
                  const isCollapsed = collapsedGroupKeys.has(item.key)
                  return (
                    <tr
                      key={`group:${item.key}`}
                      style={{ borderBottom: '1px solid rgba(0,0,0,0.08)', cursor: 'pointer' }}
                      onClick={() => toggleGroupCollapsed(item.key)}
                      title={isCollapsed ? 'Aufklappen' : 'Zuklappen'}
                    >
                      <td
                        colSpan={Math.max(1, controls.length)}
                        style={{
                          padding: '10px 12px',
                          fontSize: 12,
                          fontWeight: 800,
                          background: 'rgba(0,0,0,0.03)',
                        }}
                      >
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                          <span style={{ width: 14, display: 'inline-block', opacity: 0.75 }}>
                            {isCollapsed ? '▸' : '▾'}
                          </span>
                          <span>
                            {item.label} · {item.count}
                          </span>
                        </span>
                        {item.sum !== null && (
                          <span style={{ marginLeft: 10, opacity: 0.75, fontWeight: 600 }}>
                            Summe: {new Intl.NumberFormat('de-DE').format(item.sum)}
                          </span>
                        )}
                      </td>
                    </tr>
                  )
                }

                const row = item.row
                const isSelected = selectedUids.has(row.uid)
                return (
                  <tr
                    key={row.uid}
                    onClick={(e) => handleRowClick(row.uid, item.baseIndex, e)}
                    onDoubleClick={() => {
                      // Activate row (used by dialogs for OPEN_EDIT=double_click)
                      selectionAnchorIndexRef.current = item.baseIndex
                      setSelectedUids(new Set([row.uid]))
                      window.dispatchEvent(
                        new CustomEvent('pdvm:view-row-activated', {
                          detail: { view_guid: viewGuid, uid: row.uid, action: 'double_click' },
                        })
                      )
                    }}
                    style={{
                      borderBottom: '1px solid rgba(0,0,0,0.08)',
                      background: isSelected ? 'rgba(0, 120, 212, 0.10)' : undefined,
                      cursor: 'pointer',
                    }}
                  >
                    {controls.map((c) => {
                      const raw = getRawValue(row, c)
                      const cell = expertMode ? formatValueExpert(raw) : formatValueNormal(c, raw, dropdowns)
                      const tooltip = getAbdatumTooltip(row, c)

                      return (
                        <td
                          key={`${row.uid}:${c.control_guid}`}
                          style={{ padding: '10px 12px', fontSize: 13 }}
                          title={tooltip || undefined}
                        >
                          {cell || <span style={{ opacity: 0.4 }}>–</span>}
                        </td>
                      )
                    })}
                  </tr>
                )
              })}

              {groupingTotals && (
                <tr style={{ borderTop: '2px solid rgba(0,0,0,0.12)' }}>
                  <td
                    colSpan={Math.max(1, controls.length)}
                    style={{
                      padding: '10px 12px',
                      fontSize: 12,
                      fontWeight: 900,
                      background: 'rgba(0,0,0,0.05)',
                    }}
                  >
                    Gesamt · {groupingTotals.count}
                    {groupingTotals.sum !== null && (
                      <span style={{ marginLeft: 10, opacity: 0.85, fontWeight: 800 }}>
                        Summe: {new Intl.NumberFormat('de-DE').format(groupingTotals.sum)}
                      </span>
                    )}
                  </td>
                </tr>
              )}

              {!matrixQuery.isLoading && renderRows.length === 0 && (
                <tr>
                  <td colSpan={Math.max(1, controls.length)} style={{ padding: 16, opacity: 0.7 }}>
                    {(() => {
                      const meta = (matrixQuery.data?.meta || {}) as any
                      const baseLoaded = Number(meta.base_loaded || 0)
                      const totalAfterFilter = Number(meta.total_after_filter || 0)
                      if (baseLoaded === 0) return 'Keine Datensätze gefunden.'
                      if (totalAfterFilter === 0) return 'Keine Treffer (Filter).'
                      return 'Keine Datensätze (Seite).'
                    })()}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="pdvm-view__pager">
          <button
            type="button"
            className="pdvm-view__navButton"
            onClick={() => setPageOffset((o) => Math.max(0, o - pageLimit))}
            disabled={!hasMultiplePages || pageOffset <= 0}
          >
            Zurück
          </button>
          <button
            type="button"
            className="pdvm-view__navButton"
            onClick={() => setPageOffset((o) => o + pageLimit)}
            disabled={!hasMultiplePages || !hasMore}
          >
            Weiter
          </button>
        </div>
      </div>
    </div>
  )
}
