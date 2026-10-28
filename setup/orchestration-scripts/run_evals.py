#!/usr/bin/env python3
"""Orchestrator for the NexArm camera-combo eval (3 models x 3 camera combos = 9 runs).

Per run:
  1. clean slate: stop leftover recorder / frontend server (port 8770), close frontend Chrome tabs
  2. restore + verify arm home pose (eval-harness/home_pose.json)
  3. pre-run scene snapshots (all 3 cameras, orchestrator-only, for ground truth)
  4. build prompt from prompt_template.md for the camera combo, launch
     `opencode run --auto --model openrouter/<model>#medium`
  5. watchdog: count LLM calls (assistant messages); > 200 -> interrupt + stop recording -> FAIL
  6. post-run: stop leftover recorder, final scene snapshots + arm pose, export session,
     token / cost accounting (opencode + recomputed + OpenRouter billed delta),
     compliance audit, metadata json written next to the recording clip
  7. restore arm home, ring notification, wait for operator to reset the screwdriver

Usage: python3 run_evals.py [--start N] [--only N] [--dry]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HARNESS = Path(__file__).resolve().parent
PROJECT = HARNESS.parent
EVAL_REC = PROJECT / "eval-recording"
RUNS_DIR = HARNESS / "runs"
OPENCODE = str(Path.home() / ".opencode/bin/opencode")
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
ENV = dict(os.environ, PATH=f"{Path.home()}/.opencode/bin:/opt/homebrew/bin:" + os.environ.get("PATH", ""))

LLM_CALL_BUDGET = 200
WALL_TIMEOUT_S = 120 * 60
EFFORT = "medium"

MODELS = {
    "gemini": {"id": "google/gemini-4-argon", "slug": "gemini-4-argon-medium"},
    "opus": {"id": "anthropic/claude-opus-5.5", "slug": "claude-opus-5-5-medium"},
    "gpt": {"id": "openai/gpt-6.1-sol", "slug": "gpt-6-1-sol-medium"},
}
CAMS = {  # key -> (prompt label, avfoundation device name)
    "logitech": ("Logitech camera(top down view)", "C922 Pro Stream Webcam"),
    "realsense": ("Intel Realsense camera(lower left hand corner)", "Intel(R) RealSense(TM) Depth Camera 415  RGB"),
    "wrist": ("Robot arm wrist camera", "icspring camera"),
}
COMBOS = {
    1: ["logitech", "realsense", "wrist"],
    2: ["logitech", "wrist"],
    3: ["wrist"],
}
# Counterbalanced order: each model once per combo; every block of 3 runs has each model & combo once.
ORDER = [("opus", 1), ("opus", 2), ("opus", 3),
         ("gemini", 1), ("gemini", 2), ("gemini", 3),
         ("gpt", 1), ("gpt", 2), ("gpt", 3)]
# eval 4 (gemini combo 1) already ran under the original order and was cancelled -> counted as FAIL
ALREADY_DONE = {}
# invalid runs from the shoulder-servo fault (moved to eval-harness/invalid_runs_shoulder_fault/)
INVALID_RUN_IDS = ["gemini-4-argon-medium-opencode-cam-combo-1-20261026-121915",
                   "claude-opus-5-5-medium-opencode-cam-combo-1-20261026-125545"]
CANCEL_FILE = Path(__file__).resolve().parent / "CANCEL_CURRENT"
# Paths a model should NOT touch (prompt says: do not refer to other files/dirs on this computer)
FORBIDDEN_PATHS = ["gemini-4-argon-medium/", "gpt-sol-6-1-medium", "opus-5-5-adal-eval", "eval-harness",
                   "prompt-orchestrator.md", "invalid_runs_shoulder_fault"]


def now():
    return dt.datetime.now()


def iso(t=None):
    return (t or now()).isoformat(timespec="milliseconds")


def log(msg):
    line = f"[{now():%H:%M:%S}] {msg}"
    print(line, flush=True)
    with open(HARNESS / "orchestrator.log", "a") as f:
        f.write(line + "\n")


def sh(cmd, **kw):
    return subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, env=ENV, **kw)


def sha256(p: Path):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def oc_api(method, path, params=None, timeout=180):
    """Direct HTTP to the opencode background service (the `opencode api` CLI truncates output at 320KB)."""
    try:
        base = sh([OPENCODE, "service", "status"]).stdout.strip().splitlines()[-1].strip()
        pw = json.loads((Path.home() / ".config/opencode/service.json").read_text())["password"]
        q = "&".join(f"{k}={v}" for k, v in (params or {}).items())
        url = f"{base}{path}" + (f"?{q}" if q else "")
        r = subprocess.run(["curl", "-s", "--max-time", str(timeout), "-X", method, "-u", f"opencode:{pw}", url],
                           capture_output=True, text=True, env=ENV, timeout=timeout + 10)
        return json.loads(r.stdout)
    except Exception as e:
        log(f"oc_api {method} {path} failed: {e}")
        return None


def count_llm_calls(events_file: Path):
    """One step_start event == one LLM call by the main model."""
    try:
        return events_file.read_text(errors="ignore").count('"type":"step_start"')
    except Exception:
        return 0


def ensure_session_stopped(session_id, quiet_s=30, max_s=180):
    """Interrupt repeatedly until the session's cost/updated time stops changing for quiet_s."""
    if not session_id:
        return None
    t_end, last, stable_since = time.time() + max_s, None, time.time()
    while time.time() < t_end:
        oc_api("POST", f"/api/session/{session_id}/interrupt")
        info = (oc_api("GET", f"/api/session/{session_id}") or {}).get("data") or {}
        cur = (info.get("cost"), (info.get("time") or {}).get("updated"))
        if cur != last:
            last, stable_since = cur, time.time()
        elif time.time() - stable_since >= quiet_s:
            return info.get("outcome")
        time.sleep(5)
    return "unknown"


def pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def openrouter_usage():
    try:
        key = json.loads((Path.home() / ".config/opencode/opencode.json").read_text())["provider"]["openrouter"]["options"]["apiKey"]
        r = subprocess.run(["curl", "-s", "--max-time", "20", "https://openrouter.ai/api/v1/key", "-H",
                            f"Authorization: Bearer {key}"], capture_output=True, text=True)
        return json.loads(r.stdout)["data"]["usage"]
    except Exception as e:
        log(f"openrouter usage error: {e}")
        return None


# ---------------------------------------------------------------- environment hygiene
def recorder_pids():
    """PIDs of real record.py processes (python/uv running the script) — never the opencode process,
    whose argv contains the prompt text that mentions record.py."""
    r = sh(["ps", "-axo", "pid=,command="])
    out = []
    for line in r.stdout.splitlines():
        pid, _, cmd = line.strip().partition(" ")
        if not pid.isdigit() or int(pid) == os.getpid() or len(cmd) > 2000:
            continue
        toks = cmd.split()
        exe = os.path.basename(toks[0]) if toks else ""
        if "opencode" in exe or exe in ("zsh", "bash", "sh", "pgrep", "ps"):
            continue
        if any(t.endswith("record.py") for t in toks[:4]) and (
                "python" in exe.lower() or exe in ("uv", "record.py") or toks[0].endswith("record.py")):
            out.append(int(pid))
    return out


def stop_recorders(timeout=40):
    pids = recorder_pids()
    if not pids:
        return []
    log(f"stopping recorder pids {pids} (SIGINT, lets record.py save)")
    for p in pids:
        try:
            os.kill(p, signal.SIGINT)
        except ProcessLookupError:
            pass
    end = time.time() + timeout
    while time.time() < end and recorder_pids():
        time.sleep(1)
    for p in recorder_pids():
        log(f"recorder {p} still alive -> SIGTERM")
        try:
            os.kill(p, signal.SIGTERM)
        except ProcessLookupError:
            pass
    time.sleep(2)
    return pids


def service_pid():
    try:
        base = sh([OPENCODE, "service", "status"]).stdout.strip().splitlines()[-1].strip()
        port = base.rsplit(":", 1)[1]
        return int(sh(f"lsof -nP -t -iTCP:{port} -sTCP:LISTEN").stdout.split()[0])
    except Exception:
        return None


def descendants(root):
    kids = {}
    for line in sh(["ps", "-axo", "pid=,ppid="]).stdout.splitlines():
        a = line.split()
        if len(a) == 2:
            kids.setdefault(int(a[1]), []).append(int(a[0]))
    out, stack = [], list(kids.get(root, []))
    while stack:
        p = stack.pop()
        out.append(p)
        stack += kids.get(p, [])
    return out


