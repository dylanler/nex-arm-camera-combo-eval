import http.server
from pathlib import Path

HERE = Path(__file__).parent
original = http.server.SimpleHTTPRequestHandler.translate_path
def translate(self, path):
    if path.split('?')[0] == '/app.js':
        return str(HERE / 'app-wrist.js')
    return original(self, path)
http.server.SimpleHTTPRequestHandler.translate_path = translate
def post(self):
    data=self.rfile.read(int(self.headers['Content-Length']))
    if self.path == '/wrist-frame':
        (HERE/'wrist.jpg').write_bytes(data)
    self.send_response(204)
    self.end_headers()
http.server.SimpleHTTPRequestHandler.do_POST = post
