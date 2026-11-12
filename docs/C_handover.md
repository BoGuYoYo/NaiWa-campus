# 任务 C 交付说明与交接文档

| 项目 | 内容 |
|---|---|
| 面向对象 | 项目组长（兼 E 整合负责人） |
| 项目 | 奶娃：大学四年（工程名 `naiwa_campus`） |
| 依据 | 《任务分工手册 3.0》任务 C《校园场景移动相机碰撞与交互 v3》 |
| 交付形态 | 可合并、可验收、可运行 |
| 岗位职责 | 地图数据、移动、碰撞、相机、触发器、门与室内切换、交互点到服务的映射 |

## 1. 结论

任务 C 的开发项 C1~C9 与「独立运行测试契约」全部完成：

- 交付物清单（手册表 22）5 项全部具备；
- 手册规定的 4 条独立命令全部退出码 0；
- `game/world/` 内不存在任何属性字段（academic / stamina / social / interest / mood / energy）的读写，可接受 E 的 grep 检查；
- 已满足「完成定义」中属于本岗位的部分：代码与数据齐备、验证完成、交付说明齐全、另一名开发者可按本文件复现结果。

**待 E 完成的整合动作**见第 6、7 节。

## 2. 交付物清单（对应手册表 22）

| 状态 | 检查项 | 实际位置 |
|---|---|---|
| [x] | `game/world/` 全部文件 | `game/world/`（10 个模块） |
| [x] | `content/world/map.json`、`interactables.json` | `content/world/`（5 建筑 · 6 区域 · 25 props · 5 室内；18 交互点 + 5 门） |
| [x] | `tests/world/`（≥ 15 个测试） | `tests/world/`（11 个测试文件，共 **182** 项，其中 `-m 'not gui'` 为 **171** 项） |
| [x] | `docs/world/route_C-R1.md` 人工烟测路线 | `docs/world/route_C-R1.md` |
| [x] | 地图总览图 `docs/world/map.png`（F1+F2 截图） | `docs/world/map.png`（960×720 离屏渲染，含碰撞线框与交互点圆） |
| [x] | 独立命令报告 | `reports/standalone/C/`（route_C-R1.json、collision.json、camera_check.json） |

## 3. 目录与文件说明

```
game/world/
├─ map_data.py            C1~C4 地图/区域/建筑/室内/交互点数据加载与校验（唯一坐标入口）
├─ collision.py           C2 纯 Python 轴分离扫掠碰撞（move_and_collide / clamp_to_bounds）
├─ trigger_zone.py        C4 提示滞回与最近交互点选择（PRIORITY / HIDE_MARGIN）
├─ interaction_service.py C7 交互点 -> B/场景服务的映射（query / interact）
├─ input_map.py           C5 输入映射、8 方向朝向、速度积分、脚步计时（纯逻辑）
├─ player_controller.py   C5 PlayerMotion（纯数学）+ PlayerController（Panda3D 节点/动画/音效）
├─ camera_controller.py   C6 CameraRig（纯数学）+ CameraController（正交镜头套用）
├─ interior_scene.py      C3 室内白模与入口地垫（自动退出 + 1 秒冷却）
├─ campus_scene.py        C1~C3 室外白模与几何辅助函数
└─ debug_draw.py          C9 F1~F6 调试绘制
```

- `content/world/` 是唯一的坐标来源，代码中不硬编码任何坐标。
- `game/world/` 不依赖 Panda3D 的部分（`collision` / `trigger_zone` / `input_map` / `map_data` 及各模块的数学部分）可无界面测试。
- 导入 `panda3d` 的文件仅有：`campus_scene.py`、`interior_scene.py`、`camera_controller.py`（`_setup_ortho_lens` 内延迟导入）、`debug_draw.py`、`player_controller.py`（默认按键读取内延迟导入）。

## 4. 对外接口

### 4.1 C 提供（手册表 6）

| 接口（所在文件） | 签名 | 调用方 |
|---|---|---|
| `InteractionService`（`interaction_service.py`） | `query(state, interactable_id) -> PromptView` | D |
|  | `interact(state, interactable_id) -> InteractionResult` | A、D |

- 交互目标映射（与 C4 一致）：

  | 交互点 type | 调用 |
  |---|---|
  | `activity` | `ActivityService.start(state, target)`，并 `EventBus.emit("activity.done", result=r)` |
  | `npc` | `RelationshipService.talk(state, target)`，同上 |
  | `door` | `SceneManager.change("InteriorScene", building_id=target)` |
  | `save` | `SceneManager.push("SaveMenu", mode="save")` |
  | `inspect` | `SceneManager.push("EventScene", event_id=None, text_id="insp.<id>.body")` |

