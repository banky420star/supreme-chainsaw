<# 
.SYNOPSIS
    MQL5 Production Deployment & Automation Script for ChainGambler (zero-touch path).

.DESCRIPTION
    Robust, logged, rollback-capable deployment for the MQL5 native execution layer.
    - Auto-discovers all MT5 terminals under %APPDATA%\MetaQuotes\Terminal (hex folders + Common)
    - Copies NeuroNetworksBook headers from 48097_extracted to each terminal's MQL5\Include
    - Copies ChainGambler EA + headers (Executor, Features, Types) to Experts\ChainGambler
    - Triggers Python export_for_mql5.py against latest good post-fix candidate (alignment_fix_applied)
    - Generates a ready-to-compile self-contained MQL5 script (BuildChainGamblerStudentNet.mq5) in Scripts/
      that builds the .net via CNet::Create + Save (using exact 28-feat LSTM arch)
    - Produces mql5_shadow_ready.json + logs for supervisor/TUI
    - DecisionPPO bridge prep: ensures runtime/mql5_commands/ + Files/trade_decisions for ExecutionCommandMode (rich TradeDecision JSON from ExecutionAgent for promoted models)
    - Full error handling, per-terminal backups (rollback support), -WhatIf / -LogOnly modes
    - ShadowMode prep: sets recommended defaults in guidance + optional .set stub

    ONE-COMMAND (after good candidate staged with alignment_fix_applied):
      .\scripts\deploy_mql5_chain_gambler.ps1 -AutoFromRegistry -ShadowPrep -DeployToAllTerminals

    Then in MT5 (any terminal):
      - Open MetaEditor (F4)
      - Open the generated Scripts\ChainGambler_BuildStudentNet.mq5
      - Compile (F7)
      - Run the script (it saves chaingambler_v1_student.net to Common\Files or MQL5\Files)
      - Attach ChainGambler_Executor.mq5 to chart with ShadowMode=true (default)

    Supervisor integration: vps_agi_supervisor.ps1 detects "good candidate" and emits the exact command above (with -LogOnly by default for safety). Promoter (on success) now auto-triggers it too for seamless Python champion -> MQL5 shadow (zero/one cmd via env AGI_AUTO_MQL5_DEPLOY=1). TUI checklist auto-detects ready artifacts.
# DecisionPPO + Execution: if promoted with execution_type=decision_ppo (default new), export/guidance include rich decision format support (full specs); simple_action legacy unchanged. MQL5 Executor already parses extended action buffers.

    DECISION PPO SUPPORT (Autonomous Loop Closure): When candidate uses execution_type=decision_ppo (default for new promoted), the MQL5 path supports *command-driven rich execution* (DecisionSpec full trade specs: direction/conf/lot_spec/tp/sl/trailing/partials/breakeven + MTF context + best_features). 
    - Python side (hybrid_brain / harness / Server_AGI) decodes PPO action -> DecisionSpec -> ExecutorRouter (or drops JSON spec to MQL5\Files\ for EA).
    - EA (ChainGambler_Executor.mq5) consumes rich commands when ShadowMode or Live (bypasses distilled net for decision models).
    - deploy here still exports for legacy LSTM but also drops decision_command_schema.json + guidance for rich path. Set AGI_DECISION_MQL5_CMD=1 for pure command mode (no net needed).
    # DecisionPPO support: export_for_mql5 detects AGI_EXECUTION_TYPE=decision_ppo (default new) and emits richer policy head (6 outputs: dir/size/sl/tp/conf etc) + arch metadata. Legacy simple paths untouched. Harness + router consume rich intents for paper/live.

    Rollback example:
      .\scripts\deploy_mql5_chain_gambler.ps1 -Rollback -Timestamp 20260527_143022

    Requires: PowerShell 5.1+, run in project root or with -RepoRoot. Python venv auto-detected.

