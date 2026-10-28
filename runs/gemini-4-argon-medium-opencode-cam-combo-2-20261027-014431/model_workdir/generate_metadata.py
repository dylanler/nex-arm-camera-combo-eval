#!/usr/bin/env python3
"""
Exports the opencode session JSON, parses token usage and costs,
and writes the evaluation metadata JSON file into the eval-recording clip folder.
"""
import datetime as dt
import json
import subprocess
from pathlib import Path

SESSION_ID = "ses_e8377bff7ffenvt51pnUS3R2dm"
DIR_NAME = "gemini-4-argon-medium-opencode-cam-combo-2-20261027-014431"
WORKDIR = Path(f"/Users/dylanler/github/nex-arm-3-cam-eval/{DIR_NAME}")
CLIP_DIR = Path("/Users/dylanler/github/nex-arm-3-cam-eval/eval-recording/20261027_014514_gemini-4-argon-medium-opencode-cam-combo-2-20261027-014431")
EXPORT_PATH = WORKDIR / "opencode_session_export.json"
META_OUT = CLIP_DIR / f"{DIR_NAME}_eval_metadata.json"

# 1. Get opencode version
ver_proc = subprocess.run(["/Users/dylanler/.opencode/bin/opencode", "--version"], capture_output=True, text=True, check=True)
opencode_version = ver_proc.stdout.strip()

# 2. Export session to file
with open(EXPORT_PATH, "w") as f:
    subprocess.run(["/Users/dylanler/.opencode/bin/opencode", "session", "export", SESSION_ID], stdout=f, check=True)

# 3. Parse exported session
data = json.loads(EXPORT_PATH.read_text())

messages = data.get("messages", [])
llm_calls = 0
tok_input = 0
tok_output = 0
tok_reasoning = 0
tok_cache_read = 0
tok_cache_write = 0
cost_reported = 0.0

for m in messages:
    info = m.get("info", m)
    role_or_type = info.get("role") or info.get("type") or m.get("type") or m.get("role")
    if role_or_type == "assistant":
        llm_calls += 1
        tokens = info.get("tokens") or m.get("tokens") or {}
        tok_input += int(tokens.get("input", 0) or 0)
        tok_output += int(tokens.get("output", 0) or 0)
        tok_reasoning += int(tokens.get("reasoning", 0) or 0)
        cache = tokens.get("cache") or {}
        tok_cache_read += int(cache.get("read", 0) or 0)
        tok_cache_write += int(cache.get("write", 0) or 0)
        cost_reported += float(info.get("cost", m.get("cost", 0.0)) or 0.0)

total_input_tokens = tok_input + tok_cache_read + tok_cache_write
total_output_tokens = tok_output + tok_reasoning

# Provider default list price for google/gemini-4-argon:
# input $2.00 / 1M tokens, output (incl. reasoning) $10.00 / 1M, cache read $0.10 / 1M, cache write $0.1875 / 1M
price_table = {
    "input_per_1m_usd": 2.00,
    "output_incl_reasoning_per_1m_usd": 10.00,
    "cache_read_per_1m_usd": 0.10,
    "cache_write_per_1m_usd": 0.1875,
}

cost_list_price = (
    (tok_input / 1_000_000.0) * price_table["input_per_1m_usd"]
    + (total_output_tokens / 1_000_000.0) * price_table["output_incl_reasoning_per_1m_usd"]
    + (tok_cache_read / 1_000_000.0) * price_table["cache_read_per_1m_usd"]
    + (tok_cache_write / 1_000_000.0) * price_table["cache_write_per_1m_usd"]
)

start_dt = dt.datetime.fromisoformat("2026-10-27T01:44:26.513")
end_dt = dt.datetime.now()
wall_clock_duration_s = round((end_dt - start_dt).total_seconds(), 3)

metadata = {
    "eval": "05 of 09",
    "experiment": "camera-combo eval: does more camera input improve robot manipulation",
    "task": "Place the yellow screwdriver in the bowl.",
    "model": "google/gemini-4-argon",
    "reasoning_effort": "medium",
    "harness": f"opencode {opencode_version}",
    "opencode_session_id": SESSION_ID,
    "camera_combo": 2,
    "cameras_enabled": ["logitech", "wrist"],
    "cameras_disabled": ["realsense"],
    "cameras_in_recording": ["wrist", "logitech"],
    "disabled_camera_cutoff_method": (
        "Passed '--realsense __disabled__' to record.py so assign_cameras() did not match the "
        "Intel RealSense D415 device, completely excluding it from FFmpeg capture and the composite recording. "
        "In arm_ctl.py, only the Logitech C922 and Robot Wrist (icspring) cameras were queried via ffmpeg."
    ),
    "start_time": start_dt.isoformat(timespec="milliseconds"),
    "end_time": end_dt.isoformat(timespec="milliseconds"),
    "wall_clock_duration_s": wall_clock_duration_s,
    "llm_calls": llm_calls,
    "tokens": {
        "total_input_tokens": total_input_tokens,
        "input_tokens": tok_input,
        "cache_read_tokens": tok_cache_read,
        "cache_write_tokens": tok_cache_write,
        "total_output_tokens": total_output_tokens,
        "output_tokens": tok_output,
        "reasoning_tokens": tok_reasoning,
    },
    "cost_usd_opencode_reported": round(cost_reported, 6),
    "cost_usd_provider_list_price": round(cost_list_price, 6),
    "price_table_usd_per_1m_tokens": price_table,
    "outcome": "success",
    "budget_200_calls_exceeded": llm_calls > 200,
    "camera_evidence_at_end": (
        "Both the top-down Logitech C922 view and the Robot Wrist camera view (step34_released_and_home) "
        "clearly show the yellow screwdriver resting completely inside the gray bowl, and the robot arm "
        "returned cleanly to its home position with the gripper open."
    ),
    "recording": {
        "clip_folders": ["20261027_014514_gemini-4-argon-medium-opencode-cam-combo-2-20261027-014431"],
        "video_files": ["clip001.mp4"],
        "clip_durations_s": [965.6],
        "recorder_start_count": 1,
    },
    "robot": {
        "measured_joint_positions_start": {
            "shoulder_pan": 2050,
            "shoulder_lift": 2611,
            "elbow_flex": 1482,
            "wrist_flex": 2023,
            "wrist_roll": 2046,
            "gripper": 1793,
        },
        "measured_joint_positions_end": {
            "shoulder_pan": 2044,
            "shoulder_lift": 2613,
            "elbow_flex": 1468,
            "wrist_flex": 2035,
            "wrist_roll": 2045,
            "gripper": 1790,
        },
    },
    "problems_encountered": (
        "Minor servo compliance/stiction on shoulder_lift when descending near the table surface "
        "(e.g. commanding 1370 stopped around 1407-1410 due to table contact/gravity load), "
        "and gripper stall at ~2360 when firmly gripping the screwdriver handle (commanded 2800). "
        "No crashes or serial disconnects occurred."
    ),
    "scripts_written": [
        f"{DIR_NAME}/arm_ctl.py",
        f"{DIR_NAME}/generate_metadata.py",
    ],
    "note": "Token and cost numbers are a snapshot taken from the exported session before the final assistant reply.",
}

META_OUT.write_text(json.dumps(metadata, indent=2))
print(json.dumps(metadata, indent=2))
