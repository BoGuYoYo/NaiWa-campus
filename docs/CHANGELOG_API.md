# 公共接口变更记录 CHANGELOG_API

维护人：开发者 A。任何人只能通过“接口变更请求”修改本文件记录的内容。

格式：版本号 + 日期 + 变更点 + 影响范围 + 迁移方式。版本号与 `game/config.py` 的
`GAME_VERSION` 独立：接口版本升到 v1.1 才允许破坏性改动。

---

## v1.0.0 — 2026-01-05（首个可运行基线）

### 1. 数据类（`game/core/state.py`、`game/core/results.py`）

已按手册第 5 节实现，字段名与默认值完全一致：

- `WorldPos(location_id="loc_gate", x=40.0, y=5.0, facing="n")`，`facing ∈ {s,se,e,ne,n,nw,w,sw}`
- `GameState`：`save_version=1 seed=42 day_index=0 action_slot=0 stats{academic=10,stamina=20,
  social=10,interest=10} mood=60 energy=84 relationships{npc_sumo,npc_chenlang,npc_xiaoyou=0}
  flags counters today_counts talked_today event_log pending_event_id phase ending_id world
  tutorial_done play_seconds`
- 派生属性：`year / semester / day / semester_no / actions_left / day_finished / is_last_day`，
  以及 `max_energy() = 80 + stats["stamina"] // 5`
- `ActivityResult / DayEndResult / ChoiceView / EventView / EventResult / EndingResult /
  PromptView / InteractionResult` 与手册一致；额外提供 `SaveSummary`、`SaveError`
- 序列化：`GameState.to_dict()` 把 3 个 set 排序后输出 list；`from_dict()` 容忍缺字段与非法值，
  并在末尾调用 `clamp()`（只做兜底，正式截断仍由 B 的 `effects.apply()` 负责）

### 2. 服务接口（B/C 提供，A/D 调用）

签名未改，直接照手册：

```python
ActivityService.can_start(state, activity_id) -> (bool, error_code|None)
ActivityService.start(state, activity_id) -> ActivityResult        # 会修改 state
ActivityService.preview(state, activity_id) -> dict[str, int]
RelationshipService.talk(state, npc_id) -> ActivityResult
CalendarService.end_day(state) -> DayEndResult
EventService.get_view(state, event_id) -> EventView
EventService.choose(state, event_id, choice_id) -> EventResult
EndingService.evaluate(state) -> EndingResult
InteractionService.query(state, interactable_id) -> PromptView
InteractionService.interact(state, interactable_id) -> InteractionResult
```

`GameFlow` 只通过约定模块名导入：`game.systems.activity_service.ActivityService`、
`game.systems.calendar_service.CalendarService`、`game.systems.event_service.EventService`、
`game.systems.ending_service.EndingService`、`game.systems.relationship_service.RelationshipService`、
`game.world.interaction_service.InteractionService`。导入失败时回退到 A 的替身实现，并在日志中
标注 `[FLOW] services: {...}`，**不会**因为别人没写完而阻塞 A 的独立验收。

### 3. 结果面板与事件的时序（重要，D 必须照做）

`ActivityService.start()` 返回后，**流程不立刻推进**：

1. C 调用 `GameFlow.handle_activity_result(result)` —— 只广播 `activity.done` 并记录；
2. D 用 `result` 打开 `ResultPanel`；
3. 面板关闭时调用 `GameFlow.close_result_panel(result)` —— 有 `triggered_event_id` 就 push
   `EventScene`，否则 `day_finished` 就调用 `finish_day()`。

`finish_day()` 内部顺序：`CalendarService.end_day` → `day.ended` → autosave(`day_end`) →
push `DaySummary` → 学期事件（autosave `pre_event` → `EventScene`）→ 事件关闭 autosave
`post_event` → 新一天（传送 `loc_gate (40,5)` `facing="n"`）。最后一天的学期事件（`sem_8`）
处理完后才进 `GraduationScene`，然后 `phase=finished` → 回主菜单。

### 4. 事件总线主题

`activity.done`、`day.ended`、`day.started`、`event.started`、`event.finished`、`scene.changed`、
`game.graduated`、`asset.missing`、`save.written`、`settings.changed`。
订阅者抛异常不会影响发出方，异常进 `EventBus.errors` 并写日志（便于 E 断言）。

### 5. 任务 sort 约定

`input_poll=10 / world_update=20 / interaction_scan=30 / ui_update=40 / flow_tick=45 / 其他 ≥50`。
A 只注册 `flow_tick(45)`、`offscreen_capture(60)`、`autoplay(70)`。其他人新增任务必须走
`NaiwaApp.add_owned_task(func, name, sort)`，`sort < 50` 会直接抛 `ValueError`。
每帧 `dt` 由 A 钳到 `1/30` 秒。

### 6. Panda3D 1.10.16 实测陷阱（务必遵守，否则会白掉一天）

| 现象 | 原因 | 正确做法 |
| --- | --- | --- |
| `loadTexture("C:\\...\\walk.png")` 报 `couldn't read` / 路径变乱码 | 传 `str` 会被当成 model-path 相对路径，且非 ASCII 丢字符 | 一律 `Filename.fromOsSpecific(str(path))` 再交给 `loader.loadTexture/loadModel/loadSfx` |
| 192×384 精灵表被读成 128×256，像素糊 | Panda 默认把非 2 幂纹理缩放 | PRC 里 `textures-power-2 none`（`apply_prc()` 已设） |
| 角色卡片整张看不见 | CardMaker 卡片默认立在 XZ 平面、法线朝 -Y；P 给正角会让卡片与视方向平行 | 角色卡片 `P = CAMERA_TILT = -40`；地面/建筑占地才用 `P = -90` |
| `getScreenshot()` 返回值不是 PNMImage | 1.10 返回 `Texture`（1.11 才返回 PNMImage） | `Texture.store(PNMImage)` 后 `PNMImage.write(Filename)` |
| 覆写 `ShowBase.shutdown()` 后启动即崩 | ShowBase 的 `restart()` 会调用 `self.shutdown()` | A 的退出方法叫 `quit_game(exit_code)`，不要覆盖引擎生命周期方法 |
| 离屏模式下 `win.getProperties()` 不存在 | `win` 是 `GraphicsBuffer` | 用 `win.getXSize()/getYSize()`，A 的 `LowResPipeline.window_size()` 已处理 |

### 7. 资源与许可

- 代码里只能出现 `asset_id`，不得出现文件路径；缺失资源返回品红黑格（精灵/贴图）、静音（音频）、
  1 米灰色立方体（模型），并写日志 `[ASSET] missing id=<asset_id> path=<path> hint=检查 manifest 与文件名大小写`
- `assets/manifest.json` 的 `type` 只允许 `sprite_sheet/image/model/sound/music/font`；
  `sprite_sheet` 必须带 `frame_w/frame_h/cols/rows/fps/pivot`，`music` 必须带 `loop`
- `AssetRegistry.release_blockers()` 返回 `commercial_ok != yes` 的资源，发布脚本必须挡住

---

## 待办接口（尚未提供，先登记）

| 编号 | 内容 | 需求方 | 状态 |
| --- | --- | --- | --- |
| REQ-001 | `InteractionService.query()` 的 `cost_preview` 键名与 B 的 `effects` 键表对齐 | C/D | 待 B 确认 |
| REQ-002 | `EventScene` 需要 `page_text_ids` 之外的立绘 `portrait_id` 字段 | D | 待评估（会改 `EventView`） |
| REQ-003 | `SaveManager` 增加“导出/导入单个存档”接口供 E 的测试包使用 | E | 待评估 |
