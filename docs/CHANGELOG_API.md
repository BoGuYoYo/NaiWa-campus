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
- **角色精灵表已转正式**：`char_naiwan_walk` / `char_naiwan_idle` 由
  `tools/slice_reference_sheets.py` 从用户提供的单方向序列帧自动切片。素材更新（2026-11-07）后：
  - 一张图 = 一个方向，4 列 × 2 排 = FRAME 01～08；
  - 文件名词映射：向前→`s`、右前→`se`、向右→`e`、右后→`ne`、向后→`n`、左后→`nw`、向左→`w`、左前→`sw`；
  - `walk.png` 升级为 **384×384（8 帧）**，`manifest.json` 的 `cols` 从 4 改为 8；
    渲染层一律读 `entry.cols`，禁止硬编码 4 帧；
  - `idle.png` 仍为 144×384（3 帧），由各方向行走首帧做呼吸，可用 `--idle-source` 换成专门待机图；
  - manifest 里 `tags` 为 `["final", "sliced_from_reference"]`，许可记录 `LIC-0001`；
  - `tools/make_placeholders.py art` 已把这两张列入 `FINAL_ASSETS`，不会被占位图覆盖。

### 8. 内容变更登记（2026-11-07）

| 项 | 变更 | 影响方 | 说明 |
| --- | --- | --- | --- |
| 活动 `create_work` | 显示名「创作」→「**敲代码**」；插图 `cg_naiwan_create_work` 改为双屏写代码场景；图标 `ui_icon_create_work` 由画笔改为终端 + 代码行 | B（activities.json 文案）、D（文本/图标使用） | 活动 **ID 不变**（`create_work`，按 ID 冻结原则）；属性效果仍走 `interest`，具体数值由 B 定义 |
| 结局 `ending_creator` | 建议文案口径改为「独立开发者」，与上面的活动语义对齐 | B（endings.json）、D（结局文本） | 只改文案，ID 与判定条件不动 |
| 头像表情 ID | `portrait_naiwan_tired` → `portrait_naiwan_angry`；`portrait_naiwan_determined` → `portrait_naiwan_speechless`（用户实际交付的是「生气 / 无语」） | D（对话框、状态面板选表情） | 旧 ID 已从 manifest 移除；`game/core` 无硬编码，D 按 manifest 取即可 |
| 新增资源工具 | `tools/import_generated_art.py`（活动插图 160×90、头像 96×96 落位）；`tools/slice_reference_sheets.py` 新增 `--idle-source`；`tools/build_campus_models.py`（低多边形校园模型） | A/E（校验脚本可复用） | 头像、9 张插图、23 个模型均已转正式资源（`LIC-0006` / `LIC-0207`），`make_placeholders.py` 不再覆盖它们 |
| 校园模型转正式 | 5 栋建筑 + 5 个室内 + 地面 + 12 道具，按用户等距参考图在 Blender 中重构后转 BAM（ColorAttrib、无贴图） | C（场景摆放 / 占地对齐）、E（打包体积） | 当前室外 7,120 三角面、含室内共 7,816 三角面；占地是 A 的布景值，必须与 C 的 `content/world/map.json` 对齐后才算定稿 |
| 引擎坑（Panda3D 1.10） | `ShowBase` 已移除 `loadModel` 便捷方法 | 全员 | `AssetRegistry.load_model()` 改为 `getattr(loader, "loader", loader).loadModel(...)` |
| 缺陷修复（2026-11-08） | 关窗口后 BGM 还在响 | 全员（尤其 D 的菜单） | 三个原因一起修：① 1.10.16 的 `WindowProperties` **没有** `getCloseRequested()`，关闭判据是 `getOpen() == False`，`game/app.py::_on_window_event` 里调错 API 会让 ShowBase 的 `windowEvent` 一起崩 → 窗口关不掉；② `quit_game()` 退出前显式 `stop_audio()`（`AudioManager.stop_all()` 停音乐+音效并置静默）；③ `run()` 的 `finally` 再兜一次 `stop_audio()` + `destroy()`，任何退出路径都先停声音 |
| 校园贴图与道具（2026-11-09） | 新增草坪平铺贴图 + 树 / 路灯 / 垃圾桶 / 告示牌 4 张道具立牌；`map.json` 的 `props` 从 2 个扩到 25 个 | C（碰撞与路线）、E（打包体积） | 资源 `campus_texture_ground` 与 `campus_texture_prop_*`，许可 `LIC-0209`，由 `tools/import_campus_props.py` 生成；`CampusScene(ground_texture=, prop_art=, building_art=)` 支持贴图与立牌，不传时保持白模；建筑改用正面图后门从红色立块改成地面地垫 |

