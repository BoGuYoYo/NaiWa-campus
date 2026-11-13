# 室内家具与装修 · AI 生图提示词（5 栋建筑）

> 用途：给 5 个室内场景（宿舍 / 教学楼 / 图书馆 / 社团楼 / 食堂）生成**地板、墙面贴图**和**家具立牌**。
> 交付后由 A 用 `tools/import_interior_art.py`（下一步写）落位到 `assets/interior/<building>/`。
> 规格依据：`docs/art/README.md`（24 px/米、32 色调色板、PNG RGBA、场景物体不描边）。

---

## 0. 全局规格（每次生成都先读这段）

| 项 | 规定 |
| --- | --- |
| 像素密度 | **24 px = 1 米**（和室外场景一致，不许改） |
| 视角 | 正交相机、俯角 **40°** 的 3/4 俯视：能同时看到顶面和正面，正面朝屏幕下方（南） |
| 调色板 | 只用 `assets/palette.png` 的 32 色（见 §0.1），生成后量化到 32 色 |
| 描边 | **不要描边**（描边只给角色/NPC）；靠 3 级明暗区分结构 |
| 光影 | 光源在**左上方**，左上受光、右下投影；投影画在物体自身上，不要画地面阴影 |
| 背景 | 全透明 RGBA；透明区域 RGB 必须是 0（不要白底、不要棋盘格） |
| 格式 | PNG RGBA 8 位，无色彩配置；先按 4× 尺寸生成，再用最近邻缩到目标尺寸（禁止双三次） |
| 文字 | 画面里**不要出现任何文字/字母/数字**（贴图上的招牌文字由 UI 文本层负责） |

### 0.1 调色板（32 色，按用途分组）

```
描边   #2B2235
深底   #1B1F2A  #2C3446  #3A4458
黄     #F7C81E  #FFDD5C  #D9A417
奶油   #F1E2BC  #FFF6DF  #E3CE9E
木/肢  #4C4A2F  #6A6A45  #353320
暗     #1A1712  #FFFBEE
金     #C0A15F  #E8CF97
白灰   #F2F2F2  #B8BFC9  #7A828F  #4A505C
红橙   #C0483F  #E28B3A
绿     #4F8A5B  #8FC08A
蓝     #3F6EA8  #8FB6DC
青     #8FD3C7
紫     #7A5AA8
粉     #E091B0
棕     #8A6A46
肤     #F4D2B0
```

---

## 1. 通用前缀 / 负面提示词（每张图都带上）

**中文前缀（粘贴在每条提示词前面）**

```
像素风游戏室内素材，3/4 俯视视角（相机俯角 40°），正交投影，正面朝下。
24 像素 = 1 米的比例感，硬边像素，无抗锯齿，无渐变，无描边。
只用给定 32 色调色板，光源在左上方，物体自身带右下方向的暗面。
背景全透明，画面里没有任何文字。
```

**English prefix（for models that prefer English）**

```
pixel art game asset, 3/4 top-down view with 40-degree camera tilt, orthographic,
front facing down. Hard-edged pixels, no anti-aliasing, no gradients, no outlines.
Restricted to a 32-color palette, light from upper-left, self-shadow on the lower right.
Fully transparent background, no text anywhere in the image.
```

**负面提示词（中文）**

```
写实照片、3D 渲染、光滑渐变、抗锯齿、模糊、描边、黑色外轮廓、
透视变形、地面阴影、投影到背景、白底、棋盘格背景、文字、字母、数字、水印、
超过 32 色的颜色、霓虹、反光高光、景深
```

**Negative prompt (English)**

```
photorealistic, 3d render, smooth gradient, anti-aliasing, blurry, outlined,
thick black outline, perspective distortion, drop shadow on ground, white background,
checkerboard background, text, letters, numbers, watermark, extra colors, neon,
specular highlights, depth of field
```

---

## 2. 五间房的装修风格（先出概念图定调，再切素材）

