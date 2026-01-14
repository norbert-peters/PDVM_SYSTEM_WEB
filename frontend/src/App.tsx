import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useState } from 'react'
import Login from './components/Login'
import MandantSelect from './components/MandantSelect'
import MandantCreate from './components/MandantCreate'
import Dashboard from './components/Dashboard'
import Welcome from './components/Welcome'
import TableView from './components/TableView'
import { AppLayout } from './components/layout'
import { MenuProvider } from './contexts/MenuContext'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import type { Mandant } from './contexts/AuthContext'

function AppContent() {
  const { token, mandantId, login, logout, selectMandant } = useAuth()
  const [showCreateMandant, setShowCreateMandant] = useState(false)

  // NOTE: state 'token' and 'mandantId' now come from context
  
  const handleLogin = (newToken: string) => {
    login(newToken)
  }

  const handleMandantSelected = (mandant: Mandant) => {
    selectMandant(mandant)
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
            // Nach Erstellung zurück zur Auswahl (passiert automatisch wenn kein Mandant gewählt)
          }}
          onCancel={() => setShowCreateMandant(false)}
        />
      )
    }
    return (
      <MandantSelect
        onMandantSelected={handleMandantSelected}
        onCreateNew={() => setShowCreateMandant(true)}
      />
    )
  }

  // Token + Mandant → Dashboard mit neuem Layout
  return (
    <BrowserRouter>
      <MenuProvider>
        <AppLayout>
          <Routes>
            <Route path="/" element={<Welcome mandantId={mandantId} />} />
            <Route path="/dashboard" element={<Dashboard onLogout={logout} mandantId={mandantId} token={token} />} />
            <Route path="/table/:tableName" element={<TableView token={token} />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AppLayout>
      </MenuProvider>
    </BrowserRouter>
  )
}

function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  )
}

export default App
