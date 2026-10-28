import importlib.util
import json
import sys
import time

spec = importlib.util.spec_from_file_location('nexarm', '/Users/dylanler/github/lerobot-nexarm/src/lerobot/motors/nexarm/nexarm.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
bus = module.NexArmMotorsBus('/dev/cu.usbserial-110')
try:
    bus.connect()
    bus.enter_lerobot_mode()
    current = bus.read_positions()
    print('start', json.dumps(current), flush=True)
    if len(sys.argv) > 1:
        target = json.loads(sys.argv[1])
        duration = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
        bus.write_motion_params(50, 300)
        bus.set_torque(True)
        steps = int(duration * 20)
        for i in range(1, steps + 1):
            pose = [round(a + (b-a)*i/steps) for a, b in zip(current, target)]
            bus.write_positions(pose)
            time.sleep(0.05)
        time.sleep(0.5)
        print('end', json.dumps(bus.read_positions()), flush=True)
finally:
    bus.exit_lerobot_mode()
    bus.disconnect()
