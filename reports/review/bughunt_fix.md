# 全量 BUG 排查修复报告（A · 整合修复第 12 轮）

来源：四方（core / systems / ui / world）独立排查合并去重后的 20 条结论。
本文按"高 → 中 → 低"的顺序记录**每条的现象、根因、改法、证据与守卫测试**。
复现脚本位于 `奶娃\.tmp\bughunt_*`（不入库），验证脚本在此基础上补了
`verify_fade_tab.py`、`verify_debug_exit.py`、`verify_interior_day.py`。

- 提交前状态：`pytest tests` 全绿；`--autoplay` 16 天 + 8 学期事件 + 毕业 `ok=True`。
- 回归测试：`tests/core/test_bughunt_regressions.py`（19 条）、
  `tests/ui/test_bughunt_ui_regressions.py`（12 条）。
- 证据截图：`reports/review/bughunt/`。

---

## 高（卡死 / 崩溃 / 丢进度）

### H1 当天第 3 个行动触发关系事件 → 当天卡死、存档一起坏

- **现象**：第 2 学期起，在当天第 3 个行动与关系约 18 的 NPC 交谈 → 事件结束后日子推不下去，
  所有活动都提示「没有行动次数」；此时退出，自动存档读回来同样死。
- **根因**：`GameFlow.close_result_panel()` 遇到 `triggered_event_id` 时 `return` 得早，
  `payload.day_finished` 被丢掉；`handle_event_result()` 只处理"学期事件后开新的一天"，
  没有任何地方补"这一天结束"。`finish_day()` 因此永远不会被调用，`action_slot` 停在 3。
- **改法**：
  - `flow.py` 新增 `_pending_day_end`；`close_result_panel()` 在 push EventScene 前记下
    `payload.day_finished`；`handle_event_result()` 在事件结算后 `finish_day()`。
  - `state.day_finished` 作为兜底：读档重播的事件同样能把这一天收掉。
  - `finish_day()` 增加阶段守卫（phase 不是 campus 时拒绝并记日志），不再把
    `pending_event_id` 覆盖成 None。
- **守卫**：`test_third_action_relationship_event_still_ends_the_day`、
  `test_immediate_daily_event_on_last_action_still_ends_the_day`。

### H2 暂停菜单读档绕过 `flow.load_game` → 4 个连带问题

- **现象**：室内存的档，读出来人卡在室外东墙里、户外交互全失效；游戏一直暂停
  （游玩时长不再累计）；读最后一个自动存档进入不能操作的毕业状态；上一局暂存数据不清。
- **根因**：`SaveMenuSceneAdapter._loaded()` 自己 `flow.state = state` + `change("CampusScene")`，
  跳过了 `load_game()` 里的室内→室外地修复、`paused=False`、`_reset_pending_modals()`。
- **改法**：`GameFlow.adopt_loaded_state(state)` 抽出"接管一份已读出的存档"的全部逻辑，
  `load_game()` 与读档界面共用；`_loaded()` 改为调用它。
- **守卫**：`test_loading_an_indoor_save_lands_outside_and_unpauses`（含 `play_seconds` 累计）。

### H3 日结算面板/学期事件中途退出 → 学期事件被永久跳过

- **现象**：第 2、4、6…天结束（或学期事件播到一半）退出，按"继续"直接回校园，
  事件给的旗标拿不到，结局判定受影响。
- **根因**：两处叠加。
  1. `finish_day()` 在写 `day_end` 自动存档前把 `state.pending_event_id` 清成 None；
  2. `load_game()` 无条件 `state.phase = "campus"`，把待处理事件一起抹掉。
- **改法**：
  - `finish_day()` 写完 `end_day` 后保留 `state.pending_event_id = result.semester_event_id`
    （`_begin_next_day()` 才清）；
  - 新增 `_event_settled()` / `_open_pending_event()`：读档时若事件未结算，恢复 `phase=event`
    并在校园场景 `on_ready` 后重新 push EventScene（学期事件同时排上"第二天"与"毕业"标记）。
- **守卫**：`test_semester_event_survives_quitting_on_the_day_summary`。

### H4 通关后按"继续"重玩第 16 天 → 重复触发学期事件报错卡死

