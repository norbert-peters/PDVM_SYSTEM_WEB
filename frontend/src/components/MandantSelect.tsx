import { useState, useEffect } from 'react'
import { mandantenAPI } from '../api/client'
import { useAuth } from '../contexts/AuthContext'
import type { Mandant as SelectedMandant } from '../contexts/AuthContext'

interface MandantSelectProps {
  onMandantSelected: (mandant: SelectedMandant) => void
  onCreateNew?: () => void
}

interface Mandant {
  id: string
  name: string
  is_allowed: boolean
  description: string
}

export default function MandantSelect({ onMandantSelected, onCreateNew }: MandantSelectProps) {
  const { token } = useAuth()
  const [mandanten, setMandanten] = useState<Mandant[]>([])
  const [loading, setLoading] = useState(true)

  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadMandanten()
  }, [])

  async function loadMandanten() {
    try {
      setLoading(true)
      
      // Try to load from cache first (cached during login)
      const cachedMandanten = localStorage.getItem('mandanten')
      let mandantenList: Mandant[] = []
      
      if (cachedMandanten) {
        mandantenList = JSON.parse(cachedMandanten)
      } else {
        // Fallback: Load from API if cache miss
        mandantenList = await mandantenAPI.getAll(token || '')
        localStorage.setItem('mandanten', JSON.stringify(mandantenList))
      }
      
      setMandanten(mandantenList)
      
      // AUTO-SELECT: Wenn nur 1 Mandant → automatisch auswählen
      if (mandantenList.length === 1) {
        console.log(`✅ Auto-Select: Nur 1 Mandant verfügbar (${mandantenList[0].name}), automatische Auswahl...`)
        await selectMandant(mandantenList[0].id)
        return
      }
      
      setLoading(false)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Mandanten konnten nicht geladen werden')
      setLoading(false)
    }
  }

  async function selectMandant(mandantId: string) {
    try {
      setLoading(true)
      setError(null)
      
      // Backend-Aufruf: Mandant auswählen + Tabellen anlegen
      const selected = await mandantenAPI.selectMandant(mandantId)

      const idleTimeout = Number(selected?.idle_timeout ?? selected?.idleTimeout ?? 0)
      const idleWarning = Number(selected?.idle_warning ?? selected?.idleWarning ?? 0)
      if (Number.isFinite(idleTimeout) && idleTimeout > 0) {
        localStorage.setItem('idle_timeout', String(Math.trunc(idleTimeout)))
      } else {
        localStorage.removeItem('idle_timeout')
      }
      if (Number.isFinite(idleWarning) && idleWarning > 0) {
        localStorage.setItem('idle_warning', String(Math.trunc(idleWarning)))
      } else {
        localStorage.removeItem('idle_warning')
      }

      // Callback aufrufen (AuthContext persistiert in localStorage)
      onMandantSelected({
        uid: selected.mandant_id ?? mandantId,
        name: selected.mandant_name ?? 'Mandant',
        town: selected.mandant_town ?? undefined,
        street: selected.mandant_street ?? undefined,
      })
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Auswählen des Mandanten')
      setLoading(false)
    }
  }

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <h1 style={styles.title}>Mandantenauswahl</h1>
        <p style={styles.subtitle}>Bitte wählen Sie einen Mandanten</p>
        
        {loading && <p style={styles.loading}>Mandanten werden geladen...</p>}
        
        {error && <div style={styles.error}>{error}</div>}
        
        {!loading && !error && (
          <>
            <div style={styles.list}>
              {mandanten.map((mandant) => (
                <button
                  key={mandant.id}
                  onClick={() => selectMandant(mandant.id)}
                  style={styles.button}
                >
                  {mandant.name}
                </button>
              ))}
              
              {onCreateNew && (
                <div style={styles.separator}>
                  <button 
                    onClick={onCreateNew}
                    style={styles.createButton}
                  >
                    + Neuen Mandanten anlegen
                  </button>
                </div>
              )}
            </div>
          </>
        )}
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
    backgroundColor: '#f5f5f5',
  },
  card: {
    backgroundColor: 'white',
    padding: '2rem',
    borderRadius: '8px',
    boxShadow: '0 2px 10px rgba(0,0,0,0.1)',
    width: '100%',
    maxWidth: '500px',
  },
  title: {
    fontSize: '2rem',
    fontWeight: 'bold',
    textAlign: 'center' as const,
    marginBottom: '0.5rem',
    color: '#333',
  },
  subtitle: {
    textAlign: 'center' as const,
    color: '#666',
    marginBottom: '2rem',
  },
  loading: {
    textAlign: 'center' as const,
    color: '#666',
  },
  error: {
    backgroundColor: '#ffebee',
    color: '#c62828',
    padding: '0.75rem',
    borderRadius: '4px',
    marginBottom: '1rem',
  },
  list: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '0.75rem',
  },
  separator: {
    borderTop: '1px solid #eee',
    paddingTop: '0.75rem',
    marginTop: '0.5rem',
  },
  button: {
    padding: '1rem',
    backgroundColor: '#007bff',
    color: 'white',
    border: 'none',
    borderRadius: '4px',
    fontSize: '1rem',
    cursor: 'pointer',
    transition: 'background-color 0.2s',
    textAlign: 'left' as const,
    width: '100%',
  },
  createButton: {
    padding: '0.8rem',
    backgroundColor: 'transparent',
    color: '#666',
    border: '2px dashed #ddd',
    borderRadius: '4px',
    fontSize: '0.9rem',
    cursor: 'pointer',
    textAlign: 'center' as const,
    width: '100%',
  },
}
