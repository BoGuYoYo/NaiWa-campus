# C / D 整合报告（按 A 的共用规格）

日期：2026-11-09
提交：`07ad6ff A(merge): 按共用规格整合任务 C 与 D 的交付物`
范围：`game/world`（C）+ `game/ui`（D）+ 新增装配层 `game/core/world_scene.py`（A）

---

## 1. 一句话结论

C、D 的交付物现在能**合并即跑**：从主菜单 → 新建游戏 → 在校园里走动 → 进楼 →
用交互点做活动 → 看结果面板 → 日结算 → 学期事件 → 毕业，全链路自动化跑通，
测试 308 项全绿，autoplay 走完 16 天到 `ending_academic`，0 报错。

| 验证项 | 结果 |
| --- | --- |
| `pytest tests`（A + C + D 全部） | **308 passed**，exit 0 |
| `python -m tests.standalone_a --all` | 14/14 |
| `python -m tests.standalone_c --route C-R1 --fake-services` | exit 0 |
| `python -m tests.standalone_c --collision-fuzz 3000` | 阻挡 55 步、失败 0 |
| `python -m tests.standalone_c --camera-check` | 15/15 ok |
| `python -m tests.standalone_d --text-check` | 283 条正文 / 52 页，零问题 |
| `python -m tests.standalone_d --screen all` | 8 张截图，0 缺失文案 |
| `python -m game --dev --autoplay --offscreen --seed 42` | ok，48 次活动、8 个学期事件、ending_academic |
| `python -m tools.make_text_index --check` | 335 行索引与内容同步 |

截图证据：`reports/review/C+D/`（00 主菜单、01 校园+提示、02 查看点、03 结果面板+CG、
04 状态面板、05 宿舍室内、06 剧情选项）。

---

## 2. A 侧新增：装配层

`game/core/world_scene.py`（约 780 行）把 C 与 D 的产物包成场景协议：

| 场景 ID | 适配类 | 组装内容 |
| --- | --- | --- |
| `CampusScene` | `CampusSceneAdapter` | C 的 `CampusScene` 几何 + `PlayerController` + `CameraRig` + D 的 HUD/提示框 |
| `InteriorScene` | `InteriorSceneAdapter` | C 的 `InteriorScene` + 入口地垫自动退出 |
| `MainMenu` | `MainMenuSceneAdapter` | D 的主菜单 + A 的 `SaveManager` |
| `ResultPanel` | `ResultPanelSceneAdapter` | D 的结果面板 + 关闭后交给 `GameFlow.close_result_panel` |
| `EventScene` | `EventSceneAdapter` | D 的事件场景 + 用 `TextDB` 组出分页与选项 |
| `DaySummary` | `DaySummarySceneAdapter` | D 的日结算 + `GameFlow.today_activities` |
| `TabPanel` / `PauseMenu` / `SettingsMenu` / `SaveMenu` / `GraduationScene` | 各自适配类 | 键位、存档、设置落盘、毕业 4 页 |

配套改动：

- `SCENE_MODULES` 全部指向适配层；`make_scene` 的异常处理放宽到 `Exception` 并降级替身，
  避免"类存在但构造参数不对 → 启动即崩"。
- 相机只借用 C 的 `CameraRig`（死区/平滑/钳制），最终画面仍由 A 的
  `LowResPipeline.align_camera()` 落到 480×270 缓冲；C 的 `CameraController` 会改
  `base.cam`，与渲染管线抢镜头，故不启用。
- `AssetRegistry.load_font` 改用 `loader.loadFont()`（1.10.16 的 `TextFont()` 是抽象类，
  且只吃 unix 风格路径）；新增 `load_ui_font()` 在 `font_ui` 缺失时回退系统中文黑体。
- `GameFlow` 增加 `today_activities` 与 `FallbackRelationshipService`（B 未合入时交谈可用）。

---

## 3. C 的 5 处修正

1. `make_circle_lines` / `make_rect_lines`：`GeomLinestrips` → `GeomLines`。
   1.10.16 下线框**不渲染**（像素计数 0）且 `flattenStrong()` 踩断言，
   `loc_library` / `loc_canteen` 构造即崩；改后地垫红圈、NPC 圈、F1/F2 全部可见。
2. 区域分层 `AREA_Z`：道路 0.010/0.012/0.014、区域 0.020/0.022/0.024，消除整屏 z-fighting。
3. `interaction_service` 不再读 `state.energy`：交谈门槛交回
   `RelationshipService.can_talk/preview`，C 只透传错误码。
