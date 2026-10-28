import datetime as dt
import json
from pathlib import Path
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
session=json.loads((HERE/'opencode_session_export.json').read_text())
messages=[m for m in session['messages'] if m.get('type')=='assistant']
totals=dict(input=0,output=0,reasoning=0,cache_read=0,cache_write=0)
reported=0
priced=0
prices={'default':{'input':10,'output_including_reasoning':50,'cache_read':1,'cache_write':12.5},'prompt_over_272000':{'input':20,'output_including_reasoning':75,'cache_read':2,'cache_write':25}}
for m in messages:
    t=m.get('tokens',{})
    parts={k:t.get(k,0) for k in ['input','output','reasoning']}
    parts.update(cache_read=t.get('cache',{}).get('read',0),cache_write=t.get('cache',{}).get('write',0))
    for k,v in parts.items(): totals[k]+=v
    reported+=m.get('cost',0)
    price=prices['prompt_over_272000' if parts['input']+parts['cache_read']+parts['cache_write']>272000 else 'default']
    priced+=(parts['input']*price['input']+(parts['output']+parts['reasoning'])*price['output_including_reasoning']+parts['cache_read']*price['cache_read']+parts['cache_write']*price['cache_write'])/1e6
folders=sorted((ROOT/'eval-recording').glob('*'+HERE.name+'*'))
main=next(p for p in folders if p.name.endswith(HERE.name))
clips=[]
for folder in folders:
    for p in folder.glob('clip[0-9][0-9][0-9].json'):
        c=json.loads(p.read_text())
        clips.append({'folder':folder.name,'video':c['video'],'duration_seconds':c['duration_s'],'start':c['start_wall_time'],'end':c['end_wall_time'],'source':'direct enabled cameras final-state evidence' if folder!=main else 'screen capture of frontend; stalled/frozen during attempt'})
logs=[json.loads(l) for l in (HERE/'joint_log.jsonl').read_text().splitlines()]
start=dt.datetime.fromtimestamp(session['info']['time']['created']/1000).astimezone()
end=dt.datetime.now().astimezone()
for name in ['final_logitech.png','final_wrist.png','released_wrist.png']:
    shutil.copy2(HERE/name,main/name)
metadata={
 'eval':'17 of 18','experiment':'camera-combo eval: does more camera input improve robot manipulation','task':'Place the yellow screwdriver in the bowl.',
 'model':'~openai/gpt-astra-latest','reasoning_effort':'medium','harness':subprocess.check_output(['/Users/dylanler/.opencode/bin/opencode','--version'],text=True).strip(),'opencode_session_id':session['info']['id'],'export_model':session['info']['model'],
 'camera_combo':2,'cameras_enabled':['logitech','wrist'],'cameras_disabled':['realsense'],
 'cameras_actually_in_recording':{'main':['logitech','wrist'],'final_evidence':['logitech','wrist'],'disabled_tile':'RealSense black, no live imagery'},
 'disabled_camera_cutoff':'Before any robot movement or recording, stopped RealSense MediaStream tracks, cleared video.srcObject and deviceId, disabled selector, and replaced match function with false through Chrome DevTools. App initially auto-opened all cameras; no RealSense images were viewed or used. Final direct recording used --realsense DISABLED_NO_MATCH, preventing that device from being opened.',
 'start_time':start.isoformat(),'end_time':end.isoformat(),'wall_clock_duration_seconds':(end-start).total_seconds(),'robot_task_end_time':dt.datetime.fromtimestamp(logs[-1]['time']).astimezone().isoformat(),'metadata_time':dt.datetime.now().astimezone().isoformat(),
 'llm_calls':len(messages),'tokens':totals,'total_input_tokens':totals['input']+totals['cache_read']+totals['cache_write'],'total_output_tokens':totals['output']+totals['reasoning'],
 'cost_usd_opencode_reported':reported,'cost_usd_provider_list_price':priced,'price_table_usd_per_million_tokens':prices,'price_threshold_prompt_tokens':272000,
 'outcome':'success','outcome_evidence':'Final Logitech still and wrist still show the yellow handle resting on the inside bottom of the bowl, with its metal shaft leaning toward the inner rim; gripper is empty and withdrawn. Second grasp succeeded after first attempt missed. Main screen video suffered frozen/stalled capture; additional direct-camera clip documents final state.',
 'budget_200_calls_exceeded':len(messages)>200,
 'recording':{'clip_folders':[p.name for p in folders],'main_attempt_folder':main.name,'clips':clips,'recorder_start_count':2,'main_attempt_recording_problem':'Screen capture began before motion but later showed STALLED; camera snapshots used for control remained live. Early sampled video frame shows frontend with wrist and Logitech and black RealSense tile. Full motion capture is not reliable.'},
 'robot':{'joint_order':['shoulder_pan','shoulder_lift','elbow_flex','wrist_flex','wrist_roll','gripper'],'units':'raw servo counts (4096 per revolution)','measured_start':logs[0]['start'],'measured_end':logs[-1]['end'],'serial_port':'/dev/cu.usbserial-110','serial_released':True,'torque':'left enabled to hold final resting pose; all serial connections closed'},
 'problems':['Chrome AppleScript JavaScript disabled and macOS accessibility access unavailable; used an isolated Chrome DevTools connection instead.','Initial attempt to filter camera enumeration did not prevent auto-opening RealSense; explicitly stopped its tracks before observation and recording.','First grasp closed above handle and missed; lower second approach achieved contact at gripper count about 2400.','Joint tracking offsets up to approximately 46 counts observed; no stuck joint or serial communication failure.','Main screen capture became frozen/stalled; direct camera final-state recording added.'],
 'scripts_written':['control.py','camera.py','metadata.py'],'artifacts_directory':str(HERE),
 'cleanup':'Recorder(s), dedicated Chrome browser, frontend server and all robot-control commands stopped; serial port verified unclaimed.',
 'token_cost_snapshot_note':'Token/cost numbers are a snapshot taken before the final reply. Assistant messages without completed usage are counted as calls but contribute zero unavailable tokens/cost.'
}
path=main/(HERE.name+'_eval_metadata.json')
path.write_text(json.dumps(metadata,indent=2)+'\n')
print(json.dumps({'metadata':str(path),'calls':len(messages),'reported_cost':reported,'provider_price_cost':priced,'recordings':clips},indent=2))
