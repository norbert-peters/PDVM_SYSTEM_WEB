import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useEffect, useRef, useState } from 'react'
import Login from './components/Login'
import MandantSelect from './components/MandantSelect'
import MandantCreate from './components/MandantCreate'
import Dashboard from './components/Dashboard'
import Welcome from './components/Welcome'
import TableView from './components/TableView'
import PdvmViewPage from './components/views/PdvmViewPage'
import PdvmDialogPage from './components/dialogs/PdvmDialogPage'
import MenuHome from './components/menu/MenuHome'
import { AppLayout } from './components/layout'
import { MenuProvider } from './contexts/MenuContext'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import type { Mandant } from './contexts/AuthContext'
import { authAPI } from './api/client'
import { PdvmDialogModal } from './components/common/PdvmDialogModal'

function AppContent() {
  const { token, mandantId, login, logout, selectMandant } = useAuth()
  const [showCreateMandant, setShowCreateMandant] = useState(false)
  const [idleWarningOpen, setIdleWarningOpen] = useState(false)
  const [idleRemainingSec, setIdleRemainingSec] = useState<number | null>(null)
  const lastActivityRef = useRef<number>(Date.now())
  const warningShownRef = useRef<boolean>(false)
  const keepAliveBusyRef = useRef<boolean>(false)
  const idleConfigRef = useRef<{ timeout: number; warning: number }>({ timeout: 0, warning: 0 })

  // NOTE: state 'token' and 'mandantId' now come from context
  
  const handleLogin = (newToken: string) => {
    login(newToken)
  }

  const handleMandantSelected = (mandant: Mandant) => {
    selectMandant(mandant)
  }

  useEffect(() => {
    if (!token || !mandantId) {
      setIdleWarningOpen(false)
      setIdleRemainingSec(null)
      return
    }

    const timeout = Number(localStorage.getItem('idle_timeout') || 0)
    const warning = Number(localStorage.getItem('idle_warning') || 0)
    if (!Number.isFinite(timeout) || timeout <= 0) {
      setIdleWarningOpen(false)
      setIdleRemainingSec(null)
      return
    }

    idleConfigRef.current = {
      timeout: Math.trunc(timeout),
      warning: Number.isFinite(warning) && warning > 0 ? Math.trunc(warning) : 0,
    }
    lastActivityRef.current = Date.now()
    warningShownRef.current = false
    setIdleWarningOpen(false)

    const onActivity = () => {
      lastActivityRef.current = Date.now()
      if (idleWarningOpen) setIdleWarningOpen(false)
      warningShownRef.current = false
    }

    const events = ['mousemove', 'mousedown', 'keydown', 'scroll', 'touchstart']
    events.forEach((evt) => window.addEventListener(evt, onActivity, { passive: true }))

    const tick = () => {
      const now = Date.now()
      const cfg = idleConfigRef.current
      const idleMs = now - lastActivityRef.current
      const remainingMs = cfg.timeout * 1000 - idleMs
      const remainingSec = Math.max(0, Math.ceil(remainingMs / 1000))
      setIdleRemainingSec(remainingSec)

      if (remainingMs <= 0) {
        logout()
        return
      }

      if (cfg.warning > 0 && remainingMs <= cfg.warning * 1000 && !warningShownRef.current) {
        setIdleWarningOpen(true)
        warningShownRef.current = true
      }
    }

    const ping = async () => {
      const now = Date.now()
      if (now - lastActivityRef.current > 60_000) return
      if (keepAliveBusyRef.current) return

      keepAliveBusyRef.current = true
      try {
        const resp = await authAPI.keepAlive()
        if (resp?.idle_timeout && Number.isFinite(resp.idle_timeout)) {
          idleConfigRef.current.timeout = Math.trunc(Number(resp.idle_timeout))
          localStorage.setItem('idle_timeout', String(idleConfigRef.current.timeout))
        }
        if (resp?.idle_warning && Number.isFinite(resp.idle_warning)) {
          idleConfigRef.current.warning = Math.trunc(Number(resp.idle_warning))
          localStorage.setItem('idle_warning', String(idleConfigRef.current.warning))
        }
      } catch {
        // ignore
      } finally {
        keepAliveBusyRef.current = false
      }
    }

    tick()
    const tickId = window.setInterval(tick, 1000)
    const pingId = window.setInterval(ping, 30_000)

    return () => {
      events.forEach((evt) => window.removeEventListener(evt, onActivity as any))
      window.clearInterval(tickId)
      window.clearInterval(pingId)
    }
  }, [token, mandantId, logout])

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
          <PdvmDialogModal
            open={idleWarningOpen}
            kind="confirm"
            title="Sitzung läuft ab"
            message={
              idleRemainingSec != null
                ? `Ihre Sitzung läuft in ${idleRemainingSec} Sekunden ab. Aktiv bleiben?`
                : 'Ihre Sitzung läuft bald ab. Aktiv bleiben?'
            }
            confirmLabel="Sitzung verlängern"
            cancelLabel="Abmelden"
            onConfirm={async () => {
              lastActivityRef.current = Date.now()
              warningShownRef.current = false
              setIdleWarningOpen(false)
              try {
                await authAPI.keepAlive()
              } catch {
                // ignore
              }
            }}
            onCancel={() => {
              setIdleWarningOpen(false)
              logout()
            }}
          />
          <Routes>
            <Route path="/" element={<Welcome mandantId={mandantId} />} />
            <Route path="/menu-home" element={<MenuHome />} />
            <Route path="/dashboard" element={<Dashboard onLogout={logout} mandantId={mandantId} token={token} />} />
            <Route path="/table/:tableName" element={<TableView token={token} />} />
            <Route path="/view/:viewGuid" element={<PdvmViewPage />} />
            <Route path="/dialog/:dialogGuid" element={<PdvmDialogPage />} />
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
