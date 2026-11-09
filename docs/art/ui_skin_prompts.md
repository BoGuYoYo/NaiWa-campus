# UI 皮肤 AI 生图提示词（29 个 `ui_*` 资源）

对应 `assets/manifest.json` 里的 29 个 `ui_*` 资源。2026-11-09 已导入用户生成的 UI 皮肤，
登记为 `LIC-0210`；本文保留生成规格和验收约束，方便后续重新出图。

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

## 3. 属性图标 6 个（严格框定版，16×16）

这一版把每个图标都钉死在**同一个 16×16 网格**上：位置、尺寸、4 个色值、描边、明暗方向、
留白全部写死，6 个图标除了"形状"和"主色"之外没有任何自由度，所以出来的东西风格必然一致。

### 3.0 严格模板（6 条都套这个）

| 约束 | 值 |
| --- | --- |
| 逻辑画布 | **16×16**；出图 **512×512**（1 逻辑像素 = 32 设备像素），交付时最近邻缩到 16×16 |
| 安全区 | 图形必须落在 **x = 2..13、y = 3..12**（12 宽 × 10 高），四周各留 2 逻辑像素透明边 |
| 描边 | 外轮廓 **1 逻辑像素 = 32 设备像素**，闭合不断线，颜色固定 `#2B2235` |
| 用色 | **每个图标只用 4 色**：描边 `#2B2235` + 主色 + 亮色 + 暗色（见 3.1~3.6） |
| 明暗 | 平涂，最多两级；光源固定**左上**，暗面只出现在右下 |
| 网格 | 所有边缘对齐 16×16 网格；不许抗锯齿、不许抖动（dithering）、不许半透明 |
| 背景 | 真透明 PNG；不许白底、棋盘底、投影、外发光 |
| 构图 | 单主体、居中、不裁切；左右对称（闪电这种几何本身不对称的除外） |
| 禁止 | 文字/字母/数字、边框、外框、圆角超过 1 像素、3D 斜面、透视、多个物体 |

**通用提示词骨架**（把 `<形状>` `<主色>` `<亮色>` `<暗色>` 换掉即可，其余一个字都别改）：

```text
pixel art game UI icon, 16x16 logical grid rendered at 512x512, 1 logical pixel = 32 device pixels,
single object only: <形状>, occupying x = 2..13 and y = 3..12 of the 16x16 grid, perfectly centered,
1-logical-pixel closed outline #2B2235 on every edge with no gaps,
exactly 4 colors: outline #2B2235, main <主色>, light <亮色>, shade <暗色>,
flat two-tone shading, light source from the top-left, shade only on the bottom-right,
hard pixel edges snapped to the 16x16 grid, no anti-aliasing, no dithering, no semi-transparent pixels,
transparent background, 2-logical-pixel empty margin on all four sides,
no text, no letters, no numbers, no border, no frame, no drop shadow, no glow, no 3D bevel, no perspective
```

图例：`.` 透明 · `#` 描边 `#2B2235` · `W` `#FFF6DF` · `w` `#E3CE9E` · `T` `#C0A15F` ·
`S` `#B8BFC9` · `s` `#7A828F` · `P` `#E091B0` · `p` `#F4D2B0` · `r` `#C0483F` ·
`V` `#7A5AA8` · `X` `#FFFBEE` · `G` `#F7C81E` · `B` `#3F6EA8`

参考预览（按下面 6 个 16×16 布局实际渲染，10 倍最近邻放大）：`docs/art/preview/ui_attr_icons.png`

### 3.1 `ui_icon_academic` 学业 —— 学士帽

| 项 | 值 |
| --- | --- |
| 形状 | 一顶正面朝镜头的学士帽：上方菱形帽板 + 下方向外张开的梯形帽身，**不画流苏**（16 px 内会糊） |
| 几何 | 帽板为菱形：顶点 y3（x7..8）→ 最宽 y6（x2..13）→ 收口 y8（x7..8）；帽身 y9..12 由 6 宽张开到 8 宽 |
| 4 色 | 描边 `#2B2235` / 帽板 `#FFF6DF` / 帽板暗面 `#E3CE9E` / 帽身 `#C0A15F` |
| 参考布局 | 见下方 16×16 |

```text
y3 .......##.......
y4 ......#WW#......
y5 ....#WWWWWW#....
y6 ..#WWWWWWWWWW#..
y7 ....#wwwwww#....
y8 ......#ww#......
y9 .....#TTTT#.....
y10 ....#TTTTTT#....
y11 ....#TTTTTT#....
y12 ....########....
```

提示词（`<形状>` 已填）：

