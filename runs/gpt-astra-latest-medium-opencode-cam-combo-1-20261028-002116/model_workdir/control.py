import importlib.util, json, time, sys
from pathlib import Path
ROOT = Path(__file__).parent
spec = importlib.util.spec_from_file_location('nexbus', '/Users/dylanler/github/lerobot-nexarm/src/lerobot/motors/nexarm/nexarm.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
bus = mod.NexArmMotorsBus('/dev/cu.usbserial-110')
try:
    bus.connect()
    bus.enter_lerobot_mode()
    start = bus.read_positions()
    print('start', start, flush=True)
    target = json.loads(sys.argv[1]) if len(sys.argv)>1 else None
    if target:
        target = [start[i] if v is None else int(v) for i,v in enumerate(target)]
        assert len(target)==6 and all(500<v<3500 for v in target)
        duration = max(float(sys.argv[2]) if len(sys.argv)>2 else 3, max(abs(a-b) for a,b in zip(start,target))/180)
        bus.write_motion_params(30, 500)
        bus.write_positions(start)
        bus.set_torque(True)
        n = int(duration*30)
        for k in range(1,n+1):
            t = k/n
            t = t*t*(3-2*t)
            bus.write_positions([round(a+(b-a)*t) for a,b in zip(start,target)])
            time.sleep(duration/n)
        time.sleep(.7)
    end = bus.read_positions()
    print('end', end, flush=True)
    with (ROOT/'joint_log.jsonl').open('a') as f:
        f.write(json.dumps({'time':time.time(),'start':start,'target':target,'end':end})+'\n')
finally:
    bus.disconnect()
