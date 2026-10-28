import argparse, importlib.util, json, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('nexbus', '/Users/dylanler/github/lerobot-nexarm/src/lerobot/motors/nexarm/nexarm.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
p = argparse.ArgumentParser()
p.add_argument('action', choices=['read', 'move'])
p.add_argument('positions', nargs='*', type=int)
p.add_argument('--seconds', type=float, default=3)
a = p.parse_args()
b = m.NexArmMotorsBus('/dev/cu.usbserial-110')
b.connect()
try:
    b.enter_lerobot_mode()
    start = b.read_positions()
    if a.action == 'move':
        assert len(a.positions) == 6
        assert all(400 <= x <= 3600 for x in a.positions)
        assert max(abs(x-y) for x,y in zip(start,a.positions)) <= 1200
        b.write_motion_params(30, 350)
        b.set_torque(True)
        n = max(1, int(a.seconds * 30))
        for k in range(1,n+1):
            u=k/n; u=u*u*(3-2*u)
            b.write_positions([round(s+(t-s)*u) for s,t in zip(start,a.positions)])
            time.sleep(a.seconds/n)
        time.sleep(.5)
    end=b.read_positions()
    result={'time':time.time(),'action':a.action,'start':start,'target':a.positions,'end':end}
    print(json.dumps(result))
    with (HERE/'joint_log.jsonl').open('a') as f: f.write(json.dumps(result)+'\n')
finally:
    b.disconnect()
