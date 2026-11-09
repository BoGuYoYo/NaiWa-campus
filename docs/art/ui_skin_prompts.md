# UI 皮肤 AI 生图提示词（29 个 `ui_*` 资源）

对应 `assets/manifest.json` 里的 29 个 `ui_*` 资源，现在全是 `make_placeholders.py` 生成的
占位图（`LIC-0101`）。本文给出可直接粘贴的生图提示词，替换后重新登记许可（建议 `LIC-0210`，
作者写"用户提供的 AI 生成素材"）。

- 画布：游戏内部 480×270，UI 用**同一套 480×270 逻辑像素**，最近邻放大。
- 调色板：`assets/palette.png`，32 色，主色见下表，**生成图尽量只用这些色**。
- 描边：图标/键帽 1 px `#2B2235`；面板外框用暖金 `#C0A15F`。
- 必须：透明背景 PNG、无文字、无渐变、无抗锯齿（要么硬边，要么出图后做最近邻降采样）。

## 0. 调色板（生成时贴给模型，或作为负面约束）

| 用途 | 色值 |
| --- | --- |
| 深底 / 描边 | `#1B1F2A` `#2B2235` `#2C3446` `#3A4458` |
| 暖金强调 | `#F7C81E` `#FFDD5C` `#D9A417` `#C0A15F` |
| 纸白 / 文本 | `#F4F1E8` `#FFF6DF` `#FFFBEE` `#F1E2BC` `#E3CE9E` |
| 增益 / 减益 / 警告 | `#4F8A5B` `#8FC08A` / `#C0483F` `#E28B3A` / `#F2C14E` |
| 中性灰蓝 | `#B8BFC9` `#7A828F` `#4A505C` |
| 其余辅助 | `#6A6A45` `#353320` `#1A1712` `#F2F2F2` `#3F6EA8` `#8FB6DC` `#8FD3C7` `#7A5AA8` `#E091B0` `#8A6A46` `#F4D2B0` `#4C4A2F` |

## 1. 全局风格前缀（每条提示词都接在开头）

```text
pixel art game UI asset, 16-bit SNES style, crisp 1px hard edges, no anti-aliasing,
limited 32-color palette: deep navy #1B1F2A and #2B2235, warm gold #F7C81E and #C0A15F,
paper white #FFF6DF, flat shading, no gradients, no outline glow, no drop shadow,
front orthographic view, centered, symmetrical, transparent background, no text, no letters, no watermark
```

中文版（给支持中文的模型）：

```text
像素风游戏 UI 素材，16 位超任风格，1 像素硬边、禁止抗锯齿，
限定 32 色调色板：深蓝 #1B1F2A / #2B2235、暖金 #F7C81E / #C0A15F、纸白 #FFF6DF，
平涂无渐变、无发光、无投影，正面正交视角、居中、左右对称，透明背景，
画面里不要出现任何文字、字母或水印。
```

负面提示词（通用）：

```text
--no text, letters, numbers, watermark, signature, blur, gradient, glow, bevel 3D, photo,
realistic, chrome, glossy, drop shadow, anti-aliasing, noise, dirt, frame border outside canvas,
multiple objects, perspective, tilted, cropped
```

---

## 2. 九宫格面板 `ui_panel_9slice`（48×48，边距 16）

游戏里按整张图拉伸使用（后续可换真正的 9-slice：四角固定、中间拉伸）。
所以**四角必须完全一样、中间必须是纯色**。

```text
[风格前缀] + a 9-slice UI panel texture for a game dialog box, square canvas,
1/3 of the canvas is a 2px warm gold border #C0A15F with a thin inner dark line #2B2235,
thick dark navy fill #1B1F2A with a subtle 1px lighter inner edge #3A4458 near the border,
completely flat and uniform color in the middle third, four corners pixel-identical,
no decoration crossing the middle, no text, seamless when stretched in the center
```

| 项 | 要求 |
| --- | --- |
| 输出 | 1024×1024，再最近邻降到 48×48 |
| 边框 | 生成图里占 1/3（≈341 px），降到 48 后正好 16 px |
| 中间 | 必须均匀 `#1B1F2A`，不能有图案（会被拉伸成拉丝） |
| 四角 | 必须一致；有花纹也要四角镜像对称 |

如果想要三种皮肤（石质/纸质/像素金属），把 `warm gold border` 换成
`carved stone border` / `paper washi border` / `pixel chrome border`，其余不变。

---

## 3. 属性图标 6 个（16×16，建议一张 4×4 图标表一次出）

