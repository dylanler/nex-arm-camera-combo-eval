import sys, time, json, threading, importlib.util, argparse, contextlib
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import cv2

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
recmod = load('record', ROOT / 'record.py')
motor = load('motor', '/Users/dylanler/github/lerobot-nexarm/src/lerobot/motors/nexarm/nexarm.py')
args = argparse.Namespace(task=HERE.name, out=str(ROOT/'eval-recording'), source='cameras',
    canvas='1920x1080', fps=20, cam_fps=30, cam_size='640x480', layout='grid',
    color='normal', no_timestamp=False, codec='x264', crf=20, bitrate='12M',
    save_raw=False, wrist=None, realsense=None, logitech=None)
rec = recmod.Recorder(args)
bus = motor.NexArmMotorsBus('/dev/cu.usbserial-110')
bus.connect()
bus.enter_lerobot_mode()
initial = bus.read_positions()
state = {'start_time': recmod.now_iso(), 'initial_positions':initial, 'recorder_starts':0}
(HERE/'state.json').write_text(json.dumps(state,indent=2))
lock=threading.RLock()
running=True

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        global running
        try:
            data=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))) or '{}')
            with contextlib.nullcontext():
                if self.path=='/snapshot':
                    files={}
                    for s in rec.sources:
                        img, stamp, count=s.latest()
                        if img is not None:
                            p=HERE/(data.get('name','view')+'_'+s.key+'.jpg')
                            cv2.imwrite(str(p),img)
                            files[s.key]={'path':str(p),'age_s':time.perf_counter()-stamp,'frame':count}
                    result=files
                elif self.path=='/positions':
                    result=bus.read_positions()
                elif self.path=='/start':
                    if rec.state=='idle':
                        with lock: rec.start_clip()
                        state['recorder_starts']+=1
                        state['clip_folder']=str(rec.session_dir)
                        (HERE/'state.json').write_text(json.dumps(state,indent=2))
                    result={'recording':rec.state,'folder':str(rec.session_dir)}
                elif self.path=='/move':
                    assert rec.state=='recording', 'Recording must be active'
                    start=bus.read_positions(); target=data['positions']; duration=data.get('duration',2)
                    assert len(target)==6 and all(500<=v<=3500 for v in target)
                    assert duration>=max(abs(a-b) for a,b in zip(start,target))/500
                    bus.write_motion_params(30,400)
                    bus.set_torque(True)
                    for i in range(1,int(duration*30)+1):
                        f=i/int(duration*30); f=f*f*(3-2*f)
                        bus.write_positions([round(a+(b-a)*f) for a,b in zip(start,target)])
                        time.sleep(1/30)
                    time.sleep(.5)
                    result={'target':target,'measured':bus.read_positions()}
                    with (HERE/'moves.jsonl').open('a') as f:
                        f.write(json.dumps({'time':recmod.now_iso(),**result})+'\n')
                elif self.path=='/stop':
                    state['final_positions']=bus.read_positions()
                    state['end_time']=recmod.now_iso()
                    state['outcome']=data.get('outcome','fail')
                    with lock: rec.finish_clip(state['outcome'])
                    (HERE/'state.json').write_text(json.dumps(state,indent=2))
                    running=False
                    result=state
                else:
                    raise ValueError(self.path)
            body=json.dumps(result).encode(); self.send_response(200)
        except Exception as e:
            body=json.dumps({'error':str(e)}).encode(); self.send_response(500)
        self.end_headers(); self.wfile.write(body)
    def log_message(self,*a): pass

server=ThreadingHTTPServer(('127.0.0.1',8771),Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
try:
    rec.build_sources()
    for s in rec.sources:s.start()
    print(json.dumps({'ready':True,'positions':initial}),flush=True)
    last=time.perf_counter()
    while running:
        with lock:
            if rec.sources:
                composite,raws,info=rec.render()
                if rec.clip:
                    elapsed=time.perf_counter()-last
                    rec.clip.write(composite,raws,info,max(1,min(20,round(elapsed*rec.fps))))
            last=time.perf_counter()
        time.sleep(1/rec.fps)
finally:
    rec.finish_clip(quiet=True)
    for s in rec.sources:s.stop()
    bus.disconnect()
    server.shutdown();server.server_close()