改内容 JSON 时不需要动 `game/core`：活动、文本、结局全部由 B/D 的 JSON 驱动，A 只提供 `asset_id`。

### 9. 整合 C / D 时对交付物做的修正（2026-11-09）

这一节记录 A 在把 C、D 的交付包合入 `develop` 时**按共用规格改掉的契约偏差**，
用于回溯"为什么和当初交付的版本不一样"。全部改动都可在 git 里逐条对照。

#### 9.1 接口契约（A 侧新增装配层）

| 项 | 变更 | 说明 |
| --- | --- | --- |
| 新增 `game/core/world_scene.py` | 场景适配层 | 规范里"场景协议"（`__init__(app, **kw)` / `on_enter` / `on_exit` / `on_update` / `is_overlay`）属于 A 的装配职责。C 交的是几何构建器、D 交的是 widget，都不是协议类；本文件把他们包成 `CampusSceneAdapter` / `InteriorSceneAdapter` / 9 个界面适配器 |
| `SCENE_MODULES` | 全部指向适配层 | 类名与构造约定统一由 A 维护；`game/world`、`game/ui` 里的类名今后不再被 `app.py` 直接引用 |
| `make_scene` 异常处理 | `except (ImportError, AttributeError)` → `except Exception` | 装配失败一律降级到 A 的替身场景并记 warning。旧写法下"类存在但构造参数不对"会直接冒到主循环，表现为合并即崩 |
| `AssetRegistry.load_font` | 改用 `loader.loadFont()` | Panda3D 1.10.16 的 `TextFont()` 是抽象类（实例化抛 `TypeError`），且 `loadFont` 只接受 Panda 风格 unix 路径（`/c/...`），传 Windows 路径或 `Filename` 都会失败 |
| 新增 `AssetRegistry.load_ui_font()` | 界面字体兜底 | manifest 的 `font_ui`（`assets/fonts/FusionPixel12.ttf`）仍未交付，缺失时按 `msyh.ttc` → `simhei.ttf` → … 顺序回退系统中文黑体，并写 `[FONT]` 日志。**打包前必须补正式字体**，否则换机器会退回方框 |
| `GameFlow.today_activities` | 新增 | 记录当天已完成的活动 id，供日结算面板显示「今天的 3 次行动」；`_begin_next_day` 时清空 |
| `FallbackRelationshipService` | 新增替身 | B 未合入时交谈要有反馈：`can_talk` / `preview` / `talk`（消耗 5 精力、社交 +2、占 1 个行动位）。正式版由 B 覆盖 |

#### 9.2 任务 C 的修正

| 项 | 变更 | 原因 |
| --- | --- | --- |
| `make_circle_lines` / `make_rect_lines` | `GeomLinestrips` → `GeomLines` | 1.10.16 下 `GeomLinestrips` 既不渲染（像素计数为 0），又会让 `flattenStrong()` 踩内存断言——`loc_library` / `loc_canteen` 构造即崩。改用逐段 `GeomLines` 后地垫红圈、NPC 站位圈、F1 碰撞线框、F2 交互点圆全部可见 |
| 区域分层 | 新增 `AREA_Z` 表 | 三条道路彼此相交、道路又与广场/操场重叠，原先统一 `z=0.02` 导致整屏 z-fighting 条纹；改为道路 0.010/0.012/0.014、区域 0.020/0.022/0.024 |
| `interaction_service.py` | 去掉 `state.energy` 读取与 `NPC_TALK_ENERGY_COST` | 共用规格要求 `game/world` 不读写属性字段；交谈能否进行改由 `RelationshipService.can_talk()` 判定，C 只透传错误码与 `preview` |
| NPC 提示文案 ID | `npc.npc_sumo.talk` → `npc.sumo.talk` | `target` 已带 `npc_` 前缀，旧写法在 D 的 strings.json 里没有对应键，提示框会显示 `#npc.npc_sumo.talk` |
| `tests/world/test_gui_scene.py` | 新增 5 栋室内参数化用例 | 原先只造 `loc_dorm`，所以 2/5 室内崩溃漏检 |

#### 9.3 任务 D 的修正

