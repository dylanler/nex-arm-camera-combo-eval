#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyserial>=3.5"]
# ///
"""Orchestrator-only helper: save / verify / restore the NexArm resting home pose.

  ./arm_home.py read                 # print current joint positions (JSON)
  ./arm_home.py save                 # save current pose to home_pose.json
  ./arm_home.py goto [--tol 25]      # smoothly move to saved home, verify, hold torque
  ./arm_home.py check [--tol 25]     # exit 0 if current pose within tolerance of home
"""
import argparse
import json
import math
import struct
import sys
import time
from datetime import datetime
from pathlib import Path

import serial

PORT = "/dev/cu.usbserial-110"
HOME_FILE = Path(__file__).resolve().parent / "home_pose.json"
JOINTS = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper")


def frame(cmd, args=b""):
    raw = bytes([0xFF, (len(args) + 2) & 0xFF, cmd]) + args
    return b"\xff\xff" + raw + bytes([(~sum(raw)) & 0xFF])


class Arm:
    def __init__(self):
        self.s = serial.Serial(PORT, 1_000_000, timeout=0.05, write_timeout=0.05)
        time.sleep(0.1)
        self.s.reset_input_buffer()
        self.s.write(frame(68, bytes([1])))  # LeRobot bridge mode
        time.sleep(0.1)

    def read(self, retries=8):
        for _ in range(retries):
            self.s.reset_input_buffer()
            self.s.write(frame(96))
            buf, end = bytearray(), time.monotonic() + 0.15
            while time.monotonic() < end:
                n = self.s.in_waiting
                if n:
                    buf.extend(self.s.read(n))
                    i = bytes(buf).find(b"\xff\xff")
                    if i >= 0 and len(buf) >= i + 4:
                        total = 4 + buf[i + 3]
                        if len(buf) >= i + total:
                            args = buf[i + 5: i + total - 1]
                            if len(args) >= 12:
                                p = [struct.unpack_from("<h", args, k * 2)[0] for k in range(6)]
                                if all(5 < v < 4090 for v in p):
                                    return p
                            buf = buf[i + 2:]
                else:
                    time.sleep(0.002)
            time.sleep(0.01)
        raise TimeoutError("no position reply from NexArm")

    def write(self, pos):
        self.s.write(frame(97, b"".join(struct.pack("<h", max(0, min(4095, int(round(v))))) for v in pos)))

    def torque(self, on):
        self.s.write(frame(98, bytes([1 if on else 0])))
        time.sleep(0.03)

    def motion(self, acc=60, speed=800):
        self.s.write(frame(56, bytes([acc, speed & 0xFF, speed >> 8])))
        time.sleep(0.03)

    def close(self):
        self.s.close()


def load_home():
    return json.loads(HOME_FILE.read_text())["positions"]


def err(a, b):
    return [abs(x - y) for x, y in zip(a, b)]


def goto(arm, home, tol):
    arm.motion()
    cur = arm.read()
    arm.write(cur)  # hold where it is before enabling torque (no jump)
    arm.torque(True)
    dist = max(err(cur, home))
    dur = max(2.0, dist / 300.0)  # ~300 raw units/s max
    steps = int(dur * 30)
    for k in range(1, steps + 1):
        w = 0.5 * (1 - math.cos(math.pi * k / steps))
        arm.write([c + w * (h - c) for c, h in zip(cur, home)])
        time.sleep(1 / 30)
    for _ in range(3):  # settle + re-send final goal
        time.sleep(0.5)
        arm.write(home)
    time.sleep(0.8)
    final = arm.read()
    e = err(final, home)
    return final, e, max(e) <= tol


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["read", "save", "goto", "check", "health"])
    # 45 raw units ~= 4 deg; the loaded elbow settles ~20-40 units short of target under gravity
    ap.add_argument("--tol", type=int, default=45)
    a = ap.parse_args()
    arm = Arm()
    try:
        if a.cmd == "read":
            print(json.dumps(dict(zip(JOINTS, arm.read()))))
        elif a.cmd == "save":
            p = arm.read()
            HOME_FILE.write_text(json.dumps({"saved_at": datetime.now().isoformat(timespec="seconds"),
                                             "port": PORT, "joint_order": JOINTS, "positions": p}, indent=2))
            print("saved", dict(zip(JOINTS, p)))
        elif a.cmd == "check":
            p, h = arm.read(), load_home()
            e = err(p, h)
            print(json.dumps({"current": p, "home": h, "abs_err": e, "ok": max(e) <= a.tol}))
            sys.exit(0 if max(e) <= a.tol else 1)
        elif a.cmd == "health":
            # every joint must (a) show live readings and (b) follow a small +/-delta command, then return home
            home = load_home()
            final, e, ok = goto(arm, home, a.tol)
            res = {}
            for j, name in enumerate(JOINTS):
                d = 50 if name != "gripper" else 80
                p = list(home)
                p[j] = home[j] + d
                for _ in range(4):
                    arm.write(p)
                    time.sleep(0.3)
                time.sleep(0.4)
                moved = arm.read()[j] - home[j]
                for _ in range(4):
                    arm.write(home)
                    time.sleep(0.3)
                time.sleep(0.4)
                back = arm.read()[j] - home[j]
                res[name] = {"cmd_delta": d, "moved": moved, "returned_err": back, "ok": moved >= 10 and abs(back) <= a.tol}
            final, e, ok2 = goto(arm, home, a.tol)
            all_ok = all(v["ok"] for v in res.values()) and ok2
            print(json.dumps({"joints": res, "final": final, "abs_err": e, "ok": all_ok}))
            sys.exit(0 if all_ok else 1)
        elif a.cmd == "goto":
            final, e, ok = goto(arm, load_home(), a.tol)
            if not ok:  # one retry
                final, e, ok = goto(arm, load_home(), a.tol)
            print(json.dumps({"final": final, "home": load_home(), "abs_err": e, "ok": ok}))
            sys.exit(0 if ok else 1)
    finally:
        arm.close()


if __name__ == "__main__":
    main()