- `interact` 内置 0.3 秒重复按键锁；`enabled=False` 时返回 `kind="blocked"`，**不调用 B**，由 D 播放取消音效并抖动提示框。
- 提示文本 ID 规则：activity → `act.<target>.name`；npc → `npc.<target>.talk`；door → `ui.prompt.enter`；save → `ui.prompt.save`；inspect → `insp.<id>.name`。`PromptView.cost_preview` 为 B 的 `preview` 名义变化。

### 4.2 C 依赖（需 A / B / D 提供，签名见手册表 6）

| 依赖 | 提供方 | 说明 |
|---|---|---|
| `game.core.results`：`PromptView` / `InteractionResult` | A | C 的返回类型；**当前以同签名替身顶替，A 交付后自动切换，无需改 C 代码** |
| `ActivityService.can_start / preview / start` | B | 活动可否开始、名义消耗、实际执行 |
| `RelationshipService.talk` | B | NPC 交谈 |
| `SceneManager.change / push / pop` | A | 门切换、覆盖层 |
| `EventBus.emit` | A | `activity.done` 事件 |
| `TextDB.get` | D | 提示文案 |
| `AssetRegistry` | A | C 目前不加载正式素材；正式模型/动画/音效到位后由 A 通过注册表提供 |

`game/world/` **不导入** `game.ui`；对 A 的依赖集中在 `SceneManager` / `EventBus` / `game.core.results`。

## 5. 集成前置条件与步骤

1. 代码与数据合入 `feature/c-*` 分支，提交信息格式 `<岗位>(<模块>): <动词开头>`。
2. A 交付 `game/core/results.py`（真实 `PromptView` / `InteractionResult`）与 `SceneManager` / `EventBus` 后，删除替身依赖（`tests/world/fixtures/core_stub.py` 会自动让位，无需改代码）。
3. B 交付 `ActivityService` / `RelationshipService` 后，把 `InteractionService` 的构造参数指向真实服务。
4. 由 A 的 `GameFlow` 在 `CampusScene` 中按「移动 → 靠近交互点(C) → 按 E → ActivityService.start(B) → ResultPanel(D)」串联；C 只暴露第 4.1 节接口。
5. 合入 `develop` 后由 E 执行（本岗位无法独立完成，依赖 A/B/D/E 交付）：
   ```
   python -m pytest -m "not gui"
   python -m tools.validate_content
   python -m tools.validate_assets
   python -m tools.run_smoke_test --all --seed 42
   ```

## 6. 验证结果（本岗位独立命令，全部退出码 0）

| 命令 | 结果 |
|---|---|
| `python -m pytest tests/world -m 'not gui' -q` | 171 passed, 11 deselected |
| `python -m pytest tests/world -q` | 182 passed（含 11 个离屏 GUI 烟测） |
| `python -m tests.standalone_c --route C-R1 --fake-services` | 通过；活动序列 7 项、门切换 5 项、覆盖层推送 1 次、无 NPC 交谈、`activity.done` 事件 7 次 |
| `python -m tests.standalone_c --collision-fuzz 3000 --out reports/standalone/C/collision.json` | 3000 步，阻挡 55、失败 0 |
| `python -m tests.standalone_c --camera-check --map content/world/map.json` | 15/15 ok |

命令输出保存在 `reports/standalone/C/`（route_C-R1.json / collision.json / camera_check.json / verification.txt）。这些报告不写入用户存档、正式 `assets/` 或正式 `content/`。

## 7. 已知卡点、边界与限制（交接给 E，对应手册表 23 第 5 条）

### 相机限制
- 固定 40° 俯角正交镜头，水平朝向永远朝北，**禁止旋转与缩放**；正交 film = (20.0, 11.25) 米，= 24 像素/米。
- 室外 target 钳制在 x ∈ [10, 70]、y ∈ [8.75, 51.25]，已用四角视野测试保证**画面不显示地图外区域**（C-07）。
- 室内房间（16×10 米）小于视野，target 固定在房间中心、不跟随玩家。
- `camera.pos` 的 x、y 四舍五入到 1/24 米，保证像素对齐；任何缩放/自由旋转需求须先改规格。

### 坐标与存档边界
- 室内房间位于独立坐标区（原点 200 / 220 / 240 / 260 / 280，见 `map.json`），碰撞矩形与渲染整体平移到世界坐标；**玩家位置一律以世界坐标记录**（`location_id` 为建筑 id 时同样保存世界坐标 x/y），存档/读档须遵循此约定（C-06）。
- 玩家碰撞体 0.7×0.7 米（半宽 0.35），以脚点为中心；出口位置 = 门外触发点再向外 1 米、朝向背离建筑。

