"""纯规则系统（开发者 B）。

本包不导入任何渲染、场景或界面模块：所有逻辑必须能在无窗口、无模型、
无文本资源的环境中运行（验收项：本目录内搜索渲染库名称应为空结果）。

模块职责：
    spec_data.py            全部数值的唯一来源
    spec_export.py          由 spec_data 导出 content/rules/*.json
    content_db.py           加载并校验规则 JSON
    rng.py                  唯一随机入口（字符串种子派生）
    conditions.py           条件 DSL
    effects.py              效果应用与裁剪
    calendar_service.py     时间模型与日结算
    activity_service.py     9 个活动
    relationship_service.py 交谈与关系事件
    event_service.py        学期/关系/日常事件的视图与选择
    ending_service.py       6 个结局判定
"""

__all__ = [
    "activity_service",
    "calendar_service",
    "conditions",
    "content_db",
    "effects",
    "ending_service",
    "event_service",
    "relationship_service",
    "rng",
    "spec_data",
]
