import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { lookupsAPI } from '../../api/client'

export function PdvmLookupSelect(props: {
  table: string
  label?: string
  value: string | null
  onChange: (value: string | null) => void
  disabled?: boolean
}) {
  const [q, setQ] = useState('')

  const table = String(props.table || '').trim()
  const enabled = !!table

  const query = useQuery({
    queryKey: ['lookups', table, q],
    queryFn: () => lookupsAPI.get(table, { q: q.trim() || undefined, limit: 200, offset: 0 }),
    enabled,
  })

  const options = useMemo(() => {
    const rows = query.data?.rows || []
    return rows.map((r) => ({ value: String(r.uid), label: String(r.name || r.uid) }))
  }, [query.data?.rows])

  const current = String(props.value || '')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <input
          type="text"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Suchen…"
          disabled={props.disabled || query.isLoading || !enabled}
          style={{
            flex: 1,
            height: 30,
            borderRadius: 8,
            border: '1px solid var(--color-border-medium, rgba(0,0,0,0.24))',
            padding: '0 10px',
            font: 'inherit',
          }}
        />
        <div style={{ fontSize: 12, opacity: 0.75 }}>{query.isLoading ? 'Lade…' : `${options.length}`}</div>
      </div>

      <select
        value={current}
        disabled={props.disabled || query.isLoading || !enabled}
        onChange={(e) => {
          const v = String(e.target.value || '').trim()
          props.onChange(v ? v : null)
        }}
        style={{
          height: 34,
          borderRadius: 8,
          border: '1px solid var(--color-border-medium, rgba(0,0,0,0.24))',
          padding: '0 10px',
          font: 'inherit',
          background: 'var(--color-background-primary, white)',
        }}
      >
        <option value="">(bitte auswählen)</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>

      {query.isError ? <div style={{ color: 'crimson', fontSize: 12 }}>Lookup Fehler</div> : null}
    </div>
  )
}
