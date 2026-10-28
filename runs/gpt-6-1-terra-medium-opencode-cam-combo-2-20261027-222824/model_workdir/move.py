import importlib.util
import json
import sys
import time
from pathlib import Path

path = '/Users/dylanler/github/lerobot-nexarm/src/lerobot/motors/nexarm/nexarm.py'
spec = importlib.util.spec_from_file_location('nexarm_bus', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
bus = module.NexArmMotorsBus('/dev/cu.usbserial-110')
log = Path(__file__).with_name('moves.jsonl')
bus.connect()
try:
    bus.enter_lerobot_mode()
    before = bus.read_positions()
    if len(sys.argv) == 1:
        print(json.dumps({'positions': before}), flush=True)
    else:
        delta = [int(v) for v in sys.argv[1:7]]
        if len(delta) != 6 or max(abs(v) for v in delta) > 300:
            raise ValueError('Six deltas required, each at most 300')
        target = [a+b for a,b in zip(before, delta)]
        if min(target) < 700 or max(target) > 3400:
            raise ValueError('Target out of conservative range')
        bus.write_motion_params(100, 600)
        bus.write_positions(before)
        bus.set_torque(True)
        for n in range(1, 31):
            bus.write_positions([round(a+(b-a)*n/30) for a,b in zip(before,target)])
            time.sleep(0.05)
        time.sleep(0.6)
        after = bus.read_positions()
        record = {'time': time.time(), 'before': before, 'target':target, 'after':after}
        with log.open('a') as f: f.write(json.dumps(record)+'\n')
        print(json.dumps(record), flush=True)
finally:
    bus.exit_lerobot_mode()
    bus.disconnect()
