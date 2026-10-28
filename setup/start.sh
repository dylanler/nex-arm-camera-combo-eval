#!/usr/bin/env bash
# Serve the 3-camera eval frontend on http://localhost:8770 and open it.
# (Camera access requires localhost or https — file:// will not work.)
# Sends Cache-Control: no-store so the browser always loads the current app.js / index.html.
set -e
cd "$(dirname "$0")"
PORT="${PORT:-8770}"
( sleep 1; open "http://localhost:${PORT}" ) &
exec python3 -c '
import http.server, sys
class H(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()
http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
' "$PORT"
