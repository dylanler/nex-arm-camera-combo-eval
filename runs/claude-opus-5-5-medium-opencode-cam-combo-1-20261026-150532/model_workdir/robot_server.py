"""Persistent NexArm follower server. HTTP on 127.0.0.1:8771.
GET /pos            -> current joint positions (raw 0-4095)
GET /move?j=a,b,c,d,e,f&t=2.0   -> smooth interpolated move to target (use '_' to keep a joint)
GET /torque?on=0|1
GET /quit
"""
import json, sys, time, threading, logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
sys.path.insert(0, "/Users/dylanler/github/lerobot-nexarm/src")
from lerobot.motors.nexarm import NexArmMotorsBus

logging.basicConfig(level=logging.INFO)
bus = NexArmMotorsBus(port="/dev/tty.usbserial-110", baudrate=1_000_000)
bus.connect()
bus.enter_lerobot_mode()
bus.write_motion_params(acc=100, speed=2000)
lock = threading.Lock()


def read():
    for _ in range(5):
        try:
            p = list(bus.read_positions())
            if all(5 < v < 4090 for v in p):
                return p
        except Exception as e:
            logging.warning("read fail %s", e)
        time.sleep(0.02)
    return p


start = read()
print("START", start, flush=True)
bus.write_positions(start)
bus.set_torque(True)
cur = list(start)


def move(target, t):
    global cur
    src = list(cur)
    n = max(1, int(t * 50))
    for i in range(1, n + 1):
        a = i / n
        a = a * a * (3 - 2 * a)
        g = [int(round(s + (d - s) * a)) for s, d in zip(src, target)]
        bus.write_positions(g)
        time.sleep(t / n)
    cur = list(target)
    time.sleep(0.4)
    return read()


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        with lock:
            if u.path == "/pos":
                r = {"pos": read(), "cmd": cur}
            elif u.path == "/move":
                vals = q["j"][0].split(",")
                tgt = [cur[i] if v == "_" else int(float(v)) for i, v in enumerate(vals)]
                tgt = [max(0, min(4095, v)) for v in tgt]
                r = {"target": tgt, "pos": move(tgt, float(q.get("t", ["2"])[0]))}
            elif u.path == "/torque":
                bus.set_torque(q["on"][0] == "1")
                r = {"ok": True}
            elif u.path == "/quit":
                p = read()
                bus.write_positions(p)
                time.sleep(0.3)
                r = {"pos": p}
                threading.Thread(target=shutdown, daemon=True).start()
            else:
                r = {"err": "?"}
        b = json.dumps(r).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass


def shutdown():
    time.sleep(0.2)
    try:
        bus.exit_lerobot_mode()
    except Exception:
        pass
    bus.disconnect()
    srv.shutdown()


srv = HTTPServer(("127.0.0.1", 8771), H)
srv.serve_forever()
print("bye", flush=True)