```text
pixel art game UI icon, 16x16 logical grid rendered at 512x512, 1 logical pixel = 32 device pixels,
single object only: a graduation mortarboard seen from the front, a flat diamond cap board on top of
a short trapezoid cap body that widens toward the bottom, symmetrical, no tassel,
occupying x = 2..13 and y = 3..12 of the 16x16 grid, perfectly centered,
1-logical-pixel closed outline #2B2235 on every edge with no gaps,
exactly 4 colors: outline #2B2235, main #FFF6DF, shade #E3CE9E, cap body #C0A15F,
flat two-tone shading, light source from the top-left, shade only on the bottom-right,
hard pixel edges snapped to the 16x16 grid, no anti-aliasing, no dithering, no semi-transparent pixels,
transparent background, 2-logical-pixel empty margin on all four sides,
no text, no letters, no numbers, no border, no frame, no drop shadow, no glow, no 3D bevel, no perspective
```

不要画成：一本书（那是"三本书"活动图标）、博士服、带流苏的帽子、学士帽侧视。

### 3.2 `ui_icon_stamina` 体力 —— 哑铃（正视，左右对称）

| 项 | 值 |
| --- | --- |
| 形状 | 一个横向哑铃：左右两块配重片 + 中间一根短握杆，正视，完全左右对称 |
| 几何 | 左片 x2..5、右片 x10..13，均为 y4..11（4×8）；握杆 x6..9，只占 y7..8（4×2） |
| 4 色 | `#2B2235` / 主 `#B8BFC9` / 亮 `#F2F2F2` / 暗 `#7A828F` |
| 参考布局 | 见下方 16×16 |

```text
y5 ..####....####..
y6 ..#SS#....#SS#..
y7 ..#SS#ssss#SS#..
y8 ..#Ss#ssss#Ss#..
y9 ..#Ss#....#Ss#..
y10 ..####....####..
```

```text
pixel art game UI icon, 16x16 logical grid rendered at 512x512, 1 logical pixel = 32 device pixels,
single object only: a horizontal dumbbell seen from the front, two rectangular weight plates of equal
size on the left and right with a short thin handle bar between them, perfectly left-right symmetric,
occupying x = 2..13 and y = 3..12 of the 16x16 grid, centered vertically on y = 7.5,
1-logical-pixel closed outline #2B2235 on every edge with no gaps,
exactly 4 colors: outline #2B2235, main #B8BFC9, light #F2F2F2, shade #7A828F,
flat two-tone shading, light source from the top-left, shade only on the bottom-right,
hard pixel edges snapped to the 16x16 grid, no anti-aliasing, no dithering, no semi-transparent pixels,
transparent background, 2-logical-pixel empty margin on all four sides,
no text, no letters, no numbers, no border, no frame, no drop shadow, no glow, no 3D bevel, no perspective
```

不要画成：俯卧撑姿势、杠铃（杆更长）、健身器械、单独一块铁片、带反光的金属渐变。

### 3.3 `ui_icon_mood` 心情 —— 心形

| 项 | 值 |
| --- | --- |
| 形状 | 经典 8-bit 圆润心形：两个圆弧顶 + 一个向下的尖角，左右完全对称 |
| 几何 | 最宽 y5..y7 满宽 x2..13；尖角收在 y12（x7..8）；总高 y3..y12 |
| 4 色 | 描边 `#2B2235` / 主 `#E091B0` / 亮面 `#F4D2B0` / 暗面 `#C0483F`（**不要正红**，是"心情"不是血量） |
| 参考布局 | 见下方 16×16 |

```text
y3 ....##....##....
y4 ...#PP#..#PP#...
y5 ..#PPPPPPPPPP#..
y6 ..#PPPPPPPPPP#..
y7 ..#PPPPPPPPPP#..
y8 ...#PPPPPPPP#...
y9 ....#PPPPPP#....
y10 .....#PPPP#.....
y11 ......#rr#......
y12 .......##.......
```

```text
pixel art game UI icon, 16x16 logical grid rendered at 512x512, 1 logical pixel = 32 device pixels,
single object only: a classic rounded pixel-art heart with two round lobes on top and a tapered point
at the bottom, perfectly left-right symmetric, flat fill with no gloss,
occupying x = 2..13 and y = 3..12 of the 16x16 grid, perfectly centered,
1-logical-pixel closed outline #2B2235 on every edge with no gaps,
exactly 4 colors: outline #2B2235, main #E091B0, light #F4D2B0, shade #C0483F,
flat two-tone shading, light source from the top-left, shade only on the bottom-right,
hard pixel edges snapped to the 16x16 grid, no anti-aliasing, no dithering, no semi-transparent pixels,
transparent background, 2-logical-pixel empty margin on all four sides,
no text, no letters, no numbers, no border, no frame, no drop shadow, no glow, no 3D bevel, no perspective
```

