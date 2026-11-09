# 任务 B（核心规则系统）完成度检查报告

检查日期：2026-11-09
检查对象：`任务包/delivery_B/`（B 的自交付包）与 `naiwa_campus/`（整合仓库 master）
依据：《任务分工手册 3.0》第一部分（全员共用规格）＋ 第 10 节八周进度 ＋ 第 9 节协作流程
检查方式：不采信交付说明中的自述数字，全部在本机独立复跑；另做一次"合入 develop"预演。

---

## 1. 一句话结论

**B 的独立交付包已完成且自洽，但没有合入仓库，因此按手册"完成定义"（代码进入 develop、验证完成、可复现）B 尚未完成。**
缺口不是内容量，而是最后一步：`game/systems/`、`game/sim/`、`content/rules/` 在 master 上仍是空的（只有 `.gitkeep`），
仓库实际跑的是 A 的替身服务（`docs/integration/week-2.md` P0 项："B 的服务全部是替身"）。

合入预演显示：把 B 的包原样叠到当前 master 的 `game/core/` 上，`tests/systems` **227 条中 37 条失败**，
`from game.systems.spec_data import ...` 直接 `ImportError`。

| 层面 | 状态 |
| --- | --- |
| 独立验收（B 自己的命令，B 自己的 fixture） | ✅ 通过，与自述一致 |
| 内容数量与手册规定 | ✅ 全部对齐（9 活动 / 8 学期事件 / 9 关系事件 / 12 日常 / 6 结局 / 3 NPC） |
| 公共接口签名（手册第 6 节） | ✅ 逐条一致 |
| 依赖隔离（systems/sim 禁 panda3d、ui、world） | ✅ 0 命中，仅标准库 |
| 合入当前 master 后仍可跑 | ❌ 37 条失败（4 类根因） |
| 进入 develop 分支 | ❌ 未进入（master 无 develop 分支，B 的包也没有 git 历史） |
| 跨岗文本 ID 对齐（B ↔ D strings.json） | ❌ B 生成的 62 个 text_id 中 54 个在 `strings.json` 里不存在 |

---

## 2. 独立验收复现结果（本机实测）

