#!/usr/bin/env python3
"""
SupremeChainsaw Unified Launcher
---------------------------------
Starts and maintains the full stack:
  1. Python API backend (bottle on port 5050)
  2. React frontend (vite dev-server on port 4180, or serve built files)
  3. Optional: run a training cycle
  4. Monitors all processes and restarts them if they die

Usage:
    python supreme_launcher.py              # Start full stack (backend + frontend)
    python supreme_launcher.py --backend    # Start only backend
    python supreme_launcher.py --frontend   # Start only frontend
    python supreme_launcher.py --train      # Start backend + run training
    python supreme_launcher.py --status     # Check status of running processes
    python supreme_launcher.py --stop       # Stop all running processes
"""

import os
import sys
import json
import time
import signal
import socket
import subprocess
import threading
import atexit
from pathlib import Path
from datetime import datetime, timezone

# ── Paths ─────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
BACKEND_DIR = PROJECT_ROOT / "02_Core_Python"
FRONTEND_DIR = PROJECT_ROOT / "03_UI_Monitoring" / "frontend"
FRONTEND_BUILD_DIR = FRONTEND_DIR / "dist"
LOG_DIR = PROJECT_ROOT / "logs"
PID_DIR = PROJECT_ROOT / ".pids"

BACKEND_PORT = 5050
FRONTEND_PORT = 4180

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(PID_DIR, exist_ok=True)

# ── Pidfile helpers ───────────────────────────────────────────────
def _write_pid(name: str, pid: int):
    Path(PID_DIR / f"{name}.pid").write_text(str(pid))

def _read_pid(name: str) -> int | None:
    path = PID_DIR / f"{name}.pid"
    if path.exists():
        try:
            return int(path.read_text().strip())
        except (ValueError, OSError):
            return None
    return None

def _remove_pid(name: str):
    path = PID_DIR / f"{name}.pid"
    if path.exists():
        path.unlink()

def _is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False

def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0

# ── Logging ───────────────────────────────────────────────────────
def log(msg: str, level: str = "INFO"):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] [{level}] {msg}", flush=True)
    try:
        with open(LOG_DIR / "launcher.log", "a", encoding="utf-8") as f:
            f.write(f"[{ts}] [{level}] {msg}\n")
    except Exception:
        pass