- **根因**：`GameState.clamp()` 把 `day_index` 钳到 `TOTAL_DAYS-1`（15）。B 的 `calendar`
  在第 16 天结束时会把 `day_index` 推到 16（"已读完"），存档写的是 16，读档被钳回 15
  → 玩家回到最后一天，再结算一次 → `sem_8_*` 已在 `event_log` 里 → `EventService.choose`
  的幂等保护抛 `ContentError`，界面停住。
- **改法**：`clamp()` 上界改为 `TOTAL_DAYS`（与 `validate()` 一致）；
  `adopt_loaded_state()` 对 `day_index >= TOTAL_DAYS` 或 `phase in (graduation, finished)`
  直接评结局进毕业界面（`_resume_graduation()` / `_show_graduation()`）。
- **守卫**：`test_day_index_may_reach_total_days`、`test_loading_a_finished_save_goes_to_graduation`、
  `tests/core/test_state.py::test_from_dict_tolerates_garbage_and_clamps`（上界改为 16）。

### H5 暂停菜单选"继续"后卡住

- **根因**：`PauseMenuSceneAdapter._confirm()` 没有 `ui.menu.resume` 分支；
  而 `PauseMenu.confirm()` 已经把控件 `hide()` 了 —— 菜单看不见、覆盖层还在栈上、输入仍锁。
- **改法**：补 `ui.menu.resume → self._resume()`。
- **守卫**：`test_pause_menu_resume_pops_the_overlay_and_unpauses`。

### H6 从暂停菜单存档后返回，看不见暂停菜单（像卡死）

- **根因**：`SaveMenu` 关闭只 `pop()`，暂停菜单的控件仍是 `confirm()` 时 hide 掉的状态。
- **改法**：`WidgetSceneBase` 抽 `_hide_underlay()/_restore_underlay()`，
  `SaveMenuSceneAdapter` 与 `SettingsMenuSceneAdapter` 共用（打开时藏下层、退出时显回来）。
- **守卫**：`test_save_menu_restores_the_pause_menu_behind_it`。

### H7 毕业最后一页连按两下崩溃

- **根因**：`GraduationScene.on_space()` 最后一页 → `hide()` + `on_back_to_menu()`；
  黑场期间场景还在台上，第二下再调 `flow.finish_graduation()`，而 `state` 已被清空 →
  `require_state()` 抛 `RuntimeError`。
- **改法**：`GraduationScene` 增加 `_closed` 一次性闸门；`GameFlow.finish_graduation()`
  在 `state is None` 时直接返回。
- **守卫**：`test_graduation_last_page_double_press_calls_back_once`。

### H8 黑场时按 Tab / Esc 把面板挂到即将销毁的场景上

- **现象**：进门/出门后 0.25 秒内按 Tab，背包面板关不掉；回主菜单的黑场里按 Esc，
  暂停菜单盖在主菜单上。
- **根因**：`_on_tab/_on_escape` 只检查 `scenes.overlays`，没有检查 `is_transitioning()`。
- **改法**：`WorldSceneBase._transitioning()` + 三个入口（`_on_interact/_on_tab/_on_escape`）
  在黑场期间直接返回；`MainMenuSceneAdapter` 的确认键同样加闸（防重复"新游戏"）。
- **守卫**：`test_tab_and_escape_are_ignored_while_the_screen_fades`、
  `test_tab_still_works_after_the_fade`；实机验证 `verify_fade_tab.py`
  → `[D] base MainMenu overlays []`。

---

## 中

### M1 日结算标题永远是"第 1 天结束"

- **根因**：适配层用 `max(1, state.day - 1)`。`state.day` 是「每学期 2 天」的取模值
  （day_index 偶数时为 1），减 1 后必被 `max` 兜成 1。
- **改法**：改由 `DayEndResult.new_day_index - 1` 反推 `ended_index % DAYS_PER_SEMESTER + 1`。
- **守卫**：`test_day_summary_label_uses_the_finished_day_not_the_modulo_day`；
  实机截图 `reports/review/bughunt/day_summary_day1.png` / `day_summary_day2.png`（第 2 天结束）。

### M2 新游戏/读档后 `today_activities` 不清空

- **改法**：`new_game()` 与 `adopt_loaded_state()` 都清空 `today_activities` 与
  `last_activity_result`。
- **守卫**：`test_new_game_clears_today_activities`。

### M3 文本速度设置不生效；音量要等换歌

- **根因**：全项目没有任何地方调用 `DialogueBox.set_text_speed()`；也没有调用
  `AudioManager.apply_settings()`（只有 `play_music()` 里顺手应用一次）。
