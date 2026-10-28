# Model story facts (validated)

A per-model summary for slides. Every item is checked against `runs/<run>/session/timeline.md`, `stats.json`, and
`docs/RUN_NARRATIVES.md`. "Scripts" lists the files the model itself created or edited, including files OpenAI models added
through the `patch` tool.

## What every agent did (the common loop)
1. **Read first:** `start.sh`, `record.py`, the LeRobot NexArm driver (serial commands 96 read / 97 write / 98 torque, 1 Mbps).
2. **Build a tool:** a small control helper plus a way to grab camera frames.
3. **Learn the arm by trial:** move one joint a little, take a snapshot, infer the direction. No model used the STP CAD file for
   kinematics; a few read its header.
4. **Grasp:** close the gripper and treat a stall short of the target as contact (e.g. target 2650 → stops at 2491), then lift and
   check whether the screwdriver came along.
5. **Place, verify, clean up:** pan to the bowl, lower, open, check the images, stop processes, and write the metadata JSON.

## Claude Opus 5.5: 3/3 · 75 / 66 / 108 calls · $1.93 / $1.61 / $2.35
- **Scripts:** `robot_server.py` (persistent HTTP server holding the serial port), `snap.sh` / `r.sh` (ffmpeg snapshots + client),
  `write_metadata.py` / `make_metadata.py`.
- **Prioritized:** a stable control layer first, then cross-checking pixel positions across views.
- **Failures → recovery:**
  - Combo 1: a reach overshot the handle and lost it from the wrist view. It checked the top view, then backed the elbow off
    1970→1890 and re-aimed. One grasp, no misses.
  - Combo 2: the serial port was held by the previous run's leftover server. It found the process (PID 43076), killed it and
    restarted its own.
  - Combo 3 (wrist only): it missed twice. The first close didn't stall, so it was above the handle. The second stalled, but the
    screwdriver stayed on the table. On the third try it went lower and grabbed the shaft, which held.

## Gemini 4 Argon: 3/3 · 52 / 85 / 88 calls · $1.15 / $1.61 / $1.61 · 0 failed grasps
- **Scripts:** a single CLI helper per run (`robot_helper.py`, `arm_ctl.py`, `robot_ctl.py`) that reads, moves and snapshots, plus
  `write_metadata.py` / `generate_metadata.py`.
- **Prioritized:** few, deliberate moves with a snapshot after every step. It used the fewest calls and was the cheapest reliable model.
- **Failures → recovery:**
  - Combo 1: the jaws hit the table behind the handle. It raised the lift to 1600, extended the elbow, and used the side view to get
    over the handle.
  - Combo 2: one clean grasp at its first closure (target 2800).
  - Combo 3 (wrist only): it edited the shared `app.js` to blank the disabled cameras, then restored it at the end. Still one grasp,
    with no misses.

## GPT-6.1 Sol: 1/3 · 89 / 118 / 128 calls · $0.84 / $1.21 / $1.32
- **Scripts:** `control.py` (persistent HTTP service for moves, snapshots and the recorder), `snapshot.py`, `write_metadata.py`.
- **Prioritized:** explicit pixel-coordinate targeting, e.g. gripper (220,480) against target (430,320), with named snapshots.
- **Failures → recovery:**
  - Combo 1: the first grasp didn't hold. It changed height and pitch; the second grasp was confirmed by the side view ("lifted
    clear"). This was the cheapest success, at $0.84.
  - Combo 2: Chrome automation was blocked, so it launched its own Chrome profile and drove the page over the DevTools protocol. It
    missed 2 grasps, got the shaft on the 3rd, then **released in front of the bowl**. Operator abort at about 30 min.
  - Combo 3 (wrist only): **6 closures, none lifted the screwdriver**; it kept nudging it. It declared failure itself and restored
    the shared `app.js` it had patched.

## GPT-6.1 Terra: 1/3 · 151 / 113 calls · $1.23 / $1.30 (combo 3: fail)
- **Scripts:** `robot.py` (serial-bus helper), `move.py` (interpolated moves), `frontend.js` (Node DevTools client, because Python
  had no websocket library), `write_metadata.py` / `make_metadata.py`.
- **Prioritized:** many small, careful steps. It made the most calls of any successful run (151).
- **Failures → recovery:**
  - Combo 1: its first screen captures showed the wrong window, so it hid other apps and switched to direct camera grabs. The first
    grasp didn't lift, so it changed the approach; the second held.
  - Combo 2: two grasp sequences failed. It stopped "rather than force a lower approach".

## GPT-6 Astra: 3/3 · 73 / 71 / 134 calls · $8.14 / $5.50 / $10.28
- **Scripts:** `control.py` (6-joint moves + snapshots), `record_attempt.py` (its own three-camera composite recorder), `camera.py`
  (DevTools browser control), `browser.py`, `robot.py`, `sitecustomize.py` (served a modified frontend instead of editing the shared
  `app.js`), plus a metadata script.
- **Prioritized:** the most inventive tooling, and geometric reasoning in millimetres ("40 mm above the handle").
- **Failures → recovery:**
  - Combo 1: a window covered the browser, so the screen recording was useless. It built its own composite recorder and continued.
    One grasp, no misses.
  - Combo 2: a missed first grasp, then success. It noticed its screen recording had frozen and recorded a separate 10-second
    evidence clip.
  - Combo 3 (wrist only): 5 attempts (4 missed). It switched to a steeper approach and finally got a secure hold at call 116.
- **Cost note:** combo 1 cost more than combo 2 at the same call count. It read a 1920×1080 composite (about 2,500 tokens) after every
  move, and every image stays in the context.

## Cross-model failure → recovery patterns
| Failure | Seen in | Recovery |
|---|---|---|
| Gripper closes above the handle (no stall) | Opus c3, Sol c3, Astra c3 | Lower the approach, steeper pitch |
| Jaws hit the table | Gemini c1, Opus c3 | Raise the lift, use the side view for clearance |
| Grasp stalls but the object stays down | Sol c1, Terra c1/c2, Astra c2 | Check after the lift, change height or pitch, retry |
| Serial port held by a leftover process | Opus c2 | Find the PID, kill it, restart its own server |
| Chrome automation blocked | Sol c2, Terra c2, Astra c2/c3 | Own Chrome profile + DevTools protocol |
| Screen recording frozen or obscured | Astra c1/c2, Terra c1 | Own composite recorder, or a separate evidence clip |
| Release misses the bowl | Sol c2 | (aborted before retry) |
