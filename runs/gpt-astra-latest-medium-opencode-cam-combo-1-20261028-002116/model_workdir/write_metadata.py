import datetime as dt
import json
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).parent
sid = 'ses_e7e9d9299ffeAdlRysIsSE6c6E'
with (root / 'opencode_session_export.json').open('w') as f:
    subprocess.run([str(Path.home()/'.opencode/bin/opencode'), 'session', 'export', sid], stdout=f, check=True, cwd=root.parent)
data = json.loads((root/'opencode_session_export.json').read_text())
messages = [m for m in data['messages'] if m.get('type') == 'assistant']
totals = dict(input=0, output=0, reasoning=0, cache_read=0, cache_write=0)
reported = listed = 0.0
large = 0
for m in messages:
    t = m.get('tokens', {})
    c = t.get('cache', {})
    v = dict(input=t.get('input',0), output=t.get('output',0), reasoning=t.get('reasoning',0), cache_read=c.get('read',0), cache_write=c.get('write',0))
    for k in totals:
        totals[k] += v[k]
    long = v['input'] + v['cache_read'] + v['cache_write'] > 272000
    large += int(long)
    ip,op,rp,wp = (20,75,2,25) if long else (10,50,1,12.5)
    listed += (v['input']*ip + (v['output']+v['reasoning'])*op + v['cache_read']*rp + v['cache_write']*wp)/1e6
    reported += m.get('cost',0)

folders = sorted((root.parent/'eval-recording').glob('*_'+root.name))
main = next(p for p in folders if p.name.startswith('20261028_002308_'))
clips = []
for folder in folders:
    for path in sorted(folder.glob('clip[0-9][0-9][0-9].json')):
        c = json.loads(path.read_text())
        clips.append(dict(clip_folder=folder.name, video_file=c['video'], duration_s=c['duration_s'], outcome=c['outcome'], encoder_errors=c['encoder_errors'], dropped_frames=c['dropped_frames']))
joint = [json.loads(line) for line in (root/'joint_log.jsonl').read_text().splitlines()]
start = dt.datetime.fromisoformat('2026-10-28T00:21:16-07:00')
end = dt.datetime.fromtimestamp(json.loads((root/'task_end.json').read_text())['time'], start.tzinfo)
shutil.copy(root/'final-evidence.jpg', main/'final-evidence.jpg')
metadata = {
    'eval': '16 of 18',
    'experiment': 'camera-combo eval: does more camera input improve robot manipulation',
    'task': 'Place the yellow screwdriver in the bowl.',
    'model': '~openai/gpt-astra-latest',
    'actual_harness_model': 'openrouter/openai/gpt-6-astra',
    'reasoning_effort': 'medium',
    'harness': 'opencode v2.1.4',
    'opencode_session_id': sid,
    'camera_combo': 1,
    'cameras_enabled': ['logitech','realsense','wrist'],
    'cameras_disabled': ['none'],
    'cameras_actually_in_recording': ['logitech','realsense','wrist'],
    'disabled_camera_signal_cutoff': 'Not applicable: all three evaluation cameras enabled. FaceTime was excluded by record.py.',
    'start_time': start.isoformat(),
    'end_time': end.isoformat(),
    'wall_clock_duration_s': (end-start).total_seconds(),
    'llm_calls': len(messages),
    'total_input_tokens': totals['input']+totals['cache_read']+totals['cache_write'],
    'input_tokens': totals['input'],
    'cache_read_tokens': totals['cache_read'],
    'cache_write_tokens': totals['cache_write'],
    'total_output_tokens': totals['output']+totals['reasoning'],
    'output_tokens': totals['output'],
    'reasoning_tokens': totals['reasoning'],
    'cost_usd_opencode_reported': reported,
    'cost_usd_provider_list_price': listed,
    'provider_price_table_usd_per_million_tokens': {
        'prompt_at_most_272000': {'input':10.0,'output_including_reasoning':50.0,'cache_read':1.0,'cache_write':12.5},
        'prompt_over_272000': {'input':20.0,'output_including_reasoning':75.0,'cache_read':2.0,'cache_write':25.0},
        'prompt_definition':'input + cache read + cache write',
        'calls_using_large_prompt_prices':large,
        'source':'User-provided default list price for ~openai/gpt-astra-latest'
    },
    'outcome':'success',
    'end_evidence':'Logitech top-down and wrist views show the yellow handle resting inside the bowl with the metal shaft extending toward the opposite inner rim. The open gripper has withdrawn and the screwdriver remains in the bowl. RealSense shows the bowl and a small portion of the shaft at its rim; the yellow handle is occluded by the bowl wall.',
    'evidence_file':'final-evidence.jpg',
    'budget_exceeded':len(messages)>200,
    'llm_call_budget':200,
    'recording': {
        'main_clip_folder':main.name,
        'clip_folder_names':[p.name for p in folders],
        'clips':clips,
        'recorder_start_count':2,
        'method':'Initial record.py screen capture of index.html, followed by record.py direct-camera composite via record_attempt.py because another application obscured the browser. The direct-camera composite contains all three live views for the main attempt.',
        'started_before_first_robot_movement':True
    },
    'robot': {
        'joint_order':['shoulder_pan','shoulder_lift','elbow_flex','wrist_flex','wrist_roll','gripper'],
        'units':'raw servo encoder counts (0-4095)',
        'measured_joint_positions_start':joint[0]['start'],
        'measured_joint_positions_end':joint[-1]['end'],
        'serial_port':'/dev/cu.usbserial-110',
        'serial_port_released':True,
        'final_state':'Returned near initial pose, open gripper, holding torque retained, no control process running.'
    },
    'hardware_software_problems':[
        'Chrome AppleScript JavaScript execution was disabled; used camera captures instead.',
        'Another application obscured the initial screen recording; switched to the supplied recorder direct-camera mode for an unobstructed main clip.',
        'Joint tracking offsets of several tens of encoder counts were observed, especially elbow during motion; incremental moves used measured positions. No stuck joint or control crash observed.',
        'Initial finger contact rotated the screwdriver on the table; it was then grasped and transferred successfully.',
        'First Chrome tab cleanup loop hit an invalid-index error after closing a window; reverse-index cleanup completed successfully.'
    ],
    'scripts_written':['control.py','record_attempt.py','write_metadata.py'],
    'other_artifacts':['joint_log.jsonl','task_end.json','final-evidence.jpg','opencode_session_export.json','camera snapshots'],
    'cleanup': 'Both recorder processes and their ffmpeg children stopped; start.sh app server stopped; localhost:8770 browser tabs closed; all control invocations exited. Process inspection found no remaining task processes and lsof found no serial-port owner.',
    'token_cost_snapshot_time':dt.datetime.now(start.tzinfo).isoformat(),
    'token_cost_note':'Token/cost numbers are a snapshot taken before the final reply. Every exported message with type assistant counts as one LLM call, including any incomplete current message; tokens/cost for an unfinished call may not yet be available. Output and reasoning are summed as requested.'
}
out = main/(root.name+'_eval_metadata.json')
out.write_text(json.dumps(metadata,indent=2)+'\n')
assert json.loads(out.read_text())['outcome']=='success'
print(json.dumps({'metadata_path':str(out),'llm_calls':len(messages),'cost_usd_provider_list_price':listed,'clips':clips},indent=2))
