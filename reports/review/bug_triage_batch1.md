# 附录：小D 第 1 批分诊（已合并至 `bugscan_2026-11-09.md`）

> **本文件不再是清单，是附录。** 唯一清单 = `reports/review/bugscan_2026-11-09.md`（BUG-0 … BUG-6）。
> 下面的内容**只保留 bugscan 里没有的东西**：编号映射、修复坑位、adapter 级测试夹具做法、P3 小项、以及本轮的验证来源声明。
> 分派与执行顺序**以 bugscan 与群内定稿为准**，本文件不另立分派。

## 编号映射

| 本文件（旧） | bugscan（现行） | 状态 |
| --- | --- | --- |
| BUG-01 事件选择不生效 | **BUG-0** | 已并入，有实测对比数据 |
| BUG-02 锁定选项未门控 | **BUG-0**（第二半） | 已并入 |
| BUG-03 教程横幅未装配 / `player_moved` 无发送方 | **BUG-3** | 已并入，去重后只派一次 |
| BUG-04 字体缺失 | **BUG-5** | 已并入，等 Human 供料 |
| BUG-05 教程步骤不排队（`tutorial.py:43-50`） | 无编号 | **bugscan 未收录**，P3 |
| BUG-06 `_refresh_prompt` 两分支完全相同（`world_scene.py:362-365`） | 无编号 | **bugscan 未收录**，P3 死代码 |
| BUG-07 所有自动化绕过真实 UI 适配层 | 已作为 BUG-0 的"为什么全绿没发现" | 已并入 |

## BUG-0 修复时必须一起处理的三个坑（复核时我会逐条查）

1. **`_finished` 的无选项兜底会绕过服务层**：`world_scene.py:693-700` 在 `self._pending_result` 为空时用 `choice_id="none"` 造 `EventResult` 调 `flow.handle_event_result`。改走 `services.event.choose` 后必须改成"没有 pending_result 就只 `pop()`、不结算"，否则 `none` 会被当成一次事件结算写进 `event_log` / phase。
2. **`_inspect_only` 不能结算**：`apply()` 的 `text_id` 分支（Inspect 文本页）只展示不选择，绝不能流到 `choose`，否则看一眼告示牌就结算掉一个事件。
3. **`ContentError` 必须变成玩家可读提示**：`choose` 会抛 `E_CHOICE_LOCKED` / 重复结算 / `E_UNKNOWN_ID`；锁定提示文案 id 是 `evt.<id>.lock.<choice_id>`。异常要在适配层接住，不能冒到 scene_manager 的回调里。

## BUG-0 验收第 3 条的真实成本（已按实测更正，比原先估的便宜一半）

全仓 `tests/` 里 **零** 引用 `world_scene` / `EventSceneAdapter` / `_build_view`——这一点不变。但**不是我原先说的"没有可复用夹具"**：`tests/world/fixtures/fake_services.py` 已有 `FakeTextDB:74`、`FakeSceneManager:79`、`FakeEventBus:96`，`fake_state.py:23` 有 `FakeState`。更正后的做法：

- 子类化 `EventSceneAdapter`，覆写 `_make_widget()`（`world_scene.py:520-524`，本身只做 `self.widget_cls(...)`）返回**记录型假 widget**，不碰 panda3d 控件、不开窗口；
- `scenes` 用 `FakeSceneManager`、`bus` 用 `FakeEventBus`；
- **但 `services.event` 必须是真 `EventService` + 真 `ContentDB`**（`FakeTextDB` 只够 `_inspect_only` 那条分支用，它替不了 `ContentDB`），否则又变成测替身；
- 断言落在"`handle_event_result` 收到的 `EventResult` 带 `deltas` / `added_flags` / `next_event_id`"和"`state.stats` 真的变了"。

## 新增数据结论（对"文案 0 缺失"的修正）

`events.json` 确为 **18 个事件**、`lock` 文案 37 条，数量上不缺。**但内容有退化**，光看"有没有"会漏：

