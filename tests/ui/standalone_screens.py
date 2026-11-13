"""standalone_d 截图模式的渲染辅助（gui，仅在 panda3d 可用时运行）。

用夹具数据驱动每个界面并截图，输出到 reports/standalone/D/screens/。
不创建用户存档、不调用真实地图、不改 GameState（隔离规则）。
"""

from __future__ import annotations

import json
import os

from panda3d.core import Filename

from tests.ui.conftest import FIXTURES


def _load(name: str):
    with open(os.path.join(FIXTURES, name), "r", encoding="utf-8") as f:
        return json.load(f)


class _FakeAssetRegistry:
    """占位资源注册表：assets.json 定义纯色纹理（隔离规则）。"""

    def __init__(self) -> None:
        spec = _load("assets.json")
        self._colors = spec["assets"]

    def load_texture(self, asset_id: str):
        from panda3d.core import PNMImage, Texture

        color = self._colors.get(asset_id, {}).get("color", "#808080")
        h = color.lstrip("#")
        image = PNMImage(8, 8)
        image.fill(
            int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0
        )
        texture = Texture(asset_id)
        texture.load(image)
        return texture


class _FakePromptView:
    def __init__(self, label_text_id, enabled=True, reason_code=None, cost_preview=None):
        self.interactable_id = "ia_fixture"
        self.label_text_id = label_text_id
        self.enabled = enabled
        self.reason_code = reason_code
        self.cost_preview = cost_preview


class _FakeActivityResult:
    def __init__(self, spec):
        self.ok = spec["ok"]
        self.activity_id = spec["activity_id"]
        self.error_code = spec["error_code"]
        self.deltas = spec["deltas"]
        self.added_flags = spec["added_flags"]
        self.text_ids = spec["text_ids"]
        self.triggered_event_id = spec["triggered_event_id"]
        self.day_finished = spec["day_finished"]


class _FakeChoice:
    def __init__(self, spec):
        self.choice_id = spec["choice_id"]
        self.text_id = spec["text_id"]
        self.enabled = spec["enabled"]
        self.lock_reason_id = spec["lock_reason_id"]


class _FakeEventView:
    def __init__(self, spec, fixture_text_db):
        self.event_id = spec["event_id"]
        self.kind = spec["kind"]
        self.speaker = spec["speaker"]
        self.page_text_ids = spec["page_text_ids"]
        self.choices = [_FakeChoice(c) for c in spec["choices"]]
        # 夹具页面注册进 TextDB
        fixture_text_db.dialogues.update(spec.get("fixture_text", {}))


def _screenshot(base, path: str) -> None:
    base.graphics_engine.render_frame()
    base.graphics_engine.render_frame()
    base.screenshot(namePrefix=Filename.from_os_specific(path), defaultFilename=False)


#: 截图用的中文字体：正式 font_ui 未交付时回退系统黑体（与 A 的 load_ui_font 同策略）
SYSTEM_CJK_FONTS = ("msyh.ttc", "msyh.ttf", "simhei.ttf", "Deng.ttf", "simsun.ttc")


def _install_cjk_font(base) -> None:
    """没有中文字体时 UIKit 只会画出方框，截图就没有参考价值。"""
    import os
    from pathlib import Path

    from game.ui.widgets import set_default_font

    fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    loader = getattr(base, "loader", None)
    for name in SYSTEM_CJK_FONTS:
        path = fonts / name
        if not path.exists() or loader is None:
            continue
        try:
            font = loader.loadFont(Filename.from_os_specific(str(path)).get_fullpath())
        except Exception:
            continue
        if font is not None:
            set_default_font(font)
            print(f"[screens] ui font = {name}")
            return
    print("[screens] 未找到系统中文字体，文本会显示为方框")