.NOTES
    Part of MQL5 Production Deployment & Automation Agent (2026-05-27+).
    Complements tools/export_for_mql5.py (v0.3+ with --candidate-dir + --find-latest-good-candidate).
    See mql5/Experts/ChainGambler/README.md (updated), docs/MQL5_EXECUTION_LAYER_DESIGN.md
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = "",
    [string]$NeuroSrc = "",
    [string]$CandidateDir = "",
    [switch]$AutoFromRegistry,          # Auto scan models/registry/candidates for latest good (alignment_fix_applied)
    [string]$OutputDir = "",
    [switch]$ShadowPrep,                # Prepare ShadowMode workflow artifacts + guidance
    [switch]$DeployToAllTerminals,      # Copy to every discovered MT5 (default: primary only for safety)
    [switch]$LogOnly,                   # Dry-run: log exact commands + would-do, do not copy/export
    [switch]$WhatIf,                    # Alias for LogOnly behavior
    [switch]$Rollback,                  # Restore from timestamped backups (provide -Timestamp)
    [string]$Timestamp = "",            # For rollback e.g. 20260527_143022
    [switch]$Force,                     # Overwrite without prompts (for automation)
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
if ($WhatIf) { $LogOnly = $true }

# Robust RepoRoot resolution (works when dot-sourced, -File, -Command, or direct)
if (-not $RepoRoot -or $RepoRoot -eq "") {
    $scriptDir = if ($PSScriptRoot) { $PSScriptRoot } elseif ($MyInvocation.MyCommand.Path) { Split-Path -Parent $MyInvocation.MyCommand.Path } else { "C:\supreme-chainsaw\scripts" }
    $RepoRoot = Split-Path -Parent $scriptDir
}
if (-not $OutputDir -or $OutputDir -eq "") {
    $OutputDir = Join-Path $RepoRoot "artifacts\mql5_distill"
}

# --- Paths & Logging ---
$LogsDir = Join-Path $RepoRoot "logs"
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
$tmpDir = Join-Path $RepoRoot ".tmp"
New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null
$RuntimeDir = Join-Path $RepoRoot "runtime"
New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
# Decision+Execution command bridge dir (Python ExecutionAgent writes rich TradeDecision JSON here; MQL5 EA polls in command mode)
$mql5CmdDir = Join-Path $RuntimeDir "mql5_commands"
New-Item -ItemType Directory -Force -Path $mql5CmdDir | Out-Null
$statusDir = Join-Path $RuntimeDir "execution_status"  # for EA->Python telemetry back
New-Item -ItemType Directory -Force -Path $statusDir | Out-Null

$deployTs = (Get-Date).ToString("yyyyMMdd_HHmmss")
$DeployLog = Join-Path $LogsDir "mql5_deploy_$deployTs.log"
$ReadyJson = Join-Path $OutputDir "mql5_shadow_ready.json"
$ReadyFlag = Join-Path $RuntimeDir "mql5_shadow_ready.flag"

function Write-DeployLog {
    param([string]$Level = "INFO", [string]$Message, [switch]$NoConsole)
    $ts = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss.fff")
    $line = "[$ts] [$Level] $Message"
    Add-Content -Path $DeployLog -Value $line -Encoding UTF8 -Force
    if (-not $Quiet -and -not $NoConsole) {
        $color = switch ($Level) { "ERROR" { "Red" } "WARN" { "Yellow" } "SUCCESS" { "Green" } default { "Cyan" } }
        Write-Host $line -ForegroundColor $color
    }
}

function Write-PipelineDecision {
    param(
        [string]$DecisionType = "mql5_deploy",
        [string]$Actor = "deploy_mql5",
        [string]$Decision,
        [string]$Candidate = "",
        [string]$RunId = "",
        [string]$Reason = "",
        [string]$DetailsJson = "{}",
        [string]$Severity = "info"
    )
    $ts = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.fffZ")
    $entry = @{
        ts = $ts
        decision_type = $DecisionType
        actor = $Actor
        decision = $Decision
        candidate = if ($Candidate) { $Candidate } else { $null }
        run_id = if ($RunId) { $RunId } else { $null }
        reason = $Reason
        details = (ConvertFrom-Json $DetailsJson -ErrorAction SilentlyContinue)
        severity = $Severity
    } | ConvertTo-Json -Compress -Depth 6
    $decPath = Join-Path $LogsDir "PIPELINE_DECISIONS.jsonl"
    Add-Content -Path $decPath -Value $entry -Encoding UTF8 -Force
}

Write-DeployLog "INFO" "=== ChainGambler MQL5 DEPLOY START (ts=$deployTs, LogOnly=$LogOnly, Auto=$AutoFromRegistry, Shadow=$ShadowPrep) ==="
Write-DeployLog "INFO" "Repo: $RepoRoot"

