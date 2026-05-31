<#
.SYNOPSIS
    SupremeChainsaw Full Stack Launcher with Process Monitoring & Auto-Restart.

.DESCRIPTION
    Starts and monitors the API server and React UI dashboard for the
    SupremeChainsaw autonomous trading system. Automatically restarts
    any process that crashes. Provides keyboard controls for management.

.PARAMETER RootDir
    Root directory of the SupremeChainsaw project.

.PARAMETER ApiPort
    Port for the API server (default: 5051).

.PARAMETER UiPort
    Port for the React UI (default: 4180).

.PARAMETER NoBrowser
    Skip automatically opening the browser.

.PARAMETER PaperMode
    Run in paper trading mode.
#>

param(
    [string]$RootDir = (Get-Location).Path,
    [int]$ApiPort = 5051,
    [int]$UiPort = 4180,
    [switch]$NoBrowser,
    [switch]$PaperMode
)

# ─── Constants ────────────────────────────────────────────────────────────
$API_DIR = Join-Path $RootDir "02_Core_Python"
$UI_DIR = Join-Path $RootDir "03_UI_Monitoring" "frontend"
$VENV_PYTHON = Join-Path $RootDir ".venv312" "Scripts" "python.exe"
$API_MODULE = "Python.api_server"
$API_LOG = Join-Path $RootDir "logs" "api_server.log"
$UI_LOG = Join-Path $RootDir "logs" "react_ui.log"
$LAUNCHER_LOG = Join-Path $RootDir "logs" "launcher.log"
$LOG_DIR = Join-Path $RootDir "logs"

# ─── Ensure log directory exists ─────────────────────────────────────────
if (-not (Test-Path $LOG_DIR)) { New-Item -ItemType Directory -Path $LOG_DIR -Force | Out-Null }

# ─── Global state ────────────────────────────────────────────────────────
$script:apiProcess = $null
$script:uiProcess = $null
$script:running = $false
$script:apiStartTime = $null
$script:uiStartTime = $null
$script:apiRestartCount = 0
$script:uiRestartCount = 0
$script:lastStatusUpdate = ""

# ─── Helper: Write timestamped log ───────────────────────────────────────
function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$timestamp] [$Level] $Message"
    Write-Host $line
    Add-Content -Path $LAUNCHER_LOG -Value $line -Encoding UTF8
}

# ─── Helper: Write status to console ─────────────────────────────────────
function Write-Status {
    param([string]$Message)
    $script:lastStatusUpdate = "$(Get-Date -Format 'HH:mm:ss') | $Message"
}

# ─── Start API Server ────────────────────────────────────────────────────
function Start-ApiServer {
    if (-not (Test-Path $VENV_PYTHON)) {
        Write-Log "Python virtual environment not found at $VENV_PYTHON" "ERROR"
        return $null
    }

    Write-Log "Starting API server on port $ApiPort..."

    $env:CHAIN_GAMBLER_EXECUTION_MODE = if ($PaperMode) { "paper" } else { "demo" }
    if ($PaperMode) { $env:CHAIN_GAMBLER_EXECUTION_MODE = "paper" }

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $VENV_PYTHON
    $psi.Arguments = "-m $API_MODULE --port $ApiPort"
    $psi.WorkingDirectory = $API_DIR
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $psi.EnvironmentVariables["CHAIN_GAMBLER_EXECUTION_MODE"] = if ($PaperMode) { "paper" } else { "demo" }
    $psi.EnvironmentVariables["PYTHONUNBUFFERED"] = "1"

    try {
        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $psi
        $process.Start() | Out-Null

        # Begin reading output asynchronously
        $script:apiOutReader = $process.StandardOutput
        $script:apiErrReader = $process.StandardError

        # Start background jobs to capture output
        Start-Job -ScriptBlock {
            param($reader, $logPath)
            try {
                while (-not $reader.EndOfStream) {
                    $line = $reader.ReadLine()
                    if ($line) { Add-Content -Path $logPath -Value $line -Encoding UTF8 }
                }
            } catch { }
        } -ArgumentList $script:apiOutReader, $API_LOG | Out-Null

        Start-Job -ScriptBlock {
            param($reader, $logPath)
            try {
                while (-not $reader.EndOfStream) {
                    $line = $reader.ReadLine()
                    if ($line) { Add-Content -Path $logPath -Value "[STDERR] $line" -Encoding UTF8 }
                }
            } catch { }
        } -ArgumentList $script:apiErrReader, $API_LOG | Out-Null

        Write-Log "API server started (PID: $($process.Id))"
        return $process
    }
    catch {
        Write-Log "Failed to start API server: $_" "ERROR"
        return $null
    }
}

