import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useState } from 'react'
import Login from './components/Login'
import MandantSelect from './components/MandantSelect'
import MandantCreate from './components/MandantCreate'
import Dashboard from './components/Dashboard'
import Welcome from './components/Welcome'
import TableView from './components/TableView'
import { AppLayout } from './components/layout'

function App() {
  const [token, setToken] = useState<string | null>(
    localStorage.getItem('token')
  )
  const [mandantId, setMandantId] = useState<string | null>(
    localStorage.getItem('mandant_id')
  )
  const [showCreateMandant, setShowCreateMandant] = useState(false)

  const handleLogin = (newToken: string) => {
    localStorage.setItem('token', newToken)
    setToken(newToken)
    // Mandant wird in MandantSelect ausgewählt
    localStorage.removeItem('mandant_id')
    setMandantId(null)
  }

  const handleMandantSelected = (selectedMandantId: string) => {
    localStorage.setItem('mandant_id', selectedMandantId)
    setMandantId(selectedMandantId)
    // Speichere Mandant-Info für useAuth Hook
    localStorage.setItem('currentMandant', JSON.stringify({
      uid: selectedMandantId,
      name: 'Mandant' // TODO: Echten Namen vom Backend holen
    }))
  }

  const handleLogout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('mandant_id')
    setToken(null)
    setMandantId(null)
  }

  // Kein Token → Login
  if (!token) {
    return <Login onLogin={handleLogin} />
  }

  // Token aber kein Mandant → Mandantenauswahl oder Create
  if (!mandantId) {
    if (showCreateMandant) {
      return (
        <MandantCreate
          token={token}
          onSuccess={() => {
            setShowCreateMandant(false)
            // Nach Erstellung zurück zur Auswahl
          }}
          onCancel={() => setShowCreateMandant(false)}
        />
      )
    }
    return (
      <MandantSelect
        token={token}
        onMandantSelected={handleMandantSelected}
        onCreateNew={() => setShowCreateMandant(true)}
      />
    )
  }

  // Token + Mandant → Dashboard mit neuem Layout
  return (
    <BrowserRouter>
      <AppLayout>
        <Routes>
          <Route path="/" element={<Welcome mandantId={mandantId} />} />
          <Route path="/dashboard" element={<Dashboard onLogout={handleLogout} mandantId={mandantId} token={token} />} />
          <Route path="/table/:tableName" element={<TableView token={token} />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AppLayout>
    </BrowserRouter>
  )
}

export default App
