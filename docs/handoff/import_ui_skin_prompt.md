# 交给另一个 AI 的任务提示词：导入 UI 皮肤资源

> 用法：把下面 **从「你是本仓库的…」开始到结尾** 的整段内容，原样发给执行任务的 AI（Cursor / Claude Code / Codex 都行）。
> 前提：用户已经把 29 张 `ui_*` 图放进 `素材/UI/`（文件名 = `asset_id`.png）。

---

你是本仓库的开发者 A（技术负责人），负责**资源管线**。任务只有一件：把用户新生成的 UI 皮肤图
导入仓库、登记许可、验证能在游戏里生效。**不要改玩法代码，不要改别人负责的模块。**

## 0. 环境与红线

- 仓库：`C:\Users\huang\Desktop\奶娃\naiwa_campus`
- Python：`C:\Users\huang\Desktop\奶娃\.venv-naiwa\Scripts\python.exe`（Panda3D 1.10.16 + Pillow + numpy）
- 源码素材（只读，绝不修改）：`C:\Users\huang\Desktop\奶娃\素材\UI\`
- 只能改这些位置：`assets/ui/**`、`assets/manifest.json`、`assets/LICENSES.csv`、
  `tools/import_ui_skin.py`（新建）、`docs/art/**`、`reports/review/**`
- **禁止修改**：`game/ui/*.py`（D 负责）、`game/world/*.py`（C 负责）、`game/systems/*`（B 负责）、
  `game/app.py`、`game/core/*`、`content/**`。发现这些地方有问题 → 写进报告，不要动。
- 不改任何已有 `asset_id` 与 `path`；只替换 `assets/ui/**` 下的图片文件本体。

## 1. 先读这几份（按顺序，别跳）

1. `assets/manifest.json` —— 29 个 `ui_*` 条目的 id / path
2. `docs/art/README.md` —— 美术总规格（调色板、描边、格式）
3. `docs/art/ui_skin_prompts.md` —— 这 29 张图应该长什么样（尺寸、4 色、构图）
4. `tools/import_campus_props.py` —— **参考实现**，抠图/裁切/缩放/量化的写法照它来
5. `tools/make_placeholders.py` 里的 `PALETTE` —— 32 色调色板是唯一来源
6. `docs/CHANGELOG_API.md` §9 —— 资源与接口的变更登记惯例

## 2. 输入与目标（严格按这张表）

源文件命名：`素材/UI/<asset_id>.png`（例如 `素材/UI/ui_icon_academic.png`）。

| # | asset_id | 目标路径 | 目标尺寸 | 处理要点 |
| --- | --- | --- | --- | --- |
| 1 | `ui_panel_9slice` | `ui/panel_9slice.png` | 48×48 | 九宫格：四角必须一致，中间 1/3 纯色，边距 16 |
| 2 | `ui_icon_academic` | `ui/icons/academic.png` | 16×16 | 学士帽，4 色 |
| 3 | `ui_icon_stamina` | `ui/icons/stamina.png` | 16×16 | 哑铃，4 色 |
| 4 | `ui_icon_mood` | `ui/icons/mood.png` | 16×16 | 粉色心形 |
| 5 | `ui_icon_social` | `ui/icons/social.png` | 16×16 | 双点气泡 |
| 6 | `ui_icon_interest` | `ui/icons/interest.png` | 16×16 | 紫色四角星 |
| 7 | `ui_icon_energy` | `ui/icons/energy.png` | 16×16 | 金色闪电 |
| 8 | `ui_icon_attend_class` | `ui/icons/activity_attend_class.png` | 16×16 | 黑板 |
| 9 | `ui_icon_library_study` | `ui/icons/activity_library_study.png` | 16×16 | 三本书 |
| 10 | `ui_icon_play_games` | `ui/icons/activity_play_games.png` | 16×16 | 手柄 |
| 11 | `ui_icon_create_work` | `ui/icons/activity_create_work.png` | 16×16 | **终端 + 代码行**（不是画笔） |
| 12 | `ui_icon_join_club` | `ui/icons/activity_join_club.png` | 16×16 | 社团旗 |
| 13 | `ui_icon_exercise` | `ui/icons/activity_exercise.png` | 16×16 | 跑道 |
| 14 | `ui_icon_eat_canteen` | `ui/icons/activity_eat_canteen.png` | 16×16 | 饭碗+筷子 |
| 15 | `ui_icon_rest_dorm` | `ui/icons/activity_rest_dorm.png` | 16×16 | 床 |
| 16 | `ui_icon_campus_walk` | `ui/icons/activity_campus_walk.png` | 16×16 | 石板路脚印 |
| 17–19 | `ui_key_e` `ui_key_w` `ui_key_a` | `ui/keys/{e,w,a}.png` | 16×16 | 单字母键帽 |
| 20–21 | `ui_key_s` `ui_key_d` | `ui/keys/{s,d}.png` | 16×16 | 单字母键帽 |
| 22 | `ui_key_space` | `ui/keys/space.png` | 16×16 | 长条键帽 + `SPACE` |
| 23 | `ui_key_tab` | `ui/keys/tab.png` | 16×16 | `TAB` |
| 24 | `ui_key_esc` | `ui/keys/esc.png` | 16×16 | `ESC` |
| 25 | `ui_slot_full` | `ui/slot_full.png` | 8×8 | 实心金色圆点 |
| 26 | `ui_slot_empty` | `ui/slot_empty.png` | 8×8 | 空心灰蓝圆点 |
| 27 | `ui_bar_frame` | `ui/bar_frame.png` | 100×8 | 条的外框，左右端固定 |
| 28 | `ui_bar_fill` | `ui/bar_fill.png` | 100×8 | 条的填充，横向可平铺 |
| 29 | `ui_cursor` | `ui/cursor.png` | 8×8 | 金色三角光标 |

用户可能只生成了一部分。**缺的就跳过并记进报告**，不要用占位图覆盖，也不要新建 id。

## 3. 处理规则（每条都要遵守）

1. **去背**：只处理透明背景图。若源图是白底/棋盘底，用「从四边泛洪」去掉与边界连通的背景色
   （参考 `tools/import_campus_props.py::_flood_background`）。**不要用全局色键**——图标内部
   也有接近白色的部分。已经带 alpha 的图直接沿用它，不要重抠。
2. **缩放**：一律 `Image.Resampling.NEAREST` 缩到目标尺寸；**禁止** LANCZOS/BICUBIC（会糊边）。
   若源图不是目标尺寸的整数倍，先整数倍裁剪对齐再缩，避免半像素。
3. **量化**：量化到 `assets/palette.png` 的 32 色（用 `PIL.Image.quantize(palette=...)`，
   或取 `make_placeholders.PALETTE` 自己做最近色映射）。量化后允许保留 alpha 通道。
4. **透明像素**：`alpha == 0` 的像素把 RGB 全部置 0（否则放大时会出黑边/白边）。
5. **格式**：PNG RGBA 8 位，`optimize=True`，不写 ICC/EXIF。
6. **面板 `ui_panel_9slice` 额外校验**：四角像素必须两两镜像相同；中间 32×32 区域必须单色
   （允许 ±2 的色差）。不满足就报 `PANEL_NOT_SLICEABLE`，不要硬缩。
7. **数值条 `ui_bar_frame` / `ui_bar_fill`**：左 2 px 与右 2 px 必须列相同（可拉伸），
   不满足报 `BAR_NOT_TILEABLE`。
8. **键帽字母**：如果源图不含字母，允许用 Pillow 的像素字体把字母烧上去（`ImageDraw.text`，
   字号 5–7 px，颜色 `#FFF6DF`，居中）；如果源图自带字母，逐个核对拼写（E/W/A/S/D/TAB/ESC/SPACE）。

## 4. 要写的工具

新建 `tools/import_ui_skin.py`，结构照 `tools/import_campus_props.py`：

```
python tools/import_ui_skin.py --source "..\素材\UI"          # 导入（默认全部）
python tools/import_ui_skin.py --only ui_icon_mood            # 只导一张
python tools/import_ui_skin.py --verify                       # 只校验，退出码 0/1
```

要求：

- 输入缺失时打印 `SKIP <asset_id>（源文件不存在）` 并继续，退出码 0；
- 每张处理完打印一行 `OK <asset_id> 1920x1080 -> 16x16 colors=12`；
- `--verify` 输出表格：`asset_id | 尺寸 | 颜色数 | 有 alpha | 四角对称 | 结论`，
  任一不通过退出码 1；
- **幂等**：重复运行结果一致；不删除 `assets/ui/` 下未登记的文件；
- 生成一张对照图 `reports/review/ui_skin_sheet.png`：29 张成品按 8 列排开、深色底 `#1B1F2A`、
  每张放大 4 倍最近邻，方便人眼验收。

## 5. 登记

### 5.1 `assets/manifest.json`

- 29 条已存在，**只更新 `tags`**（若原来是 `["placeholder"]`，改成 `["final","ui","generated_from_user_art"]`）；
- `license_id` 全部改成 `LIC-0210`；
- 不要改动 `id` / `type` / `path` 三个字段，不要重排 JSON 顺序（追加/替换用顺序保留的方式写回）。
- 写完自检：`len(assets) == 119`，且 29 个 `ui_*` 条目 path 全部存在。

### 5.2 `assets/LICENSES.csv`

追加一行（表头固定 9 列，字段含逗号要加引号，**行尾用 CRLF**）：

```
LIC-0210,<29 个 ui_* 用分号连接>,用户提供的 AI 生成素材（UI 皮肤）,素材/UI/,用户提供的 AI 生成素材（生成工具与条款版本见素材来源说明）,yes,yes,<今天日期>,由 tools/import_ui_skin.py 去背/最近邻缩放/量化到 32 色；面板 48×48 边距 16、图标 16×16、键帽 16×16、点 8×8、条 100×8
```

## 6. 验证（缺一条都算没做完）

```powershell
cd C:\Users\huang\Desktop\奶娃\naiwa_campus
$py = "C:\Users\huang\Desktop\奶娃\.venv-naiwa\Scripts\python.exe"

& $py tools/import_ui_skin.py --verify                 # 期望 exit 0
& $py -m pytest tests -q                               # 期望 308 passed
& $py -m game --dev --scene CampusScene --skip-intro --offscreen --frames 60
                                                       # 期望 exit 0，日志无 [ASSET] missing id=ui_
& $py -m tests.standalone_d --screen all --out reports/standalone/D/screens
                                                       # 期望 exit 0，8 张图
& $py -m tests.standalone_d --text-check               # 期望 exit 0
```

再打开 `reports/standalone/D/screens/hud.png`、`tab.png`、`main_menu.png` 三张，肉眼确认：
图标不糊、文字没被皮肤吃掉、面板边框没有拉伸断裂。

## 7. 提交

一个提交，信息格式：

```
A(art): 导入 29 个 UI 皮肤资源并登记许可

- tools/import_ui_skin.py：去背/最近邻缩放/32 色量化/校验
- assets/ui/**：替换为用户生成图（<N> 张）
- manifest 29 条改为 final + LIC-0210；LICENSES 追加 LIC-0210
- reports/review/ui_skin_sheet.png：29 张对照图
- 验证：import --verify / pytest 308 / 校园离屏 / standalone_d 截图
```

提交前 `git status` 确认**只**包含上面列出的路径；不要把 `build/`、`.blend`、`__pycache__` 带进去。

## 8. 报告格式（最后必须给）

1. 处理结果表：`asset_id / 源尺寸 / 目标尺寸 / 颜色数 / 结论`
2. 跳过清单（缺图）、失败清单（尺寸不符、面板不可切片、条不可平铺）
3. 验证命令的输出摘要（4 条命令的 exit code + 关键行）
4. 已知限制：
   - 现有 `UIPanel`（`game/ui/widgets.py`）是「整图拉伸 + 面板底色着色 + 内衬」，
     **不是真正的九宫格**；换成真 9-slice 属于 A 的后续改动，本次不要动 D 的文件。
   - `ui_cursor` 目前 UI 里没用到（菜单光标是文本 `>`），接上去也是后续 1 行改动。
   - 字体仍是系统回退（`font_ui` 缺失），UI 中文靠 `AssetRegistry.load_ui_font()`。