运行环境：`C:\Users\huang\Desktop\奶娃\.venv-naiwa\Scripts\python.exe`（Python 3.12.14），
在 `C:\Users\huang\Desktop\奶娃\.tmp\bcheck\`（`delivery_B` 的干净副本）中执行。

| 检查项 | B 自述 | 实测 | 判定 |
| --- | --- | --- | --- |
| `pytest -m "not gui"` | 227 passed | exit 0，227 项（19 个文件，逐文件计数求和 = 227） | ✅ 一致 |
| `python -m game.systems.spec_export --check` | 与 spec_data 一致 | exit 0，"规则 JSON 与 spec_data 一致" | ✅ |
| `--strategy all --seeds 0-199` | 1200/1200 | 6 策略各 200/200 命中，mismatches 为空 | ✅ |
| `--random 3000` | balanced 2917 / creator 59 / vibrant 13 / digital 5 / academic 3 / club_leader 3 | 完全相同的分布 | ✅ |
| seed42 六策略终局（平衡报告第 2 节表） | 学业/体力/社交/兴趣/心情/关系 | 逐格一致（如 academic：100/27/35/17/26，关系 100/5/8） | ✅ |
| `game/systems`、`game/sim` 中的 panda3d / game.ui / game.world | 无 | 无命中；import 只有 `json/random/re/operator/sys/time/argparse/pathlib/typing/collections` | ✅ |
| 行覆盖率 95%、ruff 全绿、mypy 0 error | 交付说明第 2、5 节 | **无法复现**：本机 venv 未装 pytest-cov / ruff / mypy | ⚠️ 未验证（不是失败） |

### 2.1 内容评审（对照手册第 1、4 节）

| 项 | 手册规定 | 实测 | 判定 |
| --- | --- | --- | --- |
| 活动 | 9 个校园活动 | 9 个，ID 为 attend_class / library_study / play_games / create_work / join_club / exercise / eat_canteen / rest_dorm / campus_walk | ✅ |
| 食堂每日上限 | 食堂每天 2 次（E_DAILY_LIMIT） | `eat_canteen` 的 `daily_limit=2`，其余为 None | ✅ |
| 学期事件 | 8 个 `sem_<1-8>_` | sem_1_club_fair … sem_8_graduation_eve，8 个 | ✅ |
| 关系事件 | `rel_<npc>_<1-3>`，3 NPC × 3 段 | 9 个，命名合规 | ✅ |
| 日常事件 | 12 个 `daily_` | 12 个，命名合规 | ✅ |
| 开场事件 | `story_opening` | 存在 | ✅ |
| 结局 | 6 个 `ending_` | 6 个，ID 与手册一致 | ✅ |
| NPC | `npc_sumo / npc_chenlang / npc_xiaoyou` | 3 个，顺序与 A 的 `RELATIONSHIP_KEYS` 一致 | ✅ |
| 错误码 | 7 个 | 代码中 7 个全部出现（E_NO_SLOT / E_LOW_ENERGY / E_DAILY_LIMIT / E_ALREADY_TALKED / E_WRONG_PHASE / E_UNKNOWN_ID / E_CHOICE_LOCKED） | ✅ |
| 接口签名 | 手册第 6 节 | `can_start -> (bool, error_code)`、`start -> ActivityResult`、`preview -> dict`、`talk -> ActivityResult`、`end_day -> DayEndResult`、`get_view -> EventView`、`choose -> EventResult`、`evaluate -> EndingResult` 全部一致；附加的 `can_talk / first_available_choice / semester_event_id` 为增量，不冲突 | ✅ |
| 60/48 节拍 | 16 天 × 3 时段 = 48 次行动 | 模拟器完整跑完 48 次行动并触发 8 个学期事件 | ✅ |

交付物齐套性：`docs/B_delivery.md`（模块职责＋验收命令＋16 条实现约定＋交接待办）、
`docs/balance_report.md`（结局优先级表＋seed42 终局＋200 种子回归＋3000 局随机基线）、
`reports/standalone/B/`（pytest.txt、strategies_0-199.json、fuzz.json、academic_42.json）、
`tests/expected/`（unit_expect、smoke_seed42、strategies、random_3000）、`content/schema/rules.schema.json`（E 的临时版）均存在且内容自洽。

---

## 3. 合入预演：37 条失败，4 类根因

预演方法：`naiwa_campus` 全量拷贝（去 dist/build/assets/.git）→ 叠加 `delivery_B` 的
`game/systems`、`game/sim`、`content/rules`、`content/schema`、`tests/systems`、`tests/expected` →
执行 `pytest tests/systems -m "not gui"`。
临时目录：`C:\Users\huang\Desktop\奶娃\.tmp\bmerge\`，完整输出：`.tmp\merge_pytest.txt`。

| 根因 | 位置 | 失败数 | 说明 |
| --- | --- | --- | --- |
| R1 `NPC_IDS` 不存在 | `game/systems/spec_data.py:17` `from game.core.state import NPC_IDS` | 1 个硬错误（阻断整包导入） | A 的 `game/core/state.py` 只有 `RELATIONSHIP_KEYS = ("npc_sumo", "npc_chenlang", "npc_xiaoyou")`，没有 `NPC_IDS`。手工加一行别名后 `spec_data` 立即可导入，NPC 顺序校验通过 |
| R2 `GameState.validate()` 不存在 | `game/sim/simulator.py:87`，以及 `tests/systems/test_state.py` 7 条 | 8（test_state）+ 1（fuzz）+ 8（test_cli）+ 14（test_strategies）= 31，其中大部分是级联 | A 的 `GameState` 只有 `snapshot()`，没有 `validate()`。`validate()` 是 B 临时 core 的附加方法（`B_delivery.md` 第 15 条已声明"可选调用"），A 替换实现时没有保留 |
| R3 `GameState.copy()` 不存在 | `tests/systems/test_state.py::test_copy_is_deep` | 1 | 同上，`copy()` 是 B 临时 core 的附加方法（`B_delivery.md` 第 11 条），A 侧叫 `snapshot()` |
| R4 `EventBus.emit()` 返回值语义不同 | `tests/systems/test_event_bus.py` 6 条 | 6 | B 的临时 bus `emit()` 返回"被调用的 handler 数"，A 的 `emit()` 返回 `None`（手册第 6 节只写 `emit(topic, **data)`，未规定返回值）。这 6 条属 B 的用例过度绑定自己的临时实现 |

按失败文件分布：`test_state.py` 8、`test_cli.py` 8、`test_event_bus.py` 6、`test_strategies.py` 14、`test_fuzz.py` 1，合计 37。

结论：问题不在 B 的规则逻辑（1200/1200、3000 局基线在独立环境全部成立），而在
**B 交付的 `game/core` 是临时实现，A 后来用正式实现替换时两者签名出现分叉，而 B 从未拿自己的用例对正式 core 复跑过**。
B 在 `B_delivery.md` 第 3 节已预警"临时实现，A 接管，不得改变 `to_dict` 键集合"，但没覆盖 `NPC_IDS`、`validate()`、`copy()`、`emit()` 返回值四处。

---

## 4. 跨岗缺口：文本 ID（B ↔ D）

B 只产出 `text_id`（按 `B_delivery.md` 第 4 条），正文由 D 提供。实测把 B 在 9 个活动、3 次交谈、
18 个事件视图上生成的 text_id 收集起来共 **62 个**，与 `content/text/zh_CN/strings.json`（283 条）比对，
**54 个不存在**，集中在：

| 缺口 | B 生成 | D 实际键 | 影响 |
| --- | --- | --- | --- |
| 事件正文页 | `evt.<event_id>.body.1`（含 `body.2`） | 无任何 `body` 键 | 18 个事件的正文全部回落 `#text_id` |
| 学期事件选项 | `evt.<event_id>.choice.<B 的 choice_id>` | 键在，但 choice_id 不同：B 的 `submit_art`/`help_friend` ↔ D 的 `submit_work`/`help_xiaoyou` | 选项文字缺失 |
| 交谈结果 | `talk.<npc_id>.result.1` | `npc.sumo.talk` / `npc.chenlang.talk` / `npc.xiaoyou.talk` | 交谈结果缺失 |
| 锁定原因 | `evt.<event_id>.lock.<choice_id>` | 键在，但随 choice_id 一起错位 | 锁定提示缺失 |

