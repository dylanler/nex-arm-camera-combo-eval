import datetime as dt
import json
from pathlib import Path

root = Path('/Users/dylanler/github/nex-arm-3-cam-eval')
name = 'gpt-6-1-terra-medium-opencode-cam-combo-2-20261027-222824'
work = root / name
folder = '20261027_222959_' + name
clip_dir = root / 'eval-recording' / folder
export = json.loads((work / 'opencode_session_export.json').read_text())
messages = [m for m in export['messages'] if m.get('type') == 'assistant']
totals = dict(input=0, output=0, reasoning=0, cache_read=0, cache_write=0)
reported = 0.0
list_price = 0.0
for m in messages:
    t = m.get('tokens') or {}
    c = t.get('cache') or {}
    i, o, r = (t.get(k, 0) or 0 for k in ('input', 'output', 'reasoning'))
    cr, cw = (c.get(k, 0) or 0 for k in ('read', 'write'))
    for key, value in zip(totals, (i, o, r, cr, cw)):
        totals[key] += value
    high = i + cr + cw > 272000
    rates = (2, 7.5, 0.10, 2.50) if high else (1, 5, 0.05, 1.25)
    list_price += (i*rates[0] + (o+r)*rates[1] + cr*rates[2] + cw*rates[3]) / 1e6
    reported += m.get('cost', 0) or 0
start = dt.datetime.fromisoformat('2026-10-27T22:28:24-07:00')
end = dt.datetime.fromisoformat('2026-10-27T22:39:28.521-07:00')
metadata = {
    'eval': '11 of 18',
    'experiment': 'camera-combo eval: does more camera input improve robot manipulation',
    'task': 'Place the yellow screwdriver in the bowl.',
    'model': 'openai/gpt-6.1-terra', 'reasoning_effort': 'medium',
    'harness': 'opencode v2.1.4', 'opencode_session_id': 'ses_e7f04ee39ffegbHq1YiPKTfhk3',
    'camera_combo': 2, 'cameras_enabled': ['logitech', 'wrist'], 'cameras_disabled': ['realsense'],
    'cameras_actually_in_recording': ['logitech', 'wrist'],
    'camera_recording_qualification': 'Both appear as frozen initial views; no RealSense imagery appears. Screen source later reports STALLED. The sampled frames at 10, 60, 150 and 210 seconds show the same initial scene, so the recording cannot verify the actual movements.',
    'disabled_camera_cutoff': 'In the recorded frontend, set the RealSense device selector to none via Chrome DevTools; its change handler stops all RealSense tracks and clears srcObject. Verified live=false before starting the recording. The frontend status text remained 3/3 because it is not recalculated on individual selection changes.',
    'start_time': start.isoformat(), 'end_time': end.isoformat(), 'wall_clock_duration_s': (end-start).total_seconds(),
    'llm_calls': len(messages),
    'total_input_tokens': totals['input'] + totals['cache_read'] + totals['cache_write'],
    'input_tokens_uncached': totals['input'], 'cache_read_tokens': totals['cache_read'], 'cache_write_tokens': totals['cache_write'],
    'total_output_tokens': totals['output'] + totals['reasoning'], 'output_tokens': totals['output'], 'reasoning_tokens': totals['reasoning'],
    'cost_usd_opencode_reported': round(reported, 8), 'cost_usd_provider_list_price': round(list_price, 8),
    'provider_list_price_usd_per_million': {
        'prompt_at_most_272000': {'input': 1.0, 'output_including_reasoning': 5.0, 'cache_read': 0.05, 'cache_write': 1.25},
        'prompt_over_272000': {'input': 2.0, 'output_including_reasoning': 7.5, 'cache_read': 0.10, 'cache_write': 2.50},
    },
    'outcome': 'fail',
    'end_evidence': 'Final direct Logitech still final_logitech.jpg shows the yellow screwdriver still on the table to the right of an empty bowl. The recorder video ends with STALLED and cannot establish the end state; the still was captured separately after the attempt.',
    'budget_exceeded': len(messages) > 200,
    'recording': {'recorder_starts': 1, 'clip_folders': [{'name': folder, 'video_files': ['clip001.mp4'], 'durations_s': [569.2]}], 'source': 'record.py screen mode, cropped to frontend Chrome window', 'first_screen_source_age_over_2s_at_video_s': 224.4667, 'screen_stalled_frame_count': 5171},
    'robot': {'joint_order': ['shoulder_pan', 'shoulder_lift', 'elbow_flex', 'wrist_flex', 'wrist_roll', 'gripper'], 'units': 'raw servo counts', 'start_positions': [2051,2608,1469,2022,2046,1789], 'end_positions': [2059,2610,1451,2033,2046,1790], 'serial_port': '/dev/cu.usbserial-110', 'serial_port_released': True, 'torque': 'left enabled to hold the near-start pose; bridge exited and port closed'},
    'problems': ['Elbow repeatedly fell short of commanded positions by approximately 35–46 counts and drifted several counts across subsequent commands; cause undetermined. Stopped rather than force the arm.', 'Screen recorder showed apparently frozen initial frontend camera views even while the screen frame counter advanced, and then STALLED starting at about 224.47 s. The recorder was stopped normally at the end.', 'A separate test of screen capture timed out; cause of recording freeze not established.', 'Two attempted gripper closures did not lift the screwdriver.'],
    'scripts_written': ['frontend.js', 'move.py', 'write_metadata.py'],
    'token_cost_snapshot_note': 'Token and cost figures are a snapshot taken before the final reply; subsequent calls are not included.',
}
out = clip_dir / (name + '_eval_metadata.json')
out.write_text(json.dumps(metadata, indent=2) + '\n')
print(json.dumps({'metadata':str(out), 'llm_calls':len(messages), 'input_tokens':metadata['total_input_tokens'], 'output_tokens':metadata['total_output_tokens'], 'cost_reported':metadata['cost_usd_opencode_reported'], 'cost_list':metadata['cost_usd_provider_list_price']}))
