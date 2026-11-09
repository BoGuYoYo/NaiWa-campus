import sys
sys.path.insert(0, r'C:\Users\huang\Desktop\奶娃\naiwa_campus')
from panda3d.core import loadPrcFileData
loadPrcFileData('', 'window-type offscreen'); loadPrcFileData('', 'audio-library-name null'); loadPrcFileData('', 'notify-level-display fatal')
from game import config
from game.app import NaiwaApp
class Probe:
 def __init__(self):
  o=config.parse_args(['--dev','--scene','CampusScene','--skip-intro','--offscreen','--frames','10000','--seed','42']); self.a=NaiwaApp(o); self.t=0; self.sent=False; self.sent_at=0; self.a.taskMgr.add(self.tick,'probe',sort=100)
 def tick(self,task):
  self.t+=1; s=self.a.scenes.base_scene
  if not self.sent and not self.a.scenes.input_locked:
   self.sent=True; self.sent_at=self.t; print('idle at',self.t,'phase',self.a.scenes._phase); self.a.messenger.send('w'); print('down',s.player._held_keys)
  if self.sent and self.t%20==0: print('pos',s.player.motion.x,s.player.motion.y,'held',s.player._held_keys,'locked',self.a.scenes.input_locked)
  if self.sent and self.t-self.sent_at>80:
   self.a.messenger.send('w-up'); print('final',s.player.motion.x,s.player.motion.y); self.a.quit_game(); return task.done
  return task.cont
Probe().a.run()
