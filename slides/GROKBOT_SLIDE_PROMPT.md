<!--
How to use: paste everything below the line into the Grok Bot "slide-maker" chat, and attach the 4 images in
slides/grokbot_attachments/ (camera_placement_3d.png, chart_price_vs_cameras.png,
chart_reliability_vs_cost.png, chart_tokens_vs_time.png).
-->

---

Please edit an existing Google Slides deck in my dl88jing@gmail.com account (I have edit access). Don't create a new deck.

**Deck:** https://docs.google.com/presentation/d/153_EWq6IMQ6lWrRmXLZTf9lAHazB2t-kiJMdd4frTpM/edit

## Context
This is my talk "The Test Suite Is a Camera: Evaluating Models for Embodied AI Robots" for the Bench Summit (Kaggle). It's built on
the organizer's Kaggle template. I'm adding a new case study, a real-robot eval:
- **Task:** five LLM models drive a Hiwonder NexArm 6-DOF arm, via the opencode CLI, to "place the yellow screwdriver in the bowl".
- **The only variable:** which cameras the model may use.
- **Fixed:** the prompt is sent once, the budget is 200 LLM calls, and there's no pre-written control code.
- **Data, logs and videos:** github.com/dylanler/nex-arm-camera-combo-eval

## Summit guidelines (apply to every slide)
- Non-promotional, technical, and for benchmark practitioners. Be transparent about trade-offs and limits.
- No confidential information.
- **Keep the organizer's "PROPRIETARY & CONFIDENTIAL" footers exactly as they are.** They're the organizer's, not mine.
- Visuals over text: one idea per slide and as few words as possible. No paragraphs on slides; detail goes in the speaker notes.

## Hard rules for editing
1. Don't change slides 1–7 (title, about me, Looking right isn't being right, Let reality be the verifier, Case 1 + its two
   follow-up slides).
2. Build every new slide by **duplicating an existing slide with the same layout**, so fonts, colours, kicker style and footer all match
   the template. Don't add new layouts or fonts, or change the theme.
3. Put images **in the image box of the slide you duplicated**, at the same position and size. Keep the aspect ratio: no stretching or
   cropping of chart text. Delete the old image you replace.
4. Every new slide gets **speaker notes** in the existing style, starting with a time estimate like "(~0:45)". **Never overwrite the
   speaker notes of an existing slide** unless I list it below.
5. Model names to use: **Claude Opus 5.5, Gemini 4 Argon, GPT-6 Astra, GPT-6.1 Sol, GPT-6.1 Terra**. Write "GPT-6 Astra", never "GPT Astra"
   or "Astra latest". There are only five models: don't mention DeepSeek anywhere.
6. When a run failed, just call it a fail. Don't add "assumed", "not run" or similar.

## Current state of the deck (check this first)
- The deck should have 13 slides. Slide 8 is a new, partly built slide titled **"Case 2: how many cameras?"**. It has 3 body lines and a photo
  of the lightbox rig. Keep its title, body and photo. It only needs speaker notes (below).
- Check that the speaker notes of **"Token accuracy isn't physics"** still start with "(~1:30) A deterministic benchmark: harmonic
  oscillator…". An earlier editing attempt typed over them and then undid it. If they're wrong, restore them from version history.

## Slide 8 notes (add)
"(~1:00) Case 2 asks a practical question: how many cameras does an agent need to check its own work? Same idea, new rig: a Hiwonder
NexArm in a lightbox. The task: place the yellow screwdriver in the bowl. Five frontier models through the opencode CLI, the prompt sent
once, a 200-LLM-call budget, no pre-written control code. We vary only which cameras the model may use."

## Insert 7 new slides right after slide 8, in this order

**A) Duplicate slide 4 ("Let reality be the verifier": kicker, title, 3 columns with dividers)**
- Kicker: `THREE CAMERAS, THREE JOBS`
- Title: `Each camera answers one question`
- Column 1: `Top-down` / `x · y: where is the arm?`
- Column 2: `Side, low corner` / `z: how high is the gripper?`
- Column 3: `Wrist` / `grip: are the fingers on the handle?`
- Notes: "(~0:45) Each camera answers a different geometric question. The top-down Logitech gives x and y on the table. The RealSense,
  low in the front-left corner, gives height, which is the hard part for grasping. The wrist camera gives the final alignment of the
  fingers on the handle."

**B) Duplicate slide 3 ("Looking right isn't being right": title, body, picture on the right)**
- Title: `Where the cameras sit`
- Body: `Three.js model of the lightbox` / `Combo 1: all three · Combo 2: top + wrist · Combo 3: wrist only`
- Image: attached **camera_placement_3d.png** (16:9)
- Notes: "(~0:45) A 3D model of the rig. Blue: the top-down camera on its boom arm. Purple: the side camera on a small tripod outside
  the front-left corner. Pink: the wrist camera on the gripper. Combo 1 uses all three, combo 2 drops the side camera, combo 3 keeps
  only the wrist."