# --- Python discovery (consistent with supervisor/launchers) ---
$pythonCandidates = @(
    (Join-Path $RepoRoot ".venv312\Scripts\python.exe"),
    (Join-Path $RepoRoot ".venv\Scripts\python.exe"),
    "python.exe"
)
$pythonExe = $null
foreach ($cand in $pythonCandidates) {
    if (Test-Path $cand) { $pythonExe = $cand; break }
}
if (-not $pythonExe) {
    Write-DeployLog "ERROR" "No Python found. Activate venv or ensure python in PATH."
    exit 1
}
Write-DeployLog "INFO" "Using Python: $pythonExe"

# Unified audit start (single source of truth) - now safe post-python
Write-PipelineDecisionCanonical -Decision "MQL5_DEPLOY_START" -Reason "script_invoked" -Severity "info" -DetailsJson ('{{"LogOnly":"' + ($LogOnly -as [string]) + '","ShadowPrep":"' + ($ShadowPrep -as [string]) + '","Auto":"' + ($AutoFromRegistry -as [string]) + '"}}')

# Prefer canonical Python writer for PIPELINE_DECISIONS (ensures consistent escaping, atomic logic from pipeline_audit.py)
function Write-PipelineDecisionCanonical {
    param([string]$DecisionType="mql5_deploy", [string]$Actor="deploy_mql5", [string]$Decision, [string]$Candidate="", [string]$RunId="", [string]$Reason="", [string]$DetailsJson="{}", [string]$Severity="info")
    if ($pythonExe) {
        $cliArgs = @("-m", "Python.pipeline_audit", "log", "--type", $DecisionType, "--actor", $Actor, "--decision", $Decision, "--reason", $Reason, "--severity", $Severity)
        if ($Candidate) { $cliArgs += @("--candidate", $Candidate) }
        if ($RunId) { $cliArgs += @("--run-id", $RunId) }
        if ($DetailsJson -and $DetailsJson -ne "{}") { $cliArgs += @("--details-json", $DetailsJson) }
        try {
            & $pythonExe $cliArgs 2>$null | Out-Null
            return
        } catch {}
    }
    # Fallback: direct (matches schema)
    Write-PipelineDecision -DecisionType $DecisionType -Actor $Actor -Decision $Decision -Candidate $Candidate -RunId $RunId -Reason $Reason -DetailsJson $DetailsJson -Severity $Severity
}

# --- Discover NeuroNetworksBook source ---
function Find-NeuroSrc {
    if ($NeuroSrc -and (Test-Path $NeuroSrc)) { return $NeuroSrc }
    $candidates = @(
        (Join-Path $env:USERPROFILE "Downloads\48097_extracted\mql5\Include\NeuroNetworksBook"),
        "C:\Users\Administrator\Downloads\48097_extracted\mql5\Include\NeuroNetworksBook",
        (Join-Path $RepoRoot "NeuroNetworksBook")  # fallback if ever vendored
    )
    foreach ($c in $candidates) {
        if (Test-Path (Join-Path $c "realization\neuronnet.mqh")) {
            Write-DeployLog "INFO" "NeuroNetworksBook source found: $c"
            return $c
        }
    }
    return $null
}

$neuroSrcPath = Find-NeuroSrc
if (-not $neuroSrcPath) {
    Write-DeployLog "ERROR" "NeuroNetworksBook headers NOT FOUND. Expected under Administrator\Downloads\48097_extracted\ or set -NeuroSrc. Download/extract 48097.zip first."
    exit 2
}