# ─── Start React UI ──────────────────────────────────────────────────────
function Start-ReactUI {
    $nodePath = (Get-Command node -ErrorAction SilentlyContinue).Source
    if (-not $nodePath) {
        Write-Log "Node.js not found in PATH" "ERROR"
        return $null
    }

    $npmPath = (Get-Command npm -ErrorAction SilentlyContinue).Source
    $vitePath = Join-Path $UI_DIR "node_modules" ".bin" "vite"

    if (-not (Test-Path $vitePath)) {
        Write-Log "Vite not found, running npm install..."
        Push-Location $UI_DIR
        try {
            & $npmPath install 2>&1 | Add-Content -Path $UI_LOG -Encoding UTF8
        }
        finally { Pop-Location }
    }

    Write-Log "Starting React UI on port $UiPort..."

    # Configure Vite to use our port
    $env:VITE_API_PORT = $ApiPort.ToString()

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $nodePath
    $psi.Arguments = "node_modules\.bin\vite --port $UiPort --host"
    $psi.WorkingDirectory = $UI_DIR
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $psi.EnvironmentVariables["VITE_API_PORT"] = $ApiPort.ToString()
    $psi.EnvironmentVariables["PORT"] = $UiPort.ToString()

    try {
        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $psi
        $process.Start() | Out-Null

        # Background jobs to capture output
        $script:uiOutReader = $process.StandardOutput
        $script:uiErrReader = $process.StandardError

        Start-Job -ScriptBlock {
            param($reader, $logPath)
            try {
                while (-not $reader.EndOfStream) {
                    $line = $reader.ReadLine()
                    if ($line) { Add-Content -Path $logPath -Value $line -Encoding UTF8 }
                }
            } catch { }
        } -ArgumentList $script:uiOutReader, $UI_LOG | Out-Null

        Start-Job -ScriptBlock {
            param($reader, $logPath)
            try {
                while (-not $reader.EndOfStream) {
                    $line = $reader.ReadLine()
                    if ($line) { Add-Content -Path $logPath -Value "[STDERR] $line" -Encoding UTF8 }
                }
            } catch { }
        } -ArgumentList $script:uiErrReader, $UI_LOG | Out-Null

        Write-Log "React UI started (PID: $($process.Id))"
        return $process
    }
    catch {
        Write-Log "Failed to start React UI: $_" "ERROR"
        return $null
    }
}

# ─── Check if a port is in use ───────────────────────────────────────────
function Test-PortInUse {
    param([int]$Port)
    try {
        $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $Port)
        $listener.Start()
        $listener.Stop()
        return $false
    }
    catch {
        return $true
    }
}

# ─── Health check an HTTP endpoint ───────────────────────────────────────
function Test-Endpoint {
    param([string]$Url, [int]$TimeoutSeconds = 3)
    try {
        $request = [System.Net.WebRequest]::Create($Url)
        $request.Timeout = $TimeoutSeconds * 1000
        $request.Method = "GET"
        $response = $request.GetResponse()
        $response.Close()
        return $true
    }
    catch {
        return $false
    }
}

# ─── Cleanup function ────────────────────────────────────────────────────
function Stop-AllServices {
    Write-Log "Shutting down all services..."

    if ($script:uiProcess -and -not $script:uiProcess.HasExited) {
        Write-Log "Stopping React UI (PID: $($script:uiProcess.Id))..."
        try { $script:uiProcess.Kill() } catch { }
        try { $script:uiProcess.WaitForExit(5000) } catch { }
    }

    if ($script:apiProcess -and -not $script:apiProcess.HasExited) {
        Write-Log "Stopping API server (PID: $($script:apiProcess.Id))..."
        try { $script:apiProcess.Kill() } catch { }
        try { $script:apiProcess.WaitForExit(5000) } catch { }
    }

    # Kill any orphaned python processes related to our server
    Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -match "api_server"
    } | ForEach-Object {
        Write-Log "Cleaning up orphaned API process (PID: $($_.Id))..."
        try { $_.Kill() } catch { }
    }

    # Kill any orphaned node/vite processes related to our UI
    Get-Process -Name "node" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -match "vite"
    } | ForEach-Object {
        Write-Log "Cleaning up orphaned Vite process (PID: $($_.Id))..."
        try { $_.Kill() } catch { }
    }

    $script:running = $false
    Write-Log "All services stopped."
}