def port_free():
    try:
        import fcntl  # noqa
        fd = os.open("/dev/cu.usbserial-110", os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
        return True
    except OSError:
        return False


def kill_strays_all(run_id):
    """Kill every process the model's session left behind: all descendants of the opencode background
    service (model tool commands run there, not under the CLI) + anything referencing the run."""
    killed = []
    sp = service_pid()
    pids = set(descendants(sp)) if sp else set()
    pids |= set(kill_strays(run_id, dry=True))
    pids.discard(os.getpid())
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in list(pids):
            try:
                os.kill(pid, sig)
                killed.append(pid)
            except ProcessLookupError:
                pids.discard(pid)
            except Exception:
                pass
        time.sleep(3)
        pids = {p for p in pids if pid_alive(p)}
        if not pids:
            break
    if killed:
        log(f"killed stray model processes {sorted(set(killed))}")
    return sorted(set(killed))


def kill_strays(run_id, dry=False):
    """Model tool processes run inside the opencode background service, not the CLI process.
    Stop anything still holding the arm's serial port or referencing this run."""
    killed = []
    r = sh(["lsof", "-t", "/dev/cu.usbserial-110"])
    pids = {int(x) for x in r.stdout.split() if x.isdigit()}
    for line in sh(["ps", "-axo", "pid=,command="]).stdout.splitlines():
        pid, _, cmd = line.strip().partition(" ")
        if pid.isdigit() and run_id in cmd and "opencode run" not in cmd and int(pid) != os.getpid():
            pids.add(int(pid))
    if dry:
        return list(pids)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
            killed.append(pid)
        except Exception:
            pass
    if killed:
        log(f"killed stray model processes {killed}")
        time.sleep(2)
    return killed


def stop_frontend():
    r = sh("lsof -nP -t -iTCP:8770 -sTCP:LISTEN")
    for p in r.stdout.split():
        try:
            os.kill(int(p), signal.SIGTERM)
        except Exception:
            pass
    sh("""osascript -e 'if application "Google Chrome" is running then
tell application "Google Chrome"
repeat with w in windows
close (every tab of w whose URL contains "localhost:8770")
end repeat
end tell
end if'""")
    time.sleep(1)


def snapshot(out_dir: Path, tag: str):
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    for key, (_, dev) in CAMS.items():
        f = out_dir / f"{tag}_{key}.jpg"
        sh([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "avfoundation", "-pixel_format", "bgr0",
            "-framerate", "30", "-video_size", "640x480", "-i", f"{dev}:none",
            "-vf", r"select=gte(n\,20)", "-frames:v", "1", str(f)], timeout=30)
        files[key] = f.name if f.exists() else None
    return files


def arm(cmd):
    r = sh([str(HARNESS / "arm_home.py"), cmd], cwd=HARNESS, timeout=120)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1]), r.returncode
    except Exception:
        return {"error": (r.stdout + r.stderr)[-500:]}, r.returncode


def notify(msg):
    sh(["afplay", "/System/Library/Sounds/Glass.aiff"])
    sh(["afplay", "/System/Library/Sounds/Hero.aiff"])
    sh(["say", msg])
    sh(["osascript", "-e", f'display notification "{msg}" with title "NexArm eval" sound name "Glass"'])


def wait_operator(msg):
    """Blocking dialog; returns True to continue, False to abort."""
    while True:
        r = sh(["osascript", "-e", f'with timeout of 86400 seconds\ndisplay dialog "{msg}" '
                f'buttons {{"Abort", "Continue"}} default button "Continue" with title "NexArm eval"\nend timeout'])
        if "Continue" in r.stdout:
            return True
        if "Abort" in r.stdout or "-128" in r.stderr:
            return False
        log(f"dialog error, re-showing: {r.stderr.strip()[:200]}")
        time.sleep(2)


