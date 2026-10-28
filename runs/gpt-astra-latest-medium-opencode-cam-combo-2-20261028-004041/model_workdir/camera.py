import base64, json, subprocess, sys, urllib.request, time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'deps'))
import websocket
pages=json.load(urllib.request.urlopen('http://localhost:9222/json/list'))
page=next(p for p in pages if p['type']=='page')
ws=websocket.create_connection(page['webSocketDebuggerUrl'],suppress_origin=True)
counter=0
def cdp(method,params):
    global counter
    counter+=1
    ws.send(json.dumps({'id':counter,'method':method,'params':params}))
    while True:
        msg=json.loads(ws.recv())
        if msg.get('id')==counter: return msg
def js(code):
    result=cdp('Runtime.evaluate',{'expression':code,'returnByValue':True,'awaitPromise':True})
    if 'exceptionDetails' in result.get('result',{}): raise RuntimeError(result)
    return result['result']['result'].get('value')
if sys.argv[1]=='init':
    cdp('Page.addScriptToEvaluateOnNewDocument',{'source':"const originalEnumerate=navigator.mediaDevices.enumerateDevices.bind(navigator.mediaDevices);navigator.mediaDevices.enumerateDevices=async()=> (await originalEnumerate()).filter(d=>!/realsense|8086:0ad3/i.test(d.label));"})
    cdp('Page.navigate',{'url':'http://localhost:8770/'})
    time.sleep(5)
    print(js("JSON.stringify(Object.fromEntries(Object.entries(tiles).map(([k,t])=>[k,{live:!!t.stream,w:t.video.videoWidth,h:t.video.videoHeight}])))"))
elif sys.argv[1]=='disable':
    print(js("stopTile(tiles.realsense); tiles.realsense.deviceId=null; tiles.realsense.select.value=''; tiles.realsense.select.disabled=true; tiles.realsense.cfg.match=()=>false; tiles.realsense.msg.textContent='DISABLED for camera-combo 2'; JSON.stringify(Object.fromEntries(Object.entries(tiles).map(([k,t])=>[k,{live:!!t.stream,w:t.video.videoWidth,h:t.video.videoHeight}])))"))
elif sys.argv[1]=='stop':
    print(js("Object.values(tiles).forEach(stopTile); 'stopped'"))
elif sys.argv[1]=='screen':
    (HERE/'frontend.png').write_bytes(base64.b64decode(cdp('Page.captureScreenshot',{})['result']['data']))
else:
    tag=sys.argv[1]
    for key in ['logitech','wrist']:
        data=js("(()=>{const v=tiles."+key+".video;const c=document.createElement('canvas');c.width=v.videoWidth;c.height=v.videoHeight;c.getContext('2d').drawImage(v,0,0);return c.toDataURL('image/png').split(',')[1]})()")
        path=HERE/f'{tag}_{key}.png'
        path.write_bytes(base64.b64decode(data))
        print(path)