**推荐做法**：一次生成 512×512 的图标表（4 列 × 4 行，每格 128），再按格切图——
风格统一，比逐个生成稳。

```text
[风格前缀] + a 4x4 sprite sheet of 16 pixel-art game UI icons on transparent background,
each icon inside its own equal cell with 8px padding, consistent 1px #2B2235 outline,
flat two-tone shading using only the palette,
icons in reading order:
row1: open book, dumbbell, heart, speech bubble with two dots, four-point sparkle, lightning bolt
row2: blackboard with chalk, stack of three books, game controller, computer terminal with code lines,
       waving flag, running track lane
row3: rice bowl with chopsticks, bed with pillow, two footprints on a path,
       coin purse, clock, map pin
row4: (repeat simple shapes: star, arrow, plus, check mark) as filler
no text, no letters, no numbers, no grid lines, no background
```

单图版（逐个替换后缀即可）：

| # | asset_id | 主体（英文） | 说明 |
| --- | --- | --- | --- |
| 1 | `ui_icon_academic` | `an open book with a bookmark` | 学业 |
| 2 | `ui_icon_stamina` | `a dumbbell, side view` | 体力 |
| 3 | `ui_icon_mood` | `a rounded heart with a small highlight pixel` | 心情（不要用红心，用暖金/珊瑚） |
| 4 | `ui_icon_social` | `a speech bubble with two dots` | 社交 |
| 5 | `ui_icon_interest` | `a four-point sparkle / star` | 兴趣 |
| 6 | `ui_icon_energy` | `a lightning bolt` | 精力 |

```text
[风格前缀] + a single 16x16 pixel-art icon of <主体>, thick 1px #2B2235 outline,
warm gold #F7C81E as the main color, paper white #FFF6DF accent, dark navy background removed,
icon fills 90% of the canvas, centered, no text
```

---

## 4. 活动图标 9 个（16×16，同样建议一张表）

```text
[风格前缀] + a 3x3 sprite sheet of 9 pixel-art activity icons on transparent background,
equal cells with 8px padding, consistent 1px #2B2235 outline, warm gold accent,
reading order left-to-right, top-to-bottom:
1 blackboard with a chalk tray, 2 a stack of three books with a bookmark,
3 a game controller, 4 a computer terminal showing two code lines,
5 a waving club flag on a pole, 6 a running track lane with a sweat drop,
7 a rice bowl with chopsticks, 8 a bed with a folded blanket, 9 two footprints on a stone path
no text, no letters, no numbers, no background
```

| # | asset_id | 语义 | 主体 |
| --- | --- | --- | --- |
| 1 | `ui_icon_attend_class` | 上课 | 黑板 + 粉笔槽 |
| 2 | `ui_icon_library_study` | 图书馆学习 | 三本书 + 书签 |
| 3 | `ui_icon_play_games` | 打游戏 | 手柄 |
| 4 | `ui_icon_create_work` | **敲代码** | 终端窗口 + 两行代码（**不要画笔画画**） |
| 5 | `ui_icon_join_club` | 参加社团 | 旗子 |
| 6 | `ui_icon_exercise` | 操场锻炼 | 跑道 + 汗滴 |
| 7 | `ui_icon_eat_canteen` | 食堂吃饭 | 饭碗 + 筷子 |
| 8 | `ui_icon_rest_dorm` | 宿舍休息 | 床 |
| 9 | `ui_icon_campus_walk` | 校园闲逛 | 石板路上的脚印 |

> `create_work` 已经改成"敲代码"（见 `CHANGELOG_API.md` §8），图标必须是终端/代码行，
> 别再出现画板、画笔、调色盘。

---

## 5. 按键提示 8 个（16×16，`e space tab esc w a s d`）

**推荐做法**：只生成**空键帽**，字母由代码用字体渲染——这样不会出现模型画错字母。
若一定要带字母，用第二版提示词，并在验收时逐张核对拼写。

空键帽（一套 8 个可复用，只需 1 张）：

```text
[风格前缀] + a single empty keycap icon, top-down 3/4 pixel style, rounded 2px corner,
outer 1px #2B2235 outline, key face in #3A4458 with a 1px #C0A15F top highlight,
bottom edge 2px darker #1B1F2A to suggest thickness, completely blank face, no letters
```

带字母版（把 `<KEY>` 换成 `E` / `SPACE` / `TAB` / `ESC` / `W` / `A` / `S` / `D`）：

```text
[风格前缀] + a pixel-art keycap icon with the single character "<KEY>" engraved in
paper white #FFF6DF, 3x5 pixel font, perfectly centered and legible at 16x16,
outer 1px #2B2235 outline, key face #3A4458, one 1px highlight line on top edge
```

