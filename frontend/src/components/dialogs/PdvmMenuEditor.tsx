import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { menuEditorAPI, systemdatenAPI, type MenuCommandDefinition, type MenuRecordResponse } from '../../api/client'
import { PdvmDialogModal } from '../common/PdvmDialogModal'
import { PdvmInputControl } from '../common/PdvmInputControl'
import { PdvmInputModal } from '../common/PdvmInputModal'
import { PdvmLookupSelect } from '../common/PdvmLookupSelect'
import { MENU_ICON_OPTIONS, renderMenuIcon } from '../menu/menuIcons'

type MenuGroup = 'GRUND' | 'VERTIKAL' | 'TEMPLATE'

type MenuItem = {
  type?: string
  label?: string
  icon?: string
  tooltip?: string | null
  enabled?: boolean
  visible?: boolean
  sort_order?: number
  parent_guid?: string | null
  template_guid?: string | null
  command?: any
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
  source_path?: string
  historical?: boolean
  abdatum?: boolean
  configs?: Record<string, any>
}

function asObject(value: any): Record<string, any> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, any>) : {}
}

function asArray(value: any): any[] {
  return Array.isArray(value) ? value : []
}

function normalizeUpper(value: any): string {
  return String(value || '').trim().toUpperCase()
}

function normalizeGuid(value: any): string {
  return String(value || '').trim()
}

function getCommandHandler(command: any): string {
  if (!command) return ''
  if (typeof command === 'string') return String(command).trim()
  if (typeof command === 'object') return String((command as any)?.handler || '').trim()
  return ''
}

function getCommandParams(command: any): Record<string, any> {
  if (!command || typeof command !== 'object') return {}
  const params = (command as any)?.params
  return asObject(params)
}

