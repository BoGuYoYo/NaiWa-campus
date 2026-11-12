"""任务 C9：调试功能（仅 --dev 时启用）。

F1 显示碰撞矩形（红色线框）    F2 显示交互点与半径（绿色圆）
F3 左上角显示坐标/朝向/地点/FPS  F5 传送到下一个交互点（按表 14 顺序循环）
F6 当前时段直接设为 3（测试日结算）

本模块只写 state.action_slot（调试用途）以及通过 PlayerController 传送玩家，
不触碰任何属性字段（academic / stamina / social / interest / mood / energy）。
"""

from __future__ import annotations

from game.world.campus_scene import (
    make_circle_lines,
    make_rect_lines,
    make_triangle_marker,
)
from game.world.map_data import CAMPUS_SCENE, MapData

COLLISION_COLOR = (1.0, 0.15, 0.15, 1.0)
INTERACTABLE_COLOR = (0.20, 0.90, 0.30, 1.0)
TELEPORT_COLOR = (1.0, 0.55, 0.10, 1.0)

Z_DEBUG = 0.10


class DebugDraw:
    """F1~F6 调试绘制。所有节点挂在独立的 DebugDraw 根下，不影响正式场景。"""

    def __init__(self, map_data: MapData, parent, *, camera=None, player=None, state=None, goto=None):
        self.map_data = map_data
        self.root = parent.attachNewNode("DebugDraw")
        self.collision_root = self.root.attachNewNode("collision")
        self.interactable_root = self.root.attachNewNode("interactables")
        self.teleport_root = self.root.attachNewNode("teleport")
        self.camera = camera
        self.player = player
        self.state = state
        self._goto = goto
        self._scene = CAMPUS_SCENE
        self._collision_built = False
        self._interactables_built = False
        self._text = None
        self._ia_ids = [ia.id for ia in map_data.interactables]
        self._ia_index = 0
        self.collision_root.hide()
        self.interactable_root.hide()
        self.teleport_root.hide()

    # ------------------------------------------------------------------ 绑定
    def bind(self, base) -> None:
        base.accept("f1", self.toggle_collision)
        base.accept("f2", self.toggle_interactables)
        base.accept("f3", self.toggle_status)
        base.accept("f5", self.teleport_next_interactable)
        base.accept("f6", self.set_slot_three)

    # ------------------------------------------------------------------ 场景
    def set_scene(self, scene: str) -> None:
        """切换场景后重建调试几何。"""
        self._scene = scene
        for child in list(self.collision_root.getChildren()):
            child.removeNode()
        for child in list(self.interactable_root.getChildren()):
            child.removeNode()
        self._collision_built = False
        self._interactables_built = False

    # ------------------------------------------------------------------ 构建
    def _build_collision(self) -> None:
        if self._collision_built:
            return
        # 室内的阻挡矩形是房间本地坐标：不加上房间原点，线框会整体画到房间外面
        # （F1 在室内"看着不像碰撞体"就是这个原因）。
        ox = oy = 0.0
        if self.map_data.has_interior(self._scene):
            ox, oy = self.map_data.interior(self._scene).origin
        for r in self.map_data.colliders_for(self._scene):
            make_rect_lines(self.collision_root, r.x0 + ox, r.y0 + oy,
                            r.x1 + ox, r.y1 + oy, Z_DEBUG, COLLISION_COLOR)
        self._collision_built = True

    def _build_interactables(self) -> None:
        if self._interactables_built:
            return
        for ia in self.map_data.interactables_for(self._scene):
            x, y = self.map_data.to_world(ia)
            make_circle_lines(self.interactable_root, x, y, ia.radius, Z_DEBUG, INTERACTABLE_COLOR)
        self._interactables_built = True

    # ------------------------------------------------------------------ F1/F2
    def toggle_collision(self) -> bool:
        self._build_collision()
        return self._toggle(self.collision_root)

    def toggle_interactables(self) -> bool:
        self._build_interactables()
        return self._toggle(self.interactable_root)

    @staticmethod
    def _toggle(node) -> bool:
        if node.isHidden():
            node.show()
            return True
        node.hide()
        return False

    # ------------------------------------------------------------------ F3
    def toggle_status(self) -> None:
        from direct.gui.OnscreenText import OnscreenText

        if self._text is None:
            self._text = OnscreenText(
                text="",
                pos=(-1.3, 0.9),
                align=0,
                scale=0.05,
                fg=(1, 1, 1, 1),
                mayChange=True,
            )
            taskMgr.add(self._status_task, "debug_status")
        else:
            self._text.destroy()
            self._text = None
            taskMgr.remove("debug_status")

    def status_lines(self) -> str:
        if self.state is not None and self.player is not None:
            m = self.player.motion
            loc = self.state.world.location_id
            return (
                f"pos=({m.x:.2f}, {m.y:.2f})  facing={m.facing}  "
                f"loc={loc}  fps={self._fps():.0f}"
            )
        return f"fps={self._fps():.0f}"

    def _status_task(self, task):
        if self._text is not None:
            self._text.setText(self.status_lines())
        return task.cont

    @staticmethod
    def _fps() -> float:
        try:
            from direct.showbase.ShowBaseGlobal import base

            return float(base.clock.getAverageFrameRate())
        except Exception:  # pragma: no cover - 离线环境
            return 0.0

    # ------------------------------------------------------------------ F5
    def teleport_next_interactable(self) -> str:
        ia_id = self._ia_ids[self._ia_index % len(self._ia_ids)]
        self._ia_index = (self._ia_index + 1) % len(self._ia_ids)
        ia = self.map_data.interactable(ia_id)
        x, y = self.map_data.to_world(ia)
        if self._goto is not None:
            self._goto(ia.scene, x, y)
        elif self.player is not None:
            if ia.scene != self._scene:
                self.set_scene(ia.scene)
            self.player.teleport(x, y)
        return ia_id

    # ------------------------------------------------------------------ F6
    def set_slot_three(self) -> None:
        if self.state is not None:
            self.state.action_slot = 3
