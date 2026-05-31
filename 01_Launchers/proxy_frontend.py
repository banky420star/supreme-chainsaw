#!/usr/bin/env python3
"""
Chain Gambler — Static File Server + API Proxy
Serves the React production build from ui_lab_app/dist/
and proxies /api/* requests to the backend API server.
"""
import http.server
import socketserver
import urllib.request
import urllib.error
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST_DIR = os.path.join(PROJECT_DIR, "ui_lab_app", "dist")
DEFAULT_PORT = 4180
DEFAULT_API_PORT = 5050

port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
api_port = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_API_PORT
API_BASE = f"http://127.0.0.1:{api_port}"


class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIST_DIR, **kwargs)

    def log_message(self, fmt, *args):
        # Only log errors to keep output clean
        if " 404 " in fmt % args or " 500 " in fmt % args or " 502 " in fmt % args:
            super().log_message(fmt, *args)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Control-Token")
        self.end_headers()

    def _proxy(self):
        target = f"{API_BASE}{self.path}"
        try:
            body = None
            content_length = self.headers.get("Content-Length")
            if content_length:
                body = self.rfile.read(int(content_length))

            req = urllib.request.Request(
                target,
                data=body,
                headers={k: v for k, v in self.headers.items() if k.lower() not in ("host", "content-length")},
                method=self.command,
            )
            resp = urllib.request.urlopen(req, timeout=30)
            data = resp.read()
            self.send_response(resp.status)
            for k, v in resp.headers.items():
                if k.lower() not in ("transfer-encoding", "content-encoding", "content-length"):
                    self.send_header(k, v)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except urllib.error.HTTPError as e:
            data = e.read()
            self.send_response(e.code)
            for k, v in e.headers.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            msg = f'{{"error": "API unreachable: {e}"}}'.encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

    def do_GET(self):
        if self.path.startswith("/api/"):
            self._proxy()
        else:
            super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/"):
            self._proxy()
        else:
            self.send_response(405)
            self.end_headers()

    def do_PUT(self):
        if self.path.startswith("/api/"):
            self._proxy()
        else:
            self.send_response(405)
            self.end_headers()

    def do_DELETE(self):
        if self.path.startswith("/api/"):
            self._proxy()
        else:
            self.send_response(405)
            self.end_headers()


if __name__ == "__main__":
    if not os.path.isdir(DIST_DIR):
        print(f"ERROR: {DIST_DIR} not found. Run 'npm run build' first.")
        sys.exit(1)

    # Kill any existing process on the port
    os.system(f"lsof -ti :{port} | xargs kill -9 2>/dev/null; true")

    http.server.ThreadingHTTPServer.allow_reuse_address = True
    with http.server.ThreadingHTTPServer(("", port), ProxyHandler) as httpd:
        print(f"[Proxy] Serving static files from {DIST_DIR}")
        print(f"[Proxy] Proxying /api/* to {API_BASE}")
        print(f"[Proxy] Listening on http://localhost:{port}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[Proxy] Shutting down...")