| 项 | 变更 | 原因 |
| --- | --- | --- |
| `tutorial.py` | `TutorialOverlay` 不再继承 `UIWidget` | 模块级继承需要 import `widgets`，而 `widgets` 依赖 panda3d，导致 `tests/ui` 收集阶段 `NameError` 全挂 |
| `widgets.MultilineLabel` | `set_lines()` 支持按需补行 | 旧实现只遍历构造时建好的行，而所有调用点都传 `[]` → 对话正文、结果文本、毕业正文永远空白 |
| `widgets.UIWidget` | 每个界面自建容器节点，子控件挂在容器下 | 旧版子控件挂在公共 parent 上，`hide()`/`destroy()` 收不干净，关掉的界面会留在屏幕上（`--screen all` 渲出来是七层叠影） |
| `UILabel` | 以「左上角」为锚点 | 旧版按基线定位，所有标题比面板上沿高出一行 |
| `UIPanel` | 9-slice 着色 + 内衬 + 固定绘制顺序 | 占位皮肤中心偏亮，会把白字洗掉；不透明度提到 1.0，避免 3D 场景透出来影响阅读 |
| 活动 ID | `studio_practice/dorm_rest/campus_stroll/gym_train` → `create_work/rest_dorm/campus_walk/exercise` | 规范 §A8 与 `manifest.json` 冻结的 9 个活动 ID；旧名导致 4 个活动共 16 个文本键永不命中 |
| `create_work` 文案 | 「画室练习 / 速写 / 调色」→「敲代码 / 跑通 / 重构」；`ending_creator` →「独立开发者」 | 与 §8 的内容变更（插图改成双屏写代码）对齐 |
| 头像 ID | `normal/smile/shy/worried/excited/touched/serious` → `neutral/happy/sad/surprised` | 旧 ID 在 manifest 里不存在，9 处对话头像 8 处显示品红黑格 |
| 文本速度 | `instant/normal/slow`（10/20 字每秒）→ `slow20/normal40/fast80/instant` | 与 `config.TEXT_SPEED_TABLE` 一致；旧值整体慢一倍且缺 `fast` 档 |
| 音量键名 | `volume_master/music/sfx` → `master_volume/bgm_volume/sfx_volume` | 直接读写 A 的 `config.Settings`，旧键名导致三个滑块完全无效 |
| 存读档 | 槽位 `"0"/"1"/"2"` + `dict.items()` → `slot_1..3` / `autosave` + `list[SaveSummary]` | 与 `SaveManager` 对齐；旧版 `list_slots()` 直接 `AttributeError`（被 except 吞掉，永远显示"空"），`save(None, "0")` 会抛 `ValueError` |
| 结果面板 | 按 `cg_naiwan_<activity_id>` 加载活动插图；有 registry 时不再隐藏占位 | 旧逻辑恰好相反：有 registry 就把插图藏掉且永不换图，9 张 CG 一张都显示不出来 |
| 查看点文案 | `insp.gate_board/lake_bank/billboard/statue/oak_tree` → `insp.gate_notice/course_board/bookshelf/librarian/canteen_aunt` | 与 C 的 `interactables.json` 的 5 个 inspect 点对齐；旧键名两边完全不重合 |
| 新增文案 | `ui.prompt.enter` / `ui.prompt.save` | C 的门与存档点提示用这两个 ID，D 原先没有，提示框显示 `#ui.prompt.enter` |
| `TextDB` | 新增 `get_raw()`；`get()` 变严格 | 文本里带 `{...}` 但参数没给齐时记 error 并返回原文（D-ST-05）；需要原样模板的调用点改走 `get_raw()` |
| `tests/standalone_d.py` | 离屏尺寸改用 `loadPrcFileData` | 离屏缓冲不可 `set_size()`（踩 `BF_resizeable` 断言），原截图命令一条也跑不起来 |
| `tests/ui/fixtures/strings.json` | 补齐断言用到的键 | 原夹具只有 11 条，4 个测试因此交付即红 |


---

### 10. 合入 B 的规则系统（2026-11-09）

B 的 `game/systems/`、`game/sim/`、`content/rules/` 正式合入。合入前 B 的包在 master 上
**29 条用例红、4 个服务静默退回替身、日常事件能把当天锁死**；下面是逐条对齐。
合入后：`pytest tests` 536 条（5 条 skip）、`game.sim` 6 策略 × 200 种子 1200/1200、
随机 3000 局分布与 `docs/balance_report.md` 一致。

#### 10.1 公共数据层（A 的 `game/core`）

