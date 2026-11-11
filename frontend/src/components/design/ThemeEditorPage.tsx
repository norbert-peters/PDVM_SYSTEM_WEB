/**
 * Theme-Editor (P4): "Mein Design" (jeder Benutzer, nur vom Mandanten freigegebene Tokens)
 * und "Mandant" (Rolle 'overlay': Overlay, Standard-Varianten, Standard-Modus, Freigaben).
 *
 * Die Eingabefelder sind PdvmInputControl-Instanzen, deren Typ aus dem Token-Katalog stammt
 * (GET /api/layout/catalog). Leerer Wert = nicht überschrieben.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { PdvmDialogModal } from '../common/PdvmDialogModal'
import { PdvmInputControl, type PdvmInputType } from '../common/PdvmInputControl'
import {
  layoutApi,
  themeSaveErrors,
  type LayoutArea,
  type MandantThemeSettings,
  type ThemeCatalogResponse,
  type ThemeEditorState,
  type ThemeMode,
  type ThemeOverlay,
  type ThemePackageInfo,
  type ThemeScope,
  type ThemeTokenSpec,
  type UserThemeSettings,
} from '../../api/layout'
import { useTheme } from '../../hooks/useTheme'
import { refMatchesPattern } from '../../utils/themeTokens'
import { evaluatePairs, effectiveTokenValue, type PairEvaluation } from '../../utils/themeContrastPairs'
import { applyLayoutAttributes } from '../../utils/layoutAttributes'
import type { ThemeTokens } from '../../utils/themeVars'
import './ThemeEditorPage.css'

type Draft = Record<ThemeMode, Record<string, string>> // "<gruppe>.<token>" -> Wert

const MODES: ThemeMode[] = ['light', 'dark']
const MODE_LABEL: Record<ThemeMode, string> = { light: 'Hell', dark: 'Dunkel' }

/** Leere Layout-Einträge bedeuten "nicht gesetzt"; für den Vergleich Entwurf <-> gespeichert entfernen */
function normalizeSettings(settings: Record<string, any>): string {
  const clean = (value: any): any => {
    if (Array.isArray(value)) return value
    if (value && typeof value === 'object') {
      return Object.fromEntries(
        Object.entries(value)
          .filter(([, v]) => !(v === '' || (Array.isArray(v) && v.length === 0)))
          .sort(([a], [b]) => a.localeCompare(b))
      )
    }
    return value
  }
  return JSON.stringify(
    Object.fromEntries(Object.entries(settings).map(([k, v]) => [k, clean(v)]).sort(([a], [b]) => String(a).localeCompare(String(b))))
  )
}

function optionLabel(area: LayoutArea, value: string): string {
  return area.options.find((o) => o.value === value)?.label || value
}

function flatten(tokens: ThemeTokens | undefined): Record<string, string> {
  const out: Record<string, string> = {}
  Object.entries(tokens || {}).forEach(([group, entries]) => {
    Object.entries(entries || {}).forEach(([token, value]) => {
      out[`${group}.${token}`] = String(value)
    })
  })
  return out
}

function nest(flat: Record<string, string>): ThemeTokens {
  const out: ThemeTokens = {}
  Object.entries(flat).forEach(([ref, value]) => {
    if (!value.trim()) return
    const [group, ...rest] = ref.split('.')
    ;(out[group] ||= {})[rest.join('.')] = value.trim()
  })
  return out
}

function lookup(tokens: ThemeTokens, ref: string): string {
  const [group, ...rest] = ref.split('.')
  return tokens[group]?.[rest.join('.')] ?? ''
}

function toOptions(values: string[] | undefined) {
  return (values || []).map((v) => ({ value: v, label: v }))
}

