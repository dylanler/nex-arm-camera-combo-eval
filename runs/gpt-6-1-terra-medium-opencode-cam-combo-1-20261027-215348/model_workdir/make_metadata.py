import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

base = Path('/Users/dylanler/github/nex-arm-3-cam-eval')
name = 'gpt-6-1-terra-medium-opencode-cam-combo-1-20261027-215348'
work = base / name
folder = base / 'eval-recording' / ('20261027_215824_' + name)
session = 'ses_e7f2493e3ffeC4NvA51wF5UiYg'
opencode = str(Path.home() / '.opencode/bin/opencode')
with (work / 'opencode_session_export.json').open('w') as f:
    subprocess.run([opencode, 'session', 'export', session], cwd=base, stdout=f, check=True)
messages = json.loads((work / 'opencode_session_export.json').read_text())['messages']
assistant = [m for m in messages if m.get('type') == 'assistant']
totals = dict(input=0, output=0, reasoning=0, cache_read=0, cache_write=0)
reported = 0.0
list_price = 0.0
high_calls = 0
for message in assistant:
    t = message.get('tokens') or {}
    cache = t.get('cache') or {}
    i, o, r = (t.get(k, 0) or 0 for k in ('input', 'output', 'reasoning'))
    cr, cw = (cache.get(k, 0) or 0 for k in ('read', 'write'))
    for key, value in zip(totals, (i, o, r, cr, cw)):
        totals[key] += value
    high = i + cr + cw > 272000
    high_calls += high
    rates = (2, 7.5, .10, 2.5) if high else (1, 5, .05, 1.25)
    list_price += (i*rates[0] + (o+r)*rates[1] + cr*rates[2] + cw*rates[3]) / 1_000_000
    reported += message.get('cost', 0) or 0

start = dt.datetime.fromisoformat('2026-10-27T21:53:48-07:00')
end = dt.datetime.fromisoformat('2026-10-27T22:22:51-07:00')
clip = json.loads((folder / 'clip001.json').read_text())
metadata = {
    'eval': '10 of 18',
    'experiment': 'camera-combo eval: does more camera input improve robot manipulation',
    'task': 'Place the yellow screwdriver in the bowl.',
    'model': 'openai/gpt-6.1-terra', 'reasoning_effort': 'medium',
    'harness': 'opencode v2.1.4', 'opencode_session_id': session,
    'camera_combo': 1, 'cameras_enabled': ['logitech', 'realsense', 'wrist'],
    'cameras_disabled': ['none'],
    'cameras_actually_appearing_in_recording': ['logitech', 'realsense', 'wrist'],
    'camera_recording_qualification': 'All three are visible in the frontend early in the recording. The screen source stalled at 228.4 seconds and the remainder of the composite displays STALLED, including the end.',
    'disabled_camera_signal_cutoff': 'None disabled; no cutoff needed.',
    'start_time': start.isoformat(), 'end_time': end.isoformat(),
    'wall_clock_duration_seconds': (end-start).total_seconds(),
    'llm_calls': len(assistant),
    'total_input_tokens': totals['input'] + totals['cache_read'] + totals['cache_write'],
    'input_tokens_excluding_cache': totals['input'], 'cache_read_tokens': totals['cache_read'],
    'cache_write_tokens': totals['cache_write'],
    'total_output_tokens': totals['output'] + totals['reasoning'],
    'output_tokens_excluding_reasoning': totals['output'], 'reasoning_tokens': totals['reasoning'],
    'cost_usd_opencode_reported': reported, 'cost_usd_provider_list_price': list_price,
    'price_table_usd_per_million': {
        'prompt_at_most_272000': {'input': 1.0, 'output_including_reasoning': 5.0, 'cache_read': .05, 'cache_write': 1.25},
        'prompt_over_272000': {'input': 2.0, 'output_including_reasoning': 7.5, 'cache_read': .10, 'cache_write': 2.5},
        'high_context_call_count': high_calls,
    },
    'outcome': 'success',
    'outcome_evidence': 'After the last motion, an independently captured Logitech image shows the yellow screwdriver resting inside the bowl, both handle and shaft visible; saved as final_logitech_evidence.jpg. The end of the screen recording is STALLED and does not show the final result. An unexplained joint reset and bowl movement occurred before the last command, so uninterrupted video evidence of causation is unavailable.',
    'budget_exceeded': len(assistant) > 200,
    'recording': {
        'clip_folders': [folder.name], 'video_files': [clip['video']],
        'clip_durations_seconds': [clip['duration_s']], 'recorder_starts': 1,
        'source': 'screen recording of frontend with record.py',
        'screen_stalled_from_video_seconds': 228.4,
        'screen_stalled_frame_count': 18582, 'screen_total_frame_count': 22008,
        'final_evidence_image': 'final_logitech_evidence.jpg',
    },
    'robot': {
        'port': '/dev/cu.usbserial-110',
        'joint_order': ['shoulder_pan', 'shoulder_lift', 'elbow_flex', 'wrist_flex', 'wrist_roll', 'gripper'],
        'raw_joint_positions_at_start': [2054, 2609, 1483, 2024, 2047, 1790],
        'raw_joint_positions_at_end': [2062, 1661, 1902, 2024, 2046, 1603],
    },
    'hardware_software_problems': [
        'The screen source ceased producing new frames at 22:02:13; recorder produced STALLED frames until stopped, so the final manipulation is not recorded on video.',
        'Before the final commanded movement the measured joints unexpectedly returned near their original configuration and the bowl was later found displaced; cause unknown.',
        'Elbow and shoulder occasionally lagged commanded positions under load; two initial grasp attempts failed before the screwdriver was lifted.',
        'macOS denied simulated keystrokes when trying to close the existing browser tab; the pre-existing browser was not terminated. The started app server, recorder and control scripts were stopped and the serial port released.',
    ],
    'scripts_written': [name + '/robot.py', name + '/make_metadata.py'],
    'snapshot_note': 'Token and cost figures are a snapshot exported before the final reply and do not include subsequent calls.',
    'snapshot_time': dt.datetime.now().astimezone().isoformat(),
}
if '--dry-run' in sys.argv:
    print(json.dumps({'llm_calls': len(assistant), 'tokens': totals, 'reported': reported, 'list_price': list_price, 'outcome': metadata['outcome']}, indent=2))
else:
    (folder / (name + '_eval_metadata.json')).write_text(json.dumps(metadata, indent=2) + '\n')
    print('Metadata written:', folder / (name + '_eval_metadata.json'))
