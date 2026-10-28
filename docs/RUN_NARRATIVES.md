# What each model did, run by run

Each section is written from the run's full opencode transcript (`runs/<run>/session/timeline.md`; the raw JSON is in
`opencode_session_export.slim.json`). "Call N" = the N-th LLM call of the session, "t+mm:ss" = time since the session started.
Numbers (calls, tokens, cost) come from `runs/<run>/session/stats.json`; outcomes were checked against the final camera
images (see `analysis/outcomes.json`).

Common to almost every run: the model read `start.sh`, `record.py`, `index.html`/`app.js` and the LeRobot NexArm driver
(`src/lerobot/motors/nexarm/nexarm.py`, the follower robot class) first, then wrote its own small control helper and drove
the arm by **trial joint moves + camera snapshots** (closed-loop visual servoing). No model derived real kinematics from the
supplied `NexArm.stp` CAD file — at most a few read its header.

---

## Claude Opus 5.5 (medium)

### Combo 1 — top + side + wrist · ✅ success · 75 calls · $1.93 · 1 grasp, 0 failed
- **Plan / setup (Calls 1–11, t+0:00–0:57).** Read the launcher, recorder and NexArm driver, then stated its plan at Call 5: a persistent
  robot-control server plus independent camera snapshots. Wrote `robot_server.py` (HTTP server holding the serial connection to
  `/dev/cu.usbserial-110`) and `snap.sh` (ffmpeg/AVFoundation stills from the three cameras). Started the app, listed cameras with
  `record.py --list`, and started the recorder once at Call 11, before the first move.
- **Localization.** Learned joint directions by experiment (pan/lift trials, Calls 12–35) and used cross-view pixel positions: the wrist
  view put the handle near `(295,110)` (Call 32).
- **Recovery.** A reach overshot and the handle left the wrist view (Call 40, t+5:28). It checked the top view, backed the elbow off
  1970→1890 and re-adjusted the wrist (Calls 42–45).
- **Grasp + place.** Closed to 2300 with the handle between the fingers. The gripper stalled at 2279, which it read as contact, so it
  tightened and lifted (Calls 55–59). It panned about 520 units toward the bowl, refined with top and side views, and released at Call 65.
- **End.** Returned near the start pose, stopped its recorder, server and app (Call 69), and wrote the metadata (Call 73).

### Combo 2 — top + wrist · ✅ success · 66 calls · $1.61 · 1 grasp, 0 failed
- **Setup.** Same architecture (`robot_server.py`, `r.sh`). It ignored the disabled RealSense by starting the recorder with
  `--realsense DISABLED_NO_SUCH_CAMERA`, so no device matched (Call 13).
- **Failure / recovery.** Its server could not open the serial port: a process left over from the combo-1 run (PID 43076) still held it.
  It found the holder, interrupted the old recorder, killed the old server and restarted its own (Calls 14–15).
- **Localization.** Pixel estimates from the top view (board `(370,410)`, handle `(408,380)`, Call 23). An elbow decrease pulled the arm
  back instead of forward, so it switched to lift/wrist compensation (Calls 39–43).
- **Grasp + place.** Closed to 2400; it stalled at 2337, which it read as contact (Call 49). Lifted, panned to about 1850 over the bowl,
  confirmed the rim under the gripper in the wrist view, and released (Calls 51–57).
- **End.** The recorder ignored its FIFO `q` stop command, so it sent SIGINT instead (Call 62).

### Combo 3 — wrist only · ✅ success · 108 calls · $2.35 · 3 grasps, 2 failed
- **Setup.** Same server design. The recorder was started with `--realsense DISABLED_NO_DEVICE --logitech DISABLED_NO_DEVICE` and logged
  both cameras as "NOT FOUND" (Call 12).
- **Search.** The bowl was visible but the screwdriver was not. It swept wrist flex and pan until the screwdriver entered the frame
  (Calls 15–25).
- **Depth trouble.** Without an outside view, depth was ambiguous. An elbow increase raised the camera view (Call 29), and later it
  backed off when it believed the fingers were pressing the table (Calls 43–51).
