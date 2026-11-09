import sys
sys.path.insert(0, r'C:\Users\huang\Desktop\奶娃\naiwa_campus')
from panda3d.core import loadPrcFileData
loadPrcFileData('', 'window-type offscreen'); loadPrcFileData('', 'audio-library-name null'); loadPrcFileData('', 'notify-level-display fatal')
from game import config
from game.app import NaiwaApp
class Probe:
 def __init__(self):
  o=config.parse_args(['--dev','--scene','CampusScene','--skip-intro','--offscreen','--frames','10000','--seed','42']); self.a=NaiwaApp(o); self.t=0; self.sent=False; self.a.taskMgr.add(self.tick,'probe',sort=100)
 def tick(self,task):
  self.t+=1; s=self.a.scenes.base_scene
  if not self.sent and not self.a.scenes.input_locked:
   self.sent=True; p=s.player; print('idle',self.t,'scene',type(s), 'player',p, 'sceneid',s.scene_id,'locked',self.a.scenes.input_locked); p.set_key_state('w',True); print('read',p.read_input());
   for i in range(10): p.update(1/60,locked=False)
   print('direct pos',p.motion.x,p.motion.y,'state',p.state.world.x,p.state.world.y,'read',p.read_input()); p.set_key_state('w',False); self.a.quit_game(); return task.done
  return task.cont
Probe().a.run()