### 待补内容
- `props` 已按 A 交付的正面图登记 25 个：长椅、校门告示牌、13 棵树（0.6×0.6）、5 盏路灯（0.4×0.4）、5 个垃圾桶（0.5×0.5）；布置规则见 `map.json` 头部的 `notes`，`prop_gate_notice` / `prop_plaza_bench` 同时是交互点载体。
- 室内 `npc_marks` 当前仅 `loc_library`（苏墨、管理员）、`loc_clubroom`（陈朗）、`loc_canteen`（奈珑、阿姨）；`loc_classroom` 的 2 名环境 NPC 位置待正式模型阶段确定。
- 正式角色动画（`char_naiwan_walk` / `char_naiwan_idle`）、音效（`sfx_footstep_ground` / `sfx_footstep_floor`）由 A 提供；C 已按 8 fps / 3 fps、0.35 s / 0.25 s 的规格调用，素材缺失时仅空调用不报错。

### 替身依赖
- `game/core/results.py` 未交付时，`tests/world/fixtures/core_stub.py` 会安装同签名替身（`PromptView` / `InteractionResult`），使 `tests/world` 与独立命令无需 A 即可运行；A 交付后自动改用真实实现。

## 8. 维护约定

1. **每次修改碰撞（`map.json` 的 `buildings` / `props` / `furniture` 或 `collision.py`）后，必须重跑 `--route C-R1` 并更新 `docs/world/route_C-R1.md`，注明受影响的交互点。**
2. A 交付正式模型后，C 在 2 个工作日内复核碰撞并更新 `map.json`。
3. 调试键（仅 `--dev`）：F1 碰撞线框、F2 交互点与半径、F3 坐标/朝向/地点/FPS、F5 传送到下一个交互点、F6 当前时段设为 3。

## 9. 复现步骤

```bash
# 1) 安装依赖（Python 3.12 + Panda3D 1.10.16，见手册表 4）
# 2) 无界面单元测试
python -m pytest tests/world -m 'not gui' -q
# 3) 全体测试（含离屏 GUI 烟测）
python -m pytest tests/world -q
# 4) 路线 C-R1 端到端（写入 reports/standalone/C/route_C-R1.json）
python -m tests.standalone_c --route C-R1 --fake-services
# 5) 碰撞模糊测试
python -m tests.standalone_c --collision-fuzz 3000 --out reports/standalone/C/collision.json
# 6) 相机规格检查
python -m tests.standalone_c --camera-check --map content/world/map.json
```

预期：以上命令均退出码 0；JSON 报告中 `ok` 为 `true`、`problems` 为空。

---

## 10. 整合期修正（2026-11-09，A 记录）

合入 `develop` 时按共用规格改了 5 处，全部已落地在本目录的代码里：

1. **`GeomLinestrips` → `GeomLines`**（`campus_scene.py` 的 `make_circle_lines` / `make_rect_lines`）。
   Panda3D 1.10.16 下 `GeomLinestrips` 既不渲染（实测屏幕像素数 0），又会让
   `flattenStrong()` 踩内存断言：`loc_library` / `loc_canteen` 构造即崩。
   改完后入口地垫红圈、NPC 站位圈、F1 碰撞线框、F2 交互点圆全部可见。
2. **区域分层 `AREA_Z`**：三条道路彼此相交、又与广场/操场重叠，原先统一 `z=0.02`
   导致整屏 z-fighting（规律条纹）。改为道路 0.010/0.012/0.014、区域 0.020/0.022/0.024。
3. **`interaction_service.py` 去掉 `state.energy` 读取**：交谈能否进行改由
   `RelationshipService.can_talk()` 判定，`cost_preview` 取 `RelationshipService.preview()`，
   C 只透传错误码——这样才符合「`game/world/` 不读写属性字段」的独立通过条件。
4. **NPC 提示文案 ID 去掉重复前缀**：`npc.npc_sumo.talk` → `npc.sumo.talk`，
   与 `content/text/zh_CN/strings.json` 对齐（旧写法提示框会显示 `#...`）。
5. **GUI 烟测参数化到 5 栋室内**：原先只造 `loc_dorm`，所以第 1 条的崩溃在交付时没被发现。

整合后的验收（本机复现）：

```text
pytest tests/world -m "not gui"   → 171 passed
pytest tests/world                → 187 passed（含 5 栋室内参数化 + 11 项 GUI 烟测）
standalone_c --route C-R1         → exit 0（7 活动 / 5 门 / 1 覆盖层）
standalone_c --collision-fuzz 3000→ 阻挡 55 步、失败 0
standalone_c --camera-check       → 15/15 ok
```

