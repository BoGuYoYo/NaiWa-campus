"""A 的独立验收程序。

    python -m tests.standalone_a --check-save --check-assets --check-flow [--check-render]

只依赖 tests/standalone_a/fixtures/ 与 A 自己的 core 层，不依赖 B/C/D 未完成的代码；
所有输出写 reports/standalone/A/，绝不写用户存档或正式 assets。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
REPORT_DIR = ROOT / "reports" / "standalone" / "A"

sys.path.insert(0, str(ROOT))

from game import config  # noqa: E402
from game.core.asset_registry import AssetRegistry  # noqa: E402
from game.core.event_bus import TOPIC_ASSET_MISSING, EventBus  # noqa: E402
from game.core.flow import GameFlow, resolve_services  # noqa: E402
from game.core.render_pipeline import compute_viewport, snap_to_pixel_grid  # noqa: E402
from game.core.save_manager import SaveLoadError, SaveManager  # noqa: E402
from game.core.scene_manager import SceneManager  # noqa: E402
from game.core.state import GameState  # noqa: E402

CHECK_RESULTS: list[dict[str, Any]] = []


class DummyScene:
    def __init__(self, scene_id: str, **kwargs: Any) -> None:
        self.scene_id = scene_id
        self.kwargs = kwargs

    def on_enter(self, **kwargs: Any) -> None:
        pass

    def on_exit(self) -> None:
        pass


def check(name: str, fn: Callable[[], None]) -> None:
    try:
        fn()
    except Exception as exc:  # 记录失败原因而不是中断整轮
        CHECK_RESULTS.append({"name": name, "ok": False, "detail": f"{type(exc).__name__}: {exc}"})
        print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")
    else:
        CHECK_RESULTS.append({"name": name, "ok": True, "detail": ""})
        print(f"[ OK ] {name}")


# --------------------------------------------------------------------------- #
# A-ST-03：存档
# --------------------------------------------------------------------------- #
def check_save() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        saves = SaveManager(saves_root=Path(tmp))

        def roundtrip() -> None:
            fixture = json.loads((FIXTURES / "state.json").read_text(encoding="utf-8"))
            state = GameState.from_dict(fixture)
            saves.save(state, "slot_1")
            loaded = saves.load("slot_1")
            assert loaded.to_dict() == state.to_dict(), "存档往返后状态不一致"

        def corrupt_fallback() -> None:
            state = GameState.from_dict(json.loads((FIXTURES / "state.json").read_text(encoding="utf-8")))
            saves.save(state, "slot_2")
            state.day_index = 1
            saves.save(state, "slot_2")  # 现在 slot_2.bak 是 day_index=2 的旧档
            saves.path_for("slot_2").write_text("{ broken json", encoding="utf-8")
            restored = saves.load("slot_2")
            assert restored.day_index in (1, 2), "回退后的状态异常"

        def corrupt_without_bak() -> None:
            saves.delete("slot_3")
            target = saves.path_for("slot_3")
            target.write_text((FIXTURES / "corrupt.json").read_text(encoding="utf-8"), encoding="utf-8")
            try:
                saves.load("slot_3")
            except SaveLoadError as exc:
                assert exc.code == "E_SAVE_CORRUPT", exc.code
                assert exc.text_id == "err.save_corrupt"
            else:
                raise AssertionError("损坏存档未返回错误")
            assert target.exists(), "失败时不得删除原文件"

        check("A-ST-03a 存档往返一致", roundtrip)
        check("A-ST-03b 损坏档案回退 .bak", corrupt_fallback)
        check("A-ST-03c 损坏无备份返回 SaveError", corrupt_without_bak)


# --------------------------------------------------------------------------- #
# A-ST-02：资源缺失回退
# --------------------------------------------------------------------------- #
def check_assets() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assets_root = Path(tmp) / "assets"
        (assets_root / "characters" / "fixture").mkdir(parents=True, exist_ok=True)
        source = ROOT / "assets" / "characters" / "naiwan" / "walk.png"
        if source.exists():
            shutil.copy2(source, assets_root / "characters" / "fixture" / "present.png")
        manifest_text = (FIXTURES / "manifest.json").read_text(encoding="utf-8")
        (assets_root / "manifest.json").write_text(manifest_text, encoding="utf-8")
        (assets_root / "LICENSES.csv").write_text(
            "license_id,asset_ids,author,source_url,license,commercial_ok,modified,date_added,notes\n"
            "LIC-9001,fixture_sprite,qa,internal,own,yes,no,2026-01-05,fixture\n"
            "LIC-9002,fixture_model,qa,internal,own,no,no,2026-01-05,non commercial fixture\n",
            encoding="utf-8",
        )

        previous_root = config.resource_root()
        config.set_resource_root(Path(tmp))
        bus = EventBus()
        events: list[dict[str, Any]] = []
        bus.subscribe(TOPIC_ASSET_MISSING, lambda **data: events.append(data))
        try:
            registry = AssetRegistry(
                manifest_path=assets_root / "manifest.json",
                licenses_path=assets_root / "LICENSES.csv",
                bus=bus,
            )

            def manifest_ok() -> None:
                assert len(registry) == 3
                assert registry.get("fixture_sprite_present").cols == 4

            def missing_files() -> None:
                missing = dict((asset_id, path) for asset_id, path in registry.missing_files())
                assert "fixture_sprite_missing" in missing
                assert "fixture_sprite_present" not in missing

            def fallback_texture() -> None:
                try:
                    import panda3d  # noqa: F401
                except ImportError:
                    return  # 无引擎时跳过（结构已在上面校验）
                texture = registry.load_texture("fixture_sprite_missing")
                assert texture is not None
                assert events and events[0]["asset_id"] == "fixture_sprite_missing"

            def license_blockers() -> None:
                blockers = registry.release_blockers()
                assert any(item.startswith("fixture_model") for item in blockers), blockers

            check("A-ST-02a manifest 解析", manifest_ok)
            check("A-ST-02b 缺失文件列表", missing_files)
            check("A-ST-02c 缺失贴图回退并广播 asset.missing", fallback_texture)
            check("A-ST-02d 非商用资源阻止发布", license_blockers)
        finally:
            config.set_resource_root(previous_root)


# --------------------------------------------------------------------------- #
# 流程与场景
# --------------------------------------------------------------------------- #
def check_flow() -> None:
    scene_file = json.loads((FIXTURES / "scene.json").read_text(encoding="utf-8"))
    bus = EventBus()
    scenes = SceneManager(app=None, factory=lambda sid, kw: DummyScene(sid, **kw), bus=bus,
                          fade_seconds=0.25)

    def scene_script() -> None:
        for step in scene_file["steps"]:
            action = step["action"]
            if action == "start":
                scenes.start(step["scene"])
            elif action == "change":
                scenes.change(step["scene"], **step.get("kwargs", {}))
            elif action == "push":
                scenes.push(step["scene"])
            elif action == "pop":
                scenes.pop()
            elif action == "update":
                scenes.update(step["dt"])
            elif action == "expect_overlay":
                assert scenes.top_overlay_id == step["scene"], (
                    f"overlay 期望 {step['scene']} 实际 {scenes.top_overlay_id}")
            elif action == "expect_input_locked":
                assert scenes.input_locked == step["value"]
            elif action == "expect_scene":
                assert scenes.current_id == step["scene"]

    with tempfile.TemporaryDirectory() as tmp:
        saves = SaveManager(saves_root=Path(tmp))
        flow = GameFlow(app=None, scenes=scenes, saves=saves, bus=bus, services=resolve_services())

        def day_loop() -> None:
            flow.new_game(seed=42, skip_intro=True)
            state = flow.require_state()
            for _ in range(config.ACTIONS_PER_DAY):
                result = flow.services.activity.start(state, "attend_class")
                assert result.ok
                flow.handle_activity_result(result)
                flow.close_result_panel(result)
            assert state.day_index == 1, state.day_index
            assert saves.path_for("autosave").exists()

        def graduation() -> None:
            flow.new_game(seed=42, skip_intro=True)
            state = flow.require_state()
            for _ in range(config.TOTAL_DAYS * (config.ACTIONS_PER_DAY + 2)):
                state = flow.require_state()
                if state.phase == "graduation":
                    break
                if state.phase == "event":
                    event_id = state.pending_event_id or flow.story_opening_id
                    flow.handle_event_result(flow.services.event.choose(state, event_id, "ok"))
                    continue
                if not state.day_finished:
                    result = flow.services.activity.start(state, "attend_class")
                    flow.handle_activity_result(result)
                    flow.close_result_panel(result)
                else:
                    flow.finish_day()
            state = flow.require_state()
            assert state.phase == "graduation", state.phase
            assert state.day_index == config.TOTAL_DAYS - 1
            assert state.ending_id

        def pause_locks_time() -> None:
            flow.new_game(seed=1, skip_intro=True)
            state = flow.require_state()
            before = state.play_seconds
            flow.set_paused(True)
            flow.tick(1.0)
            assert state.play_seconds == before
            flow.set_paused(False)
            flow.tick(0.5)
            assert state.play_seconds > before

        check("A-ST-05 场景脚本（MainMenu→Campus→Pause）", scene_script)
        check("流程图：3 个行动结束一天并自动存档", day_loop)
        check("流程图：16 天推进到毕业", graduation)
        check("流程图：暂停不累计 play_seconds", pause_locks_time)


# --------------------------------------------------------------------------- #
# A-ST-04：离屏渲染
# --------------------------------------------------------------------------- #
def check_render() -> None:
    def viewport_rule() -> None:
        assert compute_viewport(1920, 1080).scale == 4.0
        assert compute_viewport(1280, 720).integer is False
        assert abs(compute_viewport(1280, 720).scale - 2.6667) < 1e-3
        grid = 1.0 / config.PIXELS_PER_METER
        assert abs(snap_to_pixel_grid(40.0 + grid * 0.4) - 40.0) < 1e-9
        assert abs(snap_to_pixel_grid(40.0 + grid * 0.6) - (40.0 + grid)) < 1e-9

    def offscreen_frames() -> None:
        try:
            import panda3d  # noqa: F401
        except ImportError:
            print("      (跳过：未安装 panda3d)")
            return
        from panda3d.core import loadPrcFileData

        loadPrcFileData("", "window-type offscreen")
        loadPrcFileData("", "win-size 1280 720")
        loadPrcFileData("", "audio-library-name null")
        loadPrcFileData("", "textures-power-2 none")

        from game.app import NaiwaApp

        options = config.parse_args(["--scene", "CampusScene", "--skip-intro", "--offscreen",
                                     "--frames", "999999", "--seed", "42"])
        config.setup_logging(options)
        app = NaiwaApp(options)
        try:
            target = REPORT_DIR / "offscreen_6frames.png"
            for _ in range(6):
                app.taskMgr.step()
            ok = app.pipeline.save_buffer_screenshot(str(target))
            assert ok, "截图失败"
            assert target.exists() and target.stat().st_size > 0
            assert app.pipeline.buffer is not None
            from panda3d.core import SamplerState

            assert app.pipeline.texture.getMagfilter() == SamplerState.FT_nearest, \
                "放大过滤必须是 nearest"
            try:
                from PIL import Image

                with Image.open(target) as shot:
                    assert shot.size == (480, 270), shot.size
            except ImportError:
                pass
        finally:
            app.destroy()

    check("A-ST-04a 缩放规则与网格对齐", viewport_rule)
    check("A-ST-04b 6 帧离屏渲染生成 480×270 截图", offscreen_frames)


# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A 独立验收")
    parser.add_argument("--check-save", action="store_true")
    parser.add_argument("--check-assets", action="store_true")
    parser.add_argument("--check-flow", action="store_true")
    parser.add_argument("--check-render", action="store_true")
    parser.add_argument("--all", action="store_true", help="等价于同时开启 4 个 check")
    args = parser.parse_args(argv)

    run_all = args.all or not any((args.check_save, args.check_assets, args.check_flow,
                                  args.check_render))
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    if run_all or args.check_save:
        check_save()
    if run_all or args.check_assets:
        check_assets()
    if run_all or args.check_flow:
        check_flow()
    if run_all or args.check_render:
        check_render()

    failed = [item for item in CHECK_RESULTS if not item["ok"]]
    report = {
        "suite": "standalone_a",
        "total": len(CHECK_RESULTS),
        "passed": len(CHECK_RESULTS) - len(failed),
        "failed": len(failed),
        "results": CHECK_RESULTS,
    }
    (REPORT_DIR / "standalone_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{report['passed']}/{report['total']} passed -> {REPORT_DIR / 'standalone_report.json'}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