- **Grasp attempt 1 (Calls 77–81).** Closed to 2300, then 2650. The gripper did not stall, so it had missed above the handle. It reopened
  and went lower.
- **Grasp attempt 2 (Calls 85–89).** Closed to 2833 and stalled at 2779, but after lifting the screwdriver looked smaller, so it was still
  on the table. It lowered and reopened again.
- **Grasp attempt 3 (Calls 89–93).** Went lower (shoulder target 1100, suspected table contact) and closed. The shaft rotated in view and
  stayed in the gripper when it lifted.
- **Place.** Panned 2275→1980→1940 over the bowl using wrist pixels and released (Calls 95–100).
- **End.** Its server ignored SIGINT and kept the serial port. It sent SIGTERM (Calls 103–104) to release it.

---

## Gemini 4 Argon (medium)

### Combo 1 — top + side + wrist · ✅ success · 52 calls · $1.15 · 1 grasp, 0 failed
- **Setup.** Read the repo guides (`AGENT_GUIDE.md`, `CLAUDE.md`), the driver and the frontend. Wrote a single `robot_helper.py` (read/move
  joints + snapshots from all three cameras) and ran it with the LeRobot venv. Started the app (Call 4) and the recorder with
  `--no-preview` (Call 7, t+1:18).
- **Localization.** Described the top view at Call 8: gripper bottom-centre, bowl left, screwdriver right. Joint tests with three snapshots
  after every move followed; the handle tip appeared in the wrist view at pan≈2390 (Call 12).
- **Failure / recovery.** The jaws reached the table behind the handle (Calls 28–30). It raised lift to 1600, extended the elbow to 1980,
  and used the RealSense side view to put the jaws over the handle (Calls 32–34).
- **Grasp + place.** Closed to 2650; it stopped at 2491 on the handle (Call 34). Panned to the bowl, lowered in two steps and opened at
  1400 (Calls 38–44).
- **End.** Interrupted its recorder and app, then reconnected to the arm to call `exit_lerobot_mode()` cleanly (Call 48).
- **Least effort overall:** the fewest calls and the lowest cost of the 14 runs.

### Combo 2 — top + wrist · ✅ success · 85 calls · $1.61 · 1 grasp, 0 failed
- **Setup.** Wrote `arm_ctl.py`. It disabled the RealSense through the recorder with `--realsense __disabled__` and did **not** modify
  shared files. The earlier, superseded Gemini combo-2 attempt (not in this repo) had edited the shared `app.js` and left it changed.
- **Approach.** Swept pan, lift, wrist and elbow with step-named snapshots (`step11_hover_screwdriver`, `step14_pan_center`,
  `step16_wrist_down`), working from relative image changes rather than pixel coordinates.
- **Grasp + place.** A single closure to 2800 (Call 67, t+13:03), then lift, move over the bowl and release (Calls 69–77).
- **Issues.** Repeated AVFoundation `yuv420p unsupported` warnings on snapshots; they did not stop the images coming.

### Combo 3 — wrist only · ✅ success · 88 calls · $1.61 · 1 grasp, 0 failed
- **Setup.** Edited the shared `app.js` (Call 7) so the frontend only matched the wrist camera, and restored the original at Call 84.
  Wrote `robot_ctl.py` and patched it twice to fix state reads. Started the recorder with
  `--realsense DISABLED_NONE --logitech DISABLED_NONE`.
- **Approach.** Pure wrist-camera servoing. Swept pan from about 2044 to 2320, then made many small descents, reading `wrist_snap.jpg`
  after each (Calls 12–70).
- **Grasp + place.** One closure: target 2400, stalled at 2321 (Call 72). Lifted, panned to about 2018 over the bowl and opened
  (Call 80).
- **Note.** The session's 105-minute span includes about 89 idle minutes after the work was done (Calls 87–88). Active time was about
  21 minutes.
- **Takeaway.** The only model that never missed a grasp with wrist-only input.

---

## GPT-6.1 Sol (medium)

