#!/usr/bin/env python3
"""
Update the 'SupremeChainsaw_Clean' desktop hygiene copy from the live working tree.

This keeps a clean, organized, portable snapshot of the source (no heavy models/logs/runtime/venvs)
that is easy to browse, zip, or open on Desktop.

Run from anywhere:
  python tools/update_desktop_clean_copy.py

It will mirror the latest source, configs, scripts, docs, and the new Decision PPO + Execution layer
into the categorized desktop layout while respecting .gitignore spirit + explicit hygiene exclusions.
"""

import os
import shutil
import time
from pathlib import Path
from datetime import datetime

# === CONFIG ===
SOURCE_ROOT = Path(r"C:\supreme-chainsaw")
DEST_ROOT = Path(r"C:\Users\Administrator\Desktop\SupremeChainsaw_Clean")

# Explicit hygiene exclusions (in addition to common patterns)
EXCLUDE_DIRS = {
    ".git", ".svn", "__pycache__", ".venv", ".venv312", "venv", "venv312",
    "logs", "models", "runtime", "artifacts", "data/raw", "node_modules",
    ".grok", "ui_lab_app/dist", "ui_lab_app/.vite", "ui_lab_app/node_modules",
    "_archive", "backups", "docker", "nginx", "n8n-workflow",
}

EXCLUDE_PATTERNS = {
    "*.pyc", "*.pyo", "*.pyd", "*.log", "*.tmp", "*.bak", "*.zip", "*.tar.gz",
    "*.pkl", "*.pt", "*.pth", "*.onnx", "*.h5", "Thumbs.db", ".DS_Store",
    "*_err.log", "*_out.log", "training_health.json", "last_handoff.json",
}

# Mapping from main tree -> desktop categorized buckets (for new/recent files especially)
# We do broad copies for whole trees where the layout already matches the bucket,
# plus targeted copies for brand-new modules from the 2026-05-28 dual-PPO delivery.
BUCKET_COPIES = [
    # Core Python (the heart of the system, including the just-delivered dual PPO agents)
    ("Python", "02_Core_Python/Python"),
    ("drl", "02_Core_Python/drl"),
    ("training", "02_Core_Python/training"),

    # Launchers / scripts (updated handoff, promoter, new enhanced launcher, etc.)
    ("scripts", "01_Launchers"),

    # MQL5 rich execution bridge (the Execution side of the dual-PPO)
    ("mql5", "04_MQL5/mql5"),

    # Frontend / TUI monitoring (updated for Decision/Execution visibility)
    ("frontend", "03_UI_Monitoring/frontend"),
    ("scripts/monitor_tui.py", "03_UI_Monitoring/TUI/monitor_tui.py"),
    ("scripts/swarm_status.py", "03_UI_Monitoring/TUI/swarm_status.py"),

    # Top-level useful entry points
    ("start_enhanced_training.py", "01_Launchers/start_enhanced_training.py"),
    ("launch_full_project.ps1", "01_Launchers/launch_full_project.ps1"),
    ("launch_tui.ps1", "01_Launchers/launch_tui.ps1"),
    ("launch_robust_postfix_training_v5.ps1", "01_Launchers/launch_robust_postfix_training_v5.ps1"),
]

