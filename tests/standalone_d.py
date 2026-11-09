"""开发者 D 独立运行入口（独立测试契约）。

命令（均须在 naiwa_campus/ 仓库根目录执行）：

    python -m tests.standalone_d --text-check --locale zh_CN
    python -m tests.standalone_d --screen all --out reports/standalone/D/screens/
    python -m tests.standalone_d --event event_fixture_01 --offscreen

- --text-check：纯逻辑，不依赖 panda3d；校验正式文本并输出
  reports/standalone/D/text_report.json，发现问题退出码为 1。
- --screen / --event：屏幕截图模式，需要 panda3d（gui）；本机未
  安装时打印安装说明并退出码 2。不创建用户存档、不调用真实
  地图、不改 GameState。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

REPORT_DIR = os.path.join(PROJECT_ROOT, "reports", "standalone", "D")
CONTENT_ROOT = os.path.join(PROJECT_ROOT, "content")
FIXTURES = os.path.join(PROJECT_ROOT, "tests", "ui", "fixtures")


# ----------------------------------------------------------------------
# 文本校验（纯逻辑）
# ----------------------------------------------------------------------
def run_text_check(locale: str) -> int:
    from game.ui.text_db import TextDB

    base = os.path.join(CONTENT_ROOT, "text", locale)
    db = TextDB.load(CONTENT_ROOT, locale=locale)
    problems = db.validate()

    # 结构覆盖统计（交付物清单核对）
    counts = {
        "strings_total": len(db.strings),
        "dialogues_total": len(db.dialogues),
        "activities": _count(db.strings, "act.", ".name"),
        "semester_events": _count(db.strings, "evt.sem_", ".title"),
        "relationship_events": _count(db.strings, "evt.rel_", ".title"),
        "daily_events": _count(db.strings, "daily.", ".title"),
        "endings": _count(db.strings, "ending.", ".title"),
    }

    expected = {
        "activities": 9,
        "semester_events": 8,
        "relationship_events": 9,
        "daily_events": 12,
        "endings": 6,
    }
    for key, want in expected.items():
        if counts[key] != want:
            problems.append(f"数量不符：{key} = {counts[key]}，应为 {want}")

    os.makedirs(REPORT_DIR, exist_ok=True)
    report_path = os.path.join(REPORT_DIR, "text_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({"locale": locale, "counts": counts, "problems": problems}, f, ensure_ascii=False, indent=2)

    print(f"文本统计: {json.dumps(counts, ensure_ascii=False)}")
    if problems:
        print(f"发现 {len(problems)} 个问题（详见 {report_path}）：")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"文本校验通过，报告已写入 {report_path}")
    return 0


def _count(strings: dict, prefix: str, suffix: str) -> int:
    return len({k.split(".")[1] for k in strings if k.startswith(prefix) and k.endswith(suffix)})


# ----------------------------------------------------------------------
# 截图模式（需要 panda3d；gui 标记，回归时运行）
# ----------------------------------------------------------------------
SCREEN_NAMES = ("hud", "result", "dialogue", "event", "day_summary", "tab", "main_menu", "graduation")


def _require_panda3d() -> int:
    try:
        import panda3d  # noqa: F401
    except ImportError:
        print("panda3d 未安装。请先执行：pip install -r requirements.txt")
        print("（Panda3D 1.10.16，Python 3.12.x 64 位）")
        return 2
    return 0


def _prepare_offscreen() -> None:
    """离屏缓冲不能 set_size（会踩 BF_resizeable 断言），尺寸必须在 ShowBase 之前用 PRC 定。"""
    from panda3d.core import loadPrcFileData

    loadPrcFileData("", "win-size 1280 720")
    loadPrcFileData("", "textures-power-2 none")
    loadPrcFileData("", "sync-video false")
    loadPrcFileData("", "audio-library-name null")


def run_screens(screens: str, out_dir: str) -> int:
    code = _require_panda3d()
    if code:
        return code
    _prepare_offscreen()
    from direct.showbase.ShowBase import ShowBase

    from game.ui.text_db import TextDB

    os.makedirs(out_dir, exist_ok=True)
    base = ShowBase(windowType="offscreen")
    text_db = TextDB.load(CONTENT_ROOT)

    from tests.ui.standalone_screens import render_all_screens

    render_all_screens(base, text_db, out_dir, screens)
    print(f"界面截图已写入 {out_dir}")
    base.destroy()
    return 0


def run_event_fixture(event_id: str, out_dir: str) -> int:
    code = _require_panda3d()
    if code:
        return code
    _prepare_offscreen()
    from direct.showbase.ShowBase import ShowBase

    from game.ui.text_db import TextDB
    from tests.ui.standalone_screens import render_event_fixture

    os.makedirs(out_dir or os.path.join(REPORT_DIR, "screens"), exist_ok=True)
    base = ShowBase(windowType="offscreen")
    text_db = TextDB.load(CONTENT_ROOT)

    with open(os.path.join(FIXTURES, "events.json"), "r", encoding="utf-8") as f:
        fixtures = json.load(f)
    if event_id not in fixtures:
        print(f"未知夹具事件: {event_id}（可选：{[k for k in fixtures if not k.startswith('_')]}）")
        base.destroy()
        return 1
    render_event_fixture(base, text_db, fixtures[event_id], out_dir)
    print(f"事件截图已写入 {out_dir}")
    base.destroy()
    return 0

    with open(os.path.join(FIXTURES, "events.json"), "r", encoding="utf-8") as f:
        fixtures = json.load(f)
    if event_id not in fixtures:
        print(f"未知夹具事件: {event_id}（可选：{[k for k in fixtures if not k.startswith('_')]}）")
        base.destroy()
        return 1
    render_event_fixture(base, text_db, fixtures[event_id], out_dir)
    print(f"事件截图已写入 {out_dir}")
    base.destroy()
    return 0


# ----------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="standalone_d", description="开发者 D 独立测试")
    parser.add_argument("--text-check", action="store_true", help="校验正式文本（不依赖 panda3d）")
    parser.add_argument("--locale", default="zh_CN")
    parser.add_argument("--screen", choices=["all", *SCREEN_NAMES], help="渲染指定界面截图")
    parser.add_argument("--event", metavar="EVENT_ID", help="渲染夹具事件截图")
    parser.add_argument("--offscreen", action="store_true", help="离屏渲染（截图模式默认离屏）")
    parser.add_argument("--out", default=os.path.join(REPORT_DIR, "screens"))
    args = parser.parse_args(argv)

    if args.text_check:
        return run_text_check(args.locale)
    if args.screen:
        return run_screens(args.screen, args.out)
    if args.event:
        return run_event_fixture(args.event, args.out)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
