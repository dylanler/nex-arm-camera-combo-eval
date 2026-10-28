#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["opencv-python>=4.8", "numpy>=1.24"]
# ///
"""
NEX Arm 3-camera recorder — records the robot wrist cam, RealSense D415 (RGB) and
Logitech C922 into one composite video (same view as the web frontend), with a
burned-in timestamp, pause/resume, per-trial clips, success/fail labels, markers,
live FPS / color / layout changes, and per-frame timing logs for syncing with
robot data. The built-in FaceTime camera is never opened.

    ./record.py --task pick_cube            # start recording right away
    ./record.py --task pick_cube --idle     # open preview, press SPACE to start
    ./record.py --source screen --crop chrome   # literally screen-record the web frontend
    ./record.py --list                      # show detected cameras

Hotkeys work in the preview window or in the terminal (press h for help).
"""
from __future__ import annotations

import argparse
import atexit
import csv
import datetime as dt
import json
import queue
import re
import select
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FONT = cv2.FONT_HERSHEY_SIMPLEX
FOOTER_H = 44
FRONTEND_PORT = 8770

ROLES = [  # key, display name, device-name pattern
    ("wrist", "Robot Wrist", re.compile(r"icspring", re.I)),
    ("realsense", "RealSense D415", re.compile(r"realsense", re.I)),
    ("logitech", "Logitech C922", re.compile(r"c922|logitech", re.I)),
]
EXCLUDE = re.compile(r"facetime|capture screen|built-in|desk view|iphone", re.I)
COLOR_MODES = ["normal", "grayscale", "high-contrast", "warm", "cool", "invert"]
LAYOUTS = ["grid", "row", "focus", "single"]

HELP = [
    "SPACE  start / pause / resume recording",
    "n      next clip (finish current, start new one)",
    "y / x  label clip SUCCESS / FAIL and finish it",
    "e      end clip without a label",
    "m      add marker          s  snapshot (PNG)",
    "+ / -  output FPS up / down",
    "c      cycle color mode    0  reset color/brightness/contrast",
    "[ / ]  brightness - / +    ; / '  contrast - / +",
    "l      cycle layout        f  cycle focus camera",
    "1 2 3  show / hide camera  t  toggle timestamp",
    "h      toggle this help    q / ESC  stop and quit",
]


def now_iso(t: float | None = None) -> str:
    return dt.datetime.fromtimestamp(time.time() if t is None else t).isoformat(timespec="milliseconds")


def parse_size(s: str) -> tuple[int, int]:
    w, h = (int(v) for v in s.lower().split("x"))
    return w - w % 2, h - h % 2