| 项 | 变更 | 原因 |
| --- | --- | --- |
| `state.NPC_IDS` | 新增 `NPC_IDS = RELATIONSHIP_KEYS` | B 的 `spec_data` / `content_db` 从 `game.core.state` 取这个名字。缺它时 5 个规则服务里 **4 个 ImportError**，而 `resolve_services()` 会静默退回替身，表现为"接入了但数值全不对" |
| `GameState.validate()` | 新增 | B 的模拟器在结局判定前调用。它和 `clamp()` 分工不同：`clamp()` 是读档兜底（尽量修好），`validate()` 是"不该发生"的断言（算错就抛） |
| `GameState.copy()` | 新增，别名到 `snapshot()` | B 的存档续跑/批量模拟用 `copy()`；A 原来只有 `snapshot()` |
| `EventBus.emit()` | 返回值 `None` → `int`（实际调用的处理函数个数） | 手册只写了 `emit(topic, **data)`，没规定返回值；B 的 `test_event_bus.py` 6 条用例按"返回条数"断言。改成返回计数对现有调用方完全无害（旧调用都忽略返回值） |

#### 10.2 日常事件不再锁死当天（P0）

| 项 | 变更 | 原因 |
| --- | --- | --- |
| `flow.IMMEDIATE_EVENT_PREFIX` / `is_immediate_event()` | 新增 | B 的日常事件（`daily_*`）在规则层就已立即结算、不调用 `choose`、不进 EventScene（`B_delivery.md` 第 3 节第 5 条） |
| `GameFlow.handle_activity_result()` | `daily_*` 不再写 `pending_event_id`，改为把 `evt.<id>.body.1` 追加到 `result.text_ids` | 让玩家在结果面板里看到"遇见了什么"，同时不产生后续场景 |
| `GameFlow.close_result_panel()` | `daily_*` 不进 EventScene，直接结算当天 | 旧逻辑对所有 `triggered_event_id` 一律 `push("EventScene")` + `phase = "event"`；B 的 `end_day()` 有阶段守卫（只允许 `campus`），于是**当天再也过不去**，只能读档。第四周合入时实测复现 |
| `ResultPanel.continue_hint` | 立即事件仍显示「继续」 | 面板文案写着「有事情发生了……」但后面没有场景，属于误导 |

#### 10.3 交谈结果面板（B 的 `talk.*`）

| 项 | 变更 | 原因 |
| --- | --- | --- |
| `result_panel._talk_npc_short()` | 新增 | B 的 `talk()` 返回 `activity_id="talk.npc_sumo"`，面板按 `act.talk.npc_sumo.name` / `cg_naiwan_talk.npc_sumo` 取值 → 标题与正文显示 `#id`、插图走品红缺图 |
| `ResultPanel.show_result()` | `talk.*` 走 NPC 分支：标题 `npc.<short>.name`、正文 `npc.<short>.talk`、插图用占位色块 | 交谈是 NPC 交互，不是活动，没有 160×90 的活动 CG |

#### 10.4 文案兜底（`tools/gen_placeholder_text.py`）

B 只产出 `text_id`，正文归 D。合入时关系事件（27）、日常事件（24）、部分学期事件选项（23）、
交谈（3）等共 **120 条**在 `strings.json` 里还没有。做法：

1. 学期事件的选项/结果：D 其实写过，只是用了自己的 choice_id（`follow_chenlang` vs B 的 `fair_club`）。
   工具按"同一事件的第 k 个选项 ↔ 第 k 条文案"的位置对齐，把 D 的**正式文案迁到 B 的 id 上**，
   不让占位文案把真文案挤掉；
2. 剩下没有对应文案的（锁定提示、日常事件、交谈、关系事件）按规则 JSON 里的
   `title` / `effects` / NPC 名生成可读占位（选项受 12 字上限约束）；
3. 生成的 id 全部记进 `content/text/zh_CN/_placeholder_ids.json`，D 按清单替换正式文案即可；
4. `docs/ui/text_index.csv` 由 `tools/make_text_index.py` 重新生成（335 → 455 行）。

#### 10.5 测试与用例