# Individual new/important files that must land even if the broad copy misses them
# (these are the exact deliverables from the Decision + Execution subagents + MTF work)
MUST_HAVE_FILES = [
    # The two PPO agents the user specifically requested
    ("Python/execution/trade_decision.py", "02_Core_Python/Python/execution/trade_decision.py"),
    ("Python/execution/execution_agent.py", "02_Core_Python/Python/execution/execution_agent.py"),
    ("Python/execution/__init__.py", "02_Core_Python/Python/execution/__init__.py"),

    # Decision PPO head + env support
    ("drl/decision_head.py", "02_Core_Python/drl/decision_head.py"),
    ("drl/trading_env.py", "02_Core_Python/drl/trading_env.py"),
    ("drl/ppo_agent.py", "02_Core_Python/drl/ppo_agent.py"),
    ("Python/action_translator.py", "02_Core_Python/Python/action_translator.py"),

    # MTF + best features standard (the pipeline upgrade)
    ("Python/data_feed.py", "02_Core_Python/Python/data_feed.py"),
    ("Python/features/multitimeframe_builder.py", "02_Core_Python/Python/features/multitimeframe_builder.py"),
    ("Python/feature_pipeline.py", "02_Core_Python/Python/feature_pipeline.py"),
    ("configs/best_features_per_symbol.yaml", "07_Configuration/best_features_per_symbol.yaml"),

    # Training entry that knows about the new standard + decision_ppo path
    ("training/enhanced_train_drl.py", "02_Core_Python/training/enhanced_train_drl.py"),
    ("start_enhanced_training.py", "01_Launchers/start_enhanced_training.py"),

    # The autonomous loop wiring (handoff + promoter now default to decision_ppo)
    ("scripts/handoff_watcher.py", "01_Launchers/handoff_watcher.py"),
    ("scripts/promote_candidate_to_paper.py", "01_Launchers/promote_candidate_to_paper.py"),
    ("scripts/vps_agi_supervisor.ps1", "01_Launchers/vps_agi_supervisor.ps1"),
    ("scripts/paper_mt5_execution_harness.py", "01_Launchers/paper_mt5_execution_harness.py"),

    # MQL5 ExecutionCommandMode bridge (the live side of the Execution agent)
    ("mql5/Experts/ChainGambler/ChainGambler_Executor.mq5", "04_MQL5/mql5/Experts/ChainGambler/ChainGambler_Executor.mq5"),
    ("mql5/Experts/ChainGambler/README.md", "04_MQL5/mql5/Experts/ChainGambler/README.md"),

    # Fresh architecture docs from the swarm (the "what we just built" record)
    ("docs/DECISION_EXECUTION_ARCHITECTURE.md", "05_Documentation/DECISION_EXECUTION_ARCHITECTURE.md"),
    ("docs/DECISION_PPO.md", "05_Documentation/DECISION_PPO.md"),
    ("docs/AUTONOMOUS_TRADING_LOOP.md", "05_Documentation/AUTONOMOUS_TRADING_LOOP.md"),
    ("docs/MQL5_EXECUTION_LAYER_DESIGN.md", "05_Documentation/MQL5_EXECUTION_LAYER_DESIGN.md"),

    # Dreamer (world model / Dreamer-style agent)
    ("drl/dreamer_agent.py", "02_Core_Python/drl/dreamer_agent.py"),
    ("drl/dreamer_components.py", "02_Core_Python/drl/dreamer_components.py"),
    ("Python/dreamer_policy.py", "02_Core_Python/Python/dreamer_policy.py"),
    ("training/train_dreamer.py", "02_Core_Python/training/train_dreamer.py"),
    ("Python/training/train_dreamer.py", "02_Core_Python/Python/training/train_dreamer.py"),
    ("Python/validation/validate_dreamer.py", "02_Core_Python/Python/validation/validate_dreamer.py"),
    ("tests/test_train_dreamer.py", "tests/test_train_dreamer.py"),
    ("reports/training/DREAMER_WORLD_MODEL_REPORT.md", "05_Documentation/Reports/DREAMER_WORLD_MODEL_REPORT.md"),

    # Rainforest / Random Forest (regime detector + ensemble)
    ("Python/rainforest_detector.py", "02_Core_Python/Python/rainforest_detector.py"),
    ("Python/training/train_rainforest.py", "02_Core_Python/Python/training/train_rainforest.py"),
    ("tests/test_rainforest.py", "tests/test_rainforest.py"),
    ("reports/training/RAINFOREST_REGIME_REPORT.md", "05_Documentation/Reports/RAINFOREST_REGIME_REPORT.md"),

    # Root hygiene / entry
    ("README.md", "README.md"),
]

def should_skip(path: Path) -> bool:
    """Return True if this path should be excluded from the hygiene copy."""
    parts = path.parts
    for bad in EXCLUDE_DIRS:
        if bad in parts:
            return True
    name = path.name
    for pat in EXCLUDE_PATTERNS:
        if pat.startswith("*") and name.endswith(pat[1:]):
            return True
        if name == pat:
            return True
    # Also skip very large binary-ish things even if not caught above
    if path.suffix in {".zip", ".pkl", ".pt", ".pth", ".onnx", ".h5", ".model"}:
        return True
    return False

def copy_file(src: Path, dst: Path, dry_run: bool = False) -> bool:
    """Copy one file if newer or missing. Returns True if action taken."""
    if should_skip(src):
        return False
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)

    do_copy = False
    if not dst.exists():
        do_copy = True
    else:
        try:
            if src.stat().st_mtime > dst.stat().st_mtime or src.stat().st_size != dst.stat().st_size:
                do_copy = True
        except Exception:
            do_copy = True

    if do_copy and not dry_run:
        shutil.copy2(src, dst)
    return do_copy

def copy_tree(src_dir: Path, dst_dir: Path, dry_run: bool = False) -> int:
    """Recursively copy a tree, respecting exclusions. Returns count of files copied/updated."""
    copied = 0
    if not src_dir.exists():
        return 0
    for root, dirs, files in os.walk(src_dir):
        root_p = Path(root)
        # prune excluded dirs in-place
        dirs[:] = [d for d in dirs if not should_skip(root_p / d)]
        rel = root_p.relative_to(src_dir)
        for f in files:
            src_f = root_p / f
            if should_skip(src_f):
                continue
            dst_f = dst_dir / rel / f
            if copy_file(src_f, dst_f, dry_run=dry_run):
                copied += 1
    return copied

