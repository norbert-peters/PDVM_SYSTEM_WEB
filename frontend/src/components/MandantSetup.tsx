import { useState, useEffect } from 'react'
import { apiClient } from '../api/client'

interface MandantSetupProps {
  token: string
  onSuccess: () => void
  onCancel: () => void
}

interface PendingMandant {
  id: string
  name: string
  database: string
  description: string
  reason: string
}

export default function MandantSetup({ token, onSuccess, onCancel }: MandantSetupProps) {
  const [pendingMandanten, setPendingMandanten] = useState<PendingMandant[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedMandant, setSelectedMandant] = useState<string | null>(null)
  const [building, setBuilding] = useState(false)
  const [buildProgress, setBuildProgress] = useState('')

  useEffect(() => {
    loadPendingMandanten()
  }, [])

  async function loadPendingMandanten() {
    try {
      setLoading(true)
      const response = await apiClient.get('/mandanten/pending-setup', {
        headers: { Authorization: `Bearer ${token}` }
      })
      setPendingMandanten(response.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Laden der Mandanten')
    } finally {
      setLoading(false)
    }
  }

  async function buildMandant() {
    if (!selectedMandant) return

    try {
      setBuilding(true)
      setBuildProgress('Datenbank wird erstellt...')
      
      const response = await apiClient.post(
        `/mandanten/setup/${selectedMandant}`,
        {},
        { headers: { Authorization: `Bearer ${token}` } }
      )
      
      setBuildProgress(`Erfolgreich! ${response.data.sys_tables_count} SYS_TABLES und ${response.data.features_count} FEATURES angelegt.`)
      
      setTimeout(() => {
        onSuccess()
      }, 2000)
      
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Aufbau der Datenbank')
      setBuilding(false)
    }
  }

  return (
    <div style={styles.container}>
      <h2 style={styles.title}>Mandant aufbauen</h2>
      <p style={styles.subtitle}>
        Wählen Sie einen Mandanten aus, dessen Datenbank Sie einrichten möchten.
      </p>

      {loading && <p style={styles.loading}>Mandanten werden geladen...</p>}

      {error && (
        <div style={styles.error}>
          {error}
        </div>
      )}

      {!loading && !error && pendingMandanten.length === 0 && (
        <div style={styles.success}>
          ✓ Alle Mandanten sind bereits eingerichtet!
        </div>
      )}

      {!loading && !error && pendingMandanten.length > 0 && (
        <>
          <div style={styles.list}>
            {pendingMandanten.map((mandant) => (
              <div
                key={mandant.id}
                style={{
                  ...styles.mandantCard,
                  ...(selectedMandant === mandant.id ? styles.mandantCardSelected : {})
                }}
                onClick={() => !building && setSelectedMandant(mandant.id)}
              >
                <div style={styles.mandantHeader}>
                  <input
                    type="radio"
                    checked={selectedMandant === mandant.id}
                    onChange={() => !building && setSelectedMandant(mandant.id)}
                    disabled={building}
                    style={styles.radio}
                  />
                  <div style={styles.mandantInfo}>
                    <strong style={styles.mandantName}>{mandant.name}</strong>
                    <div style={styles.mandantDetails}>
                      <span style={styles.mandantDatabase}>Datenbank: {mandant.database}</span>
                      {mandant.description && (
                        <span style={styles.mandantDescription}>{mandant.description}</span>
                      )}
                    </div>
                    <span style={styles.mandantReason}>{mandant.reason}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {buildProgress && (
            <div style={styles.progress}>
              {buildProgress}
            </div>
          )}

          <div style={styles.buttonGroup}>
            <button
              onClick={onCancel}
              style={styles.buttonCancel}
              disabled={building}
            >
              Abbrechen
            </button>
            <button
              onClick={buildMandant}
              style={{
                ...styles.buttonBuild,
                ...((!selectedMandant || building) ? styles.buttonBuildDisabled : {})
              }}
              disabled={!selectedMandant || building}
            >
              {building ? 'Wird aufgebaut...' : 'Datenbank aufbauen'}
            </button>
          </div>
        </>
      )}
    </div>
  )
}

const styles = {
  container: {
    padding: '2rem',
    maxWidth: '800px',
    margin: '0 auto',
  },
  title: {
    fontSize: '1.8rem',
    fontWeight: 'bold' as const,
    marginBottom: '0.5rem',
    color: '#333',
  },
  subtitle: {
    color: '#666',
    marginBottom: '2rem',
  },
  loading: {
    textAlign: 'center' as const,
    color: '#666',
    padding: '2rem',
  },
  error: {
    backgroundColor: '#ffebee',
    color: '#c62828',
    padding: '1rem',
    borderRadius: '4px',
    marginBottom: '1rem',
  },
  success: {
    backgroundColor: '#e8f5e9',
    color: '#2e7d32',
    padding: '2rem',
    borderRadius: '4px',
    textAlign: 'center' as const,
    fontSize: '1.2rem',
  },
  list: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '1rem',
    marginBottom: '2rem',
  },
  mandantCard: {
    border: '2px solid #ddd',
    borderRadius: '8px',
    padding: '1rem',
    cursor: 'pointer',
    transition: 'all 0.2s',
    backgroundColor: 'white',
  },
  mandantCardSelected: {
    borderColor: '#007bff',
    backgroundColor: '#f0f8ff',
  },
  mandantHeader: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '1rem',
  },
  radio: {
    marginTop: '0.25rem',
    cursor: 'pointer',
  },
  mandantInfo: {
    flex: 1,
  },
  mandantName: {
    fontSize: '1.1rem',
    color: '#333',
    display: 'block',
    marginBottom: '0.5rem',
  },
  mandantDetails: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '0.25rem',
    marginBottom: '0.5rem',
  },
  mandantDatabase: {
    fontSize: '0.9rem',
    color: '#007bff',
    fontFamily: 'monospace',
  },
  mandantDescription: {
    fontSize: '0.9rem',
    color: '#666',
  },
  mandantReason: {
    fontSize: '0.85rem',
    color: '#ff6b6b',
    fontStyle: 'italic' as const,
  },
  progress: {
    backgroundColor: '#fff3cd',
    color: '#856404',
    padding: '1rem',
    borderRadius: '4px',
    marginBottom: '1rem',
    textAlign: 'center' as const,
  },
  buttonGroup: {
    display: 'flex',
    gap: '1rem',
    justifyContent: 'flex-end',
  },
  buttonCancel: {
    padding: '0.75rem 1.5rem',
    backgroundColor: '#6c757d',
    color: 'white',
    border: 'none',
    borderRadius: '4px',
    fontSize: '1rem',
    cursor: 'pointer',
    transition: 'background-color 0.2s',
  },
  buttonBuild: {
    padding: '0.75rem 1.5rem',
    backgroundColor: '#007bff',
    color: 'white',
    border: 'none',
    borderRadius: '4px',
    fontSize: '1rem',
    cursor: 'pointer',
    transition: 'background-color 0.2s',
  },
  buttonBuildDisabled: {
    backgroundColor: '#ccc',
    cursor: 'not-allowed',
  },
}