# ----------------------------------------------------------------------------- devices
def list_video_devices() -> list[tuple[int, str]]:
    p = subprocess.run([FFMPEG, "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
                       capture_output=True, text=True)
    out, section = [], None
    for line in p.stderr.splitlines():
        if "video devices" in line:
            section = "v"
        elif "audio devices" in line:
            section = "a"
        elif section == "v" and (m := re.search(r"\]\s\[(\d+)\]\s(.+)$", line)):
            out.append((int(m.group(1)), m.group(2).strip()))
    return out


def assign_cameras(devices, overrides: dict[str, str | None]):
    """Return [(key, label, device_name or None)] in ROLES order."""
    cams = [(i, n) for i, n in devices if not EXCLUDE.search(n)]
    used, result = set(), []
    for key, label, pat in ROLES:
        want = overrides.get(key)
        pick = None
        for i, n in cams:
            if i in used:
                continue
            if (want and want.lower() in n.lower()) or (not want and pat.search(n)):
                pick = (i, n)
                break
        if pick:
            used.add(pick[0])
        result.append((key, label, pick[1] if pick else None))
    return result


# ----------------------------------------------------------------------------- capture
class FFmpegSource(threading.Thread):
    """Reads frames from an AVFoundation device through ffmpeg; keeps only the latest one.
    Reconnects automatically if the device drops out."""

    def __init__(self, key, label, device, out_size, fps, cap_size=None, vf_pre="", extra_in=()):
        super().__init__(daemon=True, name=f"src-{key}")
        self.key, self.label, self.device = key, label, device
        self.w, self.h = out_size
        self.fps, self.cap_size = fps, cap_size
        self.vf_pre, self.extra_in = vf_pre, list(extra_in)
        self.lock = threading.Lock()
        self.frame: np.ndarray | None = None
        self.frame_time = 0.0
        self.count = 0
        self.fps_meas = 0.0
        self.error = ""
        self.running = True
        self.proc: subprocess.Popen | None = None
        self._stderr: list[str] = []

    def _attempts(self):
        tries = [(self.cap_size, self.fps)]
        if self.cap_size:
            tries += [(self.cap_size, 30), ((640, 480), 30), (None, 30)]
        seen, out = set(), []
        for t in tries:
            if t not in seen:
                seen.add(t)
                out.append(t)
        return out

    def _cmd(self, cap_size, fps):
        cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-nostdin",
               "-f", "avfoundation", "-pixel_format", "bgr0", "-framerate", str(fps)]
        if cap_size:
            cmd += ["-video_size", f"{cap_size[0]}x{cap_size[1]}"]
        cmd += self.extra_in + ["-i", f"{self.device}:none"]
        vf = (self.vf_pre + "," if self.vf_pre else "") + (
            f"scale={self.w}:{self.h}:force_original_aspect_ratio=decrease,"
            f"pad={self.w}:{self.h}:(ow-iw)/2:(oh-ih)/2")
        cmd += ["-vf", vf, "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
        return cmd

    def _drain(self, pipe):
        for line in iter(pipe.readline, b""):
            self._stderr = (self._stderr + [line.decode(errors="replace").strip()])[-5:]

    def run(self):
        attempts, ai, backoff = self._attempts(), 0, 1.0
        n = self.w * self.h * 3
        while self.running:
            cap_size, fps = attempts[min(ai, len(attempts) - 1)]
            self._stderr = []
            self.proc = subprocess.Popen(self._cmd(cap_size, fps), stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, bufsize=0)
            threading.Thread(target=self._drain, args=(self.proc.stderr,), daemon=True).start()
            got = 0
            win_start, win_count = time.perf_counter(), 0
            buf = bytearray(n)
            while self.running:
                mv, r = memoryview(buf), 0
                while r < n:
                    k = self.proc.stdout.readinto(mv[r:])
                    if not k:
                        break
                    r += k
                if r < n:
                    break
                img = np.frombuffer(bytes(buf), np.uint8).reshape(self.h, self.w, 3)
                t = time.perf_counter()
                with self.lock:
                    self.frame, self.frame_time = img, t
                    self.count += 1
                got += 1
                self.error = ""
                win_count += 1
                if t - win_start >= 1.0:
                    self.fps_meas = win_count / (t - win_start)
                    win_start, win_count = t, 0
            self._kill()
            if not self.running:
                break
            if got == 0 and ai < len(attempts) - 1:
                ai += 1  # mode not supported -> try the next fallback right away
                continue
            self.error = (self._stderr[-1] if self._stderr else "disconnected")[:90]
            self.fps_meas = 0.0
            time.sleep(backoff)
            backoff = min(backoff * 2, 5.0)
            if got:
                backoff = 1.0

    def latest(self):
        with self.lock:
            return self.frame, self.frame_time, self.count

    def _kill(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def stop(self):
        self.running = False
        self._kill()


# ----------------------------------------------------------------------------- writing
class VideoWriter:
    """Pipes BGR frames into ffmpeg (H.264 MP4) from a background thread."""

    def __init__(self, path: Path, w: int, h: int, fps: int, codec: str, crf: int, bitrate: str):
        self.path = path
        cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
               "-s", f"{w}x{h}", "-r", str(fps), "-i", "-"]
        if codec == "hw":
            cmd += ["-c:v", "h264_videotoolbox", "-b:v", bitrate, "-allow_sw", "1"]
        else:
            cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf)]
        cmd += ["-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path)]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        self.q: queue.Queue = queue.Queue(maxsize=120)
        self.dropped = 0
        self.t = threading.Thread(target=self._loop, daemon=True)
        self.t.start()

    def _loop(self):
        while (item := self.q.get()) is not None:
            try:
                self.proc.stdin.write(item)
            except (BrokenPipeError, ValueError):
                break

    def write(self, frame: np.ndarray):
        try:
            self.q.put_nowait(frame.tobytes())
        except queue.Full:
            self.dropped += 1

    def close(self) -> str:
        self.q.put(None)
        self.t.join()
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        err = self.proc.stderr.read()
        self.proc.wait(timeout=60)
        return err.decode(errors="replace").strip()


class Clip:
    """One trial: composite MP4 (+ optional raw per-camera MP4s), frame-timing CSV, metadata JSON."""

    def __init__(self, session_dir: Path, idx: int, app: "Recorder"):
        self.idx, self.app = idx, app
        self.fps = app.fps
        self.base = session_dir / f"clip{idx:03d}"
        a = app.args
        self.video = VideoWriter(self.base.with_suffix(".mp4"), app.W, app.H, self.fps, a.codec, a.crf, a.bitrate)
        self.raw = {}
        if a.save_raw:
            for s in app.sources:
                self.raw[s.key] = VideoWriter(Path(f"{self.base}_{s.key}.mp4"), s.w, s.h, self.fps,
                                              a.codec, a.crf, a.bitrate)
        self.csv_f = open(f"{self.base}_frames.csv", "w", newline="")
        self.csv = csv.writer(self.csv_f)
        self.csv.writerow(["frame", "video_time_s", "unix_time", "wall_time"] +
                          [f"{s.key}_frame" for s in app.sources] + [f"{s.key}_age_ms" for s in app.sources])
        self.frames = 0
        self.duplicated = 0
        self.start_wall = time.time()
        self.events: list[dict] = []
        self.outcome: str | None = None
        self.event("start", settings=app.settings())

    @property
    def video_time(self) -> float:
        return self.frames / self.fps

    def event(self, kind: str, label: str = "", **extra):
        self.events.append({"type": kind, "label": label, "video_time_s": round(self.video_time, 3),
                            "wall_time": now_iso(), **extra})

    def write(self, composite, raws: dict, cam_info: list[tuple[int, float]], copies: int):
        for c in range(copies):
            self.video.write(composite)
            for k, w in self.raw.items():
                if raws.get(k) is not None:
                    w.write(raws[k])
            t = time.time()
            self.csv.writerow([self.frames, f"{self.video_time:.4f}", f"{t:.4f}", now_iso(t)] +
                              [ci[0] for ci in cam_info] + [f"{ci[1]:.1f}" for ci in cam_info])
            self.frames += 1
            self.duplicated += 1 if c else 0

    def finish(self, outcome: str | None = None) -> dict:
        if outcome:
            self.outcome = outcome
            self.event("outcome", outcome)
        self.event("end")
        errs = [self.video.close()] + [w.close() for w in self.raw.values()]
        self.csv_f.close()
        meta = {
            "clip": self.idx, "task": self.app.args.task, "outcome": self.outcome,
            "video": self.base.with_suffix(".mp4").name,
            "raw_videos": {k: w.path.name for k, w in self.raw.items()},
            "frames_csv": f"{self.base.name}_frames.csv",
            "fps": self.fps, "size": [self.app.W, self.app.H],
            "frames": self.frames, "duration_s": round(self.video_time, 3),
            "duplicated_frames": self.duplicated,
            "dropped_frames": self.video.dropped,
            "start_wall_time": now_iso(self.start_wall), "end_wall_time": now_iso(),
            "cameras": [{"key": s.key, "name": s.label, "device": s.device, "size": [s.w, s.h]}
                        for s in self.app.sources],
            "events": self.events,
            "encoder_errors": [e for e in errs if e],
        }
        self.base.with_suffix(".json").write_text(json.dumps(meta, indent=2))
        return meta


# ----------------------------------------------------------------------------- image ops
def _lut(delta_b, delta_g, delta_r):
    x = np.arange(256, dtype=np.int16)
    return np.dstack([np.clip(x + d, 0, 255) for d in (delta_b, delta_g, delta_r)]).astype(np.uint8)


LUT_WARM = _lut(-18, 0, 22)
LUT_COOL = _lut(22, 4, -18)
CLAHE = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))


