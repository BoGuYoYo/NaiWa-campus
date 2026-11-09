# 第 2 周整合记录（C / D 合入）

- 日期：2026-11-09
- 合并顺序：C（world）→ D（ui）→ A（装配层与资源）
- 基线：`week-1` 标签 + `6e1e866 A(audio)`
- 结果提交：`07ad6ff A(merge): 按共用规格整合任务 C 与 D 的交付物`

## 1. 已合并内容

### 1.1 任务 C（`game/world/`，10 个模块）

- `map_data` / `collision` / `trigger_zone` / `input_map`：纯逻辑，171 项无界面测试；
- `player_controller` / `camera_controller` / `interior_scene` / `campus_scene` / `debug_draw`：
  Panda3D 层，5 栋室内 + 1 张室外；
- `content/world/map.json`（5 建筑 / 6 区域 / 2 物件 / 5 室内）、
  `interactables.json`（18 交互点 + 5 门）；
- 修正 5 处（`GeomLinestrips` → `GeomLines`、区域分层、去 `state.energy`、
  NPC 文案 ID、GUI 测试参数化），详见 `docs/C_handover.md` §10。

### 1.2 任务 D（`game/ui/`，16 个模块 + 文案）

- 283 条 `strings.json` + 52 页 `dialogues.json`；`docs/ui/text_index.csv` 由
  `tools/make_text_index.py` 生成，335 行与内容同步；
- HUD / 提示框 / 结果面板 / 对话框 / 事件场景 / 日结算 / 状态面板 / 主菜单 /
  暂停 / 设置 / 存读档 / 毕业 / 教程 全部接进场景协议；
- 修正 16 处（导入错误、正文空白、隐藏残留、活动 ID、头像 ID、设置键名、
  存档槽位、插图、`insp.*`、TextDB、截图命令、夹具），详见 `docs/CHANGELOG_API.md` §9.3。

### 1.3 A 的装配层

- 新增 `game/core/world_scene.py`：11 个场景适配类；
- `make_scene` 降级保护、`AssetRegistry.load_ui_font()` 字体回退、
  `GameFlow.today_activities` 与 `FallbackRelationshipService`。

## 2. 验证（本机，全部 exit 0）

```text
pytest tests                                  → 308 passed
tests.standalone_a --all                      → 14/14
tests.standalone_c --route C-R1               → 7 活动 / 5 门 / 1 覆盖层
tests.standalone_c --collision-fuzz 3000      → 阻挡 55 / 失败 0
tests.standalone_c --camera-check             → 15/15
tests.standalone_d --text-check               → 283 条 / 52 页，零问题
tests.standalone_d --screen all               → 8 张截图，0 缺失
game --dev --autoplay --offscreen             → 48 次活动、8 学期事件、ending_academic
```

端到端手验路径（探针脚本已跑过）：主菜单 → 新游戏 → 校园走动（HUD + 交互提示）→
按 E 进宿舍（`InteriorScene`）→ 床（活动）→ 结果面板（CG + 数值）→ 踩地垫回室外
（坐标正好落在 `20.8, 40.0 − 1 = 19.8, 17.0`）→ Tab 状态面板 → Esc 暂停 → 存档写出 `slot_1.json`。

## 3. 已知问题

| 级别 | 问题 | 归属 |
| --- | --- | --- |
| P0 | `assets/fonts/FusionPixel12.ttf`（LIC-0301）未交付，现靠系统 msyh 兜底，换机器会退回方框 | A（release blocker） |
| P0 | B 的服务全部是替身：活动数值、日历、事件、结局判定都不代表正式平衡 | B |
| — | `props` 已扩到 25 个（13 树 / 5 路灯 / 5 桶 + 长椅 + 告示牌），草坪与道具贴图已接入 | C / A（已闭环） |
| P1 | 室内 `npc_marks` 与交互点坐标差 1 米 | C |
| P1 | UI 皮肤仍是 A 的占位图（28 个 `ui_*` 里 D 已接 22 个） | A / D |
| P2 | `EventSceneAdapter` 目前直接从 `TextDB` 组事件视图，B 交付后应改为调用 `EventService.get_view` | A / B |
| — | `DebugDraw`（F1/F2/F3/F5/F6）已接进适配层，A 的 FPS 开关让到 F7（截图 `reports/review/C+D/07_debug_draw.png`） | C / A（已闭环） |

## 4. 下周风险

1. **B 合入会改数值口径**：适配层已经把"拦不拦"的判定交给
   `ActivityService.can_start` 与 `RelationshipService.can_talk`，B 一旦换实现，
   D 的提示文案与 C 的交互点都不用改——但要重跑一遍 C-R1 与 autoplay。
2. **字体**：正式像素字体到位后需要复核 `UILabel` 的 `size` 与行高（现在 12px 是按
   msyh 调的，像素字体字面更小，可能要调 `FONT_SIZE_BODY`）。
3. **存档兼容**：本周没有改 `GameState` 字段，`save_version` 仍是 1；B 若加字段要
   走 `_migrate`。
4. **场景切换的落点约定**：`CampusScene(spawn, state, position)` 的 `position`
   由调用方给，`location_id` 由坐标反查区域。新增场景时必须遵守，否则
   `scene_of()` 会判错场景，交互点全部失效。
