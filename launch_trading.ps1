$ErrorActionPreference = "Stop"
$repoRoot = "C:\Users\Administrator\chain_gambler"

$pythonCandidates = @(
  (Join-Path $repoRoot ".venv312\Scripts\python.exe"),
  (Join-Path $repoRoot ".venv\Scripts\python.exe")
)

$pythonExe = $null
foreach ($cand in $pythonCandidates) {
  if (Test-Path $cand) {
    $pythonExe = $cand
    break
  }
}

if (-not $pythonExe) {
  # Fallback to system python
  $pythonExe = "python"
}

# Environment variables for trading
$envVars = @{
  "AGI_BIAS_STRENGTH" = "0.3"
  "AGI_LOW_VOL_MIN_ACTION" = "0.0001"
  "AGI_MED_VOL_MIN_ACTION" = "0.0001"
  "AGI_HIGH_VOL_MIN_ACTION" = "0.0001"
  "AGI_ACTION_THRESHOLD" = "0.0001"
  "AGI_TRADE_INTERVAL_SEC" = "60"
  "CANARY_MAX_LOSS_PCT" = "10"
  "AGI_LIVE_ENABLED" = "true"
  "AGI_REQUIRE_EXPLICIT_LIVE_ARM" = "false"
  "AGI_TRAIL_INTERVAL_SEC" = "15"
}

# Kill stale processes
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -like "*Server_AGI*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Start-Sleep -Seconds 2

# Start Backend
$serverEnv = @{
  "AGI_BIAS_STRENGTH" = "0.3"
  "AGI_LOW_VOL_MIN_ACTION" = "0.0001"
  "AGI_MED_VOL_MIN_ACTION" = "0.0001"
  "AGI_HIGH_VOL_MIN_ACTION" = "0.0001"
  "AGI_ACTION_THRESHOLD" = "0.0001"
  "AGI_TRADE_INTERVAL_SEC" = "60"
  "CANARY_MAX_LOSS_PCT" = "10"
  "AGI_LIVE_ENABLED" = "true"
  "AGI_REQUIRE_EXPLICIT_LIVE_ARM" = "false"
  "AGI_TRAIL_INTERVAL_SEC" = "15"
}

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $pythonExe
$psi.Arguments = "-m Python.Server_AGI"
$psi.WorkingDirectory = $repoRoot
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $false
$serverEnv["CHAIN_GAMBLER_EXECUTION_MODE"] = "paper"
$serverEnv["CHAIN_GAMBLER_ALLOW_LIVE"] = "0"
foreach ($entry in $serverEnv.GetEnumerator()) {
  $psi.EnvironmentVariables[[string]$entry.Key] = [string]$entry.Value
}
$serverProc = [System.Diagnostics.Process]::Start($psi)
Write-Host "Started AGI Server pid=$($serverProc.Id)"

# Wait for backend
Write-Host "Waiting for backend (45s)..."
Start-Sleep -Seconds 45

# Start Frontend
$frontendDir = Join-Path $repoRoot "ui_lab_app"
$npmCmd = Get-Command npm -ErrorAction SilentlyContinue
if ($npmCmd -and (Test-Path $frontendDir)) {
  $fePsi = New-Object System.Diagnostics.ProcessStartInfo
  $fePsi.FileName = "cmd.exe"
  $fePsi.Arguments = "/k cd /d `"$frontendDir`" && npx vite --host 0.0.0.0"
  $fePsi.WorkingDirectory = $frontendDir
  $fePsi.UseShellExecute = $false
  $fePsi.CreateNoWindow = $false
  $feProc = [System.Diagnostics.Process]::Start($fePsi)
  Write-Host "Started Frontend pid=$($feProc.Id)"
} else {
  Write-Host "npm not found or frontend dir missing; skipping frontend."
}

Start-Sleep -Seconds 10
Write-Host ""
Write-Host "============================================"
Write-Host " AGI Trading System is running!"
Write-Host "============================================"
Write-Host " Backend API : http://localhost:5000/api/status"
Write-Host " Frontend UI : http://localhost:4180/"
Write-Host ""

Start-Process "http://localhost:4180/"