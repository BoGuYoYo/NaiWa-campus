"""TextDB：全部中文文本的唯一读取入口（D4）。

- strings.json：扁平键值（不含换行的短文本）。
- dialogues.json：事件分页（含说话人 / 头像 / 行列表）。
- get() 缺失返回 「#text_id」 并记录日志；占位符使用 {name} 形式。
- 本模块不依赖 panda3d，可在独立测试中直接使用。
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

_log = logging.getLogger("naiwa.ui.text_db")

#: 每行 / 每页的硬性排版上限（D6 写作规范）
MAX_LINE_CHARS = 26
MAX_LINES_PER_PAGE = 4
MAX_CHOICE_CHARS = 12
MAX_ACT_RESULT_CHARS = 40
MAX_DAILY_BODY_CHARS = 50
MAX_INSPECT_CHARS = 80
MAX_ENDING_PARAGRAPH_CHARS = 100

_DIALOGUE_KEYS = ("speaker", "portrait", "lines")


def wrap_line(text: str, max_chars: int = MAX_LINE_CHARS) -> list[str]:
    """按标点优先断行，把超长文本拆成不超过 max_chars 的若干行。

    只在“行内换行”意义上使用；剧情正文应当由写作者预先断好，
    本函数用于错误兜底与 UI 长提示。
    """
    if len(text) <= max_chars:
        return [text]
    breaks = "，。！？；、：”』）】…"
    lines: list[str] = []
    current = ""
    for ch in text:
        current += ch
        if len(current) >= max_chars and (ch in breaks or len(current) == max_chars):
            lines.append(current)
            current = ""
    if current:
        lines.append(current)
    return lines


def paginate_lines(lines: list[str], per_page: int = MAX_LINES_PER_PAGE) -> list[list[str]]:
    """把行列表切成每页至多 per_page 行的页面（D-ST-03）。"""
    if per_page <= 0:
        raise ValueError("per_page must be positive")
    return [lines[i : i + per_page] for i in range(0, len(lines), per_page)]


class TextDB:
    """文本数据库。加载失败时保持空库，get() 一律返回 「#text_id」。"""

    def __init__(
        self,
        strings: dict[str, str] | None = None,
        dialogues: dict[str, dict] | None = None,
        locale: str = "zh_CN",
    ) -> None:
        self.locale = locale
        self.strings: dict[str, str] = dict(strings or {})
        self.dialogues: dict[str, dict] = dict(dialogues or {})

    # ------------------------------------------------------------------
    # 加载
    # ------------------------------------------------------------------
    @classmethod
    def load(cls, content_root: str, locale: str = "zh_CN") -> "TextDB":
        """从 <content_root>/text/<locale>/ 加载两份 JSON。"""
        base = os.path.join(content_root, "text", locale)
        db = cls(locale=locale)
        strings_path = os.path.join(base, "strings.json")
        dialogues_path = os.path.join(base, "dialogues.json")
        try:
            with open(strings_path, "r", encoding="utf-8") as f:
                db.strings = json.load(f)
        except (OSError, ValueError):
            _log.error("无法加载文本文件: %s", strings_path, exc_info=True)
        try:
            with open(dialogues_path, "r", encoding="utf-8") as f:
                db.dialogues = json.load(f)
        except (OSError, ValueError):
            _log.error("无法加载剧情文件: %s", dialogues_path, exc_info=True)
        return db

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def has(self, text_id: str) -> bool:
        return text_id in self.strings or text_id in self.dialogues

    def get(self, text_id: str, **fmt: Any) -> str:
        """按 text_id 取文本；缺失返回 「#text_id」 并记录日志。

        占位符使用 str.format 语法（{name}）。**只要文本里含占位符就必须
        把参数传齐**：少传或传错都会返回原文并记 error 日志，绝不静默
        留一个 {xxx} 在界面上（D-ST-05）。
        需要原样取出模板（例如二次格式化）请用 get_raw()。
        """
        raw = self.get_raw(text_id)
        if raw.startswith("#") and raw == f"#{text_id}":
            return raw
        if "{" not in raw:
            return raw
        try:
            return raw.format(**fmt)
        except (KeyError, IndexError, ValueError):
            _log.error(
                "占位符错误 text_id=%s fmt=%s raw=%r", text_id, sorted(fmt), raw
            )
            return raw

    def get_raw(self, text_id: str) -> str:
        """不做格式化地取原文；缺失返回 「#text_id」 并记录 warn。"""
        raw = self.strings.get(text_id)
        if raw is None:
            _log.warning("缺失 text_id: %s", text_id)
            return f"#{text_id}"
        return raw

    def get_dialogue(self, text_id: str) -> dict | None:
        """取事件分页定义；缺失时记录日志并返回 None。"""
        page = self.dialogues.get(text_id)
        if page is None:
            _log.warning("缺失 dialogue text_id: %s", text_id)
            return None
        return page

    # ------------------------------------------------------------------
    # 校验（供 python -m tests.standalone_d --text-check 使用）
    # ------------------------------------------------------------------
    def validate(self) -> list[str]:
        """返回文本问题清单（ID 命名、行长、页行数、占位符）。

        独立校验器使用；整合后由 tools/validate_content --text 汇总。
        """
        problems: list[str] = []
        id_re = re.compile(r"^[a-z][a-z0-9_.]*$")
        known_keys = set(self.strings) | set(self.dialogues)

        for key, value in self.strings.items():
            if not id_re.match(key):
                problems.append(f"ID 不符合命名规范: {key}")
            if not isinstance(value, str):
                problems.append(f"值必须是字符串: {key}")
                continue
            self._check_placeholder(key, value, known_keys, problems)
            self._check_domain_length(key, value, problems)

        for key, page in self.dialogues.items():
            if not id_re.match(key):
                problems.append(f"ID 不符合命名规范: {key}")
            missing = [k for k in _DIALOGUE_KEYS if k not in page]
            if missing:
                problems.append(f"分页缺少字段 {missing}: {key}")
                continue
            lines = page["lines"]
            if not isinstance(lines, list) or not lines:
                problems.append(f"分页 lines 必须是非空列表: {key}")
                continue
            if len(lines) > MAX_LINES_PER_PAGE:
                problems.append(
                    f"分页超过 {MAX_LINES_PER_PAGE} 行（{len(lines)} 行）: {key}"
                )
            for line in lines:
                if not isinstance(line, str):
                    problems.append(f"行必须是字符串: {key}")
                elif len(line) > MAX_LINE_CHARS:
                    problems.append(
                        f"行超长 {len(line)}>{MAX_LINE_CHARS}: {key}「{line}」"
                    )

        return problems

    # ------------------------------------------------------------------
    def _check_placeholder(
        self, key: str, value: str, known_keys: set[str], problems: list[str]
    ) -> None:
        for name in re.findall(r"\{(\w+)\}", value):
            if name in ("npc_name", "id", "year_name", "sem_name", "day", "label",
                        "deltas", "max", "days", "amount", "n", "text"):
                continue  # 由调用方运行时提供
            if f"npc.{name}.name" not in known_keys:
                problems.append(f"未知占位符 {{{name}}}: {key}")

    def _check_domain_length(self, key: str, value: str, problems: list[str]) -> None:
        if key.startswith("act.") and key.endswith(".name") and len(value) > 6:
            problems.append(f"活动名称超 6 字: {key}")
        if ".result." in key and key.startswith("act.") and len(value) > MAX_ACT_RESULT_CHARS:
            problems.append(f"活动结果超 {MAX_ACT_RESULT_CHARS} 字: {key}")
        if key.startswith("daily.") and key.endswith(".body") and len(value) > MAX_DAILY_BODY_CHARS:
            problems.append(f"日常事件正文超 {MAX_DAILY_BODY_CHARS} 字: {key}")
        if key.startswith("insp.") and key.endswith(".body") and len(value) > MAX_INSPECT_CHARS:
            problems.append(f"查看点正文超 {MAX_INSPECT_CHARS} 字: {key}")
        if key.startswith("ending.") and len(value) > MAX_ENDING_PARAGRAPH_CHARS:
            problems.append(f"结局段落超 {MAX_ENDING_PARAGRAPH_CHARS} 字: {key}")
        if ".choice." in key and len(value) > MAX_CHOICE_CHARS:
            problems.append(f"选项超 {MAX_CHOICE_CHARS} 字: {key}")
