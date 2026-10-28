#!/usr/bin/env python3
"""Manual-protocol hooks for the NexArm camera-combo eval (you call opencode yourself).

  python3 eval-harness/eval_hooks.py gen            # (re)generate eval-prompts/*.md
  python3 eval-harness/eval_hooks.py start NN       # BEFORE opencode: clean slate, home + joint check,
                                                    # snapshots, then spawns a background watcher that
                                                    # records tokens/cost/metadata when the run ends
  python3 eval-harness/eval_hooks.py prompt NN      # print the exact prompt for eval NN
  python3 eval-harness/eval_hooks.py status NN      # live LLM-call count / cost
  python3 eval-harness/eval_hooks.py cancel NN      # stop eval NN now (counted as FAIL)
  python3 eval-harness/eval_hooks.py finish NN      # manual fallback: post-run accounting + home + notify
  python3 eval-harness/eval_hooks.py summary        # table of all finished evals

The watcher enforces the 200-LLM-call cap and a 120 min wall cap, finds the opencode session by its
--title, and after the session goes idle: stops leftover recorder / frontend / arm-control processes,
takes final scene snapshots, restores the arm home, exports the session, computes tokens + cost,
writes <prefix>_eval_metadata.json into the recording clip folder, and rings a notification.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

HARNESS = Path(__file__).resolve().parent
sys.path.insert(0, str(HARNESS))
import run_evals as R  # noqa: E402  (shared helpers: accounting, audit, snapshots, arm, notify ...)

PROJECT = R.PROJECT
PROMPTS = PROJECT / "eval-prompts"
STATE = HARNESS / "manual_runs"
LLM_CALL_BUDGET = 200
WALL_TIMEOUT_S = 120 * 60

EVALS = {  # NN -> (model key, camera combo)   order requested by operator: model-major
    1: ("opus", 1), 2: ("opus", 2), 3: ("opus", 3),
    4: ("gemini", 1), 5: ("gemini", 2), 6: ("gemini", 3),
    7: ("gpt", 1), 8: ("gpt", 2), 9: ("gpt", 3),
}


def ids(nn):
    mk, combo = EVALS[nn]
    m = R.MODELS[mk]
    prefix = f"{m['slug']}-opencode-cam-combo-{combo}"
    title = f"eval{nn:02d}-{prefix}"
    md = PROMPTS / f"eval{nn:02d}_{m['slug']}_cam-combo-{combo}.md"
    return mk, combo, m, prefix, title, md


def log(nn, msg):
    line = f"[{dt.datetime.now():%H:%M:%S}] eval{nn:02d} {msg}"
    print(line, flush=True)
    STATE.mkdir(exist_ok=True)
    with open(STATE / "hooks.log", "a") as f:
        f.write(line + "\n")


def sdir(nn):
    d = STATE / f"eval{nn:02d}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_state(nn):
    p = sdir(nn) / "state.json"
    return json.loads(p.read_text()) if p.exists() else {}


def save_state(nn, st):
    (sdir(nn) / "state.json").write_text(json.dumps(st, indent=2))


# ------------------------------------------------------------------ prompt files
def camera_lines(combo):
    en = R.COMBOS[combo]
    return "\n".join(f"- {R.CAMS[k][0]} {'ENABLED' if k in en else 'DISABLED'}" for k in ("logitech", "realsense", "wrist"))


def prompt_text(nn):
    _, combo, _, prefix, _, _ = ids(nn)
    return f"""Create a directory called {prefix}-<current datetime as YYYYMMDD-HHMMSS> inside /Users/dylanler/github/nex-arm-3-cam-eval.  Create any needed scripts or files in that directory.

Your task is to control the Hiwonder Nexarm robot to perform this task below:

Place the yellow screwdriver in the bowl.

Refer to this repo for how to control the robot:
/Users/dylanler/github/lerobot-nexarm

This is the robot arm's STP file:
/Users/dylanler/github/nex-arm-3-cam-eval/nexarm-follower-stp-file/NexArm.stp

Use web search if necessary.  Do not refer to other files or directories on this computer.