不要画成：写实心脏、红心带白色高光、心电波形、两个心叠在一起、带脸部表情的爱心。

### 3.4 `ui_icon_social` 社交 —— 双点对话气泡

| 项 | 值 |
| --- | --- |
| 形状 | 一个圆角对话气泡 + 左下角一小截尾巴 + 气泡内两个方点（表示"两个人在说话"） |
| 几何 | 气泡 x2..13、y3..9（12×7）；尾巴在 y10..11（x4..6，两行收窄）；两个方点各 2×2，位置 x5..6 与 x9..10，y5..6 |
| 4 色 | `#2B2235` / 主 `#FFF6DF` / 亮 `#FFFBEE` / 暗 `#E3CE9E`；两个点用 `#3F6EA8` |
| 参考布局 | 见下方 16×16 |

```text
y3 ...##########...
y4 ..#WWWWWWWWWW#..
y5 ..#WWBBWWBBWW#..
y6 ..#WWBBWWBBWW#..
y7 ..#WWWWWWWWWW#..
y8 ..#WWWWWWWWWW#..
y9 ...##########...
y10 .....####.......
y11 ......##........
```

```text
pixel art game UI icon, 16x16 logical grid rendered at 512x512, 1 logical pixel = 32 device pixels,
single object only: a rounded speech bubble with a short pointed tail at the bottom-left and exactly
two small square dots inside it, no other marks,
occupying x = 2..13 and y = 3..11 of the 16x16 grid, centered,
1-logical-pixel closed outline #2B2235 on every edge with no gaps,
exactly 4 colors: outline #2B2235, main #FFF6DF, light #FFFBEE, shade #E3CE9E, the two dots #3F6EA8,
flat two-tone shading, light source from the top-left, shade only on the bottom-right,
hard pixel edges snapped to the 16x16 grid, no anti-aliasing, no dithering, no semi-transparent pixels,
transparent background, 2-logical-pixel empty margin on all four sides,
no text, no letters, no numbers, no border, no frame, no drop shadow, no glow, no 3D bevel, no perspective
```

不要画成：三个点（省略号）、对话气泡里写字、两个气泡、云朵形气泡、方形直角气泡。

### 3.5 `ui_icon_interest` 兴趣 —— 四角星（闪光）

| 项 | 值 |
| --- | --- |
| 形状 | 一枚四角星：上下两个尖角 + 左右两个尖角，中心 2×2 亮块；**四角对称** |
| 几何 | 竖向尖 y2..y9（x7..8），横向满宽 y5..y6（x2..13），中心高光 2×2 在 (7,5) |
| 4 色 | 描边 `#2B2235` / 主 `#7A5AA8`（紫）/ 亮面 `#B79AD6`≈`#E091B0` 只在上臂 1 px / 暗面 `#4A505C` |
| 参考布局 | 见下方 16×16 |

```text
y2 .......##.......
y3 ......#VV#......
y4 .....#VVVV#.....
y5 ..#VVVVVVVVVV#..
y6 ..#VVVVVVVVVV#..
y7 .....#VVVV#.....
y8 ......#VV#......
y9 .......##.......
```

```text
pixel art game UI icon, 16x16 logical grid rendered at 512x512, 1 logical pixel = 32 device pixels,
single object only: a four-pointed sparkle star with one vertical and one horizontal pair of tapered
points meeting at the center, a 2x2 light pixel in the middle, four-fold symmetric,
occupying x = 2..13 and y = 2..9 of the 16x16 grid, perfectly centered,
1-logical-pixel closed outline #2B2235 on every edge with no gaps,
exactly 4 colors: outline #2B2235, main #7A5AA8, light #E091B0 only as a 1-pixel top-left edge, shade #4A505C,
flat two-tone shading, light source from the top-left, shade only on the bottom-right,
hard pixel edges snapped to the 16x16 grid, no anti-aliasing, no dithering, no semi-transparent pixels,
transparent background, 2-logical-pixel empty margin on all four sides,
no text, no letters, no numbers, no border, no frame, no drop shadow, no glow, no 3D bevel, no perspective
```

不要画成：五角星、六芒星、三颗星散落、发光勋章、灯泡（那是"灵感"的常见画法但和精力撞色）。

### 3.6 `ui_icon_energy` 精力 —— 闪电

