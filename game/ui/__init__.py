"""开发者 D 的 UI 模块包。

模块清单（固定，不得自行增减文件）：
    theme.py           视觉规范常量、纯逻辑的数值格式化与布局校验
    text_db.py         TextDB：strings.json / dialogues.json 的加载与查询
    widgets.py         面板、按钮、列表、条等基础控件
    hud.py             日期 / 精力 / 心情 / 按键提示
    prompt.py          交互提示框
    result_panel.py    活动结果面板
    dialogue_box.py    对话框（头像 / 名字条 / 正文 / 打字机）
    event_scene.py     事件场景（分页 / 打字机 / 选项 / 锁定原因）
    day_summary.py     日结算面板
    tab_panel.py       Tab 状态面板
    main_menu.py       主菜单
    pause_menu.py      暂停菜单
    settings_menu.py   设置菜单
    save_menu.py       存读档界面
    graduation_scene.py 毕业界面（4 页）
    tutorial.py        新手教程（5 步）

隔离规则：tests/ui 的纯逻辑测试只允许 import theme / text_db /
tutorial / event_scene 中不依赖 panda3d 的纯函数，任何 UI 渲染类
都必须在 panda3d 可用时才导入。
"""

__all__ = [
    "theme",
    "text_db",
    "widgets",
    "hud",
    "prompt",
    "result_panel",
    "dialogue_box",
    "event_scene",
    "day_summary",
    "tab_panel",
    "main_menu",
    "pause_menu",
    "settings_menu",
    "save_menu",
    "graduation_scene",
    "tutorial",
]
