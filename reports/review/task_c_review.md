# 任务 C 交付验收报告

验收对象：`任务C_交付包/`（36 个文件，3437 行 Python，10 个 `game/world` 模块）
验收人：开发者 A（公共接口维护者 / 场景装配方）
验收环境：`.venv-naiwa`（Python 3.12.14 + Panda3D 1.10.16）
基准文档：《任务分工手册 3.0》第一部分共用规格 + C 的交付说明 `docs/C_handover.md`

---

## 1. 结论

**质量最高的一份交付：数据、代码、文档、证据四件齐全，4 条独立命令在本机全部逐条复现。**
但**不能直接合并**——A 的场景工厂按类名自动接管 `game.world.campus_scene.CampusScene`，
而 C 交的是几何构建器，合并后游戏 **启动即崩**。另有 2 个渲染层硬缺陷（2 栋室内构造崩溃、
全部线框图元不可见）。

| 维度 | 结论 |
| --- | --- |
| `game/world/` 10 个模块 | ✅ 与规范 §3 清单逐字一致，无越界文件 |
| `content/world/map.json` + `interactables.json` | ✅ 5 建筑 / 6 区域 / 2 物件 / 5 室内 / 18 交互点 + 5 门，坐标全部来自数据 |
| `tests/world/`（要求 ≥15 项） | ✅ 182 项（171 not-gui + 11 gui），本机复现全绿 |
| 独立命令 4 条 | ✅ 全部 exit 0，报告文件与文档数字**逐位吻合** |
| `docs/C_handover.md` + `route_C-R1.md` + `map.png` | ✅ 齐全（top-level 说明与 handover 是同一份） |
| 与 A 的场景接口 | ❌ `make_scene` → `TypeError`，合并后 `exit 1` |
| 室内场景 | ❌ `loc_library` / `loc_canteen` 构造时 Panda 断言崩溃 |
| 调试绘制 / 地垫 / 交互点圈 | ❌ `GeomLinestrips` 在 1.10.16 下**一个像素都不画** |
| 与 D 的文案 ID | ❌ 23 个交互点里 18 个的提示文案在 D 的 strings.json 中不存在 |

一句话：**C 把自己的活干到了可验收水准，坏在"接缝"上**——A 的装配层和 D 的文案层都没对齐，
外加 Panda3D 1.10.16 的一个图元坑把 C 的线框/地垫吃掉了。

---

## 2. 交付物核对

| 手册表 22 检查项 | 交付情况 |
| --- | --- |
| `game/world/` 全部文件 | ✅ map_data / collision / trigger_zone / interaction_service / input_map / player_controller / camera_controller / interior_scene / campus_scene / debug_draw |
| `content/world/*.json` | ✅ map.json 5.2 KB、interactables.json 5.0 KB |
| `tests/world/` ≥15 项 | ✅ 11 个测试文件 182 项 |
| `docs/world/route_C-R1.md` | ✅ 122 行，17 步人工路线，每步给坐标与服务调用 |
| `docs/world/map.png` | ✅ 960×720 俯视总览（5 楼 + 6 区域 + 出生点 + 2 物件 + 门标记） |
| `reports/standalone/C/*` | ✅ route_C-R1.json / collision.json / camera_check.json / verification.txt |

内容规模（`MapData.from_content_root`）：`buildings=5 areas=6 props=2 interiors=5 interactables=23`。

---

## 3. 通过项（本机逐条复现）

```text
python -m pytest tests/world -m "not gui" -q   → exit 0，171 项（72+72+27 点）
python -m pytest tests/world -q                → exit 0，182 项（72+72+38 点）
python -m tests.standalone_c --route C-R1 --fake-services
                                               → exit 0，7 活动 / 5 门 / 1 覆盖层 / 0 NPC 交谈
python -m tests.standalone_c --collision-fuzz 3000
                                               → exit 0，阻挡 55 步，失败 0
python -m tests.standalone_c --camera-check --map content/world/map.json
                                               → exit 0，15/15 ok
```

与 `reports/standalone/C/verification.txt` 里的数字**逐位一致**（171 / 182 / 55 / 15）。
交付包里的这 4 份报告不是"截个图放进去"，而是可重跑的。

值得单独肯定的几点：

