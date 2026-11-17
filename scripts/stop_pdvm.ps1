<#
.SYNOPSIS
  Beendet die Server auf den Ports 8000 (Backend) und 5173 (Frontend) samt Prozessbaum.
#>
param(
    [ValidateSet('all', 'backend', 'frontend')][string]$Target = 'all'
)

$ports = @()
if ($Target -ne 'frontend') { $ports += 8000 }
if ($Target -ne 'backend') { $ports += 5173 }

foreach ($port in $ports) {
    $pids = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
    if (-not $pids) { Write-Host "Port ${port}: nichts zu beenden."; continue }
    foreach ($procId in $pids) {
        # /T beendet auch Kindprozesse (uvicorn --reload, node)
        taskkill /PID $procId /T /F | Out-Null
        Write-Host "Port ${port}: Prozess $procId beendet."
    }
}

# Uebrig gebliebene Konsolenfenster (Titel) schliessen
Get-Process powershell -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowTitle -in 'PDVM Backend', 'PDVM Frontend' } |
    ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
