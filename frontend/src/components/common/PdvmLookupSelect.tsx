import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { lookupsAPI } from '../../api/client'

type LookupOption = {
  value: string
  label: string
}

export function PdvmLookupSelect(props: {
  table: string
  label?: string
  value: string | null
  onChange: (value: string | null) => void
  disabled?: boolean
  filterOption?: (row: any) => boolean
}) {
  const [q, setQ] = useState('')
  const [qDebounced, setQDebounced] = useState('')
  const [listOpen, setListOpen] = useState(false)
  const [highlightIndex, setHighlightIndex] = useState(0)
  const [showMissingTableHint, setShowMissingTableHint] = useState(false)
  const inputRef = useRef<HTMLInputElement | null>(null)
  const listRef = useRef<HTMLDivElement | null>(null)

  const table = String(props.table || '').trim()
  const hasTable = !!table

  const query = useQuery({
    queryKey: ['lookups', table, qDebounced],
    queryFn: () => lookupsAPI.get(table, { q: qDebounced.trim() || undefined, limit: 200, offset: 0 }),
    enabled: hasTable,
  })

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setQDebounced(q)
    }, 500)

    return () => window.clearTimeout(timer)
  }, [q])

  const options = useMemo<LookupOption[]>(() => {
    const rows = query.data?.rows || []
    const filtered = props.filterOption ? rows.filter((r: any) => props.filterOption!(r)) : rows
    return filtered.map((r: any) => ({ value: String(r.uid), label: String(r.name || r.uid) }))
  }, [query.data?.rows, props.filterOption])

  const displayOptions = useMemo<LookupOption[]>(() => {
    return [{ value: '', label: '(bitte auswählen)' }, ...options]
  }, [options])

  const current = String(props.value || '')
  const currentLabel = useMemo(() => {
    const selected = displayOptions.find((o) => o.value === current)
    if (selected) return selected.label
    return current ? current : '(bitte auswählen)'
  }, [displayOptions, current])

  useEffect(() => {
    if (!listOpen) return

    const selectedLabel = displayOptions.find((o) => o.value === current)?.label || ''
    const qNorm = qDebounced.trim().toLowerCase()
    const selectedNorm = selectedLabel.trim().toLowerCase()

    // Ohne Suchtext: auf aktuellen Wert positionieren, wenn vorhanden.
    if ((!qNorm || (selectedNorm && qNorm === selectedNorm)) && current) {
      const idx = displayOptions.findIndex((o) => o.value === current)
      setHighlightIndex(idx >= 0 ? idx : 0)
      return
    }

    // Mit Suchtext: auf ersten Treffer positionieren.
    setHighlightIndex(displayOptions.length ? 0 : -1)
  }, [listOpen, qDebounced, current, displayOptions])

  useEffect(() => {
    if (!listOpen) return
    const listEl = listRef.current
    if (!listEl) return
    const active = listEl.querySelector<HTMLElement>(`[data-lookup-index="${highlightIndex}"]`)
    active?.scrollIntoView({ block: 'nearest' })
  }, [highlightIndex, listOpen])

  const confirmSelection = (option: LookupOption) => {
    setListOpen(false)
    props.onChange(option.value ? option.value : null)
    setQ(option.label === '(bitte auswählen)' ? '' : option.label)
    window.setTimeout(() => inputRef.current?.focus(), 0)
  }

  const canInteract = !props.disabled

  useEffect(() => {
    if (hasTable && showMissingTableHint) {
      setShowMissingTableHint(false)
    }
  }, [hasTable, showMissingTableHint])

  const onInputKeyDown: React.KeyboardEventHandler<HTMLInputElement> = (e) => {
    if (!canInteract) return
    if (!hasTable) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Enter') {
        e.preventDefault()
        setShowMissingTableHint(true)
      }
      if (e.key === 'Escape') {
        setListOpen(false)
      }
      return
    }

    if (e.key === 'ArrowDown') {
      e.preventDefault()
      if (!listOpen) setListOpen(true)
      setHighlightIndex((prev) => {
        const max = displayOptions.length - 1
        if (max < 0) return -1
        return Math.min(max, Math.max(0, prev + 1))
      })
      return
    }

    if (e.key === 'ArrowUp') {
      e.preventDefault()
      if (!listOpen) setListOpen(true)
      setHighlightIndex((prev) => Math.max(0, prev - 1))
      return
    }

    if (e.key === 'Enter') {
      if (!listOpen) return
      e.preventDefault()
      const candidate = displayOptions[highlightIndex]
      if (candidate) confirmSelection(candidate)
      return
    }

    if (e.key === 'Escape') {
      setListOpen(false)
      return
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, width: '100%' }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 8, alignItems: 'center', width: '100%' }}>
        <input
          ref={inputRef}
          type="text"
          value={q}
          onChange={(e) => {
            setQ(e.target.value)
            if (!canInteract) return
            if (!hasTable) {
              setListOpen(false)
              setShowMissingTableHint(true)
              return
            }
            setListOpen(true)
          }}
          onFocus={() => {
            if (!canInteract) return
            if (!hasTable) {
              setListOpen(false)
              setShowMissingTableHint(true)
              return
            }
            setListOpen(true)
          }}
          onKeyDown={onInputKeyDown}
          placeholder="Suchen…"
          disabled={!canInteract}
          style={{
            width: '100%',
            height: 34,
            borderRadius: 8,
            border: '1px solid var(--color-border-medium, rgba(0,0,0,0.24))',
            padding: '8px 10px',
            font: 'inherit',
            boxSizing: 'border-box',
          }}
        />
      </div>

      {!listOpen ? (
        <div
          role="button"
          tabIndex={0}
          onClick={() => {
            if (!canInteract) return
            if (!hasTable) {
              setShowMissingTableHint(true)
              return
            }
            setListOpen(true)
            window.setTimeout(() => inputRef.current?.focus(), 0)
          }}
          onKeyDown={(e) => {
            if (!canInteract) return
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              if (!hasTable) {
                setShowMissingTableHint(true)
                return
              }
              setListOpen(true)
              window.setTimeout(() => inputRef.current?.focus(), 0)
            }
          }}
          style={{
            width: '100%',
            minHeight: 34,
            borderRadius: 8,
            border: '1px solid var(--color-border-medium, rgba(0,0,0,0.24))',
            padding: '8px 10px',
            font: 'inherit',
            background: 'var(--color-background-primary, white)',
            boxSizing: 'border-box',
            cursor: canInteract ? 'pointer' : 'default',
            opacity: current ? 1 : 0.8,
          }}
          title="Aktuelle Auswahl"
        >
          {currentLabel}
        </div>
      ) : null}

      {showMissingTableHint ? (
        <div style={{ color: '#b42318', fontSize: 12 }}>
          Keine Lookup-Tabelle konfiguriert. Bitte `CONFIGS.go_select_view.table` setzen.
        </div>
      ) : null}

      {listOpen ? (
        <div
          ref={listRef}
          style={{
            width: '100%',
            maxHeight: 240,
            overflowY: 'auto',
            borderRadius: 8,
            border: '1px solid var(--color-border-medium, rgba(0,0,0,0.24))',
            background: 'var(--color-background-primary, white)',
            boxSizing: 'border-box',
          }}
        >
          {query.isLoading ? (
            <div style={{ padding: '8px 10px', fontSize: 12, opacity: 0.8 }}>Lade...</div>
          ) : displayOptions.length ? (
            displayOptions.map((o, idx) => {
              const selected = o.value === current
              const active = idx === highlightIndex
              return (
                <div
                  key={`${o.value || '__empty__'}-${idx}`}
                  data-lookup-index={idx}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => confirmSelection(o)}
                  style={{
                    padding: '8px 10px',
                    cursor: 'pointer',
                    font: 'inherit',
                    background: active ? 'rgba(34, 116, 71, 0.14)' : 'transparent',
                    borderTop: idx > 0 ? '1px solid rgba(0,0,0,0.06)' : 'none',
                    fontWeight: selected ? 700 : 400,
                  }}
                >
                  {o.label}
                </div>
              )
            })
          ) : (
            <div style={{ padding: '8px 10px', fontSize: 12, opacity: 0.75 }}>Keine Treffer</div>
          )}
        </div>
      ) : null}

      {query.isError ? <div style={{ color: 'crimson', fontSize: 12 }}>Lookup Fehler</div> : null}
    </div>
  )
}