1. **坐标唯一来源做实了**：`map.json` + `interactables.json` 是唯一坐标表，10 个模块里没有一处硬编码坐标；
   `map_data.py` 还有 `_validate_relations()` 做跨表校验（门必须落在建筑边上、室内必须有点等）。
2. **纯逻辑与渲染分离彻底**：`collision` / `trigger_zone` / `input_map` / `map_data` 四条都不 import panda3d，
   171 项无界面测试全靠它们，跑完只要 0.34 s。
3. **相机规格有数值证明**：`film=(20.0, 11.25)` = 24 px/m、`hpr=(0,-40,0)`、
   死区/钳制/1-24 对齐/四角视野不越界共 15 条断言，比"目测没问题"强得多。
4. **入口地垫有冷却**（`EXIT_COOLDOWN=1.0`）和"退出位置 = 门外再外 1 米"的明确规则，避免出门口立刻被弹回。
5. **碰撞是自写轴分离扫掠**，3000 步模糊测试 0 失败，不依赖物理引擎——符合"逻辑 100% Python"的约束。

---

## 4. 阻断级缺陷（P0）

### P0-1 合并后游戏启动即崩：场景入口契约不一致

A 的 `game/app.py:44` 用类名自动接管：

```python
SCENE_MODULES = {..., "CampusScene": ("game.world.campus_scene", "CampusScene"), ...}
# make_scene():  scene = cls(self, **kwargs)      调用约定 = (app, **kwargs)
```

C 交的是几何构建器：

```python
CampusScene.__init__(self, map_data, parent: NodePath, *, dev=False)
InteriorScene.__init__(self, map_data, building_id, parent, *, dev=False)
```

本机实测（把 C 覆盖进 A 的仓库后启动）：

```text
python -m game --dev --scene CampusScene --skip-intro --offscreen --frames 3
→ File "game/app.py", line 221, in make_scene
  TypeError: CampusScene.__init__() got an unexpected keyword argument 'spawn'
  exit=1
```

`SceneProtocol` 要求的 `on_enter / on_exit / on_update / is_overlay` C 一个都没有
（`dir()` 里只有 `destroy` 和 `scene_id`）。合并前 A 是"记录未合入 → 用替身"，
合并后变成"找到类 → 构造失败 → 崩"，属于**回归**。

修法（A 侧职责，`game/core/world_scene.py` 新建，不动 C 的文件）：

```python
class CampusSceneAdapter:
    is_overlay = False
    def __init__(self, app, **kw): self.app = app
    def on_enter(self, spawn=None, state=None, **kw):
        md = MapData.from_content_root(resource_root() / "content")   # 建议缓存
        self.scene = CampusScene(md, self.app.render, dev=self.app.options.dev)
        self.player = PlayerController(md, state, self.app.render.attachNewNode("player"),
                                       camera=..., animator=..., audio=...)
        self.cam = CameraController(self.app.cam, CameraRig())
        self.debug = DebugDraw(md, self.app.render, camera=self.cam, player=self.player,
                               state=state, goto=...) if self.app.options.dev else None
        if self.debug: self.debug.bind(self.app)
    def on_update(self, dt):
        self.player.update(dt, locked=self.app.scenes.input_locked)
        ... PromptTracker.update(...) -> InteractionPrompt
    def on_exit(self):
        self.debug and self.debug.unbind(self.app); self.scene.destroy(); self.player... 
```

`InteriorScene` 同理（`flow` 不直接切室内，是 C 的 `InteractionService.interact` 发
`change("InteriorScene", building_id=...)`，适配层要接住这个 kwarg）。

### P0-2 `loc_library` / `loc_canteen` 构造即崩（Panda3D 断言）

```text
InteriorScene(md, "loc_library", render, dev=True)
→ AssertionError: pi < (int)cdata->_ends.size()
  at geomPrimitive.cxx:1995  ← interior_scene.py:71 self.root.flattenStrong()
```

逐栋复现（每栋独立进程）：

| 建筑 | 结果 |
| --- | --- |
| loc_dorm | OK |
| loc_classroom | OK |
| **loc_library** | **AssertionError（3 条断言）** |
| loc_clubroom | OK |
| **loc_canteen** | **AssertionError（3 条断言）** |