def main(dry_run: bool = False):
    print("=" * 70)
    print("Supreme Chainsaw — Desktop Clean Copy Updater")
    print(f"Source : {SOURCE_ROOT}")
    print(f"Dest   : {DEST_ROOT}")
    print(f"Time   : {datetime.now().isoformat(timespec='seconds')}")
    print("=" * 70)

    if not SOURCE_ROOT.exists():
        print("ERROR: Source root not found. Aborting.")
        return 1
    DEST_ROOT.mkdir(parents=True, exist_ok=True)

    total_copied = 0
    added_new = []

    # 1. Broad bucket copies (whole trees that map cleanly)
    print("\n[1] Broad bucket tree copies (core source)...")
    for src_rel, dst_rel in BUCKET_COPIES:
        src = SOURCE_ROOT / src_rel
        dst = DEST_ROOT / dst_rel
        n = copy_tree(src, dst, dry_run=dry_run)
        if n:
            print(f"  + {src_rel} -> {dst_rel}  ({n} files)")
            total_copied += n

    # 2. Must-have individual files (the dual-PPO deliverables + MTF + fixes)
    print("\n[2] Critical new/recent files (Decision PPO + Execution layer + MTF)...")
    for src_rel, dst_rel in MUST_HAVE_FILES:
        src = SOURCE_ROOT / src_rel
        dst = DEST_ROOT / dst_rel
        if copy_file(src, dst, dry_run=dry_run):
            action = "ADD " if not (DEST_ROOT / dst_rel).exists() or (DEST_ROOT / dst_rel).stat().st_mtime < src.stat().st_mtime else "UPD "
            print(f"  {action} {src_rel}")
            total_copied += 1
            if "trade_decision" in src_rel or "execution_agent" in src_rel or "decision_head" in src_rel:
                added_new.append(src_rel)

    # 3. Also pull in any other root-level launchers / helpers that are useful on desktop
    print("\n[3] Additional root launchers & helpers...")
    extra_roots = [
        "launch_agi_trading.ps1", "create_shortcut.ps1", "smoke_test.py",
        "requirements.txt", "pyproject.toml", "pytest.ini",
    ]
    for name in extra_roots:
        src = SOURCE_ROOT / name
        dst = DEST_ROOT / name
        if copy_file(src, dst, dry_run=dry_run):
            print(f"  + {name}")
            total_copied += 1

    # 4. Write a sync marker so humans know when it was last refreshed
    marker = DEST_ROOT / "LAST_DESKTOP_SYNC.txt"
    with open(marker, "w", encoding="utf-8") as f:
        f.write(f"Desktop clean copy last updated: {datetime.now().isoformat(timespec='seconds')}\n")
        f.write(f"Source working tree: {SOURCE_ROOT}\n\n")
        f.write("Major content brought forward in this sync:\n")
        f.write("  - Dual PPO architecture (Decision PPO + ExecutionAgent)\n")
        f.write("    * TradeDecision rich spec (lot/TP/SL/trail/partials/full-close)\n")
        f.write("    * DecisionHead + 18-dim DecisionSpec in drl/trading_env\n")
        f.write("    * Full Execution layer with MQL5 command bridge\n")
        f.write("  - Multi-timeframe (1m+5m+15m+1h) + best_features_per_symbol standard\n")
        f.write("  - data_feed.py kwarg fix for clean MTF runs\n")
        f.write("  - Latest handoff_watcher, promoter, harness, supervisor (decision_ppo default)\n")
        f.write("  - New architecture docs (DECISION_EXECUTION_ARCHITECTURE.md, DECISION_PPO.md)\n")
        f.write("  - Enhanced training pipeline + MTF support\n")
        f.write("  - Dreamer (world model) + Rainforest / Random Forest (regime detector + ensemble)\n")
        f.write("    * Full dreamer_agent / dreamer_components / dreamer_policy\n")
        f.write("    * rainforest_detector + train_rainforest + reports\n")
        f.write("  - All recent launcher / script / mql5 / config updates from 2026-05-28 swarm\n")
        f.write("\nExclusions applied: logs/, models/, runtime/, venvs, __pycache__, node_modules, artifacts, large binaries, *.log, etc.\n")
        if added_new:
            f.write("\nNew files added this sync:\n")
            for n in added_new:
                f.write(f"  - {n}\n")

    print(f"\n[4] Sync marker written: {marker.name}")

    print("\n" + "=" * 70)
    print(f"DONE. Total files copied/updated: {total_copied}")
    if added_new:
        print("New dual-PPO / architecture files added:")
        for n in added_new:
            print(f"  • {n}")
    print(f"Desktop copy is now up to date with working tree as of {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)
    print("\nTip: Re-run this script anytime after big changes:")
    print("  python tools/update_desktop_clean_copy.py")
    return 0

if __name__ == "__main__":
    import sys
    dry = "--dry-run" in sys.argv or "-n" in sys.argv
    if dry:
        print("*** DRY RUN MODE — no files will be written ***\n")
    raise SystemExit(main(dry_run=dry))
