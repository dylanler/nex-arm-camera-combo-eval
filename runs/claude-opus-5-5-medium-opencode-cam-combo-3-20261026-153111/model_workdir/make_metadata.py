import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
NAME = os.path.basename(HERE)
CLIP = "20261026_153228_" + NAME
OUT = f"/Users/dylanler/github/nex-arm-3-cam-eval/eval-recording/{CLIP}/{NAME}_eval_metadata.json"

raw = open(os.path.join(HERE, "opencode_session_export.json")).read()
data = json.loads(raw[raw.index("{"):])
msgs = []
def walk(o):
    if isinstance(o, dict):
        if o.get("type") == "assistant" and isinstance(o.get("tokens"), dict):
            msgs.append(o); return
        if o.get("role") == "assistant" and isinstance(o.get("tokens"), dict):
            msgs.append(o); return
        for v in o.values(): walk(v)
    elif isinstance(o, list):
        for v in o: walk(v)
walk(data)
s = dict(input=0, output=0, reasoning=0, cache_read=0, cache_write=0, cost=0.0)
for m in msgs:
    t = m["tokens"]; c = t.get("cache", {}) or {}
    s["input"] += t.get("input", 0) or 0
    s["output"] += t.get("output", 0) or 0
    s["reasoning"] += t.get("reasoning", 0) or 0
    s["cache_read"] += c.get("read", 0) or 0
    s["cache_write"] += c.get("write", 0) or 0
    s["cost"] += m.get("cost", 0) or 0
price = {"input_per_1M": 4.00, "output_incl_reasoning_per_1M": 20.00, "cache_read_per_1M": 0.20, "cache_write_per_1M": 5.00}
list_cost = (s["input"] * 4 + (s["output"] + s["reasoning"]) * 20 + s["cache_read"] * 0.2 + s["cache_write"] * 5) / 1e6

log = [json.loads(l) for l in open(os.path.join(HERE, "robot_log.jsonl"))]
start_pos = log[0]["pos"]
end_pos = log[-1]["pos"]

meta = {
    "eval": "03 of 09",
    "experiment": "camera-combo eval: does more camera input improve robot manipulation",
    "task": "Place the yellow screwdriver in the bowl.",
    "model": "anthropic/claude-opus-5.5",
    "reasoning_effort": "medium",
    "harness": "opencode v2.1.4",
    "opencode_session_id": "ses_e85a93f8cffeVQYIlDmJeSs3j2",
    "camera_combo": 3,
    "cameras_enabled": ["wrist"],
    "cameras_disabled": ["logitech", "realsense"],
    "cameras_in_recording": ["wrist (icspring camera)"],
    "disabled_camera_cutoff_method": "record.py was launched with --realsense DISABLED_NO_DEVICE --logitech DISABLED_NO_DEVICE, so no device matched and those cameras were never opened (recorder logged 'NOT FOUND'; clip001.json lists only the wrist camera). The agent's own control server only opened the wrist camera ('icspring camera') via ffmpeg for its snapshots. The browser frontend from start.sh was left running as instructed but was never used for perception.",
    "start_time": "2026-10-26T15:32:27-07:00",
    "end_time": "2026-10-26T15:45:48-07:00",
    "wall_clock_duration_s": 801,
    "llm_calls": len(msgs),
    "input_tokens": {"total": s["input"] + s["cache_read"] + s["cache_write"], "input_uncached": s["input"], "cache_read": s["cache_read"], "cache_write": s["cache_write"]},
    "output_tokens": {"total": s["output"] + s["reasoning"], "output": s["output"], "reasoning": s["reasoning"]},
    "cost_usd_opencode_reported": round(s["cost"], 4),
    "cost_usd_provider_list_price": round(list_cost, 4),
    "price_table_usd": price,
    "outcome": "success",
    "outcome_evidence": "After release and lift, the wrist camera (snapshots 154510_move.jpg and 154523_move.jpg) shows the yellow screwdriver lying fully inside the grey bowl (handle and shaft both inside the rim). The arm then returned to its start pose.",
    "budget_200_calls_exceeded": len(msgs) > 200,
    "recording": {
        "clip_folders": [CLIP],
        "video_files": ["clip001.mp4"],
        "clip_durations_s": [800.133],
        "recorder_start_count": 1,
        "note": "Composite 1920x1080 @30fps, wrist camera only; 0 dropped frames.",
    },
    "robot": {
        "joint_order": ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"],
        "start_positions_raw": start_pos,
        "end_positions_raw": end_pos,
        "grasp_pose_raw_target": [2275, 1147, 2890, 3080, 2051, 2833],
        "release_pose_raw_target": [1940, 1600, 2780, 3060, 2051, 1700],
    },
    "problems": [
        "No joint map/IK was available, so the joint directions had to be found by trial with the wrist camera; most of the moves went into this.",
        "Elbow and shoulder settle 20-50 raw units short of their targets under load (gravity sag); wrist_flex seems to top out around 3080.",
        "One move (shoulder_lift 2300 with elbow at about 967) pushed the gripper or camera into the table; the arm backed off right away and nothing was damaged.",
        "The first two grasp attempts closed above the handle (the gripper reached about 2779 without stalling). The third attempt went lower until the shoulder stalled at the table and grasped the shaft next to the handle (the gripper stalled at about 2752).",
        "The robot server did not react to SIGINT while running in the background under nohup, so it was stopped with SIGTERM and the serial port was released.",
    ],
    "scripts": {
        "robot_server.py": "HTTP server on 127.0.0.1:8790. It holds the NexArm serial port (lerobot NexArmMotorsBus, /dev/tty.usbserial-110), makes smooth interpolated joint moves (/move), and saves a wrist-camera-only snapshot after each move.",
        "make_metadata.py": "Parses the opencode session export and the robot log, then writes this JSON.",
    },
    "processes_stopped": "recorder (SIGINT), robot_server.py (SIGTERM, serial port released), and the start.sh http.server on port 8770. An unrelated http.server on port 8765 that was already running from 01:43 was left untouched.",
    "token_cost_note": "Token and cost numbers are a snapshot taken before the agent's final reply, so the last few calls are not included.",
}
json.dump(meta, open(OUT, "w"), indent=2)
print(json.dumps({k: meta[k] for k in ["llm_calls", "input_tokens", "output_tokens", "cost_usd_opencode_reported", "cost_usd_provider_list_price"]}), start_pos, end_pos)
