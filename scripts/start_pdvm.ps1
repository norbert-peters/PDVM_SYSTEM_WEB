<#
.SYNOPSIS
  Startet Backend (FastAPI, Port 8000) und Frontend (Vite, Port 5173) in eigenen Fenstern.
.PARAMETER Target
  all (Standard) | backend | frontend
.PARAMETER NoBrowser
  Browser nach dem Start nicht oeffnen.
#>
param(
    [ValidateSet('all', 'backend', 'frontend')][string]$Target = 'all',
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $root 'backend'
$frontendDir = Join-Path $root 'frontend'
$python = Join-Path $root '.venv\Scripts\python.exe'
$backendPort = 8000
$frontendPort = 5173

function Test-PortOpen([string]$HostName, [int]$Port) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $iar = $client.BeginConnect($HostName, $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(1000) -and $client.Connected
        $client.Close()
        return $ok
    } catch { return $false }
}

function Test-PortListening([int]$Port) {
    return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

function Wait-Url([string]$Url, [int]$TimeoutSec) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 | Out-Null
            return $true
        } catch { Start-Sleep -Milliseconds 700 }
    }
    return $false
}

# --- Preflight ---
if ($Target -ne 'frontend') {
    if (-not (Test-Path $python)) {
        throw "Python-venv fehlt: $python (python -m venv .venv; .venv\Scripts\pip install -r backend\requirements.txt)"
    }
    $envFile = Join-Path $backendDir '.env'
    if (-not (Test-Path $envFile)) {
        throw "backend\.env fehlt (Vorlage: backend\.env.example)"
    }
    $dbLine = Select-String -Path $envFile -Pattern '^DATABASE_URL_AUTH=(.+)$' | Select-Object -First 1
    if ($dbLine -and $dbLine.Matches[0].Groups[1].Value -match '@([^:/]+):?(\d+)?/') {
        $dbHost = $Matches[1]
        $dbPort = if ($Matches[2]) { [int]$Matches[2] } else { 5432 }
        if (-not (Test-PortOpen $dbHost $dbPort)) {
            Write-Warning "PostgreSQL unter ${dbHost}:${dbPort} nicht erreichbar - Backend startet evtl. nicht."
        }
    }
}
if ($Target -ne 'backend') {
    if (-not (Test-Path (Join-Path $frontendDir 'node_modules'))) {
        Write-Host 'node_modules fehlt - npm install ...'
        Push-Location $frontendDir
        try { npm install; if ($LASTEXITCODE -ne 0) { throw 'npm install fehlgeschlagen' } } finally { Pop-Location }
    }
}

# --- Start ---
if ($Target -ne 'frontend') {
    if (Test-PortListening $backendPort) {
        Write-Host "Backend laeuft bereits auf Port $backendPort."
    } else {
        $cmd = "`$env:PYTHONUTF8='1'; `$Host.UI.RawUI.WindowTitle='PDVM Backend'; & '$python' -m uvicorn app.main:app --reload --host 127.0.0.1 --port $backendPort"
        Start-Process powershell -WorkingDirectory $backendDir -ArgumentList '-NoExit', '-NoProfile', '-Command', $cmd | Out-Null
        Write-Host "Backend gestartet (Port $backendPort)."
    }
}
if ($Target -ne 'backend') {
    if (Test-PortListening $frontendPort) {
        Write-Host "Frontend laeuft bereits auf Port $frontendPort."
    } else {
        $cmd = "`$Host.UI.RawUI.WindowTitle='PDVM Frontend'; npm run dev"
        Start-Process powershell -WorkingDirectory $frontendDir -ArgumentList '-NoExit', '-NoProfile', '-Command', $cmd | Out-Null
        Write-Host "Frontend gestartet (Port $frontendPort)."
    }
}

# --- Bereitschaft pruefen ---
if ($Target -ne 'frontend') {
    if (Wait-Url "http://127.0.0.1:$backendPort/health" 40) { Write-Host "Backend bereit:  http://127.0.0.1:$backendPort/health" }
    else { Write-Warning 'Backend antwortet nicht - Fenster "PDVM Backend" pruefen.' }
}
if ($Target -ne 'backend') {
    if (Wait-Url "http://localhost:$frontendPort/" 40) {
        Write-Host "Frontend bereit: http://localhost:$frontendPort/"
        if (-not $NoBrowser) { Start-Process "http://localhost:$frontendPort/" }
    } else { Write-Warning 'Frontend antwortet nicht - Fenster "PDVM Frontend" pruefen.' }
}
