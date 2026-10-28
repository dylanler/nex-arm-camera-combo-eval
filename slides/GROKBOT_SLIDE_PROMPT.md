<!--
How to use: paste everything below the line into the Grok Bot "slide-maker" chat.
All assets are in the GitHub repo dylanler/nex-arm-camera-combo-eval (paths below); backups in slides/grokbot_attachments/.
-->

---

Correction, and the final brief: **use no content from any earlier deck.** No drawing arm, no SO-101, no Qwen / 0.6B model, no "Case 1/2/3". The only content source is the camera-combo eval repo, and the slide outline is the HTML deck in that repo.

## Sources
- **Design only:** the organizer's Kaggle template
  https://docs.google.com/presentation/d/1S3na1xr34K9l1cD-Qe-FfXXzhpXNtICKvH5RTGk14tg/edit
  Make a copy and build in the copy. Use its layouts, fonts, colours and footer, but none of its example content. **Never edit the
  template itself.**
- **Content:** GitHub repo **dylanler/nex-arm-camera-combo-eval** (private; you have access through my GitHub connection).
  - Slide outline and wording: `slides/index.html`. Follow it slide by slide.
  - Numbers and facts: `README.md`, `analysis/results.csv`, `analysis/outcomes.json`, `docs/RUN_NARRATIVES.md`.
  - Images: `slides/assets/` and `slides/grokbot_attachments/`.
- Don't touch the deck 153_EWq6IMQ6lWrRmXLZTf9lAHazB2t-kiJMdd4frTpM again. If you made a partial copy earlier, delete it.

Name the new deck: **Do more cameras help an LLM agent control a robot arm? (Bench Summit)**

## Summit guidelines (every slide)
- Non-promotional, technical, and for benchmark practitioners. Be transparent about trade-offs and limits.
- No confidential information. Keep the template's "PROPRIETARY & CONFIDENTIAL" footer exactly as the template has it; it's the
  organizer's.
- Visuals over text: one idea per slide and very few words. Detail goes in the speaker notes.
- Use only the template's layouts, fonts and colours.

## Slides (12, in this order; wording from `slides/index.html`)
| # | Slide | Content | Image (repo path) |
|---|---|---|---|
| 1 | **Do more cameras help an LLM agent control a robot arm?** | Subtitle: `5 models · 3 camera combos · 1 task · prompt sent once · 200-call budget`. Task line: "Place the yellow screwdriver in the bowl." Speaker: Dylan Ler | none (template title layout) |
| 2 | **The rig: three cameras, three jobs** | Three short items: `Top-down Logitech → x · y` (where the arm is on the table) · `Side RealSense, low corner → z` (gripper height) · `Wrist camera → grip` (finger alignment) | `slides/assets/lightbox_photo.jpg` |
| 3 | **Where the cameras are, and what each one is for** | One line: `Top-down = x/y · Side = z (height) · Wrist = fine grip` | `slides/grokbot_attachments/camera_placement_3d.png`, **large** |
| 4 | **Results: every model succeeded with all three cameras** | none | `slides/assets/01_outcome_matrix.png`, **large** |
| 5 | **More views, more successes** (big numbers) | `5 / 5` top + side + wrist · `3 / 5` top + wrist · `3 / 5` wrist only | none |
| 6 | **Take away cameras, and grasps start failing** (big numbers) | `0.4` failed grasps per run, 3 cameras · `1.0` top + wrist · `3.0` wrist only | optional small: `slides/assets/12_effort_by_combo.png` |
| 7 | **Same model, fewer cameras: Claude Opus 5.5** | Left: `3 cameras · 1 grasp · 75 calls · $1.93`. Right: `Wrist only · 3 grasps (2 missed) · 108 calls · $2.35` | Videos `runs/claude-opus-5-5-medium-opencode-cam-combo-1-20261026-150532/clips/claude-opus-5-5-medium-opencode-cam-combo-1-20261026-150532_last240s_8x.mp4` and `runs/claude-opus-5-5-medium-opencode-cam-combo-3-20261026-153111/clips/claude-opus-5-5-medium-opencode-cam-combo-3-20261026-153111_last240s_8x.mp4`: upload them to my Drive and insert as videos. If videos aren't possible, use the stills `runs/claude-opus-5-5-medium-opencode-cam-combo-1-20261026-150532/clips/final_frame.jpg` and `runs/claude-opus-5-5-medium-opencode-cam-combo-3-20261026-153111/clips/final_frame.jpg` |
| 8 | **Trade-off 1: model price vs number of cameras** | `Cheaper models (Sol, Terra) only succeed with all 3 cameras. Opus, Gemini and GPT-6 Astra also succeed with the wrist alone.` | `slides/grokbot_attachments/chart_price_vs_cameras.png`, **large** |
| 9 | **Trade-off 2: reliability vs cost** | `GPT-6 Astra is as reliable as Gemini and Opus, but costs 4–5× more per run.` | `slides/grokbot_attachments/chart_reliability_vs_cost.png`, **large** |
| 10 | **Trade-off 3: tokens vs time** | `Each camera adds image tokens to every step. Tokens drive time only loosely: inference speed matters as much.` | `slides/grokbot_attachments/chart_tokens_vs_time.png`, **large** |
| 11 | **Limits** (3-column statement layout) | `One run per cell` / `Display sleep stalled 5 screen recordings: outcomes checked from final stills` / `One arm, one scene, one task` | none |
| 12 | **Takeaways** (3 columns) | `Cameras are cheap reliability: three views took every model to 5/5` · `Or pay for a stronger model: Opus, Gemini and GPT-6 Astra manage with one camera` · `Tokens ≠ time: pick the inference tier for your latency budget` | none |

