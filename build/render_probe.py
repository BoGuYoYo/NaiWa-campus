import sys
from pathlib import Path
sys.path.insert(0, r'C:\Users\huang\Desktop\奶娃\naiwa_campus')
from panda3d.core import loadPrcFileData
loadPrcFileData('', 'window-type offscreen'); loadPrcFileData('', 'audio-library-name null'); loadPrcFileData('', 'notify-level-display fatal')
from game import config
from game.app import NaiwaApp
o=config.parse_args(['--dev','--scene','CampusScene','--skip-intro','--offscreen','--frames','1000','--seed','42'])
a=NaiwaApp(o); ticks=0
def task(t):
 global ticks
 ticks += 1; s=a.scenes.base_scene
 if ticks == 100:
  print('at100',a.scenes.input_locked,s.player.motion.facing,s.animator._row,s.animator._asset_id)
  s.player.set_key_state('d', True)
 if ticks == 140:
  print('at140',a.scenes.input_locked,s.player.motion.facing,s.animator._row,s.animator._asset_id,s.player.motion.x,s.player.motion.y)
  s.player.set_key_state('d', False)
 if ticks == 150:
  print('at150',a.scenes.input_locked,s.player.motion.facing,s.animator._row,s.animator._asset_id,s.player.motion.x,s.player.motion.y)
  a.pipeline.save_buffer_screenshot(str(Path('reports/review') / 'render_probe.png')); a.quit_game(); return t.done
 return t.cont
a.taskMgr.add(task, 'probe', sort=100); a.run()