# ─── Display status dashboard ────────────────────────────────────────────
function Show-Status {
    Clear-Host
    Write-Host ""
    Write-Host "  ╔══════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "  ║           SUPREMECHAINSAW — SYSTEM STATUS               ║" -ForegroundColor Cyan
    Write-Host "  ╚══════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""

    # ─── API Server Status ───
    $apiStatus = "⚠ STOPPED"
    $apiColor = "Red"
    $apiUptime = "N/A"
    if ($script:apiProcess -and -not $script:apiProcess.HasExited) {
        $apiStatus = "✓ RUNNING"
        $apiColor = "Green"
        if ($script:apiStartTime) {
            $elapsed = [math]::Round(((Get-Date) - $script:apiStartTime).TotalMinutes, 1)
            $apiUptime = "$elapsed min"
        }
    }
    Write-Host "  ┌─ API Server ──────────────────────────────────────────┐" -ForegroundColor DarkGray
    Write-Host "  │ Status:    " -NoNewline; Write-Host "$apiStatus" -ForegroundColor $apiColor
    Write-Host "  │ URL:       http://localhost:$ApiPort/api/status"
    Write-Host "  │ PID:       $($script:apiProcess.Id)" -NoNewline
    Write-Host "  │ Restarts:  $($script:apiRestartCount)"
    Write-Host "  │ Uptime:    $apiUptime"
    Write-Host "  │ Responding: " -NoNewline
    if ($script:apiProcess -and -not $script:apiProcess.HasExited) {
        $responding = Test-Endpoint "http://localhost:$ApiPort/api/status" -TimeoutSeconds 2
        if ($responding) {
            Write-Host "YES" -ForegroundColor Green
        } else {
            Write-Host "WAITING..." -ForegroundColor Yellow
        }
    } else {
        Write-Host "NO" -ForegroundColor Red
    }
    Write-Host "  └───────────────────────────────────────────────────────┘" -ForegroundColor DarkGray
    Write-Host ""

    # ─── React UI Status ───
    $uiStatus = "⚠ STOPPED"
    $uiColor = "Red"
    $uiUptime = "N/A"
    if ($script:uiProcess -and -not $script:uiProcess.HasExited) {
        $uiStatus = "✓ RUNNING"
        $uiColor = "Green"
        if ($script:uiStartTime) {
            $elapsed = [math]::Round(((Get-Date) - $script:uiStartTime).TotalMinutes, 1)
            $uiUptime = "$elapsed min"
        }
    }
    Write-Host "  ┌─ React Dashboard ─────────────────────────────────────┐" -ForegroundColor DarkGray
    Write-Host "  │ Status:    " -NoNewline; Write-Host "$uiStatus" -ForegroundColor $uiColor
    Write-Host "  │ URL:       http://localhost:$UiPort"
    Write-Host "  │ PID:       $($script:uiProcess.Id)" -NoNewline
    Write-Host "  │ Restarts:  $($script:uiRestartCount)"
    Write-Host "  │ Uptime:    $uiUptime"
    Write-Host "  └───────────────────────────────────────────────────────┘" -ForegroundColor DarkGray
    Write-Host ""

    # ─── Controls ───
    Write-Host "  ┌─ Controls ────────────────────────────────────────────┐" -ForegroundColor DarkGray
    Write-Host "  │  [R] Restart all services                             │"
    Write-Host "  │  [A] Restart API server only                          │"
    Write-Host "  │  [U] Restart React UI only                            │"
    Write-Host "  │  [S] Show this status screen                          │"
    Write-Host "  │  [O] Open dashboard in browser                        │"
    Write-Host "  │  [Q] Quit and shut down everything                    │"
    Write-Host "  └───────────────────────────────────────────────────────┘" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  Last update: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor DarkGray
    Write-Host ""
}

