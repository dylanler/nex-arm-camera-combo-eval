#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["matplotlib>=3.8", "numpy>=1.24"]
# ///
"""Trade-off charts for the slides: model cost vs number of cameras vs tokens / time.

  uv run analysis/make_tradeoff_charts.py   -> docs/figures/13_*.png, 14_*.png, 15_*.png, analysis/tradeoff.json
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "docs" / "figures"
R = {r["run_id"]: r for r in json.loads((ROOT / "analysis" / "results.json").read_text())}
O = json.loads((ROOT / "analysis" / "outcomes.json").read_text())["runs"]
A = json.loads((ROOT / "analysis" / "active_time.json").read_text())

MODELS = ["anthropic/claude-opus-5.5", "google/gemini-4-argon", "~openai/gpt-astra-latest",
          "openai/gpt-6.1-sol", "openai/gpt-6.1-terra"]
LABEL = {"anthropic/claude-opus-5.5": "Claude Opus 5.5", "google/gemini-4-argon": "Gemini 4 Argon",
         "openai/gpt-6.1-sol": "GPT-6.1 Sol", "openai/gpt-6.1-terra": "GPT-6.1 Terra",
         "~openai/gpt-astra-latest": "GPT-6 Astra", "deepseek/deepseek-v4.1-flash-1017": "DeepSeek V4.1 Flash"}
COLOR = {"anthropic/claude-opus-5.5": "#D97757", "google/gemini-4-argon": "#4285F4", "openai/gpt-6.1-sol": "#10A37F",
         "openai/gpt-6.1-terra": "#7C5CFC", "~openai/gpt-astra-latest": "#E5E7EB", "deepseek/deepseek-v4.1-flash-1017": "#60A5FA"}
NCAM = {1: 3, 2: 2, 3: 1}
DEEPSEEK_C1_COST = 0.833  # opencode-reported cost of the DeepSeek combo-1 session (folder not in repo)

DARK = {"figure.facecolor": "#0b0f17", "axes.facecolor": "#0b0f17", "savefig.facecolor": "#0b0f17",
        "text.color": "#e8edf5", "axes.labelcolor": "#e8edf5", "xtick.color": "#93a0b4", "ytick.color": "#93a0b4",
        "axes.edgecolor": "#334155", "grid.color": "#1f2937", "font.size": 13,
        "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 160}
plt.rcParams.update(DARK)


def runs(m):
    return [o for o in O if o["model"] == m]


summary = {}
for m in MODELS:
    rs = [o for o in runs(m) if o["run_id"] in R]
    cost = sum(R[o["run_id"]]["cost_usd_official_list_price"] for o in rs)
    succ = sum(o["outcome"] == "success" for o in runs(m))
    toks = [R[o["run_id"]]["tokens"]["total_input"] + R[o["run_id"]]["tokens"]["total_output"] for o in rs]
    summary[m] = {"success": succ, "cells": 3, "total_cost": round(cost, 2) if rs else None,
                  "cost_per_run": round(cost / len(rs), 2) if rs else DEEPSEEK_C1_COST,
                  "cost_per_success": round(cost / succ, 2) if succ else None,
                  "mtokens_per_run": round(np.mean(toks) / 1e6, 2) if toks else None,
                  "min_cameras_that_worked": min((NCAM[o["combo"]] for o in runs(m) if o["outcome"] == "success"), default=None),
                  "active_min_per_run": round(np.mean([A[o["run_id"]] for o in rs]), 1) if rs else None}
(ROOT / "analysis" / "tradeoff.json").write_text(json.dumps(summary, indent=2))

# ------------------------------------------------ 13. cost per run vs number of cameras
fig, ax = plt.subplots(figsize=(11, 6))
for k, m in enumerate(MODELS[:5]):
    xs, ys, ok = [], [], []
    for o in runs(m):
        if o["run_id"] in R:
            xs.append(NCAM[o["combo"]] + (k - 2) * 0.06); ys.append(R[o["run_id"]]["cost_usd_official_list_price"]); ok.append(o["outcome"] == "success")
    order = np.argsort(xs)[::-1]
    ax.plot(np.array(xs)[order], np.array(ys)[order], color=COLOR[m], lw=2, alpha=.55)
    for x, y, s in zip(xs, ys, ok):
        ax.scatter(x, y, s=230, color=COLOR[m] if s else "none", edgecolor=COLOR[m], lw=2.5, zorder=3, marker="o" if s else "X")
    yoff = {"openai/gpt-6.1-terra": 1.08, "google/gemini-4-argon": 0.93}.get(m, 1.0)
    ax.text(3.2, ys[int(np.argmax(xs))] * yoff, LABEL[m], color=COLOR[m], va="center", ha="right", fontsize=12, fontweight="bold")
ax.set_yscale("log"); ax.set_yticks([0.5, 1, 2, 5, 10]); ax.set_yticklabels(["$0.50", "$1", "$2", "$5", "$10"])
ax.set_xticks([3, 2, 1]); ax.set_xticklabels(["3 cameras\ntop + side + wrist", "2 cameras\ntop + wrist", "1 camera\nwrist only"])
ax.set_xlim(4.0, 0.75); ax.set_ylim(0.5, 16); ax.grid(axis="y")
ax.set_ylabel("cost per run (provider list price)")
ax.scatter([], [], s=150, color="#e8edf5", label="success"); ax.scatter([], [], s=150, color="none", edgecolor="#e8edf5", marker="X", lw=2, label="fail")
ax.legend(frameon=False, loc="lower left")
ax.set_title("Cheaper models need more cameras; pricier models cope with fewer", fontsize=15, pad=14)
fig.tight_layout(); fig.savefig(FIG / "13_cost_vs_cameras.png"); plt.close(fig)

# ------------------------------------------------ 14. tokens vs active time
fig, ax = plt.subplots(figsize=(11, 6))
for m in MODELS[:5]:
    for o in runs(m):
        if o["run_id"] not in R:
            continue
        t = R[o["run_id"]]["tokens"]; tok = (t["total_input"] + t["total_output"]) / 1e6
        ok = o["outcome"] == "success"
        ax.scatter(tok, A[o["run_id"]], s=60 + 50 * R[o["run_id"]]["cost_usd_official_list_price"], color=COLOR[m] if ok else "none",
                   edgecolor=COLOR[m], lw=2.2, alpha=.9, marker="o" if ok else "X", zorder=3)
for m in MODELS[:5]:
    ax.scatter([], [], s=120, color=COLOR[m], label=LABEL[m])
xs = [(R[o["run_id"]]["tokens"]["total_input"] + R[o["run_id"]]["tokens"]["total_output"]) / 1e6 for o in O if o["run_id"] in R]
ys = [A[o["run_id"]] for o in O if o["run_id"] in R]
r = np.corrcoef(xs, ys)[0, 1]
ax.set_xlabel("tokens per run (millions, mostly cached input)"); ax.set_ylabel("active minutes")
ax.grid(True); ax.legend(frameon=False, fontsize=11, loc="upper left")
ax.set_title(f"More tokens usually means a longer run, but loosely (r = {r:.2f})", fontsize=15, pad=14)
ax.text(0.99, 0.03, "Time also depends on inference speed: provider, tier (standard / flex / fast)\nand reasoning effort. Bubble size = cost. ✕ = failed run.",
        transform=ax.transAxes, ha="right", va="bottom", fontsize=11, color="#93a0b4")
fig.tight_layout(); fig.savefig(FIG / "14_tokens_vs_time.png"); plt.close(fig)

# ------------------------------------------------ 15. model trade-off: cost vs success, bubble = tokens
fig, ax = plt.subplots(figsize=(11, 6))
for m in MODELS:
    s = summary[m]
    rate = 100 * s["success"] / 3
    size = 300 + 260 * (s["mtokens_per_run"] or 1.5)
    ax.scatter(s["cost_per_run"], rate, s=size, color=COLOR[m], alpha=.85 if s["mtokens_per_run"] else .35,
               edgecolor="white", lw=1.5, zorder=3)
    note = f"{LABEL[m]}\n${s['cost_per_run']:.2f}/run" + (f" · {s['mtokens_per_run']:.1f}M tok" if s["mtokens_per_run"] else " · combo 1 only")
    # (x multiplier, y offset, horizontal alignment) per label
    pos = {"google/gemini-4-argon": (0.62, 0, "right"), "anthropic/claude-opus-5.5": (1.0, -17, "center"),
           "~openai/gpt-astra-latest": (1.0, -17, "center"), "openai/gpt-6.1-sol": (0.8, 0, "right"),
           "openai/gpt-6.1-terra": (1.35, 0, "left")}[m]
    ax.text(s["cost_per_run"] * pos[0], rate + pos[1], note, fontsize=11.5, va="center", ha=pos[2],
            color=COLOR[m] if m != "~openai/gpt-astra-latest" else "#e8edf5")
ax.set_xscale("log"); ax.set_xticks([0.5, 1, 2, 5, 10]); ax.set_xticklabels(["$0.50", "$1", "$2", "$5", "$10"])
ax.set_xlim(0.3, 20); ax.set_ylim(-14, 112); ax.set_yticks([0, 33, 67, 100]); ax.set_yticklabels(["0/3", "1/3", "2/3", "3/3"])
ax.set_xlabel("average cost per run (provider list price, log scale)"); ax.set_ylabel("combos solved")
ax.grid(True)
ax.set_title("Reliability vs cost: Gemini and Opus solve all 3 combos at about $1.50–2 per run", fontsize=15, pad=14)
fig.tight_layout(); fig.savefig(FIG / "15_model_tradeoff.png"); plt.close(fig)
print(json.dumps(summary, indent=1))