| asset_id | 字母 | 备注 |
| --- | --- | --- |
| `ui_key_e` / `ui_key_w` / `ui_key_a` / `ui_key_s` / `ui_key_d` | 单字母 | 16×16 里 1 个 3×5 字 |
| `ui_key_space` | `SPACE` | 字太宽，建议画成**长条键帽**（24×16 再缩） |
| `ui_key_tab` / `ui_key_esc` | `TAB` / `ESC` | 3 个字母，字号压到 3×5 仍可读 |

---

## 6. 时段点 2 个（8×8）

```text
[风格前缀] + two tiny 8x8 pixel UI dots on transparent background, side by side:
left one solid warm gold #F7C81E with a 1px #B8860B bottom shade (used slot),
right one hollow with a 1px #4A505C ring and dark #1B1F2A center (unused slot),
perfectly round by pixel steps, no anti-aliasing, no glow
```

| asset_id | 语义 |
| --- | --- |
| `ui_slot_full` | 已用掉的行动时段（实心金色） |
| `ui_slot_empty` | 剩余时段（空心灰蓝） |

## 7. 数值条 2 个（100×8）

```text
[风格前缀] + a horizontal 100x8 pixel UI bar, two separate assets on transparent background:
top = frame: 1px #2B2235 outer outline, 1px #3A4458 inner bevel, hollow dark #1B1F2A center,
bottom = fill: solid vertical gradient-free block, 1px lighter #8FC08A highlight on the top row,
1px darker #4F8A5B on the bottom row, both ends square (must tile horizontally)
no text, no numbers, no rounded ends
```

| asset_id | 用途 | 注意 |
| --- | --- | --- |
| `ui_bar_frame` | 条的外框 | 左右两端各 2 px 固定，中间可拉伸 |
| `ui_bar_fill` | 条的填充 | 纯色 + 上下各 1 px 明暗，横向可平铺 |

## 8. 光标 1 个（8×8）

```text
[风格前缀] + a small 8x8 pixel-art selection cursor, a solid warm gold #F7C81E right-pointing
triangle with a 1px #2B2235 outline, sharp pixel steps, no glow, transparent background
```

> 现在菜单光标用的是文本 `>`（`UILabel`），生成这张图之后可以换成
> `UIIcon(..., "ui_cursor")`，改动只有一行。

---

## 9. 生成与落地参数

| 项 | 建议 |
| --- | --- |
| 出图尺寸 | 面板 1024²，图标表 512²，单图标 256²，键帽 256²，条 1024×128 |
| 采样 | 支持 pixel-art 的模型直接出；出完用**最近邻**缩到目标尺寸（48/16/8/100×8） |
| 透明 | 必须真透明（PNG alpha），不要"白底"——白底会被当成图案画进面板 |
| 后处理 | 量化到 32 色（`tools/make_placeholders.py` 的 `PALETTE` 是唯一来源）、透明像素 RGB 置 0 |
| 验收 | 尺寸精确；四角对称；无文字（键帽除外）；无半透明；调色板命中率 ≥ 90% |

出图放到 `素材/UI/` 下（文件名与 `asset_id` 对应，如 `ui_icon_academic.png`、`ui_panel_9slice.png`），
之后可以用一条命令统一落位 + 量化 + 写 manifest 许可：

```powershell
python tools/import_ui_skin.py --source "..\素材\UI" --verify
```

> 该导入脚本尚未创建；生成图到位后由 A 补，流程与 `import_campus_props.py` /
> `process_building_textures.py` 一致（白底/棋盘背景泛洪去背 → 最近邻缩放到目标尺寸 →
> 量化 32 色 → 透明像素 RGB 置 0 → 登记 `manifest.json` 与 `LICENSES.csv`）。

## 10. 一句话验收清单

- [ ] 29 个资源尺寸与 `manifest.json` 标注一致（面板 48²/48 边距 16、图标 16²、键帽 16²、点 8²、条 100×8、光标 8²）
- [ ] 全部透明背景，无白边、无投影、无渐变、无半透明
- [ ] 图标只用调色板颜色，1 px `#2B2235` 描边
- [ ] `ui_icon_create_work` 是终端 + 代码行，不是画具
- [ ] `ui_panel_9slice` 中间 1/3 纯色、四角一致
- [ ] `ui_bar_*` 左右两端可拼接、横向可平铺
- [ ] 键帽字母逐个核对（E/W/A/S/D/TAB/ESC/SPACE）
