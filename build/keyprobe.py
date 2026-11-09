from direct.showbase.ShowBase import ShowBase
from panda3d.core import loadPrcFileData
import time
loadPrcFileData('', 'window-title KeyProbe')
class App(ShowBase):
 def __init__(self):
  ShowBase.__init__(self); self.events=[]
  for e in ('w','w-up','d','d-up'):
   self.accept(e, lambda ev=e: (self.events.append(ev), print('EVENT', ev, flush=True)))
  self.taskMgr.doMethodLater(5, self.done, 'done')
 def done(self,t): print('EVENTS',self.events, flush=True); self.userExit(); return t.done
App().run()