**C) Duplicate "Token accuracy isn't physics" (kicker, title, 3 big numbers with captions)**
- Kicker: `SUCCESS BY CAMERA COMBO · 5 MODELS`
- Title: `More views, more successes`
- Big numbers / captions: `5 / 5` `top + side + wrist` · `3 / 5` `top + wrist` · `3 / 5` `wrist only`
- Notes: "(~0:45) With all three cameras, every model succeeded. Drop the side camera and only three of five did; with the wrist camera
  alone, also three of five. The models: Claude Opus 5.5, Gemini 4 Argon, GPT-6 Astra, GPT-6.1 Sol and GPT-6.1 Terra."

**D) Duplicate the same big-number slide again**
- Kicker: `FAILED GRASPS PER RUN`
- Title: `Without depth, grasps miss`
- Big numbers / captions: `0.4` `3 cameras` · `1.0` `top + wrist` · `3.0` `wrist only`
- Notes: "(~0:45) The clearest signal is failed grasps. Without the side view, models closed the gripper above the handle, pressed into
  the table, or nudged the screwdriver. Calls per run rose from about 88 to 114, and active time from about 17 to 26 minutes."

**E) Duplicate slide 8 (title, body, picture on the right)**
- Title: `Price vs cameras`
- Body: `Sol and Terra only succeed with all 3 cameras` / `Opus, Gemini and GPT-6 Astra also succeed with the wrist alone`
- Image: attached **chart_price_vs_cameras.png** (it replaces the rig photo in this copy)
- Notes: "(~0:45) Cameras and model price trade off. The cheaper models, GPT-6.1 Sol and Terra, only succeeded with all three views.
  The stronger models also succeeded with just the wrist camera. A camera is a one-off hardware cost; a stronger model is a recurring
  one."

**F) Duplicate slide 8 again**
- Title: `Reliability vs cost`
- Body: `Gemini: 3/3 at $1.46 a run` / `Opus: 3/3 at $1.96` / `GPT-6 Astra: 3/3 at $7.98`
- Image: attached **chart_reliability_vs_cost.png**
- Notes: "(~0:45) Three models solved all three camera combos. Gemini 4 Argon and Claude Opus 5.5 did it for about $1.50 to $2 a run at
  the providers' own list prices. GPT-6 Astra was just as reliable at four to five times the cost."

**G) Duplicate slide 8 again**
- Title: `Tokens vs time`
- Body: `Each camera adds image tokens to every step` / `Old images stay in context, so cost grows with history` / `Time also depends on inference speed`
- Image: attached **chart_tokens_vs_time.png**
- Notes: "(~0:45) Every image stays in the context and is re-read on each later call, so each extra camera makes every step more
  expensive. GPT-6 Astra's three-camera run cost more than its two-camera run with about the same number of calls. And tokens only
  loosely predict time: provider, inference tier and effort level matter too."

## Then edit these existing slides (they follow the new ones)
1. **"Case 2: a 0.6B model"**: retitle it **"Case 3: a 0.6B model"**. Change nothing else.
2. **"What this does not show"**: in the "Small n" column, change the text to `One arm, one setup, one run per model × combo`. Keep the
   "Small n" heading. Add to its notes: "The camera eval has one run per model and camera combo, so treat it as a strong signal, not a
   statistic."
3. **"Takeaways"**: add a 4th line in the same format as lines 1–3:
   `4. Budget cameras and model together: three views let a cheaper model succeed.`
   Add to its notes: "Fourth: cameras and model choice trade off. Three views made every model succeed; only the stronger models
   coped with one."
4. Leave "Thank you" and all other slides untouched.

## Expected final order (20 slides)
1 The Test Suite Is a Camera · 2 Dylan Ler · 3 Looking right isn't being right · 4 Let reality be the verifier · 5 Case 1: a drawing arm ·
6 First drawing / First pass / Final · 7 The arm sags / A taped pen / mm vs m · **8 Case 2: how many cameras? · 9 Each camera answers one
question · 10 Where the cameras sit · 11 More views, more successes · 12 Without depth, grasps miss · 13 Price vs cameras · 14 Reliability
vs cost · 15 Tokens vs time** · 16 Case 3: a 0.6B model · 17 Token accuracy isn't physics · 18 What this does not show · 19 Takeaways ·
20 Thank you

## When you're done
- List every slide number with its title so I can check the order.
- Confirm that each new slide is a duplicate of a template slide (fonts and footer match).
- Confirm that each image sits inside its image box without stretching.
- Confirm that every new slide has speaker notes.
- Confirm that no existing speaker notes changed except slides 8, 18 and 19.
- Share a screenshot or thumbnail of slides 8–15.
