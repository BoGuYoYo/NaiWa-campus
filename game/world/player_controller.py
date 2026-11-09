"""任务 C5：移动、8 方向朝向、动画切换与脚步计时。

- PlayerMotion 是纯数学部分（不依赖 Panda3D），可在 tests/world/test_player_motion.py 中验证。
- PlayerController 把它接到 Panda3D 的玩家节点上，并处理输入读取、动画与脚步声。
  动画与音效通过注入的 animator / audio 调用（A / D 提供），C 不生成素材。

规格（任务分工手册 3.0 · C5 与表 15）：
- 输入映射、速度、帧时间上限、8 方向朝向规则见 game/world/input_map.py
- 动画：速度 > 0.1 播放 char_naiwan_walk（8 fps，按朝向行），否则 char_naiwan_idle（3 fps）
- 脚步声：移动时每 0.35 秒（快走 0.25 秒）一次，室内 sfx_footstep_floor，室外 sfx_footstep_ground
- 输入锁定：存在覆盖层或场景淡入淡出时忽略移动与交互
"""

from __future__ import annotations

from game.world.collision import Rect, clamp_to_bounds, move_and_collide
from game.world.input_map import (
    FACING_SPEED_EPS,
    FootstepTimer,
    WALK_SPEED,
    RUN_SPEED,
    approach_speed,
    clamp_dt,
    facing_for,
    input_vector,
    target_speed,
)
from game.world.map_data import CAMPUS_SCENE, MapData

# 8 方向 -> Panda3D heading（heading 0 朝 +Y=北，逆时针为正）
FACING_HEADING = {
    "n": 0.0,
    "nw": 45.0,
    "w": 90.0,
    "sw": 135.0,
    "s": 180.0,
    "se": 225.0,
    "e": 270.0,
    "ne": 315.0,
}

WALK_ASSET = "char_naiwan_walk"
IDLE_ASSET = "char_naiwan_idle"
WALK_FPS = 8.0
IDLE_FPS = 3.0

SFX_FOOTSTEP_GROUND = "sfx_footstep_ground"
SFX_FOOTSTEP_FLOOR = "sfx_footstep_floor"


class _Vec:
    __slots__ = ("x", "y")

    def __init__(self, x: float, y: float) -> None:
        self.x = float(x)
        self.y = float(y)


class PlayerMotion:
    """玩家在单一场景内的纯数学移动状态，pos 为该场景坐标。"""

    def __init__(
        self,
        x: float,
        y: float,
        facing: str = "n",
        walk_speed: float = WALK_SPEED,
        run_speed: float = RUN_SPEED,
    ) -> None:
        self.x = float(x)
        self.y = float(y)
        self.facing = facing
        self.speed = 0.0
        self.moving = False
        self.walk_speed = float(walk_speed)
        self.run_speed = float(run_speed)

    def snap(self, x: float, y: float, facing: str | None = None) -> None:
        self.x = float(x)
        self.y = float(y)
        self.speed = 0.0
        self.moving = False
        if facing is not None:
            self.facing = facing

    def update(self, pressed, running: bool, dt: float, rects=(), bounds: Rect | None = None) -> bool:
        """推进一帧；pressed 为按下的键集合。返回本帧是否在移动。"""
        dt = clamp_dt(dt)
        dx, dy = input_vector(pressed)
        has_input = dx != 0.0 or dy != 0.0
        target = (self.run_speed if running else self.walk_speed) if has_input else 0.0
        self.speed = approach_speed(self.speed, target, dt)

        if has_input and self.speed > FACING_SPEED_EPS:
            new_facing = facing_for(dx, dy)
            if new_facing is not None:
                self.facing = new_facing
            step = self.speed * dt
            pos = _Vec(self.x, self.y)
            move_and_collide(pos, _Vec(dx * step, dy * step), rects)
            self.x, self.y = pos.x, pos.y

        if bounds is not None:
            pos = _Vec(self.x, self.y)
            clamp_to_bounds(pos, bounds)
            self.x, self.y = pos.x, pos.y

        self.moving = has_input and self.speed > FACING_SPEED_EPS
        return self.moving


