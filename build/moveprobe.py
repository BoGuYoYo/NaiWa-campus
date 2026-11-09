import sys
sys.path.insert(0, r'C:\Users\huang\Desktop\奶娃\naiwa_campus')
from panda3d.core import loadPrcFileData
loadPrcFileData('', 'window-type offscreen'); loadPrcFileData('', 'audio-library-name null'); loadPrcFileData('', 'notify-level-display fatal')
from game import config
from game.app import NaiwaApp
class Probe:
 def __init__(self):
  o=config.parse_args(['--dev','--scene','CampusScene','--skip-intro','--offscreen','--frames','300','--seed','42']); self.a=NaiwaApp(o); self.t=0; self.a.taskMgr.add(self.tick,'probe',sort=100)
 def tick(self,task):
  self.t+=1
  s=self.a.scenes.base_scene
  if self.t==10: self.a.messenger.send('w'); print('send w',s.player._held_keys)
  if self.t==100: print('held',s.player._held_keys,'pos',s.player.motion.x,s.player.motion.y,'locked',self.a.scenes.input_locked,'phase',self.a.scenes._phase,'timer',self.a.scenes._timer,'overlays',[x[0] for x in self.a.scenes.overlays])
  if self.t==110: self.a.messenger.send('w-up'); print('send up',s.player._held_keys)
  if self.t==150: print('after',s.player.motion.x,s.player.motion.y); self.a.quit_game(); return task.done
  return task.cont
Probe().a.run()
