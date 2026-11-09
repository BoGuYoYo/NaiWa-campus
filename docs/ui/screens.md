# UI 界面说明（开发者 D 交付文档）

对应《任务分工手册 3.0》D1～D3 节。所有坐标均为 480×270 逻辑像素，原点左上。

## 屏幕截图

截图由独立命令生成（需要 panda3d 环境）：

```bash
python -m tests.standalone_d --screen all --out reports/standalone/D/screens/
python -m tests.standalone_d --event event_fixture_01 --offscreen
```

生成文件清单（2026-11-09 重新生成，8 张全部有内容，中文正常显示）：

| 文件 | 界面 | 说明 |
|---|---|---|
| reports/standalone/D/screens/hud.png | HUD | 日期框 + 时段圆点 + 精力/心情条（含 ui_icon_* 图标） |
| reports/standalone/D/screens/result.png | 结果面板 | 活动插图（cg_naiwan_*）+ 数值逐条显示后的状态 |
| reports/standalone/D/screens/dialogue.png | 对话框 | 打字机完成后状态（头像来自 manifest 的 4 档表情） |
| reports/standalone/D/screens/event_choices.png | 事件选项 | 3 选项 1 锁定项夹具 |
| reports/standalone/D/screens/day_summary.png | 日结算 | 学期事件预告状态 |
| reports/standalone/D/screens/tab.png | Tab 状态面板 | 5 属性条 + 关系 + 精力上限 |
| reports/standalone/D/screens/main_menu.png | 主菜单 | 继续项置灰并显示原因 |
| reports/standalone/D/screens/graduation.png | 毕业界面 | 第 1 页总评属性 |
| reports/standalone/D/screens/event_fixture_01_page.png | 事件分页 | `--event event_fixture_01` 生成 |

字体：`assets/fonts/FusionPixel12.ttf` 尚未交付，截图与游戏都走
`AssetRegistry.load_ui_font()` 的系统中文黑体回退（`[FONT]` 日志里写明来源）。
打包前必须补上正式字体，否则换机器会退回方框。

集成后的三处行为变化（原先与本文件描述不符，已按规范改实现）：

1. `hide()/destroy()` 现在能收干净——每个界面自建容器节点，子控件都挂在容器下，
   关闭界面不会把文字留在屏幕上；
2. 文本以「左上角」定位，标题不再上溢到面板边框外；
3. 面板不透明度取 1.0（`theme.PANEL_TINT`），3D 场景不会透到正文底下。

## 界面清单与状态说明

### HUD（常驻，校园场景）
- 矩形：日期框 `4,4,156,36`；精力/心情 `320,4,156,36`；按键提示 `4,252,200,16`。
- 第 1 行日期：`ui.hud.date_fmt`（大一 · 上学期 · 第 1 天）。
- 时段圆点 3 枚：已用为实心（`action_slot`）。
- 精力条按当前上限（`80 + 体力 ÷ 5`）计算；`精力 < 20` 时警告色闪烁（`HUD.tick`）。
- 按键提示仅 `day_index < 3` 显示，之后隐藏。

### 交互提示 prompt（靠近交互点时）
- 矩形：居中 `y=218`，宽 ≤220，高 30。
- 第 1 行 `[E] {label}`；第 2 行 preview 变化（顺序：精力、心情、学业、体力、社交、兴趣、关系）。
- 禁用：整体灰化 + 原因文本（`err.*`，映射表见 `prompt.py`）。

### 结果面板 result_panel（活动完成后）
- 矩形 `100,40,280,190`；插图占位 160×90。
- 数值列表逐条出现，间隔 0.12s（`REVEAL_INTERVAL`）；Space 未展示完时先补齐再关闭。
- 只显示 B 的 `deltas`，0 不显示，增益绿 #6ABE30、减益红 #D95763。
- `triggered_event_id` 非空时底部提示“有事情发生了……”。

### 对话框 dialogue_box（事件内）
- 矩形 `4,166,472,100`；头像 96×96 @(6,168)；名字条 @(108,170)；正文区 `(108,188,362,72)` 4 行。
- 打字机速度读 `settings.text_speed`（instant=即时，normal=20 字/秒，slow=10 字/秒）。
- Space/E：打字中 → 整页；整页 → 下一页。

### 事件场景 event_scene
- 选项列表 `276,92,200,68`，最多 3 项、每项高 20。
- W/S 循环移动光标（跳过锁定项）；1/2/3 直接选择（锁定无效并显示原因）。
- 锁定原因：优先 `evt.<event_id>.lock.<choice_id>`，其次通用 `err.*`，2 秒后自动消失。
- Esc 无效（事件不可中途退出，由集成层保证）。

### 日结算 day_summary
- 矩形 `120,60,240,150`；“第 N 天结束” + 3 次行动摘要 + 精力恢复 + 学期事件预告 + `[Space] 继续`。

### Tab 状态面板 tab_panel
- 矩形 `40,24,400,222`；左 5 属性条 + 精力上限；右 3 NPC 关系（未知显示 ？？？）+ 本学期剩余天数。
- 对话/事件期间 Tab 无效（D3）。

### 主菜单 main_menu
- 列表 `180,150,120,90`：新游戏 / 继续（无 autosave 置灰，原因“还没有存档”）/ 读档 / 设置 / 退出。

### 暂停菜单 pause_menu / 设置 settings_menu / 存读档 save_menu
- Esc 呼出暂停；设置文本速度 + 3 音量滑块（A/D 每次 ±10）。
- 存档位 3 + autosave 展示；空位不可读档。

### 毕业界面 graduation_scene
- 全屏 4 页：总评属性 → 四年回顾（`highlights`）→ 结局标题与正文（3 段）→ 制作人员与返回。
- 正文来自 `ending.<id>.title / body.1~3`；不评判“失败”。

### 新手教程 tutorial
- 5 步见 D7 表；横幅位于 `120,210,240,24`；完成写入 `GameState.tutorial_done`，读档不重复。
- 目标：新玩家 60 秒内完成第 1 次活动（D-01）。

## 键盘规则速查（D3）

| 按键 | 校园 | 对话/事件 | 菜单 |
|---|---|---|---|
| W/S ↑/↓ | 移动 | 选项循环光标 | 移动光标 |
| A/D ←/→ | 移动 | 无 | 调整滑块 ±10 |
| Space/Enter | 无 | 跳过打字/翻页/确认 | 确认 |
| 1/2/3 | 无 | 直接选选项 | 无 |
| E | 交互 | 同 Space | 无 |
| Esc | 暂停 | 无效 | 返回上一级 |
| Tab | 状态面板 | 无效 | 无效 |

## 已知待办（交接给 E / A）
1. 插图与头像使用占位色块，正式贴图由 A 的 AssetRegistry 接入（asset_id 见 dialogues.json 的 portrait 字段）。
2. `ui_panel_9slice` 资源缺失时退化为纯色面板并记录 `asset.missing`。
3. 事件锁定的条件值（学业 ≥ 40、兴趣 ≥ 45、社交 ≥ 35 等）需与 B 的 conditions.py 对齐，锁定原因 text_id 已冻结在 strings.json。
