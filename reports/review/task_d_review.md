# 任务 D 交付验收报告

验收对象：`naiwa_campus_任务D/naiwa_campus/`（37 个文件，2606 行 Python）
验收人：开发者 A（公共接口维护者）
验收环境：`.venv-naiwa`（Python 3.12.14 + Panda3D 1.10.16 + pytest 8.4.2）
基准文档：`文档/任务A_技术负责人项目整合与全部素材_v3.docx` 第一部分（全员共用规格）
+ `docs/CHANGELOG_API.md`（接口冻结记录）

---

## 1. 结论

**结构与文案交付基本齐全，但代码不可合并、不可运行。**

| 维度 | 结论 |
| --- | --- |
| 文件清单（D 的 16 个 ui 模块） | ✅ 16/16 全部存在，无越界文件 |
| 正式文案（strings.json / dialogues.json） | ✅ 281 条 + 52 页，计数与规范完全一致，行长/选项字数零违规 |
| 文本索引（docs/ui/text_index.csv） | ✅ 333 行，与两份 JSON **双向零差异** |
| 测试（tests/ui） | ❌ 交付即红：收集阶段 `NameError` 全挂；修掉 1 行后 42 通过 / 4 失败 |
| 与 A 的公共接口对接 | ❌ 9 个界面里 8 个 `TypeError`、1 个类名不存在 |
| 独立截图命令 | ❌ 两处崩溃，一张图也出不来 |
| 界面实际可读性 | ❌ 无字体接入（中文全空）、多行文本永远空白、关闭后残留 |

一句话：**文案和骨架是合格甚至优秀的，接线和渲染是没跑通过的状态。** 交付物里的
`docs/ui/screens.md` 第 14 行写着「生成文件清单（首次截图后请更新本节）」——这张表
至今是空的，因为截图命令从来没跑通过。

---

## 2. 交付物核对

| 规范要求（《手册 3.0》§3 仓库目录与归属） | 交付情况 |
| --- | --- |
| `game/ui/` 16 个模块 | ✅ theme / text_db / widgets / hud / prompt / result_panel / dialogue_box / event_scene / day_summary / tab_panel / main_menu / pause_menu / settings_menu / save_menu / graduation_scene / tutorial |
| `content/text/zh_CN/` | ✅ strings.json（281 条，20.5 KB）、dialogues.json（52 页，11.2 KB） |
| `tests/ui/` | ✅ 6 个测试文件 + conftest + 4 份夹具 + standalone_screens.py |
| `tests/standalone_d.py` | ✅ 独立入口（--text-check / --screen / --event） |
| `docs/ui/` | ✅ screens.md、text_index.csv |
| 不越界改动 | ⚠️ 附带 `game/__init__.py` 占位（见 P2-3） |

**交付形式缺口**（规范「提交与交接要求」要求每人一份交付说明 + 独立运行证据）：

- ❌ 没有 `docs/handover_d.md`（A 侧有 `docs/handover_a.md`，含 A-01…A-06 / A-ST-01…05 验收矩阵）。
  D-ST-01…05 只散落在 `test_theme.py` / `test_text_db.py` / `test_menu_cursor.py` 的
  docstring 里，没有一张「用例 → 通过条件 → 证据」的表。
- ❌ 没有 `reports/standalone/D/`。A 侧有 `standalone_report.json`、`autoplay.json`、
  7 张证据 PNG；D 侧一张也没有（因为截图命令跑不通，见 P0-8）。
- ❌ 交付目录不是 git 仓库，无提交记录，无法按周次标签追溯（`week-1` 已在 A 侧打）。

内容覆盖（`python -m tests.standalone_d --text-check`，退出码 0）：

```json
{"strings_total": 281, "dialogues_total": 52, "activities": 9,
 "semester_events": 8, "relationship_events": 9, "daily_events": 12, "endings": 6}
```

与规范 §A8 的 9 活动 / 8 学期事件 / 9 关系事件 / 12 日常事件 / 6 结局完全对上。

---

## 3. 通过项（可以直接保留）

1. **文本层零缺陷**：`TextDB.validate()` 对正式文案返回 `[]`；ID 全部符合
   `^[a-z][a-z0-9_.]*$`；占位符集合与调用方一致（`{year_name}` / `{sem_name}` /
   `{day}` / `{label}` / `{deltas}` / `{max}` / `{days}` / `{amount}` / `{n}`）。
