"""由 spec_data 导出规则 JSON 与期望基线（开发者 B）。

用法：
    python -m game.systems.spec_export            # 写入 content/rules/*.json
    python -m game.systems.spec_export --check    # 只比对，不一致时退出码 1

设计说明：spec_data 是“数值唯一来源”，JSON 是“内容载体”。运行期只读 JSON，
因此改 JSON 会立刻改变行为（满足“改收益值后策略回归能报错”的验收项）；
两者不一致由 tests/systems/test_spec_sync.py 守护。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from game.systems import spec_data

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RULES_DIR = PROJECT_ROOT / "content" / "rules"
EXPECTED_DIR = PROJECT_ROOT / "tests" / "expected"


def build_rules() -> dict[str, Any]:
    """拼出五个规则文件的内容。"""
    activities = [dict(item) for item in spec_data.ACTIVITIES]
    events = (
        [dict(item) for item in spec_data.SEMESTER_EVENTS]
        + [dict(item) for item in spec_data.RELATION_EVENTS]
        + [dict(item) for item in spec_data.STORY_EVENTS]
    )
    return {
        "activities.json": activities,
        "events.json": events,
        "npcs.json": [dict(item) for item in spec_data.NPCS],
        "endings.json": [dict(item) for item in spec_data.ENDINGS],
        "daily_events.json": [dict(item) for item in spec_data.DAILY_EVENTS],
    }


def build_strategies() -> dict[str, Any]:
    """导出为 JSON 兼容结构：prefs 的键统一为字符串，便于与基线文件直接比对。"""
    strategies: dict[str, Any] = {}
    for name, cfg in spec_data.STRATEGIES.items():
        item = dict(cfg)
        item["prefs"] = {str(k): v for k, v in (cfg.get("prefs") or {}).items()}
        strategies[name] = item
    return strategies


def _dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="由 spec_data 导出规则 JSON")
    parser.add_argument("--check", action="store_true", help="只比对，不写盘")
    parser.add_argument("--rules-dir", default=str(RULES_DIR))
    args = parser.parse_args(argv)

    rules_dir = Path(args.rules_dir)
    problems: list[str] = []
    for filename, payload in build_rules().items():
        target = rules_dir / filename
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        if args.check:
            current = target.read_text(encoding="utf-8") if target.exists() else ""
            if current != text:
                problems.append(filename)
        else:
            _dump(target, payload)

    if args.check:
        if problems:
            print("规则 JSON 与 spec_data 不一致：" + ", ".join(problems))
            return 1
        print("规则 JSON 与 spec_data 一致")
        return 0

    strategies_path = EXPECTED_DIR / "strategies.json"
    if not args.check:
        _dump(strategies_path, build_strategies())
    print(f"已导出 {len(build_rules())} 个规则文件到 {rules_dir}")
    print(f"已导出策略定义到 {strategies_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
