"""A 维护：按键绑定路由（accept / ignore 的归属栈）。

引擎的 ``accept(event, fn)`` / ``ignore(event)`` 是一对**全局**接口：``ignore`` 会把该事件
上的所有绑定一次性拆掉，不区分是谁绑的。场景一多就会互相踩，历史上踩过两次：

1. 主菜单点"新游戏"：``change("CampusScene")`` 要淡出 0.25 秒，开场事件对话框却先被
   ``push`` 上来了。淡出结束时会执行 ``MainMenu.on_exit`` → ``ignore("enter") /
   ignore("space")``，把对话框刚绑的确认键一起清掉 —— 玩家看到的就是
   「对话框弹出来但按什么都没反应」，连 Esc 都没了。
2. 从主菜单进入设置 / 读档再返回：子面板退场时 ``ignore`` 掉上下键与确认键，
   主菜单从此变成死界面。

``InputRouter`` 给每条绑定记住「谁绑的」，退场时只收回自己的那份，并把该事件上
剩下的最后一条（最上层）重新 ``accept`` 回去，于是"后绑定的覆盖先绑定的"这个
既有语义保持不变，同时不再误伤别人。

本模块不依赖 panda3d，可在 core 单元测试中直接验证。
"""

from __future__ import annotations

from typing import Any, Callable, Iterable

Handler = Callable[..., None]


class InputRouter:
    """按键绑定的归属栈。

    owner 用对象身份（``is``）比较，通常就是场景/控件实例本身。
    """

    def __init__(
        self,
        accept: Callable[[str, Handler], Any],
        ignore: Callable[[str], Any],
    ) -> None:
        self._accept = accept
        self._ignore = ignore
        self._claims: dict[str, list[tuple[Any, Handler]]] = {}

    # ------------------------------------------------------------------ #
    # 绑定 / 注销
    # ------------------------------------------------------------------ #
    def bind(self, owner: Any, event: str, handler: Handler) -> None:
        """登记一条绑定；同一事件上后绑定的生效（越靠上层越先拿到按键）。"""
        if not event or handler is None:
            return
        claims = self._claims.setdefault(event, [])
        claims.append((owner, handler))
        self._accept(event, handler)

    def bind_many(self, owner: Any, mapping: Iterable[tuple[str, Handler]]) -> None:
        for event, handler in mapping:
            self.bind(owner, event, handler)

    def unbind(self, owner: Any, events: Iterable[str] | None = None) -> list[str]:
        """收回 owner 的全部（或指定事件的）绑定，返回受影响的事件名。"""
        affected: list[str] = []
        targets = list(self._claims) if events is None else list(events)
        for event in targets:
            claims = self._claims.get(event)
            if not claims:
                continue
            kept = [(who, handler) for who, handler in claims if who is not owner]
            if len(kept) == len(claims):
                continue
            affected.append(event)
            if not kept:
                self._claims.pop(event, None)
                self._ignore(event)
                continue
            self._claims[event] = kept
            self._accept(event, kept[-1][1])
        return affected

    # ------------------------------------------------------------------ #
    # 查询（调试 / 测试 / 日志用）
    # ------------------------------------------------------------------ #
    @property
    def events(self) -> list[str]:
        return sorted(self._claims)

    def owner_of(self, event: str) -> Any | None:
        claims = self._claims.get(event)
        return claims[-1][0] if claims else None

    def handler_of(self, event: str) -> Handler | None:
        claims = self._claims.get(event)
        return claims[-1][1] if claims else None

    def is_bound(self, event: str) -> bool:
        return bool(self._claims.get(event))

    def depth(self, event: str) -> int:
        return len(self._claims.get(event, ()))

    def clear(self) -> None:
        """退出前清空（进程结束时可省，测试里需要）。"""
        for event in list(self._claims):
            self._claims.pop(event, None)
            self._ignore(event)


__all__ = ["InputRouter"]