2. **文本索引可用**：333 行 `text_id,chars,screen`，对 281 + 52 条做双向核对，
   `csv→content` 缺失 0、`content→csv` 未登记 0。这是本次交付里质量最高的一份产物，
   建议 E 的 `validate_content` 直接以它为基线。
3. **矩形规格与规范逐条吻合**：`theme.RECTS` 的 14 个矩形（HUD `4,4,156,36`、
   prompt `130,218,220,30`、result `100,40,280,190`、dialogue `4,166,472,100`、
   choices `276,92,200,68`、day_summary `120,60,240,150`、tab `40,24,400,222`、
   main_menu `180,150,120,90`）与 §A4、D2 一致，无越界。
4. **UI 走 aspect2d + `ui_px()`**：符合 §A4 第 5 条「UI 使用同一套 480×270 逻辑坐标，
   按同一缩放系数绘制在 aspect2d 之上」；1280×720 推出 2.667、1920×1080 推出 4.0，
   与 A 的 `LowResPipeline` 缩放一致。
5. **纯逻辑与渲染分层干净**：`theme.MenuCursor`（锁定项跳过、数字直选、锁因返回）
   与 `TutorialController`（5 步状态机、单步显示、读档不重复）都可以脱离 Panda3D 跑，
   42 个通过的测试基本覆盖这两块。
6. **错误码映射完整**：`prompt.ERROR_TEXT_IDS` 七条与 §7 表一一对应。

---

## 4. 阻断级缺陷（P0，必须修完才能合入）

### P0-1 `tutorial.py` 导入即 `NameError`，整套测试连收集都过不去

```
tests/ui/test_tutorial.py:5: in <module>
game/ui/tutorial.py:113: in <module>
    class TutorialOverlay(UIWidget):
E   NameError: name 'UIWidget' is not defined
```

`widgets.py` 的 import 被写在 `__init__` 内部（L119），类定义处却继承了 `UIWidget`。
影响：`pytest tests/ui` 直接 `Interrupted: 1 error during collection`；
**合入后 A 仓库原本 75 个绿的测试会整体转红**（实测）。

修法：`tutorial.py` 不要继承 `UIWidget`，改成组合（`self.panel` / `self.label` 自己代理
`show/hide`），或在文件末尾做条件继承。渲染层不能进纯逻辑模块。

### P0-2 9 个界面里 8 个与 A 的场景工厂不兼容

A 的 `game/app.py:214` 契约是 `cls(app, **kwargs)` + `on_enter/on_exit/on_update/is_overlay`
（`game/core/scene_manager.py:27`），D 的签名是 `(parent, transform, text_db, asset_registry=None)`。
把 D 覆盖进 A 的仓库后逐个调用 `make_scene`：

```
MainMenu         -> OK  game.app.StubMainMenu          ← 类名 MainMenuScene 不存在，静默退回替身
EventScene       -> TypeError: missing 2 required positional arguments: 'transform' and 'text_db'
ResultPanel      -> TypeError: ...
DaySummary       -> TypeError: ...
TabPanel         -> TypeError: ...
PauseMenu        -> TypeError: ...
SettingsMenu     -> TypeError: missing 3 ... and 'settings'
SaveMenu         -> TypeError: ...
GraduationScene  -> TypeError: ...
```

`make_scene` 只捕获 `ImportError/AttributeError`，`TypeError` 会直接冒到主循环 → **合并即崩**。
修法：补一个 `game/ui/scene_adapter.py`，把 D 的 widget 包成 `UISceneBase`：

```python
class UISceneAdapter:
    is_overlay = True
    def __init__(self, app, **kw): ...        # 内部建 UITransform/TextDB/registry
    def on_enter(self, **kw): ...             # 调 D 的 show()/load_event()/update_state()
    def on_exit(self): self.widget.destroy()
    def on_update(self, dt): ...              # 转发 tick()
```

顺带把 `MainMenu` 改名或加别名 `MainMenuScene`，否则主菜单永远走 A 的 ASCII 替身。

### P0-3 `MultilineLabel` 无法追加行 → 所有多行正文永远空白