### Combo 1 — top + side + wrist · ✅ success · 89 calls · $0.84 · 2 grasps, 1 failed
- **Setup.** Wrote `control.py`, a persistent HTTP service for moves, snapshots and the recorder, then patched it for locking (Call 9).
  Started recording through the service before the first move (Call 13).
- **Localization.** Pixel targets: top-view gripper at `(220,480)` and target at `(430,320)` (Call 13). Many named approach snapshots
  followed (`approach1`, `pitch1`, `lower1`–`lower3`, `graspheight`).
- **Failed grasp 1 (Calls 51–56).** Closed gradually to 2480 and lifted, but the views showed no hold, so it reopened.
- **Grasp 2.** Changed height and pitch, then closed to 2650; it stopped at 2452 (Call 62). The RealSense side view confirmed the screwdriver
  was lifted clear (Call 66).
- **Place.** Lowered over the bowl and released (Calls 75–76).
- **Cheapest successful run** of the experiment ($0.84).

### Combo 2 — top + wrist · ❌ fail (operator abort) · 118 calls · $1.21 · 3 grasps, 2 failed
- **Setup failures.** It tried to disable the RealSense tile through Chrome AppleScript, but Apple Events JavaScript was off and System
  Events had no accessibility permission (Calls 8–12).
- **Recovery.** Launched its own Chrome profile with `--remote-debugging-port=9222` and drove the page over CDP/Playwright, which
  stopped the RealSense tile (Calls 13–14).
- **Recording.** Recorded with `record.py --source screen --fps 15`. The screen capture froze after about 223 s, so the video doesn't show
  the end of the run.
- **Grasps.** Two closures (2450→2750 at Calls 62–65, and 2700 at Call 73) did not lift the screwdriver. On the third attempt it nudged
  the screwdriver upright and grabbed it by the shaft (Calls 81–87).
- **Placement failure.** The release landed **in front of** the bowl, not in it (Call 101). It started a second placement approach, and
  the operator aborted at t+29:43 ("abort, task failed").

### Combo 3 — wrist only · ❌ fail · 128 calls · $1.32 · 6 grasps, all failed
- **Setup.** Backed up and patched the shared `app.js` so only the wrist tile opened, and reverted it at the end (Calls 6–7 and 118).
  AppleScript snapshots failed, so it fell back to direct ffmpeg capture with `-pixel_format bgr0`. Recorded with `--source screen`,
  which stalled after about 221 s.
- **Grasps.** Six closures (Calls 48, 56, 68, 82, 96, 112) between t+7:08 and t+30:05. Each one nudged or rotated the screwdriver
  without lifting it.
- **End.** Declared failure at Call 114 and retreated home. Its final wrist still shows the screwdriver next to the empty bowl.

---

## GPT-6.1 Terra (medium)

### Combo 1 — top + side + wrist · ✅ success · 151 calls · $1.23 · 2 grasps, 1 failed
- **Setup.** Its desktop captures first showed the wrong window: Chrome had no visible window and Preview was in front (Calls 6–19).
  It hid other apps, brought Chrome forward, and switched to direct ffmpeg stills. Wrote `robot.py` (LeRobot serial-bus helper).
  Recorded with `--source screen --codec hw` (Call 36). The capture stalled after about 228 s.
- **Localization.** Pixel estimates in the top view: bowl `(270,300)`, screwdriver `(450,342)` (Call 24). The side view put the fingertips
  about 30 px above the table (Call 78).
- **Failed grasp 1 (Calls 90–98).** Closed to 2549 and lifted, but the screwdriver stayed down. It changed the elbow/shoulder approach.
- **Grasp 2.** Closed until it stalled at 2368 and lifted the screwdriver visibly (Call 111). Carried it over the bowl and released
  (Call 129, t+27:37).
- **Most LLM calls** of any successful run (151).

### Combo 2 — top + wrist · ❌ fail · 113 calls · $1.30 · 2 grasps, both failed
- **Setup.** Hit the same Chrome automation blockers, then used remote debugging and wrote a Node `frontend.js`, because no Python
  websocket library was installed. Set the RealSense tile to "none" (Call 18). Wrote `move.py`, which gives interpolated moves.
  Recorded with `--source screen --crop chrome`; the capture stalled after about 224 s.
