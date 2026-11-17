import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { framesAPI, mandantenAPI, type MandantCreateResult } from '../api/client'
import { useAuth } from '../contexts/AuthContext'
import { PdvmDialogModal } from './common/PdvmDialogModal'
import { PdvmFrameForm, type FrameFormError } from './frames/PdvmFrameForm'

const FRAME_STALE_MS = 5 * 60 * 1000

function resultMessage(result: MandantCreateResult): { text: string; relogin: boolean } {
  const parts = [`Der Mandant „${result.name}“ wurde gespeichert.`]
  if (result.database.status === 'created') parts.push(`Die Datenbank ${result.database.name || ''} wurde eingerichtet.`.replace('  ', ' '))
  else if (result.database.status === 'failed') {
    parts.push(`Die Datenbank konnte nicht eingerichtet werden: ${result.database.message}`)
    parts.push('Sie können den Schritt unter „Mandanten bearbeiten“ mit „Datenbank aufbauen“ wiederholen.')
  }
  if (!result.access_granted && result.access_error) parts.push(`Die Zuweisung an Ihren Benutzer ist fehlgeschlagen: ${result.access_error}`)
  const relogin = result.access_granted && result.database.status !== 'failed'
  if (relogin) parts.push('Bitte melden Sie sich neu an, damit der Mandant in der Auswahl erscheint.')
  return { text: parts.join('\n'), relogin }
}

// Die Eingabemaske ist das Frame (sys_framedaten) aus dem Template-Endpunkt; hier steht kein Feld und kein Label.
// Seite im AppLayout (Menüpunkt „Neuer Mandant“, Handler go_mandant_create); nur Superadmin, das Backend prüft ebenfalls.
export default function MandantCreate() {
  const navigate = useNavigate()
  const { currentUser, logout } = useAuth()
  const [formData, setFormData] = useState<Record<string, any> | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FrameFormError[]>([])
  const [result, setResult] = useState<MandantCreateResult | null>(null)
  const allowed = !!currentUser?.isSuperadmin

  const templateQuery = useQuery({
    queryKey: ['mandant-template'],
    queryFn: () => mandantenAPI.getTemplate(),
    staleTime: FRAME_STALE_MS,
    enabled: allowed,
  })
  const frameGuid = templateQuery.data?.frame_guid
  const frameQuery = useQuery({
    queryKey: ['frame-runtime', frameGuid],
    queryFn: () => framesAPI.getRuntime(frameGuid as string),
    enabled: !!frameGuid,
    staleTime: FRAME_STALE_MS,
  })

  const data = formData ?? templateQuery.data?.template ?? null
  const loadError = templateQuery.error || frameQuery.error
  const loadMessage = loadError
    ? (loadError as any)?.response?.data?.detail || (loadError as Error).message || 'Maske konnte nicht geladen werden'
    : ''

  async function handleSave() {
    if (!data) return
    try {
      setSaving(true)
      setError('')
      setFieldErrors([])
      setResult(await mandantenAPI.create(data))
    } catch (err: any) {
      const detail = err.response?.data?.detail
      if (err.response?.status === 422 && Array.isArray(detail?.errors)) {
        setFieldErrors(detail.errors)
        setError('Bitte die markierten Angaben prüfen')
      } else {
        setError(typeof detail === 'string' ? detail : 'Fehler beim Anlegen des Mandanten')
      }
    } finally {
      setSaving(false)
    }
  }

  const outcome = result ? resultMessage(result) : null

  if (!allowed) {
    return (
      <div style={styles.container}>
        <div style={styles.card}>
          <h1 style={styles.title}>Neuen Mandanten anlegen</h1>
          <div style={styles.error}>Für diese Funktion ist die Rolle „superadmin“ erforderlich.</div>
        </div>
      </div>
    )
  }

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <h1 style={styles.title}>Neuen Mandanten anlegen</h1>

        {error || loadMessage ? <div style={styles.error}>{error || loadMessage}</div> : null}
        {!loadMessage && (templateQuery.isLoading || frameQuery.isLoading) ? <div style={styles.loading}>Lade Maske...</div> : null}

        {frameQuery.data && data ? (
          <PdvmFrameForm
            frame={frameQuery.data}
            data={data}
            onChange={setFormData}
            errors={fieldErrors}
            disabled={saving || !!result}
          />
        ) : null}

        <div style={styles.buttons}>
          <button type="button" onClick={() => navigate('/menu-home')} style={styles.cancelButton} disabled={saving}>
            Abbrechen
          </button>
          <button type="button" onClick={handleSave} style={styles.submitButton} disabled={saving || !!result || !frameQuery.data}>
            {saving ? 'Mandant wird angelegt...' : 'Mandant anlegen'}
          </button>
        </div>
      </div>

      <PdvmDialogModal
        open={!!outcome}
        kind="info"
        title={result?.database.status === 'failed' ? 'Mandant teilweise angelegt' : 'Mandant angelegt'}
        message={<div style={{ whiteSpace: 'pre-line' }}>{outcome?.text}</div>}
        confirmLabel={outcome?.relogin ? 'Zur Anmeldung' : 'Schließen'}
        onConfirm={() => {
          const relogin = outcome?.relogin
          setResult(null)
          if (relogin) logout()
          else navigate('/menu-home')
        }}
        onCancel={() => {
          const relogin = outcome?.relogin
          setResult(null)
          if (relogin) logout()
          else navigate('/menu-home')
        }}
      />
    </div>
  )
}

const styles = {
  container: {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'flex-start',
    backgroundColor: 'var(--color-background-secondary)',
    padding: '1.5rem',
    overflowY: 'auto' as const,
  },
  card: {
    backgroundColor: 'var(--color-background-primary)',
    padding: '2rem',
    borderRadius: '8px',
    boxShadow: 'var(--shadow-md)',
    width: '100%',
    maxWidth: '900px',
  },
  title: {
    fontSize: '1.8rem',
    fontWeight: 'bold',
    marginBottom: '1.5rem',
    color: 'var(--color-text-primary)',
  },
  loading: {
    textAlign: 'center' as const,
    color: 'var(--color-text-secondary)',
  },
  error: {
    backgroundColor: 'var(--color-error-bg)',
    color: 'var(--color-error-text)',
    padding: '0.75rem',
    borderRadius: '4px',
    marginBottom: '1rem',
  },
  buttons: {
    display: 'flex',
    gap: '1rem',
    marginTop: '2rem',
    justifyContent: 'flex-end',
  },
  cancelButton: {
    padding: '0.75rem 1.5rem',
    backgroundColor: 'var(--color-background-primary)',
    color: 'var(--color-text-primary)',
    border: '1px solid var(--color-border-dark)',
    borderRadius: '4px',
    fontSize: '1rem',
    cursor: 'pointer',
  },
  submitButton: {
    padding: '0.75rem 1.5rem',
    backgroundColor: 'var(--color-primary-500)',
    color: 'var(--color-text-inverse)',
    border: 'none',
    borderRadius: '4px',
    fontSize: '1rem',
    cursor: 'pointer',
  },
}