`widgets.py:143` 的 `set_lines()` 只遍历 `__init__` 时建好的 `self.labels`，而全部调用点
都用 `[... ] = []` 初始化：

- `dialogue_box.py:36`（对话正文）
- `result_panel.py:35`（结果文本）
- `graduation_scene.py:24/26/27`（回顾、结局正文、制作名单）

结果：`labels` 恒为空，`set_lines()` 是空转。实测 `dialogue.png` 只有面板和头像，
**一个字都没有**。这是"叙事游戏看不见叙事"的级别。
修法：`set_lines()` 内部按需 `UILabel` 补建并 `hide()` 多余行，或构造时预建
`MAX_LINES_PER_PAGE=4` 行。

### P0-4 9 个活动 ID 有 4 个与冻结清单不符（含 `create_work` 完全缺失）

规范 §A8 与 `assets/manifest.json` 双向确认的活动 ID：

```
attend_class  library_study  play_games  create_work  join_club
exercise      eat_canteen    rest_dorm   campus_walk
```

D 写的是：

| D 的 ID | 应为 | 后果 |
| --- | --- | --- |
| `act.studio_practice.*` | `act.create_work.*` | 第 9 个活动（敲代码）**没有任何文案** |
| `act.dorm_rest.*` | `act.rest_dorm.*` | 4 条文本 ID 永不命中 |
| `act.campus_stroll.*` | `act.campus_walk.*` | 4 条文本 ID 永不命中 |
| `act.gym_train.*` | `act.exercise.*` | 4 条文本 ID 永不命中 |

共 16 个文本 ID 失效，UI 上会显示 `#act.create_work.name`。
`test_fixtures.py:63` 只断言"9 个"，**没断言是哪 9 个**，所以测试全绿也漏了。

顺带语义也没跟上 `CHANGELOG_API.md` §8 的变更：

```
act.studio_practice.name = '画室练习'      → 应为「敲代码」
act.studio_practice.result.2 = '画了四张速写，手感回来了。'
ending.ending_creator.title = '独立创作者'  → 应为「独立开发者」
ending.ending_creator.body.1 = '速写本画满了七本，画室的灯总是最后一个熄灭。'
evt.sem_3_art_contest.lock.submit_work = '需要先完成一次画室练习'
```

A 那边的插图 `cg_naiwan_create_work` 已经是"双屏代码窗口"，文本还停在画室 → 图文打架。

### P0-5 存读档界面与 A 的 `SaveManager` 完全不兼容

| D 的假设 | A 的实现（`game/core/save_manager.py`） |
| --- | --- |
| `list_slots()` 返回 `dict`，用 `.items()` 遍历（save_menu.py:69） | 返回 `list[SaveSummary]` → **`AttributeError`，被 `except Exception` 吞掉，永远显示"空"** |
| 槽位名 `"0"/"1"/"2"/"autosave"`（save_menu.py:82） | `config.SLOT_IDS = slot_1/slot_2/slot_3/autosave`，`_validate_slot` 会对 `"0"` 抛异常 |
| `save(None, slot)`（save_menu.py:84） | `save(state, slot)` 第一参数是 GameState，传 None 必崩 |
| `meta.get("day_index")`（save_menu.py:60） | `SaveSummary.summary["day_index"]`，外层没有 `day_index` |

另外 `save_menu.py:59` 的自动存档行取 `str(i - 1)`（i=3 → `"2"`），拿的是第 3 个手动档，
自动存档的日期永远不显示。

### P0-6 设置菜单写的键 A 根本不读（音量滑块 0 效果）

| D 写 | A 读（`config.Settings`） |
| --- | --- |
| `volume_master` / `volume_music` / `volume_sfx` | `master_volume` / `bgm_volume` / `sfx_volume` |
| 三档：`instant` / `normal`=20 / `slow`=10 | 四档：`slow`=20 / `normal`=40 / `fast`=80 / `instant`=0 |

后果：三个音量滑块调了半天 `settings.json` 不变；选"正常"实际跑 20 字/秒（规范是 40），
选"慢速"是 10（规范 20），**整体慢一倍**；`fast` 档在 UI 上不存在，`settings.json` 里
万一有 `fast`，菜单会显示成"正常"。

### P0-7 毕业界面构造即崩

```
game/ui/graduation_scene.py:37: in __init__
game/ui/widgets.py:65: in hide
E   AttributeError: 'NoneType' object has no attribute 'hide'
```

