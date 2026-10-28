import json
import subprocess
from pathlib import Path

D = Path(__file__).resolve().parent
NAME = D.name
SID = "ses_e85b2f692ffez2nDvsTBrmgIX1"
CLIP = D.parent / "eval-recording" / f"20261026_152158_{NAME}"
OC = str(Path.home() / ".opencode/bin/opencode")

exp = D / "opencode_session_export.json"
with open(exp, "w") as f:
    subprocess.run([OC, "session", "export", SID], stdout=f, cwd=D.parent, check=True)
data = json.loads(exp.read_text())


def walk(o):
    if isinstance(o, dict):
        if o.get("type") == "assistant" and isinstance(o.get("tokens"), dict):
            yield o
        else:
            for v in o.values():
                yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v)


msgs = list(walk(data))
s = dict(input=0, output=0, reasoning=0, cache_read=0, cache_write=0, cost=0.0)
for m in msgs:
    t = m["tokens"]
    s["input"] += t.get("input", 0) or 0
    s["output"] += t.get("output", 0) or 0
    s["reasoning"] += t.get("reasoning", 0) or 0
    s["cache_read"] += (t.get("cache") or {}).get("read", 0) or 0
    s["cache_write"] += (t.get("cache") or {}).get("write", 0) or 0
    s["cost"] += m.get("cost", 0) or 0

price = {"input": 4.00, "output_incl_reasoning": 20.00, "cache_read": 0.20, "cache_write": 5.00, "unit": "USD per 1M tokens"}
list_cost = (s["input"] * 4 + (s["output"] + s["reasoning"]) * 20 + s["cache_read"] * 0.2 + s["cache_write"] * 5) / 1e6

clip = json.loads((CLIP / "clip001.json").read_text())
log = [json.loads(l) for l in (D / "robot_log.jsonl").read_text().splitlines()]
start_pos = log[0]["pos"]
end_pos = log[-1]["resp"]["actual"]
st, et = (D / "start_time.txt").read_text().strip(), (D / "end_time.txt").read_text().strip()
import datetime as dt
dur = (dt.datetime.fromisoformat(et) - dt.datetime.fromisoformat(st)).total_seconds()

meta = {
    "eval": "02 of 09",
    "experiment": "camera-combo eval: does more camera input improve robot manipulation",
    "task": "Place the yellow screwdriver in the bowl.",
    "model": "anthropic/claude-opus-5.5",
    "reasoning_effort": "medium",
    "harness": "opencode " + subprocess.run([OC, "--version"], capture_output=True, text=True).stdout.strip(),
    "opencode_session_id": SID,
    "camera_combo": 2,
    "cameras_enabled": ["logitech", "wrist"],
    "cameras_disabled": ["realsense"],
    "cameras_in_recording": [c["key"] for c in clip["cameras"]],
    "disabled_camera_cutoff_method": "record.py launched with --realsense DISABLED_NO_SUCH_CAMERA so the RealSense device is never matched/opened (recorded composite contains only wrist + logitech tiles); the agent's own perception snapshots (r.sh snap, ffmpeg) only opened 'C922 Pro Stream Webcam' and 'icspring camera'. RealSense was never read.",
    "start_time": st,
    "end_time": et,
    "wall_clock_duration_s": dur,
    "llm_calls": len(msgs),
    "tokens": {
        "total_input": s["input"] + s["cache_read"] + s["cache_write"],
        "input": s["input"], "cache_read": s["cache_read"], "cache_write": s["cache_write"],
        "total_output": s["output"] + s["reasoning"],
        "output": s["output"], "reasoning": s["reasoning"],
    },
    "cost_usd_opencode_reported": round(s["cost"], 6),
    "cost_usd_provider_list_price": round(list_cost, 6),
    "price_table": price,
    "outcome": "success",
    "evidence": "Final Logitech top-down frame (snaps/152834_top.jpg) shows the yellow screwdriver lying inside the gray bowl with the arm moved clear; the wrist camera at release (snaps/152812_wrist.jpg) shows the screwdriver tip inside the bowl.",
    "budget_200_calls_exceeded": len(msgs) > 200,
    "recording": {
        "clip_folders": [CLIP.name],
        "video_files": [clip["video"]],
        "clip_durations_s": [clip["duration_s"]],
        "recorder_start_count": 1,
        "note": "Recorder started (15:21:58) before the robot server connected / first move; stopped with SIGINT after arm returned to start pose (q via stdin fifo was not picked up).",
    },
    "robot": {
        "joint_order": ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"],
        "start_positions_raw": start_pos,
        "end_positions_raw": end_pos,
        "grasp_pose_raw": [2265, 1540, 1900, 2080, 2045, 2338],
        "release_pose_raw": [1862, 1758, 2060, 2200, 2047, 2338],
    },
    "problems": [
        "Serial port /dev/tty.usbserial-110 and TCP 8799 were held by a stale arm_server.py and a still-running record.py from a previous eval (combo-1-20261026-150156); stopped them (SIGTERM / SIGINT so the old recorder saved its clip) before connecting.",
        "Elbow_flex consistently lagged target by ~30-40 raw units under load (gravity); gripper stalled at ~2338 when gripping the handle (expected, object blocking).",
        "record.py did not respond to 'q' over a fifo stdin; stopped with SIGINT instead, clip saved cleanly (0 dropped / 0 duplicated frames).",
        "No crashes or camera lag observed.",
    ],
    "scripts_written": ["robot_server.py (persistent NexArm TCP server with smooth interpolated moves)", "r.sh (client: read/move/pos/quit + snap of logitech & wrist cams via ffmpeg)", "write_metadata.py (this file)"],
    "note": "Token/cost numbers are a snapshot taken before the agent's final reply.",
}
out = CLIP / f"{NAME}_eval_metadata.json"
out.write_text(json.dumps(meta, indent=2))
print(out, meta["llm_calls"], meta["tokens"], meta["cost_usd_opencode_reported"], meta["cost_usd_provider_list_price"])