# ── Process Management ────────────────────────────────────────────
class ManagedProcess:
    """A subprocess that gets automatically restarted if it dies."""

    def __init__(self, name: str, args: list[str], cwd: str | Path,
                 env: dict | None = None, max_restarts: int = 10,
                 restart_delay: float = 2.0):
        self.name = name
        self.args = args
        self.cwd = Path(cwd)
        self.env = os.environ.copy()
        if env:
            self.env.update(env)
        self.max_restarts = max_restarts
        self.restart_delay = restart_delay
        self.process: subprocess.Popen | None = None
        self.restart_count = 0
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"proc-{self.name}")
        self._thread.start()

    def _run(self):
        while not self._stop_event.is_set() and self.restart_count < self.max_restarts:
            try:
                log(f"Starting {self.name}: {' '.join(str(a) for a in self.args)}", "INFO")
                self.process = subprocess.Popen(
                    self.args,
                    cwd=str(self.cwd),
                    env=self.env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                _write_pid(self.name, self.process.pid)
                log(f"{self.name} started (PID {self.process.pid})", "SUCCESS")

                # Stream output
                for line in self.process.stdout or []:
                    if self._stop_event.is_set():
                        break
                    line = line.rstrip("\n")
                    if line:
                        log(f"[{self.name}] {line}", "DEBUG")

                # Wait for process to finish
                self.process.wait()
                retcode = self.process.returncode
                _remove_pid(self.name)

                if self._stop_event.is_set():
                    log(f"{self.name} stopped by user", "INFO")
                    break

                self.restart_count += 1
                log(f"{self.name} exited (code {retcode}). "
                    f"Restart {self.restart_count}/{self.max_restarts} in {self.restart_delay}s", "WARNING")
                time.sleep(self.restart_delay)

            except Exception as e:
                log(f"{self.name} error: {e}", "ERROR")
                self.restart_count += 1
                time.sleep(self.restart_delay)

        if self.restart_count >= self.max_restarts:
            log(f"{self.name} reached max restarts ({self.max_restarts}). Giving up.", "CRITICAL")

    def stop(self, timeout: float = 10.0):
        self._stop_event.set()
        if self.process and self.process.poll() is None:
            log(f"Stopping {self.name} (PID {self.process.pid})...", "INFO")
            self.process.terminate()
            try:
                self.process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                log(f"{self.name} didn't terminate, killing...", "WARNING")
                self.process.kill()
                self.process.wait()
        _remove_pid(self.name)
        log(f"{self.name} stopped", "INFO")

    def is_alive(self) -> bool:
        return self.process is not None and self.process.poll() is None


# ── Backend Server ────────────────────────────────────────────────
def start_backend() -> ManagedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{BACKEND_DIR}{os.pathsep}{env.get('PYTHONPATH', '')}"
    env["AGI_AUTONOMY_TRAIN"] = "false"  # Don't auto-train on startup
    
    proc = ManagedProcess(
        name="backend",
        args=[sys.executable, "-c", """
import sys
sys.path.insert(0, '02_Core_Python')
from Python.api_server import app
import bottle
bottle.run(app, host='127.0.0.1', port=5050, quiet=False, server='wsgiref')
"""],
        cwd=PROJECT_ROOT,
        env=env,
        max_restarts=5,
    )
    return proc


# ── Frontend ──────────────────────────────────────────────────────
def start_frontend() -> ManagedProcess:
    # Check if we should serve built files or run dev server
    if FRONTEND_BUILD_DIR.exists() and (FRONTEND_BUILD_DIR / "index.html").exists():
        log("Found built frontend, serving static files...", "INFO")
        # Use a simple Python HTTP server to serve the built files
        env = os.environ.copy()
        proc = ManagedProcess(
            name="frontend",
            args=[sys.executable, "-m", "http.server", str(FRONTEND_PORT),
                  "--directory", str(FRONTEND_BUILD_DIR)],
            cwd=PROJECT_ROOT,
            env=env,
            max_restarts=5,
        )
        return proc
    else:
        # Run Vite dev server
        log("Starting Vite dev server...", "INFO")
        env = os.environ.copy()
        # Set VITE_API_URL to point to our backend
        env["VITE_API_URL"] = f"http://localhost:{BACKEND_PORT}"
        
        npx_path = None
        for candidate in ["npx", "npx.cmd", Path(FRONTEND_DIR) / "node_modules" / ".bin" / "vite"]:
            try:
                subprocess.run([candidate, "--version"], capture_output=True, timeout=5)
                npx_path = candidate
                break
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        
        if npx_path and "vite" not in str(npx_path):
            proc = ManagedProcess(
                name="frontend",
                args=[npx_path, "vite", "--port", str(FRONTEND_PORT), "--host", "127.0.0.1"],
                cwd=FRONTEND_DIR,
                env=env,
                max_restarts=5,
            )
        else:
            # No build and no Vite binary — show helpful error and exit
            log('ERROR: No frontend build found. Run: cd ' + str(FRONTEND_DIR) + ' && npm run build', 'CRITICAL')
            log('ERROR: Also ensure npx is available for Vite dev server', 'CRITICAL')
            return None
        return proc


# ── Status & Cleanup ──────────────────────────────────────────────
def status():
    """Check and display status of all managed processes."""
    components = ["backend", "frontend"]
    print(f"\n{'='*50}")
    print(f" SupremeChainsaw Stack Status")
    print(f"{'='*50}")
    
    for name in components:
        pid = _read_pid(name)
        if pid and _is_pid_alive(pid):
            print(f"  ✓ {name:15s} running (PID {pid})")
        elif pid:
            print(f"  ✗ {name:15s} PID {pid} exists but process is dead (stale pidfile)")
        else:
            print(f"  ○ {name:15s} not running")
    
    print()
    for name, port in [("Backend API", BACKEND_PORT), ("Frontend UI", FRONTEND_PORT)]:
        if _port_in_use(port):
            print(f"  ✓ {name:15s} port {port} in use")
        else:
            print(f"  ○ {name:15s} port {port} free")
    
    print(f"{'='*50}\n")


def stop_all():
    """Stop all managed processes."""
    for name in ["frontend", "backend"]:
        pid = _read_pid(name)
        if pid and _is_pid_alive(pid):
            log(f"Stopping {name} (PID {pid})...", "INFO")
            try:
                os.kill(pid, signal.SIGTERM)
                time.sleep(1)
                if _is_pid_alive(pid):
                    os.kill(pid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                pass
        _remove_pid(name)
    log("All processes stopped", "SUCCESS")


# ── Main ──────────────────────────────────────────────────────────
def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="SupremeChainsaw Unified Launcher")
    parser.add_argument("--backend", action="store_true", help="Start only backend")
    parser.add_argument("--frontend", action="store_true", help="Start only frontend")
    parser.add_argument("--train", action="store_true", help="Run training after starting")
    parser.add_argument("--status", action="store_true", help="Check status")
    parser.add_argument("--stop", action="store_true", help="Stop all processes")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild frontend before starting")
    
    args = parser.parse_args()
    
    if args.stop:
        stop_all()
        return
    
    if args.status:
        status()
        return
    
    # Rebuild frontend if requested
    if args.rebuild:
        log("Rebuilding frontend...", "INFO")
        subprocess.run(
            ["npx", "vite", "build"],
            cwd=str(FRONTEND_DIR),
            capture_output=True,
            timeout=60,
        )
        log("Frontend rebuilt", "SUCCESS")
    
    # Determine what to start
    start_back = args.backend or not args.frontend
    start_front = args.frontend or not args.backend
    
    processes = []
    
    if start_back:
        log("Starting backend API server...", "INFO")
        proc = start_backend()
        proc.start()
        processes.append(proc)
        time.sleep(2)  # Give backend time to start
    
    if start_front:
        log("Starting frontend...", "INFO")
        proc = start_frontend()
        if proc:
            proc.start()
            processes.append(proc)
        else:
            log("Frontend not started - run 'npm run build' in 03_UI_Monitoring/frontend first", "WARNING")
    
    # Run training if requested
    if args.train:
        log("Starting training cycle...", "INFO")
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{BACKEND_DIR}{os.pathsep}{env.get('PYTHONPATH', '')}"
        env["AGI_LSTM_SYMBOLS"] = "EURUSD"
        subprocess.Popen(
            [sys.executable, "training/train_lstm.py"],
            cwd=str(BACKEND_DIR),
            env=env,
        )
    
    # Show URLs
    time.sleep(1)
    print(f"\n{'='*50}")
    print(f" SupremeChainsaw Stack")
    print(f"{'='*50}")
    print(f"  Backend API:  http://localhost:{BACKEND_PORT}/api/status")
    print(f"  Frontend UI:  http://localhost:{FRONTEND_PORT}")
    print(f"  Logs:         {LOG_DIR / 'launcher.log'}")
    print(f"{'='*50}")
    print(f"  Press Ctrl+C to stop all processes")
    print(f"{'='*50}\n")
    
    # Keep alive until Ctrl+C
    try:
        while True:
            time.sleep(1)
            # Check if any process died
            for p in processes:
                if not p.is_alive():
                    log(f"{p.name} is no longer alive", "WARNING")
    except KeyboardInterrupt:
        print()
        log("Shutting down...", "INFO")
    finally:
        for p in processes:
            p.stop()
        stop_all()
        log("All processes stopped gracefully", "SUCCESS")


if __name__ == "__main__":
    main()