- **Grasp 1.** Progressive closures to 2750 (Calls 62–68). After the lift, the screwdriver was still on the table (Call 69).
- **Grasp 2.** More closures (2432/2730/2532), but no lift. At Call 93 (t+10:26) it stopped "rather than force a lower approach".
- **End.** Final top view: screwdriver beside the bowl.

---

## GPT-6 Astra (`~openai/gpt-astra-latest` → `openai/gpt-6-astra`, medium)

### Combo 1 — top + side + wrist · ✅ success · 73 calls · $8.14 · 1 grasp, 0 failed
- **Setup.** Read the recorder, frontend and driver (Calls 1–4). Chrome AppleScript JS failed (Call 5), so it wrote `control.py`, which takes
  a 6-value joint list plus a duration and saves camera snapshots. It started a screen recording (`--source screen --crop chrome`,
  Call 9).
- **Recovery.** Another window was covering the browser, so the screen recording was useless. It wrote `record_attempt.py`, which reuses
  `record.py`'s camera mode to build a direct three-camera composite. It switched to that and killed the screen recorder
  (Calls 17–19). That's why there are two clip folders: a 73 s aborted screen clip and the 591 s main clip.
- **Approach.** It reasoned explicitly about geometry ("shoulder down 150, elbow up 200, wrist 50 … only shifts 35 mm", "40 mm above
  the handle") and used the side view for table clearance. It moved in 6-joint steps with a composite image read after each
  (Calls 20–48).
- **Grasp + place.** One closure to 2450 (Call 50, t+8:08), lift, and "securely lifted" (Call 54). Panned to 2000/1960 over the bowl,
  lowered, opened to 1790 (Calls 56–61), and retracted home.
- **Fastest clean run** by call count among the OpenAI models; the most expensive per call (Astra list price $10 / $50 per M tokens).

### Combo 2 — top + wrist · ✅ success · 71 calls · $5.50 · 2 grasps, 1 failed
- **Setup.** Wrote `control.py` and `camera.py`. AppleScript was blocked, so it launched a debug Chrome profile and installed
  `websocket-client`; `camera.py` then stopped the RealSense tile over CDP (Calls 8–12). Recorded with `--source screen --crop chrome`,
  which stalled after about 247 s. Later wrote `move.py` for interpolated moves.
- **Failed grasp 1 (Calls 39–45).** Closed to 2250, then 2650. On lift the screwdriver stayed on the table. It reset, lowered, and changed the
  elbow and wrist.
- **Grasp 2.** Closed to 2750 and held the screwdriver (Call 50). Placed it in the bowl and released (Call 54).
- **Recovery for the video.** It noticed the main clip had frozen, so it recorded a separate 10 s direct-camera evidence clip
  (`--source cameras --realsense DISABLED_COMBO2`, Call 64).

### Combo 3 — wrist only · ✅ success · 134 calls · $10.28 · 5 grasps, 4 failed
- **Setup (most elaborate).** Did not edit the shared `app.js`. Instead it served a modified copy (`app-wrist.js`) through a
  `sitecustomize.py` hook in its own http.server, and wrote `browser.py` and `robot.py`.
- **Recording.** A 40 s screen-mode test, then the main recording in camera mode with
  `--realsense DISABLED_COMBO3 --logitech DISABLED_COMBO3` (Call 13).
- **Search.** Swept the wrist view until it found the screwdriver: tip near `(520,285)`, then handle centre at `(345,260)`.
- **Grasps.** Its closures at Calls 32–40 did not lift the screwdriver. At Call 66 it said "the first closures did not lift the screwdriver.
  I'm changing to a steeper approach". After more height and roll trials it got a secure hold at Call 116 (t+23:49).
- **Place.** Released over the bowl (Call 120) and confirmed with the wrist camera (Call 126).
- **Most expensive run** of the experiment ($10.28).
