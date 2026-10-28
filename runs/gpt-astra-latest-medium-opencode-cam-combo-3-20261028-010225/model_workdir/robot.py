import importlib.util, json, sys, time
from pathlib import Path
HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('nexbus', '/Users/dylanler/github/lerobot-nexarm/src/lerobot/motors/nexarm/nexarm.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
bus = mod.NexArmMotorsBus('/dev/cu.usbserial-110')
bus.connect()
try:
    bus.enter_lerobot_mode()
    start = bus.read_positions()
    if len(sys.argv)>1:
        target = json.loads(sys.argv[1])
        seconds = float(sys.argv[2]) if len(sys.argv)>2 else 3
        assert len(target)==6 and all(100 < p < 4000 for p in target)
        bus.write_motion_params(20, 350)
        bus.set_torque(True)
        for step in range(1, int(seconds*30)+1):
            a=step/int(seconds*30); a=a*a*(3-2*a)
            bus.write_positions([round(s+(t-s)*a) for s,t in zip(start,target)])
            time.sleep(1/30)
        time.sleep(.6)
    end=bus.read_positions()
    entry={'time':time.time(),'start':start,'end':end,'target':json.loads(sys.argv[1]) if len(sys.argv)>1 else None}
    with (HERE/'robot_log.jsonl').open('a') as f: f.write(json.dumps(entry)+'\n')
    print(json.dumps(entry))
finally:
    bus.disconnect()
