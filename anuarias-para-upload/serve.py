#!/usr/bin/env python3
"""Serve o site/ e, opcionalmente, roda ./atualizar.sh quando o botão
"atualizar dados" da página é clicado.

    python3 serve.py            # porta 8778
    python3 serve.py 8080       # outra porta

Só para uso local: não é feito para ficar exposto na internet.
"""

import http.server
import json
import os
import subprocess
import sys
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.path.join(BASE_DIR, "site")
UPDATE_SCRIPT = os.path.join(BASE_DIR, "atualizar.sh")
DEFAULT_PORT = 8778
TIMEOUT_SECONDS = 20 * 60

_refresh_lock = threading.Lock()


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=SITE_DIR, **kwargs)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def do_POST(self):
        if self.path != "/api/refresh":
            self.send_error(404, "not found")
            return

        if not _refresh_lock.acquire(blocking=False):
            self._send_json(409, {"ok": False, "error": "já tem uma atualização rodando"})
            return
        try:
            self._run_refresh()
        finally:
            _refresh_lock.release()

    def _run_refresh(self):
        try:
            result = subprocess.run(
                ["sh", UPDATE_SCRIPT],
                cwd=BASE_DIR,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
            )
            ok = result.returncode == 0
            log = (result.stdout or "") + (("\n" + result.stderr) if result.stderr else "")
            self._send_json(200 if ok else 500, {"ok": ok, "log": log[-8000:]})
        except subprocess.TimeoutExpired:
            self._send_json(504, {"ok": False, "error": "atualização demorou demais e foi cancelada"})
        except Exception as exc:  # não deixa a atualização derrubar o servidor
            self._send_json(500, {"ok": False, "error": str(exc)})

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    server = http.server.ThreadingHTTPServer(("", port), Handler)
    print("Anuárias em http://localhost:%d (Ctrl+C para parar)" % port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
