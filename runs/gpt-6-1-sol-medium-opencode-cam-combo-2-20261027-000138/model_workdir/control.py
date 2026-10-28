import argparse, base64, importlib.util, json, pathlib, subprocess, time

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('nexbus', '/Users/dylanler/github/lerobot-nexarm/src/lerobot/motors/nexarm/nexarm.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def js(code):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b=p.chromium.connect_over_cdp('http://localhost:9222')
        page=b.contexts[0].pages[0]
        result=page.evaluate(code)
        b.close()
        return result

def snap(label):
    for key in ['logitech', 'wrist']:
        data = js(f'(()=>{{const v=tiles.{key}.video; const c=document.createElement("canvas"); c.width=v.videoWidth;c.height=v.videoHeight;c.getContext("2d").drawImage(v,0,0);return c.toDataURL("image/png").split(",")[1]}})()')
        (HERE/f'{label}_{key}.png').write_bytes(base64.b64decode(data))

def robot(target=None, duration=3):
    bus=mod.NexArmMotorsBus('/dev/cu.usbserial-110')
    bus.connect()
    try:
        bus.enter_lerobot_mode()
        start=bus.read_positions()
        if target:
            assert len(target)==6 and all(500<x<3500 for x in target)
            assert max(abs(a-b) for a,b in zip(start,target))<1000, 'Split large motion'
            bus.write_motion_params(40,400)
            bus.set_torque(True)
            n=max(1,int(duration*30))
            for i in range(1,n+1):
                u=i/n; u=u*u*(3-2*u)
                bus.write_positions([round(a+(b-a)*u) for a,b in zip(start,target)])
                time.sleep(duration/n)
            time.sleep(.5)
        end=bus.read_positions()
        entry={'time':time.time(),'start':start,'target':target,'end':end}
        with (HERE/'joint_log.jsonl').open('a') as f:f.write(json.dumps(entry)+'\n')
        print(json.dumps(entry))
    finally: bus.disconnect()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command');p.add_argument('values',nargs='*');p.add_argument('--duration',type=float,default=3);a=p.parse_args()
    if a.command=='snap':snap(a.values[0])
    elif a.command=='js':print(js(a.values[0]))
    elif a.command=='read':robot()
    elif a.command=='move':robot(list(map(int,a.values)),a.duration)