| 项 | 变更 | 原因 |
| --- | --- | --- |
| `tests/systems/__init__.py` | 新增 | 否则 `tests/systems/test_state.py` 与 `tests/core/test_state.py` 同名冲突，pytest 收集直接报 import mismatch |
| `tests/systems/test_spec_sync.py` | `test_rules_pass_schema` 在 `content/schema/rules.schema.json` 缺失时 skip | 正式 JSON Schema 归 E；A 只搬了规则内容，没搬 B 的临时 schema。E 落库后自动生效 |
| `tests/core/test_flow.py` | 新增 `first_enabled_choice()` / `play_one_action()`；事件选择不再硬编 `"ok"`（B 的事件没有这个选项）；毕业断言放宽到 `TOTAL_DAYS-1..TOTAL_DAYS`（B 的日历在最后一天结算后把 `day_index` 推到 16） | 原来 4 条用例是按 A 的替身服务写的，接真服务后红 |
| `tests/core/test_flow.py` | 新增 `test_daily_event_is_immediate_and_does_not_lock_the_day` | 把 10.2 的锁死问题钉成回归用例 |

#### 10.6 未合入的 B 交付物

| 路径 | 处理 | 原因 |
| --- | --- | --- |
| `delivery_B/game/core/*` | 不合入 | B 的临时实现（与 A 的差 122/175 行），正式版以 A 为准 |
| `delivery_B/content/schema/rules.schema.json` | 不合入 | E 的正式 schema 未到，不留临时版占位 |
| `delivery_B/pytest.ini`、`requirements*.txt` | 不合入 | 与 E 维护的仓库配置双份版本源 |

#### 10.7 合并后仍待处理

| 事项 | 责任方 |
| --- | --- |
| `content/text/zh_CN/_placeholder_ids.json` 里 120 条占位文案换成正式文案 | D |
| `content/schema/rules.schema.json` 落库（落库后 5 条 skip 自动转正） | E |
| 日常事件的 HUD toast（现在只在结果面板显示一行） | D |
| `game/systems/spec_data.py` 与规则 JSON 的"唯一数值源"约束：改数值必须先改 `spec_data` 再 `python -m game.systems.spec_export` | B |

---

### 11. 修八向移动的动作显示（2026-11-09）

**现象**：角色按住方向键移动时，精灵会被"压扁/斜切"，走到正东、正西时几乎变成一条线；
只有正南（面朝镜头）看起来正常。

**根因**：`game/world/player_controller.py` 的 `_apply_transform()` 按 `FACING_HEADING`
给角色**卡片**做了 `setH()`。但本作是 2.5D：角色是"始终正对相机的一张卡"
（`render_pipeline.make_character_card` 已经用 `setP(CHARACTER_CARD_PITCH = -40°)`
做了俯仰补偿），八个方向由**精灵表的行**表达。再叠一层 yaw，卡片就会转离相机平面：
90°/270° 看到纸片侧边（一条线），45° 系列被斜向压缩。

**修复**：

| 文件 | 变更 |
| --- | --- |
| `game/world/player_controller.py` | `_apply_transform()` 固定 `setH(0.0)`，并注明"方向由精灵行表达、卡片不旋转" |
| `tests/world/test_player_motion.py` | `assert node.h == FACING_HEADING["e"]` → `assert node.h == 0.0` |
| `tests/world/test_gui_scene.py` | 同上（真实节点 `getH() == 0`） |

`FACING_HEADING` 常量保留（将来接 3D 模型还会用到），只是不再作用在 2.5D 卡片上。

**证据**：`reports/review/B/facing_before_slanted.png`（修复前：东向被压成斜条）与
`reports/review/B/facing_after_eight.png`（修复后：8 个方向都是直立卡片，
行序 s / se / e / ne / n / nw / w / sw 与美术一致）。

---

## BUG-24（2026-11-11）：E 键所有交互失效 —— 交互提示框 NameError

**现象**：走到任何可交互点都不弹提示，按 E 也不进建筑、打不开告示牌；日志每帧刷
`[SCENE] on_update failed: name 'rect' is not defined`。

**根因**：`game/ui/prompt.py` 的 `show_prompt()` 用了 `__init__` 里的局部变量 `rect`
（`theme.wrap_prompt_details(parts, rect[2] - 16, ...)`）。`enabled=True` 的提示一定会走这行，
于是 `NameError` 从 `_refresh_prompt()` 抛到 `on_update()`：提示框不显示，同帧后面的
`hud.update()` / `_check_autostep()` 也一起被跳过。`enabled=False`（能量不足等）走另一分支，
所以只有"可以交互"的提示会炸。

**修复**：