- **改法**：`EventScene.set_text_speed()` → `DialogueBox.set_text_speed()`；
  `EventSceneAdapter.apply()` 每次打开事件都用 `settings.text_speed` 同步；
  `SettingsMenuSceneAdapter` 在 `_adjust()` 与 `on_exit()` 调 `audio.apply_settings()`。
- **守卫**：`test_text_speed_setting_reaches_the_typewriter`；实机 `repro.py`
  → `[4] dialogue cps with text_speed=instant: 0.0`。

### M4 卡在碰撞体里时往某些方向走会被推回原处；读档位置保护从未被调用

- **根因（两个）**：
  1. `move_and_collide()` 对"起始就已经压着"的矩形也做方向性贴合，
     结果人被瞬间弹到墙的另一侧（观感就是"按了没反应/被推回原处"）；
  2. `SaveManager.load(collision_check=...)` 是空钩子，全项目没有一个调用方，
     室内存档读出来站在墙里就再也走不出去。
- **改法**：
  - `collision.py`：起始帧已压着的矩形不参与解算（离开后恢复阻挡），人能自己走出来；
  - `MapData.is_blocked()/safe_position()` 新增（室内按房间原点平移判断）；
    `GameFlow._repair_world_position()` 在读档接管时校验坐标，落在阻挡体里就退回该地点安全落点。
- **守卫**：`test_player_can_walk_out_of_a_wall_instead_of_being_snapped_back`、
  `test_load_repairs_a_position_inside_a_wall`。

### M5 事件正文可能被截断

- **根因**：`EventSceneAdapter._build_view()` 无条件用 `evt.<id>.body.*` 覆盖规则页；
  一份都找不到时把 `page_text_ids` 覆盖成空列表 → 对话框只剩一条翻页提示（正文丢失）。
  另外 `DialogueBox._wrap_lines()` 超出 4 行是静默截断。
- **改法**：无文案时保留规则页并记 warning；折行超限时打 warning 日志（数据问题可见）。
  规则页与文案页数量的对偶性由既有 `tests/systems/test_event_pages_consistency.py` 守住
  （`dialogue` 是权威分页源，`pages_source: rules` 才用规则页）。
- **守卫**：`tests/core/test_event_scene_adapter.py`（既有）+ 新增日志断言路径。

### M6 低电量 / 教程横幅可能一直不消失

- **根因**：`tut.slots`、`tut.energy` 只由 `key_space`（E 键）完成，玩家不按 E 就永久挂着。
- **改法**：`TutorialController._tick()` 增加每步兜底超时（`theme.TUTORIAL_STEP_TIMEOUT_SECONDS = 45s`，
  `tut.tab` 仍为 30s）。
- **守卫**：`test_tutorial_banner_times_out_instead_of_hanging`。

### M7 事件只有一个选项且被锁时会卡死（未复现风险项）

- **改法**：双层防线。
  1. 规则层：`ContentDB` 现在要求**每个事件**都有至少 1 个无条件选项（原来只约束学期事件）；
  2. 界面层：单选项被锁时不再"按键即确认"，且全锁时允许 Esc 离开（记 error 日志）。
- **守卫**：`test_event_with_only_conditional_choices_is_rejected`、
  `test_single_locked_choice_does_not_confirm_and_can_be_left`。

### M8 事件选择时鼠标点哪里都会确认当前选项（未复现风险项）

- **根因**：`EventSceneAdapter` 把 `mouse1` 直接绑到 `on_space`。
- **改法**：新增 `EventScene.on_click()`：选项阶段直接忽略，其余等价 Space。
- **守卫**：`test_click_does_not_pick_a_choice`、`test_click_still_advances_normal_dialogue`。

---

## 低

