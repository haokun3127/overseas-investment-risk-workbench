param(
    [switch]$Foreground,
    [switch]$OpenBrowser
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
$workbenchUrl = 'http://127.0.0.1:8000'

function Test-Workbench {
    try {
        $health = Invoke-RestMethod -Uri "$workbenchUrl/api/health" -TimeoutSec 1
        $auth = Invoke-RestMethod -Uri "$workbenchUrl/api/auth/status" -TimeoutSec 1
        return ($health.status -eq 'ok' -and
            $auth.initialized -is [bool] -and $auth.authenticated -is [bool])
    } catch {
        return $false
    }
}

if (Test-Workbench) {
    Write-Host "Workbench is already running: $workbenchUrl"
    if ($OpenBrowser) { Start-Process $workbenchUrl }
    exit 0
}

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Python environment is missing. Follow README.md to install dependencies.'
}

$portProbe = [System.Net.Sockets.TcpClient]::new()
$portOccupied = $false
try {
    $portProbe.Connect('127.0.0.1', 8000)
    $portOccupied = $true
} catch {
    # A refused connection means the port is available.
} finally {
    $portProbe.Dispose()
}
if ($portOccupied) {
    throw 'Port 8000 is occupied but the workbench is not responding. Check the existing process before restarting.'
}

$serverArguments = @('-m', 'uvicorn', 'app.main:create_app', '--factory', '--host', '127.0.0.1', '--port', '8000')
if ($Foreground) {
    & $pythonPath @serverArguments
    exit $LASTEXITCODE
}

$logDirectory = Join-Path $PSScriptRoot 'logs'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$runStamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$stdoutLog = Join-Path $logDirectory "server-$runStamp.out.log"
$stderrLog = Join-Path $logDirectory "server-$runStamp.err.log"
$serverProcess = Start-Process -FilePath $pythonPath -ArgumentList $serverArguments `
    -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog

$deadline = (Get-Date).AddSeconds(30)
do {
    if (Test-Workbench) {
        Write-Host "Workbench is running in the background: $workbenchUrl"
        Write-Host "Logs: $logDirectory"
        if ($OpenBrowser) { Start-Process $workbenchUrl }
        exit 0
    }
    $serverProcess.Refresh()
    if ($serverProcess.HasExited) {
        throw "Server exited during startup. See $stderrLog"
    }
    Start-Sleep -Milliseconds 250
} while ((Get-Date) -lt $deadline)

throw "Server did not become ready within 30 seconds. See $stderrLog"