B 的命名符合手册第 4 节"文本 ID 形如 `evt.sem_1_club_fair.body.1`"，是 D 侧偏离了规定。

---

## 5. 过程合规缺口（手册第 9 节）

1. **无分支、无合并请求**：`delivery_B` 只有 `.gitignore`，没有 `.git`；仓库 master 只有 master 一条分支，
   没有 develop。手册第 9 节要求 `feature/b-<主题>` → develop，周五由 A 合并并打 `week-N` 标签。
2. **无接口变更登记**：`NPC_IDS`、`validate()`、`copy()`、`emit()` 返回值四处分叉，`docs/CHANGELOG_API.md` 中无记录，
   违反"公共接口只能由 A 修改、变更须写入 CHANGELOG_API"。
3. **完成证据只有自述**：`pytest.txt` 里的 227 passed 与实测一致（可信），但覆盖率的 95%、ruff/mypy 全绿无机器可复现的产物（未提交 `coverage.xml`/`ruff.txt`/`mypy.txt`）。

---

## 6. 待办清单

### P0（阻塞 B 判定为"完成"）

| # | 事项 | 责任方 | 验收方式 |
| --- | --- | --- | --- |
| 1 | `game/core/state.py` 增加 `NPC_IDS = RELATIONSHIP_KEYS` 别名（或在 `spec_data.py` 改读 `RELATIONSHIP_KEYS`），并写入 `CHANGELOG_API.md` | A（改接口）或 B（改调用）二选一，须登记 | `python -c "import game.systems.spec_data"` 退出码 0 |
| 2 | 统一 `validate()`：A 给 `GameState` 加 `validate()`，或 B 在 `simulator.py` 改调 A 已有的校验入口；`copy()` 同理对齐 `snapshot()` | A + B | `pytest tests/systems -m "not gui"` 在整合仓库内 exit 0 |
| 3 | `EventBus.emit()` 返回值语义定案（建议：手册补一句"返回被调用的 handler 数"由 A 实现，或 B 改断言），6 条用例同步 | A + B | 同上 |
| 4 | B 的包按 `feature/b-systems` 合入，A 在 develop 打 `week-N` 标签，并在 `docs/integration/week-N.md` 记录 | A | `git log` 可见；`week-N` 标签存在 |
| 5 | 文本 ID 对齐：D 为 18 个事件补 `body.*`、把 choice_id 改成 B 的 ID 集、交谈键改为 `talk.<npc>.result.1`（或 B 反向适配 D 的键，二选一并登记） | D 主责，B 确认 | `tests/standalone_d --text-check` 零缺失，且 B 的 62 个 text_id 全部能在 `strings.json` 命中 |

### P1

| # | 事项 | 责任方 |
| --- | --- | --- |
| 6 | 提交覆盖率/ruff/mypy 的原始输出到 `reports/standalone/B/`，让"95%｜0 error"可复现 | B |
| 7 | `requirements.txt` 与 `requirements-dev.txt` 归位（B 把测试依赖写在 dev 里是对的，但 `requirements.txt` 只有注释，需与仓库 E 维护的两份合并，避免双份版本源） | E |
| 8 | 平衡报告第 4 节随机基线偏差（-16/-12/-4）与手册 B9 文档值不一致，需 A 在手册里补"随机抽样算法"定义，否则第 8 周 E 的回归无法判定通过 | A + B |

