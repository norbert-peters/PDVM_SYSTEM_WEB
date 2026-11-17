<#
.SYNOPSIS
  Sichert alle Datenbanken des lokalen PostgreSQL-Servers (je Datenbank ein Dump, dazu Rollen) in einen Stand-Ordner.

.DESCRIPTION
  Ablauf: Zugang aus backend\.env (DATABASE_URL_AUTH) lesen, alle Nicht-Template-Datenbanken mit pg_dump (Custom-Format)
  sichern, Rollen mit pg_dumpall --globals-only, jeden Dump mit pg_restore --list pruefen, MANIFEST.txt schreiben.
  Ziel: database\backups\stand_<Commit>_<Zeitstempel>\ (von Git ausgeschlossen: enthaelt Rollen und Passwort-Hashes).
  Das Passwort wird nur als Umgebungsvariable des Prozesses gesetzt, nie ausgegeben oder gespeichert.

  Zurueckspielen einer Datenbank: pg_restore --clean --if-exists -d <Datenbank> <Datei>.dump
  (leere Datenbank vorher mit createdb anlegen; Rollen: psql -f globals.sql)

.PARAMETER Label
  Name im Ordner statt des Git-Commits (z. B. vor_update).
.PARAMETER KeepLast
  Anzahl der Stand-Ordner, die erhalten bleiben (aeltere werden geloescht); 0 = nichts loeschen.
#>
[CmdletBinding()]
param(
    [string]$Label,
    [int]$KeepLast = 10,
    [string]$OutputRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $OutputRoot) { $OutputRoot = Join-Path $root 'database\backups' }

# --- PostgreSQL-Werkzeuge (PATH, sonst neueste Installation) ---
function Find-PgTool([string]$Name) {
    $cmd = Get-Command "$Name.exe" -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $found = Get-ChildItem "C:\Program Files\PostgreSQL\*\bin\$Name.exe" -ErrorAction SilentlyContinue |
        Sort-Object { [int](Split-Path (Split-Path $_.DirectoryName -Parent) -Leaf) } -Descending | Select-Object -First 1
    if ($found) { return $found.FullName }
    throw "$Name.exe nicht gefunden (PostgreSQL-Client-Werkzeuge installieren oder in den PATH aufnehmen)."
}
$pgDump = Find-PgTool 'pg_dump'
$pgDumpAll = Find-PgTool 'pg_dumpall'
$pgRestore = Find-PgTool 'pg_restore'
$psql = Find-PgTool 'psql'

# --- Zugang aus backend\.env ---
$envFile = Join-Path $root 'backend\.env'
if (-not (Test-Path $envFile)) { throw "backend\.env fehlt." }
$line = Select-String -Path $envFile -Pattern '^DATABASE_URL_AUTH=(.+)$' | Select-Object -First 1
if (-not $line) { throw 'DATABASE_URL_AUTH fehlt in backend\.env.' }
$url = $line.Matches[0].Groups[1].Value.Trim()
if ($url -notmatch '^postgres(?:ql)?://([^:@/]+)(?::([^@]*))?@([^:/]+)(?::(\d+))?/') { throw 'DATABASE_URL_AUTH hat kein erwartetes Format.' }
$dbUser = [uri]::UnescapeDataString($Matches[1])
$dbPassword = [uri]::UnescapeDataString([string]$Matches[2])
$dbHost = $Matches[3]
$dbPort = if ($Matches[4]) { $Matches[4] } else { '5432' }
$env:PGPASSWORD = $dbPassword
$conn = @('-h', $dbHost, '-p', $dbPort, '-U', $dbUser)

try {
    $databases = @(& $psql @conn -d postgres -At -c "select datname from pg_database where not datistemplate order by 1")
    if ($LASTEXITCODE -ne 0 -or $databases.Count -eq 0) { throw "Datenbankliste nicht lesbar (Server ${dbHost}:${dbPort} erreichbar, Zugang korrekt?)." }

    # --- Zielordner ---
    $commit = 'ohne-git'
    $dirty = ''
    try {
        $commit = (git -C $root rev-parse --short HEAD 2>$null).Trim()
        if (git -C $root status --porcelain 2>$null) { $dirty = '_mod' }
    } catch { }
    $name = if ($Label) { $Label } else { "$commit$dirty" }
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $target = Join-Path $OutputRoot "stand_${name}_$stamp"
    New-Item -ItemType Directory -Path $target -Force | Out-Null

    # --- Sicherung ---
    $manifest = New-Object System.Collections.Generic.List[string]
    $manifest.Add("Sicherung: $stamp | Commit: $commit$dirty | Server: ${dbHost}:${dbPort}")
    $failed = @()
    foreach ($db in $databases) {
        $file = Join-Path $target "$db.dump"
        Write-Host "Sichere $db ..."
        & $pgDump @conn -d $db -F c -f $file
        if ($LASTEXITCODE -ne 0) { $failed += $db; continue }
        & $pgRestore --list $file *> $null
        if ($LASTEXITCODE -ne 0) { $failed += $db; continue }
        $manifest.Add(('{0,-30} {1,10:N0} KB' -f $db, ((Get-Item $file).Length / 1KB)))
    }
    Write-Host 'Sichere Rollen (globals) ...'
    & $pgDumpAll @conn --globals-only -f (Join-Path $target 'globals.sql')
    if ($LASTEXITCODE -ne 0) { $failed += 'globals' }

    $manifest.Add($(if ($failed) { "FEHLER: $($failed -join ', ')" } else { 'Alle Dumps geprueft (pg_restore --list).' }))
    Set-Content -Path (Join-Path $target 'MANIFEST.txt') -Value $manifest -Encoding UTF8
    if ($failed) { throw "Sicherung unvollstaendig, fehlgeschlagen: $($failed -join ', ') ($target)" }

    Write-Host "Fertig: $target ($($databases.Count) Datenbanken + Rollen)"

    # --- Aufbewahrung ---
    if ($KeepLast -gt 0) {
        Get-ChildItem $OutputRoot -Directory -Filter 'stand_*' | Sort-Object LastWriteTime -Descending |
            Select-Object -Skip $KeepLast | ForEach-Object {
                Remove-Item $_.FullName -Recurse -Force
                Write-Host "Alte Sicherung geloescht: $($_.Name)"
            }
    }
}
finally {
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
}