# ─── Main monitoring loop ────────────────────────────────────────────────
function Start-Monitoring {
    $script:running = $true

    # ─── Start services ──────────────────────────────────────────────────
    $script:apiProcess = Start-ApiServer
    $script:apiStartTime = Get-Date

    Start-Sleep -Seconds 1

    $script:uiProcess = Start-ReactUI
    $script:uiStartTime = Get-Date

    # ─── Open browser after a brief delay ────────────────────────────────
    if (-not $NoBrowser) {
        $job = Start-Job -ScriptBlock {
            param($uiPort, $rootDir)
            Start-Sleep -Seconds 4
            try {
                $logPath = Join-Path $rootDir "logs" "launcher.log"
                Add-Content -Path $logPath -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Opening browser to http://localhost:$uiPort" -Encoding UTF8
                Start-Process "http://localhost:$uiPort"
            } catch { }
        } -ArgumentList $UiPort, $RootDir
    }

    # Show status initially
    Show-Status

    # ─── Main loop: monitor processes + handle keyboard input ────────────
    while ($script:running) {
        $statusChanged = $false

        # ─── Check API server health ─────────────────────────────────────
        if ($script:apiProcess) {
            if ($script:apiProcess.HasExited) {
                Write-Log "API server crashed! (Exit code: $($script:apiProcess.ExitCode)) Restarting..." "WARN"
                $script:apiRestartCount++
                $script:apiProcess.Dispose()
                $script:apiProcess = $null
                Start-Sleep -Seconds 2
                $script:apiProcess = Start-ApiServer
                $script:apiStartTime = Get-Date
                $statusChanged = $true
            }
        } else {
            Write-Log "API server not running. Starting..." "WARN"
            $script:apiProcess = Start-ApiServer
            $script:apiStartTime = Get-Date
            $statusChanged = $true
        }

        # ─── Check React UI health ───────────────────────────────────────
        if ($script:uiProcess) {
            if ($script:uiProcess.HasExited) {
                Write-Log "React UI crashed! (Exit code: $($script:uiProcess.ExitCode)) Restarting..." "WARN"
                $script:uiRestartCount++
                $script:uiProcess.Dispose()
                $script:uiProcess = $null
                Start-Sleep -Seconds 2
                $script:uiProcess = Start-ReactUI
                $script:uiStartTime = Get-Date
                $statusChanged = $true
            }
        } else {
            Write-Log "React UI not running. Starting..." "WARN"
            $script:uiProcess = Start-ReactUI
            $script:uiStartTime = Get-Date
            $statusChanged = $true
        }

        # ─── Handle keyboard input (non-blocking) ────────────────────────
        if ([Console]::KeyAvailable) {
            $key = [Console]::ReadKey($true)
            switch ($key.Key) {
                'Q' {
                    Write-Log "User requested shutdown (Q)"
                    Stop-AllServices
                    return
                }
                'R' {
                    Write-Log "User requested full restart (R)"
                    Stop-AllServices
                    Start-Sleep -Seconds 2
                    $script:apiProcess = Start-ApiServer
                    $script:apiStartTime = Get-Date
                    Start-Sleep -Seconds 1
                    $script:uiProcess = Start-ReactUI
                    $script:uiStartTime = Get-Date
                    $statusChanged = $true
                }
                'A' {
                    Write-Log "User requested API restart (A)"
                    if ($script:apiProcess -and -not $script:apiProcess.HasExited) {
                        try { $script:apiProcess.Kill() } catch { }
                        try { $script:apiProcess.WaitForExit(3000) } catch { }
                    }
                    if ($script:apiProcess) { $script:apiProcess.Dispose() }
                    $script:apiProcess = $null
                    Start-Sleep -Seconds 1
                    $script:apiProcess = Start-ApiServer
                    $script:apiStartTime = Get-Date
                    $statusChanged = $true
                }
                'U' {
                    Write-Log "User requested React UI restart (U)"
                    if ($script:uiProcess -and -not $script:uiProcess.HasExited) {
                        try { $script:uiProcess.Kill() } catch { }
                        try { $script:uiProcess.WaitForExit(3000) } catch { }
                    }
                    if ($script:uiProcess) { $script:uiProcess.Dispose() }
                    $script:uiProcess = $null
                    Start-Sleep -Seconds 1
                    $script:uiProcess = Start-ReactUI
                    $script:uiStartTime = Get-Date
                    $statusChanged = $true
                }
                'S' { $statusChanged = $true }
                'O' {
                    Write-Log "Opening browser to http://localhost:$UiPort"
                    try { Start-Process "http://localhost:$UiPort" } catch { }
                }
            }
        }

        # Refresh status display if anything changed
        if ($statusChanged) {
            Show-Status
        }

        Start-Sleep -Milliseconds 500
    }
}

# ─── Entry point ─────────────────────────────────────────────────────────
try {
    # Register cleanup on script exit
    Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action {
        Stop-AllServices
    } | Out-Null

    Start-Monitoring
}
catch {
    Write-Log "Fatal error: $_" "ERROR"
    Write-Host "`n[X] Fatal error: $_" -ForegroundColor Red
}
finally {
    Stop-AllServices
}
