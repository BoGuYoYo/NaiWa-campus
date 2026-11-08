# 美术与音频规格说明（A 维护）

## 1. 全局规格

| 项目 | 规定 |
| --- | --- |
| 像素密度 | 每米 24 像素，场景纹理与角色共用，禁止混用 |
| 调色板 | `assets/palette.png`，32 色，`tools/make_placeholders.py` 的 `PALETTE` 是唯一来源 |
| 描边 | 角色/NPC 1 像素，颜色 `#2B2235`；场景物体不描边 |
| 方向顺序 | `s se e ne n nw w sw`（s 表示面朝镜头） |
| 角色帧 | 48×48，脚点 pivot `(24,46)`，身高约 38 像素（≈1.6 米） |
| 文件格式 | PNG RGBA 8 位，透明像素 RGB 置 0，禁止嵌入色彩配置 |
| 阴影 | `char_shadow` 24×8 椭圆，黑色 40% 不透明度，是唯一允许半透明的贴图 |
| 模型 | Blender 4.x → glTF 2.0 → `tools/gltf_to_bam.py`；单栋建筑 ≤ 800 三角面，室外 ≤ 30,000 |
| 模型纹理 | 边长 2 的幂（64～512），最近邻，不生成 mipmap |
| 音频 | BGM：OGG Vorbis 44.1kHz 立体声、60～120 秒可无缝循环、约 -16 LUFS；SFX：单声道，峰值 ≤ -3 dBFS |

## 2. 当前资源状态（第 1 周）

| 资源 | 状态 | 来源 |
| --- | --- | --- |
| `char_naiwan_walk` / `char_naiwan_idle` | **正式**（`LIC-0001`） | 用户提供的单方向序列帧 + `待机图.jfif`，经 `tools/slice_reference_sheets.py` 切片 |
| `portrait_naiwan_*`（8 张） | **正式**（`LIC-0006`） | 用户提供的 `素材/小表情/`，经 `tools/import_generated_art.py` 落位 |
| `cg_naiwan_*`（9 张） | **正式**（`LIC-0006`） | 用户提供的 `素材/场景/`，同一工具落位 |
| 其余全部美术与音频 | 同尺寸占位资源 | `tools/make_placeholders.py` 程序生成 |

## 2.1 当前角色规格（2026-11-08 素材更新后）

| 项 | 值 |
| --- | --- |
| 行走表 | `walk.png` 384×384：**8 帧** × 8 方向，8 fps |
| 待机表 | `idle.png` 144×384：3 帧 × 8 方向，3 fps（来自 `素材/待机图.jfif`） |
| 单帧 | 48×48，脚点 (24,46)，实测身高 39～42 像素 |
| 头像 | `portraits/naiwan/<表情>.png` 96×96：neutral happy sad **angry** surprised **speechless** shy proud |
| 活动插图 | `art/cg/naiwan_<活动>.png` 160×90，9 个活动各一张 |

> 表情 ID 在 2026-11-08 调整：用户实际交付的是 `生气/无语`，因此
> `portrait_naiwan_tired` → `portrait_naiwan_angry`、`portrait_naiwan_determined` →
> `portrait_naiwan_speechless`（旧 ID 已从 manifest 移除，`game/core` 无任何硬编码引用）。

`walk.png` 从 A8 表的 4 帧（192×384）升级到 8 帧（384×384）：新素材本身就是 8 帧循环，
丢掉一半会破坏接触—经过的节奏。行宽由 `manifest.json` 的 `cols` 驱动，App/渲染层不做硬编码。

切片的完整流程（可重复执行，结果稳定）：

```powershell
python tools/slice_reference_sheets.py --verify   # 只输出 build/_slice_contact_{walk,idle}.png 核对图
python tools/slice_reference_sheets.py            # 写入 assets/characters/naiwan/{walk,idle}.png
python tools/slice_reference_sheets.py --idle-source "..\素材\待机.jfif"   # 有专门待机图时
```

切片做的处理（每一步都能在脚本里查到）：

1. 素材识别：按文件名关键字把 8 张图映射到方向（向前→s、右前→se、向右→e、右后→ne、
   向后→n、左后→nw、向左→w、左前→sw），缺方向或少文件会直接报错；
2. 面板定位：黄色身体掩码 → 1/4 降采样连通域 → 按行/列排序成 FRAME 01～08（杂乱小块按面积过滤）；
3. 抠背景：从 bbox 边界对灰色背景洪水填充，3×3 开闭去噪，再按“贴着身体 + 面积占比”保留
   分离的手臂/脚（只留最大连通域会把背面视图的胳膊吃掉）；
