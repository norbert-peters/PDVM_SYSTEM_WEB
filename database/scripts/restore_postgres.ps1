[CmdletBinding()]
param(
    [string]$ContainerName = "pdvm_postgres",
    [string]$Database = "pdvm_system",
    [string]$Username = "postgres",
    [string]$Password = "password",
    [string]$BackupFile,
    [string]$BackupDir = "..\backups"
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

function Resolve-BackupFile {
    param(
        [Parameter(Mandatory = $true)][string]$File,
        [Parameter(Mandatory = $true)][string]$Dir,
        [Parameter(Mandatory = $true)][string]$DatabaseName,
        [Parameter(Mandatory = $true)][string]$ScriptDirectory
    )

    if ($File) {
        if ([System.IO.Path]::IsPathRooted($File)) {
            return $File
        }
        return Join-Path $ScriptDirectory $File
    }

    $resolvedDir = if ([System.IO.Path]::IsPathRooted($Dir)) {
        $Dir
    }
    else {
        Join-Path $ScriptDirectory $Dir
    }

    if (-not (Test-Path -Path $resolvedDir)) {
        throw "Backup-Verzeichnis nicht gefunden: $resolvedDir"
    }

    $latest = Get-ChildItem -Path $resolvedDir -Filter "${DatabaseName}_*.dump" -File |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    if (-not $latest) {
        throw "Keine Backup-Datei im Verzeichnis gefunden: $resolvedDir"
    }

    return $latest.FullName
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$resolvedBackupFile = Resolve-BackupFile -File $BackupFile -Dir $BackupDir -DatabaseName $Database -ScriptDirectory $scriptDir

if (-not (Test-Path -Path $resolvedBackupFile)) {
    throw "Backup-Datei nicht gefunden: $resolvedBackupFile"
}

$runningContainers = Invoke-DockerCommand -Command 'docker ps --format "{{.Names}}"'
if ($runningContainers -notcontains $ContainerName) {
    throw "Docker-Container '$ContainerName' läuft nicht. Bitte zuerst starten."
}

$fileName = Split-Path -Leaf $resolvedBackupFile
$containerRestorePath = "/tmp/$fileName"

Write-Host "⚠️ Restore startet für Datenbank '$Database' aus '$resolvedBackupFile'"
Write-Host "🔄 Kopiere Backup in Container..."

Invoke-DockerCommand -Command "docker cp \"$resolvedBackupFile\" \"${ContainerName}:${containerRestorePath}\""

Write-Host "🔄 Spiele Backup ein (bestehende Objekte werden ersetzt)..."

Invoke-DockerCommand -Command "docker exec -e \"PGPASSWORD=$Password\" $ContainerName pg_restore -U $Username -d $Database --clean --if-exists --no-owner --no-privileges $containerRestorePath"

Invoke-DockerCommand -Command "docker exec $ContainerName rm -f $containerRestorePath"

Write-Host "✅ Restore abgeschlossen."