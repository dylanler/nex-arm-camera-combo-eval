#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "/Users/dylanler/github/lerobot-nexarm/src")
from lerobot.motors.nexarm.nexarm import NexArmMotorsBus, JOINT_NAMES

PORT = "/dev/cu.usbserial-110"
WORKDIR = Path(__file__).resolve().parent
FFMPEG = "/opt/homebrew/bin/ffmpeg"

CAMERAS = {
    "logitech": "C922 Pro Stream Webcam",
    "realsense": "Intel(R) RealSense(TM) Depth Camera 415  RGB",
    "wrist": "icspring camera",
}


def capture_cam(key: str, dev: str, out_path: Path):
    cmd = [
        FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "avfoundation", "-framerate", "30", "-video_size", "640x480",
        "-i", f"{dev}:none",
        "-frames:v", "1",
        str(out_path)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    if res.returncode != 0:
        # fallback without video_size
        cmd = [
            FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "avfoundation", "-framerate", "30",
            "-i", f"{dev}:none",
            "-frames:v", "1",
            str(out_path)
        ]
        subprocess.run(cmd, capture_output=True, text=True, timeout=10)


def snap_all(tag: str = "latest"):
    snap_dir = WORKDIR / "snaps"
    snap_dir.mkdir(exist_ok=True)
    procs = []
    paths = {}
    for key, dev in CAMERAS.items():
        out_path = snap_dir / f"{tag}_{key}.jpg"
        paths[key] = out_path
        cmd = [
            FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "avfoundation", "-framerate", "30", "-video_size", "640x480",
            "-i", f"{dev}:none",
            "-frames:v", "1",
            str(out_path)
        ]
        procs.append((key, subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)))
    for key, p in procs:
        p.wait(timeout=10)
    return {k: str(v) for k, v in paths.items()}


def read_pos(bus: NexArmMotorsBus) -> list[int]:
    for _ in range(5):
        raw = bus.read_positions(retries=5)
        if all(5 < p < 4090 for p in raw):
            return raw
        time.sleep(0.05)
    return bus.read_positions(retries=5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("cmd", choices=["read", "snap", "move"])
    parser.add_argument("--targets", type=int, nargs=6, help="6 joint positions")
    parser.add_argument("--speed", type=int, default=800)
    parser.add_argument("--acc", type=int, default=60)
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--duration", type=float, default=1.5)
    parser.add_argument("--settle", type=float, default=0.6)
    parser.add_argument("--tag", type=str, default="latest")
    parser.add_argument("--no-snap", action="store_true")
    args = parser.parse_args()

    if args.cmd == "snap":
        paths = snap_all(args.tag)
        print(json.dumps({"snaps": paths}))
        return

    bus = NexArmMotorsBus(port=PORT)
    bus.connect()
    try:
        bus.enter_lerobot_mode()
        cur = read_pos(bus)
        if args.cmd == "read":
            paths = {} if args.no_snap else snap_all(args.tag)
            print(json.dumps({
                "positions": cur,
                "named": dict(zip(JOINT_NAMES, cur)),
                "snaps": paths,
            }))
            return

        if args.cmd == "move":
            assert args.targets is not None
            bus.write_motion_params(acc=args.acc, speed=args.speed)
            bus.set_torque(True)
            targets = [max(50, min(4045, int(t))) for t in args.targets]
            steps = max(1, args.steps)
            dt = args.duration / steps
            for s in range(1, steps + 1):
                alpha = s / steps
                interp = [int(round(cur[i] + alpha * (targets[i] - cur[i]))) for i in range(6)]
                bus.write_positions(interp)
                time.sleep(dt)
            time.sleep(args.settle)
            final = read_pos(bus)
            paths = {} if args.no_snap else snap_all(args.tag)
            print(json.dumps({
                "start": cur,
                "target": targets,
                "final": final,
                "named": dict(zip(JOINT_NAMES, final)),
                "snaps": paths,
            }))
    finally:
        bus.disconnect()


if __name__ == "__main__":
    main()