Use the script:
/Users/dylanler/github/nex-arm-3-cam-eval/record.py to record the frontend camera view at /Users/dylanler/github/nex-arm-3-cam-eval/index.html immediately when you start moving the robot arm.  Use the same directory name as the task name for the recording so the clip folder is named descriptively.

For this eval, these would be the camera settings:
{camera_lines(combo)}

If the camera is labelled DISABLED, please do not use that camera and cut off the recording signal from that camera.

Remember to start the app first via /Users/dylanler/github/nex-arm-3-cam-eval/start.sh

Once the task is succesful, stop the recording and store it in the /Users/dylanler/github/nex-arm-3-cam-eval/eval-recording folder.

When you are finished (success or not), stop every process you started (recorder, app server, any robot-control server) so the robot's serial port is released.

We will cap the task budget at 200 LLM calls to the model within the coding harness driving the robot arm.  If you exceed this task budget, the task is considered a fail and we stop recording immediately."""


def md_text(nn):
    mk, combo, m, prefix, title, md = ids(nn)
    en = ", ".join(R.COMBOS[combo])
    rel = md.relative_to(PROJECT)
    nxt = f"eval{nn + 1:02d}" if nn < 9 else "none - this is the last eval"
    return f"""# Eval {nn:02d}/09 - {m['id']} (medium effort) - camera combo {combo}

| | |
|---|---|
| Model | `openrouter/{m['id']}#medium` |
| Camera combo | {combo} - enabled: {en} |
| opencode session title | `{title}` |
| Model work dir / recording task | `{prefix}-<YYYYMMDD-HHMMSS>` |
| Next eval | {nxt} |

## Operator steps (run from a terminal)

**1. Reset the scene.** Put the yellow screwdriver at its start position (same spot every eval).

**2. Prepare.** Cleans up leftovers, moves the arm to the saved home pose, checks every joint responds,
takes "before" snapshots, notes the OpenRouter balance, and starts the background watcher that records
tokens / cost / metadata when the run ends:

```bash
cd /Users/dylanler/github/nex-arm-3-cam-eval && python3 eval-harness/eval_hooks.py start {nn}
```
Wait for `READY`. If it says `JOINT CHECK FAILED` or `HOME FAILED`, fix the arm and run it again.

**3. Run the eval (the prompt is sent once; the model runs end to end):**

```bash
cd /Users/dylanler/github/nex-arm-3-cam-eval && ~/.opencode/bin/opencode run --auto --title {title} --model "openrouter/{m['id']}#medium" "$(sed -n '/^<!-- PROMPT START -->$/,/^<!-- PROMPT END -->$/{{//!p;}}' {rel})"
```

**4. When it ends** the watcher automatically (no action needed):
- stops any recorder / app server / robot-control process the model left running
- takes "after" snapshots from all 3 cameras, then moves the arm back to home
- exports the opencode session and records **input / output / reasoning / cache tokens, LLM call count,
  cost** (opencode, recomputed from the provider list price, and the real OpenRouter billed delta)
- writes `{prefix}-..._eval_metadata.json` into the recording clip folder in `eval-recording/`
- rings a notification so you can reset the screwdriver

Useful commands while it runs:
```bash
python3 eval-harness/eval_hooks.py status {nn}   # live LLM calls + cost
python3 eval-harness/eval_hooks.py cancel {nn}   # stop now, counted as FAIL
python3 eval-harness/eval_hooks.py finish {nn}   # only if the watcher died: do step 4 by hand
```
Over 200 LLM calls (or 120 min) the watcher stops the recording and the session -> FAIL.

**5. Verify the outcome.** Look at the screwdriver, then record it:
```bash
python3 eval-harness/eval_hooks.py verdict {nn} success   # or: fail
```

## Prompt sent to the model (everything between the markers, verbatim)

<!-- PROMPT START -->
{prompt_text(nn)}
<!-- PROMPT END -->
"""


def gen():
    PROMPTS.mkdir(exist_ok=True)
    rows = []
    for nn in EVALS:
        mk, combo, m, prefix, title, md = ids(nn)
        md.write_text(md_text(nn))
        rows.append(f"| {nn:02d} | `{m['id']}` | {combo} | {', '.join(R.COMBOS[combo])} | [{md.name}]({md.name}) |")
    (PROMPTS / "00_README.md").write_text("""# NexArm camera-combo eval - manual protocol

