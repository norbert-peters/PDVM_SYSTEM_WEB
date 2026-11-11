import { useState, FormEvent } from 'react'
import { authAPI, type LoginResponse } from '../api/client'
import { PdvmDialogModal } from './common/PdvmDialogModal'

interface LoginProps {
  onLogin: (token: string, autoSelectMandantId?: string) => void
}

export default function Login({ onLogin }: LoginProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [pwChangeOpen, setPwChangeOpen] = useState(false)
  const [pwChangeError, setPwChangeError] = useState<string | null>(null)
  const [pwChangeBusy, setPwChangeBusy] = useState(false)
  const [pendingLogin, setPendingLogin] = useState<LoginResponse | null>(null)
  const [pendingToken, setPendingToken] = useState<string | null>(null)
  const [forgotOpen, setForgotOpen] = useState(false)
  const [forgotBusy, setForgotBusy] = useState(false)
  const [forgotError, setForgotError] = useState<string | null>(null)
  const [forgotSuccess, setForgotSuccess] = useState<string | null>(null)

  const demoLogin = {
    username: 'admin@example.com',
    password: 'Pdvm_@dmin_2026',
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

  const performLogin = async (username: string, pass: string) => {
    setError('')
    setForgotSuccess(null)
    setLoading(true)

    try {
      const response = await authAPI.login({ username, password: pass })

      if (response.password_change_required) {
        setPendingLogin(response)
        setPendingToken(response.access_token)
        setPwChangeError(null)
        setPwChangeOpen(true)
        return
      }

      persistLoginData(response)
      onLogin(response.access_token)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    await performLogin(email, password)
  }

  return (
    <div style={styles.container}>
      <PdvmDialogModal
        open={pwChangeOpen}
        kind="form"
        title="Passwort ändern"
        message="Sie müssen ein neues Passwort vergeben."
        fields={[
          {
            name: 'new_password',
            label: 'Neues Passwort',
            type: 'password',
            required: true,
            minLength: 12,
            autoFocus: true,
          },
          {
            name: 'confirm_password',
            label: 'Passwort bestätigen',
            type: 'password',
            required: true,
            minLength: 12,
          },
        ]}
        confirmLabel="Speichern"
        cancelLabel="Abbrechen"
        busy={pwChangeBusy}
        error={pwChangeError}
        onCancel={() => {
          setPwChangeOpen(false)
          setPwChangeError(null)
          setPendingLogin(null)
          setPendingToken(null)
        }}
        onConfirm={async (values) => {
          if (!pendingToken || !pendingLogin) return
          setPwChangeBusy(true)
          setPwChangeError(null)
          try {
            await authAPI.changePassword(
              {
                new_password: String(values?.new_password || ''),
                confirm_password: String(values?.confirm_password || ''),
              },
              pendingToken
            )

            persistLoginData(pendingLogin)
            onLogin(pendingToken)
            setPwChangeOpen(false)
            setPendingLogin(null)
            setPendingToken(null)
          } catch (err: any) {
            setPwChangeError(err.response?.data?.detail || err.message || 'Passwortänderung fehlgeschlagen')
          } finally {
            setPwChangeBusy(false)
          }
        }}
      />
      <PdvmDialogModal
        open={forgotOpen}
        kind="form"
        title="Passwort vergessen"
        message="Bitte geben Sie Ihre E-Mail-Adresse ein."
        fields={[
          {
            name: 'email',
            label: 'E-Mail-Adresse',
            type: 'text',
            required: true,
            autoFocus: true,
          },
        ]}
        confirmLabel="Senden"
        cancelLabel="Abbrechen"
        busy={forgotBusy}
        error={forgotError}
        onCancel={() => {
          setForgotOpen(false)
          setForgotError(null)
        }}
        onConfirm={async (values) => {
          setForgotBusy(true)
          setForgotError(null)
          try {
            const targetEmail = String(values?.email || '').trim()
            const result = await authAPI.forgotPassword({ email: targetEmail })
            if (!result.email_sent) {
              throw new Error(result.email_error || 'E-Mail konnte nicht gesendet werden')
            }
            setForgotSuccess('Ein maschinelles Passwort wurde versendet.')
            setForgotOpen(false)
          } catch (err: any) {
            setForgotError(err.response?.data?.detail || err.message || 'E-Mail konnte nicht gesendet werden')
          } finally {
            setForgotBusy(false)
          }
        }}
      />
      <div style={styles.card}>
        <h1 style={styles.title}>PDVM System</h1>
        <p style={styles.subtitle}>Business Management Platform</p>
        
        <form onSubmit={handleSubmit} style={styles.form}>
          <div style={styles.field}>
            <label style={styles.label}>Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={styles.input}
              required
            />
          </div>
          
          <div style={styles.field}>
            <label style={styles.label}>Password</label>
            <div style={styles.inputWrap}>
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                style={styles.input}
                required
              />
              <button
                type="button"
                onClick={() => setShowPassword((prev) => !prev)}
                style={styles.inputToggle}
                aria-label={showPassword ? 'Passwort verbergen' : 'Passwort anzeigen'}
                title={showPassword ? 'Passwort verbergen' : 'Passwort anzeigen'}
              >
                {showPassword ? '🙈' : '👁️'}
              </button>
            </div>
          </div>

          <button
            type="button"
            onClick={() => setForgotOpen(true)}
            style={styles.linkButton}
          >
            Passwort vergessen?
          </button>

          {error && <div style={styles.error}>{error}</div>}
          {forgotSuccess && <div style={styles.success}>{forgotSuccess}</div>}
          
          <button
            type="submit"
            disabled={loading}
            style={styles.button}
          >
            {loading ? 'Logging in...' : 'Login'}
          </button>
          <button
            type="button"
            disabled={loading}
            style={styles.demoButton}
            onClick={async () => {
              setEmail(demoLogin.username)
              setPassword(demoLogin.password)
              await performLogin(demoLogin.username, demoLogin.password)
            }}
          >
            DEMO - Login
          </button>
        </form>
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
  form: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '1rem',
  },
  field: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '0.5rem',
  },
  label: {
    fontSize: '0.9rem',
    fontWeight: '500',
    color: 'var(--color-text-primary)',
  },
  input: {
    padding: '0.75rem',
    fontSize: '1rem',
    border: '1px solid var(--color-border-medium)',
    borderRadius: '4px',
    outline: 'none',
    width: '100%',
  },
  inputWrap: {
    position: 'relative' as const,
    display: 'flex',
    alignItems: 'center',
  },
  inputToggle: {
    position: 'absolute' as const,
    right: '10px',
    top: '50%',
    transform: 'translateY(-50%)',
    border: 'none',
    background: 'transparent',
    cursor: 'pointer',
    fontSize: '1rem',
    lineHeight: 1,
    padding: 0,
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
  demoButton: {
    padding: '0.75rem',
    fontSize: '1rem',
    fontWeight: '500',
    color: 'var(--color-text-on-primary)',
    backgroundColor: 'transparent',
    border: '1px solid var(--color-primary-500)',
    borderRadius: '4px',
    cursor: 'pointer',
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
