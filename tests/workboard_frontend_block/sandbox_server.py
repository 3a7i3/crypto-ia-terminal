"""Faux serveur 127.0.0.1:8181 : sert le dist de la release que le "processus web" a charge (state/running_wd).
Fautes pilotees par des fichiers 'knobs'. Conteneur de test, jamais le VPS."""
import http.server, os
SBX = os.environ["SBX"]; K = SBX + "/knobs"
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        p = self.path.split("?")[0].lstrip("/")
        root = open(SBX + "/state/running_wd").read().strip() + "/dist"
        if os.path.exists(f"{K}/missing_sw") and p == "sw.js":
            self.send_response(404); self.end_headers(); return
        f = os.path.join(root, p)
        if p.startswith("direction/") or not p: f = os.path.join(root, "index.html")
        elif not os.path.isfile(f): self.send_response(404); self.end_headers(); return
        try: d = open(f, "rb").read()
        except OSError: self.send_response(404); self.end_headers(); return
        if os.path.exists(f"{K}/tamper_css") and p.endswith(".css"): d += b"/*tamper*/"
        self.send_response(200); self.end_headers(); self.wfile.write(d)
    do_HEAD = do_GET
    def log_message(self, *a): pass
http.server.HTTPServer(("127.0.0.1", 8181), H).serve_forever()