Task: *Place the yellow screwdriver in the bowl.* 3 models x 3 camera combos = 9 evals, medium effort,
opencode CLI (`--auto`) via OpenRouter, 200 LLM-call cap. Order: all combos for a model before the next model.

| Eval | Model | Combo | Enabled cameras | File |
|---|---|---|---|---|
""" + "\n".join(rows) + """

Each eval file has the same 5 steps: reset screwdriver -> `eval_hooks.py start NN` -> `opencode run ...`
(prompt sent once) -> watcher records tokens/cost/metadata + homes the arm + rings -> `eval_hooks.py verdict NN`.

Results table at any time: `python3 eval-harness/eval_hooks.py summary`

Consistency controls (applied identically to every eval by `start` / the watcher):
- arm restored to `eval-harness/home_pose.json` (saved 2026-10-26 14:23) and every joint must respond to a small test move
- frontend server / recorder / leftover robot-control processes stopped before and after each run
- before/after snapshots of all 3 cameras saved with the metadata
- same prompt template (only work-dir name + camera lines differ), same harness version, same effort level
""")
    print(f"wrote {len(EVALS)} eval files + 00_README.md to {PROMPTS}")


# ------------------------------------------------------------------ process hygiene
def stray_pids(prefix):
    """Processes left by a model run: cwd or argv inside the model's work dir, opencode-service children,
    recorders, the frontend server on 8770."""
    me = {os.getpid(), os.getppid()}
    pids = set(R.recorder_pids())
    out = R.sh(["lsof", "-d", "cwd", "-Fpn"]).stdout.splitlines()
    pid = None
    for line in out:
        if line.startswith("p"):
            pid = int(line[1:])
        elif line.startswith("n") and pid and prefix in line:
            pids.add(pid)
    for line in R.sh(["ps", "-axo", "pid=,command="]).stdout.splitlines():
        p, _, cmd = line.strip().partition(" ")
        if p.isdigit() and prefix in cmd and "opencode run" not in cmd and "eval_hooks.py" not in cmd:
            pids.add(int(p))
    sp = R.service_pid()
    if sp:
        pids |= set(R.descendants(sp))
    pids |= {int(x) for x in R.sh("lsof -nP -t -iTCP:8770 -sTCP:LISTEN").stdout.split() if x.isdigit()}
    return sorted(pids - me)


def cleanup(nn, prefix):
    R.stop_recorders()
    killed = []
    for sig in (signal.SIGTERM, signal.SIGKILL):
        pids = stray_pids(prefix)
        if not pids:
            break
        for p in pids:
            try:
                os.kill(p, sig)
                killed.append(p)
            except Exception:
                pass
        time.sleep(3)
    R.stop_frontend()
    if killed:
        log(nn, f"stopped leftover processes {sorted(set(killed))}")
    return sorted(set(killed))


def home_with_retry(nn, prefix, tries=4):
    res, rc = R.arm("goto")
    for i in range(tries):
        if rc == 0:
            break
        log(nn, f"home failed ({str(res)[:150]}), cleanup + retry {i + 1}")
        cleanup(nn, prefix)
        time.sleep(2)
        res, rc = R.arm("goto")
    return res, rc


# ------------------------------------------------------------------ start / watch
def start(nn):
    mk, combo, m, prefix, title, md = ids(nn)
    st = load_state(nn)
    if st.get("status") == "running":
        print(f"eval{nn:02d} already has a running watcher (pid {st.get('watcher_pid')}). cancel it first.")
        sys.exit(1)
    if not md.exists():
        gen()
    log(nn, "preparing")
    left = cleanup(nn, prefix)
    home, rc = home_with_retry(nn, prefix)
    if rc != 0:
        R.notify("Robot home position failed.")
        print(f"HOME FAILED: {home}\nFix the arm and run start again.")
        sys.exit(2)
    health, hrc = R.arm("health")
    if hrc != 0:
        R.notify("Robot joint check failed.")
        print(f"JOINT CHECK FAILED: {json.dumps(health)}\nFix the servo and run start again.")
        sys.exit(3)
    d = sdir(nn)
    for f in d.glob("*"):
        if f.is_file() and f.name not in ("state.json",):
            f.unlink()
    snaps = R.snapshot(d / "scene_snapshots", "pre_run")
    st = {"eval": nn, "model_key": mk, "combo": combo, "prefix": prefix, "title": title,
          "prompt_file": str(md), "prompt_sha256": hashlib.sha256(prompt_text(nn).encode()).hexdigest(),
          "prepared_at": time.time(), "prepared_at_iso": R.iso(), "pre_home": home, "joint_health": health,
          "pre_snapshots": snaps, "processes_stopped_before_run": left,
          "openrouter_usage_before": R.openrouter_usage(),
          "eval_recording_dirs_before": sorted(p.name for p in R.EVAL_REC.iterdir() if p.is_dir()),
          "status": "running"}
    (d / "prompt_sent.md").write_text(prompt_text(nn))
    save_state(nn, st)
    w = subprocess.Popen([sys.executable, "-u", __file__, "watch", str(nn)], cwd=PROJECT,
                         stdout=open(d / "watcher.log", "a"), stderr=subprocess.STDOUT,
                         start_new_session=True, env=R.ENV)
    st["watcher_pid"] = w.pid
    save_state(nn, st)
    log(nn, f"READY - watcher pid {w.pid}")
    print(f"\nREADY. Now run step 3 from {md.relative_to(PROJECT)} (session title must be {title}).")


def find_session(title, after):
    r = R.oc_api("GET", "/api/session", {"search": title, "limit": "10"}) or {}
    c = [s for s in r.get("data", []) if s.get("title") == title and s["time"]["created"] / 1000 >= after - 5]
    return sorted(c, key=lambda s: s["time"]["created"])[-1] if c else None


def assistant_count(sid):
    e = R.oc_api("GET", f"/api/experimental/session/{sid}/export", timeout=120)
    if not e or "data" not in e:
        return None, None
    return sum(1 for m in e["data"]["messages"] if m.get("type") == "assistant"), e["data"]


def watch(nn):
    st = load_state(nn)
    t_prep = st["prepared_at"]
    log(nn, "watcher waiting for opencode session " + st["title"])
    sess = None
    while sess is None:
        if (sdir(nn) / "CANCEL").exists() and time.time() - t_prep > 1:
            st["status"] = "cancelled_before_start"
            save_state(nn, st)
            return
        sess = find_session(st["title"], t_prep)
        if sess is None:
            if time.time() - t_prep > 3 * 3600:
                log(nn, "no session after 3h - watcher exits")
                return
            time.sleep(5)
    sid = sess["id"]
    st.update(session_id=sid, session_created=sess["time"]["created"] / 1000)
    save_state(nn, st)
    log(nn, f"session {sid} found")
    t0 = st["session_created"]
    reason, quiet_since, last_upd, rec_seen = None, None, None, None
    while True:
        time.sleep(10)
        if rec_seen is None and R.recorder_pids():
            rec_seen = R.iso()
            st["recorder_first_seen_running"] = rec_seen
            save_state(nn, st)
        n, _ = assistant_count(sid)
        if n is not None:
            st["llm_calls_live"] = n
        if (sdir(nn) / "CANCEL").exists():
            reason = "fail_cancelled_by_operator"
        elif n is not None and n > LLM_CALL_BUDGET:
            reason = "fail_budget_exceeded"
        elif time.time() - t0 > WALL_TIMEOUT_S:
            reason = "fail_timeout"
        if reason:
            log(nn, f"{reason} -> stop recording + interrupt session")
            R.stop_recorders()
            R.ensure_session_stopped(sid)
            break
        info = (R.oc_api("GET", f"/api/session/{sid}") or {}).get("data") or {}
        active = ((R.oc_api("GET", "/api/session/active") or {}).get("data") or {})
        upd = (info.get("time") or {}).get("updated")
        idle = sid not in active and bool(info.get("outcome"))
        if idle and upd == last_upd:
            if quiet_since and time.time() - quiet_since >= 30:
                break
            quiet_since = quiet_since or time.time()
        else:
            quiet_since = None
        last_upd = upd
        save_state(nn, st)
    st["end_reason"] = reason
    st["session_ended_at"] = time.time()
    save_state(nn, st)
    finish(nn)


# ------------------------------------------------------------------ finish
def finish(nn):
    st = load_state(nn)
    mk, combo, m, prefix, title, md = ids(nn)
    d = sdir(nn)
    sid = st.get("session_id") or (find_session(title, st.get("prepared_at", 0)) or {}).get("id")
    if sid:
        R.ensure_session_stopped(sid, quiet_s=15, max_s=90)
    recorder_left = bool(R.recorder_pids())
    strays = cleanup(nn, prefix)
    final_pose, _ = R.arm("read")
    post = R.snapshot(d / "scene_snapshots", "post_run")
    home_after, rc = home_with_retry(nn, prefix)
    export = None
    if sid:
        e = R.oc_api("GET", f"/api/experimental/session/{sid}/export", timeout=180)
        if e and "data" in e:
            export = e["data"]
            (d / "opencode_session_export.json").write_text(json.dumps(export))
    cat = (R.oc_api("GET", "/api/model") or {}).get("data", [])
    mc = next((x for x in cat if x.get("id") == m["id"] and x.get("providerID") == "openrouter"), {})
    acct = R.accounting(export, mc) if export else {}
    disabled = [k for k in R.CAMS if k not in R.COMBOS[combo]]
    other_ids = [ids(k)[3] for k in EVALS if k != nn] + R.INVALID_RUN_IDS
    aud = R.audit(export, disabled, other_ids + list(st.get("eval_recording_dirs_before", []))) if export else {}
    time.sleep(15)
    ub, ua = st.get("openrouter_usage_before"), R.openrouter_usage()

    before = set(st.get("eval_recording_dirs_before", []))
    new = sorted(p for p in R.EVAL_REC.iterdir() if p.is_dir() and p.name not in before)
    clips = []
    for c_dir in new:
        for cj in sorted(c_dir.glob("clip*.json")):
            try:
                c = json.loads(cj.read_text())
                clips.append({"folder": c_dir.name, "clip_json": cj.name, "video": c.get("video"),
                              "raw_videos": c.get("raw_videos"), "duration_s": c.get("duration_s"),
                              "frames": c.get("frames"), "fps": c.get("fps"), "size": c.get("size"),
                              "start_wall_time": c.get("start_wall_time"), "end_wall_time": c.get("end_wall_time"),
                              "recorder_outcome_label": c.get("outcome"),
                              "cameras_in_clip": [x.get("key") for x in c.get("cameras", [])],
                              "settings_events": [ev for ev in c.get("events", []) if "settings" in ev],
                              "dropped_frames": c.get("dropped_frames"), "duplicated_frames": c.get("duplicated_frames")})
            except Exception as ex:
                clips.append({"folder": c_dir.name, "error": str(ex)})
    durs = {c["folder"]: c.get("duration_s") or 0 for c in clips if "folder" in c}
    if new:
        meta_dir = max(new, key=lambda x: durs.get(x.name, 0))
    else:
        meta_dir = R.EVAL_REC / f"{dt.datetime.now():%Y%m%d_%H%M%S}_eval{nn:02d}_{prefix}_NO_RECORDING_FOUND"
        meta_dir.mkdir(parents=True)
    run_name = meta_dir.name.split("_", 2)[-1] if new else prefix
    work_dirs = sorted(str(p) for p in PROJECT.glob(f"{prefix}-*") if p.is_dir())

    reason = st.get("end_reason")
    t0 = st.get("session_created") or st.get("prepared_at")
    t_end = st.get("session_ended_at") or time.time()
    meta = {
        "schema": "nexarm-camera-combo-eval/v2-manual",
        "eval_index": nn, "eval_total": 9, "eval_name": f"eval{nn:02d}_{prefix}",
        "task": "Place the yellow screwdriver in the bowl.",
        "experiment": "Does more camera input improve LLM-driven robot manipulation? 3 models x 3 camera combos",
        "model": {"provider_route": "openrouter", "model_id": m["id"], "opencode_model_arg": f"openrouter/{m['id']}#medium",
                  "reasoning_effort": "medium",
                  "catalog": {k: mc.get(k) for k in ("name", "family", "capabilities", "limit", "time")}},
        "camera_combo": {"combo_number": combo, "enabled": R.COMBOS[combo], "disabled": disabled,
                         "prompt_lines": camera_lines(combo).splitlines(),
                         "devices": {k: R.CAMS[k][1] for k in R.CAMS}},
        "harness": {"name": "opencode", "version": R.sh([R.OPENCODE, "--version"]).stdout.strip(),
                    "launch": "manual by operator", "session_title": title, "session_id": sid,
                    "session_directory": ((export or {}).get("info") or {}).get("location"),
                    "session_outcome": ((export or {}).get("info") or {}).get("outcome"),
                    "agent": next((x.get("agent") for x in (export or {}).get("messages", []) if x.get("type") == "assistant"), None),
                    "prompt_passed_once": True},
        "budget": {"llm_call_cap": LLM_CALL_BUDGET, "llm_calls_used": acct.get("llm_calls_main_model"),
                   "budget_exceeded": reason == "fail_budget_exceeded", "wall_cap_s": WALL_TIMEOUT_S,
                   "wall_timed_out": reason == "fail_timeout"},
        "timing": {"prepared_at": st.get("prepared_at_iso"),
                   "session_created": R.iso(dt.datetime.fromtimestamp(t0)) if t0 else None,
                   "session_ended": R.iso(dt.datetime.fromtimestamp(t_end)),
                   "session_wall_time_s": round(t_end - t0, 1) if t0 else None,
                   "recorder_first_seen_running": st.get("recorder_first_seen_running")},
        "tokens_and_cost": {**acct,
                            "openrouter_billed_usd_delta": round(ua - ub, 6) if ub is not None and ua is not None else None,
                            "openrouter_usage_before": ub, "openrouter_usage_after": ua,
                            "note": "opencode cost = provider list price x tokens per call; recomputed = same from "
                                    "catalog price table; openrouter delta = real billed on the key (only valid if "
                                    "nothing else used the key during the run)"},
        "outcome": {"status": reason or "pending_verdict",
                    "model_final_message": R.final_text(export) if export else None,
                    "recorder_outcome_labels": [c.get("recorder_outcome_label") for c in clips],
                    "human_verified_success": False if reason else None,
                    "verdict_note": None},
        "recording": {"clip_folders_created": [x.name for x in new], "clips": clips, "metadata_dir": str(meta_dir),
                      "recorder_left_running_by_model": recorder_left, "model_work_dirs": work_dirs},
        "robot": {"model": "Hiwonder NexArm (follower)", "serial_port": "/dev/cu.usbserial-110",
                  "joint_order": json.loads((HARNESS / "home_pose.json").read_text())["joint_order"],
                  "home_pose_reference": json.loads((HARNESS / "home_pose.json").read_text()),
                  "home_tolerance_raw_units": 45,
                  "pre_run_home_restore": st.get("pre_home"), "pre_run_joint_health_check": st.get("joint_health"),
                  "final_pose_at_end_of_run": final_pose, "post_run_home_restore": home_after,
                  "post_run_home_ok": rc == 0},
        "hygiene": {"processes_stopped_before_run": st.get("processes_stopped_before_run"),
                    "leftover_processes_stopped_after_run": strays},
        "scene": {"pre_run_snapshots": st.get("pre_snapshots"), "post_run_snapshots": post,
                  "snapshot_dir": f"eval{nn:02d}_eval_artifacts/scene_snapshots",
                  "object_reset": "screwdriver reset to the same start spot by the operator before each eval; bowl fixed"},
        "compliance_audit": aud,
        "prompt": {"file": str(md.relative_to(PROJECT)), "sha256": st.get("prompt_sha256"),
                   "base_prompt_md_sha256": R.sha256(PROJECT / "prompt.md")},
        "environment": {"lerobot_nexarm_git_commit": R.sh(["git", "-C", str(Path.home() / "github/lerobot-nexarm"),
                                                           "rev-parse", "HEAD"]).stdout.strip(),
                        "file_sha256": {f: R.sha256(PROJECT / f) for f in ("record.py", "start.sh", "index.html", "app.js")},
                        "ffmpeg": R.sh([R.FFMPEG, "-version"]).stdout.splitlines()[0],
                        "uv": R.sh(["uv", "--version"]).stdout.strip(), "frontend_port": 8770},
        "experiment_design": {"order": [{"eval": k, "model": R.MODELS[v[0]]["id"], "combo": v[1]} for k, v in EVALS.items()],
                              "ordering": "model-major (all combos for a model before the next model)"},
    }
    art = meta_dir / f"eval{nn:02d}_eval_artifacts"
    if art.exists():
        shutil.rmtree(art)
    shutil.copytree(d, art, ignore=shutil.ignore_patterns("state.json"))
    mp = meta_dir / f"eval{nn:02d}_{run_name}_eval_metadata.json"
    mp.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    st.update(status="done", metadata=str(mp))
    save_state(nn, st)
    t = acct.get("main_model_tokens", {})
    log(nn, f"DONE {reason or 'ended'} calls={acct.get('llm_calls_main_model')} in={t.get('total_input_incl_cache')} "
            f"out={t.get('total_output_incl_reasoning')} cost=${acct.get('main_model_cost_usd_opencode')} -> {mp}")
    R.notify(f"Eval {nn} of 9 complete. Please reset the screwdriver.")


# ------------------------------------------------------------------ misc commands
def status(nn):
    st = load_state(nn)
    sid = st.get("session_id")
    if not sid:
        print(f"eval{nn:02d}: {st.get('status', 'not started')}, no session yet")
        return
    n, e = assistant_count(sid)
    print(f"eval{nn:02d}: {st.get('status')} session={sid} llm_calls={n}/{LLM_CALL_BUDGET} "
          f"cost=${round((e or {}).get('info', {}).get('cost') or 0, 3)}")


def verdict(nn, v, note=""):
    st = load_state(nn)
    mp = Path(st["metadata"])
    meta = json.loads(mp.read_text())
    meta["outcome"]["human_verified_success"] = v == "success"
    if not meta["outcome"]["status"].startswith("fail_"):
        meta["outcome"]["status"] = v
    meta["outcome"]["verdict_note"] = note or None
    meta["outcome"]["verdict_at"] = R.iso()
    mp.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    print(f"eval{nn:02d} -> {meta['outcome']['status']}")


def summary():
    print(f"{'eval':5} {'model':28} {'combo':5} {'status':28} {'calls':>5} {'in_tok':>10} {'out_tok':>8} {'cost$':>7} {'min':>5}")
    for nn in EVALS:
        st = load_state(nn)
        _, combo, m, *_ = ids(nn)
        if st.get("metadata") and Path(st["metadata"]).exists():
            mt = json.loads(Path(st["metadata"]).read_text())
            t = mt["tokens_and_cost"]
            mt_tok = t.get("main_model_tokens", {})
            print(f"{nn:02d}    {m['id']:28} {combo:<5} {mt['outcome']['status']:28} {t.get('llm_calls_main_model') or 0:>5} "
                  f"{mt_tok.get('total_input_incl_cache') or 0:>10} {mt_tok.get('total_output_incl_reasoning') or 0:>8} "
                  f"{t.get('main_model_cost_usd_opencode') or 0:>7.2f} {(mt['timing']['session_wall_time_s'] or 0) / 60:>5.1f}")
        else:
            print(f"{nn:02d}    {m['id']:28} {combo:<5} {st.get('status', 'not started'):28}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__)
    elif a[0] == "gen":
        gen()
    elif a[0] == "prompt":
        print(prompt_text(int(a[1])))
    elif a[0] == "start":
        start(int(a[1]))
    elif a[0] == "watch":
        watch(int(a[1]))
    elif a[0] == "finish":
        finish(int(a[1]))
    elif a[0] == "status":
        status(int(a[1]))
    elif a[0] == "cancel":
        (sdir(int(a[1])) / "CANCEL").write_text(R.iso())
        print("cancel requested - the watcher will stop the run within ~10 s")
    elif a[0] == "verdict":
        verdict(int(a[1]), a[2], " ".join(a[3:]))
    elif a[0] == "summary":
        summary()
    else:
        print(__doc__)
