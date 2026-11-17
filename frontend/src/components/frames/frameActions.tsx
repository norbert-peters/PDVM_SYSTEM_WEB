import { useCallback, useState, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { frameActionsAPI, type FrameActionResult, type FrameActionStateEntry } from '../../api/client'
import { uiText } from '../../i18n/uiTexts'
import { useAuth } from '../../contexts/AuthContext'
import { PdvmDialogModal, type PdvmDialogModalField } from '../common/PdvmDialogModal'

/**
 * Frame-Aktionen (Typen `action` und `info`, Regel 2.17, Spec PDVM_FRAME_ACTIONS_SPEC_V1.md).
 *
 * Das Control verweist nur auf eine Aktions-ID; Rechte, Bedingungen mit Serverdaten und Ausfuehrung liegen im Backend.
 * Hier: deklarative Bedingungen (kein Code), Textersetzung `{{pfad}}`, gebuendelter Zustandsabruf je Satz und der
 * Ausfuehrungsablauf (Bestaetigung/Parameter/Warnung bei ungespeicherten Aenderungen/Ergebnis).
 */

type DataObject = Record<string, any>
export type FrameActionMode = 'create' | 'edit'
export type FrameActionSeverity = 'info' | 'warning' | 'error'
export type FrameActionPlacement = 'field' | 'header'

export interface FrameActionFieldLike {
  key?: string
  label?: string
  name?: string
  tooltip?: string
  type?: string
  configs?: DataObject
}

export interface FrameActionCondition {
  path: string
  equals?: unknown
  not?: unknown
  in?: unknown[]
  empty?: boolean
  not_empty?: boolean
}

export interface FrameActionView {
  visible: boolean
  enabled: boolean
  disabledReason?: string
  text: string
  severity: FrameActionSeverity
  placement: FrameActionPlacement
}

function isObject(value: unknown): value is DataObject {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function readCfg(configs: DataObject | undefined, key: string): DataObject {
  if (!isObject(configs)) return {}
  const hit = Object.keys(configs).find((k) => k.toLowerCase() === key)
  return hit && isObject(configs[hit]) ? (configs[hit] as DataObject) : {}
}

export function getActionConfig(field: FrameActionFieldLike): DataObject {
  return readCfg(field.configs, 'action')
}

export function getInfoConfig(field: FrameActionFieldLike): DataObject {
  return readCfg(field.configs, 'info')
}

export function isActionField(field: FrameActionFieldLike): boolean {
  return String(field.type || '').toLowerCase() === 'action' && !!String(getActionConfig(field).id || '').trim()
}

export function isInfoField(field: FrameActionFieldLike): boolean {
  return String(field.type || '').toLowerCase() === 'info'
}

/** Aktions-IDs, deren Rechte/Zustand fuer den Satz geladen werden muessen (Aktionen und Zustandsquellen von Hinweisen). */
export function collectFrameActionIds(fields: FrameActionFieldLike[]): string[] {
  const ids = new Set<string>()
  fields.forEach((field) => {
    if (isActionField(field)) ids.add(String(getActionConfig(field).id).trim())
    else if (isInfoField(field)) {
      const stateAction = String(readCfg(getInfoConfig(field), 'state').action || '').trim()
      if (stateAction) ids.add(stateAction)
    }
  })
  return Array.from(ids).sort()
}

function getByPath(source: DataObject | undefined, path: string): unknown {
  let cursor: any = source
  for (const part of String(path || '').split('.').filter(Boolean)) {
    if (!isObject(cursor)) return undefined
    const key = Object.keys(cursor).find((k) => k === part) ?? Object.keys(cursor).find((k) => k.toLowerCase() === part.toLowerCase())
    cursor = key === undefined ? undefined : cursor[key]
  }
  return cursor
}

/** `state.<pfad>` liest den Zustand der Aktion, alles andere den Datensatz. */
function resolvePath(path: string, data: DataObject, state: DataObject | null): unknown {
  const p = String(path || '').trim()
  if (p.toLowerCase().startsWith('state.')) return getByPath(state || {}, p.slice(6))
  return getByPath(data, p)
}

function toBool(value: unknown): boolean {
  if (typeof value === 'string') return ['true', '1', 'ja', 'yes', 'y', 'on'].includes(value.trim().toLowerCase())
  return !!value
}

function looseEquals(actual: unknown, expected: unknown): boolean {
  if (typeof expected === 'boolean') return toBool(actual) === expected
  return String(actual ?? '').trim().toLowerCase() === String(expected ?? '').trim().toLowerCase()
}

function isEmpty(value: unknown): boolean {
  if (value === null || value === undefined) return true
  if (typeof value === 'string') return value.trim() === ''
  if (Array.isArray(value)) return value.length === 0
  if (isObject(value)) return Object.keys(value).length === 0
  return false
}

/** Deklarative Bedingung (nur Pfad plus equals/not/in/empty/not_empty); ohne Bedingung gilt sie als erfuellt. */
export function evaluateCondition(condition: unknown, data: DataObject, state: DataObject | null): boolean {
  if (!isObject(condition) || !String(condition.path || '').trim()) return true
  const value = resolvePath(String(condition.path), data, state)
  if ('equals' in condition) return looseEquals(value, condition.equals)
  if ('not' in condition) return !looseEquals(value, condition.not)
  if (Array.isArray(condition.in)) return condition.in.some((item) => looseEquals(value, item))
  if (condition.empty === true) return isEmpty(value)
  if (condition.not_empty === true) return !isEmpty(value)
  return true
}

/** Ersetzt `{{pfad}}` durch Werte aus Datensatz oder Zustand (`{{state.source_name}}`); fehlende Werte werden leer. */
export function renderTemplate(template: string, data: DataObject, state: DataObject | null): string {
  return String(template || '').replace(/\{\{\s*([A-Za-z0-9_.]+)\s*\}\}/g, (_m, path: string) => {
    const value = resolvePath(path, data, state)
    return value === undefined || value === null ? '' : String(value)
  })
}

function formatValue(value: unknown, format: string): string {
  if (format === 'yes_no') return toBool(value) ? 'Ja' : 'Nein'
  return value === undefined || value === null ? '' : String(value)
}

function normalizeSeverity(value: unknown): FrameActionSeverity {
  const v = String(value || '').trim().toLowerCase()
  return v === 'warning' || v === 'error' ? v : 'info'
}

function normalizeModes(value: unknown, fallback: FrameActionMode[]): FrameActionMode[] {
  const list = Array.isArray(value) ? value.map((m) => String(m).trim().toLowerCase()) : []
  const modes = list.filter((m): m is FrameActionMode => m === 'create' || m === 'edit')
  return modes.length ? modes : fallback
}

export interface BuildViewContext {
  data: DataObject
  mode: FrameActionMode
  /** Zustaende vom Backend; undefined solange sie noch laden (Aktionen bleiben dann verborgen). */
  states: Record<string, FrameActionStateEntry> | undefined
}

/** Sichtbarkeit, Aktivierung und Text eines `action`/`info`-Controls; reine Funktion ohne Request. */
export function buildActionView(field: FrameActionFieldLike, ctx: BuildViewContext): FrameActionView {
  const hidden: FrameActionView = { visible: false, enabled: false, text: '', severity: 'info', placement: 'field' }

  if (isActionField(field)) {
    const cfg = getActionConfig(field)
    const placement: FrameActionPlacement = String(cfg.placement || '').toLowerCase() === 'header' ? 'header' : 'field'
    const entry = ctx.states?.[String(cfg.id).trim()]
    if (!entry) return { ...hidden, placement }
    const defaultModes: FrameActionMode[] = entry.executor === 'host' ? ['create', 'edit'] : ['edit']
    if (!normalizeModes(cfg.modes, defaultModes).includes(ctx.mode)) return { ...hidden, placement }
    const denied = !entry.allowed
    const disableWhenDenied = String(cfg.when_denied || '').toLowerCase() === 'disable'
    if (denied && !disableWhenDenied) return { ...hidden, placement }
    const state = entry.state
    if (!evaluateCondition(cfg.visible_when, ctx.data, state)) return { ...hidden, placement }
    const enabled = !denied && evaluateCondition(cfg.enabled_when, ctx.data, state)
    return {
      visible: true,
      enabled,
      disabledReason: denied ? entry.reason || undefined : undefined,
      text: field.label || field.name || '',
      severity: 'info',
      placement,
    }
  }

  if (isInfoField(field)) {
    const cfg = getInfoConfig(field)
    const placement: FrameActionPlacement = String(cfg.placement || '').toLowerCase() === 'header' ? 'header' : 'field'
    if (!normalizeModes(cfg.modes, ['edit']).includes(ctx.mode)) return { ...hidden, placement }
    const stateAction = String(readCfg(cfg, 'state').action || '').trim()
    let state: DataObject | null = null
    if (stateAction) {
      const entry = ctx.states?.[stateAction]
      if (!entry || !entry.allowed) return { ...hidden, placement }
      state = entry.state
    }
    if (!evaluateCondition(cfg.visible_when, ctx.data, state)) return { ...hidden, placement }
    const text = cfg.text
      ? renderTemplate(String(cfg.text), ctx.data, state)
      : formatValue(cfg.value_path ? resolvePath(String(cfg.value_path), ctx.data, state) : undefined, String(cfg.format || ''))
    return { visible: true, enabled: false, text, severity: normalizeSeverity(cfg.severity), placement }
  }

  return hidden
}

/** Rechte und Zustaende fuer einen Satz in einer gebuendelten Anfrage (nur wenn der Frame solche Controls enthaelt). */
export function useFrameActionStates(params: {
  table: string | null
  uid: string | null
  ids: string[]
  enabled?: boolean
  /** Host-Aktionen brauchen keinen Datensatz (z. B. im Entwurf); der Server liefert dann nur die Rechte. */
  allowNoRecord?: boolean
}) {
  const { table, uid, ids, enabled = true, allowNoRecord = false } = params
  const key = ids.join('|')
  return useQuery({
    queryKey: ['frame-actions', 'state', table, uid, key],
    queryFn: () => frameActionsAPI.getStates(table as string, uid, ids),
    enabled: enabled && !!table && (!!uid || allowNoRecord) && ids.length > 0,
    staleTime: 60_000,
  })
}

interface PendingRun {
  field: FrameActionFieldLike
  withDirtyWarning: boolean
}

function paramFields(cfg: DataObject): PdvmDialogModalField[] {
  const raw = Array.isArray(cfg.params) ? cfg.params : []
  return raw
    .filter((p): p is DataObject => isObject(p) && !!String(p.name || '').trim())
    .map((p) => ({
      name: String(p.name).trim(),
      label: String(p.label || p.name),
      type: String(p.type || 'text').toLowerCase() === 'text' ? 'textarea' : 'text',
      required: p.required === true,
    }))
}

/**
 * Ausfuehrungsablauf einer Aktion: optional Bestaetigung/Parameter (aus dem Control) und Warnung bei ungespeicherten
 * Aenderungen (der Benutzer kann abbrechen), danach `POST /api/frame-actions/{id}/run` und ein Ergebnisfenster.
 * `element` muss einmal im Host gerendert werden.
 */
export function useFrameActionRunner(params: {
  table: string | null
  uid: string | null
  dirty: boolean
  onRefresh?: (refresh: FrameActionResult['refresh']) => void | Promise<void>
  /** Aktions-ID -> Handler im Host; dafuer entfaellt der Server-Aufruf (Rechte kommen weiterhin vom Server-Zustand). */
  hostActions?: Record<string, () => void | Promise<void>>
}): { trigger: (field: FrameActionFieldLike) => void; busy: boolean; element: ReactNode } {
  const { table, uid, dirty, onRefresh, hostActions } = params
  const queryClient = useQueryClient()
  const { logout } = useAuth()
  const [pending, setPending] = useState<PendingRun | null>(null)
  const [busy, setBusy] = useState(false)
  const [outcome, setOutcome] = useState<{ message: string; error: boolean; relogin?: boolean } | null>(null)

  const execute = useCallback(
    async (field: FrameActionFieldLike, values: Record<string, string>) => {
      if (!table || !uid) return
      setBusy(true)
      try {
        const res = await frameActionsAPI.run(String(getActionConfig(field).id).trim(), table, uid, values)
        // `data.relogin`: die Aktion verlangt eine Neuanmeldung (z. B. Mandanten-Datenbank eingerichtet); Abmeldung nach der Bestätigung
        setOutcome({ message: res.message, error: res.status === 'error', relogin: res.status !== 'error' && res.data?.relogin === true })
        if (res.refresh.length) {
          await queryClient.invalidateQueries({ queryKey: ['frame-actions', 'state'] })
          await onRefresh?.(res.refresh)
        }
      } catch (e: any) {
        setOutcome({ message: e?.response?.data?.detail || e?.message || uiText('action.failedFallback'), error: true })
      } finally {
        setBusy(false)
      }
    },
    [table, uid, queryClient, onRefresh]
  )

  const trigger = useCallback(
    (field: FrameActionFieldLike) => {
      const cfg = getActionConfig(field)
      const hostHandler = hostActions?.[String(cfg.id).trim()]
      if (hostHandler) {
        void hostHandler()
        return
      }
      if (!isObject(cfg.confirm) && paramFields(cfg).length === 0 && !dirty) {
        void execute(field, {})
        return
      }
      setPending({ field, withDirtyWarning: dirty })
    },
    [dirty, execute, hostActions]
  )

  const closeOutcome = () => {
    const relogin = outcome?.relogin
    setOutcome(null)
    if (relogin) void logout()
  }

  const cfg = pending ? getActionConfig(pending.field) : {}
  const confirm = isObject(cfg.confirm) ? cfg.confirm : {}
  const fields = paramFields(cfg)
  const message = (
    <>
      {confirm.message ? <div>{String(confirm.message)}</div> : null}
      {pending?.withDirtyWarning ? (
        <div style={{ marginTop: confirm.message ? 8 : 0, color: 'var(--color-warning-text)' }}>{uiText('action.dirtyWarning')}</div>
      ) : null}
    </>
  )

  const element = (
    <>
      <PdvmDialogModal
        open={!!pending}
        kind={fields.length ? 'form' : 'confirm'}
        title={String(confirm.title || pending?.field.label || '')}
        message={message}
        fields={fields}
        confirmLabel={String(confirm.label || (pending?.withDirtyWarning ? uiText('action.confirmAnyway') : uiText('action.confirm')))}
        cancelLabel={uiText('action.cancel')}
        busy={busy}
        onCancel={() => setPending(null)}
        onConfirm={async (values) => {
          const current = pending
          setPending(null)
          if (current) await execute(current.field, values || {})
        }}
      />
      <PdvmDialogModal
        open={!!outcome}
        kind="info"
        title={outcome?.error ? uiText('action.failedTitle') : uiText('action.resultTitle')}
        message={outcome?.message || ''}
        confirmLabel={outcome?.relogin ? uiText('action.relogin') : undefined}
        onCancel={closeOutcome}
        onConfirm={closeOutcome}
      />
    </>
  )

  return { trigger, busy, element }
}
