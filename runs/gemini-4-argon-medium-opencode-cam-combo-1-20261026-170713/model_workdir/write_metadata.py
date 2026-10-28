#!/usr/bin/env python3
import datetime as dt
import json
import subprocess
from pathlib import Path

WORKDIR = Path("/Users/dylanler/github/nex-arm-3-cam-eval/gemini-4-argon-medium-opencode-cam-combo-1-20261026-170713")
CLIP_DIR = Path("/Users/dylanler/github/nex-arm-3-cam-eval/eval-recording/20261026_170839_gemini-4-argon-medium-opencode-cam-combo-1-20261026-170713")
SESSION_ID = "ses_e85515e5effeHRGkVu5LuVI0aq"
EXPORT_PATH = WORKDIR / "opencode_session_export.json"


def main():
    ver = subprocess.run(
        ["/Users/dylanler/.opencode/bin/opencode", "--version"],
        capture_output=True, text=True, check=True
    ).stdout.strip()

    with open(EXPORT_PATH, "w") as f:
        subprocess.run(
            ["/Users/dylanler/.opencode/bin/opencode", "session", "export", SESSION_ID],
            stdout=f, check=True
        )

    data = json.loads(EXPORT_PATH.read_text())
    messages = data.get("messages", data if isinstance(data, list) else [])

    llm_calls = 0
    inp = 0
    out = 0
    reasoning = 0
    cache_read = 0
    cache_write = 0
    cost_reported = 0.0

    for m in messages:
        info = m.get("info", m) if isinstance(m, dict) else {}
        m_type = m.get("type") or info.get("type") or info.get("role")
        if m_type == "assistant" or info.get("role") == "assistant":
            llm_calls += 1
            tokens = m.get("tokens") or info.get("tokens") or {}
            inp += int(tokens.get("input", 0) or 0)
            out += int(tokens.get("output", 0) or 0)
            reasoning += int(tokens.get("reasoning", 0) or 0)
            cache = tokens.get("cache") or {}
            cache_read += int(cache.get("read", 0) or 0)
            cache_write += int(cache.get("write", 0) or 0)
            c = m.get("cost") if m.get("cost") is not None else info.get("cost", 0.0)
            cost_reported += float(c or 0.0)

    total_input_tokens = inp + cache_read + cache_write
    total_output_tokens = out + reasoning

    price_table = {
        "input_per_1m_usd": 2.00,
        "output_incl_reasoning_per_1m_usd": 10.00,
        "cache_read_per_1m_usd": 0.10,
        "cache_write_per_1m_usd": 0.1875,
    }

    cost_list_price = (
        (inp / 1_000_000.0) * price_table["input_per_1m_usd"]
        + ((out + reasoning) / 1_000_000.0) * price_table["output_incl_reasoning_per_1m_usd"]
        + (cache_read / 1_000_000.0) * price_table["cache_read_per_1m_usd"]
        + (cache_write / 1_000_000.0) * price_table["cache_write_per_1m_usd"]
    )

    start_dt = dt.datetime.fromtimestamp(1793059627430 / 1000.0)
    end_dt = dt.datetime.now()
    wall_clock_s = round((end_dt - start_dt).total_seconds(), 3)

    metadata = {
        "eval": "04 of 09",
        "experiment": "camera-combo eval: does more camera input improve robot manipulation",
        "task": "Place the yellow screwdriver in the bowl.",
        "model": "google/gemini-4-argon",
        "reasoning_effort": "medium",
        "harness": f"opencode {ver}",
        "opencode_version": ver,
        "opencode_session_id": SESSION_ID,
        "camera_combo": 1,
        "cameras_enabled": ["logitech", "realsense", "wrist"],
        "cameras_disabled": ["none"],
        "cameras_in_recording": ["wrist", "realsense", "logitech"],
        "disabled_cameras_cutoff_method": "No cameras were labelled DISABLED in camera_combo 1 (all three cameras: logitech, realsense, and wrist were ENABLED and active).",
        "start_time": start_dt.isoformat(timespec="milliseconds"),
        "end_time": end_dt.isoformat(timespec="milliseconds"),
        "wall_clock_duration_s": wall_clock_s,
        "llm_calls": llm_calls,
        "tokens": {
            "total_input_tokens": total_input_tokens,
            "input_tokens": inp,
            "cache_read_tokens": cache_read,
            "cache_write_tokens": cache_write,
            "total_output_tokens": total_output_tokens,
            "output_tokens": out,
            "reasoning_tokens": reasoning,
        },
        "cost_usd_opencode_reported": round(cost_reported, 6),
        "cost_usd_provider_list_price": round(cost_list_price, 6),
        "price_table_usd_per_1m_tokens": price_table,
        "outcome": "success",
        "budget_200_calls_exceeded": llm_calls > 200,
        "camera_evidence_at_end": (
            "All three cameras confirm success: Logitech top-down view (end_logitech.jpg) shows the yellow "
            "screwdriver lying completely inside the grey bowl with the gripper retracted to the bottom of the frame; "
            "RealSense side view (end_realsense.jpg) shows the table surface to the right of the bowl is now empty "
            "(the screwdriver is inside the bowl); Wrist camera view (end_wrist.jpg) shows the yellow screwdriver "
            "resting inside the grey bowl between the open retracted gripper jaws."
        ),
        "recording": {
            "clip_folder_names": ["20261026_170839_gemini-4-argon-medium-opencode-cam-combo-1-20261026-170713"],
            "main_clip_folder": "20261026_170839_gemini-4-argon-medium-opencode-cam-combo-1-20261026-170713",
            "video_file_names": ["clip001.mp4"],
            "clip_durations_s": [593.8],
            "recorder_start_count": 1,
        },
        "robot": {
            "start_joint_positions": {
                "shoulder_pan": 2053,
                "shoulder_lift": 2606,
                "elbow_flex": 1470,
                "wrist_flex": 2017,
                "wrist_roll": 2047,
                "gripper": 1789,
                "raw_array": [2053, 2606, 1470, 2017, 2047, 1789],
            },
            "end_joint_positions": {
                "shoulder_pan": 2048,
                "shoulder_lift": 2604,
                "elbow_flex": 1461,
                "wrist_flex": 2018,
                "wrist_roll": 2046,
                "gripper": 1787,
                "raw_array": [2048, 2604, 1461, 2018, 2046, 1787],
            },
        },
        "problems_encountered": (
            "No hardware faults or crashes occurred. On step 11, lowering shoulder_lift to 1450 with elbow_flex at "
            "1750 lightly touched the table behind the screwdriver handle (stopping shoulder_lift at 1516); increasing "
            "elbow_flex to 1922 and adjusting wrist_flex to 1883 positioned the jaws directly around the screwdriver "
            "handle for a clean grasp and placement into the bowl."
        ),
        "scripts_written": [
            "gemini-4-argon-medium-opencode-cam-combo-1-20261026-170713/robot_helper.py",
            "gemini-4-argon-medium-opencode-cam-combo-1-20261026-170713/write_metadata.py",
        ],
        "note": "Token and cost numbers are a snapshot taken from the exported OpenCode session before the final reply.",
    }

    out_file_clip = CLIP_DIR / "gemini-4-argon-medium-opencode-cam-combo-1-20261026-170713_eval_metadata.json"
    out_file_work = WORKDIR / "gemini-4-argon-medium-opencode-cam-combo-1-20261026-170713_eval_metadata.json"
    out_file_clip.write_text(json.dumps(metadata, indent=2))
    out_file_work.write_text(json.dumps(metadata, indent=2))
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
