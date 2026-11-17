import { useState, type FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { authAPI, publicAPI, type FrameRuntime, type FrameRuntimeField, type LoginFramesResponse, type LoginResponse } from '../api/client'
import { PdvmFrameForm } from './frames/PdvmFrameForm'
import { uiText } from '../i18n/uiTexts'
import { preferredLanguage } from '../i18n/uiLanguage'

interface LoginProps {
  onLogin: (token: string, autoSelectMandantId?: string) => void
}

type View = 'login' | 'forgot' | 'change'
type LoginFrames = LoginFramesResponse['frames']

const FRAMES_STALE_MS = 5 * 60 * 1000

function fallbackField(gruppe: string, feld: string, type: string, label: string, configs: Record<string, any>, order: number): FrameRuntimeField {
  return {
    key: `${gruppe}.${feld}`, control_uid: null, tab: 1, display_order: order, type, label, tooltip: null, gruppe, feld,
    source_path: 'root', save_path: null, table: null, read_only: false, immutable: false, immutable_after: null,
    default: null, configs, options: [], resolution_warning: null,
  }
}

function fallbackFrame(name: string, fields: FrameRuntimeField[]): FrameRuntime {
  return { uid: name, name, root: { FRAME_TYPE: 'public_form' }, tabs: [{ index: 1, head: name }], fields }
}

/**
 * Notfall-Rueckfall: Ist der oeffentliche Frame-Endpunkt nicht erreichbar oder ein Frame ungueltig, bleibt die Anmeldung
 * moeglich (ein beschaedigter Frame darf niemanden aussperren, der ihn reparieren muesste). Gleiche Felder wie die Seed-Frames.
 */
function buildFallbackFrames(): LoginFrames {
  const email = { input: { name: 'username', autocomplete: 'username' } }
  const newPassword = { input: { autocomplete: 'new-password' }, password_input: { reveal: true, min_length: 12 } }
  return {
    login: fallbackFrame('Login', [
      fallbackField('LOGIN', 'EMAIL', 'string', uiText('login.fallback.email'), email, 10),
      fallbackField('LOGIN', 'PASSWORD', 'password_input', uiText('login.fallback.password'),
        { input: { name: 'password', autocomplete: 'current-password' }, password_input: { reveal: true } }, 20),
    ]),
    forgot: fallbackFrame('Passwort vergessen', [
      fallbackField('FORGOT', 'BENUTZER', 'string', uiText('login.fallback.benutzer'), email, 10),
      fallbackField('FORGOT', 'EMAIL', 'string', uiText('login.fallback.storedEmail'), { input: { name: 'email', autocomplete: 'email' } }, 20),
    ]),
    change: fallbackFrame('Passwort ändern', [
      fallbackField('CHANGE', 'NEW_PASSWORD', 'password_input', uiText('login.fallback.password'), newPassword, 10),
      fallbackField('CHANGE', 'CONFIRM_PASSWORD', 'password_input', uiText('login.fallback.password'),
        { ...newPassword, password_input: { reveal: true, min_length: 12, confirm_with: 'NEW_PASSWORD' } }, 20),
    ]),
  }
}

// Passwoerter stehen nur im Formularzustand bis zum Absenden; Zugriff auf Felder der Gruppen LOGIN/FORGOT/CHANGE
function readValue(data: Record<string, any>, group: string, field: string): string {
  return String(data?.[group]?.[field] ?? '')
}

export default function Login({ onLogin }: LoginProps) {
  const [view, setView] = useState<View>('login')
  const [formData, setFormData] = useState<Record<string, any>>({})
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')
  const [busy, setBusy] = useState(false)
  const [pendingLogin, setPendingLogin] = useState<LoginResponse | null>(null)

  const language = preferredLanguage()
  const framesQuery = useQuery({
    queryKey: ['public', 'login-frames', language],
    queryFn: () => publicAPI.getLoginFrames(language),
    staleTime: FRAMES_STALE_MS,
    retry: false,
  })
  const frames: LoginFrames | null = framesQuery.data?.frames ?? (framesQuery.isError ? buildFallbackFrames() : null)

  const clearSecrets = () =>
    setFormData((prev) => ({
      ...prev,
      LOGIN: { ...prev.LOGIN, PASSWORD: '' },
      CHANGE: { ...prev.CHANGE, NEW_PASSWORD: '', CONFIRM_PASSWORD: '' },
    }))

  const switchView = (next: View) => {
    setError('')
    setInfo('')
    setView(next)
  }

  const persistLoginData = (response: LoginResponse) => {
    if (response.user_data) {
      localStorage.setItem(
        'user_data',
        JSON.stringify({
          uid: response.user_id,
          username: response.email,
          name: response.name,
          email: response.email,
          ...response.user_data,
        })
      )
    }
    if (response.mandanten) {
      localStorage.setItem('mandanten', JSON.stringify(response.mandanten))
    }
  }

  const handleLogin = async (e: FormEvent) => {
    e.preventDefault()
    const username = readValue(formData, 'LOGIN', 'EMAIL').trim()
    const password = readValue(formData, 'LOGIN', 'PASSWORD')
    if (!username || !password) return
    setError('')
    setInfo('')
    setBusy(true)
    try {
      const response = await authAPI.login({ username, password })
      if (response.password_change_required) {
        setPendingLogin(response)
        clearSecrets()
        switchView('change')
        return
      }
      persistLoginData(response)
      clearSecrets()
      onLogin(response.access_token)
    } catch (err: any) {
      setError(err.response?.data?.detail || uiText('login.failed'))
      clearSecrets()
    } finally {
      setBusy(false)
    }
  }

  const sendReset = async (benutzer: string, email: string) => {
    setError('')
    setInfo('')
    setBusy(true)
    try {
      const result = await authAPI.forgotPassword({ benutzer, email })
      if (!result.email_sent) {
        throw new Error(result.email_error || uiText('login.forgot.failed'))
      }
      setFormData((prev) => ({ ...prev, FORGOT: { BENUTZER: '', EMAIL: '' } }))
      switchView('login')
      setInfo(uiText('login.forgot.sent'))
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || uiText('login.forgot.failed'))
    } finally {
      setBusy(false)
    }
  }

  // Der Benutzer steht meist schon im Login-Formular und wird uebernommen; die hinterlegte E-Mail-Adresse wird abgefragt
  const startForgot = () => {
    const known = readValue(formData, 'LOGIN', 'EMAIL').trim()
    if (known && !readValue(formData, 'FORGOT', 'BENUTZER').trim()) {
      setFormData((prev) => ({ ...prev, FORGOT: { ...prev.FORGOT, BENUTZER: known } }))
    }
    switchView('forgot')
  }

  const handleForgot = async (e: FormEvent) => {
    e.preventDefault()
    const benutzer = readValue(formData, 'FORGOT', 'BENUTZER').trim()
    const email = readValue(formData, 'FORGOT', 'EMAIL').trim()
    if (!benutzer || !email) return
    await sendReset(benutzer, email)
  }

  const handleChange = async (e: FormEvent) => {
    e.preventDefault()
    if (!pendingLogin) return
    const newPassword = readValue(formData, 'CHANGE', 'NEW_PASSWORD')
    const confirmPassword = readValue(formData, 'CHANGE', 'CONFIRM_PASSWORD')
    if (newPassword !== confirmPassword) {
      setError(uiText('form.passwordMismatch'))
      return
    }
    setError('')
    setBusy(true)
    try {
      const changed = await authAPI.changePassword({ new_password: newPassword, confirm_password: confirmPassword }, pendingLogin.access_token)
      persistLoginData(pendingLogin)
      clearSecrets()
      // Der Server ersetzt das eingeschränkte Login-Token durch ein vollwertiges (F2)
      onLogin(changed.access_token || pendingLogin.access_token)
      setPendingLogin(null)
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || uiText('login.change.failed'))
    } finally {
      setBusy(false)
    }
  }

  const cancelChange = () => {
    setPendingLogin(null)
    clearSecrets()
    switchView('login')
  }

  const messages = (
    <>
      {error && <div style={styles.error} role="alert">{error}</div>}
      {info && <div style={styles.success}>{info}</div>}
    </>
  )

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <h1 style={styles.title}>{uiText('login.title')}</h1>
        <p style={styles.subtitle}>{uiText('login.subtitle')}</p>

        {!frames ? <p style={styles.loading}>{uiText('login.loading')}</p> : null}

        {frames && view === 'login' ? (
          <form onSubmit={handleLogin} style={styles.form}>
            <PdvmFrameForm frame={frames.login} data={formData} onChange={setFormData} disabled={busy} />
            <button type="button" onClick={startForgot} style={styles.linkButton}>
              {uiText('login.forgotLink')}
            </button>
            {messages}
            <button type="submit" disabled={busy} style={styles.button}>
              {busy ? uiText('login.submitBusy') : uiText('login.submit')}
            </button>
          </form>
        ) : null}

        {frames && view === 'forgot' ? (
          <form onSubmit={handleForgot} style={styles.form}>
            <h2 style={styles.heading}>{uiText('login.forgot.title')}</h2>
            <p style={styles.hint}>{uiText('login.forgot.hint')}</p>
            <PdvmFrameForm frame={frames.forgot} data={formData} onChange={setFormData} disabled={busy} />
            {messages}
            <button type="submit" disabled={busy} style={styles.button}>{uiText('login.forgot.submit')}</button>
            <button type="button" onClick={() => switchView('login')} style={styles.linkButton}>{uiText('login.back')}</button>
          </form>
        ) : null}

        {frames && view === 'change' ? (
          <form onSubmit={handleChange} style={styles.form}>
            <h2 style={styles.heading}>{uiText('login.change.title')}</h2>
            <p style={styles.hint}>{uiText('login.change.hint')}</p>
            <PdvmFrameForm frame={frames.change} data={formData} onChange={setFormData} disabled={busy} />
            {messages}
            <button type="submit" disabled={busy} style={styles.button}>{uiText('login.change.submit')}</button>
            <button type="button" onClick={cancelChange} style={styles.linkButton}>{uiText('action.cancel')}</button>
          </form>
        ) : null}
      </div>
    </div>
  )
}

