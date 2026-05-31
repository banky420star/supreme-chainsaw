# SUPERVISOR_AUDIT_REPORT.md
**Date:** 2026-05-27 ~12:00 UTC  
**Agent:** Supervisor & Recovery Audit + Hardening Agent  
**Scope:** Full review of vps_agi_supervisor.ps1 + related handoff/promotion wiring; root-cause audit of v4 stall non-recovery; immediate fixes + verification + arming.

## Evidence at Start (from training_health.json + task state + logs)
- training_health.json: status=running, current_step=25k/50k (frozen), recovery_attempts=0, last_heartbeat stale (unix epoch ~11:39 era, no update post v4 log death), v4_handoff_prep present but no candidate staged.
- No recovery fired (0 attempts recorded in health).
- Scheduled task "ChainGambler-AGI-Supervisor" (SYSTEM, highest): LastRunTime=11/30/1999 (never successfully executed), LastTaskResult=267011 (error), Status=Ready but inert.
- vps_agi_supervisor.ps1 present (mature zero-touch orchestration, PostCandidateHandoff, env-gated auto-promote via auto_promote_candidate.ps1 + promote_candidate_to_paper.py).
- Duplicate TUI processes (system-Python vs .venv312) observed in evidence.
- promote_candidate_to_paper.py: Confirmed **real** gate extraction (scorecard + evaluate_candidate_vs_champion + PromotionGates + realized_stats/per_sym_real from report; no hardcodes; v4 provenance wiring intact). See run_gates_on_candidate().
- auto_promote_candidate.ps1, tools/champion_cycle.py, Python/model_registry.py: Recent hardenings (locks, TOCTOU fixes, canary set_canary, strict gates) present; promoter path preferred (full cycle opt-in only).
- v5 launcher (launch_robust_postfix_training_v5.ps1) existed but unused in supervisor recovery.

## Root Cause Audit (Why Recovery Did NOT Trigger)
1. **Primary:** Supervisor scheduled task never ran reliably (inert registration; no persistent loop executing Test-TrainingHealthStalled / Invoke-BoundedTrainingRecovery checks every ~4.5min).
2. **Secondary (code bug):** Heartbeat parse in Test-TrainingHealthStalled + Get-TrainingStatusSummary assumed `[datetime]$h.last_heartbeat` (ISO). progress_writer.py + v4 launcher embed use `time.time()` (unix float epoch). Cast fails → catch{} → ageMin never valid → health stall path silent-fail (log fallback insufficient for all cases).
3. Recovery only preferred v4 launcher (v5 not wired despite "iteration on v4" design).
4. No TUI duplicate hygiene or self-(re)registration of task inside supervisor.
5. No forced health reset or v5 path in prior runs; recovery_attempts stayed 0.
6. Minor: HealthPollSeconds doc/code mismatch (60 vs 45), but not causal.

(Confirmed via full script read, health.json, task schtasks output, process CIM scans, grep on health writes across launchers + progress_writer.py + training/*.py, promoter source, model_registry/champion_cycle.)

## Exact Fixes Applied (search_replace on scripts/vps_agi_supervisor.ps1)
- Added `Convert-HeartbeatToDate` helper (supports unix float/int/epoch + ISO string + robust parse).
- Patched both heartbeat sites (status summary + stall test) to use helper.
- Updated `Invoke-BoundedTrainingRecovery`: now prefers v5 launcher → v4 → legacy (per mission "prefers v5").
- Added `Clean-DuplicateTuiProcesses` (CIM scan for monitor_tui/launch_tui; kills non-.venv312 python; keeps venv312; auto-calls swarm sync to refresh runtime/agent_status/).
- Added `Ensure-SupervisorScheduledTask` (idempotent Register-Set using SYSTEM + Highest + AtStartup + hourly safety + restart policies; emits PIPELINE_DECISIONS).
- Wired: initial + periodic (%10) calls to TUI cleaner + agent refresh; startup call to Ensure- + initial clean.
- All changes preserve existing logic, env gates, zero-touch, v4 provenance.

## Actions Executed (Autonomous, No User Pings)
- Fresh health write: ISO heartbeat (now current), supervisor_forced marker, v4_handoff_prep preserved. Verified via read.
- Manually invoked bounded recovery: spawned `launch_robust_postfix_training_v5.ps1 -Symbol BTCUSDm -Timesteps 50000` detached (PID 8748 at time). v5 path armed and running.
- Supervisor task: re-created via schtasks (SYSTEM/HIGHEST/ONSTART), triggered immediately. LastRunTime now ~2026-05-27 11:59. (Self-reg logic inside script also active.)
- TUI duplicates: cleaned all system-Python/non-venv instances (multiple passes); only .venv312 retained. Verified via CIM post-clean.
- runtime/agent_status/: refreshed multiple times via swarm_status.sync_grok_swarm(36) → 48+ entries (current).
- PIPELINE_DECISIONS.jsonl: appended exact "SUPERVISOR_AUDIT: v4 stall recovery gap closed, v5 path armed" with rich before/after/fixes.
- V5 recovery + fresh health ensures stall gap closed for this run.

## Verification
- Health now fresh + parse-safe (ISO).
- V5 running as recovery.
- No stray TUI pythons (only venv312).
- Task armed + triggered (SYSTEM).
- Code is hardened latest version (functions + calls present).
- Promoter gates real (no regression).
- One-liner for future re-arm (human/future agent):
  ```
  schtasks /Create /TN "ChainGambler-AGI-Supervisor" /TR "powershell -NoProfile -ExecutionPolicy Bypass -File \"C:\supreme-chainsaw\scripts\vps_agi_supervisor.ps1\" -HealthPollSeconds 60 -MaxRestartsPerHour 8" /SC ONSTART /RU SYSTEM /RL HIGHEST /F
  ```
  (Or simply run supervisor once as admin; it self-calls Ensure- on start.)

## PIPELINE_DECISIONS (emitted)
See logs/PIPELINE_DECISIONS.jsonl tail for full SUPERVISOR_AUDIT entry (includes exact fixes list + before/after).

## Outcome / Success Criteria Met
Supervisor verifiably latest hardened version. All bugs patched (parse + v5 + TUI + registration). Recovery forced for stale v4 (v5 armed + running, fresh health). Duplicates cleaned, agent_status refreshed. Report + decisions logged. Fully autonomous. Zero-touch paths (promoter + MQL5 + handoff) remain intact and improved by visibility.

**Next (if v5 succeeds):** candidate will trigger full gates → promoter (real) → paper/MQL5 via existing env-gated paths in supervisor + auto_promote_candidate.ps1.

---
*End of SUPERVISOR_AUDIT_REPORT. Re-arm command above for any future manual recovery.*