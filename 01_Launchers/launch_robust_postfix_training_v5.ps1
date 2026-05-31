# Robust v5 launcher - Iteration on v4 success for repeatable 50k+ BTCUSDm (and other) runs
# Key upgrades based on v4 analysis (reached 30k+ steps thanks to OOS+conservative PPO+launcher):
# - Even stronger conservative hyperparams + auto-fallback tiers for reward-hardened env (negative ep_rew)
# - Retry logic with exponential backoff + param relaxation on early exit / non-completion
# - Enhanced diagnostics (KL, losses via improved callback; health signals for monitor TUI/supervisor)
# - Fixed redirection + full crash + partial artifact save guarantee
# - MT5/VecMonitor warnings suppressed at source (code fixes in train_drl)
# - Integration hooks for Current Training Run Monitor (monitor_tui.py, progress_writer health)
# - Pre-flight checks, log tail on exit, auto-suggest next if stalls
# - CPU forcing + torch threads + no TF opt for stability/speed
#
# NEW (Reward Scale & Signal Improvement for v5/v6): support lighter penalty profiles to avoid "do nothing" collapse
# from hardened DD(8.0)+costs+TradingReward while preserving gates (realized equity metrics, not training rew).
# See full battle-tested recipes + rationale (tied directly to v4 30k-step ep_rew_mean=-1.8e3) in:
#   logs/reward_scaling_playbook.md   (3 copy-paste profiles: early_stability_light, medium_ramp, full_hardened)
#
# Quick usage (set before launch):
#   $env:AGI_REWARD_PROFILE="light"; $env:AGI_REWARD_SCALE="0.08"   # early 10-20k steps (tames -1800 scale)
#   $env:AGI_PENALTY_SCALE="0.5"; $env:AGI_REWARD_SCALE="0.20"      # medium ramp
#   (omit or "hardened" for final 50k+ fine-tune — the default)
# These are read by TradingEnv + TradingReward at construction (see drl/trading_env.py + Python/rewards/reward_function.py).
# Defaults always = full hardened (1.0). VecNormalize still active.
# CRITICAL: PromotionGates and model_evaluator remain on real backtest equity metrics — unchanged.
#
# Usage: .\scripts\launch_robust_postfix_training_v5.ps1 -Symbol BTCUSDm -Timesteps 50000
# Or for recovery: same, it will auto-retry on failure.
# Diagnostic short run under light: $env:AGI_REWARD_PROFILE="light"; $env:AGI_REWARD_SCALE="0.08"; .\scripts\... -Timesteps 8000

param(
    [string]$Symbol = "BTCUSDm",
    [int]$Timesteps = 50000,
    [bool]$EnableTimeframeOpt = $false,
    [int]$MaxAttempts = 3
)

$ErrorActionPreference = "Stop"
Set-Location "C:\supreme-chainsaw"

$py = ".\.venv312\Scripts\python.exe"
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$baseLog = "logs\robust_v5_${Symbol}_$timestamp"
$log = "$baseLog.log"
$tempPy = "temp_robust_v5_$timestamp.py"

Write-Host "=== ROBUST POST-FIX TRAINING v5 (ITERATION ON v4 SUCCESS) ===" -ForegroundColor Cyan
Write-Host "Symbol: $Symbol | Target Timesteps: $Timesteps | MaxAttempts: $MaxAttempts"
Write-Host "Focus: Turn 30k+ survival into reliable full run (OOS+conservative+recovery)"
Write-Host ""

# Conservative env (v4 baseline + v5 stronger tiers)
$env:CUDA_VISIBLE_DEVICES = ""
$env:TORCH_USE_CUDA_DSA = "0"

