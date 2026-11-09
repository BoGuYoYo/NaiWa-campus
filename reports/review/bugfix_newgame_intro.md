# BUG 修复报告：新游戏开场（对话框按不动 / 人物消失 / Esc 失效）

日期：2026-11-09
范围：`game/core/flow.py`、`game/core/scene_manager.py`、`game/core/world_scene.py`、
`game/core/input_router.py`（新增）、`game/ui/event_scene.py`、`game/world/player_controller.py`、
`game/app.py`、`content/text/zh_CN/strings.json`

---

## 1. 用户报的三个现象

1. 主界面点「新游戏」→ 进入游戏，开场对话框弹出来，但**按什么都没反应**；
2. **人物消失**（校园里有建筑、有道具，就是看不到奶娃）；
3. **Esc 无效**（既退不出对话框，也打不开暂停菜单）。

三个现象是**同一条装配链路上三个独立缺陷**叠加出来的，不是一个 bug。

---

## 2. 根因

### 2.1 覆盖层抢在基础场景淡出途中 push（对话框按不动 + Esc 失效）

旧版 `GameFlow.new_game()`：

```python
self.scenes.change("CampusScene", spawn="loc_gate", state=state)   # 只是登记，0.25 秒后才真正切
state.phase = "event"
self.scenes.push("EventScene", ...)                                # 立刻 push 覆盖层
```

`change()` 是**异步**的：它把 `_pending` 记下来，等 0.25 秒黑场淡出结束才退旧场景、
建新场景。而 `push("EventScene")` 是同步的，于是执行顺序变成：

1. `EventScene` 在主菜单**之上**被 push，绑定 `space / enter / w / s / 1 / 2 / 3 / escape`；
2. 0.25 秒后淡出结束 → `MainMenu.on_exit()` → `app.ignore("enter") / ignore("space") /
   ignore("arrow_up") / ignore("w") / ignore("s")`。

Panda3D 的 `ignore(event)` 是**全局**接口，它不区分是谁绑的：主菜单退场时把对话框刚绑的
确认键一起拆掉了。于是：

- `Space / Enter / W / S` 全部失效 → 对话框推不动；
- `EventScene` 的 `escape` 也一起被删掉，之后 `CampusScene.on_enter` 才补绑
  `escape → _on_escape`，而它开头有 `if self.app.scenes.overlays: return`，所以
  **Esc 在事件里完全没有反应**；
- 玩家因此永远卡在开场事件里（`input_locked` 恒为 True）。

同一个缺陷还有两个"兄弟"：主菜单 → 设置/读档 → 返回，以及暂停菜单 → 设置/存档 → 返回，
子面板退场时的 `ignore()` 会把下层菜单的上下键与确认键一起清掉，菜单变死界面。

### 2.2 角色卡片建好没摆位（人物消失）

`WorldSceneBase.on_enter()` 里 `PlayerController(..., card)` 传了 `set_scene(..., reset=False)`，
而卡片节点只在 `PlayerController.update()`（非锁定帧）里才 `setPos`。开场事件覆盖层一直开着，
`on_update` 第一行 `if locked: ... return` 直接返回，**卡片永远停在节点原点 (0,0,0)**，
而相机在出生点 (40, 5)，所以镜头里"人没了"。

顺带：`SpriteAnimator.play()` 只换了贴图、没落 UV，锁定期间没人调 `tick()`，
卡片会显示**整张 8×8 精灵表**（不是静止帧），即使进了视野也是错的。

### 2.3 选项面板文字被平移两次（附带发现）

`EventScene._build_choice_labels()` 把选项 `UILabel` 挂在 `self.panel.root` 上，却又喂了
**绝对**逻辑坐标；`UIPanel.root` 本身已经平移到面板左上角，于是文字被平移两次，
跑到面板外面去 —— 面板看起来是空的（只有边框）。旧版没人能走到选项阶段，所以一直没暴露。

---

## 3. 修复

