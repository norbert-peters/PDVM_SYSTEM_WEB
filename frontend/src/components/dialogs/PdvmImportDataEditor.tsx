import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { importDataAPI, type ImportPreviewResponse } from '../../api/client'
import { PdvmInputControl } from '../common/PdvmInputControl'
import { PdvmDialogModal } from '../common/PdvmDialogModal'

export type ImportDataEditorProps = {
  tableName: string | null
  datasetUid: string | null
  onApplied?: () => void
  step?: number
  onStepChange?: (step: number) => void
  hideSteps?: boolean
}

type PreviewRow = Record<string, any>

export type ImportDataStepsProps = {
  step: number
  onChange: (step: number) => void
}

export function PdvmImportDataSteps({ step, onChange }: ImportDataStepsProps) {
  return (
    <div className="pdvm-dialog__importSteps">
      {[
        { id: 1, label: 'Konfiguration' },
        { id: 2, label: 'Upload & Vorschau' },
        { id: 3, label: 'Speichern' },
      ].map((s) => (
        <button
          key={s.id}
          type="button"
          className={`pdvm-dialog__importStep ${step === s.id ? 'pdvm-dialog__importStep--active' : ''}`.trim()}
          onClick={() => onChange(s.id)}
        >
          {s.id}. {s.label}
        </button>
      ))}
    </div>
  )
}

