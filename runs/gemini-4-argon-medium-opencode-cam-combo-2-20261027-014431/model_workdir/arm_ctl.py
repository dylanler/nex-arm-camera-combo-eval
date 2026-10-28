#!/usr/bin/env python3
"""
Helper script to control the NexArm follower arm, read joint positions,
and capture camera frames from the enabled cameras ONLY (Logitech top-down and Robot Wrist).
RealSense camera is disabled and never opened.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "/Users/dylanler/github/lerobot-nexarm/src")
from lerobot.motors.nexarm.nexarm import JOINT_NAMES, NexArmMotorsBus, POSITION_MAX, POSITION_MIN

PORT = "/dev/cu.usbserial-110"
FFMPEG = "/opt/homebrew/bin/ffmpeg"
WORKDIR = Path("/Users/dylanler/github/nex-arm-3-cam-eval/gemini-4-argon-medium-opencode-cam-combo-2-20261027-014431")

# Enabled cameras ONLY:
# Logitech C922 (top down view): "C922 Pro Stream Webcam"
# Robot arm wrist camera: "icspring camera"
# RealSense camera is DISABLED and strictly excluded.
ENABLED_CAMERAS = {
    "logitech": "C922 Pro Stream Webcam",
    "wrist": "icspring camera",
}


def capture_cameras(tag: str = "snap"):
    out_paths = {}
    for key, dev in ENABLED_CAMERAS.items():
        out_file = WORKDIR / f"{tag}_{key}.jpg"
        cmd = [
            FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "avfoundation", "-framerate", "30", "-video_size", "640x480",
            "-i", f"{dev}:none", "-frames:v", "1", str(out_file)
        ]
        subprocess.run(cmd, check=False, timeout=10)
        out_paths[key] = str(out_file)
    return out_paths


def read_pos(bus: NexArmMotorsBus) -> list[int]:
    pos = bus.read_positions(retries=5)
    # Check for corrupt reads (<= 5 or >= 4090)
    for _ in range(3):
        if any(p <= 5 or p >= 4090 for p in pos):
            time.sleep(0.02)
            pos = bus.read_positions(retries=5)
        else:
            break
    return pos


def move_smooth(bus: NexArmMotorsBus, target: list[int], steps: int = 25, duration: float = 1.2):
    cur = read_pos(bus)
    dt = duration / max(1, steps)
    for s in range(1, steps + 1):
        alpha = s / steps
        interp = [
            int(round(cur[i] + alpha * (target[i] - cur[i])))
            for i in range(6)
        ]
        bus.write_positions(interp)
        time.sleep(dt)
    time.sleep(0.3)
    return read_pos(bus)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["status", "snap", "move", "torque_off"])
    p.add_argument("--pos", type=int, nargs=6, help="6 joint positions: pan lift elbow wrist_flex wrist_roll gripper")
    p.add_argument("--steps", type=int, default=25)
    p.add_argument("--duration", type=float, default=1.2)
    p.add_argument("--tag", default="snap")
    p.add_argument("--no-snap", action="store_true")
    args = p.parse_args()

    result = {}
    if args.action in ("status", "move", "torque_off"):
        bus = NexArmMotorsBus(port=PORT)
        bus.connect()
        try:
            bus.enter_lerobot_mode()
            if args.action == "status":
                pos = read_pos(bus)
                result["positions"] = dict(zip(JOINT_NAMES, pos))
                result["raw"] = pos
            elif args.action == "move":
                bus.write_motion_params(acc=60, speed=1500)
                bus.set_torque(True)
                pos = move_smooth(bus, args.pos, steps=args.steps, duration=args.duration)
                result["positions"] = dict(zip(JOINT_NAMES, pos))
                result["raw"] = pos
            elif args.action == "torque_off":
                pos = read_pos(bus)
                bus.write_positions(pos)
                time.sleep(0.3)
                bus.set_torque(False)
                bus.exit_lerobot_mode()
                result["positions"] = dict(zip(JOINT_NAMES, pos))
                result["raw"] = pos
        finally:
            bus.disconnect()

    if args.action == "snap" or (args.action in ("status", "move") and not args.no_snap):
        result["images"] = capture_cameras(args.tag)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
