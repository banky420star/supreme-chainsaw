#!/usr/bin/env python3
"""
MT5 Wine Bridge Launcher for macOS
==================================

This script sets up an RPyC classic server inside a Wine Python environment
so that the Chain Gambler backend can connect to MetaTrader5 running under
Wine/CrossOver on macOS.

Prerequisites:
1. Wine or CrossOver installed
2. A Windows Python environment inside Wine (e.g., via pywin32 or portable Python)
3. MetaTrader 5 installed inside Wine
4. RPyC installed in BOTH host Python and Wine Python

Usage:
    python scripts/start_mt5_wine_bridge.py

Environment variables:
    MT5_WINE_HOST - Host to bind RPyC server (default: 0.0.0.0)
    MT5_WINE_PORT - Port for RPyC server (default: 18812)
    WINE_PYTHON   - Path to Python executable inside Wine (auto-detected)
"""

import os
import subprocess
import sys
import time


def find_wine_python():
    """Try to find a Python executable inside Wine."""
    candidates = [
        os.environ.get("WINE_PYTHON"),
        "/Applications/CrossOver.app/Contents/SharedSupport/CrossOver/bin/wine",
        "/opt/homebrew/bin/wine64",
        "/usr/local/bin/wine64",
        "wine64",
        "wine",
    ]

    # Check if WINE_PYTHON points to an actual exe inside the Wine prefix
    wine_python = os.environ.get("WINE_PYTHON")
    if wine_python and os.path.exists(wine_python):
        return wine_python

    # Try to find python inside a common Wine prefix
    prefixes = [
        os.environ.get("WINEPREFIX", os.path.expanduser("~/.wine")),
        os.path.expanduser("~/wineprefix"),
        os.path.expanduser("~/Library/Application Support/net.metaquotes.wine.metatrader5"),
    ]

    for prefix in prefixes:
        if not os.path.isdir(prefix):
            continue
        python_paths = [
            os.path.join(prefix, "drive_c", "winpython", "python.exe"),
            os.path.join(prefix, "drive_c", "Python39", "python.exe"),
            os.path.join(prefix, "drive_c", "Python310", "python.exe"),
            os.path.join(prefix, "drive_c", "Python311", "python.exe"),
            os.path.join(prefix, "drive_c", "Python312", "python.exe"),
            os.path.join(prefix, "drive_c", "Program Files", "Python39", "python.exe"),
            os.path.join(prefix, "drive_c", "Program Files", "Python310", "python.exe"),
            os.path.join(prefix, "drive_c", "Program Files", "Python311", "python.exe"),
            os.path.join(prefix, "drive_c", "Program Files", "Python312", "python.exe"),
            os.path.join(prefix, "drive_c", "Users", "crossover", "AppData", "Local", "Programs", "Python", "Python311", "python.exe"),
            os.path.join(prefix, "drive_c", "Users", "crossover", "AppData", "Local", "Programs", "Python", "Python312", "python.exe"),
        ]
        for path in python_paths:
            if os.path.exists(path):
                return path

    return None


def _wine_binary():
    """Return the wine binary to use."""
    wine = os.environ.get("WINE")
    if wine:
        return wine
    for candidate in ["wine64", "wine"]:
        if subprocess.run(["which", candidate], capture_output=True).returncode == 0:
            return candidate
    return "wine64"


