"""TextDB 测试（D-ST-05：缺失、占位符、超长文本不得静默空白）。"""

from __future__ import annotations

import logging

import pytest

from game.ui.text_db import (
    MAX_LINES_PER_PAGE,
    TextDB,
    paginate_lines,
    wrap_line,
)


def test_get_existing(fixture_text_db):
    assert fixture_text_db.get("ui.test.act.name") == "测试活动"


def test_get_with_placeholder(fixture_text_db):
    assert fixture_text_db.get("ui.test.hello", name="奶娃") == "你好，奶娃！"


def test_missing_returns_hash_id(fixture_text_db, caplog):
    with caplog.at_level(logging.WARNING, logger="naiwa.ui.text_db"):
        result = fixture_text_db.get("ui.test.not_exists")
    assert result == "#ui.test.not_exists"
    assert any("ui.test.not_exists" in message for message in caplog.messages)


def test_missing_dialogue_returns_none(fixture_text_db, caplog):
    with caplog.at_level(logging.WARNING, logger="naiwa.ui.text_db"):
        assert fixture_text_db.get_dialogue("evt.nowhere.body.9") is None
    assert caplog.messages


def test_bad_placeholder_not_silent(fixture_text_db, caplog):
    """占位符错误时：返回原文并记录错误日志（D-ST-05）。"""
    with caplog.at_level(logging.ERROR, logger="naiwa.ui.text_db"):
        result = fixture_text_db.get("ui.test.missing_case")
    assert result == "占位符 {unknown_field} 测试"
    assert "{unknown_field}" in result
    assert any("占位符错误" in message for message in caplog.messages)


def test_paginate_lines_splits_by_page():
    """D-ST-03：4 行长文本分页，Space 逐页推进由 UI 层消费本结果。"""
    lines = ["一", "二", "三", "四", "五"]
    pages = paginate_lines(lines)
    assert len(pages) == 2
    assert pages[0] == ["一", "二", "三", "四"]
    assert pages[1] == ["五"]
    assert all(len(page) <= MAX_LINES_PER_PAGE for page in pages)


def test_wrap_line_respects_width():
    text = "这是一个非常长的句子，需要在标点处断行，不能越界。"
    for line in wrap_line(text, max_chars=10):
        assert len(line) <= 10


def test_validate_reports_overlong_lines():
    """D-ST-05：超长文本必须明确报告，不允许静默。"""
    db = TextDB({"evt.bad.choice.x": "这个选项的名字远远超过了十二个字的硬性上限规定"})
    problems = db.validate()
    assert any("选项超 12 字" in p for p in problems)


def test_validate_reports_bad_id():
    db = TextDB({"Bad-ID!": "非法 ID"})
    assert any("命名规范" in p for p in db.validate())


def test_load_missing_file_keeps_empty_db(tmp_path):
    db = TextDB.load(str(tmp_path))
    assert db.get("anything.else") == "#anything.else"
