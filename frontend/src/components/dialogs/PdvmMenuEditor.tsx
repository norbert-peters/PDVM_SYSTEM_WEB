import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { menuEditorAPI, type MenuRecordResponse } from '../../api/client'

type MenuGroup = 'GRUND' | 'VERTIKAL'

type MenuItem = {
  type?: string
  label?: string
  icon?: string
  sort_order?: number
  parent_guid?: string | null
  template_guid?: string | null
  command?: any
}

function asObject(value: any): Record<string, any> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, any>) : {}
}

function normalizeGuid(value: any): string {
  return String(value || '').trim()
}

function newGuid(): string {
  const w: any = window as any
  const uuid = w?.crypto?.randomUUID
  if (typeof uuid === 'function') return uuid.call(w.crypto)

  // Fallback (RFC4122 v4-ish)
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

function getChildren(itemsByUid: Record<string, MenuItem>, parentGuid: string | null): Array<[string, MenuItem]> {
  const out: Array<[string, MenuItem]> = []
  for (const [uid, item] of Object.entries(itemsByUid)) {
    const p = normalizeGuid(item?.parent_guid)
    if ((parentGuid == null && !p) || (parentGuid != null && p === parentGuid)) {
      out.push([uid, item])
    }
  }
  out.sort((a, b) => Number(a[1]?.sort_order || 0) - Number(b[1]?.sort_order || 0))
  return out
}

function hasChildren(itemsByUid: Record<string, MenuItem>, uid: string): boolean {
  const u = normalizeGuid(uid)
  for (const item of Object.values(itemsByUid)) {
    if (normalizeGuid(item?.parent_guid) === u) return true
  }
  return false
}

function resequenceSortOrder(itemsByUid: Record<string, MenuItem>, parentGuid: string | null): Record<string, MenuItem> {
  const siblings = getChildren(itemsByUid, parentGuid)
  const next: Record<string, MenuItem> = { ...itemsByUid }
  siblings.forEach(([uid, item], idx) => {
    next[uid] = { ...item, sort_order: (idx + 1) * 10 }
  })
  return next
}

function reorderSiblings(itemsByUid: Record<string, MenuItem>, parentGuid: string | null, dragUid: string, dropUid: string) {
  const siblings = getChildren(itemsByUid, parentGuid)
  const ids = siblings.map(([uid]) => uid)
  const from = ids.indexOf(dragUid)
  const to = ids.indexOf(dropUid)
  if (from < 0 || to < 0 || from === to) return itemsByUid

  const nextIds = [...ids]
  const [moved] = nextIds.splice(from, 1)
  nextIds.splice(to, 0, moved)

  const next: Record<string, MenuItem> = { ...itemsByUid }
  nextIds.forEach((uid, idx) => {
    next[uid] = { ...next[uid], sort_order: (idx + 1) * 10 }
  })
  return next
}

function insertSibling(
  itemsByUid: Record<string, MenuItem>,
  parentGuid: string | null,
  targetUid: string,
  position: 'before' | 'after',
  newUid: string,
  newItem: MenuItem
): Record<string, MenuItem> {
  const siblings = getChildren(itemsByUid, parentGuid)
  const ids = siblings.map(([uid]) => uid)
  const idx = ids.indexOf(targetUid)
  if (idx < 0) return { ...itemsByUid, [newUid]: newItem }

  const nextIds = [...ids]
  nextIds.splice(position === 'before' ? idx : idx + 1, 0, newUid)

  const next: Record<string, MenuItem> = { ...itemsByUid, [newUid]: newItem }
  nextIds.forEach((uid, i) => {
    next[uid] = { ...(next[uid] || {}), sort_order: (i + 1) * 10 }
  })
  return next
}

export function PdvmMenuEditor(props: { menuGuid: string; group: MenuGroup; onMissingMenuGuid?: (uid: string) => void }) {
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<MenuRecordResponse | null>(null)
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set())

  const menuQuery = useQuery<MenuRecordResponse>({
    queryKey: ['menu-editor', 'menu', props.menuGuid],
    queryFn: () => menuEditorAPI.getMenu(props.menuGuid),
    enabled: !!props.menuGuid,
  })

  // Self-healing: if a menu GUID was restored (e.g. via last_call) but the record no longer exists,
  // tell the parent so it can reset selection and clear persisted last_call.
  useEffect(() => {
    if (!menuQuery.isError) return
    const status = (menuQuery.error as any)?.response?.status
    if (status !== 404) return
    if (!props.menuGuid) return
    props.onMissingMenuGuid?.(props.menuGuid)
  }, [menuQuery.isError, menuQuery.error, props.menuGuid, props.onMissingMenuGuid])

  // Reset local state when switching to another menu GUID
  useEffect(() => {
    setDraft(null)
    setCollapsed(new Set())
  }, [props.menuGuid])

  // Sync draft from query result
  useEffect(() => {
    if (!menuQuery.data) return
    setDraft(menuQuery.data)
  }, [menuQuery.data])

  const menu = draft ?? menuQuery.data ?? null

  const groupItems = useMemo(() => {
    const daten = asObject(menu?.daten)
    const raw = asObject(daten[props.group])
    return raw as Record<string, MenuItem>
  }, [menu?.daten, props.group])

  const rootItems = useMemo(() => {
    const daten = asObject(menu?.daten)
    return asObject(daten['ROOT'])
  }, [menu?.daten])

  const updateMutation = useMutation({
    mutationFn: async (nextDaten: Record<string, any>) => {
      return menuEditorAPI.updateMenu(props.menuGuid, { daten: nextDaten })
    },
    onSuccess: async (saved) => {
      setDraft(saved)
      await queryClient.invalidateQueries({ queryKey: ['menu-editor', 'menu', props.menuGuid] })
    },
  })

  const setGroupItems = (nextGroupItems: Record<string, MenuItem>) => {
    setDraft((prev) => {
      const base = prev ?? menuQuery.data
      if (!base) return prev
      const nextDaten = { ...asObject(base.daten), [props.group]: nextGroupItems }
      return { ...base, daten: nextDaten }
    })
  }

  const save = async () => {
    const base = menu
    if (!base) return
    const nextDaten = { ...asObject(base.daten), ROOT: rootItems, [props.group]: groupItems }
    await updateMutation.mutateAsync(nextDaten)
  }

  const toggleCollapsed = (uid: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(uid)) next.delete(uid)
      else next.add(uid)
      return next
    })
  }

  const expandAll = () => setCollapsed(new Set())
  const collapseAll = () => {
    const next = new Set<string>()
    for (const uid of Object.keys(groupItems)) {
      if (hasChildren(groupItems, uid)) next.add(uid)
    }
    setCollapsed(next)
  }

  const addRootItem = () => {
    const uid = newGuid()
    const newItem: MenuItem = {
      type: 'item',
      label: 'Neues MenüItem',
      parent_guid: null,
      sort_order: 10,
    }
    const next = { ...groupItems, [uid]: newItem }
    setGroupItems(resequenceSortOrder(next, null))
  }

  const addSibling = (targetUid: string, position: 'before' | 'after') => {
    const target = groupItems[targetUid]
    if (!target) return
    const parent = normalizeGuid(target.parent_guid)
    const parentGuid = parent ? parent : null

    const uid = newGuid()
    const newItem: MenuItem = {
      type: 'item',
      label: 'Neues MenüItem',
      parent_guid: parentGuid,
      sort_order: 0,
    }
    const next = insertSibling(groupItems, parentGuid, targetUid, position, uid, newItem)
    setGroupItems(next)
  }

  const addChild = (parentUid: string) => {
    const uid = newGuid()
    const newItem: MenuItem = {
      type: 'item',
      label: 'Neues MenüItem',
      parent_guid: parentUid,
      sort_order: 0,
    }
    const next = { ...groupItems, [uid]: newItem }
    setGroupItems(resequenceSortOrder(next, parentUid))
    setCollapsed((prev) => {
      const s = new Set(prev)
      s.delete(parentUid)
      return s
    })
  }

  const moveUp = (uid: string) => {
    const item = groupItems[uid]
    if (!item) return
    const parent = normalizeGuid(item.parent_guid)
    const parentGuid = parent ? parent : null
    const siblings = getChildren(groupItems, parentGuid)
    const ids = siblings.map(([x]) => x)
    const idx = ids.indexOf(uid)
    if (idx <= 0) return
    const above = ids[idx - 1]
    setGroupItems(reorderSiblings(groupItems, parentGuid, uid, above))
  }

  const moveDown = (uid: string) => {
    const item = groupItems[uid]
    if (!item) return
    const parent = normalizeGuid(item.parent_guid)
    const parentGuid = parent ? parent : null
    const siblings = getChildren(groupItems, parentGuid)
    const ids = siblings.map(([x]) => x)
    const idx = ids.indexOf(uid)
    if (idx < 0 || idx >= ids.length - 1) return
    const below = ids[idx + 1]
    setGroupItems(reorderSiblings(groupItems, parentGuid, uid, below))
  }

  const indent = (uid: string) => {
    const item = groupItems[uid]
    if (!item) return
    const parent = normalizeGuid(item.parent_guid)
    const parentGuid = parent ? parent : null
    const siblings = getChildren(groupItems, parentGuid)
    const ids = siblings.map(([x]) => x)
    const idx = ids.indexOf(uid)
    if (idx <= 0) return
    const newParent = ids[idx - 1]
    const next: Record<string, MenuItem> = { ...groupItems, [uid]: { ...(groupItems[uid] || {}), parent_guid: newParent } }
    setGroupItems(resequenceSortOrder(resequenceSortOrder(next, parentGuid), newParent))
    setCollapsed((prev) => {
      const s = new Set(prev)
      s.delete(newParent)
      return s
    })
  }

  const outdent = (uid: string) => {
    const item = groupItems[uid]
    if (!item) return
    const parentUid = normalizeGuid(item.parent_guid)
    if (!parentUid) return
    const parentItem = groupItems[parentUid]
    const grandParent = normalizeGuid(parentItem?.parent_guid)
    const grandParentGuid = grandParent ? grandParent : null
    const next: Record<string, MenuItem> = { ...groupItems, [uid]: { ...(groupItems[uid] || {}), parent_guid: grandParentGuid } }
    setGroupItems(resequenceSortOrder(resequenceSortOrder(next, parentUid), grandParentGuid))
  }

  const renderNode = (uid: string, item: MenuItem, level: number) => {
    const isParent = hasChildren(groupItems, uid)
    const isCollapsed = collapsed.has(uid)
    const label = String(item?.label || '').trim() || '(ohne Label)'

    return (
      <div
        key={uid}
        draggable
        onDragStart={(ev) => {
          ev.dataTransfer.setData('text/pdvm-drag-uid', uid)
          ev.dataTransfer.setData('text/pdvm-drag-parent', normalizeGuid(item?.parent_guid || ''))
        }}
        onDragOver={(ev) => {
          ev.preventDefault()
        }}
        onDrop={(ev) => {
          ev.preventDefault()
          const dragUid = ev.dataTransfer.getData('text/pdvm-drag-uid')
          const dragParent = ev.dataTransfer.getData('text/pdvm-drag-parent')
          if (!dragUid || !groupItems[dragUid]) return
          if (dragUid === uid) return

          const dropParent = normalizeGuid(item?.parent_guid || '')
          const dropParentGuid = dropParent ? dropParent : null

          if (ev.shiftKey) {
            // Move into this node (become child)
            const oldParentGuid = normalizeGuid(dragParent) ? normalizeGuid(dragParent) : null
            const next: Record<string, MenuItem> = {
              ...groupItems,
              [dragUid]: { ...(groupItems[dragUid] || {}), parent_guid: uid },
            }
            setGroupItems(resequenceSortOrder(resequenceSortOrder(next, oldParentGuid), uid))
            setCollapsed((prev) => {
              const s = new Set(prev)
              s.delete(uid)
              return s
            })
            return
          }

          // Default: reorder within the drop target's parent level (and allow cross-level by adopting dropParent)
          const oldParentGuid = normalizeGuid(dragParent) ? normalizeGuid(dragParent) : null
          let next: Record<string, MenuItem> = { ...groupItems }
          if (oldParentGuid !== dropParentGuid) {
            next[dragUid] = { ...(next[dragUid] || {}), parent_guid: dropParentGuid }
            next = resequenceSortOrder(next, oldParentGuid)
          }
          next = reorderSiblings(next, dropParentGuid, dragUid, uid)
          setGroupItems(next)
        }}
        style={{
          border: '1px solid rgba(255,255,255,0.08)',
          borderRadius: 10,
          padding: 10,
          marginBottom: 8,
          background: 'rgba(255,255,255,0.03)',
          marginLeft: level * 18,
        }}
        title="Drag & Drop: gleiche Ebene sortieren. Shift+Drop: als Kind einhängen."
      >
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          {isParent ? (
            <button type="button" onClick={() => toggleCollapsed(uid)} title={isCollapsed ? 'Aufklappen' : 'Zuklappen'}>
              {isCollapsed ? '▸' : '▾'}
            </button>
          ) : (
            <span style={{ width: 26, display: 'inline-block' }} />
          )}

          <div style={{ fontWeight: 800 }}>{label}</div>

          <div style={{ marginLeft: 'auto', display: 'flex', gap: 6, alignItems: 'center' }}>
            <button type="button" onClick={() => addSibling(uid, 'before')} title="Neues Item oberhalb einfügen">
              +↑
            </button>
            <button type="button" onClick={() => addSibling(uid, 'after')} title="Neues Item unterhalb einfügen">
              +↓
            </button>
            <button type="button" onClick={() => addChild(uid)} title="Neues Kind-Item einfügen">
              +Kind
            </button>
            <button type="button" onClick={() => moveUp(uid)} title="Nach oben">
              ↑
            </button>
            <button type="button" onClick={() => moveDown(uid)} title="Nach unten">
              ↓
            </button>
            <button type="button" onClick={() => indent(uid)} title="Einrücken (Ebene tiefer)">
              →
            </button>
            <button type="button" onClick={() => outdent(uid)} title="Ausrücken (Ebene höher)">
              ←
            </button>
            <button
              type="button"
              onClick={() => {
                alert('Bearbeiten (Stufe 2): kommt als nächstes. Hier aktuell nur Struktur / Reihenfolge / Einfügen.')
              }}
              title="Bearbeiten (Stufe 2)"
            >
              ✎
            </button>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 10, marginTop: 6, fontSize: 12, opacity: 0.75 }}>
          <div style={{ fontFamily: 'monospace' }}>{uid}</div>
          <div style={{ marginLeft: 'auto' }}>sort: {item?.sort_order ?? '-'}</div>
        </div>
      </div>
    )
  }

  const renderTree = (parentGuid: string | null, level: number) => {
    const children = getChildren(groupItems, parentGuid)
    if (!children.length) return null

    return (
      <div>
        {children.map(([uid, item]) => {
          const isParent = hasChildren(groupItems, uid)
          const isCollapsed = collapsed.has(uid)
          return (
            <div key={uid}>
              {renderNode(uid, item, level)}
              {isParent && isCollapsed ? null : renderTree(uid, level + 1)}
            </div>
          )
        })}
      </div>
    )
  }

  if (menuQuery.isLoading) return <div>Lade Menü…</div>
  if (menuQuery.isError)
    return (
      <div style={{ color: 'crimson' }}>
        Fehler: {(menuQuery.error as any)?.message || 'Menü konnte nicht geladen werden'}
      </div>
    )
  if (!menu)
    return (
      <div style={{ opacity: 0.85 }}>
        Kein Menü geladen. (UID: <span style={{ fontFamily: 'monospace' }}>{props.menuGuid}</span>)
      </div>
    )

  const itemCount = Object.keys(groupItems).length

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
        <div style={{ fontSize: 12, opacity: 0.75 }}>
          Menü: <span style={{ fontFamily: 'monospace' }}>{menu.uid}</span>
        </div>
        <div style={{ fontSize: 12, opacity: 0.75 }}>Gruppe: {props.group}</div>
        <div style={{ fontSize: 12, opacity: 0.75 }}>Items: {itemCount}</div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button type="button" onClick={addRootItem}>
            + Root
          </button>
          <button type="button" onClick={expandAll}>
            Alles aufklappen
          </button>
          <button type="button" onClick={collapseAll}>
            Alles zuklappen
          </button>
          <button type="button" onClick={() => setGroupItems(resequenceSortOrder(groupItems, null))}>
            Sort neu nummerieren
          </button>
          <button type="button" onClick={save} disabled={updateMutation.isPending}>
            {updateMutation.isPending ? 'Speichere…' : 'Speichern'}
          </button>
        </div>
      </div>

      {itemCount === 0 ? <div style={{ opacity: 0.8 }}>Noch keine Items. Mit “+ Root” anfangen.</div> : null}

      {renderTree(null, 0)}
    </div>
  )
}