---

## 7. 判定

- **B 的交付内容**：完成。数量、ID、接口、隔离、回归、文档、证据齐套，227 条用例与 1200/1200、3000 局基线在本机复现一致。
- **B 的任务**：未完成。缺"合入 develop"这一步，且合入后当前 master 会红 37 条；文本 ID 与 D 有 54 处缺口，合入后事件正文与交谈结果会显示 `#text_id`。
- 建议在例会上把 P0-1～P0-3 定为 A+B 当周联合修复项（都是几行代码的接口对齐，不是重写），P0-5 交给 D 补文案，然后走一次完整合入 + `week-N` 打标。

---

## 8. 第二轮：补掉 R1/R2 之后的整合实测

第一轮只做了"把包叠上去跑用例"。这一轮把 R1/R2 补掉，再看**游戏本身**能不能跑起来。
预演目录：`奶娃/.tmp/bcheck/naiwa_campus`（master 全量拷贝 + B 的 systems/sim/rules）。

### 8.1 补丁只有两处（`game/core/state.py`）

```python
NPC_IDS = RELATIONSHIP_KEYS      # B 的 spec_data / content_db 按这个名字取 NPC 列表

def validate(self) -> None:      # 不变量断言，非法抛 ValueError
    ...                          # clamp() 是读档兜底（尽量修好），validate() 是"不该发生"的断言
```

| 项目 | 补丁前 | 补丁后 |
| --- | --- | --- |
| `resolve_services()` | activity/calendar/event/relationship = **fallback**，ending/interaction = real | **6/6 real** |
| `python -m game.sim --strategy all --seeds 0-199` | 跑不起来（ImportError） | 6 × **200/200** 全中 |
| `--random 3000` | 跑不起来 | 2917 / 59 / 13 / 5 / 3 / 3，与 `balance_report.md` 逐项一致 |
| `--strategy academic --seed 42 --save-resume` | 跑不起来 | 正常收尾，无异常 |
| `spec_export --check` | 跑不起来 | "规则 JSON 与 spec_data 一致" |
| B 的用例跑在 **A 的 core** 上 | 37 failed | **220 passed / 7 failed** |

剩下 7 条全是"B 的用例在测 A 的文件"：6 条 `test_event_bus.py`（`emit()` 返回值、`unsubscribe(handler)` 单参数）+ 1 条 `test_state.py::test_copy_is_deep`。
`game/systems` 全仓搜索 **0 处**使用 EventBus，所以这 6 条不影响运行；`copy()` 加个 `return self.snapshot()` 别名即可。

**结论：R1/R2 属于"补两行就能通"的接口对齐，不是 B 的逻辑问题。**

### 8.2 新发现（第一轮没覆盖）：日常事件把当天锁死 —— P0

用真实流程跑（`game/services` 全 real，直接调服务 + `GameFlow`）：

```text
=== 活动 campus_walk ===   ok: evt=daily_old_friend slot=3 phase=event overlays=['EventScene']
=== 日结算 end_day ===     !! RuntimeError: end_day 只能在 campus 阶段（毕业之前）调用，
                             当前 phase=event、day_index=0、pending_event_id=daily_old_friend
=== 日常事件 get_view ===   !! ContentError: E_UNKNOWN_ID: 事件 daily_lost_cat 不存在
```

**根因**：B 文档第 3 节第 5 条写明日常事件"立即结算、不调用 `choose`、不进 EventScene"；
A 的 `GameFlow.close_result_panel()`（`game/core/flow.py:363`）只要 `triggered_event_id` 非空就推 EventScene，
而日常事件不在 `ContentDB.events` 里，`get_view()` 抛 `ContentError` → EventScene 拿到空数据，
`phase` 却已经置成 `event` → B 的 `CalendarService.end_day()` 阶段守卫拒绝结算 → **当天过不去，只能读档**。

**证据**：`reports/review/B/event_daily_empty.png`（空白对话框）、`reports/review/B/result_activity_ok.png`（普通活动正常对照）。

**修法（A 侧）**：
1. 先解阻断：`close_result_panel()` 里按前缀分流，`daily_*` 不进 EventScene，改 HUD 提示，并保留 `if payload.day_finished: finish_day()`；
2. 第 6 周平衡复核时给 `ActivityResult` 加 `immediate_text_id` 字段，由 B 填，A 只判断"有就提示"。