def apply_color(img, mode, brightness, contrast):
    if mode == "grayscale":
        img = cv2.cvtColor(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    elif mode == "high-contrast":
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        lab[..., 0] = CLAHE.apply(lab[..., 0])
        img = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    elif mode == "warm":
        img = cv2.LUT(img, LUT_WARM)
    elif mode == "cool":
        img = cv2.LUT(img, LUT_COOL)
    elif mode == "invert":
        img = 255 - img
    if brightness or abs(contrast - 1.0) > 1e-3:
        img = cv2.convertScaleAbs(img, alpha=contrast, beta=128 * (1 - contrast) + brightness)
    return img


def put_text(img, s, org, scale=0.6, color=(235, 235, 235), thick=1, bg=(0, 0, 0), pad=5, anchor="left"):
    (tw, th), bl = cv2.getTextSize(s, FONT, scale, thick)
    x, y = org
    if anchor == "right":
        x -= tw
    elif anchor == "center":
        x -= tw // 2
    if bg is not None:
        cv2.rectangle(img, (x - pad, y - th - pad), (x + tw + pad, y + bl + pad - 2), bg, -1)
    cv2.putText(img, s, (x, y), FONT, scale, color, thick, cv2.LINE_AA)
    return tw


def fit_into(canvas, img, rect):
    x, y, w, h = rect
    ih, iw = img.shape[:2]
    s = min(w / iw, h / ih)
    nw, nh = max(2, int(iw * s)), max(2, int(ih * s))
    interp = cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR
    r = cv2.resize(img, (nw, nh), interpolation=interp)
    ox, oy = x + (w - nw) // 2, y + (h - nh) // 2
    canvas[oy:oy + nh, ox:ox + nw] = r
    return ox, oy, nw, nh


def fmt_dur(sec: float) -> str:
    m, s = divmod(max(0.0, sec), 60)
    h, m = divmod(int(m), 60)
    return f"{h:d}:{m:02d}:{s:05.2f}" if h else f"{m:02d}:{s:05.2f}"


# ----------------------------------------------------------------------------- terminal keys
class TerminalKeys:
    def __init__(self):
        self.q: queue.Queue = queue.Queue()
        self.ok = sys.stdin.isatty()
        if not self.ok:
            return
        import termios
        import tty
        self.fd = sys.stdin.fileno()
        self.old = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)
        atexit.register(self.restore)
        threading.Thread(target=self._loop, daemon=True).start()

    def restore(self):
        if self.ok:
            import termios
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)
            self.ok = False

    def _loop(self):
        while self.ok:
            r, _, _ = select.select([sys.stdin], [], [], 0.2)
            if r:
                ch = sys.stdin.read(1)
                self.q.put("esc" if ch == "\x1b" else ch)

    def get(self):
        try:
            return self.q.get_nowait()
        except queue.Empty:
            return None