> 概念图只作风格参考，**不进游戏**；真正入库的是 §3 的地板/墙面和 §4 的家具。

### 2.1 宿舍（暖木 + 米色墙）

**中文**

```
【概念图】一间大学四人间宿舍的像素风室内全景，16:10。暖棕色木地板，米白色墙面，
墙脚有深色踢脚线；靠墙两套上下铺木床（床品用奶油色被子 + 蓝色枕头），
窗边一张木书桌配台灯，角落一个浅木衣柜；窗外是校园绿树。
整体干净、生活感、有点乱但不脏。俯角 40°，无人物。
```

**English**

```
[concept] pixel art interior of a four-person college dorm, 16:10. Warm brown wooden floor,
cream white walls with dark skirting board; two wooden bunk beds (cream quilts, blue pillows),
a wooden desk with a desk lamp by the window, a light-wood wardrobe in the corner;
green campus trees outside the window. Cozy, lived-in, slightly messy but clean.
40-degree top-down, no characters.
```

### 2.2 教学楼（浅灰绿 + 黑板）

**中文**

```
【概念图】大学教室像素风室内全景，16:10。浅灰绿色地砖，白灰墙面，后墙一整块深绿色黑板
（带木质边框和粉笔槽），黑板前一张木质讲台，两组连排课桌（桌面浅木色、金属桌腿），
天花板两盏长条日光灯。整洁、有点灰尘感。
```

**English**

```
[concept] pixel art university classroom, 16:10. Light grey-green floor tiles, off-white walls,
a large dark-green chalkboard on the back wall with wooden frame and chalk tray,
a wooden podium in front of it, two rows of connected student desks (light wood tops,
metal legs), two long fluorescent lights on the ceiling. Tidy, slightly dusty.
```

### 2.3 图书馆（深木 + 暖灯）

**中文**

```
【概念图】大学图书馆阅览室像素风室内全景，16:10。深棕色木地板，暖灰色墙面，
三面到顶的深木书架塞满书脊（书脊用红、蓝、绿、奶油四色块），中间一张长阅览桌配四把木椅，
桌上两盏绿色台灯；屋顶暖黄吊灯。安静、暖光。
```

**English**

```
[concept] pixel art university library reading room, 16:10. Dark brown wooden floor,
warm grey walls, floor-to-ceiling dark wood bookshelves on three sides stuffed with book spines
(red, blue, green, cream blocks), a long reading table with four wooden chairs in the middle,
two green banker's lamps on the table, warm yellow pendant lights. Quiet, warm light.
```

### 2.4 社团活动楼（水泥 + 海报）

**中文**

```
【概念图】大学社团活动室像素风室内全景，16:10。灰色水泥自流平地面，浅灰墙面，
墙上贴满社团海报（用色块表示，不写字），角落一张旧沙发（红棕色），
靠墙一张电脑桌配老式显示器，房间中间一个画架，墙上一块软木公告板。
有点杂乱的社团活动室气氛。
```

**English**

```
[concept] pixel art university club room, 16:10. Grey concrete floor, light grey walls covered
with club posters (color blocks only, no text), a worn red-brown sofa in the corner,
a computer desk with a chunky CRT monitor against the wall, an easel in the middle,
a cork notice board on the wall. Slightly cluttered club-room vibe.
```

### 2.5 食堂（白瓷砖 + 不锈钢）

**中文**

```
【概念图】大学食堂像素风室内全景，16:10。米白色方砖地面（砖缝浅灰），下半墙白瓷砖、
上半墙奶油色，一整排不锈钢打饭窗口（带玻璃挡板和菜盆），
大厅里两张长条餐桌配长凳（桌面浅木色），墙上一块菜单板（只有色块）。
明亮、干净、有点蒸汽感。
```

**English**

