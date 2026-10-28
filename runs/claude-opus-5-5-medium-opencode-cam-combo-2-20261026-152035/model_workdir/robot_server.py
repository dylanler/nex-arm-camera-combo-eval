"""Persistent NexArm follower server. Listens on TCP 127.0.0.1:8799 for one-line JSON commands.

Commands:
  {"cmd":"read"}
  {"cmd":"move","pos":[6 ints] or {"joint":val,...}, "dur":2.0}   (smooth interpolation)
  {"cmd":"torque","on":true}
  {"cmd":"quit"}
"""
import json
import socket
import sys
import time

sys.path.insert(0, "/Users/dylanler/github/lerobot-nexarm/src")
from lerobot.motors.nexarm import NexArmMotorsBus  # noqa: E402
from lerobot.motors.nexarm.nexarm import JOINT_NAMES  # noqa: E402

PORT = "/dev/cu.usbserial-110"
LOG = open(sys.argv[1] if len(sys.argv) > 1 else "robot_log.jsonl", "a")

bus = NexArmMotorsBus(port=PORT)
bus.connect()
bus.enter_lerobot_mode()
bus.write_motion_params(acc=60, speed=1500)
cur = bus.read_positions()
bus.write_positions(cur)
bus.set_torque(True)
target = list(cur)


def log(**kw):
    kw["t"] = time.time()
    LOG.write(json.dumps(kw) + "\n")
    LOG.flush()


log(event="start", pos=cur)


def move(goal, dur):
    global target
    start = list(target)
    n = max(1, int(dur / 0.03))
    for i in range(1, n + 1):
        a = i / n
        a = a * a * (3 - 2 * a)
        p = [int(round(s + (g - s) * a)) for s, g in zip(start, goal)]
        bus.write_positions(p)
        time.sleep(0.03)
    target = list(goal)
    time.sleep(0.4)


srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", 8799))
srv.listen(1)
running = True
while running:
    c, _ = srv.accept()
    f = c.makefile("rw")
    line = f.readline()
    try:
        req = json.loads(line)
        cmd = req["cmd"]
        if cmd == "read":
            pass
        elif cmd == "move":
            goal = list(target)
            pos = req["pos"]
            if isinstance(pos, dict):
                for k, v in pos.items():
                    goal[JOINT_NAMES.index(k)] = int(v)
            else:
                goal = [int(v) for v in pos]
            move(goal, float(req.get("dur", 2.0)))
        elif cmd == "torque":
            bus.set_torque(bool(req["on"]))
        elif cmd == "quit":
            running = False
        actual = bus.read_positions()
        resp = {"ok": True, "target": target, "actual": actual,
                "err": [a - b for a, b in zip(actual, target)]}
        log(event=cmd, req=req, resp=resp)
    except Exception as e:  # noqa: BLE001
        resp = {"ok": False, "error": repr(e)}
    f.write(json.dumps(resp) + "\n")
    f.flush()
    c.close()

p = bus.read_positions()
bus.write_positions(p)
time.sleep(0.3)
bus.set_torque(False)
bus.exit_lerobot_mode()
bus.disconnect()
