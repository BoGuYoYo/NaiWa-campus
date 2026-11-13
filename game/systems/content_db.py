"""规则内容加载与校验（开发者 B）。

运行期以 content/rules/*.json 为权威数据源；本模块负责：
    1. 读取五个 JSON 并建立索引；
    2. 结构校验（ID 正则、效果键白名单、运算符白名单、引用完整性、
       每个学期事件至少一个无条件选项）；
    3. 模块级缓存，避免 3000 局模拟反复解析文件。

校验失败抛 ContentError，消息中包含文件名、对象 ID 与具体键名，
以便内容修改者直接定位。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, NoReturn

from game.core.state import STAT_KEYS

ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
TEXT_ID_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")

ALLOWED_OPS = (">=", "<=", "==", ">", "<")
BASE_EFFECT_KEYS = ("academic", "stamina", "social", "interest", "mood", "energy")
EVENT_KINDS = ("semester", "relationship", "story")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RULES_DIR = PROJECT_ROOT / "content" / "rules"

RULE_FILES = {
    "activities": "activities.json",
    "events": "events.json",
    "npcs": "npcs.json",
    "endings": "endings.json",
    "daily_events": "daily_events.json",
}


class ContentError(Exception):
    """内容文件不合法。"""


def _fail(path: Path, obj_id: str | None, message: str) -> NoReturn:
    where = f"{path.name}"
    if obj_id:
        where += f" [{obj_id}]"
    raise ContentError(f"{where}: {message}")


def _check_id(path: Path, obj_id: Any, obj_desc: str) -> str:
    if not isinstance(obj_id, str) or not ID_RE.match(obj_id):
        _fail(path, str(obj_id), f"{obj_desc} 的 ID 不符合 ^[a-z][a-z0-9_]*$")
    return obj_id


def _check_effect_keys(path: Path, obj_id: str, effects: dict[str, Any],
                       npc_ids: set[str]) -> None:
    if not isinstance(effects, dict):
        _fail(path, obj_id, "effects 必须是对象")
    for key, value in effects.items():
        if key.startswith("rel."):
            npc = key[4:]
            if npc not in npc_ids:
                _fail(path, obj_id, f"效果键 {key} 引用了不存在的 NPC")
        elif key not in BASE_EFFECT_KEYS:
            _fail(path, obj_id, f"未知效果键 {key}（只允许 "
                                f"{', '.join(BASE_EFFECT_KEYS)} 或 rel.<npc_id>）")
        if not isinstance(value, int) or isinstance(value, bool):
            _fail(path, obj_id, f"效果键 {key} 的值必须是整数")


def _check_conditions(path: Path, obj_id: str, conditions: list[dict[str, Any]],
                      counters: set[str], npc_ids: set[str], prefix: str = "",
                      referenced: dict[str, str] | None = None) -> None:
    if conditions is None:
        _fail(path, obj_id, f"{prefix}conditions 不能为 null，使用 [] 表示无条件")
    if not isinstance(conditions, list):
        _fail(path, obj_id, f"{prefix}conditions 必须是数组")
    for cond in conditions:
        if not isinstance(cond, dict) or "type" not in cond:
            _fail(path, obj_id, f"{prefix}条件缺少 type")
        ctype = cond["type"]
        if ctype == "any":
            items = cond.get("items")
            if not isinstance(items, list) or not items:
                _fail(path, obj_id, f"{prefix}any 条件必须提供非空 items（空数组等价于恒假）")
            _check_conditions(path, obj_id, items, counters, npc_ids, prefix + "any.",
                              referenced)
            continue
        if ctype in ("stat",):
            if cond.get("key") not in STAT_KEYS:
                _fail(path, obj_id, f"{prefix}stat 条件 key 非法：{cond.get('key')}")
        elif ctype == "counter":
            if cond.get("key") not in counters:
                _fail(path, obj_id, f"{prefix}counter 条件引用了未定义的计数器：{cond.get('key')}")
        elif ctype == "counter_sum":
            keys = cond.get("keys")
            if not isinstance(keys, list) or not keys:
                _fail(path, obj_id, f"{prefix}counter_sum 条件必须提供非空 keys")
            unknown = [key for key in keys if key not in counters]
            if unknown:
                _fail(path, obj_id,
                      f"{prefix}counter_sum 条件引用了未定义的计数器：{unknown[0]}")
        elif ctype == "rel":
            if cond.get("key") not in npc_ids:
                _fail(path, obj_id, f"{prefix}rel 条件引用了不存在的 NPC：{cond.get('key')}")
        elif ctype in ("mood", "energy", "semester"):
            pass
        elif ctype in ("flag", "not_flag"):
            if not cond.get("key"):
                _fail(path, obj_id, f"{prefix}{ctype} 条件缺少 key")
            if referenced is not None:
                referenced.setdefault(str(cond["key"]), f"{path.name} [{obj_id}] {prefix}")
        else:
            _fail(path, obj_id, f"{prefix}未知条件类型 {ctype}")
        if ctype in ("stat", "counter", "counter_sum", "rel", "mood", "energy", "semester"):
            if cond.get("op") not in ALLOWED_OPS:
                _fail(path, obj_id, f"{prefix}运算符非法：{cond.get('op')}")
            if not isinstance(cond.get("value"), int) or isinstance(cond.get("value"), bool):
                _fail(path, obj_id, f"{prefix}条件的 value 必须是整数")


def _read(path: Path) -> Any:
    if not path.exists():
        raise ContentError(f"缺少规则文件：{path}")
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise ContentError(f"{path.name}: JSON 解析失败：{exc}") from exc
    except UnicodeDecodeError as exc:
        raise ContentError(f"{path.name}: 不是有效的 UTF-8 编码：{exc}") from exc


def _check_rows(path: Path, rows: Any) -> list[dict[str, Any]]:
    """顶层必须是对象数组：dict 之外的形态在这里拦下，避免运行期裸抛 AttributeError。"""
    if not isinstance(rows, list):
        _fail(path, None, "顶层必须是 JSON 数组")
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            _fail(path, str(index), f"第 {index} 项必须是对象，当前为 {type(row).__name__}")
    return rows


class ContentDB:
    """五个规则文件的只读索引。"""

    def __init__(self, rules_dir: Path | None = None) -> None:
        self.rules_dir = Path(rules_dir) if rules_dir else RULES_DIR
        self._load()

    # ---- 加载 -----------------------------------------------------------
    def _load(self) -> None:
        paths = {k: self.rules_dir / v for k, v in RULE_FILES.items()}
        raw_activities = _check_rows(paths["activities"], _read(paths["activities"]))
        raw_events = _check_rows(paths["events"], _read(paths["events"]))
        raw_npcs = _check_rows(paths["npcs"], _read(paths["npcs"]))
        raw_endings = _check_rows(paths["endings"], _read(paths["endings"]))
        raw_daily = _check_rows(paths["daily_events"], _read(paths["daily_events"]))

        # 全量收集「谁会产出旗标」：条件里引用的旗标必须在其中，
        # 否则一个拼错的 flag 永远不成立，事件/结局静默失效且没人报错。
        self.produced_flags: set[str] = set()
        self.referenced_flags: dict[str, str] = {}   # flag -> 首次引用处（报错用）

        self.npcs, npc_ids = self._load_npcs(paths, raw_npcs)
        counters = self._load_activities(paths, raw_activities, npc_ids)
        self._load_events(paths, raw_events, counters, npc_ids)
        self._load_endings(paths, raw_endings, counters, npc_ids)
        self._load_daily(paths, raw_daily, npc_ids)
        self._check_flag_references(paths)

        self.semester_event_by_no: dict[int, str] = {
            evt["semester_no"]: evt["id"]
            for evt in raw_events
            if evt.get("kind") == "semester"
        }

    def _load_npcs(self, paths: dict[str, Path],
                   raw_npcs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], set[str]]:
        self.npcs = raw_npcs
        npc_ids: set[str] = set()
        for npc in raw_npcs:
            npc_ids.add(_check_id(paths["npcs"], npc.get("id"), "NPC"))
        if len(npc_ids) != len(raw_npcs):
            _fail(paths["npcs"], None, "存在重复的 NPC ID")
        return raw_npcs, npc_ids

    def _load_activities(self, paths: dict[str, Path],
                         raw_activities: list[dict[str, Any]],
                         npc_ids: set[str]) -> set[str]:
        self.activities = raw_activities
        self.activities_by_id: dict[str, dict[str, Any]] = {}
        counters: set[str] = set()
        for act in raw_activities:
            act_id = _check_id(paths["activities"], act.get("id"), "活动")
            if act_id in self.activities_by_id:
                _fail(paths["activities"], act_id, "活动 ID 重复")
            _check_effect_keys(paths["activities"], act_id, act.get("effects", {}), npc_ids)
            self.produced_flags.update(str(f) for f in act.get("add_flags", []) or [])
            counter = act.get("counter")
            if counter:
                _check_id(paths["activities"], counter, "计数器")
                counters.add(counter)
            self.activities_by_id[act_id] = act
        self.counters: set[str] = set(counters)
        return counters

    def _load_events(self, paths: dict[str, Path], raw_events: list[dict[str, Any]],
                     counters: set[str], npc_ids: set[str]) -> None:
        self.events = raw_events
        self.events_by_id: dict[str, dict[str, Any]] = {}
        semester_seen: set[int] = set()
        for evt in raw_events:
            evt_id = _check_id(paths["events"], evt.get("id"), "事件")
            if evt_id in self.events_by_id:
                _fail(paths["events"], evt_id, "事件 ID 重复")
            self._check_event(paths, evt, evt_id, counters, npc_ids, semester_seen)
            self.events_by_id[evt_id] = evt

        self._check_next_event_ids(paths, raw_events)

        missing_sem = set(range(1, 9)) - semester_seen
        if missing_sem:
            _fail(paths["events"], None, f"缺少学期事件：{sorted(missing_sem)}")

    def _check_event(self, paths: dict[str, Path], evt: dict[str, Any], evt_id: str,
                     counters: set[str], npc_ids: set[str],
                     semester_seen: set[int]) -> None:
        kind = evt.get("kind")
        if kind not in EVENT_KINDS:
            _fail(paths["events"], evt_id,
                  f"kind 非法：{kind!r}，只允许 {', '.join(EVENT_KINDS)}")
        self._check_semester_no(paths, evt_id, kind, evt.get("semester_no"))

        choices = evt.get("choices") or []
        if not choices:
            _fail(paths["events"], evt_id, "事件至少需要 1 个选项")
        has_free = self._check_choices(paths, evt_id, choices, counters, npc_ids)

        if not has_free:
            # 所有选项都带条件时，条件一旦全不满足，事件就卡在选项页没法继续
            # （事件不允许中途退出）。学期事件本来就有这条约束，其它事件同样适用。
            _fail(paths["events"], evt_id, "事件必须至少有 1 个无条件选项（否则可能卡在选项页）")

        if evt.get("kind") == "semester":
            sem = evt["semester_no"]
            if sem in semester_seen:
                _fail(paths["events"], evt_id, f"学期 {sem} 有多个事件")
            semester_seen.add(int(sem))

    def _check_semester_no(self, paths: dict[str, Path], evt_id: str, kind: Any,
                           semester_no: Any) -> None:
        if kind == "semester":
            if (not isinstance(semester_no, int) or isinstance(semester_no, bool)
                    or not 1 <= semester_no <= 8):
                _fail(paths["events"], evt_id,
                      f"学期事件的 semester_no 必须是 1..8 的整数，当前为 {semester_no!r}")
        elif semester_no is not None and (
                not isinstance(semester_no, int) or isinstance(semester_no, bool)
                or semester_no < 0):
            _fail(paths["events"], evt_id,
                  f"非学期事件的 semester_no 必须是 >=0 的整数，当前为 {semester_no!r}")

    def _check_choices(self, paths: dict[str, Path], evt_id: str,
                       choices: list[dict[str, Any]], counters: set[str],
                       npc_ids: set[str]) -> bool:
        has_free = False
        choice_ids: set[str] = set()
        for choice in choices:
            cid = _check_id(paths["events"], choice.get("id"), "选项")
            if cid in choice_ids:
                _fail(paths["events"], evt_id, f"选项 ID 重复：{cid}")
            choice_ids.add(cid)
            conds = choice.get("conditions", [])
            if not conds:
                has_free = True
            _check_conditions(paths["events"], evt_id, conds, counters, npc_ids,
                              prefix=f"choice {cid} ", referenced=self.referenced_flags)
            _check_effect_keys(paths["events"], evt_id,
                               choice.get("effects", {}), npc_ids)
            self.produced_flags.update(str(f) for f in choice.get("add_flags", []) or [])
        return has_free

    def _check_next_event_ids(self, paths: dict[str, Path],
                              raw_events: list[dict[str, Any]]) -> None:
        """链式事件目标在全部事件载入后再校验（此时 events_by_id 已完整）。"""
        for evt in raw_events:
            for choice in evt.get("choices", []):
                target = choice.get("next_event_id")
                if target is None:
                    continue
                if not isinstance(target, str) or not ID_RE.match(target):
                    _fail(paths["events"], evt["id"],
                          f"选项 {choice['id']} 的 next_event_id 非法：{target!r}")
                if target not in self.events_by_id:
                    _fail(paths["events"], evt["id"],
                          f"选项 {choice['id']} 指向不存在的事件 {target}")

    def _load_endings(self, paths: dict[str, Path], raw_endings: list[dict[str, Any]],
                      counters: set[str], npc_ids: set[str]) -> None:
        self.endings = raw_endings
        self.endings_by_id: dict[str, dict[str, Any]] = {}
        priorities: dict[int, str] = {}
        for ending in raw_endings:
            eid = _check_id(paths["endings"], ending.get("id"), "结局")
            _check_conditions(paths["endings"], eid, ending.get("conditions", []),
                              counters, npc_ids, referenced=self.referenced_flags)
            priority = ending.get("priority")
            if not isinstance(priority, int) or isinstance(priority, bool):
                _fail(paths["endings"], eid, f"priority 必须是整数，当前为 {priority!r}")
            if priority in priorities:
                # 同优先级的两个结局谁生效取决于文件顺序 —— 改一行顺序就换结局，
                # 而且不会有任何报错。优先级冲突必须直接拦下来。
                _fail(paths["endings"], eid,
                      f"priority {priority} 与 {priorities[priority]} 重复")
            priorities[priority] = eid
            self.endings_by_id[eid] = ending
        if "ending_mediocre" not in self.endings_by_id:
            _fail(paths["endings"], None, "缺少无条件兜底结局 ending_mediocre")
        if not any(not ending.get("conditions") for ending in raw_endings):
            _fail(paths["endings"], None,
                  "至少要有 1 个无条件结局（否则条件全不满足时结算不出结局）")

    def _load_daily(self, paths: dict[str, Path], raw_daily: list[dict[str, Any]],
                    npc_ids: set[str]) -> None:
        self.daily_events = raw_daily
        seen_daily: set[str] = set()
        for daily in raw_daily:
            did = _check_id(paths["daily_events"], daily.get("id"), "日常事件")
            if did in seen_daily:
                _fail(paths["daily_events"], did, "日常事件 ID 重复")
            seen_daily.add(did)
            _check_effect_keys(paths["daily_events"], did, daily.get("effects", {}), npc_ids)
            self.produced_flags.update(str(f) for f in daily.get("add_flags", []) or [])

    def _check_flag_references(self, paths: dict[str, Path]) -> None:
        """条件里引用的旗标必须由某处产出（规则文件或代码）。

        旧版对 flag / not_flag 只检查"key 非空"：拼错一个字母，该条件永远不成立，
        相关事件/结局静默失效，跑几千局模拟都看不出来。
        """
        produced = set(self.produced_flags)
        # 代码里产出的旗标：计数器达标、熬夜、关系阶段。
        try:
            from game.systems import spec_data
        except Exception:  # pragma: no cover - 规则库单独使用时没有 spec_data
            spec_data = None
        if spec_data is not None:
            for npc_id in sorted({npc["id"] for npc in self.npcs}):
                for stage in getattr(spec_data, "REL_STAGES", ()):
                    produced.add(f"{npc_id}_stage{stage['stage']}")
                    require = stage.get("require_flag")
                    if require:
                        produced.add(str(require).format(npc_id=npc_id))
            for name in dir(spec_data):
                if name.endswith("_FLAG"):
                    value = getattr(spec_data, name)
                    if isinstance(value, str):
                        produced.add(value)
            # 活动表里的"计数器达标 / 熬夜"旗标（模拟器与正式流程都用同一份表）
            for act in getattr(spec_data, "ACTIVITIES", ()) or ():
                for key in ("flag_when_counter", "late_flag_on_daily_count"):
                    rule = act.get(key)
                    if isinstance(rule, dict) and rule.get("flag"):
                        produced.add(str(rule["flag"]))

        unknown = {flag: where for flag, where in self.referenced_flags.items()
                   if flag not in produced}
        if unknown:
            detail = "；".join(f"{flag}（{where}）" for flag, where in sorted(unknown.items()))
            _fail(paths["events"], None, f"条件引用了从未产出的旗标：{detail}")

    # ---- 便捷访问 -------------------------------------------------------
    def activity(self, activity_id: str) -> dict[str, Any] | None:
        return self.activities_by_id.get(activity_id)

    def event(self, event_id: str) -> dict[str, Any] | None:
        return self.events_by_id.get(event_id)

    def npc(self, npc_id: str) -> dict[str, Any] | None:
        return next((n for n in self.npcs if n["id"] == npc_id), None)

    def semester_event(self, semester_no: int) -> dict[str, Any] | None:
        event_id = self.semester_event_by_no.get(semester_no)
        return self.events_by_id.get(event_id) if event_id else None


_CACHE: dict[str, tuple[tuple[int, ...], ContentDB]] = {}


def _content_stamp(rules_dir: Path) -> tuple[int, ...]:
    """五份 JSON 的 mtime 序列，任一份变化都会改变该戳。

    用序列而不是最大值：若被改的文件恰好不是最新的那份（或 mtime 被回拨），
    取最大值的实现会漏判，导致继续用旧缓存。
    """
    stamps: list[int] = []
    for filename in RULE_FILES.values():
        path = rules_dir / filename
        try:
            stamps.append(path.stat().st_mtime_ns)
        except FileNotFoundError:
            stamps.append(-1)
    return tuple(stamps)


def get_db(rules_dir: str | Path | None = None) -> ContentDB:
    """取规则库。

    规则目录内任一 JSON 的 mtime 变化时自动重建，开发期改内容无需重启进程；
    未变化时返回同一实例（避免 3000 局模拟反复解析）。
    """
    directory = Path(rules_dir).resolve() if rules_dir else RULES_DIR
    key = str(directory)
    stamp = _content_stamp(directory)
    cached = _CACHE.get(key)
    if cached is not None and cached[0] == stamp:
        return cached[1]
    db = ContentDB(directory)
    _CACHE[key] = (stamp, db)
    return db


def reset_cache() -> None:
    _CACHE.clear()