# ----------------------------------------------------------------------------- app
class Recorder:
    def __init__(self, args):
        self.args = args
        self.W, self.H = parse_size(args.canvas)
        self.fps = args.fps
        self.fps_steps = sorted({5, 10, 15, 20, 24, 30, args.cam_fps, args.fps})
        self.layout = args.layout
        self.color = args.color
        self.brightness = 0
        self.contrast = 1.0
        self.show_ts = not args.no_timestamp
        self.show_help = False
        self.hidden: set[int] = set()
        self.focus = 0
        self.state = "idle"  # idle | recording | paused
        self.clip: Clip | None = None
        self.clip_idx = 0
        self.history: list[dict] = []
        self.session_dir: Path | None = None
        self.toast, self.toast_until = "", 0.0
        self.last_marker = ""
        self.pending_fps: int | None = None
        self.pending_until = 0.0
        self.running = True
        self.sources: list[FFmpegSource] = []
        self.missing: list[tuple[str, str]] = []
        self.started = time.time()

    # --- setup ---
    def build_sources(self):
        a = self.args
        if a.source == "screen":
            dev, crop = screen_device(a.screen_index), ""
            if a.crop:
                c = chrome_crop(dev) if a.crop == "chrome" else tuple(int(v) for v in a.crop.split(","))
                if c:
                    crop = "crop={2}:{3}:{0}:{1}".format(*c)
                    print(f"  screen crop (pixels): x={c[0]} y={c[1]} w={c[2]} h={c[3]}")
                else:
                    print("  ! could not find the frontend window, recording the full screen")
            self.sources = [FFmpegSource("screen", "Frontend (screen)", dev, (self.W, self.H - FOOTER_H),
                                         a.fps if a.fps > 30 else 30, None, crop, ["-capture_cursor", "1"])]
            self.layout = "single"
            return
        cam_size = parse_size(a.cam_size)
        assigned = assign_cameras(list_video_devices(),
                                  {"wrist": a.wrist, "realsense": a.realsense, "logitech": a.logitech})
        for key, label, dev in assigned:
            if dev is None:
                self.missing.append((key, label))
                print(f"  ! {label}: NOT FOUND")
                continue
            print(f"  {label:<15} <- {dev}")
            self.sources.append(FFmpegSource(key, label, dev, cam_size, a.cam_fps, cam_size))
        if not self.sources:
            sys.exit("No cameras found (FaceTime is excluded on purpose). Run with --list.")

    def settings(self):
        return {"fps": self.fps, "layout": self.layout, "color": self.color, "brightness": self.brightness,
                "contrast": round(self.contrast, 2), "timestamp": self.show_ts,
                "hidden": [self.sources[i].key for i in sorted(self.hidden) if i < len(self.sources)]}

    def ensure_session(self) -> Path:
        if self.session_dir is None:
            stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", self.args.task)
            self.session_dir = Path(self.args.out).expanduser().resolve() / f"{stamp}_{safe}"
            self.session_dir.mkdir(parents=True, exist_ok=True)
        return self.session_dir

    def say(self, msg: str, secs=2.0):
        self.toast, self.toast_until = msg, time.time() + secs
        print(f"  · {msg}")

    # --- clips ---
    def start_clip(self):
        self.clip_idx += 1
        self.clip = Clip(self.ensure_session(), self.clip_idx, self)
        self.state = "recording"
        self.say(f"REC clip {self.clip_idx:03d} @ {self.fps} fps")

    def finish_clip(self, outcome=None, quiet=False):
        if not self.clip:
            return
        meta = self.clip.finish(outcome)
        self.history.append(meta)
        self.write_session()
        if not quiet:
            o = f" [{outcome.upper()}]" if outcome else ""
            self.say(f"saved clip {meta['clip']:03d}{o}  {fmt_dur(meta['duration_s'])}  ->  {meta['video']}")
        self.clip, self.state = None, "idle"

    def apply_pending_fps(self):
        if self.pending_fps is None or time.time() < self.pending_until:
            return
        new, self.pending_fps = self.pending_fps, None
        if new == self.fps:
            return
        self.fps = new
        if self.clip:  # container FPS is fixed per file -> continue in a new clip
            was_paused, prev = self.state == "paused", self.clip.idx
            self.clip.event("split", f"fps change -> {new}, continues in clip {prev + 1:03d}")
            self.finish_clip(quiet=True)
            self.start_clip()
            self.clip.event("continues", f"continues clip {prev:03d}")
            if was_paused:
                self.state = "paused"
                self.clip.event("pause")

    def change_setting(self, what: str):
        if self.clip:
            self.clip.event("setting", what, settings=self.settings())

    def write_session(self):
        if not self.session_dir:
            return
        oc = [m["outcome"] for m in self.history]
        summary = {"task": self.args.task, "started": now_iso(self.started), "updated": now_iso(),
                   "clips": len(self.history), "success": oc.count("success"), "fail": oc.count("fail"),
                   "unlabeled": oc.count(None),
                   "clip_files": [{"clip": m["clip"], "video": m["video"], "outcome": m["outcome"],
                                   "duration_s": m["duration_s"]} for m in self.history]}
        (self.session_dir / "session.json").write_text(json.dumps(summary, indent=2))

    # --- keys ---
    def handle_key(self, k: str):
        if k in ("q", "esc"):
            self.running = False
        elif k == " ":
            if self.state == "idle":
                self.start_clip()
            elif self.state == "recording":
                self.state = "paused"
                self.clip.event("pause")
                self.say("PAUSED")
            else:
                self.state = "recording"
                self.clip.event("resume")
                self.say("RESUMED")
        elif k == "n":
            self.finish_clip()
            self.start_clip()
        elif k in ("y", "x"):
            if self.clip:
                self.finish_clip("success" if k == "y" else "fail")
            else:
                self.say("no clip open - press SPACE to start one")
        elif k == "e":
            self.finish_clip()
        elif k == "m":
            if self.clip:
                n = sum(e["type"] == "marker" for e in self.clip.events) + 1
                self.clip.event("marker", f"marker {n}")
                self.last_marker = f"marker {n} @ {fmt_dur(self.clip.video_time)}"
                self.say(self.last_marker)
            else:
                self.say("markers need an open clip")
        elif k == "s":
            self.snapshot()
        elif k in ("+", "=", "-", "_"):
            cur = self.pending_fps or self.fps
            i = self.fps_steps.index(cur) if cur in self.fps_steps else 0
            i = min(i + 1, len(self.fps_steps) - 1) if k in "+=" else max(i - 1, 0)
            if not self.clip:
                self.fps, self.pending_fps = self.fps_steps[i], None
                self.say(f"output FPS -> {self.fps}")
            else:  # applied after 1 s without further presses (avoids tiny clips)
                self.pending_fps, self.pending_until = self.fps_steps[i], time.time() + 1.0
                self.say(f"output FPS -> {self.pending_fps} (new clip in 1 s)")
        elif k == "c":
            self.color = COLOR_MODES[(COLOR_MODES.index(self.color) + 1) % len(COLOR_MODES)]
            self.say(f"color: {self.color}")
            self.change_setting("color")
        elif k in ("[", "]"):
            self.brightness = int(np.clip(self.brightness + (10 if k == "]" else -10), -100, 100))
            self.say(f"brightness {self.brightness:+d}")
            self.change_setting("brightness")
        elif k in (";", "'"):
            self.contrast = float(np.clip(self.contrast + (0.1 if k == "'" else -0.1), 0.3, 3.0))
            self.say(f"contrast {self.contrast:.1f}")
            self.change_setting("contrast")
        elif k == "0":
            self.color, self.brightness, self.contrast = "normal", 0, 1.0
            self.say("color reset")
            self.change_setting("reset")
        elif k == "l" and self.args.source == "cameras":
            self.layout = LAYOUTS[(LAYOUTS.index(self.layout) + 1) % len(LAYOUTS)]
            self.say(f"layout: {self.layout}")
            self.change_setting("layout")
        elif k == "f" and self.args.source == "cameras":
            self.focus = (self.focus + 1) % len(self.sources)
            self.say(f"focus: {self.sources[self.focus].label}")
            self.change_setting("focus")
        elif k in ("1", "2", "3") and int(k) <= len(self.sources):
            i = int(k) - 1
            self.hidden ^= {i}
            self.say(f"{self.sources[i].label}: {'hidden' if i in self.hidden else 'shown'}")
            self.change_setting("visibility")
        elif k == "t":
            self.show_ts = not self.show_ts
            self.say(f"timestamp {'on' if self.show_ts else 'off'}")
            self.change_setting("timestamp")
        elif k in ("h", "?"):
            self.show_help = not self.show_help
            if self.show_help:
                print("\n".join("    " + l for l in HELP))

    def snapshot(self):
        d = self.ensure_session() / "snapshots"
        d.mkdir(exist_ok=True)
        stamp = dt.datetime.now().strftime("%H%M%S_%f")[:-3]
        cv2.imwrite(str(d / f"{stamp}_composite.png"), self.composite)
        for s in self.sources:
            f, _, _ = s.latest()
            if f is not None:
                cv2.imwrite(str(d / f"{stamp}_{s.key}.png"), f)
        self.say(f"snapshot -> snapshots/{stamp}_*.png")

    # --- rendering ---
    def layout_rects(self):
        W, H = self.W, self.H - FOOTER_H
        vis = [i for i in range(len(self.sources)) if i not in self.hidden] or [0]
        g = 6
        if self.layout == "row":
            cw = W // len(vis)
            return [(i, (k * cw + g, g, cw - 2 * g, H - 2 * g)) for k, i in enumerate(vis)], None
        if self.layout == "single" or len(vis) == 1:
            i = self.focus if self.focus in vis else vis[0]
            return [(i, (g, g, W - 2 * g, H - 2 * g))], None
        if self.layout == "focus":
            f = self.focus if self.focus in vis else vis[0]
            others = [i for i in vis if i != f]
            bw = W * 2 // 3
            rects = [(f, (g, g, bw - 2 * g, H - 2 * g))]
            sh = H // max(1, len(others))
            rects += [(i, (bw + g, k * sh + g, W - bw - 2 * g, sh - 2 * g)) for k, i in enumerate(others)]
            return rects, None
        cw, ch = W // 2, H // 2  # grid: 2x2, last free cell becomes the info panel
        cells = [(c % 2 * cw + g, c // 2 * ch + g, cw - 2 * g, ch - 2 * g) for c in range(4)]
        rects = [(i, cells[k]) for k, i in enumerate(vis)]
        return rects, (cells[len(vis)] if len(vis) < 4 else None)

    def render(self):
        canvas = np.full((self.H, self.W, 3), 18, np.uint8)
        raws, cam_info, now = {}, [], time.perf_counter()
        for s in self.sources:
            f, ft, cnt = s.latest()
            raws[s.key] = f
            cam_info.append((cnt, (now - ft) * 1000 if f is not None else -1))
        rects, info_rect = self.layout_rects()
        screen = self.args.source == "screen"
        for i, (x, y, w, h) in rects:
            s = self.sources[i]
            f, ft, _ = s.latest()
            cv2.rectangle(canvas, (x, y), (x + w, y + h), (0, 0, 0), -1)
            if f is None or now - ft > 2.0:
                msg = "NO SIGNAL - reconnecting" if f is None or s.error else "STALLED"
                put_text(canvas, msg, (x + w // 2, y + h // 2), 0.8, (120, 140, 255), 2, None, anchor="center")
                if s.error:
                    put_text(canvas, s.error, (x + w // 2, y + h // 2 + 30), 0.45, (150, 150, 150), 1, None,
                             anchor="center")
            else:
                fit_into(canvas, apply_color(f, self.color, self.brightness, self.contrast), (x, y, w, h))
            if not screen:
                put_text(canvas, f"{i + 1}  {s.label}", (x + 12, y + 26), 0.65, (255, 255, 255), 1, (20, 20, 20))
                put_text(canvas, f"{s.fps_meas:4.1f} fps", (x + w - 10, y + 26), 0.5, (170, 230, 170), 1,
                         (20, 20, 20), anchor="right")
        if info_rect:
            self.draw_info(canvas, info_rect)
        self.draw_footer(canvas)
        return canvas, raws, cam_info

    def draw_info(self, canvas, rect):
        x, y, w, h = rect
        cv2.rectangle(canvas, (x, y), (x + w, y + h), (28, 28, 28), -1)
        t = dt.datetime.now()
        put_text(canvas, t.strftime("%H:%M:%S.") + f"{t.microsecond // 1000:03d}", (x + 30, y + 90), 2.0,
                 (255, 255, 255), 3, None)
        put_text(canvas, t.strftime("%A %Y-%m-%d"), (x + 32, y + 130), 0.8, (170, 170, 170), 1, None)
        lines = [f"task:  {self.args.task}"]
        if self.clip:
            lines.append(f"clip:  {self.clip.idx:03d}   t = {fmt_dur(self.clip.video_time)}   "
                         f"frame {self.clip.frames}")
        oc = [m["outcome"] for m in self.history]
        if self.history:
            lines.append(f"done:  {len(oc)} clips   success {oc.count('success')}   fail {oc.count('fail')}")
        if self.last_marker:
            lines.append(f"last:  {self.last_marker}")
        for k, label in self.missing:
            lines.append(f"!  {label} not connected")
        for j, l in enumerate(lines):
            put_text(canvas, l, (x + 32, y + 185 + j * 34), 0.7, (220, 220, 220), 1, None)

    def draw_footer(self, canvas):
        y0 = self.H - FOOTER_H
        canvas[y0:] = 0
        if not self.show_ts:
            return
        t = dt.datetime.now()
        stamp = t.strftime("%Y-%m-%d  %H:%M:%S.") + f"{t.microsecond // 1000:03d}"
        put_text(canvas, stamp, (16, y0 + 30), 0.75, (255, 255, 255), 2, None)
        mid = f"{self.args.task}"
        if self.clip:
            mid += f"   clip {self.clip.idx:03d}"
        put_text(canvas, mid, (self.W // 2, y0 + 30), 0.7, (200, 200, 200), 1, None, anchor="center")
        if self.clip:
            put_text(canvas, f"t {fmt_dur(self.clip.video_time)}   frame {self.clip.frames:06d}",
                     (self.W - 16, y0 + 30), 0.7, (200, 200, 200), 1, None, anchor="right")

    def preview_frame(self, composite):
        p = composite.copy()
        if self.state == "recording":
            on = int(time.time() * 2) % 2 == 0
            label, col = f"REC  {fmt_dur(self.clip.video_time)}", (40, 40, 220)
            if on:
                cv2.circle(p, (self.W - 250, 34), 10, (40, 40, 255), -1)
        elif self.state == "paused":
            label, col = f"PAUSED  {fmt_dur(self.clip.video_time)}", (0, 170, 230)
        else:
            label, col = "IDLE - SPACE to record", (90, 90, 90)
        put_text(p, label, (self.W - 20, 42), 0.8, (255, 255, 255), 2, col, 8, anchor="right")
        fps_s = f"{self.fps}->{self.pending_fps}" if self.pending_fps else f"{self.fps}"
        put_text(p, f"{fps_s} fps | {self.color} | B {self.brightness:+d} C {self.contrast:.1f} | "
                    f"{self.layout} | h = help", (self.W - 20, 82), 0.5, (230, 230, 230), 1, (30, 30, 30),
                 anchor="right")
        if self.toast and time.time() < self.toast_until:
            put_text(p, self.toast, (self.W // 2, self.H - FOOTER_H - 30), 0.9, (255, 255, 255), 2,
                     (60, 60, 60), 10, anchor="center")
        if self.show_help:
            bw, bh = 760, 40 + 34 * len(HELP)
            x0, y0 = (self.W - bw) // 2, (self.H - bh) // 2
            roi = p[y0:y0 + bh, x0:x0 + bw]
            roi[:] = (roi * 0.25).astype(np.uint8)
            for j, line in enumerate(HELP):
                put_text(p, line, (x0 + 30, y0 + 45 + j * 34), 0.65, (255, 255, 255), 1, None)
        return p

    # --- main loop ---
    def run(self):
        a = self.args
        print("NEX Arm recorder")
        self.build_sources()
        for s in self.sources:
            s.start()
        keys = TerminalKeys()
        preview = not a.no_preview
        win = "NEX Arm recorder"
        if preview:
            cv2.namedWindow(win, cv2.WINDOW_NORMAL)
            pw = a.preview_width
            cv2.resizeWindow(win, pw, int(pw * self.H / self.W))

        # wait (max 8 s) for every camera to deliver a frame before the first clip starts
        t0 = time.time()
        while time.time() - t0 < 8 and not all(s.latest()[0] is not None for s in self.sources):
            if preview:
                cv2.waitKey(50)
            else:
                time.sleep(0.05)
        for s in self.sources:
            if s.latest()[0] is None:
                print(f"  ! {s.label}: no frames yet ({s.error or 'waiting'})")

        print(f"  output: {self.W}x{self.H} @ {self.fps} fps, {a.codec}, -> {Path(a.out).resolve()}")
        print("  hotkeys: SPACE pause/resume  n next clip  y/x success/fail  m marker  s snapshot  "
              "+/- fps  c color  l layout  t timestamp  h help  q quit")
        if keys.ok:
            print("  (hotkeys also work here in the terminal)")
        if not a.idle:
            self.start_clip()

        signal.signal(signal.SIGINT, lambda *_: setattr(self, "running", False))
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "running", False))
        next_tick = time.perf_counter()
        self.composite = np.zeros((self.H, self.W, 3), np.uint8)
        try:
            while self.running:
                now = time.perf_counter()
                if now >= next_tick:
                    period = 1.0 / self.fps
                    lag = int((now - next_tick) / period)
                    if lag > self.fps:  # stalled > 1 s: resync instead of padding
                        lag, next_tick = 0, now
                    self.composite, raws, cam_info = self.render()
                    if self.state == "recording" and self.clip:
                        self.clip.write(self.composite, raws, cam_info, 1 + lag)
                    next_tick += period * (1 + lag)
                    if preview:
                        cv2.imshow(win, self.preview_frame(self.composite))
                if preview:
                    k = cv2.waitKey(1)
                    if k != -1:
                        k &= 0xFF
                        self.handle_key("esc" if k == 27 else chr(k))
                    if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
                        self.running = False
                else:
                    time.sleep(max(0.0, min(0.01, next_tick - time.perf_counter())))
                while (k := keys.get()) is not None:
                    self.handle_key(k)
                self.apply_pending_fps()
                if a.duration and self.clip and self.clip.video_time >= a.duration:
                    self.say(f"duration {a.duration}s reached")
                    self.running = False
        finally:
            self.finish_clip(quiet=True)
            for s in self.sources:
                s.stop()
            keys.restore()
            if preview:
                cv2.destroyAllWindows()
                cv2.waitKey(1)
            self.print_summary()

    def print_summary(self):
        if not self.history:
            print("No clips recorded.")
            return
        print(f"\nSession: {self.session_dir}")
        for m in self.history:
            extra = f"  dropped {m['dropped_frames']}" if m["dropped_frames"] else ""
            print(f"  clip {m['clip']:03d}  {fmt_dur(m['duration_s']):>9}  {m['frames']:6d} frames  "
                  f"{m['fps']} fps  {str(m['outcome'] or '-'):8}  {m['video']}{extra}")
        oc = [m["outcome"] for m in self.history]
        labeled = oc.count("success") + oc.count("fail")
        if labeled:
            print(f"  success rate: {oc.count('success')}/{labeled} = {100 * oc.count('success') / labeled:.0f}%")


# ----------------------------------------------------------------------------- screen mode helpers
def screen_device(index: int) -> str:
    for _, n in list_video_devices():
        if n.lower() == f"capture screen {index}":
            return n
    sys.exit(f"Capture screen {index} not found (grant Screen Recording permission to your terminal).")


def screen_pixel_size(dev: str):
    p = subprocess.run([FFMPEG, "-hide_banner", "-f", "avfoundation", "-pixel_format", "bgr0", "-i",
                        f"{dev}:none", "-frames:v", "1", "-f", "null", "-"], capture_output=True, text=True,
                       timeout=20)
    m = re.search(r"Video: rawvideo.*?, (\d+)x(\d+)", p.stderr)
    return (int(m.group(1)), int(m.group(2))) if m else None


def osa(script: str) -> str:
    return subprocess.run(["osascript", "-e", script], capture_output=True, text=True).stdout.strip()


def ensure_frontend():
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", FRONTEND_PORT)) == 0:
            return
    print(f"  starting frontend server on :{FRONTEND_PORT}")
    subprocess.Popen([sys.executable, "-m", "http.server", str(FRONTEND_PORT), "--bind", "127.0.0.1"],
                     cwd=HERE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    time.sleep(1)


def chrome_crop(dev: str):
    """Find the Chrome window showing the frontend, bring it to front, return its pixel crop rect."""
    ensure_frontend()
    url = f"localhost:{FRONTEND_PORT}"
    found = osa(f'''tell application "Google Chrome"
        repeat with w in windows
            if URL of active tab of w contains "{url}" then
                set index of w to 1
                activate
                return "ok"
            end if
        end repeat
        return ""
    end tell''')
    if not found:
        subprocess.run(["open", "-a", "Google Chrome", f"http://{url}/"])
        time.sleep(4)
    b = osa(f'tell application "Google Chrome" to get bounds of front window')
    d = osa('tell application "Finder" to get bounds of window of desktop')
    px = screen_pixel_size(dev)
    try:
        x1, y1, x2, y2 = (int(v) for v in b.split(", "))
        _, _, dw, _ = (int(v) for v in d.split(", "))
    except ValueError:
        return None
    if not px:
        return None
    scale = px[0] / dw
    x, y = max(0, int(x1 * scale)), max(0, int(y1 * scale))
    w, h = min(px[0] - x, int((x2 - x1) * scale)), min(px[1] - y, int((y2 - y1) * scale))
    return x, y, w - w % 2, h - h % 2


# ----------------------------------------------------------------------------- cli
def main():
    p = argparse.ArgumentParser(description="Record the 3 NEX Arm cameras (no FaceTime) for robotic tasks.",
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--task", default="task", help="task name (used in folder name and overlay)")
    p.add_argument("--out", default=str(HERE / "recordings"), help="output directory")
    p.add_argument("--source", choices=["cameras", "screen"], default="cameras",
                   help="cameras = capture devices directly; screen = screen-record the web frontend")
    p.add_argument("--fps", type=int, default=30, help="output FPS (change live with +/-)")
    p.add_argument("--cam-fps", type=int, default=30, help="camera capture FPS")
    p.add_argument("--cam-size", default="640x480", help="camera capture resolution")
    p.add_argument("--canvas", default="1920x1080", help="composite video resolution")
    p.add_argument("--layout", choices=LAYOUTS, default="grid")
    p.add_argument("--color", choices=COLOR_MODES, default="normal")
    p.add_argument("--codec", choices=["x264", "hw"], default="x264", help="hw = Apple VideoToolbox")
    p.add_argument("--crf", type=int, default=20, help="x264 quality (lower = better)")
    p.add_argument("--bitrate", default="12M", help="bitrate for --codec hw")
    p.add_argument("--save-raw", action="store_true", help="also save each camera unprocessed as its own MP4")
    p.add_argument("--no-timestamp", action="store_true", help="start with timestamp overlay off")
    p.add_argument("--idle", action="store_true", help="open preview but wait for SPACE before recording")
    p.add_argument("--duration", type=float, default=0, help="stop after N seconds of recording")
    p.add_argument("--no-preview", action="store_true", help="no window (hotkeys via terminal / Ctrl+C)")
    p.add_argument("--preview-width", type=int, default=1280)
    p.add_argument("--crop", help='screen mode: "x,y,w,h" in pixels, or "chrome" to find the frontend window')
    p.add_argument("--screen-index", type=int, default=0)
    p.add_argument("--wrist", help="override wrist camera device name (substring)")
    p.add_argument("--realsense", help="override RealSense device name (substring)")
    p.add_argument("--logitech", help="override Logitech device name (substring)")
    p.add_argument("--list", action="store_true", help="list cameras and their assignment, then exit")
    a = p.parse_args()

    if a.list:
        devs = list_video_devices()
        for i, n in devs:
            print(f"  [{i}] {n}{'   (excluded)' if EXCLUDE.search(n) else ''}")
        print("assignment:")
        for key, label, dev in assign_cameras(devs, {"wrist": a.wrist, "realsense": a.realsense,
                                                     "logitech": a.logitech}):
            print(f"  {label:<15} <- {dev or 'NOT FOUND'}")
        return
    if a.source == "screen" and a.preview_width == 1280:
        a.preview_width = 480  # keep the control window small so it doesn't cover the frontend
    Recorder(a).run()


if __name__ == "__main__":
    main()