4. 缩放：整张表统一用一个 `scale` 做面积（BOX）缩放——新素材的放大倍数不是整数（≈15.3），
   块众数会随网格漂移把眼睛和描边吃掉；
5. 落位：身高归一到 38 像素、脚点 (24,46)、加 1 像素 `#2B2235` 描边、量化到 32 色、
   透明像素 RGB 置 0；
6. 待机：没有待机素材时用各方向行走首帧 + 1 像素呼吸位移（3 帧）；有 `--idle-source` 就用它。

### 头像与活动插图的落位（`tools/import_generated_art.py`）

```powershell
python tools/import_generated_art.py --all --verify   # 只出核对图 build/_cg_final.png / _portraits_final.png
python tools/import_generated_art.py --all            # 写入 assets/art/cg 与 assets/portraits/naiwan
```

- **场景**：2752×1536 居中裁成 16:9 → 面积缩放到 160×90 → 自适应量化 64 色（插图细节多，
  不套用 32 色角色板）；
- **表情**：1024×1024 抠灰底（边界洪水填充 + 最大连通域）→ 按**肩宽**归一裁剪成半身像
  （8 张站姿不同，按 bbox 高度裁会让头像忽大忽小）→ 缩到 96×96 → 量化 32 色 → 透明像素 RGB 置 0。

游戏里已经接上：`game/app.py` 的替身 `ResultPanel` 会按 `cg_naiwan_<activity_id>` 显示活动插图
（缺失时 registry 自动回退占位图），文本与插图分居左下 / 中上，互不遮挡。

### 校园模型（`tools/build_campus_models.py`）

用户提供的等距参考图（`素材/建筑/`：宿舍楼、教学楼、图书馆、社团、饭堂、12 个道具、草地1）
已经转成可运行的低多边形模型，**纯顶点色、无贴图**：

```powershell
python tools/build_campus_models.py          # 写入 assets/campus/*.bam
```

| 模型 | 三角面 | 造型要点（对照参考图） |
| --- | --- | --- |
| `dorm` | 454 | 三层冷灰墙、砖红双坡屋顶 + 3 个老虎窗、屋顶水箱（8 边）+ 天线 + 小烟囱、阳台/晾衣杆、雨棚台阶 |
| `teaching` | 388 | 四层 U 形、奶油墙 + 横向窗带、红色女儿墙、中央钟塔 + 圆钟、旗杆红旗、屋顶空调箱 |
| `library` | 252 | 三层方体 + 转角石块、四坡屋顶 + 采光脊、通高中央窗、四柱门廊 + 宽台阶 |
| `club` | 170 | 两层灰绿、红女儿墙、屋顶招牌（双柱）、彩虹雨棚、底层大玻璃 |
| `canteen` | 270 | 单层赭黄、非对称双坡屋顶、三根不锈钢排烟管、四柱深挑檐、外侧售餐台 |
| `ground` | 84 | 80×45 草地 + 南北主路（世界 x 38~44）+ 东西支路（世界 y 6~11）+ 4 块深色草斑 |
| 12 个道具 | 24~84 | 树/路灯/长椅/围栏/告示牌/花坛/垃圾桶/车架/旗杆/石头/花圃/路面 |

合计 **2,900 三角面**（室外预算 30,000），单栋最大 454（预算 800）。

- 命名 `mesh_*`、原点在占地西南角、Z 向上、1 单位 = 1 米；
- 没有法线（= 引擎不参与光照，颜色直出），符合像素风平涂；
- 碰撞体不在模型里，`content/world/map.json` 由 C 提供；
- `game/app.py` 的替身校园已按 `BUILDINGS` 表摆放这 5 栋 + 18 个道具，模型缺失时自动退回占位方块。
- **待办**：建筑占地目前是 A 的布景值，等 C 的地图表定稿后需要对齐（`docs/integration/week-1.md` 已登记）。

注意：`tools/make_placeholders.py art` 会跳过 `FINAL_ASSETS`（`walk.png`、`idle.png`），
不会被占位图覆盖回去。要恢复占位图必须先手动删除这两张正式资源。

占位资源清单（其余部分仍需按 A9 重绘）：

清单（与 `assets/manifest.json` 一致，共 109 条）：

