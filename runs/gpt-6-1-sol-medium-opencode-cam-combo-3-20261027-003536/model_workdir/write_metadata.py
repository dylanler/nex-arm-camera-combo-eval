import csv
import datetime as dt
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
NAME = HERE.name
CLIP = ROOT / 'eval-recording' / ('20261027_003713_' + NAME)
export = json.loads((HERE / 'opencode_session_export.json').read_text())
calls = [m for m in export['messages'] if m.get('type') == 'assistant']
sums = dict(input=0, output=0, reasoning=0, cache_read=0, cache_write=0)
reported = price_cost = 0.0
prices = {
    'default': dict(input=2.00, output_including_reasoning=10.00, cache_read=0.10, cache_write=2.50),
    'prompt_over_272000': dict(input=4.00, output_including_reasoning=15.00, cache_read=0.20, cache_write=5.00),
}
for m in calls:
    t = m.get('tokens', {})
    vals = dict(input=t.get('input', 0), output=t.get('output', 0), reasoning=t.get('reasoning', 0),
                cache_read=t.get('cache', {}).get('read', 0), cache_write=t.get('cache', {}).get('write', 0))
    for k, v in vals.items():
        sums[k] += v
    reported += m.get('cost', 0) or 0
    p = prices['prompt_over_272000' if vals['input'] + vals['cache_read'] + vals['cache_write'] > 272000 else 'default']
    price_cost += (vals['input'] * p['input'] + (vals['output'] + vals['reasoning']) * p['output_including_reasoning']
                   + vals['cache_read'] * p['cache_read'] + vals['cache_write'] * p['cache_write']) / 1e6
joint_log = [json.loads(line) for line in (HERE / 'joint_log.jsonl').read_text().splitlines()]
clip = json.loads((CLIP / 'clip001.json').read_text())
with (CLIP / 'clip001_frames.csv').open() as f:
    first_stale = next((float(r['video_time_s']) for r in csv.DictReader(f) if float(r['screen_age_ms']) > 2000), None)
for name in ['final.png', 'frontend2.png', 'recording_start.png', 'recording_end.png', 'joint_log.jsonl']:
    shutil.copy2(HERE / name, CLIP / name)