- 孤儿三元组仍存在（与 BUG-6 同类）：`evt.sem_3_art_contest.*.submit_work`（`strings.json:80-84`）、`evt.sem_6_lab_invite.*.join_lab`（`:103-107`）、`evt.sem_7_final_project.*.solo_exhibition`（`:112-116`）——对应事件里真正的选项 id 是 `submit_art`（`events.json:100`）、`accept_lab`（`:251`）、`exhibition`（`:320`）。
- 后果不是"缺文案"，是**具体原因写在了死 id 上**：live 选项的 lock 文案是通用占位「（条件未满足）」（`:288-375` 那一批），而"需要学业 ≥ 40""需要兴趣 ≥ 45"这种真原因恰好躺在孤儿 id 里。玩家看到的是占位符。
- 所以 BUG-6 的修法不是"删孤儿就完事"，而是**把具体文案迁到 live id**，再删孤儿；`run_election` 是反例（它既是真选项 `events.json:198`、又带具体文案 `strings.json:98`），可作样板。

## 发布漂移（本轮顺带发现，单独记）

仓库里有 `dist-fixed/NaiwaCampus/_internal/content/{rules/events.json,text/zh_CN/strings.json}` 的**打包副本**，与源码是两份。改完代码/内容若不复包，分发出去的是旧代码 + 旧内容；建议在 BUG-0 收尾时确认 dist 复包策略，至少记录"dist 未同步"这一状态。

## BUG-7（发布核对）验收标准里有个洞——用 autoplay 验复包 = 假绿重现

bugscan 给 BUG-7 的验收是"复包后实跑 `dist/NaiwaCampus/NaiwaCampus.exe --offscreen --autoplay --frames 60000` 必须 `ok:true`"。**这条验不了 BUG-0 是否进包**，因为 `AutoplayDriver`（`app.py:900-918`）自己走 `services.event.choose` 并 `scenes.pop()` 掉 EventScene，**从不进 `EventSceneAdapter`**——这正是 BUG-0 能"全绿潜伏"的原因。同一个假绿会原样复现在 exe 上。

另外 `_internal/content` 与源码 SHA256 一致只证明**内容**没漂移；BUG-0 改的是 `world_scene.py`，它在 pyz 里，内容哈希对此**完全不敏感**。

因此 BUG-7 的验收应改成至少两条独立证据：
1. **行为**：复包后经**真实 UI 路径**验一次（`push("EventScene", event_id=...)` → 模拟确认 → 断言 `state.stats` 变化），或直接比对 pyz 内 `world_scene.py` 的源码/时间戳是否为新版；
2. **内容**：`_internal/content/**` 与源码 SHA256 一致（现有那条，保留但降级为辅助证据）。

建议：把 BUG-0 第 3 条要建的 adapter 级夹具抽成**公共夹具**，BUG-1（冒烟退出码）与 BUG-7（复包核对）复用同一套，否则三处各自造一遍，且都绕开真实路径。

## 第 2 批（进行中）：已读无新发现的模块

已完整读过、**未发现新缺陷**：`game/core/save_manager.py`、`game/world/interaction_service.py`、`game/world/player_controller.py`、`game/core/event_bus.py`（`TOPIC_ACTIVITY_DONE == "activity.done"` 与 `interaction_service.py:123,127` 的字面量一致，无 topic 拼写漂移）。这几处不必再有人重复扫。

## P2-A 主存档损坏时，读档界面看不到可恢复的 `.bak`

- **位置**：`game/core/save_manager.py:223-241` `peek()` 只读 `path_for(slot)`，不读 `bak_path_for(slot)`；而 `load()`（`:142-151`）会回退 `.bak`。
- **现象**：`<slot>.json` 损坏但 `<slot>.json.bak` 完好时，读档界面把该槽显示为"空槽"（`peek()` 返回 `None`），玩家根本看不到这条其实可恢复的存档；只有盲点该槽才会意外恢复成功。
- **修复方向**：`peek()` 在主文件解析失败时回退 `.bak` 并在 `SaveSummary` 上标一个 `from_backup=True`，让 UI 能提示"已回退到备份"。
- **验收**：手工写坏 `<slot>.json` → 读档界面仍列出该槽且标注备份来源 → 选择后能正常进入。