`graduation_scene.py:26` 传 `[]` 建 `MultilineLabel` → `root=None`（widgets.py:141）→
第 36 行循环 `hide()` 直接炸。**毕业界面一次都没跑起来**（`--screen all` 也是死在这一步）。

### P0-8 独立截图命令两处崩溃，一张图都出不来

```bash
python -m tests.standalone_d --screen all --out reports/standalone/D/screens/
```

1. `standalone_d.py:109`（`--event` 分支在 L130 同样）`base.win.set_size(1280, 720)`：
   `AssertionError: Cannot resize buffer unless it is created with BF_resizeable flag`
   —— 离屏 buffer 不可 resize，必须用 `loadPrcFileData("", "win-size 1280 720")` 在
   `ShowBase()` 之前设。
2. 修掉 1 之后再撞 `widgets.py:41` `base.win.get_properties()`：
   `AttributeError: 'panda3d.core.GraphicsBuffer' object has no attribute 'get_properties'`
   —— 离屏时 `win` 是 `GraphicsBuffer`，只能用 `getXSize()/getYSize()`
   （这个坑 A 侧已经踩过并写在 `docs/handover_a.md`）。

### P0-9 9 个对话头像 ID 有 8 个在 manifest 里不存在

`dialogues.json` 用的表情名是 D 自己编的，规范 §A8 冻结的是
`portrait_<npc>_<neutral|happy|sad|surprised>`：

```
用到且存在：portrait_npc_chenlang_happy                       （1/9）
用到但缺失：portrait_npc_sumo_normal / _smile、
            portrait_npc_chenlang_serious / _touched、
            portrait_npc_xiaoyou_shy / _worried / _smile / _excited   （8/9）
```

后果：8 处对话头像走 `asset.missing` → 品红黑格。修法是把表情归一到 4 档
（`normal→neutral`、`smile/happy→happy`、`worried→sad`、`excited/shy→surprised`）。

### P0-10 `hide()` / `destroy()` 收不干净，界面会互相叠影

`UIWidget.destroy()`（widgets.py:72）只删 `self.root`（那张面板卡），而所有
`UILabel` / `StatBar` / 卡片都挂在**公共 parent** 上（如 `dialogue_box.py:32-40`、
`result_panel.py:35-40`）。全屏只有 `HUD` 把子节点挂到自建 `hud` 节点下，所以只有它收得干净。

实测 `--screen all` 连续渲染时，`main_menu.png` 是**七层界面叠在一起**：Tab 面板的属性条、
结果面板的 `学业 +5 / 精力 -20`、日结算的三行行动、对话框的 `[Space] 继续` 全在屏上。
合入后表现就是"关掉菜单，菜单文字留在场景里"。

---

## 5. 重要缺陷（P1）