now = dt.datetime.now().astimezone()
start = dt.datetime.fromtimestamp(export['info']['time']['created'] / 1000).astimezone() if 'time' in export['info'] else dt.datetime.fromtimestamp(1793086530.886).astimezone()
metadata = {
    'eval': '09 of 09',
    'experiment': 'camera-combo eval: does more camera input improve robot manipulation',
    'task': 'Place the yellow screwdriver in the bowl.',
    'model': 'openai/gpt-6.1-sol', 'reasoning_effort': 'medium',
    'harness': 'opencode v2.1.4', 'opencode_version': 'opencode v2.1.4',
    'opencode_session_id': export['info']['id'],
    'camera_combo': 3, 'cameras_enabled': ['wrist'], 'cameras_disabled': ['logitech', 'realsense'],
    'cameras_actually_appearing_in_recording': {
        'source': 'Screen capture of Chrome frontend; no direct camera sources in recorder',
        'camera_signals': ['wrist only, where frontend is visible'],
        'limitations': 'Terminal obscured frontend in sampled early video; recording became black STALLED at about 220.867 seconds. Final wrist evidence is final.png, not an end-of-video camera frame.',
        'disabled_camera_signals': [],
    },
    'disabled_camera_cutoff_method': 'Temporary startTile guard in app.js stopped existing streams and returned before getUserMedia for every non-wrist role; selectors disabled, black DISABLED tiles. Applied before start.sh. Original app.js restored after stopping recorder and server; frontend tabs closed.',
    'frontend_original_restored': (ROOT / 'app.js').read_bytes() == (HERE / 'app.js.original').read_bytes(),
    'start_time': start.isoformat(), 'end_time': now.isoformat(),
    'wall_clock_duration_s': (now-start).total_seconds(),
    'robot_first_measurement_time': dt.datetime.fromtimestamp(joint_log[0]['time']).astimezone().isoformat(),
    'robot_last_measurement_time': dt.datetime.fromtimestamp(joint_log[-1]['time']).astimezone().isoformat(),
    'llm_calls': len(calls),
    'tokens': {
        'total_input': sums['input'] + sums['cache_read'] + sums['cache_write'],
        'input_uncached': sums['input'], 'cache_read': sums['cache_read'], 'cache_write': sums['cache_write'],
        'total_output': sums['output'] + sums['reasoning'],
        'output': sums['output'], 'reasoning': sums['reasoning'],
    },
    'cost_usd_opencode_reported': reported,
    'cost_usd_provider_list_price': price_cost,
    'provider_price_table_usd_per_million_tokens': prices,
    'provider_cost_formula': 'Per assistant call: input*input_price + (output+reasoning)*output_price + cache.read*cache_read_price + cache.write*cache_write_price, divided by 1e6. High-context table applies only when input+cache.read+cache.write > 272000.',
    'outcome': 'fail',
    'outcome_evidence': 'Final wrist snapshot final.png shows empty metal bowl on left and yellow screwdriver lying horizontally on tabletop to its right. Multiple grasp/lift checks failed to retain screwdriver. No placement in bowl occurred. Video itself ends STALLED, so it does not verify final scene.',
    'budget': {'limit_llm_calls': 200, 'exceeded': len(calls) > 200, 'snapshot_before_final_reply': True},
    'recording': {
        'clip_folders': [CLIP.name], 'main_attempt_clip_folder': CLIP.name,
        'video_files': ['clip001.mp4'], 'clip_durations_s': [clip['duration_s']],
        'recorder_starts': 1, 'fps': clip['fps'], 'frames': clip['frames'],
        'recording_start': clip['start_wall_time'], 'recording_end': clip['end_wall_time'],
        'first_screen_frame_age_over_2s_at_video_time_s': first_stale,
        'encoder_errors': clip['encoder_errors'],
        'evidence_files': ['final.png', 'frontend2.png', 'recording_start.png', 'recording_end.png', 'joint_log.jsonl'],
    },
    'robot': {
        'joint_order': ['shoulder_pan', 'shoulder_lift', 'elbow_flex', 'wrist_flex', 'wrist_roll', 'gripper'],
        'position_units': 'raw encoder counts, 0..4095',
        'measured_joint_positions_start': joint_log[0]['start'],
        'measured_joint_positions_end': joint_log[-1]['end'],
        'serial_port': '/dev/cu.usbserial-110', 'serial_port_released': True,
        'shutdown': 'One-shot control scripts disconnected serial in finally. Recorder SIGTERM completed cleanly, its ffmpeg children exited. App server SIGTERM stopped. Matching processes absent and lsof serial port empty. Torque left enabled to hold retreated pose; no control process remains.',
    },
    'problems': [
        'Several approach and closure attempts nudged/rotated the screwdriver instead of securing it; lift checks showed it remained on table.',
        'Joint tracking offsets, typically a few to about 40 counts, particularly elbow and shoulder at low poses. Gripper maximum closure measured about 2780 for requested 2830; cannot distinguish mechanical limit from load using position alone. No confirmed stuck joint.',
        'Chrome AppleScript JavaScript disabled, so snapshot.py could not capture browser canvas. System Events menu access denied assistive permission. Used only icspring wrist camera via short ffmpeg snapshots instead.',
        'Initial ffmpeg snapshot pixel format auto-fell back; subsequent snapshots explicitly used bgr0.',
        'Screen recorder initially captured foreground terminal obscuring frontend, then AVFoundation screen source stopped delivering fresh frames after about 219 seconds. Recorder emitted STALLED for remaining video. This was discovered during post-run verification, not fixed during attempt.',
    ],
    'scripts_written': ['control.py', 'snapshot.py (browser canvas attempt; failed due permissions)', 'write_metadata.py'],
    'other_files_written': 'Wrist snapshots, frontend screenshots, app/recorder logs, original app.js backup, opencode_session_export.json, joint_log.jsonl. All task scripts and working artifacts are in task directory; final evidence copied into clip folder.',
    'usage_snapshot_note': 'Token and cost numbers are a snapshot from the session export taken before metadata generation, notification, and final reply. Later assistant calls are not included.',
}
dest = CLIP / (NAME + '_eval_metadata.json')
dest.write_text(json.dumps(metadata, indent=2) + '\n')
print(json.dumps({'metadata': str(dest), 'llm_calls': len(calls), 'reported_cost': reported, 'provider_cost': price_cost, 'outcome': 'fail'}))