| # | 文件 | 改动 |
| --- | --- | --- |
| 1 | `game/core/input_router.py`（新增，~110 行） | `InputRouter`：给每条 `accept` 记住归属，`unbind(owner)` 只收回自己那份，并把该事件上剩下的**最上层**绑定重新 `accept` 回去。后绑定覆盖先绑定的语义不变 |
| 2 | `game/app.py` | 装配 `self.input = InputRouter(self.accept, self.ignore)`；A 的替身场景（Stub*）全部改走 `self.bind()` / `input.unbind(self)` |
| 3 | `game/core/world_scene.py` | 所有场景/覆盖层的 `bind_input()` 改走 `self.bind()`，`unbind_input()` 统一 `app.input.unbind(self)`；新增 `player.apply_pose()` 调用 |
| 4 | `game/core/scene_manager.py` | `start() / change()` 支持 `on_ready` 回调：新场景建立且**淡入结束**后回调一次（异常被吞掉并记日志；`fade_seconds<=0` 时同步回调） |
| 5 | `game/core/flow.py` | `new_game()` 把「push 开场事件」放进 `change(..., on_ready=...)`，且回调里校验 `self.state is state`（被读档/二次新游戏抢走时不重复弹） |
| 6 | `game/world/player_controller.py` | 新增 `apply_pose()`：把运动状态立刻落到节点 + 播待机帧；`world_scene.on_enter()` 建完场景就调用 |
| 7 | `game/core/world_scene.py`（`SpriteAnimator.play`） | `play()` 里立刻 `_apply()` 当前帧 UV，锁定期间也是对的帧 |
| 8 | `game/ui/event_scene.py` | 新增 `on_escape()`：结果页 → 结束；打字中 → 整页；还有下一页 → 翻页；选项阶段 → 提示「先选一个选项吧」（新文本 `ui.event.escape_hint`）。选项标签改挂 `self.root` |
| 9 | `game/core/world_scene.py` | 事件/结果面板/日结算三个"按 Space 继续"的面板补 `mouse1`；结果面板与日结算补 `escape`（等同确认关闭） |

打开顺序因此变成：**淡出 → 退主菜单 → 建校园场景 → 淡入 → 再 push 开场事件**，
覆盖层的绑定永远在旧场景退场之后，`InputRouter` 再做一层保险（其它路径也不会互相踩）。

---

## 4. 验证

| 验证项 | 结果 |
| --- | --- |
| `pytest tests` | **546 passed / 5 skipped**，exit 0 |
| `pytest tests/core/test_input_router.py` | 10 项（绑定覆盖、退场还原、旧场景不抢新绑定、限定事件注销） |
| `pytest tests/core/test_scene_manager.py` | 新增 4 项（on_ready 时机 / 只跑一次 / 无淡出同步 / 异常隔离） |
| `pytest tests/core/test_flow.py` | 新增 1 项（开场事件必须等校园场景就绪） |
| `pytest tests/world/test_player_motion.py` | 新增 1 项（`apply_pose` 在首次 update 前就把卡片摆在出生点） |
| 离屏真机复现脚本（主菜单 → 新游戏 → 推完开场 → 走动） | 淡入后 `base=CampusScene`、`overlays=[EventScene]`、卡片 `(40.0, 5.0, 0.0)`、`space/enter/e/w/s/1/2/3/escape/mouse1` 全部在册；Esc 提示 `先选一个选项吧`；事件结束后 Esc 正常打开暂停菜单 |
| 离屏真机复现脚本（菜单层级） | 主菜单→设置→返回、校园→暂停→存档→返回→Esc 再开暂停：`escape` 归属每次回到正确层 |
| 离屏真机复现脚本（移动） | 开场结束后按 W：`y 5.0 → 6.77`；按 D：`x → 41.33`、朝向 `e`、`heading 270`，`GameState.world` 同步 |
| `python -m game --offscreen --autoplay --frames 100000` | exit 0，16 天到结局，`autoplay.json` `ok: true` |
| `dist/NaiwaCampus/NaiwaCampus.exe --offscreen --autoplay --frames 100000` | exit 0（打包版已用修好的代码重建） |

### 截图（离屏，480×270 游戏层 + 1280×720 窗口层，存于 `reports/review/bugfix_newgame/`）

- `10_dialog_window.png`：开场对话框第一页，打字机进行中，`[Space] 继续` 提示；
- `11_choices_window.png`：第 5 页 + 选项面板，**选项「继续」在面板内**（修复前是空面板）；
- `12_escape_hint_window.png`：Esc 后整页显示 + 提示「先选一个选项吧」；
- `12_campus_playable.png`：开场结束，**奶娃站在出生点（黄三角是 C 的出生点标记）**；
- `20_moved.png`：按 D 之后角色朝右、镜头跟随（相机死区内有轻微滞后是设计行为）；
- `13_pause_window.png`：Esc 打开暂停菜单（继续游戏 / 设置 / 存档 / 读档 / 回主菜单）。

---

## 5. 遗留（不在本次范围）

`TutorialController` 只创建了逻辑层，`TutorialOverlay` 从未被 `WorldSceneBase` 装配，
`player_moved` 事件也没有人发 → 新手教程横幅永远不显示、`tut.move` 不会自动完成。
这是"功能未接"，不是本次的按键/摆位缺陷，需要 D 的横幅接进 `ui_root` 后单独处理。
