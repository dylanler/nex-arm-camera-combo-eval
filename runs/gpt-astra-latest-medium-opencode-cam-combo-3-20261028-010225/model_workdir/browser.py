import subprocess, json, sys, base64
from pathlib import Path
HERE = Path(__file__).parent
def js(code):
    script = 'tell application "Google Chrome" to execute active tab of front window javascript ' + json.dumps(code)
    p = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
    if p.returncode: raise RuntimeError(p.stderr)
    return p.stdout.strip()
if __name__ == '__main__':
    if sys.argv[1] == 'snap':
        data = js('(()=>{const v=tiles.wrist.video;const c=document.createElement("canvas");c.width=v.videoWidth;c.height=v.videoHeight;c.getContext("2d").drawImage(v,0,0);return c.toDataURL("image/png").split(",")[1]})()')
        path = HERE / (sys.argv[2] if len(sys.argv)>2 else 'wrist.png')
        path.write_bytes(base64.b64decode(data))
        print(path)
    else:
        print(js(sys.argv[1]))
