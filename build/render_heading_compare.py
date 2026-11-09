import sys
from pathlib import Path
sys.path.insert(0, r'C:\Users\huang\Desktop\奶娃\naiwa_campus')
from panda3d.core import loadPrcFileData
loadPrcFileData('', 'window-type offscreen'); loadPrcFileData('', 'audio-library-name null'); loadPrcFileData('', 'notify-level-display fatal')
from game import config
from game.app import NaiwaApp
from game.world import player_controller

def run(name, rotate):
 if not rotate:
  player_controller.FACING_HEADING = {k: 0.0 for k in player_controller.FACING_HEADING}
 o=config.parse_args(['--dev','--scene','CampusScene','--skip-intro','--offscreen','--frames','1000','--seed','42'])
 a=NaiwaApp(o); ticks=0
 def task(t):
  nonlocal ticks
  ticks += 1
  s=a.scenes.base_scene
  if ticks == 100:
   s.player.set_key_state('d', True)
  if ticks == 140:
   s.player.set_key_state('d', False)
   a.pipeline.save_buffer_screenshot(str(Path('reports/review') / f'{name}.png'))
   a.quit_game(); return t.done
  return t.cont
 a.taskMgr.add(task, 'compare', sort=100)
 a.run()
run('heading_current', True)
run('heading_zero', False)
