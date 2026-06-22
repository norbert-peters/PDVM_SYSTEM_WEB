export type ElementFieldControlResolution = {
  data: Record<string, any>
  source: 'inline' | 'uid' | 'uid_inline_override' | 'none'
  warning?: string
}

export type ElementFieldRuntimeContract = {
  fieldDef: Record<string, any>
  name: string
  hasName: boolean
  resolvedControl: ElementFieldControlResolution
  controlData: Record<string, any>
  controlPayload: Record<string, any>
  hasControl: boolean
  unresolvedMsg?: string
  runtimeWarning?: string
  mappedType: 'string' | 'text' | 'textarea' | 'number' | 'dropdown' | 'multi_dropdown' | 'true_false' | 'go_select_view'
  goSelectLookupTable?: string
  readOnly: boolean
  tooltip: string
  fieldCompositeKey: string
  sourcePath: string
  controlConfigs: Record<string, any>
  controlConfigsElements: Record<string, any>
}

const NON_BLOCKING_RESOLUTION_WARNINGS = new Set([
  'CONTROL_UID fehlt. Inline CONTROL als Uebergang verwendet.',
])

type ResolveElementFieldRuntimeContractParams = {
  fieldRaw: any
  parentFieldKey: string
  resolveElementFieldControl: (fieldDefRaw: any) => ElementFieldControlResolution
  mapPicTypeToElementFieldType: (value: any) => 'string' | 'text' | 'textarea' | 'number' | 'dropdown' | 'multi_dropdown' | 'true_false' | 'go_select_view'
  resolveGoSelectViewTable: (configs: any, controlData?: any) => string
}

function asObject(value: any): Record<string, any> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, any>) : {}
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

function isUuidString(value: any): boolean {
  const s = String(value || '').trim()
  if (!s) return false
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(s)
}

export function resolveElementFieldRuntimeContract(
  params: ResolveElementFieldRuntimeContractParams,
): ElementFieldRuntimeContract {
  const {
    fieldRaw,
    parentFieldKey,
    resolveElementFieldControl,
    mapPicTypeToElementFieldType,
    resolveGoSelectViewTable,
  } = params

  const fieldDef = asObject(fieldRaw)
  const name = String(fieldDef.name || '').trim()
  const hasName = !!name

  const resolvedControl = resolveElementFieldControl(fieldDef)
  const controlData = asObject(resolvedControl.data)
  const controlPayload = asObject(controlData.CONTROL)
  const hasControl = Object.keys(controlPayload).length > 0

  const controlUid = String((fieldDef as any).CONTROL_UID || '').trim()
  const unresolvedMsg = hasControl
    ? undefined
    : (resolvedControl.warning || (isUuidString(controlUid)
        ? `Control-Auflösung fehlgeschlagen für Element-Feld '${name}' (CONTROL_UID='${controlUid}' konnte nicht geladen werden).`
        : `Control-Auflösung fehlt für Element-Feld '${name}' (im Frame ist weder CONTROL noch CONTROL_UID gesetzt).`))

  const explicitType = String((fieldDef as any).type || '').trim().toLowerCase()
  const mappedType = explicitType === 'go_select_view'
    ? 'go_select_view'
    : mapPicTypeToElementFieldType(controlPayload.TYPE)

  const goSelectLookupTable =
    mappedType === 'go_select_view'
      ? resolveGoSelectViewTable(asObject(controlPayload.CONFIGS), controlPayload)
      : ''

  const runtimeWarningParts = [
    String(resolvedControl.warning || '').trim(),
    mappedType === 'go_select_view' && !String(goSelectLookupTable || '').trim()
      ? 'go_select_view nicht konfiguriert: resolved_configs.go_select_view.table fehlt.'
      : '',
  ]
    .map((s) => String(s || '').trim())
    .filter((s) => !!s && !NON_BLOCKING_RESOLUTION_WARNINGS.has(s))
  const runtimeWarning = runtimeWarningParts.join(' · ') || undefined

  const readOnly = toBoolean(controlPayload.READ_ONLY)
  const tooltip = String(controlPayload.TOOLTIP ?? fieldDef.tooltip ?? fieldDef.help_text ?? '').trim()
  const fieldCompositeKey = `${parentFieldKey}::${name}`
  const sourcePath = String(controlPayload.SOURCE_PATH ?? controlPayload.source_path ?? `root.${parentFieldKey}`).trim() || `root.${parentFieldKey}`
  const controlConfigs = asObject((controlPayload as any).CONFIGS ?? (controlPayload as any).configs)
  const controlConfigsElements = asObject((controlPayload as any).CONFIGS_ELEMENTS ?? (controlPayload as any).configs_elements)

  return {
    fieldDef,
    name,
    hasName,
    resolvedControl,
    controlData,
    controlPayload,
    hasControl,
    unresolvedMsg,
    runtimeWarning,
    mappedType,
    goSelectLookupTable: goSelectLookupTable || undefined,
    readOnly,
    tooltip,
    fieldCompositeKey,
    sourcePath,
    controlConfigs,
    controlConfigsElements,
  }
}