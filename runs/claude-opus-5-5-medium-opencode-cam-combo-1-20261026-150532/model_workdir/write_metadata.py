import json, datetime as dt
from pathlib import Path

D = "claude-opus-5-5-medium-opencode-cam-combo-1-20261026-150532"
HERE = Path(__file__).resolve().parent
CLIP = HERE.parent / "eval-recording" / f"20261026_150631_{D}"
SID = "ses_e85c0c150ffeWiH2XDWY4iSw3B"

raw = (HERE / "opencode_session_export.json").read_text()
data = json.loads(raw[raw.index("{"):])
msgs = []
def walk(o):
    if isinstance(o, dict):
        if o.get("type") == "assistant" and isinstance(o.get("tokens"), dict):
            msgs.append(o)
        else:
            for v in o.values():
                walk(v)
    elif isinstance(o, list):
        for v in o:
            walk(v)
walk(data)

s = dict(input=0, output=0, reasoning=0, cache_read=0, cache_write=0, cost=0.0)
for m in msgs:
    t = m["tokens"]
    s["input"] += t.get("input", 0) or 0
    s["output"] += t.get("output", 0) or 0
    s["reasoning"] += t.get("reasoning", 0) or 0
    c = t.get("cache", {}) or {}
    s["cache_read"] += c.get("read", 0) or 0
    s["cache_write"] += c.get("write", 0) or 0
    s["cost"] += m.get("cost", 0) or 0

price = {"input_per_M": 4.00, "output_incl_reasoning_per_M": 20.00, "cache_read_per_M": 0.20, "cache_write_per_M": 5.00}
list_cost = (s["input"] * 4 + (s["output"] + s["reasoning"]) * 20 + s["cache_read"] * 0.2 + s["cache_write"] * 5) / 1e6

start = dt.datetime.fromisoformat("2026-10-26T15:05:32")
end = dt.datetime.fromisoformat("2026-10-26T15:16:10")
meta = {
    "eval": "01 of 09",
    "experiment": "camera-combo eval: does more camera input improve robot manipulation",
    "task": "Place the yellow screwdriver in the bowl.",
    "model": "anthropic/claude-opus-5.5",
    "reasoning_effort": "medium",
    "harness": "opencode v2.1.4",
    "opencode_session_id": SID,
    "camera_combo": 1,
    "cameras_enabled": ["logitech", "realsense", "wrist"],
    "cameras_disabled": ["none"],
    "cameras_in_recording": ["wrist", "realsense", "logitech"],
    "disabled_camera_cutoff": "Not needed: all three cameras were enabled, so record.py ran with all three and none were hidden.",
    "start_time": start.isoformat(),
    "end_time": end.isoformat(),
    "wall_clock_duration_s": (end - start).total_seconds(),
    "llm_calls": len(msgs),
    "tokens": {
        "total_input": s["input"] + s["cache_read"] + s["cache_write"],
        "input_uncached": s["input"], "cache_read": s["cache_read"], "cache_write": s["cache_write"],
        "total_output": s["output"] + s["reasoning"],
        "output": s["output"], "reasoning": s["reasoning"],
    },
    "cost_usd_opencode_reported": round(s["cost"], 6),
    "cost_usd_provider_list_price": round(list_cost, 6),
    "price_table_usd": price,
    "outcome": "success",
    "evidence": "Final Logitech top-down frame shows the yellow screwdriver lying inside the bowl, with the arm back at its start pose. Right after release, the wrist camera showed the screwdriver resting in the bottom of the bowl. The RealSense showed the screwdriver gone from its original spot behind the bowl.",
    "budget_200_calls_exceeded": len(msgs) > 200,
    "recording": {
        "clip_folders": [CLIP.name],
        "video_files": ["clip001.mp4"],
        "clip_durations_s": [579.433],
        "recorder_starts": 1,
        "duplicated_frames": 98, "dropped_frames": 0,
    },
    "robot": {
        "joint_order": ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"],
        "start_positions_raw": [2052, 2605, 1458, 2027, 2046, 1792],
        "end_positions_raw": [2046, 2590, 1455, 2024, 2045, 1792],
        "grasp_pose_raw": [2285, 1490, 1745, 1695, 2046, 2347],
        "release_pose_raw": [1840, 1700, 1700, 1880, 2046, 1792],
    },
    "problems": [
        "No stuck joints and no crashes. The elbow ran about 30-40 units short of its target under load. The gripper stopped at about 2347 when told 2420, because it was squeezing the handle.",
        "The joint directions were unknown at the start, so the first moves were small probing moves. One reach went past the handle and had to be backed off.",
        "Snapshots came from a separate ffmpeg grab while record.py was running. One grab came back empty and was simply retried.",
        "Processes from an earlier run were still alive when this eval started: arm_server.py (PID 43076, holds /dev/tty.usbserial-110), a record.py for the ...150156 run, and http.server on port 8765. They were not started by this session, so they were left running.",
    ],
    "scripts_written": [f"{D}/robot_server.py", f"{D}/snap.sh", f"{D}/write_metadata.py"],
    "note": "Token and cost numbers are a snapshot taken before the final reply.",
}
out = CLIP / f"{D}_eval_metadata.json"
out.write_text(json.dumps(meta, indent=2))
print(out, len(msgs), s, list_cost)