| 类别 | 数量 | 规格 | 状态 |
| --- | --- | --- | --- |
| `char_naiwan_walk` | 1 | 384×384，8 帧 × 8 方向，8 fps | 正式（切片） |
| `char_naiwan_idle` | 1 | 144×384，3 帧 × 8 方向，3 fps | 正式（切片） |
| `char_shadow` | 1 | 24×8 | 占位 |
| `portrait_naiwan_*` | 8 | 96×96（neutral happy sad angry surprised speechless shy proud） | 正式（生成落位） |
| `cg_naiwan_*` | 9 | 160×90（9 个活动插图） | 正式（生成落位） |
| `char_npc_*_idle` | 3 | 96×192，2 帧 × 4 方向（s e n w），2 fps | 占位 |
| `portrait_npc_*` | 12 | 96×96，每人 4 个表情 | 占位 |
| `char_extra_*` | 4 | 48×48 单帧 s 方向 | 占位 |
| `model_*` | 5 + 5 + 1 + 12 | 5 栋建筑、5 个室内、地面、12 种道具 | 正式（程序建模，`LIC-0207`） |
| `ui_*` | 29 | 九宫格面板 48×48（边距 16）×1、属性图标 16×16 ×6、活动图标 16×16 ×9、按键提示 16×16 ×8、时段点 8×8 ×2、血条框/填充 100×8 ×2、光标 8×8 ×1 | 占位 |
| `palette` | 1 | 128×64（32 色 × 16px） | 定稿 |
| `font_ui` | 1 | Fusion Pixel 12px（**待放入**，见下） | 待补 |
| `bgm_*` / `sfx_*` | 4 / 12 | OGG Vorbis | 合成占位 |

### 9 张活动插图与活动名对照（`cg_naiwan_*`，160×90）

| asset_id | 活动 ID | 显示名 | 画面内容 |
| --- | --- | --- | --- |
| `cg_naiwan_attend_class` | `attend_class` | 上课 | 教室、黑板、课桌 |
| `cg_naiwan_library_study` | `library_study` | 图书馆学习 | 书架、台灯、书 |
| `cg_naiwan_play_games` | `play_games` | 打游戏 | 显示器、手柄 |
| `cg_naiwan_create_work` | `create_work` | **敲代码** | 双屏代码窗口、笔记本、咖啡 |
| `cg_naiwan_join_club` | `join_club` | 参加社团 | 横幅、活动室 |
| `cg_naiwan_exercise` | `exercise` | 锻炼 | 跑道、球 |
| `cg_naiwan_eat_canteen` | `eat_canteen` | 食堂用餐 | 餐盘、饭桌 |
| `cg_naiwan_rest_dorm` | `rest_dorm` | 宿舍休息 | 床铺、被子 |
| `cg_naiwan_campus_walk` | `campus_walk` | 校园闲逛 | 林荫道、路灯 |

> 2026-11-07 变更：`create_work` 的语义由「创作（画画）」调整为「敲代码」。
> 活动 ID 保持不变（ID 冻结原则，文件仍叫 `create_work`），只改显示名、插图与图标
> （`ui/icons/activity_create_work.png` 从画笔改为终端 + 代码行）。
> 结局 `ending_creator` 的文案建议一并改成「独立开发者」口径，由 B/D 在内容 JSON 里落实。

## 3. 正式素材替换流程（每人只需覆盖同名文件）

1. 在 `docs/art/frames/<asset>/` 下画单帧，命名 `<方向>_<序号>.png`（例如 `ne_3.png`）；
2. 用打包脚本生成精灵表与预览：

```powershell
python tools/pack_sprites.py --input docs/art/frames/naiwan_walk `
    --output assets/characters/naiwan/walk.png --cols 4 --frame 48x48 `
    --preview docs/art/preview/naiwan_walk.gif --max-colors 12
```

3. 更新 `assets/LICENSES.csv`（作者、来源、许可、是否修改、日期、AI 工具与条款版本）；
4. `python tools/make_placeholders.py check` 必须零缺失零未登记；
5. `python -m tests.standalone_a --check-assets` 复验，再提合并请求。

## 4. 角色比例参考

`docs/art/naiwan_ref.png` 来自用户提供的三视图（`naiwan_ref_source.jfif`，AI 生成，**仅作参考，
不进入发布包**）。比例要点：蛋形圆身、奶油色肚皮占下半身约 2/3、四肢深橄榄色、眼睛靠近头顶。
切片后的正式行走表见 `docs/art/preview/naiwan_walk.gif`（4 帧 × 8 方向循环）。

## 5. 字体（待办）

`assets/fonts/FusionPixel12.ttf`（SIL OFL 1.1，`LIC-0301`）尚未放入仓库。放入前：

- D 的 `TextDB` 使用 `AssetRegistry.load_font("font_ui")`，返回 `None` 时回退引擎默认字体，
  日志会出现 `[ASSET] missing id=font_ui`；
- 中文字符缺字体时 Panda3D 会打印 `:text(warning): No definition in ... for character U+....`，
  A 的替身场景因此全部改用 ASCII 标签。