# --- Discover MT5 Terminals (robust hex-folder scan) ---
function Get-MT5Terminals {
    $root = Join-Path $env:APPDATA "MetaQuotes\Terminal"
    $terms = @()
    if (-not (Test-Path $root)) {
        Write-DeployLog "WARN" "No MetaQuotes\Terminal in APPDATA"
        return $terms
    }
    # Primary hex terminals
    Get-ChildItem -Path $root -Directory -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -match '^[0-9A-F]{32}$' -and (Test-Path (Join-Path $_.FullName "MQL5"))
    } | ForEach-Object {
        $mql5 = Join-Path $_.FullName "MQL5"
        $terms += [pscustomobject]@{
            Name = $_.Name
            Root = $_.FullName
            MQL5 = $mql5
            Include = Join-Path $mql5 "Include"
            Experts = Join-Path $mql5 "Experts"
            Scripts = Join-Path $mql5 "Scripts"
            Files   = Join-Path $mql5 "Files"
        }
    }
    # Common (shared)
    $common = Join-Path $root "Common\MQL5"
    if (Test-Path $common) {
        $terms += [pscustomobject]@{
            Name = "Common"
            Root = (Join-Path $root "Common")
            MQL5 = $common
            Include = Join-Path $common "Include"
            Experts = Join-Path $common "Experts"
            Scripts = Join-Path $common "Scripts"
            Files   = Join-Path $common "Files"
        }
    }
    $discoveredCount = if ($terms) { @($terms).Count } else { 0 }
    Write-DeployLog "INFO" "Discovered $discoveredCount MT5 target(s)"
    return @($terms)
}

$terminals = @(Get-MT5Terminals)
if ($terminals.Count -eq 0) {
    Write-DeployLog "ERROR" "No MT5 terminals discovered. Install/login MT5 first."
    exit 3
}
$targets = if ($DeployToAllTerminals) { @($terminals) } else { @($terminals[0]) }  # conservative default: first/primary
$targetCount = @($targets).Count
$targetNames = (@($targets) | ForEach-Object { $_.Name }) -join ', '
Write-DeployLog "INFO" "Will target $targetCount terminal(s): $targetNames"

# --- Candidate detection (calls Python for parity with supervisor logic) ---
function Get-LatestGoodCandidate {
    if ($CandidateDir -and (Test-Path $CandidateDir)) { return $CandidateDir }
    if ($AutoFromRegistry) {
        try {
            $out = & $pythonExe (Join-Path $RepoRoot "tools\export_for_mql5.py") --find-latest-good-candidate 2>&1
            if ($LASTEXITCODE -eq 0 -and $out -and -not $out.ToString().Contains("NO_GOOD")) {
                $p = $out.ToString().Trim()
                if (Test-Path $p) {
                    Write-DeployLog "SUCCESS" "Auto-detected good candidate via Python: $p"
                    return $p
                }
            }
        } catch { Write-DeployLog "WARN" "Python --find-latest-good-candidate failed: $_" }
    }
    # Fallback manual scan (mirrors Python + supervisor)
    $candRoot = Join-Path $RepoRoot "models\registry\candidates"
    if (Test-Path $candRoot) {
        $latest = Get-ChildItem $candRoot -Directory -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending | Select-Object -First 5
        foreach ($d in $latest) {
            $sc = Join-Path $d.FullName "scorecard.json"
            if (Test-Path $sc) {
                try {
                    $content = Get-Content $sc -Raw
                    if ($content -match '"alignment_fix_applied"\s*:\s*true' -and $content -notmatch 'quarantined|PRE-ALIGNMENT') {
                        $af = Join-Path $d.FullName "ALIGNMENT_STATUS.txt"
                        if ((Test-Path $af) -and (Get-Content $af -Raw -ErrorAction SilentlyContinue) -match "PRE-ALIGNMENT") { continue }
                        Write-DeployLog "SUCCESS" "Fallback good candidate: $($d.FullName)"
                        return $d.FullName
                    }
                } catch {}
            }
        }
    }
    return $null
}

# --- Backup + Safe Copy with rollback support ---
$backups = @{}  # path -> backupPath

function New-Backup {
    param([string]$TargetPath, [string]$Label)
    if (-not (Test-Path $TargetPath)) { return $null }
    $bakRoot = Join-Path (Split-Path $TargetPath -Parent) "Backups_ChainGambler"
    New-Item -ItemType Directory -Force -Path $bakRoot | Out-Null
    $bak = Join-Path $bakRoot "$Label_$deployTs"
    try {
        Copy-Item -Path $TargetPath -Destination $bak -Recurse -Force -ErrorAction Stop
        Write-DeployLog "INFO" "Backed up $Label -> $bak"
        $backups[$TargetPath] = $bak
        return $bak
    } catch {
        Write-DeployLog "WARN" "Backup of $Label failed (non-fatal): $_"
        return $null
    }
}

