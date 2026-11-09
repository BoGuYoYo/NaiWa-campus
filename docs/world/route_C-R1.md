# 路线 C-R1：校园漫游烟测

> 对应《任务 C 校园场景移动相机碰撞与交互》表 19 的 C-01（人工烟测）与 C-04。
> 本文件是任务 C 的交付物之一，用于人工验证「移动 + 碰撞 + 相机 + 门/室内切换 + 交互点到服务映射」的端到端行为。
> 每一步的坐标与预期结果均取自 `content/world/map.json`、`content/world/interactables.json`。

## 1. 目的

沿一条固定路线走完全部 5 栋建筑与 3 个室外交互点，确认：

- 玩家能在地图边界与建筑物之间正常移动、贴墙滑动、不穿模；
- 相机跟随、死区、平滑、边界钳制均按 C6 规格工作；
- 走到门前按 E 能进出室内，退出位置与朝向正确；
- 每个交互点在范围内提示、按 E 能映射到任务 B/D 的服务调用；
- 校门告示牌触发 `inspect` 覆盖层。

## 2. 前置条件

- Python 3.12 + Panda3D 1.10.16（见仓库 `.venv`）。
- 工作目录为仓库根 `naiwa_campus/`。
- 每栋建筑都必须存在室内定义（`interiors`）与唯一的门交互点。

## 3. 运行方式

自动化等价版本（推荐，退出码 0 即通过）：

```bash
python -m tests.standalone_c --route C-R1 --fake-services
```

该命令用 `InteractionService` + 假服务驱动完整路线，把每一步的实际结果写入
`reports/standalone/C/route_C-R1.json`，并对活动调用序列、门切换序列、覆盖层推送、
事件总数逐条断言。

人工烟测版本：启动带图形的引擎，按下方步骤用 `WASD`/方向键移动、`E` 交互、`Shift` 快走，
逐步核对「操作 → 预期」。

## 4. 路线总览

出生点 `(40.0, 5.0)` 朝向 `n`（校门广场）开始，依次：

| # | 目标 | 类型 | 位置（世界/本地） | 预期服务调用 |
|---|------|------|------------------|--------------|
| 1 | 宿舍楼门 `ia_door_dorm` | door | 世界 (18.8, 17.0) r=1.2 | 切换场景 `InteriorScene(loc_dorm)` |
| 2 | 床 `ia_bed` | activity | 本地 (3.0, 7.0) r=1.2 | `rest_dorm` |
| 3 | 宿舍入口地垫（退出） | — | 本地 (8.0, 0.6) r=0.8 | 退出到世界 (19.8, 17.0) 朝向 `e` |
| 4 | 跑道起点 `ia_track_start` | activity | 世界 (28.0, 17.0) r=2.0 | `exercise` |
| 5 | 广场长椅 `ia_plaza_bench` | activity | 世界 (40.0, 33.0) r=1.5 | `campus_walk` |
| 6 | 教学楼门 `ia_door_classroom` | door | 世界 (20.8, 40.0) r=1.2 | `InteriorScene(loc_classroom)` |
| 7 | 课桌 `ia_class_desk` | activity | 本地 (8.0, 6.0) r=1.2 | `attend_class` |
| 8 | 教学楼入口地垫（退出） | — | 本地 (8.0, 0.6) r=0.8 | 退出到世界 (21.8, 40.0) 朝向 `e` |
| 9 | 图书馆门 `ia_door_library` | door | 世界 (59.2, 40.0) r=1.2 | `InteriorScene(loc_library)` |
| 10 | 阅览桌 `ia_reading_desk` | activity | 本地 (6.0, 5.0) r=1.2 | `library_study` |
| 11 | 图书馆入口地垫（退出） | — | 本地 (8.0, 0.6) r=0.8 | 退出到世界 (58.2, 40.0) 朝向 `w` |
| 12 | 社团楼门 `ia_door_clubroom` | door | 世界 (61.2, 17.0) r=1.2 | `InteriorScene(loc_clubroom)` |
| 13 | 游戏电脑 `ia_game_pc` | activity | 本地 (3.0, 7.0) r=1.2 | `play_games` |
| 14 | 社团楼入口地垫（退出） | — | 本地 (8.0, 0.6) r=0.8 | 退出到世界 (60.2, 17.0) 朝向 `w` |
| 15 | 食堂门 `ia_door_canteen` | door | 世界 (40.0, 47.2) r=1.2 | `InteriorScene(loc_canteen)` |
| 16 | 打饭窗口 `ia_food_window` | activity | 本地 (8.0, 8.5) r=1.5 | `eat_canteen` |
| 17 | 食堂入口地垫（退出） | — | 本地 (8.0, 0.6) r=0.8 | 退出到世界 (40.0, 46.2) 朝向 `s` |
| 18 | 校门告示牌 `ia_gate_notice` | inspect | 世界 (43.0, 4.0) r=1.5 | 推送覆盖层 `EventScene(text_id=insp.gate_notice.body)` |

