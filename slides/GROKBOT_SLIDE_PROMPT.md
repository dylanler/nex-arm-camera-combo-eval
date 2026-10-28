<!--
How to use: paste everything below the line into the Grok Bot "slide-maker" chat.
The images it needs already live in the content deck (see "Sources"); backups are in slides/grokbot_attachments/.
-->

---

New task, which replaces the previous one. Please build an **entirely new Google Slides deck** in my dl88jing@gmail.com account.

## Sources
- **Design template (the organizer's Kaggle template):**
  https://docs.google.com/presentation/d/1S3na1xr34K9l1cD-Qe-FfXXzhpXNtICKvH5RTGk14tg/edit
  Make a copy of it and build in the copy. **Never edit the template itself.**
- **Content source (approved text, speaker notes and images):**
  https://docs.google.com/presentation/d/153_EWq6IMQ6lWrRmXLZTf9lAHazB2t-kiJMdd4frTpM/edit
  This is the 20-slide deck you just edited. Copy the slide text, speaker notes and images from it. Don't change that deck any further.
- **Data, if you need to check a number:** github.com/dylanler/nex-arm-camera-combo-eval (private; you have access through my GitHub
  connection).

Name the new deck: **The Test Suite Is a Camera: Evaluating Models for Embodied AI Robots (Bench Summit)**

## What the talk is
My Bench Summit (Kaggle) talk. Its thesis: when a model acts in the physical world, the test suite has to look at the world, not
just at the code. There are three cases:
1. **Case 1, a drawing arm (SO-101):** an agent wrote the control code; a camera caught the bugs.
2. **Case 2, the camera-combo robot eval (new):** five LLM models drive a Hiwonder NexArm to "place the yellow screwdriver in
   the bowl", and we vary which cameras they may use.
3. **Case 3, a 0.6B model writing physics sims:** token accuracy isn't physics.

## Summit guidelines (apply to every slide)
- Non-promotional, technical, and for benchmark practitioners. Be transparent about trade-offs and limits.
- No confidential information. Keep the template's "PROPRIETARY & CONFIDENTIAL" footer exactly as the template has it; it's the
  organizer's.
- Visuals over text: one idea per slide and as few words as possible. Detail goes in the speaker notes.
- Use only the template's own layouts, fonts and colours. Don't add new fonts, colours or themes.

## Slides to build (20, in this order)
Use the same text and speaker notes as the matching slide in the content deck. Pick the template layout that best fits each slide.

| # | Slide (title in the content deck) | Layout guidance |
|---|---|---|
| 1 | The Test Suite Is a Camera | template title layout |
| 2 | Dylan Ler | speaker / about layout with photo |
| 3 | Looking right isn't being right | title + body + image |
| 4 | Let reality be the verifier (Camera / Invariant / Trace) | 3-column statement layout |
| 5 | Case 1: a drawing arm | title + body + image |
| 6 | First drawing / First pass / Final | 3 images with captions |
| 7 | The arm sags / A taped pen / mm vs m, IK flips | 3 images with captions |
| 8 | Case 2: how many cameras? | title + body + rig photo |
| 9 | Each camera answers one question (Top-down x·y / Side z / Wrist grip) | 3-column statement layout |
| 10 | Where the cameras sit (3D model image) | **large image**: the 3D render should fill most of the slide |
| 11 | More views, more successes (5/5 · 3/5 · 3/5) | big-number 3-column layout |
| 12 | Without depth, grasps miss (0.4 · 1.0 · 3.0) | big-number 3-column layout |
| 13 | Price vs cameras (chart) | **large image** |
| 14 | Reliability vs cost (chart) | **large image** |
| 15 | Tokens vs time (chart) | **large image** |
| 16 | Case 3: a 0.6B model (85.6% token accuracy) | title + body + big number |
| 17 | Token accuracy isn't physics (631.6% / 0.21% / ~2,527×) | big-number 3-column layout |
| 18 | What this does not show (Rebuilt log / Small n / Proxy test) | 3-column statement layout |
| 19 | Takeaways (4 lines) | title + body |
| 20 | Thank you | template closing layout |

## Images
- **Charts and the 3D render (slides 10, 13, 14, 15) must be legible from the back of a room.** Use a layout with a wide image area,
  or give the image most of the slide width: at least ~80% of the slide width, centred, with the title above. Keep the body text to
  one short line, or move it into the notes. Keep the aspect ratio, and don't crop or stretch.
- All other images: fit inside the layout's image placeholder, keeping the aspect ratio.
- Take every image from the content deck, so the versions match what was approved (slide 14 uses the chart whose y-axis just says
  "combos solved").

## Content rules
- Model names: **Claude Opus 5.5, Gemini 4 Argon, GPT-6 Astra, GPT-6.1 Sol, GPT-6.1 Terra**. Write "GPT-6 Astra", never "GPT Astra".
  There are only five models: don't mention DeepSeek.
- A failed run is just a fail. Don't add "assumed", "not run" or similar.
- Every slide keeps its speaker notes from the content deck, starting with the time estimate, e.g. "(~0:45)".
- Remove any template example slides you don't use, so the deck has exactly these 20 slides.

## When you're done, send me
1. The link to the new deck.
2. The list of slide numbers with titles.
3. A thumbnail grid of all 20 slides, plus a full-size view of slides 10, 13, 14 and 15, so I can check the charts are readable.
4. Confirmation that every slide has its speaker notes, and that the footer and fonts match the template.