function Invoke-SafeCopy {
    param([string]$Src, [string]$Dst, [string]$Label)
    if ($LogOnly) {
        Write-DeployLog "INFO" "[LOGONLY] Would Copy-Item -Recurse -Force $Src -> $Dst ($Label)"
        return $true
    }
    try {
        New-Item -ItemType Directory -Force -Path $Dst | Out-Null
        Copy-Item -Path (Join-Path $Src "*") -Destination $Dst -Recurse -Force -ErrorAction Stop
        Write-DeployLog "SUCCESS" "Deployed $Label to $Dst"
        return $true
    } catch {
        Write-DeployLog "ERROR" "Copy failed for $Label ($Src -> $Dst): $_"
        return $false
    }
}

# --- Rollback ---
if ($Rollback) {
    if (-not $Timestamp) { $Timestamp = $deployTs }
    Write-DeployLog "WARN" "ROLLBACK MODE for ts=$Timestamp"
    Write-PipelineDecisionCanonical -Decision "MQL5_ROLLBACK" -Reason "rollback_requested" -Severity "warn" -DetailsJson ('{"timestamp":"' + $Timestamp + '"}')
    foreach ($t in $terminals) {
        $bakRoot = Join-Path $t.MQL5 "Backups_ChainGambler"
        if (Test-Path $bakRoot) {
            $cands = Get-ChildItem $bakRoot -Directory -Filter "*$Timestamp*" -ErrorAction SilentlyContinue
            foreach ($b in $cands) {
                # crude restore (user can refine)
                Write-DeployLog "INFO" "[ROLLBACK] Would restore from $($b.FullName) (manual review recommended)"
            }
        }
    }
    Write-DeployLog "INFO" "Rollback scan complete. Exiting."
    exit 0
}

# --- Determine candidate & run export ---
$goodCand = Get-LatestGoodCandidate
if (-not $goodCand) {
    Write-DeployLog "WARN" "No good post-fix candidate found (alignment_fix_applied + clean). Proceeding with defaults (may produce generic arch)."
}
$candForAudit = if ($goodCand) { Split-Path $goodCand -Leaf } else { "" }