class PlayerController:
    """把 PlayerMotion 接到 Panda3D 玩家节点；场景坐标一律使用世界坐标。"""

    def __init__(
        self,
        map_data: MapData,
        state,
        player_node_path,
        camera=None,
        *,
        animator=None,
        audio=None,
        key_down=None,
        walk_speed: float = WALK_SPEED,
        run_speed: float = RUN_SPEED,
    ) -> None:
        self.map_data = map_data
        self.state = state
        self.player = player_node_path
        self.camera = camera
        self.animator = animator
        self.audio = audio
        self._key_down = key_down or _default_key_down
        self._footstep = FootstepTimer()
        self._scene = CAMPUS_SCENE
        self._rects: tuple[Rect, ...] = ()
        self._bounds: Rect | None = None
        self.input_locked = False
        self.motion = PlayerMotion(state.world.x, state.world.y, state.world.facing, walk_speed, run_speed)
        self.set_scene(CAMPUS_SCENE, reset=False)

    # ------------------------------------------------------------------ 场景
    def set_scene(self, scene: str, reset: bool = True) -> None:
        """切换碰撞上下文。室内房间在世界坐标系下渲染，因此矩形整体平移房间原点。"""
        self._scene = scene
        if scene == CAMPUS_SCENE:
            self._rects = self.map_data.colliders_for(CAMPUS_SCENE)
            self._bounds = self.map_data.bounds
        else:
            origin = self.map_data.interior(scene).origin
            size = self.map_data.interior(scene).size
            self._rects = tuple(
                Rect(r.x0 + origin[0], r.y0 + origin[1], r.x1 + origin[0], r.y1 + origin[1])
                for r in self.map_data.colliders_for(scene)
            )
            self._bounds = Rect(origin[0], origin[1], origin[0] + size[0], origin[1] + size[1])
        if reset:
            self.motion.snap(self.state.world.x, self.state.world.y, self.state.world.facing)
            self._apply_transform()

    def teleport(self, x: float, y: float, facing: str | None = None) -> None:
        self.motion.snap(x, y, facing)
        self.state.world.x = self.motion.x
        self.state.world.y = self.motion.y
        if facing is not None:
            self.state.world.facing = facing
        self._apply_transform()
        if self.camera is not None:
            self.camera.update((self.motion.x, self.motion.y), 1.0)

    # ------------------------------------------------------------------ 输入
    def read_input(self, keys=("w", "a", "s", "d", "up", "down", "left", "right", "shift")):
        pressed = {k for k in keys if k != "shift" and self._key_down(k)}
        running = self._key_down("shift")
        return pressed, running

    # ------------------------------------------------------------------ 推进
    def update(self, dt: float, locked: bool | None = None) -> None:
        locked = self.input_locked if locked is None else locked
        if locked:
            self.motion.speed = 0.0
            self.motion.moving = False
            self._footstep.reset()
            self._play_idle()
            return

        pressed, running = self.read_input()
        moving = self.motion.update(pressed, running, dt, self._rects, self._bounds)

        self.state.world.x = self.motion.x
        self.state.world.y = self.motion.y
        self.state.world.facing = self.motion.facing
        self._apply_transform()

        self._update_footstep(dt, moving, running)
        self._play_animation(moving, running)

        if self.camera is not None:
            self.camera.update((self.motion.x, self.motion.y), dt)

    # ------------------------------------------------------------------ 内部
    def _apply_transform(self) -> None:
        self.player.setPos(self.motion.x, self.motion.y, 0.0)
        self.player.setH(FACING_HEADING.get(self.motion.facing, 0.0))

    def _update_footstep(self, dt: float, moving: bool, running: bool) -> None:
        if self.audio is None:
            return
        if self._footstep.tick(dt, moving, running):
            sfx = SFX_FOOTSTEP_FLOOR if self._scene != CAMPUS_SCENE else SFX_FOOTSTEP_GROUND
            self.audio.play(sfx)

    def _play_animation(self, moving: bool, running: bool) -> None:
        if self.animator is None:
            return
        if moving:
            self.animator.play(WALK_ASSET, row=self.motion.facing, fps=WALK_FPS)
        else:
            self.animator.play(IDLE_ASSET, row=self.motion.facing, fps=IDLE_FPS)

    def _play_idle(self) -> None:
        if self.animator is not None:
            self.animator.play(IDLE_ASSET, row=self.motion.facing, fps=IDLE_FPS)


def _default_key_down(key: str) -> bool:
    """默认从 Panda3D 的 mouseWatcherNode 读取按键状态。"""
    from direct.showbase.ShowBaseGlobal import base

    watcher = getattr(base, "mouseWatcherNode", None)
    if watcher is None:
        return False
    return bool(watcher.isKeyDown(key))