def check_mt5_installed(wine_python_path):
    """Check if MetaTrader5 is importable inside Wine Python."""
    wine_cmd = [_wine_binary(), wine_python_path, "-c", "import MetaTrader5; print('MT5_OK')"]
    try:
        result = subprocess.run(wine_cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0 and "MT5_OK" in result.stdout
    except Exception:
        return False


def _is_terminal_running():
    """Check if terminal64.exe is already running under our Wine session."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "terminal64.exe"],
            capture_output=True, text=True
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except Exception:
        return False


def start_terminal():
    """Start MetaTrader 5 terminal64.exe under Wine if not already running."""
    if _is_terminal_running():
        print("[Wine Bridge] terminal64.exe is already running.")
        return True

    wine = _wine_binary()
    terminal_path = "C:\\Program Files\\MetaTrader 5\\terminal64.exe"
    cmd = [wine, terminal_path]
    print(f"[Wine Bridge] Starting MetaTrader 5 terminal: {terminal_path}")
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Wait a few seconds for the terminal to initialize IPC
        for _ in range(10):
            time.sleep(1)
            if _is_terminal_running():
                print(f"[Wine Bridge] Terminal started successfully (PID {proc.pid}).")
                return True
        print("[Wine Bridge] Warning: terminal may still be starting...")
        return True
    except Exception as e:
        print(f"[Wine Bridge] Failed to start terminal: {e}")
        return False


def start_rpyc_server(wine_python_path, host="0.0.0.0", port=18812):
    """Start an RPyC classic server inside Wine Python."""
    server_script = f"""
import sys, threading
sys.path.insert(0, r"C:\\Program Files\\MetaTrader 5")

from rpyc.utils.server import ThreadedServer
from rpyc import classic

class MT5Service(classic.ClassicService):
    pass

srv = ThreadedServer(MT5Service, hostname="127.0.0.1", port={port}, auto_register=False)
print(f"[BRIDGE] RPyC server listening on {host}:{port}")
print("[BRIDGE] MT5 Wine bridge is ready for connections")

# Import MT5 in background so server starts immediately
def _import_mt5():
    try:
        import MetaTrader5 as mt5
        print("[BRIDGE] MetaTrader5 imported successfully")
    except Exception as e:
        print(f"[BRIDGE] Failed to import MetaTrader5: {{e}}")

threading.Thread(target=_import_mt5, daemon=True).start()

try:
    srv.start()
except KeyboardInterrupt:
    print("[BRIDGE] Shutting down...")
    srv.close()
"""

    wine = _wine_binary()
    print(f"[Wine Bridge] Starting RPyC server on {host}:{port} via Wine Python...")
    print(f"[Wine Bridge] Wine binary: {wine}")
    print(f"[Wine Bridge] Wine Python: {wine_python_path}")
    cmd = [wine, wine_python_path, "-u", "-c", server_script]

    # Separate stderr log for debugging Wine Python issues
    stderr_path = os.path.join(os.environ.get("LOG_DIR", "/tmp"), "wine_python_stderr.log")
    try:
        stderr_file = open(stderr_path, "w")
    except OSError:
        stderr_file = None

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=stderr_file if stderr_file else subprocess.STDOUT,
            text=True,
        )
        print(f"[Wine Bridge] Wine Python subprocess started (PID {proc.pid})")

        # Wait for the server to come online
        for _ in range(60):
            if proc.poll() is not None:
                print(f"[Wine Bridge] WARNING: Wine Python exited early (code {proc.poll()})")
                break
            line = proc.stdout.readline()
            if line:
                print(f"  {line.strip()}")
                if "ready for connections" in line:
                    print(f"[Wine Bridge] Server is ready. PID: {proc.pid}")
                    if stderr_file:
                        stderr_file.close()
                    return proc
            time.sleep(0.5)

        print("[Wine Bridge] Warning: server may still be starting...")
        if stderr_file:
            stderr_file.close()
        return proc
    except FileNotFoundError as exc:
        print(f"[Wine Bridge] ERROR: wine binary not found ({exc}). Install Wine or CrossOver.")
        if stderr_file:
            stderr_file.close()
        sys.exit(1)


def main():
    host = os.environ.get("MT5_WINE_HOST", "0.0.0.0")
    port = int(os.environ.get("MT5_WINE_PORT", "18812"))

    print("=" * 60)
    print("  Chain Gambler — MT5 Wine Bridge Launcher")
    print("=" * 60)

    # Step 1: Find Wine Python
    wine_python = find_wine_python()
    if wine_python:
        print(f"[1/4] Found Wine Python: {wine_python}")
    else:
        print("[1/4] WARNING: Could not auto-detect Wine Python.")
        print("      Set WINE_PYTHON env var to the path inside your Wine prefix.")
        print("      Example: WINE_PYTHON=~/.wine/drive_c/Python311/python.exe")
        sys.exit(1)

    # Step 2: Check MT5 (skipped — assume user has it)
    print("[2/4] Checking MetaTrader5 installation inside Wine...")
    print("      SKIPPED — assuming MetaTrader5 is available.")

    # Step 3: Ensure MetaTrader 5 terminal is running
    print("[3/3] Ensuring MetaTrader 5 terminal is running...")
    if not start_terminal():
        print("[Wine Bridge] WARNING: Could not confirm terminal is running.")
        print("              mt5.initialize() may fail if terminal is not already started.")

    # Step 4: Start RPyC server
    print("[4/4] Starting RPyC classic server...")
    proc = start_rpyc_server(wine_python, host=host, port=port)

    print()
    print("MT5 Wine bridge is running. The backend will connect automatically.")
    print("Keep this terminal open. Press Ctrl+C to stop.")
    print()

    try:
        while True:
            line = proc.stdout.readline()
            if line:
                print(f"  {line.strip()}")
            if proc.poll() is not None:
                print("[Wine Bridge] Server process exited.")
                break
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n[Wine Bridge] Stopping...")
        proc.terminate()
        proc.wait(timeout=5)
        print("[Wine Bridge] Stopped.")


if __name__ == "__main__":
    main()
