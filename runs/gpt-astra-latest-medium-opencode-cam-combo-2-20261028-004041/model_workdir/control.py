import argparse, importlib.util, json, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('nexbus', '/Users/dylanler/github/lerobot-nexarm/src/lerobot/motors/nexarm/nexarm.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
p = argparse.ArgumentParser()
p.add_argument('positions', nargs='*', type=int)
p.add_argument('--seconds', type=float, default=3)
a = p.parse_args()
bus = mod.NexArmMotorsBus('/dev/cu.usbserial-110')
bus.connect()
try:
    bus.enter_lerobot_mode()
    start = bus.read_positions()
    if a.positions:
        assert len(a.positions) == 6
        assert all(500 <= v <= 3500 for v in a.positions)
        bus.write_motion_params(20, 300)
        bus.set_torque(True)
        steps = max(1, int(a.seconds * 30))
        for i in range(1, steps + 1):
            t = i / steps
            f = t*t*(3-2*t)
            bus.write_positions([round(x+(y-x)*f) for x,y in zip(start,a.positions)])
            time.sleep(a.seconds/steps)
        time.sleep(0.6)
    end = bus.read_positions()
    event = {'time':time.time(),'start':start,'target':a.positions,'end':end}
    with (HERE/'joint_log.jsonl').open('a') as out: out.write(json.dumps(event)+'\n')
    print(json.dumps(event))
finally:
    bus.disconnect()
