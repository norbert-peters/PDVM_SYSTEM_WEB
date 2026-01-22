import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { dialogsAPI, type DialogRow, type DialogDefinitionResponse, type DialogRecordResponse } from '../../api/client'
import { PdvmViewPageContent } from '../views/PdvmViewPage'
import { PdvmMenuEditor } from './PdvmMenuEditor'
import { PdvmJsonEditor, type PdvmJsonEditorHandle, type PdvmJsonEditorMode } from '../common/PdvmJsonEditor'
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

  // Avoid writing last_call for a new dialog_table using an old selection.
  const lastPersistContextKeyRef = useRef<string>('')
  const persistContextKey = `${String(dialogGuid || '')}|${String(dialogTable || '')}`

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

    // Mark context switch so the persistence effect can skip one cycle.
    lastPersistContextKeyRef.current = persistContextKey
  }, [dialogGuid, dialogTable])

  const defQuery = useQuery<DialogDefinitionResponse>({
    queryKey: ['dialog', 'definition', dialogGuid, dialogTable],
    queryFn: () => dialogsAPI.getDefinition(dialogGuid!, { dialog_table: dialogTable }),
    enabled: !!dialogGuid,
  })

  const openEditMode = String(defQuery.data?.open_edit_mode || 'tab').trim().toLowerCase()
  const editType = String(defQuery.data?.edit_type || 'show_json').trim().toLowerCase()
  const wantsMenuEditor = editType === 'menu'
  const hasEmbeddedView = !!String(defQuery.data?.view_guid || '').trim()

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

  const isMenuEditor = wantsMenuEditor

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

  // Optional preselect: if dialog root defines MENU_GUID, select it once.
  useEffect(() => {
    if (!wantsMenuEditor) return
    if (!menuGuid) return
    if (selectedUid) return
    setSelectedUid(menuGuid)
    setSelectedUids([menuGuid])
  }, [wantsMenuEditor, menuGuid, selectedUid])

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

  // Persist last selection immediately (best-effort), even before loading the record.
  useEffect(() => {
    if (!dialogGuid) return
    if (!selectedUid) return
    if (!isUuidString(selectedUid)) return

    // If the dialog context just changed (e.g. new dialog_table), don't persist the previous selection.
    if (lastPersistContextKeyRef.current !== persistContextKey) {
      lastPersistContextKeyRef.current = persistContextKey
      return
    }

    dialogsAPI.putLastCall(dialogGuid, selectedUid, { dialog_table: dialogTable }).catch(() => {
      // Best-effort persistence only.
    })
  }, [dialogGuid, selectedUid, dialogTable])

  const jsonEditorRef = useRef<PdvmJsonEditorHandle | null>(null)
  const [jsonError, setJsonError] = useState<string | null>(null)
  const [jsonDirty, setJsonDirty] = useState(false)
  const [jsonMode, setJsonMode] = useState<PdvmJsonEditorMode>('text')
  const [jsonSearch, setJsonSearch] = useState('')
  const [jsonSearchHits, setJsonSearchHits] = useState<number | null>(null)
  const jsonSearchInputRef = useRef<HTMLInputElement | null>(null)

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

  const updateMutation = useMutation({
    mutationFn: async (nextJson: Record<string, any>) => {
      return dialogsAPI.updateRecord(dialogGuid!, selectedUid!, { daten: nextJson }, { dialog_table: dialogTable })
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['dialog', 'record', dialogGuid, dialogTable, selectedUid] })
    },
  })

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

  const handleMissingMenuGuid = (missingUid: string) => {
    // Only relevant for menu dialogs
    if (!dialogGuid) return
    setAutoLastCallError(`Letztes Menü (last_call) wurde nicht gefunden: ${missingUid}. Bitte neu auswählen.`)
    setSelectedUid(null)
    setActiveTab('view')
    dialogsAPI.putLastCall(dialogGuid, null, { dialog_table: dialogTable }).catch(() => {
      // Best-effort persistence only.
    })
  }

  return (
    <div className="pdvm-dialog">
      <div className="pdvm-dialog__header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <h2 style={{ margin: 0 }}>{title}</h2>
          <div style={{ fontSize: 12, opacity: 0.7 }}>
            {defQuery.data?.root_table ? `TABLE: ${defQuery.data.root_table}` : null}
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
              onClick={() => setActiveTab('view')}
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
            className={`pdvm-dialog__panelScroll ${activeTab === 'view' && hasEmbeddedView ? 'pdvm-dialog__panelScroll--noScroll' : ''}`}
          >
          {/* edit_type=menu nutzt Auswahl im View-Tab; ROOT.MENU_GUID ist optional (Preselect) */}

          {autoLastCallError ? (
            <div style={{ marginBottom: 10, color: 'goldenrod', fontSize: 12 }}>{autoLastCallError}</div>
          ) : null}

          {activeTab === 'view' ? (
            <div className="pdvm-dialog__view">
              {defQuery.data?.view_guid ? (
                <PdvmViewPageContent viewGuid={String(defQuery.data.view_guid)} tableOverride={dialogTable} editType={editType} embedded />
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
            <div>
              {isMenuEditor ? (
                <>
                  {!selectedUid ? <div>Kein Menüdatensatz ausgewählt. Bitte zuerst im View-Tab auswählen.</div> : null}

                  {selectedUid ? (
                    <div>
                      <div style={{ marginBottom: 10, fontSize: 12, opacity: 0.8 }}>
                        Menü UID: <span style={{ fontFamily: 'monospace' }}>{selectedUid}</span>
                      </div>

                      {menuEditTabs.tabs >= 2 && menuEditTabs.items.length >= 2 ? (
                        <div className="pdvm-tabs" style={{ marginBottom: 10 }}>
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
                              menuGuid={selectedUid}
                              group={menuActiveTab}
                              onMissingMenuGuid={handleMissingMenuGuid}
                            />
                          </div>
                        </div>
                      ) : (
                        <>
                          <div style={{ marginBottom: 16 }}>
                            <div style={{ fontWeight: 800, marginBottom: 8 }}>GRUND</div>
                            <PdvmMenuEditor menuGuid={selectedUid} group="GRUND" onMissingMenuGuid={handleMissingMenuGuid} />
                          </div>
                          <div>
                            <div style={{ fontWeight: 800, marginBottom: 8 }}>VERTIKAL</div>
                            <PdvmMenuEditor menuGuid={selectedUid} group="VERTIKAL" onMissingMenuGuid={handleMissingMenuGuid} />
                          </div>
                        </>
                      )}
                    </div>
                  ) : null}
                </>
              ) : (
                <>
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
                                disabled={updateMutation.isPending}
                                className="pdvm-dialog__toolBtn"
                                title="Alle Knoten aufklappen"
                                aria-label="Alle Knoten aufklappen"
                              >
                                Alle auf
                              </button>
                              <button
                                type="button"
                                onClick={() => jsonEditorRef.current?.collapseAll()}
                                disabled={updateMutation.isPending}
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
                                disabled={updateMutation.isPending}
                                className="pdvm-dialog__toolBtn"
                                title="Objekt-Schlüssel sortieren (A–Z)"
                                aria-label="Objekt-Schlüssel sortieren"
                              >
                                Sortieren
                              </button>
                              <button
                                type="button"
                                onClick={formatJson}
                                disabled={updateMutation.isPending}
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
                                disabled={updateMutation.isPending}
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
                              disabled={updateMutation.isPending || !!jsonError}
                              className="pdvm-dialog__toolBtn pdvm-dialog__toolBtn--primary"
                              title="Speichern"
                              aria-label="Speichern"
                            >
                              Speichern
                            </button>

                            {jsonDirty && !updateMutation.isPending ? (
                              <div style={{ fontSize: 12, opacity: 0.8 }}>Änderungen…</div>
                            ) : null}
                            {updateMutation.isPending ? <div style={{ fontSize: 12, opacity: 0.8 }}>Speichere...</div> : null}
                            {updateMutation.isSuccess ? <div style={{ fontSize: 12, opacity: 0.8 }}>Gespeichert</div> : null}
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
                </>
              )}
            </div>
          ) : null}
          </div>
        </div>
      </div>
    </div>
  )
}
