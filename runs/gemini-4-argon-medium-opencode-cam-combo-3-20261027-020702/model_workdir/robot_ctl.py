#!/usr/bin/env python3
import argparse
import sys
import time
from pathlib import Path
import subprocess

sys.path.insert(0, "/Users/dylanler/github/lerobot-nexarm/src")
from lerobot.motors.nexarm.nexarm import NexArmMotorsBus, JOINT_NAMES

PORT = "/dev/cu.usbserial-110"
SNAP_PATH = "/Users/dylanler/github/nex-arm-3-cam-eval/gemini-4-argon-medium-opencode-cam-combo-3-20261027-020702/wrist_snap.jpg"

def take_snapshot(out_path=SNAP_PATH):
    # Capture 1 frame from icspring camera (device 0) via ffmpeg
    cmd = [
        "/opt/homebrew/bin/ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "avfoundation", "-pixel_format", "bgr0", "-framerate", "30", "-video_size", "640x480",
        "-i", "icspring camera:none", "-frames:v", "3", "-update", "1", out_path
    ]
    subprocess.run(cmd, check=True)

def safe_read_positions(bus):
    # Read multiple times and require two consecutive identical-ish reads (within 15 units)
    prev = None
    for _ in range(15):
        pos = bus.read_positions()
        if all(100 < p < 3995 for p in pos):
            if prev is not None and all(abs(pos[i] - prev[i]) < 20 for i in range(6)):
                return pos
            prev = pos
        time.sleep(0.025)
    return prev if prev is not None else bus.read_positions()

def read_robot():
    bus = NexArmMotorsBus(port=PORT)
    bus.connect()
    try:
        bus.enter_lerobot_mode()
        pos = safe_read_positions(bus)
        return pos
    finally:
        bus.disconnect()

def move_robot(target, steps=20, dt=0.04, speed=800, acc=80, hold_torque=True):
    bus = NexArmMotorsBus(port=PORT)
    bus.connect()
    try:
        bus.enter_lerobot_mode()
        bus.write_motion_params(acc=acc, speed=speed)
        bus.set_torque(True)
        cur = safe_read_positions(bus)
        print(f"Start:  {dict(zip(JOINT_NAMES, cur))}")
        for s in range(1, steps + 1):
            alpha = s / steps
            interp = [int(round(cur[i] + alpha * (target[i] - cur[i]))) for i in range(6)]
            bus.write_positions(interp)
            time.sleep(dt)
        time.sleep(0.3)
        end_pos = safe_read_positions(bus)
        print(f"End:    {dict(zip(JOINT_NAMES, end_pos))}")
        if not hold_torque:
            bus.set_torque(False)
            bus.exit_lerobot_mode()
        return end_pos
    finally:
        bus.disconnect()

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--read", action="store_true")
    p.add_argument("--snap", action="store_true")
    p.add_argument("--move", nargs=6, type=int, metavar=("J1", "J2", "J3", "J4", "J5", "J6"))
    p.add_argument("--steps", type=int, default=20)
    p.add_argument("--dt", type=float, default=0.04)
    p.add_argument("--speed", type=int, default=800)
    p.add_argument("--acc", type=int, default=80)
    p.add_argument("--release", action="store_true")
    args = p.parse_args()

    if args.read:
        pos = read_robot()
        print("Positions:", pos)
        for name, val in zip(JOINT_NAMES, pos):
            print(f"  {name}: {val}")
    if args.move:
        move_robot(args.move, steps=args.steps, dt=args.dt, speed=args.speed, acc=args.acc, hold_torque=not args.release)
    if args.snap:
        take_snapshot()
        print(f"Saved snapshot to {SNAP_PATH}")