```
[concept] pixel art university canteen, 16:10. Cream square floor tiles with light grey grout,
white tiled lower walls and cream upper walls, a long row of stainless-steel serving windows
with glass sneeze guards and food trays, two long dining tables with benches (light wood tops),
a menu board on the wall (color blocks only). Bright, clean, slightly steamy.
```

---

## 3. 装修贴图（每栋 2 张：地板 + 墙面）

> **状态（2026-11-13）：本节已被实际素材替代，暂不需要再生成。**
> 用户已提供 `素材/建筑材质/`（五栋楼的地板 + 墙面共 10 张），由
> `tools/import_interior_art.py` 落成 `assets/campus/textures/interior/<建筑>_{floor,wall}.png`
> 并登记进 manifest（`tile_m` / `average_rgb`）。落地规格：地板 96×96 = 4 m 平铺、
> 墙面高 72 px = 3 m 层高（24 px/m）。若将来要换成像素风贴图，保持这两个尺寸
> 与 manifest 里的 `tile_m` 一致即可直接替换，无需改代码。

**规格**：`floor` 64×64 px（= 2.67 m 的四方连续砖块，**必须无缝平铺**）；`wall` 64×72 px（2.67 m 宽 × 3 m 高，同样四方连续）。

**统一提示词模板（中文）**

```
像素风【材质】四方连续贴图，正俯视（90° 正上方看），正交投影，无透视。
每块 64×64 像素，边界处图案必须能无缝拼接（上下左右对齐）。
只用 32 色调色板，光源左上，噪点颗粒感，无描边，无文字，无阴影，无场景物件。
```

**Template (English)**

```
seamless tileable pixel art texture of [material], straight top-down view, orthographic,
no perspective. 64x64 pixels per tile, edges must tile seamlessly in all four directions.
32-color palette only, light from upper-left, subtle dithering, no outlines, no text,
no shadows, no props.
```

| 建筑 | 文件名 | 材质关键词（贴到模板的 [material]） |
| --- | --- | --- |
| 宿舍 | `assets/interior/dorm/floor.png` | 暖棕色木地板，横向木板纹理，板缝 1 px 深棕 |
| 宿舍 | `assets/interior/dorm/wall.png` | 米白乳胶漆墙面，底部 6 px 深色踢脚线 |
| 教学楼 | `assets/interior/classroom/floor.png` | 浅灰绿色 30 cm 方砖，砖缝浅灰 |
| 教学楼 | `assets/interior/classroom/wall.png` | 白灰墙面，下半 40% 刷浅灰绿墙裙 |
| 图书馆 | `assets/interior/library/floor.png` | 深棕色人字拼木地板 |
| 图书馆 | `assets/interior/library/wall.png` | 暖灰色墙布，细密竖纹 |
| 社团楼 | `assets/interior/clubroom/floor.png` | 灰色水泥自流平，带少量深色斑点 |
| 社团楼 | `assets/interior/clubroom/wall.png` | 浅灰水泥墙，局部有 1 px 裂纹 |
| 食堂 | `assets/interior/canteen/floor.png` | 米白方砖，砖缝浅灰，砖面有极淡的深浅差 |
| 食堂 | `assets/interior/canteen/wall.png` | 下半白瓷砖（小方砖）、上半奶油色涂料 |

---

## 4. 家具立牌（17 件，逐个提示词）

> **立牌规格**：一张图一个物件，**底边贴画布底边、左右居中**，画布外全透明。
> 画布宽度 = 占地宽度（24 px/米），高度按物体真实高度给（家具默认 1 m = 24 px，衣柜/书架给 2 m）。
> 物件正面朝下（南），能看到一点点顶面（40° 俯视）。

### 4.1 宿舍

**① 床（上下铺）** `furn_bed` — 占地 4.0×2.0 m，画布 **96×64**

```
像素风大学宿舍上下铺木床，单一物件，3/4 俯视（40°），正面朝下，底边贴齐画布底部。
深棕色木框 + 奶油色被子 + 蓝色枕头，两层床板，侧边有木爬梯；可见床顶面。
96×64 像素，无描边，无地面阴影，透明背景，无文字。
```

