import os
import json
import http.server
import socketserver


def _load_secrets() -> None:
    """secrets.env (bu script ile ayni dizin) -> yalnizca eksik env anahtarlarini doldurur.

    nebius_handler env degiskenlerini IMPORT aninda okudugu icin bu yukleme
    import'tan ONCE yapilmalidir. Zaten tanimliysa dokunmaz (setdefault).
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "secrets.env")
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip("'\""))


_load_secrets()

from nebius_handler import handler  # noqa: E402  (secrets yuklendikten sonra)

PORT = int(os.environ.get("CLOUD_PORT", 8090))

class CloudHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        event = json.loads(post_data.decode('utf-8'))
        
        response = handler(event)
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode('utf-8'))

    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "provider": "nvidia"}).encode('utf-8'))

class CloudServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

if __name__ == "__main__":
    with CloudServer(("", PORT), CloudHandler) as httpd:
        print(f"Cloud Server running on port {PORT}")
        httpd.serve_forever()