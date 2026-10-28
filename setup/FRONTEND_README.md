# NEX Arm · 3-Camera Eval

Browser frontend that shows the three robot cameras side by side and **never opens the built-in FaceTime camera**.

| Tile | Device (as macOS reports it) | USB VID:PID |
|---|---|---|
| Robot Wrist (USB) | `icspring camera` | `32e6:9005` |
| RealSense D415 (RGB) | `Intel(R) RealSense(TM) Depth Camera 415 RGB` | `8086:0ad3` |
| Logitech C922 | `C922 Pro Stream Webcam` | `046d:085c` |

## Run

```bash
./start.sh          # serves on http://localhost:8770 and opens it (PORT=xxxx to change)
```

Use Chrome (recommended) and allow camera access when asked.

## Features
- Finds each camera by name or USB ID; drop-downs let you reassign one by hand
- FaceTime / built-in cameras are filtered out of every list
- Global resolution (480p / 720p / 1080p) and FPS
- Live resolution + measured FPS on each tile
- Snapshot per camera or all three together (PNG, shared timestamp)
- Record all three at once (one MP4/WebM per camera)
- Hot-plug: cameras reconnect when they're plugged back in

## Recording robot tasks — `record.py`

```bash
./record.py --task pick_cube              # starts recording immediately (preview window + hotkeys)
./record.py --task pick_cube --idle       # preview first, press SPACE to start each trial
./record.py --task pick_cube --save-raw   # also save each camera unprocessed (for datasets)
./record.py --list                        # show detected cameras / assignment
./record.py -h                            # all options
```
On the first run `uv` installs `opencv-python` + `numpy` (inline script deps). Needs `ffmpeg` (Homebrew).

The recorder reads all 3 cameras directly (FaceTime is never opened) and builds the same view as the
frontend. It can run while the browser frontend is open.
Output is a 1920×1080 H.264 MP4 per clip, with a burned-in timestamp, the task/clip name and the frame number.

**Hotkeys** (in the preview window or the terminal):

| Key | Action |
|---|---|
| `SPACE` | start / pause / resume |
| `n` | next clip (finish current, start a new one) |
| `y` / `x` | label clip **success** / **fail** and finish it (SPACE starts the next trial) |
| `e` | end clip without a label |
| `m` | add a marker (e.g. "grasp", "release") |
| `s` | snapshot PNG (composite + each raw camera) |
| `+` / `-` | output FPS (5–30). A recording clip continues in a new linked clip after 1 s |
| `c` | color mode: normal, grayscale, high-contrast (CLAHE), warm, cool, invert |
| `[` `]` / `;` `'` | brightness / contrast, `0` resets |
| `l` / `f` | layout: grid (with clock/info panel), row, focus, single / which camera gets focus |
| `1` `2` `3` | hide / show wrist, RealSense, Logitech |
| `t` | timestamp overlay on/off |
| `h` | help overlay · `q` / `ESC` / Ctrl+C stops and saves |

**Output** — `recordings/<date>_<task>/`:
- `clip001.mp4`: the composite video
- `clip001_<cam>.mp4`: one per camera, only with `--save-raw`
- `clip001_frames.csv`: per-frame wall-clock time, plus each camera's frame number and frame age in ms. Use it to sync with robot logs.
- `clip001.json`: outcome, markers, pauses, setting changes, and the dropped/duplicated frame counts
- `session.json`: every clip with its outcome and success/fail totals. The success rate also prints when you quit.

Pauses are cut out of the video. Video time always equals recorded time: if the loop falls behind, a frame is repeated, and the json counts it.

**Screen mode** (literally screen-records the web frontend):
`./record.py --source screen --crop chrome` finds the Chrome tab at `localhost:8770`, brings it forward
and records that window area. Your terminal needs Screen Recording permission. It records
**whatever is on top of that area** (other windows, popups), so camera mode is preferred for clean footage.

## Notes
- The D415 RGB sensor comes through as a normal UVC webcam. Depth and IR need `pyrealsense2` / librealsense and can't be read in a browser.
- With three USB cameras on one hub, 1080p@30 on every camera can run out of USB bandwidth. If a tile fails to open, drop to 720p or 480p, or move cameras to separate ports.