const styles = {
  container: {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    minHeight: '100vh',
    backgroundColor: 'var(--color-background-secondary)',
  },
  card: {
    backgroundColor: 'var(--color-background-primary)',
    padding: '2rem',
    borderRadius: '8px',
    boxShadow: 'var(--shadow-md)',
    width: '100%',
    maxWidth: '400px',
  },
  title: {
    fontSize: '2rem',
    fontWeight: 'bold',
    textAlign: 'center' as const,
    marginBottom: '0.5rem',
    color: 'var(--color-text-primary)',
  },
  subtitle: {
    textAlign: 'center' as const,
    color: 'var(--color-text-secondary)',
    marginBottom: '2rem',
  },
  heading: {
    fontSize: '1.2rem',
    fontWeight: 600,
    color: 'var(--color-text-primary)',
    margin: 0,
  },
  hint: {
    color: 'var(--color-text-secondary)',
    fontSize: '0.9rem',
    margin: 0,
  },
  loading: {
    textAlign: 'center' as const,
    color: 'var(--color-text-secondary)',
  },
  form: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '1rem',
  },
  linkButton: {
    background: 'none',
    border: 'none',
    padding: 0,
    color: 'var(--color-text-on-primary)',
    cursor: 'pointer',
    textAlign: 'left' as const,
    fontSize: '0.9rem',
  },
  button: {
    padding: '0.75rem',
    fontSize: '1rem',
    fontWeight: '500',
    color: 'var(--color-text-inverse)',
    backgroundColor: 'var(--color-primary-500)',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
    marginTop: '0.5rem',
  },
  error: {
    padding: '0.75rem',
    backgroundColor: 'var(--color-error-bg)',
    color: 'var(--color-error-text)',
    borderRadius: '4px',
    fontSize: '0.9rem',
  },
  success: {
    padding: '0.75rem',
    backgroundColor: 'var(--color-success-bg)',
    color: 'var(--color-success-text)',
    borderRadius: '4px',
    fontSize: '0.9rem',
  },
}