最小复现（与 C 的代码无关，纯 `flattenStrong` 的问题）：

| 场景 | 结果 |
| --- | --- |
| 地面 + 1 个 `make_circle_lines` + `flattenStrong()` | OK |
| 地面 + 长方体 + **2 个** `make_circle_lines` + `flattenStrong()` | **崩** |
| 同上但改用 `flattenMedium()` | OK |
| 同上但不 flatten | OK |

即：**Panda3D 1.10.16 的 `flattenStrong()` 合并同一子树内的多个 `GeomLinestrips` 时会踩内存断言**
（与线段数无关，32/16 都崩）。触发点并不稳定——2 个线环的最小场景会崩，
而社团活动楼同样是「地垫 + 1 个 NPC 圈」却没崩——所以不能按"几何个数"去判断是否会炸：
图书馆与食堂各有 3 个线环，稳定复现崩溃。

影响：**图书馆、食堂进不去**——一按门就抛异常。

修法（推荐改图元，见 P0-3）：把 `make_circle_lines` 换成"三角带圆环"或 `GeomLines` 逐段，
再保留 `flattenStrong()`；或至少把 `flattenStrong()` 换成 `flattenMedium()`。

### P0-3 所有 `GeomLinestrips` 图元在 1.10.16 下**不渲染**

同一个 8×8 米正交视野里画四种图元，数像素：

| 图元 | 屏幕上非背景像素 |
| --- | --- |
| `make_circle_lines`（C：`GeomLinestrips` + `addConsecutiveVertices`） | **0** |
| 手写 `GeomLines` 逐段 | 352 |
| 三角带圆环（`GeomTriangles`） | 2172 |
| `make_rect_lines`（C：`GeomLinestrips`，F1 碰撞线框） | **0** |

证据图：`reports/review/C/screens/prim_probe.png`（能看到两个环，前两种 C 的图元完全没画出来）。

影响面：
- **入口地垫的红圈看不见**（室内截图里地垫完全不存在）——玩家不知道走到哪里会自动退出；
- **NPC 站位圈看不见**；
- **C9 的 F1 碰撞线框、F2 交互点圆全部看不见**，调试功能等于没有；
- `docs/world/map.png` 的说明写着"含碰撞线框与交互点圆"，实际图上也没有——文档描述与产物不符。

修法：`make_circle_lines` / `make_rect_lines` 改用 `GeomLines`（每段两个顶点）或四边面片；
若必须闭合环路，`GeomLinestrips` 要显式 `closePrimitive()` 且**不要**再进 `flattenStrong()`。

---

## 5. 重要缺陷（P1）

### P1-1 与 D 的文案 ID 对不上：23 个交互点里 18 个会显示 `#text_id`

用 D 的正式 `strings.json` 校验 C 产出的 `PromptView.label_text_id`：

```text
命中  5/23：act.attend_class / act.library_study / act.play_games / act.join_club / act.eat_canteen
落空 18/23 + 5 个 inspect 正文
```

| 类别 | C 产出的 text_id | D 的键 | 责任 |
| --- | --- | --- | --- |
| 活动 ×4 | `act.rest_dorm.name` / `act.exercise.name` / `act.campus_walk.name` / `act.create_work.name` | D 写成了 `act.dorm_rest` / `gym_train` / `campus_stroll` / `studio_practice` | **D**（C 用的才是规范 ID） |
| NPC ×3 | `npc.npc_sumo.talk`、`npc.npc_chenlang.talk`、`npc.npc_xiaoyou.talk` | D 有 `npc.sumo.talk` | **C**（`interaction_service.py:78` 用 `ia.target` 直接拼，`target` 已带 `npc_` 前缀） |
| 门 ×5 | `ui.prompt.enter` | D 无此键 | **C 或 D**，需定案 |
| 存档 ×1 | `ui.prompt.save` | D 无此键 | 同上 |
| 查看点 ×5 | `insp.gate_notice` / `course_board` / `bookshelf` / `librarian` / `canteen_aunt` | D 写的是 `insp.gate_board` / `lake_bank` / `billboard` / `statue` / `oak_tree` | **两边各写一套，全不重合** |

C 侧一行就能修的：`label = f"npc.{ia.target.removeprefix('npc_')}.talk"`。