终点约在世界 `(43.0, 4.0)`，回到室外场景 `campus`。

## 5. 详细步骤与预期

1. **出生点**：世界 `(40.0, 5.0)`，朝向 `n`，场景 `campus`，当前地点 `loc_gate`。
   相机 target 由初始位置驱动，`camera.hpr` 固定 `(0, -40, 0)`。
2. **走到宿舍楼门**（世界 18.8, 17.0）：进入半径 1.2 后提示显示「宿舍楼门」，按 E 切到
   室内场景，玩家出现在 `loc_dorm` 的出生点本地 `(8.0, 1.6)` 朝向 `n`。
3. **走到床**（本地 3.0, 7.0）：提示「床」，按 E 调用 `rest_dorm`（体力类活动，由任务 B 处理数值），
   触发一次 `activity.done` 事件。
4. **踩入口地垫退出**（本地 8.0, 0.6，半径 0.8）：走入地垫即触发退出，回到室外
   `(19.8, 17.0)`，朝向 `e`（背离建筑）。退出有 1 秒冷却，期间再踩地垫不重复触发。
5. **操场跑道起点**（世界 28.0, 17.0，半径 2.0）：按 E 调用 `exercise`。
6. **广场长椅**（世界 40.0, 33.0，半径 1.5）：按 E 调用 `campus_walk`。
   长椅本身是障碍物 `prop_plaza_bench`（39.0, 33.6 ~ 41.0, 34.2），需贴墙滑到交互半径内。
7. **教学楼门**（世界 20.8, 40.0）→ 进入 `loc_classroom`；出生本地 `(8.0, 1.6)`。
8. **课桌**（本地 8.0, 6.0）：按 E 调用 `attend_class`。
9. **退出教学楼** → 世界 `(21.8, 40.0)` 朝向 `e`。
10. **图书馆门**（世界 59.2, 40.0，朝向 `w`）→ 进入 `loc_library`。
11. **阅览桌**（本地 6.0, 5.0）：按 E 调用 `library_study`。
12. **退出图书馆** → 世界 `(58.2, 40.0)` 朝向 `w`。
13. **社团楼门**（世界 61.2, 17.0，朝向 `w`）→ 进入 `loc_clubroom`。
14. **游戏电脑**（本地 3.0, 7.0）：按 E 调用 `play_games`。
15. **退出社团楼** → 世界 `(60.2, 17.0)` 朝向 `w`。
16. **食堂门**（世界 40.0, 47.2，朝向 `s`）→ 进入 `loc_canteen`。
17. **打饭窗口**（本地 8.0, 8.5，半径 1.5）：按 E 调用 `eat_canteen`。
18. **退出食堂** → 世界 `(40.0, 46.2)` 朝向 `s`。
19. **绕行到校门告示牌**（世界 43.0, 4.0）：从食堂向南绕过广场，按 E 触发 `inspect`，
    推送覆盖层 `EventScene(text_id=insp.gate_notice.body)`，不调用任务 B 的活动服务。

全程提示遵守半径滞回：离开交互点超过「半径 + 0.3」米后提示消失；多个交互点同时在范围内时
取最近，距离相同时按 `npc > activity > door > save > inspect` 选择。

## 6. 自动化断言（`--route C-R1`）

命令通过时 `reports/standalone/C/route_C-R1.json` 的 `ok` 应为 `true`，且满足：

- 活动调用序列：
  `["rest_dorm", "exercise", "campus_walk", "attend_class", "library_study", "play_games", "eat_canteen"]`
- 门切换序列：`["loc_dorm", "loc_classroom", "loc_library", "loc_clubroom", "loc_canteen"]`
- 覆盖层推送：`[("EventScene", {"event_id": null, "text_id": "insp.gate_notice.body"})]`
- 全程无 NPC 交谈（`type=npc` 交互点未被触发）；
- `activity.done` 事件数 = 7；
- `problems` 为空。

## 7. 维护说明

- **每次修改碰撞体（`content/world/map.json` 的 `buildings` / `props` / `furniture` 或
  `game/world/collision.py`）后，必须重跑本路线并更新本文件，注明受影响的交互点。**
  室内坐标依赖 `interiors` 的房间原点与家具位置，室外坐标依赖建筑 `rect` 与门触发点；
  任一改动都可能让某一步「走不到」或「提前触发」。
- 若路线在某一栋卡住，优先检查：门的 `outside_trigger` 是否仍在其门半径内、
  室内入口地垫是否被新增家具遮挡、退出点是否落在建筑外 1 米处。
- 修改后重新生成报告：

  ```bash
  python -m tests.standalone_c --route C-R1 --fake-services
  ```

  确认 `ok: true` 后再提交；本文件第 4 节的坐标表需同步为最新值。