Close with the template's thank-you / closing layout: `Thank you · github.com/dylanler · dylanler.github.io` (the repo is private, so don't link it).

## Images
- **Large** means the image fills at least ~80% of the slide width, centred, under the title, with at most one short text line. These
  charts must be readable from the back of a room.
- Keep every image's aspect ratio: no stretching or cropping.

## Content rules
- Five models only: **Claude Opus 5.5, Gemini 4 Argon, GPT-6 Astra, GPT-6.1 Sol, GPT-6.1 Terra**. Write "GPT-6 Astra", never "GPT Astra".
  Don't mention DeepSeek.
- A failed run is just a fail. Don't add "assumed", "not run" or similar.
- Costs are at the providers' own list prices, as in the README.

## Speaker notes (one per slide; start with a time estimate)
1. "(~0:30) I'm Dylan Ler. One question: if you give a general coding agent more camera views of a robot, does it manipulate better, or just spend more tokens looking?"
2. "(~0:45) A Hiwonder NexArm in a lightbox. Three cameras: the top-down Logitech gives x and y, the RealSense low in the front-left corner gives height, and the wrist camera gives the final alignment on the handle."
3. "(~0:45) A three.js model of the rig. Combo 1 uses all three cameras, combo 2 drops the side camera, combo 3 keeps only the wrist."
4. "(~0:45) Five models through the opencode CLI: prompt sent once, 200-call budget, no pre-written control code. With all three cameras, every model succeeded."
5. "(~0:30) Five of five with three views, three of five with top plus wrist, three of five with the wrist alone."
6. "(~0:45) The clearest signal is failed grasps: 0.4 per run with three cameras, 3.0 with the wrist only. Without the side view, models closed above the handle, pressed into the table or nudged the screwdriver. Calls per run rose from about 88 to 114."
7. "(~0:45) Same model, same task. With three cameras Opus grasped once. With the wrist alone it missed twice before the third grasp held."
8. "(~0:45) Cameras and model price trade off. GPT-6.1 Sol and Terra only succeeded with all three views; the stronger models coped with the wrist camera alone."
9. "(~0:45) Gemini 4 Argon and Claude Opus 5.5 solved all three combos for about $1.50 to $2 a run. GPT-6 Astra did too, at four to five times the cost."
10. "(~0:45) Every image stays in context and is re-read on later calls, so a camera costs tokens on every step. GPT-6 Astra's three-camera run cost more than its two-camera run with the same number of calls. And tokens only loosely predict time."
11. "(~0:45) Limits: one run per model and combo, one arm, one scene. Five screen recordings stalled when the display slept, so those outcomes were checked from the models' final camera stills."
12. "(~0:30) Three takeaways: cameras are cheap reliability, a stronger model can substitute for views, and tokens are not time."

## When you're done, send me
1. The link to the new deck.
2. The list of slide numbers with titles.
3. A thumbnail grid of all slides, plus a full-size view of slides 3, 4, 8, 9 and 10.
4. Confirmation that no content from the old deck (drawing arm, Qwen, Case 1/2/3) appears anywhere, including the notes.
