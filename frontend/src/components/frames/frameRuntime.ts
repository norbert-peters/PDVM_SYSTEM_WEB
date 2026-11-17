import type { FrameRuntimeField } from '../../api/client'

type DataObject = Record<string, any>

function isObject(value: unknown): value is DataObject {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function groupPath(gruppe: string): string[] {
  return String(gruppe || 'ROOT')
    .split('.')
    .map((p) => p.trim())
    .filter(Boolean)
}

/** Lesen: SOURCE_PATH + GRUPPE + FELD (Regel 1.10d). Vor der Mandantenwahl gilt nur SOURCE_PATH `root`. */
export function readFieldValue(data: DataObject, field: FrameRuntimeField): any {
  let cursor: any = data
  for (const part of [...groupPath(field.gruppe), field.feld]) {
    if (!isObject(cursor)) return undefined
    cursor = cursor[part]
  }
  return cursor
}

/** Schreiben: liefert eine neue Datenstruktur, die uebergebene bleibt unveraendert. */
export function writeFieldValue(data: DataObject, field: FrameRuntimeField, value: any): DataObject {
  const parts = [...groupPath(field.gruppe), field.feld]
  const out: DataObject = { ...data }
  let cursor: DataObject = out
  parts.forEach((part, idx) => {
    if (idx === parts.length - 1) {
      cursor[part] = value
      return
    }
    cursor[part] = isObject(cursor[part]) ? { ...cursor[part] } : {}
    cursor = cursor[part]
  })
  return out
}

/**
 * Unveraenderliches Feld (CONTROL.IMMUTABLE) im Modus `edit`: gesperrt, sobald es einen Wert hat.
 * Ein leeres Feld darf einmalig gesetzt werden (Set-Once, entspricht immutable_fields_service im Backend).
 * Mit `condition.after` (CONTROL.IMMUTABLE_AFTER, Pfad `GRUPPE.FELD`) gilt die Sperre erst, wenn dieses Feld im
 * gespeicherten Satz (`condition.data`) einen Wert hat.
 */
export function isImmutableLocked(
  immutable: boolean,
  mode: 'create' | 'edit',
  value: unknown,
  condition?: { after?: string | null; data?: DataObject | null }
): boolean {
  if (!immutable || mode !== 'edit') return false
  if (condition?.after && !hasValue(readPathValue(condition.data, condition.after), true)) return false
  return hasValue(value)
}

function hasValue(value: unknown, placeholderIsEmpty = false): boolean {
  if (value === null || value === undefined) return false
  if (typeof value === 'string') return value.trim() !== '' && !(placeholderIsEmpty && value.trim() === '-eingeben-')
  if (typeof value === 'object') return Object.keys(value as object).length > 0
  return true
}

function readPathValue(data: DataObject | null | undefined, path: string): unknown {
  let cursor: any = data
  for (const part of String(path).split('.').map((p) => p.trim()).filter(Boolean)) {
    if (!isObject(cursor)) return undefined
    cursor = cursor[part]
  }
  return cursor
}

export const IMMUTABLE_LOCK_HINT = 'Nach der Anlage unveränderlich'

/** Typen, die der Renderer ohne weitere Quellen (Lookup-Tabellen, Element-Frames) darstellen kann; `dropdown` mit vom Backend gelieferten Optionen. */
export const SIMPLE_FIELD_TYPES = new Set(['string', 'text', 'text_popup', 'number', 'true_false', 'password', 'password_input', 'dropdown'])

export function unsupportedTypeMessage(field: FrameRuntimeField): string | null {
  if (field.source_path.toLowerCase() !== 'root') {
    return `SOURCE_PATH '${field.source_path}' wird in diesem Kontext nicht unterstützt (nur root).`
  }
  if (!SIMPLE_FIELD_TYPES.has(field.type)) {
    return `Control-Typ '${field.type}' wird in diesem Kontext nicht unterstützt.`
  }
  return null
}