### P1-2 道路与区域共面 z-fighting

`campus_scene.py` 把所有区域统一画在 `Z_AREA = 0.02`，而 `road_main`(37–43 × 0–48)、
`road_east_west`(18–62 × 15–19)、`road_north`(20–60 × 38–42) 与广场(30–50 × 26–42)、
操场(22–34 × 10–24)、校门(34–46 × 0–8) **矩形互相重叠**。
实测广场视角整屏出现规律条纹闪烁（`reports/review/C/screens/01_outdoor_plaza.png`）。

修法：按层给不同 z（草地 0 / 道路 0.02 / 区域 0.04），或给道路单独一层并裁剪。

### P1-3 `interaction_service` 读 `state.energy`，与交付说明的"零属性读写"自相矛盾

```python
# interaction_service.py:75
elif state.energy < NPC_TALK_ENERGY_COST:   # 常量 5，硬编码
```

而 `docs/C_handover.md` §1 写「`game/world/` 内不存在任何属性字段（… mood / energy）的**读写**」。
E 的 grep 会命中；C 自己的 `test_no_attribute_writes.py` 只查写入，所以测试是绿的、文档是错的。
另外"交谈要 5 点精力"是 B 的规则，C 硬编码一份，B 的 `RelationshipService.talk` 可能返回不同的
`E_LOW_ENERGY`，就会出现"提示可交谈 → 按 E 被拒"或反之。

修法：提示只读 B 的 `can_start`（若 B 提供 `RelationshipService.can_talk`），或把该值移入内容表。

### P1-4 GUI 烟测只覆盖 1 栋室内，P0-2 因此漏检

`tests/world/test_gui_scene.py` 里 5 处 `InteriorScene(map_data, "loc_dorm", ...)`，
没有任何一栋其他建筑的用例。建议改成 `@pytest.mark.parametrize("bid", map_data.interiors)`，
一组参数化就能把 library/canteen 的崩溃挡住。

---

## 6. 次要 / 风险（P2）

1. `docs/C_handover.md` 与顶层 `C_交付与交接说明.md` 内容完全相同（同 hash），建议只留一份并互相引用。
2. `props` 只有长椅 + 告示牌 2 个，树与路灯缺（C 已声明待 A 的模型）→ 与 A 的 `model_props`（12 种道具）不一致，需在整合周补齐碰撞。
3. `route C-R1` 只走了 9 个活动里的 7 个（`create_work`、`join_club` 有点位未走），建议加成 9/9。
4. `debug_draw.bind()` 无条件 `accept("f1"/"f2"/...)`，只靠调用方保证"仅 dev 构造"；
   若 `--dev` 关掉后仍构造，会占用游戏键位。
5. 室内 `npc_marks` 的"本地坐标"与 `interactables.json` 的 NPC 坐标不一致
   （图书馆苏墨：mark (11,7) / 交互点 (11,6)；社团楼陈朗：mark (12,6) / 交互点 (12,5)），
   正式模型阶段需要对齐，否则会出现"人站在这里，圆点在那里"。
6. `verification.txt` 里记录的绝对路径是另一台机器（`C:\Users\baba\Documents\Trae\...`），
   本机重跑可复现，但报告里的路径不可直接点击。

---

## 7. 三岗契约对照（合并前必须定案）

| 契约点 | A（权威实现） | C（现状） | 定案 |
| --- | --- | --- | --- |
| 场景类构造 | `cls(app, **kw)` | `(map_data, parent, *, dev)` | A 写适配层 |
| 场景生命周期 | `on_enter/on_exit/on_update` + `is_overlay` | 无 | A 写适配层 |
| `change("CampusScene")` 参数 | `spawn=loc_id, state=GameState` | — | 适配层接 `spawn`/`state` |
| `change("InteriorScene")` 参数 | —（A 未实现） | `building_id` | 适配层接 `building_id` |
| `InteractionService.query/interact` | ✅ 已在 `SCENE_MODULES` 之外，签名吻合 | ✅ | 直接可用 |
| 提示文案 ID | — | `npc.npc_xxx.talk` 等 18 处在 D 中缺失 | 见 P1-1 |
| 活动 ID | ✅ 与 C 完全一致 | ✅ `rest_dorm/exercise/campus_walk/create_work` | D 需改 |
| 存档槽/设置键 | A 的 `slot_1..3` / `master_volume` | C 不涉及 | D 需改 |
| 玩家位置所有权 | `GameState.world` | `PlayerController` 每帧回写 | ✅ 一致 |