| 文件 | 变更 |
| --- | --- |
| `game/ui/prompt.py` | `__init__` 保存 `self._rect = theme.RECTS["prompt"]`，`show_prompt()` 用 `self._rect[2] - 16` 折行 |
| `game/core/world_scene.py` | `_refresh_prompt()` 里给 `show_prompt()` 加兜底 try/except：提示框渲染失败只记日志并隐藏，不再中断整帧（否则 E 会跟着一起死） |
| `tests/world/test_gui_scene.py` | 新增 `test_interaction_prompt_renders_enabled_and_disabled`：活动预览、门、禁用态三种提示都必须可见 |

**证据**：`reports/review/prompt_fixed.png`（门口显示「[E] 进入」、告示牌显示「[E] 校门告示牌」）。

---

## BUG-25（2026-11-11）：进出建筑后提示框显示「内容缺失」

**现象**：进入任一建筑再走出来，站在门口（或走到任何户外交互点）提示框变成
`[E] #ia.ia_door_dorm.name` / `内容缺失：ia_door_dorm`。

**根因**：`WorldSceneBase.on_enter()` 先按 `spawn` 写 `WorldPos.location_id`
（从室内回来时 `spawn` 传的是建筑 id），随后 `position` 分支用
`area_at(exit) or self._state.world.location_id` 兜底——新出口（如宿舍 16.924, 7.923）
不在任何登记区域内，`area_at` 返回 None，于是 location_id 保留成 `loc_dorm`。
`trigger_zone.scene_of()` 据此判成「室内」，户外交互点全部查不到，
`InteractionService.query()` 只能给 unknown 占位文案。

**修复**：

| 文件 | 变更 |
| --- | --- |
| `game/world/map_data.py` | 新增 `nearest_area(x, y)`（点到矩形距离）与 `outdoor_location_at(x, y, fallback="loc_gate")` |
| `game/core/world_scene.py` | 出口落点改用 `map_data.outdoor_location_at(...)`，不再拿旧的 location_id 兜底；室内地垫退出（`_check_autostep`）同样走这个函数 |
| `game/core/flow.py` | `load_game()` 新增 `_restore_outdoor_after_indoor_save()`：存档是在室内存的（坐标 200+、location_id 是建筑 id）时，读档落回该楼门外并改回室外地点 |
| `tests/world/test_map_data.py` | 新增 `test_nearest_area_falls_back_for_points_outside_every_area` 与 `test_exit_points_always_land_outside`（遍历 5 栋楼的出口，断言地点不是室内 id） |
| `tests/world/test_outdoor_location.py` | 新增：出口地点必须室外、室内存档读档后落在门外、室外存档保持原位置 |

**证据**：`reports/review/exit_prompt_fixed.png`（进出宿舍后提示框为「[E] 进入」）。

---

## NPC 资源更新（2026-11-12，`LIC-0212`）

第三名 NPC 的内部 ID 保持 `npc_xiaoyou` / `xiaoyou`，显示名更新为「奈珑」，
避免存档、关系规则和事件 ID 迁移。资源由用户提供的 `奈珑八向图.jfif` 正面大图裁切：

| 资源 | 尺寸 | 说明 |
| --- | --- | --- |
| `char_npc_xiaoyou_idle` | 48×48 | 场景内正面像素立牌，脚点 `(24, 46)` |
| `portrait_npc_xiaoyou_neutral` | 96×96 | 对话头像 |
| `portrait_npc_xiaoyou_happy` | 96×96 | 本轮暂复用正面头像 |
| `portrait_npc_xiaoyou_sad` | 96×96 | 本轮暂复用正面头像 |
| `portrait_npc_xiaoyou_surprised` | 96×96 | 本轮暂复用正面头像 |

处理工具：`tools/import_nailong_character.py`。直接使用 `01_FRONT.png` 的透明 Alpha，最近邻缩放到目标尺寸；
对照图见 `reports/review/npc/nailong_sheet.png`。

---

## 待办接口（尚未提供，先登记）

| 编号 | 内容 | 需求方 | 状态 |
| --- | --- | --- | --- |
| REQ-001 | `InteractionService.query()` 的 `cost_preview` 键名与 B 的 `effects` 键表对齐 | C/D | 待 B 确认 |
| REQ-002 | `EventScene` 需要 `page_text_ids` 之外的立绘 `portrait_id` 字段 | D | 待评估（会改 `EventView`） |
| REQ-003 | `SaveManager` 增加“导出/导入单个存档”接口供 E 的测试包使用 | E | 待评估 |
