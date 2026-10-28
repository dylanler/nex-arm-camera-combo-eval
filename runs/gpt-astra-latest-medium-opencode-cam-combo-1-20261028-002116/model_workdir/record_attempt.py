import importlib.util, sys, time
from pathlib import Path
import cv2
ROOT=Path(__file__).parent
spec=importlib.util.spec_from_file_location('rec','/Users/dylanler/github/nex-arm-3-cam-eval/record.py')
rec=importlib.util.module_from_spec(spec)
spec.loader.exec_module(rec)
original=rec.Recorder.render
def render(self):
    result=original(self)
    if time.time()-getattr(self,'last_saved',0)>.5:
        self.last_saved=time.time()
        for key,frame in result[1].items():
            if frame is not None:
                cv2.imwrite(str(ROOT/(key+'.jpg')),frame)
        cv2.imwrite(str(ROOT/'composite.jpg'),result[0])
    if (ROOT/'finish_success').exists():
        self.finish_clip('success')
        self.running=False
    return result
rec.Recorder.render=render
sys.argv=['record.py','--task',ROOT.name,'--out','/Users/dylanler/github/nex-arm-3-cam-eval/eval-recording','--no-preview','--fps','15']
rec.main()
