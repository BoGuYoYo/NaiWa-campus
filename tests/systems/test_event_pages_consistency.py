"""数据一致性守卫：`events.json` 声明的 pages 必须覆盖 `dialogues.json` 里该事件的全部正文本。

背景（BUG-26，BUG-0 修复引出的回归）：
`EventSceneAdapter._build_view()` 改成从 `EventService.get_view()` 取视图后，分页来源
从"扫描 TextDB 的 `evt.<id>.body.*`"变成"`events.json` 的 `pages` 列表"。
而 `events.json` 里每个事件**只登记了 `body.1`**，`dialogues.json` 却有 2~5 页：

    sem_1_club_fair 声明 1 页 / 实际 4 页
    story_opening   声明 1 页 / 实际 5 页
    rel_npc_sumo_2  声明 1 页 / 实际 4 页
    …共 17 个事件、丢失 33 页正文

后果不只是"少看几页新闻"：
1. 只有 1 页 = 永远是"最后一页" → **选项面板在第 1 页就弹出来**（玩家正文没看完就能选）；
2. 带 `speaker` / `portrait` 的页全部在 body.2 之后（body.1 一律是旁白）→
   **玩家永远看不到任何立绘**，观感就是"人物头像消失"。
"""

from __future__ import annotations

import json
import re

import pytest

import game.config as config


def _load(name: str):
    return json.loads((config.resource_root() / "content" / name).read_text(encoding="utf-8"))


def _actual_pages() -> dict[str, int]:
    dial = _load("text/zh_CN/dialogues.json")
    counts: dict[str, int] = {}
    for key in dial:
        m = re.match(r"evt\.(.+)\.body\.(\d+)$", key)
        if m:
            counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    return counts


@pytest.mark.xfail(
    strict=True,
    reason="BUG-26：events.json 每个事件只登记 body.1，dialogues.json 有 2~5 页 → "
           "正文丢失 33 页、选项提前出现、立绘永远不显示；修好后本条会 XPASS，请删掉 xfail 标记",
)
def test_event_pages_cover_all_dialogue_bodies() -> None:
    events = _load("rules/events.json")
    actual = _actual_pages()

    short = {}
    for event in events:
        eid = event["id"]
        declared = len([p for p in event.get("pages", []) if ".body." in p])
        if eid in actual and declared < actual[eid]:
            short[eid] = f"声明 {declared} 页 / 实际 {actual[eid]} 页"

    assert short == {}, f"以下事件的正文本没有全部登记进 pages：{short}"


def test_declared_pages_exist_in_dialogues() -> None:
    """反向：声明了的页必须真的存在（防手写 pages 打错 id）。"""
    events = _load("rules/events.json")
    dial = _load("text/zh_CN/dialogues.json")

    missing = []
    for event in events:
        for page_id in event.get("pages", []):
            if page_id not in dial:
                missing.append((event["id"], page_id))

    assert missing == [], f"events.json 声明的页在 dialogues.json 里不存在：{missing}"


def test_pages_have_portraits_after_first_page() -> None:
    """佐证 BUG-26 的观感后果：带立绘的页都在 body.2 之后。

    这条现在是**绿的**（说明数据本身有立绘），用来钉住"立绘没显示不是数据缺"。
    """
    dial = _load("text/zh_CN/dialogues.json")
    first_pages_with_portrait = [
        key for key, page in dial.items()
        if re.match(r"evt\..+\.body\.1$", key) and page.get("portrait")
    ]
    assert first_pages_with_portrait == [], (
        f"意外的数据形态（body.1 竟然带立绘）：{first_pages_with_portrait}"
    )
    portrait_pages = [k for k, p in dial.items() if p.get("portrait")]
    assert portrait_pages, "dialogues 里一个带立绘的页都没有"


# --------------------------------------------------------------------------- #
# 同一"rules 与 TextDB 各写一份"的对偶性，在 choices / result / lock 上也成立。
# 这三类现在是齐的（实测 0 缺失），所以是**常驻绿守卫**：将来谁漏配一条，
# 界面就会显示 `#evt.xxx.result.yyy` 这类原始 id（与 BUG-10 同一症状）。
# --------------------------------------------------------------------------- #
def test_every_choice_has_choice_result_and_lock_text() -> None:
    events = _load("rules/events.json")
    strings = _load("text/zh_CN/strings.json")

    missing: dict[str, list[str]] = {}
    for event in events:
        for choice in event.get("choices", []):
            for kind in ("choice", "result", "lock"):
                key = f"evt.{event['id']}.{kind}.{choice['id']}"
                if key not in strings:
                    missing.setdefault(kind, []).append(key)

    assert missing == {}, f"选项文案缺失（界面会显示原始 id）：{missing}"


def test_event_pages_are_ordered_starting_at_one() -> None:
    """声明的页必须从 body.1 起连续编号——防手写 pages 时漏中间页/跳号。"""
    events = _load("rules/events.json")

    broken = {}
    for event in events:
        numbers = []
        for page_id in event.get("pages", []):
            if ".body." in page_id:
                tail = page_id.rsplit(".", 1)[-1]
                numbers.append(int(tail) if tail.isdigit() else -1)
        if numbers and numbers != list(range(1, len(numbers) + 1)):
            broken[event["id"]] = numbers

    assert broken == {}, f"pages 编号不连续/不从 1 起：{broken}"


# --------------------------------------------------------------------------- #
# 第三态的正面防线（BUG-25）：告示里"有 portrait 但加载失败"会静默落成灰块，
# 所以数据侧必须保证每个 portrait id 既登记在 manifest、文件也真的存在。
# 同类：speaker 必须有名字文案与立牌资源（与 BUG-15 串起来）。
# --------------------------------------------------------------------------- #
def _manifest() -> dict[str, dict]:
    import json

    path = config.resource_root() / "assets" / "manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data["assets"] if isinstance(data, dict) else data
    return {e["id"]: e for e in entries}


def test_dialogue_portraits_are_registered_and_on_disk() -> None:
    dial = _load("text/zh_CN/dialogues.json")
    entries = _manifest()
    assets_root = config.resource_root() / "assets"

    unregistered, missing_files = [], []
    for key, page in dial.items():
        pid = page.get("portrait")
        if not pid:
            continue
        entry = entries.get(pid)
        if entry is None:
            unregistered.append((key, pid))
            continue
        if not (assets_root / entry["path"]).exists():
            missing_files.append((key, pid, entry["path"]))

    assert unregistered == [], f"portrait 未在 manifest 登记：{unregistered}"
    assert missing_files == [], f"portrait 文件不存在：{missing_files}"


def test_dialogue_speakers_have_name_text_and_idle_asset() -> None:
    dial = _load("text/zh_CN/dialogues.json")
    strings = _load("text/zh_CN/strings.json")
    entries = _manifest()

    problems = []
    for key, page in dial.items():
        speaker = page.get("speaker")
        if not speaker:
            continue
        short = str(speaker).replace("npc_", "")
        if f"npc.{short}.name" not in strings:
            problems.append((key, speaker, "缺名字文案"))
        if f"char_npc_{short}_idle" not in entries:
            problems.append((key, speaker, "缺 char_npc_*_idle 立牌资源"))

    assert problems == [], (
        "说话人缺文案/资源（会出现：有人在说话但没有名字或没有立牌）："
        f"{problems}"
    )
