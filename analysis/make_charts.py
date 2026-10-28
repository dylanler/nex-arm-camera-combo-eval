#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["matplotlib>=3.8", "numpy>=1.24", "pillow>=10"]
# ///
"""Build the tables + charts for the README from analysis/results.json and analysis/outcomes.json.

  uv run analysis/make_charts.py      -> docs/figures/*.png, analysis/summary_table.md, analysis/active_time.json
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "docs" / "figures"
FIG.mkdir(parents=True, exist_ok=True)
results = {r["run_id"]: r for r in json.loads((ROOT / "analysis" / "results.json").read_text())}
outcomes = json.loads((ROOT / "analysis" / "outcomes.json").read_text())["runs"]

MODELS = ["anthropic/claude-opus-5.5", "google/gemini-4-argon", "openai/gpt-6.1-sol", "openai/gpt-6.1-terra",
          "~openai/gpt-astra-latest", "deepseek/deepseek-v4.1-flash-1017"]
LABEL = {"anthropic/claude-opus-5.5": "Claude Opus 5.5", "google/gemini-4-argon": "Gemini 4 Argon",
         "openai/gpt-6.1-sol": "GPT-6.1 Sol", "openai/gpt-6.1-terra": "GPT-6.1 Terra",
         "~openai/gpt-astra-latest": "GPT Astra (latest)", "deepseek/deepseek-v4.1-flash-1017": "DeepSeek V4.1 Flash"}
COLOR = {"anthropic/claude-opus-5.5": "#D97757", "google/gemini-4-argon": "#4285F4", "openai/gpt-6.1-sol": "#10A37F",
         "openai/gpt-6.1-terra": "#7C5CFC", "~openai/gpt-astra-latest": "#111827", "deepseek/deepseek-v4.1-flash-1017": "#4D6BFE"}
SHORT = {"anthropic/claude-opus-5.5": "Opus", "google/gemini-4-argon": "Gemini", "openai/gpt-6.1-sol": "Sol",
         "openai/gpt-6.1-terra": "Terra", "~openai/gpt-astra-latest": "Astra", "deepseek/deepseek-v4.1-flash-1017": "DeepSeek"}
COMBO = {1: "Combo 1\ntop + side + wrist", 2: "Combo 2\ntop + wrist", 3: "Combo 3\nwrist only"}
plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 150})


def cell(model, combo):
    return next((o for o in outcomes if o["model"] == model and o["combo"] == combo), None)


def active_minutes(run_id, cap_s=300):
    """Sum of gaps between consecutive LLM calls, each gap capped at 5 min (removes idle time after the run)."""
    d = json.loads((ROOT / "runs" / run_id / "session" / "opencode_session_export.slim.json").read_text())
    t = sorted(m["time"]["created"] for m in d["messages"] if m.get("type") == "assistant")
    return round(sum(min((b - a) / 1000, cap_s) for a, b in zip(t, t[1:])) / 60, 1)


def per_call_cost(run_id):
    import importlib.util
    spec = importlib.util.spec_from_file_location("an", ROOT / "analysis" / "analyze_sessions.py")
    an = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(an)
    d = json.loads((ROOT / "runs" / run_id / "session" / "opencode_session_export.slim.json").read_text())
    model = d["info"]["model"]["id"]
    return [an.call_cost(model, m.get("tokens") or {})[0] for m in d["messages"] if m.get("type") == "assistant"]


rows = [o for o in outcomes if o["run_id"] in results]
active = {o["run_id"]: active_minutes(o["run_id"]) for o in rows}
(ROOT / "analysis" / "active_time.json").write_text(json.dumps(active, indent=2))

# ---------------------------------------------------------------- 1. outcome matrix
fig, ax = plt.subplots(figsize=(9, 5.2))
cmap = {"success": "#22C55E", "fail": "#EF4444", "not_run": "#E5E7EB"}
for i, m in enumerate(MODELS):
    for j, c in enumerate([1, 2, 3]):
        o = cell(m, c)
        st = o["outcome"] if o else "not_run"
        ax.add_patch(plt.Rectangle((j, len(MODELS) - 1 - i), 0.95, 0.9, color=cmap[st]))
        txt = {"success": "SUCCESS", "fail": "FAIL", "not_run": "not run"}[st]
        r = results.get(o["run_id"]) if o and o["run_id"] else None
        sub = f"\n{r['llm_calls']} calls · ${r['cost_usd_official_list_price']:.2f}" if r else ""
        ax.text(j + 0.475, len(MODELS) - 1 - i + 0.45, txt + sub, ha="center", va="center",
                color="white" if st != "not_run" else "#6B7280", fontsize=9.5, fontweight="bold")
ax.set_xlim(0, 3); ax.set_ylim(0, len(MODELS))
ax.set_xticks([0.475, 1.475, 2.475]); ax.set_xticklabels([COMBO[c] for c in (1, 2, 3)])
ax.set_yticks([len(MODELS) - 1 - i + 0.45 for i in range(len(MODELS))]); ax.set_yticklabels([LABEL[m] for m in MODELS])
ax.tick_params(length=0); [s.set_visible(False) for s in ax.spines.values()]
ax.set_title("Place the yellow screwdriver in the bowl: outcome per model × camera combo", fontsize=12, pad=12)
fig.tight_layout(); fig.savefig(FIG / "01_outcome_matrix.png"); plt.close(fig)

# ---------------------------------------------------------------- 2. success rate by combo
fig, ax = plt.subplots(figsize=(8, 4.2))
for incl, off, col, lab in ((False, -0.2, "#3B82F6", "5 models with logs (DeepSeek excluded)"), (True, 0.2, "#94A3B8", "incl. DeepSeek combo 1 (fail)")):
    rates, ns = [], []
    for c in (1, 2, 3):
        cs = [o for o in outcomes if o["combo"] == c and o["outcome"] != "not_run" and (incl or not o["model"].startswith("deepseek"))]
        rates.append(100 * sum(o["outcome"] == "success" for o in cs) / len(cs)); ns.append(len(cs))
    b = ax.bar(np.arange(3) + off, rates, 0.38, color=col, label=lab)
    for x, r, n in zip(np.arange(3) + off, rates, ns):
        ax.text(x, r + 2, f"{r:.0f}%\n(n={n})", ha="center", fontsize=9)
ax.set_xticks(range(3)); ax.set_xticklabels([COMBO[c] for c in (1, 2, 3)]); ax.set_ylim(0, 115); ax.set_ylabel("success rate (%)")
ax.set_title("Success rate by camera combination"); ax.legend(frameon=False, fontsize=9, loc="upper right")
fig.tight_layout(); fig.savefig(FIG / "02_success_rate_by_combo.png"); plt.close(fig)


# ---------------------------------------------------------------- grouped bar helper
def grouped(metric, ylabel, title, fname, fmt="{:.0f}", models=MODELS[:5]):
    fig, ax = plt.subplots(figsize=(10, 4.6))
    w = 0.16
    for k, m in enumerate(models):
        vals = []
        for c in (1, 2, 3):
            o = cell(m, c)
            vals.append(metric(o) if o and o["run_id"] in results else np.nan)
        xs = np.arange(3) + (k - (len(models) - 1) / 2) * w
        bars = ax.bar(xs, vals, w, color=COLOR[m], label=LABEL[m])
        for x, v, c in zip(xs, vals, (1, 2, 3)):
            o = cell(m, c)
            if not np.isnan(v):
                ax.text(x, v, fmt.format(v), ha="center", va="bottom", fontsize=7.5)
                if o["outcome"] == "fail":
                    ax.text(x, 0, "✗", ha="center", va="bottom", color="white", fontsize=9, fontweight="bold")
    ax.set_xticks(range(3)); ax.set_xticklabels([COMBO[c] for c in (1, 2, 3)]); ax.set_ylabel(ylabel)
    ax.set_title(title + "   (✗ = failed run)"); ax.legend(frameon=False, fontsize=8.5, ncol=3, loc="upper left")
    ax.set_ylim(0, ax.get_ylim()[1] * 1.18)
    fig.tight_layout(); fig.savefig(FIG / fname); plt.close(fig)


grouped(lambda o: results[o["run_id"]]["llm_calls"], "LLM calls", "LLM calls per run (budget = 200)", "03_llm_calls.png")
grouped(lambda o: results[o["run_id"]]["cost_usd_official_list_price"], "USD", "Cost per run at the provider's official list price",
        "04_cost_usd.png", "${:.2f}")
grouped(lambda o: active[o["run_id"]], "minutes", "Active wall time per run (idle gaps > 5 min removed)", "05_active_minutes.png", "{:.0f}")
grouped(lambda o: results[o["run_id"]]["tokens"]["total_input"] / 1e6, "million tokens", "Total input tokens per run (incl. cached)",
        "06_input_tokens.png", "{:.1f}")
grouped(lambda o: results[o["run_id"]]["tokens"]["total_output"] / 1e3, "thousand tokens", "Total output tokens per run (incl. reasoning)",
        "07_output_tokens.png", "{:.0f}")

# ---------------------------------------------------------------- 8. grasp attempts
fig, ax = plt.subplots(figsize=(11, 4.6))
labels, ok, bad, cols = [], [], [], []
for m in MODELS[:5]:
    for c in (1, 2, 3):
        o = cell(m, c)
        if not o or o["grasp_attempts"] is None:
            continue
        labels.append(f"{SHORT[m]}\nC{c}{' ✗' if o['outcome'] == 'fail' else ''}")
        bad.append(o["failed_grasps"]); ok.append(o["grasp_attempts"] - o["failed_grasps"]); cols.append(COLOR[m])
x = np.arange(len(labels))
ax.bar(x, ok, color="#22C55E", label="grasp that lifted the screwdriver")
ax.bar(x, bad, bottom=ok, color="#F97316", label="failed grasp (missed / slipped / not lifted)")
ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=9); ax.set_ylabel("gripper closures on the screwdriver")
ax.set_title("Grasp attempts per run (from transcript review)   C = camera combo, ✗ = failed run")
ax.legend(frameon=False, fontsize=9)
fig.tight_layout(); fig.savefig(FIG / "08_grasp_attempts.png"); plt.close(fig)

# ---------------------------------------------------------------- 9. cumulative cost curves
fig, axes = plt.subplots(1, 3, figsize=(14, 4.2), sharey=True)
for j, c in enumerate((1, 2, 3)):
    ax = axes[j]
    for m in MODELS[:5]:
        o = cell(m, c)
        if not o or o["run_id"] not in results:
            continue
        cc = np.cumsum(per_call_cost(o["run_id"]))
        ax.plot(range(1, len(cc) + 1), cc, color=COLOR[m], lw=2, ls="--" if o["outcome"] == "fail" else "-",
                label=f"{LABEL[m]}{' (fail)' if o['outcome'] == 'fail' else ''}")
    ax.set_title(COMBO[c].replace("\n", ": ")); ax.set_xlabel("LLM call #"); ax.axvline(200, color="#9CA3AF", lw=1, ls=":")
    ax.legend(frameon=False, fontsize=8)
axes[0].set_ylabel("cumulative cost, USD (list price)")
fig.suptitle("Cumulative cost over the run (dashed = failed run, dotted line = 200-call budget)", fontsize=12)
fig.tight_layout(); fig.savefig(FIG / "09_cumulative_cost.png"); plt.close(fig)

# ---------------------------------------------------------------- 10. tool mix
fig, ax = plt.subplots(figsize=(11, 4.6))
tools = ["shell", "read", "write", "edit", "patch", "glob", "grep", "webfetch", "websearch", "todowrite"]
others = []
bottom = np.zeros(len(rows))
lab = [f"{SHORT[o['model']]}\nC{o['combo']}" for o in rows]
palette = plt.get_cmap("tab10")
for k, t in enumerate(tools + ["other"]):
    vals = []
    for o in rows:
        tc = results[o["run_id"]]["tool_calls"]
        vals.append(sum(v for kk, v in tc.items() if kk not in tools) if t == "other" else tc.get(t, 0))
    if sum(vals) == 0:
        continue
    ax.bar(range(len(rows)), vals, bottom=bottom, label=t, color=palette(k % 10))
    bottom += np.array(vals)
ax.set_xticks(range(len(rows))); ax.set_xticklabels(lab, fontsize=9); ax.set_ylabel("tool calls")
ax.set_title("What the agents spent their tool calls on"); ax.legend(frameon=False, fontsize=8, ncol=6)
fig.tight_layout(); fig.savefig(FIG / "10_tool_mix.png"); plt.close(fig)

# ---------------------------------------------------------------- 11. final frame gallery
W, H = 640, 360
imgs = []
for o in rows:
    rd = ROOT / "runs" / o["run_id"]
    ev = rd / "clips" / "final_evidence.jpg"
    imgs.append((o, ev if ev.exists() else rd / "clips" / "final_frame.jpg"))
cols_n = 3
sheet = Image.new("RGB", (W * cols_n, (H + 34) * ((len(imgs) + cols_n - 1) // cols_n)), "white")
dr = ImageDraw.Draw(sheet)
try:
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 20)
except OSError:
    font = ImageFont.load_default()
for i, (o, p) in enumerate(imgs):
    im = Image.open(p).convert("RGB")
    im.thumbnail((W, H))
    x, y = (i % cols_n) * W, (i // cols_n) * (H + 34)
    sheet.paste(im, (x + (W - im.width) // 2, y + 34))
    col = (22, 163, 74) if o["outcome"] == "success" else (220, 38, 38)
    dr.rectangle([x, y, x + W - 2, y + 32], fill=col)
    dr.text((x + 8, y + 5), f"{LABEL[o['model']]} · combo {o['combo']} · {o['outcome'].upper()}", fill="white", font=font)
sheet.save(FIG / "11_final_state_gallery.jpg", quality=85)


# ---------------------------------------------------------------- 12. effort by combo
fig, axes = plt.subplots(1, 3, figsize=(13, 3.8))
mets = [("failed grasps per run", lambda o: o["failed_grasps"]), ("LLM calls per run", lambda o: results[o["run_id"]]["llm_calls"]),
        ("active minutes per run", lambda o: active[o["run_id"]])]
for ax, (title, f) in zip(axes, mets):
    means = []
    for c in (1, 2, 3):
        vs = [f(o) for o in rows if o["combo"] == c]
        means.append(np.mean(vs))
        ax.scatter([c] * len(vs), vs, color=[COLOR[o["model"]] for o in rows if o["combo"] == c], zorder=3, s=36)
    ax.plot([1, 2, 3], means, color="#111827", lw=2, marker="D", zorder=2, label="mean")
    for c, mv in zip((1, 2, 3), means):
        ax.text(c + 0.08, mv, f"{mv:.1f}", fontsize=9, va="center")
    ax.set_xticks([1, 2, 3]); ax.set_xticklabels(["3 cams", "2 cams", "wrist only"]); ax.set_title(title)
axes[0].legend(frameon=False, fontsize=8)
fig.suptitle("Fewer cameras -> more failed grasps, more LLM calls, more time (dots = runs, colored by model)", fontsize=12)
fig.tight_layout(); fig.savefig(FIG / "12_effort_by_combo.png"); plt.close(fig)

# ---------------------------------------------------------------- summary table (markdown)
lines = ["| Model | Combo | Outcome | LLM calls | Input tokens (cached) | Output tokens (reasoning) | Cost @ list price | Active min | Grasps (failed) |",
         "|---|---|---|---:|---:|---:|---:|---:|---:|"]
for o in outcomes:
    r = results.get(o["run_id"]) if o["run_id"] else None
    if r:
        t = r["tokens"]
        lines.append(f"| {LABEL[o['model']]} | {o['combo']} | {'✅ success' if o['outcome'] == 'success' else '❌ fail'} | {r['llm_calls']} | "
                     f"{t['total_input']:,} ({t['cache_read']:,}) | {t['total_output']:,} ({t['reasoning']:,}) | "
                     f"${r['cost_usd_official_list_price']:.2f} | {active[o['run_id']]} | {o['grasp_attempts']} ({o['failed_grasps']}) |")
    else:
        lines.append(f"| {LABEL[o['model']]} | {o['combo']} | {'❌ fail' if o['outcome'] == 'fail' else '— not run'} | — | — | — | — | — | — |")
(ROOT / "analysis" / "summary_table.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
print("figures:", sorted(p.name for p in FIG.iterdir()))
