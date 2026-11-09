"""按 content/text 的两份 JSON 重新生成 UI 文本索引（docs/ui/text_index.csv）。

索引是给"文案 → 界面"对照用的：`text_id,chars,screen`。
screen 由 ID 前缀推断，规则集中在 SCREEN_RULES 里，改规则就改这一张表，
避免手工维护 CSV 与 strings.json 漂移（历史上改过活动 ID 之后索引就过期了）。

用法：
    python tools/make_text_index.py            # 写 docs/ui/text_index.csv
    python tools/make_text_index.py --check    # 只校验是否已同步，退出码 0/1
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_DIR = ROOT / "content" / "text" / "zh_CN"
TARGET = ROOT / "docs" / "ui" / "text_index.csv"

#: 前缀 -> 界面名（按顺序匹配，命中即停）
SCREEN_RULES: tuple[tuple[str, str], ...] = (
    ("ui.hud.", "HUD"),
    ("ui.prompt.", "交互提示"),
    ("ui.result.", "结果面板"),
    ("ui.dialogue.", "对话框"),
    ("ui.event.", "事件场景"),
    ("ui.day_summary.", "日结算"),
    ("ui.tab.", "状态面板"),
    ("ui.settings.", "设置"),
    ("ui.save.", "存读档"),
    ("ui.graduation.", "毕业界面"),
    ("ui.menu.resume", "暂停菜单"),
    ("ui.menu.", "主菜单"),
    ("ui.main_menu.", "主菜单"),
    ("tut.", "新手教程"),
    ("err.", "错误提示"),
    ("ia.", "交互提示"),
    ("insp.", "查看点"),
    ("npc.", "对话框"),
    ("daily.", "日常事件"),
    ("ending.", "毕业界面"),
    ("act.", "结果面板"),
    ("evt.", "事件场景"),
    ("stat.", "数值显示"),
)


def screen_for(text_id: str) -> str:
    for prefix, screen in SCREEN_RULES:
        if text_id.startswith(prefix):
            return screen
    return "其他"


def build_rows() -> list[tuple[str, str, str]]:
    strings = json.loads((TEXT_DIR / "strings.json").read_text(encoding="utf-8"))
    dialogues = json.loads((TEXT_DIR / "dialogues.json").read_text(encoding="utf-8"))
    rows: list[tuple[str, str, str]] = []
    for text_id, value in strings.items():
        rows.append((text_id, str(len(value)), screen_for(text_id)))
    for text_id, page in dialogues.items():
        chars = sum(len(line) for line in page.get("lines", []))
        screen = "对话框" if text_id.startswith("evt.") else screen_for(text_id)
        rows.append((text_id, str(chars), screen))
    return rows


def render_csv(rows: list[tuple[str, str, str]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["text_id", "chars", "screen"])
    writer.writerows(rows)
    return buffer.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="make_text_index")
    parser.add_argument("--check", action="store_true", help="只校验，不写文件")
    args = parser.parse_args(argv)

    rows = build_rows()
    text = render_csv(rows)
    if args.check:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != text:
            print(f"[text-index] 与内容不同步：{TARGET.relative_to(ROOT)}（请运行 python tools/make_text_index.py）")
            return 1
        print(f"[text-index] 已同步：{len(rows)} 行")
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(text, encoding="utf-8")
    print(f"[text-index] 写入 {TARGET.relative_to(ROOT)}：{len(rows)} 行")
    return 0


if __name__ == "__main__":
    sys.exit(main())
