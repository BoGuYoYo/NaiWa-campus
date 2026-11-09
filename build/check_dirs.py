import sys
sys.path.insert(0, r'C:\\Users\\huang\\Desktop\\奶娃\\naiwa_campus')
from pathlib import Path
from game.world.map_data import MapData
from game.world.player_controller import PlayerController
from tests.world.fixtures.fake_state import FakeState
class N:
 def setPos(self,*x): pass
 def setH(self,*x): pass
md=MapData.from_content_root(Path('content'))
for keys in [('w',),('d',),('s',),('a',),('w','d'),('w','a'),('s','d'),('s','a')]:
 s=FakeState(); c=PlayerController(md,s,N(),key_down=lambda _k:False)
 for k in keys: c.set_key_state(k,True)
 for _ in range(30): c.update(1/60,locked=False)
 print(keys,c.motion.facing,round(c.motion.x,3),round(c.motion.y,3))
