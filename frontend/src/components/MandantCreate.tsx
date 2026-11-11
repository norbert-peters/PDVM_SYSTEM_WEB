import { useState, useEffect } from 'react'
import { apiClient } from '../api/client'

interface MandantCreateProps {
  token: string
  onSuccess: () => void
  onCancel: () => void
}

interface Property {
  name: string
  label: string
  type: string
  readonly: boolean
  display_order: number
  required: boolean
  default_value: string
}

interface PropertyControl {
  [key: string]: Property
}

export default function MandantCreate({ token, onSuccess, onCancel }: MandantCreateProps) {
  const [properties, setProperties] = useState<PropertyControl>({})
  const [formData, setFormData] = useState<any>({})
  const [validated, setValidated] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    loadTemplate()
  }, [])

  async function loadTemplate() {
    try {
      const response = await apiClient.get('/mandanten/template', {
        headers: { Authorization: `Bearer ${token}` }
      })
      
      // Template IST das Formular - direkt als formData verwenden
      setProperties(response.data.properties)
      setFormData(response.data.template)
      
    } catch (err: any) {
      console.error('Template-Ladefehler:', err)
      setError(err.response?.data?.detail || err.message || 'Template konnte nicht geladen werden')
    }
  }

  function handleValidate(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    
    // Validierung
    if (!formData.ROOT?.NAME) {
      setError('Bitte Bezeichnung eingeben')
      return
    }
    if (!formData.MANDANT?.DATABASE || formData.MANDANT.DATABASE === '-eingeben-') {
      setError('Bitte Mandanten Datenbank eingeben')
      return
    }
    
    setValidated(true)
    setError('')
  }

  async function handleCreate() {
    if (!validated) return
    
    try {
      setSaving(true)
      setError('')
      
      // Nur speichern - DB-Create-Prozess kommt später
      const response = await apiClient.post('/mandanten/save', formData, {
        headers: { Authorization: `Bearer ${token}` }
      })
      
      console.log('Mandant gespeichert:', response.data)
      alert('Mandant erfolgreich gespeichert!')
      onSuccess()
      
    } catch (err: any) {
      console.error('Speicher-Fehler:', err)
      setError(err.response?.data?.detail || 'Fehler beim Speichern des Mandanten')
      setValidated(false)
    } finally {
      setSaving(false)
    }
  }

  function handleChange(group: string, field: string, value: any) {
    setFormData({
      ...formData,
      [group]: { ...formData[group], [field]: value }
    })
  }

  function renderField(group: string, fieldName: string) {
    // System-Felder ausblenden (diese werden automatisch gesetzt)
    if (['SELF_GUID', 'CREATED_AT', 'MODIFIED_AT', 'CREATED_BY'].includes(fieldName)) {
      return null
    }

    const property = properties[fieldName]
    const value = formData[group]?.[fieldName]
    
    // Fallback wenn keine Property-Definition vorhanden
    const propertyType = property?.type || 'text'
    const isReadonly = property?.readonly === true
    const label = property?.label || fieldName

    switch (propertyType) {
      case 'list':
        // Arrays/Listen als JSON-String in textarea
        const displayValue = Array.isArray(value) ? JSON.stringify(value, null, 2) : (value || '')
        return (
          <div key={fieldName} style={styles.field}>
            <label style={styles.label}>{label}</label>
            <textarea
              value={displayValue}
              disabled={isReadonly}
              style={{...styles.input, minHeight: '80px', fontFamily: 'monospace', fontSize: '12px'}}
              rows={4}
            />
          </div>
        )

      case 'boolean':
        return (
          <div key={fieldName} style={styles.field}>
            <label style={styles.checkboxLabel}>
              <input
                type="checkbox"
                checked={value || false}
                onChange={(e) => handleChange(group, fieldName, e.target.checked)}
                disabled={isReadonly}
              />
              <span style={styles.label}>{label}</span>
            </label>
          </div>
        )

      case 'number':
        return (
          <div key={fieldName} style={styles.field}>
            <label style={styles.label}>{label}</label>
            <input
              type="number"
              value={value || ''}
              onChange={(e) => handleChange(group, fieldName, parseInt(e.target.value))}
              disabled={isReadonly}
              style={styles.input}
            />
          </div>
        )

      case 'email':
        return (
          <div key={fieldName} style={styles.field}>
            <label style={styles.label}>{label}</label>
            <input
              type="email"
              value={value || ''}
              onChange={(e) => handleChange(group, fieldName, e.target.value)}
              disabled={isReadonly}
              style={styles.input}
            />
          </div>
        )

      default: // text und alle anderen Typen
        return (
          <div key={fieldName} style={styles.field}>
            <label style={styles.label}>{label}</label>
            <input
              type="text"
              value={value || ''}
              onChange={(e) => handleChange(group, fieldName, e.target.value)}
              disabled={isReadonly}
              style={styles.input}
            />
          </div>
        )
    }
  }

  function renderGroup(groupName: string) {
    const groupData = formData[groupName]
    if (!groupData || typeof groupData !== 'object') return null

    return (
      <div key={groupName} style={styles.group}>
        <h3 style={styles.groupTitle}>{groupName}</h3>
        <div style={styles.groupFields}>
          {Object.keys(groupData).map((fieldName) => 
            renderField(groupName, fieldName)
          )}
        </div>
      </div>
    )
  }

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <h1 style={styles.title}>Neuen Mandanten anlegen</h1>
        
        {error && <div style={styles.error}>{error}</div>}
        {validated && !error && <div style={{...styles.error, backgroundColor: 'var(--color-success-bg)', color: 'var(--color-success-text)', border: '1px solid var(--color-success-border)'}}>Daten validiert. Klicken Sie auf "Speichern" um die Daten zu sichern.</div>}
        
        <form onSubmit={handleValidate}>
          {renderGroup('ROOT')}
          {renderGroup('MANDANT')}
          {renderGroup('CONFIG')}
          {renderGroup('CONTACT')}
          {renderGroup('SECURITY')}
          
          <div style={styles.buttons}>
            <button
              type="button"
              onClick={onCancel}
              style={styles.cancelButton}
              disabled={saving}
            >
              Abbrechen
            </button>
            <button
              type="submit"
              style={styles.submitButton}
              disabled={saving || validated}
            >
              Übernehmen
            </button>
            <button
              type="button"
              onClick={handleCreate}
              style={{...styles.submitButton, backgroundColor: validated ? 'var(--color-success)' : 'var(--color-text-secondary)'}}
              disabled={!validated || saving}
            >
              {saving ? 'Wird gespeichert...' : 'Speichern'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

const styles = {
  container: {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'flex-start',
    minHeight: '100vh',
    backgroundColor: 'var(--color-background-secondary)',
    padding: '2rem',
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
  group: {
    marginBottom: '2rem',
    padding: '1rem',
    backgroundColor: 'var(--color-background-secondary)',
    borderRadius: '6px',
    border: '1px solid var(--color-border-light)',
  },
  groupTitle: {
    fontSize: '1.2rem',
    fontWeight: 'bold',
    marginBottom: '1rem',
    color: 'var(--color-text-secondary)',
    borderBottom: '2px solid var(--color-primary-500)',
    paddingBottom: '0.5rem',
  },
  groupFields: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '1rem',
  },
  field: {
    marginBottom: '0.5rem',
  },
  label: {
    display: 'block',
    marginBottom: '0.5rem',
    fontWeight: '500',
    color: 'var(--color-text-primary)',
  },
  checkboxLabel: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    cursor: 'pointer',
  },
  input: {
    width: '100%',
    padding: '0.5rem',
    border: '1px solid var(--color-border-medium)',
    borderRadius: '4px',
    fontSize: '1rem',
  },
  buttons: {
    display: 'flex',
    gap: '1rem',
    marginTop: '2rem',
    justifyContent: 'flex-end',
  },
  cancelButton: {
    padding: '0.75rem 1.5rem',
    backgroundColor: 'var(--color-text-secondary)',
    color: 'var(--color-text-inverse)',
    border: 'none',
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
