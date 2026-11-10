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
