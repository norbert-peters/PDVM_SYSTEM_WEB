[CmdletBinding()]
param(
    [string]$ContainerName = "pdvm_postgres",
    [string]$Database = "pdvm_system",
    [string]$Username = "postgres",
    [SecureString]$Password = (ConvertTo-SecureString "password" -AsPlainText -Force),
    [string]$OutputDir = "..\backups",
    [string]$FallbackOutputDir = "..\backups",
    [int]$KeepDays = 14
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-DockerCommand {
    param([Parameter(Mandatory = $true)][string]$Command)

    $output = Invoke-Expression $Command 2>&1
    if ($LASTEXITCODE -ne 0) {
        $detail = ($output | Out-String).Trim()
        if ([string]::IsNullOrWhiteSpace($detail)) {
            $detail = "Unbekannter Docker-Fehler"
        }
        throw "Docker-Kommando fehlgeschlagen: $Command`n$detail"
    }

    return $output
}

function New-DirectoryIfMissing {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -Path $Path)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

function Resolve-DirectoryPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$ScriptDirectory
    )

    if ([System.IO.Path]::IsPathRooted($Path)) {
        return $Path
    }

    return Join-Path $ScriptDirectory $Path
}

function Test-DirectoryWritable {
    param([Parameter(Mandatory = $true)][string]$Path)

    $probeFile = Join-Path $Path (".write_test_{0}.tmp" -f ([guid]::NewGuid().ToString("N")))
    try {
        Set-Content -Path $probeFile -Value "test" -Encoding UTF8
        Remove-Item -Path $probeFile -Force
        return $true
    }
    catch {
        return $false
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$resolvedOutputDir = Resolve-DirectoryPath -Path $OutputDir -ScriptDirectory $scriptDir
$resolvedFallbackDir = Resolve-DirectoryPath -Path $FallbackOutputDir -ScriptDirectory $scriptDir

$activeOutputDir = $null
try {
    New-DirectoryIfMissing -Path $resolvedOutputDir
    if (-not (Test-DirectoryWritable -Path $resolvedOutputDir)) {
        throw "Zielverzeichnis nicht beschreibbar"
    }
    $activeOutputDir = $resolvedOutputDir
}
catch {
    if ($resolvedFallbackDir -eq $resolvedOutputDir) {
        throw "Backup-Ziel '$resolvedOutputDir' ist nicht verfügbar oder nicht beschreibbar. Kein separates Fallback konfiguriert."
    }

    Write-Warning "Backup-Ziel '$resolvedOutputDir' nicht verfügbar: $($_.Exception.Message)"
    Write-Warning "Wechsle auf Fallback-Ziel '$resolvedFallbackDir'."

    New-DirectoryIfMissing -Path $resolvedFallbackDir
    if (-not (Test-DirectoryWritable -Path $resolvedFallbackDir)) {
        throw "Fallback-Ziel '$resolvedFallbackDir' ist nicht beschreibbar."
    }
    $activeOutputDir = $resolvedFallbackDir
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$fileName = "${Database}_${timestamp}.dump"
$hostBackupPath = Join-Path $activeOutputDir $fileName
$containerBackupPath = "/tmp/$fileName"

$runningContainers = Invoke-DockerCommand -Command 'docker ps --format "{{.Names}}"'
if ($runningContainers -notcontains $ContainerName) {
    throw "Docker-Container '$ContainerName' läuft nicht. Bitte zuerst starten."
}

Write-Host "🔄 Erstelle Backup für Datenbank '$Database' aus Container '$ContainerName'..."

$plainTextPassword = [System.Net.NetworkCredential]::new("", $Password).Password

Invoke-DockerCommand -Command "docker exec -e \"PGPASSWORD=$plainTextPassword\" $ContainerName pg_dump -U $Username -d $Database -F c -f $containerBackupPath"

Invoke-DockerCommand -Command "docker cp \"${ContainerName}:${containerBackupPath}\" \"$hostBackupPath\""
Invoke-DockerCommand -Command "docker exec $ContainerName rm -f $containerBackupPath"

Write-Host "✅ Backup erstellt: $hostBackupPath"

if ($KeepDays -gt 0) {
    $cutoffDate = (Get-Date).AddDays(-$KeepDays)
    $oldBackups = Get-ChildItem -Path $activeOutputDir -Filter "${Database}_*.dump" -File |
        Where-Object { $_.LastWriteTime -lt $cutoffDate }

    foreach ($oldBackup in $oldBackups) {
        Remove-Item -Path $oldBackup.FullName -Force
        Write-Host "🧹 Altes Backup gelöscht: $($oldBackup.Name)"
    }
}

Write-Host "🏁 Backup-Prozess abgeschlossen."