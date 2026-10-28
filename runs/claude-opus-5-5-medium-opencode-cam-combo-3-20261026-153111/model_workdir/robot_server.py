"""NexArm control server: holds the serial port, exposes HTTP endpoints on 127.0.0.1:8790,
and keeps a live wrist-camera frame (ONLY the wrist camera is opened) for snapshots.

  /read                         -> current joint positions
  /move?p=a,b,c,d,e,f&t=2       -> smooth interpolated move (raw 0-4095), then snapshot
  /snap                         -> save wrist snapshot, return path
  /torque?on=1
"""
import json, subprocess, sys, threading, time, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import numpy as np, cv2
sys.path.insert(0, "/Users/dylanler/github/lerobot-nexarm/src")
from lerobot.motors.nexarm import NexArmMotorsBus

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.join(HERE, "snaps")
os.makedirs(SNAP, exist_ok=True)
PORT = "/dev/tty.usbserial-110"
W, H = 640, 480

bus = NexArmMotorsBus(PORT)
bus.connect()
bus.enter_lerobot_mode()
bus.write_motion_params(acc=60, speed=1200)
time.sleep(0.1)
cur = bus.read_positions()
bus.write_positions(cur)
bus.set_torque(True)
target = list(cur)
log = open(os.path.join(HERE, "robot_log.jsonl"), "a")
log.write(json.dumps({"t": time.time(), "event": "start", "pos": cur}) + "\n"); log.flush()

frame = {"img": None, "t": 0}

def cam_loop():
    while True:
        cmd = ["/opt/homebrew/bin/ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
               "-f", "avfoundation", "-pixel_format", "bgr0", "-framerate", "30",
               "-video_size", f"{W}x{H}", "-i", "icspring camera:none",
               "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        n = W * H * 3
        while True:
            b = p.stdout.read(n)
            if len(b) < n:
                break
            frame["img"] = np.frombuffer(b, np.uint8).reshape(H, W, 3)
            frame["t"] = time.time()
        p.kill(); time.sleep(1)

threading.Thread(target=cam_loop, daemon=True).start()

def snap(tag="s"):
    t0 = time.time()
    while frame["t"] < t0 + 0.3 and time.time() - t0 < 3:
        time.sleep(0.05)
    if frame["img"] is None:
        return None
    path = os.path.join(SNAP, f"{time.strftime('%H%M%S')}_{tag}.jpg")
    cv2.imwrite(path, frame["img"])
    return path

def read():
    for _ in range(5):
        try:
            return bus.read_positions()
        except Exception:
            time.sleep(0.02)
    return None

def move(p, t):
    global target
    start = read() or target
    steps = max(1, int(t * 50))
    for i in range(1, steps + 1):
        a = i / steps
        a = a * a * (3 - 2 * a)
        bus.write_positions([round(s + (e - s) * a) for s, e in zip(start, p)])
        time.sleep(1 / 50)
    target = list(p)
    time.sleep(0.4)

class Hd(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}
        out = {}
        try:
            if u.path == "/move":
                p = [int(float(x)) for x in q["p"].split(",")]
                move(p, float(q.get("t", 2)))
                out["snap"] = snap("move")
            elif u.path == "/snap":
                out["snap"] = snap("snap")
            elif u.path == "/torque":
                bus.set_torque(q.get("on", "1") == "1")
            out["target"] = target
            out["pos"] = read()
            log.write(json.dumps({"t": time.time(), "path": self.path, **out}) + "\n"); log.flush()
        except Exception as e:
            out["error"] = repr(e)
        b = json.dumps(out).encode()
        self.send_response(200); self.end_headers(); self.wfile.write(b)

srv = ThreadingHTTPServer(("127.0.0.1", 8790), Hd)
print("ready", cur, flush=True)
try:
    srv.serve_forever()
finally:
    try:
        pos = bus.read_positions(); bus.write_positions(pos); time.sleep(0.3)
    except Exception:
        pass
    bus.exit_lerobot_mode(); bus.disconnect()
