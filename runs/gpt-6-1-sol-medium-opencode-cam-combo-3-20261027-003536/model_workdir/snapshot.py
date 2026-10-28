import base64, subprocess, sys
from pathlib import Path
js = "JSON.stringify({status:document.getElementById('status').textContent,streams:Object.fromEntries(Object.entries(tiles).map(([k,t])=>[k,!!t.stream])),image:(()=>{let v=tiles.wrist.video;let c=document.createElement('canvas');c.width=v.videoWidth;c.height=v.videoHeight;c.getContext('2d').drawImage(v,0,0);return c.toDataURL('image/png').split(',')[1]})()})"
osa = 'tell application "Google Chrome" to execute active tab of front window javascript '+ '"'+js.replace('\\','\\\\').replace('"','\\"')+'"'
r=subprocess.run(['osascript','-e',osa],capture_output=True,text=True,check=True)
import json
d=json.loads(r.stdout)
Path(sys.argv[1]).write_bytes(base64.b64decode(d.pop('image')))
print(d)