| # | 问题 | 改法 | 守卫 |
| --- | --- | --- | --- |
| L1 | 出门立刻又显示"进入"，连按 E 弹回室内 | `MapData.EXIT_DISTANCE = 1.8`（门半径 1.2 + 玩家半身 0.35 之外） | `test_exit_point_is_outside_the_door_trigger_radius`；实机 `verify_debug_exit.py` → 出口处 `active interactable: None` |
| L2 | 换日传送后镜头从远处平移 | `WorldSceneBase.teleport()` 传送后立刻 `_apply_scene_camera()`（重设相机死区/对齐） | 代码路径 + 换日实机走查 |
| L3 | 事件结果页逐字显示时一按就关 | `on_space/on_escape` 在 `_showing_result` 时先 `dialogue.advance()`，整页后才关 | `test_result_page_typewriter_is_finished_before_it_closes` |
| L4 | 存档版本号固定写 1 | `SaveManager.save()` 写 `config.SAVE_VERSION` | `test_save_payload_uses_current_save_version` |
| L5 | 主存档损坏但备份完好时列表显示"空" | `peek()` 回退 `.bak` 并记 warning | `test_peek_falls_back_to_the_backup_file` |
| L6 | 结局回顾里同一事件重复 | `EndingService._highlights()` 只取已结算的 `id:choice` 并按事件 id 去重 | `test_highlights_do_not_repeat_the_same_semester_event` |
| L7 | 关系事件只在"交谈"时检查阈值 | 抽出 `RelationshipService.check_stage()`；`GameFlow._maybe_trigger_relationship_event()` 在任意活动后补查 | `test_relationship_event_triggers_from_a_non_talk_activity` |
| L8 | 内容校验查不出旗标拼错/结局优先级重复 | `ContentDB` 收集"谁会产出旗标"（规则文件 + `spec_data` 的计数器/熬夜/关系阶段旗标），条件里引用的旗标必须存在；结局 `priority` 必须唯一且为整数 | `test_unknown_flag_reference_is_rejected`、`test_duplicate_ending_priority_is_rejected` |
| L9 | 食堂阿姨站在打饭窗口台里 | `content/world/map.json`：阿姨 `(5.0, 9.4) → (5.0, 8.4)`（窗口台矩形 3.0~11.0 × 9.0~9.9 之外） | `verify_interior_day.py` → 落在家具里 `[]`；截图 `canteen_interior.png` |
| L10 | `--dev` 下 F5 报 ValueError | `WorldSceneBase._debug_goto(scene, x, y)` 接住 DebugDraw 的 `(场景, x, y)` 调用；跨场景改走 `scenes.change(...)`（室内新增 `at=` 落点参数） | `verify_debug_exit.py` → F5 ok 三次 |
| L11 | `--dev` 下 F1 室内碰撞线框画错位置 | `DebugDraw._build_collision()` 给室内矩形加上房间原点 | `verify_interior_day.py` → 线框 x 范围 280~296 = 期望值 |

### 额外一并修掉的同类问题

- **链式事件被丢弃**：`EventService.choose()` 把 `next_event_id` 写进 `pending_event_id`，
  但 `handle_event_result()` 统一清成 campus → 下一段永远播不到（选项效果却已生效）。
  现在检测到未结算的 `next_event_id` 就继续 push EventScene。
  守卫：`test_chained_event_is_pushed_instead_of_dropped`。
- **"当天行动用完、还没结算"的存档读回来是死档**：`adopt_loaded_state()` 在
  `day_finished` 且无待处理事件时补结算（`on_ready` 里 `finish_day()`）。
  守卫：`test_loading_a_save_that_used_up_the_day_ends_it`。

---

## 验证记录

```text
pytest tests -q                        # 全绿（新增 31 条回归断言）
python -m game --dev --offscreen --autoplay --seed 42 --skip-intro --frames 1200
  → [AUTOPLAY] ok=True steps=58 phases=[campus, event]×8 + graduation
dist\NaiwaCampus\NaiwaCampus.exe --dev --scene CampusScene --skip-intro --offscreen --frames 40
  → services 6/6 real, BOOT/FONT ok, quit exit_code=0
dist\NaiwaCampus\NaiwaCampus.exe --dev --offscreen --autoplay --seed 7 --frames 1200
  → [AUTOPLAY] ok=True steps=58
```

`.tmp/bughunt_*` 原脚本结果：

- `bughunt_core/repro.py`：1→DaySummary 且 slot 归零；2→`phase event pending sem_1_club_fair`，
  读档后 `overlay EventScene`；4→`today_activities []`；6→`phase event pending next_evt`。
- `bughunt_ui/repro.py`：`[1] overlays [] locked False paused False`、
  `[2] overlays ['PauseMenu'] visible True`、`[3] play_seconds advanced 0.65`、`[4] cps 0.0`。
- `bughunt_ui/repro2.py`：`[A] loc_playground pos 16.924 7.123`（不再卡墙）、`[B] no exception`。
- `bughunt_world/repro.py`：卡墙后按 A 能走出（77.233），F5 签名正确。
