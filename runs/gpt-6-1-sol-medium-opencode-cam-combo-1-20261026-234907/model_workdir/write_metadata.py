import json, datetime as dt, subprocess, shutil
from pathlib import Path

here=Path(__file__).resolve().parent
state=json.loads((here/'state.json').read_text())
export=json.loads((here/'opencode_session_export.json').read_text())
messages=[m for m in export['messages'] if m.get('type')=='assistant']
clipdir=Path(state['clip_folder'])
clip=json.loads((clipdir/'clip001.json').read_text())
totals=dict(input=0,output=0,reasoning=0,cache_read=0,cache_write=0)
reported=0; listed=0; long_calls=0
for m in messages:
    t=m.get('tokens',{}); cache=t.get('cache',{})
    i=t.get('input',0); o=t.get('output',0); r=t.get('reasoning',0)
    cr=cache.get('read',0); cw=cache.get('write',0)
    for k,v in zip(totals,(i,o,r,cr,cw)):totals[k]+=v
    long=i+cr+cw>272000
    long_calls+=int(long)
    prices=(4,15,.2,5) if long else (2,10,.1,2.5)
    listed+=(i*prices[0]+(o+r)*prices[1]+cr*prices[2]+cw*prices[3])/1e6
    reported+=m.get('cost',0)
start=dt.datetime.strptime(here.name[-15:],'%Y%m%d-%H%M%S')
end=dt.datetime.fromisoformat(state['end_time'])
video_info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration,size','-of','json',str(clipdir/'clip001.mp4')]))
for cam in ('logitech','wrist','realsense'):
    shutil.copy2(here/f'final_{cam}.jpg',clipdir/f'final_{cam}.jpg')
metadata={
    'eval':'07 of 09',
    'experiment':'camera-combo eval: does more camera input improve robot manipulation',
    'task':'Place the yellow screwdriver in the bowl.',
    'model':'openai/gpt-6.1-sol','reasoning_effort':'medium',
    'harness':'opencode v2.1.4','opencode_session_id':export['info']['id'],
    'camera_combo':1,'cameras_enabled':['logitech','realsense','wrist'],
    'cameras_disabled':['none'],
    'cameras_actually_in_recording':['logitech','realsense','wrist'],
    'disabled_camera_cutoff':'Not applicable: all three designated cameras enabled; FaceTime excluded by record.py device filter.',
    'start_time':start.astimezone().isoformat(),
    'end_time':end.astimezone().isoformat(),
    'wall_clock_duration_s':(end-start).total_seconds(),
    'timing_note':'Start is attempt-directory creation; end is task/recording stop. Setup included. Metadata preparation follows task end.',
    'llm_calls':len(messages),
    'total_input_tokens':totals['input']+totals['cache_read']+totals['cache_write'],
    'input_tokens':totals['input'],'cache_read_tokens':totals['cache_read'],'cache_write_tokens':totals['cache_write'],
    'total_output_tokens':totals['output']+totals['reasoning'],
    'output_tokens':totals['output'],'reasoning_tokens':totals['reasoning'],
    'cost_usd_opencode_reported':reported,'cost_usd_provider_list_price':listed,
    'price_table_usd_per_million_tokens':{
        'prompt_tokens_at_most_272000':{'input':2,'output_including_reasoning':10,'cache_read':.1,'cache_write':2.5},
        'prompt_tokens_over_272000':{'input':4,'output_including_reasoning':15,'cache_read':.2,'cache_write':5},
        'prompt_definition':'input + cache read + cache write','long_prompt_calls':long_calls,
        'source':'Default provider list-price table supplied in evaluation instructions.'},
    'outcome':'success',
    'evidence':'Wrist released image shows entire yellow screwdriver resting inside bowl with empty open jaws. Final Logitech top-down image shows yellow handle and metal shaft fully within bowl after arm returns home. RealSense confirms lift and release; final interior obscured by bowl wall.',
    'budget_exceeded':len(messages)>200,'llm_call_budget':200,
    'recording':{
        'clip_folders':[clipdir.name],'main_attempt_clip_folder':clipdir.name,
        'video_files':['clip001.mp4'],'clip_durations_s':[float(video_info['format']['duration'])],
        'recorder_started_count':state['recorder_starts'],
        'recording_start_time':clip['start_wall_time'],'recording_end_time':clip['end_wall_time'],
        'recording_wall_clock_duration_s':(dt.datetime.fromisoformat(clip['end_wall_time'])-dt.datetime.fromisoformat(clip['start_wall_time'])).total_seconds(),
        'source':'Supplied record.py Recorder, FFmpegSource, render and Clip classes imported by control.py; direct composite of the same three frontend cameras.',
        'resolution':[1920,1080],'fps':20,'encoder_errors':clip['encoder_errors'],
        'dropped_frames':clip['dropped_frames'],
        'timing_issue':'Custom recording loop slept after rendering rather than scheduling fixed-rate ticks. All manipulation was captured, but nominal-20fps video is 468.05 seconds versus about 541 seconds wall time (approximately 1.16x playback). Per-frame wall-clock timestamps retained in clip001_frames.csv.'},
    'robot':{
        'joint_order':['shoulder_pan','shoulder_lift','elbow_flex','wrist_flex','wrist_roll','gripper'],
        'position_units':'raw 12-bit servo ticks',
        'measured_start_positions':state['initial_positions'],
        'measured_end_positions':state['final_positions'],
        'serial_port':'/dev/cu.usbserial-110','serial_released':True,
        'shutdown':'Control process exited, bus disconnected. Torque left holding home pose to avoid an uncontrolled drop. App server terminated and frontend Chrome tab closed.'},
    'hardware_software_problems':[
        'First grasp at insufficient depth rotated the handle but failed the lift check. Reopened, lowered farther, and second grasp lifted successfully.',
        'Modest servo tracking offsets, especially elbow (up to roughly 50 ticks) and shoulder under load. No stuck joint, serial timeout, camera dropout, or crash observed.',
        'Gripper measured about 2452 ticks against the handle despite 2650-tick close command, consistent with object contact.',
        'Recording time-base issue described under recording.timing_issue.'
    ],
    'scripts_written':['control.py','write_metadata.py'],
    'other_artifacts':['moves.jsonl','state.json','control.log','opencode_session_export.json','camera snapshots'],
    'usage_snapshot_note':'Token, cost and LLM-call values are a session-export snapshot taken before the final reply; excludes this metadata-writing tool call and subsequent final response as applicable.',
    'metadata_written_at':dt.datetime.now().astimezone().isoformat()
}
path=clipdir/(here.name+'_eval_metadata.json')
path.write_text(json.dumps(metadata,indent=2)+'\n')
print(json.dumps({'metadata':str(path),'llm_calls':len(messages),'provider_cost':listed,'reported_cost':reported,'video_duration_s':video_info['format']['duration']}))
