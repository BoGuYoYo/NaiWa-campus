"""模拟器命令行（开发者 B，手册 B11）。

    python -m game.sim --strategy academic --seed 42 --out reports/academic_42.json
    python -m game.sim --strategy all --seeds 0-199 --summary
    python -m game.sim --random 3000 --summary --out reports/random_3000.json
    python -m game.sim --strategy academic --seed 42 --save-resume --out ...

退出码：0 成功；1 结局与 --expect 不符；2 运行异常。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from game.sim import simulator
from game.sim.strategies import build_strategy
from game.systems import spec_data


def parse_seeds(text: str) -> list[int]:
    seeds: list[int] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            seeds.extend(range(int(start), int(end) + 1))
        else:
            seeds.append(int(part))
    return seeds


def _write(path: str, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")


def _run_one(strategy_name: str, seed: int, save_resume: bool) -> dict[str, Any]:
    strategy = build_strategy(strategy_name, seed)
    return simulator.run(strategy, seed, save_resume=save_resume)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m game.sim",
                                     description="奶娃：大学四年 无界面模拟器")
    parser.add_argument("--strategy", default="balanced",
                        help="策略名，可选 all / " + " / ".join(spec_data.STRATEGY_NAMES)
                             + " / random")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--seeds", default=None, help="种子范围，例如 0-199 或 0,1,2")
    parser.add_argument("--random", type=int, default=0, help="随机策略局数，例如 3000")
    parser.add_argument("--summary", action="store_true", help="打印结局分布")
    parser.add_argument("--out", default=None, help="输出 JSON 路径")
    parser.add_argument("--expect", default=None, help="期望结局 ID，不符时退出码 1")
    parser.add_argument("--save-resume", action="store_true",
                        help="第 7 天执行 to_dict/from_dict 续跑，验证存档一致性")
    args = parser.parse_args(argv)

    try:
        # ---- 随机基线 ---------------------------------------------------
        if args.random:
            counter: Counter[str] = Counter()
            runs: list[dict[str, Any]] = []
            for seed in range(args.random):
                report = _run_one("random", seed, args.save_resume)
                counter[report["ending_id"]] += 1
                runs.append({
                    "seed": seed,
                    "ending_id": report["ending_id"],
                    "min_end_energy": report["min_end_energy"],
                })
            payload = {
                "mode": "random",
                "total": args.random,
                "distribution": dict(counter.most_common()),
                "runs": runs,
            }
            if args.summary:
                print(f"随机策略 {args.random} 局：{dict(counter.most_common())}")
            if args.out:
                _write(args.out, payload)
            return 0

        # ---- 指定策略 / 全部策略 ---------------------------------------
        if args.seeds:
            seeds = parse_seeds(args.seeds)
            names = (list(spec_data.STRATEGY_NAMES) if args.strategy == "all"
                     else [args.strategy])
            distribution: dict[str, dict[str, int]] = {}
            mismatches: list[str] = []
            for name in names:
                counter = Counter()
                expected = (spec_data.STRATEGIES.get(name) or {}).get("expected_ending")
                for seed in seeds:
                    report = _run_one(name, seed, args.save_resume)
                    counter[report["ending_id"]] += 1
                    if expected and report["ending_id"] != expected:
                        mismatches.append(f"{name}/{seed} -> {report['ending_id']}"
                                          f"（期望 {expected}）")
                distribution[name] = dict(counter.most_common())
            payload = {
                "mode": "batch",
                "seeds": {"from": seeds[0], "to": seeds[-1], "count": len(seeds)},
                "distribution": distribution,
                "mismatches": mismatches,
            }
            if args.summary:
                for name, dist in distribution.items():
                    total = sum(dist.values())
                    detail = "，".join(f"{k} {v}" for k, v in dist.items())
                    print(f"{name}: {detail}（共 {total} 局）")
                if mismatches:
                    print(f"未命中 {len(mismatches)} 局：")
                    for line in mismatches[:10]:
                        print("  " + line)
            if args.out:
                _write(args.out, payload)
            return 0 if not mismatches else 1

        # ---- 单局（--strategy all 即同一 seed 跑全部策略）-----------------
        names = (list(spec_data.STRATEGY_NAMES) if args.strategy == "all"
                 else [args.strategy])
        reports = [_run_one(name, args.seed, args.save_resume) for name in names]
        if args.summary:
            for report in reports:
                print(f"{report['strategy']} seed={args.seed} -> {report['ending_id']} "
                      f"({report['elapsed_ms']} ms，最低日末精力 {report['min_end_energy']})")
        if args.out:
            payload = reports[0] if len(reports) == 1 else {"mode": "single",
                                                            "seed": args.seed,
                                                            "runs": reports}
            _write(args.out, payload)
        if args.expect:
            for report in reports:
                if report["ending_id"] != args.expect:
                    print(f"结局不符：{report['strategy']} 实际 {report['ending_id']}，"
                          f"期望 {args.expect}")
                    return 1
        return 0
    except Exception as exc:  # noqa: BLE001 - 命令行需要统一退出码
        print(f"运行异常：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
