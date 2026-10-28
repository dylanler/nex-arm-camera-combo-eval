import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).parent
SESSION = 'ses_e7e77eab8ffepwoHG6M3pPsYWi'
CLI = str(Path.home() / '.opencode/bin/opencode')
PYTHON = '/Users/dylanler/github/lerobot-nexarm/.venv/bin/python'

# This read-only position query closes its serial connection in finally.
subprocess.run([PYTHON, str(HERE / 'robot.py')], check=True, capture_output=True)
processes = json.loads((HERE / 'processes.json').read_text())
for key in ('app', 'recorder'):
    try:
        os.kill(processes[key], 0)
    except ProcessLookupError:
        pass
    else:
        raise RuntimeError(f'{key} still running')

with (HERE / 'opencode_session_export.json').open('w') as output:
    subprocess.run([CLI, 'session', 'export', SESSION], stdout=output, check=True)
export = json.loads((HERE / 'opencode_session_export.json').read_text())
calls = [m for m in export['messages'] if m.get('type') == 'assistant']
sums = dict(input=0, output=0, reasoning=0, cache_read=0, cache_write=0)
reported_cost = 0.0
provider_cost = 0.0
price_table = {
    'prompt_tokens_lte_272000': {'input': 10.0, 'output_including_reasoning': 50.0, 'cache_read': 1.0, 'cache_write': 12.5},
    'prompt_tokens_gt_272000': {'input': 20.0, 'output_including_reasoning': 75.0, 'cache_read': 2.0, 'cache_write': 25.0},
}
for message in calls:
    tokens = message.get('tokens') or {}
    cache = tokens.get('cache') or {}
    values = {k: tokens.get(k, 0) or 0 for k in ('input', 'output', 'reasoning')}
    values.update(cache_read=cache.get('read', 0) or 0, cache_write=cache.get('write', 0) or 0)
    for key, value in values.items():
        sums[key] += value
    prompt = values['input'] + values['cache_read'] + values['cache_write']
    price = price_table['prompt_tokens_gt_272000' if prompt > 272000 else 'prompt_tokens_lte_272000']
    provider_cost += (values['input'] * price['input'] + (values['output'] + values['reasoning']) * price['output_including_reasoning'] + values['cache_read'] * price['cache_read'] + values['cache_write'] * price['cache_write']) / 1e6
    reported_cost += message.get('cost', 0) or 0

clips = []
for folder in sorted((HERE.parent / 'eval-recording').glob('*' + HERE.name)):
    clip = json.loads((folder / 'clip001.json').read_text())
    clips.append({'clip_folder': folder.name, 'video_files': [clip['video']], 'duration_seconds': clip['duration_s'], 'capture_mode': 'screen frontend' if len(clips) == 0 else 'direct wrist feed with recorder overlays', 'cameras_actually_visible': ['wrist']})
