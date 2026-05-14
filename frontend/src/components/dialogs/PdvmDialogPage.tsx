import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  controlDictAPI,
  dialogsAPI,
  workflowDraftsAPI,
  systemdatenAPI,
  viewsAPI,
  usersAPI,
  type DialogRow,
  type DialogDefinitionResponse,
  type FrameDefinitionResponse,
  type DialogRecordResponse,
  type DialogDraftResponse,
  type DialogUiStateResponse,
  type DialogValidationIssue,
  type WorkflowDraftValidationResponse,
} from '../../api/client'
import { PdvmViewPageContent } from '../views/PdvmViewPage'
import { PdvmMenuEditor } from './PdvmMenuEditor'
import { PdvmImportDataEditor, PdvmImportDataSteps } from './PdvmImportDataEditor'
import { PdvmJsonEditor, type PdvmJsonEditorHandle, type PdvmJsonEditorMode } from '../common/PdvmJsonEditor'
import { PdvmDialogModal, type PdvmDialogModalField } from '../common/PdvmDialogModal'
import { PdvmInputControl, type PdvmDropdownOption, type PdvmElementField } from '../common/PdvmInputControl'
import { useAuth } from '../../hooks/useAuth'
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

function readCfgValue(source: any, keys: string[]): any {
  const obj = asObject(source)
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(obj, key)) return (obj as any)[key]
    const up = key.toUpperCase()
    if (Object.prototype.hasOwnProperty.call(obj, up)) return (obj as any)[up]
    const low = key.toLowerCase()
    if (Object.prototype.hasOwnProperty.call(obj, low)) return (obj as any)[low]
  }
  return undefined
}

function resolveGoSelectViewTable(configs: any, controlData?: any): string {
  const cfg = asObject(configs)
  const ctl = asObject(controlData)

  const direct = readCfgValue(cfg, ['go_select_view'])
  const directObj = asObject(direct)
  const nestedConfigs = asObject(readCfgValue(cfg, ['CONFIGS', 'configs']))
  const nestedGoSelect = asObject(readCfgValue(nestedConfigs, ['go_select_view']))

  const controlConfigs = asObject(readCfgValue(ctl, ['CONFIGS', 'configs']))
  const controlGoSelect = asObject(readCfgValue(controlConfigs, ['go_select_view']))
  const controlDirectGoSelect = asObject(readCfgValue(ctl, ['go_select_view']))

  const table =
    readCfgValue(controlDirectGoSelect, ['table']) ??
    readCfgValue(controlGoSelect, ['table']) ??
    readCfgValue(directObj, ['table']) ??
    readCfgValue(nestedGoSelect, ['table']) ??
    ''

  return String(table || '').trim()
}

function resolveElementEditorConfig(configs: any): { template: Record<string, any> | null; fields: any[] | null } {
  const cfg = asObject(configs)
  const cfgElements = asObject(readCfgValue(cfg, ['CONFIGS_ELEMENTS', 'configs_elements']))

  const directTemplate = asObject(readCfgValue(cfg, ['element_template', 'template', 'elemente_template']))
  const cfgElementsTemplate = asObject(readCfgValue(cfgElements, ['element_template', 'template', 'elemente_template', 'ELEMENT_TEMPLATE']))
  const template = Object.keys(directTemplate).length ? directTemplate : Object.keys(cfgElementsTemplate).length ? cfgElementsTemplate : null

  const directFields = readCfgValue(cfg, ['element_fields', 'fields'])
  const cfgElementsFields = readCfgValue(cfgElements, ['element_fields', 'fields', 'ELEMENT_FIELDS'])
  const fieldsRaw = Array.isArray(directFields) ? directFields : Array.isArray(cfgElementsFields) ? cfgElementsFields : null

  return {
    template,
    fields: fieldsRaw,
  }
}

function resolveSelectConfigByType(params: {
  type: 'dropdown' | 'multi_dropdown'
  cfgElements?: any
  cfgControlConfigs?: any
  cfgLegacy?: any
}): Record<string, any> {
  const key = params.type === 'multi_dropdown' ? 'multi_dropdown' : 'dropdown'
  const keyUpper = key.toUpperCase()

  const fromElements = asObject(asObject(params.cfgElements)[key] ?? asObject(params.cfgElements)[keyUpper])
  if (Object.keys(fromElements).length) return fromElements

  const fromControlConfigs = asObject(asObject(params.cfgControlConfigs)[key] ?? asObject(params.cfgControlConfigs)[keyUpper])
  if (Object.keys(fromControlConfigs).length) return fromControlConfigs

  return asObject(asObject(params.cfgLegacy)[key] ?? asObject(params.cfgLegacy)[keyUpper])
}

function cloneValue(value: any): any {
  if (value == null) return value
  if (Array.isArray(value)) return value.map((entry) => cloneValue(entry))
  if (typeof value !== 'object') return value
  try {
    return JSON.parse(JSON.stringify(value))
  } catch {
    return value
  }
}

function normalizeValueEnvelope(value: any): Record<string, any> {
  const obj = asObject(value)
  if (Object.prototype.hasOwnProperty.call(obj, 'ORIGINAL')) {
    return obj
  }
  return { ORIGINAL: cloneValue(value) }
}

function buildFlatPicControl(params: {
  controlData: any
  fieldKey: string
  value: any
  valueTimeKey?: string | null
  sourcePath?: string | null
}): Record<string, any> {
  const controlData = asObject(params.controlData)
  const controlRoot = asObject(controlData.ROOT)
  const controlPayload = asObject(controlData.CONTROL)
  const guidRaw = String(controlRoot.SELF_GUID ?? '').trim()
  const resolvedValueTimeKey = String(params.valueTimeKey || '').trim() || 'ORIGINAL'
  const resolvedSourcePath =
    String(
      params.sourcePath ??
        (controlPayload as any).SOURCE_PATH ??
        (controlPayload as any).source_path ??
        (controlData as any).SOURCE_PATH ??
        (controlData as any).source_path ??
        'root'
    ).trim() || 'root'

  return {
    ...controlPayload,
    FIELD_KEY: String(params.fieldKey || '').trim(),
    GUID_KEY: guidRaw || null,
    SOURCE_PATH: resolvedSourcePath,
    VALUE: normalizeValueEnvelope(params.value),
    VALUE_TIME_KEY: resolvedValueTimeKey,
  }
}

function normalizePicType(
  value: any
): 'string' | 'number' | 'text' | 'dropdown' | 'multi_dropdown' | 'true_false' | 'datetime' | 'date' | 'time' | 'go_select_view' | 'action' | 'element_list' | 'group_list' {
  const t = String(value || '').trim().toLowerCase()
  if (t === 'number' || t === 'int' || t === 'integer') return 'number'
  if (t === 'text') return 'text'
  if (t === 'dropdown') return 'dropdown'
  if (t === 'multi_dropdown') return 'multi_dropdown'
  if (t === 'true_false' || t === 'bool' || t === 'boolean') return 'true_false'
  if (t === 'datetime') return 'datetime'
  if (t === 'date') return 'date'
  if (t === 'time') return 'time'
  if (t === 'go_select_view' || t === 'selected_view' || t === 'lookup') return 'go_select_view'
  if (t === 'action') return 'action'
  if (t === 'element_list' || t === 'elemente_list') return 'element_list'
  if (t === 'group_list') return 'group_list'
  return 'string'
}

function buildElementFieldsFromCollectionValue(value: any): Array<{ name: string; label: string; type: 'string' | 'text' | 'textarea' | 'number' | 'dropdown' | 'multi_dropdown' | 'true_false' }> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return []
  const first = Object.values(value).find((row) => row && typeof row === 'object' && !Array.isArray(row)) as Record<string, any> | undefined
  if (!first) return []
  return Object.keys(first)
    .filter((k) => String(k || '').trim())
    .map((k) => ({ name: k, label: k, type: 'string' as const }))
}

function mapPicTypeToElementFieldType(value: any): 'string' | 'text' | 'textarea' | 'number' | 'dropdown' | 'multi_dropdown' | 'true_false' {
  const t = normalizePicType(value)
  if (t === 'number') return 'number'
  if (t === 'text') return 'textarea'
  if (t === 'dropdown') return 'dropdown'
  if (t === 'multi_dropdown') return 'multi_dropdown'
  if (t === 'true_false') return 'true_false'
  return 'string'
}

function inferElementFieldTypeFromValue(value: any): 'string' | 'number' | 'true_false' {
  if (typeof value === 'boolean') return 'true_false'
  if (typeof value === 'number') return 'number'
  return 'string'
}

function extractControlPayloadFromRecord(daten: any): Record<string, any> {
  const data = asObject(daten)
  const wrapped = asObject(data.CONTROL)
  if (Object.keys(wrapped).length) return wrapped
  const flat = { ...data }
  delete (flat as any).ROOT
  delete (flat as any).CONTROL
  return asObject(flat)
}

function buildFrameFieldsElementEditorFields(baseFields: any, controlTemplatePayload: Record<string, any>): PdvmElementField[] {
  const rawBase = Array.isArray(baseFields) ? baseFields : []
  const out: PdvmElementField[] = rawBase.map((f: any, idx) => ({
    ...(asObject(f) as any),
    name: String((f as any)?.name || '').trim(),
    label: String((f as any)?.label || (f as any)?.name || '').trim(),
    display_order: Number((f as any)?.display_order ?? (idx + 1) * 10),
  }))

  const existing = new Set(out.map((f) => String(f.name || '').trim().toUpperCase()).filter(Boolean))
  let order = (Math.max(0, ...out.map((f) => Number(f.display_order || 0))) || 0) + 10

  for (const [k, v] of Object.entries(asObject(controlTemplatePayload))) {
    const key = String(k || '').trim().toUpperCase()
    if (!key) continue
    if (existing.has(key)) continue
    if (key === 'FIELD' || key === 'FELD' || key === 'NAME') continue

    out.push({
      name: key,
      label: key,
      type: inferElementFieldTypeFromValue(v),
      SAVE_PATH: key,
      required: false,
      display_order: order,
    })
    existing.add(key)
    order += 10
  }

  return out
}

function valuesEqual(a: any, b: any): boolean {
  try {
    return JSON.stringify(a) === JSON.stringify(b)
  } catch {
    return String(a) === String(b)
  }
}

function normalizeControlToken(value: any): string {
  return String(value || '').trim().toUpperCase()
}

function resolveControlUidToken(rawToken: any, uidByToken: Record<string, string>): string {
  const raw = String(rawToken || '').trim()
  if (!raw) return ''
  if (isUuidString(raw)) return raw
  const mapped = uidByToken[normalizeControlToken(raw)]
  return String(mapped || '').trim()
}