| 编号 | 位置 | 问题 | 证据 |
| --- | --- | --- | --- |
| P1-1 | 全部 `UILabel` | **没有字体接入**。`UILabel` 不调 `set_font`，引擎默认字体无中文 → `:text(warning): No definition ... for character U+7b2c`，中文全空/方框 | `hud.png` 全是对勾框 |
| P1-2 | `result_panel.py:57` | 插图逻辑反了：`if self.assets is not None: node.hide()` —— 有 AssetRegistry 就把占位藏掉，且**从没加载 `cg_naiwan_<activity>`**。9 张活动插图永远不显示 | `result.png` 空白插图区 |
| P1-3 | `hud.py:50,52` | 精力/心情数字写在 x=436，画布只有 480，实测被右边界裁成 `84/8` | `hud.png` 右上 |
| P1-4 | `hud.py:94` | `tick()` 靠 `self._last_value` 提前 return，而全项目没有任何地方给它赋值 → 「精力<20 闪烁」是死代码。HUD 也没用 `RECTS["hud_date"/"hud_gauges"]` 画底板，文字直接压在 3D 场景上 | 代码 |
| P1-5 | `tab_panel.py:32` | 用 `theme.DELTA_ORDER`（含 `energy`/`mood`）遍历 `state.stats`，`stats` 里没有这两个键 → 面板永远多两行"精力 0 / 心情 0"空条，而 mood 反而没地方显示 | `tab.png` 前两行 |
| P1-6 | `tab_panel.py:69` | `met = set(state.relationships)` 恒含 3 个键 → `known` 恒 True，「未知 NPC 显示 ？？？」永不触发 | 代码 |
| P1-7 | 测试 | 交付即 4 红：`test_main_menu_items_exist`（夹具缺 `ui.menu.*`）、`test_pause_menu_returns_without_exit_during_event`（夹具缺 `err.*`）、`test_energy_step_triggered_below_40`（夹具缺 `tut.energy.body`）、`test_bad_placeholder_not_silent`（`get()` 不带 kwargs 时不进 format 分支，永不记 error 日志） | `pytest -q` 输出 |
| P1-8 | UI 皮肤接入度 | manifest 里 28 个 `ui_*` 资源，D 只用 1 个（`ui_panel_9slice`）。`ui_icon_*` 15 个、`ui_key_*` 8 个、`ui_slot_full/empty`、`ui_bar_frame/fill`、`ui_cursor` 全部未接 | 静态扫描 |
| P1-9 | `dialogue_box.py:32-36` | 名字条/正文用裸数字 `110,172` / `110,190`，与 `RECTS` 的 `108,170` / `108,188` 差 2px；且基线锚点导致名字条画到面板上沿**外面** | `dialogue.png` |
| P1-10 | 全部面板标题 | **统一基线偏移**：`UILabel` 以文字**基线**为锚点，`set_pos(..., ay)` 后 12px 字实际占 `y-12 .. y`。所有标题写 `rect.y + 8`，等于把文字顶推到 `rect.y - 4`，每块标题都压在面板上边框外 | `day_summary.png` 的「第 1 天结束」、`tab.png` 的「状态面板」 |

---

## 6. 次要 / 风险（P2）

1. `event_scene.py:100` `self.text_db.get("err.unknown_id", id=...)` 传了 `{id}`，
   但 `err.unknown_id` 正文没这个占位符，参数被忽略；建议改成显式拼接。
2. `pause_menu.py` / `main_menu.py` 的 `confirm()` 只返回键名，不派发；且 `cancel()`
   没有 `on_enter` 生命周期，接 A 的 `SceneManager` 时需要适配层统一。
3. `game/__init__.py` 是 6 行占位说明。**整目录拷贝会把 A 的 `__version__` 删掉**，
   合并时必须排除这个文件。
4. `graduation_scene.py:73` 用 `theme.format_delta()` 显示总评，会强制带符号
   （"学业 +42"），且遍历 `DELTA_ORDER` 把 `energy/mood` 也列出来显示 `+0`。
5. `EndingResult.highlights` 的语义两边没对齐：D 当 **text_id** 用
   （`graduation_scene.py:83` 再 `text_db.get()`），而 `results.py:115` 只是 `list[str]`，
   A 的替身返回 `highlights=[]`。B 若填中文句子，毕业界面会显示 `#...`。
6. `tests/ui/__init__.py` 与 `tests/__init__.py` 同时存在，`tests/ui/conftest.py` 的
   `project_root` 与 A 根 `conftest.py` 同名 fixture 有覆盖关系，将来加"文本变更即失败"
   的校验时容易踩。

---

## 7. 契约不一致一览（合并前必须逐条定案）

| 契约点 | A（权威） | D（现状） | 定案 |
| --- | --- | --- | --- |
| 场景类入口 | `cls(app, **kw)` + `on_enter/on_exit/on_update/is_overlay` | `(parent, transform, text_db, registry)` + `show/hide/tick` | 加适配层，D 侧不动 |
| 主菜单类名 | `game.ui.main_menu.MainMenuScene` | `MainMenu` | 加别名 |
| 活动 ID | `rest_dorm` / `campus_walk` / `exercise` / `create_work` | `dorm_rest` / `campus_stroll` / `gym_train` / `studio_practice` | 按 A 改 D |
| 文本速度 | `slow20 / normal40 / fast80 / instant` | `slow10 / normal20 / instant` | 按 A 改 D |
| 音量键名 | `master_volume` / `bgm_volume` / `sfx_volume` | `volume_master/music/sfx` | 按 A 改 D |
| 存档槽位 | `slot_1..3` + `autosave`，`list_slots()->list[SaveSummary]` | `"0".."2"` + `dict.items()` | 按 A 改 D |
| NPC 表情 | `neutral/happy/sad/surprised` | `normal/smile/shy/worried/excited/touched/serious` | 按 A 改 D |
| 多行文本 | —（无此契约） | `MultilineLabel` 需支持追加 | 修实现 |