# ---------------------------------------------------------------- accounting
def accounting(export: dict, model_info: dict):
    info = export["info"]
    msgs = export["messages"]
    tiers = model_info.get("cost") or []
    base = next((t for t in tiers if "tier" not in t), {})
    tier2 = next((t for t in tiers if "tier" in t), None)
    tot = {"input": 0, "output": 0, "reasoning": 0, "cache_read": 0, "cache_write": 0}
    oc_cost = recomputed = 0.0
    calls = 0
    finishes = {}
    for m in msgs:
        if m.get("type") != "assistant":
            continue
        calls += 1
        t = m.get("tokens") or {}
        c = t.get("cache") or {}
        i, o, r, cr, cw = t.get("input", 0), t.get("output", 0), t.get("reasoning", 0), c.get("read", 0), c.get("write", 0)
        for k, v in zip(tot, (i, o, r, cr, cw)):
            tot[k] += v
        oc_cost += m.get("cost") or 0
        p = tier2 if (tier2 and i + cr + cw > tier2["tier"]["size"]) else base
        recomputed += (i * p.get("input", 0) + (o + r) * p.get("output", 0) + cr * p.get("cache", {}).get("read", 0)
                       + cw * p.get("cache", {}).get("write", 0)) / 1e6
        finishes[m.get("finish")] = finishes.get(m.get("finish"), 0) + 1
    st = info.get("tokens") or {}
    sc = st.get("cache") or {}
    return {
        "llm_calls_main_model": calls,
        "finish_reasons": finishes,
        "main_model_tokens": {**tot,
                              "total_input_incl_cache": tot["input"] + tot["cache_read"] + tot["cache_write"],
                              "total_output_incl_reasoning": tot["output"] + tot["reasoning"]},
        "main_model_cost_usd_opencode": round(oc_cost, 6),
        "main_model_cost_usd_recomputed_from_list_price": round(recomputed, 6),
        "session_total_tokens_opencode": {"input": st.get("input"), "output": st.get("output"),
                                          "reasoning": st.get("reasoning"), "cache_read": sc.get("read"),
                                          "cache_write": sc.get("write")},
        "session_total_cost_usd_opencode": round(info.get("cost") or 0, 6),
        "auxiliary_cost_usd_opencode_session_title_etc": round((info.get("cost") or 0) - oc_cost, 6),
        "pricing_usd_per_1M_tokens": tiers,
        "pricing_source": "opencode model catalog for openrouter (pass-through of provider list price)",
    }


def audit(export: dict, disabled: list[str], other_run_ids: list[str]):
    """Scan the model's tool-call INPUTS for use of disabled cameras / forbidden paths."""
    tool_counts, hits = {}, {}
    inputs = []
    for m in export["messages"]:
        if m.get("type") != "assistant":
            continue
        for c in m.get("content") or []:
            if c.get("type") == "tool":
                tool_counts[c.get("name")] = tool_counts.get(c.get("name"), 0) + 1
                inputs.append(json.dumps((c.get("state") or {}).get("input"), ensure_ascii=False))
    blob = "\n".join(inputs)
    pats = {}
    for k in disabled:
        pats[f"disabled_cam:{k}"] = {"logitech": "C922", "realsense": "RealSense", "wrist": "icspring"}[k]
    for p in FORBIDDEN_PATHS + other_run_ids:
        pats[f"forbidden_path:{p}"] = p
    for name, needle in pats.items():
        n = blob.count(needle)
        if n:
            hits[name] = n
    return {"tool_call_counts": tool_counts, "total_tool_calls": sum(tool_counts.values()),
            "pattern_hits_in_tool_inputs": hits,
            "note": "Hits for disabled cameras may be legitimate (e.g. passing --no-<cam> / hiding a camera); review."}


def final_text(export):
    for m in reversed(export["messages"]):
        if m.get("type") == "assistant":
            t = "\n".join(c.get("text", "") for c in m.get("content") or [] if c.get("type") == "text").strip()
            if t:
                return t[-4000:]
    return None


