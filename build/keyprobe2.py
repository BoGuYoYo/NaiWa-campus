from direct.showbase.ShowBase import ShowBase
from panda3d.core import loadPrcFileData
import ctypes
loadPrcFileData('', 'window-title KeyProbe2')
class App(ShowBase):
 def __init__(self):
  ShowBase.__init__(self); self.events=[]
  for e in ('w','w-up','d','d-up'):
   self.accept(e, lambda ev=e: (self.events.append(ev), print('EVENT', ev, flush=True)))
  self.taskMgr.doMethodLater(1, self.send, 'send')
  self.taskMgr.doMethodLater(4, self.done, 'done')
 def send(self,t):
  u=ctypes.windll.user32; h=u.FindWindowW(None,'KeyProbe2'); u.SetForegroundWindow(h); u.keybd_event(0x57,0,0,0); u.keybd_event(0x57,0,2,0); return t.done
 def done(self,t): print('EVENTS',self.events, flush=True); self.userExit(); return t.done
App().run()