## P2-B（埋雷）生产路径没有注册任何存档迁移，`SAVE_VERSION` 一旦 bump 就是全量读档失败

- **位置**：`game/app.py:96` `self.saves = SaveManager()` —— 不传 `migrations`；全仓唯一传 `migrations=` 的是 `tests/core/test_save_manager.py:107`。
- **现象**：`save_manager.py:190-196` 的迁移循环在 `current < SAVE_VERSION` 且 `migrations` 为空时 `raise ValueError("no migration from save_version N")`，被 `_read_state`（`:183-184`）接成 `E_SAVE_CORRUPT`。当前 `config.SAVE_VERSION = 1`（`config.py:20`）所以休眠；一旦有人为"版本证据"去动它，所有旧档立刻全废。
- **顺带提醒**：BUG-7 要 bump 的是 `GAME_VERSION`（`config.py:19`，启动日志 `:300` 打印），**不是** `SAVE_VERSION`。这两个别混。
- **验收**：`SAVE_VERSION` 保持 1，或同时提供 `app.py:96` 的 `migrations={1: ...}` 且有单测覆盖"旧档能升级"。

## P2-B 补一条落地护栏：新增错误码会被静默降级成"存档 IO 错误"

`game/core/results.py:158-165` `SaveError.text_id` 只映射 4 个码（`E_SAVE_CORRUPT / E_SAVE_IO / E_SAVE_VERSION / E_SLOT_EMPTY`），**未知码一律 `.get(code, "err.save_io")`**。所以 BUG-9 若新增"迁移缺失"专用码而不动这张表，玩家看到的不是"存档损坏"而是更误导的"存档 IO 错误"——等于修了个寂寞。

落地要求：新码必须**同时**加到 `results.py:160-165` 的映射与 `content/text/zh_CN/strings.json`，并加一条单测断言 `SaveError("E_SAVE_MIGRATION").text_id != "err.save_io"`。

顺带核实：`app.py:91` 是 `strict_topics=options.dev`，所以生产环境 topic 拼写漂移确实是静默的——与 `SaveError` 这张表是同一类"未知输入静默降级"模式，值得作为一条通用审视点。

## BUG-0 工作区改动复核（未提交版本，行号会随改动漂移）

工作区已改成走服务层的版本，`_build_view`（现 `world_scene.py:652-655`）已用 `services.event.get_view`，`_show_content_error`（`:657-671`）接住 `ContentError`。三处顺手核过、**没问题**：`TextDB.has` 存在（`text_db.py:97`）、`EventScene._show_lock_hint` 存在（`event_scene.py:167`）、`ui.event.choice_locked_hint` 与 `ui.event.escape_hint` 文案齐全（`strings.json:252,254`）→ 这条 error path 不会漏 `#id`。

**但有一条 D-ST-05 违规**：`world_scene.py:665` `self.app.text.get("err.unknown_id")` 没传 `id=`。`err.unknown_id` 的值是 `"内容缺失：{id}"`（`strings.json:274`），而 `TextDB.get()`（`text_db.py:108-119`）见 `{` 就 `format(**fmt)`，`fmt` 为空 → `KeyError` → 记 error 日志后**原样返回带 `{id}` 的字符串**，玩家看到「内容缺失：{id}」。这正是该函数 docstring（`text_db.py:103-105`）明令禁止的情形。

修法：`self.app.text.get("err.unknown_id", id=event_id)`。

## BUG-10（P1，实机可见）四个存档错误码没有文案——已核实

`strings.json` 全量只有 7 条 `err.*`（`:269-275`：`no_slot / low_energy / daily_limit / already_talked / wrong_phase / unknown_id / choice_locked`），而 `results.py:160-165` 映射的 `err.save_corrupt / err.save_io / err.save_version / err.slot_empty` **一条都不在**。`TextDB.get_raw()`（`text_db.py:121-127`）缺 id 返回 `f"#{text_id}"` → 玩家读空槽/损坏档看到 `#err.slot_empty`。**BUG-9 的护栏要先补这 4 条文案，再谈新错误码。**

