import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useState } from 'react'
import Login from './components/Login'
import MandantSelect from './components/MandantSelect'
import MandantCreate from './components/MandantCreate'
import Dashboard from './components/Dashboard'
import TableView from './components/TableView'

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

  // Token + Mandant → Dashboard
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Dashboard onLogout={handleLogout} mandantId={mandantId} token={token} />} />
        <Route path="/table/:tableName" element={<TableView token={token} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
