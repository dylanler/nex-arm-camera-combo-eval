#!/usr/bin/env python3
import json
import subprocess
import datetime as dt
from pathlib import Path

SESSION_ID = "ses_e83633cadffe1ls5JktmyrqvQY"
WORK_DIR = Path("/Users/dylanler/github/nex-arm-3-cam-eval/gemini-4-argon-medium-opencode-cam-combo-3-20261027-020702")
EXPORT_FILE = WORK_DIR / "opencode_session_export.json"
CLIP_DIR = Path("/Users/dylanler/github/nex-arm-3-cam-eval/eval-recording/20261027_020822_gemini-4-argon-medium-opencode-cam-combo-3-20261027-020702")
META_FILE = CLIP_DIR / "gemini-4-argon-medium-opencode-cam-combo-3-20261027-020702_eval_metadata.json"

# Export session
subprocess.run(f"~/.opencode/bin/opencode session export {SESSION_ID} > {EXPORT_FILE}", shell=True, check=True)
ver = subprocess.check_output(["/Users/dylanler/.opencode/bin/opencode", "--version"], text=True).strip()

data = json.loads(EXPORT_FILE.read_text())

messages = data.get("messages", [])
llm_calls = 0
inp_tok = 0
out_tok = 0
reas_tok = 0
cache_r = 0
cache_w = 0
cost_reported = 0.0

for m in messages:
    info = m.get("info", m)
    role = info.get("role") or info.get("type") or m.get("type")
    if role == "assistant":
        llm_calls += 1
        t = info.get("tokens", {})
        inp_tok += int(t.get("input", 0) or 0)
        out_tok += int(t.get("output", 0) or 0)
        reas_tok += int(t.get("reasoning", 0) or 0)
        c = t.get("cache", {}) or {}
        cache_r += int(c.get("read", 0) or 0)
        cache_w += int(c.get("write", 0) or 0)
        cost_reported += float(info.get("cost", 0.0) or 0.0)

# Price table for google/gemini-4-argon:
# input $2.00 / 1M tokens, output (incl. reasoning) $10.00 / 1M, cache read $0.10 / 1M, cache write $0.1875 / 1M
price_table = {
    "input_per_1m_usd": 2.00,
    "output_including_reasoning_per_1m_usd": 10.00,
    "cache_read_per_1m_usd": 0.10,
    "cache_write_per_1m_usd": 0.1875
}

total_input_tokens = inp_tok + cache_r + cache_w
total_output_tokens = out_tok + reas_tok

cost_list = (
    (inp_tok / 1_000_000.0) * price_table["input_per_1m_usd"]
    + (total_output_tokens / 1_000_000.0) * price_table["output_including_reasoning_per_1m_usd"]
    + (cache_r / 1_000_000.0) * price_table["cache_read_per_1m_usd"]
    + (cache_w / 1_000_000.0) * price_table["cache_write_per_1m_usd"]
)

start_dt = dt.datetime.fromisoformat("2026-10-27T02:06:56-07:00")
end_dt = dt.datetime.now().astimezone()
wall_duration_s = round((end_dt - start_dt).total_seconds(), 2)

metadata = {
    "eval": "06 of 09",
    "experiment": "camera-combo eval: does more camera input improve robot manipulation",
    "task": "Place the yellow screwdriver in the bowl.",
    "model": "google/gemini-4-argon",
    "reasoning_effort": "medium",
    "harness": ver,
    "opencode_session_id": SESSION_ID,
    "camera_combo": 3,
    "cameras_enabled": ["wrist"],
    "cameras_disabled": ["logitech", "realsense"],
    "cameras_in_recording": ["wrist"],
    "how_disabled_cameras_cut_off": "Passed --realsense DISABLED_NONE --logitech DISABLED_NONE to record.py so FFmpegSource was never created or opened for RealSense D415 or Logitech C922, and updated app.js in the web frontend so RealSense and Logitech matchers returned false during the eval (reverted after completion).",
    "start_time": start_dt.isoformat(),
    "end_time": end_dt.isoformat(),
    "wall_clock_duration_s": wall_duration_s,
    "llm_calls": llm_calls,
    "tokens": {
        "total_input_tokens": total_input_tokens,
        "input": inp_tok,
        "cache_read": cache_r,
        "cache_write": cache_w,
        "total_output_tokens": total_output_tokens,
        "output": out_tok,
        "reasoning": reas_tok
    },
    "cost_usd_opencode_reported": round(cost_reported, 6),
    "cost_usd_provider_list_price": round(cost_list, 6),
    "price_table_usd_per_1m_tokens": price_table,
    "outcome": "success",
    "evidence": "The final wrist camera frame (and recording clip001.mp4) clearly shows the yellow screwdriver resting completely inside the grey bowl, with the gripper open and returned to the home pose above the bowl.",
    "budget_200_calls_exceeded": llm_calls > 200,
    "recording": {
        "clip_folders": ["20261027_020822_gemini-4-argon-medium-opencode-cam-combo-3-20261027-020702"],
        "video_file_names": ["clip001.mp4"],
        "clip_durations_s": [802.3],
        "recorder_start_count": 1
    },
    "robot": {
        "start_joint_positions": {
            "shoulder_pan": 2044,
            "shoulder_lift": 2614,
            "elbow_flex": 1458,
            "wrist_flex": 2035,
            "wrist_roll": 2044,
            "gripper": 1789
        },
        "end_joint_positions": {
            "shoulder_pan": 2041,
            "shoulder_lift": 2619,
            "elbow_flex": 1448,
            "wrist_flex": 2048,
            "wrist_roll": 2043,
            "gripper": 1786
        }
    },
    "problems_and_scripts": {
        "problems_hit": [
            "Initial ffmpeg snapshot without -pixel_format bgr0 printed a yuv420p warning on macOS AVFoundation; added -pixel_format bgr0 to fix.",
            "Occasional corrupted or byte-shifted serial position reads (e.g., 4095 or shifted array values) from the NexArm AT32 bridge; mitigated by adding safe_read_positions() requiring two consecutive consistent reads within bounds."
        ],
        "scripts_written": [
            "gemini-4-argon-medium-opencode-cam-combo-3-20261027-020702/robot_ctl.py",
            "gemini-4-argon-medium-opencode-cam-combo-3-20261027-020702/generate_metadata.py"
        ]
    },
    "note": "Token and cost numbers are a snapshot taken before the final assistant reply."
}

META_FILE.write_text(json.dumps(metadata, indent=2))
print("Wrote metadata to", META_FILE)
print(json.dumps(metadata, indent=2))