## BUG-11（P1）在室内存档 → 读档 → 所有交互点提示变成「内容缺失：<id>」，交互全部失效

**这是对"`prompt.py:58` 的 `E_UNKNOWN_ID` 可达性未证实"的回答：它可达，路径就是读档。**

链路（逐行核过）：

1. `flow.py:327-332` `load_game()` → `enter_campus(spawn=state.world.location_id, keep_position=True)`；
2. `flow.py:350` `scenes.change("CampusScene", spawn=state.world.location_id, state=state)` —— **没有 `position` 参数**；
3. `world_scene.py:170-171` `if ... and spawn: self._state.world.location_id = self._place_for(spawn)`，而 `WorldSceneBase._place_for`（`:284-285`）**原样返回 spawn**。若存档时玩家在室内，`location_id` 就是建筑 id（如 `loc_dorm`）→ 被原样写回；
4. `trigger_zone.py:101-104` `scene_of(state)` —— `location_id` 有对应 interior 就返回**室内 id**；
5. `interaction_service.py:142-148` `_lookup()` 发现 `ia.scene != scene_of(...)` → 返回 `None`；
6. `interaction_service.py:52-59` `query()` 于是返回 `PromptView(enabled=False, reason_code=E_UNKNOWN_ID)`；
7. `prompt.py:56-59` 拿 `ERROR_TEXT_IDS["E_UNKNOWN_ID"] = "err.unknown_id"` 去 `get()` → 见 BUG-10，渲染出「内容缺失：{id}」/`#err.unknown_id`。

**关键点**：`world_scene.py:196` 那个"用 `area_at()` 把 location_id 校正回室外区域"的修正分支，**只在传了 `position` 时执行**；`load_game` 不传 → 修正永远不生效。

**后果**：读室内存档后，室外场景里每一个交互点都变成"内容缺失"提示且不可交互（`enabled=False`），玩家坐标还是室内世界坐标（`collision_check` 默认 `None`，`_apply_load_position` 也不会兜底），角色可能站进建筑里。

**修法（原方案已作废，按实测更正）**：我原先建议的"`area_at()` 校正分支跑起来"**不够**——室内坐标 `(208.0, 1.6)` 不在任何室外 area 里，`area_at()` 返回 `None`，`location_id` 仍会留在 `loc_dorm`。正确做法：

1. `load_game` / `enter_campus` 先判 `map_data.has_interior(state.world.location_id)`（`map_data.py:424`）；
2. 是的话用 `map_data.exit_point(building_id)`（`map_data.py:462`，`interior_scene.py:99` 的 `exit_world()` 用的同一个入口）拿到门外落点 `(x, y, facing)`；
3. 把 `position=(x, y, facing)` 传给 `scenes.change("CampusScene", ...)`——**复用适配层已有分支** `world_scene.py:184-196`（它本来就会用 `area_at(exit_x, exit_y)` 校正 `location_id`），不必在 `flow.py` 里再写一套；
4. 顺带写回 `state.world.facing`，否则朝向是旧的。

**验收第 ② 条会卡在一个不存在的 API 上**：`collision.py` 只提供 `overlap(pos, half, rect)`（`:32`）、`move_and_collide`、`clamp_to_bounds`，**没有"点是否在碰撞体内"的查询**，而 `_apply_load_position` 要的正是 `Callable[[float, float], bool]`。补法（几行）：

```python
from game.world.collision import PLAYER_HALF, overlap
def blocked(x, y):
    scene = scene_of(state, map_data)          # 用当前场景的碰撞体，别固定 CAMPUS
    return any(overlap(_Vec(x, y), PLAYER_HALF, r) for r in map_data.colliders_for(scene))
```
注意必须取**当前场景**的 `colliders_for`，固定用 `CAMPUS_SCENE` 会让室内落点永远判为"不阻塞"。

**真正的成因在兜底值**：`world_scene.py` 写回 `location_id` 时用的是 `md.area_at(exit_x, exit_y) or self._state.world.location_id`——**取不到就当没事发生，保留旧值**。所以只要落点解析失败一次，`loc_dorm` 就被原样留下，BUG-11 复发。同一份逻辑在 `InteriorSceneAdapter._check_autostep` 里却是 `area_at(...) or "loc_gate"`，两处兜底不一致。建议统一成**安全默认**（`or "loc_gate"`），别用"保留旧值"——这与 `SaveError.text_id` 回落、`YEAR_IDS` 回落是同一个毛病：兜底取的是最误导的那个值。