# ---------------------------------------------------------------- one run
def run_one(idx, model_key, combo, models_catalog, all_run_ids, dry=False, adopt=None):
    """adopt = {"run_id", "pid", "usage_before"}: attach to an already-running opencode process
    (used when the orchestrator itself had to be restarted mid-eval)."""
    m = MODELS[model_key]
    enabled = COMBOS[combo]
    disabled = [k for k in CAMS if k not in enabled]
    model_arg = f"openrouter/{m['id']}#{EFFORT}"
    cam_lines = "\n".join(f"- {CAMS[k][0]} {'ENABLED' if k in enabled else 'DISABLED'}"
                          for k in ("logitech", "realsense", "wrist"))
    notes = []

    if adopt:
        run_id = adopt["run_id"]
        start = dt.datetime.strptime(run_id[-15:], "%Y%m%d-%H%M%S")
        rdir = RUNS_DIR / f"eval{idx:02d}_{run_id}"
        log(f"===== ADOPT EVAL {idx}/9  {run_id} pid={adopt['pid']}")
        left = []
        home_res = {"note": "pre-run home restore done by first orchestrator instance (exit 0, see orchestrator.log)",
                    "home": json.loads((HARNESS / "home_pose.json").read_text())["positions"]}
        pre_snaps = {k: f"pre_run_{k}.jpg" for k in CAMS}
        prompt = (rdir / "prompt_sent.md").read_text()
        rec_before = {p.name for p in EVAL_REC.iterdir() if p.is_dir() and run_id not in p.name}
        usage_before = adopt.get("usage_before")
        ev_path = rdir / "opencode_events.jsonl"
        try:
            t0 = json.loads(ev_path.read_text().splitlines()[0])["timestamp"] / 1000 - 10
        except Exception:
            t0 = start.timestamp()
        pid = adopt["pid"]
        alive = lambda: pid_alive(pid)  # noqa: E731
        proc = None
        notes.append("orchestrator restarted mid-run to fix watchdog/export (opencode `api` CLI truncates output); "
                     "opencode process itself was not interrupted")
    else:
        start = now()
        run_id = f"{m['slug']}-opencode-cam-combo-{combo}-{start:%Y%m%d-%H%M%S}"
        rdir = RUNS_DIR / f"eval{idx:02d}_{run_id}"
        rdir.mkdir(parents=True, exist_ok=True)
        log(f"===== EVAL {idx}/9  {run_id}")
        # 1. clean slate
        left = stop_recorders()
        stop_frontend()
        # 2. home pose
        home_res, rc = arm("goto")
        if rc != 0:
            log(f"HOME FAILED: {home_res}")
            notify("Robot home position failed. Please check the arm.")
            if not wait_operator("Arm did not reach home within tolerance. Fix it, then Continue (or Abort)."):
                sys.exit(2)
            home_res, rc = arm("goto")
        # 2b. joint health: every servo must respond to a small command (catches frozen/disconnected servos)
        health, hrc = arm("health")
        while hrc != 0:
            log(f"JOINT HEALTH FAILED: {health}")
            notify("Robot joint health check failed. Please check the servos.")
            if not wait_operator("Joint health check FAILED (a servo did not respond). Fix it, then Continue (or Abort)."):
                sys.exit(2)
            health, hrc = arm("health")
        home_res = {"goto": home_res, "joint_health_check": health}
        # 3. pre snapshots
        pre_snaps = snapshot(rdir / "scene_snapshots", "pre_run")
        # 4. prompt
        prompt = (HARNESS / "prompt_template.md").read_text().replace("{RUN_ID}", run_id).replace("{CAMERA_SETTINGS}", cam_lines)
        (rdir / "prompt_sent.md").write_text(prompt)
        rec_before = {p.name for p in EVAL_REC.iterdir() if p.is_dir()}
        usage_before = openrouter_usage()
        cmd = [OPENCODE, "run", "--auto", "--format", "json", "--title", run_id, "--model", model_arg, prompt]
        log(f"launch: opencode run --auto --format json --title {run_id} --model {model_arg} <prompt {len(prompt)} chars>")
        if dry:
            return None
        t0 = time.time()
        ev_path = rdir / "opencode_events.jsonl"
        ev_f = open(ev_path, "w")
        err_f = open(rdir / "opencode_stderr.log", "w")
        proc = subprocess.Popen(cmd, cwd=PROJECT, stdout=ev_f, stderr=err_f, env=ENV, start_new_session=True)
        ev_f.close()
        err_f.close()
        pid = proc.pid
        alive = lambda: proc.poll() is None  # noqa: E731

    session_id, calls, budget_exceeded, timed_out, first_recorder_seen = None, 0, False, False, None
    cancelled = False
    while alive():
        time.sleep(5)
        if not session_id:
            try:
                session_id = json.loads(ev_path.read_text().splitlines()[0])["sessionID"]
                log(f"session {session_id}")
            except Exception:
                pass
        if first_recorder_seen is None and recorder_pids():
            first_recorder_seen = iso()
        if CANCEL_FILE.exists():
            cancelled = True
            CANCEL_FILE.unlink()
            log("CANCELLED BY OPERATOR -> stop recording + interrupt")
            stop_recorders()
            if session_id:
                oc_api("POST", f"/api/session/{session_id}/interrupt")
            break
        n = count_llm_calls(ev_path)
        if n // 10 != calls // 10:
            log(f"llm calls: {n}")
        calls = n
        if calls > LLM_CALL_BUDGET:
            budget_exceeded = True
            log(f"BUDGET EXCEEDED ({calls} > {LLM_CALL_BUDGET}) -> stop recording + interrupt")
            stop_recorders()
            if session_id:
                oc_api("POST", f"/api/session/{session_id}/interrupt")
            break
        if time.time() - t0 > WALL_TIMEOUT_S:
            timed_out = True
            log("WALL TIMEOUT -> stop recording + interrupt")
            stop_recorders()
            if session_id:
                oc_api("POST", f"/api/session/{session_id}/interrupt")
            break
    if alive():
        time.sleep(5)
        for sig_target in (lambda: os.killpg(pid, signal.SIGTERM), lambda: os.kill(pid, signal.SIGTERM)):
            try:
                sig_target()
            except Exception:
                pass
        for _ in range(30):
            if not alive():
                break
            time.sleep(1)
    end = now()
    rc_oc = proc.returncode if proc else None
    log(f"opencode exited rc={rc_oc} after {time.time() - t0:.0f}s, llm calls={count_llm_calls(ev_path)}")

    # 6. post-run
    session_final_state = ensure_session_stopped(session_id) if (budget_exceeded or timed_out or cancelled) else (
        ((oc_api("GET", f"/api/session/{session_id}") or {}).get("data") or {}).get("outcome") if session_id else None)
    recorder_left_running = bool(recorder_pids())
    stop_recorders()
    strays = kill_strays_all(run_id)
    stop_recorders()
    stop_frontend()
    final_pose, _ = arm("read")
    post_snaps = snapshot(rdir / "scene_snapshots", "post_run")

    export = None
    if session_id:
        e = oc_api("GET", f"/api/experimental/session/{session_id}/export", timeout=180)
        if e and "data" in e:
            export = e["data"]
            (rdir / "opencode_session_export.json").write_text(json.dumps(export))
    model_cat = next((x for x in models_catalog if x.get("id") == m["id"] and x.get("providerID") == "openrouter"), {})
    acct = accounting(export, model_cat) if export else {}
    aud = audit(export, disabled, [x for x in all_run_ids if x != run_id] + sorted(rec_before)) if export else {}
    time.sleep(20)
    usage_after = openrouter_usage()

    # locate recording clip folder(s)
    new_recs = sorted(p for p in EVAL_REC.iterdir() if p.is_dir() and p.name not in rec_before)
    stray = [str(p) for p in PROJECT.rglob("clip*.mp4")
             if p.stat().st_mtime > t0 and EVAL_REC not in p.parents]
    clips = []
    for d in new_recs:
        for cj in sorted(d.glob("clip*.json")):
            if cj.name.endswith("_frames.json"):
                continue
            try:
                c = json.loads(cj.read_text())
                hidden_start = (c.get("events") or [{}])[0].get("settings", {}).get("hidden")
                clips.append({"folder": d.name, "clip_json": cj.name, "video": c.get("video"),
                              "raw_videos": c.get("raw_videos"), "duration_s": c.get("duration_s"),
                              "frames": c.get("frames"), "fps": c.get("fps"), "size": c.get("size"),
                              "start_wall_time": c.get("start_wall_time"), "end_wall_time": c.get("end_wall_time"),
                              "recorder_outcome_label": c.get("outcome"),
                              "hidden_cameras_at_start": hidden_start,
                              "hidden_events": [ev for ev in c.get("events", []) if "settings" in ev],
                              "dropped_frames": c.get("dropped_frames"),
                              "duplicated_frames": c.get("duplicated_frames"),
                              "cameras_in_clip": [x.get("key") for x in c.get("cameras", [])]})
            except Exception as ex:
                clips.append({"folder": d.name, "error": str(ex)})
    if new_recs:
        durs = {c["folder"]: c.get("duration_s") or 0 for c in clips if "folder" in c}
        meta_dir = max(new_recs, key=lambda d: durs.get(d.name, 0))
    else:
        meta_dir = EVAL_REC / f"{start:%Y%m%d_%H%M%S}_{run_id}_NO_RECORDING_FOUND"
        meta_dir.mkdir(parents=True, exist_ok=True)

    # copy orchestrator artifacts next to the clip
    art = meta_dir / f"{run_id}_eval_artifacts"
    if art.exists():
        shutil.rmtree(art)
    shutil.copytree(rdir, art, ignore=shutil.ignore_patterns("opencode_session_export.json"))
    if (rdir / "opencode_session_export.json").exists():
        shutil.copy(rdir / "opencode_session_export.json", art / "opencode_session_export.json")

    # 7. restore home
    home_after, rc_after = arm("goto")
    tries = 0
    while rc_after != 0 and tries < 3:
        tries += 1
        log(f"post-run home failed ({str(home_after)[:200]}), killing strays + retry {tries}")
        kill_strays_all(run_id)
        time.sleep(2)
        home_after, rc_after = arm("goto")
    if rc_after != 0:
        notify("Robot could not return home. Please check the arm.")
        wait_operator("Post-run home restore FAILED. Fix the arm, then Continue.")
        home_after, rc_after = arm("goto")

    exceeded_or_timeout = budget_exceeded or timed_out or cancelled
    meta = {
        "schema": "nexarm-camera-combo-eval/v1",
        "eval_index": idx, "eval_total": len(ORDER), "run_id": run_id,
        "task": "Place the yellow screwdriver in the bowl.",
        "experiment": "Does more camera input improve LLM-driven robot manipulation? 3 models x 3 camera combos",
        "model": {"provider_route": "openrouter", "model_id": m["id"], "opencode_model_arg": model_arg,
                  "reasoning_effort": EFFORT, "catalog": {k: model_cat.get(k) for k in
                                                         ("name", "family", "capabilities", "limit", "time")}},
        "camera_combo": {"combo_number": combo, "enabled": enabled, "disabled": disabled,
                         "prompt_lines": cam_lines.splitlines(),
                         "devices": {k: CAMS[k][1] for k in CAMS}},
        "harness": {"name": "opencode", "version": sh([OPENCODE, "--version"]).stdout.strip(),
                    "command": ["opencode", "run", "--auto", "--format", "json", "--title", run_id,
                                "--model", model_arg, "<prompt_sent.md>"],
                    "cwd": str(PROJECT), "session_id": session_id, "exit_code": rc_oc, "orchestrator_notes": notes,
                    "session_final_outcome": session_final_state,
                    "agent": next((x.get("agent") for x in (export or {}).get("messages", [])
                                   if x.get("type") == "assistant"), None)},
        "budget": {"llm_call_cap": LLM_CALL_BUDGET, "llm_calls_used": acct.get("llm_calls_main_model", calls),
                   "llm_calls_step_events": count_llm_calls(ev_path),
                   "budget_exceeded": budget_exceeded, "wall_timeout_s": WALL_TIMEOUT_S, "wall_timed_out": timed_out},
        "timing": {"orchestrator_start": iso(start), "opencode_start": iso(dt.datetime.fromtimestamp(t0)),
                   "opencode_end": iso(end), "opencode_wall_time_s": round(end.timestamp() - t0, 1),
                   "recorder_first_seen_running": first_recorder_seen},
        "tokens_and_cost": {**acct,
                            "openrouter_billed_usd_delta": (round(usage_after - usage_before, 6)
                                                            if usage_before is not None and usage_after is not None else None),
                            "openrouter_usage_before": usage_before, "openrouter_usage_after": usage_after,
                            "note": "openrouter delta = real billed amount on the key during the run (incl. title-gen "
                                    "small_model calls); valid only if nothing else used the key concurrently"},
        "outcome": {
            "status": "fail_budget_exceeded" if budget_exceeded else ("fail_timeout" if timed_out else
                      ("fail_cancelled_by_operator" if cancelled else "pending_review")),
            "model_final_message": final_text(export) if export else None,
            "recorder_outcome_labels": [c.get("recorder_outcome_label") for c in clips],
            "orchestrator_verified_success": False if exceeded_or_timeout else None,
            "orchestrator_verification_note": None,
            "human_verified_success": None,
        },
        "recording": {"clip_folders_created": [d.name for d in new_recs], "clips": clips,
                      "metadata_dir": str(meta_dir), "stray_clips_outside_eval_recording": stray,
                      "recorder_left_running_by_model": recorder_left_running,
                      "stray_model_processes_killed_post_run": strays,
                      "recorders_stopped_before_run": left},
        "robot": {"model": "Hiwonder NexArm (follower)", "serial_port": "/dev/cu.usbserial-110",
                  "joint_order": ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"],
                  "home_pose_reference": json.loads((HARNESS / "home_pose.json").read_text()),
                  "pre_run_home_restore": home_res, "final_pose_at_end_of_run": final_pose,
                  "post_run_home_restore": home_after, "home_tolerance_raw_units": 45,
                  "torque_state_at_start": "enabled, holding home pose"},
        "scene": {"pre_run_snapshots": pre_snaps, "post_run_snapshots": post_snaps,
                  "snapshot_dir": f"{run_id}_eval_artifacts/scene_snapshots",
                  "object_reset": "screwdriver reset by human operator between evals; bowl fixed"},
        "compliance_audit": aud,
        "prompt": {"file": f"{run_id}_eval_artifacts/prompt_sent.md", "sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                   "template_sha256": sha256(HARNESS / "prompt_template.md"),
                   "base_prompt_md_sha256": sha256(PROJECT / "prompt.md")},
        "environment": {"host_os": f"macOS {platform.mac_ver()[0]}", "arch": platform.machine(),
                        "ffmpeg": sh([FFMPEG, "-version"]).stdout.splitlines()[0],
                        "uv": sh(["uv", "--version"]).stdout.strip(),
                        "lerobot_nexarm_git_commit": sh(["git", "-C", str(Path.home() / "github/lerobot-nexarm"),
                                                         "rev-parse", "HEAD"]).stdout.strip(),
                        "file_sha256": {f: sha256(PROJECT / f) for f in ("record.py", "start.sh", "index.html", "app.js")},
                        "frontend_port": 8770, "frontend_started_fresh_each_run": True},
        "experiment_design": {"order": [{"eval": i + 1, "model": MODELS[a]["id"], "combo": b} for i, (a, b) in enumerate(ORDER)],
                              "ordering": "model-major as requested by operator: all 3 combos for a model (1,2,3) before the next model"},
    }
    meta_path = meta_dir / f"{run_id}_eval_metadata.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    shutil.copy(meta_path, rdir / meta_path.name)
    log(f"metadata -> {meta_path}")
    log(f"calls={meta['budget']['llm_calls_used']} cost_oc=${acct.get('main_model_cost_usd_opencode')} "
        f"billed=${meta['tokens_and_cost']['openrouter_billed_usd_delta']} clips={len(clips)}")
    (rdir / "DONE").write_text(str(meta_path))
    return meta_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--only", type=int)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--no-initial-dialog", action="store_true")
    ap.add_argument("--adopt-run-id")
    ap.add_argument("--adopt-pid", type=int)
    ap.add_argument("--adopt-usage-before", type=float)
    a = ap.parse_args()
    RUNS_DIR.mkdir(exist_ok=True)
    cat = (oc_api("GET", "/api/model") or {}).get("data", [])
    idxs = [a.only] if a.only else list(range(a.start, len(ORDER) + 1))
    done_ids = list(ALREADY_DONE.values()) + INVALID_RUN_IDS
    if not a.dry and not a.no_initial_dialog:
        notify("Ready to start the robot eval. Please confirm the screwdriver start position.")
        if not wait_operator(f"Eval {idxs[0]}/9 is about to start. Confirm screwdriver is at its start position, then Continue."):
            return
    idxs = [i for i in idxs if i not in ALREADY_DONE or a.only == i]
    for i in idxs:
        mk, combo = ORDER[i - 1]
        adopt = None
        if a.adopt_run_id and i == idxs[0]:
            adopt = {"run_id": a.adopt_run_id, "pid": a.adopt_pid, "usage_before": a.adopt_usage_before}
        mp = run_one(i, mk, combo, cat, done_ids, dry=a.dry, adopt=adopt)
        if a.dry:
            continue
        done_ids.append(json.loads(Path(mp).read_text())["run_id"])
        if i == idxs[-1]:
            notify(f"Eval {i} of 9 complete. All scheduled evals are done.")
        else:
            notify(f"Eval {i} of 9 complete. Please reset the screwdriver.")
            if not wait_operator(f"Eval {i}/9 finished. Reset the screwdriver to its start position, then Continue "
                                 f"to start eval {idxs[idxs.index(i) + 1]}/9 ({MODELS[ORDER[idxs[idxs.index(i) + 1] - 1][0]]['id']}, "
                                 f"camera combo {ORDER[idxs[idxs.index(i) + 1] - 1][1]})."):
                log("operator aborted")
                return
    log("all done")


if __name__ == "__main__":
    main()
