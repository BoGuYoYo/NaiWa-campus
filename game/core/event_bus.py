"""A 维护：事件总线（全员共用）。

订阅者抛出异常不得影响发出方；异常写入日志并通过 errors 列表暴露给测试。
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Callable

# 主题常量：字符串写错在整合期最难查，统一在这里定义。
TOPIC_ACTIVITY_DONE = "activity.done"
TOPIC_DAY_ENDED = "day.ended"
TOPIC_EVENT_STARTED = "event.started"
TOPIC_EVENT_FINISHED = "event.finished"
TOPIC_SCENE_CHANGED = "scene.changed"
TOPIC_GAME_GRADUATED = "game.graduated"
TOPIC_ASSET_MISSING = "asset.missing"
TOPIC_DAY_STARTED = "day.started"
TOPIC_SAVE_WRITTEN = "save.written"
TOPIC_SETTINGS_CHANGED = "settings.changed"

KNOWN_TOPICS = (
    TOPIC_ACTIVITY_DONE,
    TOPIC_DAY_ENDED,
    TOPIC_EVENT_STARTED,
    TOPIC_EVENT_FINISHED,
    TOPIC_SCENE_CHANGED,
    TOPIC_GAME_GRADUATED,
    TOPIC_ASSET_MISSING,
    TOPIC_DAY_STARTED,
    TOPIC_SAVE_WRITTEN,
    TOPIC_SETTINGS_CHANGED,
)

Handler = Callable[..., Any]


class EventBus:
    def __init__(self, logger: logging.Logger | None = None, strict_topics: bool = False) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._log = logger or logging.getLogger("naiwa.bus")
        self._strict = strict_topics
        self.errors: list[tuple[str, BaseException]] = []
        self.emitted: list[tuple[str, dict[str, Any]]] = []

    def subscribe(self, topic: str, handler: Handler) -> Handler:
        if self._strict and topic not in KNOWN_TOPICS:
            self._log.warning("[BUS] unknown topic %s (subscribed anyway)", topic)
        if handler not in self._handlers[topic]:
            self._handlers[topic].append(handler)
        return handler

    def unsubscribe(self, topic: str, handler: Handler) -> None:
        handlers = self._handlers.get(topic)
        if handlers and handler in handlers:
            handlers.remove(handler)

    def emit(self, topic: str, **data: Any) -> int:
        """派发事件，返回实际被调用的处理函数个数。

        返回值是 B 的规则层用例（`test_event_bus.py`）依赖的契约：`emit()` 在
        没有订阅者时返回 0，不算异常。旧签名的调用方忽略返回值即可。
        """
        self.emitted.append((topic, data))
        if self._strict and topic not in KNOWN_TOPICS:
            self._log.warning("[BUS] unknown topic %s", topic)
        called = 0
        for handler in list(self._handlers.get(topic, ())):
            called += 1
            try:
                handler(**data)
            except Exception as exc:  # 单个订阅者失败不能拖垮流程
                self.errors.append((topic, exc))
                self._log.exception("[BUS] handler error on %s: %s", topic, exc)
        return called

    def clear(self) -> None:
        self._handlers.clear()
        self.errors.clear()
        self.emitted.clear()

    def handler_count(self, topic: str) -> int:
        return len(self._handlers.get(topic, ()))
