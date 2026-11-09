"""整合期临时文案生成（A）：给 B 的规则补上 D 还没写的 text_id。

背景：B 的规则系统只产出 text_id（`evt.<id>.choice.<cid>` / `talk.<npc>.result.1` …），
正文归 D。第四周合入 B 时，关系事件、日常事件、部分学期事件选项还没有文案，
界面会直接显示 `#text_id`。这里按规则 JSON 里的信息生成**可读的占位文案**，
让整合期试玩不是满屏井号；生成的 id 记在 `_placeholder_ids.json` 里，D 补正文时按它替换。

用法：
    python tools/gen_placeholder_text.py           # 只补缺失的，已有文案不动
    python tools/gen_placeholder_text.py --check    # 只报告缺多少，不写文件
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "content" / "rules"
TEXT_DIR = ROOT / "content" / "text" / "zh_CN"
STRINGS = TEXT_DIR / "strings.json"
DIALOGUES = TEXT_DIR / "dialogues.json"  # 仅用于存在性检查
MANIFEST = TEXT_DIR / "_placeholder_ids.json"

STAT_NAMES = {
    "academic": "学业",
    "stamina": "体力",
    "social": "社交",
    "interest": "兴趣",
    "energy": "精力",
    "mood": "心情",
}

LOCK_TEXT = "（条件未满足）"
GENERIC_CHOICE = "继续"
GENERIC_RESULT = "就这样，奶娃做了决定。"


def load(name: str):
    return json.loads((RULES / name).read_text(encoding="utf-8"))


def npc_names() -> dict[str, str]:
    return {npc["id"]: npc.get("name", npc["id"]) for npc in load("npcs.json")}


def _rel_npc_of(event_id: str) -> str | None:
    """`rel_npc_sumo_2` -> `npc_sumo`；不是关系事件返回 None。"""
    if not event_id.startswith("rel_"):
        return None
    parts = event_id.split("_")
    if len(parts) < 3:
        return None
    return "_".join(parts[1:-1])  # 去掉 rel_ 前缀和末尾的段号


def effect_summary(effects: dict, names: dict[str, str], limit: int = 12) -> str:
    """把 effects 写成「社交+4 陈朗+10」。

    选项文案有 12 字上限（D 的 `TextDB.validate()`），超出就按顺序丢掉尾部效果。
    """
    parts: list[str] = []
    for key, value in effects.items():
        if key.startswith("rel."):
            npc = key[4:]
            label = names.get(npc, npc)
        else:
            label = STAT_NAMES.get(key, key)
        suffix = f"{value:+d}" if isinstance(value, int) else f"{value}"
        parts.append(f"{label}{suffix}")
    while parts and len(" ".join(parts)) > limit:
        parts.pop()
    return " ".join(parts)


def inherit_existing_text(strings: dict[str, str], manifest: dict[str, str]) -> dict[str, str]:
    """把 D 已经写好的选项/结果文案搬到 B 的 choice_id 上。

    D 给同一批学期事件写的是自己的 choice_id（`follow_chenlang`），B 的规则用
    `fair_club` —— 两者顺序和意图一一对应。这里按**位置**对齐：某事件的选项数
    与 D 的文案数相等时，第 k 条文案就给 B 的第 k 个选项，避免让占位文案把
    D 的真文案挤掉。
    """
    inherited: dict[str, str] = {}
    for event in load("events.json"):
        event_id = event["id"]
        choices = event.get("choices", [])
        for suffix in ("choice", "result"):
            prefix = f"evt.{event_id}.{suffix}."
            d_keys = [
                key for key in strings
                if key.startswith(prefix) and key not in manifest
            ]
            if len(d_keys) != len(choices):
                continue
            for choice, key in zip(choices, d_keys):
                inherited[f"{prefix}{choice['id']}"] = strings[key]
    return inherited


def build_placeholders() -> dict[str, str]:
    """返回 {text_id: 占位文案}，只包含"该有但可能缺"的 id。"""
    names = npc_names()
    out: dict[str, str] = {}

    for event in load("events.json"):
        event_id = event["id"]
        rel_npc = _rel_npc_of(event_id)
        for choice in event.get("choices", []):
            choice_id = choice["id"]
            label = effect_summary(choice.get("effects", {}), names) or GENERIC_CHOICE
            out[f"evt.{event_id}.choice.{choice_id}"] = label
            if rel_npc:
                npc_name = names.get(rel_npc, rel_npc)
                out[f"evt.{event_id}.result.{choice_id}"] = (
                    f"和{npc_name}聊了很久，关系又近了一点。"
                )
            else:
                out[f"evt.{event_id}.result.{choice_id}"] = (
                    f"就这样定了：{label}。" if label != GENERIC_CHOICE else GENERIC_RESULT
                )
            out[f"evt.{event_id}.lock.{choice_id}"] = LOCK_TEXT

    for npc in load("npcs.json"):
        npc_id = npc["id"]
        npc_name = npc.get("name", npc_id)
        out[f"talk.{npc_id}.result.1"] = f"和{npc_name}聊了几句，气氛很轻松。"

    for daily in load("daily_events.json"):
        daily_id = daily["id"]
        title = daily.get("title", daily_id)
        # HUD 用的短键：去掉 daily_ 前缀，避免出现 ui.hud.daily.daily_xxx
        hud_key = daily_id.removeprefix("daily_")
        out[f"evt.{daily_id}.body.1"] = f"{title}。奶娃把这件事记在了心里。"
        out[f"ui.hud.daily.{hud_key}"] = f"【{title}】"

    for activity in load("activities.json"):
        activity_id = activity["id"]
        for n in (1, 2, 3):
            out.setdefault(f"act.{activity_id}.result.{n}", f"{activity.get('name', activity_id)}的日常记录。")

    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="补齐 B 规则用到的 text_id（占位文案）")
    parser.add_argument("--check", action="store_true", help="只统计缺失，不写文件")
    args = parser.parse_args(argv)

    strings = json.loads(STRINGS.read_text(encoding="utf-8"))
    dialogues: dict = {}
    if DIALOGUES.exists():
        dialogues = json.loads(DIALOGUES.read_text(encoding="utf-8"))
    manifest: dict[str, str] = {}
    if MANIFEST.exists():
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    # D 的正式文案 = 现有键里去掉"上一轮 A 生成的占位"
    official = (set(strings) - set(manifest)) | set(dialogues)

    candidates = build_placeholders()
    candidates.update(inherit_existing_text(strings, manifest))

    todo = {
        key: value for key, value in candidates.items()
        if key not in official and strings.get(key) != value
    }
    if args.check:
        print(f"规则用到 {len(candidates)} 条 text_id；D 已写 {len(candidates) - len(todo)} 条，缺 {len(todo)} 条")
        for key in list(todo)[:10]:
            print("  ", key)
        return 0 if not todo else 1

    if not todo:
        print("没有需要补的 text_id")
        return 0

    strings.update(todo)
    STRINGS.write_text(
        json.dumps(strings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    for key in todo:
        manifest[key] = "A 生成/迁移（整合期占位），待 D 补正式文案"
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    by_family: dict[str, int] = {}
    for key in todo:
        parts = key.split(".")
        family = ".".join(parts[:2])
        by_family[family] = by_family.get(family, 0) + 1
    print(f"写入 {len(todo)} 条：")
    for family, count in sorted(by_family.items(), key=lambda kv: -kv[1])[:12]:
        print(f"  {family}: {count}")
    print(f"清单：{MANIFEST.relative_to(ROOT)}（D 按此清单替换正式文案）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