def render_all_screens(base, text_db, out_dir: str, screens: str) -> None:
    from game.ui import theme
    from game.ui.dialogue_box import DialogueBox
    from game.ui.event_scene import EventScene
    from game.ui.graduation_scene import GraduationScene
    from game.ui.hud import HUD
    from game.ui.result_panel import ResultPanel
    from game.ui.widgets import UITransform

    _install_cjk_font(base)
    # 夹具文案合并进正式文本库：截图既能用真实剧情，也能用夹具里的用例文本
    text_db.strings.update(_load("strings.json"))
    transform = UITransform.from_base(base)
    assets = _FakeAssetRegistry()
    aspect2d = base.aspect2d

    targets = SCREEN_NAMES_ALL if screens == "all" else (screens,)
    state = _make_state()

    if "hud" in targets:
        hud = HUD(aspect2d, transform, text_db, assets)
        hud.update(state)
        _screenshot(base, os.path.join(out_dir, "hud.png"))
        hud.destroy()

    if "result" in targets:
        panel = ResultPanel(aspect2d, transform, text_db, assets)
        results = _load("results.json")
        panel.show_result(_FakeActivityResult(results["result_library"]))
        for _ in range(8):
            panel.tick(0.13)
        base.graphics_engine.render_frame()
        _screenshot(base, os.path.join(out_dir, "result.png"))
        panel.destroy()

    if "dialogue" in targets:
        box = DialogueBox(aspect2d, transform, text_db, assets)
        box.show_page({"speaker": "npc_chenlang", "portrait": "portrait_npc_chenlang_happy",
                       "lines": ["夹具对话第一页。", "头像与名字条应为陈朗。"]})
        box.tick(5.0)
        base.graphics_engine.render_frame()
        _screenshot(base, os.path.join(out_dir, "dialogue.png"))
        box.destroy()

    if "event" in targets:
        events = _load("events.json")
        scene = EventScene(aspect2d, transform, text_db, assets)
        scene.load_event(_FakeEventView(events["event_fixture_01"], text_db))
        scene.dialogue.tick(5.0)
        base.graphics_engine.render_frame()
        _screenshot(base, os.path.join(out_dir, "event_choices.png"))
        scene.destroy()

    if "day_summary" in targets:
        from game.ui.day_summary import DaySummary

        summary = DaySummary(aspect2d, transform, text_db, assets)
        summary.show_summary(_make_day_end(), day=1, action_names=["上课", "图书馆学习", "打游戏"])
        _screenshot(base, os.path.join(out_dir, "day_summary.png"))
        summary.destroy()

    if "tab" in targets:
        from game.ui.tab_panel import TabPanel

        tab = TabPanel(aspect2d, transform, text_db, assets)
        tab.update_state(state)
        tab.show()
        _screenshot(base, os.path.join(out_dir, "tab.png"))
        tab.destroy()

    if "main_menu" in targets:
        from game.ui.main_menu import MainMenu

        menu = MainMenu(aspect2d, transform, text_db, assets)
        menu.show()
        _screenshot(base, os.path.join(out_dir, "main_menu.png"))
        menu.destroy()

    if "graduation" in targets:
        graduation = GraduationScene(aspect2d, transform, text_db, assets)
        graduation.open(_make_ending(), state_snapshot={
            "stats": state.stats, "relationships": state.relationships,
            "mood": state.mood, "energy": state.energy,
        })
        base.graphics_engine.render_frame()
        _screenshot(base, os.path.join(out_dir, "graduation.png"))
        graduation.destroy()


def render_event_fixture(base, text_db, event_spec, out_dir: str) -> None:
    from game.ui.event_scene import EventScene
    from game.ui.widgets import UITransform

    _install_cjk_font(base)
    transform = UITransform.from_base(base)
    scene = EventScene(base.aspect2d, transform, text_db, _FakeAssetRegistry())
    scene.load_event(_FakeEventView(event_spec, text_db))
    scene.dialogue.tick(5.0)
    _screenshot(base, os.path.join(out_dir, f"{event_spec['event_id']}_page.png"))
    if event_spec["choices"]:
        scene.panel.show()
        scene.dialogue.hide()
        base.graphics_engine.render_frame()
        _screenshot(base, os.path.join(out_dir, f"{event_spec['event_id']}_choices.png"))


# ----------------------------------------------------------------------
SCREEN_NAMES_ALL = ("hud", "result", "dialogue", "event", "day_summary", "tab", "main_menu", "graduation")


def _make_state():
    from tests.ui.conftest import FakeState

    return FakeState(relationships={"npc_sumo": 2})


class _FakeDayEnd:
    deltas = {"energy": 30}
    new_day_index = 1
    semester_event_id = "sem_1_club_fair"
    graduated = False


class _FakeEnding:
    ending_id = "ending_kaoyan"
    matched = ["cond_high_academic"]
    highlights = ["四年回顾：图书馆是第二个家。", "四年回顾：错题本换了两本。"]


def _make_day_end():
    return _FakeDayEnd()


def _make_ending():
    return _FakeEnding()