**验收**：站在 5 个室内各存一次档 → 读档 → ①玩家坐标 = 该建筑门外落点、②`location_id` 是室外区域、③相邻交互点 `query().enabled == True`、④`reason_code` 不再出现 `E_UNKNOWN_ID`、⑤落点在碰撞体内能退回默认出生点。


## BUG-12（P3，维护陷阱）"出生点"这个概念有多个名字/副本

**更正过的准确清单**（我先前说"`DEFAULT_SPAWN_LOCATION` 有两份定义"是错的，已读原文核对）：

- `DEFAULT_SPAWN_LOCATION` **只有一份定义**：`game/core/state.py:26`；`flow.py:27` 是 `from .state import DEFAULT_SPAWN_LOCATION, GameState, WorldPos, new_state`（**import，不是第二份定义**）。
- 真正的第二个名字：`game/systems/spec_data.py:24-25` `START_LOCATION = "loc_gate"` / `START_POS = (40.0, 5.0)`。
- `camera_controller.py:35 DEFAULT_TARGET = (40.0, 5.0)` 语义是镜头初始目标，**不是出生点**，保留 + 加注释指向 `START_POS`。
- `"loc_gate"` 字面量：`flow.py:312`、`config.py:217`、`config.py:235`、`world_scene.py::InteriorSceneAdapter._check_autostep` 内（行号随改动漂移）、`save_manager.py:24`（映射键）。
- 坐标 `(40.0, 5.0)` **7 处**：`save_manager.py:24`、`save_manager.py:214`、`spec_data.py:25`、`camera_controller.py:35`、`flow.py:347`、`flow.py:354`、`state.py:270`（docstring）。
  - `save_manager.py:214` **必须算进去**：它是 `DEFAULT_SPAWN_BY_LOCATION.get(state.world.location_id, (40.0, 5.0))` 的**字面量默认参数**，不是引用；它本身也属于"`.get(..., 默认值)`"同族，按 6 处去 grep 会漏掉。

**收敛方案**：以 `spec_data.START_LOCATION / START_POS` 为唯一来源，`state.py:26` 反过来转发；`_check_autostep` 用常量不用字面量。

**规则后缀（双方各补一条）**：
- 报"重名定义"之前，先确认第二次出现是不是 `import`（对方补）；
- 报行号之前先**读到那一行的原文**——本次我误判 `flow.py:26` 是第二份定义，就是转述了别人给的行号、没读原文，这正是我一直劝别人别做的事（我补）。

## 两条 P3（建议并入唯一清单的 BUG-3）

- **教程步骤会被吞**：`game/ui/tutorial.py:43-50` `_start()` 在 `active_step` 非空时直接 `return`，不排队。`tut.move` 卡住期间玩家靠近交互点，`tut.interact` 永久丢失。
- **死代码**：`game/core/world_scene.py:362-365` 的 `if not view.enabled: notify("near_interactable") else: notify("near_interactable")` 两分支完全相同，会掩盖 BUG-3 那类判定错误。


## 验证来源声明（不要据此认为有人重复劳动）

- 本文件的结论来自**静态读取**（该 Session 的 `pwsh` 全量 `0xC0000142`，未跑过任何测试）；
- `bugscan_2026-11-09.md` 的基线数字来自另一个能跑命令的 Session，**我无法复现**，按报告采信；
- 我逐条静态核对过并与报告一致的部分：`config.py:224 frames=6`、`world_scene.py:684 _choose`、`world_scene.py:649-667 _build_view`、`app.py:900-918 AutoplayDriver`、`flow.py:463-480 handle_event_result`、`TOPIC_EVENT_FINISHED` 无订阅者、`tests/standalone_a/__main__.py:216` 写死 `"ok"`、`events.json` 用 `fair_*`、`assets/fonts/` 为空。
