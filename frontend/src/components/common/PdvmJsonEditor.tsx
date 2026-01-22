import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'
import JSONEditor from 'jsoneditor'
import 'jsoneditor/dist/jsoneditor.css'
import './PdvmJsonEditor.css'

export type PdvmJsonEditorMode = 'text' | 'tree'

export interface PdvmJsonEditorHandle {
  getJson: () => any
  setJson: (value: any) => void
  setMode: (mode: PdvmJsonEditorMode) => void
  getMode: () => PdvmJsonEditorMode
  search: (query: string) => number
  expandAll: () => void
  collapseAll: () => void
  sort: () => void
  format: () => void
}

export interface PdvmJsonEditorProps {
  className?: string
  initialMode?: PdvmJsonEditorMode
  initialJson?: any
  readOnly?: boolean
  onDirty?: () => void
  onFocus?: () => void
  onValidationMessage?: (message: string | null) => void
}

function translateMenuLabel(label: string): string {
  const l = String(label || '').trim().toLowerCase()
  if (!l) return label
  if (l === 'insert') return 'Einfügen'
  if (l === 'append') return 'Anhängen'
  if (l === 'duplicate') return 'Duplizieren'
  if (l === 'remove') return 'Entfernen'
  if (l === 'sort') return 'Sortieren'
  if (l === 'extract') return 'Extrahieren'
  if (l === 'transform') return 'Transformieren'
  return label
}

function isAllowedMenuItemText(label: string): boolean {
  const l = String(label || '').trim().toLowerCase()
  // minimal required set: editing + sort
  return ['insert', 'append', 'duplicate', 'remove', 'sort'].includes(l)
}

