"""Faux serveur 127.0.0.1:8181 : sert le dist de la release que le "processus web" a charge (state/running_wd).
Fautes pilotees par des fichiers 'knobs'. Conteneur de test, jamais le VPS."""

import http.server
import os

SBX = os.environ["SBX"]
K = SBX + "/knobs"


class Handler(http.server.BaseHTTPRequestHandler):
    def reply_status(self, code):
        self.send_response(code)
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0].lstrip("/")
        with open(SBX + "/state/running_wd") as stream:
            root = stream.read().strip() + "/dist"
        if os.path.exists(f"{K}/missing_sw") and path == "sw.js":
            return self.reply_status(404)
        target = os.path.join(root, path)
        if path.startswith("direction/") or not path:
            target = os.path.join(root, "index.html")
        elif not os.path.isfile(target):
            return self.reply_status(404)
        try:
            with open(target, "rb") as stream:
                data = stream.read()
        except OSError:
            return self.reply_status(404)
        if os.path.exists(f"{K}/tamper_css") and path.endswith(".css"):
            data += b"/*tamper*/"
        self.send_response(200)
        self.end_headers()
        self.wfile.write(data)

    do_HEAD = do_GET

    def log_message(self, *args):
        pass


http.server.HTTPServer(("127.0.0.1", 8181), Handler).serve_forever()
