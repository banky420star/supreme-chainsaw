$ErrorActionPreference = "Continue"
$RepoRoot = "C:\Users\Administrator\Desktop\SupremeChainsaw_Clean"
$PyExe = Join-Path $RepoRoot ".venv312\Scripts\python.exe"
$PythonDir = Join-Path $RepoRoot "02_Core_Python"

Set-Location $RepoRoot
$env:PYTHONPATH = $PythonDir

Write-Host "[START] Launching Server_AGI..."
Write-Host "PYTHONPATH=$env:PYTHONPATH"
Write-Host "Python: $PyExe"

$proc = Start-Process -FilePath $PyExe -ArgumentList "-m","Python.Server_AGI" -WorkingDirectory $RepoRoot -PassThru -NoNewWindow
Write-Host "[START] Server_AGI PID=$($proc.Id)"

Start-Sleep 8

# Check health
try {
    $resp = Invoke-WebRequest -Uri "http://127.0.0.1:5050/api/health" -UseBasicParsing -TimeoutSec 5
    $body = $resp.Content | ConvertFrom-Json
    Write-Host "[HEALTH] status=$($body.status) server_running=$($body.checks.server_running) brain=$($body.checks.brain_initialized)"
} catch {
    Write-Host "[HEALTH] Failed: $_"
}

# Also check if process is alive
$running = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
if ($running) {
    Write-Host "[OK] Server_AGI process still alive (PID=$($proc.Id))"
} else {
    Write-Host "[WARN] Server_AGI process died, exit code=$($proc.ExitCode)"
}

Write-Host "[DONE] Launch script complete"