**② 书桌（带台灯）** `furn_dorm_desk` — 占地 3.0×1.6 m，画布 **72×56**

```
像素风学生书桌，单一物件，3/4 俯视，正面朝下。浅木色桌面、深色桌腿，
桌面上一盏黄绿色台灯、两本摊开的书、一个笔筒。72×56 像素，无描边，透明背景，无文字。
```

**③ 衣柜** `furn_wardrobe` — 占地 1.3×3.8 m，画布 **48×64**

```
像素风双门木质衣柜，单一物件，正面朝下。浅木色门板、深色把手、门缝 1 px，
顶部有一点积灰的深色边。48×64 像素，无描边，透明背景，无文字。
```

### 4.2 教学楼

**④ 课桌连排（北）** `furn_desk_row_n` — 占地 6.0×1.0 m，画布 **144×40**

```
像素风一排三张连在一起的学生课桌，单一物件，3/4 俯视。浅木色桌面、深灰金属桌腿，
桌面各放一本书和一支笔，桌面边缘有 1 px 高光。144×40 像素，无描边，透明背景，无文字。
```

**⑤ 课桌连排（南）** `furn_desk_row_s` — 占地 6.0×0.8 m，画布 **144×40**

```
同上的学生课桌连排，稍窄一些、桌面更空，只放一个铅笔盒。144×40 像素，
无描边，透明背景，无文字。
```

**⑥ 讲台** `furn_podium` — 占地 4.0×1.0 m，画布 **96×40**

```
像素风木质讲台，单一物件，3/4 俯视，正面朝下。厚实的浅木色台体、深色台面，
台面上一盒粉笔和一块黑板擦。96×40 像素，无描边，透明背景，无文字。
```

### 4.3 图书馆

**⑦ 阅览长桌（带绿罩台灯）** `furn_reading_table` — 占地 4.0×1.2 m，画布 **96×48**

```
像素风图书馆阅览长桌，单一物件，3/4 俯视。深木色桌面，桌上两盏绿色灯罩台灯（暖黄光点），
两本摊开的书、一把木椅露在桌后。96×48 像素，无描边，透明背景，无文字。
```

**⑧ 书架（西墙，长 3.8 m）** `furn_shelf_w` — 占地 1.0×3.8 m，画布 **48×64**

```
像素风深木色书架，单一物件，3/4 俯视，正面朝下。四层隔板塞满书脊，
书脊用红、蓝、绿、奶油色的小色块表示，不许有可读文字。48×64 像素，无描边，透明背景。
```

**⑨ 书架（北墙，长 5 m）** `furn_shelf_n` — 占地 5.0×1.0 m，画布 **120×64**

```
同上风格的长书架，更宽（5 米），五层隔板，书脊色块错落。120×64 像素，无描边，透明背景。
```

**⑩ 服务台** `furn_service_desk` — 占地 3.0×0.6 m，画布 **72×40**

```
像素风图书馆服务台，单一物件，3/4 俯视。深木色台体 + 浅色台面，台面上一个还书箱和
一台老式显示器（屏幕用深蓝灰块）。72×40 像素，无描边，透明背景，无文字。
```

### 4.4 社团活动楼

**⑪ 电脑桌（含 CRT 显示器）** `furn_pc_desk` — 占地 3.0×1.6 m，画布 **72×56**

```
像素风电脑桌，单一物件，3/4 俯视，正面朝下。浅灰桌板 + 深灰桌腿，
桌上一台米白色 CRT 显示器（屏幕深蓝，带一点青色反光）、机械键盘和鼠标。72×56 像素，
无描边，透明背景，无文字。
```

**⑫ 画架** `furn_easel` — 占地 1.2×1.0 m，画布 **32×48**