| 项 | 值 |
| --- | --- |
| 形状 | 经典折线闪电：上宽下尖，中间有一个向右的横向台阶；**允许左右不对称**（几何本身不对称） |
| 几何 | 顶部 y2（x6..8）向左下延伸，台阶在 y6（x2..10），尖端收在 y12（x2..4） |
| 4 色 | `#2B2235` / 主 `#F7C81E` / 亮 `#FFDD5C` / 暗 `#D9A417` |
| 参考布局 | 见下方 16×16 |

```text
y2 ......###.......
y3 .....#GGG#......
y4 ....#GGG#.......
y5 ...#GGG#........
y6 ..#GGGGGGG#.....
y7 .......#GGG#....
y8 ......#GGG#.....
y9 .....#GGG#......
y10 ....#GGG#.......
y11 ...#GGG#........
y12 ..###...........
```

```text
pixel art game UI icon, 16x16 logical grid rendered at 512x512, 1 logical pixel = 32 device pixels,
single object only: a classic zigzag lightning bolt, wide at the top, narrowing to a sharp point at the
bottom, with one horizontal step jutting to the right in the middle, asymmetric silhouette allowed,
occupying x = 2..13 and y = 2..12 of the 16x16 grid, centered,
1-logical-pixel closed outline #2B2235 on every edge with no gaps,
exactly 4 colors: outline #2B2235, main #F7C81E, light #FFDD5C, shade #D9A417,
flat two-tone shading, light source from the top-left, shade only on the bottom-right,
hard pixel edges snapped to the 16x16 grid, no anti-aliasing, no dithering, no semi-transparent pixels,
transparent background, 2-logical-pixel empty margin on all four sides,
no text, no letters, no numbers, no border, no frame, no drop shadow, no glow, no 3D bevel, no perspective
```

不要画成：带发光光环的闪电、云中闪电、双闪电、闪电符号字母 "S"、金色描边闪电。

### 3.7 强化负面提示词（6 条都加）

```text
--no text, letters, numbers, glyphs, badge, frame, border, rounded square background,
drop shadow, outer glow, bloom, gradient, dithering, anti-aliasing, semi-transparent pixels,
3D bevel, emboss, glossy highlight, photo, realistic, chrome, glass, brush stroke,
multiple objects, collage, sprite sheet grid lines, watermark, signature, jpeg artifacts
```

### 3.8 一次出 6 个的替代做法（不推荐但可用）

要求模型出 **3 列 × 2 行**、每格 256 的图标表，六个格子的顺序写死：
`学业(学士帽) | 体力(哑铃) | 心情(心)` / `社交(气泡) | 兴趣(四角星) | 精力(闪电)`，
并强调"六格共用同一套 4 色与同一描边粗细"。切图时按格裁 256×256 再缩到 16×16。
**注意**：图标表最容易出现"风格漂移"（有的格描边 2px、有的没描边），验收要逐格查。

### 3.9 逐项验收（6 个都过一遍）

- [ ] 尺寸 16×16，四周至少有 1 像素透明边（安全区没被撑破）
- [ ] 只有 4 种颜色（量一下：≤ 5 种，抗锯齿会带出中间色）
- [ ] 外轮廓闭合、厚度 1 像素，颜色 `#2B2235`
- [ ] 明暗方向一致：亮在左上、暗在右下
- [ ] 左右对称（学士帽 / 哑铃 / 心 / 气泡 / 四角星）；闪电允许不对称
- [ ] 没有文字、没有外框、没有投影
- [ ] 缩到 16×16 后仍能认出是什么（把它们并排贴到深色 `#1B1F2A` 上看一眼）


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

当前导入脚本为 `tools/import_ui_skin.py`：它读取 `素材/UI/` 的合成图，按表格切分活动图标、
共享键帽和点/条/光标，再执行白底/棋盘背景泛洪去背、最近邻缩放、32 色量化、透明像素 RGB 清零，
并更新 `manifest.json` 与 `LICENSES.csv`。重复运行结果稳定；缺源图时只打印 `SKIP`，不会覆盖现有文件。

## 10. 一句话验收清单

- [ ] 29 个资源尺寸与 `manifest.json` 标注一致（面板 48²/48 边距 16、图标 16²、键帽 16²、点 8²、条 100×8、光标 8²）
- [ ] 全部透明背景，无白边、无投影、无渐变、无半透明
- [ ] 图标只用调色板颜色，1 px `#2B2235` 描边
- [ ] `ui_icon_create_work` 是终端 + 代码行，不是画具
- [ ] `ui_panel_9slice` 中间 1/3 纯色、四角一致
- [ ] `ui_bar_*` 左右两端可拼接、横向可平铺
- [ ] 键帽字母逐个核对（E/W/A/S/D/TAB/ESC/SPACE）