---

## 8. 修复顺序

1. **P0-3 + P0-2**（C 侧，约 40 行）：`make_circle_lines` / `make_rect_lines` 换成 `GeomLines`/四边面片，
   顺带解决 flatten 崩溃；`test_gui_scene` 参数化 5 栋室内（P1-4）。
2. **P0-1**（A 侧，约 150 行新文件 `game/core/world_scene.py`）：`CampusScene` / `InteriorScene` 适配器。
   同时把 `make_scene` 的 `except` 从 `(ImportError, AttributeError)` 扩到 `Exception` 并降级到替身，
   避免以后再出现"合并即崩"。
3. **P1-1**（C 一行 + D 一批文案）：NPC 文案 ID 去前缀；`ui.prompt.enter/save` 与 `insp.*` 三方定案。
4. **P1-2**（C 十行）：区域分层 z。
5. **P1-3**（C/B 协商）：去掉 `state.energy` 读取，改由 B 判定。
6. **P2**：树/路灯 props、route 补 9/9、npc_marks 对齐。

估：C 侧 0.5 人日，A 侧适配层 1 人日，D 侧文案 0.5 人日。

---

## 9. 复现方式

```bash
# 合并演练（C 覆盖到 A 的仓库后）
python -m pytest tests/world -m "not gui" -q                 # 171 passed
python -m pytest tests/world -q                              # 182 passed
python -m tests.standalone_c --route C-R1 --fake-services     # exit 0
python -m tests.standalone_c --collision-fuzz 3000            # 阻挡 55 / 失败 0
python -m tests.standalone_c --camera-check --map content/world/map.json   # 15/15

# 崩溃复现
python -m game --dev --scene CampusScene --skip-intro --offscreen --frames 3
#   → TypeError: CampusScene.__init__() got an unexpected keyword argument 'spawn'

# 逐栋室内
python - <<'PY'
import sys; sys.path.insert(0, ".")
from panda3d.core import loadPrcFileData
loadPrcFileData("", "window-type offscreen")
from direct.showbase.ShowBase import ShowBase
from pathlib import Path
from game.world.map_data import MapData
from game.world.interior_scene import InteriorScene
base = ShowBase(); md = MapData.from_content_root(Path("content"))
for bid in ("loc_dorm","loc_classroom","loc_library","loc_clubroom","loc_canteen"):
    try: InteriorScene(md, bid, base.render); print(bid, "OK")
    except Exception as e: print(bid, type(e).__name__, str(e).splitlines()[0][:60])
PY
#   → loc_library / loc_canteen 抛 AssertionError
```

### 附图（`reports/review/C/screens/`）

用 C 的 `CampusScene` / `CameraController` 在 **480×270 离屏 + 4 倍最近邻放大**下渲染，
`loc_library` / `loc_canteen` 那两张是**先把 `flattenStrong()` 临时换成 `flattenMedium()`** 才渲出来的，
用来证明"修掉 flatten 后室内是能出画面的"。

| 文件 | 能看出的问题 |
| --- | --- |
| `00_outdoor_gate.png` | 出生点三角、主干道、告示牌；地垫/交互点圈不可见（室外本就没有） |
| `01_outdoor_plaza.png` | **整屏规律条纹 = 道路与广场 z-fighting** |
| `02_outdoor_playground.png` | 操场与东西横道重叠处同样有条纹 |
| `01_interior_loc_dorm.png` | 房间/家具正常，但**入口地垫红圈完全没有** |
| `02_interior_loc_classroom.png` | 同上 |
| `03_interior_loc_library.png` | 原代码此处崩溃；修掉 flatten 后可渲染，NPC 圈仍不可见 |
| `04_interior_loc_clubroom.png` | 同上 |
| `05_interior_loc_canteen.png` | 原代码此处崩溃 |
| `prim_probe.png` | 四种图元同屏对比：只有 `GeomLines` 与三角环被画出来，C 的 `GeomLinestrips` 两个都是空白 |