export const PdvmJsonEditor = forwardRef<PdvmJsonEditorHandle, PdvmJsonEditorProps>(function PdvmJsonEditor(
  { className, initialMode = 'text', initialJson, readOnly = false, onDirty, onFocus, onValidationMessage },
  ref,
) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const editorRef = useRef<any>(null)
  const pendingJsonRef = useRef<any | null>(null)
  const pendingModeRef = useRef<PdvmJsonEditorMode | null>(null)
  const lastAppliedJsonRef = useRef<any | null>(null)
  const suppressDirtyRef = useRef(false)

  const toJsonEditorMode = (mode: PdvmJsonEditorMode): 'code' | 'tree' => {
    // JSONEditor: 'text' is plain textarea; 'code' uses Ace and supports navigation/highlight.
    return mode === 'tree' ? 'tree' : 'code'
  }

  const fromJsonEditorMode = (mode: string | undefined | null): PdvmJsonEditorMode => {
    const m = String(mode || '').toLowerCase()
    return m === 'tree' ? 'tree' : 'text'
  }

  // Keep callback props stable for the JSONEditor instance.
  const onDirtyRef = useRef<typeof onDirty | undefined>(onDirty)
  const onFocusRef = useRef<typeof onFocus | undefined>(onFocus)
  const onValidationMessageRef = useRef<typeof onValidationMessage | undefined>(onValidationMessage)

  const getAceEditor = (): any | null => {
    try {
      // When JSONEditor runs in 'code' mode, it exposes an Ace editor instance on `aceEditor`.
      const ace = editorRef.current?.aceEditor
      if (ace) return ace
      // Fallback: some builds attach the editor instance on the DOM element.
      const el = containerRef.current?.querySelector?.('.ace_editor') as any
      return el?.env?.editor || el?.editor || null
    } catch {
      return null
    }
  }

  useEffect(() => {
    onDirtyRef.current = onDirty
  }, [onDirty])

  useEffect(() => {
    onFocusRef.current = onFocus
  }, [onFocus])

  useEffect(() => {
    onValidationMessageRef.current = onValidationMessage
  }, [onValidationMessage])

  useEffect(() => {
    if (!containerRef.current) return
    if (editorRef.current) return

    const focusHandler = () => {
      onFocusRef.current?.()
    }
    containerRef.current.addEventListener('focusin', focusHandler)

    const opts: any = {
      mode: toJsonEditorMode(initialMode),
      modes: ['code', 'tree'],
      mainMenuBar: false,
      navigationBar: false,
      statusBar: false,
      indentation: 2,
      onChange: () => {
        if (suppressDirtyRef.current) return
        onDirtyRef.current?.()
      },
      onValidationError: (errors: Array<any>) => {
        if (!errors || errors.length === 0) {
          onValidationMessageRef.current?.(null)
          return
        }
        const msg = String(errors[0]?.message || 'Ungültiges JSON')
        onValidationMessageRef.current?.(msg)
      },
      onCreateMenu: (items: Array<any>) => {
        const filtered = (items || []).filter((it) => isAllowedMenuItemText(it?.text))
        for (const it of filtered) {
          if (it && typeof it.text === 'string') {
            it.text = translateMenuLabel(it.text)
          }
        }
        return filtered
      },
    }
    if (readOnly) {
      opts.onEditable = () => false
    }

    const editor = new (JSONEditor as any)(containerRef.current, opts)
    editorRef.current = editor

    // Apply any pending operations that happened before the editor was ready.
    try {
      if (pendingModeRef.current) {
        editorRef.current?.setMode?.(toJsonEditorMode(pendingModeRef.current))
        pendingModeRef.current = null
      }
      if (pendingJsonRef.current !== null) {
        suppressDirtyRef.current = true
        editorRef.current?.set?.(pendingJsonRef.current)
        suppressDirtyRef.current = false
        pendingJsonRef.current = null
      } else if (initialJson !== undefined) {
        // First mount: initialize from prop
        suppressDirtyRef.current = true
        editorRef.current?.set?.(initialJson)
        suppressDirtyRef.current = false
        lastAppliedJsonRef.current = initialJson
      }
    } catch {
      // Best-effort
    }

    return () => {
      try {
        containerRef.current?.removeEventListener('focusin', focusHandler)
      } catch {
        // ignore
      }
      try {
        editorRef.current?.destroy?.()
      } catch {
        // ignore
      }
      editorRef.current = null
    }
  }, [initialMode, readOnly, initialJson])

  // If the component remounts (e.g. tab switch) or initialJson changes, ensure it's applied.
  useEffect(() => {
    if (initialJson === undefined) return
    if (lastAppliedJsonRef.current === initialJson) return
    lastAppliedJsonRef.current = initialJson

    // Use imperative setter (will queue until editor is ready)
    try {
      suppressDirtyRef.current = true
      if (!editorRef.current) {
        pendingJsonRef.current = initialJson
      } else {
        editorRef.current?.set?.(initialJson)
      }
    } finally {
      suppressDirtyRef.current = false
    }
  }, [initialJson])

  useImperativeHandle(
    ref,
    () => ({
      getJson: () => {
        return editorRef.current?.get?.()
      },
      setJson: (value: any) => {
        if (!editorRef.current) {
          pendingJsonRef.current = value
          return
        }
        editorRef.current?.set?.(value)
      },
      setMode: (mode: PdvmJsonEditorMode) => {
        if (!editorRef.current) {
          pendingModeRef.current = mode
          return
        }
        editorRef.current?.setMode?.(toJsonEditorMode(mode))
      },
      getMode: () => {
        return fromJsonEditorMode(editorRef.current?.getMode?.() || toJsonEditorMode(initialMode))
      },
      search: (query: string) => {
        const q = String(query || '').trim()
        if (!q) return 0
        try {
          const currentMode = fromJsonEditorMode(editorRef.current?.getMode?.() || toJsonEditorMode(initialMode))

          if (currentMode === 'text') {
            const ace = getAceEditor()
            if (!ace) return 0

            // Highlight all matches and jump to the first visible one.
            try {
              ace.findAll?.(q, {
                wrap: true,
                caseSensitive: false,
                wholeWord: false,
                regExp: false,
              })
            } catch {
              // ignore
            }

            try {
              ace.find?.(q, {
                wrap: true,
                caseSensitive: false,
                wholeWord: false,
                regExp: false,
              })
            } catch {
              // ignore
            }

            // Count hits (robust, independent of Ace internals)
            try {
              const text = String(ace.getValue?.() ?? editorRef.current?.getText?.() ?? '')
              if (!text) return 0
              const escaped = q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
              const re = new RegExp(escaped, 'gi')
              return (text.match(re) || []).length
            } catch {
              return 0
            }
          }

          // tree mode (and others): use jsoneditor's search if available
          const res = editorRef.current?.search?.(q)
          if (Array.isArray(res)) return res.length
          if (typeof res === 'number') return res
          return 0
        } catch {
          return 0
        }
      },
      expandAll: () => {
        editorRef.current?.expandAll?.()
      },
      collapseAll: () => {
        editorRef.current?.collapseAll?.()
      },
      sort: () => {
        editorRef.current?.sort?.()
      },
      format: () => {
        // stable formatting without relying on editor internals
        const json = editorRef.current?.get?.()
        editorRef.current?.set?.(json)
      },
    }),
    [initialMode],
  )

  return (
    <div className={`pdvm-jsoneditor ${className || ''}`.trim()}>
      <div className="pdvm-jsoneditor__frame">
        <div ref={containerRef} className="pdvm-jsoneditor__container" />
      </div>
    </div>
  )
})