function toBoolean(value: any): boolean {
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

function isApplyLikeActionControl(def: any): boolean {
  const row = asObject(def)
  const configs = asObject((row as any).configs)
  const control = asObject((row as any).CONTROL)

  const token = [
    row.label,
    row.name,
    row.feld,
    row.key,
    (configs as any).action,
    (configs as any).action_id,
    (configs as any).action_key,
    (configs as any).handler,
    (configs as any).command,
    (control as any).ACTION,
    (control as any).ACTION_ID,
    (control as any).ACTION_KEY,
    (control as any).HANDLER,
    (control as any).COMMAND,
  ]
    .filter((v) => v !== undefined && v !== null)
    .map((v) => String(v).trim().toLowerCase())
    .join(' ')

  if (!token) return false

  return ['apply', 'anwenden', 'release_apply', 'import_apply', 'paket angewendet'].some((kw) => token.includes(kw))
}

function buildActionToken(def: any): string {
  const row = asObject(def)
  const configs = asObject((row as any).configs)
  const control = asObject((row as any).CONTROL)
  return [
    row.label,
    row.name,
    row.feld,
    row.key,
    (configs as any).action,
    (configs as any).action_id,
    (configs as any).action_key,
    (configs as any).handler,
    (configs as any).command,
    (control as any).ACTION,
    (control as any).ACTION_ID,
    (control as any).ACTION_KEY,
    (control as any).HANDLER,
    (control as any).COMMAND,
  ]
    .filter((v) => v !== undefined && v !== null)
    .map((v) => String(v).trim().toLowerCase())
    .join(' ')
}

function collectWorkflowSetupPayload(datenRaw: Record<string, any> | null | undefined): Record<string, any> {
  const daten = asObject(datenRaw)
  const fromFields = (field: string) => getFieldValue(daten, 'FIELDS', field)
  const fromRoot = (field: string) => getFieldValue(daten, 'ROOT', field)

  const pickString = (value: any): string => String(value ?? '').trim()

  return {
    WORKFLOW_NAME: pickString(fromFields('WORKFLOW_NAME') ?? fromRoot('WORKFLOW_NAME')),
    TARGET_TABLE: pickString(fromFields('TARGET_TABLE') ?? fromRoot('TARGET_TABLE') ?? 'sys_dialogdaten'),
    DESCRIPTION: pickString(fromFields('DESCRIPTION') ?? fromRoot('DESCRIPTION')),
  }
}

function buildElementFieldsFromFrameDaten(
  frameDaten: Record<string, any> | null | undefined,
  expertModeEnabled: boolean = false,
): PdvmElementField[] {
  const defs = extractPicDefs(frameDaten)
  return defs
    .map((d) => {
      const row = asObject(d as any)
      const name = String((d as any).feld ?? row.FELD ?? (d as any).name ?? row.NAME ?? '').trim()
      if (!name) return null
      const label = String((d as any).label ?? row.LABEL ?? (d as any).name ?? row.NAME ?? name).trim() || name
      const fieldType = mapPicTypeToElementFieldType((d as any).type ?? row.TYPE)
      const displayOrder = Number((d as any).display_order ?? row.DISPLAY_ORDER)
      const tooltip = String((d as any).tooltip ?? row.TOOLTIP ?? row.HELP_TEXT ?? '').trim()
      const required = toBoolean((d as any).required ?? row.REQUIRED)
      const expertMode = !!expertModeEnabled

      return {
        name,
        label,
        type: fieldType,
        required,
        tooltip: tooltip || undefined,
        help_text: tooltip || undefined,
        control_debug: {
          ...asObject(row.CONTROL),
          FIELD_KEY: `ELEMENT.${name}`,
          EXPERT_MODE: expertMode,
        },
        EXPERT_MODE: expertMode,
        SAVE_PATH: name,
        display_order: Number.isFinite(displayOrder) ? displayOrder : undefined,
      } as PdvmElementField
    })
    .filter(Boolean) as PdvmElementField[]
}

function buildElementTemplateFromFields(fields: PdvmElementField[]): Record<string, any> {
  const out: Record<string, any> = {}
  fields.forEach((field) => {
    if (!field?.name) return
    if (field.type === 'number') {
      out[field.name] = 0
      return
    }
    if (field.type === 'true_false') {
      out[field.name] = false
      return
    }
    if (field.type === 'multi_dropdown') {
      out[field.name] = []
      return
    }
    out[field.name] = ''
  })
  return out
}

function isCollectionObject(value: any): boolean {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const entries = Object.entries(value)
  if (!entries.length) return false
  return entries.every(([key, row]) => String(key || '').trim() && row && typeof row === 'object' && !Array.isArray(row))
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

        if (isCollectionObject(raw)) {
          base.type = 'element_list'
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

function parseFrameTabElements(frameRootInput: any): Map<number, { head: string; group: string }> {
  const frameRoot = asObject(frameRootInput)
  const tabElementsRaw = (frameRoot as any).TAB_ELEMENTS ?? (frameRoot as any).tab_elements
  const tabElements = tabElementsRaw && typeof tabElementsRaw === 'object' && !Array.isArray(tabElementsRaw) ? tabElementsRaw : null
  const out = new Map<number, { head: string; group: string }>()

  if (!tabElements) return out

  for (const [key, value] of Object.entries(tabElements)) {
    const row = asObject(value)
    if (!Object.keys(row).length) continue

    const keyMatch = /^tab[_-]?0*(\d+)$/i.exec(String(key || '').trim())
    const idxRaw = row.index ?? row.tab ?? row.TAB ?? (keyMatch ? Number(keyMatch[1]) : 0)
    const idx = Number(idxRaw || 0)
    if (!idx || idx < 1 || idx > 20) continue

    const head = String(row.HEAD ?? row.head ?? '').trim()
    const group = String(row.GRUPPE ?? row.gruppe ?? '').trim()

    const previous = out.get(idx)
    if (!previous) {
      out.set(idx, { head, group })
      continue
    }

    out.set(idx, {
      head: previous.head || head,
      group: previous.group || group,
    })
  }

  return out
}

function buildUnifiedControlMatrix(
  source: UnifiedControlSource,
  opts: {
    frameDaten?: Record<string, any> | null
    currentDaten?: Record<string, any> | null
    excludeRootGroup?: boolean
  }
): ControlEditModel {
  if (source === 'frame_fields') {
    const allDefs = extractPicDefs(opts.frameDaten || null)
    const defs = opts.excludeRootGroup
      ? allDefs.filter((d) => String(d.gruppe || '').trim().toUpperCase() !== 'ROOT')
      : allDefs
    const tabsMap = new Map<number, { index: number; head: string; group: string }>()
    const tabMetaMap = parseFrameTabElements(asObject(asObject(opts.frameDaten).ROOT))

    defs.forEach((d) => {
      const tabIndex = Number(d.tab || 1) || 1
      if (tabsMap.has(tabIndex)) return

      const tabMeta = tabMetaMap.get(tabIndex)
      const group = String(d.gruppe || tabMeta?.group || '').trim()
      const head = String(tabMeta?.head || '').trim() || group || `Tab ${tabIndex}`
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
  const frameRoot = asObject(fd.ROOT)
  const tabMetaMap = parseFrameTabElements(frameRoot)
  const out: PicDef[] = []
  for (const [key, value] of Object.entries(fields)) {
    const item = asObject(value)
    const control = asObject((item as any).CONTROL)
    const root = asObject((item as any).ROOT)
    const configsRaw = asObject((item as any).configs ?? (item as any).CONFIGS)
    const cfgElements = asObject((item as any).CONFIGS_ELEMENTS ?? control.CONFIGS_ELEMENTS)
    const mergedConfigs = {
      ...configsRaw,
      ...(Object.keys(cfgElements).length ? { CONFIGS_ELEMENTS: cfgElements } : {}),
      ...(Object.keys(asObject((configsRaw as any).dropdown)).length ? {} : { dropdown: asObject((cfgElements as any).dropdown) }),
    }

    const displayOrderRaw = (item as any).display_order ?? (item as any).DISPLAY_ORDER ?? control.DISPLAY_ORDER ?? control.EXPERT_ORDER
    const tabRaw =
      (item as any).tab ??
      (item as any).TAB ??
      control.TAB ??
      (item as any).index ??
      (item as any).INDEX ??
      control.EDIT_TAB
    const tabIndex = Number(tabRaw || 1) || 1
    const tabMeta = tabMetaMap.get(tabIndex)

    out.push({
      ...(item as PicDef),
      key,
      tab: tabIndex,
      name: String((item as any).name ?? (item as any).NAME ?? control.NAME ?? key).trim(),
      label: String((item as any).label ?? (item as any).LABEL ?? control.LABEL ?? control.NAME ?? key).trim(),
      tooltip: String((item as any).tooltip ?? (item as any).TOOLTIP ?? control.TOOLTIP ?? '').trim() || undefined,
      type: String((item as any).type ?? (item as any).TYPE ?? control.TYPE ?? 'string').trim(),
      table: String((item as any).table ?? (item as any).TABLE ?? control.TABLE ?? '').trim(),
      gruppe: String((item as any).gruppe ?? (item as any).GRUPPE ?? control.GRUPPE ?? tabMeta?.group ?? '').trim(),
      feld: String((item as any).feld ?? (item as any).FELD ?? control.FIELD ?? control.FELD ?? key).trim(),
      display_order: Number(displayOrderRaw || 0),
      read_only: toBoolean((item as any).read_only ?? (item as any).READ_ONLY ?? control.READ_ONLY),
      historical: toBoolean((item as any).historical ?? (item as any).HISTORICAL ?? control.HISTORICAL),
      abdatum: toBoolean((item as any).abdatum ?? (item as any).ABDATUM ?? control.ABDATUM),
      source_path: String((item as any).source_path ?? (item as any).SOURCE_PATH ?? control.SOURCE_PATH ?? '').trim() || undefined,
      configs: mergedConfigs,
      ...(Object.keys(control).length ? { CONTROL: control } : {}),
      ...(Object.keys(root).length ? { ROOT: root } : {}),
    } as any)
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

type CreateContextFieldDef = {
  modalField: PdvmDialogModalField
  contextKey: string
  valueType: 'string' | 'number'
  defaultValue?: string
}

function parseModalDropdownOptions(raw: any): Array<{ value: string; label: string }> {
  if (!Array.isArray(raw)) return []
  const out: Array<{ value: string; label: string }> = []
  raw.forEach((entry) => {
    if (entry == null) return
    if (typeof entry === 'string' || typeof entry === 'number' || typeof entry === 'boolean') {
      const s = String(entry)
      out.push({ value: s, label: s })
      return
    }
    if (typeof entry !== 'object') return
    const obj = asObject(entry)
    const value = String(readCfgValue(obj, ['value', 'uid', 'key', 'id']) ?? '').trim()
    if (!value) return
    const label =
      String(readCfgValue(obj, ['label', 'name', 'title']) ?? '').trim() ||
      value
    out.push({ value, label })
  })
  return out
}

function buildCreateContextFieldsFromFrame(frameDaten: Record<string, any> | null | undefined): CreateContextFieldDef[] {
  const defs = extractPicDefs(frameDaten)
  const out: CreateContextFieldDef[] = []
  const usedNames = new Set<string>()

  defs.forEach((def, idx) => {
    const gruppe = String(def.gruppe || '').trim().toUpperCase()
    // Create-Frames verwenden je nach Konvention ROOT oder FIELDS als Gruppe.
    if (gruppe && gruppe !== 'ROOT' && gruppe !== 'FIELDS') return
    if (toBoolean(def.read_only)) return

    const rawField = String(def.feld || def.name || '').trim().toUpperCase()
    if (!rawField) return
    if (rawField === 'SELF_GUID' || rawField === 'SELF_NAME') return

    const rawType = normalizePicType(def.type)
    if (rawType === 'action' || rawType === 'go_select_view' || rawType === 'element_list' || rawType === 'group_list' || rawType === 'multi_dropdown' || rawType === 'true_false' || rawType === 'datetime' || rawType === 'date' || rawType === 'time') {
      return
    }

    const fieldNameBase = `create_ctx__${rawField.toLowerCase()}`
    let fieldName = fieldNameBase
    let suffix = 1
    while (usedNames.has(fieldName)) {
      suffix += 1
      fieldName = `${fieldNameBase}_${suffix}`
    }
    usedNames.add(fieldName)

    const cfg = asObject(def.configs)
    const isRequired = toBoolean(readCfgValue(cfg, ['required', 'is_required', 'pflicht']))
    const defaultRaw = readCfgValue(cfg, ['default', 'default_value', 'initial_value', 'value'])
    const defaultValue = defaultRaw == null ? undefined : String(defaultRaw)

    let modalType: PdvmDialogModalField['type'] = 'text'
    let valueType: 'string' | 'number' = 'string'
    let options: Array<{ value: string; label: string }> | undefined

    if (rawType === 'number') {
      modalType = 'number'
      valueType = 'number'
    } else if (rawType === 'text') {
      modalType = 'textarea'
    } else if (rawType === 'dropdown') {
      const parsed = parseModalDropdownOptions(
        readCfgValue(cfg, ['options', 'values', 'items']) ??
          readCfgValue(asObject(cfg.dropdown), ['options', 'values', 'items'])
      )
      if (parsed.length > 0) {
        modalType = 'dropdown'
        options = parsed
      }
    }

    out.push({
      contextKey: rawField,
      valueType,
      defaultValue,
      modalField: {
        name: fieldName,
        label: String(def.label || def.name || rawField).trim(),
        type: modalType,
        required: isRequired,
        placeholder: String(def.tooltip || '').trim() || undefined,
        options,
      },
    })
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

function getValueByPath(source: Record<string, any> | null | undefined, path: string): any {
  const obj = source && typeof source === 'object' ? source : {}
  const parts = String(path || '')
    .split('.')
    .map((p) => p.trim())
    .filter(Boolean)
  if (!parts.length) return undefined
  let cursor: any = obj
  for (const part of parts) {
    if (!cursor || typeof cursor !== 'object') return undefined
    cursor = cursor[part]
  }
  return cursor
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

function isElementCollectionType(typeRaw: any): boolean {
  const t = normalizePicType(typeRaw)
  return t === 'element_list' || t === 'group_list'
}

function getControlValueForRender(
  currentDaten: Record<string, any>,
  gruppe: string,
  feld: string,
  typeRaw: any,
): any {
  const direct = getFieldValue(currentDaten, gruppe, feld)
  if (!isElementCollectionType(typeRaw)) return direct

  // Sonderfall FIELDS/FIELDS: Collection liegt auf Gruppenebene.
  if ((direct === undefined || direct === null) && gruppe && feld && gruppe.toUpperCase() === feld.toUpperCase()) {
    const groupObj = asObject((currentDaten as any)[gruppe])
    if (Object.keys(groupObj).length) return groupObj
  }

  return direct
}

function setControlValueFromEdit(
  base: Record<string, any>,
  gruppe: string,
  feld: string,
  typeRaw: any,
  value: any,
): Record<string, any> {
  if (isElementCollectionType(typeRaw) && gruppe && feld && gruppe.toUpperCase() === feld.toUpperCase()) {
    const out = { ...asObject(base) }
    out[gruppe] = asObject(value)
    return out
  }

  return setFieldValue(base, gruppe, feld, value)
}

function getFirstCollectionRow(value: any): Record<string, any> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const first = Object.values(value).find((row) => row && typeof row === 'object' && !Array.isArray(row))
  return first && typeof first === 'object' && !Array.isArray(first) ? (first as Record<string, any>) : null
}

function resolveDropdownTableToken(params: {
  tableToken: string
  currentDaten: Record<string, any>
  gruppe?: string
  elementContext?: Record<string, any> | null
}): string {
  const tableToken = String(params.tableToken || '').trim()
  if (!tableToken) return ''
  if (!tableToken.startsWith('*')) return tableToken

  const refField = tableToken.slice(1).trim()
  if (!refField) return ''

  const current = asObject(params.currentDaten)
  const gruppe = String(params.gruppe || '').trim()
  const elementContext = params.elementContext && typeof params.elementContext === 'object' ? params.elementContext : null

  const candidates: any[] = []

  // 1) ELEMENT-Ebene: nur im aktuellen Element suchen (strikt lokal)
  if (elementContext) {
    candidates.push(getValueByPath(elementContext, refField))
    candidates.push((elementContext as any)[refField])
    candidates.push((elementContext as any)[refField.toUpperCase()])
    candidates.push((elementContext as any)[refField.toLowerCase()])

    for (const candidate of candidates) {
      const s = String(candidate ?? '').trim()
      if (s) return s
    }
    return ''
  }

  // 2) GROUP-Ebene: nur in derselben Gruppe wie das Control suchen
  if (gruppe) {
    const groupCandidate = getFieldValue(current, gruppe, refField)
    const s = String(groupCandidate ?? '').trim()
    if (s) return s

    const groupObj = asObject((current as any)[gruppe])
    const direct = String((groupObj as any)[refField] ?? '').trim()
    if (direct) return direct
    const directUpper = String((groupObj as any)[refField.toUpperCase()] ?? '').trim()
    if (directUpper) return directUpper
    const directLower = String((groupObj as any)[refField.toLowerCase()] ?? '').trim()
    if (directLower) return directLower

    return ''
  }

  // 3) ROOT-Ebene (nur wenn keine Gruppe vorhanden ist)
  candidates.push(getFieldValue(current, 'ROOT', refField))
  candidates.push((current as any)[refField])
  candidates.push((current as any)[refField.toUpperCase()])
  candidates.push((current as any)[refField.toLowerCase()])

  for (const candidate of candidates) {
    const s = String(candidate ?? '').trim()
    if (s) return s
  }

  return ''
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
  const { canReleaseApply, canReleaseValidate } = useAuth()
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
  const globalExpertMode = toBoolean((defQuery.data?.meta as any)?.expert_mode)

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

  const activeModuleType = String(activeModule?.module || '').trim().toLowerCase()
  const activeModuleGuid = String(activeModule?.guid || '').trim()
  const isEditLikeModule = activeModuleType === 'edit' || activeModuleType === 'acti'
  const activeModuleFrameQuery = useQuery<FrameDefinitionResponse>({
    queryKey: ['dialog', 'module-frame', dialogGuid, activeTab, activeModuleGuid],
    queryFn: () => dialogsAPI.getFrameDefinition(activeModuleGuid),
    enabled: !!dialogGuid && isEditLikeModule && isUuidString(activeModuleGuid),
  })
  const effectiveFramePayload = useMemo(() => {
    return (activeModuleFrameQuery.data || defQuery.data?.frame || null) as FrameDefinitionResponse | null
  }, [activeModuleFrameQuery.data, defQuery.data?.frame])

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
    const et = String(activeModule?.edit_type || '').trim().toLowerCase()
    if (et) return et
    return String(defQuery.data?.edit_type || 'show_json').trim().toLowerCase()
  }, [activeModule, defQuery.data?.edit_type])

  const dialogType = String(defQuery.data?.dialog_type || '').trim().toLowerCase() || 'norm'
  const isWorkflowDialog = dialogType === 'work' || dialogType === 'acti'
  const blockApplyForRole = isWorkflowDialog && canReleaseValidate && !canReleaseApply
  const isWorkflowDraftBuilderDialog = useMemo(() => {
    const n1 = String(defQuery.data?.name || '').trim().toUpperCase()
    const n2 = String((defQuery.data?.root as any)?.SELF_NAME || '').trim().toUpperCase()
    return n1 === 'WORKFLOW_DRAFT_BUILDER_DIALOG_TEMPLATE' || n2 === 'WORKFLOW_DRAFT_BUILDER_DIALOG_TEMPLATE'
  }, [defQuery.data?.name, defQuery.data?.root])

  const workflowDraftTableOptions = useMemo(() => {
    const root = asObject(defQuery.data?.root)
    const draftTable = String(root.DRAFT_TABLE ?? root.draft_table ?? '').trim()
    const draftItemTable = String(root.DRAFT_ITEM_TABLE ?? root.draft_item_table ?? '').trim()
    return {
      draft_table: draftTable || undefined,
      draft_item_table: draftItemTable || undefined,
    }
  }, [defQuery.data?.root])

  const effectiveDialogTable = useMemo(() => {
    const override = String(dialogTable || '').trim()
    if (override) return override
    const rt = String(defQuery.data?.root_table || defQuery.data?.root?.TABLE || '').trim()
    return rt || null
  }, [dialogTable, defQuery.data?.root_table, defQuery.data?.root])

  const createFrameGuid = useMemo(() => {
    const root = asObject(defQuery.data?.root)
    const guid = String(root.CREATE_FRAME_GUID ?? root.create_frame_guid ?? '').trim()
    return guid
  }, [defQuery.data?.root])

  const createFrameQuery = useQuery<FrameDefinitionResponse>({
    queryKey: ['dialog', 'create-frame', dialogGuid, createFrameGuid],
    queryFn: () => dialogsAPI.getFrameDefinition(createFrameGuid),
    enabled: !!dialogGuid && isUuidString(createFrameGuid),
  })

  const createContextFieldDefs = useMemo(() => {
    return buildCreateContextFieldsFromFrame(createFrameQuery.data?.daten || null)
  }, [createFrameQuery.data?.daten])

  const createTableOptionsQuery = useQuery({
    queryKey: ['dialog', 'create-table-options', dialogGuid, dialogTable],
    queryFn: () => dialogsAPI.getCreateTableOptions(dialogGuid!, { dialog_table: dialogTable }),
    enabled:
      !!dialogGuid &&
      createContextFieldDefs.some((x) => x.contextKey === 'TABLE'),
  })

  const createTableOptions = useMemo(() => {
    return (createTableOptionsQuery.data?.tables || []).map((t) => ({
      value: String(t.value || '').trim(),
      label: String(t.label || t.value || '').trim(),
    }))
  }, [createTableOptionsQuery.data?.tables])

  const createRequiredSet = useMemo(() => {
    const out = new Set<string>()
    const root = asObject(defQuery.data?.root)
    const raw = readCfgValue(root, ['CREATE_REQUIRED', 'create_required'])
    const values = Array.isArray(raw) ? raw : typeof raw === 'string' ? String(raw).split(',') : []
    values.forEach((entry) => {
      const key = String(entry || '').trim().toUpperCase()
      if (key) out.add(key)
    })
    return out
  }, [defQuery.data?.root])

  const createDefaultsByContextKey = useMemo(() => {
    const out: Record<string, string> = {}
    const root = asObject(defQuery.data?.root)
    const raw = readCfgValue(root, ['CREATE_DEFAULTS', 'create_defaults'])
    const obj = asObject(raw)

    Object.entries(obj).forEach(([k, v]) => {
      const key = String(k || '').trim().toUpperCase()
      if (!key) return
      out[key] = String(v ?? '')
    })

    return out
  }, [defQuery.data?.root])

  const createContextModalFields = useMemo(() => {
    return createContextFieldDefs.map((x) => ({
      ...x.modalField,
      type:
        x.contextKey === 'TABLE' && (!Array.isArray(x.modalField.options) || x.modalField.options.length === 0)
          ? 'dropdown'
          : x.modalField.type,
      options:
        x.contextKey === 'TABLE' && (!Array.isArray(x.modalField.options) || x.modalField.options.length === 0)
          ? createTableOptions
          : x.modalField.options,
      required: Boolean(x.modalField.required) || createRequiredSet.has(x.contextKey),
    }))
  }, [createContextFieldDefs, createRequiredSet, createTableOptions])

  const createContextInitialValues = useMemo(() => {
    const out: Record<string, string> = {}
    createContextFieldDefs.forEach((x) => {
      const dialogDefault = createDefaultsByContextKey[x.contextKey]
      if (dialogDefault != null) {
        out[x.modalField.name] = dialogDefault
      } else if (x.defaultValue != null) {
        out[x.modalField.name] = x.defaultValue
      } else if (x.contextKey === 'TABLE' && createTableOptions.length > 0) {
        out[x.modalField.name] = String(createTableOptions[0].value || '')
      } else if (x.modalField.type === 'dropdown' && Array.isArray(x.modalField.options) && x.modalField.options.length > 0) {
        out[x.modalField.name] = String(x.modalField.options[0].value || '')
      }
    })
    return out
  }, [createContextFieldDefs, createDefaultsByContextKey, createTableOptions])

  const lastCallScopeKey = useMemo(() => {
    const dg = String(dialogGuid || '').trim().toLowerCase()
    const table = String(effectiveDialogTable || '').trim().toUpperCase()
    if (!dg || !table) return ''
    return `${dg}::${table}`
  }, [dialogGuid, effectiveDialogTable])

  const persistContextKey = lastCallScopeKey
  const debugLastCallScopeClient = lastCallScopeKey

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
  // pdvm_edit is the central field editor; edit_user shares this core path.
  const isPdvmEditCore = isPdvmEdit || isPicEditor
  const isControlEditor = editType === 'edit_control'
  const usesUnifiedControlMatrix = isPdvmEditCore || isControlEditor
  const isFieldEditor = usesUnifiedControlMatrix
  const useUnifiedControlContract = isFieldEditor
  const CONTROL_TEMPLATE_UID = '55555555-5555-5555-5555-555555555555'
  const [importStep, setImportStep] = useState(1)

  useEffect(() => {
    if (!isImportEditor) return
    setImportStep(1)
  }, [isImportEditor, selectedUid, effectiveDialogTable])
  const frameDaten = (effectiveFramePayload?.daten || null) as Record<string, any> | null
  const frameRoot = (effectiveFramePayload?.root || {}) as Record<string, any>

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

    return { tabs: items.length, items }
  }, [frameRoot])

  const [picActiveTab, setPicActiveTab] = useState(1)
  const [picDraft, setPicDraft] = useState<Record<string, any> | null>(null)
  const [picDirty, setPicDirty] = useState(false)
  const [activeDraft, setActiveDraft] = useState<DialogDraftResponse | null>(null)
  const [draftValidationIssues, setDraftValidationIssues] = useState<DialogValidationIssue[]>([])
  const [workflowDraftGuid, setWorkflowDraftGuid] = useState<string | null>(null)
  const [workflowDraftStatus, setWorkflowDraftStatus] = useState<string | null>(null)
  const [workflowDraftError, setWorkflowDraftError] = useState<string | null>(null)
  const [workflowDraftBusy, setWorkflowDraftBusy] = useState(false)
  const [workflowDraftValidation, setWorkflowDraftValidation] = useState<WorkflowDraftValidationResponse | null>(null)

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

  const lastCallRuntimeState = useMemo(() => {
    if (autoLastCallError) return 'fallback_to_view'
    if (recordQuery.isLoading) return 'loading_record'
    if (recordQuery.isError) return 'record_error'
    if (selectedUid) return 'record_selected'
    return 'view_mode'
  }, [autoLastCallError, recordQuery.isLoading, recordQuery.isError, selectedUid])

  const isDraftMode = !!activeDraft
  const currentDaten = activeDraft?.daten || recordQuery.data?.daten || null
  const currentName = activeDraft?.name || recordQuery.data?.name || ''
  const unifiedControlMatrix = useMemo(() => {
    if (!usesUnifiedControlMatrix) return null
    const source: UnifiedControlSource = isPdvmEditCore ? 'frame_fields' : 'record_groups'
    return buildUnifiedControlMatrix(source, {
      frameDaten,
      currentDaten: (picDraft ? picDraft : currentDaten) as Record<string, any> | null,
      excludeRootGroup: isPdvmEditCore,
    })
  }, [usesUnifiedControlMatrix, isPdvmEditCore, frameDaten, picDraft, currentDaten])

  const controlEditModel = useMemo(() => {
    if (!isControlEditor) return null
    return unifiedControlMatrix
  }, [isControlEditor, unifiedControlMatrix])
  const effectivePicDefs = useMemo(() => {
    if (usesUnifiedControlMatrix) {
      const defs = unifiedControlMatrix?.defs || []
      if (isPdvmEditCore) {
        return defs.filter((d) => String(d.gruppe || '').trim().toUpperCase() !== 'ROOT')
      }
      return defs
    }
    return picDefs
  }, [usesUnifiedControlMatrix, unifiedControlMatrix, picDefs, isPdvmEditCore])

  const controlResolveListQuery = useQuery({
    queryKey: ['control-dict', 'list', 'resolve', effectiveDialogTable],
    queryFn: () => controlDictAPI.listControls({ limit: 2000, skip: 0 }),
    enabled: useUnifiedControlContract,
  })

  const controlTemplateQuery = useQuery({
    queryKey: ['control-dict', 'template', CONTROL_TEMPLATE_UID],
    queryFn: () => controlDictAPI.getControl(CONTROL_TEMPLATE_UID),
    enabled: useUnifiedControlContract,
  })

  const controlTemplateData = useMemo(() => asObject(controlTemplateQuery.data?.daten), [controlTemplateQuery.data])
  const controlTemplatePayload = useMemo(() => {
    const direct = asObject(controlTemplateData.CONTROL)
    if (Object.keys(direct).length) return direct
    const templates = asObject(controlTemplateData.TEMPLATES)
    return asObject(templates.CONTROL)
  }, [controlTemplateData])

  const matchedControlRefs = useMemo(() => {
    if (!useUnifiedControlContract) return [] as Array<{ uid: string; gruppe: string; feld: string }>

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
        const gruppe = String(d.gruppe || 'ROOT').trim().toUpperCase()
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
  }, [useUnifiedControlContract, controlResolveListQuery.data, effectivePicDefs, effectiveDialogTable])

  const resolvedControlQueries = useQueries({
    queries: matchedControlRefs.map((entry) => ({
      queryKey: ['control-dict', 'resolved', entry.uid],
      queryFn: () => controlDictAPI.getControl(entry.uid),
      enabled: useUnifiedControlContract,
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

  const resolvedControlByUid = useMemo(() => {
    const out: Record<string, { uid: string; data: Record<string, any> }> = {}
    matchedControlRefs.forEach((entry, idx) => {
      const data = asObject(resolvedControlQueries[idx]?.data?.daten)
      if (!Object.keys(data).length) return
      out[entry.uid] = { uid: entry.uid, data }
    })
    return out
  }, [matchedControlRefs, resolvedControlQueries])

  const elementUidLabels = useMemo(() => {
    const out: Record<string, string> = {}

    const rows = controlResolveListQuery.data?.items || []
    rows.forEach((row: any) => {
      const uid = String(row?.uid || '').trim()
      if (!uid) return
      const label = String(row?.label || row?.name || '').trim()
      if (label) out[uid] = label
    })

    Object.entries(resolvedControlByUid).forEach(([uid, entry]) => {
      const controlObj = asObject(asObject((entry as any).data).CONTROL)
      const rootObj = asObject(asObject((entry as any).data).ROOT)
      const label = String(controlObj.LABEL || rootObj.NAME || controlObj.NAME || '').trim()
      if (label) out[uid] = label
    })

    return out
  }, [controlResolveListQuery.data, resolvedControlByUid])

  const controlUidByToken = useMemo(() => {
    const out: Record<string, string> = {}

    const add = (token: any, uid: string) => {
      const key = normalizeControlToken(token)
      if (!key) return
      if (!out[key]) out[key] = uid
    }

    const rows = controlResolveListQuery.data?.items || []
    rows.forEach((row: any) => {
      const uid = String(row?.uid || '').trim()
      if (!isUuidString(uid)) return
      add(uid, uid)
      add(row?.name, uid)
      add(row?.label, uid)
      add(row?.field, uid)
      add(row?.feld, uid)
    })

    Object.values(resolvedControlByUid).forEach((entry: any) => {
      const data = asObject(entry?.data)
      const control = extractControlPayloadFromRecord(data)
      const root = asObject(data.ROOT)
      const uid = String(root.SELF_GUID || entry?.uid || '').trim()
      if (!isUuidString(uid)) return
      add(uid, uid)
      add(control.FIELD, uid)
      add(control.FELD, uid)
      add(control.NAME, uid)
      add(control.LABEL, uid)
      add(root.SELF_NAME, uid)
      add(root.NAME, uid)
    })

    return out
  }, [controlResolveListQuery.data, resolvedControlByUid])

  const frameFieldsSelectedControlUids = useMemo(() => {
    if (!isFieldEditor) return [] as string[]
    if (String(effectiveDialogTable || '').trim().toLowerCase() !== 'sys_framedaten') return [] as string[]

    const current = (picDraft ? picDraft : currentDaten || {}) as Record<string, any>
    const rows = asObject((current as any).FIELDS)
    const set = new Set<string>()

    Object.entries(rows).forEach(([rowUid, row]: [string, any]) => {
      const rowObj = asObject(row)
      const uidToken = String(rowUid || '').trim()
      const fieldRaw = String(readCfgValue(rowObj, ['FIELD', 'FELD']) || '').trim()
      const fieldUid =
        resolveControlUidToken(uidToken, controlUidByToken) ||
        resolveControlUidToken(fieldRaw, controlUidByToken)
      if (isUuidString(fieldUid)) set.add(fieldUid)
    })

    return Array.from(set)
  }, [isFieldEditor, effectiveDialogTable, picDraft, currentDaten, controlUidByToken])

  const frameFieldsSelectedControlQueries = useQueries({
    queries: frameFieldsSelectedControlUids.map((uid) => ({
      queryKey: ['control-dict', 'frame-fields-selected', uid],
      queryFn: () => controlDictAPI.getControl(uid),
      enabled: isFieldEditor && String(effectiveDialogTable || '').trim().toLowerCase() === 'sys_framedaten',
    })),
  })

  const frameFieldsControlPayloadByUid = useMemo(() => {
    const out: Record<string, Record<string, any>> = {}
    frameFieldsSelectedControlUids.forEach((uid, idx) => {
      const daten = asObject(frameFieldsSelectedControlQueries[idx]?.data?.daten)
      if (!Object.keys(daten).length) return
      const payload = extractControlPayloadFromRecord(daten)
      if (!Object.keys(payload).length) return
      out[uid] = payload
    })
    return out
  }, [frameFieldsSelectedControlUids, frameFieldsSelectedControlQueries])

  const effectivePicDefsResolved = useMemo(() => {
    return effectivePicDefs.map((d) => {
      const gruppe = String(d.gruppe || 'ROOT').trim().toUpperCase()
      const feld = String(d.feld || '').trim().toUpperCase()
      const fieldKey = String(d.key || `CTRL.${gruppe}.${feld}`)
      const key = `${gruppe}::${feld}`
      const resolved = resolvedControlByGroupField[key]
      const controlData = asObject(resolved?.data)
      const wrappedPayload = asObject(controlData.CONTROL)
      // Older/newer control_dict records may be stored as flat payload (no CONTROL wrapper).
      const resolvedPayload = Object.keys(wrappedPayload).length
        ? wrappedPayload
        : (() => {
            const flat = { ...controlData }
            delete (flat as any).ROOT
            delete (flat as any).CONTROL
            return flat
          })()
      const inheritedPayload = {
        ...controlTemplatePayload,
        ...resolvedPayload,
      }

      if (!Object.keys(inheritedPayload).length) return d

      const name = String(inheritedPayload.NAME ?? d.name ?? d.feld ?? '').trim()
      const label = String(inheritedPayload.LABEL ?? name ?? '').trim()
      const typeRaw = String(inheritedPayload.TYPE ?? d.type ?? '').trim()
      const tooltip = String(inheritedPayload.TOOLTIP ?? d.tooltip ?? '').trim()
      const readOnly = inheritedPayload.READ_ONLY
      // GUID-only frame FIELDS often miss gruppe/feld in frame data.
      // In that case, hydrate from resolved sys_control_dict payload.
      const hydratedGruppe = String(inheritedPayload.GRUPPE ?? d.gruppe ?? 'ROOT').trim()
      const hydratedFeld = String(inheritedPayload.FIELD ?? inheritedPayload.FELD ?? d.feld ?? '').trim()
      const tabRaw = d.tab ?? inheritedPayload.TAB ?? inheritedPayload.EDIT_TAB
      const hydratedTab = Number(tabRaw ?? 1) || 1
      const configs = asObject(d.configs)
      configs.control_flat = buildFlatPicControl({
        controlData: {
          ROOT: asObject(controlData.ROOT),
          CONTROL: inheritedPayload,
        },
        fieldKey,
        value: null,
        valueTimeKey: 'ORIGINAL',
      })
      delete configs.control_original
      delete configs.control_root
      delete configs.control_payload

      return {
        ...d,
        tab: hydratedTab,
        gruppe: hydratedGruppe || d.gruppe,
        feld: hydratedFeld || d.feld,
        name: name || d.name,
        label: label || d.label,
        type: typeRaw || d.type,
        tooltip: tooltip || d.tooltip,
        read_only: readOnly ?? d.read_only,
        configs,
      }
    })
  }, [effectivePicDefs, resolvedControlByGroupField, controlTemplatePayload])

  const uiPicDefs = useMemo(() => {
    return effectivePicDefsResolved
  }, [effectivePicDefsResolved])

  const buildControlDebugForField = (
    def: PicDef,
    fieldKey: string,
    rawValue: any,
    resolvedControl: { uid: string; data: Record<string, any> } | null
  ): Record<string, any> => {
    const current = (picDraft ? picDraft : currentDaten || {}) as Record<string, any>
    const normalizedType = normalizePicType(def.type)
    const isDateTimeType = normalizedType === 'datetime' || normalizedType === 'date' || normalizedType === 'time'
    const dateTimeDebug = {
      DATETIME_MODE: isDateTimeType ? normalizedType : undefined,
      DATETIME_PDVM_RAW: isDateTimeType ? rawValue : undefined,
    }
    const resolvedData = asObject(resolvedControl?.data)
    const resolvedPayload = asObject(resolvedData.CONTROL)
    const controlSourceForGoSelect = Object.keys(resolvedPayload).length ? resolvedPayload : asObject((def as any).CONTROL)
    const goSelectTableToken = normalizedType === 'go_select_view' ? resolveGoSelectViewTable(def.configs, controlSourceForGoSelect) : ''
    const goSelectWarning = normalizedType === 'go_select_view' && !goSelectTableToken
      ? 'go_select_view: CONFIGS.go_select_view.table ist leer.'
      : ''
    const selectType = normalizedType === 'multi_dropdown' ? 'multi_dropdown' : 'dropdown'
    const selectCfg = resolveSelectConfigByType({
      type: selectType,
      cfgElements: asObject(asObject(def.configs).control_flat).CONFIGS_ELEMENTS,
      cfgControlConfigs: asObject(asObject(def.configs).control_flat).CONFIGS,
      cfgLegacy: asObject(def.configs),
    })
    const tableToken = String(readCfgValue(selectCfg, ['table']) || '').trim()
    const resolvedTable = resolveDropdownTableToken({
      tableToken,
      currentDaten: current,
      gruppe: String(def.gruppe || '').trim(),
    })
    const tableWarning =
      tableToken.startsWith('*') && !resolvedTable
        ? `Dropdown TABLE-Referenz '${tableToken}' konnte nicht aufgelöst werden.`
        : ''

    if (Object.keys(resolvedPayload).length) {
      const payload = buildFlatPicControl({
        controlData: resolvedData,
        fieldKey,
        value: rawValue,
        valueTimeKey: 'ORIGINAL',
      })
      return {
        ...payload,
        ...dateTimeDebug,
        EXPERT_MODE: globalExpertMode,
        FORCE_DEBUG_BUTTON: normalizedType === 'go_select_view',
        DROPDOWN_TABLE_TOKEN: tableToken || undefined,
        DROPDOWN_TABLE_RESOLVED: resolvedTable || undefined,
        DROPDOWN_TABLE_WARNING: tableWarning || undefined,
        MULTI_DROPDOWN_TABLE_TOKEN: normalizedType === 'multi_dropdown' ? (tableToken || undefined) : undefined,
        MULTI_DROPDOWN_TABLE_RESOLVED: normalizedType === 'multi_dropdown' ? (resolvedTable || undefined) : undefined,
        MULTI_DROPDOWN_TABLE_WARNING: normalizedType === 'multi_dropdown' ? (tableWarning || undefined) : undefined,
        GO_SELECT_TABLE_TOKEN: goSelectTableToken || undefined,
        GO_SELECT_TABLE_RESOLVED: goSelectTableToken || undefined,
        GO_SELECT_TABLE_WARNING: goSelectWarning || undefined,
      }
    }

    const cfgFlat = asObject(asObject(def.configs).control_flat)
    if (Object.keys(cfgFlat).length) {
      return {
        ...cfgFlat,
        ...dateTimeDebug,
        EXPERT_MODE: globalExpertMode,
        FORCE_DEBUG_BUTTON: normalizedType === 'go_select_view',
        FIELD_KEY: String((cfgFlat as any).FIELD_KEY || fieldKey).trim(),
        VALUE: normalizeValueEnvelope(rawValue),
        VALUE_TIME_KEY: String((cfgFlat as any).VALUE_TIME_KEY || 'ORIGINAL').trim() || 'ORIGINAL',
        DROPDOWN_TABLE_TOKEN: tableToken || undefined,
        DROPDOWN_TABLE_RESOLVED: resolvedTable || undefined,
        DROPDOWN_TABLE_WARNING: tableWarning || undefined,
        MULTI_DROPDOWN_TABLE_TOKEN: normalizedType === 'multi_dropdown' ? (tableToken || undefined) : undefined,
        MULTI_DROPDOWN_TABLE_RESOLVED: normalizedType === 'multi_dropdown' ? (resolvedTable || undefined) : undefined,
        MULTI_DROPDOWN_TABLE_WARNING: normalizedType === 'multi_dropdown' ? (tableWarning || undefined) : undefined,
        GO_SELECT_TABLE_TOKEN: goSelectTableToken || undefined,
        GO_SELECT_TABLE_RESOLVED: goSelectTableToken || undefined,
        GO_SELECT_TABLE_WARNING: goSelectWarning || undefined,
      }
    }

    return {
      ...dateTimeDebug,
      EXPERT_MODE: globalExpertMode,
      FORCE_DEBUG_BUTTON: normalizedType === 'go_select_view',
      FIELD_KEY: String(fieldKey || '').trim(),
      SOURCE_PATH: String(def.source_path || 'root').trim() || 'root',
      VALUE: normalizeValueEnvelope(rawValue),
      VALUE_TIME_KEY: 'ORIGINAL',
      DROPDOWN_TABLE_TOKEN: tableToken || undefined,
      DROPDOWN_TABLE_RESOLVED: resolvedTable || undefined,
      DROPDOWN_TABLE_WARNING: tableWarning || undefined,
      MULTI_DROPDOWN_TABLE_TOKEN: normalizedType === 'multi_dropdown' ? (tableToken || undefined) : undefined,
      MULTI_DROPDOWN_TABLE_RESOLVED: normalizedType === 'multi_dropdown' ? (resolvedTable || undefined) : undefined,
      MULTI_DROPDOWN_TABLE_WARNING: normalizedType === 'multi_dropdown' ? (tableWarning || undefined) : undefined,
      GO_SELECT_TABLE_TOKEN: goSelectTableToken || undefined,
      GO_SELECT_TABLE_RESOLVED: goSelectTableToken || undefined,
      GO_SELECT_TABLE_WARNING: goSelectWarning || undefined,
    }
  }

  const effectivePicTabs = useMemo(() => {
    if (usesUnifiedControlMatrix) {
      const headByIndex = new Map<number, string>()
      ;(picTabs.items || []).forEach((t) => {
        const idx = Number(t.index || 0)
        if (idx > 0) headByIndex.set(idx, String(t.head || '').trim())
      })

      const items = (unifiedControlMatrix?.tabs || []).map((t) => {
        const idx = Number(t.index || 0)
        const mappedHead = headByIndex.get(idx)
        return {
          index: t.index,
          head: mappedHead || t.head,
        }
      })

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
    mutationFn: async (payload: { name: string; is_template?: boolean; create_context?: Record<string, any> }) => {
      const tableOverride = String(effectiveDialogTable || dialogTable || '').trim()
      return dialogsAPI.startDraft(
        dialogGuid!,
        {
          name: payload.name,
          template_uid: '66666666-6666-6666-6666-666666666666',
          is_template: payload.is_template,
          create_context: payload.create_context,
        },
        tableOverride ? { dialog_table: tableOverride } : undefined
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

      if (isWorkflowDraftBuilderDialog) {
        const root = asObject((draft as any)?.daten?.ROOT)
        const workflowDraftGuid = String(root.WORKFLOW_DRAFT_GUID || '').trim()
        if (workflowDraftGuid && isUuidString(workflowDraftGuid)) {
          setWorkflowDraftGuid(workflowDraftGuid)
        }
      }
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
    if (!d) return ''

    const root = asObject(d.root)
    const rootLevel = String(readCfgValue(root, ['LEVEL']) ?? '').trim()
    if (rootLevel) return rootLevel

    const rootSelfName = String(readCfgValue(root, ['SELF_NAME', 'ROOT_SELF_NAME']) ?? '').trim()
    if (rootSelfName) return rootSelfName

    const fallbackName = String(d.name || '').trim()
    if (fallbackName) return fallbackName

    return String(d.uid || '').trim()
  }, [defQuery.data])

  const selectedRecordSubtitle = useMemo(() => {
    if (activeTab === viewTabIndex) return ''

    const root = asObject(asObject(currentDaten).ROOT)
    const name = String(currentName || readCfgValue(root, ['SELF_NAME']) || '').trim()
    const rawUid = String(selectedUid || readCfgValue(root, ['SELF_GUID']) || '').trim()
    const uid8 = rawUid.replace(/-/g, '').slice(0, 8)

    if (!name && !uid8) return ''
    if (name && uid8) return `${name} (${uid8})`
    return name || uid8
  }, [activeTab, viewTabIndex, currentDaten, currentName, selectedUid])

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
    if (!isFieldEditor) {
      return [] as Array<
        | { kind: 'system'; fieldKey: string; table: string; datasetUid: string; field: string; group?: string }
        | { kind: 'view'; fieldKey: string; viewGuid: string; tableOverride?: string }
      >
    }

    const out: Array<
      | { kind: 'system'; fieldKey: string; table: string; datasetUid: string; field: string; group?: string }
      | { kind: 'view'; fieldKey: string; viewGuid: string; tableOverride?: string }
    > = []

    const current = (picDraft ? picDraft : currentDaten || {}) as Record<string, any>

    uiPicDefs.forEach((def) => {
      const type = normalizePicType(def.type)
      if (type !== 'dropdown' && type !== 'multi_dropdown') return
      const selectType = type === 'multi_dropdown' ? 'multi_dropdown' : 'dropdown'

      const flatControl = asObject(def.configs?.control_flat)
      const flatControlConfigs = asObject((flatControl as any).CONFIGS ?? (flatControl as any).configs)
      const cfgElements = asObject((flatControl as any).CONFIGS_ELEMENTS ?? (flatControl as any).configs_elements)
      const cfgLegacy = asObject(def.configs)
      const cfg = resolveSelectConfigByType({
        type: selectType,
        cfgElements,
        cfgControlConfigs: flatControlConfigs,
        cfgLegacy,
      })

      const keyRaw = String(readCfgValue(cfg, ['key', 'dataset_uid', 'view_guid']) || '').trim()
      const field = String(readCfgValue(cfg, ['field', 'feld']) || '').trim()
      const tableToken = String(readCfgValue(cfg, ['table']) || '').trim()
      const group = String(readCfgValue(cfg, ['group', 'gruppe']) || '').trim()
      const gruppe = String(def.gruppe || '').trim()
      const table = resolveDropdownTableToken({ tableToken, currentDaten: current, gruppe })

      const fieldKey = String(def.key || `${def.gruppe || ''}.${def.feld || ''}`)

      if (group.toUpperCase() === '*VIEW' && keyRaw) {
        out.push({ kind: 'view', fieldKey, viewGuid: keyRaw, tableOverride: table || undefined })
        return
      }

      if (!keyRaw || !field || !table) return
      out.push({ kind: 'system', fieldKey, table, datasetUid: keyRaw, field, group: group || undefined })
    })
    return out
  }, [isFieldEditor, uiPicDefs, picDraft, currentDaten])

  const dropdownQueries = useQueries({
    queries: dropdownFieldConfigs.map((cfg) => ({
      queryKey:
        cfg.kind === 'system'
          ? ['systemdaten', 'dropdown', cfg.table, cfg.datasetUid, cfg.field, cfg.group || '']
          : ['views', 'dropdown-source', cfg.viewGuid, cfg.tableOverride || ''],
      queryFn: () => {
        if (cfg.kind === 'system') {
          return systemdatenAPI.getDropdown({
            table: cfg.table,
            dataset_uid: cfg.datasetUid,
            field: cfg.field,
            group: cfg.group,
          })
        }
        return viewsAPI.postMatrix(
          cfg.viewGuid,
          {
            include_historisch: false,
            limit: 1000,
            offset: 0,
          },
          cfg.tableOverride ? { table: cfg.tableOverride } : undefined,
        )
      },
      enabled: isFieldEditor,
    })),
  })

  const dropdownOptionsByFieldKey = useMemo(() => {
    const out: Record<string, PdvmDropdownOption[]> = {}
    dropdownFieldConfigs.forEach((cfg, idx) => {
      const res = dropdownQueries[idx]

      if (cfg.kind === 'system') {
        const options = (res?.data as any)?.options || []
        out[cfg.fieldKey] = options.map((opt: any) => ({ value: String(opt.key), label: String(opt.value) }))
        return
      }

      const rows = Array.isArray((res?.data as any)?.rows) ? (res?.data as any).rows : []
      out[cfg.fieldKey] = rows
        .filter((row: any) => row && typeof row === 'object' && String(row.kind || '').toLowerCase() === 'data' && row.uid)
        .map((row: any) => ({ value: String(row.uid), label: String(row.name || row.uid) }))
    })
    return out
  }, [dropdownFieldConfigs, dropdownQueries])

  const elementFrameRefs = useMemo(() => {
    if (!isPdvmEditCore || !isFieldEditor) return [] as Array<{ fieldKey: string; frameGuid: string }>

    const current = (picDraft ? picDraft : currentDaten || {}) as Record<string, any>
    const refs: Array<{ fieldKey: string; frameGuid: string }> = []

    uiPicDefs.forEach((def) => {
      const type = normalizePicType(def.type)
      if (type !== 'element_list' && type !== 'group_list') return

      const gruppe = String(def.gruppe || 'ROOT').trim()
      const feld = String(def.feld || '').trim()
      if (!feld) return

      const frameGuidField = `${feld}_GUID`
      const frameGuidRaw = getFieldValue(current, gruppe, frameGuidField)
      const frameGuid = String(frameGuidRaw || '').trim()
      if (!isUuidString(frameGuid)) return

      const fieldKey = String(def.key || `${gruppe}.${feld}`)
      refs.push({ fieldKey, frameGuid })
    })

    const uniqueByField = new Map<string, { fieldKey: string; frameGuid: string }>()
    refs.forEach((ref) => {
      if (!uniqueByField.has(ref.fieldKey)) uniqueByField.set(ref.fieldKey, ref)
    })

    return Array.from(uniqueByField.values())
  }, [isPdvmEditCore, isFieldEditor, uiPicDefs, picDraft, currentDaten])

  const elementFrameQueries = useQueries({
    queries: elementFrameRefs.map((ref) => ({
      queryKey: ['dialogs', 'frame', ref.frameGuid],
      queryFn: () => dialogsAPI.getFrameDefinition(ref.frameGuid),
      enabled: isPdvmEditCore && !!ref.frameGuid,
    })),
  })

  const elementFrameConfigByFieldKey = useMemo(() => {
    const out: Record<string, { fields: PdvmElementField[]; template: Record<string, any>; frame: FrameDefinitionResponse }> = {}
    elementFrameRefs.forEach((ref, idx) => {
      const frame = elementFrameQueries[idx]?.data as FrameDefinitionResponse | undefined
      if (!frame?.daten) return
      const fields = buildElementFieldsFromFrameDaten(frame.daten, globalExpertMode)
      if (!fields.length) return
      out[ref.fieldKey] = {
        fields,
        template: buildElementTemplateFromFields(fields),
        frame,
      }
    })
    return out
  }, [elementFrameRefs, elementFrameQueries])

  const elementFieldCandidates = useMemo(() => {
    if (!usesUnifiedControlMatrix) return [] as string[]
    const out = new Set<string>()

    uiPicDefs.forEach((def) => {
      const type = normalizePicType(def.type)
      if (type !== 'element_list' && type !== 'group_list') return

      const fieldKey = String(def.key || `${def.gruppe || ''}.${def.feld || ''}`)
      const frameFields = elementFrameConfigByFieldKey[fieldKey]?.fields || []
      const cfgFieldsRaw = resolveElementEditorConfig(def.configs).fields || []
      const cfgFields = Array.isArray(cfgFieldsRaw) ? cfgFieldsRaw : []
      const source = frameFields.length ? frameFields : cfgFields

      source.forEach((field: any) => {
        const nameUpper = String(field?.name || '').trim().toUpperCase()
        if (nameUpper) out.add(nameUpper)
      })
    })

    return Array.from(out)
  }, [usesUnifiedControlMatrix, uiPicDefs, elementFrameConfigByFieldKey])

  const elementFieldControlRefs = useMemo(() => {
    if (!usesUnifiedControlMatrix) return [] as Array<{ fieldUpper: string; uid: string }>
    const rows = controlResolveListQuery.data?.items || []
    if (!rows.length || !elementFieldCandidates.length) return [] as Array<{ fieldUpper: string; uid: string }>

    const tableNorm = String(effectiveDialogTable || '').trim().toLowerCase()
    const refs: Array<{ fieldUpper: string; uid: string }> = []

    elementFieldCandidates.forEach((fieldUpper) => {
      const candidates = rows
        .map((row) => {
          const uid = String(row.uid || '').trim()
          const rowField = String(row.field || '').trim().toUpperCase()
          const rowTable = String(row.table || '').trim().toLowerCase()
          const rowGroup = String(row.gruppe || '').trim().toUpperCase()
          if (!uid || !rowField || rowField !== fieldUpper) return null
          let score = 0
          if (tableNorm && rowTable === tableNorm) score += 10
          if (!rowTable) score += 5
          if (rowGroup === 'ROOT') score += 2
          if (!rowGroup) score += 1
          return { uid, score }
        })
        .filter(Boolean) as Array<{ uid: string; score: number }>

      if (!candidates.length) return
      candidates.sort((a, b) => b.score - a.score)
      refs.push({ fieldUpper, uid: candidates[0].uid })
    })

    return refs
  }, [usesUnifiedControlMatrix, controlResolveListQuery.data, elementFieldCandidates, effectiveDialogTable])

  const elementFieldControlQueries = useQueries({
    queries: elementFieldControlRefs.map((entry) => ({
      queryKey: ['control-dict', 'element-field', entry.uid],
      queryFn: () => controlDictAPI.getControl(entry.uid),
      enabled: usesUnifiedControlMatrix,
    })),
  })

  const elementFieldControlByName = useMemo(() => {
    const out: Record<string, Record<string, any>> = {}
    elementFieldControlRefs.forEach((entry, idx) => {
      const daten = asObject(elementFieldControlQueries[idx]?.data?.daten)
      const controlPayload = asObject(daten.CONTROL)
      if (!Object.keys(controlPayload).length) return
      out[entry.fieldUpper] = daten
    })
    return out
  }, [elementFieldControlRefs, elementFieldControlQueries])

  const elementDropdownFieldConfigs = useMemo(() => {
    if (!isFieldEditor) {
      return [] as Array<
        | { kind: 'system'; fieldCompositeKey: string; table: string; datasetUid: string; field: string; group?: string }
        | { kind: 'view'; fieldCompositeKey: string; viewGuid: string; tableOverride?: string }
      >
    }

    const out: Array<
      | { kind: 'system'; fieldCompositeKey: string; table: string; datasetUid: string; field: string; group?: string }
      | { kind: 'view'; fieldCompositeKey: string; viewGuid: string; tableOverride?: string }
    > = []

    const current = (picDraft ? picDraft : currentDaten || {}) as Record<string, any>

    uiPicDefs.forEach((def) => {
      const type = normalizePicType(def.type)
      if (type !== 'element_list' && type !== 'group_list') return

      const parentFieldKey = String(def.key || `${def.gruppe || ''}.${def.feld || ''}`)
      const gruppe = String(def.gruppe || '').trim()
      const feld = String(def.feld || '').trim()
      const parentCollection = gruppe && feld ? getFieldValue(current, gruppe, feld) : null
      const firstElementContext = getFirstCollectionRow(parentCollection)
      const frameFields = elementFrameConfigByFieldKey[parentFieldKey]?.fields || []
      const cfgFieldsRaw = resolveElementEditorConfig(def.configs).fields || []
      const cfgFields = Array.isArray(cfgFieldsRaw) ? cfgFieldsRaw : []
      const source = frameFields.length ? frameFields : cfgFields

      source.forEach((field: any) => {
        const name = String(field?.name || '').trim()
        if (!name) return
        const lookupKey = name.toUpperCase()
        const controlData = asObject(elementFieldControlByName[lookupKey])
        const controlPayload = asObject(controlData.CONTROL)
        const controlConfigs = asObject((controlPayload as any).CONFIGS ?? (controlPayload as any).configs)
        const cfgElements = asObject((controlPayload as any).CONFIGS_ELEMENTS ?? (controlPayload as any).configs_elements)
        const fieldType = mapPicTypeToElementFieldType(controlPayload.TYPE)
        const selectType = fieldType === 'multi_dropdown' ? 'multi_dropdown' : 'dropdown'
        const cfg = resolveSelectConfigByType({
          type: selectType,
          cfgElements,
          cfgControlConfigs: controlConfigs,
          cfgLegacy: asObject(field),
        })
        if (!Object.keys(cfg).length) return

        const keyRaw = String(readCfgValue(cfg, ['key', 'dataset_uid', 'view_guid']) || '').trim()
        const fieldName = String(readCfgValue(cfg, ['field', 'feld']) || '').trim()
        const tableToken = String(readCfgValue(cfg, ['table']) || '').trim()
        const table = resolveDropdownTableToken({
          tableToken,
          currentDaten: current,
          gruppe,
          elementContext: firstElementContext,
        })
        const group = String(readCfgValue(cfg, ['group', 'gruppe']) || '').trim()
        const fieldCompositeKey = `${parentFieldKey}::${name}`

        if (group.toUpperCase() === '*VIEW' && keyRaw) {
          out.push({ kind: 'view', fieldCompositeKey, viewGuid: keyRaw, tableOverride: table || undefined })
          return
        }

        if (!keyRaw || !fieldName || !table) return
        out.push({ kind: 'system', fieldCompositeKey, table, datasetUid: keyRaw, field: fieldName, group: group || undefined })
      })
    })

    return out
  }, [isFieldEditor, uiPicDefs, elementFrameConfigByFieldKey, elementFieldControlByName, picDraft, currentDaten])

  const elementDropdownQueries = useQueries({
    queries: elementDropdownFieldConfigs.map((cfg) => ({
      queryKey:
        cfg.kind === 'system'
          ? ['systemdaten', 'dropdown', cfg.table, cfg.datasetUid, cfg.field, cfg.group || '']
          : ['views', 'dropdown-source', cfg.viewGuid, cfg.tableOverride || ''],
      queryFn: () => {
        if (cfg.kind === 'system') {
          return systemdatenAPI.getDropdown({
            table: cfg.table,
            dataset_uid: cfg.datasetUid,
            field: cfg.field,
            group: cfg.group,
          })
        }
        return viewsAPI.postMatrix(
          cfg.viewGuid,
          {
            include_historisch: false,
            limit: 1000,
            offset: 0,
          },
          cfg.tableOverride ? { table: cfg.tableOverride } : undefined,
        )
      },
      enabled: isFieldEditor,
    })),
  })

  const elementDropdownOptionsByCompositeKey = useMemo(() => {
    const out: Record<string, PdvmDropdownOption[]> = {}
    elementDropdownFieldConfigs.forEach((cfg, idx) => {
      const res = elementDropdownQueries[idx]
      if (cfg.kind === 'system') {
        const options = (res?.data as any)?.options || []
        out[cfg.fieldCompositeKey] = options.map((opt: any) => ({ value: String(opt.key), label: String(opt.value) }))
        return
      }

      const rows = Array.isArray((res?.data as any)?.rows) ? (res?.data as any).rows : []
      out[cfg.fieldCompositeKey] = rows
        .filter((row: any) => row && typeof row === 'object' && String(row.kind || '').toLowerCase() === 'data' && row.uid)
        .map((row: any) => ({ value: String(row.uid), label: String(row.name || row.uid) }))
    })
    return out
  }, [elementDropdownFieldConfigs, elementDropdownQueries])

  const enrichElementFields = (fieldsRaw: any, parentFieldKey: string): PdvmElementField[] => {
    const fields = Array.isArray(fieldsRaw) ? fieldsRaw : []
    return fields.map((field: any) => {
      const fieldDef = asObject(field)
      const name = String(fieldDef.name || '').trim()
      if (!name) return fieldDef as PdvmElementField

      const lookupKey = name.toUpperCase()
      const controlData = asObject(elementFieldControlByName[lookupKey])
      const controlPayload = asObject(controlData.CONTROL)
      if (!Object.keys(controlPayload).length) return fieldDef as PdvmElementField

      const explicitType = String((fieldDef as any).type || '').trim().toLowerCase()
      const mappedType = explicitType === 'go_select_view' ? 'go_select_view' : mapPicTypeToElementFieldType(controlPayload.TYPE)
      const readOnly = toBoolean(controlPayload.READ_ONLY)
      const expertMode = globalExpertMode
      const tooltip = String(controlPayload.TOOLTIP ?? fieldDef.tooltip ?? fieldDef.help_text ?? '').trim()
      const fieldCompositeKey = `${parentFieldKey}::${name}`
      const resolvedOptions = elementDropdownOptionsByCompositeKey[fieldCompositeKey] || []
      const currentRecord = (picDraft ? picDraft : currentDaten || {}) as Record<string, any>

      const parentParts = String(parentFieldKey || '').split('.').filter(Boolean)
      const parentGruppe = parentParts[0] || ''
      const parentFeld = parentParts.slice(1).join('.')
      const parentCollection = parentGruppe && parentFeld ? getFieldValue(currentRecord, parentGruppe, parentFeld) : null
      const firstElementContext = getFirstCollectionRow(parentCollection)
      const tableToken = String(asObject(asObject(controlPayload.CONFIGS_ELEMENTS).dropdown).table || '').trim()
      const resolvedTable = resolveDropdownTableToken({
        tableToken,
        currentDaten: currentRecord,
        gruppe: parentGruppe,
        elementContext: firstElementContext,
      })
      const tableWarning =
        tableToken.startsWith('*') && !resolvedTable
          ? `Dropdown TABLE-Referenz '${tableToken}' konnte nicht aufgelöst werden.`
          : ''

      const controlDebug = buildFlatPicControl({
        controlData,
        fieldKey: `${parentFieldKey}.${name}`,
        value: null,
        valueTimeKey: 'ORIGINAL',
        sourcePath: String(controlPayload.SOURCE_PATH ?? controlPayload.source_path ?? `root.${parentFieldKey}`).trim() || `root.${parentFieldKey}`,
      })

      const controlDebugWithDiag = {
        ...controlDebug,
        EXPERT_MODE: globalExpertMode,
        DROPDOWN_TABLE_TOKEN: tableToken || undefined,
        DROPDOWN_TABLE_RESOLVED: resolvedTable || undefined,
        DROPDOWN_TABLE_WARNING: tableWarning || undefined,
      }

      return {
        ...fieldDef,
        type: mappedType,
        label: String(controlPayload.LABEL ?? fieldDef.label ?? name).trim() || name,
        required: toBoolean(fieldDef.required ?? false),
        placeholder: String(fieldDef.placeholder ?? '').trim() || undefined,
        tooltip: tooltip || undefined,
        help_text: tooltip || undefined,
        SAVE_PATH: String(fieldDef.SAVE_PATH || name).trim(),
        options: resolvedOptions.length ? resolvedOptions : (Array.isArray(fieldDef.options) ? fieldDef.options : undefined),
        control_debug: controlDebugWithDiag,
        EXPERT_MODE: expertMode,
        ...(readOnly ? { READ_ONLY: true } : {}),
      } as any
    }) as PdvmElementField[]
  }

  // Menu editor tabs come from frame definition (sys_framedaten)
  const menuEditTabs = useMemo(() => {
    const frameRootLocal = frameRoot

    const tabsRaw = frameRootLocal.TABS ?? frameRootLocal.tabs
    const tabs = Number(tabsRaw || 0)

    const pickTabBlock = (tabIndex: number): Record<string, any> | null => {
      const rx = new RegExp(`^tab[_-]?0*${tabIndex}$`, 'i')
      for (const key of Object.keys(frameRootLocal)) {
        if (!rx.test(String(key))) continue
        const v = (frameRootLocal as any)[key]
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
  }, [frameRoot])

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

  const workflowDraftRuntimeQuery = useQuery<DialogUiStateResponse>({
    queryKey: ['dialog', 'ui-state', 'workflow-draft-runtime', dialogGuid, dialogTable],
    queryFn: () => dialogsAPI.getUiState(dialogGuid!, { dialog_table: dialogTable }),
    enabled: !!dialogGuid && defQuery.isSuccess && isWorkflowDraftBuilderDialog,
  })

  const workflowOpenDraftsQuery = useQuery({
    queryKey: ['workflow-drafts', 'open', dialogGuid, workflowDraftTableOptions.draft_table, workflowDraftTableOptions.draft_item_table],
    queryFn: () => workflowDraftsAPI.listOpen(workflowDraftTableOptions),
    enabled: !!dialogGuid && isWorkflowDraftBuilderDialog,
  })

  useEffect(() => {
    if (!isWorkflowDraftBuilderDialog) return
    const runtime = (workflowDraftRuntimeQuery.data?.ui_state as any)?.workflow_draft_runtime
    const persistedGuid = String(runtime?.draft_guid || '').trim()
    if (persistedGuid && isUuidString(persistedGuid)) {
      setWorkflowDraftGuid(persistedGuid)
      return
    }

    if (workflowDraftGuid) return
    const firstOpenGuid = String(workflowOpenDraftsQuery.data?.drafts?.[0]?.draft_guid || '').trim()
    if (firstOpenGuid && isUuidString(firstOpenGuid)) {
      setWorkflowDraftGuid(firstOpenGuid)
    }
  }, [
    isWorkflowDraftBuilderDialog,
    workflowDraftRuntimeQuery.data,
    workflowOpenDraftsQuery.data,
    workflowDraftGuid,
  ])

  const persistWorkflowDraftGuid = (nextGuid: string | null) => {
    setWorkflowDraftGuid(nextGuid)
    if (!dialogGuid) return
    dialogsAPI
      .putUiState(
        dialogGuid,
        {
          ui_state: {
            workflow_draft_runtime: {
              draft_guid: nextGuid,
            },
          },
        },
        { dialog_table: dialogTable }
      )
      .catch(() => {
        // Best-effort persistence only.
      })
  }

  const ensureWorkflowDraft = async (): Promise<string> => {
    if (workflowDraftGuid && isUuidString(workflowDraftGuid)) return workflowDraftGuid

    const source = (picDraft ? picDraft : currentDaten || {}) as Record<string, any>
    const setup = collectWorkflowSetupPayload(source)
    const title = setup.WORKFLOW_NAME || `WORKFLOW_DRAFT_${new Date().toISOString().slice(0, 19)}`

    const created = await workflowDraftsAPI.create({
      workflow_type: setup.WORKFLOW_TYPE || 'work',
      title,
      initial_setup: setup,
      draft_table: workflowDraftTableOptions.draft_table || null,
      draft_item_table: workflowDraftTableOptions.draft_item_table || null,
    })

    persistWorkflowDraftGuid(created.draft_guid)
    setWorkflowDraftStatus(`Draft erstellt: ${created.draft_guid.slice(0, 8)}`)
    return created.draft_guid
  }

  const saveWorkflowSetup = async (): Promise<string> => {
    const draftGuid = await ensureWorkflowDraft()
    const source = (picDraft ? picDraft : currentDaten || {}) as Record<string, any>
    const setup = collectWorkflowSetupPayload(source)

    await workflowDraftsAPI.saveItem(draftGuid, {
      item_type: 'setup',
      item_key: 'setup',
      payload: setup,
    }, workflowDraftTableOptions)

    setWorkflowDraftStatus(`Setup gespeichert (${draftGuid.slice(0, 8)})`)
    return draftGuid
  }

  const loadWorkflowSetup = async () => {
    if (!workflowDraftGuid || !isUuidString(workflowDraftGuid)) {
      setWorkflowDraftError('Kein Workflow-Draft vorhanden.')
      return
    }

    const loaded = await workflowDraftsAPI.load(workflowDraftGuid, workflowDraftTableOptions)
    const setupItem = (loaded.items || []).find((i) => String(i.item_type || '').toLowerCase() === 'setup')
    const payload = asObject(setupItem?.payload)

    if (!Object.keys(payload).length) {
      setWorkflowDraftStatus('Kein Setup-Item im Draft gefunden.')
      return
    }

    setPicDraft((prev) => {
      let next = asObject(prev || currentDaten || {})
      next = setFieldValue(next, 'FIELDS', 'WORKFLOW_NAME', String(payload.WORKFLOW_NAME || ''))
      next = setFieldValue(next, 'FIELDS', 'TARGET_TABLE', String(payload.TARGET_TABLE || 'sys_dialogdaten'))
      next = setFieldValue(next, 'FIELDS', 'DESCRIPTION', String(payload.DESCRIPTION || ''))
      return next
    })
    setPicDirty(true)
    setWorkflowDraftStatus(`Setup geladen (${workflowDraftGuid.slice(0, 8)})`)
  }

  const validateWorkflowDraft = async () => {
    const draftGuid = await saveWorkflowSetup()
    const result = await workflowDraftsAPI.validate(draftGuid, workflowDraftTableOptions)
    setWorkflowDraftValidation(result)
    if (result.valid) {
      setWorkflowDraftStatus(`Validierung OK (${draftGuid.slice(0, 8)})`)
    } else {
      setWorkflowDraftStatus(`Validierung mit ${result.error_count} Fehler(n)`)
    }
  }

  const runWorkflowDraftAction = async (def: any) => {
    const token = buildActionToken(def)
    if (!token) return

    setWorkflowDraftError(null)
    setWorkflowDraftStatus(null)

    setWorkflowDraftBusy(true)
    try {
      if (token.includes('validate')) {
        await validateWorkflowDraft()
        return
      }
      if (token.includes('load')) {
        await loadWorkflowSetup()
        return
      }
      if (token.includes('save') || token.includes('build')) {
        await saveWorkflowSetup()
        return
      }
      setWorkflowDraftStatus('Aktion ist fuer den aktuellen Ausbau noch nicht verdrahtet.')
    } catch (e: any) {
      setWorkflowDraftError(String(e?.response?.data?.detail || e?.message || 'Workflow-Draft-Aktion fehlgeschlagen'))
    } finally {
      setWorkflowDraftBusy(false)
    }
  }

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
      const draft = await dialogsAPI.startDraft(
        dialogGuid,
        {
          name,
          template_uid: '66666666-6666-6666-6666-666666666666',
        },
        String(effectiveDialogTable || dialogTable || '').trim()
          ? { dialog_table: String(effectiveDialogTable || dialogTable || '').trim() }
          : undefined
      )
      const created = await dialogsAPI.commitDraft(
        dialogGuid,
        draft.draft_id,
        { daten: draft.daten },
        String(effectiveDialogTable || dialogTable || '').trim()
          ? { dialog_table: String(effectiveDialogTable || dialogTable || '').trim() }
          : undefined
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
        message={
          createContextModalFields.length > 0
            ? 'Bitte Name und Create-Parameter eingeben. Der Draft wird aus Template 6666... vorbereitet.'
            : isSysMenuTable
            ? 'Bitte Name und Menü-Typ auswählen. Es wird zuerst ein Draft erzeugt.'
            : 'Bitte Name eingeben (Template: 6666... → Draft → Edit → Speichern).'
        }
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
        )
          .concat(createContextModalFields as any[])
          .concat(
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
        initialValues={{
          ...(isSysMenuTable ? { menu_type: 'standard' } : {}),
          ...createContextInitialValues,
        }}
        confirmLabel="Erstellen"
        cancelLabel="Abbrechen"
        busy={createFrameQuery.isLoading || createMutation.isPending || updateMutation.isPending || commitDraftMutation.isPending}
        error={
          createModalError ||
          (createFrameGuid && !isUuidString(createFrameGuid)
            ? 'CREATE_FRAME_GUID ist keine gültige GUID.'
            : (createFrameQuery.error as any)?.response?.data?.detail ||
              (createFrameQuery.error as any)?.message ||
              (createTableOptionsQuery.error as any)?.response?.data?.detail ||
              (createTableOptionsQuery.error as any)?.message ||
              null)
        }
        onCancel={() => {
          if (createFrameQuery.isLoading || createMutation.isPending || updateMutation.isPending || commitDraftMutation.isPending) return
          setCreateModalOpen(false)
          setCreateModalError(null)
        }}
        onConfirm={async (values) => {
          const name = String(values?.name || '').trim()
          if (!name) return

          const menuType = String(values?.menu_type || '').trim().toLowerCase()
          const isTemplate = menuType === 'template'

          const createContext: Record<string, any> = {}
          createContextFieldDefs.forEach((def) => {
            const raw = values?.[def.modalField.name]
            const text = String(raw ?? '').trim()
            if (!text) return

            if (def.valueType === 'number') {
              const n = Number(text)
              if (Number.isFinite(n)) {
                createContext[def.contextKey] = n
                return
              }
            }
            createContext[def.contextKey] = text
          })

          try {
            setAutoLastCallError(null)
            setCreateModalError(null)
            await createMutation.mutateAsync({
              name,
              is_template: isSysMenuTable ? isTemplate : undefined,
              create_context: Object.keys(createContext).length > 0 ? createContext : undefined,
            })
            setCreateModalOpen(false)
          } catch (e: any) {
            const detail = e?.response?.data?.detail
            let message = 'Neuer Datensatz konnte nicht angelegt werden'
            if (typeof detail === 'string' && detail.trim()) {
              message = detail
            } else if (detail && typeof detail === 'object') {
              const detailMessage = String((detail as any).message || '').trim()
              const missing = Array.isArray((detail as any).missing_fields)
                ? (detail as any).missing_fields.join(', ')
                : ''
              if (detailMessage && missing) {
                message = `${detailMessage}: ${missing}`
              } else if (detailMessage) {
                message = detailMessage
              } else {
                message = JSON.stringify(detail)
              }
            } else if (!e?.response && e?.request) {
              message = 'Netzwerkfehler: Backend nicht erreichbar oder Request abgebrochen'
            } else if (String(e?.message || '').trim()) {
              message = String(e.message)
            }
            setCreateModalError(message)
          }
        }}
      />

      <div className="pdvm-dialog__header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <h2 style={{ margin: 0 }}>{title}</h2>
            {selectedRecordSubtitle ? (
              <div style={{ fontSize: 14, fontWeight: 700, fontStyle: 'italic', opacity: 0.9 }}>{selectedRecordSubtitle}</div>
            ) : null}
          </div>
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
                onClick={async () => {
                  const next = Math.min(tabs, activeTab + 1)

                  if (isWorkflowDraftBuilderDialog) {
                    try {
                      setWorkflowDraftError(null)
                      const draftGuid = await ensureWorkflowDraft()
                      const nextTab = moduleTabs.find((m) => Number(m?.index || 0) === Number(next)) || null
                      await workflowDraftsAPI.ensureStep(draftGuid, {
                        step: next,
                        table: String(nextTab?.table || '').trim() || undefined,
                        module: String(nextTab?.module || '').trim().toLowerCase() || undefined,
                        head: String(nextTab?.head || '').trim() || undefined,
                        draft_table: workflowDraftTableOptions.draft_table || null,
                        draft_item_table: workflowDraftTableOptions.draft_item_table || null,
                      })
                    } catch (e: any) {
                      setWorkflowDraftError(String(e?.response?.data?.detail || e?.message || 'Workflow-Step konnte nicht vorbereitet werden'))
                      return
                    }
                  }

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
            <div>
              last_call_scope: <span style={{ fontFamily: 'monospace' }}>{String((defQuery.data.meta as any)?.last_call_scope || 'unknown')}</span>
            </div>
            <div>
              last_call_scope_client: <span style={{ fontFamily: 'monospace' }}>{debugLastCallScopeClient || '-'}</span>
            </div>
            <div>
              last_call_runtime_state: <span style={{ fontFamily: 'monospace' }}>{lastCallRuntimeState}</span>
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

          {isEditLikeModule || (!moduleTabs.length && activeTab === editTabIndex) ? (
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
                                frameDaten={frameDaten}
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
                                frameDaten={frameDaten}
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
                                frameDaten={frameDaten}
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

                    <div
                      style={{
                        display: 'grid',
                        gap: 12,
                        gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
                        alignItems: 'start',
                      }}
                    >
                      {uiPicDefs
                        .filter((d) => Number(d.tab || 1) === picActiveTab)
                        .map((d) => {
                          const gruppe = String(d.gruppe || 'ROOT').trim()
                          const feld = String(d.feld || '').trim()
                          if (!feld) return null

                          const current = picDraft ? picDraft : currentDaten || {}
                          const rawValue = getControlValueForRender(current as Record<string, any>, gruppe, feld, d.type)
                          const type = normalizePicType(d.type)
                          const fieldKey = String(d.key || `${gruppe}.${feld}`)
                          const validationKey = `${gruppe}.${feld}`
                          const validationMessage = draftErrorByField[validationKey]
                          const options = dropdownOptionsByFieldKey[fieldKey] || []
                          const resolvedControl = resolvedControlByGroupField[`${gruppe.toUpperCase()}::${feld.toUpperCase()}`] || null
                          const elementFrameConfig = elementFrameConfigByFieldKey[fieldKey]
                          const isFrameFieldsList =
                            String(effectiveDialogTable || '').trim().toLowerCase() === 'sys_framedaten' &&
                            (type === 'element_list' || type === 'group_list') &&
                            gruppe.toUpperCase() === 'FIELDS' &&
                            feld.toUpperCase() === 'FIELDS'
                          const fallbackElementTemplate = isFrameFieldsList
                            ? {
                                FIELD: '',
                                TAB: 1,
                                DISPLAY_ORDER: 10,
                                TABLE: 'sys_control_dict',
                                GRUPPE: '',
                              }
                            : null
                          const fallbackElementFields = isFrameFieldsList
                            ? [
                                {
                                  name: 'FIELD',
                                  label: 'Feld (sys_control_dict)',
                                  type: 'go_select_view',
                                  lookupTable: 'sys_control_dict',
                                  SAVE_PATH: 'FIELD',
                                  required: true,
                                  display_order: 10,
                                },
                                {
                                  name: 'TAB',
                                  label: 'Tab',
                                  type: 'number',
                                  SAVE_PATH: 'TAB',
                                  required: true,
                                  display_order: 20,
                                },
                                {
                                  name: 'DISPLAY_ORDER',
                                  label: 'Display Order',
                                  type: 'number',
                                  SAVE_PATH: 'DISPLAY_ORDER',
                                  required: true,
                                  display_order: 30,
                                },
                              ]
                            : null
                          const elementConfig = resolveElementEditorConfig(d.configs)
                          const elementTemplate = elementFrameConfig?.template || elementConfig.template || fallbackElementTemplate || null
                          const elementFieldsRaw = elementFrameConfig?.fields || elementConfig.fields || fallbackElementFields || null
                          const frameFieldsEditorRaw = isFrameFieldsList
                            ? buildFrameFieldsElementEditorFields(elementFieldsRaw, controlTemplatePayload)
                            : elementFieldsRaw
                          const elementFields = enrichElementFields(frameFieldsEditorRaw, fieldKey)

                          const hydrateFrameFieldElementDraft = isFrameFieldsList
                            ? (draft: Record<string, any>, draftUid?: string | null) => {
                                const row = asObject(draft)
                                const uidToken = String(draftUid || '').trim()
                                const fieldRaw = String(readCfgValue(row, ['FIELD', 'FELD']) || '').trim()
                                const fieldUid =
                                  resolveControlUidToken(uidToken, controlUidByToken) ||
                                  resolveControlUidToken(fieldRaw, controlUidByToken)
                                if (!isUuidString(fieldUid)) return row
                                const base = asObject(frameFieldsControlPayloadByUid[fieldUid])
                                if (!Object.keys(base).length) {
                                  return {
                                    ...row,
                                    FIELD: fieldUid,
                                  }
                                }
                                return {
                                  ...base,
                                  ...row,
                                  FIELD: fieldUid,
                                }
                              }
                            : undefined

                          const normalizeFrameFieldElementDraft = isFrameFieldsList
                            ? (draft: Record<string, any>, draftUid?: string | null) => {
                                const row = asObject(draft)
                                const uidToken = String(draftUid || '').trim()
                                const fieldRaw = String(readCfgValue(row, ['FIELD', 'FELD']) || '').trim()
                                const uidCandidate = resolveControlUidToken(uidToken, controlUidByToken)
                                const fieldCandidate = resolveControlUidToken(fieldRaw, controlUidByToken)
                                const fieldUid = uidCandidate || fieldCandidate
                                if ((uidToken || fieldRaw) && !isUuidString(fieldUid)) {
                                  const sourceToken = uidToken || fieldRaw
                                  throw new Error(`FIELD/Element-UID '${sourceToken}' konnte nicht auf eine Control-UID aufgeloest werden.`)
                                }
                                const base = isUuidString(fieldUid) ? asObject(frameFieldsControlPayloadByUid[fieldUid]) : {}

                                const out: Record<string, any> = {}
                                if (fieldUid) out.__ELEMENT_UID = fieldUid

                                const tabRaw = row.TAB
                                if (tabRaw !== undefined && tabRaw !== null && String(tabRaw).trim() !== '') {
                                  out.TAB = Number(tabRaw)
                                }

                                const orderRaw = row.DISPLAY_ORDER
                                if (orderRaw !== undefined && orderRaw !== null && String(orderRaw).trim() !== '') {
                                  out.DISPLAY_ORDER = Number(orderRaw)
                                }

                                Object.entries(row).forEach(([k, v]) => {
                                  const key = String(k || '').trim().toUpperCase()
                                  if (!key) return
                                  if (key === 'FIELD' || key === 'FELD' || key === 'TAB' || key === 'DISPLAY_ORDER') return
                                  if (v === undefined || v === null) return
                                  if (typeof v === 'string' && !v.trim()) return

                                  const baseVal = (base as any)[key]
                                  if (valuesEqual(v, baseVal)) return
                                  out[key] = v
                                })

                                return out
                              }
                            : undefined

                          const onChange = (value: any) => {
                            setPicDraft((prev) => {
                              const base = prev || (currentDaten || {})
                              return setControlValueFromEdit(base as Record<string, any>, gruppe, feld, d.type, value)
                            })
                            setPicDirty(true)
                          }

                          if (type === 'action') {
                                    const blockedApplyAction = blockApplyForRole && isApplyLikeActionControl(d)
                                    const actionDisabled = !!d.read_only || blockedApplyAction || (isWorkflowDraftBuilderDialog && workflowDraftBusy)
                                    const actionTitle = blockedApplyAction
                                      ? 'Apply ist fuer Ihre Rolle nicht freigegeben (nur Admin)'
                                      : (d.tooltip || undefined)
                            return (
                                      <div key={fieldKey} className="pdvm-pic" title={actionTitle}>
                                <div className="pdvm-pic__labelRow">
                                  <label className="pdvm-pic__label">{d.label || d.name || feld}</label>
                                </div>
                                <div className="pdvm-pic__control">
                                          <button
                                            type="button"
                                            className="pdvm-dialog__toolBtn"
                                            disabled={actionDisabled}
                                            onClick={() => {
                                              if (isWorkflowDraftBuilderDialog) {
                                                runWorkflowDraftAction(d)
                                              }
                                            }}
                                          >
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
                              lookupTable={type === 'go_select_view' ? resolveGoSelectViewTable(d.configs, (d as any).CONTROL) : undefined}
                              helpText={validationMessage ? `${validationMessage}${d.tooltip ? ` · ${d.tooltip}` : ''}` : (d.tooltip || '')}
                              elementTemplate={elementTemplate}
                              elementFields={elementFields}
                              elementLabelKeys={isFrameFieldsList ? ['LABEL', 'NAME', 'FIELD'] : undefined}
                              elementUidLabels={elementUidLabels}
                              elementDraftHydrator={hydrateFrameFieldElementDraft}
                              elementDraftNormalizer={normalizeFrameFieldElementDraft}
                              controlDebug={buildControlDebugForField(d, fieldKey, rawValue, resolvedControl)}
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
                          {isWorkflowDraftBuilderDialog ? (
                            <div style={{ marginBottom: 10, display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
                              <button
                                type="button"
                                className="pdvm-dialog__toolBtn"
                                onClick={async () => {
                                  setWorkflowDraftError(null)
                                  setWorkflowDraftBusy(true)
                                  try {
                                    await loadWorkflowSetup()
                                  } catch (e: any) {
                                    setWorkflowDraftError(String(e?.response?.data?.detail || e?.message || 'Setup konnte nicht geladen werden'))
                                  } finally {
                                    setWorkflowDraftBusy(false)
                                  }
                                }}
                                disabled={workflowDraftBusy}
                              >
                                Setup laden
                              </button>
                              <button
                                type="button"
                                className="pdvm-dialog__toolBtn"
                                onClick={async () => {
                                  setWorkflowDraftError(null)
                                  setWorkflowDraftBusy(true)
                                  try {
                                    await saveWorkflowSetup()
                                  } catch (e: any) {
                                    setWorkflowDraftError(String(e?.response?.data?.detail || e?.message || 'Setup konnte nicht gespeichert werden'))
                                  } finally {
                                    setWorkflowDraftBusy(false)
                                  }
                                }}
                                disabled={workflowDraftBusy}
                              >
                                Setup speichern
                              </button>
                              <button
                                type="button"
                                className="pdvm-dialog__toolBtn"
                                onClick={async () => {
                                  setWorkflowDraftError(null)
                                  setWorkflowDraftBusy(true)
                                  try {
                                    await validateWorkflowDraft()
                                  } catch (e: any) {
                                    setWorkflowDraftError(String(e?.response?.data?.detail || e?.message || 'Validierung fehlgeschlagen'))
                                  } finally {
                                    setWorkflowDraftBusy(false)
                                  }
                                }}
                                disabled={workflowDraftBusy}
                              >
                                Validieren
                              </button>
                              <div style={{ fontSize: 12, opacity: 0.8, marginLeft: 'auto' }}>
                                Draft: <span style={{ fontFamily: 'monospace' }}>{workflowDraftGuid || 'neu'}</span>
                              </div>
                            </div>
                          ) : null}
                          {isWorkflowDraftBuilderDialog && (workflowDraftStatus || workflowDraftError || workflowDraftValidation) ? (
                            <div style={{ marginBottom: 8, fontSize: 12, lineHeight: 1.35 }}>
                              {workflowDraftStatus ? <div style={{ color: '#195e36' }}>{workflowDraftStatus}</div> : null}
                              {workflowDraftError ? <div style={{ color: 'crimson' }}>{workflowDraftError}</div> : null}
                              {workflowDraftValidation && !workflowDraftValidation.valid ? (
                                <div style={{ color: '#9a4f00' }}>
                                  Fehler: {workflowDraftValidation.errors.map((e) => e.message).join(' | ')}
                                </div>
                              ) : null}
                            </div>
                          ) : null}
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

                            <div
                              style={{
                                display: 'grid',
                                gap: 12,
                                gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
                                alignItems: 'start',
                              }}
                            >
                              {uiPicDefs
                                .filter((d) => Number(d.tab || 1) === picActiveTab)
                                .map((d) => {
                                  const gruppe = String(d.gruppe || 'ROOT').trim()
                                  const feld = String(d.feld || '').trim()
                                  if (!feld) return null

                                  const current = picDraft ? picDraft : currentDaten || {}
                                  const rawValue = getControlValueForRender(current as Record<string, any>, gruppe, feld, d.type)
                                  const type = normalizePicType(d.type)
                                  const fieldKey = String(d.key || `${gruppe}.${feld}`)
                                  const validationKey = `${gruppe}.${feld}`
                                  const validationMessage = draftErrorByField[validationKey]
                                  const options = dropdownOptionsByFieldKey[fieldKey] || []
                                  const resolvedControl = resolvedControlByGroupField[`${gruppe.toUpperCase()}::${feld.toUpperCase()}`] || null
                                  const elementFrameConfig = elementFrameConfigByFieldKey[fieldKey]
                                  const isFrameFieldsList =
                                    String(effectiveDialogTable || '').trim().toLowerCase() === 'sys_framedaten' &&
                                    (type === 'element_list' || type === 'group_list') &&
                                    gruppe.toUpperCase() === 'FIELDS' &&
                                    feld.toUpperCase() === 'FIELDS'
                                  const fallbackElementTemplate = isFrameFieldsList
                                    ? {
                                        FIELD: '',
                                        TAB: 1,
                                        DISPLAY_ORDER: 10,
                                        TABLE: 'sys_control_dict',
                                        GRUPPE: '',
                                      }
                                    : null
                                  const fallbackElementFields = isFrameFieldsList
                                    ? [
                                        {
                                          name: 'FIELD',
                                          label: 'Feld (sys_control_dict)',
                                          type: 'go_select_view',
                                          lookupTable: 'sys_control_dict',
                                          SAVE_PATH: 'FIELD',
                                          required: true,
                                          display_order: 10,
                                        },
                                        {
                                          name: 'TAB',
                                          label: 'Tab',
                                          type: 'number',
                                          SAVE_PATH: 'TAB',
                                          required: true,
                                          display_order: 20,
                                        },
                                        {
                                          name: 'DISPLAY_ORDER',
                                          label: 'Display Order',
                                          type: 'number',
                                          SAVE_PATH: 'DISPLAY_ORDER',
                                          required: true,
                                          display_order: 30,
                                        },
                                      ]
                                    : null
                                  const elementConfig = resolveElementEditorConfig(d.configs)
                                  const elementTemplate = elementFrameConfig?.template || elementConfig.template || fallbackElementTemplate || null
                                  const elementFieldsRaw = elementFrameConfig?.fields || elementConfig.fields || fallbackElementFields || null
                                  const frameFieldsEditorRaw = isFrameFieldsList
                                    ? buildFrameFieldsElementEditorFields(elementFieldsRaw, controlTemplatePayload)
                                    : elementFieldsRaw
                                  const elementFields = enrichElementFields(frameFieldsEditorRaw, fieldKey)

                                  const hydrateFrameFieldElementDraft = isFrameFieldsList
                                    ? (draft: Record<string, any>, draftUid?: string | null) => {
                                        const row = asObject(draft)
                                        const uidToken = String(draftUid || '').trim()
                                        const fieldRaw = String(readCfgValue(row, ['FIELD', 'FELD']) || '').trim()
                                        const fieldUid =
                                          resolveControlUidToken(uidToken, controlUidByToken) ||
                                          resolveControlUidToken(fieldRaw, controlUidByToken)
                                        if (!isUuidString(fieldUid)) return row
                                        const base = asObject(frameFieldsControlPayloadByUid[fieldUid])
                                        if (!Object.keys(base).length) {
                                          return {
                                            ...row,
                                            FIELD: fieldUid,
                                          }
                                        }
                                        return {
                                          ...base,
                                          ...row,
                                          FIELD: fieldUid,
                                        }
                                      }
                                    : undefined

                                  const normalizeFrameFieldElementDraft = isFrameFieldsList
                                    ? (draft: Record<string, any>, draftUid?: string | null) => {
                                        const row = asObject(draft)
                                        const uidToken = String(draftUid || '').trim()
                                        const fieldRaw = String(readCfgValue(row, ['FIELD', 'FELD']) || '').trim()
                                        const uidCandidate = resolveControlUidToken(uidToken, controlUidByToken)
                                        const fieldCandidate = resolveControlUidToken(fieldRaw, controlUidByToken)
                                        const fieldUid = uidCandidate || fieldCandidate
                                        if ((uidToken || fieldRaw) && !isUuidString(fieldUid)) {
                                          const sourceToken = uidToken || fieldRaw
                                          throw new Error(`FIELD/Element-UID '${sourceToken}' konnte nicht auf eine Control-UID aufgeloest werden.`)
                                        }
                                        const base = isUuidString(fieldUid) ? asObject(frameFieldsControlPayloadByUid[fieldUid]) : {}

                                        const out: Record<string, any> = {}
                                        if (fieldUid) out.__ELEMENT_UID = fieldUid

                                        const tabRaw = row.TAB
                                        if (tabRaw !== undefined && tabRaw !== null && String(tabRaw).trim() !== '') {
                                          out.TAB = Number(tabRaw)
                                        }

                                        const orderRaw = row.DISPLAY_ORDER
                                        if (orderRaw !== undefined && orderRaw !== null && String(orderRaw).trim() !== '') {
                                          out.DISPLAY_ORDER = Number(orderRaw)
                                        }

                                        Object.entries(row).forEach(([k, v]) => {
                                          const key = String(k || '').trim().toUpperCase()
                                          if (!key) return
                                          if (key === 'FIELD' || key === 'FELD' || key === 'TAB' || key === 'DISPLAY_ORDER') return
                                          if (v === undefined || v === null) return
                                          if (typeof v === 'string' && !v.trim()) return

                                          const baseVal = (base as any)[key]
                                          if (valuesEqual(v, baseVal)) return
                                          out[key] = v
                                        })

                                        return out
                                      }
                                    : undefined

                                  const onChange = (value: any) => {
                                    setPicDraft((prev) => {
                                      const base = prev || (currentDaten || {})
                                      return setControlValueFromEdit(base as Record<string, any>, gruppe, feld, d.type, value)
                                    })
                                    setPicDirty(true)
                                  }

                                  if (type === 'action') {
                                    const blockedApplyAction = blockApplyForRole && isApplyLikeActionControl(d)
                                    const actionDisabled = !!d.read_only || blockedApplyAction || (isWorkflowDraftBuilderDialog && workflowDraftBusy)
                                    const actionTitle = blockedApplyAction
                                      ? 'Apply ist fuer Ihre Rolle nicht freigegeben (nur Admin)'
                                      : (d.tooltip || undefined)
                                    return (
                                      <div key={fieldKey} className="pdvm-pic" title={actionTitle}>
                                        <div className="pdvm-pic__labelRow">
                                          <label className="pdvm-pic__label">{d.label || d.name || feld}</label>
                                        </div>
                                        <div className="pdvm-pic__control">
                                          <button
                                            type="button"
                                            className="pdvm-dialog__toolBtn"
                                            disabled={actionDisabled}
                                            onClick={() => {
                                              if (isWorkflowDraftBuilderDialog) {
                                                runWorkflowDraftAction(d)
                                              }
                                            }}
                                          >
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
                                      lookupTable={type === 'go_select_view' ? resolveGoSelectViewTable(d.configs, (d as any).CONTROL) : undefined}
                                      helpText={validationMessage ? `${validationMessage}${d.tooltip ? ` · ${d.tooltip}` : ''}` : (d.tooltip || '')}
                                      elementTemplate={elementTemplate}
                                      elementFields={elementFields}
                                      elementLabelKeys={isFrameFieldsList ? ['LABEL', 'NAME', 'FIELD'] : undefined}
                                      elementUidLabels={elementUidLabels}
                                      elementDraftHydrator={hydrateFrameFieldElementDraft}
                                      elementDraftNormalizer={normalizeFrameFieldElementDraft}
                                      controlDebug={buildControlDebugForField(d, fieldKey, rawValue, resolvedControl)}
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
                          canApplyWrite={!blockApplyForRole}
                          applyDeniedMessage="Apply ist fuer Ihre Rolle nicht freigegeben (nur Admin)."
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
          ) : null}
          </div>
        </div>
      </div>
    </div>
  )
}