main = HERE.parent / 'eval-recording' / clips[-1]['clip_folder']
shutil.copy2(HERE / 'success-evidence.jpg', main / 'success-evidence.jpg')
shutil.copy2(HERE / 'clip-1-end.png', main / 'recording-final-frame.png')
log = [json.loads(line) for line in (HERE / 'robot_log.jsonl').read_text().splitlines()]
start = dt.datetime.fromtimestamp(export['info']['time']['created'] / 1000).astimezone() if 'time' in export['info'] else dt.datetime.fromtimestamp(1793174541.645).astimezone()
end = dt.datetime.fromisoformat(processes['task_end_time'])
metadata = {
    'eval': '18 of 18',
    'experiment': 'camera-combo eval: does more camera input improve robot manipulation',
    'task': 'Place the yellow screwdriver in the bowl.',
    'model': '~openai/gpt-astra-latest',
    'harness_model_id': 'openrouter/openai/gpt-6-astra',
    'reasoning_effort': 'medium',
    'harness': 'opencode ' + subprocess.check_output([CLI, '--version'], text=True).strip(),
    'opencode_session_id': SESSION,
    'camera_combo': 3,
    'cameras_enabled': ['wrist'],
    'cameras_disabled': ['logitech', 'realsense'],
    'cameras_actually_in_recording': ['wrist'],
    'disabled_camera_cutoff': 'A task-local app-wrist.js is served for /app.js by sitecustomize.py. startTile returns before getUserMedia for both disabled roles, stops any tracks, clears video.srcObject, disables selection and labels the panels DISABLED. The main recorder uses nonmatching --realsense DISABLED_COMBO3 and --logitech DISABLED_COMBO3 device overrides, so neither camera is opened or recorded.',
    'start_time': start.isoformat(),
    'end_time': end.isoformat(),
    'wall_clock_duration_seconds': (end - start).total_seconds(),
    'llm_calls': len(calls),
    'total_input_tokens': sums['input'] + sums['cache_read'] + sums['cache_write'],
    'input_tokens_uncached': sums['input'],
    'input_tokens_cache_read': sums['cache_read'],
    'input_tokens_cache_write': sums['cache_write'],
    'total_output_tokens': sums['output'] + sums['reasoning'],
    'output_tokens': sums['output'],
    'reasoning_tokens': sums['reasoning'],
    'cost_usd_opencode_reported': round(reported_cost, 8),
    'cost_usd_provider_list_price': round(provider_cost, 8),
    'provider_price_table_usd_per_million_tokens': price_table,
    'cost_calculation': 'Per assistant message: prompt=input+cache.read+cache.write; output charged as output+reasoning, following the requested accounting convention; select the long-prompt price tier when prompt >272000.',
    'outcome': 'success',
    'end_camera_evidence': 'After release and arm retraction, the wrist image and final recorded frame show the yellow handle and entire metal shaft resting within the bowl. The open gripper is visibly clear of the screwdriver.',
    'budget_limit_llm_calls': 200,
    'budget_exceeded': len(calls) > 200,
    'recording': {'main_clip_folder': main.name, 'clips': clips, 'recorder_starts': processes['recorder_starts'], 'main_attempt_recorded_before_first_movement': True, 'note': 'First clip records the actual frontend with wrist live and disabled panels black. Following an auxiliary screen-capture timeout, the main clip was recorded with record.py camera mode using the same live wrist feed as the frontend, rather than a literal browser-window capture. Later inspection confirmed the first screen clip was valid.'},
    'robot': {'joint_order': ['shoulder_pan', 'shoulder_lift', 'elbow_flex', 'wrist_flex', 'wrist_roll', 'gripper'], 'units': 'raw servo position counts, 0..4095', 'measured_start': log[0]['start'], 'measured_end_of_motion': log[-2]['end'], 'measured_final_after_recording': log[-1]['end'], 'serial_port': '/dev/cu.usbserial-110', 'serial_connection_closed': True, 'holding_torque_retained': True},
    'hardware_software_problems': [
        'Chrome JavaScript via Apple Events was disabled. Used a task-local frontend frame-upload loop instead; only wrist frames were uploaded.',
        'A separate one-frame AVFoundation screen capture timed out. Switched the main recording to direct wrist-camera capture. The original screen recording was later confirmed valid.',
        'Several initial closures missed because the gripper was above the handle. Low approaches brushed and displaced the screwdriver; raised and realigned using wrist-only feedback.',
        'Observed joint tracking errors under load and apparent firmware limits near wrist flex 800/3076 and wrist roll 3082; revised targets and approach. No robot-control process crash or persistent serial failure.',
        'Final grasp was confirmed by gripper obstruction around raw 2478 versus a 2800 target and by the screwdriver moving with the lifted gripper.'
    ],
    'scripts_written': ['sitecustomize.py', 'app-wrist.js', 'browser.py', 'robot.py', 'finish_metadata.py'],
    'cleanup': 'Both app-server instances, both recorder runs and their capture/encoder children were stopped; all robot control scripts exited and closed serial; frontend localhost:8770 tabs were closed. A pre-existing unrelated server on port 8765 was not started by this evaluation.',
    'usage_snapshot_time': dt.datetime.now().astimezone().isoformat(),
    'usage_note': 'Token/cost numbers are a snapshot taken before the final reply. Assistant messages without completed usage fields contribute zero usage but are counted as calls.'
}
destination = main / (HERE.name + '_eval_metadata.json')
destination.write_text(json.dumps(metadata, indent=2) + '\n')
print(json.dumps({'metadata': str(destination), 'outcome': metadata['outcome'], 'llm_calls': len(calls), 'provider_cost_usd': metadata['cost_usd_provider_list_price']}), flush=True)

# The operator notification is deliberately the final external action.
subprocess.run('afplay /System/Library/Sounds/Glass.aiff; say "Eval 18 of 18 complete. Please reset the screwdriver."', shell=True, check=True)