function buildCommand(handler: string, params: Record<string, any>) {
  const h = String(handler || '').trim()
  if (!h) return null
  return { handler: h, params: params || {} }
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

function findPicDef(picDefs: PicDef[], feld: string): PicDef | null {
  const f = String(feld || '').trim().toLowerCase()
  if (!f) return null
  for (const d of picDefs) {
    const df = String((d as any)?.feld || (d as any)?.FELD || '').trim().toLowerCase()
    if (df && df === f) return d
  }
  return null
}

function normalizePicType(value: any): 'string' | 'text' | 'dropdown' | 'true_false' | 'menu_command' | 'selected_view' {
  const t = String(value || '').trim().toLowerCase()
  if (t === 'text') return 'text'
  if (t === 'dropdown') return 'dropdown'
  if (t === 'true_false' || t === 'bool' || t === 'boolean') return 'true_false'
  if (t === 'menu_command' || t === 'menu_commando') return 'menu_command'
  if (t === 'selected_view') return 'selected_view'
  return 'string'
}

function isFakeGuid(value: any): boolean {
  const s = String(value || '').trim()
  if (s.length < 8) return false
  const head = s.slice(0, 8)
  return head.split('').every((c) => c === head[0])
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

function getDescendants(itemsByUid: Record<string, MenuItem>, rootUid: string): string[] {
  const root = normalizeGuid(rootUid)
  if (!root) return []

  const out: string[] = []
  const stack: string[] = [root]

  while (stack.length) {
    const cur = stack.pop()!
    for (const [uid, item] of Object.entries(itemsByUid)) {
      if (normalizeGuid(item?.parent_guid) === cur) {
        out.push(uid)
        stack.push(uid)
      }
    }
  }

  return out
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

export function PdvmMenuEditor(props: {
  menuGuid: string
  group: MenuGroup
  systemdatenUid?: string | null
  frameDaten?: Record<string, any> | null
  onMissingMenuGuid?: (uid: string) => void
}) {
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<MenuRecordResponse | null>(null)
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set())
  const [selectedItemUid, setSelectedItemUid] = useState<string | null>(null)
  const [editOpen, setEditOpen] = useState(false)

  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleteTargetUid, setDeleteTargetUid] = useState<string | null>(null)
  const [deleteTitle, setDeleteTitle] = useState('Item löschen?')
  const [deleteMessage, setDeleteMessage] = useState('Soll dieses Item wirklich gelöscht werden?')

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
    setSelectedItemUid(null)
    setEditOpen(false)
  }, [props.menuGuid])
  // Sync draft from query result
  useEffect(() => {
    if (!menuQuery.data) return
    setDraft(menuQuery.data)
  }, [menuQuery.data])

  const menu = draft ?? menuQuery.data ?? null

  const rootItems = useMemo(() => {
    const daten = asObject(menu?.daten)
    return asObject(daten['ROOT'])
  }, [menu?.daten])

  const isTemplateMenu = useMemo(() => {
    const v = (rootItems as any)?.is_template ?? (rootItems as any)?.IS_TEMPLATE
    if (typeof v === 'boolean') return v
    if (typeof v === 'number') return v !== 0
    if (typeof v === 'string') return ['1', 'true', 'ja', 'yes', 'y'].includes(v.trim().toLowerCase())
    return false
  }, [rootItems])

  const effectiveGroup: MenuGroup = isTemplateMenu ? 'TEMPLATE' : props.group

  const groupItems = useMemo(() => {
    const daten = asObject(menu?.daten)
    const raw = asObject(daten[effectiveGroup])
    return raw as Record<string, MenuItem>
  }, [menu?.daten, effectiveGroup])

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
      const nextDaten = { ...asObject(base.daten), [effectiveGroup]: nextGroupItems }
      return { ...base, daten: nextDaten }
    })
  }

  const picDefs = useMemo(() => {
    const all = extractPicDefs(props.frameDaten)
    return all.filter((d) => {
      const t = normalizeUpper(d.table)
      return !t || t === 'SYS_MENUDATEN'
    })
  }, [props.frameDaten])

  const commandControlDef = useMemo(() => findPicDef(picDefs, 'command'), [picDefs])
  const menuCommandConfig = useMemo(() => {
    const cfg = asObject(commandControlDef?.configs)
    return asObject(cfg.menu_command)
  }, [commandControlDef])

  const menuCommandDatasetUid = String(menuCommandConfig?.key || props.systemdatenUid || '').trim()

  const commandCatalogQuery = useQuery({
    queryKey: ['systemdaten', 'menu-commands', menuCommandDatasetUid],
    queryFn: () => systemdatenAPI.getMenuCommands({ dataset_uid: menuCommandDatasetUid || undefined }),
    enabled: !!commandControlDef,
  })

  const menuConfigsQuery = useQuery({
    queryKey: ['systemdaten', 'menu-configs', menuCommandDatasetUid],
    queryFn: () => systemdatenAPI.getMenuConfigs({ dataset_uid: menuCommandDatasetUid || undefined }),
    enabled: !!commandControlDef,
  })

  const selectedItem = selectedItemUid ? groupItems[selectedItemUid] : null
  const selectedIsParent = selectedItemUid ? hasChildren(groupItems, selectedItemUid) : false
  const selectedType = selectedItem ? String((selectedItem as any)?.type || '').trim().toUpperCase() : ''
  const selectedTemplateGuid = selectedItem ? normalizeGuid((selectedItem as any)?.template_guid) : ''

  const commandDefs: MenuCommandDefinition[] = commandCatalogQuery.data?.commands || []
  const handlerOptions = commandDefs.map((c) => ({ value: c.handler, label: String(c.label || c.handler) }))

  const selectedCmdHandler = selectedItem ? getCommandHandler(selectedItem.command) : ''
  const selectedCmdParams = selectedItem ? getCommandParams(selectedItem.command) : {}
  const selectedCmdDef = selectedCmdHandler
    ? commandDefs.find((c) => String(c.handler || '').trim() === selectedCmdHandler) || null
    : null

  const helpConfig = useMemo(() => asObject(commandControlDef?.configs?.help), [commandControlDef])
  const helpDatasetUid = String(helpConfig?.key || '').trim()
  const helpEntryKey = String(helpConfig?.feld || '').trim()
  const helpGroup = String(helpConfig?.gruppe || '').trim() || undefined

  const helpTextQuery = useQuery({
    queryKey: ['systemdaten', 'text', helpDatasetUid, helpEntryKey, helpGroup || ''],
    queryFn: () =>
      systemdatenAPI.getText({
        dataset_uid: helpDatasetUid,
        entry_key: helpEntryKey,
        group: helpGroup,
      }),
    enabled: !!helpDatasetUid && !!helpEntryKey,
  })

  const paramHelpKeys = useMemo(() => {
    const prefix = helpEntryKey || 'menu_command'
    const params = asArray(selectedCmdDef?.params)
    return params
      .map((p: any) => String(p?.name || '').trim())
      .filter(Boolean)
      .map((name) => `${prefix}_${name}`)
  }, [helpEntryKey, selectedCmdDef])

  const paramHelpQueries = useQueries({
    queries: paramHelpKeys.map((entryKey) => ({
      queryKey: ['systemdaten', 'text', helpDatasetUid, entryKey, helpGroup || ''],
      queryFn: () =>
        systemdatenAPI.getText({
          dataset_uid: helpDatasetUid,
          entry_key: entryKey,
          group: helpGroup,
        }),
      enabled: !!helpDatasetUid && !!entryKey,
    })),
  })

  const paramHelpMap = useMemo(() => {
    const map: Record<string, string | null> = {}
    paramHelpQueries.forEach((q, idx) => {
      const key = paramHelpKeys[idx]
      if (!key) return
      map[key] = q.data?.text ?? null
    })
    return map
  }, [paramHelpQueries, paramHelpKeys])

  const menuParamConfigs = useMemo(() => menuConfigsQuery.data?.configs || {}, [menuConfigsQuery.data?.configs])

  const dropdownParamConfigs = useMemo(() => {
    const params = asArray(selectedCmdDef?.params)
    return params
      .map((p: any) => {
        const name = String(p?.name || '').trim()
        if (!name) return null
        const cfg = menuParamConfigs[name] as any
        const handler = String(cfg?.handler || '').trim()
        if (handler !== 'go_dropdown') return null
        const dropdownCfg = cfg?.dropdown || null
        const datasetUid = String(dropdownCfg?.key || '').trim()
        const field = String(dropdownCfg?.field || dropdownCfg?.feld || '').trim()
        const table = String(dropdownCfg?.table || '').trim()
        if (!datasetUid || !field || !table) return null
        return { name, datasetUid, field, table }
      })
      .filter(Boolean) as Array<{ name: string; datasetUid: string; field: string; table: string }>
  }, [selectedCmdDef, menuParamConfigs])

  const dropdownQueries = useQueries({
    queries: dropdownParamConfigs.map((cfg) => ({
      queryKey: ['systemdaten', 'dropdown', cfg.table, cfg.datasetUid, cfg.field],
      queryFn: () => systemdatenAPI.getDropdown({ table: cfg.table, dataset_uid: cfg.datasetUid, field: cfg.field }),
      enabled: !!cfg.datasetUid && !!cfg.field && !!cfg.table,
    })),
  })

  const dropdownOptionsByParam = useMemo(() => {
    const map: Record<string, Array<{ value: string; label: string }>> = {}
    dropdownParamConfigs.forEach((cfg, idx) => {
      const res = dropdownQueries[idx]
      const options = res?.data?.options || []
      map[cfg.name] = options.map((o) => ({ value: String(o.key), label: String(o.value) }))
    })
    return map
  }, [dropdownParamConfigs, dropdownQueries])

  const basicControls = useMemo(() => {
    return picDefs.filter((d) => {
      const table = normalizeUpper(d.table)
      const feld = String(d.feld || '').trim()
      if (table && table !== 'SYS_MENUDATEN') return false
      if (!feld) return false
      const t = normalizePicType(d.type)
      return t !== 'menu_command'
    })
  }, [picDefs])

  const commandHandlerDef = useMemo(() => findPicDef(picDefs, 'command.handler'), [picDefs])

  const patchItem = (uid: string, patch: Partial<MenuItem>) => {
    if (!uid || !groupItems[uid]) return
    setGroupItems({
      ...groupItems,
      [uid]: {
        ...(groupItems[uid] || {}),
        ...patch,
      },
    })
  }

  const patchItemCommand = (uid: string, nextCommand: any) => {
    patchItem(uid, { command: nextCommand })
  }

  const openEditor = (uid: string) => {
    setSelectedItemUid(uid)
    setEditOpen(true)
  }

  const requestDelete = (uid: string) => {
    const item = groupItems[uid]
    if (!item) return

    const label = String(item?.label || '').trim() || '(ohne Label)'
    const type = String((item as any)?.type || '').trim().toUpperCase()
    const templateGuid = normalizeGuid((item as any)?.template_guid)

    const descendants = getDescendants(groupItems, uid)
    const childCount = descendants.length

    // 1) Template placeholder: warn that the template itself is not deleted.
    if (templateGuid) {
      setDeleteTitle('Template-Eintrag löschen?')
      setDeleteMessage(
        `Du löschst nur diesen Template-Platzhalter ("${label}"). Das eigentliche Template (${templateGuid}) wird NICHT gelöscht.`
      )
    }
    // 2) Submenu/parent: warn that all children are deleted.
    else if (childCount > 0 || type === 'SUBMENU') {
      setDeleteTitle('Submenü löschen?')
      setDeleteMessage(`"${label}" wird gelöscht. Dabei werden auch alle untergeordneten Einträge (${childCount}) mit gelöscht.`)
    }
    // 3) Normal delete.
    else {
      setDeleteTitle('Item löschen?')
      setDeleteMessage(`Soll "${label}" wirklich gelöscht werden?`)
    }

    setDeleteTargetUid(uid)
    setDeleteOpen(true)
  }

  const performDelete = (uid: string) => {
    const item = groupItems[uid]
    if (!item) return

    const parent = normalizeGuid(item.parent_guid)
    const parentGuid = parent ? parent : null
    const descendants = getDescendants(groupItems, uid)

    const next: Record<string, MenuItem> = { ...groupItems }
    for (const d of descendants) delete next[d]
    delete next[uid]

    setCollapsed((prev) => {
      const s = new Set(prev)
      s.delete(uid)
      for (const d of descendants) s.delete(d)
      return s
    })

    setSelectedItemUid((prev) => {
      if (!prev) return prev
      if (prev === uid) return null
      if (descendants.includes(prev)) return null
      return prev
    })

    setGroupItems(resequenceSortOrder(next, parentGuid))
  }

  const save = async () => {
    const base = menu
    if (!base) return
    const nextDaten = { ...asObject(base.daten), ROOT: rootItems, [effectiveGroup]: groupItems }
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
      type: 'BUTTON',
      label: 'Neues MenüItem',
      icon: null as any,
      tooltip: null as any,
      enabled: true as any,
      visible: true as any,
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

    const newItem: MenuItem = {
      type: 'BUTTON',
      label: 'Neues MenüItem',
      icon: null as any,
      tooltip: null as any,
      enabled: true as any,
      visible: true as any,
      parent_guid: parentGuid,
      sort_order: 0,
    }
    const next = insertSibling(groupItems, parentGuid, targetUid, position, uid, newItem)
    setGroupItems(next)
  }

  const addChild = (parentUid: string) => {
    const uid = newGuid()
    const newItem: MenuItem = {
      type: 'BUTTON',
      label: 'Neues MenüItem',
      icon: null as any,
      tooltip: null as any,
      enabled: true as any,
      visible: true as any,
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
    const isSelected = selectedItemUid === uid

    return (
      <div
        key={uid}
        draggable
        onClick={() => setSelectedItemUid(uid)}
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
          border: isSelected ? '2px solid rgba(80,160,255,0.85)' : '1px solid rgba(255,255,255,0.08)',
          borderRadius: 10,
          padding: 10,
          marginBottom: 8,
          background: isSelected ? 'rgba(80,160,255,0.14)' : 'rgba(255,255,255,0.03)',
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

          {renderMenuIcon((item as any)?.icon ?? (item as any)?.ICON ?? (item as any)?.Icon, 16)}
          <div style={{ fontWeight: 800 }}>{label}</div>

          <div className="pdvm-menu-editor__nodeActions" style={{ marginLeft: 'auto', display: 'flex', gap: 6, alignItems: 'center' }}>
            <button type="button" onClick={() => addSibling(uid, 'before')} title="Neues Item oberhalb einfügen">
              +↑
            </button>
            <button type="button" onClick={() => addSibling(uid, 'after')} title="Neues Item unterhalb einfügen">
              +↓
            </button>
            <button type="button" onClick={() => addChild(uid)} title="Neues Kind-Item einfügen">
              +Kind
            </button>
            <button type="button" onClick={() => requestDelete(uid)} title="Item löschen">
              -Item
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
                openEditor(uid)
              }}
              title="Bearbeiten (Stufe 2)"
            >
              ✎
            </button>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 10, marginTop: 6, fontSize: 12, opacity: 0.75 }}>
          <div style={{ fontFamily: 'monospace' }}>{uid}</div>
          <div>type: {String((item as any)?.type || '').toUpperCase() || '-'}</div>
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

  const getFieldValue = (feld: string) => {
    const key = String(feld || '').trim().toLowerCase()
    if (!selectedItem) return ''
    if (key === 'tooltip') return selectedItem.tooltip ?? ''
    if (key === 'icon') return selectedItem.icon ?? (selectedItem as any)?.ICON ?? (selectedItem as any)?.Icon ?? ''
    if (key === 'enabled') return selectedItem.enabled ?? true
    if (key === 'visible') return selectedItem.visible ?? true
    if (key === 'label') return selectedItem.label ?? ''
    return (selectedItem as any)?.[key] ?? ''
  }

  const setFieldValue = (feld: string, value: any) => {
    if (!selectedItemUid) return
    const key = String(feld || '').trim().toLowerCase()
    if (key === 'template_guid') {
      const s = String(value ?? '').trim()
      if (s) {
        patchItem(selectedItemUid, { template_guid: s, type: 'SPACER' })
      } else {
        patchItem(selectedItemUid, { template_guid: null, type: 'BUTTON' })
      }
      return
    }
    if (key === 'tooltip') {
      patchItem(selectedItemUid, { tooltip: String(value ?? '') || null })
      return
    }
    if (key === 'icon') {
      const s = String(value ?? '').trim()
      patchItem(selectedItemUid, { icon: s ? s : undefined })
      return
    }
    if (key === 'enabled') {
      patchItem(selectedItemUid, { enabled: !!value })
      return
    }
    if (key === 'visible') {
      patchItem(selectedItemUid, { visible: !!value })
      return
    }
    if (key === 'label') {
      patchItem(selectedItemUid, { label: String(value ?? '') })
      return
    }

    patchItem(selectedItemUid, { [key]: value } as any)
  }

  return (
    <div>
      <PdvmDialogModal
        open={deleteOpen}
        kind="confirm"
        title={deleteTitle}
        message={deleteMessage}
        confirmLabel="Löschen"
        cancelLabel="Abbrechen"
        busy={updateMutation.isPending}
        onCancel={() => {
          if (updateMutation.isPending) return
          setDeleteOpen(false)
          setDeleteTargetUid(null)
        }}
        onConfirm={() => {
          if (updateMutation.isPending) return
          const uid = deleteTargetUid
          setDeleteOpen(false)
          setDeleteTargetUid(null)
          if (uid) performDelete(uid)
        }}
      />

      <PdvmInputModal
        open={editOpen}
        title={
          selectedItem
            ? `MenüItem bearbeiten: ${String(selectedItem?.label || '').trim() || '(ohne Label)'}`
            : 'MenüItem bearbeiten'
        }
        busy={updateMutation.isPending}
        onClose={() => setEditOpen(false)}
        onSave={
          selectedItem
            ? async () => {
                await save()
                setEditOpen(false)
              }
            : undefined
        }
        footerExtra={
          selectedItem ? (
            <button
              type="button"
              onClick={() => {
                const daten = asObject(menuQuery.data?.daten)
                const raw = asObject(daten[effectiveGroup]) as Record<string, MenuItem>
                setGroupItems(raw)
              }}
              disabled={updateMutation.isPending}
              className="pdvm-modal__btn"
            >
              Änderungen verwerfen
            </button>
          ) : null
        }
      >
        {!selectedItemUid || !selectedItem ? (
          <div style={{ opacity: 0.8 }}>Kein Item ausgewählt.</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ fontSize: 12, opacity: 0.8 }}>
              UID: <span style={{ fontFamily: 'monospace' }}>{selectedItemUid}</span>
            </div>

            <div style={{ display: 'flex', gap: 10, fontSize: 12, opacity: 0.8, flexWrap: 'wrap' }}>
              <div>type: {selectedType || '-'}</div>
              <div>sort: {selectedItem?.sort_order ?? '-'}</div>
              <div>parent: {normalizeGuid(selectedItem?.parent_guid) || '-'}</div>
            </div>

            {selectedTemplateGuid ? (
              <div style={{ fontSize: 12, opacity: 0.85 }}>
                Template: <span style={{ fontFamily: 'monospace' }}>{selectedTemplateGuid}</span>
              </div>
            ) : null}

            {basicControls.length === 0 ? (
              <div style={{ opacity: 0.75 }}>Keine FIELDS-Controls für SYS_MENUDATEN gefunden.</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {basicControls.map((def) => {
                  const feld = String(def.feld || '').trim()
                  const feldLower = feld.toLowerCase()
                  const label = String(def.label || def.name || feld || 'Feld')
                  const tooltip = def.tooltip || null
                  const typ = normalizePicType(def.type)
                  const readOnly = !!def.read_only
                  const value = getFieldValue(feld)

                  if (typ === 'selected_view') {
                    const cfg = asObject(def.configs)
                    const viewCfg = asObject(cfg.selected_view)
                    const table = String(viewCfg.table || '').trim()

                    return (
                      <div key={def.key || feld} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                        <div style={{ fontSize: 12, fontWeight: 700 }} title={tooltip || undefined}>
                          {label}
                        </div>
                        <PdvmLookupSelect
                          table={table}
                          value={value ? String(value) : null}
                          disabled={readOnly || selectedIsParent}
                          filterOption={(row) => !isFakeGuid(row.uid)}
                          onChange={(v) => setFieldValue(feld, v)}
                        />
                      </div>
                    )
                  }

                  if (feldLower === 'icon') {
                    const rawValue = value != null ? String(value) : ''
                    const hasValue = rawValue && !MENU_ICON_OPTIONS.some((opt) => opt.value === rawValue)
                    const extraOption = hasValue ? [{ value: rawValue, label: rawValue }] : []
                    const preview = rawValue || ''

                    return (
                      <div key={def.key || feld} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                        <PdvmInputControl
                          label={label}
                          tooltip={tooltip}
                          type="dropdown"
                          value={rawValue}
                          options={[...extraOption, ...MENU_ICON_OPTIONS]}
                          readOnly={readOnly}
                          onChange={(v) => setFieldValue(feld, v)}
                        />
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, opacity: 0.85 }}>
                          <span>Vorschau:</span>
                          {renderMenuIcon(preview, 16)}
                          <span style={{ fontFamily: 'monospace' }}>{preview || '-'}</span>
                        </div>
                      </div>
                    )
                  }

                  return (
                    <PdvmInputControl
                      key={def.key || feld}
                      label={label}
                      tooltip={tooltip}
                      type={typ}
                      value={value}
                      readOnly={readOnly}
                      onChange={(v) => setFieldValue(feld, v)}
                    />
                  )
                })}
              </div>
            )}

            {commandControlDef ? (
              <div style={{ marginTop: 4, paddingTop: 10, borderTop: '1px solid rgba(255,255,255,0.10)' }}>
                <div style={{ fontWeight: 800, marginBottom: 8 }}>{commandControlDef.label || 'Menü Kommando'}</div>

                {selectedIsParent ? (
                  <div style={{ fontSize: 12, opacity: 0.85, marginBottom: 8 }}>
                    Dieses Item hat Kinder (Submenü). Ein Command wird serverseitig entfernt.
                  </div>
                ) : null}

                <PdvmInputControl
                  id="menu-item-command-handler"
                  label={String(commandHandlerDef?.label || commandHandlerDef?.name || 'Handler')}
                  tooltip={commandHandlerDef?.tooltip || null}
                  helpText={helpTextQuery.data?.text || null}
                  type={handlerOptions.length > 0 ? 'dropdown' : 'string'}
                  value={selectedCmdHandler}
                  options={handlerOptions}
                  disabled={selectedIsParent || commandCatalogQuery.isLoading}
                  onChange={(v) => {
                    const handler = String(v || '').trim()
                    const nextParams: Record<string, any> = {}
                    const def = handler ? commandDefs.find((c) => c.handler === handler) : null
                    for (const p of asArray(def?.params)) {
                      const name = String((p as any)?.name || '').trim()
                      if (!name) continue
                      nextParams[name] = selectedCmdParams[name] ?? ''
                    }
                    patchItemCommand(selectedItemUid, buildCommand(handler, nextParams))
                  }}
                />

                {handlerOptions.length === 0 ? (
                  <div style={{ fontSize: 12, opacity: 0.75, marginTop: 6 }}>
                    Kein Command-Katalog gefunden. Handler wird als Freitext erfasst.
                  </div>
                ) : null}

                {commandCatalogQuery.isError ? (
                  <div style={{ color: 'crimson', fontSize: 12, marginTop: 6 }}>Command-Katalog konnte nicht geladen werden.</div>
                ) : null}

                {selectedCmdDef && asArray(selectedCmdDef.params).length > 0 ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 10 }}>
                    {asArray(selectedCmdDef.params).map((p: any) => {
                      const name = String(p?.name || '').trim()
                      if (!name) return null
                      const required = !!p?.required
                      const label = `${name}${required ? ' *' : ''}`
                      const cur = selectedCmdParams[name]
                      const helpKey = `${helpEntryKey || 'menu_command'}_${name}`
                      const helpText = paramHelpMap[helpKey] ?? null

                      const cfg = menuParamConfigs[name] as any
                      const handler = String(cfg?.handler || '').trim()
                      const fromTable = String(cfg?.from_table || '').trim()
                      const dropdownCfg = cfg?.dropdown || null

                      if (handler === 'go_select_view' && fromTable) {
                        return (
                          <div key={name} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                            <div style={{ fontSize: 12, fontWeight: 700 }}>{label}</div>
                            <PdvmLookupSelect
                              table={fromTable}
                              value={cur ? String(cur) : null}
                              disabled={selectedIsParent}
                              onChange={(v) => {
                                const h = getCommandHandler(selectedItem.command)
                                const params = { ...getCommandParams(selectedItem.command), [name]: v }
                                patchItemCommand(selectedItemUid, buildCommand(h, params))
                              }}
                            />
                          </div>
                        )
                      }

                      if (handler === 'go_dropdown') {
                        const options = dropdownOptionsByParam[name] || []
                        return (
                          <PdvmInputControl
                            key={name}
                            label={label}
                            type="dropdown"
                            value={cur ?? ''}
                            helpText={helpText}
                            options={options}
                            disabled={selectedIsParent}
                            onChange={(v) => {
                              const h = getCommandHandler(selectedItem.command)
                              const params = { ...getCommandParams(selectedItem.command), [name]: String(v ?? '') }
                              patchItemCommand(selectedItemUid, buildCommand(h, params))
                            }}
                          />
                        )
                      }

                      return (
                        <PdvmInputControl
                          key={name}
                          label={label}
                          type="string"
                          value={cur ?? ''}
                          helpText={helpText}
                          disabled={selectedIsParent}
                          onChange={(v) => {
                            const h = getCommandHandler(selectedItem.command)
                            const params = { ...getCommandParams(selectedItem.command), [name]: String(v ?? '') }
                            patchItemCommand(selectedItemUid, buildCommand(h, params))
                          }}
                        />
                      )
                    })}
                  </div>
                ) : selectedCmdHandler ? (
                  <div style={{ fontSize: 12, opacity: 0.8, marginTop: 8 }}>Keine Parameter für diesen Handler.</div>
                ) : null}
              </div>
            ) : null}
          </div>
        )}
      </PdvmInputModal>

      <div className="pdvm-menu-editor__toolbar" style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
        <div style={{ fontSize: 12, opacity: 0.75 }}>Gruppe: {effectiveGroup}</div>
        <div style={{ fontSize: 12, opacity: 0.75 }}>Items: {itemCount}</div>
        <div className="pdvm-menu-editor__toolbarActions" style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
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