4. NPC 文案 ID：`npc.npc_sumo.talk` → `npc.sumo.talk`。
5. GUI 烟测参数化到 5 栋室内（原先只造 `loc_dorm`，所以第 1 条崩溃漏检）。

## 4. D 的 16 处修正

| # | 修正 | 之前的表现 |
| --- | --- | --- |
| 1 | `tutorial` 不再模块级继承 `UIWidget` | `pytest tests/ui` 收集期 `NameError`，整套挂掉 |
| 2 | `MultilineLabel` 支持补行 | 对话正文、结果文本、毕业正文**永远空白** |
| 3 | 每个界面自建容器节点 | 关掉的界面留在屏幕上（`--screen all` 是七层叠影） |
| 4 | 文本按左上角定位 | 所有标题上溢到面板边框外 |
| 5 | 面板着色 + 内衬 + 不透明 | 占位皮肤把白字洗掉、3D 场景透到正文下 |
| 6 | 活动 ID 归位（4 个） | 16 个文本键永不命中，`create_work` 没有文案 |
| 7 | 「敲代码」语义同步 | 结果图是代码屏，文案还在"画室/速写" |
| 8 | 头像 ID 归一到 4 档 | 9 处对话头像 8 处显示品红黑格 |
| 9 | 文本速度 4 档 20/40/80/instant | 整体慢一倍、缺 `fast` 档 |
| 10 | 音量键名对齐 `Settings` | 三个滑块完全无效 |
| 11 | 存档槽位对齐 `SaveManager` | `list_slots()` 抛异常被吞，永远显示"空"；存档直接 `ValueError` |
| 12 | 结果面板加载 `cg_naiwan_*` | 有 registry 时反而把插图藏掉，9 张 CG 一张不显示 |
| 13 | `insp.*` 换成 C 的 5 个查看点 | 两边各写一套，全不重合 |
| 14 | 新增 `ui.prompt.enter/save` | 门与存档点提示显示 `#...` |
| 15 | `TextDB` 变严格 + `get_raw()` | 占位符缺失静默留在界面上 |
| 16 | 截图命令改 `loadPrcFileData` + `getXSize` | 离屏缓冲 `set_size` 断言，一条命令也跑不起来 |

---

## 5. 跨模块契约（现在一致的版本）

| 契约 | 现值 |
| --- | --- |
| 9 个活动 ID | `attend_class / library_study / play_games / create_work / join_club / exercise / eat_canteen / rest_dorm / campus_walk` |
| 交互提示文案 | activity → `act.<id>.name`；npc → `npc.<短名>.talk`；door → `ui.prompt.enter`；save → `ui.prompt.save`；inspect → `insp.<短名>.name/.body` |
| 属性字段 | `game/world` 只读 `talked_today` / `world`；属性读写全在 `game/systems`（B）与 `game/core`（A） |
| 场景切换参数 | `CampusScene(spawn=, state=, position=)`；`InteriorScene(building_id=, state=)` |
| 存档 | `slot_1..3` + `autosave`，`list[SaveSummary]`，`summary["day_index"]` |
| 设置 | `master_volume / bgm_volume / sfx_volume / text_speed(slow20 normal40 fast80 instant)` |

---

## 6. 仍然待办（不属于这次整合）

1. **`assets/fonts/FusionPixel12.ttf`（LIC-0301）仍未交付**：现在靠系统 msyh 兜底，
   打包换机器会退回方框。这是 release blocker。
2. **B 的服务全是替身**：活动/日历/事件/结局/关系都走 `Fallback*`，数值不代表正式平衡。
3. **C 的 `props` 只有 2 个**（长椅、告示牌）：A 的 manifest 有 12 种道具，树与路灯的
   碰撞位置待 C 补登记。
4. **室内 `npc_marks` 与交互点差 1 米**（苏墨 mark(11,7) vs 交互点(11,6)），正式模型阶段对齐。
5. **UI 皮肤仍是占位**：28 个 `ui_*` 资源里 D 已接 22 个（面板/条/图标/键位），
   但资源本身是 A 的占位图，等正式 9-slice 与图标。
6. **B 的 `EventService.get_view`**：适配层现在直接从 `TextDB` 组事件视图，B 交付后
   应改为调用 B，并把 `ChoiceView.lock_reason_id` 当作完整 text_id 传进来。