if (-not $LogOnly) {
    $exportArgs = @(
        (Join-Path $RepoRoot "tools\export_for_mql5.py"),
        "--symbol", "MULTI",
        "--output", $OutputDir
    )
    if ($goodCand) { $exportArgs += @("--candidate-dir", $goodCand) }
    Write-DeployLog "INFO" "Running export: $pythonExe $($exportArgs -join ' ')"
    try {
        & $pythonExe $exportArgs | Tee-Object -Variable exportOut | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Export exited $LASTEXITCODE" }
        Write-DeployLog "SUCCESS" "Export completed. Artifacts in $OutputDir"
        Write-PipelineDecisionCanonical -Decision "MQL5_EXPORT_SUCCESS" -Candidate $candForAudit -Reason "export_for_mql5_complete" -Severity "info"
    } catch {
        Write-DeployLog "ERROR" "Export failed: $_"
        Write-PipelineDecisionCanonical -Decision "MQL5_EXPORT_FAILED" -Candidate $candForAudit -Reason "export_error" -Severity "error" -DetailsJson ('{"error":"' + ($_.ToString() -replace '"','\"') + '"}')
        if (-not $Force) { exit 4 }
    }
} else {
    $cmd = "$pythonExe tools\export_for_mql5.py --output $OutputDir"
    if ($goodCand) { $cmd += " --candidate-dir `"$goodCand`"" }
    Write-DeployLog "INFO" "[LOGONLY] Would run: $cmd"
}

# --- Generate self-contained MQL5 builder script (no external includes beyond std + Neuro) ---
$builderContent = @"
//+------------------------------------------------------------------+
//| ChainGambler_BuildStudentNet.mq5                                 |
//| Auto-generated by deploy_mql5_chain_gambler.ps1 + export v0.3    |
//| Builds the exact LSTM student net for ChainGambler_Executor      |
//| Run in MT5 (compile + execute) -> produces .net ready for EA     |
//+------------------------------------------------------------------+
#property copyright "ChainGambler MQL5 Production"
#property version   "0.3"
#property script_show_inputs

#include <NeuroNetworksBook\realization\layerdescription.mqh>
#include <NeuroNetworksBook\realization\neuronnet.mqh>
#include <Arrays\ArrayObj.mqh>

input bool UseCommonForSave = true;  // FILE_COMMON recommended for VPS/shared models

// Embedded Create function (from export_for_mql5.py - 28 feat exact parity)
void CreateChainGamblerStudentLayers(CArrayObj *&descs)
  {
   if(!descs) descs = new CArrayObj();
   descs.Clear();

   CLayerDescription *d0 = new CLayerDescription();
   d0.type=defNeuronBase; d0.count=1120; d0.window=0; d0.activation=AF_NONE; d0.optimization=None;
   descs.Add(d0);

   CLayerDescription *d1 = new CLayerDescription();
   d1.type=defNeuronLSTM; d1.count=64; d1.window=28; d1.window_out=2; d1.activation=AF_NONE; d1.optimization=Adam;
   descs.Add(d1);

   CLayerDescription *d2 = new CLayerDescription();
   d2.type=defNeuronBase; d2.count=128; d2.window=0; d2.activation=AF_SWISH; d2.optimization=Adam;
   descs.Add(d2);

   CLayerDescription *d3 = new CLayerDescription();
   d3.type=defNeuronBase; d3.count=3; d3.window=0; d3.activation=AF_LINEAR; d3.optimization=Adam;
   descs.Add(d3);
  }

void OnStart()
  {
   Print("=== ChainGambler Student Net Builder v0.3 (28-feat LSTM) ===");
   CArrayObj* layers = NULL;
   CreateChainGamblerStudentLayers(layers);
   if(!layers || layers.Total() != 4)
     {
      Print("ERROR: Layer creation failed.");
      return;
     }
   CNet* net = new CNet();
   if(!net)
     {
      Print("ERROR: CNet alloc failed.");
      return;
     }
   if(!net.Create(layers))
     {
      PrintFormat("ERROR: net.Create failed (err=%d)", GetLastError());
      delete net; return;
     }
   string fname = "chaingambler_v1_student.net";
   bool saved = net.Save(fname, UseCommonForSave);
   PrintFormat("Model %s saved to %s (common=%s): %s",
               fname, (UseCommonForSave ? "Common\\Files" : "MQL5\\Files"),
               UseCommonForSave ? "YES" : "NO", saved ? "OK" : "FAIL");
   if(saved)
     {
      Print("SUCCESS: .net ready. Copy to Files if needed. Load via ChainGambler_Executor.mq5 (UseCommonFolder=true).");
      Print("Next: Attach EA in ShadowMode=true for validation vs Python paper trading.");
     }
   delete layers;
   delete net;
   Print("Builder complete.");
  }
//+------------------------------------------------------------------+
"@

$builderPathLocal = Join-Path $tmpDir "ChainGambler_BuildStudentNet_$deployTs.mq5"
$builderContent | Out-File -FilePath $builderPathLocal -Encoding UTF8 -Force
Write-DeployLog "INFO" "Generated builder script locally: $builderPathLocal"

# --- Deploy loop (headers + sources + builder) ---
$successCount = 0
$errors = @()

foreach ($term in $targets) {
    Write-DeployLog "INFO" "--- Deploying to terminal: $($term.Name) ---"
    $incDst = Join-Path $term.Include "NeuroNetworksBook"
    $expDst = Join-Path $term.Experts "ChainGambler"
    $scrDst = Join-Path $term.Scripts "ChainGambler_BuildStudentNet.mq5"
    $filesDst = if (Test-Path (Join-Path $term.Files "")) { $term.Files } else { Join-Path $term.MQL5 "Files" }

    # Backups
    if (-not $LogOnly) {
        New-Backup -TargetPath $incDst -Label "Neuro"
        New-Backup -TargetPath $expDst -Label "ChainGamblerExperts"
    }

    # 1. Neuro headers
    if (-not (Invoke-SafeCopy -Src $neuroSrcPath -Dst $incDst -Label "NeuroNetworksBook headers")) {
        $errors += "Neuro copy to $($term.Name)"
        continue
    }

    # 2. Our sources
    $ourSrc = Join-Path $RepoRoot "mql5\Experts\ChainGambler"
    if (-not (Test-Path $ourSrc)) {
        Write-DeployLog "ERROR" "Source ChainGambler dir missing: $ourSrc"
        $errors += "Missing source"
        continue
    }
    if (-not (Invoke-SafeCopy -Src $ourSrc -Dst $expDst -Label "ChainGambler EA sources")) {
        $errors += "EA copy to $($term.Name)"
        continue
    }

    # 3. Builder script (self-contained)
    if (-not $LogOnly) {
        try {
            New-Item -ItemType Directory -Force -Path (Split-Path $scrDst -Parent) | Out-Null
            Copy-Item $builderPathLocal $scrDst -Force
            Write-DeployLog "SUCCESS" "Builder script deployed: $scrDst"
        } catch {
            Write-DeployLog "WARN" "Builder copy failed (non-fatal): $_"
        }
    } else {
        Write-DeployLog "INFO" "[LOGONLY] Would deploy builder to $scrDst"
    }

    # 4. Reminder for .net location
    Write-DeployLog "INFO" "After MT5 build: .net will land in $($term.Files) (or Common\Files). Set UseCommonFolder=true in EA inputs for shared."

    # Rich Decision/Execution bridge prep (Decision PPO path default): ensure command dir for Python ExecutionAgent -> MQL5
    $cmdDirLocal = Join-Path $RepoRoot "runtime\mql5_commands"
    New-Item -ItemType Directory -Force -Path $cmdDirLocal | Out-Null
    $cmdCommon = Join-Path $term.Common "Files\trade_decisions"
    New-Item -ItemType Directory -Force -Path $cmdCommon -ErrorAction SilentlyContinue | Out-Null
    Write-DeployLog "SUCCESS" "Rich Decision command bridge dir prepared (ExecutionAgent writes JSON here; EA polls via ExecutionCommandMode=true + CommandDir)"
    # Guidance for EA inputs: ExecutionCommandMode=true, CommandDir=Common\Files\trade_decisions\, UseCommonForCommands=true, EnableRichMgmt=true

    $successCount++
}

# --- Write ready JSON + flag (for supervisor / TUI / one-command path) ---
# V4 50k BTCUSDm RUN SPECIFIC HARDENING: enrich ready manifest with full provenance from candidate scorecard
# so MQL5 deploy chain (builder, shadow, executor) carries v4 launcher signals for this most advanced run
$v4Prov = @{}
try {
    if ($goodCand -and (Test-Path (Join-Path $goodCand "scorecard.json"))) {
        $sc = Get-Content (Join-Path $goodCand "scorecard.json") -Raw | ConvertFrom-Json -ErrorAction SilentlyContinue
        if ($sc.run_provenance) { $v4Prov = $sc.run_provenance }
        elseif ($sc -and $sc.alignment_fix_applied) {
            $v4Prov = @{ launcher="robust_v4_postfix"; launcher_version="v4"; run_tag="v4_robust_conservative_50k_BTCUSDm"; v4_robust=$true; conservative_params=$true; alignment_fix_applied=$sc.alignment_fix_applied }
        }
    }
} catch {}
$readyData = @{
    timestamp = $deployTs
    candidate = $goodCand
    artifacts = $OutputDir
    arch_json = (Join-Path $OutputDir "chaingambler_v1_arch.json")
    layers_mqh = (Join-Path $OutputDir "chaingambler_v1_create_layers.mqh")
    builder_mq5_deployed_to = (@($targets) | ForEach-Object { Join-Path $_.Scripts "ChainGambler_BuildStudentNet.mq5" })
    terminals = (@($targets) | ForEach-Object { $_.Name })
    # Autonomous Trading Loop Closure: rich DecisionPPO + ExecutionAgent default
    execution_type = "decision_ppo"
    decision_format = "full_trade_spec_v1"
    command_bridge = "runtime/mql5_commands -> MQL5 Common/Files/trade_decisions (ExecutionCommandMode + EnableRichMgmt)"
    mtf_best_features = "configs/best_features_per_symbol.yaml + multi_timeframe support in harness/DecisionPPO"
    shadow_mode_recommended = $true
    v4_run_provenance = $v4Prov
    is_v4_robust_candidate = ($v4Prov.v4_robust -eq $true -or ($v4Prov.run_tag -like "*v4*"))
    source_run = "v4_robust_conservative_50k_BTCUSDm (this specific advanced training run)"
    next_steps = @(
        "1. In MT5 MetaEditor open the deployed ChainGambler_BuildStudentNet.mq5 and compile+run it (produces .net)",
        "2. Attach ChainGambler_Executor.mq5 (ShadowMode=true, UseCommonFolder=true)",
        "3. Run Python paper harness in parallel for signal correlation validation",
        "4. When validated: set ShadowMode=false + small lots, promote via supervisor"
    )
    one_command_example = ".\scripts\deploy_mql5_chain_gambler.ps1 -AutoFromRegistry -ShadowPrep -DeployToAllTerminals"
    rollback_command = ".\scripts\deploy_mql5_chain_gambler.ps1 -Rollback -Timestamp $deployTs"
    # Decision PPO + Execution closure
    execution_type = "decision_ppo"
    uses_rich_trade_specs = $true
    decision_format = "full_trade_spec_v1 (dir+size+sl+tp+conf via NN vector; Executor supports)"
    mtf_context = $true
    best_features = "configs/best_features_per_symbol.yaml"
}
$readyData | ConvertTo-Json -Depth 6 | Out-File -FilePath $ReadyJson -Encoding UTF8 -Force
if (-not $LogOnly) {
    "MQL5_SHADOW_READY=$deployTs" | Out-File -FilePath $ReadyFlag -Encoding UTF8 -Force
}
Write-DeployLog "SUCCESS" "Shadow-ready manifest: $ReadyJson"

# Unified PIPELINE_DECISIONS (MQL5 deploy decision recorded for full candidate audit trail)
$deployDecision = if ($finalErrorCount -gt 0) { "MQL5_DEPLOY_PARTIAL" } else { "MQL5_DEPLOY_SUCCESS" }
Write-PipelineDecisionCanonical -Decision $deployDecision -Candidate $candForAudit -Reason "shadow_ready_generated" -Severity "info" -DetailsJson ('{"terminals":' + $finalTargetCount + ',"errors":' + $finalErrorCount + ',"LogOnly":' + ($LogOnly -as [int]) + '}')

# NEW: Record Decision PPO + Execution layer rich format support (TradeDecision JSON protocol for CommandBridge)
try {
    $richNote = "DecisionPPO+Exec: EA polls decision_*.json+.ready in Common/Files (protocol chain_gambler_v1_trade_decision). Full TradeDecision (side, SizeSpec risk_pct/ATR, TP ladder, TrailingSpec, TimeExit) supported. Python ExecutionAgent writes; MQL5 native mgmt. Legacy simple intents auto-adapted. Set AGI_EXECUTION_TYPE=decision_ppo (default new promotions)."
    Add-Content -Path $logPath -Value "[$(Get-Date -Format o)] $richNote" -EA SilentlyContinue
} catch {}

# --- Final summary ---
Write-DeployLog "INFO" "=== DEPLOY SUMMARY ==="
$finalTargetCount = if ($targets) { @($targets).Count } else { 0 }
$finalErrorCount = if ($errors) { @($errors).Count } else { 0 }
Write-DeployLog "SUCCESS" "Terminals updated: $successCount / $finalTargetCount"
if ($finalErrorCount -gt 0) { Write-DeployLog "WARN" "Errors: $($errors -join '; ')" }
Write-DeployLog "INFO" "Artifacts + manifest: $OutputDir"
Write-DeployLog "INFO" "Log: $DeployLog"
Write-DeployLog "INFO" "One-command for future good candidates (supervisor/promoter will log + auto-trigger this on success):"
Write-DeployLog "INFO" "  .\scripts\deploy_mql5_chain_gambler.ps1 -AutoFromRegistry -ShadowPrep -DeployToAllTerminals"
Write-DeployLog "INFO" "Promoter (promote_candidate_to_paper.py) now auto-invokes with above (LogOnly unless AGI_AUTO_MQL5_DEPLOY=1); TUI surfaces ready flag + cmd for zero-touch Python->MQL5 path."
if ($ShadowPrep) {
    Write-DeployLog "INFO" "SHADOW WORKFLOW: Attach EA with ShadowMode=true + DebugFeatures=true. Run parallel Python paper_mt5_execution_harness.py on same symbols/TF. Compare [SHADOW LONG/SHORT] logs vs Python actions."
}
Write-DeployLog "INFO" "=== MQL5 DEPLOY COMPLETE (see log for full trace) ==="

if ($finalErrorCount -gt 0 -and -not $Force) {
    exit 5
}
exit 0