---

## 8. 建议的修复顺序

1. **P0-1**（1 行）→ 先让 `pytest tests/ui` 能收集。
2. **P0-3 / P0-7**（~30 行）→ `MultilineLabel` 支持追加，毕业界面才能构造。
3. **P0-4 / P0-9 / P1-1**（文案 + 字体钩子）→ 一次改完 `strings.json` 的 16 个 ID、
   9 个头像 ID，`UILabel` 加 `set_font`。
4. **P0-2**（新文件 `scene_adapter.py`，~120 行）→ 8 个界面接进 `SceneManager`。
5. **P0-5 / P0-6**（~40 行）→ 存档与设置按 A 的键名/槽位/档位重写。
6. **P0-8**（2 行）→ 截图命令用 `loadPrcFileData` + `getXSize`。
7. **P0-10 / P1-2 / P1-3 / P1-5 / P1-10**（widgets 重构 + 局部）→ 视觉验收。
   `widgets.py` 的 `UILabel` 建议一次改到位：构造函数里接收 `parent_root`，
   把节点挂到所属 widget 的 `root` 下（解决 P0-10），并把 `set_pos` 的 y 加上
   一个行高做顶部对齐（解决 P1-10）。
8. **P1-7** → 补夹具并让 4 个红测试转绿。

估：D 侧约 1.5 人日；适配层可由 A 出（属 A 的场景装配职责）。

---

## 9. 复现方式

```bash
# 1) 纯逻辑：文本校验（当前 exit 0）
python -m tests.standalone_d --text-check

# 2) D 的单元测试（当前：先 NameError，修掉后 42 通过 4 失败）
python -m pytest tests/ui -q -m "not gui"

# 3) 截图（当前两处崩溃；本文档附图是打了 3 处最小补丁后渲的）
python -m tests.standalone_d --screen all --out reports/standalone/D/screens/

# 4) 合入 A 后的场景工厂探测（8 个 TypeError）
python - <<'PY'
import sys; sys.path.insert(0, ".")
from game import config
from game.app import NaiwaApp, apply_prc
opts = config.parse_args(["--dev","--offscreen","--frames","1"])
apply_prc(opts, config.Settings())
app = NaiwaApp(opts)
for sid in ("MainMenu","EventScene","ResultPanel","DaySummary","TabPanel",
            "PauseMenu","SettingsMenu","SaveMenu","GraduationScene"):
    try: print(sid, "OK", type(app.make_scene(sid, {})).__name__)
    except Exception as e: print(sid, type(e).__name__, e)
app.stop_audio(); app.destroy()
PY
```

### 附图说明（`reports/review/D/screens/`）

这 7 张图是在 D 的代码上打了 **3 处最小补丁**后渲出来的，用于看布局，不代表交付态：

1. `tutorial.py` 的 `TutorialOverlay` 去掉 `UIWidget` 继承；
2. `widgets.py` 的 `from_base` 改用 `get_x_size()/get_y_size()`；
3. `standalone_d.py` 改用 `loadPrcFileData("win-size 1280 720")`。

未修的缺陷（多行空白、无字体、叠影、插图缺失、HUD 溢出）在图上都能直接看到。

| 文件 | 能看出的问题 |
| --- | --- |
| `screens/hud.png` | 中文全空、精力数字被右边裁掉、无面板底板 |
| `screens/result.png` | 插图区空白、结果文本空白 |
| `screens/dialogue.png` | 正文空白、名字条溢出面板上沿、上一个界面的 `[Space] 继续` 残留 |
| `screens/event_choices.png` | 正文空白、残留文字、选项面板因停在第一页未显示 |
| `screens/day_summary.png` | 用 UILabel，三行行动 / 精力恢复 / 预告都在（未受 MultilineLabel 影响）；但标题上溢到面板外、底部压着上一个界面的 `[Space] 继续` |
| `screens/tab.png` | 前两行「精力/心情」恒为 0 的空条、多层界面叠影 |
| `screens/main_menu.png` | 七层界面叠在一起（残留问题最直观的一张） |
