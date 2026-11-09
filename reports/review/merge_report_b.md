# 任务 B 合入报告（核心规则系统）

- 执行：A（技术负责人）
- 合入对象：`任务包/delivery_B/` 的 `game/systems/`、`game/sim/`、`content/rules/`
- 参考：`reports/review/task_b_review.md`（评审 + 第二轮整合实测）
- 接口变更说明：`docs/CHANGELOG_API.md` §10

## 1. 合入结果

| 项目 | 合入前 | 合入后 |
| --- | --- | --- |
| `resolve_services()` | 4 个服务静默退回替身 | **6/6 real** |
| `pytest tests` | 308 条（B 的用例不在仓库里） | **536 条：531 passed / 5 skipped** |
| B 的规则基线 | 只能在 B 自己的包里跑 | `--strategy all --seeds 0-199` → **1200/1200** |
| 随机基线 | — | `--random 3000` → 2917/59/13/5/3/3（与 `balance_report.md` 一致） |
| 规则一致性 | — | `python -m game.systems.spec_export --check` → 一致 |
| 日常事件 | **触发即锁死当天**（`end_day` 被阶段守卫拒绝） | 立即结算，`phase` 保持 `campus`，当天正常结束 |
| 交谈结果面板 | 标题/正文 `#id` + 品红缺图 | 标题「苏墨」+ D 的正文 + 占位色块 |
| 文案覆盖 | 120 条 `#text_id` | 全部有文案（114 条为占位，清单见 `_placeholder_ids.json`） |

## 2. 代码改动清单

| 文件 | 改动 |
| --- | --- |
| `game/core/state.py` | `NPC_IDS`、`validate()`、`copy()` |
| `game/core/event_bus.py` | `emit()` 返回被调用的处理函数个数 |
| `game/core/flow.py` | `is_immediate_event()` + 日常事件分流（不进 EventScene）；`FallbackEndingService` 的 `ending_vitality` → `ending_vibrant` |
| `game/ui/result_panel.py` | `talk.*` 走 NPC 分支；立即事件不显示"有事情发生了" |
| `game/systems/*`（12 个文件） | B 的规则系统，原样合入 |
| `game/sim/*`（5 个文件） | B 的无界面模拟器 + CLI，原样合入 |
| `content/rules/*.json`（5 份） | B 的规则内容，原样合入 |
| `content/text/zh_CN/strings.json` | 补 120 条文案（含 D 的正式文案按位置迁到 B 的 choice_id） |
| `content/text/zh_CN/_placeholder_ids.json` | 新增：A 生成/迁移的 id 清单，D 按此替换 |
| `docs/ui/text_index.csv` | 335 → 455 行 |
| `tools/gen_placeholder_text.py` | 新增：文案兜底工具（幂等，`--check` 只报告不写） |
| `tests/systems/*`、`tests/expected/*` | B 的 227 条用例与基准数据，原样合入（`tests/systems/__init__.py` 解决同名冲突） |
| `tests/core/test_flow.py` | 事件选择改取"第一个可用选项"；新增 `play_one_action()`；毕业断言按 B 的日历放宽；新增日常事件锁死回归用例 |
| `tests/systems/test_spec_sync.py` | schema 缺失时 skip（正式 schema 归 E） |

## 3. 实机证据（`reports/review/B/`）

| 文件 | 内容 |
| --- | --- |
| `merged_result_talk.png` | 交谈结果面板：标题「苏墨」+ D 的正文，无 `#id`、无品红 |
| `merged_result_daily.png` | 日常事件：活动文案 + 日常事件那一行，提示语是「继续」，`phase` 仍是 campus |
| `merged_result_activity.png` | 普通活动：标题 + 活动 CG + 文案 |
| `merged_event_dialogue.png` | 学期事件：陈朗立绘 + 正文（B 的 pages + D 的文本） |

复现命令：

```powershell
python -m pytest tests -q
python -m game.sim --strategy all --seeds 0-199 --summary
python -m game.sim --random 3000 --summary
python -m game.systems.spec_export --check
python -m game --dev --scene CampusScene --skip-intro --seed 42   # 手动试玩
```

## 4. 遗留

| 事项 | 责任方 | 说明 |
| --- | --- | --- |
| 120 条占位文案换正式文案 | D | 清单 `content/text/zh_CN/_placeholder_ids.json`；其中学期事件的选项/结果已用 D 的现成文案，只有锁定提示、日常事件、交谈、关系事件是新写的短句 |
| `content/schema/rules.schema.json` | E | 落库后 `test_rules_pass_schema` 5 条 skip 自动转正 |
| 日常事件的 HUD toast | D | 现在只在结果面板里显示一行文字 |
| 关系事件的三段文案语气 | D | 占位是「和 X 聊了很久，关系又近了一点。」，正式文案建议按 NPC 性格分写 |
| 平衡复核 | B | 改动数值须先改 `spec_data` 再 `spec_export`；否则 `test_spec_sync` 会报不一致 |