```
像素风木质画架，单一物件，正面朝下。三脚木架 + 一块空白画布（奶油色），
画布边缘有夹子，架脚有颜料渍。32×48 像素，无描边，透明背景，无文字。
```

**⑬ 软木公告板** `furn_notice_board` — 占地 2.0×0.2 m，画布 **48×40**

```
像素风挂墙软木公告板，单一物件，正面朝下。棕色软木面 + 深木外框，
板上钉着 4 张彩色便签（黄、粉、蓝、绿小方块，不写字）。48×40 像素，无描边，透明背景。
```

**⑭ 沙发** `furn_sofa` — 占地 3.0×1.0 m，画布 **72×48**

```
像素风旧布艺沙发，单一物件，3/4 俯视，正面朝下。红棕色布面、深色木脚，
坐垫有 2 处磨损的浅色补丁，扶手略塌。72×48 像素，无描边，透明背景。
```

### 4.5 食堂

**⑮ 打饭窗口（长 8 m）** `furn_food_window` — 占地 8.0×0.9 m，画布 **192×56**

```
像素风食堂打饭窗口，单一物件，正面朝下。不锈钢台面（浅灰 + 白色高光条），
上方玻璃挡板（半透明感用浅青灰实色块表现），台面上四个方形菜盆
（分别装红、绿、黄、棕色的菜），后面一排浅灰保温柜。192×56 像素，无描边，透明背景，无文字。
```

**⑯ 长餐桌（东）** `furn_table_e` — 占地 5.0×1.4 m，画布 **120×56**

```
像素风食堂长餐桌，单一物件，3/4 俯视。浅木色桌面、深灰金属桌腿，两侧各一条木长凳，
桌面放两个餐盘和一个不锈钢碗。120×56 像素，无描边，透明背景，无文字。
```

**⑰ 长餐桌（西）** `furn_table_w` — 占地 5.0×1.4 m，画布 **120×56**

```
同上风格长餐桌，桌面更空，只留一个餐盘和一杯水。120×56 像素，无描边，透明背景。
```

---

## 5. 交付与落位

| 类别 | 数量 | 命名 | 尺寸 |
| --- | --- | --- | --- |
| 地板 | 5 | `assets/interior/<building>/floor.png` | 64×64 无缝 |
| 墙面 | 5 | `assets/interior/<building>/wall.png` | 64×72 无缝 |
| 家具 | 17 | `assets/interior/<building>/furn_<id>.png` | 见 §4 每条的画布尺寸 |

`<building>` 取值：`dorm` / `classroom` / `library` / `clubroom` / `canteen`；
`<id>` 取自 `content/world/map.json` 的 `furniture[].id` 去掉 `furn_` 前缀后的名字（如 `furn_bed` → `bed`）。

**交付前自查**

1. 透明背景：四角 alpha = 0，且没有白色/棋盘格残留；
2. 颜色数 ≤ 32，且都在 §0.1 的色板里（用 `tools/` 的量化脚本核对）；
3. 画布尺寸与 §4 完全一致，物件**底边贴画布底边**；
4. 地板/墙面能 2×2 平铺看不出接缝（把 4 张拼一起看）；
5. 画面里没有任何可读文字；
6. 文件名全小写、与表一致。

---

## 6. 给 A 的备注（接图后要做的事）

1. 室内现在是**纯色盒子**（`game/world/interior_scene.py`：地板 `FLOOR_COLOR`、墙 `BUILDING_COLOR`、家具 `FURNITURE_COLOR`）。
   接入这批图需要把 `make_ground` 换成正贴图 + 家具从 `make_box` 换成 `make_prop_card`（占地区域仍用 map.json 的 rect 做碰撞）。
2. 新增 manifest 条目：`interior_<building>_floor` / `_wall` / `furn_<building>_<id>`，许可证按来源登记（自制填 `LIC-0210`）。
3. 家具卡片的高度 = 物体真实高度（默认 1 m），衣柜/书架 2 m；渲染时按占地宽度缩放，避免比例失真。
