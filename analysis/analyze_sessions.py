#!/usr/bin/env python3
"""Analyze the opencode session exports of every eval run.

For each run in runs/<run_id>/ it reads the full opencode session export (from _raw_exports/, which is
not committed because it embeds every camera image as base64) and writes:

  runs/<run_id>/session/opencode_session_export.slim.json   full transcript, base64 images replaced by a stub
  runs/<run_id>/session/timeline.md                         every LLM call: time, text, tool call, tool output
  runs/<run_id>/session/stats.json                          counts, tokens, cost at official provider list price

and the cross-run tables analysis/results.json + analysis/results.csv.

Cost is recomputed per LLM call from the token counts opencode recorded, using the model provider's own
published list price (not OpenRouter / flex / batch / discounted rates). See PRICING below for sources.

Usage: python3 analysis/analyze_sessions.py
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "_raw_exports"
RUNS = ROOT / "runs"

# USD per 1M tokens, provider's own standard list price (checked 2026-10-28).
#   Anthropic: https://platform.claude.com/docs/en/about-claude/pricing
#   Google:    https://ai.google.dev/gemini-api/docs/pricing  (rates valid through 2026-11-30)
#   OpenAI:    https://developers.openai.com/api/docs/pricing (standard tier; >272K-token prompt tier)
PRICING = {
    "anthropic/claude-opus-5.5": {"base": {"input": 4.0, "cache_read": 0.20, "cache_write": 5.0, "output": 20.0},
                                  "source": "https://platform.claude.com/docs/en/about-claude/pricing"},
    "google/gemini-4-argon": {"base": {"input": 2.0, "cache_read": 0.10, "cache_write": 0.0, "output": 10.0},
                              "source": "https://ai.google.dev/gemini-api/docs/pricing (implicit caching only; no write fee)"},
    "openai/gpt-6.1-sol": {"base": {"input": 2.0, "cache_read": 0.10, "cache_write": 2.50, "output": 10.0},
                           "long": {"input": 4.0, "cache_read": 0.20, "cache_write": 5.0, "output": 15.0},
                           "source": "https://developers.openai.com/api/docs/pricing"},
    "openai/gpt-6.1-terra": {"base": {"input": 1.0, "cache_read": 0.05, "cache_write": 1.25, "output": 5.0},
                             "long": {"input": 2.0, "cache_read": 0.10, "cache_write": 2.50, "output": 7.50},
                             "source": "https://developers.openai.com/api/docs/pricing"},
    "~openai/gpt-astra-latest": {"base": {"input": 10.0, "cache_read": 1.0, "cache_write": 12.50, "output": 50.0},
                                 "long": {"input": 20.0, "cache_read": 2.0, "cache_write": 25.0, "output": 75.0},
                                 "source": "https://developers.openai.com/api/docs/pricing (alias of openai/gpt-6-astra)"},
}
PRICING["openai/gpt-6-astra"] = PRICING["~openai/gpt-astra-latest"]  # same model; sessions may record either id
LONG_CONTEXT_THRESHOLD = 272_000  # OpenAI: prompt (input + cached) above this uses the "long" row

IMG_RE = re.compile(r"^data:image/[a-z]+;base64,")
SHELL_TOOLS = {"shell", "bash"}


def slim(o):
    """Replace embedded base64 images (and other huge blobs) by a short stub."""
    if isinstance(o, dict):
        return {k: slim(v) for k, v in o.items()}
    if isinstance(o, list):
        return [slim(v) for v in o]
    if isinstance(o, str):
        if IMG_RE.match(o):
            return f"<base64 image removed: {len(o)} chars>"
        if len(o) > 200_000:
            return o[:2000] + f"... <truncated, {len(o)} chars total>"
    return o


def ts(ms):
    return dt.datetime.fromtimestamp(ms / 1000).isoformat(timespec="seconds") if ms else None


def tool_text(state):
    out = []
    for c in state.get("content") or []:
        if c.get("type") == "text":
            out.append(c.get("text") or "")
        elif c.get("uri", "").startswith("data:image"):
            out.append("[image]")
    return "\n".join(out)


def short(s, n):
    s = (s or "").strip()
    return s if len(s) <= n else s[:n] + f" …[+{len(s) - n} chars]"


def call_cost(model, t):
    p = PRICING[model]
    c = t.get("cache") or {}
    i, o, r, cr, cw = t.get("input", 0), t.get("output", 0), t.get("reasoning", 0), c.get("read", 0), c.get("write", 0)
    row = p.get("long") if (p.get("long") and i + cr + cw > LONG_CONTEXT_THRESHOLD) else p["base"]
    return (i * row["input"] + cr * row["cache_read"] + cw * row["cache_write"] + (o + r) * row["output"]) / 1e6, row is p.get("long")


ARM_MOVE = re.compile(r"\b(move|goto|go_to|pose|joint|set_pos|write_pos|send_action|step|nudge|jog|approach|lower|lift|raise|descend)\b", re.I)
GRIP = re.compile(r"\b(grip|gripper|grasp|grab|close|open_gripper|close_gripper|release|pinch)\b", re.I)
SNAP = re.compile(r"(snap|snapshot|capture|ffmpeg .*avfoundation|grab_frame|see\.sh|look|frame)", re.I)


def analyze(run_dir: Path):
    rid = run_dir.name
    raw = json.loads((RAW / f"{rid}.json").read_text())
    info, msgs = raw["info"], raw["messages"]
    model = info["model"]["id"]
    sdir = run_dir / "session"
    sdir.mkdir(exist_ok=True)
    (sdir / "opencode_session_export.slim.json").write_text(json.dumps(slim(raw), indent=1, ensure_ascii=False))

    tok = Counter()
    cost_official = cost_opencode = 0.0
    long_calls = 0
    tools, files_written, errors, images_viewed = Counter(), [], 0, 0
    shell_cmds, recorder_starts, arm_cmds, grip_cmds, snap_cmds = 0, 0, 0, 0, 0
    lines = [f"# Timeline: {rid}", "", f"model `{model}` · variant `{info['model'].get('variant')}` · session `{info['id']}`", ""]
    t0 = next((m["time"]["created"] for m in msgs if m.get("time")), None)
    n_call = 0
    for m in msgs:
        typ = m.get("type")
        if typ == "user":
            lines += ["## Prompt (user)", "", "```", short(m.get("text"), 6000), "```", ""]
            continue
        if typ != "assistant":
            continue
        n_call += 1
        t = m.get("tokens") or {}
        c = t.get("cache") or {}
        tok.update(input=t.get("input", 0), output=t.get("output", 0), reasoning=t.get("reasoning", 0),
                   cache_read=c.get("read", 0), cache_write=c.get("write", 0))
        cc, is_long = call_cost(model, t)
        cost_official += cc
        long_calls += is_long
        cost_opencode += m.get("cost") or 0
        el = (m["time"]["created"] - t0) / 1000 if t0 else 0
        lines.append(f"### Call {n_call} · t+{int(el // 60)}m{int(el % 60):02d}s · in {t.get('input', 0) + c.get('read', 0) + c.get('write', 0):,} / out {t.get('output', 0) + t.get('reasoning', 0):,} tok · ${cc:.4f}")
        for part in m.get("content") or []:
            pt = part.get("type")
            if pt == "text" and (part.get("text") or "").strip():
                lines += ["", "**Model:** " + short(part["text"], 1500).replace("\n", "\n> ")]
            elif pt == "reasoning" and (part.get("text") or "").strip():
                lines += ["", "*Reasoning (summary):* " + short(part["text"], 800).replace("\n", " ")]
            elif pt == "tool":
                name = part.get("name")
                st = part.get("state") or {}
                inp = st.get("input") or {}
                tools[name] += 1
                out = tool_text(st)
                meta = st.get("metadata") or {}
                failed = st.get("status") == "error" or (isinstance(meta.get("exit"), int) and meta.get("exit") != 0)
                errors += failed
                images_viewed += out.count("[image]")
                if name in ("write", "edit") and inp.get("path"):
                    files_written.append(inp["path"])
                cmd = inp.get("command") or ""
                if name in SHELL_TOOLS:
                    shell_cmds += 1
                    if "record.py" in cmd and "--list" not in cmd and "-h" not in cmd.split():
                        recorder_starts += 1
                    if ARM_MOVE.search(cmd):
                        arm_cmds += 1
                    if GRIP.search(cmd):
                        grip_cmds += 1
                    if SNAP.search(cmd):
                        snap_cmds += 1
                shown = cmd if cmd else json.dumps(inp, ensure_ascii=False)
                if name in ("write", "edit"):
                    shown = f"{inp.get('path')} ({len(inp.get('content') or inp.get('newString') or '')} chars)"
                lines += ["", f"- **{name}**{' ❌' if failed else ''}: `{short(shown, 500).replace('`', chr(39))}`"]
                if out.strip():
                    lines += ["  ```", "  " + short(out, 700).replace("\n", "\n  "), "  ```"]
        lines.append("")
    final = next((p.get("text") for m in reversed(msgs) if m.get("type") == "assistant"
                  for p in (m.get("content") or []) if p.get("type") == "text" and (p.get("text") or "").strip()), None)
    (sdir / "timeline.md").write_text("\n".join(lines))
    t_first = next((m["time"]["created"] for m in msgs if m.get("time")), None)
    t_last = max((m["time"].get("completed") or m["time"]["created"] for m in msgs if m.get("time")), default=None)
    stats = {
        "run_id": rid, "model": model, "variant": info["model"].get("variant"), "session_id": info["id"],
        "session_outcome": info.get("outcome"), "start": ts(t_first), "end": ts(t_last),
        "wall_minutes": round((t_last - t_first) / 60000, 1) if t_first and t_last else None,
        "llm_calls": n_call,
        "tokens": {**dict(tok), "total_input": tok["input"] + tok["cache_read"] + tok["cache_write"],
                   "total_output": tok["output"] + tok["reasoning"]},
        "cost_usd_official_list_price": round(cost_official, 4),
        "cost_usd_opencode_reported": round(cost_opencode, 4),
        "calls_in_long_context_tier": long_calls,
        "pricing_usd_per_1m": PRICING[model],
        "tool_calls": dict(tools), "total_tool_calls": sum(tools.values()), "failed_tool_calls": errors,
        "shell_commands": shell_cmds, "recorder_starts": recorder_starts,
        "shell_cmds_mentioning_arm_motion": arm_cmds, "shell_cmds_mentioning_gripper": grip_cmds,
        "shell_cmds_mentioning_camera_capture": snap_cmds, "images_returned_to_model": images_viewed,
        "files_written_or_edited": sorted(set(files_written)),
        "final_message": final,
    }
    (sdir / "stats.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False))
    return stats


def main():
    rows = [analyze(d) for d in sorted(RUNS.iterdir()) if d.is_dir() and (RAW / f"{d.name}.json").exists()]
    (ROOT / "analysis" / "results.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    cols = ["run_id", "model", "variant", "session_outcome", "wall_minutes", "llm_calls", "total_input", "total_output",
            "cache_read", "reasoning", "cost_usd_official_list_price", "cost_usd_opencode_reported", "total_tool_calls",
            "failed_tool_calls", "recorder_starts", "images_returned_to_model"]
    with open(ROOT / "analysis" / "results.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            flat = {**r, **r["tokens"]}
            w.writerow([flat.get(c) for c in cols])
    for r in rows:
        print(f"{r['run_id'][:-16]:50s} calls={r['llm_calls']:4d} in={r['tokens']['total_input']:>10,} out={r['tokens']['total_output']:>8,} "
              f"official=${r['cost_usd_official_list_price']:.2f} opencode=${r['cost_usd_opencode_reported']:.2f} "
              f"tools={r['total_tool_calls']} fail={r['failed_tool_calls']} rec={r['recorder_starts']} imgs={r['images_returned_to_model']} min={r['wall_minutes']}")


if __name__ == "__main__":
    main()