export function PdvmImportDataEditor({
  tableName,
  datasetUid,
  onApplied,
  step,
  onStepChange,
  hideSteps,
}: ImportDataEditorProps) {
  const [internalStep, setInternalStep] = useState(1)
  const activeStep = step ?? internalStep
  const setActiveStep = onStepChange ?? setInternalStep
  const [file, setFile] = useState<File | null>(null)
  const [sheetName, setSheetName] = useState('')
  const [preview, setPreview] = useState<ImportPreviewResponse | null>(null)
  const [rows, setRows] = useState<PreviewRow[]>([])
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const [matchKeysText, setMatchKeysText] = useState('')
  const [conflictPolicy, setConflictPolicy] = useState('base_wins')
  const [hasHeaders, setHasHeaders] = useState(true)
  const [customHeadersText, setCustomHeadersText] = useState('')
  const [headerOverridesText, setHeaderOverridesText] = useState('')
  const [columnsMap, setColumnsMap] = useState<Record<string, any>>({})
  const [activeElementId, setActiveElementId] = useState<string | null>(null)
  const [elementDraft, setElementDraft] = useState<Record<string, any> | null>(null)
  const [elementOpen, setElementOpen] = useState(false)
  const templateUid = '55555555-5555-5555-5555-555555555555'
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false)

  const canPreview = !!tableName && !!datasetUid && !!file

  const datasetQuery = useQuery({
    queryKey: ['import', 'dataset', tableName, datasetUid],
    queryFn: () => importDataAPI.getDataset({ table_name: tableName!, dataset_uid: datasetUid! }),
    enabled: !!tableName && !!datasetUid,
  })

  useEffect(() => {
    if (!datasetQuery.data) return
    const root = (datasetQuery.data.daten || {}).ROOT || {}
    const config = (datasetQuery.data.daten || {}).CONFIG || {}
    const cols = (config.COLUMNS || {}) as Record<string, any>

    setColumnsMap(cols)
    setMatchKeysText(Array.isArray(root.MATCH_KEYS) ? root.MATCH_KEYS.join(', ') : '')
    setConflictPolicy(String(root.CONFLICT_POLICY || 'base_wins'))
    setHasHeaders(root.HAS_HEADERS !== false)
    setCustomHeadersText(Array.isArray(root.CUSTOM_HEADERS) ? root.CUSTOM_HEADERS.join(', ') : '')
    setHeaderOverridesText(root.HEADER_OVERRIDES ? JSON.stringify(root.HEADER_OVERRIDES, null, 2) : '')
  }, [datasetQuery.data])

  const previewMutation = useMutation({
    mutationFn: async () => {
      let overrides: Record<string, any> | undefined
      if (headerOverridesText.trim()) {
        try {
          overrides = JSON.parse(headerOverridesText)
        } catch {
          throw new Error('HEADER_OVERRIDES ist kein gueltiges JSON')
        }
      }

      return importDataAPI.preview({
        dataset_uid: datasetUid!,
        table_name: tableName!,
        file: file!,
        sheet_name: sheetName.trim() || undefined,
        has_headers: hasHeaders,
        custom_headers: customHeadersText.trim() || undefined,
        header_overrides: overrides,
      })
    },
    onSuccess: (data) => {
      setPreview(data)
      setRows(data.rows || [])
      setError(null)
      setInfo(null)
    },
    onError: (err: any) => {
      setError(err?.message || 'Preview fehlgeschlagen')
    },
  })

  const applyMutation = useMutation({
    mutationFn: async () => {
      return importDataAPI.apply({
        table_name: tableName!,
        dataset_uid: datasetUid!,
        rows,
      })
    },
    onSuccess: () => {
      setInfo('Import gespeichert')
      setError(null)
      onApplied?.()
    },
    onError: (err: any) => {
      setError(err?.message || 'Speichern fehlgeschlagen')
    },
  })

  const clearMutation = useMutation({
    mutationFn: async () => {
      return importDataAPI.clearData({
        table_name: tableName!,
        dataset_uid: datasetUid!,
      })
    },
    onSuccess: () => {
      setInfo('Daten geloescht')
      setError(null)
      setRows([])
      setPreview(null)
    },
    onError: (err: any) => {
      setError(err?.message || 'Daten loeschen fehlgeschlagen')
    },
  })

  const configMutation = useMutation({
    mutationFn: async () => {
      const matchKeys = matchKeysText
        .split(',')
        .map((x) => x.trim())
        .filter(Boolean)

      let overrides: Record<string, any> | undefined
      if (headerOverridesText.trim()) {
        overrides = JSON.parse(headerOverridesText)
      }

      const normalizedColumns: Record<string, any> = {}
      const usedKeys = new Set<string>()
      const errors: string[] = []

      Object.entries(columnsMap || {}).forEach(([uid, cfg]) => {
        if (uid === templateUid) {
          if (cfg && typeof cfg === 'object') normalizedColumns[uid] = { ...cfg }
          return
        }
        const data = cfg && typeof cfg === 'object' ? { ...cfg } : {}
        const key = String(data.key || data.label || '').trim()
        const label = String(data.label || key).trim()
        if (!key) {
          errors.push('Spalten-Key fehlt')
          return
        }
        const keyNorm = key.toLowerCase()
        if (usedKeys.has(keyNorm)) {
          errors.push(`Duplicate Spalten-Key: ${key}`)
          return
        }
        usedKeys.add(keyNorm)
        data.key = key
        data.label = label
        if (data.aliases && !Array.isArray(data.aliases)) {
          data.aliases = [data.aliases]
        }
        normalizedColumns[uid] = data
      })

      if (errors.length > 0) {
        throw new Error(errors[0])
      }

      return importDataAPI.updateConfig({
        table_name: tableName!,
        dataset_uid: datasetUid!,
        columns_map: normalizedColumns,
        root_patch: {
          MATCH_KEYS: matchKeys,
          CONFLICT_POLICY: conflictPolicy,
          HAS_HEADERS: hasHeaders,
          CUSTOM_HEADERS: customHeadersText
            .split(',')
            .map((x) => x.trim())
            .filter(Boolean),
          HEADER_OVERRIDES: overrides || {},
        },
      })
    },
    onSuccess: (data) => {
      setInfo('Konfiguration gespeichert')
      setError(null)
      const root = (data.daten || {}).ROOT || {}
      setHasHeaders(root.HAS_HEADERS !== false)
    },
    onError: (err: any) => {
      setError(err?.message || 'Konfiguration speichern fehlgeschlagen')
    },
  })

  const columns = useMemo(() => preview?.canonical_headers || [], [preview?.canonical_headers])

  const elementEntries = useMemo(() => {
    return Object.entries(columnsMap || {}).map(([uid, cfg]) => ({
      uid,
      cfg: cfg && typeof cfg === 'object' ? cfg : {},
    }))
  }, [columnsMap])

  const elementTemplate = useMemo(() => {
    const t = columnsMap['55555555-5555-5555-5555-555555555555']
    if (t && typeof t === 'object') return t
    return {
      label: '',
      key: '',
      type: 'str',
      required: false,
      source: 'base',
      aliases: [],
    }
  }, [columnsMap])

  const elementLabel = (cfg: Record<string, any>) => {
    const label = String(cfg?.label || '').trim()
    return label || String(cfg?.key || '').trim() || 'Unbenannt'
  }

  const openElement = (uid: string) => {
    const cfg = columnsMap[uid]
    if (!cfg || typeof cfg !== 'object') return
    setActiveElementId(uid)
    setElementDraft({ ...cfg })
    setElementOpen(true)
  }

  const addElement = () => {
    const uid = (window as any)?.crypto?.randomUUID?.() ||
      'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
        const r = (Math.random() * 16) | 0
        const v = c === 'x' ? r : (r & 0x3) | 0x8
        return v.toString(16)
      })
    const next = { ...elementTemplate }
    next.label = next.label || 'Neue Spalte'
    next.key = next.key || ''
    setColumnsMap((prev) => ({ ...prev, [uid]: next }))
    openElement(uid)
  }

  const deleteElement = (uid: string) => {
    setColumnsMap((prev) => {
      const next = { ...prev }
      delete next[uid]
      return next
    })
  }

  const elementBaseFields = ['label', 'key', 'type', 'required', 'source', 'aliases']
  const elementExtraFields = useMemo(() => {
    const draft = elementDraft || {}
    return Object.keys(draft)
      .filter((k) => !elementBaseFields.includes(k))
      .sort()
  }, [elementDraft])

  const toFieldValue = (value: any) => {
    if (Array.isArray(value)) return value.join(', ')
    if (value && typeof value === 'object') return JSON.stringify(value, null, 2)
    return value ?? ''
  }

  const parseFieldValue = (key: string, value: any, original: any) => {
    if (typeof original === 'boolean') return !!value
    if (Array.isArray(original)) {
      return String(value || '')
        .split(',')
        .map((x) => x.trim())
        .filter(Boolean)
    }
    if (original && typeof original === 'object') {
      try {
        return JSON.parse(String(value || ''))
      } catch {
        return original
      }
    }
    if (key === 'required') return !!value
    return value
  }

  const removeRow = (index: number) => {
    setRows((prev) => prev.filter((_, idx) => idx !== index))
  }

  return (
    <div className="pdvm-dialog__import">
      {!hideSteps ? <PdvmImportDataSteps step={activeStep} onChange={setActiveStep} /> : null}

      {activeStep === 1 ? (
        <div className="pdvm-dialog__importConfig">
          <div className="pdvm-dialog__importRow">
            <label className="pdvm-dialog__importLabel">Spalten (elemente_list)</label>
            <div className="pdvm-dialog__elementList">
              {elementEntries.map(({ uid, cfg }) => (
                <div key={uid} className="pdvm-dialog__elementItem" title={JSON.stringify(cfg, null, 2)}>
                  <div className="pdvm-dialog__elementLabel">{elementLabel(cfg)}</div>
                  <div className="pdvm-dialog__elementActions">
                    <button type="button" className="pdvm-dialog__toolBtn" onClick={() => openElement(uid)}>
                      Bearbeiten
                    </button>
                    <button type="button" className="pdvm-dialog__toolBtn" onClick={() => deleteElement(uid)}>
                      Entfernen
                    </button>
                  </div>
                </div>
              ))}
              <button type="button" className="pdvm-dialog__toolBtn" onClick={addElement}>
                + Spalte hinzufuegen
              </button>
            </div>
          </div>
          <div className="pdvm-dialog__importRow">
            <label className="pdvm-dialog__importLabel">Match Keys</label>
            <input
              value={matchKeysText}
              onChange={(e) => setMatchKeysText(e.target.value)}
              placeholder="z.B. ISO2, ISO3"
              className="pdvm-dialog__toolInput"
            />
          </div>
          <div className="pdvm-dialog__importRow">
            <label className="pdvm-dialog__importLabel">Konfliktstrategie</label>
            <select value={conflictPolicy} onChange={(e) => setConflictPolicy(e.target.value)} className="pdvm-dialog__toolInput">
              <option value="base_wins">base_wins</option>
              <option value="update_wins">update_wins</option>
              <option value="insert_new_only">insert_new_only</option>
              <option value="new_record_on_conflict">new_record_on_conflict</option>
              <option value="field_priority">field_priority</option>
            </select>
          </div>
          <div className="pdvm-dialog__importRow">
            <label className="pdvm-dialog__importLabel">Header vorhanden</label>
            <label className="pdvm-dialog__importToggle">
              <input type="checkbox" checked={hasHeaders} onChange={(e) => setHasHeaders(e.target.checked)} />
              <span>Erste Zeile als Header verwenden</span>
            </label>
          </div>
          {!hasHeaders ? (
            <div className="pdvm-dialog__importRow">
              <label className="pdvm-dialog__importLabel">Custom Headers</label>
              <input
                value={customHeadersText}
                onChange={(e) => setCustomHeadersText(e.target.value)}
                placeholder="z.B. ISO2, ISO3, LANDNAME"
                className="pdvm-dialog__toolInput"
              />
            </div>
          ) : null}
          <div className="pdvm-dialog__importRow">
            <label className="pdvm-dialog__importLabel">HEADER_OVERRIDES (JSON)</label>
            <textarea
              value={headerOverridesText}
              onChange={(e) => setHeaderOverridesText(e.target.value)}
              placeholder='{"ISO2": "Land ISO2"}'
              className="pdvm-dialog__importTextarea"
              rows={4}
            />
          </div>

          <div className="pdvm-dialog__importActions">
            <button type="button" className="pdvm-dialog__toolBtn" onClick={() => configMutation.mutate()}>
              Konfiguration speichern
            </button>
            <button type="button" className="pdvm-dialog__toolBtn pdvm-dialog__toolBtn--primary" onClick={() => setActiveStep(2)}>
              Weiter
            </button>
          </div>
        </div>
      ) : null}

      {activeStep === 2 ? (
        <div className="pdvm-dialog__importUpload">
          <div className="pdvm-dialog__importToolbar">
            <div className="pdvm-dialog__importRow">
              <label className="pdvm-dialog__importLabel">Datei</label>
              <input
                type="file"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                className="pdvm-dialog__importFile"
              />
            </div>
            <div className="pdvm-dialog__importRow">
              <label className="pdvm-dialog__importLabel">Sheet</label>
              <input
                value={sheetName}
                onChange={(e) => setSheetName(e.target.value)}
                placeholder="Optional (XLSX)"
                className="pdvm-dialog__toolInput"
              />
            </div>
            <div className="pdvm-dialog__importActions">
              <button
                type="button"
                className="pdvm-dialog__toolBtn"
                onClick={() => previewMutation.mutate()}
                disabled={!canPreview || previewMutation.isPending}
              >
                Vorschau
              </button>
              <button type="button" className="pdvm-dialog__toolBtn pdvm-dialog__toolBtn--primary" onClick={() => setActiveStep(3)}>
                Weiter
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {activeStep === 3 ? (
        <div className="pdvm-dialog__importApply">
          <div className="pdvm-dialog__importActions">
            <button type="button" className="pdvm-dialog__toolBtn" onClick={() => setActiveStep(2)}>
              Zurueck
            </button>
            <button
              type="button"
              className="pdvm-dialog__toolBtn"
              onClick={() => setClearConfirmOpen(true)}
              disabled={!tableName || !datasetUid || clearMutation.isPending}
            >
              Daten loeschen
            </button>
            <button
              type="button"
              className="pdvm-dialog__toolBtn pdvm-dialog__toolBtn--primary"
              onClick={() => applyMutation.mutate()}
              disabled={!tableName || !datasetUid || rows.length === 0 || applyMutation.isPending}
            >
              Speichern
            </button>
          </div>
          <div className="pdvm-dialog__importNotice">Zeilen in Vorschau: {rows.length}</div>
        </div>
      ) : null}

      {error ? <div className="pdvm-dialog__importError">{error}</div> : null}
      {info ? <div className="pdvm-dialog__importInfo">{info}</div> : null}

      {preview?.unmatched_headers?.length ? (
        <div className="pdvm-dialog__importNotice">
          Nicht zugeordnete Header: {preview.unmatched_headers.join(', ')}
        </div>
      ) : null}

      <div className="pdvm-dialog__importTableWrap">
        {columns.length === 0 ? (
          <div className="pdvm-dialog__importEmpty">Keine Vorschau geladen.</div>
        ) : (
          <table className="pdvm-dialog__importTable">
            <thead>
              <tr>
                <th style={{ width: 64 }}>Aktion</th>
                {columns.map((c) => (
                  <th key={c}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, idx) => (
                <tr key={idx}>
                  <td>
                    <button type="button" className="pdvm-dialog__toolBtn" onClick={() => removeRow(idx)}>
                      Entfernen
                    </button>
                  </td>
                  {columns.map((c) => (
                    <td key={c}>{String(row?.[c] ?? '')}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {elementOpen && elementDraft ? (
        <div className="pdvm-modal__overlay" role="dialog" aria-modal="true">
          <div className="pdvm-modal">
            <div className="pdvm-modal__header">
              <div className="pdvm-modal__title">Spalte bearbeiten</div>
              <button type="button" className="pdvm-modal__close" onClick={() => setElementOpen(false)}>
                ×
              </button>
            </div>
            <div className="pdvm-modal__body">
              <div className="pdvm-modal__fields">
                <div className="pdvm-dialog__importNotice">Basis</div>
                {elementBaseFields.map((field) => {
                  if (!(field in elementDraft)) return null
                  const original = elementDraft[field]
                  const rawValue = toFieldValue(original)
                  const type = typeof original === 'boolean' ? 'true_false' : 'string'
                  const isLong = typeof rawValue === 'string' && rawValue.length > 60
                  const inputType = isLong || typeof original === 'object' ? 'text' : type
                  return (
                    <PdvmInputControl
                      key={field}
                      label={field}
                      type={inputType as any}
                      value={rawValue}
                      onChange={(value) => {
                        setElementDraft((prev) => {
                          const base = prev || {}
                          return { ...base, [field]: parseFieldValue(field, value, original) }
                        })
                      }}
                    />
                  )
                })}
                {elementExtraFields.length > 0 ? <div className="pdvm-dialog__importNotice">Weitere</div> : null}
                {elementExtraFields.map((field) => {
                  const original = elementDraft[field]
                  const rawValue = toFieldValue(original)
                  const type = typeof original === 'boolean' ? 'true_false' : 'string'
                  const isLong = typeof rawValue === 'string' && rawValue.length > 60
                  const inputType = isLong || typeof original === 'object' ? 'text' : type
                  return (
                    <PdvmInputControl
                      key={field}
                      label={field}
                      type={inputType as any}
                      value={rawValue}
                      onChange={(value) => {
                        setElementDraft((prev) => {
                          const base = prev || {}
                          return { ...base, [field]: parseFieldValue(field, value, original) }
                        })
                      }}
                    />
                  )
                })}
              </div>
            </div>
            <div className="pdvm-modal__footer">
              <button type="button" className="pdvm-modal__btn" onClick={() => setElementOpen(false)}>
                Abbrechen
              </button>
              <button
                type="button"
                className="pdvm-modal__btn pdvm-modal__btn--primary"
                onClick={() => {
                  if (activeElementId) {
                    setColumnsMap((prev) => ({ ...prev, [activeElementId]: elementDraft }))
                  }
                  setElementOpen(false)
                }}
              >
                Speichern
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <PdvmDialogModal
        open={clearConfirmOpen}
        kind="confirm"
        title="Daten loeschen"
        message="Soll die gesamte Tabelle wirklich geleert werden?"
        confirmLabel="Loeschen"
        cancelLabel="Abbrechen"
        busy={clearMutation.isPending}
        onCancel={() => setClearConfirmOpen(false)}
        onConfirm={async () => {
          setClearConfirmOpen(false)
          clearMutation.mutate()
        }}
      />
    </div>
  )
}
