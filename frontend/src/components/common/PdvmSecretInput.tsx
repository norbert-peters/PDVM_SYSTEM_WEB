import { useCallback, useEffect, useState } from 'react'
import { credentialsAPI, type CredentialInfo } from '../../api/client'

function newCredentialName(prefix: string): string {
  const id = typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID().slice(0, 8) : String(Date.now())
  return `${prefix}-${id}`
}

function errorText(err: any): string {
  const status = err?.response?.status
  if (status === 403) return 'Keine Berechtigung (Admin-Recht erforderlich)'
  const detail = err?.response?.data?.detail
  return typeof detail === 'string' ? detail : err?.message || 'Fehler'
}

/**
 * Write-only Eingabe fuer Passwoerter (Control-Typ `password`).
 * Der Feldwert ist der Name des Zugangsdatensatzes (Verweis, kein Geheimnis). Das Passwort geht direkt an
 * PUT /api/credentials/{name}, wird nie angezeigt und nie als Feldwert gehalten.
 */
export function PdvmSecretInput(props: {
  id?: string
  name: string
  namePrefix?: string
  disabled?: boolean
  onNameChange: (name: string) => void
}) {
  const { name, namePrefix = 'cred', disabled, onNameChange } = props
  const [info, setInfo] = useState<CredentialInfo | null>(null)
  const [secret, setSecret] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!name) {
      setInfo(null)
      return
    }
    try {
      setInfo(await credentialsAPI.getInfo(name))
      setError(null)
    } catch (err) {
      setInfo(null)
      setError(errorText(err))
    }
  }, [name])

  useEffect(() => {
    void load()
  }, [load])

  const save = async () => {
    if (!secret) return
    const target = name || newCredentialName(namePrefix)
    try {
      setBusy(true)
      setError(null)
      const saved = await credentialsAPI.setPassword(target, secret)
      setInfo(saved)
      setSecret('')
      if (target !== name) onNameChange(target)
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  const fromEnv = info?.source === 'env'
  const status = fromEnv
    ? 'Kommt aus der Konfiguration (nicht änderbar)'
    : info?.exists
      ? 'Passwort gesetzt'
      : 'Noch kein Passwort gesetzt'

  return (
    <div style={{ display: 'grid', gap: 6, width: '100%' }}>
      <div style={{ fontSize: 12, opacity: 0.8 }}>{status}</div>
      <div style={{ display: 'flex', gap: 8 }}>
        <input
          id={props.id}
          className="pdvm-pic__input"
          type="password"
          autoComplete="new-password"
          value={secret}
          placeholder={info?.exists ? 'Neues Passwort eingeben, um es zu ersetzen' : 'Passwort eingeben'}
          disabled={disabled || busy || fromEnv}
          onChange={(e) => setSecret(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              void save()
            }
          }}
        />
        <button type="button" className="pdvm-pic__openBtn" disabled={disabled || busy || fromEnv || !secret} onClick={() => void save()}>
          {busy ? 'Speichert…' : 'Speichern'}
        </button>
      </div>
      {error ? <div style={{ fontSize: 12, color: 'var(--color-error-text)' }}>{error}</div> : null}
    </div>
  )
}