### 8.3 新发现：交谈结果面板掉 `#id` + 品红占位 —— P1

`talk()` 返回 `activity_id="talk.npc_sumo"`、`text_ids=["talk.npc_sumo.result.1"]`；A 的结果面板按
`act.<activity_id>.name` / `cg_naiwan_<activity_id>` 取值，于是标题 `#act.talk.npc_sumo.name`、
正文 `#talk.npc_sumo.result.1`、插图直接走品红棋盘（`reports/review/B/result_talk_broken.png`）。

修法：`ResultPanel.apply()` 对 `talk.*` 走 NPC 分支（`npc.<short>.name` + `npc.<short>.talk` + 立绘），
或单独给一张 `cg_naiwan_talk`。

### 8.4 文案缺口复核：比第一轮明显好转，但新增了三族

| 族 | 第一轮 | 本轮实测 |
| --- | --- | --- |
| 活动名 `act.<id>.name` | 缺 | **0 缺**（9 个全齐） |
| 活动结果 `act.<id>.result.1..3` | 缺 | **0 缺**（27 条全齐） |
| 事件正文页 `evt.<id>.body.*` | 全缺 | **0 缺**（24 页全齐，D 已补） |
| 学期事件选项/结果/锁定 | choice_id 错位 | 24 个选项里 4 个有文案，缺 **20+20+23** |
| 关系事件 `evt.rel_*` | 未测 | 9 事件 × 3 条 = **27 全缺** |
| 日常事件 | 未测 | 12 × 2 种 id = **24 全缺** |
| 交谈 `talk.<npc>.result.1` | 缺 | **3 全缺**（D 用的是 `npc.<short>.talk`） |
| 结局 `ending.<id>.title/body.1..3` | 未测 | **0 缺**（6 个结局全齐） |

合计缺失 **120 条**，集中在关系事件、日常事件、学期事件的选项文案。

### 8.5 A 自己的 4 条 flow 用例要跟着改 —— P2

`pytest tests/core tests/ui tests/world` 在合并副本里 **304 passed / 4 failed**，全部是 `tests/core/test_flow.py`
按替身写的用例：

- 不看 `phase` 直接 `activity.start()` → 真服务返回 `E_WRONG_PHASE`；
- 学期事件硬编 `choose(..., "ok")` → B 的事件没有 `ok` 选项（`E_UNKNOWN_ID: sem_1_club_fair 没有选项 ok`）。

不算 B 的问题，但合入时必须同步改这 4 条，否则 A 自己的回归会红。

### 8.6 补充问题（第一轮未覆盖）

| # | 问题 | 级别 | 归属 |
| --- | --- | --- | --- |
| 1 | `FallbackEndingService` 映射出 `ending_vitality`，B 的结局集合里没有（应为 `ending_vibrant`） | P2 | A |
| 2 | 4 份规则 JSON 内嵌 30 条中文文案（activities 9 / daily 12 / npcs 3 / endings 6），与"文案只走 text_id"冲突；当前 UI 不读，但会分叉 | P2 | B |
| 3 | `CalendarService.end_day` 阶段守卫抛 `RuntimeError`，A 侧任何漏改 phase 的地方都会变成"当天卡死"，建议改错误码 + 日志 | P3 | B/A |
| 4 | 结果面板标题与 160×90 插图重叠（`result_illustration` 从 x=160 起，标题 24px 从 x=60 起） | P3 | D |

### 8.7 修订后的判定

- **B 的交付内容：通过**（第一轮已确认，本轮进一步证实：补两行核心缺口后，B 的全部基准在 A 的 core 上逐项复现）。
- **"能合进游戏"：还差 1 个 P0。** 日常事件不修掉，随机日常事件一触发就锁死当天，无法交付试玩。
- 建议的落库顺序：
  1. A 的 core 三处小改（`NPC_IDS` / `validate()` / `copy()`）+ EventBus 向后兼容（`emit` 返回数量、`unsubscribe` 单参数）
  2. 接 `game/systems` + `game/sim` + `content/rules`（**不接** B 的 `game/core`、`content/schema`、`pytest.ini`、`requirements*`）
  3. 修 P0（日常事件分流）+ 修 `ending_vitality`
  4. 结果面板 `talk.*` 分支
  5. 补 120 条文案（D 主责，A 先加 id 兜底）
  6. 接 `tests/systems` + `tests/expected`，同步改 B 的 7 条与 A 的 4 条用例
  7. `docs/CHANGELOG_API.md` 增一节记录本次 core 改动