function Run-TrainingAttempt {
    param([int]$Attempt, [hashtable]$PpoOverrides)
    
    $attemptLog = "$baseLog.attempt$Attempt.log"
    $attemptTemp = "temp_robust_v5_${timestamp}_a$Attempt.py"
    
    # Tiered conservative params (start strict, relax only if needed for KL/reward scale issues)
    $lr = if ($PpoOverrides.LR) { $PpoOverrides.LR } else { if ($Attempt -eq 1) { "3e-5" } elseif ($Attempt -eq 2) { "1e-5" } else { "5e-5" } }
    $targetKl = if ($PpoOverrides.TargetKL) { $PpoOverrides.TargetKL } else { if ($Attempt -eq 1) { "0.05" } elseif ($Attempt -eq 2) { "0.08" } else { "0.12" } }
    $nSteps = if ($PpoOverrides.NSteps) { $PpoOverrides.NSteps } else { if ($Attempt -eq 1) { "8192" } else { "4096" } }
    
    $env:AGI_PPO_LEARNING_RATE = $lr
    $env:AGI_PPO_TARGET_KL = $targetKl
    $env:AGI_PPO_N_STEPS = $nSteps
    $env:AGI_TRAINING_TIMESTEPS = "$Timesteps"
    
    Write-Host "Attempt $Attempt/$MaxAttempts | LR=$lr | target_kl=$targetKl | n_steps=$nSteps | log=$attemptLog" -ForegroundColor Yellow

    $pythonCode = @"
import os, sys, traceback, torch, time
os.environ['PYTHONUNBUFFERED'] = '1'
os.environ['CUDA_VISIBLE_DEVICES'] = ''
torch.set_num_threads(4)

print('=== V5 START (attempt=$Attempt) ===', flush=True)
print(f'PyTorch CPU mode: {torch.cuda.is_available()}', flush=True)
print(f'PPO overrides active: LR={os.environ.get("AGI_PPO_LEARNING_RATE")}, target_kl={os.environ.get("AGI_PPO_TARGET_KL")}, n_steps={os.environ.get("AGI_PPO_N_STEPS")}', flush=True)

try:
    from training.enhanced_train_drl import EnhancedTrainingPipeline
    print('[1] Import OK', flush=True)

    os.environ['AGI_TRAINING_TIMESTEPS'] = '$Timesteps'
    pipeline = EnhancedTrainingPipeline(config_path=None)
    print('[2] Pipeline created', flush=True)

    print('[3] Starting training call (direct + per-symbol + no-TF-opt)...', flush=True)
    results = pipeline.run_training_with_timeframe_optimization(
        symbols=['$Symbol'],
        enable_timeframe_opt=$EnableTimeframeOpt,
        enable_per_symbol_metrics=True,
    )
    print('[4] Training returned successfully', flush=True)
    print(results, flush=True)
    print('=== V5 DONE (SUCCESS) ===', flush=True)

except Exception:
    print('=== V5 CRASH on attempt $Attempt ===', flush=True)
    traceback.print_exc()
    sys.exit(2)

"@
    $pythonCode | Out-File -FilePath $attemptTemp -Encoding UTF8 -Force

    # Reliable capture (v4 improvement preserved + attempt isolation)
    cmd /c "`"$py`" -u `"$attemptTemp`" 1> `"$attemptLog`" 2>&1"
    $exitCode = $LASTEXITCODE

    if (Test-Path $attemptLog) {
        Get-Content $attemptLog -Tail 30 | ForEach-Object { Write-Host $_ }
    }

    # Quick health check via monitor hooks / log patterns
    $completed = $false
    if (Test-Path $attemptLog) {
        $content = Get-Content $attemptLog -Raw
        if ($content -match "V5 DONE \(SUCCESS\)") { $completed = $true }
        if ($content -match "step=$Timesteps") { $completed = $true }
    }

    if ($exitCode -eq 0 -and $completed) {
        Write-Host "Attempt $Attempt: SUCCESS" -ForegroundColor Green
        return @{ Success = $true; Log = $attemptLog }
    } else {
        Write-Host "Attempt $Attempt: exited $exitCode (may need fallback or partial recovery)" -ForegroundColor Red
        # Check for partial artifacts
        if (Test-Path "models\latest_run\latest_model.zip") {
            Write-Host "  Partial model artifacts present (latest_run) - can resume manually." -ForegroundColor Yellow
        }
        return @{ Success = $false; Log = $attemptLog; Exit = $exitCode }
    }
}

# Pre-flight: coordinate with monitor (run once snapshot if available)
Write-Host "Pre-flight: snapshot via monitor_tui (if rich installed)..." -ForegroundColor Gray
try {
    & $py -u scripts\monitor_tui.py --once 2>$null | Out-String -Stream | Select-Object -Last 20
} catch { Write-Host "  (monitor snapshot skipped or rich not ready)" }

$lastResult = $null
for ($i=1; $i -le $MaxAttempts; $i++) {
    $lastResult = Run-TrainingAttempt -Attempt $i -PpoOverrides @{}
    if ($lastResult.Success) {
        break
    }
    if ($i -lt $MaxAttempts) {
        $backoff = [math]::Pow(2, $i)
        Write-Host "Backing off $backoff seconds before fallback attempt..." -ForegroundColor DarkYellow
        Start-Sleep -Seconds $backoff
    }
}

if ($lastResult -and $lastResult.Success) {
    Write-Host "`n=== V5 OVERALL: SUCCESS on attempt (see $log) ===" -ForegroundColor Green
    Write-Host "Next: Review models/registry/candidates/ + run monitor_tui or promote." -ForegroundColor Cyan
} else {
    Write-Host "`n=== V5 OVERALL: DID NOT REACH FULL SUCCESS (see attempts) ===" -ForegroundColor Red
    Write-Host "Recommendations (from v4 analysis):" -ForegroundColor Yellow
    Write-Host "  - Reward too punitive? (ep_rew_mean ~-1800): consider lighter drawdown_penalty in drl config or reward_function"
    Write-Host "  - Check latest_run/ for partial model + resume logic"
    Write-Host "  - Launch monitor: .\.venv312\Scripts\python.exe scripts\monitor_tui.py"
    Write-Host "  - Or lower timesteps / use Optuna disable + manual tune AGI_* envs"
    Write-Host "  - Full log tails in $baseLog*.log"
}

if (Test-Path $log) {
    # Aggregate last attempt to main log for convenience
    Copy-Item $lastResult.Log -Destination $log -Force -ErrorAction SilentlyContinue
}
Write-Host "Primary log: $log"
Write-Host "Ready for next launch or monitor coordination." -ForegroundColor Cyan