export default function ThemeEditorPage() {
  const { reloadTheme, currentTheme } = useTheme()
  const [scope, setScope] = useState<ThemeScope>('user')
  const [state, setState] = useState<ThemeEditorState | null>(null)
  const [catalog, setCatalog] = useState<ThemeCatalogResponse | null>(null)
  const [canEditOverlay, setCanEditOverlay] = useState(false)
  const [mode, setMode] = useState<ThemeMode>('light')
  const [draft, setDraft] = useState<Draft>({ light: {}, dark: {} })
  const [settings, setSettings] = useState<Record<string, any>>({})
  const [filter, setFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [errors, setErrors] = useState<string[]>([])
  const [saved, setSaved] = useState(false)
  const [confirmClear, setConfirmClear] = useState(false)
  const [availablePackages, setAvailablePackages] = useState<ThemePackageInfo[]>([])

  const load = useCallback(async (nextScope: ThemeScope) => {
    setLoading(true)
    setErrors([])
    try {
      const [editorState, cat, packages] = await Promise.all([
        layoutApi.getEditorState(nextScope),
        catalog ? Promise.resolve(catalog) : layoutApi.getCatalog(),
        nextScope === 'mandant' ? layoutApi.getAvailablePackages() : Promise.resolve<ThemePackageInfo[]>([]),
      ])
      setCatalog(cat)
      setAvailablePackages(packages)
      setState(editorState)
      setCanEditOverlay(editorState.can_edit_overlay)
      setDraft({ light: flatten(editorState.modes.light.overlay), dark: flatten(editorState.modes.dark.overlay) })
      setSettings({ ...editorState.settings })
    } catch (err) {
      setState(null)
      setErrors(themeSaveErrors(err))
    } finally {
      setLoading(false)
    }
    // catalog bewusst nicht als Abhängigkeit: wird nur einmal geladen
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Paketwechsel (Ebene "Mein Design"): Basis und Varianten des gewählten Pakets laden, Entwurf bleibt erhalten
  const previewPackage = async (guid: string) => {
    if (!state) return
    const isDefault = state.packages.find((p) => p.guid === guid)?.is_default
    setSaved(false)
    try {
      const preview = await layoutApi.getEditorState('user', guid)
      setState(preview)
      setSettings((s) => ({
        ...s,
        theme_choice: isDefault ? '' : guid,
        variant_light: preview.variants.light.includes(s.variant_light) ? s.variant_light : '',
        variant_dark: preview.variants.dark.includes(s.variant_dark) ? s.variant_dark : '',
      }))
    } catch (err) {
      setErrors(themeSaveErrors(err))
    }
  }

  useEffect(() => {
    void load(scope)
  }, [scope, load])

  const saveable = scope === 'user' || canEditOverlay
  const savedDraft = useMemo<Draft>(
    () => (state ? { light: flatten(state.modes.light.overlay), dark: flatten(state.modes.dark.overlay) } : { light: {}, dark: {} }),
    [state]
  )
  const dirty = useMemo(() => {
    if (!state) return false
    const normalize = (d: Draft) => JSON.stringify(MODES.map((m) => Object.entries(d[m]).filter(([, v]) => v.trim()).sort()))
    return normalize(draft) !== normalize(savedDraft) || normalizeSettings(settings) !== normalizeSettings(state.settings)
  }, [draft, savedDraft, settings, state])

  // Layout-Vorschau: gewählte Varianten sofort auf <html> setzen, beim Verlassen den gespeicherten Stand wiederherstellen
  const previewLayout = useMemo<Record<string, string>>(() => {
    if (!state) return {}
    const out: Record<string, string> = {}
    Object.entries(state.layout).forEach(([area, data]) => {
      out[area] = scope === 'user'
        ? (settings.layout_choice?.[area] || data.mandant_default)
        : (settings.layout_default?.[area] || data.default)
    })
    return out
  }, [state, scope, settings.layout_choice, settings.layout_default])
  const savedLayoutRef = useRef(currentTheme?.layout)
  useEffect(() => {
    savedLayoutRef.current = currentTheme?.layout
  }, [currentTheme])
  useEffect(() => {
    if (!state) return
    applyLayoutAttributes(previewLayout)
    return () => applyLayoutAttributes(savedLayoutRef.current)
  }, [previewLayout, state])

  // Basis + Entwurf = so sieht das Theme nach dem Speichern aus
  const effective = useMemo<ThemeTokens>(() => {
    if (!state) return {}
    const merged: ThemeTokens = {}
    Object.entries(state.modes[mode].base).forEach(([g, t]) => (merged[g] = { ...t }))
    Object.entries(nest(draft[mode])).forEach(([g, t]) => (merged[g] = { ...(merged[g] || {}), ...t }))
    return merged
  }, [state, draft, mode])

  const visibleGroups = useMemo(() => {
    if (!catalog || !state) return []
    const needle = filter.trim().toLowerCase()
    return Object.entries(catalog.groups)
      .map(([group, data]) => {
        const tokens = Object.entries(data.tokens).filter(([name, spec]) => {
          if (scope === 'user') {
            if (!spec.user_editable) return false
            if (!(state.allowed_patterns || []).some((p) => refMatchesPattern(`${group}.${name}`, p))) return false
          }
          return !needle || `${data.label} ${spec.label}`.toLowerCase().includes(needle)
        })
        return { group, label: data.label, tokens }
      })
      .filter((g) => g.tokens.length > 0)
  }, [catalog, state, scope, filter])

  // Kontrast: je Modus Basis + Entwurf auswerten. "Blockierend" sind Paare, die der Entwurf veraendert und die
  // unter dem Mindestkontrast liegen (der Server lehnt sie ab); der Rest sind Hinweise zum Paket.
  const chainByRef = useMemo(() => {
    const map: Record<string, string[]> = {}
    ;(catalog?.contrast_pairs || []).forEach((p) => {
      map[p.fg] = p.fg_chain
      map[p.bg] = p.bg_chain
    })
    return map
  }, [catalog])

  const mergedFor = useCallback((m: ThemeMode): ThemeTokens => {
    if (!state) return {}
    const merged: ThemeTokens = {}
    Object.entries(state.modes[m].base).forEach(([g, t]) => (merged[g] = { ...t }))
    Object.entries(nest(draft[m])).forEach(([g, t]) => (merged[g] = { ...(merged[g] || {}), ...t }))
    return merged
  }, [state, draft])

  const evaluations = useMemo(() => {
    const pairs = catalog?.contrast_pairs || []
    const blocking: Array<PairEvaluation & { mode: ThemeMode }> = []
    const inherited: PairEvaluation[] = []
    MODES.forEach((m) => {
      const touched = new Set(Object.entries(draft[m]).filter(([, v]) => v.trim()).map(([ref]) => ref))
      evaluatePairs(mergedFor(m), pairs, touched).forEach((ev) => {
        if (ev.fgChanged || ev.bgChanged) blocking.push({ ...ev, mode: m })
        else if (m === mode) inherited.push(ev)
      })
    })
    return { blocking, inherited }
  }, [catalog, draft, mergedFor, mode])

  const labelOf = useCallback((ref: string) => {
    const [group, ...rest] = ref.split('.')
    const data = catalog?.groups[group]
    return data ? `${data.label}: ${data.tokens[rest.join('.')]?.label || rest.join('.')}` : ref
  }, [catalog])

  const setValue = (ref: string, value: string) => {
    setSaved(false)
    setDraft((prev) => ({ ...prev, [mode]: { ...prev[mode], [ref]: value } }))
  }

  const applySuggestions = (items: Array<{ mode: ThemeMode; suggestions: Array<{ ref: string; value: string }> }>) => {
    setSaved(false)
    setDraft((prev) => {
      const next: Draft = { light: { ...prev.light }, dark: { ...prev.dark } }
      items.forEach((it) => it.suggestions.forEach((s) => { next[it.mode][s.ref] = s.value }))
      return next
    })
  }

  const buildOverlay = (): ThemeOverlay => ({ light: nest(draft.light), dark: nest(draft.dark) })

  const save = async () => {
    setSaving(true)
    setErrors([])
    setSaved(false)
    try {
      if (scope === 'user') {
        const s = settings as UserThemeSettings
        await layoutApi.saveUserSettings({
          overlay: buildOverlay(),
          theme_choice: s.theme_choice || '',
          variant_light: s.variant_light || '',
          variant_dark: s.variant_dark || '',
          layout_choice: s.layout_choice || {},
        })
      } else {
        const s = settings as MandantThemeSettings
        await layoutApi.saveMandantSettings({
          theme_default: s.theme_default || undefined,
          theme_allowed: s.theme_allowed || [],
          theme_light: s.theme_light || '',
          theme_dark: s.theme_dark || '',
          default_mode: s.default_mode || '',
          user_theme_edit: s.user_theme_edit || [],
          layout_default: s.layout_default || {},
          layout_allowed: s.layout_allowed || {},
        })
        await layoutApi.saveMandantOverlay(buildOverlay())
      }
      await load(scope)
      await reloadTheme()
      setSaved(true)
    } catch (err) {
      setErrors(themeSaveErrors(err))
    } finally {
      setSaving(false)
    }
  }

  const resetToSaved = () => {
    if (!state) return
    if (scope === 'user') {
      void load(scope) // setzt auch die Paket-Vorschau zurück
      setSaved(false)
      return
    }
    setDraft(savedDraft)
    setSettings({ ...state.settings })
    setErrors([])
    setSaved(false)
  }

  const clearMode = () => {
    setDraft((prev) => ({ ...prev, [mode]: {} }))
    setConfirmClear(false)
    setSaved(false)
  }

  const renderToken = (group: string, name: string, spec: ThemeTokenSpec) => {
    const ref = `${group}.${name}`
    const baseValue = lookup(state!.modes[mode].base, ref)
    const value = draft[mode][ref] ?? ''
    const partner = (spec.contrast_against || [])[0]
    const resolvedConfigs = partner
      ? { theme_token: { contrast_against: { value: effectiveTokenValue(effective, chainByRef[partner.ref] || [partner.ref]).value, min: partner.min, label: labelOf(partner.ref) } } }
      : undefined
    return (
      <div key={ref} className={`pdvm-theme-editor__token${value.trim() ? ' pdvm-theme-editor__token--overridden' : ''}`}>
        <PdvmInputControl
          id={`theme-${mode}-${ref}`}
          label={spec.label}
          type={spec.control_type as PdvmInputType}
          value={value}
          placeholder={baseValue || undefined}
          options={toOptions(spec.options)}
          resolvedConfigs={resolvedConfigs}
          helpEnabled={false}
          disabled={!saveable}
          onChange={(v) => setValue(ref, String(v ?? ''))}
        />
      </div>
    )
  }

  const variantOptions = (m: ThemeMode) => toOptions(state?.variants[m])
  const layoutAreas = Object.entries(state?.layout || {})
  const presetOptions = (catalog?.user_edit_presets || []).map((p) => ({ value: p.value, label: p.label }))

  if (loading && !state) return <div className="pdvm-theme-editor"><p>Design wird geladen …</p></div>

  return (
    <div className="pdvm-theme-editor">
      <header className="pdvm-theme-editor__head">
        <h2>Design anpassen</h2>
        <div className="pdvm-theme-editor__tabs" role="tablist">
          <button type="button" role="tab" aria-selected={scope === 'user'} className={scope === 'user' ? 'is-active' : ''} onClick={() => setScope('user')}>
            Mein Design
          </button>
          {canEditOverlay ? (
            <button type="button" role="tab" aria-selected={scope === 'mandant'} className={scope === 'mandant' ? 'is-active' : ''} onClick={() => setScope('mandant')}>
              Mandant
            </button>
          ) : null}
        </div>
      </header>

      {errors.length ? (
        <div className="pdvm-theme-editor__alert pdvm-theme-editor__alert--error" role="alert">
          {errors.map((e) => <div key={e}>{e}</div>)}
        </div>
      ) : null}
      {saved ? <div className="pdvm-theme-editor__alert pdvm-theme-editor__alert--ok">Gespeichert. Das Design ist aktiv.</div> : null}

      {state ? (
        <>
          <section className="pdvm-theme-editor__panel">
            <h3>{scope === 'user' ? 'Meine Einstellungen' : 'Mandanten-Einstellungen'}</h3>
            <div className="pdvm-theme-editor__settings">
              {scope === 'user' && state.packages.length > 1 ? (
                <PdvmInputControl
                  label="Farbschema (Theme-Paket)"
                  type="dropdown"
                  value={settings.theme_choice || state.packages.find((p) => p.is_default)?.guid || ''}
                  options={state.packages.map((p) => ({ value: p.guid, label: p.is_default ? `${p.name} (Standard)` : p.name }))}
                  helpEnabled={false}
                  onChange={(v) => void previewPackage(String(v ?? ''))}
                />
              ) : null}
              {scope === 'mandant' ? (
                <>
                  <PdvmInputControl
                    label="Standard-Paket"
                    type="dropdown"
                    value={settings.theme_default || ''}
                    options={availablePackages.map((p) => ({ value: p.guid, label: p.name }))}
                    helpEnabled={false}
                    disabled={!saveable}
                    onChange={(v) => { setSaved(false); setSettings((s) => ({ ...s, theme_default: v, theme_light: '', theme_dark: '' })) }}
                  />
                  <PdvmInputControl
                    label="Weitere Pakete für Benutzer"
                    type="multi_dropdown"
                    value={settings.theme_allowed || []}
                    options={availablePackages.filter((p) => p.guid !== settings.theme_default).map((p) => ({ value: p.guid, label: p.name }))}
                    helpEnabled={false}
                    disabled={!saveable}
                    onChange={(v) => { setSaved(false); setSettings((s) => ({ ...s, theme_allowed: Array.isArray(v) ? v : [] })) }}
                  />
                </>
              ) : null}
              <PdvmInputControl
                label={scope === 'user' ? 'Variante Hell' : 'Standard-Variante Hell'}
                type="dropdown"
                value={scope === 'user' ? settings.variant_light || '' : settings.theme_light || ''}
                options={variantOptions('light')}
                helpEnabled={false}
                disabled={!saveable}
                onChange={(v) => { setSaved(false); setSettings((s) => ({ ...s, [scope === 'user' ? 'variant_light' : 'theme_light']: v })) }}
              />
              <PdvmInputControl
                label={scope === 'user' ? 'Variante Dunkel' : 'Standard-Variante Dunkel'}
                type="dropdown"
                value={scope === 'user' ? settings.variant_dark || '' : settings.theme_dark || ''}
                options={variantOptions('dark')}
                helpEnabled={false}
                disabled={!saveable}
                onChange={(v) => { setSaved(false); setSettings((s) => ({ ...s, [scope === 'user' ? 'variant_dark' : 'theme_dark']: v })) }}
              />
              {scope === 'mandant' ? (
                <>
                  <PdvmInputControl
                    label="Standard-Modus"
                    type="dropdown"
                    value={settings.default_mode || ''}
                    options={[{ value: 'light', label: 'Hell' }, { value: 'dark', label: 'Dunkel' }]}
                    helpEnabled={false}
                    disabled={!saveable}
                    onChange={(v) => { setSaved(false); setSettings((s) => ({ ...s, default_mode: v })) }}
                  />
                  <PdvmInputControl
                    label="Für Benutzer freigegeben"
                    type="multi_dropdown"
                    value={settings.user_theme_edit || []}
                    options={presetOptions}
                    helpEnabled={false}
                    disabled={!saveable}
                    onChange={(v) => { setSaved(false); setSettings((s) => ({ ...s, user_theme_edit: Array.isArray(v) ? v : [] })) }}
                  />
                </>
              ) : null}
            </div>
            <p className="pdvm-theme-editor__hint">
              {scope === 'user'
                ? 'Ohne Auswahl gilt die Variante des Mandanten.'
                : 'Ohne Auswahl gilt die Variante „light“ bzw. „dark“ des Pakets. Varianten und Overlay beziehen sich auf das gespeicherte Standard-Paket; das Overlay gilt für alle Pakete. Nach einem Paketwechsel zuerst speichern.'}
            </p>
            {scope === 'user' && !(state.allowed_patterns || []).length ? (
              <p className="pdvm-theme-editor__hint">Ihr Mandant hat keine Farben zur Anpassung freigegeben; Sie können nur die Variante wählen.</p>
            ) : null}
          </section>

          <section className="pdvm-theme-editor__panel">
            <h3>Layout</h3>
            {scope === 'user' && !layoutAreas.some(([, a]) => a.available.length > 1) ? (
              <p className="pdvm-theme-editor__hint">Ihr Mandant bietet keine weiteren Layout-Varianten an.</p>
            ) : null}
            <div className="pdvm-theme-editor__settings">
              {layoutAreas.map(([key, area]) => {
                const selectable = area.options.filter((o) => area.available.includes(o.value))
                if (scope === 'user') {
                  if (selectable.length < 2) return null
                  const chosen = settings.layout_choice?.[key] || area.mandant_default
                  return (
                    <div key={key} className="pdvm-theme-editor__layoutArea">
                      <PdvmInputControl
                        label={`${area.label} (Vorgabe: ${optionLabel(area, area.mandant_default)})`}
                        type="dropdown"
                        value={settings.layout_choice?.[key] || ''}
                        options={selectable.map((o) => ({ value: o.value, label: o.label }))}
                        helpEnabled={false}
                        onChange={(v) => { setSaved(false); setSettings((s) => ({ ...s, layout_choice: { ...(s.layout_choice || {}), [key]: v } })) }}
                      />
                      <p className="pdvm-theme-editor__hint">{area.options.find((o) => o.value === chosen)?.description}</p>
                    </div>
                  )
                }
                const effective = settings.layout_default?.[key] || area.default
                return (
                  <div key={key} className="pdvm-theme-editor__layoutArea">
                    <PdvmInputControl
                      label={`${area.label}: Vorgabe`}
                      type="dropdown"
                      value={settings.layout_default?.[key] || ''}
                      options={area.options.map((o) => ({ value: o.value, label: o.label }))}
                      helpEnabled={false}
                      disabled={!saveable}
                      onChange={(v) => { setSaved(false); setSettings((s) => ({ ...s, layout_default: { ...(s.layout_default || {}), [key]: v } })) }}
                    />
                    <PdvmInputControl
                      label={`${area.label}: für Benutzer freigegeben`}
                      type="multi_dropdown"
                      value={settings.layout_allowed?.[key] || []}
                      options={area.options.map((o) => ({ value: o.value, label: o.label }))}
                      helpEnabled={false}
                      disabled={!saveable}
                      onChange={(v) => { setSaved(false); setSettings((s) => ({ ...s, layout_allowed: { ...(s.layout_allowed || {}), [key]: Array.isArray(v) ? v : [] } })) }}
                    />
                    <p className="pdvm-theme-editor__hint">{area.options.find((o) => o.value === effective)?.description}</p>
                  </div>
                )
              })}
            </div>
            <p className="pdvm-theme-editor__hint">
              {scope === 'user'
                ? 'Die Auswahl wird sofort als Vorschau angewendet; gespeichert wird mit „Speichern“.'
                : 'Benutzer sehen nur die Vorgabe und die hier freigegebenen Varianten. Die Auswahl wirkt sofort als Vorschau.'}
            </p>
          </section>

          <section className="pdvm-theme-editor__panel">
            <div className="pdvm-theme-editor__bar">
              <div className="pdvm-theme-editor__tabs" role="tablist" aria-label="Modus">
                {MODES.map((m) => (
                  <button key={m} type="button" role="tab" aria-selected={mode === m} className={mode === m ? 'is-active' : ''} onClick={() => setMode(m)}>
                    {MODE_LABEL[m]}
                  </button>
                ))}
              </div>
              <input
                type="search"
                className="pdvm-pic__input pdvm-theme-editor__filter"
                placeholder="Einstellung suchen …"
                aria-label="Einstellung suchen"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              />
              <div className="pdvm-theme-editor__actions">
                <button type="button" className="pdvm-theme-editor__btn" onClick={() => setConfirmClear(true)} disabled={!saveable || saving || !Object.values(draft[mode]).some((v) => v.trim())}>
                  {MODE_LABEL[mode]}: Anpassungen entfernen
                </button>
                <button type="button" className="pdvm-theme-editor__btn" onClick={resetToSaved} disabled={!dirty || saving}>Verwerfen</button>
                <button
                  type="button"
                  className="pdvm-theme-editor__btn pdvm-theme-editor__btn--primary"
                  onClick={() => void save()}
                  disabled={!saveable || !dirty || saving || evaluations.blocking.length > 0}
                  title={evaluations.blocking.length ? 'Speichern nicht möglich: Kontrast zu gering' : undefined}
                >
                  {saving ? 'Speichern …' : 'Speichern'}
                </button>
              </div>
            </div>

            <PdvmInputControl
              label={`Vorschau (${MODE_LABEL[mode]}, Variante ${state.modes[mode].variant || '-'})`}
              type="theme_preview"
              value={effective}
              resolvedConfigs={{ theme_token: { mode } }}
              helpEnabled={false}
              onChange={() => undefined}
            />

            {evaluations.blocking.length ? (
              <div className="pdvm-theme-editor__alert pdvm-theme-editor__alert--error" role="alert">
                <strong>Kontrast zu gering – so lässt sich nicht speichern:</strong>
                {evaluations.blocking.map((ev) => (
                  <div key={`${ev.mode}|${ev.pair.fg}|${ev.pair.bg}`} className="pdvm-theme-editor__issue">
                    <span>
                      {MODE_LABEL[ev.mode]}: {labelOf(ev.pair.fg)} auf {labelOf(ev.pair.bg)} = {ev.ratio}:1 (mind. {ev.pair.min}:1)
                      {ev.suggestions.length ? ` – Vorschlag: ${ev.suggestions.map((s) => `${labelOf(s.ref)} = ${s.value}`).join(', ')}` : ''}
                    </span>
                    {ev.suggestions.length ? (
                      <button type="button" className="pdvm-theme-editor__btn" onClick={() => applySuggestions([ev])}>Vorschlag übernehmen</button>
                    ) : null}
                  </div>
                ))}
                <div>
                  <button
                    type="button"
                    className="pdvm-theme-editor__btn"
                    onClick={() => applySuggestions(evaluations.blocking)}
                    disabled={!evaluations.blocking.some((ev) => ev.suggestions.length)}
                  >
                    Alle Vorschläge übernehmen
                  </button>
                </div>
              </div>
            ) : null}

            {evaluations.inherited.length ? (
              <div className="pdvm-theme-editor__alert pdvm-theme-editor__alert--warn">
                <strong>Hinweis – das Theme selbst unterschreitet den Richtwert (WCAG AA); Ihre Anpassungen sind davon nicht betroffen:</strong>
                {evaluations.inherited.map((ev) => (
                  <div key={`${ev.pair.fg}|${ev.pair.bg}`}>{labelOf(ev.pair.fg)} auf {labelOf(ev.pair.bg)}: {ev.ratio}:1 (mind. {ev.pair.min}:1)</div>
                ))}
              </div>
            ) : null}

            {visibleGroups.length === 0 ? <p className="pdvm-theme-editor__hint">Keine passenden Einstellungen.</p> : null}
            {visibleGroups.map(({ group, label, tokens }) => (
              <details key={group} className="pdvm-theme-editor__group" open={visibleGroups.length <= 3 || !!filter.trim()}>
                <summary>
                  {label}
                  <span className="pdvm-theme-editor__count">
                    {tokens.filter(([n]) => (draft[mode][`${group}.${n}`] || '').trim()).length} angepasst
                  </span>
                </summary>
                <div className="pdvm-theme-editor__grid">{tokens.map(([name, spec]) => renderToken(group, name, spec))}</div>
              </details>
            ))}
          </section>
        </>
      ) : null}

      <PdvmDialogModal
        open={confirmClear}
        kind="confirm"
        title="Anpassungen entfernen"
        message={`Alle Anpassungen im Modus „${MODE_LABEL[mode]}“ aus dem Entwurf entfernen? Gespeichert wird erst mit „Speichern“.`}
        confirmLabel="Entfernen"
        cancelLabel="Abbrechen"
        onConfirm={clearMode}
        onCancel={() => setConfirmClear(false)}
      />
    </div>
  )
}
